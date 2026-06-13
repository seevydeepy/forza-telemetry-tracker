import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from telemetry_tracker.car_info import car_identity_from_packet, car_info_for_lap
from telemetry_tracker.packet_bridge import decode_packet, encode_packet_for_test, packet_to_live_fields
from telemetry_tracker.storage import TelemetryStore


def _insert_car_lap(
    store: TelemetryStore,
    *,
    ordinal: int = 1229,
    catalog: bool = True,
    catalog_record: dict | None = None,
) -> str:
    session_id = store.create_session(label="Car lap")
    lap_id = store.create_lap(session_id=session_id, lap_number=1, boundary_confidence="game_field")
    if catalog:
        record = {
            "ordinal": ordinal,
            "display_name": "Furai",
            "model_short": "Mazda Furai",
            "year": 2008,
            "catalog_source": "test",
        }
        if catalog_record:
            record.update(catalog_record)
        store.upsert_car_catalog_records([record])
    raw_packets = []
    decoded_packets = []
    samples = []
    for sequence, speed in enumerate((10.0, 20.0, 30.0), start=1):
        raw = encode_packet_for_test(
            {
                "TimestampMS": sequence * 16,
                "LapNumber": 1,
                "CurrentLap": float(sequence),
                "CurrentRaceTime": float(sequence),
                "PositionX": float(sequence),
                "PositionY": 0.0,
                "PositionZ": float(sequence),
                "Speed": speed,
                "CarOrdinal": ordinal,
                "CarClass": 6,
                "CarPerformanceIndex": 998,
                "DrivetrainType": 1,
                "NumCylinders": 3,
                "CarGroup": 26,
                "EngineMaxRpm": 9999.995,
                "Power": 331000.0 + sequence,
                "Torque": 392.0 + sequence,
                "Boost": 0.0,
                "Fuel": 0.75,
            }
        )
        decoded = decode_packet(raw)
        sample = packet_to_live_fields(decoded, sequence=sequence, received_at_ms=sequence * 16)
        sample["lap_id"] = lap_id
        raw_packets.append(raw)
        decoded_packets.append(decoded)
        samples.append(sample)
    store.insert_packet_batch(session_id, raw_packets, decoded_packets, samples)
    return lap_id


class CarInfoTests(unittest.TestCase):

    def test_car_identity_from_packet_uses_catalog_and_build_tuple(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            store.upsert_car_catalog_records(
                [
                    {
                        "ordinal": 368,
                        "display_name": "Acura Integra Type R",
                        "model_short": "Integra R",
                    }
                ]
            )

            identity = car_identity_from_packet(
                store,
                {
                    "CarOrdinal": 368,
                    "CarClass": 3,
                    "CarPerformanceIndex": 700,
                    "DrivetrainType": 0,
                },
            )

            self.assertEqual(identity["car_identity_key"], "ordinal:368|class:3|pi:700|drive:0")
            self.assertEqual(identity["car_name"], "Integra R")
            self.assertEqual(identity["car_class_label"], "A")
            self.assertEqual(identity["car_performance_index"], 700)
            self.assertEqual(identity["drivetrain_label"], "FWD")

    def test_car_identity_from_packet_returns_none_without_identity_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()

            self.assertIsNone(car_identity_from_packet(store, {"Speed": 30.0}))

    def test_car_info_for_lap_uses_telemetry_identity_and_catalog_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            lap_id = _insert_car_lap(store)

            info = car_info_for_lap(store, lap_id)

            self.assertEqual(info["ordinal"], 1229)
            self.assertEqual(info["name"], "Mazda Furai")
            self.assertEqual(info["year"], 2008)
            self.assertEqual(info["class_label"], "R")
            self.assertEqual(info["performance_index"], 998)
            self.assertEqual(info["drivetrain_label"], "RWD")
            self.assertEqual(info["details"]["num_cylinders"], 3)
            self.assertEqual(info["details"]["car_group"], 26)
            self.assertEqual(info["details"]["car_group_label"], "Extreme Track Toys")
            self.assertAlmostEqual(info["details"]["engine_max_rpm"], 9999.995, places=2)
            self.assertGreater(info["details"]["peak_power_w"], 331000.0)
            self.assertAlmostEqual(info["details"]["fuel"], 0.75)

    def test_car_info_for_lap_falls_back_to_unknown_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            lap_id = _insert_car_lap(store, ordinal=99999, catalog=False)

            info = car_info_for_lap(store, lap_id)

            self.assertEqual(info["ordinal"], 99999)
            self.assertEqual(info["name"], "Unknown")
            self.assertEqual(info["catalog_source"], "unknown")
            self.assertEqual(info["class_label"], "R")
            self.assertEqual(info["performance_index"], 998)

    def test_car_info_for_lap_supplements_cached_catalog_without_year(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            lap_id = _insert_car_lap(store, catalog_record={"year": None})

            with patch(
                "telemetry_tracker.car_info.supplement_car_catalog_record",
                side_effect=lambda catalog: {**catalog, "year": 2008},
            ) as supplement:
                info = car_info_for_lap(store, lap_id)

            self.assertEqual(info["year"], 2008)
            supplement.assert_called_once()

    def test_car_info_for_lap_returns_none_when_lap_has_no_packets(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TelemetryStore(Path(tmp) / "telemetry_tracker.sqlite3")
            store.migrate()
            session_id = store.create_session(label="Empty lap")
            lap_id = store.create_lap(session_id=session_id, lap_number=1, boundary_confidence="game_field")

            self.assertIsNone(car_info_for_lap(store, lap_id))


if __name__ == "__main__":
    unittest.main()
