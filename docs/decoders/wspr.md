[← README](../../README.md) · [Documentation](../README.md)

# WSPR

WSPR beacons (Weak Signal Propagation Reporter, 2-minute cycles, down to about −28 dB SNR in 2.5 kHz) on the HF bands
and 6 m, decoded by **wsprd** of WSJT-X 2.7.0 (`lib\wspr\wsprd.exe`, built for RADIMCOM, see `installer\WSPR.txt`).

**DECODERS › WSPR** (DEC key):

- **ON** and the **band keys** 160 m, 80 m, 60 m, 40 m, 30 m, 20 m, 17 m, 15 m, 12 m, 10 m and 6 m (dial frequencies of WSPR,
  USB); a key stays lit while the VFO is on that band (also when it was tuned there another way).
- **Clock chip and SYNC:** the offset of the PC clock against NTP (pool.ntp.org, time.windows.com, time.google.com),
  green under 0.5 s, amber up to 1 s, red over it. WSPR (and FT8) need the clock within about ±1 s. **SYNC** sets the clock
  of Windows by it; without administrator rights Windows asks for consent. The same chip and SYNC are in the head of FT8.
- **Recording progress bar:** the 114 s of each cycle being recorded (from every even UTC minute), then *decoding*.
- **Table:** UTC, SNR (dB), DT (s), drift (Hz/min), MHz, call, locator, power (dBm) and the distance from the QTH;
  **LOG** writes a daily log (`data\logs\wspr\YYYY\MM\DD\wspr_YYYY-MM-DD.txt`; also switched in SETTINGS › DATA/LOG › LOGGING), **CLR** clears the table and the map.
- **Map** beside the table, the same as the FT8 one: the stations heard in their locator squares (green, beacons;
  the selected one red, faded after 30 minutes without being heard), labels with our SNR from zoom 5, the QTH, a dashed
  line to the selected station, a list of the stations (a click zooms to one), a popup with call, locator, km and azimuth,
  SNR, band, drift, power, the age and a QRZ link.

## How it works

- The audio of the VFO (USB, 12 kHz) is recorded from the start of every even UTC minute for 114 s into a WAV in
  `data\wspr\`, then wsprd decodes it with the depth of WSJT-X *normal* (`-C 500 -o 4`) at a lower priority, in under
  a second to a few seconds. The WAV is deleted after decoding; one that timed out is kept as `timeout_last.wav`.
- A cycle in which the VFO was retuned is skipped.
- The stations heard go to PROPAGATION too (FT8 + WSPR · LAST 30′), from all VFOs.
