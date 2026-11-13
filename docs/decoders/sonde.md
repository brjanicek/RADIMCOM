# SONDE (radiosondes)

Decoder of weather balloon radiosondes (`sonde.py`), page **SONDE** in the DECODERS tab: position, altitude,
horizontal speed, direction and climb of the sonde, its flight path on a map, the burst.

## Use

1. Tune the VFO onto the sonde in **400–406 MHz** (the mode and filter do not matter, the decoder takes the baseband of
   the VFO; a few kHz off is fine, the **offset** in the status line shows how far the signal is from the dial).
2. Switch **ON** on the SONDE page. RS41 and DFM run at once, in both polarities.
3. **SONDES**: the newest data of each sonde (serial, frequency, position, altitude, climb, km/h, direction, distance,
   azimuth / elevation from the station, GPS satellites, battery, state: rising, falling after the burst, landed, lost).
   A click on the serial or position opens the **MAP**: a balloon while it rises, a parachute after the burst (yellow ring
   at the highest point), the flight path in green, the station as a red dot; the □ key opens the map in a new tab
   (`?map=sonde`). **FRAMES**: every decoded frame. **LOG** writes `data\logs\sonde_YYYY-MM-DD.txt`.

Around Bratislava (station JN88NC): Wien Hohe Warte (11035, 56 km, RS41, launched at about 23:00 and 11:00 UTC),
Prostějov, Budapest (403.2 MHz), Poprad-Gánovce (400.6 MHz), Praha, Graz, Linz, Zagreb – all RS41.
DFM sondes are launched by the military (e.g. Záhorie, irregularly). A high sonde is heard 300–500 km away,
one on the ground only a few km.

## Types

- **Vaisala RS41** (RS41-SG, -SGP, -SGM): GFSK 4800 Bd, a frame a second. Fully decoded: serial number, frame number,
  battery voltage, GPS time, ECEF position and velocity → latitude, longitude, altitude (above the WGS84 ellipsoid),
  horizontal speed, direction, climb; satellites. RS41-SGM (military) frames with the encrypted block are marked
  *encrypted*. Temperature and humidity are not decoded (they need the calibration sent in 51 pieces).
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
