import json
import struct
from pathlib import Path

from telemetry_tracker.track_catalog import (
    BxmlNode,
    _map_region_record_from_object,
    _track_records_from_dataset_node,
    parse_career_track_info_string_table,
    parse_ai_track_route_file,
    parse_track_locator_file,
)


def test_parse_career_track_info_string_table_pairs_values_with_keys():
    raw = (
        b"binary\xffjunk\x00"
        b"Race description\x00Legend Island Circuit\x00LEGEND ISLAND CIRCUIT\x00Legend Island\x00"
        b"IDS_Description_11111111111111111111111111111111\x00"
        b"IDS_DisplayName_22222222222222222222222222222222\x00"
        b"IDS_ShortDisplayNameAllCaps_33333333333333333333333333333333\x00"
        b"IDS_ShortDisplayName_44444444444444444444444444444444\x00"
    )

    strings = parse_career_track_info_string_table(raw)

    assert strings["IDS_DisplayName_22222222222222222222222222222222"] == "Legend Island Circuit"
    assert (
        strings["CareerTrackInfo.IDS_ShortDisplayName_44444444444444444444444444444444"]
        == "Legend Island"
    )


def test_track_records_from_dataset_resolves_localized_names():
    dataset = BxmlNode(
        "object",
        {"type": "TrackInfoDataSet"},
        [
            BxmlNode(
                "property",
                {"id": "Data"},
                [
                    BxmlNode(
                        "map_element",
                        {},
                        [
                            BxmlNode("key", {"value": "42"}, []),
                            BxmlNode(
                                "value",
                                {},
                                [
                                    BxmlNode("property", {"id": "MediaTrackId", "value": "820"}, []),
                                    BxmlNode("property", {"id": "MediaTrackName", "value": "Brio"}, []),
                                    BxmlNode("property", {"id": "RouteId", "value": "8001"}, []),
                                    BxmlNode("property", {"id": "CustomRouteId", "value": "28006"}, []),
                                    BxmlNode("property", {"id": "UseCrossCountryAI", "value": "True"}, []),
                                    BxmlNode("property", {"id": "RibbonConfig", "value": "Circuit"}, []),
                                    BxmlNode(
                                        "property",
                                        {
                                            "id": "DisplayName",
                                            "value": "CareerTrackInfo.IDS_DisplayName_22222222222222222222222222222222",
                                        },
                                        [],
                                    ),
                                    BxmlNode(
                                        "property",
                                        {
                                            "id": "ShortDisplayName",
                                            "value": "CareerTrackInfo.IDS_ShortDisplayName_44444444444444444444444444444444",
                                        },
                                        [],
                                    ),
                                    BxmlNode(
                                        "property",
                                        {
                                            "id": "ShortDisplayNameAllCaps",
                                            "value": "CareerTrackInfo.IDS_ShortDisplayNameAllCaps_33333333333333333333333333333333",
                                        },
                                        [],
                                    ),
                                    BxmlNode(
                                        "property",
                                        {
                                            "id": "Description",
                                            "value": "CareerTrackInfo.IDS_Description_11111111111111111111111111111111",
                                        },
                                        [],
                                    ),
                                ],
                            ),
                        ],
                    )
                ],
            )
        ],
    )
    strings = {
        "CareerTrackInfo.IDS_DisplayName_22222222222222222222222222222222": "Legend Island Circuit",
        "CareerTrackInfo.IDS_ShortDisplayName_44444444444444444444444444444444": "Legend Island",
        "CareerTrackInfo.IDS_ShortDisplayNameAllCaps_33333333333333333333333333333333": "LEGEND ISLAND CIRCUIT",
        "CareerTrackInfo.IDS_Description_11111111111111111111111111111111": "Fast circuit route.",
    }

    records = _track_records_from_dataset_node(dataset, strings, "source/ScribbleData/test.om.xml")

    assert records == [
        {
            "track_key": "track-info:42",
            "source_dataset_key": 42,
            "route_id": 8001,
            "custom_route_id": 28006,
            "media_track_id": 820,
            "media_track_name": "Brio",
            "ribbon_config": "Circuit",
            "display_name": "Legend Island Circuit",
            "short_display_name": "Legend Island",
            "short_display_name_all_caps": "LEGEND ISLAND CIRCUIT",
            "description": "Fast circuit route.",
            "display_name_key": "CareerTrackInfo.IDS_DisplayName_22222222222222222222222222222222",
            "short_display_name_key": "CareerTrackInfo.IDS_ShortDisplayName_44444444444444444444444444444444",
            "short_display_name_all_caps_key": "CareerTrackInfo.IDS_ShortDisplayNameAllCaps_33333333333333333333333333333333",
            "description_key": "CareerTrackInfo.IDS_Description_11111111111111111111111111111111",
            "route_activation_trigger_zone_name": None,
            "use_cross_country_ai": True,
            "stray_warning_distance": None,
            "stray_teleport_distance": None,
            "source_file": "source/ScribbleData/test.om.xml",
            "catalog_source": "fh6_local_files",
        }
    ]


