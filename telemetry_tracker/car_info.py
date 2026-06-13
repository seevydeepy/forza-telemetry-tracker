"""Lap-level car telemetry aggregation."""

from __future__ import annotations

import math
from collections import Counter
from statistics import fmean

from telemetry_tracker.car_catalog import (
    car_class_label,
    car_group_label,
    drivetrain_label,
    supplement_car_catalog_record,
)
from telemetry_tracker.packet_bridge import decode_packet
from telemetry_tracker.storage import TelemetryStore


_INT_FIELDS = (
    "CarOrdinal",
    "CarClass",
    "CarPerformanceIndex",
    "DrivetrainType",
    "NumCylinders",
    "CarGroup",
)


def _optional_int(value) -> int | None:
    if value is None:
        return None
    return int(value)


def _mode(values: list[int | None]) -> int | None:
    present = [int(value) for value in values if value is not None]
    if not present:
        return None
    return Counter(present).most_common(1)[0][0]


def _float_values(packets: list[dict], field_name: str) -> list[float]:
    values: list[float] = []
    for packet in packets:
        value = packet.get(field_name)
        if value is None:
            continue
        numeric = float(value)
        if math.isfinite(numeric):
            values.append(numeric)
    return values


def _max_or_none(values: list[float]) -> float | None:
    return max(values) if values else None


def _mean_or_none(values: list[float]) -> float | None:
    return fmean(values) if values else None


def _last_or_none(values: list[float]) -> float | None:
    return values[-1] if values else None


def _catalog_value(catalog: dict | None, key: str):
    return None if catalog is None else catalog.get(key)



def car_identity_from_packet(store: TelemetryStore, packet: dict) -> dict | None:
    """Return the session-level car identity tuple from one decoded packet."""

    ordinal = _optional_int(packet.get("CarOrdinal"))
    car_class = _optional_int(packet.get("CarClass"))
    performance_index = _optional_int(packet.get("CarPerformanceIndex"))
    drivetrain = _optional_int(packet.get("DrivetrainType"))
    if (
        ordinal is None
        and car_class is None
        and performance_index is None
        and drivetrain is None
    ):
        return None

    catalog = (
        supplement_car_catalog_record(store.car_by_ordinal(ordinal))
        if ordinal is not None
        else None
    )
    name = "Unknown car"
    if catalog is not None:
        name = catalog.get("model_short") or catalog.get("display_name") or name

    return {
        "car_identity_key": "|".join(
            [
                f"ordinal:{ordinal}" if ordinal is not None else f"name:{name.strip().lower()}",
                f"class:{car_class}" if car_class is not None else "class:unknown",
                f"pi:{performance_index}" if performance_index is not None else "pi:unknown",
                f"drive:{drivetrain}" if drivetrain is not None else "drive:unknown",
            ]
        ),
        "car_ordinal": ordinal,
        "car_name": name,
        "car_class_id": car_class,
        "car_class_label": car_class_label(car_class),
        "car_performance_index": performance_index,
        "drivetrain_id": drivetrain,
        "drivetrain_label": drivetrain_label(drivetrain),
    }

def car_info_from_packets(store: TelemetryStore, packets: list[dict]) -> dict | None:
    """Return API-ready car identity and curated details from decoded packets."""

    if not packets:
        return None

    ordinal = _mode([_optional_int(packet.get("CarOrdinal")) for packet in packets])
    car_class = _mode([_optional_int(packet.get("CarClass")) for packet in packets])
    performance_index = _mode(
        [_optional_int(packet.get("CarPerformanceIndex")) for packet in packets]
    )
    drivetrain = _mode([_optional_int(packet.get("DrivetrainType")) for packet in packets])
    cylinders = _mode([_optional_int(packet.get("NumCylinders")) for packet in packets])
    car_group = _mode([_optional_int(packet.get("CarGroup")) for packet in packets])

    catalog = (
        supplement_car_catalog_record(store.car_by_ordinal(ordinal))
        if ordinal is not None
        else None
    )
    name = "Unknown"
    if catalog is not None:
        name = catalog.get("model_short") or catalog.get("display_name") or "Unknown"

    power_values = _float_values(packets, "Power")
    torque_values = _float_values(packets, "Torque")
    boost_values = _float_values(packets, "Boost")
    fuel_values = _float_values(packets, "Fuel")

    return {
        "ordinal": ordinal,
        "name": name,
        "display_name": _catalog_value(catalog, "display_name"),
        "model_short": _catalog_value(catalog, "model_short"),
        "year": _catalog_value(catalog, "year"),
        "class_id": car_class,
        "class_label": car_class_label(car_class),
        "performance_index": performance_index,
        "drivetrain_id": drivetrain,
        "drivetrain_label": drivetrain_label(drivetrain),
        "catalog_source": _catalog_value(catalog, "catalog_source") or "unknown",
        "catalog": catalog,
        "details": {
            "num_cylinders": cylinders,
            "car_group": car_group,
            "car_group_label": car_group_label(car_group),
            "engine_max_rpm": _max_or_none(_float_values(packets, "EngineMaxRpm")),
            "peak_power_w": _max_or_none(power_values),
            "average_power_w": _mean_or_none(power_values),
            "peak_torque_nm": _max_or_none(torque_values),
            "average_torque_nm": _mean_or_none(torque_values),
            "peak_boost_bar": _max_or_none(boost_values),
            "fuel": _last_or_none(fuel_values),
        },
    }


def car_info_from_packet_bytes(store: TelemetryStore, raw_packets: list[bytes]) -> dict | None:
    """Return API-ready car identity and curated details from raw packet bytes."""

    if not raw_packets:
        return None
    return car_info_from_packets(store, [decode_packet(raw) for raw in raw_packets])


def car_info_for_lap(store: TelemetryStore, lap_id: str) -> dict | None:
    """Return API-ready car identity and curated details for a lap."""

    return car_info_from_packet_bytes(store, store.packet_bytes_for_lap(lap_id))
