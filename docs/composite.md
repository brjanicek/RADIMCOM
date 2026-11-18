[← Back to README](../README.md)

# COMPOSITE map

One map with everything that has a position from the decoders running on **all VFOs**: aircraft from ADS-B, ACARS / VDL2
and HFDL, ships from AIS and radiosondes from SONDE. For example VFO A on VDL2, VFO B on HFDL and VFO C on the sondes, all
on one map. It is also a test of a format to merge the feeds of more stations (a community feed).

## Opening it

The **COM** key (group DECODE, under DEC) shows / hides the **COMPOSITE** tab next to DECODERS (one switch for all VFOs).
The ↗ key in the top right corner of the map opens the whole pane alone in a new tab (for a second screen); that tab asks
all VFOs itself.

## Sources

The **SOURCES** row has one key per VFO and decoder with positions, e.g. `VFO A · VDL2 (12)`, `VFO B · HFDL (5)`
(the number = objects with a position). A click shows / hides the source on the map (remembered in the browser).
A decoder that no longer runs but saw something in the last 6 hours stays as `… · history`.

## The map

- Aircraft as on their own maps: icon turned to the heading (the source's track; otherwise from the last two positions;
  otherwise the track from the adsb.fi / adsb.lol lookup), label below with the flight and type (or flight level).
- Ships and sondes with the icons and labels of the AIS and SONDE maps; ground stations (VDL2, HFDL) as ▲.
- Trail colour = source (ADS-B yellow, ACARS / VDL2 blue, HFDL orange, AIS green, SONDE pink); the selected object and
  its trail red; grey = no position for 15 minutes.
- **Precipitation** and **Trails** switches in the top right corner (see [Decoder maps](features.md#decoder-maps)); the map
  keeps its view.

## Details

A click on an aircraft, ship or sonde shows its details in the panel **right of the map** (under it on a narrow screen),
with the same lines as the popups of its own map (aircraft: flight, registration, ICAO, country, type, altitude, speed,
squawk, position, adsb.fi / adsb.lol; ship: as on the AIS map; sonde: as on the SONDE map), then **SOURCES (n)**: every
record joined into the object (VFO, decoder, its identifiers, number of messages, last time, *(history)*) and
**joined by …** (or *one record, nothing joined*). A click on the empty map drops the selection.

## Joining the same aircraft

Records of more VFOs and decoders are joined into one aircraft by:

1. the **ICAO address** (hex);
2. the **registration** (`D-AIAB` = `DAIAB`);
3. the **flight number**: ACARS and HFDL send it in the IATA form (`LH0123`), ADS-B in the ICAO form (`DLH123`); a table
   of ~100 airlines (European, large world and cargo carriers) turns IATA into ICAO, leading zeros do not matter;
4. the **squawk**, only an uncommon one (not 0000, 1000, 1200, 2000, 7000, 7500, 7600, 7700, …), only within 150 km and
   15 minutes.

Two different ICAO addresses are never joined. The newest position wins, the details are filled from the other records,
the trails are joined by time.

## History

Each VFO server takes the positions of its decoders every 30 s (also while the tab is closed) and keeps 6 hours of them,
trails up to 500 points, in `data\composite_<VFO>.json` (written every 2 minutes and at a normal stop, read at the start),
so the map has its data again after a server restart. Objects only in the history are marked *FROM HISTORY*.

## Feed format

- `GET /api/positions` of every VFO server: `{"t", "sources", "hist_sources", "items": [{"src", "id", "label", "lat",
  "lon", "alt_m", "t", "trail": [[lat, lon, t]…], "air" | "ship" | "sonde", "hist"}], "gs": [{"src", "id", "label",
  "lat", "lon", "t"}]}` (t = UNIX seconds, alt_m in metres; `air` = hex, reg, flight, type, desc, alt_ft, gs_kt, squawk,
  ground, track, gs, n).
- The **JSON** key downloads the merged feed shown (`"format": "radimcom-composite", "version": 1`, the joined objects
  with their sources).
