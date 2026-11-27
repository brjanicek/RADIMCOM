[← README](../README.md) · [Documentation](README.md)

# Propagation and space weather (PROP)

The **PROP** key (group PROP) shows the **PROPAGATION** tab: space weather and an estimate of the HF bands at the station,
corrected by the ionosondes nearby and by what the FT8 and WSPR decoders of all VFOs hear. It is one tab for the whole
station (the same on every VFO). A small chip under the S-meter shows `SFI · Kp · A · R S G` in the colour of the worst
value (amber from Kp 4, R1, S1 or an M flare; red from Kp 5, G1, R3 or an X flare); a click on it opens the tab.

## Blocks

All parts are blocks in the style of SETTINGS › STATION:

- **SOLAR FLUX** (SFI and its 90-day mean, sunspot number, flares of the last 30 days), **X-RAY** (GOES, the last flare),
  **SOLAR WIND** (speed, Bt, Bz), **GEOMAGNETIC** (Kp now and its estimate every minute, A index = mean ap of the last
  8 three-hour periods), **NOAA SCALES** (R / S / G yesterday, now and the next 3 days), **HF AT THE STATION** (the model,
  its correction by the ionosondes and the stations used) and **SPORADIC E** (foEs of the ionosondes, Es heard by FT8).
- **Charts:** Kp for 3 days with the forecast (paler bars, a line at *now*), X-ray flux for 6 hours (log scale, classes
  A–X) and the **magnetogram of Kiruna** (X, Y, Z as the deviation from the 24 h median in nT; ΔX over the last 3 hours:
  under 150 nT quiet, 150–400 active, over 400 disturbed).
- **Kp bars:** observed 3-hour values in full colour. NOAA marks the intervals of today as *estimated*, but they are its
  forecast, so they are pale like the rest of the forecast. An interval that has begun and is not observed yet shows the
  highest 1-minute estimated Kp measured in it so far; a dashed line over the bar marks what NOAA forecast for it (also in
  the tooltip and in the line under the head: *this 3 h max … , NOAA forecast …*).
- **AURORA · OVATION · NORTH** (at the right, over the blocks and the charts): the aurora forecast map of NOAA for the
  northern hemisphere (OVATION model, about 30–90 minutes ahead) as NOAA draws it; a click opens it in full size. Above
  it, from the OVATION grid: the nearest place of the oval (10 % probability or more) with its distance and beam heading
  from the station (aurora scatter on 6 m / 2 m works with the antenna towards it), the probability over the station, the
  highest probability and the time of the forecast. The border is red with the oval up to 1000 km away, amber up to 1600 km.
- **HF BANDS · ESTIMATE NEXT 24 H:** a grid of the bands 160–6 m (with their MHz) against the next 24 hours in UTC, rows
  SUN (day / night) and MUF in MHz, the column NOW first. GOOD = the band under 85 % of the MUF, FAIR up to 105 %, else POOR.
  A corner mark in the NOW cell says that FT8 heard the band open (FT8) or that it is sporadic E (Es).
- **FT8 + WSPR · LAST 30′:** per band the number of stations heard by the FT8 and WSPR decoders of all VFOs in the last
  30 minutes and the farthest one (bar on a log scale 100–20 000 km), with an Es chip for sporadic E (500–2300 km on 6 m
  and up, or on 15–10 m while the F2 MUF is under the band).
- **FT8 BAND TEST:** when FT8 heard nothing in the last 30 minutes, this block asks for a test: choose the VFO and 15, 30
  or 60 s per band, START. The VFO goes to USB with FT8 on 160 m … 6 m, listens on each band from the start of the next
  15 s cycle, and fills the FT8 column; then it **returns to its frequency, mode and decoder** as before. A band out of the
  range of the dongle is skipped. The original state is kept in the browser while the test runs: if the page is closed
  during the test, the VFO is returned at the next start. A VFO running DAB, VDL2, ACARS or ISM is refused.
- **Alerts** of NOAA for the last 48 hours; a click opens the whole text.
- Under the blocks the sources with their age (NOAA SWPC, GIRO via KC2G, IRF Kiruna), each a link.

