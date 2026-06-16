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
    def test_read_windows_pe_subsystem_reads_gui_subsystem(self):
        smoke = _load_smoke_module()

        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "ForzaTelemetryTracker.exe"
            data = bytearray(512)
            data[0:2] = b"MZ"
            data[0x3C:0x40] = (0x80).to_bytes(4, "little")
            data[0x80:0x84] = b"PE\0\0"
            data[0x80 + 24:0x80 + 26] = (0x20B).to_bytes(2, "little")
            data[0x80 + 24 + 68:0x80 + 24 + 70] = smoke.WINDOWS_SUBSYSTEM_WINDOWS_GUI.to_bytes(2, "little")
            exe.write_bytes(data)

            subsystem = smoke.read_windows_pe_subsystem(exe)

        self.assertEqual(subsystem, smoke.WINDOWS_SUBSYSTEM_WINDOWS_GUI)

    def test_read_windows_pe_subsystem_reads_pe32_gui_subsystem(self):
        smoke = _load_smoke_module()

        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "ForzaTelemetryTracker.exe"
            data = bytearray(512)
            data[0:2] = b"MZ"
            data[0x3C:0x40] = (0x80).to_bytes(4, "little")
            data[0x80:0x84] = b"PE\0\0"
            data[0x80 + 24:0x80 + 26] = (0x10B).to_bytes(2, "little")
            data[0x80 + 24 + 68:0x80 + 24 + 70] = smoke.WINDOWS_SUBSYSTEM_WINDOWS_GUI.to_bytes(2, "little")
            exe.write_bytes(data)

            subsystem = smoke.read_windows_pe_subsystem(exe)

        self.assertEqual(subsystem, smoke.WINDOWS_SUBSYSTEM_WINDOWS_GUI)

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
