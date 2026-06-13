import unittest

from telemetry_tracker.packet_bridge import (
    PACKET_SIZE,
    decode_packet,
    encode_packet_for_test,
    iter_packet_bytes,
    packet_to_live_fields,
)


class PacketBridgeTests(unittest.TestCase):
    def test_decode_uses_existing_packet_contract(self):
        raw = encode_packet_for_test(
            {
                "TimestampMS": 1234,
                "PositionX": 10.5,
                "PositionY": 1.25,
                "PositionZ": -3.5,
                "Speed": 44.0,
                "CurrentLap": 12.25,
                "LapNumber": 2,
                "Accel": 255,
                "Brake": 12,
                "Gear": 5,
            }
        )

        self.assertEqual(len(raw), PACKET_SIZE)
        decoded = decode_packet(raw)
        self.assertEqual(decoded["TimestampMS"], 1234)
        self.assertAlmostEqual(decoded["PositionX"], 10.5)
        self.assertAlmostEqual(decoded["PositionY"], 1.25)
        self.assertAlmostEqual(decoded["PositionZ"], -3.5)
        self.assertAlmostEqual(decoded["Speed"], 44.0)
        self.assertAlmostEqual(decoded["CurrentLap"], 12.25)
        self.assertEqual(decoded["LapNumber"], 2)
        self.assertEqual(decoded["Accel"], 255)
        self.assertEqual(decoded["Brake"], 12)
        self.assertEqual(decoded["Gear"], 5)

    def test_packet_to_live_fields_keeps_only_rendering_subset(self):
        raw = encode_packet_for_test(
            {
                "TimestampMS": 2000,
                "PositionX": 2.0,
                "PositionY": 3.0,
                "PositionZ": 4.0,
                "Speed": 30.0,
                "CurrentLap": 5.5,
                "CurrentRaceTime": 9.25,
                "LapNumber": 1,
                "Accel": 128,
                "Brake": 64,
                "Steer": -10,
                "Gear": 3,
                "IsRaceOn": 1,
            }
        )
        live = packet_to_live_fields(decode_packet(raw), sequence=7, received_at_ms=999)

        self.assertEqual(live["sequence"], 7)
        self.assertEqual(live["received_at_ms"], 999)
        self.assertEqual(live["game_timestamp_ms"], 2000)
        self.assertTrue(live["is_race_on"])
        self.assertEqual(live["lap_number"], 1)
        self.assertAlmostEqual(live["current_lap"], 5.5)
        self.assertAlmostEqual(live["current_race_time"], 9.25)
        self.assertAlmostEqual(live["x"], 2.0)
        self.assertAlmostEqual(live["y"], 3.0)
        self.assertAlmostEqual(live["z"], 4.0)
        self.assertAlmostEqual(live["speed_mps"], 30.0)
        self.assertEqual(live["throttle"], 128)
        self.assertEqual(live["brake"], 64)
        self.assertEqual(live["steer"], -10)
        self.assertEqual(live["gear"], 3)

    def test_packet_to_live_fields_includes_dashboard_telemetry(self):
        raw = encode_packet_for_test(
            {
                "TimestampMS": 3000,
                "PositionX": 2.0,
                "PositionY": 3.0,
                "PositionZ": 4.0,
                "Speed": 30.0,
                "CurrentLap": 5.5,
                "CurrentRaceTime": 9.25,
                "LapNumber": 1,
                "Accel": 128,
                "Brake": 64,
                "Steer": -10,
                "Gear": 3,
                "IsRaceOn": 1,
                "AccelerationX": 1.1,
                "AccelerationY": -2.2,
                "AccelerationZ": 3.3,
                "VelocityX": 4.4,
                "VelocityY": 5.5,
                "VelocityZ": 6.6,
                "AngularVelocityX": 0.1,
                "AngularVelocityY": 0.2,
                "AngularVelocityZ": 0.3,
                "Yaw": 0.4,
                "Pitch": -0.5,
                "Roll": 0.6,
                "SmashableVelDiff": 4.5,
                "SmashableMass": 3.25,
                "Power": 310_000.0,
                "Torque": 425.5,
                "Boost": 1.2,
                "EngineIdleRpm": 900.0,
                "Fuel": 0.72,
                "DistanceTraveled": 1234.5,
                "BestLap": 70.1,
                "LastLap": 72.3,
                "RacePosition": 4,
                "Clutch": 7,
                "HandBrake": 9,
                "NormalizedDrivingLine": 12,
                "NormalizedAIBrakeDifference": 34,
                "TireSlipRatioFrontLeft": 0.11,
                "TireSlipRatioFrontRight": 0.12,
                "TireSlipRatioRearLeft": 0.13,
                "TireSlipRatioRearRight": 0.14,
                "TireSlipAngleFrontLeft": -1.1,
                "TireSlipAngleFrontRight": -1.2,
                "TireSlipAngleRearLeft": -1.3,
                "TireSlipAngleRearRight": -1.4,
                "TireCombinedSlipFrontLeft": 0.21,
                "TireCombinedSlipFrontRight": 0.22,
                "TireCombinedSlipRearLeft": 0.23,
                "TireCombinedSlipRearRight": 0.24,
                "WheelRotationSpeedFrontLeft": 31.0,
                "WheelRotationSpeedFrontRight": 32.0,
                "WheelRotationSpeedRearLeft": 33.0,
                "WheelRotationSpeedRearRight": 34.0,
                "WheelOnRumbleStripFrontLeft": 1,
                "WheelOnRumbleStripFrontRight": 0,
                "WheelOnRumbleStripRearLeft": 1,
                "WheelOnRumbleStripRearRight": 0,
                "WheelInPuddleFrontLeft": 1,
                "WheelInPuddleFrontRight": 2,
                "WheelInPuddleRearLeft": 3,
                "WheelInPuddleRearRight": 4,
                "SurfaceRumbleFrontLeft": 0.31,
                "SurfaceRumbleFrontRight": 0.32,
                "SurfaceRumbleRearLeft": 0.33,
                "SurfaceRumbleRearRight": 0.34,
                "SuspensionTravelMetersFrontLeft": 0.41,
                "SuspensionTravelMetersFrontRight": 0.42,
                "SuspensionTravelMetersRearLeft": 0.43,
                "SuspensionTravelMetersRearRight": 0.44,
            }
        )

        live = packet_to_live_fields(decode_packet(raw), sequence=8, received_at_ms=1001)

        expected_values = {
            "acceleration_x": 1.1,
            "acceleration_y": -2.2,
            "acceleration_z": 3.3,
            "velocity_x": 4.4,
            "velocity_y": 5.5,
            "velocity_z": 6.6,
            "angular_velocity_x": 0.1,
            "angular_velocity_y": 0.2,
            "angular_velocity_z": 0.3,
            "yaw": 0.4,
            "pitch": -0.5,
            "roll": 0.6,
            "smashable_vel_diff": 4.5,
            "smashable_mass": 3.25,
            "power_w": 310_000.0,
            "torque_nm": 425.5,
            "boost_bar": 1.2,
            "engine_idle_rpm": 900.0,
            "fuel": 0.72,
            "distance_traveled_m": 1234.5,
            "best_lap": 70.1,
            "last_lap": 72.3,
            "tire_slip_ratio_front_left": 0.11,
            "tire_slip_angle_rear_right": -1.4,
            "tire_combined_slip_front_right": 0.22,
            "wheel_rotation_speed_rear_left": 33.0,
            "surface_rumble_rear_right": 0.34,
            "suspension_travel_meters_front_left": 0.41,
        }
        for field_name, expected_value in expected_values.items():
            with self.subTest(field_name=field_name):
                self.assertAlmostEqual(live[field_name], expected_value, places=5)
        expected_int_values = {
            "race_position": 4,
            "clutch": 7,
            "handbrake": 9,
            "normalized_driving_line": 12,
            "normalized_ai_brake_difference": 34,
            "wheel_on_rumble_strip_front_left": 1,
            "wheel_on_rumble_strip_front_right": 0,
            "wheel_in_puddle_depth_front_right": 2,
        }
        for field_name, expected_value in expected_int_values.items():
            with self.subTest(field_name=field_name):
                self.assertEqual(live[field_name], expected_value)
        self.assertAlmostEqual(live["combined_slip"], 0.24)
        self.assertAlmostEqual(live["rear_combined_slip"], 0.24)

    def test_iter_packet_bytes_rejects_partial_raw_file(self):
        with self.assertRaisesRegex(ValueError, "multiple of 324"):
            list(iter_packet_bytes(b"short"))

    def test_iter_packet_bytes_splits_valid_raw_blob(self):
        first = encode_packet_for_test({"TimestampMS": 1})
        second = encode_packet_for_test({"TimestampMS": 2})

        packets = list(iter_packet_bytes(first + second))

        self.assertEqual(packets, [first, second])


if __name__ == "__main__":
    unittest.main()
