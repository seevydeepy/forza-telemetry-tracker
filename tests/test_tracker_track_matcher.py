from pathlib import Path

from fastapi.testclient import TestClient

from telemetry_tracker.app import create_app
from telemetry_tracker.storage import TelemetryStore
from telemetry_tracker.track_matcher import MATCHER_VERSION, match_lap_track, match_samples_to_tracks


def _store(tmp_path: Path) -> TelemetryStore:
    store = TelemetryStore(tmp_path / "telemetry_tracker.sqlite3")
    store.migrate()
    return store


def _insert_track_and_locators(store: TelemetryStore, *, track_key: str, route_id: int, offset_z: float = 0.0):
    store.upsert_track_catalog_records(
        [
            {
                "track_key": track_key,
                "source_dataset_key": route_id,
                "route_id": route_id,
                "media_track_id": 820,
                "media_track_name": "Brio",
                "ribbon_config": "Circuit",
                "display_name": f"Route {route_id}",
                "catalog_source": "test",
            }
        ],
        [],
        [
            {
                "source_file": f"Tracks/Brio/trackroutes/route{route_id}.nt",
                "media_track_name": "Brio",
                "locator_collection": f"route{route_id}",
                "locator_name": "start_line_000",
                "locator_kind": "start_line",
                "route_id": route_id,
                "x": 0.0,
                "y": 0.0,
                "z": offset_z,
                "heading_yaw_rad": 0.0,
                "transform_json": "{}",
                "catalog_source": "test",
            },
            {
                "source_file": f"Tracks/Brio/trackroutes/route{route_id}.nt",
                "media_track_name": "Brio",
                "locator_collection": f"route{route_id}",
                "locator_name": "finish_line_000",
                "locator_kind": "finish_line",
                "route_id": route_id,
                "x": 100.0,
                "y": 0.0,
                "z": offset_z,
                "heading_yaw_rad": 0.0,
                "transform_json": "{}",
                "catalog_source": "test",
            },
        ],
    )


def _insert_extra_route_locators(store: TelemetryStore, *, route_id: int, count: int, offset_z: float):
    store.upsert_game_track_locator_records(
        [
            {
                "source_file": f"Tracks/Brio/trackroutes/route{route_id}.nt",
                "media_track_name": "Brio",
                "locator_collection": f"route{route_id}",
                "locator_name": f"Arena_{index:03d}",
                "locator_kind": "arena",
                "route_id": route_id,
                "x": float(index * 25),
                "y": 0.0,
                "z": offset_z,
                "heading_yaw_rad": 0.0,
                "transform_json": "{}",
                "catalog_source": "test",
            }
            for index in range(count)
        ]
    )


def _insert_track_with_route_points(store: TelemetryStore, *, track_key: str, route_id: int, offset_z: float = 0.0):
    store.upsert_track_catalog_records(
        [
            {
                "track_key": track_key,
                "source_dataset_key": route_id,
                "route_id": route_id,
                "media_track_id": 820,
                "media_track_name": "Brio",
                "ribbon_config": "Circuit",
                "display_name": f"Route {route_id}",
                "catalog_source": "test",
            }
        ],
        [],
        [
            {
                "source_file": f"OpenWorld/Brio/AITracks/Route{route_id}.owt",
                "media_track_name": "Brio",
                "locator_collection": f"aitrack_route{route_id}",
                "locator_name": f"route_point_{index:05d}",
                "locator_kind": "route_point",
                "route_id": route_id,
                "x": float(index * 10),
                "y": 0.0,
                "z": offset_z,
                "heading_yaw_rad": None,
                "transform_json": "{}",
                "catalog_source": "test",
            }
            for index in range(11)
        ],
    )


