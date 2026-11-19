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

The **Sources** section of the [map settings](#map-settings) has one switch per VFO and decoder with positions, e.g.
`VFO A · VDL2 12`, `VFO B · HFDL 5` (the number = objects with a position); it shows / hides the source on the map
(remembered in the browser). A decoder that no longer runs but saw something in the last 6 hours stays as `… · history`.

Under **Sharing** (objects from other stations): **adsb.fi**, the aircraft the adsb.fi network (open data) sees around
the station, with the number received and shown. Its filter: **Radius** 25–250 NM (100 by default), **Refresh** every
5 / 10 / 30 / 60 s (10 by default; the server asks adsb.fi at most every 4 s, one request for all windows),
**Altitude from / to** (any by default), **At most** the 25 / 50 / 100 / 200 nearest (100 by default) or all, **only
aircraft the local decoders do not hear** (on by default; with it off they are joined into the local record) and **also
aircraft on the ground** (off by default). Positions older than a minute are left out; the trails of the last 15 minutes
are made from the positions asked. Aircraft only from shared sources take the **Sharing** column of Objects and Labels.

Ships under **Sharing**: **aisstream**, the ships the aisstream.io network reports around the station (a free API key
from aisstream.io, typed into the **API key** field and stored on the server in `data\mapkeys.json`). The server keeps
one WebSocket to aisstream while windows ask (closed 5 minutes after the last request) and keeps a ship 30 minutes after
its last report (positions come every few minutes). Filter: **Radius** 25–250 NM (50 by default), **At most** the
nearest N, **only ships the local AIS decoder does not hear** (on by default) and **only moving ships**. New
`GET /api/share/aisstream?dist=`.

Radiosondes under **Sharing**: **SondeHub**, the sondes the SondeHub network heard around the station (open data, no
key). Filter: **Radius** 50–400 NM (150 by default), **Heard within** 1 / 3 / 6 / 24 h (3 by default), **only sondes the
local SONDE decoder does not hear** (on by default) and **only sondes in flight** (a frame in the last 10 minutes). The
server asks SondeHub at most every 15 s and makes the trails (the last 6 h) from the records asked; a sonde falling
after the burst gets the parachute icon. New `GET /api/share/sondehub?dist=&last=`.

## Status row

Under the map: **Tracks** (the objects on the map, `of n` when some are hidden, and how many are joined from more
sources), **Precipitation** (the time of the radar frame shown, while it is on), **Clouds** (the time of the satellite
image shown, while it is on; the newest is asked for every 2 minutes), the mouse position (**LAT**, **LON** and **A/D**:
azimuth / distance from the station in the unit of the A/D map) and the **JSON** key (see [Feed format](#feed-format)).

## The map

- Aircraft as on their own maps: icon turned to the heading (the source's track; otherwise from the last two positions;
  otherwise the track from the adsb.fi / adsb.lol lookup), label below with the flight and type (or flight level).
- Ships and sondes with the icons and labels of the AIS and SONDE maps; ground stations (VDL2, HFDL) as ▲.
- Trail colour = source (ADS-B yellow, ACARS / VDL2 blue, HFDL orange, AIS green, SONDE pink); the selected object and
  its trail orange; an emergency squawk (7500 / 7600 / 7700) red; grey = no position for 15 minutes.
- **⚙ map settings** in the top right corner (see [Map settings](#map-settings)); the map keeps its view.

## Map settings

The **⚙** key in the top right corner of the map opens its settings (**Settings** shows beside it while open) in
sections that open and close with a click (which are open is remembered): **Sources** (**Aircraft**, **Radiosondes** and **Ships**,
each a part that opens with a click, one at a time: the local decoders, one switch per VFO and decoder with the number of
objects, and **Sharing** from other stations), **Map** (base map, OpenSeaMap, OpenAIP, own layers, A/D map, ADS-B range),
**Weather** (precipitation, clouds), **Aircraft**, **Radiosondes**, **Ships** and **Labels**. The settings are remembered in the browser (also from
the map opened alone in a new tab) and applied at once in all open tabs and windows of the same address.

- **Base map:** OpenStreetMap (the default), Esri dark grey, OpenTopoMap, Esri satellite, **Own tile address**
  (an XYZ address `https://…/{z}/{x}/{y}.png`) or **Plain colour** (no tiles, a background of the colour chosen, black
  by default), with **darken** (on by default: the tiles turned dark so the marks
  stand out). **OpenSeaMap** adds the sea marks, buoys and waterways on top (useful with AIS on rivers).
  **OpenAIP** adds airspaces, airports and navaids on top (opacity 10–100 %); it needs the free API key of an
  openaip.net account, typed into the **API key** field under the switch and stored on the server
  (`data\mapkeys.json`) for every window and computer. OpenAIP data: CC BY-NC.
- **Own layers:** **Add** a GeoJSON, KML or GPX file (KMZ: unpack the KML from it first; KML / GPX are turned into
  GeoJSON in the browser): points, lines and areas, with the name and description as a tooltip. The layers are stored
  on the server in `data\maplayers` (one folder for all VFOs, up to 20 MB each), so every window and computer has
  them; on / off, **colour** and **opacity** of each are per browser; ✕ deletes a layer for everyone.
- **Precipitation:** the RainViewer radar (no position sent, only the map tiles) on / off; **only the latest frame**
  or a **loop of the last 20 / 30 / 60 / 90 / 120 min** (frames every 10 minutes, the newest held a moment; 30 min by
  default); opacity 10–100 % (60 % by default). The time of the frame shown is in the status row under the map. A new frame
  is asked for a minute after the source should have it (every 10 minutes, then every minute until it comes); sharp up
  to zoom 7. Off by default.
- **Clouds:** the infrared image (10.5 µm) of the MTG satellite from EUMETSAT, a new one every 10 minutes; cold cloud
  tops show white over the map, the warm ground stays dark; an opacity slider as for the precipitation (10–100 %, 70 % by
  default). Off by default.
- **A/D map:** azimuth / distance rings around the station (MENU › SETUP › LOCATION) on / off: rings every 50 km or NM (every 100 thicker,
  labelled to the north) up to **50–400** (by 50; 200 by default), **km / NM**, and azimuth lines every 30° (labelled
  at the end); **Also every 10 km / NM and 10°** adds the fine rings and lines. Each group (50 · 30° and 10 · 10°) has
  its own **colour** and **brightness** (10–100 %). Off by default.
- **ADS-B range** on / off (on by default): the outlines of the farthest decoded positions per altitude band (any
  altitude, ≤ 30000, ≤ 20000, ≤ 10000 ft) from the ADS-B decoder (as RANGE on the ADS-B map); each band its own **line** colour and brightness (none, 10–100 %; 80 % by default) and
  **fill** colour and opacity (none, 5–100 %; 5 % by default).
  Asked again every minute.
- **Aircraft**, **Radiosondes** and **Ships:** each its own table (the same rows; the aircraft symbol only for aircraft),
  with a column for the **Selected** object, one for **Local** (the tracks of the local decoders)
  and one for **Sharing** (the tracks of shared sources, other stations, to come):
  - **Trails:** **Full (line)**, small dots of the **last 1 / 2 /
    3 / 5 / 10 min** (fading with age, the oldest the faintest), **Echo 1 / 2 / 3 / 5 min** (as a primary radar
    paints it: every 4 s a piece of an annulus centred on the station, 12 × 4 px, with afterglow), or **Off**. Full by
    default.
  - **Aircraft symbol** (local decoders / sharing): the aircraft icon, an outline **square □**, **circle ○** or
    **triangle △**, or an **asterisk \***.
  - **Icon size** 50–250 %.
  - **Prediction** 1 / 2 / 3 / 5 / 10 min or Off (3 min for the selected object, Off for the others by default): a thin
    line from the icon along the track (course) as far as the object gets in that time at its speed, with a tick every
    minute; none for an object that stands or has no position for 5 minutes.
  - **Icon colour**, **Trail colour** and **Prediction colour**: a colour picker, or **auto** (the default) for the
    map's own colours (the icons as on the decoder maps, the trail in the colour of its source, orange for the selected
    object).
    An object without a position for a while stays grey and an emergency squawk stays red.
  - **No position after** 1 / 2 / 3 / 5 / 10 min or **auto** (the default: 15 min) and **No position colour** (grey by default): the icon of an
    object without a new position for that long; the selected one stays orange, an emergency squawk red.
  - **Hide when no position for** 1 / 2 / 3 / 5 / 10 min, or **never** (the default): an object without a new position
    for that long disappears from the map; the selected object always stays.
- **Labels** (the same three columns): **Font size** 80–200 %, **Background** opacity 0–100 % by 5 % (85 % by default; a
  see-through one gets a dark text shadow), **Text colour** (a picker or auto) and **Show:** the items of the label (name / flight,
  registration, ICAO / MMSI, type, altitude, speed, climb, squawk, frequency, azimuth and distance from the station as
  `123°/45km` (in the unit of the A/D map, km / NM), source); an item an object does not have is left out, no item = no
  label. **Without units** shows the numbers alone (`FL330 · 597 kt · 235°/69km` → `330 · 597 · 235/69`).
- The selected object is **orange** (icon and trail). An aircraft with the squawk **7500, 7600 or 7700** has a **red
  icon 1.5× the set size**, and the positions sent with that squawk are red in its trail (dots; on the full line a red
  line over them); the squawk in its label is red too.
- A **label can be moved with the mouse** (drag it; a double click puts it back under its mark). The place is kept per
  object for that window only (also over a reload of the tab); other and new windows keep their own.
- A **thin line** joins each icon to its label, at the corner or the middle of a longer side of the label nearest to the
  icon.

## Lists

The panel **right of the map** has three sections that open and close with a click (remembered): **Aircraft**,
**Radiosondes** and **Ships**, each a table of the objects on the map with their number. Aircraft: flag, flight, type,
FL, speed (kt), distance from the station (in the unit of the A/D map) and the age of the position; radiosondes: serial,
type, altitude (m), climb (m/s), distance, age; ships: flag, name, type, speed (kt), distance, age. A click on a column
sorts by it, again the other way (remembered); the colour bar on the left is the source. A click on a row selects the
object and centres the map on it; the tooltip has its identifiers and sources. An aircraft with the squawk **7500, 7600 or
7700** opens the Aircraft section, is scrolled into view and stays on top in red while the squawk lasts and one minute
after (`EMERGENCY` beside the number).

## Details

A click on an aircraft, ship or sonde (on the map or in the list) shows its details at the top of that panel (under it on a narrow screen),
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
