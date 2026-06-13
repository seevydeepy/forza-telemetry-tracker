import unittest

from telemetry_tracker.collision_detection import generate_collision_markers


def make_sample(
    sequence: int,
    *,
    speed: float,
    timestamp_ms: int | None = None,
    smashable_vel_diff: float = 0.0,
    smashable_mass: float = 0.0,
    acceleration_x: float = 0.0,
    acceleration_y: float = 0.0,
    acceleration_z: float = 0.0,
    angular_velocity_z: float = 0.0,
    brake: int = 0,
    is_race_on: bool = True,
) -> dict:
    timestamp = sequence * 100 if timestamp_ms is None else timestamp_ms
    return {
        "sequence": sequence,
        "received_at_ms": timestamp,
        "game_timestamp_ms": timestamp,
        "is_race_on": is_race_on,
        "lap_number": 1,
        "current_lap": timestamp / 1000.0,
        "current_race_time": timestamp / 1000.0,
        "x": float(sequence),
        "y": 0.0,
        "z": float(sequence),
        "speed_mps": speed,
        "throttle": 128,
        "brake": brake,
        "steer": 0,
        "gear": 4,
        "smashable_vel_diff": smashable_vel_diff,
        "smashable_mass": smashable_mass,
        "acceleration_x": acceleration_x,
        "acceleration_y": acceleration_y,
        "acceleration_z": acceleration_z,
        "angular_velocity_z": angular_velocity_z,
    }


def constant_run(count: int, speed: float = 40.0) -> list[dict]:
    return [make_sample(sequence, speed=speed) for sequence in range(1, count + 1)]


