import json
import zipfile
from pathlib import Path

from telemetry_tracker.car_catalog import (
    FH6_PI_BUCKETS,
    car_class_label,
    car_group_label,
    drivetrain_label,
    load_local_fh6_catalog,
    parse_data_car_string_table,
    scan_car_zip_ordinals,
)


def test_fh6_class_and_drivetrain_labels():
    assert FH6_PI_BUCKETS["R"] == (901, 998)
    assert car_class_label(0) == "D"
    assert car_class_label(4) == "S1"
    assert car_class_label(7) == "X"
    assert car_class_label(99) is None
    assert drivetrain_label(0) == "FWD"
    assert drivetrain_label(1) == "RWD"
    assert drivetrain_label(2) == "AWD"
    assert drivetrain_label(9) is None
    assert car_group_label(26) == "Extreme Track Toys"
    assert car_group_label(34) == "Rally Monsters"
    assert car_group_label(None) is None
    assert car_group_label(999) is None


def test_parse_data_car_string_table_pairs_display_and_model_short_values():
    raw = (
        b"Integra Type R\x00NSX Type S\x00"
        b"Acura Integra\x00Acura NSX '22\x00"
        b"IDS_DisplayName_368\x00IDS_DisplayName_3767\x00"
        b"IDS_ModelShort_368\x00IDS_ModelShort_3767\x00"
    )

    records = parse_data_car_string_table(raw)

    assert records[368]["display_name"] == "Integra Type R"
    assert records[368]["model_short"] == "Acura Integra"
    assert records[3767]["display_name"] == "NSX Type S"
    assert records[3767]["model_short"] == "Acura NSX '22"


def test_parse_data_car_string_table_fails_safe_on_value_count_mismatch():
    raw = (
        b"Only One Display Value\x00"
        b"IDS_DisplayName_368\x00IDS_DisplayName_3767\x00"
        b"IDS_ModelShort_368\x00IDS_ModelShort_3767\x00"
    )

    records = parse_data_car_string_table(raw)

    assert records[368]["display_name"] is None
    assert records[3767]["display_name"] is None


def test_scan_car_zip_ordinals_extracts_carclips_ordinal(tmp_path: Path):
    cars_dir = tmp_path / "Cars"
    cars_dir.mkdir()
    with zipfile.ZipFile(cars_dir / "ACU_IntegraR_01.zip", "w") as archive:
        archive.writestr("Scene/animations/Mojo/clip/carclips_368.clipd", b"clip")

    records = scan_car_zip_ordinals(cars_dir)

    assert records[368]["asset_name"] == "ACU_IntegraR_01"
    assert records[368]["asset_zip"] == "ACU_IntegraR_01.zip"


def test_scan_car_zip_ordinals_ignores_ambiguous_archives(tmp_path: Path):
    cars_dir = tmp_path / "Cars"
    cars_dir.mkdir()
    with zipfile.ZipFile(cars_dir / "BROKEN.zip", "w") as archive:
        archive.writestr("Scene/animations/Mojo/clip/carclips_1.clipd", b"clip")
        archive.writestr("Scene/animations/Mojo/clip/carclips_2.clipd", b"clip")

    assert scan_car_zip_ordinals(cars_dir) == {}


def test_load_local_fh6_catalog_merges_string_table_and_zip_data(tmp_path: Path):
    media_root = tmp_path / "media"
    cars_dir = media_root / "Cars"
    strings_dir = media_root / "Stripped" / "StringTables"
    cars_dir.mkdir(parents=True)
    strings_dir.mkdir(parents=True)
    with zipfile.ZipFile(cars_dir / "ACU_IntegraR_01.zip", "w") as archive:
        archive.writestr("Scene/animations/Mojo/clip/carclips_368.clipd", b"clip")
    raw = b"Integra Type R\x00Acura Integra\x00IDS_DisplayName_368\x00IDS_ModelShort_368\x00"
    with zipfile.ZipFile(strings_dir / "EN.zip", "w") as archive:
        archive.writestr("Data_Car.str", raw)

    records = {record["ordinal"]: record for record in load_local_fh6_catalog(media_root)}

    assert records[368]["display_name"] == "Integra Type R"
    assert records[368]["model_short"] == "Acura Integra"
    assert records[368]["asset_zip"] == "ACU_IntegraR_01.zip"
    assert records[368]["catalog_source"] == "fh6_local_files"


def test_load_local_fh6_catalog_applies_car_catalog_supplements(tmp_path: Path):
    media_root = tmp_path / "media"
    cars_dir = media_root / "Cars"
    strings_dir = media_root / "Stripped" / "StringTables"
    cars_dir.mkdir(parents=True)
    strings_dir.mkdir(parents=True)
    with zipfile.ZipFile(cars_dir / "MAZ_Furai_08.zip", "w") as archive:
        archive.writestr("Scene/animations/Mojo/clip/carclips_3606.clipd", b"clip")
    raw = b"Mazda Furai\x00Furai\x00IDS_DisplayName_3606\x00IDS_ModelShort_3606\x00"
    with zipfile.ZipFile(strings_dir / "EN.zip", "w") as archive:
        archive.writestr("Data_Car.str", raw)
    supplements_path = tmp_path / "car_catalog_supplements.json"
    supplements_path.write_text(
        json.dumps(
            {
                "cars": [
                    {
                        "year": 2008,
                        "make": "Mazda",
                        "model": "Furai",
                        "display_name": "2008 Mazda Furai",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    records = {
        record["ordinal"]: record
        for record in load_local_fh6_catalog(media_root, supplements_path=supplements_path)
    }

    assert records[3606]["display_name"] == "Mazda Furai"
    assert records[3606]["year"] == 2008
    assert records[3606]["make"] == "Mazda"
    assert records[3606]["model"] == "Furai"
