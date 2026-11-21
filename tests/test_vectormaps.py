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


def test_style_is_cleaned_and_stored(tmp_path, monkeypatch):
    monkeypatch.setattr(vm, "VMAP_DIR", str(tmp_path))
    vm.save("openaip_SK", vm.openaip_collection("SK", {}))
    vm.set_view({"style": {"airspace.CTR": {"c": "#112233", "w": 3, "d": "dot", "x": 1, "o": 7},
                           "airport.intl": {"sym": "square", "r": 6, "fc": "red"}, "bad key": {"c": "#000000"}}})
    assert vm.get_view()["style"] == {"airspace.CTR": {"c": "#112233", "w": 3, "d": "dot"}, "airport.intl": {"sym": "square", "r": 6}}


OA = {
    "airports.csv": b'"id","ident","type","name","latitude_deg","longitude_deg","elevation_ft","iso_country","municipality","gps_code","iata_code","icao_code"\n'
                    b'1,"LZIB","large_airport","Bratislava Airport",48.17,17.21,436,"SK","Bratislava","LZIB","BTS","LZIB"\n'
                    b'2,"LHBP","large_airport","Budapest",47.43,19.26,495,"HU","Budapest","LHBP","BUD","LHBP"\n'
                    b'3,"SK-0001","closed","Old strip",48.5,18.0,,"SK","","","",""\n',
    "airport-frequencies.csv": b'"id","airport_ref","airport_ident","type","description","frequency_mhz"\n'
                               b'10,1,"LZIB","TWR","BRATISLAVA TOWER",118.3\n11,2,"LHBP","TWR","x",118.1\n',
    "runways.csv": b'"id","airport_ref","airport_ident","closed","le_ident","he_ident"\n20,1,"LZIB",0,"04","22"\n21,1,"LZIB",1,"13","31"\n',
    "navaids.csv": b'"id","filename","ident","name","type","frequency_khz","latitude_deg","longitude_deg","elevation_ft","iso_country","dme_channel"\n'
                   b'30,"x","PWZ","PIESTANY","NDB",418,48.6,17.8,600,"SK",""\n31,"y","BKS","BRATISLAVA","VOR-DME",114200,48.1,17.1,,"SK","089X"\n',
}


def test_ourairports_tables_and_collection(tmp_path, monkeypatch):
    monkeypatch.setattr(vm, "OURAIRPORTS_DIR", str(tmp_path))
    calls = []
    tables, _ = vm.ourairports_tables(lambda n: calls.append(n) or OA[n])
    vm.ourairports_tables(lambda n: calls.append(n) or OA[n])   # kept a day: no second download
    assert sorted(calls) == sorted(vm.OURAIRPORTS_FILES)
    c = vm.ourairports_collection("SK", tables)
    assert c["radimcom"]["source"] == "ourairports" and c["radimcom"]["country"] == "SK"
    by = {f["properties"]["srcId"]: f["properties"] for f in c["features"]}
    a = by["1"]
    assert (a["kind"], a["cat"], a["ident"], a["iata"], a["elev"], a["rwy"]) == ("airport", "large", "LZIB", "BTS", 133, ["04/22"])
    assert a["freq"] == [{"f": 118.3, "name": "BRATISLAVA TOWER", "type": "TWR"}]
    assert by["3"]["cat"] == "closed" and "2" not in by
    assert by["nav30"]["cat"] == "NDB" and by["nav30"]["freq"] == [{"f": 0.418}]
    assert by["nav31"]["cat"] == "VOR-DME" and by["nav31"]["freq"] == [{"f": 114.2}] and by["nav31"]["channel"] == "089X"


def test_ourairports_rejects_non_csv(tmp_path, monkeypatch):
    monkeypatch.setattr(vm, "OURAIRPORTS_DIR", str(tmp_path))
    try:
        vm.ourairports_tables(lambda n: b"<html>blocked</html>")
        assert False
    except ValueError:
        pass


