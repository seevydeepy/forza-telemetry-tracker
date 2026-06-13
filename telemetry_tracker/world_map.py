"""Local FH6 world-map cache helpers.

The tracker never ships FH6 map assets.  This module only discovers a
user-provided game install, invokes the local converter helper, stores cache
metadata, and serves files that already live under the generated cache
directory.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from typing import Any

from telemetry_tracker.storage import TelemetryStore

SUPPORTED_SEASONS = frozenset({"spring", "summer", "autumn", "winter"})
DEFAULT_MAP_NAME = "brio"
DEFAULT_WORLD_ORIGIN_X = -12548.0
DEFAULT_WORLD_ORIGIN_Z = -11281.0
DEFAULT_WORLD_SIZE = 22035.0
DEFAULT_TILE_SIZE = 1024
DEFAULT_MAX_ZOOM = 3
TILE_COORDINATE_SYSTEM = "fh6-row-column-v1"
FH6_MAP_TILE_CONVERTER_ENV = "FH6_MAP_TILE_CONVERTER"
SUPPORTED_DXGI_FORMATS = frozenset({28, 29, 71, 72, 74, 75, 77, 78, 80, 81, 83, 84, 87, 98, 99})

_TILE_ENTRY_RE = re.compile(r"^(\d+)-(\d+)-(\d+)\.swatchbin$", re.IGNORECASE)
_FLOAT_RE = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)"


def season_source_zip(media_root: Path, season: str) -> Path:
    """Return the canonical seasonal FH6 world-map source archive path."""

    normalized = _validate_season(season)
    season_title = normalized.title()
    return (
        Path(media_root)
        / "UI"
        / "Textures"
        / "Data_Bound"
        / f"Map_Brio_{season_title}.zip"
    )


def parse_tile_entry_name(entry_name: str) -> tuple[int, int, int]:
    """Parse FH6 ``z-row-column.swatchbin`` names into ``(z, x, y)``."""

    match = _TILE_ENTRY_RE.match(Path(str(entry_name)).name)
    if match is None:
        raise ValueError(f"invalid map tile entry name: {entry_name}")
    z, row, column = (int(group) for group in match.groups())
    return z, column, row


def load_map_calibration(media_root: Path) -> dict[str, float]:
    """Load FH6 map calibration from ``UI.zip`` with a safe canonical fallback."""

    calibration = _default_calibration()
    ui_zip = Path(media_root) / "UI" / "Textures" / "Data_Bound" / "UI.zip"
    if not ui_zip.exists():
        return calibration
    try:
        with zipfile.ZipFile(ui_zip) as archive:
            for entry in archive.infolist():
                if entry.is_dir() or not entry.filename.lower().endswith((".xml", ".xaml")):
                    continue
                try:
                    text = archive.read(entry).decode("utf-8", errors="ignore")
                except (KeyError, OSError, UnicodeDecodeError):
                    continue
                parsed = _parse_calibration_text(text)
                if parsed is not None:
                    return parsed
    except (OSError, zipfile.BadZipFile):
        return calibration
    return calibration


def tile_world_bounds(
    *,
    z: int,
    x: int,
    y: int,
    calibration: dict[str, float],
) -> dict[str, float]:
    """Return world-coordinate bounds for a tile using a top-left tile origin."""

    z = _non_negative_int(z, "z")
    x = _non_negative_int(x, "x")
    y = _non_negative_int(y, "y")
    count = 2**z
    if x >= count or y >= count:
        raise ValueError(f"tile coordinates {z}/{x}/{y} are outside zoom {z}")
    world_origin_x = float(calibration.get("world_origin_x", DEFAULT_WORLD_ORIGIN_X))
    world_origin_z = float(calibration.get("world_origin_z", DEFAULT_WORLD_ORIGIN_Z))
    world_size = float(calibration.get("world_size", DEFAULT_WORLD_SIZE))
    west = world_origin_x + (x / count) * world_size
    east = world_origin_x + ((x + 1) / count) * world_size
    north = world_origin_z + (1 - y / count) * world_size
    south = world_origin_z + (1 - (y + 1) / count) * world_size
    return {"west": west, "east": east, "north": north, "south": south}


def safe_cache_tile_path(cache_dir: Path, *, z: int, x: int, y: int) -> Path:
    """Resolve a cache tile path and prove it remains inside ``cache_dir``."""

    z = _non_negative_int(z, "z")
    x = _non_negative_int(x, "x")
    y = _non_negative_int(y, "y")
    cache_root = Path(cache_dir).resolve()
    candidate = (cache_root / str(z) / str(x) / f"{y}.png").resolve()
    if not candidate.is_relative_to(cache_root):
        raise ValueError("tile path escapes the map cache directory")
    if candidate.suffix.lower() != ".png":
        raise ValueError("map cache tiles must be PNG files")
    return candidate


def resolve_converter_path(repo_root: Path) -> Path | None:
    """Resolve the configured or built map-tile converter executable."""

    configured = os.environ.get(FH6_MAP_TILE_CONVERTER_ENV)
    if configured:
        configured_path = Path(configured)
        if configured_path.exists():
            return configured_path
    default_path = (
        Path(repo_root)
        / "tools"
        / "fh6-map-tile-converter"
        / "bin"
        / "Release"
        / "net9.0-windows"
        / "forza-map-tile-converter.exe"
    )
    return default_path if default_path.exists() else None


def build_world_map_cache(
    *,
    store: TelemetryStore,
    media_root: Path,
    season: str,
    converter_path: Path | None = None,
    cache_root: Path | None = None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Build a local PNG tile cache from a user's FH6 install."""

    normalized_season = _validate_season(season)
    media_root = Path(media_root).expanduser()
    source_zip = season_source_zip(media_root, normalized_season)
    target_cache_root = Path(cache_root) if cache_root is not None else store.db_path.parent / "map-cache"
    cache_dir = target_cache_root / "fh6" / DEFAULT_MAP_NAME / normalized_season
    tile_set_id = _tile_set_id(normalized_season)
    calibration = load_map_calibration(media_root)

    if not media_root.exists() or not media_root.is_dir():
        return _store_error_status(
            store=store,
            status="source_missing",
            tile_set_id=tile_set_id,
            season=normalized_season,
            source_zip=source_zip,
            cache_dir=cache_dir,
            calibration=calibration,
            error_message=f"FH6 media root does not exist: {media_root}",
        )
    if not source_zip.exists():
        return _store_error_status(
            store=store,
            status="source_missing",
            tile_set_id=tile_set_id,
            season=normalized_season,
            source_zip=source_zip,
            cache_dir=cache_dir,
            calibration=calibration,
            error_message=f"FH6 world-map archive is missing: {source_zip}",
        )

    resolved_converter = converter_path or resolve_converter_path(
        repo_root or Path(__file__).resolve().parents[1]
    )
    if resolved_converter is None or not Path(resolved_converter).exists():
        return _store_error_status(
            store=store,
            status="converter_missing",
            tile_set_id=tile_set_id,
            season=normalized_season,
            source_zip=source_zip,
            cache_dir=cache_dir,
            calibration=calibration,
            error_message="FH6 map tile converter is missing. Build the helper or set FH6_MAP_TILE_CONVERTER.",
        )

    inspect = _run_converter(
        Path(resolved_converter),
        ["inspect-zip", "--input", str(source_zip)],
    )
    if inspect.returncode != 0:
        return _store_error_status(
            store=store,
            status="error",
            tile_set_id=tile_set_id,
            season=normalized_season,
            source_zip=source_zip,
            cache_dir=cache_dir,
            calibration=calibration,
            error_message=_converter_error("inspect-zip", inspect),
        )

    try:
        inspect_payload = json.loads(inspect.stdout)
        entries = _validate_inspection_entries(inspect_payload)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        return _store_error_status(
            store=store,
            status="error",
            tile_set_id=tile_set_id,
            season=normalized_season,
            source_zip=source_zip,
            cache_dir=cache_dir,
            calibration=calibration,
            error_message=f"Unsupported FH6 map tile archive: {exc}",
        )

    if cache_dir.exists():
        shutil.rmtree(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = cache_dir / "manifest.json"
    convert = _run_converter(
        Path(resolved_converter),
        [
            "convert-zip",
            "--input",
            str(source_zip),
            "--output",
            str(cache_dir),
            "--format",
            "png",
            "--manifest",
            str(manifest_path),
        ],
    )
    if convert.returncode != 0:
        return _store_error_status(
            store=store,
            status="error",
            tile_set_id=tile_set_id,
            season=normalized_season,
            source_zip=source_zip,
            cache_dir=cache_dir,
            calibration=calibration,
            error_message=_converter_error("convert-zip", convert),
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _store_error_status(
            store=store,
            status="error",
            tile_set_id=tile_set_id,
            season=normalized_season,
            source_zip=source_zip,
            cache_dir=cache_dir,
            calibration=calibration,
            error_message=f"Converter did not write a valid manifest: {exc}",
        )

    manifest = _manifest_with_calibration(manifest, calibration)
    tile_records = manifest.get("tiles")
    if not isinstance(tile_records, list):
        tile_records = []
    max_zoom = max((int(tile["z"]) for tile in tile_records), default=DEFAULT_MAX_ZOOM)
    min_zoom = min((int(tile["z"]) for tile in tile_records), default=0)
    record = _tile_set_record(
        tile_set_id=tile_set_id,
        season=normalized_season,
        source_zip=source_zip,
        cache_dir=cache_dir,
        calibration=calibration,
        manifest=manifest,
        status="ready",
        error_message=None,
        min_zoom=min_zoom,
        max_zoom=max_zoom,
        tile_size=int(manifest.get("tileSize") or DEFAULT_TILE_SIZE),
    )
    store.upsert_world_map_tile_set(record)
    payload = world_map_status_payload(store, converter_path=resolved_converter)
    payload["status"] = "ready"
    payload["inspect"] = {"entries": len(entries)}
    return payload


def world_map_status_payload(
    store: TelemetryStore,
    *,
    converter_path: Path | None = None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Return the API status payload for world-map settings and cache state."""

    settings = store.world_map_settings()
    season = _validate_season(settings.get("world_map_season") or "summer")
    media_root_text = settings.get("fh6_media_root")
    source_zip: Path | None = None
    source_available = False
    if media_root_text:
        source_zip = season_source_zip(Path(str(media_root_text)), season)
        source_available = source_zip.exists()
    tile_set = store.latest_world_map_tile_set("fh6", DEFAULT_MAP_NAME, season)
    tile_set_is_current = tile_set_uses_current_tile_coordinates(tile_set)
    enriched_tile_set = _api_tile_set(tile_set) if tile_set_is_current else None
    if not settings.get("world_map_enabled"):
        status = "disabled"
    elif enriched_tile_set is not None:
        status = "ready"
    elif tile_set is not None and not tile_set_is_current:
        status = "cache_stale"
    elif media_root_text and source_available:
        status = "cache_missing"
    else:
        status = "source_missing"
    converter = (
        Path(converter_path)
        if converter_path is not None
        else resolve_converter_path(repo_root or Path(__file__).resolve().parents[1])
    )
    converter_available = converter.exists() if converter is not None else False
    return {
        "status": status,
        "settings": settings,
        "source": {
            "available": source_available,
            "path": str(source_zip) if source_zip is not None else None,
            "season": season,
        },
        "converter": {
            "available": converter_available,
            "path": str(converter) if converter is not None else None,
        },
        "tile_set": enriched_tile_set,
    }


def _default_calibration() -> dict[str, float]:
    return {
        "world_origin_x": DEFAULT_WORLD_ORIGIN_X,
        "world_origin_z": DEFAULT_WORLD_ORIGIN_Z,
        "world_size": DEFAULT_WORLD_SIZE,
    }


def _parse_calibration_text(text: str) -> dict[str, float] | None:
    world_size = _first_float(
        (
            rf"background_size\s*=\s*['\"]({_FLOAT_RE})['\"]",
            rf"\bbackground_size\b[^-+\d]*({_FLOAT_RE})",
            rf"\bworld_size\b[^-+\d]*({_FLOAT_RE})",
        ),
        text,
    )
    origin_x = _first_float(
        (
            rf"background_offset\b[^>]*\bx\s*=\s*['\"]({_FLOAT_RE})['\"]",
            rf"background_offset\b[^>]*\bX\s*=\s*['\"]({_FLOAT_RE})['\"]",
            rf"\bworld_origin_x\b[^-+\d]*({_FLOAT_RE})",
            rf"\borigin_x\b[^-+\d]*({_FLOAT_RE})",
        ),
        text,
    )
    origin_z = _first_float(
        (
            rf"background_offset\b[^>]*\bz\s*=\s*['\"]({_FLOAT_RE})['\"]",
            rf"background_offset\b[^>]*\bZ\s*=\s*['\"]({_FLOAT_RE})['\"]",
            rf"\bworld_origin_z\b[^-+\d]*({_FLOAT_RE})",
            rf"\borigin_z\b[^-+\d]*({_FLOAT_RE})",
        ),
        text,
    )
    if world_size is None or origin_x is None or origin_z is None:
        return None
    return {
        "world_origin_x": origin_x,
        "world_origin_z": origin_z,
        "world_size": world_size,
    }


def _first_float(patterns: tuple[str, ...], text: str) -> float | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        if match is not None:
            return float(match.group(1))
    return None


def _validate_season(season: object) -> str:
    normalized = str(season or "").strip().lower()
    if normalized not in SUPPORTED_SEASONS:
        raise ValueError("season must be one of autumn, spring, summer, or winter")
    return normalized


def _non_negative_int(value: object, name: str) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a non-negative integer") from exc
    if normalized < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return normalized


def _tile_set_id(season: str) -> str:
    return f"fh6-{DEFAULT_MAP_NAME}-{season}"


def _run_converter(converter_path: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    command = _converter_command(converter_path, args)
    return subprocess.run(
        command,
        timeout=180,
        capture_output=True,
        text=True,
        check=False,
    )


def _looks_like_python_script(header: bytes) -> bool:
    stripped = header.lstrip()
    return (
        stripped.startswith(b"#!")
        or stripped.startswith(b"import ")
        or stripped.startswith(b"from ")
    )


def _converter_command(converter_path: Path, args: list[str]) -> list[str]:
    if converter_path.suffix.lower() == ".py":
        return [sys.executable, str(converter_path), *args]
    try:
        with converter_path.open("rb") as _fh:
            header = _fh.read(512)
        if _looks_like_python_script(header):
            return [sys.executable, str(converter_path), *args]
    except OSError:
        pass
    return [str(converter_path), *args]


def _converter_error(command_name: str, result: subprocess.CompletedProcess[str]) -> str:
    stderr = (result.stderr or "").strip()
    stdout = (result.stdout or "").strip()
    detail = stderr or stdout or "no converter output"
    return f"{command_name} failed with exit code {result.returncode}: {detail}"


def _validate_inspection_entries(payload: object) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        raise ValueError("inspection payload must be an object")
    entries = payload.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ValueError("inspection payload did not include any tile entries")
    normalized: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("inspection entry must be an object")
        name = str(entry.get("entry") or "")
        parsed = parse_tile_entry_name(name)
        if tuple(int(entry.get(key, -1)) for key in ("z", "x", "y")) != parsed:
            raise ValueError(f"inspection coordinates do not match tile name: {name}")
        if bool(entry.get("isDurango")):
            raise ValueError(f"Durango/Xbox tiled swatchbin is not supported: {name}")
        if int(entry.get("width") or 0) != DEFAULT_TILE_SIZE or int(entry.get("height") or 0) != DEFAULT_TILE_SIZE:
            raise ValueError(f"unsupported tile dimensions for {name}")
        dxgi_format = int(entry.get("dxgiFormat") or -1)
        if dxgi_format not in SUPPORTED_DXGI_FORMATS:
            raise ValueError(f"unsupported DXGI format {dxgi_format} for {name}")
        normalized.append(entry)
    return normalized


def _manifest_with_calibration(
    manifest: dict[str, Any],
    calibration: dict[str, float],
) -> dict[str, Any]:
    enriched = dict(manifest)
    enriched.setdefault("game", "fh6")
    enriched.setdefault("map", DEFAULT_MAP_NAME)
    enriched.setdefault("format", "png")
    enriched["worldOriginX"] = float(calibration["world_origin_x"])
    enriched["worldOriginZ"] = float(calibration["world_origin_z"])
    enriched["worldSize"] = float(calibration["world_size"])
    enriched["tileCoordinateSystem"] = TILE_COORDINATE_SYSTEM
    enriched.setdefault("tileSize", DEFAULT_TILE_SIZE)
    enriched.setdefault("maxZoom", DEFAULT_MAX_ZOOM)
    enriched.setdefault("minZoom", 0)
    return enriched


def _store_error_status(
    *,
    store: TelemetryStore,
    status: str,
    tile_set_id: str,
    season: str,
    source_zip: Path,
    cache_dir: Path,
    calibration: dict[str, float],
    error_message: str,
) -> dict[str, Any]:
    manifest = _manifest_with_calibration(
        {
            "game": "fh6",
            "map": DEFAULT_MAP_NAME,
            "season": season,
            "format": "png",
            "tileSize": DEFAULT_TILE_SIZE,
            "minZoom": 0,
            "maxZoom": DEFAULT_MAX_ZOOM,
            "tiles": [],
        },
        calibration,
    )
    store.upsert_world_map_tile_set(
        _tile_set_record(
            tile_set_id=tile_set_id,
            season=season,
            source_zip=source_zip,
            cache_dir=cache_dir,
            calibration=calibration,
            manifest=manifest,
            status="error",
            error_message=error_message,
            min_zoom=0,
            max_zoom=DEFAULT_MAX_ZOOM,
            tile_size=DEFAULT_TILE_SIZE,
        )
    )
    payload = world_map_status_payload(store)
    payload["status"] = status
    payload["error_message"] = error_message
    return payload


def _tile_set_record(
    *,
    tile_set_id: str,
    season: str,
    source_zip: Path,
    cache_dir: Path,
    calibration: dict[str, float],
    manifest: dict[str, Any],
    status: str,
    error_message: str | None,
    min_zoom: int,
    max_zoom: int,
    tile_size: int,
) -> dict[str, Any]:
    source_stat = _stat_or_none(source_zip)
    now_ms = int(time.time() * 1000)
    return {
        "id": tile_set_id,
        "game": "fh6",
        "map_name": DEFAULT_MAP_NAME,
        "season": season,
        "source_zip_path": str(source_zip),
        "source_zip_mtime_ms": (
            int(source_stat.st_mtime * 1000) if source_stat is not None else 0
        ),
        "source_zip_size_bytes": source_stat.st_size if source_stat is not None else 0,
        "cache_dir": str(cache_dir),
        "tile_format": "png",
        "tile_size": int(tile_size),
        "min_zoom": int(min_zoom),
        "max_zoom": int(max_zoom),
        "world_origin_x": float(calibration["world_origin_x"]),
        "world_origin_z": float(calibration["world_origin_z"]),
        "world_size": float(calibration["world_size"]),
        "status": status,
        "manifest_json": json.dumps(manifest, sort_keys=True),
        "error_message": error_message,
        "last_built_at_ms": now_ms if status == "ready" else None,
        "updated_at_ms": now_ms,
    }


def _stat_or_none(path: Path) -> os.stat_result | None:
    try:
        return path.stat()
    except OSError:
        return None


def tile_set_uses_current_tile_coordinates(tile_set: dict[str, Any] | None) -> bool:
    if tile_set is None:
        return False
    manifest = tile_set.get("manifest") or {}
    if not isinstance(manifest, dict):
        return False
    return manifest.get("tileCoordinateSystem") == TILE_COORDINATE_SYSTEM


def _api_tile_set(tile_set: dict[str, Any]) -> dict[str, Any]:
    payload = dict(tile_set)
    payload.pop("manifest_json", None)
    manifest = dict(payload.get("manifest") or {})
    template = f"/api/map/tiles/{payload['id']}/{{z}}/{{x}}/{{y}}.png"
    manifest["tileUrlTemplate"] = template
    payload["manifest"] = manifest
    payload["tile_url_template"] = template
    return payload


__all__ = [
    "DEFAULT_MAP_NAME",
    "DEFAULT_MAX_ZOOM",
    "DEFAULT_TILE_SIZE",
    "DEFAULT_WORLD_ORIGIN_X",
    "DEFAULT_WORLD_ORIGIN_Z",
    "DEFAULT_WORLD_SIZE",
    "FH6_MAP_TILE_CONVERTER_ENV",
    "SUPPORTED_SEASONS",
    "TILE_COORDINATE_SYSTEM",
    "tile_set_uses_current_tile_coordinates",
    "build_world_map_cache",
    "load_map_calibration",
    "parse_tile_entry_name",
    "resolve_converter_path",
    "safe_cache_tile_path",
    "season_source_zip",
    "tile_world_bounds",
    "world_map_status_payload",
]
