# SONDE (radiosondes)

Decoder of weather balloon radiosondes (`sonde.py`), page **SONDE** in the DECODERS tab: position, altitude,
horizontal speed, direction and climb of the sonde, its flight path on a map, the burst.

## Use

1. Tune the VFO onto the sonde in **400–406 MHz** (the mode and filter do not matter, the decoder takes the baseband of
   the VFO; a few kHz off is fine, the **offset** in the status line shows how far the signal is from the dial).
   **403 MHz** in the header of the page tunes the VFO to the middle of the band in FM and switches the decoder on
   (the dongle moves there when 403 MHz is outside its band).
2. Switch **ON** on the SONDE page. RS41, DFM and M20 run at once, in both polarities.
   **MULTI** (on by default): every sonde signal in the visible part of the waterfall (inside 400–406 MHz, up to 6)
   gets its own decoder too, so several sondes are decoded at once without retuning. Their frequencies are listed above
   the SONDES table (`MULTI 402.000–404.000 MHz:` and one key per signal: frequency, type and serial once decoded,
   frames, level above the noise; green = frames decoded, blue frame = the VFO is on it). The VFO is not retuned.
   The search covers what the waterfall shows: zoom out or use a wider bandwidth to watch more of the band.
   How: once a second a max-hold spectrum of the dongle samples (1 kHz bins) finds signals at least 8 dB above the
   median noise and 4 kHz wide (the gaps of up to 10 kHz merged, so a strong M20 stays one); each signal gets a channel
   cut out by one FFT channelizer (overlap-save, the dongle rate / a power of two ≥ 30 kHz, flat ±12 kHz) and its own
   RS41 / DFM / M20 demodulator. A channel without a signal and a frame for 60 s is dropped. The signal the VFO is
   tuned to (±10 kHz) is decoded by the VFO only. While SONDE is on (with or without MULTI), the audio of the VFO is
   muted (a sonde is only noise to listen to; MUTE in the VFO list); switch SONDE off to listen. Runs in its own thread; ~7 ms of CPU a channel per 64 ms of samples.