def test_osm_transmitters():
    els = [{"type": "node", "id": 1, "lat": 48.1, "lon": 17.1, "tags": {"man_made": "tower", "tower:type": "communication",
            "communication:television": "yes", "communication:radio": "yes", "name": "Kamzik", "height": "196 m", "operator": "Towercom"}},
           {"type": "way", "id": 2, "center": {"lat": 48.2, "lon": 17.2}, "tags": {"man_made": "mast", "communication:mobile_phone": "yes"}},
           {"type": "node", "id": 3, "lat": 48.3, "lon": 17.3, "tags": {"man_made": "tower", "tower:type": "radar"}},
           {"type": "node", "id": 4, "lat": 48.4, "lon": 17.4, "tags": {"man_made": "antenna", "communication:amateur_radio": "yes"}},
           {"type": "node", "id": 5, "lat": 48.5, "lon": 17.5, "tags": {"man_made": "antenna"}},
           {"type": "node", "id": 1, "lat": 48.1, "lon": 17.1, "tags": {}}]
    c = vm.osm_tx_collection("SK", els)
    by = {f["properties"]["srcId"]: f["properties"] for f in c["features"]}
    assert len(c["features"]) == 5 and c["radimcom"]["source"] == "osm"
    k = by["n1"]
    assert (k["kind"], k["cat"], k["name"], k["height"], k["operator"]) == ("tx", "bcast", "Kamzik", 196, "Towercom")
    assert "television" in k["remarks"]
    assert [by[x]["cat"] for x in ("w2", "n3", "n4", "n5")] == ["mobile", "radar", "ham", "comm"]
    assert c["features"][1]["geometry"]["coordinates"] == [17.2, 48.2]
    q = []
    try:
        vm.osm_update("sk", get=lambda x: q.append(x) or {"elements": []})
    except ValueError:
        pass
    assert '"ISO3166-1"="SK"' in q[0]


def test_memories_channels():
    items = [{"id": "a1", "name": "OK1 rpt", "groups": ["Repeatery 2 m", "x"], "freq_hz": 145600000, "mode": "FM", "lat": 48.1, "lon": 17.1, "note": "n"},
             {"id": "a2", "name": "no loc", "groups": [], "freq_hz": 1, "lat": None, "lon": None},
             {"id": "a3", "name": "Kamzík", "group": "", "freq_hz": 99000000, "mode": "WFM", "lat": 48.18, "lon": 17.1}]
    c = vm.memories_collection(items)
    assert [f["properties"]["srcId"] for f in c["features"]] == ["a1", "a3"]
    p = c["features"][0]["properties"]
    assert p["kind"] == "chan" and p["freq"] == [{"f": 145.6, "type": "FM"}] and p["groups"] == ["Repeatery 2 m", "x"]
    names = c["radimcom"]["catNames"]
    assert names[p["cat"]] == "Repeatery 2 m" and names["nogroup"] == "(no group)"
    assert vm.re.fullmatch(r"[\w-]{1,30}", p["cat"])


def test_own_file():
    gj = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"name": "Zone"}, "geometry": SQ},
        {"type": "Feature", "properties": {"Name": "Track", "description": "<b>x</b>"}, "geometry": {"type": "LineString", "coordinates": [[17, 48], [18, 49]]}},
        {"type": "Feature", "properties": {}, "geometry": {"type": "MultiPoint", "coordinates": [[17, 48], [18, 49]]}},
        {"type": "Feature", "properties": {"kind": "airspace", "cat": "CTR", "name": "MY CTR", "hidden": True}, "geometry": SQ},
        {"type": "Feature", "properties": {}, "geometry": None}]}
    c = vm.own_collection("My", gj)
    ps = [f["properties"] for f in c["features"]]
    assert [(p["kind"], p["cat"]) for p in ps] == [("own", "area"), ("own", "line"), ("own", "point"), ("own", "point"), ("airspace", "CTR")]
    assert ps[1]["name"] == "Track" and ps[1]["remarks"] == "x" and "hidden" not in ps[4]
    assert len({p["srcId"] for p in ps}) == 5 and c["radimcom"]["source"] == "file"


