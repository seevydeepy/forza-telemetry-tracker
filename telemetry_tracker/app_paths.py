"""Path helpers for development and packaged desktop tracker runs."""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

APP_PRODUCT_NAME = "Forza Telemetry Tracker"
ENV_RESOURCE_ROOT = "FORZA_TRACKER_RESOURCE_ROOT"
ENV_USER_DATA_ROOT = "FORZA_TRACKER_USER_DATA_ROOT"

@dataclass(frozen=True)
class DesktopPaths:
    resource_root: Path
    user_data_root: Path
    frontend_dist: Path
    car_catalog_supplements: Path
    map_converter: Path
    database: Path
    logs_dir: Path
    map_cache_dir: Path
    imports_dir: Path
    backups_dir: Path
    exports_dir: Path
    release_metadata: Path

    def ensure_user_directories(self) -> None:
        self.user_data_root.mkdir(parents=True, exist_ok=True)
        for path in (
            self.logs_dir,
            self.map_cache_dir,
            self.imports_dir,
            self.backups_dir,
            self.exports_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

def _env_path(name: str) -> Path | None:
    raw = os.environ.get(name)
    return Path(raw).expanduser() if raw and raw.strip() else None

def resource_root() -> Path:
    override = _env_path(ENV_RESOURCE_ROOT)
    if override is not None:
        return override
    meipass = getattr(sys, "_MEIPASS", None)
    if getattr(sys, "frozen", False) and meipass:
        return Path(str(meipass))
    return Path(__file__).resolve().parents[1]

def user_data_root() -> Path:
    override = _env_path(ENV_USER_DATA_ROOT)
    if override is not None:
        return override
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / APP_PRODUCT_NAME
    return Path.home() / ".local" / "share" / APP_PRODUCT_NAME

def frontend_dist_path(resource_base: Path | None = None) -> Path:
    root = Path(resource_base) if resource_base is not None else resource_root()
    bundled = root / "frontend-dist"
    return bundled if bundled.exists() else root / "web" / "telemetry-tracker" / "dist"

def car_catalog_supplements_path(resource_base: Path | None = None) -> Path:
    root = Path(resource_base) if resource_base is not None else resource_root()
    bundled = root / "resources" / "car_catalog_supplements.json"
    return bundled if bundled.exists() else root / "telemetry_tracker" / "resources" / "car_catalog_supplements.json"

def map_converter_path(resource_base: Path | None = None) -> Path:
    root = Path(resource_base) if resource_base is not None else resource_root()
    bundled = root / "bin" / "map-converter" / "forza-map-tile-converter.exe"
    if bundled.exists():
        return bundled
    return root / "tools" / "fh6-map-tile-converter" / "bin" / "Release" / "net9.0-windows" / "forza-map-tile-converter.exe"

def default_desktop_paths(*, resource_base: Path | None = None, user_data_base: Path | None = None) -> DesktopPaths:
    resources = Path(resource_base) if resource_base is not None else resource_root()
    data = Path(user_data_base) if user_data_base is not None else user_data_root()
    return DesktopPaths(
        resource_root=resources,
        user_data_root=data,
        frontend_dist=frontend_dist_path(resources),
        car_catalog_supplements=car_catalog_supplements_path(resources),
        map_converter=map_converter_path(resources),
        database=data / "telemetry_tracker.sqlite3",
        logs_dir=data / "logs",
        map_cache_dir=data / "map-cache",
        imports_dir=data / "imports",
        backups_dir=data / "backups",
        exports_dir=data / "exports",
        release_metadata=resources / "release-metadata.json",
    )
