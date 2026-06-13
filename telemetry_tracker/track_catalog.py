"""Track catalog helpers for Forza telemetry tracker."""

from __future__ import annotations

import json
import math
import re
import struct
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

TRACK_INFO_DATASET_PATH = "source/ScribbleData/13260499414882115191.om.xml"
CAREER_TRACK_INFO_STRING_TABLE = "CareerTrackInfo.str"
LOCAL_TRACK_CATALOG_SOURCE = "fh6_local_files"

_TRACK_STRING_KEY_RE = re.compile(
    r"IDS_(?:Description|DisplayName|ShortDisplayNameAllCaps|ShortDisplayName)_[0-9a-fA-F]{32}$"
)
_ROUTE_FILE_RE = re.compile(r"^route(\d+)$", re.IGNORECASE)
_AI_TRACK_ROUTE_FILE_RE = re.compile(r"^Route(\d+)\.owt$", re.IGNORECASE)
_TRANSFORM_KEY_RE = re.compile(r"^value\._(\d)(\d)$")
_AI_TRACK_MAGIC = b"FTWO"
_AI_TRACK_ROUTE_POINT_HEADER_BYTES = 0x60
_AI_TRACK_ROUTE_POINT_COUNT_OFFSET = 0x24
_AI_TRACK_ROUTE_POINT_STRIDE_BYTES = 0x38
_AI_TRACK_ROUTE_POINT_SPACING_METERS = 25.0


@dataclass(frozen=True)
class BxmlNode:
    tag: str
    attrs: dict[str, str]
    children: list["BxmlNode"]


@dataclass(frozen=True)
class LocalFH6TrackCatalog:
    tracks: list[dict]
    map_regions: list[dict]
    locators: list[dict]


class _BxmlParser:
    """Minimal BXML reader for FH6 ObjectModelGame ScribbleData files."""

    def __init__(self, raw: bytes):
        if raw[:4] != b"BXML":
            raise ValueError("not a BXML object model file")
        self._raw = raw
        self._offset = 5
        string_count = self._read_u32()
        string_table_length = self._read_u32()
        string_table_end = self._offset + string_table_length
        self._strings: list[str] = []
        for _ in range(string_count):
            length = self._read_u16()
            value = raw[self._offset : self._offset + length].decode("utf-8", errors="replace")
            self._offset += length
            self._strings.append(value)
        if self._offset != string_table_end:
            self._offset = string_table_end
        self._index_size = 1 if string_count <= 255 else 2

    def parse(self) -> BxmlNode:
        return self._read_node()

    def _read_u16(self) -> int:
        value = int.from_bytes(self._raw[self._offset : self._offset + 2], "little")
        self._offset += 2
        return value

    def _read_u32(self) -> int:
        value = int.from_bytes(self._raw[self._offset : self._offset + 4], "little")
        self._offset += 4
        return value

    def _read_string_index(self) -> int:
        if self._index_size == 1:
            value = self._raw[self._offset]
            self._offset += 1
            return value
        value = int.from_bytes(self._raw[self._offset : self._offset + 2], "little")
        self._offset += 2
        return value

    def _read_attrs(self) -> dict[str, str]:
        attr_count = self._raw[self._offset]
        self._offset += 1
        attrs: dict[str, str] = {}
        for _ in range(attr_count):
            key_index = self._read_string_index()
            value_index = self._read_string_index()
            attrs[self._strings[key_index]] = self._strings[value_index]
        return attrs

    def _read_node(self) -> BxmlNode:
        token = self._raw[self._offset]
        self._offset += 1
        if token == 1:
            return self._read_node()
        if token == 7:
            tag = self._strings[self._read_string_index()]
            attrs = self._read_attrs()
            child_count = self._read_u16()
            return BxmlNode(tag, attrs, [self._read_node() for _ in range(child_count)])
        if token == 5:
            tag = self._strings[self._read_string_index()]
            child_count = self._read_u16()
            return BxmlNode(tag, {}, [self._read_node() for _ in range(child_count)])
        if token == 3:
            tag = self._strings[self._read_string_index()]
            attrs = self._read_attrs()
            return BxmlNode(tag, attrs, [])
        raise ValueError(f"unsupported BXML token {token} at payload offset {self._offset - 1}")


def parse_bxml(raw: bytes) -> BxmlNode:
    return _BxmlParser(raw).parse()


