"""Adapter around the tracker FH6 Data Out parser."""

from __future__ import annotations

from typing import Iterator

from telemetry_tracker import data_out

PACKET_SIZE = data_out.PACKET_SIZE
FIELD_NAMES = tuple(data_out.FIELD_NAMES)
_OPTIONAL_FLOAT_FIELD_MAP = {
    "tire_temp_front_left": "TireTempFrontLeft",
    "tire_temp_front_right": "TireTempFrontRight",
    "tire_temp_rear_left": "TireTempRearLeft",
    "tire_temp_rear_right": "TireTempRearRight",
    "suspension_travel_front_left": "NormalizedSuspensionTravelFrontLeft",
    "suspension_travel_front_right": "NormalizedSuspensionTravelFrontRight",
    "suspension_travel_rear_left": "NormalizedSuspensionTravelRearLeft",
    "suspension_travel_rear_right": "NormalizedSuspensionTravelRearRight",
    "current_rpm": "CurrentEngineRpm",
    "engine_max_rpm": "EngineMaxRpm",
    "acceleration_x": "AccelerationX",
    "acceleration_y": "AccelerationY",
    "acceleration_z": "AccelerationZ",
    "velocity_x": "VelocityX",
    "velocity_y": "VelocityY",
    "velocity_z": "VelocityZ",
    "angular_velocity_x": "AngularVelocityX",
    "angular_velocity_y": "AngularVelocityY",
    "angular_velocity_z": "AngularVelocityZ",
    "yaw": "Yaw",
    "pitch": "Pitch",
    "roll": "Roll",
    "smashable_vel_diff": "SmashableVelDiff",
    "smashable_mass": "SmashableMass",
    "power_w": "Power",
    "torque_nm": "Torque",
    "boost_bar": "Boost",
    "engine_idle_rpm": "EngineIdleRpm",
    "fuel": "Fuel",
    "distance_traveled_m": "DistanceTraveled",
    "best_lap": "BestLap",
    "last_lap": "LastLap",
    "tire_slip_ratio_front_left": "TireSlipRatioFrontLeft",
    "tire_slip_ratio_front_right": "TireSlipRatioFrontRight",
    "tire_slip_ratio_rear_left": "TireSlipRatioRearLeft",
    "tire_slip_ratio_rear_right": "TireSlipRatioRearRight",
    "tire_slip_angle_front_left": "TireSlipAngleFrontLeft",
    "tire_slip_angle_front_right": "TireSlipAngleFrontRight",
    "tire_slip_angle_rear_left": "TireSlipAngleRearLeft",
    "tire_slip_angle_rear_right": "TireSlipAngleRearRight",
    "tire_combined_slip_front_left": "TireCombinedSlipFrontLeft",
    "tire_combined_slip_front_right": "TireCombinedSlipFrontRight",
    "tire_combined_slip_rear_left": "TireCombinedSlipRearLeft",
    "tire_combined_slip_rear_right": "TireCombinedSlipRearRight",
    "wheel_rotation_speed_front_left": "WheelRotationSpeedFrontLeft",
    "wheel_rotation_speed_front_right": "WheelRotationSpeedFrontRight",
    "wheel_rotation_speed_rear_left": "WheelRotationSpeedRearLeft",
    "wheel_rotation_speed_rear_right": "WheelRotationSpeedRearRight",
    "surface_rumble_front_left": "SurfaceRumbleFrontLeft",
    "surface_rumble_front_right": "SurfaceRumbleFrontRight",
    "surface_rumble_rear_left": "SurfaceRumbleRearLeft",
    "surface_rumble_rear_right": "SurfaceRumbleRearRight",
    "suspension_travel_meters_front_left": "SuspensionTravelMetersFrontLeft",
    "suspension_travel_meters_front_right": "SuspensionTravelMetersFrontRight",
    "suspension_travel_meters_rear_left": "SuspensionTravelMetersRearLeft",
    "suspension_travel_meters_rear_right": "SuspensionTravelMetersRearRight",
}
_OPTIONAL_INT_FIELD_MAP = {
    "race_position": "RacePosition",
    "clutch": "Clutch",
    "handbrake": "HandBrake",
    "normalized_driving_line": "NormalizedDrivingLine",
    "normalized_ai_brake_difference": "NormalizedAIBrakeDifference",
    "wheel_on_rumble_strip_front_left": "WheelOnRumbleStripFrontLeft",
    "wheel_on_rumble_strip_front_right": "WheelOnRumbleStripFrontRight",
    "wheel_on_rumble_strip_rear_left": "WheelOnRumbleStripRearLeft",
    "wheel_on_rumble_strip_rear_right": "WheelOnRumbleStripRearRight",
    "wheel_in_puddle_depth_front_left": "WheelInPuddleFrontLeft",
    "wheel_in_puddle_depth_front_right": "WheelInPuddleFrontRight",
    "wheel_in_puddle_depth_rear_left": "WheelInPuddleRearLeft",
    "wheel_in_puddle_depth_rear_right": "WheelInPuddleRearRight",
}
OPTIONAL_LIVE_FIELDS = (
    "combined_slip",
    "rear_combined_slip",
    *_OPTIONAL_FLOAT_FIELD_MAP.keys(),
    *_OPTIONAL_INT_FIELD_MAP.keys(),
)


