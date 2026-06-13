"""FH6 Data Out packet decoding and capture artifact helpers."""

from __future__ import annotations

import csv
import json
import struct
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator, Sequence


PACKET_SIZE = 324
PARSER_VERSION = "1.2.0"

TYPE_CODES = {
    "S32": "i",
    "U32": "I",
    "F32": "f",
    "U16": "H",
    "U8": "B",
    "S8": "b",
    "pad": "x",
}

TYPE_SIZES = {
    "S32": 4,
    "U32": 4,
    "F32": 4,
    "U16": 2,
    "U8": 1,
    "S8": 1,
    "pad": 1,
}

SCHEMA = [
    ("IsRaceOn", "S32", 0),
    ("TimestampMS", "U32", 4),
    ("EngineMaxRpm", "F32", 8),
    ("EngineIdleRpm", "F32", 12),
    ("CurrentEngineRpm", "F32", 16),
    ("AccelerationX", "F32", 20),
    ("AccelerationY", "F32", 24),
    ("AccelerationZ", "F32", 28),
    ("VelocityX", "F32", 32),
    ("VelocityY", "F32", 36),
    ("VelocityZ", "F32", 40),
    ("AngularVelocityX", "F32", 44),
    ("AngularVelocityY", "F32", 48),
    ("AngularVelocityZ", "F32", 52),
    ("Yaw", "F32", 56),
    ("Pitch", "F32", 60),
    ("Roll", "F32", 64),
    ("NormalizedSuspensionTravelFrontLeft", "F32", 68),
    ("NormalizedSuspensionTravelFrontRight", "F32", 72),
    ("NormalizedSuspensionTravelRearLeft", "F32", 76),
    ("NormalizedSuspensionTravelRearRight", "F32", 80),
    ("TireSlipRatioFrontLeft", "F32", 84),
    ("TireSlipRatioFrontRight", "F32", 88),
    ("TireSlipRatioRearLeft", "F32", 92),
    ("TireSlipRatioRearRight", "F32", 96),
    ("WheelRotationSpeedFrontLeft", "F32", 100),
    ("WheelRotationSpeedFrontRight", "F32", 104),
    ("WheelRotationSpeedRearLeft", "F32", 108),
    ("WheelRotationSpeedRearRight", "F32", 112),
    ("WheelOnRumbleStripFrontLeft", "S32", 116),
    ("WheelOnRumbleStripFrontRight", "S32", 120),
    ("WheelOnRumbleStripRearLeft", "S32", 124),
    ("WheelOnRumbleStripRearRight", "S32", 128),
    ("WheelInPuddleFrontLeft", "S32", 132),
    ("WheelInPuddleFrontRight", "S32", 136),
    ("WheelInPuddleRearLeft", "S32", 140),
    ("WheelInPuddleRearRight", "S32", 144),
    ("SurfaceRumbleFrontLeft", "F32", 148),
    ("SurfaceRumbleFrontRight", "F32", 152),
    ("SurfaceRumbleRearLeft", "F32", 156),
    ("SurfaceRumbleRearRight", "F32", 160),
    ("TireSlipAngleFrontLeft", "F32", 164),
    ("TireSlipAngleFrontRight", "F32", 168),
    ("TireSlipAngleRearLeft", "F32", 172),
    ("TireSlipAngleRearRight", "F32", 176),
    ("TireCombinedSlipFrontLeft", "F32", 180),
    ("TireCombinedSlipFrontRight", "F32", 184),
    ("TireCombinedSlipRearLeft", "F32", 188),
    ("TireCombinedSlipRearRight", "F32", 192),
    ("SuspensionTravelMetersFrontLeft", "F32", 196),
    ("SuspensionTravelMetersFrontRight", "F32", 200),
    ("SuspensionTravelMetersRearLeft", "F32", 204),
    ("SuspensionTravelMetersRearRight", "F32", 208),
    ("CarOrdinal", "S32", 212),
    ("CarClass", "S32", 216),
    ("CarPerformanceIndex", "S32", 220),
    ("DrivetrainType", "S32", 224),
    ("NumCylinders", "S32", 228),
    ("CarGroup", "U32", 232),
    ("SmashableVelDiff", "F32", 236),
    ("SmashableMass", "F32", 240),
    ("PositionX", "F32", 244),
    ("PositionY", "F32", 248),
    ("PositionZ", "F32", 252),
    ("Speed", "F32", 256),
    ("Power", "F32", 260),
    ("Torque", "F32", 264),
    ("TireTempFrontLeft", "F32", 268),
    ("TireTempFrontRight", "F32", 272),
    ("TireTempRearLeft", "F32", 276),
    ("TireTempRearRight", "F32", 280),
    ("Boost", "F32", 284),
    ("Fuel", "F32", 288),
    ("DistanceTraveled", "F32", 292),
    ("BestLap", "F32", 296),
    ("LastLap", "F32", 300),
    ("CurrentLap", "F32", 304),
    ("CurrentRaceTime", "F32", 308),
    ("LapNumber", "U16", 312),
    ("RacePosition", "U8", 314),
    ("Accel", "U8", 315),
    ("Brake", "U8", 316),
    ("Clutch", "U8", 317),
    ("HandBrake", "U8", 318),
    ("Gear", "U8", 319),
    ("Steer", "S8", 320),
    ("NormalizedDrivingLine", "S8", 321),
    ("NormalizedAIBrakeDifference", "S8", 322),
    ("_ReservedPadding", "pad", 323),
]

