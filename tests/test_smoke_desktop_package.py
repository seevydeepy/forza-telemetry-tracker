import importlib.util
import tempfile
import unittest
from pathlib import Path


def _load_smoke_module():
    module_path = Path(__file__).resolve().parents[1] / "tools" / "smoke-desktop-package.py"
    spec = importlib.util.spec_from_file_location("smoke_desktop_package", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SmokeDesktopPackageTests(unittest.TestCase):
    def test_prepare_smoke_user_data_sets_non_default_udp_port(self):
        smoke = _load_smoke_module()

        with tempfile.TemporaryDirectory() as tmp:
            user_data_root = Path(tmp) / "data"
            smoke._prepare_smoke_user_data(user_data_root, 54123)

            from telemetry_tracker.storage import TelemetryStore

            store = TelemetryStore(user_data_root / "telemetry_tracker.sqlite3")
            with store.connect() as con:
                row = con.execute("SELECT udp_host, udp_port FROM user_settings LIMIT 1").fetchone()

        self.assertEqual(dict(row), {"udp_host": "127.0.0.1", "udp_port": 54123})


if __name__ == "__main__":
    unittest.main()