def test_aerodrome_layout():
    g = vm.strip_poly([[17.0, 48.0], [17.01, 48.0]], 40)
    ring = g["coordinates"][0]
    assert g["type"] == "Polygon" and len(ring) == 5 and ring[0] == ring[-1]
    assert abs((ring[0][1] - ring[3][1]) * 110540 - 40) < 0.5   # 40 m across an east-west runway
    els = [{"type": "way", "id": 1, "tags": {"aeroway": "runway", "ref": "04/22", "width": "45", "surface": "asphalt"},
            "geometry": [{"lat": 48.1, "lon": 17.1}, {"lat": 48.12, "lon": 17.12}]},
           {"type": "way", "id": 2, "tags": {"aeroway": "taxiway"}, "geometry": [{"lat": 48.1, "lon": 17.1}, {"lat": 48.11, "lon": 17.1}]},
           {"type": "way", "id": 3, "tags": {"aeroway": "apron"},
            "geometry": [{"lat": 48, "lon": 17}, {"lat": 48, "lon": 17.01}, {"lat": 48.01, "lon": 17.01}, {"lat": 48, "lon": 17}]},
           {"type": "relation", "id": 4, "tags": {"aeroway": "aerodrome", "name": "Letisko", "icao": "LZIB"},
            "members": [{"role": "outer", "geometry": [{"lat": 48, "lon": 17}, {"lat": 48, "lon": 17.1}, {"lat": 48.1, "lon": 17.1}, {"lat": 48, "lon": 17}]}]},
           {"type": "node", "id": 5, "lat": 48.1, "lon": 17.1, "tags": {"man_made": "antenna"}}]
    c = vm.osm_tx_collection("SK", els)
    by = {f["properties"]["srcId"]: f for f in c["features"]}
    assert by["w1"]["geometry"]["type"] == "Polygon" and by["w1"]["properties"]["name"] == "04/22" and by["w1"]["properties"]["remarks"] == "asphalt"
    assert by["w2"]["geometry"]["type"] == "LineString" and by["w3"]["properties"]["cat"] == "apron"
    assert by["r4"]["properties"]["cat"] == "aerodrome" and by["r4"]["properties"]["ident"] == "LZIB"
    assert by["n5"]["properties"]["kind"] == "tx"


def test_ourairports_runway_strip():
    t = {"airports.csv": [{"id": "1", "iso_country": "SK", "type": "large_airport", "name": "A", "latitude_deg": "48", "longitude_deg": "17"}],
         "runways.csv": [{"id": "9", "airport_ref": "1", "airport_ident": "LZIB", "closed": "0", "le_ident": "04", "he_ident": "22", "width_ft": "148",
                          "le_latitude_deg": "48.1", "le_longitude_deg": "17.1", "he_latitude_deg": "48.12", "he_longitude_deg": "17.13", "surface": "ASP"}]}
    c = vm.ourairports_collection("SK", t)
    rw = [f for f in c["features"] if f["properties"]["kind"] == "aero"]
    assert len(rw) == 1 and rw[0]["properties"]["name"] == "04/22" and rw[0]["geometry"]["type"] == "Polygon"


def test_notes_set_and_remove(tmp_path, monkeypatch):
    monkeypatch.setattr(vm, "NOTES_PATH", str(tmp_path / "notes.json"))
    assert vm.load_notes() == {}
    assert vm.set_note("openaip:a1", " Home strip ", "") == {"openaip:a1": {"name": "Home strip"}}
    vm.set_note("osm:n5", "", "mast seen from the hill")
    assert vm.load_notes()["osm:n5"] == {"note": "mast seen from the hill"}
    assert "openaip:a1" not in vm.set_note("openaip:a1", "", "")


def test_fua_active_planned_and_past():
    now = 1795300000
    def feat(name, start, end, **kw):
        p = {"airspace": name, "startdate": start * 1000, "enddate": end * 1000, "type_code": "TRA", "airspace_type": "AMA",
             "lower_val": 5000, "lower_uom": "AMSL", "lower_ft": "ft", "upper_val": 125, "upper_uom": "", "upper_fl": "FL", **kw}
        return {"type": "Feature", "properties": p, "geometry": {"type": "Polygon", "coordinates": [[[17, 48], [17.1, 48], [17.1, 48.1], [17, 48]]]}}
    gj = {"features": [feat("LZTRA3", now - 60, now + 3600), feat("LZR10", now + 600, now + 7200), feat("LZD2", now - 7200, now - 1)]}
    c = vm.fua_collection(gj, now)
    got = {f["properties"]["name"]: f["properties"] for f in c["features"]}
    assert set(got) == {"LZTRA3", "LZR10"}
    assert got["LZTRA3"]["cat"] == "active" and got["LZR10"]["cat"] == "planned"
    assert got["LZTRA3"]["lower"] == {"v": 5000, "u": "ft", "ref": "MSL"} and got["LZTRA3"]["upper"] == {"v": 125, "u": "FL", "ref": "STD"}
    assert got["LZTRA3"]["srcId"] == "LZTRA3" and c["radimcom"]["source"] == "fua"


def test_fua_update_stores(tmp_path, monkeypatch):
    monkeypatch.setattr(vm, "VMAP_DIR", str(tmp_path))
    m = vm.fua_update(get=lambda: {"features": []}, now=1795300000)
    assert m["id"] == "fua_SK" and m["n"] == 0
