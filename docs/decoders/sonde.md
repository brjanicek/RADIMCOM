# SONDE (radiosondes)

Decoder of weather balloon radiosondes (`sonde.py`), page **SONDE** in the DECODERS tab: position, altitude,
horizontal speed, direction and climb of the sonde, its flight path on a map, the burst.

## Use

1. Tune the VFO onto the sonde in **400–406 MHz** (the mode and filter do not matter, the decoder takes the baseband of
   the VFO; a few kHz off is fine, the **offset** in the status line shows how far the signal is from the dial).
   **403 MHz** in the header of the page tunes the VFO to the middle of the band in FM and switches the decoder on
   (the dongle moves there when 403 MHz is outside its band).
2. Switch **ON** on the SONDE page. RS41 and DFM run at once, in both polarities.
3. **SONDES**: the newest data of each sonde (serial, frequency, position, altitude, climb, km/h, direction, distance,
   azimuth / elevation from the station, RS41 temperature and humidity, GPS satellites, battery, state: rising, falling after the burst, landed, lost).
   A click on the serial or position opens the **MAP**: a balloon while it rises, a parachute after the burst (yellow ring
   at the highest point), the flight path in green, the station as a red dot; the □ key opens the map in a new tab
   (`?map=sonde`). **FRAMES**: every decoded frame. Every frame goes to the radiosonde log `data\logs\radiosonde\` automatically (no LOG key; see below).

Around Bratislava (station JN88NC): Wien Hohe Warte (11035, 56 km, RS41, launched at about 23:00 and 11:00 UTC),
Prostějov, Budapest (403.2 MHz), Poprad-Gánovce (400.6 MHz), Praha, Graz, Linz, Zagreb – all RS41.
DFM sondes are launched by the military (e.g. Záhorie, irregularly). A high sonde is heard 300–500 km away,
one on the ground only a few km.

## Launch sites on the map

The MAP shows the radiosonde launch sites in Europe (the **Launch sites** switch in its top right corner, remembered in
the browser). A click on a site: its name, WMO number and height, the sondes it launches with their frequency when known
(green = types RADIMCOM decodes), the launch times (UTC), the next launch and whether its sonde is probably in the air
now, the usual ascent / burst / descent, and its distance and azimuth from the QTH. **Green, pulsing** = launched within
the last 2.5 h (the sonde is probably still in the air), **amber** = a launch within the next hour, **grey** = otherwise.
The times of the list are the synoptic times; the balloon goes up about 45 min before them.

The list comes from [SondeHub](https://sondehub.org) (`https://api.v2.sondehub.org/sites`): the server downloads it when
the map first asks for it and keeps the European sites in `data\sonde_sites.json` for a week (all VFOs share it; without
internet the last saved list is used). The type names follow the SondeHub tracker (MIT).

### Own sites: `data\sonde_sites_extra.json`

Sites SondeHub does not list (e.g. military ones such as Senica) or changes of a listed site go into
`data\sonde_sites_extra.json` (not part of the package, kept on upgrade). It is a JSON list; each site needs `name`,
`lat` and `lon`, the rest is optional:

```json
[
  {"id": "senica", "name": "Senica (military)", "lat": 48.68, "lon": 17.37, "alt": 210,
   "types": [{"name": "DFM-17", "mhz": 403.63}], "times": ["0:06:00"], "note": "irregular launches"},
  {"id": "11747", "note": "Czech Army aerological station"}
]
```

- `id`: any text for an own site; the WMO number (or SondeHub id) of a listed site changes that site instead (here
  Prostějov gets a note), so its `name`, `lat` and `lon` can then be left out.
- `types`: names as in the list (`RS41`, `DFM-09`, `DFM-17`, `M10`, …) or `{"name", "mhz"}`.
- `times`: `"day:hh:mm"` in UTC, day `0` = every day, `1`–`7` = Monday–Sunday (synoptic time, launch ~45 min earlier).
- `note`: a line of text in the popup. Own sites are marked *(own)*.

The file is read at each opening of the map (no restart needed, reload the page); a broken file is reported under the
map. The coordinates in the example are only an illustration – use the real position of the site.

## Types

