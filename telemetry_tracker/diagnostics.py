"""Diagnostics payload helpers for the telemetry tracker."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from telemetry_tracker.storage import TelemetryStore


ROW_COUNT_TABLES: tuple[tuple[str, str], ...] = (
    ("sessions", "sessions"),
    ("laps", "laps"),
    ("packets", "packet_blobs"),
    ("issue_markers", "issue_markers"),
    ("track_profiles", "track_profiles"),
    ("world_map_tile_sets", "world_map_tile_sets"),
)


def diagnostics_payload(
    store: TelemetryStore,
    app_version: str,
    listener_status: dict | None = None,
    capture_status: dict | None = None,
    expose_absolute_database_path: bool = False,
) -> dict[str, Any]:
    """Build a JSON-serializable diagnostics snapshot.

    Packet volume is intentionally counted with ``COUNT(*)`` against
    ``packet_blobs`` so diagnostics never reads raw packet payload data.
    """

    db_path = store.db_path.resolve()
    return {
        "database_path": (
            str(db_path) if expose_absolute_database_path else _display_database_path(db_path)
        ),
        "database_size_bytes": _file_size(db_path),
        "wal_size_bytes": _file_size(_wal_path(db_path)),
        "row_counts": _row_counts(store),
        "world_map": _world_map_status(store),
        "listener_status": dict(listener_status) if listener_status is not None else None,
        "capture_status": dict(capture_status) if capture_status is not None else None,
        "recent_errors": [],
        "app_version": str(app_version),
    }


def _row_counts(store: TelemetryStore) -> dict[str, int]:
    counts: dict[str, int] = {}
    with store.connect() as con:
        for payload_key, table_name in ROW_COUNT_TABLES:
            counts[payload_key] = int(
                con.execute(
                    f"SELECT COUNT(*) AS row_count FROM {table_name}"
                ).fetchone()["row_count"]
            )
    return counts


def _world_map_status(store: TelemetryStore) -> dict[str, Any]:
    settings = store.world_map_settings()
    ready_tile_set = store.latest_world_map_tile_set(
        "fh6",
        "brio",
        settings["world_map_season"],
    )
    return {
        "settings": settings,
        "tile_set_count": store.world_map_tile_set_count(),
        "ready_tile_set_id": (
            ready_tile_set["id"] if ready_tile_set is not None else None
        ),
    }


def _file_size(path: Path) -> int:
    try:
        return int(path.stat().st_size)
    except OSError:
        return 0


def _display_database_path(db_path: Path) -> str:
    return db_path.name or "telemetry database"


def _wal_path(db_path: Path) -> Path:
    return Path(str(db_path) + "-wal")


__all__ = ["diagnostics_payload"]
