"""Vector maps: openAIP items -> the common GeoJSON properties, paging, the stored list."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import vectormaps as vm  # noqa: E402

SQ = {"type": "Polygon", "coordinates": [[[17, 48], [17.2, 48], [17.2, 48.2], [17, 48]]]}
PT = {"type": "Point", "coordinates": [20.24, 49.07]}


def test_airspace_limits_class_freq():
    f = vm.openaip_airspace({"_id": "a1", "name": "BOLERAZ", "type": 13, "icaoClass": 6, "geometry": SQ,
                             "upperLimit": {"value": 4000, "unit": 1, "referenceDatum": 1},
                             "lowerLimit": {"value": 0, "unit": 1, "referenceDatum": 0},
                             "frequencies": [{"value": "132.080", "unit": 2, "primary": True}]})
    p = f["properties"]
    assert p["kind"] == "airspace" and p["cat"] == "ATZ" and p["cls"] == "G"
    assert p["upper"] == {"v": 4000, "u": "ft", "ref": "MSL"} and p["lower"] == {"v": 0, "u": "ft", "ref": "GND"}
    assert p["freq"] == [{"f": 132.08}] and p["srcId"] == "a1" and f["geometry"] == SQ


def test_airspace_flight_level_and_other_named_tma():
    f = vm.openaip_airspace({"name": "BRATISLAVA TMA 1", "type": 0, "icaoClass": 2, "geometry": SQ,
                             "upperLimit": {"value": 660, "unit": 6, "referenceDatum": 2}})
    assert f["properties"]["cat"] == "TMA" and f["properties"]["upper"] == {"v": 660, "u": "FL", "ref": "STD"}
    assert "lower" not in f["properties"]
    assert vm.openaip_airspace({"name": "RUTOL AREA", "type": 0, "geometry": SQ})["properties"]["cat"] == "OTHER"


def test_airport_navaid_point_obstacle():
    a = vm.openaip_airport({"name": "POPRAD TATRY", "icaoCode": "LZTT", "type": 3, "geometry": PT,
                            "elevation": {"value": 703, "unit": 0, "referenceDatum": 1},
                            "frequencies": [{"value": "121.350", "unit": 2, "type": 14, "name": "TATRY TOWER"}],
                            "runways": [{"designator": "09"}, {"designator": "27"}]})["properties"]
    assert (a["kind"], a["cat"], a["ident"], a["elev"], a["rwy"]) == ("airport", "intl", "LZTT", 703, ["09", "27"])
    assert a["freq"] == [{"f": 121.35, "name": "TATRY TOWER", "type": "TWR"}]
    n = vm.openaip_navaid({"name": "NITRA", "identifier": "PW", "type": 2, "geometry": PT,
                           "frequency": {"value": "418", "unit": 1}})["properties"]
    assert (n["cat"], n["ident"], n["freq"]) == ("NDB", "PW", [{"f": 0.418}])
    r = vm.openaip_point({"name": "WHISKEY", "compulsory": True, "geometry": PT})["properties"]
    assert (r["kind"], r["cat"]) == ("point", "RP")
    o = vm.openaip_obstacle({"name": "Kamzik", "type": 4, "geometry": PT,
                             "height": {"value": 196, "unit": 0, "referenceDatum": 0}})["properties"]
    assert (o["kind"], o["cat"], o["height"]) == ("obstacle", "tower", 196)


def test_no_geometry_is_skipped():
    assert vm.openaip_airport({"name": "X", "type": 2}) is None


def test_download_follows_pages_and_builds_collection():
    calls = []

    def get(ep, country, key, page):
        calls.append((ep, page))
        if ep == "airports":
            return {"totalPages": 2, "items": [{"name": f"A{page}", "type": 2, "geometry": PT}]}
        return {"totalPages": 1, "items": []}

    items = vm.openaip_download("SK", "k", get=get)
    assert ("airports", 2) in calls and len(items["airports"]) == 2
    coll = vm.openaip_collection("SK", items, fetched=100)
    assert coll["radimcom"]["country"] == "SK" and coll["radimcom"]["fetched"] == 100
    assert vm.summary(coll) == {"airport": {"civil": 2}}


def test_store_and_list(tmp_path, monkeypatch):
    monkeypatch.setattr(vm, "VMAP_DIR", str(tmp_path))
    coll = vm.openaip_collection("SK", {"navaids": [{"name": "N", "type": 4, "geometry": PT}]}, fetched=1)
    vm.save("openaip_SK", coll)
    [m] = vm.list_maps()
    assert m["id"] == "openaip_SK" and m["n"] == 1 and m["stale"] and m["cats"] == {"navaid": {"VOR-DME": 1}}
    assert vm._path("../x") is None


def test_update_needs_country_and_key(monkeypatch):
    monkeypatch.setattr(vm, "_openaip_key", lambda: "")
    for c, msg in (("SVK", "two letters"), ("SK", "key")):
        try:
            vm.openaip_update(c)
            assert False
        except ValueError as e:
            assert msg in str(e)


def test_view_stored_in_files_and_kept_on_update(tmp_path, monkeypatch):
    monkeypatch.setattr(vm, "VMAP_DIR", str(tmp_path))
    items = {"airports": [{"_id": "a1", "name": "A", "type": 2, "geometry": PT}, {"_id": "a2", "name": "B", "type": 2, "geometry": PT}]}
    vm.save("openaip_SK", vm.openaip_collection("SK", items))
    vm.save("openaip_CZ", vm.openaip_collection("CZ", {}))
    assert vm.get_view()["stored"] is False
    vm.set_view({"cats": {"airport.civil": False}, "lbl": {"airport": True}, "maxFL": 95,
                 "maps": {"openaip_CZ": False}, "hidden": ["openaip:a2"]})
    v = vm.get_view()
    assert v["stored"] and v["cats"] == {"airport.civil": False} and v["maxFL"] == 95
    assert v["maps"] == {"openaip_CZ": False, "openaip_SK": True} and v["hidden"] == ["openaip:a2"]
    # a new download of SK keeps the hidden object and the view
    new = vm.keep_view(vm._load(vm._path("openaip_SK")), vm.openaip_collection("SK", items))
    assert [f["properties"].get("hidden") for f in new["features"]] == [None, True]
    assert new["radimcom"]["view"]["cats"] == {"airport.civil": False}
