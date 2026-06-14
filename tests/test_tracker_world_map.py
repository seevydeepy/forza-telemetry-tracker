import base64
import json
import os
import tempfile
import textwrap
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from telemetry_tracker.app import create_app
from telemetry_tracker.storage import TelemetryStore
from telemetry_tracker.world_map import (
    DEFAULT_WORLD_ORIGIN_X,
    DEFAULT_WORLD_ORIGIN_Z,
    DEFAULT_WORLD_SIZE,
    TILE_COORDINATE_SYSTEM,
    build_world_map_cache,
    load_map_calibration,
    parse_tile_entry_name,
    resolve_media_root,
    safe_cache_tile_path,
    season_source_zip,
    tile_world_bounds,
)


PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADElEQVR42mP8z8AARQAFAAH/"
    "Af8AftsJAAAAAElFTkSuQmCC"
)


def _make_media_root(root: Path, *, include_ui_zip: bool = False) -> Path:
    media_root = root / "media"
    data_bound = media_root / "UI" / "Textures" / "Data_Bound"
    data_bound.mkdir(parents=True)
    with zipfile.ZipFile(data_bound / "Map_Brio_Summer.zip", "w") as archive:
        archive.writestr("0-0-0.swatchbin", b"fake tile")
    if include_ui_zip:
        with zipfile.ZipFile(data_bound / "UI.zip", "w") as archive:
            archive.writestr(
                "MapIncludeSharedResources.xml",
                """
                <root background_size="22035">
                  <background_offset x="-12548" z="-11281" />
                </root>
                """,
            )
    return media_root


def _make_fake_converter(root: Path) -> Path:
    converter = root / "fake_converter.py"
    png_literal = base64.b64encode(PNG_BYTES).decode("ascii")
    converter.write_text(
        textwrap.dedent(
            f"""
            import base64
            import json
            import sys
            from pathlib import Path

            def value_after(name):
                return sys.argv[sys.argv.index(name) + 1]

            command = sys.argv[1]
            if command == "inspect-zip":
                print(json.dumps({{
                    "entries": [{{
                        "entry": "0-0-0.swatchbin",
                        "z": 0,
                        "x": 0,
                        "y": 0,
                        "dxgiFormat": 71,
                        "width": 1024,
                        "height": 1024,
                        "isDurango": False,
                    }}]
                }}))
                raise SystemExit(0)
            if command == "convert-zip":
                output = Path(value_after("--output"))
                manifest_path = Path(value_after("--manifest"))
                tile_path = output / "0" / "0" / "0.png"
                tile_path.parent.mkdir(parents=True, exist_ok=True)
                tile_path.write_bytes(base64.b64decode("{png_literal}"))
                manifest_path.write_text(json.dumps({{
                    "game": "fh6",
                    "map": "brio",
                    "season": "summer",
                    "format": "png",
                    "tileSize": 1024,
                    "minZoom": 0,
                    "maxZoom": 0,
                    "tiles": [{{"z": 0, "x": 0, "y": 0, "path": "0/0/0.png"}}],
                }}), encoding="utf-8")
                raise SystemExit(0)
            print(f"unknown command: {{command}}", file=sys.stderr)
            raise SystemExit(2)
            """
        ),
        encoding="utf-8",
    )
    return converter