def decode_packet(raw: bytes) -> dict:
    """Decode one supported FH Data Out packet."""

    return data_out.decode_packet(raw)


def encode_packet_for_test(values: dict | None = None) -> bytes:
    """Build one synthetic packet using the existing test encoder."""

    return data_out.encode_packet_for_test(values)


def iter_packet_bytes(raw: bytes) -> Iterator[bytes]:
    """Yield fixed-size packet bytes from an in-memory raw capture blob."""

    if len(raw) % PACKET_SIZE != 0:
        raise ValueError(f"raw telemetry bytes must be a multiple of {PACKET_SIZE}")
    for offset in range(0, len(raw), PACKET_SIZE):
        yield raw[offset : offset + PACKET_SIZE]


def _optional_float(packet: dict, field_name: str) -> float | None:
    value = packet.get(field_name)
    if value is None:
        return None
    return float(value)


def _optional_int(packet: dict, field_name: str) -> int | None:
    value = packet.get(field_name)
    if value is None:
        return None
    return int(value)


def _max_abs_optional(values: list[float | None]) -> float | None:
    present = [abs(value) for value in values if value is not None]
    if not present:
        return None
    return max(present)


def packet_to_live_fields(packet: dict, sequence: int, received_at_ms: int) -> dict:
    """Reduce a decoded packet to the fields needed by the tracker UI."""

    combined_slip = _max_abs_optional(
        [
            _optional_float(packet, "TireCombinedSlipFrontLeft"),
            _optional_float(packet, "TireCombinedSlipFrontRight"),
            _optional_float(packet, "TireCombinedSlipRearLeft"),
            _optional_float(packet, "TireCombinedSlipRearRight"),
        ]
    )
    rear_combined_slip = _max_abs_optional(
        [
            _optional_float(packet, "TireCombinedSlipRearLeft"),
            _optional_float(packet, "TireCombinedSlipRearRight"),
        ]
    )
    live_fields = {
        "sequence": int(sequence),
        "received_at_ms": int(received_at_ms),
        "game_timestamp_ms": int(packet["TimestampMS"]),
        "is_race_on": int(packet.get("IsRaceOn", 0)) > 0,
        "lap_number": int(packet["LapNumber"]),
        "current_lap": float(packet["CurrentLap"]),
        "current_race_time": float(packet["CurrentRaceTime"]),
        "x": float(packet["PositionX"]),
        "y": float(packet["PositionY"]),
        "z": float(packet["PositionZ"]),
        "speed_mps": float(packet["Speed"]),
        "throttle": int(packet["Accel"]),
        "brake": int(packet["Brake"]),
        "steer": int(packet["Steer"]),
        "gear": int(packet["Gear"]),
        "combined_slip": combined_slip,
        "rear_combined_slip": rear_combined_slip,
    }
    for live_name, packet_name in _OPTIONAL_FLOAT_FIELD_MAP.items():
        live_fields[live_name] = _optional_float(packet, packet_name)
    for live_name, packet_name in _OPTIONAL_INT_FIELD_MAP.items():
        live_fields[live_name] = _optional_int(packet, packet_name)
    return live_fields