3. **SONDES**: the newest data of each sonde (serial, frequency, position, altitude, climb, km/h, direction, distance,
   azimuth / elevation from the station, RS41 temperature and humidity, GPS satellites, battery, state: rising, falling after the burst, landed, lost).
   A click on the serial or position opens the **MAP**: a balloon while it rises, a parachute after the burst (yellow ring
   at the highest point), the flight path in green, the station as a red dot; the □ key opens the map in a new tab
   (`?map=sonde`). **HISTORY OFF / 1D / 7D** in the header of the page, beside SONDES / MAP / FRAMES (one choice for the table and the map): the flights of all VFOs from the
   radiosonde log of the last day / week as thin blue paths with their last point (tooltip: serial, type, frequency, time,
   highest altitude); a click opens the flight like a logged one. A sonde heard now is drawn only once, as itself.
   The choice is remembered in the browser, the list is read again every 5 minutes (`/api/sonde/history?days=1..7`).
   In the SONDES table the same choice adds these flights to the table in grey (last time,
   type, serial, frequency, last position and altitude, highest altitude, burst); a click opens the flight on the MAP. **FRAMES**: every decoded frame. Every frame goes to the radiosonde log `data\logs\radiosonde\` automatically (no LOG key; see below).

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

Decoded by rs1729's programs (see *How it works*): RS41, DFM, M10 / M20 (below), and **LMS6-403** (Lockheed Martin),
**iMet-54** (InterMet), **MRZ-N1 / MP3-H1** (Meteo-Radiy), **iMS-100 / RS-11G** (Meisei), **MTS01** (Meteosis),
**CF-06 / HT03** (Chinese): serial, position, altitude, speed, direction, climb and what the type sends of
temperature, humidity, pressure, satellites and battery. The descriptions below are of the formats (the Python parsers
kept in `sonde.py`).

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
- **Graw DFM** (DFM-06 / 06P / 09 / 09P / 17 / 17P, PS-15), *experimental*: 2500 Bd Manchester (1250 bit/s). Position,
  altitude, speed, direction, climb, frame counter, satellites, time (UTC of the sonde). The **serial number** comes in
  the configuration blocks: DFM-09 / 17 and PS-15 in two halves (decimal, e.g. DFM-23038743), DFM-06 whole in the
  channel after the null channel 0x5A / 0x5B (hex, e.g. DFM-612345). It is taken when it has come twice the same (a few
  seconds); until then the sonde is shown as `DFM-<frequency>` and then renamed. The channel of the serial gives the
  **type** (DFM06, DFM06P, PS15, DFM09, DFM09P, DFM17, DFM17P), and with it the **temperature** from the measurement
  channels 0–8 (reference resistor 220 kΩ DFM-06 / 09, 332 kΩ DFM-17, Steinhart–Hart) and the **battery** of DFM-09 / 17.
- **Meteomodem M20**, *experimental*: 9600 Bd biphase, one burst of ~0.12 s a second (on the waterfall: a short
  wide flash every second). Position, altitude, horizontal speed, direction, climb, battery, GPS time, frame counter.
  Serial as on the label, e.g. `M20-507-2-02967` (year and month of production, line, number). No error correction,
  only the checksum: a weak signal gives a position every few seconds. Needs a VFO bandwidth of **2.048 MHz or more**
  (at 1.024 / 1.536 MHz the channel has too few samples per symbol). Found on a real M20 on 403.5 MHz (2026-11-15);
  logs of older versions keep its raw name M20-C25C2E.
- **Meteomodem M10** (Trimble GPS), *experimental*: 9615 Bd, the same header and checksum as M20, 101 bytes.
  Position, altitude, speeds, climb, satellites, battery, GPS time, serial as on the label (`M10-805-1-20298`).
  Tested on synthetic frames only (no M10 heard here yet).
- **M10 / M20 temperature, humidity, pressure:** main sensor an NTC (Shibaura PB5-41E) in a divider of 3 ranges →
  resistance → Steinhart–Hart; humidity sensor temperature from the SMD NTC (2.2 kΩ). Humidity: M20 by DF9DQ's formula
  with the calibration word of the frame and the sensor temperature; M10 from the 555 counts of the capacitive sensor
  against its 55 % reference with rs1729's empirical cold correction (approximate). M20 with a pressure sensor also
  gives the **pressure** (hPa, in the T tooltip and FRAMES). Checked on the real M20 frame: 11.1 km,
  −58.3 °C, 219 hPa (standard atmosphere at 11.1 km: 220 hPa).
- Other types (RS92, iMet, LMS6, MRZ, Meisei …) are not decoded.

The M10 / M20 frame layouts, checksum, serial numbers, temperature, humidity and pressure and the DFM serial, type,
temperature and battery follow the decoders of **rs1729** (zilog80) (<https://github.com/rs1729/RS>: m10mod.c, m20mod.c, dfm09mod.c; the M20 humidity is DF9DQ's
formula from <https://github.com/einergehtnochrein/ra-firmware>), which radiosonde_auto_rx of
**Project Horus** uses (<https://github.com/projecthorus/radiosonde_auto_rx>); reimplemented in Python, no code
taken over.

## How it works

- **Since 1.0beta1 the frames are decoded by the decoders of rs1729** (zilog80, <https://github.com/rs1729/RS>,
  GPL v3; separate programs in `lib\sonde`, built by `installer/build_sonde.sh`, `sonde_ext.py`): RS41, DFM, M10 / M20,
  LMS6-403, iMet-54, MRZ-N1 / MP3-H1, iMS-100 / RS-11G, MTS01 and CF-06 / HT03. The baseband of the channel (the VFO
  channel and each MULTI channel) goes as float32 I/Q into all of them (`--IQ 0.0 --lpIQ --dc --json`); under 44 kHz
  at twice the rate (rs41mod loses frames at 37.5 kHz and fails at 32 kHz). The first one that decodes a frame stays,
  the others are ended; silent for 60 s, all of them listen again. Their JSON lines become the frames of the SONDE page
  (time: rs1729's GPS time − 18 s). Without samples for 10 s the programs end. RS92 is not run: it needs GPS
  ephemeris for a position.
- **IQ recording** for later analysis: `POST /api/sonde {"action": "rec_iq", "secs": 120}` records the VFO channel
  (what the decoders get) into `data\sonde_iq\<date>_<time>_<MHz>_<rate>.cf32` (complex64, ≤ 900 s);
  `python tests/sonde_replay.py <file>` decodes it again.
- The Python decoders below (RS41, DFM, M10 / M20) are kept in `sonde.py` for the tests and as a description of
  the formats; they no longer decode the signal.
- Channel filter ±10 kHz → FM discriminator (Hz) → for each type a low-pass (0.7 × symbol rate) → slicer whose
  threshold is the middle of the signal envelope (follows the offset) → bit clock (PLL of the packet decoder) → framers
  of both polarities.
- **RS41**: the 64-bit header (at most 4 wrong bits) starts a frame of 320 bytes (518 when the frame type is 0xF0),
  bytes LSB first. The frame is de-whitened with the 64-byte mask, then the two interleaved Reed–Solomon RS(255,231)
  codewords (GF(256), polynomial 0x11D, parity in bytes 8–55) correct up to 12 wrong bytes each
  (Berlekamp–Massey, Chien, Forney). The frame is a chain of blocks with a CRC-16 each; only blocks with a good CRC are used.
- **DFM**: the 16-bit header (32 symbols, at most 2 wrong) starts 264 bits: a configuration block of 7 and two data
  blocks of 13 Hamming(8,4) codewords, sent interleaved; one wrong bit per codeword is corrected. The last nibble of a
  data block is its number: 1 = second (ms), 2 = latitude and speed, 3 = longitude and direction, 4 = altitude and
  climb, 8 = date, hour, minute and satellites; a position is published when 2, 3 and 4 of the same second are there.
  Configuration block: channel nibble, then 6 nibbles: channels 0–8 are measurements (24-bit float: 4-bit exponent,
  20-bit value). The serial channel is the one after the null channel (data 0) or the highest one followed by C:
  A–D + C (DFM-09 / 17) and 7 / 8 + 0 (PS-15) carry a half of the serial (nibbles 2–5, nibble 6 = which half),
  DFM-06 (null channel 0x5A / 0x5B) the whole serial in nibbles 1–6 (port of rs1729's conf_out).
- **M10 / M20**: the 32-symbol header `10011001100110010100110010011001` (at most 2 wrong) starts the frame:
  bit = 1 when the first symbols of two neighbouring pairs are equal, MSB first. Byte 0 = length L (M20 0x45, M10 0x64,
  M10 with aux data 0x76), byte 1 = type (0x20 M20, 0x9F M10); the framer reads the length byte and collects L + 1 bytes;
  the checksum of M10 / M20 (rs1729's m10mod) is in bytes L−1, L over bytes 0..L−2.
  M20: altitude 0x08 (3 bytes, cm), east / north / up speed 0x0B / 0x0D / 0x18 (cm/s), GPS time of week 0x0F (s),
  serial 0x12 (3 bytes), frame 0x15, GPS week 0x1A, latitude / longitude 0x1C / 0x20 (µ°), battery 0x26 (× 3.3 / 255 V).
  M10: east / north / up speed 0x04 / 0x06 / 0x08 (1/200 m/s), time of week 0x0A (ms), latitude / longitude 0x0E / 0x12
  (360° / 2³²), altitude 0x16 (mm), satellites 0x1E, GPS week 0x20, battery 0x45, serial 0x5D (5 bytes), frame 0x62.
- Burst: the sonde falls faster than 8 m/s more than 200 m below its highest point (above 5 km).
- Bad GPS positions are dropped (the rest of the frame stays, FRAMES shows *position dropped* and why): fewer than
  4 satellites (after the burst a sonde often loses its fix and sends an extrapolated, frozen or random position),
  altitude under −100 m or over 45 km, a fall faster than 60 m/s + altitude / 250, a jump farther than
  2 km + 0.25 km/s from the last good position (after 30 jumps in a row the new place is believed). Also when a log is
  read back, so old flights are shown cleaned; the log files are not changed.
- The server keeps the last 300 frames and the flight path of up to 50 sondes (`/api/sonde`; not over a restart).

## Tests

Since the rs1729 decoders: the chain tests (RS41 at 32 / 37.5 kHz with a 3 kHz offset and at 14 dB, M20 and M10
band-limited at 37.5 kHz, MULTI with RS41 + M20) run through `lib\sonde` (skipped when it is not built), the JSON
mapping (`to_frame`: GPS time − 18 s, DFM without serial, no fix) and the lock to one decoder.
Before that, `python -m unittest tests.test_sonde`: Reed–Solomon (up to 12 wrong bytes, too many), geodesy (ECEF round trip,
distance / azimuth / elevation), the RS41 frame (header, de-whitening, blocks, CRC, extended frame, corrected bit errors),
the whole chain on synthetic GFSK at 32 and 37.5 kHz baseband, inverted, weak (11 dB), with a tuning offset, DFM frames,
noise only, M20 (a real frame and synthetic ones), M10, the DFM serial / type / temperature (DFM-17, DFM-06, PS-15), M10 / M20 temperature, humidity and
pressure (the real M20 frame), MULTI (two sondes at
once), the filter of bad GPS positions.

Real signals: the I/Q recordings of the Signal Identification Wiki (RS41-SG and DFM-17, both on the ground)
decode completely: RS41 31 frames of 32 (serial, GPS time, position, battery; all blocks with a good CRC,
also at the 37.5 kHz baseband of RADIMCOM), DFM-17 a position every second for the 20 s of the recording.
Not yet tested on a sonde in flight.