class WorldMapHelperTests(unittest.TestCase):
    def test_season_source_zip_returns_canonical_source_archive(self):
        install_root = Path("G:/FH6")

        self.assertEqual(
            season_source_zip(install_root, "summer"),
            install_root / "media" / "UI" / "Textures" / "Data_Bound" / "Map_Brio_Summer.zip",
        )

    def test_season_source_zip_rejects_unknown_season(self):
        with self.assertRaisesRegex(ValueError, "season"):
            season_source_zip(Path("G:/FH6"), "monsoon")

    def test_resolve_media_root_rejects_direct_media_folder(self):
        for direct_media_root in (Path("G:/FH6/media"), Path("G:/FH6/Media"), Path("G:/FH6/media/")):
            with self.subTest(direct_media_root=direct_media_root):
                with self.assertRaisesRegex(ValueError, "top-level FH6 install folder"):
                    resolve_media_root(direct_media_root)

    def test_load_map_calibration_reads_values_from_ui_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            media_root = _make_media_root(Path(tmp), include_ui_zip=True)

            calibration = load_map_calibration(media_root.parent)

        self.assertEqual(calibration["world_origin_x"], -12548.0)
        self.assertEqual(calibration["world_origin_z"], -11281.0)
        self.assertEqual(calibration["world_size"], 22035.0)

    def test_load_map_calibration_falls_back_to_canonical_constants_without_ui_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            media_root = _make_media_root(Path(tmp), include_ui_zip=False)

            calibration = load_map_calibration(media_root.parent)

        self.assertEqual(calibration["world_origin_x"], DEFAULT_WORLD_ORIGIN_X)
        self.assertEqual(calibration["world_origin_z"], DEFAULT_WORLD_ORIGIN_Z)
        self.assertEqual(calibration["world_size"], DEFAULT_WORLD_SIZE)

    def test_tile_world_bounds_center_is_inside_world_extent(self):
        calibration = load_map_calibration(Path("missing"))

        bounds = tile_world_bounds(z=3, x=4, y=4, calibration=calibration)
        center_x = (bounds["west"] + bounds["east"]) / 2
        center_z = (bounds["north"] + bounds["south"]) / 2

        self.assertGreater(center_x, DEFAULT_WORLD_ORIGIN_X)
        self.assertLess(center_x, DEFAULT_WORLD_ORIGIN_X + DEFAULT_WORLD_SIZE)
        self.assertGreater(center_z, DEFAULT_WORLD_ORIGIN_Z)
        self.assertLess(center_z, DEFAULT_WORLD_ORIGIN_Z + DEFAULT_WORLD_SIZE)

    def test_parse_tile_entry_name_accepts_canonical_names_and_rejects_invalid_names(self):
        self.assertEqual(parse_tile_entry_name("3-2-5.swatchbin"), (3, 5, 2))
        self.assertEqual(parse_tile_entry_name("3-4-4.swatchbin"), (3, 4, 4))
        with self.assertRaisesRegex(ValueError, "invalid"):
            parse_tile_entry_name("3/4/4.png")

    def test_zoom_zero_bounds_use_top_left_origin_and_invert_vertical_axis(self):
        calibration = load_map_calibration(Path("missing"))

        bounds = tile_world_bounds(z=0, x=0, y=0, calibration=calibration)

        self.assertEqual(bounds["west"], DEFAULT_WORLD_ORIGIN_X)
        self.assertEqual(bounds["east"], DEFAULT_WORLD_ORIGIN_X + DEFAULT_WORLD_SIZE)
        self.assertEqual(bounds["south"], DEFAULT_WORLD_ORIGIN_Z)
        self.assertEqual(bounds["north"], DEFAULT_WORLD_ORIGIN_Z + DEFAULT_WORLD_SIZE)
        self.assertGreater(bounds["north"], bounds["south"])

    def test_safe_cache_tile_path_rejects_invalid_coordinates(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_root = Path(tmp) / "cache"

            self.assertEqual(
                safe_cache_tile_path(cache_root, z=3, x=4, y=4),
                cache_root.resolve() / "3" / "4" / "4.png",
            )
            with self.assertRaisesRegex(ValueError, "non-negative integer"):
                safe_cache_tile_path(cache_root, z=0, x=0, y="../secret")

    def test_build_world_map_cache_uses_fake_converter_and_persists_ready_tile_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            media_root = _make_media_root(root)
            converter = _make_fake_converter(root)
            store = TelemetryStore(root / "telemetry_tracker.sqlite3")
            store.migrate()

            status = build_world_map_cache(
                store=store,
                media_root=media_root.parent,
                season="summer",
                converter_path=converter,
            )
            tile_set = store.world_map_tile_set("fh6-brio-summer")

        self.assertEqual(status["status"], "ready")
        self.assertIsNotNone(tile_set)
        self.assertEqual(tile_set["status"], "ready")
        self.assertEqual(tile_set["manifest"]["worldOriginX"], DEFAULT_WORLD_ORIGIN_X)
        self.assertEqual(tile_set["manifest"]["tileCoordinateSystem"], TILE_COORDINATE_SYSTEM)
        self.assertEqual(tile_set["manifest"]["tiles"][0]["path"], "0/0/0.png")

    def test_build_world_map_cache_rejects_direct_media_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            media_root = _make_media_root(root)
            converter = _make_fake_converter(root)
            store = TelemetryStore(root / "telemetry_tracker.sqlite3")
            store.migrate()

            status = build_world_map_cache(
                store=store,
                media_root=media_root,
                season="summer",
                converter_path=converter,
            )

        self.assertEqual(status["status"], "source_missing")
        self.assertIn("top-level FH6 install folder", status["error_message"])


class WorldMapApiTests(unittest.TestCase):
    def test_map_settings_build_status_and_tile_endpoints(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            media_root = _make_media_root(root)
            converter = _make_fake_converter(root)
            app = create_app(db_path=root / "telemetry_tracker.sqlite3")

            with patch.dict(
                os.environ,
                {"FH6_MAP_TILE_CONVERTER": str(converter)},
                clear=False,
            ):
                with TestClient(app) as client:
                    settings = client.patch(
                        "/api/map/settings",
                        json={
                            "fh6_media_root": str(media_root.parent),
                            "world_map_enabled": True,
                            "world_map_season": "summer",
                        },
                    )
                    build = client.post("/api/map/cache/build", json={})
                    status = client.get("/api/map/status")
                    tile_set_id = status.json()["tile_set"]["id"]
                    tile = client.get(f"/api/map/tiles/{tile_set_id}/0/0/0.png")

            self.assertEqual(settings.status_code, 200)
            self.assertTrue(settings.json()["settings"]["world_map_enabled"])
            self.assertEqual(build.status_code, 200)
            self.assertEqual(build.json()["status"], "ready")
            self.assertEqual(status.status_code, 200)
            self.assertEqual(status.json()["tile_set"]["status"], "ready")
            self.assertIn(
                "/api/map/tiles/fh6-brio-summer/{z}/{x}/{y}.png",
                status.json()["tile_set"]["tile_url_template"],
            )
            self.assertEqual(tile.status_code, 200)
            self.assertTrue(tile.headers["content-type"].startswith("image/png"))
            self.assertEqual(tile.content, PNG_BYTES)

    def test_status_reports_stale_tile_set_when_manifest_uses_old_coordinate_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(
                db_path=root / "telemetry_tracker.sqlite3",
                start_udp_listener=False,
            )
            media_root = _make_media_root(root)
            cache_dir = root / "cache"
            tile_path = cache_dir / "0" / "0" / "0.png"
            tile_path.parent.mkdir(parents=True)
            tile_path.write_bytes(PNG_BYTES)
            app.state.store.update_world_map_settings(
                media_root=str(media_root.parent),
                enabled=True,
                season="summer",
            )
            app.state.store.upsert_world_map_tile_set(
                {
                    "id": "fh6-brio-summer",
                    "game": "fh6",
                    "map_name": "brio",
                    "season": "summer",
                    "source_zip_path": str(root / "Map_Brio_Summer.zip"),
                    "source_zip_mtime_ms": 1,
                    "source_zip_size_bytes": 1,
                    "cache_dir": str(cache_dir),
                    "tile_format": "png",
                    "tile_size": 1024,
                    "min_zoom": 0,
                    "max_zoom": 0,
                    "world_origin_x": DEFAULT_WORLD_ORIGIN_X,
                    "world_origin_z": DEFAULT_WORLD_ORIGIN_Z,
                    "world_size": DEFAULT_WORLD_SIZE,
                    "status": "ready",
                    "manifest_json": json.dumps({"tileSize": 1024, "tiles": []}),
                    "error_message": None,
                }
            )

            with TestClient(app) as client:
                response = client.get("/api/map/status")
                tile_response = client.get("/api/map/tiles/fh6-brio-summer/0/0/0.png")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "cache_stale")
        self.assertIsNone(response.json()["tile_set"])
        self.assertEqual(tile_response.status_code, 404)

    def test_tile_endpoint_rejects_non_ready_tile_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache_dir = root / "cache"
            tile_path = cache_dir / "0" / "0" / "0.png"
            tile_path.parent.mkdir(parents=True)
            tile_path.write_bytes(PNG_BYTES)
            app = create_app(
                db_path=root / "telemetry_tracker.sqlite3",
                start_udp_listener=False,
            )
            app.state.store.upsert_world_map_tile_set(
                {
                    "id": "fh6-brio-summer",
                    "game": "fh6",
                    "map_name": "brio",
                    "season": "summer",
                    "source_zip_path": str(root / "Map_Brio_Summer.zip"),
                    "source_zip_mtime_ms": 1,
                    "source_zip_size_bytes": 1,
                    "cache_dir": str(cache_dir),
                    "tile_format": "png",
                    "tile_size": 1024,
                    "min_zoom": 0,
                    "max_zoom": 0,
                    "world_origin_x": DEFAULT_WORLD_ORIGIN_X,
                    "world_origin_z": DEFAULT_WORLD_ORIGIN_Z,
                    "world_size": DEFAULT_WORLD_SIZE,
                    "status": "error",
                    "manifest_json": json.dumps({"tileSize": 1024, "tiles": []}),
                    "error_message": "conversion failed",
                }
            )

            with TestClient(app) as client:
                response = client.get("/api/map/tiles/fh6-brio-summer/0/0/0.png")

        self.assertEqual(response.status_code, 404)

    def test_map_status_uses_explicit_converter_path(self):
        from telemetry_tracker.world_map import world_map_status_payload
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = TelemetryStore(root / "telemetry_tracker.sqlite3")
            store.migrate()
            converter = _make_fake_converter(root)
            status = world_map_status_payload(store, converter_path=converter)
        self.assertTrue(status["converter"]["available"])
        self.assertEqual(status["converter"]["path"], str(converter))

    def test_map_status_reports_explicit_missing_converter_path(self):
        from telemetry_tracker.world_map import world_map_status_payload
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = TelemetryStore(root / "telemetry_tracker.sqlite3")
            store.migrate()
            converter = root / "missing-converter.exe"
            status = world_map_status_payload(store, converter_path=converter)
        self.assertFalse(status["converter"]["available"])
        self.assertEqual(status["converter"]["path"], str(converter))

    def test_app_map_cache_build_uses_runtime_converter_and_cache_root(self):
        from telemetry_tracker.app_paths import default_desktop_paths
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            media_root = _make_media_root(root)
            converter = _make_fake_converter(root)
            resources = root / "resources"
            bundled = resources / "bin" / "map-converter" / "forza-map-tile-converter.exe"
            bundled.parent.mkdir(parents=True)
            bundled.write_text(converter.read_text(encoding="utf-8"), encoding="utf-8")
            paths = default_desktop_paths(resource_base=resources, user_data_base=root / "data")
            app = create_app(runtime_paths=paths)
            with TestClient(app) as client:
                client.patch("/api/map/settings", json={"fh6_media_root": str(media_root.parent), "world_map_enabled": True, "world_map_season": "summer"})
                response = client.post("/api/map/cache/build", json={"season": "summer"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["status"], "ready")
            self.assertTrue((paths.map_cache_dir / "fh6" / "brio" / "summer" / "0" / "0" / "0.png").exists())


if __name__ == "__main__":
    unittest.main()