FIELD_NAMES = [name for name, type_name, _offset in SCHEMA if type_name != "pad"]
STRUCT_FORMAT = "<" + "".join(TYPE_CODES[type_name] for _name, type_name, _offset in SCHEMA)
PACKET_STRUCT = struct.Struct(STRUCT_FORMAT)

CLASS_LABELS = {
    0: "D",
    1: "C",
    2: "B",
    3: "A",
    4: "S1",
    5: "S2",
    6: "R",
    7: "X",
}

CLASS_PI_RANGES = {
    0: (100, 400),
    1: (401, 500),
    2: (501, 600),
    3: (601, 700),
    4: (701, 800),
    5: (801, 900),
    6: (901, 998),
    7: (999, 999),
}

DRIVETRAIN_LABELS = {
    0: "FWD",
    1: "RWD",
    2: "AWD",
}


def validate_schema() -> None:
    offset = 0
    for name, type_name, declared_offset in SCHEMA:
        if declared_offset != offset:
            raise ValueError(f"{name} offset {declared_offset} does not match {offset}")
        offset += TYPE_SIZES[type_name]
    if offset != PACKET_SIZE:
        raise ValueError(f"schema totals {offset} bytes, expected {PACKET_SIZE}")
    if PACKET_STRUCT.size != PACKET_SIZE:
        raise ValueError(f"struct size {PACKET_STRUCT.size}, expected {PACKET_SIZE}")


validate_schema()


def decode_packet(data: bytes) -> dict:
    if len(data) != PACKET_SIZE:
        raise ValueError(f"Data Out packet must be {PACKET_SIZE} bytes, got {len(data)}")
    values = PACKET_STRUCT.unpack(data)
    return dict(zip(FIELD_NAMES, values, strict=True))


def encode_packet_for_test(values: dict | None = None) -> bytes:
    merged = {
        "IsRaceOn": 1,
        "TimestampMS": 0,
        "EngineMaxRpm": 8000.0,
        "EngineIdleRpm": 900.0,
        "CurrentEngineRpm": 3500.0,
        "Speed": 30.0,
        # FH6 S1 caps at PI 800, not the older Horizon S1 900 scale.
        "CarClass": 4,
        "CarPerformanceIndex": 800,
        "DrivetrainType": 2,
        "Accel": 128,
        "Brake": 0,
        "Gear": 3,
        "Steer": 0,
    }
    if values:
        merged.update(values)

    packed_values = []
    for name, type_name, _offset in SCHEMA:
        if type_name == "pad":
            continue
        packed_values.append(merged.get(name, 0.0 if type_name == "F32" else 0))
    return PACKET_STRUCT.pack(*packed_values)


def iter_raw_packet_bytes(path: Path) -> Iterator[bytes]:
    raw = path.read_bytes()
    if len(raw) % PACKET_SIZE != 0:
        raise ValueError(
            f"{path} is {len(raw)} bytes, not a multiple of {PACKET_SIZE}"
        )
    for index in range(0, len(raw), PACKET_SIZE):
        yield raw[index : index + PACKET_SIZE]


def iter_raw_packets(path: Path) -> Iterator[dict]:
    for packet in iter_raw_packet_bytes(path):
        yield decode_packet(packet)


def _max_abs(packets: Sequence[dict], fields: Iterable[str]) -> float:
    values = [abs(float(packet[field])) for packet in packets for field in fields]
    return max(values) if values else 0.0


def _avg(packets: Sequence[dict], fields: Iterable[str]) -> float:
    values = [float(packet[field]) for packet in packets for field in fields]
    return sum(values) / len(values) if values else 0.0


