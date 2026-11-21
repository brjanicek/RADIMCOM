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

## Tracks, Tracker and Maps bars

Two bars over the bottom of the map: **Tracks** with **Show all labels** and **Hide all labels** (of the tracks on the
map now; new tracks follow the map settings), and under it **Tracker** with **Center** (the station in the middle of the
map, the zoom stays), **Show / Hide clouds**, **Show / Hide precipitations** (as in Weather of the map settings), **Show / Hide A/D map**,
**Find track** (a small window: the text is looked for in the flight, registration, ICAO, ship name, MMSI, call sign and
serial of the tracks, whole first, then a part; the track found is selected, its label shown and the map moved to it,
else an error shows in the window) and **Unlock** while the map follows a track. Each folds to the left into its name (◀ / ▶) and opens
over the whole width of the map (remembered).

Under them the **Maps** bar (Map memory): ten keys **MapMemo 1** … **MapMemo 10**, each recalling a stored setup of
the maps (the vector maps with what is shown and their styles, the base map, the A/D map, the ADS-B range and the
station); an empty memory is grey. **Map info** (OFF at first, per browser) switches the info of a vector maps point or
area under the mouse on and off; **Map edit** (OFF at first, per browser) switches the right click card of a point or area
(own name, note, Hide this object) on and off; the right click on a track keeps its Track menu either way. **Save actual** opens a small window: the memory and its name (MapMemo 1 … at first);
**OK** stores what the maps show now into an empty memory at once and asks before overwriting a used one. **Export**
saves the memories ticked in its window (all at first) into a `.json` file; **Import** reads such a file and lists its
memories, each with a checkbox and the memory it goes into (its own number at first), and asks before overwriting used ones. The memories
are kept in the browser (all its tabs and windows); the vector maps part of a recall goes to the server like any change
of the vector maps.

## Status row

