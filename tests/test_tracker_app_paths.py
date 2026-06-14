import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import telemetry_tracker.app_paths as _app_paths_module
from telemetry_tracker.app_paths import (
    ENV_RESOURCE_ROOT,
    ENV_USER_DATA_ROOT,
    DesktopPaths,
    car_catalog_supplements_path,
    default_desktop_paths,
    frontend_dist_path,
    map_converter_path,
    resource_root,
    user_data_root,
)

class AppPathTests(unittest.TestCase):
    def test_resource_root_uses_environment_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "resources"
            with patch.dict(os.environ, {ENV_RESOURCE_ROOT: str(root)}, clear=False):
                self.assertEqual(resource_root(), root)

    def test_resource_root_uses_pyinstaller_meipass_when_frozen(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "_MEI12345"
            # Exclude ENV_RESOURCE_ROOT so an outer-environment override cannot shadow _MEIPASS.
            env_without_override = {k: v for k, v in os.environ.items() if k != ENV_RESOURCE_ROOT}
            with patch.dict(os.environ, env_without_override, clear=True), \
                 patch.object(sys, "frozen", True, create=True), \
                 patch.object(sys, "_MEIPASS", str(root), create=True):
                self.assertEqual(resource_root(), root)

    def test_resource_root_dev_fallback(self):
        # When not frozen and no env override, resource_root() must equal the repo root
        # (parents[1] relative to app_paths.py, which lives one level below the repo root).
        expected = Path(_app_paths_module.__file__).resolve().parents[1]
        env_without_override = {k: v for k, v in os.environ.items() if k != ENV_RESOURCE_ROOT}
        with patch.dict(os.environ, env_without_override, clear=True), \
             patch.object(sys, "frozen", False, create=True):
            self.assertEqual(resource_root(), expected)

    def test_user_data_root_non_windows_fallback(self):
        # When both the env override and LOCALAPPDATA are absent, falls back to ~/.local/share/...
        with tempfile.TemporaryDirectory() as tmp:
            fake_home = Path(tmp) / "home"
            env_without_data_vars = {
                k: v for k, v in os.environ.items()
                if k not in (ENV_USER_DATA_ROOT, "LOCALAPPDATA")
            }
            with patch.dict(os.environ, env_without_data_vars, clear=True), \
                 patch.object(Path, "home", staticmethod(lambda: fake_home)):
                expected = fake_home / ".local" / "share" / "Forza Telemetry Tracker"
                self.assertEqual(user_data_root(), expected)

    def test_user_data_root_uses_localappdata(self):
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp) / "LocalAppData"
            with patch.dict(os.environ, {"LOCALAPPDATA": str(local)}, clear=True):
                self.assertEqual(user_data_root(), local / "Forza Telemetry Tracker")

    def test_user_data_root_uses_environment_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            with patch.dict(os.environ, {ENV_USER_DATA_ROOT: str(data)}, clear=False):
                self.assertEqual(user_data_root(), data)

    def test_frontend_dist_prefers_bundled_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundled = root / "frontend-dist"
            bundled.mkdir()
            self.assertEqual(frontend_dist_path(root), bundled)

    def test_car_catalog_supplements_prefers_bundled_resource(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundled = root / "resources" / "car_catalog_supplements.json"
            bundled.parent.mkdir(parents=True)
            bundled.write_text('{"cars": []}', encoding="utf-8")
            self.assertEqual(car_catalog_supplements_path(root), bundled)

    def test_map_converter_prefers_bundled_side_binary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            converter = root / "bin" / "map-converter" / "forza-map-tile-converter.exe"
            converter.parent.mkdir(parents=True)
            converter.write_text("fake", encoding="utf-8")
            self.assertEqual(map_converter_path(root), converter)

    def test_default_desktop_paths_has_expected_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "resources"
            data = Path(tmp) / "data"
            paths = default_desktop_paths(resource_base=root, user_data_base=data)
            self.assertIsInstance(paths, DesktopPaths)
            self.assertEqual(paths.database, data / "telemetry_tracker.sqlite3")
            self.assertEqual(paths.logs_dir, data / "logs")
            self.assertEqual(paths.map_cache_dir, data / "map-cache")
            self.assertEqual(paths.imports_dir, data / "imports")
            self.assertEqual(paths.backups_dir, data / "backups")
            self.assertEqual(paths.exports_dir, data / "exports")
            self.assertEqual(paths.release_metadata, root / "release-metadata.json")
            self.assertEqual(paths.frontend_dist, root / "web" / "telemetry-tracker" / "dist")
            self.assertEqual(
                paths.car_catalog_supplements,
                root / "telemetry_tracker" / "resources" / "car_catalog_supplements.json",
            )

    def test_default_desktop_paths_uses_bundled_car_catalog_supplements(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "resources"
            data = Path(tmp) / "data"
            bundled = root / "resources" / "car_catalog_supplements.json"
            bundled.parent.mkdir(parents=True)
            bundled.write_text('{"cars": []}', encoding="utf-8")
            paths = default_desktop_paths(resource_base=root, user_data_base=data)
            self.assertEqual(paths.car_catalog_supplements, bundled)

    def test_ensure_user_directories_creates_only_mutable_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            resources = Path(tmp) / "resources"
            data = Path(tmp) / "data"
            paths = default_desktop_paths(resource_base=resources, user_data_base=data)
            paths.ensure_user_directories()
            self.assertTrue(paths.logs_dir.is_dir())
            self.assertTrue(paths.map_cache_dir.is_dir())
            self.assertTrue(paths.imports_dir.is_dir())
            self.assertTrue(paths.backups_dir.is_dir())
            self.assertTrue(paths.exports_dir.is_dir())
            self.assertFalse(resources.exists())

    def test_default_desktop_paths_exports_dir_respects_user_data_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            resources = Path(tmp) / "resources"
            data = Path(tmp) / "custom-data-root"
            paths = default_desktop_paths(resource_base=resources, user_data_base=data)
            self.assertEqual(paths.exports_dir, data / "exports")

if __name__ == "__main__":
    unittest.main()
