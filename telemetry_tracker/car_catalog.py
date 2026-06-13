"""Car catalog helpers for Forza telemetry tracker."""

from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path

FH6_PI_BUCKETS = {
    "D": (100, 400),
    "C": (401, 500),
    "B": (501, 600),
    "A": (601, 700),
    "S1": (701, 800),
    "S2": (801, 900),
    "R": (901, 998),
    "X": (999, 999),
}
CAR_CLASS_LABELS = {
    0: "D",
    1: "C",
    2: "B",
    3: "A",
    4: "S1",
    5: "S2",
    6: "R",
    7: "X",
}
DRIVETRAIN_LABELS = {0: "FWD", 1: "RWD", 2: "AWD"}
# FH6 telemetry CarGroup values correspond to the local CarBuckets.str
# IDS_Name_* entries in the installed game's string tables.
CAR_GROUP_LABELS = {
    1: "Cult Cars",
    2: "GT Cars",
    3: "Hot Hatch",
    4: "Iconic Rally",
    5: "Muscle",
    6: "Offroad",
    7: "Saloon Cars",
    8: "Sports Cars",
    9: "Supercars",
    10: "World Classics",
    11: "Modern Supercars",
    12: "Retro Supercars",
    13: "Hypercars",
    14: "Retro Super Saloons",
    16: "Utility Heroes",
    17: "Retro Sports Cars",
    18: "Modern Sports Cars",
    19: "Modern Super Saloons",
    20: "Classic Racers",
    21: "Cult Cars",
    22: "Rare Classics",
    23: "Hot Hatch",
    24: "Retro Hot Hatch",
    25: "Super Hot Hatch",
    26: "Extreme Track Toys",
    28: "Classic Muscle",
    29: "Rods and Customs",
    30: "Retro Muscle",
    31: "Modern Muscle",
    32: "Retro Rally",
    33: "Classic Rally",
    34: "Rally Monsters",
    35: "Modern Rally",
    36: "GT Cars",
    37: "Super GT",
    38: "Unlimited Offroad",
    39: "Sports Utility Heroes",
    40: "Offroad",
    41: "Unlimited Buggies",
    42: "Classic Sports Cars",
    43: "Track Toys",
    44: "Vintage Racers",
    45: "Trucks",
    46: "Buggies",
    47: "Drift Cars",
    48: "Pickups & 4x4's",
    49: "UTV's",
    50: "Eclectic Domestics",
    51: "Retro Racers",
}
_DISPLAY_KEY_RE = re.compile(rb"IDS_DisplayName_(\d+)")
_MODEL_SHORT_KEY_RE = re.compile(rb"IDS_ModelShort_(\d+)")
_CARCLIPS_RE = re.compile(r"(?:^|/)carclips_(\d+)\.clipd$", re.IGNORECASE)
_YEAR_PREFIX_RE = re.compile(r"^(?:19|20)\d{2}\s+")
_NON_NAME_PART_RE = re.compile(r"[^a-z0-9]+")
def _resolve_default_supplements_path() -> Path:
    from telemetry_tracker.app_paths import car_catalog_supplements_path as _app_supplements_path
    app_path = _app_supplements_path()
    if app_path.exists():
        return app_path
    return Path(__file__).resolve().parent / "resources" / "car_catalog_supplements.json"

_DEFAULT_SUPPLEMENTS_PATH = _resolve_default_supplements_path()


def car_class_label(value: int | None) -> str | None:
    if value is None:
        return None
    return CAR_CLASS_LABELS.get(int(value))


def drivetrain_label(value: int | None) -> str | None:
    if value is None:
        return None
    return DRIVETRAIN_LABELS.get(int(value))


def car_group_label(value: int | None) -> str | None:
    if value is None:
        return None
    return CAR_GROUP_LABELS.get(int(value))


def _clean_string(value: bytes) -> str:
    return value.decode("utf-8", errors="replace").strip("\x00\r\n\t ")


def _normalized_car_name(value: object) -> str:
    text = str(value or "").strip().lower()
    text = _YEAR_PREFIX_RE.sub("", text)
    return _NON_NAME_PART_RE.sub(" ", text).strip()


def _car_catalog_supplements(supplements_path: Path | None) -> dict[str, dict]:
    if supplements_path is None or not supplements_path.exists():
        return {}
    try:
        raw_index = json.loads(supplements_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw_index, dict):
        return {}

    supplements: dict[str, dict] = {}
    ambiguous_keys: set[str] = set()
    for car in raw_index.get("cars", []):
        if not isinstance(car, dict):
            continue
        detail = {
            "year": car.get("year"),
            "make": car.get("make"),
            "model": car.get("model"),
            "display_name": car.get("display_name"),
        }
        if not any(detail.values()):
            continue
        keys = {
            _normalized_car_name(car.get("display_name")),
            _normalized_car_name(f"{car.get('make') or ''} {car.get('model') or ''}"),
            _normalized_car_name(car.get("model")),
        }
        for key in keys:
            if not key or key in ambiguous_keys:
                continue
            existing = supplements.get(key)
            if existing is not None and any(
                existing.get(field) != detail.get(field)
                for field in ("year", "make", "model")
            ):
                supplements.pop(key, None)
                ambiguous_keys.add(key)
                continue
            supplements[key] = detail
    return supplements


def _apply_car_catalog_supplements(
    records: dict[int, dict],
    supplements_path: Path | None,
) -> None:
    supplements = _car_catalog_supplements(supplements_path)
    if not supplements:
        return
    for record in records.values():
        candidate_keys = [
            _normalized_car_name(record.get("display_name")),
            _normalized_car_name(record.get("model_short")),
            _normalized_car_name(record.get("asset_name")),
        ]
        supplement = next(
            (supplements[key] for key in candidate_keys if key in supplements),
            None,
        )
        if supplement is None:
            continue
        for field in ("year", "make", "model"):
            if record.get(field) in (None, "") and supplement.get(field) not in (None, ""):
                record[field] = supplement[field]