def classify_summary(summary: dict) -> dict:
    """Classify capture usefulness from summary fields only."""

    packet_count = int(summary.get("packet_count", 0) or 0)
    duration_seconds = float(summary.get("duration_seconds", 0.0) or 0.0)
    top_speed_mph = float(summary.get("top_speed_mph", 0.0) or 0.0)
    lap_number = int(summary.get("lap_number", 0) or 0)
    best_lap = float(summary.get("best_lap", 0.0) or 0.0)
    last_lap = float(summary.get("last_lap", 0.0) or 0.0)
    current_lap = float(summary.get("current_lap", 0.0) or 0.0)
    has_lap_signal = lap_number > 0 or best_lap > 0.0 or last_lap > 0.0

    reasons: list[str] = []
    if packet_count < 1_000 and top_speed_mph < 25.0 and duration_seconds <= 30.0:
        reasons.append("short near-stationary segment")
        return {
            "label": "tail",
            "score": 10,
            "reasons": reasons,
        }

    if top_speed_mph < 35.0 and not has_lap_signal:
        reasons.append("low top speed with no lap signal")
        return {
            "label": "staging",
            "score": 20,
            "reasons": reasons,
        }

    useful_score = 0
    if has_lap_signal:
        useful_score += 2
        reasons.append("lap fields present")
    if top_speed_mph >= 100.0:
        useful_score += 1
        reasons.append("meaningful top speed")
    if duration_seconds >= 90.0:
        useful_score += 1
        reasons.append("long enough for a driving run")
    if packet_count >= 10_000:
        useful_score += 1
        reasons.append("large packet count")

    if useful_score >= 3:
        return {
            "label": "useful",
            "score": 100 + useful_score,
            "reasons": reasons,
        }

    if top_speed_mph >= 60.0 or current_lap > 0.0:
        reasons.append("some driving signal but not enough for a clean run")
        return {
            "label": "maybe",
            "score": 50 + useful_score,
            "reasons": reasons,
        }

    reasons.append("insufficient speed, duration, packet, and lap signals")
    return {
        "label": "staging",
        "score": 20 + useful_score,
        "reasons": reasons,
    }


def summarize_packets(packets: Sequence[dict]) -> dict:
    packets = list(packets)
    if not packets:
        summary = {
            "packet_count": 0,
            "duration_seconds": 0.0,
            "sample_rate_hz": 0.0,
            "diagnostics": ["No packets decoded."],
        }
        summary["segment_classification"] = classify_summary(summary)
        return summary

    active_packets = [
        packet
        for packet in packets
        if int(packet["IsRaceOn"]) == 1
        and (
            float(packet["Speed"]) > 0.5
            or float(packet["EngineMaxRpm"]) > 0
            or int(packet["CarPerformanceIndex"]) > 0
        )
    ]
    analysis_packets = active_packets or packets

    first = analysis_packets[0]
    last = analysis_packets[-1]
    duration_seconds = max(
        0.0, (float(last["TimestampMS"]) - float(first["TimestampMS"])) / 1000.0
    )
    if duration_seconds == 0.0:
        duration_seconds = max(0.0, float(last["CurrentRaceTime"]) - float(first["CurrentRaceTime"]))
    sample_rate = (len(packets) - 1) / duration_seconds if duration_seconds > 0 else 0.0

    top_speed_mps = max(float(packet["Speed"]) for packet in analysis_packets)
    engine_max = max(float(packet["EngineMaxRpm"]) for packet in analysis_packets)
    limiter_threshold = engine_max * 0.98 if engine_max else 0.0

    suspension_fields = [
        "NormalizedSuspensionTravelFrontLeft",
        "NormalizedSuspensionTravelFrontRight",
        "NormalizedSuspensionTravelRearLeft",
        "NormalizedSuspensionTravelRearRight",
    ]
    front_slip = ["TireCombinedSlipFrontLeft", "TireCombinedSlipFrontRight"]
    rear_slip = ["TireCombinedSlipRearLeft", "TireCombinedSlipRearRight"]
    all_combined = front_slip + rear_slip

    bottoming_events = sum(
        1
        for packet in analysis_packets
        if any(float(packet[field]) >= 0.95 for field in suspension_fields)
    )
    limiter_samples = sum(
        1
        for packet in analysis_packets
        if int(packet["Accel"]) > 200 and limiter_threshold and float(packet["CurrentEngineRpm"]) >= limiter_threshold
    )
    bog_samples = sum(
        1
        for packet in analysis_packets
        if int(packet["Accel"]) > 200
        and float(packet["EngineMaxRpm"]) > 0
        and float(packet["CurrentEngineRpm"]) < float(packet["EngineMaxRpm"]) * 0.35
    )
    braking_slip_samples = sum(
        1
        for packet in analysis_packets
        if int(packet["Brake"]) > 200
        and max(
            abs(float(packet["TireSlipRatioFrontLeft"])),
            abs(float(packet["TireSlipRatioFrontRight"])),
            abs(float(packet["TireSlipRatioRearLeft"])),
            abs(float(packet["TireSlipRatioRearRight"])),
        )
        > 1.0
    )

    diagnostics = []
    if bottoming_events:
        diagnostics.append("Suspension reached near-full compression.")
    if limiter_samples:
        diagnostics.append("Limiter contact detected under throttle.")
    if bog_samples:
        diagnostics.append("Low-RPM bog detected under throttle.")
    if braking_slip_samples:
        diagnostics.append("Brake-input slip spikes detected.")

    car_class = int(last["CarClass"])
    car_pi = int(last["CarPerformanceIndex"])
    class_pi_range = CLASS_PI_RANGES.get(car_class)
    class_pi_min = class_pi_range[0] if class_pi_range else None
    class_pi_cap = class_pi_range[1] if class_pi_range else None

    summary = {
        "packet_count": len(packets),
        "active_packet_count": len(active_packets),
        "duration_seconds": round(duration_seconds, 3),
        "sample_rate_hz": round(sample_rate, 2),
        "top_speed_mps": round(top_speed_mps, 3),
        "top_speed_kph": round(top_speed_mps * 3.6, 3),
        "top_speed_mph": round(top_speed_mps * 2.2369362921, 3),
        "car_class": car_class,
        "car_class_label": CLASS_LABELS.get(car_class, "unknown"),
        "car_performance_index": car_pi,
        "car_class_pi_min": class_pi_min,
        "car_class_pi_cap": class_pi_cap,
        "pi_to_class_cap_delta": class_pi_cap - car_pi if class_pi_cap is not None else None,
        "drivetrain_type": int(last["DrivetrainType"]),
        "drivetrain_label": DRIVETRAIN_LABELS.get(int(last["DrivetrainType"]), "unknown"),
        "lap_number": int(last["LapNumber"]),
        "best_lap": float(last["BestLap"]),
        "last_lap": float(last["LastLap"]),
        "current_lap": float(last["CurrentLap"]),
        "peak_combined_slip": round(_max_abs(analysis_packets, all_combined), 4),
        "peak_front_combined_slip": round(_max_abs(analysis_packets, front_slip), 4),
        "peak_rear_combined_slip": round(_max_abs(analysis_packets, rear_slip), 4),
        "avg_front_tire_temp": round(_avg(analysis_packets, ["TireTempFrontLeft", "TireTempFrontRight"]), 3),
        "avg_rear_tire_temp": round(_avg(analysis_packets, ["TireTempRearLeft", "TireTempRearRight"]), 3),
        "tire_temp_unit": "raw_game_value_unit_unverified",
        "max_suspension_compression": round(
            max(float(packet[field]) for packet in analysis_packets for field in suspension_fields), 4
        ),
        "bottoming_events": bottoming_events,
        "limiter_samples": limiter_samples,
        "bog_samples": bog_samples,
        "braking_slip_samples": braking_slip_samples,
        "diagnostics": diagnostics,
    }
    summary["segment_classification"] = classify_summary(summary)
    return summary


