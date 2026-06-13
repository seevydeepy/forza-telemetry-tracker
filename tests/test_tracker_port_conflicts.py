import unittest
from unittest.mock import patch
from telemetry_tracker.port_conflicts import PortBinding, ProcessConflict, _host_matches, find_port_conflicts, kill_process_tree

class PortConflictHelperTests(unittest.TestCase):
    def test_host_matching_treats_loopback_names_as_equivalent(self):
        self.assertTrue(_host_matches("127.0.0.1", "localhost"))
        self.assertTrue(_host_matches("localhost", "127.0.0.1"))
        self.assertTrue(_host_matches("0.0.0.0", "127.0.0.1"))
        self.assertFalse(_host_matches("127.0.0.1", "192.168.1.20"))

    def test_find_port_conflicts_maps_rows_to_conflicts(self):
        binding = PortBinding("UDP", "127.0.0.1", 5400, "Forza UDP listener")
        rows = [{"local_address": "127.0.0.1", "pid": 1234, "process_name": "python.exe", "executable_path": "C:/Python/python.exe", "command_line": "python tracker.py"}]
        with patch("telemetry_tracker.port_conflicts._query_windows_port_owners", return_value=rows):
            conflicts = find_port_conflicts([binding], windows_only=False)
        self.assertEqual(conflicts, [ProcessConflict(binding, 1234, "python.exe", "C:/Python/python.exe", "python tracker.py")])

    def test_kill_process_tree_uses_taskkill(self):
        completed = type("Completed", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        with patch("subprocess.run", return_value=completed) as run:
            kill_process_tree(4321)
        run.assert_called_once_with(["taskkill", "/PID", "4321", "/T", "/F"], text=True, capture_output=True)

    def test_kill_process_tree_rejects_invalid_pid(self):
        with self.assertRaisesRegex(RuntimeError, "invalid"):
            kill_process_tree(0)