def _insert_lap_points(store: TelemetryStore, session_id: str, lap_id: str, points: list[tuple[float, float]]):
    with store.connect() as con:
        for index, (x, z) in enumerate(points, start=1):
            con.execute(
                """
                INSERT INTO lap_samples(
                    session_id, lap_id, sequence, received_at_ms, game_timestamp_ms,
                    is_race_on, lap_number, current_lap, current_race_time,
                    x, y, z, speed_mps, throttle, brake, steer, gear
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    lap_id,
                    index,
                    index * 16,
                    index * 16,
                    1,
                    1,
                    float(index),
                    float(index),
                    float(x),
                    0.0,
                    float(z),
                    30.0,
                    128,
                    0,
                    0,
                    3,
                ),
            )


def _line_points(offset_z: float = 0.0) -> list[tuple[float, float]]:
    return [(float(index * 10), offset_z) for index in range(11)]


def test_match_samples_to_tracks_scores_direct_route_locator_match(tmp_path: Path):
    store = _store(tmp_path)
    _insert_track_and_locators(store, track_key="track-info:3001", route_id=3001)
    _insert_track_and_locators(store, track_key="track-info:3002", route_id=3002, offset_z=1000.0)

    candidates = match_samples_to_tracks(
        store,
        [{"x": x, "z": z} for x, z in _line_points()],
    )

    assert candidates[0]["track_key"] == "track-info:3001"
    assert candidates[0]["confidence"] >= 0.9
    assert candidates[0]["score_components"]["start_distance_m"] == 0.0
    assert candidates[0]["score_components"]["finish_distance_m"] == 0.0


def test_match_samples_to_tracks_scores_ai_route_points_without_start_finish_locators(tmp_path: Path):
    store = _store(tmp_path)
    _insert_track_with_route_points(store, track_key="track-info:161", route_id=161)
    _insert_track_with_route_points(store, track_key="track-info:162", route_id=162, offset_z=1000.0)

    candidates = match_samples_to_tracks(
        store,
        [{"x": x, "z": z} for x, z in _line_points()],
    )

    assert candidates[0]["track_key"] == "track-info:161"
    assert candidates[0]["confidence"] >= 0.9
    assert candidates[0]["score_components"]["locator_count"] == 11


def test_match_lap_track_auto_assigns_when_confidence_is_high(tmp_path: Path):
    store = _store(tmp_path)
    _insert_track_and_locators(store, track_key="track-info:3001", route_id=3001)
    _insert_track_and_locators(store, track_key="track-info:3002", route_id=3002, offset_z=1000.0)
    session_id = store.create_session("Matcher demo")
    lap_id = store.create_lap(session_id, lap_number=1, boundary_confidence="game_field")
    _insert_lap_points(store, session_id, lap_id, _line_points())

    result = match_lap_track(store, lap_id, auto_assign=True)
    lap = store.lap(lap_id)
    candidates = store.track_match_candidates_for_lap(lap_id, MATCHER_VERSION)

    assert result["assignment"]["assigned"] is True
    assert result["assignment"]["track_key"] == "track-info:3001"
    assert lap["track_profile_id"] == result["assignment"]["track_profile_id"]
    assert store.track_profile(lap["track_profile_id"])["source"] == "fh6_catalog_match"
    assert candidates[0]["track_key"] == "track-info:3001"
    assert candidates[0]["assigned_track_profile_id"] == lap["track_profile_id"]


def test_match_lap_track_does_not_auto_assign_when_margin_is_small(tmp_path: Path):
    store = _store(tmp_path)
    _insert_track_and_locators(store, track_key="track-info:3001", route_id=3001)
    _insert_track_and_locators(store, track_key="track-info:3002", route_id=3002)
    session_id = store.create_session("Ambiguous matcher demo")
    lap_id = store.create_lap(session_id, lap_number=1, boundary_confidence="game_field")
    _insert_lap_points(store, session_id, lap_id, _line_points())

    result = match_lap_track(store, lap_id, auto_assign=True)

    assert result["assignment"]["assigned"] is False
    assert result["assignment"]["reason"] == "confidence_margin_too_small"
    assert store.lap(lap_id)["track_profile_id"] is None


def test_match_lap_track_returns_catalog_profile_ids_for_suggestions(tmp_path: Path):
    store = _store(tmp_path)
    _insert_track_and_locators(store, track_key="track-info:3001", route_id=3001)
    _insert_track_and_locators(store, track_key="track-info:3002", route_id=3002)
    store.ensure_game_track_profiles()
    session_id = store.create_session("Catalog suggestion demo")
    lap_id = store.create_lap(session_id, lap_number=1, boundary_confidence="game_field")
    _insert_lap_points(store, session_id, lap_id, _line_points())

    result = match_lap_track(store, lap_id, auto_assign=True)

    assert result["assignment"]["assigned"] is False
    assert result["assignment"]["reason"] == "confidence_margin_too_small"
    assert all(candidate["track_profile_id"] for candidate in result["candidates"])


def test_match_lap_track_requires_route_locator_coverage_for_auto_assignment(tmp_path: Path):
    store = _store(tmp_path)
    _insert_track_and_locators(store, track_key="track-info:3001", route_id=3001)
    _insert_extra_route_locators(store, route_id=3001, count=8, offset_z=1000.0)
    session_id = store.create_session("Sparse matcher demo")
    lap_id = store.create_lap(session_id, lap_number=1, boundary_confidence="game_field")
    _insert_lap_points(store, session_id, lap_id, _line_points())

    result = match_lap_track(store, lap_id, auto_assign=True)

    assert result["assignment"]["assigned"] is False
    assert result["best_candidate"]["score_components"]["locator_hit_ratio"] < 0.55
    assert store.lap(lap_id)["track_profile_id"] is None


def test_match_lap_track_preserves_existing_manual_assignment(tmp_path: Path):
    store = _store(tmp_path)
    _insert_track_and_locators(store, track_key="track-info:3001", route_id=3001)
    session_id = store.create_session("Manual matcher demo")
    lap_id = store.create_lap(session_id, lap_number=1, boundary_confidence="game_field")
    manual_profile_id = store.create_track_profile("Manual", "Full", "manual", "user")
    store.assign_track_profile(session_id, lap_id, manual_profile_id)
    _insert_lap_points(store, session_id, lap_id, _line_points())

    result = match_lap_track(store, lap_id, auto_assign=True)

    assert result["assignment"]["assigned"] is False
    assert result["assignment"]["reason"] == "existing_track_profile_id"
    assert store.lap(lap_id)["track_profile_id"] == manual_profile_id
    candidates = store.track_match_candidates_for_lap(lap_id, MATCHER_VERSION)
    assert candidates[0]["assigned_track_profile_id"] is None



def test_track_match_api_normalizes_assigned_profile_id_for_suggestions(tmp_path: Path):
    app = create_app(db_path=tmp_path / "telemetry_tracker.sqlite3")
    store = app.state.store
    session_id = store.create_session("Stored candidate demo")
    lap_id = store.create_lap(session_id, lap_number=1, boundary_confidence="game_field")
    profile_id = store.create_track_profile("Emerald Circuit", "Full", "manual", "user")
    with store.connect() as con:
        con.execute(
            """
            INSERT INTO track_match_candidates(
                lap_id, session_id, matcher_version, candidate_rank, candidate_kind,
                track_key, track_profile_id, route_id, display_name, confidence,
                score_components_json, reasons_json, is_auto_assignable,
                assigned_track_profile_id, created_at_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                lap_id,
                session_id,
                MATCHER_VERSION,
                1,
                "catalog",
                None,
                None,
                3001,
                "Emerald Circuit",
                0.95,
                "{}",
                "[]",
                1,
                profile_id,
                1_000,
            ),
        )

    with TestClient(app) as client:
        response = client.get(f"/api/laps/{lap_id}/track-match")

    assert response.status_code == 200
    candidate = response.json()["best_candidate"]
    assert candidate["assigned_track_profile_id"] == profile_id
    assert candidate["track_profile_id"] == profile_id

