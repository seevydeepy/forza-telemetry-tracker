"""SQLite persistence for the telemetry tracker."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Iterable

from telemetry_tracker.track_assets import validate_asset, validate_transform

SCHEMA_VERSION = 12
LOCAL_USER_ID = "00000000-0000-0000-0000-000000000001"
SUPPORTED_REFERENCE_SCOPES = frozenset({"track", "track_car", "track_car_build"})
SUPPORTED_WORLD_MAP_SEASONS = frozenset({"spring", "summer", "autumn", "winter"})
WORLD_MAP_TILE_SET_STATUSES = frozenset({"missing", "building", "ready", "error"})
_REFERENCE_CONTEXT_JSON_PATHS = {
    "track": "$.comparison_contexts.track",
    "track_car": "$.comparison_contexts.track_car",
    "track_car_build": "$.comparison_contexts.track_car_build",
}
_REFERENCE_COMPLETED_STATES = frozenset(
    {"finalized", "lap_boundary", "manual_stop", "replay_complete"}
)
_REFERENCE_REJECTED_STATES = frozenset(
    {
        "active",
        "deleted",
        "event_exit",
        "free_roam",
        "invalid",
        "no_lap",
        "no_lap_signal",
        "partial_lap",
        "recording",
        "unavailable",
        "uncertain",
        "car_switch",
    }
)
_PRUNABLE_UNASSIGNED_NON_RACE_SAMPLE_PREDICATE = """
lap_id IS NULL
AND is_race_on = 0
AND lap_number = 0
AND current_lap = 0
AND current_race_time = 0
"""
_REFERENCE_CAR_FIELDS = (
    "car_profile_id",
    "car_id",
    "car_slug",
    "vehicle_id",
    "vehicle_slug",
    "car_ordinal",
    "car_name",
)
_REFERENCE_BUILD_FIELDS = (
    "build_id",
    "build_slug",
    "tune_id",
    "tune_slug",
    "setup_id",
    "setup_slug",
    "variant_id",
    "variant_slug",
    "build_name",
)
_BASE_SAMPLE_COLUMNS = (
    "lap_id",
    "sequence",
    "received_at_ms",
    "game_timestamp_ms",
    "is_race_on",
    "lap_number",
    "current_lap",
    "current_race_time",
    "x",
    "y",
    "z",
    "speed_mps",
    "throttle",
    "brake",
    "steer",
    "gear",
)
_EXTENDED_SAMPLE_COLUMNS = (
    "combined_slip",
    "rear_combined_slip",
    "tire_temp_front_left",
    "tire_temp_front_right",
    "tire_temp_rear_left",
    "tire_temp_rear_right",
    "suspension_travel_front_left",
    "suspension_travel_front_right",
    "suspension_travel_rear_left",
    "suspension_travel_rear_right",
    "current_rpm",
    "engine_max_rpm",
)
_DASHBOARD_SAMPLE_COLUMN_DEFINITIONS = (
    ("acceleration_x", "REAL"),
    ("acceleration_y", "REAL"),
    ("acceleration_z", "REAL"),
    ("velocity_x", "REAL"),
    ("velocity_y", "REAL"),
    ("velocity_z", "REAL"),
    ("angular_velocity_x", "REAL"),
    ("angular_velocity_y", "REAL"),
    ("angular_velocity_z", "REAL"),
    ("yaw", "REAL"),
    ("pitch", "REAL"),
    ("roll", "REAL"),
    ("smashable_vel_diff", "REAL"),
    ("smashable_mass", "REAL"),
    ("power_w", "REAL"),
    ("torque_nm", "REAL"),
    ("boost_bar", "REAL"),
    ("engine_idle_rpm", "REAL"),
    ("fuel", "REAL"),
    ("distance_traveled_m", "REAL"),
    ("best_lap", "REAL"),
    ("last_lap", "REAL"),
    ("race_position", "INTEGER"),
    ("clutch", "INTEGER"),
    ("handbrake", "INTEGER"),
    ("normalized_driving_line", "INTEGER"),
    ("normalized_ai_brake_difference", "INTEGER"),
    ("tire_slip_ratio_front_left", "REAL"),
    ("tire_slip_ratio_front_right", "REAL"),
    ("tire_slip_ratio_rear_left", "REAL"),
    ("tire_slip_ratio_rear_right", "REAL"),
    ("tire_slip_angle_front_left", "REAL"),
    ("tire_slip_angle_front_right", "REAL"),
    ("tire_slip_angle_rear_left", "REAL"),
    ("tire_slip_angle_rear_right", "REAL"),
    ("tire_combined_slip_front_left", "REAL"),
    ("tire_combined_slip_front_right", "REAL"),
    ("tire_combined_slip_rear_left", "REAL"),
    ("tire_combined_slip_rear_right", "REAL"),
    ("wheel_rotation_speed_front_left", "REAL"),
    ("wheel_rotation_speed_front_right", "REAL"),
    ("wheel_rotation_speed_rear_left", "REAL"),
    ("wheel_rotation_speed_rear_right", "REAL"),
    ("wheel_on_rumble_strip_front_left", "INTEGER"),
    ("wheel_on_rumble_strip_front_right", "INTEGER"),
    ("wheel_on_rumble_strip_rear_left", "INTEGER"),
    ("wheel_on_rumble_strip_rear_right", "INTEGER"),
    ("wheel_in_puddle_depth_front_left", "INTEGER"),
    ("wheel_in_puddle_depth_front_right", "INTEGER"),
    ("wheel_in_puddle_depth_rear_left", "INTEGER"),
    ("wheel_in_puddle_depth_rear_right", "INTEGER"),
    ("surface_rumble_front_left", "REAL"),
    ("surface_rumble_front_right", "REAL"),
    ("surface_rumble_rear_left", "REAL"),
    ("surface_rumble_rear_right", "REAL"),
    ("suspension_travel_meters_front_left", "REAL"),
    ("suspension_travel_meters_front_right", "REAL"),
    ("suspension_travel_meters_rear_left", "REAL"),
    ("suspension_travel_meters_rear_right", "REAL"),
)
_DASHBOARD_SAMPLE_COLUMNS = tuple(
    column_name for column_name, _column_type in _DASHBOARD_SAMPLE_COLUMN_DEFINITIONS
)
_RACE_CONTROL_SAMPLE_COLUMN_DEFINITIONS = (
    ("uncertainty", "TEXT"),
)
_RACE_CONTROL_SAMPLE_COLUMNS = tuple(
    column_name for column_name, _column_type in _RACE_CONTROL_SAMPLE_COLUMN_DEFINITIONS
)
_ALL_EXTENDED_SAMPLE_COLUMNS = (*_EXTENDED_SAMPLE_COLUMNS, *_DASHBOARD_SAMPLE_COLUMNS)
_LAP_SAMPLE_INSERT_COLUMNS = (
    "session_id",
    *_BASE_SAMPLE_COLUMNS,
    *_ALL_EXTENDED_SAMPLE_COLUMNS,
    *_RACE_CONTROL_SAMPLE_COLUMNS,
)


class _ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def _now_ms() -> int:
    return int(time.time() * 1000)


def _optional_int_value(value) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _decoded_is_race_on(decoded: dict) -> bool:
    try:
        return int(decoded.get("IsRaceOn", 0)) > 0
    except (TypeError, ValueError):
        return False


def _table_columns(con: sqlite3.Connection, table_name: str) -> set[str]:
    return {
        row["name"]
        for row in con.execute(f"PRAGMA table_info({table_name})").fetchall()
    }


def _ensure_column(
    con: sqlite3.Connection,
    table_name: str,
    column_name: str,
    column_definition: str,
) -> None:
    if column_name not in _table_columns(con, table_name):
        con.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_definition}")


def _sample_select_columns() -> str:
    return ", ".join(
        (*_BASE_SAMPLE_COLUMNS, *_ALL_EXTENDED_SAMPLE_COLUMNS, *_RACE_CONTROL_SAMPLE_COLUMNS)
    )


def _lap_sample_insert_values(
    session_id: str,
    sample: dict,
    *,
    fallback_is_race_on: bool,
) -> tuple:
    values = []
    for column in _LAP_SAMPLE_INSERT_COLUMNS:
        if column == "session_id":
            values.append(session_id)
        elif column == "lap_id":
            values.append(sample.get("lap_id"))
        elif column == "is_race_on":
            values.append(int(bool(sample.get("is_race_on", fallback_is_race_on))))
        elif column in {"sequence", "received_at_ms", "game_timestamp_ms", "lap_number", "throttle", "brake", "steer", "gear"}:
            values.append(int(sample[column]))
        elif column in {"current_lap", "current_race_time", "x", "y", "z", "speed_mps"}:
            values.append(float(sample[column]))
        else:
            values.append(sample.get(column))
    return tuple(values)


def _completed_lap_time_candidate_sql(lap_alias: str) -> str:
    return f"""
        lower(trim(coalesce({lap_alias}.status, ''))) NOT IN (
            'active', 'recording', 'uncertain', 'partial_lap',
            'no_lap', 'no_lap_signal', 'event_exit'
        )
        AND lower(trim(coalesce({lap_alias}.boundary_confidence, ''))) NOT IN (
            '', 'unknown', 'uncertain', 'heuristic'
        )
    """


def _lap_sample_duration_sql(lap_alias: str) -> str:
    return f"""
        (
            SELECT CASE
                WHEN COUNT(*) >= 2
                THEN CAST(
                    ROUND(
                        (MAX(lap_time_samples.current_lap) - MIN(lap_time_samples.current_lap))
                        * 1000.0
                    ) AS INTEGER
                )
            END
            FROM lap_samples AS lap_time_samples
            WHERE lap_time_samples.lap_id = {lap_alias}.id
        )
    """


def _lap_time_ms_sql(lap_alias: str = "laps", summary_alias: str = "lap_summaries") -> str:
    completed_candidate = _completed_lap_time_candidate_sql(lap_alias)
    sample_duration = _lap_sample_duration_sql(lap_alias)
    return f"""
        COALESCE(
            CASE
                WHEN json_valid({summary_alias}.summary_json)
                     AND json_type({summary_alias}.summary_json, '$.lap_time_ms') IN ('integer', 'real')
                THEN CAST(ROUND(json_extract({summary_alias}.summary_json, '$.lap_time_ms')) AS INTEGER)
            END,
            CASE
                WHEN {completed_candidate}
                THEN COALESCE(
                    {sample_duration},
                    CASE
                        WHEN {lap_alias}.ended_at_ms IS NOT NULL
                             AND {lap_alias}.ended_at_ms >= {lap_alias}.started_at_ms
                        THEN {lap_alias}.ended_at_ms - {lap_alias}.started_at_ms
                    END
                )
                ELSE NULL
            END
        )
    """


def _normalized_car_name_key(value: str | None) -> str | None:
    clean = " ".join(str(value or "").strip().lower().split())
    return f"name:{clean}" if clean else None


def _car_key_from_values(car_ordinal: object, car_name: object) -> str | None:
    try:
        ordinal = int(car_ordinal) if car_ordinal is not None else None
    except (TypeError, ValueError):
        ordinal = None
    if ordinal is not None and ordinal > 0:
        return f"ordinal:{ordinal}"
    return _normalized_car_name_key(str(car_name) if car_name is not None else None)


def _sample_from_row(
    row: sqlite3.Row,
    *,
    include_extended: bool,
) -> dict:
    sample = {column: row[column] for column in _BASE_SAMPLE_COLUMNS}
    sample["is_race_on"] = bool(sample["is_race_on"])
    if include_extended:
        for column in (*_ALL_EXTENDED_SAMPLE_COLUMNS, *_RACE_CONTROL_SAMPLE_COLUMNS):
            sample[column] = row[column]
    return sample


class TelemetryStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)

    def connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(self.db_path, factory=_ClosingConnection)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA busy_timeout=5000")
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA synchronous=NORMAL")
        return con

    def migrate(self) -> None:
        with self.connect() as con:
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("PRAGMA synchronous=NORMAL")
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at_ms INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    created_at_ms INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS auth_identities (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    provider TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    created_at_ms INTEGER NOT NULL,
                    UNIQUE(provider, subject)
                );
                CREATE TABLE IF NOT EXISTS user_settings (
                    user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                    capture_mode TEXT NOT NULL,
                    udp_host TEXT NOT NULL,
                    udp_port INTEGER NOT NULL,
                    preferred_overlay TEXT NOT NULL,
                    unit_system TEXT NOT NULL DEFAULT 'imperial',
                    fh6_media_root TEXT,
                    world_map_enabled INTEGER NOT NULL DEFAULT 0,
                    world_map_season TEXT NOT NULL DEFAULT 'summer',
                    updated_at_ms INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS track_profiles (
                    id TEXT PRIMARY KEY,
                    owner_user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
                    name TEXT NOT NULL,
                    layout TEXT NOT NULL,
                    source TEXT NOT NULL,
                    confidence TEXT NOT NULL,
                    shape_signature TEXT,
                    created_at_ms INTEGER NOT NULL,
                    updated_at_ms INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS track_assets (
                    id TEXT PRIMARY KEY,
                    track_profile_id TEXT NOT NULL REFERENCES track_profiles(id) ON DELETE CASCADE,
                    filename TEXT NOT NULL,
                    stored_path TEXT NOT NULL,
                    mime_type TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    transform_json TEXT NOT NULL,
                    created_at_ms INTEGER NOT NULL,
                    updated_at_ms INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    label TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'recording',
                    started_at_ms INTEGER NOT NULL,
                    ended_at_ms INTEGER,
                    ended_reason TEXT,
                    last_active_at_ms INTEGER,
                    car_identity_key TEXT,
                    car_ordinal INTEGER,
                    car_name TEXT,
                    car_class_id INTEGER,
                    car_class_label TEXT,
                    car_performance_index INTEGER,
                    drivetrain_id INTEGER,
                    drivetrain_label TEXT,
                    label_generated INTEGER NOT NULL DEFAULT 0,
                    auto_created_reason TEXT,
                    track_profile_id TEXT REFERENCES track_profiles(id) ON DELETE SET NULL
                );
                CREATE TABLE IF NOT EXISTS session_counters (
                    user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                    next_session_number INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS laps (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    lap_number INTEGER,
                    status TEXT NOT NULL DEFAULT 'recording',
                    started_at_ms INTEGER NOT NULL,
                    ended_at_ms INTEGER,
                    ended_reason TEXT,
                    boundary_confidence TEXT NOT NULL DEFAULT 'unknown',
                    track_profile_id TEXT REFERENCES track_profiles(id) ON DELETE SET NULL
                );
                CREATE TABLE IF NOT EXISTS packet_blobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    lap_id TEXT REFERENCES laps(id) ON DELETE SET NULL,
                    sequence INTEGER NOT NULL,
                    received_at_ms INTEGER NOT NULL,
                    game_timestamp_ms INTEGER NOT NULL,
                    lap_number INTEGER NOT NULL,
                    position_x REAL NOT NULL,
                    position_y REAL NOT NULL,
                    position_z REAL NOT NULL,
                    speed_mps REAL NOT NULL,
                    raw_packet BLOB NOT NULL
                );
                CREATE TABLE IF NOT EXISTS lap_samples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    lap_id TEXT REFERENCES laps(id) ON DELETE SET NULL,
                    sequence INTEGER NOT NULL,
                    received_at_ms INTEGER NOT NULL,
                    game_timestamp_ms INTEGER NOT NULL,
                    is_race_on INTEGER NOT NULL DEFAULT 1,
                    lap_number INTEGER NOT NULL,
                    current_lap REAL NOT NULL,
                    current_race_time REAL NOT NULL,
                    x REAL NOT NULL,
                    y REAL NOT NULL,
                    z REAL NOT NULL,
                    speed_mps REAL NOT NULL,
                    uncertainty TEXT,
                    throttle INTEGER NOT NULL,
                    brake INTEGER NOT NULL,
                    steer INTEGER NOT NULL,
                    gear INTEGER NOT NULL,
                    combined_slip REAL,
                    rear_combined_slip REAL,
                    tire_temp_front_left REAL,
                    tire_temp_front_right REAL,
                    tire_temp_rear_left REAL,
                    tire_temp_rear_right REAL,
                    suspension_travel_front_left REAL,
                    suspension_travel_front_right REAL,
                    suspension_travel_rear_left REAL,
                    suspension_travel_rear_right REAL,
                    current_rpm REAL,
                    engine_max_rpm REAL,
                    acceleration_x REAL,
                    acceleration_y REAL,
                    acceleration_z REAL,
                    velocity_x REAL,
                    velocity_y REAL,
                    velocity_z REAL,
                    angular_velocity_x REAL,
                    angular_velocity_y REAL,
                    angular_velocity_z REAL,
                    yaw REAL,
                    pitch REAL,
                    roll REAL,
                    smashable_vel_diff REAL,
                    smashable_mass REAL,
                    power_w REAL,
                    torque_nm REAL,
                    boost_bar REAL,
                    engine_idle_rpm REAL,
                    fuel REAL,
                    distance_traveled_m REAL,
                    best_lap REAL,
                    last_lap REAL,
                    race_position INTEGER,
                    clutch INTEGER,
                    handbrake INTEGER,
                    normalized_driving_line INTEGER,
                    normalized_ai_brake_difference INTEGER,
                    tire_slip_ratio_front_left REAL,
                    tire_slip_ratio_front_right REAL,
                    tire_slip_ratio_rear_left REAL,
                    tire_slip_ratio_rear_right REAL,
                    tire_slip_angle_front_left REAL,
                    tire_slip_angle_front_right REAL,
                    tire_slip_angle_rear_left REAL,
                    tire_slip_angle_rear_right REAL,
                    tire_combined_slip_front_left REAL,
                    tire_combined_slip_front_right REAL,
                    tire_combined_slip_rear_left REAL,
                    tire_combined_slip_rear_right REAL,
                    wheel_rotation_speed_front_left REAL,
                    wheel_rotation_speed_front_right REAL,
                    wheel_rotation_speed_rear_left REAL,
                    wheel_rotation_speed_rear_right REAL,
                    wheel_on_rumble_strip_front_left INTEGER,
                    wheel_on_rumble_strip_front_right INTEGER,
                    wheel_on_rumble_strip_rear_left INTEGER,
                    wheel_on_rumble_strip_rear_right INTEGER,
                    wheel_in_puddle_depth_front_left INTEGER,
                    wheel_in_puddle_depth_front_right INTEGER,
                    wheel_in_puddle_depth_rear_left INTEGER,
                    wheel_in_puddle_depth_rear_right INTEGER,
                    surface_rumble_front_left REAL,
                    surface_rumble_front_right REAL,
                    surface_rumble_rear_left REAL,
                    surface_rumble_rear_right REAL,
                    suspension_travel_meters_front_left REAL,
                    suspension_travel_meters_front_right REAL,
                    suspension_travel_meters_rear_left REAL,
                    suspension_travel_meters_rear_right REAL
                );
                CREATE INDEX IF NOT EXISTS idx_lap_samples_session_time
                ON lap_samples(session_id, game_timestamp_ms);
                CREATE INDEX IF NOT EXISTS idx_lap_samples_session_sequence
                ON lap_samples(session_id, sequence);
                CREATE INDEX IF NOT EXISTS idx_lap_samples_lap_current_lap
                ON lap_samples(lap_id, current_lap);
                CREATE INDEX IF NOT EXISTS idx_packet_blobs_session_sequence
                ON packet_blobs(session_id, sequence);
                CREATE TABLE IF NOT EXISTS lap_summaries (
                    lap_id TEXT PRIMARY KEY REFERENCES laps(id) ON DELETE CASCADE,
                    summary_json TEXT NOT NULL,
                    created_at_ms INTEGER NOT NULL,
                    updated_at_ms INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS comparison_refs (
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    scope TEXT NOT NULL,
                    context_key TEXT NOT NULL,
                    lap_id TEXT NOT NULL REFERENCES laps(id) ON DELETE CASCADE,
                    pinned_at_ms INTEGER NOT NULL,
                    PRIMARY KEY(user_id, scope, context_key),
                    CHECK(scope IN ('track', 'track_car', 'track_car_build'))
                );
                CREATE INDEX IF NOT EXISTS idx_comparison_refs_lap
                ON comparison_refs(lap_id);
                CREATE TABLE IF NOT EXISTS cars (
                    ordinal INTEGER PRIMARY KEY,
                    display_name TEXT,
                    model_short TEXT,
                    make TEXT,
                    model TEXT,
                    year INTEGER,
                    base_class_label TEXT,
                    base_pi INTEGER,
                    car_type TEXT,
                    country TEXT,
                    value_cr INTEGER,
                    rarity TEXT,
                    source TEXT,
                    source_info TEXT,
                    asset_name TEXT,
                    asset_zip TEXT,
                    catalog_source TEXT NOT NULL DEFAULT 'unknown',
                    updated_at_ms INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS game_tracks (
                    track_key TEXT PRIMARY KEY,
                    source_dataset_key INTEGER,
                    route_id INTEGER,
                    custom_route_id INTEGER,
                    media_track_id INTEGER,
                    media_track_name TEXT,
                    ribbon_config TEXT,
                    display_name TEXT,
                    short_display_name TEXT,
                    short_display_name_all_caps TEXT,
                    description TEXT,
                    display_name_key TEXT,
                    short_display_name_key TEXT,
                    short_display_name_all_caps_key TEXT,
                    description_key TEXT,
                    route_activation_trigger_zone_name TEXT,
                    use_cross_country_ai INTEGER,
                    stray_warning_distance REAL,
                    stray_teleport_distance REAL,
                    source_file TEXT,
                    catalog_source TEXT NOT NULL DEFAULT 'unknown',
                    updated_at_ms INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_game_tracks_route_id
                ON game_tracks(route_id);
                CREATE INDEX IF NOT EXISTS idx_game_tracks_custom_route_id
                ON game_tracks(custom_route_id);
                CREATE INDEX IF NOT EXISTS idx_game_tracks_media_track
                ON game_tracks(media_track_name, ribbon_config);
                CREATE TABLE IF NOT EXISTS game_map_regions (
                    region_key TEXT PRIMARY KEY,
                    english_name TEXT,
                    english_short_name TEXT,
                    japanese_name TEXT,
                    japanese_short_name TEXT,
                    name_key TEXT,
                    short_name_key TEXT,
                    locator_collection_name TEXT,
                    top_image_path TEXT,
                    map_tile_mascot_image TEXT,
                    map_hover_fmod_event TEXT,
                    first_time_enter_fmod_event TEXT,
                    rich_presence_event TEXT,
                    full_reveal_percentage INTEGER,
                    announcement_ie_state TEXT,
                    source_file TEXT,
                    catalog_source TEXT NOT NULL DEFAULT 'unknown',
                    updated_at_ms INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_game_map_regions_locator_collection
                ON game_map_regions(locator_collection_name);
                CREATE TABLE IF NOT EXISTS game_track_locators (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_file TEXT NOT NULL,
                    media_track_name TEXT,
                    locator_collection TEXT NOT NULL,
                    locator_name TEXT NOT NULL,
                    locator_kind TEXT NOT NULL,
                    route_id INTEGER,
                    x REAL NOT NULL,
                    y REAL NOT NULL,
                    z REAL NOT NULL,
                    heading_yaw_rad REAL,
                    transform_json TEXT NOT NULL,
                    catalog_source TEXT NOT NULL DEFAULT 'unknown',
                    updated_at_ms INTEGER NOT NULL,
                    UNIQUE(source_file, locator_name)
                );
                CREATE INDEX IF NOT EXISTS idx_game_track_locators_route
                ON game_track_locators(route_id, locator_kind);
                CREATE INDEX IF NOT EXISTS idx_game_track_locators_collection
                ON game_track_locators(locator_collection);
                CREATE INDEX IF NOT EXISTS idx_game_track_locators_position
                ON game_track_locators(x, z);
                CREATE TABLE IF NOT EXISTS game_track_profile_links (
                    track_key TEXT PRIMARY KEY REFERENCES game_tracks(track_key) ON DELETE CASCADE,
                    track_profile_id TEXT NOT NULL UNIQUE REFERENCES track_profiles(id) ON DELETE CASCADE,
                    created_at_ms INTEGER NOT NULL,
                    updated_at_ms INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS track_match_candidates (
                    lap_id TEXT NOT NULL REFERENCES laps(id) ON DELETE CASCADE,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    matcher_version TEXT NOT NULL,
                    candidate_rank INTEGER NOT NULL,
                    candidate_kind TEXT NOT NULL,
                    track_key TEXT REFERENCES game_tracks(track_key) ON DELETE SET NULL,
                    track_profile_id TEXT REFERENCES track_profiles(id) ON DELETE SET NULL,
                    route_id INTEGER,
                    display_name TEXT,
                    confidence REAL NOT NULL,
                    score_components_json TEXT NOT NULL,
                    reasons_json TEXT NOT NULL,
                    is_auto_assignable INTEGER NOT NULL DEFAULT 0,
                    assigned_track_profile_id TEXT REFERENCES track_profiles(id) ON DELETE SET NULL,
                    created_at_ms INTEGER NOT NULL,
                    PRIMARY KEY(lap_id, matcher_version, candidate_rank)
                );
                CREATE INDEX IF NOT EXISTS idx_track_match_candidates_lap
                ON track_match_candidates(lap_id, matcher_version, candidate_rank);
                CREATE INDEX IF NOT EXISTS idx_track_match_candidates_track
                ON track_match_candidates(track_key, confidence);
                CREATE TABLE IF NOT EXISTS world_map_tile_sets (
                    id TEXT PRIMARY KEY,
                    game TEXT NOT NULL,
                    map_name TEXT NOT NULL,
                    season TEXT NOT NULL,
                    source_zip_path TEXT NOT NULL,
                    source_zip_mtime_ms INTEGER NOT NULL,
                    source_zip_size_bytes INTEGER NOT NULL,
                    cache_dir TEXT NOT NULL,
                    tile_format TEXT NOT NULL,
                    tile_size INTEGER NOT NULL,
                    min_zoom INTEGER NOT NULL,
                    max_zoom INTEGER NOT NULL,
                    world_origin_x REAL NOT NULL,
                    world_origin_z REAL NOT NULL,
                    world_size REAL NOT NULL,
                    status TEXT NOT NULL,
                    manifest_json TEXT NOT NULL,
                    error_message TEXT,
                    last_built_at_ms INTEGER,
                    updated_at_ms INTEGER NOT NULL,
                    UNIQUE(game, map_name, season, source_zip_path)
                );
                CREATE INDEX IF NOT EXISTS idx_world_map_tile_sets_lookup
                ON world_map_tile_sets(game, map_name, season, status, updated_at_ms);
                CREATE TABLE IF NOT EXISTS issue_markers (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    lap_id TEXT REFERENCES laps(id) ON DELETE CASCADE,
                    start_sequence INTEGER NOT NULL,
                    end_sequence INTEGER NOT NULL,
                    metric TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    ruleset_version INTEGER NOT NULL,
                    confidence REAL NOT NULL,
                    anchor_sequence INTEGER,
                    issue_kind TEXT,
                    actual_value REAL,
                    threshold_value REAL,
                    threshold_operator TEXT,
                    value_label TEXT,
                    value_unit TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_issue_markers_lap_sequence
                ON issue_markers(lap_id, start_sequence, end_sequence);
                CREATE INDEX IF NOT EXISTS idx_issue_markers_session_sequence
                ON issue_markers(session_id, start_sequence);
                """
            )
            self._apply_v2_migrations(con)
            self._apply_v3_migrations(con)
            self._apply_v4_session_management_migrations(con)
            self._apply_session_car_identity_migrations(con)
            self._apply_v5_live_race_state_migrations(con)
            self._apply_v6_live_race_state_backfill(con)
            self._apply_v7_dashboard_sample_migrations(con)
            self._apply_v8_dashboard_sample_backfill(con)
            self._apply_v9_issue_marker_detail_migrations(con)
            self._apply_v10_smashable_sample_backfill(con)
            self._apply_v11_race_control_sample_migrations(con)
            self._apply_user_settings_migrations(con)
            self._apply_world_map_migrations(con)
            self._apply_track_profile_migrations(con)
            self._apply_car_catalog_migrations(con)
            self._apply_track_catalog_migrations(con)
            self._apply_track_match_migrations(con)
            self._apply_v11_lifetime_stats_migrations(con)
            self._apply_feedback_migrations(con)
            self._ensure_reference_context_indexes(con)
            now_ms = _now_ms()
            for version in range(1, SCHEMA_VERSION + 1):
                con.execute(
                    "INSERT OR IGNORE INTO schema_migrations(version, applied_at_ms) VALUES (?, ?)",
                    (version, now_ms),
                )
            con.execute(
                "INSERT OR IGNORE INTO users(id, display_name, created_at_ms) VALUES (?, ?, ?)",
                (LOCAL_USER_ID, "Local User", now_ms),
            )
            con.execute(
                """
                INSERT OR IGNORE INTO auth_identities(id, user_id, provider, subject, created_at_ms)
                VALUES (?, ?, ?, ?, ?)
                """,
                (str(uuid.uuid4()), LOCAL_USER_ID, "local", "local", now_ms),
            )
            con.execute(
                """
                INSERT OR IGNORE INTO user_settings(user_id, capture_mode, udp_host, udp_port, preferred_overlay, unit_system, updated_at_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (LOCAL_USER_ID, "auto", "127.0.0.1", 5400, "issues", "imperial", now_ms),
            )

    def feedback_state_value(self, key: str) -> str | None:
        with self.connect() as con:
            row = con.execute(
                "SELECT value FROM feedback_state WHERE key = ?",
                (key,),
            ).fetchone()
        return None if row is None else str(row["value"])

    def set_feedback_state_value(self, key: str, value: str) -> None:
        now_ms = _now_ms()
        with self.connect() as con:
            con.execute(
                """
                INSERT INTO feedback_state(key, value, updated_at_ms)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                  value = excluded.value,
                  updated_at_ms = excluded.updated_at_ms
                """,
                (key, value, now_ms),
            )

    def feedback_report_exists(self, report_ref: str) -> bool:
        with self.connect() as con:
            row = con.execute(
                "SELECT 1 FROM feedback_outbox WHERE report_ref = ?",
                (report_ref,),
            ).fetchone()
        return row is not None

    def enqueue_feedback_report(
        self,
        report_ref: str,
        payload_json: str,
        now_ms: int,
        next_attempt_at_ms: int,
    ) -> None:
        with self.connect() as con:
            con.execute(
                """
                INSERT INTO feedback_outbox(
                    report_ref, payload_json, status, attempt_count, last_error,
                    created_at_ms, updated_at_ms, next_attempt_at_ms,
                    issue_number, issue_url
                )
                VALUES (?, ?, 'pending', 0, NULL, ?, ?, ?, NULL, NULL)
                ON CONFLICT(report_ref) DO UPDATE SET
                  payload_json = excluded.payload_json,
                  status = CASE
                    WHEN feedback_outbox.status = 'sent' THEN feedback_outbox.status
                    ELSE 'pending'
                  END,
                  updated_at_ms = excluded.updated_at_ms,
                  next_attempt_at_ms = CASE
                    WHEN feedback_outbox.status = 'sent' THEN feedback_outbox.next_attempt_at_ms
                    ELSE excluded.next_attempt_at_ms
                  END
                """,
                (report_ref, payload_json, int(now_ms), int(now_ms), int(next_attempt_at_ms)),
            )

    def mark_feedback_report_sent(
        self,
        report_ref: str,
        issue_number: int | None,
        issue_url: str | None,
        now_ms: int,
    ) -> None:
        with self.connect() as con:
            con.execute(
                """
                UPDATE feedback_outbox
                SET status = 'sent',
                    last_error = NULL,
                    updated_at_ms = ?,
                    next_attempt_at_ms = ?,
                    issue_number = ?,
                    issue_url = ?
                WHERE report_ref = ?
                """,
                (int(now_ms), int(now_ms), issue_number, issue_url, report_ref),
            )

    def mark_feedback_report_failed(
        self,
        report_ref: str,
        error: str,
        now_ms: int,
        next_attempt_at_ms: int,
    ) -> None:
        with self.connect() as con:
            con.execute(
                """
                UPDATE feedback_outbox
                SET status = 'pending',
                    attempt_count = attempt_count + 1,
                    last_error = ?,
                    updated_at_ms = ?,
                    next_attempt_at_ms = ?
                WHERE report_ref = ? AND status <> 'sent'
                """,
                (error, int(now_ms), int(next_attempt_at_ms), report_ref),
            )

    def delete_feedback_report(self, report_ref: str) -> None:
        with self.connect() as con:
            con.execute(
                "DELETE FROM feedback_outbox WHERE report_ref = ?",
                (report_ref,),
            )

    def pending_feedback_reports(self, now_ms: int, limit: int = 5) -> list[dict]:
        with self.connect() as con:
            rows = con.execute(
                """
                SELECT report_ref, payload_json, status, attempt_count, last_error,
                       created_at_ms, updated_at_ms, next_attempt_at_ms,
                       issue_number, issue_url
                FROM feedback_outbox
                WHERE status = 'pending'
                  AND next_attempt_at_ms <= ?
                ORDER BY created_at_ms, report_ref
                LIMIT ?
                """,
                (int(now_ms), max(1, int(limit))),
            ).fetchall()
        return [dict(row) for row in rows]

    def prune_feedback_outbox(
        self,
        now_ms: int,
        max_pending: int = 25,
        ttl_ms: int = 30 * 24 * 60 * 60 * 1000,
    ) -> None:
        cutoff_ms = int(now_ms) - int(ttl_ms)
        max_pending = max(0, int(max_pending))
        with self.connect() as con:
            con.execute(
                """
                DELETE FROM feedback_outbox
                WHERE status <> 'sent'
                  AND created_at_ms < ?
                """,
                (cutoff_ms,),
            )
            con.execute(
                """
                DELETE FROM feedback_outbox
                WHERE status = 'sent'
                  AND updated_at_ms < ?
                """,
                (cutoff_ms,),
            )
            if max_pending == 0:
                con.execute("DELETE FROM feedback_outbox WHERE status = 'pending'")
            else:
                con.execute(
                    """
                    DELETE FROM feedback_outbox
                    WHERE report_ref IN (
                        SELECT report_ref
                        FROM feedback_outbox
                        WHERE status = 'pending'
                        ORDER BY created_at_ms DESC, report_ref DESC
                        LIMIT -1 OFFSET ?
                    )
                    """,
                    (max_pending,),
                )

    def database_size_info(self) -> dict:
        with self.connect() as con:
            page_size = int(con.execute("PRAGMA page_size").fetchone()[0])
            page_count = int(con.execute("PRAGMA page_count").fetchone()[0])
            freelist_count = int(con.execute("PRAGMA freelist_count").fetchone()[0])
        file_bytes = self.db_path.stat().st_size if self.db_path.exists() else 0
        freelist_bytes = page_size * freelist_count
        allocated_bytes = page_size * page_count
        used_bytes = max(allocated_bytes - freelist_bytes, 0)
        freelist_ratio = (freelist_count / page_count) if page_count else 0.0
        return {
            "file_bytes": int(file_bytes),
            "page_size": page_size,
            "page_count": page_count,
            "freelist_count": freelist_count,
            "allocated_bytes": allocated_bytes,
            "freelist_bytes": freelist_bytes,
            "used_bytes": used_bytes,
            "freelist_ratio": freelist_ratio,
        }

    def count_prunable_unassigned_non_race_telemetry(self) -> int:
        with self.connect() as con:
            return int(
                con.execute(
                    f"""
                    SELECT COUNT(*)
                    FROM lap_samples
                    WHERE {_PRUNABLE_UNASSIGNED_NON_RACE_SAMPLE_PREDICATE}
                    """
                ).fetchone()[0]
            )

    def prune_unassigned_non_race_telemetry(
        self,
        *,
        max_rows: int | None = None,
        dry_run: bool = False,
    ) -> dict:
        """Delete menu/off-race telemetry that is not assigned to any lap.

        The predicate is intentionally narrow. It removes only unassigned rows
        that are clearly zero-state non-race noise, leaving race-on, mid-lap
        pause, and lap-associated telemetry intact. Raw packet rows are deleted
        first using the packet identity that ingest writes to both tables
        because ``packet_blobs`` does not store decoded race fields.
        """

        if max_rows is not None and int(max_rows) <= 0:
            raise ValueError("max_rows must be positive")

        limit_sql = "" if max_rows is None else "LIMIT ?"
        params: tuple[object, ...] = () if max_rows is None else (int(max_rows),)
        with self.connect() as con:
            con.execute(
                """
                CREATE TEMP TABLE prune_unassigned_non_race_keys (
                    session_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    received_at_ms INTEGER NOT NULL,
                    game_timestamp_ms INTEGER NOT NULL
                )
                """
            )
            con.execute(
                f"""
                INSERT INTO prune_unassigned_non_race_keys(
                    session_id, sequence, received_at_ms, game_timestamp_ms
                )
                SELECT session_id, sequence, received_at_ms, game_timestamp_ms
                FROM lap_samples
                WHERE {_PRUNABLE_UNASSIGNED_NON_RACE_SAMPLE_PREDICATE}
                ORDER BY id
                {limit_sql}
                """,
                params,
            )
            con.execute(
                """
                CREATE INDEX idx_prune_unassigned_non_race_keys
                ON prune_unassigned_non_race_keys(
                    session_id, sequence, received_at_ms, game_timestamp_ms
                )
                """
            )
            target_samples = int(
                con.execute(
                    "SELECT COUNT(*) FROM prune_unassigned_non_race_keys"
                ).fetchone()[0]
            )
            if dry_run:
                return {
                    "dry_run": True,
                    "target_sample_count": target_samples,
                    "deleted_packet_count": 0,
                    "deleted_sample_count": 0,
                }

            packet_cursor = con.execute(
                """
                DELETE FROM packet_blobs
                WHERE id IN (
                    SELECT packet_blobs.id
                    FROM packet_blobs
                    JOIN prune_unassigned_non_race_keys AS prune_keys
                      ON prune_keys.session_id = packet_blobs.session_id
                     AND prune_keys.sequence = packet_blobs.sequence
                     AND prune_keys.received_at_ms = packet_blobs.received_at_ms
                     AND prune_keys.game_timestamp_ms = packet_blobs.game_timestamp_ms
                    WHERE packet_blobs.lap_id IS NULL
                )
                """
            )
            sample_cursor = con.execute(
                f"""
                DELETE FROM lap_samples
                WHERE id IN (
                    SELECT lap_samples.id
                    FROM lap_samples
                    JOIN prune_unassigned_non_race_keys AS prune_keys
                      ON prune_keys.session_id = lap_samples.session_id
                     AND prune_keys.sequence = lap_samples.sequence
                     AND prune_keys.received_at_ms = lap_samples.received_at_ms
                     AND prune_keys.game_timestamp_ms = lap_samples.game_timestamp_ms
                    WHERE {_PRUNABLE_UNASSIGNED_NON_RACE_SAMPLE_PREDICATE}
                )
                """
            )
            return {
                "dry_run": False,
                "target_sample_count": target_samples,
                "deleted_packet_count": max(int(packet_cursor.rowcount), 0),
                "deleted_sample_count": max(int(sample_cursor.rowcount), 0),
            }

    def wal_checkpoint_truncate(self) -> dict:
        with self.connect() as con:
            row = con.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        return {
            "busy": int(row[0]),
            "log_frames": int(row[1]),
            "checkpointed_frames": int(row[2]),
        }

    def vacuum(self) -> dict:
        before = self.database_size_info()
        con = self.connect()
        try:
            con.isolation_level = None
            con.execute("VACUUM")
        finally:
            con.close()
        return {"ran": True, "before": before, "after": self.database_size_info()}

    def vacuum_if_needed(
        self,
        *,
        min_freelist_bytes: int,
        min_freelist_ratio: float,
        force: bool = False,
    ) -> dict:
        """Run full SQLite VACUUM only when explicitly forced or thresholds pass.

        VACUUM needs exclusive database access, so callers should use this for
        operator-triggered/offline maintenance rather than during active capture.
        """

        before = self.database_size_info()
        should_run = force or (
            int(before["freelist_bytes"]) >= int(min_freelist_bytes)
            and float(before["freelist_ratio"]) >= float(min_freelist_ratio)
        )
        if not should_run:
            return {
                "ran": False,
                "reason": "below_threshold",
                "before": before,
                "after": before,
            }
        self.wal_checkpoint_truncate()
        result = self.vacuum()
        result["reason"] = "forced" if force else "threshold_met"
        return result


    def _apply_v2_migrations(self, con: sqlite3.Connection) -> None:
        """Bring legacy v1 databases up to the v2 lap/session history schema."""

        _ensure_column(con, "sessions", "status", "status TEXT NOT NULL DEFAULT 'recording'")
        _ensure_column(con, "sessions", "ended_at_ms", "ended_at_ms INTEGER")
        _ensure_column(con, "sessions", "ended_reason", "ended_reason TEXT")

        _ensure_column(con, "laps", "lap_number", "lap_number INTEGER")
        _ensure_column(con, "laps", "status", "status TEXT NOT NULL DEFAULT 'recording'")
        _ensure_column(con, "laps", "ended_at_ms", "ended_at_ms INTEGER")
        _ensure_column(con, "laps", "ended_reason", "ended_reason TEXT")
        _ensure_column(
            con,
            "laps",
            "boundary_confidence",
            "boundary_confidence TEXT NOT NULL DEFAULT 'unknown'",
        )

        _ensure_column(con, "packet_blobs", "lap_id", "lap_id TEXT")
        _ensure_column(con, "lap_samples", "lap_id", "lap_id TEXT")
        _ensure_column(con, "lap_samples", "combined_slip", "combined_slip REAL")
        _ensure_column(
            con, "lap_samples", "rear_combined_slip", "rear_combined_slip REAL"
        )
        _ensure_column(
            con,
            "lap_samples",
            "tire_temp_front_left",
            "tire_temp_front_left REAL",
        )
        _ensure_column(
            con,
            "lap_samples",
            "tire_temp_front_right",
            "tire_temp_front_right REAL",
        )
        _ensure_column(
            con, "lap_samples", "tire_temp_rear_left", "tire_temp_rear_left REAL"
        )
        _ensure_column(
            con, "lap_samples", "tire_temp_rear_right", "tire_temp_rear_right REAL"
        )
        _ensure_column(
            con,
            "lap_samples",
            "suspension_travel_front_left",
            "suspension_travel_front_left REAL",
        )
        _ensure_column(
            con,
            "lap_samples",
            "suspension_travel_front_right",
            "suspension_travel_front_right REAL",
        )
        _ensure_column(
            con,
            "lap_samples",
            "suspension_travel_rear_left",
            "suspension_travel_rear_left REAL",
        )
        _ensure_column(
            con,
            "lap_samples",
            "suspension_travel_rear_right",
            "suspension_travel_rear_right REAL",
        )
        _ensure_column(con, "lap_samples", "current_rpm", "current_rpm REAL")
        _ensure_column(con, "lap_samples", "engine_max_rpm", "engine_max_rpm REAL")

        con.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_packet_blobs_session_lap_time
            ON packet_blobs(session_id, lap_id, game_timestamp_ms);
            CREATE INDEX IF NOT EXISTS idx_packet_blobs_session_sequence
            ON packet_blobs(session_id, sequence);
            CREATE INDEX IF NOT EXISTS idx_lap_samples_lap_sequence
            ON lap_samples(lap_id, sequence);
            CREATE INDEX IF NOT EXISTS idx_lap_samples_lap_current_lap
            ON lap_samples(lap_id, current_lap);
            CREATE INDEX IF NOT EXISTS idx_laps_user_started
            ON laps(user_id, started_at_ms);
            CREATE INDEX IF NOT EXISTS idx_sessions_user_started
            ON sessions(user_id, started_at_ms);
            CREATE TABLE IF NOT EXISTS lap_summaries (
                lap_id TEXT PRIMARY KEY REFERENCES laps(id) ON DELETE CASCADE,
                summary_json TEXT NOT NULL,
                created_at_ms INTEGER NOT NULL,
                updated_at_ms INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS issue_markers (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                lap_id TEXT REFERENCES laps(id) ON DELETE CASCADE,
                start_sequence INTEGER NOT NULL,
                end_sequence INTEGER NOT NULL,
                metric TEXT NOT NULL,
                severity TEXT NOT NULL,
                reason TEXT NOT NULL,
                ruleset_version INTEGER NOT NULL,
                confidence REAL NOT NULL,
                anchor_sequence INTEGER,
                issue_kind TEXT,
                actual_value REAL,
                threshold_value REAL,
                threshold_operator TEXT,
                value_label TEXT,
                value_unit TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_issue_markers_lap_sequence
            ON issue_markers(lap_id, start_sequence, end_sequence);
            CREATE INDEX IF NOT EXISTS idx_issue_markers_session_sequence
            ON issue_markers(session_id, start_sequence);
            """
        )

    def _apply_v3_migrations(self, con: sqlite3.Connection) -> None:
        """Bring v2 databases up to the v3 comparison-reference schema."""

        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS comparison_refs (
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                scope TEXT NOT NULL,
                context_key TEXT NOT NULL,
                lap_id TEXT NOT NULL REFERENCES laps(id) ON DELETE CASCADE,
                pinned_at_ms INTEGER NOT NULL,
                PRIMARY KEY(user_id, scope, context_key),
                CHECK(scope IN ('track', 'track_car', 'track_car_build'))
            );
            CREATE INDEX IF NOT EXISTS idx_comparison_refs_lap
            ON comparison_refs(lap_id);
            """
        )

    def _apply_v4_session_management_migrations(self, con: sqlite3.Connection) -> None:
        """Bring databases up to the v4 first-class session management schema."""

        _ensure_column(con, "sessions", "last_active_at_ms", "last_active_at_ms INTEGER")
        now_ms = _now_ms()
        con.execute(
            """
            UPDATE sessions
            SET last_active_at_ms = COALESCE(ended_at_ms, started_at_ms, ?)
            WHERE last_active_at_ms IS NULL
            """,
            (now_ms,),
        )
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS session_counters (
                user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                next_session_number INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_sessions_user_last_active
            ON sessions(user_id, last_active_at_ms);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_sessions_one_active_user
            ON sessions(user_id)
            WHERE status = 'active';
            """
        )
        con.execute(
            """
            INSERT OR IGNORE INTO session_counters(user_id, next_session_number)
            SELECT users.id,
                   COALESCE(
                       (
                           SELECT MAX(CAST(substr(label, 9) AS INTEGER)) + 1
                           FROM sessions
                           WHERE user_id = users.id
                             AND label GLOB 'Session [0-9]*'
                       ),
                       (SELECT COUNT(*) + 1 FROM sessions WHERE user_id = users.id)
                   )
            FROM users
            """
        )


    def _apply_session_car_identity_migrations(self, con: sqlite3.Connection) -> None:
        """Ensure sessions persist one car identity tuple and label provenance."""

        _ensure_column(con, "sessions", "car_identity_key", "car_identity_key TEXT")
        _ensure_column(con, "sessions", "car_ordinal", "car_ordinal INTEGER")
        _ensure_column(con, "sessions", "car_name", "car_name TEXT")
        _ensure_column(con, "sessions", "car_class_id", "car_class_id INTEGER")
        _ensure_column(con, "sessions", "car_class_label", "car_class_label TEXT")
        _ensure_column(
            con,
            "sessions",
            "car_performance_index",
            "car_performance_index INTEGER",
        )
        _ensure_column(con, "sessions", "drivetrain_id", "drivetrain_id INTEGER")
        _ensure_column(con, "sessions", "drivetrain_label", "drivetrain_label TEXT")
        _ensure_column(
            con,
            "sessions",
            "label_generated",
            "label_generated INTEGER NOT NULL DEFAULT 0",
        )
        _ensure_column(
            con,
            "sessions",
            "auto_created_reason",
            "auto_created_reason TEXT",
        )
        con.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_sessions_car_identity
            ON sessions(user_id, car_identity_key, started_at_ms)
            """
        )

    def _apply_v5_live_race_state_migrations(self, con: sqlite3.Connection) -> None:
        """Persist packet race state so live recovery can exclude menu packets."""

        _ensure_column(
            con,
            "lap_samples",
            "is_race_on",
            "is_race_on INTEGER NOT NULL DEFAULT 1",
        )
        con.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_lap_samples_session_race_sequence
            ON lap_samples(session_id, is_race_on, sequence)
            """
        )

    def _apply_v6_live_race_state_backfill(self, con: sqlite3.Connection) -> None:
        """Recover legacy race state from raw packets after the v5 column add.

        v5 added ``lap_samples.is_race_on`` with a default of true.  That was
        safe for new ingestion, but existing databases may already contain
        pause/menu packets whose raw blobs say ``IsRaceOn=0``.  Backfill once
        from ``packet_blobs.raw_packet`` so recovered live history does not draw
        those zero-position pause packets as part of a lap.
        """

        if self._schema_migration_applied(con, 6):
            return
        if "is_race_on" not in _table_columns(con, "lap_samples"):
            return

        from telemetry_tracker.packet_bridge import decode_packet

        last_sample_id = 0
        batch_size = 1_000
        while True:
            rows = con.execute(
                """
                SELECT lap_samples.id AS sample_id,
                       lap_samples.is_race_on AS stored_is_race_on,
                       packet_blobs.raw_packet AS raw_packet
                FROM lap_samples
                INNER JOIN packet_blobs
                  ON packet_blobs.session_id = lap_samples.session_id
                 AND packet_blobs.sequence = lap_samples.sequence
                 AND packet_blobs.received_at_ms = lap_samples.received_at_ms
                 AND packet_blobs.game_timestamp_ms = lap_samples.game_timestamp_ms
                WHERE lap_samples.id > ?
                ORDER BY lap_samples.id
                LIMIT ?
                """,
                (last_sample_id, batch_size),
            ).fetchall()
            if not rows:
                break

            updates: list[tuple[int, int]] = []
            for row in rows:
                sample_id = int(row["sample_id"])
                last_sample_id = sample_id
                try:
                    is_race_on = _decoded_is_race_on(decode_packet(row["raw_packet"]))
                except Exception:
                    continue
                stored_is_race_on = int(bool(row["stored_is_race_on"]))
                next_is_race_on = int(is_race_on)
                if stored_is_race_on != next_is_race_on:
                    updates.append((next_is_race_on, sample_id))

            if updates:
                con.executemany(
                    "UPDATE lap_samples SET is_race_on = ? WHERE id = ?",
                    updates,
                )


    def _apply_v7_dashboard_sample_migrations(self, con: sqlite3.Connection) -> None:
        """Persist dashboard telemetry fields on recorded lap samples."""

        for column_name, column_type in _DASHBOARD_SAMPLE_COLUMN_DEFINITIONS:
            _ensure_column(
                con,
                "lap_samples",
                column_name,
                f"{column_name} {column_type}",
            )

    def _apply_v8_dashboard_sample_backfill(self, con: sqlite3.Connection) -> None:
        """Hydrate legacy lap samples from their saved raw packet bytes.

        v7 added the dashboard columns to ``lap_samples`` and new recordings
        write them directly.  Older recordings still have the raw FH Data Out
        packet bytes in ``packet_blobs``, so decode those packets once and
        populate the same persisted sample fields that new captures receive.
        """

        if self._schema_migration_applied(con, 8):
            return

        from telemetry_tracker.packet_bridge import decode_packet, packet_to_live_fields

        set_columns = ", ".join(f"{column} = ?" for column in _ALL_EXTENDED_SAMPLE_COLUMNS)
        update_sql = f"UPDATE lap_samples SET {set_columns} WHERE id = ?"
        last_sample_id = 0
        batch_size = 1_000
        while True:
            rows = con.execute(
                """
                SELECT lap_samples.id AS sample_id,
                       lap_samples.sequence AS sequence,
                       lap_samples.received_at_ms AS received_at_ms,
                       packet_blobs.raw_packet AS raw_packet
                FROM lap_samples
                INNER JOIN packet_blobs
                  ON packet_blobs.session_id = lap_samples.session_id
                 AND packet_blobs.sequence = lap_samples.sequence
                 AND packet_blobs.received_at_ms = lap_samples.received_at_ms
                 AND packet_blobs.game_timestamp_ms = lap_samples.game_timestamp_ms
                WHERE lap_samples.id > ?
                ORDER BY lap_samples.id
                LIMIT ?
                """,
                (last_sample_id, batch_size),
            ).fetchall()
            if not rows:
                break

            updates: list[tuple] = []
            for row in rows:
                sample_id = int(row["sample_id"])
                last_sample_id = sample_id
                try:
                    live_fields = packet_to_live_fields(
                        decode_packet(row["raw_packet"]),
                        sequence=int(row["sequence"]),
                        received_at_ms=int(row["received_at_ms"]),
                    )
                except Exception:
                    continue
                updates.append(
                    tuple(live_fields.get(column) for column in _ALL_EXTENDED_SAMPLE_COLUMNS)
                    + (sample_id,)
                )

            if updates:
                con.executemany(update_sql, updates)

    def _apply_v9_issue_marker_detail_migrations(self, con: sqlite3.Connection) -> None:
        """Add display-ready issue marker detail columns for route issue popovers."""

        _ensure_column(con, "issue_markers", "anchor_sequence", "anchor_sequence INTEGER")
        _ensure_column(con, "issue_markers", "issue_kind", "issue_kind TEXT")
        _ensure_column(con, "issue_markers", "actual_value", "actual_value REAL")
        _ensure_column(con, "issue_markers", "threshold_value", "threshold_value REAL")
        _ensure_column(con, "issue_markers", "threshold_operator", "threshold_operator TEXT")
        _ensure_column(con, "issue_markers", "value_label", "value_label TEXT")
        _ensure_column(con, "issue_markers", "value_unit", "value_unit TEXT")

    def _apply_v10_smashable_sample_backfill(self, con: sqlite3.Connection) -> None:
        """Hydrate smashable collision sample fields added after the v8 backfill."""

        if self._schema_migration_applied(con, 10):
            return

        from telemetry_tracker.packet_bridge import decode_packet, packet_to_live_fields

        update_sql = (
            "UPDATE lap_samples "
            "SET smashable_vel_diff = ?, smashable_mass = ? "
            "WHERE id = ?"
        )
        last_sample_id = 0
        batch_size = 1_000
        while True:
            rows = con.execute(
                """
                SELECT lap_samples.id AS sample_id,
                       lap_samples.sequence AS sequence,
                       lap_samples.received_at_ms AS received_at_ms,
                       packet_blobs.raw_packet AS raw_packet
                FROM lap_samples
                INNER JOIN packet_blobs
                  ON packet_blobs.session_id = lap_samples.session_id
                 AND packet_blobs.sequence = lap_samples.sequence
                 AND packet_blobs.received_at_ms = lap_samples.received_at_ms
                 AND packet_blobs.game_timestamp_ms = lap_samples.game_timestamp_ms
                WHERE lap_samples.id > ?
                ORDER BY lap_samples.id
                LIMIT ?
                """,
                (last_sample_id, batch_size),
            ).fetchall()
            if not rows:
                break

            updates: list[tuple[float | None, float | None, int]] = []
            for row in rows:
                sample_id = int(row["sample_id"])
                last_sample_id = sample_id
                try:
                    live_fields = packet_to_live_fields(
                        decode_packet(row["raw_packet"]),
                        sequence=int(row["sequence"]),
                        received_at_ms=int(row["received_at_ms"]),
                    )
                except Exception:
                    continue
                updates.append(
                    (
                        live_fields.get("smashable_vel_diff"),
                        live_fields.get("smashable_mass"),
                        sample_id,
                    )
                )

            if updates:
                con.executemany(update_sql, updates)

    def _apply_v11_race_control_sample_migrations(self, con: sqlite3.Connection) -> None:
        """Persist packet-level race-control uncertainty such as rewinds/resets."""

        for column_name, column_type in _RACE_CONTROL_SAMPLE_COLUMN_DEFINITIONS:
            _ensure_column(
                con,
                "lap_samples",
                column_name,
                f"{column_name} {column_type}",
            )

    def _schema_migration_applied(self, con: sqlite3.Connection, version: int) -> bool:
        return (
            con.execute(
                "SELECT 1 FROM schema_migrations WHERE version = ?",
                (version,),
            ).fetchone()
            is not None
        )

    def _apply_user_settings_migrations(self, con: sqlite3.Connection) -> None:
        """Ensure local user preference columns exist on legacy databases."""

        _ensure_column(
            con,
            "user_settings",
            "unit_system",
            "unit_system TEXT NOT NULL DEFAULT 'imperial'",
        )
        _ensure_column(con, "user_settings", "fh6_media_root", "fh6_media_root TEXT")
        _ensure_column(
            con,
            "user_settings",
            "world_map_enabled",
            "world_map_enabled INTEGER NOT NULL DEFAULT 0",
        )
        _ensure_column(
            con,
            "user_settings",
            "world_map_season",
            "world_map_season TEXT NOT NULL DEFAULT 'summer'",
        )

    def _apply_world_map_migrations(self, con: sqlite3.Connection) -> None:
        """Ensure local FH6 world-map cache metadata storage exists."""

        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS world_map_tile_sets (
                id TEXT PRIMARY KEY,
                game TEXT NOT NULL,
                map_name TEXT NOT NULL,
                season TEXT NOT NULL,
                source_zip_path TEXT NOT NULL,
                source_zip_mtime_ms INTEGER NOT NULL,
                source_zip_size_bytes INTEGER NOT NULL,
                cache_dir TEXT NOT NULL,
                tile_format TEXT NOT NULL,
                tile_size INTEGER NOT NULL,
                min_zoom INTEGER NOT NULL,
                max_zoom INTEGER NOT NULL,
                world_origin_x REAL NOT NULL,
                world_origin_z REAL NOT NULL,
                world_size REAL NOT NULL,
                status TEXT NOT NULL,
                manifest_json TEXT NOT NULL,
                error_message TEXT,
                last_built_at_ms INTEGER,
                updated_at_ms INTEGER NOT NULL,
                UNIQUE(game, map_name, season, source_zip_path)
            );
            CREATE INDEX IF NOT EXISTS idx_world_map_tile_sets_lookup
            ON world_map_tile_sets(game, map_name, season, status, updated_at_ms);
            """
        )

    def _apply_track_profile_migrations(self, con: sqlite3.Connection) -> None:
        """Ensure user-correctable track profile storage exists.

        This migration intentionally runs idempotently without increasing the
        historical schema version.  The task is additive and existing v1/v2/v3
        migration tests expect the migration ledger to remain compatible.
        """

        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS track_profiles (
                id TEXT PRIMARY KEY,
                owner_user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
                name TEXT NOT NULL,
                layout TEXT NOT NULL,
                source TEXT NOT NULL,
                confidence TEXT NOT NULL,
                shape_signature TEXT,
                created_at_ms INTEGER NOT NULL,
                updated_at_ms INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_track_profiles_shape_signature
            ON track_profiles(shape_signature);
            CREATE TABLE IF NOT EXISTS track_assets (
                id TEXT PRIMARY KEY,
                track_profile_id TEXT NOT NULL REFERENCES track_profiles(id) ON DELETE CASCADE,
                filename TEXT NOT NULL,
                stored_path TEXT NOT NULL,
                mime_type TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                transform_json TEXT NOT NULL,
                created_at_ms INTEGER NOT NULL,
                updated_at_ms INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_track_assets_profile
            ON track_assets(track_profile_id, created_at_ms);
            """
        )
        _ensure_column(
            con,
            "sessions",
            "track_profile_id",
            "track_profile_id TEXT REFERENCES track_profiles(id) ON DELETE SET NULL",
        )
        _ensure_column(
            con,
            "laps",
            "track_profile_id",
            "track_profile_id TEXT REFERENCES track_profiles(id) ON DELETE SET NULL",
        )
        self._repair_track_profile_foreign_keys(con)
        self._backfill_lap_track_profiles_from_legacy_sessions(con)
        con.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_sessions_user_started
            ON sessions(user_id, started_at_ms);
            CREATE INDEX IF NOT EXISTS idx_laps_user_started
            ON laps(user_id, started_at_ms);
            CREATE INDEX IF NOT EXISTS idx_sessions_track_profile
            ON sessions(track_profile_id);
            CREATE INDEX IF NOT EXISTS idx_laps_track_profile
            ON laps(track_profile_id);
            """
        )


    def _backfill_lap_track_profiles_from_legacy_sessions(
        self,
        con: sqlite3.Connection,
    ) -> None:
        session_columns = {
            row["name"] for row in con.execute("PRAGMA table_info(sessions)").fetchall()
        }
        lap_columns = {
            row["name"] for row in con.execute("PRAGMA table_info(laps)").fetchall()
        }
        if "track_profile_id" not in session_columns or "track_profile_id" not in lap_columns:
            return
        con.execute(
            """
            UPDATE laps
            SET track_profile_id = (
                SELECT sessions.track_profile_id
                FROM sessions
                WHERE sessions.id = laps.session_id
            )
            WHERE track_profile_id IS NULL
              AND EXISTS (
                  SELECT 1
                  FROM sessions
                  WHERE sessions.id = laps.session_id
                    AND sessions.track_profile_id IS NOT NULL
              )
            """
        )

    def _repair_track_profile_foreign_keys(self, con: sqlite3.Connection) -> None:
        """Rebuild older tables whose track_profile_id column lacks its FK."""

        tables_to_rebuild = [
            table_name
            for table_name in ("sessions", "laps")
            if not self._has_track_profile_foreign_key(con, table_name)
        ]
        if not tables_to_rebuild:
            return

        con.commit()
        previous_foreign_keys = int(con.execute("PRAGMA foreign_keys").fetchone()[0])
        previous_legacy_alter = int(
            con.execute("PRAGMA legacy_alter_table").fetchone()[0]
        )
        con.execute("PRAGMA foreign_keys=OFF")
        con.execute("PRAGMA legacy_alter_table=ON")
        con.execute("BEGIN")
        try:
            for table_name in tables_to_rebuild:
                self._rebuild_track_profile_reference_table(con, table_name)
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.execute(f"PRAGMA legacy_alter_table={previous_legacy_alter}")
            con.execute(f"PRAGMA foreign_keys={previous_foreign_keys}")

    def _has_track_profile_foreign_key(
        self,
        con: sqlite3.Connection,
        table_name: str,
    ) -> bool:
        return any(
            row["from"] == "track_profile_id"
            and row["table"] == "track_profiles"
            and row["to"] == "id"
            for row in con.execute(f"PRAGMA foreign_key_list({table_name})").fetchall()
        )

    def _rebuild_track_profile_reference_table(
        self,
        con: sqlite3.Connection,
        table_name: str,
    ) -> None:
        table_sql = self._table_create_sql(con, table_name)
        replacement_sql = self._table_sql_with_track_profile_fk(table_sql)
        dependent_sql = self._table_dependent_sql(con, table_name)
        column_names = [
            row["name"]
            for row in con.execute(f"PRAGMA table_info({self._quote_identifier(table_name)})").fetchall()
        ]
        if "track_profile_id" not in column_names:
            raise ValueError(
                f"cannot repair track_profile_id FK because {table_name} lacks the column"
            )

        old_table_name = f"__{table_name}_old_track_profile_fk_{uuid.uuid4().hex}"
        quoted_table = self._quote_identifier(table_name)
        quoted_old_table = self._quote_identifier(old_table_name)
        quoted_columns = ", ".join(self._quote_identifier(column) for column in column_names)
        select_expressions = ", ".join(
            self._track_profile_copy_expression(column, old_table_name)
            for column in column_names
        )

        con.execute(f"ALTER TABLE {quoted_table} RENAME TO {quoted_old_table}")
        con.execute(replacement_sql)
        con.execute(
            f"""
            INSERT INTO {quoted_table}({quoted_columns})
            SELECT {select_expressions}
            FROM {quoted_old_table}
            """
        )
        con.execute(f"DROP TABLE {quoted_old_table}")
        for sql in dependent_sql:
            self._execute_schema_statement(con, sql)

    def _execute_schema_statement(self, con: sqlite3.Connection, sql: str) -> None:
        con.execute(sql)

    def _table_create_sql(self, con: sqlite3.Connection, table_name: str) -> str:
        row = con.execute(
            """
            SELECT sql
            FROM sqlite_master
            WHERE type = 'table' AND name = ?
            """,
            (table_name,),
        ).fetchone()
        if row is None or row["sql"] is None:
            raise ValueError(f"cannot find CREATE TABLE SQL for {table_name}")
        return str(row["sql"])

    def _table_dependent_sql(
        self,
        con: sqlite3.Connection,
        table_name: str,
    ) -> list[str]:
        rows = con.execute(
            """
            SELECT type, name, sql
            FROM sqlite_master
            WHERE tbl_name = ?
              AND type IN ('index', 'trigger')
              AND sql IS NOT NULL
            ORDER BY CASE type WHEN 'index' THEN 0 ELSE 1 END, name
            """,
            (table_name,),
        ).fetchall()
        return [str(row["sql"]) for row in rows]

    def _table_sql_with_track_profile_fk(self, create_sql: str) -> str:
        open_index = create_sql.find("(")
        if open_index < 0:
            raise ValueError("cannot repair track_profile_id FK in malformed CREATE TABLE SQL")

        close_index = self._matching_close_paren_index(create_sql, open_index)
        body = create_sql[open_index + 1 : close_index]
        definitions = self._split_sql_definitions(body)
        replaced = False
        repaired_definitions = []
        for definition in definitions:
            if self._definition_column_name(definition) == "track_profile_id":
                column_token = definition.lstrip().split(None, 1)[0]
                repaired_definitions.append(
                    f"{column_token} TEXT REFERENCES track_profiles(id) ON DELETE SET NULL"
                )
                replaced = True
            else:
                repaired_definitions.append(definition)

        if not replaced:
            raise ValueError("cannot repair missing track_profile_id column definition")

        repaired_body = ",".join(repaired_definitions)
        return f"{create_sql[: open_index + 1]}{repaired_body}{create_sql[close_index:]}"

    def _matching_close_paren_index(self, sql: str, open_index: int) -> int:
        depth = 0
        quote: str | None = None
        bracket_quote = False
        index = open_index
        while index < len(sql):
            char = sql[index]
            if quote is not None:
                if bracket_quote and char == "]":
                    quote = None
                    bracket_quote = False
                elif char == quote:
                    if index + 1 < len(sql) and sql[index + 1] == quote:
                        index += 1
                    else:
                        quote = None
                index += 1
                continue

            if char in {"'", '"', "`"}:
                quote = char
            elif char == "[":
                quote = "]"
                bracket_quote = True
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    return index
            index += 1

        raise ValueError("cannot repair track_profile_id FK in malformed CREATE TABLE SQL")

    def _split_sql_definitions(self, sql_body: str) -> list[str]:
        definitions: list[str] = []
        start = 0
        depth = 0
        quote: str | None = None
        bracket_quote = False
        index = 0
        while index < len(sql_body):
            char = sql_body[index]
            if quote is not None:
                if bracket_quote and char == "]":
                    quote = None
                    bracket_quote = False
                elif char == quote:
                    if index + 1 < len(sql_body) and sql_body[index + 1] == quote:
                        index += 1
                    else:
                        quote = None
                index += 1
                continue

            if char in {"'", '"', "`"}:
                quote = char
            elif char == "[":
                quote = "]"
                bracket_quote = True
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            elif char == "," and depth == 0:
                definitions.append(sql_body[start:index])
                start = index + 1
            index += 1

        definitions.append(sql_body[start:])
        return definitions

    def _definition_column_name(self, definition: str) -> str | None:
        stripped = definition.strip()
        if not stripped:
            return None
        first_token = stripped.split(None, 1)[0]
        normalized_token = first_token.strip('"`[]')
        if normalized_token.upper() in {
            "CONSTRAINT",
            "PRIMARY",
            "FOREIGN",
            "UNIQUE",
            "CHECK",
            "EXCLUDE",
        }:
            return None
        return normalized_token

    def _track_profile_copy_expression(
        self,
        column_name: str,
        old_table_name: str,
    ) -> str:
        quoted_column = self._quote_identifier(column_name)
        old_column = f"{self._quote_identifier(old_table_name)}.{quoted_column}"
        if column_name != "track_profile_id":
            return old_column
        return (
            "CASE "
            f"WHEN {old_column} IN (SELECT id FROM track_profiles) "
            f"THEN {old_column} "
            "ELSE NULL END"
        )

    def _ensure_reference_context_indexes(self, con: sqlite3.Connection) -> None:
        """Ensure comparison context lookup indexes without bumping schema."""

        for scope, json_path in _REFERENCE_CONTEXT_JSON_PATHS.items():
            con.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_lap_summaries_context_{scope}
                ON lap_summaries(
                    CASE
                        WHEN json_valid(summary_json)
                        THEN json_extract(summary_json, '{json_path}')
                    END
                )
                """
            )

    def _apply_car_catalog_migrations(self, con: sqlite3.Connection) -> None:
        """Ensure best-effort car catalog lookup storage exists."""

        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS cars (
                ordinal INTEGER PRIMARY KEY,
                display_name TEXT,
                model_short TEXT,
                make TEXT,
                model TEXT,
                year INTEGER,
                base_class_label TEXT,
                base_pi INTEGER,
                car_type TEXT,
                country TEXT,
                value_cr INTEGER,
                rarity TEXT,
                source TEXT,
                source_info TEXT,
                asset_name TEXT,
                asset_zip TEXT,
                catalog_source TEXT NOT NULL DEFAULT 'unknown',
                updated_at_ms INTEGER NOT NULL
            );
            """
        )

    def _apply_track_catalog_migrations(self, con: sqlite3.Connection) -> None:
        """Ensure canonical game track lookup storage exists."""

        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS game_tracks (
                track_key TEXT PRIMARY KEY,
                source_dataset_key INTEGER,
                route_id INTEGER,
                custom_route_id INTEGER,
                media_track_id INTEGER,
                media_track_name TEXT,
                ribbon_config TEXT,
                display_name TEXT,
                short_display_name TEXT,
                short_display_name_all_caps TEXT,
                description TEXT,
                display_name_key TEXT,
                short_display_name_key TEXT,
                short_display_name_all_caps_key TEXT,
                description_key TEXT,
                route_activation_trigger_zone_name TEXT,
                use_cross_country_ai INTEGER,
                stray_warning_distance REAL,
                stray_teleport_distance REAL,
                source_file TEXT,
                catalog_source TEXT NOT NULL DEFAULT 'unknown',
                updated_at_ms INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_game_tracks_route_id
            ON game_tracks(route_id);
            CREATE INDEX IF NOT EXISTS idx_game_tracks_custom_route_id
            ON game_tracks(custom_route_id);
            CREATE INDEX IF NOT EXISTS idx_game_tracks_media_track
            ON game_tracks(media_track_name, ribbon_config);
            CREATE TABLE IF NOT EXISTS game_map_regions (
                region_key TEXT PRIMARY KEY,
                english_name TEXT,
                english_short_name TEXT,
                japanese_name TEXT,
                japanese_short_name TEXT,
                name_key TEXT,
                short_name_key TEXT,
                locator_collection_name TEXT,
                top_image_path TEXT,
                map_tile_mascot_image TEXT,
                map_hover_fmod_event TEXT,
                first_time_enter_fmod_event TEXT,
                rich_presence_event TEXT,
                full_reveal_percentage INTEGER,
                announcement_ie_state TEXT,
                source_file TEXT,
                catalog_source TEXT NOT NULL DEFAULT 'unknown',
                updated_at_ms INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_game_map_regions_locator_collection
            ON game_map_regions(locator_collection_name);
            CREATE TABLE IF NOT EXISTS game_track_locators (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_file TEXT NOT NULL,
                media_track_name TEXT,
                locator_collection TEXT NOT NULL,
                locator_name TEXT NOT NULL,
                locator_kind TEXT NOT NULL,
                route_id INTEGER,
                x REAL NOT NULL,
                y REAL NOT NULL,
                z REAL NOT NULL,
                heading_yaw_rad REAL,
                transform_json TEXT NOT NULL,
                catalog_source TEXT NOT NULL DEFAULT 'unknown',
                updated_at_ms INTEGER NOT NULL,
                UNIQUE(source_file, locator_name)
            );
            CREATE INDEX IF NOT EXISTS idx_game_track_locators_route
            ON game_track_locators(route_id, locator_kind);
            CREATE INDEX IF NOT EXISTS idx_game_track_locators_collection
            ON game_track_locators(locator_collection);
            CREATE INDEX IF NOT EXISTS idx_game_track_locators_position
            ON game_track_locators(x, z);
            """
        )

    def _apply_track_match_migrations(self, con: sqlite3.Connection) -> None:
        """Ensure confidence-scored track-match storage exists."""

        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS game_track_profile_links (
                track_key TEXT PRIMARY KEY REFERENCES game_tracks(track_key) ON DELETE CASCADE,
                track_profile_id TEXT NOT NULL UNIQUE REFERENCES track_profiles(id) ON DELETE CASCADE,
                created_at_ms INTEGER NOT NULL,
                updated_at_ms INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS track_match_candidates (
                lap_id TEXT NOT NULL REFERENCES laps(id) ON DELETE CASCADE,
                session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                matcher_version TEXT NOT NULL,
                candidate_rank INTEGER NOT NULL,
                candidate_kind TEXT NOT NULL,
                track_key TEXT REFERENCES game_tracks(track_key) ON DELETE SET NULL,
                track_profile_id TEXT REFERENCES track_profiles(id) ON DELETE SET NULL,
                route_id INTEGER,
                display_name TEXT,
                confidence REAL NOT NULL,
                score_components_json TEXT NOT NULL,
                reasons_json TEXT NOT NULL,
                is_auto_assignable INTEGER NOT NULL DEFAULT 0,
                assigned_track_profile_id TEXT REFERENCES track_profiles(id) ON DELETE SET NULL,
                created_at_ms INTEGER NOT NULL,
                PRIMARY KEY(lap_id, matcher_version, candidate_rank)
            );
            CREATE INDEX IF NOT EXISTS idx_track_match_candidates_lap
            ON track_match_candidates(lap_id, matcher_version, candidate_rank);
            CREATE INDEX IF NOT EXISTS idx_track_match_candidates_track
            ON track_match_candidates(track_key, confidence);
            """
        )

    def _apply_v11_lifetime_stats_migrations(self, con: sqlite3.Connection) -> None:
        """Create and backfill deletion-stable lifetime stat snapshots."""

        should_backfill = not self._schema_migration_applied(con, 11)
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS lifetime_stat_laps (
                lap_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                recorded_at_ms INTEGER NOT NULL,
                lap_started_at_ms INTEGER,
                lap_ended_at_ms INTEGER,
                lap_time_ms INTEGER,
                max_speed_mps REAL,
                car_ordinal INTEGER,
                car_key TEXT,
                car_name TEXT,
                car_class_label TEXT,
                drivetrain_label TEXT,
                track_profile_id TEXT,
                track_name TEXT,
                track_layout TEXT,
                created_at_ms INTEGER NOT NULL,
                updated_at_ms INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_lifetime_stat_laps_user_recorded
            ON lifetime_stat_laps(user_id, recorded_at_ms);
            CREATE INDEX IF NOT EXISTS idx_lifetime_stat_laps_user_car
            ON lifetime_stat_laps(user_id, car_key);
            CREATE INDEX IF NOT EXISTS idx_lifetime_stat_laps_user_track
            ON lifetime_stat_laps(user_id, track_profile_id);
            CREATE INDEX IF NOT EXISTS idx_lifetime_stat_laps_user_class
            ON lifetime_stat_laps(user_id, car_class_label);
            CREATE INDEX IF NOT EXISTS idx_lifetime_stat_laps_user_drive
            ON lifetime_stat_laps(user_id, drivetrain_label);
            """
        )
        if should_backfill:
            self._backfill_lifetime_stat_laps(con)

    def _apply_feedback_migrations(self, con: sqlite3.Connection) -> None:
        """Create local feedback identity and retry outbox tables."""

        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS feedback_state (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL,
              updated_at_ms INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS feedback_outbox (
              report_ref TEXT PRIMARY KEY,
              payload_json TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'pending',
              attempt_count INTEGER NOT NULL DEFAULT 0,
              last_error TEXT,
              created_at_ms INTEGER NOT NULL,
              updated_at_ms INTEGER NOT NULL,
              next_attempt_at_ms INTEGER NOT NULL,
              issue_number INTEGER,
              issue_url TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_feedback_outbox_pending
            ON feedback_outbox(status, next_attempt_at_ms);

            CREATE INDEX IF NOT EXISTS idx_feedback_outbox_updated
            ON feedback_outbox(updated_at_ms);
            """
        )

    def _backfill_lifetime_stat_laps(self, con: sqlite3.Connection) -> None:
        """Backfill lifetime stats from existing completed local laps.

        Existing databases do not carry a reliable origin marker for historical
        replay/import sessions, so this migration snapshots all completed laps.
        Do not expose this implementation caveat in the Stats UI.
        """

        now_ms = _now_ms()
        lap_time_ms_sql = _lap_time_ms_sql("laps", "lap_summaries")
        completed_lap_predicate = _completed_lap_time_candidate_sql("laps")
        rows = con.execute(
            f"""
            WITH lap_speed AS (
                SELECT lap_id, MAX(speed_mps) AS max_speed_mps
                FROM lap_samples
                WHERE lap_id IS NOT NULL
                GROUP BY lap_id
            )
            SELECT laps.id AS lap_id,
                   laps.user_id,
                   laps.session_id,
                   COALESCE(laps.ended_at_ms, sessions.last_active_at_ms, sessions.ended_at_ms, laps.started_at_ms) AS recorded_at_ms,
                   laps.started_at_ms AS lap_started_at_ms,
                   laps.ended_at_ms AS lap_ended_at_ms,
                   {lap_time_ms_sql} AS lap_time_ms,
                   lap_speed.max_speed_mps,
                   sessions.car_ordinal,
                   sessions.car_name,
                   sessions.car_class_label,
                   sessions.drivetrain_label,
                   laps.track_profile_id,
                   track_profiles.name AS track_name,
                   track_profiles.layout AS track_layout
            FROM laps
            JOIN sessions ON sessions.id = laps.session_id
            LEFT JOIN lap_summaries ON lap_summaries.lap_id = laps.id
            LEFT JOIN lap_speed ON lap_speed.lap_id = laps.id
            LEFT JOIN track_profiles ON track_profiles.id = laps.track_profile_id
            WHERE laps.user_id = ?
              AND sessions.user_id = ?
              AND lower(trim(coalesce(laps.status, ''))) NOT IN ('active', 'recording')
              AND {completed_lap_predicate}
            """,
            (LOCAL_USER_ID, LOCAL_USER_ID),
        ).fetchall()
        for row in rows:
            car_key = _car_key_from_values(row["car_ordinal"], row["car_name"])
            con.execute(
                """
                INSERT OR IGNORE INTO lifetime_stat_laps(
                    lap_id, user_id, session_id, recorded_at_ms,
                    lap_started_at_ms, lap_ended_at_ms, lap_time_ms, max_speed_mps,
                    car_ordinal, car_key, car_name, car_class_label, drivetrain_label,
                    track_profile_id, track_name, track_layout, created_at_ms, updated_at_ms
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["lap_id"],
                    row["user_id"],
                    row["session_id"],
                    int(row["recorded_at_ms"] or now_ms),
                    row["lap_started_at_ms"],
                    row["lap_ended_at_ms"],
                    row["lap_time_ms"],
                    row["max_speed_mps"],
                    row["car_ordinal"],
                    car_key,
                    row["car_name"],
                    row["car_class_label"],
                    row["drivetrain_label"],
                    row["track_profile_id"],
                    row["track_name"],
                    row["track_layout"],
                    now_ms,
                    now_ms,
                ),
            )

    def _session_select_sql(self, where_clause: str = "") -> str:
        where_sql = f"WHERE {where_clause}" if where_clause else ""
        lap_time_ms_sql = _lap_time_ms_sql("laps", "lap_summaries")
        return f"""
            WITH candidate_sessions AS (
                SELECT sessions.id
                FROM sessions
                {where_sql}
            ),
            lap_metrics AS (
                SELECT laps.id, laps.session_id,
                       {lap_time_ms_sql} AS lap_time_ms
                FROM laps
                JOIN candidate_sessions ON candidate_sessions.id = laps.session_id
                LEFT JOIN lap_summaries ON lap_summaries.lap_id = laps.id
            ),
            session_lap_aggregates AS (
                SELECT session_id,
                       COUNT(*) AS lap_count,
                       SUM(CASE WHEN lap_time_ms IS NOT NULL THEN 1 ELSE 0 END) AS completed_lap_count,
                       MIN(lap_time_ms) AS best_lap_time_ms,
                       AVG(lap_time_ms) AS average_lap_time_ms,
                       SUM(lap_time_ms) AS total_lap_time_ms
                FROM lap_metrics
                GROUP BY session_id
            )
            SELECT sessions.id, sessions.user_id, sessions.label, sessions.status,
                   sessions.started_at_ms, sessions.ended_at_ms,
                   sessions.ended_reason,
                   sessions.car_identity_key,
                   sessions.car_ordinal,
                   sessions.car_name,
                   sessions.car_class_id,
                   sessions.car_class_label,
                   sessions.car_performance_index,
                   sessions.drivetrain_id,
                   sessions.drivetrain_label,
                   sessions.label_generated,
                   sessions.auto_created_reason,
                   COALESCE(
                       sessions.last_active_at_ms,
                       sessions.ended_at_ms,
                       sessions.started_at_ms
                   ) AS last_active_at_ms,
                   COALESCE(session_lap_aggregates.lap_count, 0) AS lap_count,
                   COALESCE(session_lap_aggregates.completed_lap_count, 0) AS completed_lap_count,
                   session_lap_aggregates.best_lap_time_ms,
                   session_lap_aggregates.average_lap_time_ms,
                   session_lap_aggregates.total_lap_time_ms
            FROM sessions
            JOIN candidate_sessions ON candidate_sessions.id = sessions.id
            LEFT JOIN session_lap_aggregates ON session_lap_aggregates.session_id = sessions.id
        """

    def _next_session_label(self, con: sqlite3.Connection) -> str:
        con.execute(
            """
            INSERT OR IGNORE INTO session_counters(user_id, next_session_number)
            VALUES (?, ?)
            """,
            (LOCAL_USER_ID, 1),
        )
        row = con.execute(
            """
            SELECT next_session_number
            FROM session_counters
            WHERE user_id = ?
            """,
            (LOCAL_USER_ID,),
        ).fetchone()
        next_number = int(row["next_session_number"])
        con.execute(
            """
            UPDATE session_counters
            SET next_session_number = ?
            WHERE user_id = ?
            """,
            (next_number + 1, LOCAL_USER_ID),
        )
        return f"Session {next_number}"


    def _session_car_identity_values(self, car_identity: dict | None) -> dict:
        car_identity = car_identity or {}

        def text_value(key: str) -> str | None:
            value = car_identity.get(key)
            if value is None:
                return None
            text = str(value).strip()
            return text or None

        return {
            "car_identity_key": text_value("car_identity_key"),
            "car_ordinal": _optional_int_value(car_identity.get("car_ordinal")),
            "car_name": text_value("car_name"),
            "car_class_id": _optional_int_value(car_identity.get("car_class_id")),
            "car_class_label": text_value("car_class_label"),
            "car_performance_index": _optional_int_value(
                car_identity.get("car_performance_index")
            ),
            "drivetrain_id": _optional_int_value(car_identity.get("drivetrain_id")),
            "drivetrain_label": text_value("drivetrain_label"),
        }

    def _unique_session_label(
        self,
        con: sqlite3.Connection,
        base_label: str,
        *,
        exclude_session_id: str | None = None,
    ) -> str:
        candidate = base_label
        suffix = 2
        while True:
            row = con.execute(
                """
                SELECT 1
                FROM sessions
                WHERE user_id = ?
                  AND label = ?
                  AND (? IS NULL OR id != ?)
                LIMIT 1
                """,
                (LOCAL_USER_ID, candidate, exclude_session_id, exclude_session_id),
            ).fetchone()
            if row is None:
                return candidate
            candidate = f"{base_label} {suffix}"
            suffix += 1

    def _session_label_from_car_identity(
        self,
        con: sqlite3.Connection,
        car_identity: dict,
        *,
        exclude_session_id: str | None = None,
    ) -> str:
        car_name = str(car_identity.get("car_name") or "Unknown car").strip()
        if not car_name:
            car_name = "Unknown car"
        parts: list[str] = [car_name]
        class_label = car_identity.get("car_class_label")
        if class_label:
            parts.append(str(class_label))
        performance_index = car_identity.get("car_performance_index")
        if performance_index is not None:
            parts.append(str(performance_index))
        drivetrain = car_identity.get("drivetrain_label")
        if drivetrain:
            parts.append(str(drivetrain))
        parts.append("Session")
        return self._unique_session_label(
            con,
            " ".join(parts),
            exclude_session_id=exclude_session_id,
        )

    def session(self, session_id: str) -> dict | None:
        with self.connect() as con:
            row = con.execute(
                self._session_select_sql("sessions.id = ?"),
                (session_id,),
            ).fetchone()
        return None if row is None else dict(row)

    def active_session(self) -> dict | None:
        with self.connect() as con:
            row = con.execute(
                self._session_select_sql(
                    "sessions.user_id = ? AND sessions.status = 'active'"
                ),
                (LOCAL_USER_ID,),
            ).fetchone()
        return None if row is None else dict(row)

    def create_session(self, label: str, status: str = "recording") -> str:
        session_id = str(uuid.uuid4())
        now_ms = _now_ms()
        clean_label = self._required_text(label, "label")
        with self.connect() as con:
            con.execute(
                """
                INSERT INTO sessions(
                    id, user_id, label, status, started_at_ms, last_active_at_ms
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (session_id, LOCAL_USER_ID, clean_label, status, now_ms, now_ms),
            )
        return session_id

    def start_session(
        self,
        label: str | None = None,
        *,
        car_identity: dict | None = None,
        auto_created_reason: str | None = None,
    ) -> str:
        session_id = str(uuid.uuid4())
        now_ms = _now_ms()
        clean_auto_created_reason = (
            str(auto_created_reason).strip() if auto_created_reason is not None else None
        )
        if clean_auto_created_reason == "":
            clean_auto_created_reason = None
        with self.connect() as con:
            identity_values = self._session_car_identity_values(car_identity)
            if label is not None:
                clean_label = self._required_text(label, "label")
                label_generated = 0
            elif car_identity is not None:
                clean_label = self._session_label_from_car_identity(con, identity_values)
                label_generated = 1
            else:
                clean_label = self._next_session_label(con)
                label_generated = 1
            con.execute(
                """
                UPDATE sessions
                SET status = ?, ended_at_ms = COALESCE(ended_at_ms, ?),
                    ended_reason = ?, last_active_at_ms = ?
                WHERE user_id = ? AND status = 'active'
                """,
                ("user_end", now_ms, "new_session_started", now_ms, LOCAL_USER_ID),
            )
            con.execute(
                """
                INSERT INTO sessions(
                    id, user_id, label, status, started_at_ms, last_active_at_ms,
                    car_identity_key, car_ordinal, car_name, car_class_id,
                    car_class_label, car_performance_index, drivetrain_id,
                    drivetrain_label, label_generated, auto_created_reason
                )
                VALUES (?, ?, ?, 'active', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    LOCAL_USER_ID,
                    clean_label,
                    now_ms,
                    now_ms,
                    identity_values["car_identity_key"],
                    identity_values["car_ordinal"],
                    identity_values["car_name"],
                    identity_values["car_class_id"],
                    identity_values["car_class_label"],
                    identity_values["car_performance_index"],
                    identity_values["drivetrain_id"],
                    identity_values["drivetrain_label"],
                    label_generated,
                    clean_auto_created_reason,
                ),
            )
        return session_id

    def attach_session_car_identity(self, session_id: str, car_identity: dict) -> dict:
        identity_values = self._session_car_identity_values(car_identity)
        now_ms = _now_ms()
        with self.connect() as con:
            row = con.execute(
                """
                SELECT id, label, label_generated
                FROM sessions
                WHERE id = ? AND user_id = ?
                """,
                (session_id, LOCAL_USER_ID),
            ).fetchone()
            if row is None:
                raise ValueError(f"unknown session_id: {session_id}")
            label_generated = int(row["label_generated"] or 0)
            label = str(row["label"])
            if label_generated:
                label = self._session_label_from_car_identity(
                    con,
                    identity_values,
                    exclude_session_id=session_id,
                )
            con.execute(
                """
                UPDATE sessions
                SET car_identity_key = ?, car_ordinal = ?, car_name = ?,
                    car_class_id = ?, car_class_label = ?, car_performance_index = ?,
                    drivetrain_id = ?, drivetrain_label = ?, label = ?,
                    label_generated = ?, last_active_at_ms = ?
                WHERE id = ? AND user_id = ?
                """,
                (
                    identity_values["car_identity_key"],
                    identity_values["car_ordinal"],
                    identity_values["car_name"],
                    identity_values["car_class_id"],
                    identity_values["car_class_label"],
                    identity_values["car_performance_index"],
                    identity_values["drivetrain_id"],
                    identity_values["drivetrain_label"],
                    label,
                    label_generated,
                    now_ms,
                    session_id,
                    LOCAL_USER_ID,
                ),
            )
        session = self.session(session_id)
        if session is None:
            raise ValueError(f"unknown session_id: {session_id}")
        return session

    def end_session(self, session_id: str, reason: str = "user_end") -> dict:
        now_ms = _now_ms()
        with self.connect() as con:
            row = con.execute(
                """
                SELECT status
                FROM sessions
                WHERE id = ? AND user_id = ?
                """,
                (session_id, LOCAL_USER_ID),
            ).fetchone()
            if row is None:
                raise ValueError(f"unknown session_id: {session_id}")
            if row["status"] == "active":
                con.execute(
                    """
                    UPDATE sessions
                    SET status = ?, ended_at_ms = ?, ended_reason = ?,
                        last_active_at_ms = ?
                    WHERE id = ?
                    """,
                    (reason, now_ms, reason, now_ms, session_id),
                )
        session = self.session(session_id)
        if session is None:
            raise ValueError(f"unknown session_id: {session_id}")
        return session

    def activate_session(
        self,
        session_id: str,
        reason: str = "session_activated",
    ) -> dict:
        now_ms = _now_ms()
        clean_reason = self._required_text(reason, "reason")
        with self.connect() as con:
            row = con.execute(
                """
                SELECT id
                FROM sessions
                WHERE id = ? AND user_id = ?
                """,
                (session_id, LOCAL_USER_ID),
            ).fetchone()
            if row is None:
                raise ValueError(f"unknown session_id: {session_id}")
            con.execute(
                """
                UPDATE sessions
                SET status = ?, ended_at_ms = COALESCE(ended_at_ms, ?),
                    ended_reason = ?, last_active_at_ms = ?
                WHERE user_id = ? AND status = 'active' AND id != ?
                """,
                (
                    clean_reason,
                    now_ms,
                    clean_reason,
                    now_ms,
                    LOCAL_USER_ID,
                    session_id,
                ),
            )
            con.execute(
                """
                UPDATE sessions
                SET status = 'active', ended_at_ms = NULL, ended_reason = NULL,
                    last_active_at_ms = ?
                WHERE id = ? AND user_id = ?
                """,
                (now_ms, session_id, LOCAL_USER_ID),
            )
        session = self.session(session_id)
        if session is None:
            raise ValueError(f"unknown session_id: {session_id}")
        return session

    def rename_session(self, session_id: str, label: str) -> dict:
        clean_label = str(label or "").strip()
        if not clean_label:
            raise ValueError("label must not be empty")
        now_ms = _now_ms()
        with self.connect() as con:
            cursor = con.execute(
                """
                UPDATE sessions
                SET label = ?, label_generated = 0, last_active_at_ms = ?
                WHERE id = ? AND user_id = ?
                """,
                (clean_label, now_ms, session_id, LOCAL_USER_ID),
            )
            if cursor.rowcount != 1:
                raise ValueError(f"unknown session_id: {session_id}")
        session = self.session(session_id)
        if session is None:
            raise ValueError(f"unknown session_id: {session_id}")
        return session

    def delete_session(self, session_id: str) -> dict:
        with self.connect() as con:
            row = con.execute(
                self._session_select_sql("sessions.id = ?"),
                (session_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"unknown session_id: {session_id}")
            deleted = dict(row)
            con.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        return deleted

    def delete_all_recorded_telemetry(self) -> dict[str, int]:
        """Delete all durable telemetry rows while preserving app metadata.

        Track profiles, assets, catalog rows, map cache metadata, users, and
        settings are intentionally preserved.  The deleted tables below are
        session-owned telemetry, derived recorded lap statistics, or counters
        that only exist to label future telemetry sessions.
        """

        telemetry_tables = (
            "comparison_refs",
            "lap_summaries",
            "track_match_candidates",
            "issue_markers",
            "lap_samples",
            "packet_blobs",
            "lifetime_stat_laps",
            "session_counters",
            "laps",
            "sessions",
        )
        with self.connect() as con:
            deleted_counts = {
                table_name: int(
                    con.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
                )
                for table_name in telemetry_tables
            }
            for table_name in telemetry_tables:
                con.execute(f"DELETE FROM {table_name}")
        return deleted_counts

    def delete_empty_auto_created_session(
        self,
        session_id: str,
        *,
        auto_created_reason: str,
    ) -> dict | None:
        with self.connect() as con:
            row = con.execute(
                self._session_select_sql("sessions.id = ?"),
                (session_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"unknown session_id: {session_id}")
            session = dict(row)
            if session.get("auto_created_reason") != auto_created_reason:
                return None

            finalized_lap_count = int(
                con.execute(
                    """
                    SELECT COUNT(*)
                    FROM laps
                    WHERE session_id = ?
                      AND ended_at_ms IS NOT NULL
                      AND status != 'recording'
                    """,
                    (session_id,),
                ).fetchone()[0]
            )
            if finalized_lap_count > 0:
                return None

            con.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            return session

    def create_lap(
        self,
        session_id: str,
        lap_number: int | None,
        boundary_confidence: str,
    ) -> str:
        lap_id = str(uuid.uuid4())
        now_ms = _now_ms()
        with self.connect() as con:
            cursor = con.execute(
                """
                INSERT INTO laps(
                    id, user_id, session_id, lap_number, status,
                    started_at_ms, boundary_confidence
                )
                SELECT ?, user_id, id, ?, ?, ?, ?
                FROM sessions
                WHERE id = ?
                """,
                (
                    lap_id,
                    lap_number,
                    "recording",
                    now_ms,
                    boundary_confidence,
                    session_id,
                ),
            )
            if cursor.rowcount != 1:
                raise ValueError(f"unknown session_id: {session_id}")
            con.execute(
                """
                UPDATE sessions
                SET last_active_at_ms = ?
                WHERE id = ?
                """,
                (now_ms, session_id),
            )
        return lap_id

    def finalize_lap(
        self,
        lap_id: str,
        reason: str,
        boundary_confidence: str | None = None,
    ) -> None:
        now_ms = _now_ms()
        with self.connect() as con:
            set_clause = "ended_at_ms = ?, status = ?, ended_reason = ?"
            params: list[object] = [now_ms, reason, reason]
            if boundary_confidence is not None:
                set_clause += ", boundary_confidence = ?"
                params.append(boundary_confidence)
            params.append(lap_id)
            cursor = con.execute(
                f"""
                UPDATE laps
                SET {set_clause}
                WHERE id = ?
                """,
                params,
            )
            if cursor.rowcount != 1:
                raise ValueError(f"unknown lap_id: {lap_id}")
            con.execute(
                """
                UPDATE sessions
                SET last_active_at_ms = ?
                WHERE id = (
                    SELECT session_id
                    FROM laps
                    WHERE id = ?
                )
                """,
                (now_ms, lap_id),
            )

    def finalize_session(self, session_id: str, reason: str) -> None:
        now_ms = _now_ms()
        with self.connect() as con:
            cursor = con.execute(
                """
                UPDATE sessions
                SET ended_at_ms = ?, status = ?, ended_reason = ?,
                    last_active_at_ms = ?
                WHERE id = ?
                """,
                (now_ms, reason, reason, now_ms, session_id),
            )
            if cursor.rowcount != 1:
                raise ValueError(f"unknown session_id: {session_id}")

    def create_track_profile(
        self,
        name: str,
        layout: str,
        source: str,
        confidence: str,
        shape_signature: str | None = None,
    ) -> str:
        profile_id = str(uuid.uuid4())
        now_ms = _now_ms()
        name = self._required_text(name, "name")
        layout = self._required_text(layout, "layout")
        source = self._required_text(source, "source")
        confidence = self._required_text(confidence, "confidence")
        with self.connect() as con:
            con.execute(
                """
                INSERT INTO track_profiles(
                    id, owner_user_id, name, layout, source, confidence,
                    shape_signature, created_at_ms, updated_at_ms
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    profile_id,
                    LOCAL_USER_ID,
                    name,
                    layout,
                    source,
                    confidence,
                    shape_signature,
                    now_ms,
                    now_ms,
                ),
            )
        return profile_id

    def update_track_profile(self, profile_id: str, name: str, layout: str) -> None:
        now_ms = _now_ms()
        name = self._required_text(name, "name")
        layout = self._required_text(layout, "layout")
        with self.connect() as con:
            cursor = con.execute(
                """
                UPDATE track_profiles
                SET name = ?, layout = ?, updated_at_ms = ?
                WHERE id = ?
                """,
                (name, layout, now_ms, profile_id),
            )
            if cursor.rowcount != 1:
                raise ValueError(f"unknown track_profile_id: {profile_id}")
            con.execute(
                """
                UPDATE lifetime_stat_laps
                SET track_name = ?, track_layout = ?, updated_at_ms = ?
                WHERE track_profile_id = ?
                """,
                (name, layout, now_ms, profile_id),
            )

    def merge_track_profiles(
        self,
        keep_profile_id: str,
        merge_profile_id: str,
    ) -> None:
        if keep_profile_id == merge_profile_id:
            raise ValueError("cannot merge a track profile into itself")

        now_ms = _now_ms()
        with self.connect() as con:
            keep_profile = con.execute(
                """
                SELECT id, name, layout
                FROM track_profiles
                WHERE id = ?
                """,
                (keep_profile_id,),
            ).fetchone()
            if keep_profile is None:
                raise ValueError(f"unknown track_profile_id: {keep_profile_id}")
            self._require_track_profile(con, merge_profile_id)
            for table_name in self._track_profile_reference_tables(con):
                quoted_table = self._quote_identifier(table_name)
                con.execute(
                    f"""
                    UPDATE {quoted_table}
                    SET track_profile_id = ?
                    WHERE track_profile_id = ?
                    """,
                    (keep_profile_id, merge_profile_id),
                )
            con.execute(
                "UPDATE track_profiles SET updated_at_ms = ? WHERE id = ?",
                (now_ms, keep_profile_id),
            )
            con.execute(
                """
                UPDATE lifetime_stat_laps
                SET track_profile_id = ?, track_name = ?, track_layout = ?, updated_at_ms = ?
                WHERE track_profile_id IN (?, ?)
                """,
                (
                    keep_profile_id,
                    keep_profile["name"],
                    keep_profile["layout"],
                    now_ms,
                    keep_profile_id,
                    merge_profile_id,
                ),
            )
            con.execute("DELETE FROM track_profiles WHERE id = ?", (merge_profile_id,))

    def assign_track_profile(
        self,
        session_id: str,
        lap_id: str | None,
        profile_id: str,
    ) -> None:
        now_ms = _now_ms()
        with self.connect() as con:
            self._require_track_profile(con, profile_id)
            self._require_session(con, session_id)
            if lap_id is None:
                raise ValueError("lap_id is required for track profile assignment")

            self._require_lap_in_session(con, session_id, lap_id)
            con.execute(
                "UPDATE laps SET track_profile_id = ? WHERE id = ?",
                (profile_id, lap_id),
            )
            track_row = con.execute(
                """
                SELECT track_profiles.name AS track_name,
                       track_profiles.layout AS track_layout
                FROM track_profiles
                WHERE track_profiles.id = ?
                """,
                (profile_id,),
            ).fetchone()
            con.execute(
                """
                UPDATE lifetime_stat_laps
                SET track_profile_id = ?, track_name = ?, track_layout = ?, updated_at_ms = ?
                WHERE lap_id = ?
                """,
                (
                    profile_id,
                    track_row["track_name"] if track_row is not None else None,
                    track_row["track_layout"] if track_row is not None else None,
                    now_ms,
                    lap_id,
                ),
            )

    def record_lifetime_lap_stats(
        self,
        lap_id: str,
        *,
        require_completed_candidate: bool = True,
    ) -> None:
        now_ms = _now_ms()
        lap_time_ms_sql = _lap_time_ms_sql("laps", "lap_summaries")
        completed_lap_predicate = (
            _completed_lap_time_candidate_sql("laps")
            if require_completed_candidate
            else "1 = 1"
        )
        with self.connect() as con:
            row = con.execute(
                f"""
                WITH lap_speed AS (
                    SELECT lap_id, MAX(speed_mps) AS max_speed_mps
                    FROM lap_samples
                    WHERE lap_id = ?
                    GROUP BY lap_id
                )
                SELECT laps.id AS lap_id,
                       laps.user_id,
                       laps.session_id,
                       COALESCE(laps.ended_at_ms, sessions.last_active_at_ms, sessions.ended_at_ms, laps.started_at_ms) AS recorded_at_ms,
                       laps.started_at_ms AS lap_started_at_ms,
                       laps.ended_at_ms AS lap_ended_at_ms,
                       {lap_time_ms_sql} AS lap_time_ms,
                       lap_speed.max_speed_mps,
                       sessions.car_ordinal,
                       sessions.car_name,
                       sessions.car_class_label,
                       sessions.drivetrain_label,
                       laps.track_profile_id,
                       track_profiles.name AS track_name,
                       track_profiles.layout AS track_layout
                FROM laps
                JOIN sessions ON sessions.id = laps.session_id
                LEFT JOIN lap_summaries ON lap_summaries.lap_id = laps.id
                LEFT JOIN lap_speed ON lap_speed.lap_id = laps.id
                LEFT JOIN track_profiles ON track_profiles.id = laps.track_profile_id
                WHERE laps.id = ?
                  AND laps.user_id = ?
                  AND sessions.user_id = ?
                  AND lower(trim(coalesce(laps.status, ''))) NOT IN ('active', 'recording')
                  AND {completed_lap_predicate}
                """,
                (lap_id, lap_id, LOCAL_USER_ID, LOCAL_USER_ID),
            ).fetchone()
            if row is None:
                return
            car_key = _car_key_from_values(row["car_ordinal"], row["car_name"])
            con.execute(
                """
                INSERT OR IGNORE INTO lifetime_stat_laps(
                    lap_id, user_id, session_id, recorded_at_ms,
                    lap_started_at_ms, lap_ended_at_ms, lap_time_ms, max_speed_mps,
                    car_ordinal, car_key, car_name, car_class_label, drivetrain_label,
                    track_profile_id, track_name, track_layout, created_at_ms, updated_at_ms
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["lap_id"],
                    row["user_id"],
                    row["session_id"],
                    int(row["recorded_at_ms"] or now_ms),
                    row["lap_started_at_ms"],
                    row["lap_ended_at_ms"],
                    row["lap_time_ms"],
                    row["max_speed_mps"],
                    row["car_ordinal"],
                    car_key,
                    row["car_name"],
                    row["car_class_label"],
                    row["drivetrain_label"],
                    row["track_profile_id"],
                    row["track_name"],
                    row["track_layout"],
                    now_ms,
                    now_ms,
                ),
            )

    def track_profiles(self) -> list[dict]:
        with self.connect() as con:
            rows = con.execute(
                """
                SELECT id, owner_user_id, name, layout, source, confidence,
                       shape_signature, created_at_ms, updated_at_ms
                FROM track_profiles
                ORDER BY lower(name) ASC, lower(layout) ASC, created_at_ms ASC, id ASC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def track_profile(self, profile_id: str) -> dict | None:
        with self.connect() as con:
            row = con.execute(
                """
                SELECT id, owner_user_id, name, layout, source, confidence,
                       shape_signature, created_at_ms, updated_at_ms
                FROM track_profiles
                WHERE id = ?
                """,
                (profile_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def create_track_asset(
        self,
        *,
        track_profile_id: str,
        filename: str,
        stored_path: str,
        mime_type: str,
        size_bytes: int,
        transform: dict | None = None,
    ) -> str:
        asset_id = str(uuid.uuid4())
        now_ms = _now_ms()
        clean_filename = self._required_text(filename, "filename")
        clean_stored_path = self._required_text(stored_path, "stored_path")
        validate_asset(clean_filename, mime_type, size_bytes)
        normalized_transform = validate_transform(transform)
        transform_json = json.dumps(
            normalized_transform,
            sort_keys=True,
            separators=(",", ":"),
        )
        with self.connect() as con:
            self._require_track_profile(con, track_profile_id)
            con.execute(
                """
                INSERT INTO track_assets(
                    id, track_profile_id, filename, stored_path, mime_type,
                    size_bytes, transform_json, created_at_ms, updated_at_ms
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    asset_id,
                    track_profile_id,
                    clean_filename,
                    clean_stored_path,
                    mime_type,
                    int(size_bytes),
                    transform_json,
                    now_ms,
                    now_ms,
                ),
            )
        return asset_id

    def update_track_asset_transform(self, asset_id: str, transform: dict) -> dict:
        now_ms = _now_ms()
        normalized_transform = validate_transform(transform)
        transform_json = json.dumps(
            normalized_transform,
            sort_keys=True,
            separators=(",", ":"),
        )
        with self.connect() as con:
            cursor = con.execute(
                """
                UPDATE track_assets
                SET transform_json = ?, updated_at_ms = ?
                WHERE id = ?
                """,
                (transform_json, now_ms, asset_id),
            )
            if cursor.rowcount != 1:
                raise ValueError(f"unknown track_asset_id: {asset_id}")
            row = self._require_track_asset(con, asset_id)
        return self._track_asset_from_row(row)

    def delete_track_asset(self, asset_id: str) -> dict:
        with self.connect() as con:
            row = self._require_track_asset(con, asset_id)
            asset = self._track_asset_from_row(row)
            con.execute("DELETE FROM track_assets WHERE id = ?", (asset_id,))
        return asset

    def track_assets_for_profile(self, profile_id: str) -> list[dict]:
        with self.connect() as con:
            self._require_track_profile(con, profile_id)
            rows = con.execute(
                """
                SELECT id, track_profile_id, filename, stored_path, mime_type,
                       size_bytes, transform_json, created_at_ms, updated_at_ms
                FROM track_assets
                WHERE track_profile_id = ?
                ORDER BY created_at_ms ASC, id ASC
                """,
                (profile_id,),
            ).fetchall()
        return [self._track_asset_from_row(row) for row in rows]

    def track_asset(self, asset_id: str) -> dict | None:
        with self.connect() as con:
            row = con.execute(
                """
                SELECT id, track_profile_id, filename, stored_path, mime_type,
                       size_bytes, transform_json, created_at_ms, updated_at_ms
                FROM track_assets
                WHERE id = ?
                """,
                (asset_id,),
            ).fetchone()
        return self._track_asset_from_row(row) if row is not None else None

    def delete_lap(self, lap_id: str) -> dict | None:
        with self.connect() as con:
            row = con.execute(
                """
                SELECT laps.id, laps.user_id, laps.session_id, sessions.label AS session_label,
                       laps.lap_number, laps.status, laps.started_at_ms, laps.ended_at_ms,
                       laps.ended_reason, laps.boundary_confidence, laps.track_profile_id
                FROM laps
                JOIN sessions ON sessions.id = laps.session_id
                WHERE laps.id = ?
                """,
                (lap_id,),
            ).fetchone()
            if row is None:
                return None
            lap = dict(row)

            con.execute("DELETE FROM packet_blobs WHERE lap_id = ?", (lap_id,))
            con.execute("DELETE FROM lap_samples WHERE lap_id = ?", (lap_id,))
            con.execute("DELETE FROM issue_markers WHERE lap_id = ?", (lap_id,))
            con.execute("DELETE FROM lap_summaries WHERE lap_id = ?", (lap_id,))
            con.execute("DELETE FROM comparison_refs WHERE lap_id = ?", (lap_id,))
            con.execute("DELETE FROM laps WHERE id = ?", (lap_id,))
        return lap

    def _laps_query(self, where_clause: str = "") -> str:
        where_sql = f"WHERE {where_clause}" if where_clause else ""
        lap_time_ms_sql = _lap_time_ms_sql("laps", "lap_summaries")
        return f"""
            SELECT laps.id, laps.user_id, laps.session_id, sessions.label AS session_label,
                   laps.lap_number, laps.status, laps.started_at_ms, laps.ended_at_ms,
                   laps.ended_reason, laps.boundary_confidence,
                   laps.track_profile_id, track_profiles.name AS track_profile_name,
                   track_profiles.layout AS track_profile_layout,
                   {lap_time_ms_sql} AS lap_time_ms
            FROM laps
            JOIN sessions ON sessions.id = laps.session_id
            LEFT JOIN track_profiles ON track_profiles.id = laps.track_profile_id
            LEFT JOIN lap_summaries ON lap_summaries.lap_id = laps.id
            {where_sql}
        """

    def latest_laps(self, limit: int = 50) -> list[dict]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        with self.connect() as con:
            rows = con.execute(
                self._laps_query()
                + """
                ORDER BY COALESCE(laps.ended_at_ms, laps.started_at_ms) DESC,
                         laps.started_at_ms DESC,
                         laps.rowid DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def lap(self, lap_id: str) -> dict | None:
        with self.connect() as con:
            row = con.execute(self._laps_query("laps.id = ?"), (lap_id,)).fetchone()
        return None if row is None else dict(row)

    def laps_for_session(self, session_id: str) -> list[dict]:
        with self.connect() as con:
            self._require_session(con, session_id)
            rows = con.execute(
                self._laps_query("sessions.id = ?")
                + """
                ORDER BY COALESCE(laps.ended_at_ms, laps.started_at_ms) DESC,
                         laps.started_at_ms DESC,
                         laps.rowid DESC
                """,
                (session_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def latest_sessions(self, limit: int = 50) -> list[dict]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        return self.paged_sessions(page=1, page_size=limit)["sessions"]

    def _stats_favourite_from_lifetime_snapshots(
        self,
        con: sqlite3.Connection,
        column_name: str,
    ) -> dict | None:
        allowed_columns = {"car_name", "car_class_label", "drivetrain_label"}
        if column_name not in allowed_columns:
            raise ValueError(f"unsupported stats favourite column: {column_name}")

        quoted_column = self._quote_identifier(column_name)
        group_expression = "car_key" if column_name == "car_name" else quoted_column
        if column_name == "car_name":
            group_predicate = "car_key IS NOT NULL"
        else:
            group_predicate = f"TRIM(COALESCE({quoted_column}, '')) != ''"
        row = con.execute(
            f"""
            SELECT TRIM({quoted_column}) AS value,
                   COUNT(lap_id) AS lap_count,
                   COUNT(DISTINCT session_id) AS session_count,
                   MAX(recorded_at_ms) AS last_used_at_ms
            FROM lifetime_stat_laps
            WHERE user_id = ?
              AND TRIM(COALESCE({quoted_column}, '')) != ''
              AND {group_predicate}
            GROUP BY {group_expression}
            ORDER BY lap_count DESC,
                     last_used_at_ms DESC,
                     lower(value) ASC
            LIMIT 1
            """,
            (LOCAL_USER_ID,),
        ).fetchone()
        return None if row is None else dict(row)

    def _stats_favourite_track(self, con: sqlite3.Connection) -> dict | None:
        row = con.execute(
            """
            WITH eligible_track_laps AS (
                SELECT rowid AS snapshot_rowid,
                       lap_id,
                       session_id,
                       track_profile_id,
                       track_name,
                       track_layout,
                       recorded_at_ms
                FROM lifetime_stat_laps
                WHERE user_id = ?
                  AND track_profile_id IS NOT NULL
                  AND TRIM(COALESCE(track_name, '')) != ''
            ),
            track_totals AS (
                SELECT track_profile_id,
                       COUNT(lap_id) AS lap_count,
                       COUNT(DISTINCT session_id) AS session_count,
                       MAX(recorded_at_ms) AS last_used_at_ms
                FROM eligible_track_laps
                GROUP BY track_profile_id
            ),
            latest_display AS (
                SELECT track_profile_id,
                       track_name,
                       track_layout,
                       ROW_NUMBER() OVER (
                           PARTITION BY track_profile_id
                           ORDER BY recorded_at_ms DESC,
                                    snapshot_rowid DESC,
                                    lap_id DESC
                       ) AS display_rank
                FROM eligible_track_laps
            )
            SELECT latest_display.track_name AS value,
                   latest_display.track_layout AS detail,
                   track_totals.lap_count,
                   track_totals.session_count,
                   track_totals.last_used_at_ms
            FROM track_totals
            JOIN latest_display
              ON latest_display.track_profile_id = track_totals.track_profile_id
             AND latest_display.display_rank = 1
            ORDER BY lap_count DESC,
                     last_used_at_ms DESC,
                     lower(value) ASC,
                     lower(detail) ASC,
                     track_totals.track_profile_id ASC
            LIMIT 1
            """,
            (LOCAL_USER_ID,),
        ).fetchone()
        return None if row is None else dict(row)

    def stats_summary(self) -> dict:
        with self.connect() as con:
            row = con.execute(
                """
                SELECT
                    COUNT(*) AS laps_recorded,
                    COUNT(DISTINCT session_id) AS sessions_created,
                    MAX(max_speed_mps) AS max_speed_mps,
                    COALESCE(SUM(lap_time_ms), 0) AS time_spent_racing_ms,
                    COUNT(DISTINCT track_profile_id) AS tracks_driven,
                    COUNT(DISTINCT car_key) AS cars_driven
                FROM lifetime_stat_laps
                WHERE user_id = ?
                """,
                (LOCAL_USER_ID,),
            ).fetchone()
            summary = dict(row)
            summary["favourite_car"] = self._stats_favourite_from_lifetime_snapshots(
                con,
                "car_name",
            )
            summary["favourite_pi_class"] = self._stats_favourite_from_lifetime_snapshots(
                con,
                "car_class_label",
            )
            summary["favoured_drive"] = self._stats_favourite_from_lifetime_snapshots(
                con,
                "drivetrain_label",
            )
            summary["favourite_track"] = self._stats_favourite_track(con)
        summary["laps_recorded"] = int(summary["laps_recorded"] or 0)
        summary["sessions_created"] = int(summary["sessions_created"] or 0)
        summary["time_spent_racing_ms"] = int(summary["time_spent_racing_ms"] or 0)
        summary["tracks_driven"] = int(summary["tracks_driven"] or 0)
        summary["cars_driven"] = int(summary["cars_driven"] or 0)
        return summary

    def paged_sessions(
        self,
        *,
        page: int = 1,
        page_size: int = 100,
        name: str | None = None,
        created_from: int | None = None,
        created_to: int | None = None,
        last_active_from: int | None = None,
        last_active_to: int | None = None,
        lap_count_min: int | None = None,
        lap_count_max: int | None = None,
        track: str | None = None,
        car: str | None = None,
    ) -> dict:
        if page <= 0:
            raise ValueError("page must be positive")
        if page_size <= 0 or page_size > 100:
            raise ValueError("page_size must be between 1 and 100")

        where = ["sessions.user_id = ?"]
        params: list[object] = [LOCAL_USER_ID]
        outer_where = []
        outer_params: list[object] = []

        if name:
            where.append("lower(sessions.label) LIKE ?")
            params.append(f"%{name.strip().lower()}%")
        if created_from is not None:
            where.append("sessions.started_at_ms >= ?")
            params.append(int(created_from))
        if created_to is not None:
            where.append("sessions.started_at_ms <= ?")
            params.append(int(created_to))
        if last_active_from is not None:
            where.append(
                """
                COALESCE(
                    sessions.last_active_at_ms,
                    sessions.ended_at_ms,
                    sessions.started_at_ms
                ) >= ?
                """
            )
            params.append(int(last_active_from))
        if last_active_to is not None:
            where.append(
                """
                COALESCE(
                    sessions.last_active_at_ms,
                    sessions.ended_at_ms,
                    sessions.started_at_ms
                ) <= ?
                """
            )
            params.append(int(last_active_to))
        if track:
            where.append(
                """
                EXISTS (
                    SELECT 1
                    FROM laps AS track_filter_laps
                    JOIN track_profiles AS track_filter_profiles
                      ON track_filter_profiles.id = track_filter_laps.track_profile_id
                    WHERE track_filter_laps.session_id = sessions.id
                      AND (
                          lower(coalesce(track_filter_profiles.name, '')) LIKE ?
                          OR lower(coalesce(track_filter_profiles.layout, '')) LIKE ?
                      )
                )
                """
            )
            track_filter = f"%{track.strip().lower()}%"
            params.extend([track_filter, track_filter])
        if car:
            where.append("lower(coalesce(sessions.car_name, '')) LIKE ?")
            params.append(f"%{car.strip().lower()}%")
        if lap_count_min is not None:
            outer_where.append("lap_count >= ?")
            outer_params.append(int(lap_count_min))
        if lap_count_max is not None:
            outer_where.append("lap_count <= ?")
            outer_params.append(int(lap_count_max))

        inner = self._session_select_sql(" AND ".join(where))
        base = "SELECT * FROM (" + inner + ") AS filtered_sessions"
        all_params = params
        if outer_where:
            base += " WHERE " + " AND ".join(outer_where)
            all_params = [*params, *outer_params]

        offset = (page - 1) * page_size
        with self.connect() as con:
            total = int(
                con.execute(f"SELECT COUNT(*) FROM ({base})", all_params).fetchone()[0]
            )
            rows = con.execute(
                base
                + """
                ORDER BY last_active_at_ms DESC, started_at_ms DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                [*all_params, page_size, offset],
            ).fetchall()

        total_pages = 0 if total == 0 else ((total - 1) // page_size) + 1
        return {
            "sessions": [dict(row) for row in rows],
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
        }

    def insert_lap_summary(self, lap_id: str, summary: dict) -> None:
        now_ms = _now_ms()
        with self.connect() as con:
            merged_summary = self._summary_with_preserved_comparison_contexts(
                con,
                lap_id,
                summary,
            )
            summary_json = json.dumps(merged_summary, sort_keys=True, separators=(",", ":"))
            con.execute(
                """
                INSERT INTO lap_summaries(lap_id, summary_json, created_at_ms, updated_at_ms)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(lap_id) DO UPDATE SET
                    summary_json = excluded.summary_json,
                    updated_at_ms = excluded.updated_at_ms
                """,
                (lap_id, summary_json, now_ms, now_ms),
            )

    def lap_summary(self, lap_id: str) -> dict | None:
        with self.connect() as con:
            row = con.execute(
                "SELECT summary_json FROM lap_summaries WHERE lap_id = ?",
                (lap_id,),
            ).fetchone()
        if row is None:
            return None
        return json.loads(row["summary_json"])

    def pin_reference_lap(self, scope: str, context_key: str, lap_id: str) -> None:
        scope = self._validate_reference_scope(scope)
        context_key = self._reference_context_key(context_key)
        now_ms = _now_ms()
        with self.connect() as con:
            row = con.execute(
                "SELECT id FROM laps WHERE id = ? AND user_id = ?",
                (lap_id, LOCAL_USER_ID),
            ).fetchone()
            if row is None:
                raise ValueError(f"unknown lap_id: {lap_id}")
            con.execute(
                """
                INSERT INTO comparison_refs(user_id, scope, context_key, lap_id, pinned_at_ms)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id, scope, context_key) DO UPDATE SET
                    lap_id = excluded.lap_id,
                    pinned_at_ms = excluded.pinned_at_ms
                """,
                (LOCAL_USER_ID, scope, context_key, lap_id, now_ms),
            )

    def clear_reference_lap(self, scope: str, context_key: str) -> None:
        scope = self._validate_reference_scope(scope)
        context_key = self._reference_context_key(context_key)
        with self.connect() as con:
            con.execute(
                """
                DELETE FROM comparison_refs
                WHERE user_id = ? AND scope = ? AND context_key = ?
                """,
                (LOCAL_USER_ID, scope, context_key),
            )

    def pinned_reference_lap(
        self,
        scope: str,
        context_key: str,
        *,
        exclude_lap_id: str | None = None,
    ) -> dict | None:
        scope = self._validate_reference_scope(scope)
        context_key = self._reference_context_key(context_key)
        exclude_lap_id = str(exclude_lap_id) if exclude_lap_id is not None else None
        exclude_clause = ""
        params: list[object] = [LOCAL_USER_ID, scope, context_key]
        if exclude_lap_id is not None:
            exclude_clause = "AND laps.id != ?"
            params.append(exclude_lap_id)
        with self.connect() as con:
            row = con.execute(
                f"""
                SELECT {self._reference_lap_select_columns()},
                       comparison_refs.pinned_at_ms AS pinned_at_ms
                FROM comparison_refs
                JOIN laps ON laps.id = comparison_refs.lap_id
                JOIN sessions ON sessions.id = laps.session_id
                LEFT JOIN lap_summaries ON lap_summaries.lap_id = laps.id
                WHERE comparison_refs.user_id = ?
                  AND comparison_refs.scope = ?
                  AND comparison_refs.context_key = ?
                  {exclude_clause}
                """,
                params,
            ).fetchone()

        if row is not None:
            reference = self._reference_lap_from_row(
                row,
                scope=scope,
                context_key=context_key,
                source="pinned",
                pinned_at_ms=row["pinned_at_ms"],
            )
            if self._is_usable_reference_lap(reference):
                return reference

        candidates = self.candidate_reference_laps(
            scope,
            context_key,
            limit=1,
            exclude_lap_id=exclude_lap_id,
        )
        if not candidates:
            return None
        fallback = dict(candidates[0])
        fallback["source"] = "best_available"
        return fallback

    def candidate_reference_laps(
        self,
        scope: str,
        context_key: str,
        limit: int = 20,
        *,
        exclude_lap_id: str | None = None,
        session_id: str | None = None,
    ) -> list[dict]:
        scope = self._validate_reference_scope(scope)
        context_key = self._reference_context_key(context_key)
        if limit <= 0:
            raise ValueError("limit must be positive")

        exclude_lap_id = str(exclude_lap_id) if exclude_lap_id is not None else None
        session_id = str(session_id) if session_id is not None else None
        context_predicate, context_params = self._reference_context_sql_predicate(
            scope,
            context_key,
        )
        assignment_track_profile_id = self._track_profile_id_from_reference_context(
            scope,
            context_key,
        )
        assignment_predicate = ""
        assignment_params: tuple[str, ...] = ()
        if assignment_track_profile_id is not None:
            assignment_predicate = "OR laps.track_profile_id = ?"
            assignment_params = (assignment_track_profile_id,)
        rejected_states = tuple(sorted(_REFERENCE_REJECTED_STATES))
        completed_states = tuple(sorted(_REFERENCE_COMPLETED_STATES))
        rejected_placeholders = ",".join("?" for _ in rejected_states)
        completed_placeholders = ",".join("?" for _ in completed_states)
        session_clause = ""
        exclude_clause = ""
        params: list[object] = [
            LOCAL_USER_ID,
            *context_params,
            *assignment_params,
            *rejected_states,
            *rejected_states,
            *completed_states,
            *completed_states,
        ]
        if session_id is not None:
            session_clause = "AND laps.session_id = ?"
            params.append(session_id)
        if exclude_lap_id is not None:
            exclude_clause = "AND laps.id != ?"
            params.append(exclude_lap_id)

        with self.connect() as con:
            rows = con.execute(
                f"""
                SELECT {self._reference_lap_select_columns()},
                       NULL AS pinned_at_ms
                FROM laps
                JOIN sessions ON sessions.id = laps.session_id
                JOIN lap_summaries ON lap_summaries.lap_id = laps.id
                WHERE laps.user_id = ?
                  AND (({context_predicate}) {assignment_predicate})
                  AND EXISTS (
                      SELECT 1
                      FROM lap_samples
                      WHERE lap_samples.lap_id = laps.id
                      LIMIT 1
                  )
                  AND laps.ended_at_ms IS NOT NULL
                  AND lower(coalesce(laps.boundary_confidence, '')) NOT IN (
                      '', 'unknown', 'uncertain'
                  )
                  AND lower(trim(coalesce(laps.status, ''))) NOT IN ({rejected_placeholders})
                  AND lower(trim(coalesce(laps.ended_reason, ''))) NOT IN ({rejected_placeholders})
                  AND (
                      lower(trim(coalesce(laps.status, ''))) IN ({completed_placeholders})
                      OR lower(trim(coalesce(laps.ended_reason, ''))) IN ({completed_placeholders})
                  )
                  {session_clause}
                  {exclude_clause}
                """,
                params,
            ).fetchall()

        references = [
            self._reference_lap_from_row(
                row,
                scope=scope,
                context_key=context_key,
                source="candidate",
                pinned_at_ms=None,
            )
            for row in rows
        ]
        usable_references = [
            reference
            for reference in references
            if self._is_usable_reference_lap(reference)
        ]
        usable_references.sort(key=self._reference_candidate_sort_key)
        return usable_references[:limit]

    def samples_for_lap(self, lap_id: str) -> list[dict]:
        select_columns = _sample_select_columns()
        with self.connect() as con:
            rows = con.execute(
                f"""
                SELECT {select_columns}
                FROM lap_samples
                WHERE lap_id = ?
                ORDER BY sequence ASC, id ASC
                """,
                (lap_id,),
            ).fetchall()
        return [_sample_from_row(row, include_extended=True) for row in rows]

    def samples_for_range(
        self,
        session_id: str,
        start_sequence: int,
        end_sequence: int,
        lap_id: str | None = None,
    ) -> list[dict]:
        conditions = ["session_id = ?", "sequence BETWEEN ? AND ?"]
        params: list[object] = [session_id, int(start_sequence), int(end_sequence)]
        if lap_id is not None:
            conditions.append("lap_id = ?")
            params.append(lap_id)
        select_columns = _sample_select_columns()
        query = f"""
            SELECT {select_columns}
            FROM lap_samples
            WHERE {' AND '.join(conditions)}
            ORDER BY sequence ASC, id ASC
        """
        with self.connect() as con:
            rows = con.execute(query, tuple(params)).fetchall()
        return [_sample_from_row(row, include_extended=True) for row in rows]

    def delete_lap_samples_after_current_lap(
        self,
        lap_id: str,
        current_lap: float,
    ) -> int:
        """Delete samples for a lap segment that was invalidated by rewind/reset.

        The caller supplies the current-lap timestamp of the matched return point.
        Existing samples after that point describe route that no longer happened
        after a rewind or checkpoint reset, so remove both derived samples and
        their raw blobs before appending the replacement packet.
        """

        with self.connect() as con:
            rows = con.execute(
                """
                SELECT session_id, lap_id, sequence
                FROM lap_samples
                WHERE lap_id = ? AND current_lap > ?
                ORDER BY sequence
                """,
                (lap_id, float(current_lap)),
            ).fetchall()
            keys = [(row["session_id"], row["lap_id"], int(row["sequence"])) for row in rows]
            if not keys:
                return 0
            first_deleted_sequence = min(sequence for _session_id, _lap_id, sequence in keys)
            con.executemany(
                """
                DELETE FROM packet_blobs
                WHERE session_id = ? AND lap_id = ? AND sequence = ?
                """,
                keys,
            )
            con.executemany(
                """
                DELETE FROM lap_samples
                WHERE session_id = ? AND lap_id = ? AND sequence = ?
                """,
                keys,
            )
            con.execute(
                "DELETE FROM issue_markers WHERE lap_id = ? AND end_sequence >= ?",
                (lap_id, first_deleted_sequence),
            )
            con.execute("DELETE FROM lap_summaries WHERE lap_id = ?", (lap_id,))
            return len(keys)

    def insert_issue_markers(self, markers: list[dict]) -> None:
        if not markers:
            return
        with self.connect() as con:
            self._validate_marker_lap_ids(con, markers)
            con.executemany(
                """
                INSERT INTO issue_markers(
                    id, session_id, lap_id, start_sequence, end_sequence,
                    metric, severity, reason, ruleset_version, confidence,
                    anchor_sequence, issue_kind, actual_value, threshold_value,
                    threshold_operator, value_label, value_unit
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    session_id = excluded.session_id,
                    lap_id = excluded.lap_id,
                    start_sequence = excluded.start_sequence,
                    end_sequence = excluded.end_sequence,
                    metric = excluded.metric,
                    severity = excluded.severity,
                    reason = excluded.reason,
                    ruleset_version = excluded.ruleset_version,
                    confidence = excluded.confidence,
                    anchor_sequence = excluded.anchor_sequence,
                    issue_kind = excluded.issue_kind,
                    actual_value = excluded.actual_value,
                    threshold_value = excluded.threshold_value,
                    threshold_operator = excluded.threshold_operator,
                    value_label = excluded.value_label,
                    value_unit = excluded.value_unit
                """,
                [
                    (
                        marker["id"],
                        marker["session_id"],
                        marker.get("lap_id"),
                        int(marker["start_sequence"]),
                        int(marker["end_sequence"]),
                        marker["metric"],
                        marker["severity"],
                        marker["reason"],
                        int(marker["ruleset_version"]),
                        float(marker["confidence"]),
                        None if marker.get("anchor_sequence") is None else int(marker["anchor_sequence"]),
                        marker.get("issue_kind"),
                        marker.get("actual_value"),
                        marker.get("threshold_value"),
                        marker.get("threshold_operator"),
                        marker.get("value_label"),
                        marker.get("value_unit"),
                    )
                    for marker in markers
                ],
            )

    def replace_analysis_results(
        self,
        session_id: str,
        lap_id: str | None,
        summary: dict | None,
        markers: list[dict],
    ) -> None:
        with self.connect() as con:
            self._validate_marker_lap_ids(con, markers)
            self._delete_issue_markers_for_scope(con, session_id=session_id, lap_id=lap_id)
            if lap_id is not None and summary is not None:
                now_ms = _now_ms()
                merged_summary = self._summary_with_preserved_comparison_contexts(
                    con,
                    lap_id,
                    summary,
                )
                summary_json = json.dumps(merged_summary, sort_keys=True, separators=(",", ":"))
                con.execute(
                    """
                    INSERT INTO lap_summaries(lap_id, summary_json, created_at_ms, updated_at_ms)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(lap_id) DO UPDATE SET
                        summary_json = excluded.summary_json,
                        updated_at_ms = excluded.updated_at_ms
                    """,
                    (lap_id, summary_json, now_ms, now_ms),
                )
            if markers:
                con.executemany(
                    """
                    INSERT INTO issue_markers(
                        id, session_id, lap_id, start_sequence, end_sequence,
                        metric, severity, reason, ruleset_version, confidence,
                        anchor_sequence, issue_kind, actual_value, threshold_value,
                        threshold_operator, value_label, value_unit
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            marker["id"],
                            marker["session_id"],
                            marker.get("lap_id"),
                            int(marker["start_sequence"]),
                            int(marker["end_sequence"]),
                            marker["metric"],
                            marker["severity"],
                            marker["reason"],
                            int(marker["ruleset_version"]),
                            float(marker["confidence"]),
                            None if marker.get("anchor_sequence") is None else int(marker["anchor_sequence"]),
                            marker.get("issue_kind"),
                            marker.get("actual_value"),
                            marker.get("threshold_value"),
                            marker.get("threshold_operator"),
                            marker.get("value_label"),
                            marker.get("value_unit"),
                        )
                        for marker in markers
                    ],
                )

    def issue_markers_for_lap(
        self,
        lap_id: str | None,
        session_id: str | None = None,
    ) -> list[dict]:
        if lap_id is None and session_id is None:
            raise ValueError("session_id is required when lap_id is None")
        query = """
            SELECT id, session_id, lap_id, start_sequence, end_sequence,
                   metric, severity, reason, ruleset_version, confidence,
                   anchor_sequence, issue_kind, actual_value, threshold_value,
                   threshold_operator, value_label, value_unit
            FROM issue_markers
        """
        params: tuple[object, ...]
        if lap_id is None:
            query += " WHERE lap_id IS NULL AND session_id = ?"
            params = (session_id,)
        else:
            query += " WHERE lap_id = ?"
            params = (lap_id,)
        query += " ORDER BY start_sequence ASC, end_sequence ASC, metric ASC, id ASC"
        with self.connect() as con:
            rows = con.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def raw_packet_at_sequence(self, session_id: str, sequence: int) -> bytes | None:
        with self.connect() as con:
            row = con.execute(
                """
                SELECT raw_packet
                FROM packet_blobs
                WHERE session_id = ? AND sequence = ?
                ORDER BY id ASC
                LIMIT 1
                """,
                (session_id, int(sequence)),
            ).fetchone()
        if row is None:
            return None
        return bytes(row["raw_packet"])

    def latest_packet_bytes(self, session_id: str, limit: int) -> list[bytes]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        with self.connect() as con:
            rows = con.execute(
                """
                SELECT raw_packet
                FROM packet_blobs
                WHERE session_id = ?
                ORDER BY sequence DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        return [bytes(row["raw_packet"]) for row in reversed(rows)]

    def packet_bytes_for_lap(self, lap_id: str) -> list[bytes]:
        with self.connect() as con:
            rows = con.execute(
                """
                SELECT raw_packet
                FROM packet_blobs
                WHERE lap_id = ?
                ORDER BY sequence ASC
                """,
                (lap_id,),
            ).fetchall()
        return [bytes(row["raw_packet"]) for row in rows]

    def _summary_with_preserved_comparison_contexts(
        self,
        con: sqlite3.Connection,
        lap_id: str,
        summary: dict,
    ) -> dict:
        merged_summary = dict(summary)
        if "comparison_contexts" in merged_summary:
            return merged_summary

        row = con.execute(
            "SELECT summary_json FROM lap_summaries WHERE lap_id = ?",
            (lap_id,),
        ).fetchone()
        if row is None:
            return merged_summary

        existing_summary = self._reference_summary(row["summary_json"])
        if (
            isinstance(existing_summary, dict)
            and "comparison_contexts" in existing_summary
        ):
            merged_summary["comparison_contexts"] = existing_summary[
                "comparison_contexts"
            ]
        return merged_summary

    def _reference_lap_select_columns(self) -> str:
        lap_time_ms_sql = _lap_time_ms_sql("laps", "lap_summaries")
        return f"""
            laps.id AS id,
            laps.id AS lap_id,
            laps.user_id AS user_id,
            laps.session_id AS session_id,
            sessions.label AS session_label,
            laps.lap_number AS lap_number,
            laps.status AS status,
            laps.started_at_ms AS started_at_ms,
            laps.ended_at_ms AS ended_at_ms,
            laps.ended_reason AS ended_reason,
            laps.boundary_confidence AS boundary_confidence,
            laps.track_profile_id AS track_profile_id,
            {lap_time_ms_sql} AS lap_time_ms,
            lap_summaries.summary_json AS summary_json,
            lap_summaries.created_at_ms AS summary_created_at_ms,
            lap_summaries.updated_at_ms AS summary_updated_at_ms,
            (
                SELECT COUNT(*)
                FROM lap_samples
                WHERE lap_samples.lap_id = laps.id
            ) AS stored_sample_count
        """

    def _reference_lap_from_row(
        self,
        row: sqlite3.Row,
        *,
        scope: str,
        context_key: str,
        source: str,
        pinned_at_ms: int | None,
    ) -> dict:
        summary = self._reference_summary(row["summary_json"])
        stored_sample_count = int(row["stored_sample_count"] or 0)
        sample_count = self._reference_sample_count(summary, stored_sample_count)
        lap_time_ms = self._reference_lap_time_ms(summary, row["lap_time_ms"])
        return {
            "id": row["lap_id"],
            "lap_id": row["lap_id"],
            "user_id": row["user_id"],
            "session_id": row["session_id"],
            "session_label": row["session_label"],
            "lap_number": row["lap_number"],
            "status": row["status"],
            "started_at_ms": row["started_at_ms"],
            "ended_at_ms": row["ended_at_ms"],
            "ended_reason": row["ended_reason"],
            "boundary_confidence": row["boundary_confidence"],
            "track_profile_id": row["track_profile_id"],
            "summary": summary,
            "summary_created_at_ms": row["summary_created_at_ms"],
            "summary_updated_at_ms": row["summary_updated_at_ms"],
            "stored_sample_count": stored_sample_count,
            "sample_count": sample_count,
            "lap_time_ms": lap_time_ms,
            "lap_duration_ms": lap_time_ms,
            "scope": scope,
            "context_key": context_key,
            "comparison_context_key": context_key,
            "source": source,
            "pinned_at_ms": pinned_at_ms,
        }

    def _reference_summary(self, summary_json: str | None) -> dict | None:
        if summary_json is None:
            return None
        try:
            summary = json.loads(summary_json)
        except json.JSONDecodeError:
            return None
        return summary if isinstance(summary, dict) else None

    def _reference_sample_count(
        self,
        summary: dict | None,
        stored_sample_count: int,
    ) -> int | None:
        if summary is not None:
            for key in ("sample_count", "packet_count"):
                parsed_count = self._non_negative_int(summary.get(key))
                if parsed_count is not None:
                    return parsed_count
        if stored_sample_count > 0:
            return stored_sample_count
        return None

    def _reference_lap_time_ms(
        self,
        summary: dict | None,
        row_lap_time_ms: object,
    ) -> float | None:
        try:
            duration = float(row_lap_time_ms)
        except (TypeError, ValueError, OverflowError):
            duration = None
        if duration is not None and duration >= 0:
            return duration

        if isinstance(summary, dict):
            for key in ("lap_time_ms", "lap_duration_ms"):
                if key not in summary:
                    continue
                value = summary.get(key)
                if value is None:
                    continue
                try:
                    duration = float(value)
                except (TypeError, ValueError, OverflowError):
                    continue
                if duration >= 0:
                    return duration
        return None

    def _reference_matches_context(self, reference: dict) -> bool:
        if self._summary_matches_reference_context(
            reference.get("summary"),
            str(reference.get("scope") or ""),
            str(reference.get("context_key") or ""),
        ):
            return True
        return self._track_profile_context_matches(reference)

    def _reference_context_sql_predicate(
        self,
        scope: str,
        context_key: str,
    ) -> tuple[str, tuple[str, ...]]:
        json_path = _REFERENCE_CONTEXT_JSON_PATHS[scope]
        json_doc = (
            "CASE "
            "WHEN json_valid(lap_summaries.summary_json) "
            "THEN lap_summaries.summary_json "
            "ELSE '{}' "
            "END"
        )
        context_value = (
            "CASE "
            "WHEN json_valid(lap_summaries.summary_json) "
            f"THEN json_extract(lap_summaries.summary_json, '{json_path}') "
            "END"
        )
        predicate = f"""
            {context_value} = ?
            OR CASE
                   WHEN json_valid(lap_summaries.summary_json)
                   THEN json_extract(lap_summaries.summary_json, '{json_path}.context_key')
               END = ?
            OR CASE
                   WHEN json_valid(lap_summaries.summary_json)
                   THEN json_extract(lap_summaries.summary_json, '{json_path}.key')
               END = ?
            OR CASE
                   WHEN json_valid(lap_summaries.summary_json)
                   THEN json_extract(lap_summaries.summary_json, '{json_path}.id')
               END = ?
            OR EXISTS (
                SELECT 1
                FROM json_each({json_doc}, '{json_path}') AS context_values
                WHERE context_values.type = 'text'
                  AND context_values.value = ?
            )
        """
        return predicate, (context_key,) * 5

    def _summary_matches_reference_context(
        self,
        summary: object,
        scope: str,
        context_key: str,
    ) -> bool:
        if not isinstance(summary, dict):
            return False

        contexts = summary.get("comparison_contexts")
        if not isinstance(contexts, dict):
            return False

        return self._context_value_matches(contexts.get(scope), context_key)

    def _context_value_matches(self, value: object, context_key: str) -> bool:
        if isinstance(value, str):
            return value == context_key
        if isinstance(value, (list, tuple, set)):
            return any(
                isinstance(candidate, str) and candidate == context_key
                for candidate in value
            )
        if isinstance(value, dict):
            for key in ("context_key", "key", "id"):
                if value.get(key) == context_key:
                    return True
        return False

    def _track_profile_context_matches(self, reference: dict) -> bool:
        scope = str(reference.get("scope") or "")
        context_key = str(reference.get("context_key") or "")
        return self._track_profile_context_key(reference, scope) == context_key

    def _track_profile_context_key(self, reference: dict, scope: str) -> str | None:
        profile_id = self._context_value_as_string(reference.get("track_profile_id"))
        if profile_id is None or scope not in SUPPORTED_REFERENCE_SCOPES:
            return None
        if scope == "track":
            return profile_id

        car_key = self._reference_car_key(reference, scope)
        if scope == "track_car":
            return f"{profile_id}|{car_key}"

        build_key = self._reference_build_key(reference)
        return f"{profile_id}|{car_key}|{build_key}"

    def _reference_car_key(self, reference: dict, scope: str) -> str:
        direct_key = self._reference_context_component(reference, "car")
        if direct_key is None:
            direct_key = self._reference_field_value(reference, _REFERENCE_CAR_FIELDS)
        if direct_key is not None:
            return direct_key
        if scope == "track_car_build":
            return (
                self._reference_context_scope_part(reference, "track_car_build", 1)
                or self._reference_context_scope_part(reference, "track_car", 1)
                or "unknown_car"
            )
        return (
            self._reference_context_scope_part(reference, "track_car", 1)
            or self._reference_context_scope_part(reference, "track_car_build", 1)
            or "unknown_car"
        )

    def _reference_build_key(self, reference: dict) -> str:
        return (
            self._reference_context_component(reference, "build")
            or self._reference_field_value(reference, _REFERENCE_BUILD_FIELDS)
            or self._reference_context_scope_part(reference, "track_car_build", 2)
            or "unknown_build"
        )

    def _reference_context_component(self, reference: dict, key: str) -> str | None:
        summary = reference.get("summary")
        if not isinstance(summary, dict):
            return None
        contexts = summary.get("comparison_contexts")
        if not isinstance(contexts, dict):
            return None
        return self._context_value_as_string(contexts.get(key))

    def _reference_context_scope_part(
        self,
        reference: dict,
        key: str,
        index: int,
    ) -> str | None:
        summary = reference.get("summary")
        if not isinstance(summary, dict):
            return None
        contexts = summary.get("comparison_contexts")
        if not isinstance(contexts, dict):
            return None
        value = self._reference_context_component(reference, key)
        if value is None:
            return None
        parts = value.split("|")
        if len(parts) <= index:
            return None
        return self._context_value_as_string(parts[index])

    def _track_profile_id_from_reference_context(
        self,
        scope: str,
        context_key: str,
    ) -> str | None:
        if scope not in SUPPORTED_REFERENCE_SCOPES:
            return None
        text = str(context_key or "").strip()
        if not text:
            return None
        candidate = text if scope == "track" else text.split("|", 1)[0]
        if not candidate or candidate.startswith("unknown_track:"):
            return None
        return candidate

    def _reference_field_value(
        self,
        reference: dict,
        keys: tuple[str, ...],
        *,
        default: str | None = None,
    ) -> str | None:
        containers = [reference]
        summary = reference.get("summary")
        if isinstance(summary, dict):
            containers.append(summary)
        for container in list(containers):
            for nested_key in ("metadata", "context", "lap_context"):
                nested = container.get(nested_key)
                if isinstance(nested, dict):
                    containers.append(nested)

        for container in containers:
            for key in keys:
                value = self._context_value_as_string(container.get(key))
                if value is not None:
                    return value
        return default

    def _context_value_as_string(self, value: object) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            text = value.strip()
            return text or None
        if isinstance(value, dict):
            for key in ("context_key", "key", "id", "slug", "name"):
                parsed_value = self._context_value_as_string(value.get(key))
                if parsed_value is not None:
                    return parsed_value
            return None
        if isinstance(value, (list, tuple, set)):
            for candidate in value:
                parsed_value = self._context_value_as_string(candidate)
                if parsed_value is not None:
                    return parsed_value
            return None
        return str(value)

    def _is_usable_reference_lap(self, reference: dict) -> bool:
        if not self._reference_matches_context(reference):
            return False

        status = self._normalized_state(reference.get("status"))
        ended_reason = self._normalized_state(reference.get("ended_reason"))
        if (
            status in _REFERENCE_REJECTED_STATES
            or ended_reason in _REFERENCE_REJECTED_STATES
        ):
            return False
        if (
            status not in _REFERENCE_COMPLETED_STATES
            and ended_reason not in _REFERENCE_COMPLETED_STATES
        ):
            return False

        if reference.get("ended_at_ms") is None:
            return False

        boundary_confidence = str(reference.get("boundary_confidence") or "").lower()
        if boundary_confidence in {"", "unknown", "uncertain"}:
            return False

        summary = reference.get("summary")
        if isinstance(summary, dict):
            uncertainty_count = self._non_negative_int(summary.get("uncertainty_count"))
            if uncertainty_count is not None and uncertainty_count > 0:
                return False

        if reference.get("lap_time_ms") is None:
            return False

        return int(reference.get("stored_sample_count") or 0) > 0

    def _normalized_state(self, value: object) -> str:
        return str(value or "").strip().lower()

    def _reference_candidate_sort_key(self, reference: dict) -> tuple:
        newest_ms = int(
            reference.get("ended_at_ms")
            or reference.get("started_at_ms")
            or 0
        )
        lap_time_ms = reference.get("lap_time_ms")
        lap_id = str(reference.get("lap_id") or "")
        if lap_time_ms is not None:
            return (0, float(lap_time_ms), -newest_ms, lap_id)
        if reference.get("summary") is not None:
            return (1, -newest_ms, lap_id)
        return (2, -newest_ms, lap_id)

    def _non_negative_int(self, value: object) -> int | None:
        try:
            parsed_value = int(value)
        except (TypeError, ValueError, OverflowError):
            return None
        if parsed_value < 0:
            return None
        return parsed_value

    def _required_text(self, value: str, field_name: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError(f"{field_name} is required")
        return text

    def _table_exists(self, con: sqlite3.Connection, table_name: str) -> bool:
        row = con.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table' AND name = ?
            """,
            (table_name,),
        ).fetchone()
        return row is not None

    def _track_profile_reference_tables(self, con: sqlite3.Connection) -> list[str]:
        rows = con.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()
        table_names = []
        for row in rows:
            table_name = row["name"]
            foreign_keys = con.execute(
                f"PRAGMA foreign_key_list({self._quote_identifier(table_name)})"
            ).fetchall()
            if any(
                foreign_key["from"] == "track_profile_id"
                and foreign_key["table"] == "track_profiles"
                and foreign_key["to"] == "id"
                for foreign_key in foreign_keys
            ):
                table_names.append(table_name)
        return table_names

    def _quote_identifier(self, identifier: str) -> str:
        return '"' + identifier.replace('"', '""') + '"'

    def _car_record_tuple(self, record: dict, now_ms: int) -> tuple:
        return (
            int(record["ordinal"]),
            record.get("display_name"),
            record.get("model_short"),
            record.get("make"),
            record.get("model"),
            _optional_int_value(record.get("year")),
            record.get("base_class_label"),
            _optional_int_value(record.get("base_pi")),
            record.get("car_type"),
            record.get("country"),
            _optional_int_value(record.get("value_cr")),
            record.get("rarity"),
            record.get("source"),
            record.get("source_info"),
            record.get("asset_name"),
            record.get("asset_zip"),
            record.get("catalog_source") or "unknown",
            now_ms,
        )

    def upsert_car_catalog_records(self, records: list[dict]) -> int:
        if not records:
            return 0
        now_ms = _now_ms()
        with self.connect() as con:
            con.executemany(
                """
                INSERT INTO cars(
                    ordinal, display_name, model_short, make, model, year,
                    base_class_label, base_pi, car_type, country, value_cr,
                    rarity, source, source_info, asset_name, asset_zip,
                    catalog_source, updated_at_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ordinal) DO UPDATE SET
                    display_name = COALESCE(excluded.display_name, cars.display_name),
                    model_short = COALESCE(excluded.model_short, cars.model_short),
                    make = COALESCE(excluded.make, cars.make),
                    model = COALESCE(excluded.model, cars.model),
                    year = COALESCE(excluded.year, cars.year),
                    base_class_label = COALESCE(excluded.base_class_label, cars.base_class_label),
                    base_pi = COALESCE(excluded.base_pi, cars.base_pi),
                    car_type = COALESCE(excluded.car_type, cars.car_type),
                    country = COALESCE(excluded.country, cars.country),
                    value_cr = COALESCE(excluded.value_cr, cars.value_cr),
                    rarity = COALESCE(excluded.rarity, cars.rarity),
                    source = COALESCE(excluded.source, cars.source),
                    source_info = COALESCE(excluded.source_info, cars.source_info),
                    asset_name = COALESCE(excluded.asset_name, cars.asset_name),
                    asset_zip = COALESCE(excluded.asset_zip, cars.asset_zip),
                    catalog_source = excluded.catalog_source,
                    updated_at_ms = excluded.updated_at_ms
                """,
                [self._car_record_tuple(record, now_ms) for record in records],
            )
        return len(records)

    def car_by_ordinal(self, ordinal: int | None) -> dict | None:
        if ordinal is None:
            return None
        with self.connect() as con:
            row = con.execute(
                "SELECT * FROM cars WHERE ordinal = ?",
                (int(ordinal),),
            ).fetchone()
        return None if row is None else dict(row)

    def car_catalog_count(self) -> int:
        with self.connect() as con:
            return int(con.execute("SELECT COUNT(*) FROM cars").fetchone()[0])

    def _game_track_record_tuple(self, record: dict, now_ms: int) -> tuple:
        use_cross_country_ai = record.get("use_cross_country_ai")
        return (
            str(record["track_key"]),
            _optional_int_value(record.get("source_dataset_key")),
            _optional_int_value(record.get("route_id")),
            _optional_int_value(record.get("custom_route_id")),
            _optional_int_value(record.get("media_track_id")),
            record.get("media_track_name"),
            record.get("ribbon_config"),
            record.get("display_name"),
            record.get("short_display_name"),
            record.get("short_display_name_all_caps"),
            record.get("description"),
            record.get("display_name_key"),
            record.get("short_display_name_key"),
            record.get("short_display_name_all_caps_key"),
            record.get("description_key"),
            record.get("route_activation_trigger_zone_name"),
            None if use_cross_country_ai is None else int(bool(use_cross_country_ai)),
            record.get("stray_warning_distance"),
            record.get("stray_teleport_distance"),
            record.get("source_file"),
            record.get("catalog_source") or "unknown",
            now_ms,
        )

    def _game_map_region_record_tuple(self, record: dict, now_ms: int) -> tuple:
        return (
            str(record["region_key"]),
            record.get("english_name"),
            record.get("english_short_name"),
            record.get("japanese_name"),
            record.get("japanese_short_name"),
            record.get("name_key"),
            record.get("short_name_key"),
            record.get("locator_collection_name"),
            record.get("top_image_path"),
            record.get("map_tile_mascot_image"),
            record.get("map_hover_fmod_event"),
            record.get("first_time_enter_fmod_event"),
            record.get("rich_presence_event"),
            _optional_int_value(record.get("full_reveal_percentage")),
            record.get("announcement_ie_state"),
            record.get("source_file"),
            record.get("catalog_source") or "unknown",
            now_ms,
        )

    def _game_track_locator_record_tuple(self, record: dict, now_ms: int) -> tuple:
        return (
            str(record["source_file"]),
            record.get("media_track_name"),
            str(record["locator_collection"]),
            str(record["locator_name"]),
            str(record["locator_kind"]),
            _optional_int_value(record.get("route_id")),
            float(record["x"]),
            float(record["y"]),
            float(record["z"]),
            record.get("heading_yaw_rad"),
            str(record["transform_json"]),
            record.get("catalog_source") or "unknown",
            now_ms,
        )

    def upsert_game_track_records(self, records: list[dict]) -> int:
        if not records:
            return 0
        now_ms = _now_ms()
        with self.connect() as con:
            con.executemany(
                """
                INSERT INTO game_tracks(
                    track_key, source_dataset_key, route_id, custom_route_id,
                    media_track_id, media_track_name, ribbon_config,
                    display_name, short_display_name, short_display_name_all_caps,
                    description, display_name_key, short_display_name_key,
                    short_display_name_all_caps_key, description_key,
                    route_activation_trigger_zone_name, use_cross_country_ai,
                    stray_warning_distance, stray_teleport_distance, source_file,
                    catalog_source, updated_at_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(track_key) DO UPDATE SET
                    source_dataset_key = COALESCE(excluded.source_dataset_key, game_tracks.source_dataset_key),
                    route_id = COALESCE(excluded.route_id, game_tracks.route_id),
                    custom_route_id = COALESCE(excluded.custom_route_id, game_tracks.custom_route_id),
                    media_track_id = COALESCE(excluded.media_track_id, game_tracks.media_track_id),
                    media_track_name = COALESCE(excluded.media_track_name, game_tracks.media_track_name),
                    ribbon_config = COALESCE(excluded.ribbon_config, game_tracks.ribbon_config),
                    display_name = COALESCE(excluded.display_name, game_tracks.display_name),
                    short_display_name = COALESCE(excluded.short_display_name, game_tracks.short_display_name),
                    short_display_name_all_caps = COALESCE(excluded.short_display_name_all_caps, game_tracks.short_display_name_all_caps),
                    description = COALESCE(excluded.description, game_tracks.description),
                    display_name_key = COALESCE(excluded.display_name_key, game_tracks.display_name_key),
                    short_display_name_key = COALESCE(excluded.short_display_name_key, game_tracks.short_display_name_key),
                    short_display_name_all_caps_key = COALESCE(excluded.short_display_name_all_caps_key, game_tracks.short_display_name_all_caps_key),
                    description_key = COALESCE(excluded.description_key, game_tracks.description_key),
                    route_activation_trigger_zone_name = COALESCE(excluded.route_activation_trigger_zone_name, game_tracks.route_activation_trigger_zone_name),
                    use_cross_country_ai = COALESCE(excluded.use_cross_country_ai, game_tracks.use_cross_country_ai),
                    stray_warning_distance = COALESCE(excluded.stray_warning_distance, game_tracks.stray_warning_distance),
                    stray_teleport_distance = COALESCE(excluded.stray_teleport_distance, game_tracks.stray_teleport_distance),
                    source_file = COALESCE(excluded.source_file, game_tracks.source_file),
                    catalog_source = excluded.catalog_source,
                    updated_at_ms = excluded.updated_at_ms
                """,
                [self._game_track_record_tuple(record, now_ms) for record in records],
            )
        return len(records)

    def upsert_game_map_region_records(self, records: list[dict]) -> int:
        if not records:
            return 0
        now_ms = _now_ms()
        with self.connect() as con:
            con.executemany(
                """
                INSERT INTO game_map_regions(
                    region_key, english_name, english_short_name, japanese_name,
                    japanese_short_name, name_key, short_name_key,
                    locator_collection_name, top_image_path, map_tile_mascot_image,
                    map_hover_fmod_event, first_time_enter_fmod_event,
                    rich_presence_event, full_reveal_percentage,
                    announcement_ie_state, source_file, catalog_source, updated_at_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(region_key) DO UPDATE SET
                    english_name = COALESCE(excluded.english_name, game_map_regions.english_name),
                    english_short_name = COALESCE(excluded.english_short_name, game_map_regions.english_short_name),
                    japanese_name = COALESCE(excluded.japanese_name, game_map_regions.japanese_name),
                    japanese_short_name = COALESCE(excluded.japanese_short_name, game_map_regions.japanese_short_name),
                    name_key = COALESCE(excluded.name_key, game_map_regions.name_key),
                    short_name_key = COALESCE(excluded.short_name_key, game_map_regions.short_name_key),
                    locator_collection_name = COALESCE(excluded.locator_collection_name, game_map_regions.locator_collection_name),
                    top_image_path = COALESCE(excluded.top_image_path, game_map_regions.top_image_path),
                    map_tile_mascot_image = COALESCE(excluded.map_tile_mascot_image, game_map_regions.map_tile_mascot_image),
                    map_hover_fmod_event = COALESCE(excluded.map_hover_fmod_event, game_map_regions.map_hover_fmod_event),
                    first_time_enter_fmod_event = COALESCE(excluded.first_time_enter_fmod_event, game_map_regions.first_time_enter_fmod_event),
                    rich_presence_event = COALESCE(excluded.rich_presence_event, game_map_regions.rich_presence_event),
                    full_reveal_percentage = COALESCE(excluded.full_reveal_percentage, game_map_regions.full_reveal_percentage),
                    announcement_ie_state = COALESCE(excluded.announcement_ie_state, game_map_regions.announcement_ie_state),
                    source_file = COALESCE(excluded.source_file, game_map_regions.source_file),
                    catalog_source = excluded.catalog_source,
                    updated_at_ms = excluded.updated_at_ms
                """,
                [self._game_map_region_record_tuple(record, now_ms) for record in records],
            )
        return len(records)

    def upsert_game_track_locator_records(self, records: list[dict]) -> int:
        if not records:
            return 0
        now_ms = _now_ms()
        with self.connect() as con:
            con.executemany(
                """
                INSERT INTO game_track_locators(
                    source_file, media_track_name, locator_collection, locator_name,
                    locator_kind, route_id, x, y, z, heading_yaw_rad,
                    transform_json, catalog_source, updated_at_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_file, locator_name) DO UPDATE SET
                    media_track_name = COALESCE(excluded.media_track_name, game_track_locators.media_track_name),
                    locator_collection = excluded.locator_collection,
                    locator_kind = excluded.locator_kind,
                    route_id = COALESCE(excluded.route_id, game_track_locators.route_id),
                    x = excluded.x,
                    y = excluded.y,
                    z = excluded.z,
                    heading_yaw_rad = COALESCE(excluded.heading_yaw_rad, game_track_locators.heading_yaw_rad),
                    transform_json = excluded.transform_json,
                    catalog_source = excluded.catalog_source,
                    updated_at_ms = excluded.updated_at_ms
                """,
                [self._game_track_locator_record_tuple(record, now_ms) for record in records],
            )
        return len(records)

    def upsert_track_catalog_records(
        self,
        tracks: list[dict],
        map_regions: list[dict] | None = None,
        locators: list[dict] | None = None,
    ) -> dict[str, int]:
        return {
            "tracks": self.upsert_game_track_records(tracks),
            "map_regions": self.upsert_game_map_region_records(map_regions or []),
            "locators": self.upsert_game_track_locator_records(locators or []),
        }

    def track_catalog_count(self) -> int:
        with self.connect() as con:
            return int(con.execute("SELECT COUNT(*) FROM game_tracks").fetchone()[0])

    def game_track_by_route_id(self, route_id: int | None) -> dict | None:
        if route_id is None:
            return None
        with self.connect() as con:
            row = con.execute(
                """
                SELECT * FROM game_tracks
                WHERE route_id = ?
                ORDER BY source_dataset_key
                LIMIT 1
                """,
                (int(route_id),),
            ).fetchone()
        return None if row is None else dict(row)

    def game_track_by_key(self, track_key: str | None) -> dict | None:
        if not track_key:
            return None
        with self.connect() as con:
            row = con.execute(
                "SELECT * FROM game_tracks WHERE track_key = ?",
                (track_key,),
            ).fetchone()
        return None if row is None else dict(row)

    def game_tracks(self) -> list[dict]:
        with self.connect() as con:
            rows = con.execute(
                """
                SELECT * FROM game_tracks
                ORDER BY COALESCE(display_name, short_display_name, track_key), source_dataset_key
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def game_track_locators(self) -> list[dict]:
        with self.connect() as con:
            rows = con.execute(
                """
                SELECT * FROM game_track_locators
                ORDER BY locator_collection, locator_name
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def game_track_locator_count(self, *, source_file_like: str | None = None) -> int:
        with self.connect() as con:
            if source_file_like:
                return int(
                    con.execute(
                        """
                        SELECT COUNT(*)
                        FROM game_track_locators
                        WHERE source_file LIKE ?
                        """,
                        (source_file_like,),
                    ).fetchone()[0]
                )
            return int(con.execute("SELECT COUNT(*) FROM game_track_locators").fetchone()[0])

    def ensure_game_track_profiles(self) -> int:
        now_ms = _now_ms()
        created = 0
        with self.connect() as con:
            tracks = con.execute(
                """
                SELECT game_tracks.*
                FROM game_tracks
                LEFT JOIN game_track_profile_links
                  ON game_track_profile_links.track_key = game_tracks.track_key
                WHERE game_track_profile_links.track_key IS NULL
                ORDER BY COALESCE(
                    game_tracks.display_name,
                    game_tracks.short_display_name,
                    game_tracks.track_key
                ), game_tracks.source_dataset_key
                """
            ).fetchall()
            for track in tracks:
                profile_id = str(uuid.uuid4())
                display_name = self._game_track_profile_display_name(track)
                layout = self._game_track_profile_layout(track)
                con.execute(
                    """
                    INSERT INTO track_profiles(
                        id, owner_user_id, name, layout, source, confidence,
                        shape_signature, created_at_ms, updated_at_ms
                    ) VALUES (?, NULL, ?, ?, ?, ?, NULL, ?, ?)
                    """,
                    (
                        profile_id,
                        display_name,
                        layout,
                        "fh6_catalog_match",
                        "auto",
                        now_ms,
                        now_ms,
                    ),
                )
                con.execute(
                    """
                    INSERT INTO game_track_profile_links(
                        track_key, track_profile_id, created_at_ms, updated_at_ms
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (track["track_key"], profile_id, now_ms, now_ms),
                )
                created += 1
        return created

    def game_track_profile_ids_by_track_key(self, track_keys: Iterable[str]) -> dict[str, str]:
        normalized_keys = sorted({str(track_key) for track_key in track_keys if track_key})
        if not normalized_keys:
            return {}
        placeholders = ",".join("?" for _ in normalized_keys)
        with self.connect() as con:
            rows = con.execute(
                f"""
                SELECT track_key, track_profile_id
                FROM game_track_profile_links
                WHERE track_key IN ({placeholders})
                """,
                tuple(normalized_keys),
            ).fetchall()
        return {str(row["track_key"]): str(row["track_profile_id"]) for row in rows}

    def ensure_game_track_profile(self, track_key: str) -> dict:
        now_ms = _now_ms()
        with self.connect() as con:
            existing = con.execute(
                """
                SELECT track_profiles.id, track_profiles.owner_user_id,
                       track_profiles.name, track_profiles.layout,
                       track_profiles.source, track_profiles.confidence,
                       track_profiles.shape_signature, track_profiles.created_at_ms,
                       track_profiles.updated_at_ms
                FROM game_track_profile_links
                JOIN track_profiles ON track_profiles.id = game_track_profile_links.track_profile_id
                WHERE game_track_profile_links.track_key = ?
                """,
                (track_key,),
            ).fetchone()
            if existing is not None:
                return dict(existing)

            track = con.execute(
                "SELECT * FROM game_tracks WHERE track_key = ?",
                (track_key,),
            ).fetchone()
            if track is None:
                raise ValueError(f"unknown track_key: {track_key}")

            profile_id = str(uuid.uuid4())
            display_name = self._game_track_profile_display_name(track)
            layout = self._game_track_profile_layout(track)
            con.execute(
                """
                INSERT INTO track_profiles(
                    id, owner_user_id, name, layout, source, confidence,
                    shape_signature, created_at_ms, updated_at_ms
                ) VALUES (?, NULL, ?, ?, ?, ?, NULL, ?, ?)
                """,
                (
                    profile_id,
                    str(display_name),
                    str(layout),
                    "fh6_catalog_match",
                    "auto",
                    now_ms,
                    now_ms,
                ),
            )
            con.execute(
                """
                INSERT INTO game_track_profile_links(
                    track_key, track_profile_id, created_at_ms, updated_at_ms
                ) VALUES (?, ?, ?, ?)
                """,
                (track_key, profile_id, now_ms, now_ms),
            )
            row = con.execute(
                """
                SELECT id, owner_user_id, name, layout, source, confidence,
                       shape_signature, created_at_ms, updated_at_ms
                FROM track_profiles
                WHERE id = ?
                """,
                (profile_id,),
            ).fetchone()
        return dict(row)

    @staticmethod
    def _game_track_profile_display_name(track: dict) -> str:
        return str(
            track["display_name"]
            or track["short_display_name"]
            or (f"Route {track['route_id']}" if track["route_id"] is not None else track["track_key"])
        )

    @staticmethod
    def _game_track_profile_layout(track: dict) -> str:
        return str(track["ribbon_config"] or track["media_track_name"] or "Unknown")

    def replace_track_match_candidates(
        self,
        *,
        lap_id: str,
        session_id: str,
        matcher_version: str,
        candidates: list[dict],
        assigned_track_profile_id: str | None = None,
    ) -> int:
        now_ms = _now_ms()
        with self.connect() as con:
            self._require_lap_in_session(con, session_id, lap_id)
            track_keys = sorted(
                {
                    str(candidate["track_key"])
                    for candidate in candidates
                    if candidate.get("track_key")
                }
            )
            profile_ids_by_track_key: dict[str, str] = {}
            if track_keys:
                placeholders = ",".join("?" for _ in track_keys)
                profile_ids_by_track_key = {
                    str(row["track_key"]): str(row["track_profile_id"])
                    for row in con.execute(
                        f"""
                        SELECT track_key, track_profile_id
                        FROM game_track_profile_links
                        WHERE track_key IN ({placeholders})
                        """,
                        tuple(track_keys),
                    ).fetchall()
                }
            con.execute(
                """
                DELETE FROM track_match_candidates
                WHERE lap_id = ? AND matcher_version = ?
                """,
                (lap_id, matcher_version),
            )
            con.executemany(
                """
                INSERT INTO track_match_candidates(
                    lap_id, session_id, matcher_version, candidate_rank,
                    candidate_kind, track_key, track_profile_id, route_id,
                    display_name, confidence, score_components_json, reasons_json,
                    is_auto_assignable, assigned_track_profile_id, created_at_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    self._track_match_candidate_tuple(
                        lap_id,
                        session_id,
                        matcher_version,
                        candidate,
                        index,
                        assigned_track_profile_id,
                        profile_ids_by_track_key,
                        now_ms,
                    )
                    for index, candidate in enumerate(candidates, start=1)
                ],
            )
        return len(candidates)

    def _track_match_candidate_tuple(
        self,
        lap_id: str,
        session_id: str,
        matcher_version: str,
        candidate: dict,
        rank: int,
        assigned_track_profile_id: str | None,
        profile_ids_by_track_key: dict[str, str],
        now_ms: int,
    ) -> tuple:
        track_key = candidate.get("track_key")
        track_profile_id = candidate.get("track_profile_id")
        if track_profile_id is None and track_key:
            track_profile_id = profile_ids_by_track_key.get(str(track_key))
        return (
            lap_id,
            session_id,
            matcher_version,
            rank,
            candidate.get("candidate_kind") or "game_track",
            track_key,
            track_profile_id,
            _optional_int_value(candidate.get("route_id")),
            candidate.get("display_name"),
            float(candidate.get("confidence") or 0.0),
            json.dumps(candidate.get("score_components") or {}, separators=(",", ":"), sort_keys=True),
            json.dumps(candidate.get("reasons") or [], separators=(",", ":"), sort_keys=True),
            int(bool(candidate.get("is_auto_assignable"))),
            assigned_track_profile_id if rank == 1 else None,
            now_ms,
        )

    def track_match_candidates_for_lap(
        self,
        lap_id: str,
        matcher_version: str | None = None,
    ) -> list[dict]:
        params: tuple = (lap_id,)
        version_predicate = ""
        if matcher_version is not None:
            version_predicate = "AND matcher_version = ?"
            params = (lap_id, matcher_version)
        with self.connect() as con:
            rows = con.execute(
                f"""
                SELECT *
                FROM track_match_candidates
                WHERE lap_id = ?
                {version_predicate}
                ORDER BY created_at_ms DESC, matcher_version DESC, candidate_rank ASC
                """,
                params,
            ).fetchall()
        candidates = []
        for row in rows:
            candidate = dict(row)
            try:
                candidate["score_components"] = json.loads(candidate.pop("score_components_json"))
            except (TypeError, json.JSONDecodeError):
                candidate["score_components"] = {}
            try:
                candidate["reasons"] = json.loads(candidate.pop("reasons_json"))
            except (TypeError, json.JSONDecodeError):
                candidate["reasons"] = []
            candidate["is_auto_assignable"] = bool(candidate["is_auto_assignable"])
            if (
                candidate.get("track_profile_id") is None
                and candidate.get("assigned_track_profile_id") is not None
            ):
                candidate["track_profile_id"] = candidate["assigned_track_profile_id"]
            candidates.append(candidate)
        return candidates
    def world_map_settings(self) -> dict:
        with self.connect() as con:
            row = con.execute(
                """
                SELECT fh6_media_root, world_map_enabled, world_map_season
                FROM user_settings
                WHERE user_id = ?
                """,
                (LOCAL_USER_ID,),
            ).fetchone()
        if row is None:
            return {
                "fh6_media_root": None,
                "world_map_enabled": False,
                "world_map_season": "summer",
            }
        return self._world_map_settings_from_row(row)

    def update_world_map_settings(
        self,
        *,
        media_root: str | None,
        enabled: bool,
        season: str,
    ) -> dict:
        normalized_media_root = self._optional_text(media_root)
        normalized_season = self._validate_world_map_season(season)
        now_ms = _now_ms()
        with self.connect() as con:
            con.execute(
                """
                UPDATE user_settings
                SET fh6_media_root = ?,
                    world_map_enabled = ?,
                    world_map_season = ?,
                    updated_at_ms = ?
                WHERE user_id = ?
                """,
                (
                    normalized_media_root,
                    int(bool(enabled)),
                    normalized_season,
                    now_ms,
                    LOCAL_USER_ID,
                ),
            )
            row = con.execute(
                """
                SELECT fh6_media_root, world_map_enabled, world_map_season
                FROM user_settings
                WHERE user_id = ?
                """,
                (LOCAL_USER_ID,),
            ).fetchone()
        return self._world_map_settings_from_row(row)

    def upsert_world_map_tile_set(self, record: dict) -> dict:
        normalized = self._world_map_tile_set_record(record)
        with self.connect() as con:
            con.execute(
                """
                INSERT INTO world_map_tile_sets(
                    id, game, map_name, season, source_zip_path,
                    source_zip_mtime_ms, source_zip_size_bytes, cache_dir,
                    tile_format, tile_size, min_zoom, max_zoom,
                    world_origin_x, world_origin_z, world_size,
                    status, manifest_json, error_message,
                    last_built_at_ms, updated_at_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    game = excluded.game,
                    map_name = excluded.map_name,
                    season = excluded.season,
                    source_zip_path = excluded.source_zip_path,
                    source_zip_mtime_ms = excluded.source_zip_mtime_ms,
                    source_zip_size_bytes = excluded.source_zip_size_bytes,
                    cache_dir = excluded.cache_dir,
                    tile_format = excluded.tile_format,
                    tile_size = excluded.tile_size,
                    min_zoom = excluded.min_zoom,
                    max_zoom = excluded.max_zoom,
                    world_origin_x = excluded.world_origin_x,
                    world_origin_z = excluded.world_origin_z,
                    world_size = excluded.world_size,
                    status = excluded.status,
                    manifest_json = excluded.manifest_json,
                    error_message = excluded.error_message,
                    last_built_at_ms = excluded.last_built_at_ms,
                    updated_at_ms = excluded.updated_at_ms
                """,
                normalized,
            )
            row = con.execute(
                "SELECT * FROM world_map_tile_sets WHERE id = ?",
                (str(record["id"]),),
            ).fetchone()
        return self._world_map_tile_set_from_row(row)

    def world_map_tile_set(self, tile_set_id: str) -> dict | None:
        with self.connect() as con:
            row = con.execute(
                "SELECT * FROM world_map_tile_sets WHERE id = ?",
                (str(tile_set_id),),
            ).fetchone()
        return None if row is None else self._world_map_tile_set_from_row(row)

    def latest_world_map_tile_set(
        self,
        game: str,
        map_name: str,
        season: str,
    ) -> dict | None:
        normalized_season = self._validate_world_map_season(season)
        with self.connect() as con:
            row = con.execute(
                """
                SELECT *
                FROM world_map_tile_sets
                WHERE game = ?
                  AND map_name = ?
                  AND season = ?
                  AND status = 'ready'
                ORDER BY updated_at_ms DESC, id
                LIMIT 1
                """,
                (str(game), str(map_name), normalized_season),
            ).fetchone()
        return None if row is None else self._world_map_tile_set_from_row(row)

    def world_map_tile_set_count(self) -> int:
        with self.connect() as con:
            return int(con.execute("SELECT COUNT(*) FROM world_map_tile_sets").fetchone()[0])

    def _world_map_settings_from_row(self, row: sqlite3.Row) -> dict:
        return {
            "fh6_media_root": row["fh6_media_root"],
            "world_map_enabled": bool(row["world_map_enabled"]),
            "world_map_season": row["world_map_season"],
        }

    def _optional_text(self, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _validate_world_map_season(self, season: str) -> str:
        normalized = str(season or "").strip().lower()
        if normalized not in SUPPORTED_WORLD_MAP_SEASONS:
            raise ValueError(
                "world_map_season must be one of autumn, spring, summer, or winter"
            )
        return normalized

    def _validate_world_map_status(self, status: str) -> str:
        normalized = str(status or "").strip().lower()
        if normalized not in WORLD_MAP_TILE_SET_STATUSES:
            raise ValueError("world map tile-set status must be missing, building, ready, or error")
        return normalized

    def _world_map_tile_set_record(self, record: dict) -> tuple:
        manifest_json = record.get("manifest_json")
        if manifest_json is None:
            manifest_json = json.dumps(record.get("manifest") or {}, sort_keys=True)
        else:
            json.loads(str(manifest_json))
            manifest_json = str(manifest_json)
        now_ms = _now_ms()
        updated_at_ms = _optional_int_value(record.get("updated_at_ms")) or now_ms
        return (
            str(record["id"]),
            str(record.get("game") or "fh6"),
            str(record.get("map_name") or "brio"),
            self._validate_world_map_season(str(record.get("season") or "summer")),
            str(record["source_zip_path"]),
            int(record["source_zip_mtime_ms"]),
            int(record["source_zip_size_bytes"]),
            str(record["cache_dir"]),
            str(record.get("tile_format") or "png"),
            int(record["tile_size"]),
            int(record["min_zoom"]),
            int(record["max_zoom"]),
            float(record["world_origin_x"]),
            float(record["world_origin_z"]),
            float(record["world_size"]),
            self._validate_world_map_status(str(record.get("status") or "missing")),
            manifest_json,
            record.get("error_message"),
            _optional_int_value(record.get("last_built_at_ms")),
            updated_at_ms,
        )

    def _world_map_tile_set_from_row(self, row: sqlite3.Row) -> dict:
        record = dict(row)
        record["manifest"] = json.loads(record["manifest_json"])
        return record

    def _require_track_profile(
        self,
        con: sqlite3.Connection,
        profile_id: str,
    ) -> sqlite3.Row:
        row = con.execute(
            "SELECT id FROM track_profiles WHERE id = ?",
            (profile_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown track_profile_id: {profile_id}")
        return row

    def _require_track_asset(
        self,
        con: sqlite3.Connection,
        asset_id: str,
    ) -> sqlite3.Row:
        row = con.execute(
            """
            SELECT id, track_profile_id, filename, stored_path, mime_type,
                   size_bytes, transform_json, created_at_ms, updated_at_ms
            FROM track_assets
            WHERE id = ?
            """,
            (asset_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown track_asset_id: {asset_id}")
        return row

    def _track_asset_from_row(self, row: sqlite3.Row) -> dict:
        asset = dict(row)
        try:
            asset["transform"] = validate_transform(json.loads(asset["transform_json"]))
        except (TypeError, json.JSONDecodeError, ValueError) as exc:
            raise ValueError(f"invalid transform_json for track_asset_id: {asset['id']}") from exc
        del asset["transform_json"]
        return asset

    def _require_session(
        self,
        con: sqlite3.Connection,
        session_id: str,
    ) -> sqlite3.Row:
        row = con.execute(
            "SELECT id FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown session_id: {session_id}")
        return row

    def _require_lap_in_session(
        self,
        con: sqlite3.Connection,
        session_id: str,
        lap_id: str,
    ) -> sqlite3.Row:
        row = con.execute(
            "SELECT id, session_id FROM laps WHERE id = ?",
            (lap_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown lap_id: {lap_id}")
        if row["session_id"] != session_id:
            raise ValueError(f"lap_id does not belong to session {session_id}: {lap_id}")
        return row

    def _validate_reference_scope(self, scope: str) -> str:
        if scope not in SUPPORTED_REFERENCE_SCOPES:
            supported = ", ".join(sorted(SUPPORTED_REFERENCE_SCOPES))
            raise ValueError(f"unsupported reference scope: {scope}; expected one of {supported}")
        return scope

    def _reference_context_key(self, context_key: str) -> str:
        if context_key is None:
            raise ValueError("context_key is required")
        return str(context_key)

    def _delete_issue_markers_for_scope(
        self,
        con: sqlite3.Connection,
        *,
        session_id: str,
        lap_id: str | None,
    ) -> None:
        if lap_id is None:
            con.execute(
                "DELETE FROM issue_markers WHERE session_id = ? AND lap_id IS NULL",
                (session_id,),
            )
            return
        con.execute("DELETE FROM issue_markers WHERE lap_id = ?", (lap_id,))

    def insert_packet_batch(
        self,
        session_id: str,
        raw_packets: list[bytes],
        decoded_packets: list[dict],
        samples: list[dict],
    ) -> None:
        if len(raw_packets) != len(decoded_packets) or len(raw_packets) != len(samples):
            raise ValueError("raw_packets, decoded_packets, and samples must have the same length")
        if not raw_packets:
            return
        with self.connect() as con:
            self._validate_lap_ids_for_session(con, session_id, samples)
            con.executemany(
                """
                INSERT INTO packet_blobs(
                    session_id, lap_id, sequence, received_at_ms, game_timestamp_ms, lap_number,
                    position_x, position_y, position_z, speed_mps, raw_packet
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        session_id,
                        sample.get("lap_id"),
                        int(sample["sequence"]),
                        sample["received_at_ms"],
                        int(decoded["TimestampMS"]),
                        int(decoded["LapNumber"]),
                        float(decoded["PositionX"]),
                        float(decoded["PositionY"]),
                        float(decoded["PositionZ"]),
                        float(decoded["Speed"]),
                        raw,
                    )
                    for index, (raw, decoded, sample) in enumerate(
                        zip(raw_packets, decoded_packets, samples, strict=True)
                    )
                ],
            )
            lap_sample_columns = ", ".join(_LAP_SAMPLE_INSERT_COLUMNS)
            lap_sample_placeholders = ", ".join("?" for _ in _LAP_SAMPLE_INSERT_COLUMNS)
            con.executemany(
                f"""
                INSERT INTO lap_samples({lap_sample_columns})
                VALUES ({lap_sample_placeholders})
                """,
                [
                    _lap_sample_insert_values(
                        session_id,
                        sample,
                        fallback_is_race_on=_decoded_is_race_on(decoded_packets[index]),
                    )
                    for index, sample in enumerate(samples)
                ],
            )
            con.execute(
                """
                UPDATE sessions
                SET last_active_at_ms = ?
                WHERE id = ?
                """,
                (_now_ms(), session_id),
            )

    def _validate_lap_ids_for_session(
        self,
        con: sqlite3.Connection,
        session_id: str,
        samples: list[dict],
    ) -> None:
        lap_ids = {
            str(lap_id)
            for sample in samples
            if (lap_id := sample.get("lap_id")) is not None
        }
        if not lap_ids:
            return

        placeholders = ",".join("?" for _ in lap_ids)
        rows = con.execute(
            f"SELECT id, session_id FROM laps WHERE id IN ({placeholders})",
            tuple(lap_ids),
        ).fetchall()
        lap_sessions = {row["id"]: row["session_id"] for row in rows}
        missing_lap_ids = lap_ids - set(lap_sessions)
        if missing_lap_ids:
            missing = ", ".join(sorted(missing_lap_ids))
            raise ValueError(f"unknown lap_id: {missing}")

        mismatched_lap_ids = [
            lap_id
            for lap_id, lap_session_id in lap_sessions.items()
            if lap_session_id != session_id
        ]
        if mismatched_lap_ids:
            mismatched = ", ".join(sorted(mismatched_lap_ids))
            raise ValueError(
                f"lap_id does not belong to session {session_id}: {mismatched}"
            )

    def _validate_marker_lap_ids(
        self,
        con: sqlite3.Connection,
        markers: list[dict],
    ) -> None:
        marker_groups: dict[str, set[str]] = {}
        for marker in markers:
            lap_id = marker.get("lap_id")
            session_id = marker.get("session_id")
            if lap_id is None:
                continue
            marker_groups.setdefault(str(session_id), set()).add(str(lap_id))

        for session_id, lap_ids in marker_groups.items():
            placeholders = ",".join("?" for _ in lap_ids)
            rows = con.execute(
                f"SELECT id, session_id FROM laps WHERE id IN ({placeholders})",
                tuple(lap_ids),
            ).fetchall()
            lap_sessions = {row["id"]: row["session_id"] for row in rows}
            missing_lap_ids = lap_ids - set(lap_sessions)
            if missing_lap_ids:
                missing = ", ".join(sorted(missing_lap_ids))
                raise ValueError(f"unknown lap_id: {missing}")

            mismatched_lap_ids = [
                lap_id
                for lap_id, lap_session_id in lap_sessions.items()
                if lap_session_id != session_id
            ]
            if mismatched_lap_ids:
                mismatched = ", ".join(sorted(mismatched_lap_ids))
                raise ValueError(
                    f"lap_id does not belong to session {session_id}: {mismatched}"
                )

    def count_packets(self, session_id: str) -> int:
        with self.connect() as con:
            return int(
                con.execute(
                    "SELECT COUNT(*) FROM packet_blobs WHERE session_id = ?",
                    (session_id,),
                ).fetchone()[0]
            )

    def latest_samples(self, session_id: str, limit: int) -> list[dict]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        select_columns = _sample_select_columns()
        with self.connect() as con:
            rows = con.execute(
                f"""
                SELECT {select_columns}
                FROM lap_samples
                WHERE session_id = ?
                ORDER BY sequence DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        samples = []
        for row in reversed(rows):
            sample = _sample_from_row(row, include_extended=True)
            sample.pop("lap_id", None)
            samples.append(sample)
        return samples

    def latest_session_recent_samples(self, limit: int) -> dict:
        if limit <= 0:
            raise ValueError("limit must be positive")
        select_columns = _sample_select_columns()
        with self.connect() as con:
            session = con.execute(
                """
                SELECT id
                FROM sessions
                ORDER BY started_at_ms DESC, rowid DESC
                LIMIT 1
                """
            ).fetchone()
            if session is None:
                return {"session_id": None, "samples": []}
            latest_race_lap = con.execute(
                """
                SELECT lap_id
                FROM lap_samples
                WHERE session_id = ? AND is_race_on = 1
                ORDER BY sequence DESC
                LIMIT 1
                """,
                (session["id"],),
            ).fetchone()
            latest_lap_id = (
                latest_race_lap["lap_id"] if latest_race_lap is not None else None
            )
            lap_condition = "AND lap_id = ?" if latest_lap_id is not None else ""
            params: tuple[object, ...] = (
                (session["id"], latest_lap_id, limit)
                if latest_lap_id is not None
                else (session["id"], limit)
            )
            rows = con.execute(
                f"""
                SELECT {select_columns}
                FROM lap_samples
                WHERE session_id = ? AND is_race_on = 1
                {lap_condition}
                ORDER BY sequence DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        samples = []
        for row in reversed(rows):
            sample = _sample_from_row(row, include_extended=True)
            sample.pop("lap_id", None)
            samples.append(sample)
        return {"session_id": session["id"], "samples": samples}