def _walk_nodes(node: BxmlNode) -> Iterable[BxmlNode]:
    yield node
    for child in node.children:
        yield from _walk_nodes(child)


def _find_object(node: BxmlNode, object_type: str) -> BxmlNode | None:
    for candidate in _walk_nodes(node):
        if candidate.tag == "object" and candidate.attrs.get("type") == object_type:
            return candidate
    return None


def _find_objects(node: BxmlNode, object_type: str) -> list[BxmlNode]:
    return [
        candidate
        for candidate in _walk_nodes(node)
        if candidate.tag == "object" and candidate.attrs.get("type") == object_type
    ]


def _properties(node: BxmlNode) -> dict[str, str]:
    values: dict[str, str] = {}
    for child in node.children:
        if child.tag == "property" and "id" in child.attrs and "value" in child.attrs:
            values[child.attrs["id"]] = child.attrs["value"]
    return values


def _property_node(node: BxmlNode, property_id: str) -> BxmlNode | None:
    for child in node.children:
        if child.tag == "property" and child.attrs.get("id") == property_id:
            return child
    return None


def _int_or_none(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _float_or_none(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _bool_or_none(value: object) -> bool | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return None


def _valid_table_string(value: bytes) -> str | None:
    if len(value) > 1000:
        return None
    try:
        text = value.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if not text:
        return None
    if "\ufffd" in text:
        return None
    if any(ord(char) < 32 for char in text):
        return None
    if not all(char.isprintable() for char in text):
        return None
    return text


def _value_block_candidate(raw: bytes, start: int, end: int, count: int) -> tuple[float, list[str]] | None:
    values: list[str] = []
    position = start
    for _ in range(count):
        terminator = raw.find(b"\x00", position, end)
        if terminator < 0:
            return None
        text = _valid_table_string(raw[position:terminator])
        if text is None:
            return None
        values.append(text)
        position = terminator + 1
    total_chars = sum(max(1, len(value)) for value in values)
    printable_chars = sum(sum(char.isprintable() for char in value) for value in values)
    long_value_bonus = sum(min(len(value), 80) for value in values) / max(1, len(values)) / 1000.0
    return (printable_chars / total_chars) + long_value_bonus, values


def _null_terminated_entries(raw: bytes) -> list[tuple[int, str]]:
    entries: list[tuple[int, str]] = []
    position = 0
    for part in raw.split(b"\x00"):
        start = position
        position = start + len(part) + 1
        text = _valid_table_string(part)
        if text is not None:
            entries.append((start, text))
    return entries


def parse_career_track_info_string_table(raw: bytes) -> dict[str, str]:
    """Parse FH6 CareerTrackInfo.str into key and table-qualified key mappings."""

    entries = _null_terminated_entries(raw)
    keys = [(offset, text) for offset, text in entries if _TRACK_STRING_KEY_RE.fullmatch(text)]
    if not keys:
        return {}

    keys.sort(key=lambda item: item[0])
    first_key_offset = keys[0][0]
    candidate_starts = [0]
    candidate_starts.extend(
        index + 1
        for index, byte in enumerate(raw[:first_key_offset])
        if byte == 0 and index + 1 < first_key_offset
    )

    best: tuple[float, list[str]] | None = None
    for start in candidate_starts:
        candidate = _value_block_candidate(raw, start, first_key_offset, len(keys))
        if candidate is None:
            continue
        if best is None or candidate[0] > best[0]:
            best = candidate
    if best is None:
        return {}

    values = best[1]
    resolved: dict[str, str] = {}
    for (_, key), value in zip(keys, values, strict=False):
        resolved[key] = value
        resolved[f"CareerTrackInfo.{key}"] = value
    return resolved


def _load_career_track_strings(media_root: Path) -> dict[str, str]:
    string_table_zip = media_root / "Stripped" / "StringTables" / "EN.zip"
    if not string_table_zip.exists():
        return {}
    try:
        with zipfile.ZipFile(string_table_zip) as archive:
            raw = archive.read(CAREER_TRACK_INFO_STRING_TABLE)
    except (OSError, KeyError, zipfile.BadZipFile):
        return {}
    return parse_career_track_info_string_table(raw)


def _resolve_string(key: str | None, strings: dict[str, str]) -> str | None:
    if not key:
        return None
    if key in strings:
        return strings[key]
    unqualified = key.rsplit(".", 1)[-1]
    return strings.get(unqualified)


def _track_records_from_dataset_node(
    dataset_node: BxmlNode,
    strings: dict[str, str],
    source_file: str,
) -> list[dict]:
    data_node = _property_node(dataset_node, "Data")
    if data_node is None:
        return []

    records: list[dict] = []
    for map_element in data_node.children:
        if map_element.tag != "map_element":
            continue
        key_node = next((child for child in map_element.children if child.tag == "key"), None)
        value_node = next((child for child in map_element.children if child.tag == "value"), None)
        if key_node is None or value_node is None:
            continue
        dataset_key = _int_or_none(key_node.attrs.get("value"))
        if dataset_key is None:
            continue
        values = _properties(value_node)
        display_key = values.get("DisplayName")
        short_key = values.get("ShortDisplayName")
        short_caps_key = values.get("ShortDisplayNameAllCaps")
        description_key = values.get("Description")
        records.append(
            {
                "track_key": f"track-info:{dataset_key}",
                "source_dataset_key": dataset_key,
                "route_id": _int_or_none(values.get("RouteId")),
                "custom_route_id": _int_or_none(values.get("CustomRouteId")),
                "media_track_id": _int_or_none(values.get("MediaTrackId")),
                "media_track_name": values.get("MediaTrackName"),
                "ribbon_config": values.get("RibbonConfig"),
                "display_name": _resolve_string(display_key, strings),
                "short_display_name": _resolve_string(short_key, strings),
                "short_display_name_all_caps": _resolve_string(short_caps_key, strings),
                "description": _resolve_string(description_key, strings),
                "display_name_key": display_key,
                "short_display_name_key": short_key,
                "short_display_name_all_caps_key": short_caps_key,
                "description_key": description_key,
                "route_activation_trigger_zone_name": values.get("RouteActivationTriggerZoneName"),
                "use_cross_country_ai": _bool_or_none(values.get("UseCrossCountryAI")),
                "stray_warning_distance": _float_or_none(values.get("StrayWarningDistance")),
                "stray_teleport_distance": _float_or_none(values.get("StrayTeleportDistance")),
                "source_file": source_file,
                "catalog_source": LOCAL_TRACK_CATALOG_SOURCE,
            }
        )
    return records


def _map_region_record_from_object(region_node: BxmlNode, source_file: str) -> dict | None:
    values = _properties(region_node)
    region_key = values.get("LocatorsCollectionName") or values.get("ENName") or region_node.attrs.get("id")
    if not region_key:
        return None
    return {
        "region_key": region_key,
        "english_name": values.get("ENName"),
        "english_short_name": values.get("ENShortName"),
        "japanese_name": values.get("JPName"),
        "japanese_short_name": values.get("JPShortName"),
        "name_key": values.get("Name"),
        "short_name_key": values.get("ShortName"),
        "locator_collection_name": values.get("LocatorsCollectionName"),
        "top_image_path": values.get("TopImagePath"),
        "map_tile_mascot_image": values.get("MapTileMascotImage"),
        "map_hover_fmod_event": values.get("MapHoverFMODEvent"),
        "first_time_enter_fmod_event": values.get("FirstTimeEnterFMODEvent"),
        "rich_presence_event": values.get("RichPresenceEvent"),
        "full_reveal_percentage": _int_or_none(values.get("FullRevealPercentage")),
        "announcement_ie_state": values.get("AnnouncementIEState"),
        "source_file": source_file,
        "catalog_source": LOCAL_TRACK_CATALOG_SOURCE,
    }


def _load_object_model_catalog(media_root: Path, strings: dict[str, str]) -> tuple[list[dict], list[dict]]:
    object_model_zip = media_root / "ObjectModelGame.zip"
    if not object_model_zip.exists():
        return [], []

    tracks: list[dict] = []
    regions_by_key: dict[str, dict] = {}
    try:
        with zipfile.ZipFile(object_model_zip) as archive:
            try:
                root = parse_bxml(archive.read(TRACK_INFO_DATASET_PATH))
            except (KeyError, ValueError):
                root = None
            if root is not None:
                dataset = _find_object(root, "TrackInfoDataSet")
                if dataset is not None:
                    tracks = _track_records_from_dataset_node(dataset, strings, TRACK_INFO_DATASET_PATH)

            for name in archive.namelist():
                if not name.endswith(".om.xml"):
                    continue
                try:
                    root = parse_bxml(archive.read(name))
                except (OSError, ValueError):
                    continue
                for region_node in _find_objects(root, "MapRegionData"):
                    record = _map_region_record_from_object(region_node, name)
                    if record is not None:
                        regions_by_key[record["region_key"]] = record
    except (OSError, zipfile.BadZipFile):
        return tracks, list(regions_by_key.values())
    return tracks, list(regions_by_key.values())


def _relative_media_path(path: Path, media_root: Path) -> str:
    try:
        return path.relative_to(media_root).as_posix()
    except ValueError:
        return path.as_posix()


def _locator_kind(locator_name: str, locator_collection: str) -> str:
    name = locator_name.lower()
    collection = locator_collection.lower()
    if collection.startswith("map_region_"):
        return "map_region"
    if name.startswith("start_line"):
        return "start_line"
    if name.startswith("finish_line"):
        return "finish_line"
    if name.startswith("arena"):
        return "arena"
    if "start" in name and "end" not in name:
        return "challenge_start"
    if "finish" in name or name.endswith("_end") or "end" in name:
        return "challenge_end"
    if "parking" in collection or "parking" in name:
        return "parking"
    if "pinata" in collection or "pinata" in name:
        return "pinata"
    if "barn" in name:
        return "barn_find"
    if "carmeet" in name or "car_meet" in name:
        return "car_meet"
    return "locator"


def _transform_dict(scene_transform: ET.Element | None) -> dict[str, float]:
    transform: dict[str, float] = {}
    if scene_transform is None:
        return transform
    for key, value in scene_transform.attrib.items():
        match = _TRANSFORM_KEY_RE.match(key)
        if not match:
            continue
        short_key = f"m{match.group(1)}{match.group(2)}"
        parsed = _float_or_none(value)
        if parsed is not None:
            transform[short_key] = parsed
    return transform


def _heading_yaw_rad(transform: dict[str, float]) -> float | None:
    m31 = transform.get("m31")
    m33 = transform.get("m33")
    if m31 is None or m33 is None:
        return None
    return math.atan2(m31, m33)


def parse_track_locator_file(path: Path, media_root: Path | None = None) -> list[dict]:
    """Parse a Brio trackroutes .nt locator file into DB-ready records."""

    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return []

    media_root = media_root or path.parents[3]
    source_file = _relative_media_path(path, media_root)
    locator_collection = path.stem
    route_match = _ROUTE_FILE_RE.match(locator_collection)
    route_id = int(route_match.group(1)) if route_match else None
    media_track_name = path.parents[1].name if path.parent.name.lower() == "trackroutes" else None

    records: list[dict] = []
    for locator in root.findall(".//Locator"):
        name_node = locator.find("Name")
        scene_transform = locator.find("SceneTransform")
        locator_name = name_node.attrib.get("value") if name_node is not None else None
        if not locator_name:
            continue
        transform = _transform_dict(scene_transform)
        x = transform.get("m41")
        y = transform.get("m42")
        z = transform.get("m43")
        if x is None or y is None or z is None:
            continue
        records.append(
            {
                "source_file": source_file,
                "media_track_name": media_track_name,
                "locator_collection": locator_collection,
                "locator_name": locator_name,
                "locator_kind": _locator_kind(locator_name, locator_collection),
                "route_id": route_id,
                "x": x,
                "y": y,
                "z": z,
                "heading_yaw_rad": _heading_yaw_rad(transform),
                "transform_json": json.dumps(transform, sort_keys=True, separators=(",", ":")),
                "catalog_source": LOCAL_TRACK_CATALOG_SOURCE,
            }
        )
    return records


def _read_ai_track_route_points(raw: bytes) -> list[tuple[int, float, float, float]]:
    if raw[:4] != _AI_TRACK_MAGIC or len(raw) < _AI_TRACK_ROUTE_POINT_HEADER_BYTES:
        return []
    point_count = int.from_bytes(
        raw[
            _AI_TRACK_ROUTE_POINT_COUNT_OFFSET : _AI_TRACK_ROUTE_POINT_COUNT_OFFSET
            + 4
        ],
        "little",
    )
    if point_count <= 0:
        return []
    payload_end = _AI_TRACK_ROUTE_POINT_HEADER_BYTES + (
        point_count * _AI_TRACK_ROUTE_POINT_STRIDE_BYTES
    )
    if payload_end > len(raw):
        return []

    points: list[tuple[int, float, float, float]] = []
    for index in range(point_count):
        offset = _AI_TRACK_ROUTE_POINT_HEADER_BYTES + (
            index * _AI_TRACK_ROUTE_POINT_STRIDE_BYTES
        )
        x, y, z = struct.unpack_from("<fff", raw, offset)
        if math.isfinite(x) and math.isfinite(y) and math.isfinite(z):
            points.append((index, float(x), float(y), float(z)))
    return points


def _decimated_ai_track_route_points(
    points: list[tuple[int, float, float, float]],
    *,
    spacing_meters: float = _AI_TRACK_ROUTE_POINT_SPACING_METERS,
) -> list[tuple[int, float, float, float]]:
    if len(points) <= 2:
        return points

    selected: list[tuple[int, float, float, float]] = []
    last_selected: tuple[int, float, float, float] | None = None
    final_raw_index = points[-1][0]
    for point in points:
        raw_index, x, _y, z = point
        if (
            last_selected is None
            or raw_index == final_raw_index
            or math.hypot(x - last_selected[1], z - last_selected[3]) >= spacing_meters
        ):
            selected.append(point)
            last_selected = point

    if selected[-1][0] != final_raw_index:
        selected.append(points[-1])
    return selected


def parse_ai_track_route_file(path: Path, media_root: Path | None = None) -> list[dict]:
    """Parse an OpenWorld AITracks Route*.owt route line into DB-ready records."""

    route_match = _AI_TRACK_ROUTE_FILE_RE.match(path.name)
    if route_match is None:
        return []
    route_id = int(route_match.group(1))
    try:
        raw = path.read_bytes()
    except OSError:
        return []

    raw_points = _read_ai_track_route_points(raw)
    points = _decimated_ai_track_route_points(raw_points)
    if not points:
        return []

    media_root = media_root or path.parents[3]
    source_file = _relative_media_path(path, media_root)
    media_track_name = path.parents[1].name if path.parent.name.lower() == "aitracks" else None
    locator_collection = f"aitrack_route{route_id}"

    records: list[dict] = []
    raw_point_count = len(raw_points)
    for raw_index, x, y, z in points:
        transform = {
            "format": "owt",
            "raw_point_count": raw_point_count,
            "raw_point_index": raw_index,
            "route_id": route_id,
            "spacing_meters": _AI_TRACK_ROUTE_POINT_SPACING_METERS,
        }
        records.append(
            {
                "source_file": source_file,
                "media_track_name": media_track_name,
                "locator_collection": locator_collection,
                "locator_name": f"route_point_{raw_index:05d}",
                "locator_kind": "route_point",
                "route_id": route_id,
                "x": x,
                "y": y,
                "z": z,
                "heading_yaw_rad": None,
                "transform_json": json.dumps(transform, sort_keys=True, separators=(",", ":")),
                "catalog_source": LOCAL_TRACK_CATALOG_SOURCE,
            }
        )
    return records


def load_track_locators(media_root: Path) -> list[dict]:
    records: list[dict] = []
    tracks_root = media_root / "Tracks"
    if not tracks_root.exists():
        return records
    for trackroutes_dir in sorted(tracks_root.glob("*/trackroutes")):
        if not trackroutes_dir.is_dir():
            continue
        for locator_file in sorted(trackroutes_dir.glob("*.nt")):
            records.extend(parse_track_locator_file(locator_file, media_root))
    return records


def load_ai_track_locators(media_root: Path) -> list[dict]:
    records: list[dict] = []
    open_world_root = media_root / "OpenWorld"
    if not open_world_root.exists():
        return records
    for ai_tracks_dir in sorted(open_world_root.glob("*/AITracks")):
        if not ai_tracks_dir.is_dir():
            continue
        for route_file in sorted(ai_tracks_dir.glob("Route*.owt")):
            records.extend(parse_ai_track_route_file(route_file, media_root))
    return records


def load_local_fh6_track_catalog(media_root: Path) -> LocalFH6TrackCatalog:
    """Load best-effort FH6 track metadata from the installed game media folder."""

    media_root = Path(media_root)
    strings = _load_career_track_strings(media_root)
    tracks, map_regions = _load_object_model_catalog(media_root, strings)
    locators = [*load_track_locators(media_root), *load_ai_track_locators(media_root)]
    return LocalFH6TrackCatalog(tracks=tracks, map_regions=map_regions, locators=locators)