- **Vaisala RS41** (RS41-SG, -SGP, -SGM): GFSK 4800 Bd, a frame a second. Fully decoded: serial number, frame number,
  battery voltage, GPS time, ECEF position and velocity → latitude, longitude, altitude (above the WGS84 ellipsoid),
  horizontal speed, direction, climb; satellites. RS41-SGM (military) frames with the encrypted block are marked
  *encrypted*. **Temperature and humidity**: the raw sensor frequencies (block 0x7A) are converted with the
  calibration the sonde sends in 51 pieces of 16 bytes, one per frame; the decoder collects them per serial, so the
  temperature appears after up to 51 s of reception (pieces 3–6 needed; until then the T column shows how many pieces
  are known, e.g. *12/51*) and humidity right after it. Temperature as in rs41mod (rs1729): reference resistors →
  sensor resistance → polynomial; humidity with its simple empirical formula (approximate, a few %). The sonde type
  (RS41-SG / RS41-SGP) also comes from the calibration. Pressure of the RS41-SGP is not decoded.
  **Profile** in MAP, on the right of the map: the sonde chosen in the list above it (orange icon; Auto = the one decoded on the tuned frequency; a click on a sonde on the map chooses it, a click on the map goes back to Auto), altitude on the vertical axis, two panels side by side – temperature °C
  and humidity % (descent after the burst fainter); the right edge labels the altitude with the pressure of the
  standard atmosphere (hPa, orientation only). Hover shows altitude, time, T, RH, hPa. The altitude axis is fixed
  0–41 km and the plot fills the page height.
- **Radiosonde log** `data\logs\radiosonde\<YYYY-MM-DD>_<serial>.jsonl` (UTC date of the first frame): every frame
  of every sonde, written automatically whatever the LOG key, one JSON line (time, position, speeds, T, RH, sats,
  battery, frequency, VFO). After a server restart the sondes of the last 24 h of that VFO are read back with their
  flight paths (*from log* in SONDES); the list above the profile also offers older logged flights, drawn in the profile and on
  the map.
- **Flight prediction** in MAP (red dashed line from the last decoded point, every sonde in the air, also one no longer
  heard): +1 h, +2 h, +3 h after the launch, burst (yellow ring) and landing (✕, time UTC). Wind from the sonde's own flight path in 500 m layers (above the highest one heard the top
  layer is kept, below the lowest one its speed falls off to a half at the ground; a layer heard during the fall
  takes the wind of the fall), ascent rate from the last 5 min, burst assumed at 33 km until it happens, fall from the measured
  descent rate (mean of the last five steps), slowing down in thicker air (5 m/s at sea level before the burst), ground at 400 m. No weather model: only an estimate, best after the burst.
  The circle around the ✕ is the landing area: 60 more runs with the inputs scattered by their likely errors (wind of
  each layer, descent / ascent rate, burst altitude, ground), the circle holds 90 % of them; the label gives the landing
  time span and the radius.
- **Graw DFM** (DFM-06 / 09 / 17), *experimental*: 2500 Bd Manchester (1250 bit/s). Position, altitude, speed,
  direction, climb, frame counter. The serial number is not decoded yet: the sonde is shown as `DFM-<frequency>`.
- Meteomodem M10 / M20 and others are not decoded.

## How it works

- Channel filter ±10 kHz → FM discriminator (Hz) → for each type a low-pass (0.7 × symbol rate) → slicer whose
  threshold is the middle of the signal envelope (follows the offset) → bit clock (PLL of the packet decoder) → framers
  of both polarities.
- **RS41**: the 64-bit header (at most 4 wrong bits) starts a frame of 320 bytes (518 when the frame type is 0xF0),
  bytes LSB first. The frame is de-whitened with the 64-byte mask, then the two interleaved Reed–Solomon RS(255,231)
  codewords (GF(256), polynomial 0x11D, parity in bytes 8–55) correct up to 12 wrong bytes each
  (Berlekamp–Massey, Chien, Forney). The frame is a chain of blocks with a CRC-16 each; only blocks with a good CRC are used.
- **DFM**: the 16-bit header (32 symbols, at most 2 wrong) starts 264 bits: a configuration block of 7 and two data
  blocks of 13 Hamming(8,4) codewords, sent interleaved; one wrong bit per codeword is corrected. The last nibble of a
  data block is its number: 2 = latitude and speed, 3 = longitude and direction, 4 = altitude and climb; a position is
  published when 2, 3 and 4 of the same second are there.
- Burst: the sonde falls faster than 8 m/s more than 200 m below its highest point (above 5 km).
- The server keeps the last 300 frames and the flight path of up to 50 sondes (`/api/sonde`; not over a restart).

## Tests

`python -m unittest tests.test_sonde`: Reed–Solomon (up to 12 wrong bytes, too many), geodesy (ECEF round trip,
distance / azimuth / elevation), the RS41 frame (header, de-whitening, blocks, CRC, extended frame, corrected bit errors),
the whole chain on synthetic GFSK at 32 and 37.5 kHz baseband, inverted, weak (11 dB), with a tuning offset, DFM frames,
noise only.

Real signals: the I/Q recordings of the Signal Identification Wiki (RS41-SG and DFM-17, both on the ground)
decode completely: RS41 31 frames of 32 (serial, GPS time, position, battery; all blocks with a good CRC,
also at the 37.5 kHz baseband of RADIMCOM), DFM-17 a position every second for the 20 s of the recording.
Not yet tested on a sonde in flight.