class CollisionDetectionTests(unittest.TestCase):
    def test_ignores_smashable_contact_without_meaningful_slowdown(self):
        samples = constant_run(24, speed=40.0)
        samples[10]["smashable_vel_diff"] = 2.0
        samples[10]["smashable_mass"] = 1.5
        samples[11]["speed_mps"] = 38.8
        samples[12]["speed_mps"] = 38.9
        samples[13]["speed_mps"] = 39.2

        markers = generate_collision_markers(samples, ruleset_version=3)

        self.assertEqual(markers, [])

    def test_creates_warning_smashable_marker_for_moderate_time_loss(self):
        samples = constant_run(32, speed=40.0)
        samples[10]["smashable_vel_diff"] = 3.0
        samples[10]["smashable_mass"] = 2.0
        recovery_speeds = ([33.0] * 12) + [35.0, 37.0, 39.0]
        for index, speed in enumerate(recovery_speeds, start=11):
            samples[index - 1]["speed_mps"] = speed
        expected_loss = round(
            sum(max(0.0, 40.0 - speed) * 0.1 for speed in recovery_speeds[1:]) / 40.0,
            3,
        )

        markers = generate_collision_markers(samples, ruleset_version=3)

        self.assertEqual(len(markers), 1)
        marker = markers[0]
        self.assertEqual(marker["metric"], "collision_smashable_time_loss")
        self.assertEqual(marker["issue_kind"], "Smashable collision")
        self.assertEqual(marker["severity"], "warning")
        self.assertAlmostEqual(marker["actual_value"], expected_loss)
        self.assertGreaterEqual(marker["actual_value"], 0.2)
        self.assertLess(marker["actual_value"], 0.6)

    def test_creates_critical_smashable_marker_for_significant_speed_drop(self):
        samples = constant_run(32, speed=40.0)
        samples[10]["smashable_vel_diff"] = 5.5
        samples[10]["smashable_mass"] = 2.5
        recovery_speeds = [28.0, 27.0, 28.5, 30.0, 31.0, 32.0, 33.0, 34.0, 35.0, 36.0, 37.0, 38.0, 39.0, 39.0]
        for index, speed in enumerate(recovery_speeds, start=11):
            samples[index - 1]["speed_mps"] = speed

        markers = generate_collision_markers(samples, ruleset_version=3)

        self.assertEqual(len(markers), 1)
        marker = markers[0]
        self.assertEqual(marker["metric"], "collision_smashable_time_loss")
        self.assertEqual(marker["issue_kind"], "Smashable collision")
        self.assertEqual(marker["severity"], "critical")
        self.assertEqual(marker["ruleset_version"], 3)
        self.assertEqual(marker["threshold_operator"], "gte")
        self.assertEqual(marker["threshold_value"], 0.2)
        self.assertEqual(marker["value_label"], "Estimated time loss")
        self.assertEqual(marker["value_unit"], "s")
        self.assertGreaterEqual(marker["actual_value"], 0.2)
        self.assertGreaterEqual(marker["confidence"], 0.8)
        self.assertEqual(marker["anchor_sequence"], 11)
        self.assertIn("lost", marker["reason"])

    def test_groups_adjacent_smashable_packets_into_one_marker(self):
        samples = constant_run(32, speed=42.0)
        samples[10]["smashable_vel_diff"] = 2.0
        samples[10]["smashable_mass"] = 1.5
        samples[11]["smashable_vel_diff"] = 6.0
        samples[11]["smashable_mass"] = 1.5
        recovery_speeds = [29.0, 28.0, 29.5, 31.0, 32.0, 33.0, 34.0, 35.0, 36.0, 37.0, 38.0, 39.0, 40.0]
        for index, speed in enumerate(recovery_speeds, start=12):
            samples[index - 1]["speed_mps"] = speed

        markers = generate_collision_markers(samples, ruleset_version=3)

        self.assertEqual(len(markers), 1)
        marker = markers[0]
        self.assertEqual(marker["start_sequence"], 11)
        self.assertEqual(marker["end_sequence"], 12)
        self.assertEqual(marker["anchor_sequence"], 12)

    def test_creates_inferred_solid_marker_for_abrupt_loss_without_smashable_signal(self):
        samples = constant_run(36, speed=45.0)
        recovery_speeds = [36.0] * 14 + [38.0, 40.0, 43.0, 45.0]
        for index, speed in enumerate(recovery_speeds, start=11):
            samples[index - 1]["speed_mps"] = speed
        samples[10]["acceleration_x"] = -28.0
        samples[10]["angular_velocity_z"] = 2.4

        markers = generate_collision_markers(samples, ruleset_version=4)

        self.assertEqual(len(markers), 1)
        marker = markers[0]
        self.assertEqual(marker["metric"], "collision_solid_inferred_time_loss")
        self.assertEqual(marker["issue_kind"], "Solid impact (inferred)")
        self.assertEqual(marker["severity"], "warning")
        self.assertEqual(marker["threshold_value"], 0.25)
        self.assertEqual(marker["threshold_operator"], "gte")
        self.assertEqual(marker["value_unit"], "s")
        self.assertGreaterEqual(marker["actual_value"], 0.25)
        self.assertGreaterEqual(marker["confidence"], 0.7)
        self.assertEqual(marker["anchor_sequence"], 11)
        self.assertIn("inferred", marker["reason"].lower())

    def test_hard_braking_without_angular_disruption_does_not_create_solid_marker(self):
        samples = constant_run(36, speed=45.0)
        recovery_speeds = [36.0] * 14 + [38.0, 40.0, 43.0, 45.0]
        for index, speed in enumerate(recovery_speeds, start=11):
            samples[index - 1]["speed_mps"] = speed
        for index in range(9, 13):
            samples[index - 1]["brake"] = 220
        samples[10]["acceleration_x"] = -30.0

        markers = generate_collision_markers(samples, ruleset_version=4)

        self.assertEqual(markers, [])

    def test_nearby_smashable_signal_suppresses_duplicate_inferred_solid_marker(self):
        samples = constant_run(36, speed=45.0)
        recovery_speeds = [36.0] * 14 + [38.0, 40.0, 43.0, 45.0]
        for index, speed in enumerate(recovery_speeds, start=11):
            samples[index - 1]["speed_mps"] = speed
        samples[10]["acceleration_x"] = -28.0
        samples[10]["angular_velocity_z"] = 2.4
        samples[10]["smashable_vel_diff"] = 4.0
        samples[10]["smashable_mass"] = 2.0

        markers = generate_collision_markers(samples, ruleset_version=4)

        self.assertEqual(len(markers), 1)
        self.assertEqual(markers[0]["metric"], "collision_smashable_time_loss")

    def test_infers_solid_marker_from_abrupt_loss_over_16ms_packets(self):
        samples = [
            make_sample(sequence, speed=45.0, timestamp_ms=sequence * 16)
            for sequence in range(1, 130)
        ]
        transition_speeds = {
            21: 43.0,
            22: 40.0,
            23: 38.0,
        }
        for sequence, speed in transition_speeds.items():
            samples[sequence - 1]["speed_mps"] = speed
        for sequence in range(24, 110):
            samples[sequence - 1]["speed_mps"] = 36.0
        samples[23]["acceleration_x"] = -28.0
        samples[23]["angular_velocity_z"] = 2.4

        markers = generate_collision_markers(samples, ruleset_version=4)

        self.assertEqual(len(markers), 1)
        marker = markers[0]
        self.assertEqual(marker["metric"], "collision_solid_inferred_time_loss")
        self.assertEqual(marker["issue_kind"], "Solid impact (inferred)")
        self.assertEqual(marker["severity"], "warning")
        self.assertEqual(marker["anchor_sequence"], 24)
        self.assertGreaterEqual(marker["actual_value"], 0.25)

    def test_minor_smashable_candidate_does_not_suppress_inferred_solid_marker(self):
        samples = constant_run(36, speed=45.0)
        recovery_speeds = [36.0] * 14 + [38.0, 40.0, 43.0, 45.0]
        for index, speed in enumerate(recovery_speeds, start=11):
            samples[index - 1]["speed_mps"] = speed
        samples[10]["acceleration_x"] = -28.0
        samples[10]["angular_velocity_z"] = 2.4
        samples[10]["smashable_vel_diff"] = 0.6

        markers = generate_collision_markers(samples, ruleset_version=4)

        self.assertEqual(len(markers), 1)
        self.assertEqual(markers[0]["metric"], "collision_solid_inferred_time_loss")


if __name__ == "__main__":
    unittest.main()