## How the estimate is made

It is a model, not a measurement:

- foF2 over the QTH from the solar flux (mean of today and the 90-day mean), the height of the sun relative to its noon,
  a winter anomaly of ±15 % and the storm (Kp 5 / 6 / 7 → ×0.85 / 0.75 / 0.65); MUF(3000) = 3 × foF2.
- D-layer absorption by day ∝ cos χ^0.75 · (1 + 0.006 · (SFI − 65)) · (7 / f)², stronger with R1 / R2 / R3 radio blackouts;
  Kp 6 and more lowers a band by one step, Kp 8 by two.
- **Ionosondes:** the MUF measured by the GIRO ionosondes up to 1000 km (at most 90 minutes old, confidence ≥ 25) against the
  model at their place and time gives a factor k (weighted by 1 / distance, limited to 0.5–2); it applies now and fades with a
  time constant of 6 hours. Sporadic E from the ionosondes: MUF(Es) ≈ 5.3 × foEs (one hop of ~2000 km) raises NOW on the
  bands from 14 MHz.
- **What is heard beats the estimate:** at least one FT8 station over 1000 km makes NOW at least FAIR, three or more (or Es)
  GOOD.

## Data

Downloaded by the running program only, refreshed when older than their interval, kept in `data\spacewx\`:

| Source | What | Interval |
|---|---|---|
| NOAA SWPC (<https://www.swpc.noaa.gov>, public domain) | Kp, F10.7, daily indexes, GOES X-ray, solar wind, scales, alerts | 5–60 min |
| NOAA SWPC OVATION | the aurora grid (only the cells north of 30° N are kept, `aur.json`) and the aurora map of the northern hemisphere (`aurora_north.jpg`, served to the page as `/api/spacewx/aurora.jpg`) | 10 min |
| GIRO ionosondes via KC2G (<https://prop.kc2g.com>, GIRO data CC BY-NC-SA 4.0, Reinisch & Galkin 2011) | MUF, foF2, foEs of the stations up to 1500 km | 15 min (the stations themselves report every 5–15 min, some lag hours) |
| IRF Kiruna (<https://www2.irf.se/maggraphs/>) | 1-minute magnetometer X, Y, Z; the last 24 hours are kept in `data\spacewx\kir.json` | 5 min |

The page asks the launcher (`GET /api/spacewx`), once for the whole station.

## DX cluster

The **DX** key beside PROP (group PROP) shows the **DX CLUSTER** tab: the spots of the DX cluster of the last 30 minutes.

- **Source:** the public DX cluster feed of [HamQTH](https://www.hamqth.com) (no login, no callsign, nothing about the
  station is sent). The launcher (`dxcluster.py`, `/api/dxcluster`) reads it at most once a minute for the whole station and
  keeps the spots in memory; a spot older than 30 minutes is dropped. The same DX on the same frequency (within 1 kHz) is one
  row: the newest spot, with **+n** for more spotters.
- **HF / VHF / UHF** (up to 30 MHz, 30–300 MHz, from 300 MHz) choose the list, each with its number of spots; the **filter**
  field narrows it (DX call, spotter, country, band or comment). Columns: UTC, frequency, DX, country and continent, mode,
  comment, spotter, age. A row lit red is the spot the VFO is tuned to.
- **A click on a row tunes the active VFO** to the spot with its mode: from the comment (CW, FT8 / FT4 and other digital
  modes → USB, SSB, FM, AM), else from the IARU Region 1 band plan (CW and digital segments, the FT8 / FT4 frequencies, FM on
  2 m / 70 cm, phone LSB under 10 MHz and USB above; a beacon `/B` → CW). A frequency the VFO cannot receive is only reported.
- **MARKS IN SPECTRUM** (on by default): while the DX key is on, the spots in the shown part of the spectrum are pink ▼ marks
  at its bottom edge with the DX call (above the CW skimmer's rows while it runs; spots older than 15 minutes fainter). The
  tooltip of a mark gives the country, mode, age, comment and spotters; a click tunes there.