def supplement_car_catalog_record(
    record: dict | None,
    supplements_path: Path | None = _DEFAULT_SUPPLEMENTS_PATH,
) -> dict | None:
    if record is None:
        return None
    try:
        ordinal = int(record.get("ordinal") or 0)
    except (TypeError, ValueError):
        ordinal = 0
    records = {ordinal: dict(record)}
    _apply_car_catalog_supplements(records, supplements_path)
    return records[ordinal]


def _valid_string_part(value: bytes) -> bool:
    if len(value) > 96:
        return False
    text = value.decode("utf-8", errors="replace")
    if "\ufffd" in text:
        return False
    return not any(ord(char) < 32 for char in text)


def _value_block_candidate(raw: bytes, start: int, end: int, count: int) -> tuple[float, list[str]] | None:
    values: list[bytes] = []
    position = start
    for _ in range(count):
        terminator = raw.find(b"\x00", position, end)
        if terminator < 0:
            return None
        part = raw[position:terminator]
        if not _valid_string_part(part):
            return None
        values.append(part)
        position = terminator + 1
    decoded = [_clean_string(value) for value in values]
    if not decoded or not decoded[0] or not decoded[-1]:
        return None
    total_chars = sum(max(1, len(value)) for value in decoded)
    printable_chars = sum(sum(char.isprintable() for char in value) for value in decoded)
    non_empty = sum(1 for value in decoded if value)
    score = (printable_chars / total_chars) - ((count - non_empty) * 0.01)
    return score, decoded


def _string_blocks_before_keys(raw: bytes, expected_count: int) -> tuple[list[str], list[str]]:
    key_positions = [match.start() for match in _DISPLAY_KEY_RE.finditer(raw)]
    if not key_positions or expected_count <= 0:
        return [], []
    key_start = min(key_positions)
    required_values = expected_count * 2
    starts = [0]
    starts.extend(index + 1 for index, byte in enumerate(raw[:key_start]) if byte == 0 and index + 1 < key_start)

    best: tuple[float, list[str]] | None = None
    for start in starts:
        candidate = _value_block_candidate(raw, start, key_start, required_values)
        if candidate is None:
            continue
        if best is None or candidate[0] > best[0]:
            best = candidate
    if best is None:
        return [], []
    values = best[1]
    return values[:expected_count], values[expected_count:required_values]


def parse_data_car_string_table(raw: bytes) -> dict[int, dict]:
    """Parse display and model-short strings from an FH6 Data_Car.str blob.

    The binary file contains offset data before the null-terminated string blocks,
    so the parser searches for two adjacent readable value blocks that match the
    display-name key count instead of blindly splitting from byte zero.
    """

    display_ordinals = [int(match.group(1)) for match in _DISPLAY_KEY_RE.finditer(raw)]
    model_short_ordinals = [int(match.group(1)) for match in _MODEL_SHORT_KEY_RE.finditer(raw)]
    if not display_ordinals:
        return {}

    display_values, model_short_values = _string_blocks_before_keys(raw, len(display_ordinals))
    if len(display_values) != len(display_ordinals):
        display_values = []
    if len(model_short_values) != len(display_ordinals):
        model_short_values = []

    records: dict[int, dict] = {}
    for index, ordinal in enumerate(display_ordinals):
        records.setdefault(ordinal, {"ordinal": ordinal})["display_name"] = (
            display_values[index] if index < len(display_values) else None
        )
    for index, ordinal in enumerate(model_short_ordinals):
        records.setdefault(ordinal, {"ordinal": ordinal})["model_short"] = (
            model_short_values[index] if index < len(model_short_values) else None
        )
    return records


def scan_car_zip_ordinals(cars_dir: Path) -> dict[int, dict]:
    records: dict[int, dict] = {}
    if not cars_dir.exists():
        return records
    for zip_path in sorted(cars_dir.glob("*.zip")):
        try:
            with zipfile.ZipFile(zip_path) as archive:
                names = archive.namelist()
        except (OSError, zipfile.BadZipFile):
            continue
        ordinals = sorted(
            {
                int(match.group(1))
                for name in names
                if (match := _CARCLIPS_RE.search(name.replace("\\", "/")))
            }
        )
        if len(ordinals) != 1:
            continue
        ordinal = ordinals[0]
        records[ordinal] = {
            "ordinal": ordinal,
            "asset_name": zip_path.stem,
            "asset_zip": zip_path.name,
            "catalog_source": "fh6_local_files",
        }
    return records


def load_local_fh6_catalog(
    media_root: Path,
    supplements_path: Path | None = _DEFAULT_SUPPLEMENTS_PATH,
) -> list[dict]:
    records: dict[int, dict] = {}
    for ordinal, record in scan_car_zip_ordinals(media_root / "Cars").items():
        records.setdefault(ordinal, {"ordinal": ordinal}).update(record)

    string_table_zip = media_root / "Stripped" / "StringTables" / "EN.zip"
    if string_table_zip.exists():
        try:
            with zipfile.ZipFile(string_table_zip) as archive:
                raw = archive.read("Data_Car.str")
        except (OSError, KeyError, zipfile.BadZipFile):
            raw = b""
        for ordinal, record in parse_data_car_string_table(raw).items():
            records.setdefault(ordinal, {"ordinal": ordinal}).update(
                {key: value for key, value in record.items() if value is not None}
            )
            records[ordinal].setdefault("catalog_source", "fh6_local_files")
    _apply_car_catalog_supplements(records, supplements_path)
    return list(records.values())