def test_track_match_api_assigns_and_returns_stored_candidates(tmp_path: Path):
    app = create_app(db_path=tmp_path / "telemetry_tracker.sqlite3")
    store = app.state.store
    _insert_track_and_locators(store, track_key="track-info:3001", route_id=3001)
    _insert_track_and_locators(store, track_key="track-info:3002", route_id=3002, offset_z=1000.0)
    session_id = store.create_session("API matcher demo")
    lap_id = store.create_lap(session_id, lap_number=1, boundary_confidence="game_field")
    _insert_lap_points(store, session_id, lap_id, _line_points())

    with TestClient(app) as client:
        post_response = client.post(f"/api/laps/{lap_id}/track-match")
        get_response = client.get(f"/api/laps/{lap_id}/track-match")

    assert post_response.status_code == 200
    post_payload = post_response.json()
    assert post_payload["assignment"]["assigned"] is True
    assert post_payload["best_candidate"]["track_key"] == "track-info:3001"
    assert get_response.status_code == 200
    get_payload = get_response.json()
    assert get_payload["matcher_version"] == MATCHER_VERSION
    assert get_payload["best_candidate"]["track_key"] == "track-info:3001"
    assert get_payload["best_candidate"]["track_profile_id"] == post_payload["assignment"]["track_profile_id"]
    assert store.lap(lap_id)["track_profile_id"] == post_payload["assignment"]["track_profile_id"]