def write_packets_csv(path: Path, packets: Sequence[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELD_NAMES)
        writer.writeheader()
        writer.writerows(packets)


def write_capture_artifacts(
    capture_dir: Path,
    raw_packets: Sequence[bytes],
    metadata: dict | None = None,
) -> dict:
    capture_dir.mkdir(parents=True, exist_ok=True)
    raw_path = capture_dir / "raw.bin"
    packets_csv_path = capture_dir / "packets.csv"
    summary_path = capture_dir / "summary.json"
    manifest_path = capture_dir / "manifest.json"

    raw_path.write_bytes(b"".join(raw_packets))
    decoded = [decode_packet(packet) for packet in raw_packets]
    write_packets_csv(packets_csv_path, decoded)
    summary = summarize_packets(decoded)
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    manifest = {
        "parser_version": PARSER_VERSION,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "capture_dir": str(capture_dir.resolve()),
        "raw_path": str(raw_path.resolve()),
        "packets_csv_path": str(packets_csv_path.resolve()),
        "summary_path": str(summary_path.resolve()),
        "manifest_path": str(manifest_path.resolve()),
        "packet_count": len(raw_packets),
        "segment_classification": summary["segment_classification"],
        "metadata": metadata or {},
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def write_latest_pointer(latest_path: Path, manifest_path: Path) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "manifest_path": str(Path(manifest["manifest_path"]).resolve()),
        "capture_dir": manifest["capture_dir"],
        "raw_path": manifest["raw_path"],
        "summary_path": manifest["summary_path"],
        "packets_csv_path": manifest["packets_csv_path"],
        "packet_count": manifest["packet_count"],
        "segment_classification": manifest.get("segment_classification"),
        "updated_utc": datetime.now(timezone.utc).isoformat(),
    }
    temp_path = latest_path.with_suffix(latest_path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temp_path.replace(latest_path)