Under the map (in full screen and in the map alone in a new tab; not in the small map of the tab): **Tracks** of all
kinds as `Total 45 (44/1) · Local 45 (44/1) · Sharing 0 (0/0)` (the objects on the map: all, from a local decoder, only
from sharing, each as live / no position, see *No position* in the map settings), how many are joined from more
sources, how many the map settings hide, and the track the map is locked on, **Precipitation** (the time of the radar frame shown, while it is on), **Clouds** (the time of the satellite
image shown, while it is on; the newest is asked for every 2 minutes), the mouse position (**LAT**, **LON** and **A/D**:
azimuth / distance from the station in the unit of the A/D map) and the **JSON** key (see [Feed format](#feed-format)).

## The map

- Aircraft as on their own maps: icon turned to the heading (the source's track; otherwise from the last two positions;
  otherwise the track from the adsb.fi / adsb.lol lookup), label below with the flight and type (or flight level).
- Ships and sondes with the icons and labels of the AIS and SONDE maps; ground stations (VDL2, HFDL) as ▲.
- Trail colour = source (ADS-B yellow, ACARS / VDL2 blue, HFDL orange, AIS green, SONDE pink); the selected object and
  its trail orange; an emergency squawk (7500 / 7600 / 7700) red; grey = no position for 15 minutes.
- **⚙ map settings** in the top right corner (see [Map settings](#map-settings)); the map keeps its view.
- **Full screen** key beside ⚙: the map with its lists and the status row over the whole screen (Esc or the key again
  leaves it).

## Map settings

**Restore default** at the right end of the settings bar (while the settings are open) puts all map settings and the
layout of the map (lists, their width and sorting, the bars) back to the defaults of `static/com_defaults.js`, in all
windows. The same defaults are used the first time the page opens in a browser; after that the browser keeps its own.

The keys in the top right corner of the map (settings ⚙, full screen, new tab) are one bar. **⚙** opens its settings (**Settings** shows beside it while open) in
sections that open and close with a click (which are open is remembered): **Sources** (**Aircrafts**, **Radiosondes** and **Ships**,
each a part that opens with a click, one at a time: the local decoders, one switch per VFO and decoder with the number of
objects, and **Sharing** from other stations), **Maps** (with the parts **Vector maps** with **Map sources** and **Maps** (one of the two open at a time), **Base map** with OpenSeaMap,
**A/D map**, **ADS-B range** and, at the bottom, **Station**, each opening with a click),
**Weather** (precipitation, clouds), **Aircrafts**, **Radiosondes** and **Ships** (each with the parts **Symbol**, **Label**
and **List**, one open at a time). All sections are closed the first time. In the small map of the tab the window takes
the right edge of the map (never taller than the map) and the full screen / new tab keys hide while it is open. The
settings and the open sections are remembered in the browser (also from the map opened alone in a new tab) and applied
at once in all open tabs and windows of the same address.

- **Station** (Maps, at the bottom): the icon of your location (circle, square, triangle, diamond, star, cross, house) and its colour.
- **Base map:** (the map zooms in to zoom 18) OpenStreetMap (the default), Esri dark grey, OpenTopoMap, Esri satellite, **Own tile address**
  (an XYZ address `https://…/{z}/{x}/{y}.png`) or **Plain colour** (no tiles, a background of the colour chosen, black
  by default), with **darken** (on by default: the tiles turned dark so the marks
  stand out). **OpenSeaMap** adds the sea marks, buoys and waterways on top (useful with AIS on rivers).
- **Vector maps:** airspaces, airports, navaids, reporting points and obstacles from openAIP, drawn on every decoder
  map under the tracks and kept on the server, so they work offline. They are downloaded in **Map sources** (inside **Vector
  maps**), on the tab of the source; each tab has **Use in maps** (all the maps of that source on or off, its tab
  struck through when off) and the number of points, lines and areas of its maps: on the **openAIP** tab type the free **API key** of an openaip.net account (stored in `data\mapkeys.json`); the list
  below has every country (**Find** filters it by name or code), the downloaded ones highlighted with the date of the
  download (⚠ when it is older than an AIRAC cycle, 28 days) and a checkbox that shows them on the map. ⬇ downloads a
  country into `data\vectormaps` (one file per country, a few seconds each), ↻ updates it, ✕ deletes it and
  **Update all** downloads all the downloaded ones again; the downloaded countries are at the top. The **OurAirports** tab works the same
  without a key: airports (large, medium, small, heliports, …) with their frequencies and runways, and navaids, from
  ourairports.com; a runway with both ends known is also drawn as a strip of its width under **Aerodrome layout** (public domain); the world files (about 20 MB) are downloaded at most once a day into
  `data\vectormaps\_ourairports` and cut per country. The **OpenStreetMap** tab downloads the transmitter sites of a country
  (masts, towers and antennas: broadcasting, radar, amateur radio, other radio and mobile phone, the last off at first)
  through the Overpass API (ODbL, no key; a big country takes a minute or two); they show as **Transmitters** in the
  tree, with the operator and the height. The same download brings the aerodrome layout mapped in OpenStreetMap
  (aerodrome boundaries, runways, taxiways, aprons and helipads) as **Aerodrome layout**, with the runway numbers and surface. The **FUA** tab downloads the airspaces activated today in Slovakia (TRA, TSA, R, D, … from the AUP / UUP of
  AMC Zvolen and the national areas) from the public map of LPS SR (gis.lps.sk/vfrm, no key) as **FUA (activated
  airspaces)** with the parts **Active now** (red) and **Planned (later today)** (orange, dashed), with the vertical
  limits and the time window (UTC); while the map exists the server downloads it again every 2 minutes and the maps
  shown follow. Information only: check the airspace with the ATS unit before flying. The **MEMORIES** tab shows the MEMORIES channels that have a location (LAT / LON) as
  **MEMORIES channels**, one part per group, with the frequency and mode; the map is made again whenever the channels
  change. On **Own files** **Add** stores a GeoJSON, KML or GPX file as a vector map: its areas, lines and points
  show under **Own files** in the tree (a file in this format keeps its kinds), the same name again replaces it. The tree in **Maps** (▸ opens a kind or a part) switches the
  kinds (**Airspaces**, **Airports**, **Navaids**, **Reporting points**, **Obstacles**: off at first) and their parts
  (CTR, TMA, R, D, … / international, civil, ultralight, … / VOR-DME, NDB, …) on and off; each part opens to its objects
  in groups by country (by map for MEMORIES and own files), each group with a checkbox for all its objects, and in them
  the objects one by one with a checkbox (the mouse over a kind, part or object shows the maps it comes from). **Names on the map** per kind (from a zoom on, names that would overlap are left out);
  **Only starting below** FL… shows only the airspaces whose lower limit is below that level. The mouse over an object
  shows its name, class, vertical limits, frequencies, own note and the map it comes from; a right click opens it with
  **Hide this object** and **Name** and **Note** to fill in (**Save** or Enter; an own name shown instead of the map's one, empty = the map's name, and a note; kept on the server in
  `data\vectormaps_notes.json`, apart from the maps, so an update or a new download keeps them; the right click on a track stays its Track menu) (**Show all** in
  the settings brings the hidden ones back). A click on the colour mark of a part opens its **style**: line (colour,
  width, solid / dash / long / dot / dash-dot, opacity, from which to which zoom) and fill (colour, opacity, from which to which zoom) of an area, symbol (colour,
  circle / square / diamond / triangle / cross or a symbol of the aeronautical charts: aerodrome paved / grass /
  military / closed, heliport, glider and ultralight site, VOR, VOR-DME, VORTAC, TACAN, DME, NDB, NDB-DME, compulsory and
  on-request reporting point, obstacle, wind turbine, transmitter mast; these are the defaults of the matching parts;
  size, opacity, **Shown** at every zoom or from / to a zoom) of a point, and its name (colour, size, from which to which zoom; **This zoom** takes the zoom the map
  has now); ✕ closes the style, **Default** returns to the built-in look. **Copy** remembers the whole look of the part
  (in this browser), **Paste** puts it on the part open (a point takes no line or fill,
  an area no symbol). What is shown, hidden and styled is stored in the map files on the server, the
  same in every browser and computer, and kept by Update. openAIP data: CC BY-NC. (The former own layers of the base map
  are gone: add such files on **Own files** of Map sources.)
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
- **Symbol** of **Aircrafts**, **Radiosondes** and **Ships** (the same rows; the symbol only for aircrafts; the colours
  Icon / Trail / Prediction / No position under one heading), with a column for the **Selected** object, one for **Local**
  (the tracks of the local decoders) and one for **Sharing** (the tracks of shared sources):
  - **Trails:** **Full (line)**, small dots of the **last 1 / 2 /
    3 / 5 / 10 min** (fading with age, the oldest the faintest), **Echo 1 / 2 / 3 / 5 min** (as a primary radar
    paints it: every 4 s a piece of an annulus centred on the station, 12 × 4 px, with afterglow), or **Off**. Full by
    default.
  - **Aircraft symbol** (local decoders / sharing): the aircraft icon, an outline **square □**, **circle ○** or
    **triangle △**, or an **asterisk \***.
  - **Icon size** 50–250 %.
  - **Prediction**: radiosondes by default the **landing predictor of the SONDE decoder** (path, burst, landing point and
    area, from the sonde's own winds and GFS; its colours under **Landing prediction**: **Ascent** (blue), **Descent**
    (red), **Landing area** (red) and **Burst ✱** (yellow)), or as aircrafts 1 / 2 / 3 / 5 / 10 min or Off (3 min for the selected object, Off for the others by default): a thin
    line from the icon along the track (course) as far as the object gets in that time at its speed, with a tick every
    minute; none for an object that stands or has no position for 5 minutes.
  - **Icon colour**, **Trail colour** (radiosondes: **Trail ascent** and **Trail descent**, before and after the
    burst) and **Prediction colour**: a colour picker, or **auto** (the default) for the
    map's own colours (the icons as on the decoder maps, the trail in the colour of its source, orange for the selected
    object).
    An object without a position for a while stays grey and an emergency squawk stays red.
  - **No position after** 1 / 2 / 3 / 5 / 10 min or **auto** (the default: 15 min) and **No position colour** (grey by default): the icon of an
    object without a new position for that long; the selected one stays orange, an emergency squawk red.
  - **Hide when no position for** 1 / 2 / 3 / 5 / 10 min, or **never** (the default): an object without a new position
    for that long disappears from the map; the selected object always stays.
- **Label** and **List** of each kind: the items are listed under the marks *Line 1:*, *Line 2:* … (label up to 5 lines,
  list 2); the items and the marks are dragged with the mouse (the grip ⠿ at the right), an item shows in the line of
  the mark above it; the items are shaded in turn.
- **Label** of each kind (the same three columns; the items differ: aircrafts flight, registration, ICAO, type, model,
  FL, speed, climb, squawk; radiosondes serial, type, frequency, altitude, climb, speed, temperature, humidity, state,
  predicted landing; ships name, MMSI, call sign, type, speed, course, navigation status, destination; all azimuth,
  distance, source, note): **Show label** (on by default: the label of a new track; one track: its Track menu),
  **Font size** 80–200 %, **Background** opacity 0–100 % by 5 % (85 % by default; a
  see-through one gets a dark text shadow), **Text colour** (a picker or auto) and **Show:** the items of the label (name / flight,
  registration, ICAO / MMSI, type, altitude, speed, climb, squawk, frequency, azimuth and distance from the station as
  `123°/45km` (in the unit of the A/D map, km / NM), source, **Note** (the note of the Track menu; last by default,
  movable as the other items)); an item an object does not have is left out, no item = no
  label. **Without units** shows the numbers alone (`FL330 · 597 kt · 235°/69km` → `330 · 597 · 235/69`).
- Objects only from shared sources (adsb.fi, aisstream, SondeHub) are drawn as the outline of their icon in its
  colour, not filled; those of the local decoders keep the filled icons.
- The selected object is **orange** (icon and trail). An aircraft with the squawk **7500, 7600 or 7700** has a **red
  icon 1.5× the set size**, and the positions sent with that squawk are red in its trail (dots; on the full line a red
  line over them); the squawk in its label is red too. While the squawk lasts its label is always shown (also when
  hidden by hand), bigger and red, with the squawk; after it the label is as before.
- A **label can be moved with the mouse** (drag it; a double click puts it back under its mark). The place is kept per
  object for that window only (also over a reload of the tab); other and new windows keep their own.
- A **thin line** joins each icon to its label, at the corner or the middle of a longer side of the label nearest to the
  icon.

## Lists

The border between the map and this panel can be dragged with the mouse (the width is remembered). The panel **right of the map** has three sections that open and close with a click (remembered): **Aircrafts**,
**Radiosondes** and **Ships**, each a table of the objects on the map, with **Show** (the kind on the map or not,
remembered; an emergency squawk is always shown) and the counts as in the status row
(`Total 45 (44/1) · Local … · Sharing …`, live / no position). The first column is always the
name (flight, serial, ship; with the flag unless switched off), over all lines of the object; the other columns are those
chosen in **List** of the map settings (by default aircrafts: type, FL, speed, distance, age of the position;
radiosondes: type, altitude, climb, distance, age; ships: type, speed, distance, age) in one or two lines. The objects
are shaded in turn. A click on a column sorts by it, again the other way (remembered); the colour bar on the left is the
source. A click on a row selects the
object, shows its label and centres the map on it; while an object is selected its section is open and its row is kept
in view (the list scrolls by itself); the tooltip has its identifiers and sources. An aircraft with the squawk **7500, 7600 or
7700** opens the Aircraft section, is scrolled into view and stays on top in red while the squawk lasts and one minute
after (`EMERGENCY` beside the number).

## Track menu

A right click on an aircraft, ship or sonde (on the map or in the list beside it) opens the floating **Track menu** at
the mouse, with the settings of that track only (over those of the map settings; kept for that window only, also over a
reload of the tab):

- **Hide label** / **Show label**.
- **Font**, **Prediction** and **Trail**: *default* (the map settings) or a value of its own.
- **Note**: up to 20 characters shown in its label (where the item Note is in Label of the map settings; last by default).
- **Lock display** / **Unlock display**: the map follows the track (the zoom stays); one track at a time, locking
  another unlocks the one before.
- **Reset this track**: back to the map settings.

The selects and the note change the map at once; the menu closes with a click elsewhere, Esc, Enter in the note or a
move of the map by hand.

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