def test_map_region_record_extracts_direct_english_and_locator_names():
    region = BxmlNode(
        "object",
        {"type": "MapRegionData", "id": "region-object"},
        [
            BxmlNode("property", {"id": "ENName", "value": "Legend Island"}, []),
            BxmlNode("property", {"id": "ENShortName", "value": "Legend Island"}, []),
            BxmlNode("property", {"id": "JPName", "value": "レジェンドアイランド"}, []),
            BxmlNode("property", {"id": "LocatorsCollectionName", "value": "map_region_legend_island"}, []),
            BxmlNode("property", {"id": "FullRevealPercentage", "value": "59"}, []),
        ],
    )

    record = _map_region_record_from_object(region, "source/ScribbleData/region.om.xml")

    assert record["region_key"] == "map_region_legend_island"
    assert record["english_name"] == "Legend Island"
    assert record["japanese_name"] == "レジェンドアイランド"
    assert record["full_reveal_percentage"] == 59


def test_parse_track_locator_file_extracts_route_positions_and_transform(tmp_path: Path):
    locator_file = tmp_path / "media" / "Tracks" / "Brio" / "trackroutes" / "route3001.nt"
    locator_file.parent.mkdir(parents=True)
    locator_file.write_text(
        """
<TrackLocators>
  <Locator Version="2">
    <Name value="start_line_000"/>
    <GUID value="0"/>
    <SceneTransform value._11="1.000000" value._12="0" value._13="0" value._14="0" value._21="0" value._22="1" value._23="0" value._24="0" value._31="0.232854" value._32="0" value._33="0.972433" value._34="0" value._41="1199.184498" value._42="101.982351" value._43="-5318.321989" value._44="1"/>
    <AttachTo/>
  </Locator>
</TrackLocators>
""".strip(),
        encoding="utf-8",
    )

    records = parse_track_locator_file(locator_file, tmp_path / "media")

    assert len(records) == 1
    record = records[0]
    assert record["source_file"] == "Tracks/Brio/trackroutes/route3001.nt"
    assert record["media_track_name"] == "Brio"
    assert record["locator_collection"] == "route3001"
    assert record["locator_kind"] == "start_line"
    assert record["route_id"] == 3001
    assert record["x"] == 1199.184498
    assert record["z"] == -5318.321989
    assert json.loads(record["transform_json"])["m43"] == -5318.321989


def test_parse_ai_track_route_file_extracts_decimated_route_points(tmp_path: Path):
    route_file = tmp_path / "media" / "OpenWorld" / "Brio" / "AITracks" / "Route161.owt"
    route_file.parent.mkdir(parents=True)
    raw = bytearray(0x60 + (4 * 0x38))
    raw[:4] = b"FTWO"
    raw[0x24:0x28] = (4).to_bytes(4, "little")
    for index, (x, y, z) in enumerate(
        [
            (100.0, 10.0, 200.0),
            (110.0, 10.0, 200.0),
            (130.0, 10.0, 200.0),
            (140.0, 10.0, 200.0),
        ]
    ):
        struct.pack_into("<fff", raw, 0x60 + (index * 0x38), x, y, z)
    route_file.write_bytes(raw)

    records = parse_ai_track_route_file(route_file, tmp_path / "media")

    assert [record["locator_name"] for record in records] == [
        "route_point_00000",
        "route_point_00002",
        "route_point_00003",
    ]
    first = records[0]
    assert first["source_file"] == "OpenWorld/Brio/AITracks/Route161.owt"
    assert first["media_track_name"] == "Brio"
    assert first["locator_collection"] == "aitrack_route161"
    assert first["locator_kind"] == "route_point"
    assert first["route_id"] == 161
    assert first["x"] == 100.0
    assert first["z"] == 200.0
    assert json.loads(first["transform_json"])["spacing_meters"] == 25.0
