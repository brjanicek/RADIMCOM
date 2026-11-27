# Changelog

## Ver. 1.2beta5

Test beta (GitHub branch `1.2beta5`; continues 1.2beta4).

### Changes

#### PROPAGATION

- **AURORA** block: the NOAA aurora forecast map of the northern hemisphere (OVATION), and from its grid the nearest part
  of the oval with its distance and beam heading from the station (aurora scatter on 6 m / 2 m), the probability over the
  station; the border amber / red with the oval up to 1600 / 1000 km. A click opens the map in full size.
- New layout of the top: the blocks over the charts at the left, the aurora map at the right over both rows.

#### COMPOSITE map

- **Photo of the selected aircraft** in its detail, from Planespotters.net (by the ICAO address or registration, with the
  photographer's name, a click opens it there; remembered in the browser for a week).
- A click on a row of the list selects the object without moving the map; a callsign heard by ATC speech to text selects
  its aircraft without moving the map either.
- STCA: the prediction line of an aircraft in conflict is 2 minutes long (was 3).
- The detail: the sources line cut with … (whole in the tooltip), the adsb.fi / adsb.lol links always whole; the
  identifiers in SOURCES wrap instead of being cut.

#### ATC speech to text

- **AI · ATC** block in SETTINGS › STATION under AUDIO (the voice after the demodulator → Whisper → the COMPOSITE map).
- The text comes sooner: a transmission ends after 0.4 s of closed squelch (was 0.6 s); the model uses 8 CPU threads
  (about 20 % faster).

#### General

- Tooltips stay open when the element under the mouse is drawn again (panels refreshed every few seconds).

### Fixes

- PROPAGATION, Kp chart: the intervals of today were drawn as measured although they are NOAA's forecast (a red Kp 5
  bar with Kp 0 measured). The forecast is now pale; a begun interval shows the highest 1-minute Kp measured in it, with
  a dashed line at what NOAA forecast.

## Ver. 1.2beta4

Test beta (GitHub branch `1.2beta4`; continues 1.2beta3).

### Main Features

- **ATC speech to text** (AUDIO › **ATC**, airband AM 118–137 MHz): each transmission (squelch open to closed) is
  transcribed by a local Whisper model fine-tuned on ATC radio, on the CPU, no cloud. The text runs as a subtitle in
  the AD window with the callsigns coloured; a callsign heard is matched to an aircraft of ADS-B / FR24 and selected on
  the COMPOSITE map. The airline telephony comes from OpenFlights (Open Database License). Optional download in the
  setup (about 1.7 GB) or `install_atc.bat`.
- **Local FR24 receiver** (SETTINGS › FR24 RECEIVER): the BaseStation stream (TCP 30003) of the station's
  Flightradar24 receiver (or any dump1090 box) as a source of aircraft: the COMPOSITE map source **FR24**, and with
  **FR24** ticked in DECODERS › ADS-B its aircraft join those decoded by the VFO (marked F, those only it hears cyan).
- **COMPOSITE map: STCA** (Short Term Conflict Alert) and **multiselect**: Alt / Ctrl + click adds aircraft, ships or
  sondes to a selection; the selected aircraft are listed with the separation of every pair (now and at the closest
  approach). STCA predicts every pair of airborne aircraft and warns of a pair that is or will be closer than both
  minima (line, rings, STCA list, blinking, sound); settings in the map settings, the STCA bar over the map. A help for
  watching, not an ATC tool.

### Changes

#### COMPOSITE map

- **ATC radar** design in map memory 4 (put once into an empty memory): dark plain background, range rings in NM,
  small square targets with radar echoes and a 1 min vector, a label without background (callsign / FL ↑↓ speed /
  type). Map memories now keep the look of the aircraft too (symbol, label, trails, vector, colours).
- Climbing / descending arrow right after the flight level in the aircraft label (350↓).
- Vector maps: the name of a point sits right under its symbol, whatever its size.
- New default settings for aircraft (a new browser or Restore default): the look of the ATC radar design and STCA on.

#### ADS-B

- **FR24** check box in the ADS-B card and a map option for the cyan layer of the aircraft only the FR24 receiver hears.

#### GRAVES

- **Size of the meteoroid** in the echo detail: line density from the duration or the SNR, magnitude, mass and size
  with its range (`meteor_size.py`).
- Detail PREV / NEXT step only onto echoes whose detail is still kept.

#### DAB

- Magnifier next to the song (NOW ON AIR): search it on **Spotify** or **Apple Music**.

#### ATU

- A station you tune away from (wheel, drag, digits) is no longer pulled back: a carrier within 300 Hz of where the
  gesture started is not taken ("ATU: kept (station left)").

#### RECORD / STATION

- The PLAY key opens the RECORDINGS tab (replaces RECS), its LED lit while open.
- SETTINGS › STATION: the audio chain shows TNF, APF and BIN in their places; RECORDER (REC / REC SQ, after the squelch
  or the DAB MP3) and REC IQ / PRE-REC (raw IQ) drawn where they take their samples.
- Memory tags over the spectrum: the tooltip only over the tag and its ▲ mark, not the spectrum between them.

#### Setup

- The tasks page says that an RTL-SDR dongle (or Airspy) never installed on this PC needs Zadig; before Zadig starts, a
  window explains what to do in it step by step.
- Optional: download the ATC speech to text (faster-whisper into `lib\whisper` + the model, about 1.7 GB); offered
  again when a new setup brings another Python.

## Ver. 1.2beta3

Test beta (GitHub branch `1.2beta3`; continues 1.2beta2).

### Changes

#### GRAVES

- **?** next to **i**: a sub-page of how each echo is classified, in the look of STATION – the rules of the meteor
  detector in the order they decide (head echo, aircraft, satellite pieces, slow satellites, sweeps, meteors), the
  satellite tracker with the orbital elements, and the weak detectors FAST, SAT·TLE and SAT·LINES.
- **Kind tags:** UNDER, OVER, PLANE, SAT and HEAD as coloured tags (the colours of the charts) in the ECHOES table, the
  title of the detail and the ? page. An aircraft found by SAT·LINES says so (a slow line, not a satellite).
- **Detail: ◀ PREV / NEXT ▶** (fixed at its left) open the echo before / after among those the table shows (source,
  kinds, minimum SNR).
- **Detail: a head echo outside ±500 Hz is shown whole** in the upper spectrum: its Hz widened to the head echo, the rest
  filled from the head echo spectrum (before, only its last tens of ms within the band showed).

## Ver. 1.2beta2

Test beta (GitHub branch `1.2beta2`; continues 1.2beta1).

### Main Features

- **IQ PLAYER:** an IQ file from the disk plays through the current VFO as a virtual dongle: waterfall, demodulation
  and all the decoders, as if live. Thanks to **Dano OM1ATS** for the idea.
- **NAVTEX decoder** (DECODERS › NAVTEX): maritime safety information on 518 / 490 / 4209.5 kHz and the HF MSI
  frequencies.
- **GRAVES: the detection of meteors, satellites and aircraft rebuilt on physics and statistics.** Tuning it is
  demanding: it builds on scientific work on meteor radar, bistatic radar and statistical decision, and on our own
  remarks from the live echoes.

### Changes

#### IQ PLAYER

- **IQ FILE…** in the RECORDINGS tab (and ▶ at an IQ recording) opens a file: WAV of SDR# / SDR++ / HDSDR / RADIMCOM
  (with the centre frequency in its `auxi` chunk or name), HackRF / PortaPack `.C16` with its `.TXT`, raw `.cu8`,
  `.cs8`, `.c16`, `.cf32`, SigMF, the names of gqrx and rtl_433. The sample rate is fitted to the VFO (a faster file
  decimated, a slower one upsampled).
- PLAY switches to the SPECTRUM tab; the bar above the tabs: play / pause, position (click to seek), LOOP, the file
  and its rate; **BACK TO VFO** returns to the dongle with the whole earlier setting (frequency, mode, gain,
  demodulator, decoders, everything).
- The VFO display shows the frequency as usual (the centre of the file when its name has one); the only sign of the
  player is a blue blinking **IQ** instead of the USB / network icon. No tuning range check while playing.
- SETTINGS › STATION draws the IQ file as the virtual dongle of the VFO.

#### NAVTEX

- SITOR-B (CCIR 476, FEC mode B) from the baseband of the VFO, any mode: AFC on the 170 Hz tone pair within ±3 kHz,
  bit clock, word sync, each character from its DX or RX copy; messages from `ZCZC B1B2B3B4` to `NNNN`.
- Frequency keys (tune USB 1.7 kHz below), filter, live text, LOG, the decoder in memories and in SETTINGS › STATION.

#### GRAVES

- **The physical bounds of each target** (bistatic Doppler at 143.05 MHz): an aircraft at most ~286 Hz off the
  carrier and ~6 Hz/s; a satellite near the carrier at least ~18 Hz/s (at most ~121 Hz/s); a meteor trail moves only
  with the wind. A drift decides a class only when it is beyond the bound by two standard errors (the drift measured
  with its uncertainty: bin quantisation and the correlation of the detector's frames).
- **Meteors no longer taken for satellite pieces:** a short ping on the line of a satellite is weighed by Bayes
  factors – its own drift (with the line or still like a trail), the chance of a meteor there from the station's own
  meteor rate and Doppler (learnt live) and the orbital elements. The same for a meteor that came where a satellite
  track was, and for a "satellite" track made of meteors at different Dopplers joined by the tracker.
- **Orbital elements (TLE) as evidence:** whether a satellite lit by GRAVES and over the station is predicted at the
  measured Doppler; the chance of that by accident is measured on shifted copies (near the carrier ~230 of ~470 lit
  satellites, so a short ping is not decided by TLE, a longer track is). The share of satellites without public
  elements is learnt from the identifications.
- **The head echo decides:** an echo with a head echo (the meteoroid itself, ≥ 0.5 kHz/s onto the trail's Doppler) is
  always a meteor. **Faint head echoes** are found too: the power summed along the lines ending at the trail
  (track-before-detect), against the noise just before; threshold set on noise alone (under ~1 false head in 1000
  echoes), ~3.5 dB more sensitive. The detail shows "faint … σ over the noise".
- **REC** (SETTINGS › RECORDINGS and the head of ECHOES): every echo of the chosen kinds (meteor / satellite /
  aircraft) to the RECORDINGS tab as MP3 (source GRAVES), optionally its IQ (±8 kHz) and the IQ of the whole band from
  PRE-REC; **SAVE** in the detail saves one echo.
- **Waterfall grid:** faint lines at the carrier and at steps of the Doppler shift, under the signal, from the start.
- The GRAVES page stays on the VFO where GRAVES runs (its history no longer disappears after switching the VFO).
- **Robust drift (Theil-Sen):** the drift of every echo, piece and track is the median of the slopes of pairs of its
  points (those at least half its length apart, as the Doppler is quantised to bins), not least squares, so the end of
  a head echo at the start of a trail or noise as it fades no longer makes a still trail look drifting (a
  "satellite"). Its standard error from the robust spread of the points (MAD).
- **Decay time τ of the trail:** fitted on the fall of its power after the peak (an underdense trail decays
  exponentially, τ = λ² sec²φ / 32π²D), with the noise taken out; the detail shows it and whether the decay is
  exponential (underdense) or not (overdense, fading). Measurable from about 0.15 s (the detector's resolution).
  Both ideas taken after a comparison with the open-source detector dhruva-meteor-detector.
- **Strong echoes no longer cut short:** a strong echo lifted the noise floor under itself (~8 dB in 0.3 s for a
  33 dB echo), so it ended early and its decay looked too fast. Under an echo the floor now rises at most 0.2 dB/s.

#### RECORDINGS

- GRAVES MP3 and IQ files and PRE-REC SAVE files are recognised (memory, source, length).

## Ver. 1.2beta1

Test beta (GitHub branch `1.2beta1`; continues the release 1.1).

### Changes

#### GRAVES

- **Slow satellites are no longer counted as meteors.** An echo drifting straight at 25 Hz/s or more for at least
  0.6 s, both its halves the same way, is a satellite (a meteor trail drifts only a few Hz/s with the wind). The drift
  is taken from all points of the echo, so a weak one gets it too. Echoes that start on its line within 10 s are its
  pieces: not counted, not reported again. Tuned on live echoes (satellites near the carrier −34 to −59 Hz/s, meteors
  up to ~17 Hz/s).
- **SAT·TLE far fewer false satellites:** z score 10 (was 7) and a median level of 1.5 dB along the streak; with
  thousands of lit satellites some curve fitted the noise every few seconds.
- **SNR of weak satellites:** SAT·TLE / SAT·LINES showed 6.0 dB for every one (taken from the capped spectrum); now the
  median level along the streak.
- **SAT·LINES:** a straight line near the carrier drifting 25 Hz/s or more is a satellite, not an aircraft.
- docs: how the AFC works.

## Ver. 1.1

What is new against 1.0 (tested in the betas `1.1beta1`, `1.1beta2` and the release candidates `1.1rc1` … `1.1rc4`).

### Main Features

- **RADIMCOM much faster:** each VFO server needs about half the CPU, the page no longer stutters, switching the VFO
  takes ~0.15 s instead of ~1.9 s (details under *Speed*).
- **AGC+ much better: smart clipping and LINEARITY.** The result of hours of testing and tuning on real signals of the
  short-wave bands: it drives the A/D to its top, judged by the mean clipping of the last second, and checks the tuner
  for intermodulation across its gain steps. A clearly better sensitivity for weak stations on short waves (on 40 m LSB
  about 30 dB of gain instead of 3.7 dB), better also on FM broadcast, DAB and airband AM. On by default.
- **DECODERS › GRAVES:** echoes of the GRAVES radar (143.050 MHz): meteors counted per hour and day with a yearly chart
  of the showers, head echoes, satellites identified from their orbital elements, aircraft looked up on adsb.fi, a fine
  waterfall of 1 Hz × 16 ms, the detail and sound of each echo, weak echoes (FAST, SAT·TLE, SAT·LINES).
- **Remote dongles over the network (rtl_tcp)** *(by Brano, [brjanicek](https://github.com/brjanicek))* with a
  Raspberry Pi server and its own SETTINGS page, and **SpyServer** as a source; **SETTINGS › SDR SOURCES** assigns the
  sources inside the running RADIMCOM and restarts only the VFOs that change.
- **COMPOSITE map** (COM key): everything with a position from the decoders of all VFOs on one map, the same aircraft
  joined; settings, lists, sharing (adsb.fi, aisstream.io, SondeHub), tracks and offline **vector maps** *(by Brano)*.
- **PROPAGATION** (PROP key): space weather and the HF bands at the station for the next 24 h, corrected by the
  ionosondes and by what FT8 and WSPR hear; **DX CLUSTER** (DX key).
- **New decoders:** **WSPR** (with a station map), **Q65 / JT65**, **BPSK** satellite telemetry (FUNcube family, AX.25),
  **MSK144** meteor scatter; **spots** of FT8 to PSK Reporter and of WSPR to WSPRnet.
- **SETTINGS › GENERAL › BACKUP:** the settings of the whole station to a ZIP and back, factory reset.
- **Audio:** **TNF** tracking notches, **APF** CW peak filter, **BIN** binaural, **DNR NR4**, **NTH › EXP › FAST** and
  the **ALC** card for weak speech, **HUM** without the echo.
- **PRE-REC:** the last minute of IQ in RAM; Alt+click on the waterfall plays what was there.
- **SATELLITES › SUN NOISE** (G/T on the Sun, SUN SCAN of the rotor pointing) and the **Moon for EME**.
- **SETTINGS › DEBUG:** where RADIMCOM spends its time, as text to copy.

### Changes

#### Speed

- **Each VFO server needs about half the CPU** (38–49 % → 15–26 % of one core): the channel mixer is ~100× faster,
  the waterfall FFT 3.5× faster.
- **The page no longer stutters:** drawing the status of the VFOs took ~47 % of the browser's time, now ~3 %.
- **Switching the VFO ~1.9 s → ~0.15 s**; a row of the main waterfall 1.44 → 0.16 ms.
- **SETTINGS › DEBUG** (`static/debug.js`, `dbgstats.py`): where RADIMCOM spends its time – in the page (frames,
  functions, requests) and in the servers (CPU of every process and thread, with its lines of Python) – as text to copy.

#### Gain: AGC+, WF GAIN COMP, A/D

- **AGC+ smart clipping.** AGC+ no longer keeps an A/D headroom target (about 15 dB on HF, which left the A/D mostly
  unused: 2.7–3.7 dB of gain on 80 m / 40 m, the band's noise only 6–10 dB over the A/D's own noise). It drives the A/D
  to its top: the gain climbs until samples hit full scale now and then, and it is judged by the **mean clipping of the
  last second** (limit 0.1 %), not by single blocks – a block clipping 0.5 % now and then does not cut it; only one block
  over 10× the limit (at least 1 %) does. With the clipping under the limit it **probes the next tuner step**; a probe
  that goes over returns at once to the step before, and the same step is tried again after 20, 40, 80 … s (at most
  every 5 min), so on a steady band it settles. When the band gets quieter (headroom 3 dB more and 4× less clipping for
  10 s) it climbs again at once. On 40 m LSB it now sits at about 30 dB of gain with the band's noise 22–28 dB over the
  A/D's – the weak stations clearly better. Together with the audio **NTH** expander and, where needed, **DNR**, such
  weak signals get much more readable. Listening tests show it better also on FM broadcast, DAB and airband AM.
  "Gain wasted" still stops the climb; ADS-B keeps the headroom of its pulses.
- **AGC+ is on by default** for every VFO with its own dongle except SpyServer and rtl_tcp sources (a VFO where it was
  switched off keeps it off). The presets CONSERV., CAREFUL, MODERATE and BOLD are gone (they set too little gain); a
  VFO saved with one of them gets the new defaults.
- **AGC+ LINEARITY** (`imd.py`): intermodulation of the tuner that does not clip the A/D (phantom stations) is found by
  comparing the spectra at two neighbouring gains, line by line: a real signal moves with the gain one to one, a
  product about three times as much. A probe up with intermodulation goes back down and holds a ceiling under it (2 min,
  doubled each time on the band, 15 min max, lifted at once when the strongest stations fade); at the top a step down
  is tried now and then.
- **WF GAIN COMP** (`wfcomp.py`, GAIN COMP in the waterfall settings, on by default): the waterfall and spectrum rows
  corrected for the tuner gain, so the colours do not jump when AGC+ or a hand changes the RF gain (each real step
  measured on the noise floor; none with tuner AGC).
- **AGC+ card:** the numbers stand in fixed cells refreshed twice a second, the warning (one line) and the *why* line
  (two lines) keep their place, the whole text in the tooltip, so nothing below jumps; a warning is one short line,
  "more gain buys nothing" is grey information, only the warnings to act on are amber. The A/D values of the VFO window
  and of the AGC+ card are the same (99.9 % peak, clipping of the worst block of 2 s).
- **A/D value not red for a few clipped samples:** the dBFS value of the VFO window and the AGC+ bar turned red when a
  single sample hit full scale in the last 2 s (an impulse). Red now only over the AGC+ clipping limit; a few clipped
  samples under it are amber, with their share in the tooltip.
- **RF gain under the waterfall speed bar:** under the WF label the tuner gain of the active VFO (*RF*, the number in dB,
  AUTO, green with AGC+; the full text in the tooltip).

#### Audio

- **TNF, APF and BIN keys** (AUDIO group after HUM, `audiofx.py`). **TNF**: tracking notch filters, **Shift+click** on
  the spectrum or waterfall sets a notch on a carrier there (a second click removes it, up to 16, width 10–500 Hz in the
  TNF settings, CLEAR removes all); the notches sit on the RF frequency in the baseband, so they stay on the carrier when
  the VFO is retuned, and are drawn as marks in the spectrum. **APF**: audio peak filter for CW, two band-pass sections
  at the 700 Hz pitch, 50 / 100 / 200 Hz wide. **BIN**: binaural, the audio split by a Hilbert filter into a 90° phase
  difference between the left and right ear, so a signal seems to come from a place in the head (CW, SSB, AM;
  headphones).
- **DNR: WIENER and NR4** (SETTINGS › AUDIO › DNR, `nrx.py`): **NR4** is spectral bleaching after libspecbleach (noise
  estimated by speech presence probability, decision-directed SNR, smoothed gains; less music noise). **WIENER** distorts
  the voice less: the strength of a level comes mostly from the floor (5.7–30 dB, was 6–24 dB) and much less from
  overestimating the noise (1.0–1.45 ×, was 1.0–2.35 ×); at the same noise reduction the voice is 1.3–1.9 dB cleaner.
  Default level 3 (was 5; a saved level stays). The mouse wheel over the DNR key changes the level (1–10); its tooltip
  shows the algorithm and the level and stays up while the wheel changes it.
- **NTH › EXP › FAST** (SETTINGS › AUDIO, on by default together with AUTO) for weak signals, where the expander often
  turned the speech down: the voice detector smooths less, the audio goes out ~8 ms later so the opening comes before the
  syllable (look-ahead), it stays open down to 1/3 of the threshold (normally 1/2), holds at least 250 ms and closes in
  150 ms (normally 80). Simulated weak speech (−3 / 0 dB over 6 kHz): speech turned down 100 % → 9 %, 35 % → 1 %. *Now*
  shows FAST. It also switches the ALC to FAST.
- **ALC card** (SETTINGS › AUDIO, under NTH, per VFO): **FAST / SLOW** and their *hold* and *rise* times (hold
  0–2000 ms, rise 100–5000 ms, DEFAULT). **FAST is the default** (hold 400 ms, rise 100 ms; SLOW: 600 ms, 1000 ms;
  before: 400 ms, 1500 ms), so weak speech after a loud part is loud again sooner (−10 dB back in ~0.4 s with FAST,
  ~1.4 s with SLOW; before ~2 s). The title and the tooltip of the ALC key say SLOW / FAST.
- **HUM without the echo:** the former comb notched all ~60 multiples of 50 Hz up to 3 kHz at once and rang every 20 ms
  in the speech it took out (an echo, −12 dB). Now each harmonic is followed separately and notched only while it is a
  steady tone over 1 s standing 6 dB over the other harmonics – typically 2–8 notches, coming and going smoothly. Echo
  −28 dB, the hum 20–28 dB down under speech (was ~9 dB), speech without hum untouched, ~3 % of a CPU core. Tests
  `tests/test_hum.py`.
- **ATU: CW zero beat.** The ATU key tunes a CW signal near the dial onto the 700 Hz pitch (max-hold of 0.2 s frames,
  ±400 Hz search, parabolic interpolation), as it does AM / SSB carriers.
- **SETTINGS › VFO › AUDIO** as a chain of blocks in the order of the audio (NB, HUM, DNR, ALC, NTH, AFI, HPF / LPF,
  ASQ, tone squelch; TNF, APF and BIN with a block each); a block whose key is off is greyed and can still be set.

#### Sources: rtl_tcp, SpyServer, SDR SOURCES

- **Remote dongles over the network (rtl_tcp)** *(by Brano, [brjanicek](https://github.com/brjanicek))*: a VFO can take
  its RTL-SDR dongle over USB or from another computer, e.g. a Raspberry Pi with several dongles. Driver `rtltcp`
  (`rtltcp.py`): the VFO tunes, sets gain, RTL AGC, ppm and bias-tee over the network and gets the same raw I/Q as from
  USB, so VDL2, DAB and ISM work too. A dongle on a server with rtltcp-manager is addressed by its serial
  (`SDR1@192.168.1.50`), any plain rtl_tcp server as `host:port`.
- **Raspberry Pi server: `rpi/install_rtltcp.sh`** for a clean Raspberry Pi OS (any Debian): builds the rtl-sdr-blog
  driver (V3, V4, generic) into /opt/rtlsdr-blog without touching a librtlsdr already there, blacklists the DVB-T driver
  and installs the service **rtltcp-manager**: one rtl_tcp per dongle by serial on a fixed port (1234, 1235 …), dongles
  plugged in later start by themselves, an rtl_tcp whose client stopped answering is restarted. Its HTTP side (port 1233)
  lists the dongles and the state of the server.
- **SETTINGS › RTL_TCP SERVER:** one card per server with name, IP, link (LAN / WIFI with SSID, signal and rate), ping,
  CPU (load, clock, temperature), RAM, disk, power (Raspberry Pi under-voltage / throttling), time against this PC,
  graphs of the last 10 minutes, the dongles with their VFO, frequency, data rate and share of the samples arriving, and
  RESTART (one dongle), RESTART SERVER, SHUTDOWN and UPDATE (installs the rtltcp-manager shipped with RADIMCOM).
- **VFO window: network icon** for rtl_tcp and SpyServer instead of the USB symbol; **orange** when the network does not
  carry all the samples (rtl_tcp drops the rest silently; also in the VFO log), **red** when the server is not
  reachable, a **blinking lightning** when the server has under-voltage or overheats.
- **SpyServer source:** an own client of the Airspy SpyServer protocol (driver `spyserver`); a server with a narrow band
  (e.g. an HF+ with 228 kHz) is upsampled and the VFO keeps its tuning inside the real band; on a shared server the gain
  is the server's. A **click on the network icon** of a SpyServer VFO pauses it (disconnects: the client slot is free)
  and connects it again; the tooltip shows the data rate and the owner and country of the server (from the Natural
  Earth borders in `countries.json`).
- **SETTINGS › SDR SOURCES:** the SDR setup is now a page of the running RADIMCOM in the STATION style (the *SDR setup…*
  item of the tray menu is gone; the Start menu item and `--setup` open this page). Sources (USB devices with their USB
  name, index, tuner and the VFO using them; rtl_tcp dongles; SpyServers) are dragged onto VFO A–D; network servers are
  told apart by their protocol, and **DIRECTORY** lists the public SpyServers that answer (table and map, by the distance
  from the QTH, filters, a click adds one). **APPLY restarts only the VFOs that change**, the others keep running; a VFO
  keeps its settings with its source, also when it moves to another letter. EEPROM serial numbers with STOP USB VFOs.
- **Each dongle keeps its PPM and upconverter LO** (by serial number, `data\dongle_cal.json`): taken off a VFO and put
  on one again, or two VFOs swapping their dongles, it gets its own values back instead of 0. PPM typed there also goes
  into the dongle profile of the VFO settings.
- **No dongles assigned yet** (new installation, factory reset): RADIMCOM.exe opens the **SDR setup** by itself, in a
  window in the middle of the screen. Cancelled without saving, RADIMCOM starts with the four VFO windows, VFO A dark
  and silent (NO SDR); SETTINGS › SDR SOURCES assigns the dongles later.
- **SETTINGS › VFO › RX CHAIN** (was SDR DONGLE, with the former ADVANCED page): cards in the order of the signal like
  the STATION scheme – antenna, upconverter, LO, bias-tee, **Source** (local device, chained VFO, rtl_tcp or SpyServer
  with address and device), dongle, tuner gain, RTL2832 gain, bandwidth, ppm, DC, SP, S-meter, AGC+ with its diagram –
  as narrow blocks with an arrow before each; where a line wraps, a wire leads to the start of the next line. With a
  network source the antenna, upconverter LO and bias-tee are greyed, with a shared SpyServer the gain too. The *Dongles
  and VFOs* table and the *Settings for* card are gone.

#### Decoders

- **Decoders: one at a time** per VFO: switching one on (its ON key, a band key, a memory, ISM) switches the running one
  off. The DECODERS tab names the running decoder in green (*DECODERS FT8*), its key has a lit green bar on top also
  while another page is open, and the tab opens on the page of the running decoder.
- The band key of the frequency the VFO is on stays lit (FT8, WSPR, WEFAX, SSTV, ACARS, AIS, ADS-B, ISM), also when the
  VFO was tuned another way.
- **WSPR decoder** (DECODERS › WSPR): WSPR beacons on 160 m – 6 m by wsprd of WSJT-X 2.7.0 (`lib\wspr\wsprd.exe`, built
  for RADIMCOM); band keys, a progress bar of the 2-minute recording, table (SNR, DT, drift, call, locator, power, km),
  LOG and a **station map** like that of FT8 (□ opens it alone in a new browser tab). See docs/decoders/wspr.md.
- **Q65 / JT65 decoder** (DECODERS › Q65/JT65, `q65.py`): the slow weak-signal modes of HF, 6 m scatter and EME, decoded
  by jt9 of WSJT-X 2.7.0 (`lib\jt9`, built by `installer/build_jt9.sh`, its licences in `installer/JT9.txt`). The USB
  passband is recorded for the whole T/R period from its UTC start (Q65 15–300 s with submodes A–E, JT65 60 s A–C) and
  decoded at its end. Band keys with the usual dial frequencies and modes, a progress bar of the period, PC clock check
  with SYNC, table and daily log. See docs/decoders/q65.md.
- **BPSK decoder for satellites** (DECODERS › BPSK, `bpsk.py`, `funcube.py`): telemetry at **1200, 2400, 4800 or
  9600 Bd** from the baseband of the VFO, in any mode. It finds the carrier within **SEARCH** ±3 / ±6 / ±12 kHz (the line
  of the squared signal) and follows its Doppler, with or without the Doppler correction of the satellite tracking.
  Differential detection decodes DBPSK and NRZI alike, and every framing is tried on the same signal: **AO-40 FEC** of the
  FUNcube family (FUNcube-1 AO-73, Nayif-1 EO-88, JY1Sat JO-97) with the realtime telemetry of FUNcube-1 above the table,
  and **AX.25** (HDLC with NRZI), plain or with the G3RUH scrambler. Satellite keys, the bytes of each frame, daily log.
  Checked on a recording of FUNcube-1 (every frame decoded); AX.25 only on generated signals so far.
  See docs/decoders/bpsk.md.
- **MSK144 decoder** (DECODERS › MSK144, `msk144.py`): meteor scatter as WSJT-X MSK144 on 6 m, 2 m, 1.25 m and 70 cm
  (band keys 50.260 / 50.280 / 144.150 / 144.360 / 222.100 / 432.360 MHz, USB). Own decoder: each ping found by the
  squared spectrum, its frame located by the two sync words, frames of a long ping averaged, LDPC (128,90) by belief
  propagation and CRC-13 (the code tables in `msk144_ldpc.py` from WSJT-X, GPL-3). No time slots and no PC clock needed;
  the same message within 10 s is one row (× count). A 0.3 s ping decodes at about 5 dB SNR in 2.5 kHz in simulation;
  short messages and free text are not decoded. Untested on the air.
- **Spots to the networks** (SETTINGS › GENERAL › SPOTS, `spotting.py`): FT8 decodes to PSK Reporter, WSPR decodes to
  WSPRnet. Off until a callsign is entered and a network switched on; nothing is sent while the station location is
  still 0 / 0. Spots that could not be sent go to the daily log `logs\spots`.
- **PC clock against NTP** in the heads of FT8, WSPR and Q65 (green / amber / red by the offset) with **SYNC**, which sets
  the clock of Windows (with the administrator consent of Windows when needed).
- **WEFAX:** the image can be dragged sideways (wrapping round), the following lines keep the alignment; a saved image is
  saved again after a shift or a slant fix.
- **HFDL:** the status lines moved under INFO, so the map gets more room.
- **ISM devices in columns, distance estimate:** the DEVICES view has a column per kind of device (weather, TPMS, remote,
  sensor, …) with compact cards in the look of STATION; the kind filter moved to the top line. Each card shows a rough
  distance estimated from its SNR (log-distance path loss from a ~3 mW transmitter, e.g. 30 dB ≈ 85 m, 10 dB ≈ 350 m).

#### GRAVES (meteors, satellites, aircraft)

- **DECODERS › GRAVES** (`meteor.py`) in three tabs **LIVE / STATS / SETTINGS**, the counts HOUR, PREV,
  60 MIN, TODAY, PLANES, SATS beside them. Echoes of the French space radar GRAVES (143.050 MHz): the spectrum of the VFO
  baseband (~4–8 Hz bins, every ~30 ms) within ±500 Hz of the carrier, each frame normalised by its median, a slow floor
  per bin (a steady carrier does not trigger), threshold 10 dB (THR) with hysteresis on the echo's own bins. Underdense
  (< 1 s) and overdense echoes are counted per UTC hour with the time monitored in `data\meteors_<VFO>.json` (400 days).
- **Fine waterfall** (`meteor_fine.py`): the meteor band in cells of 1 Hz × 16 ms, sharp in time and in frequency at once
  (a reassigned spectrogram of 64 ms and 1 s frames, Auger & Flandrin). Width **±250 Hz**, **±500 Hz**, **±1 kHz** (a
  part of the satellite spectrum) or **±8 kHz**, time **10 s … 1 h**; one column per screen pixel (every 16 ms cell up to
  3 minutes); it scrolls smoothly. ⚙ colours and levels like the main waterfall; a new installation starts with ±500 Hz,
  1 minute, Classic colours, dark under 10 dB, full colour at 25 dB. The ±250 / ±500 Hz views are ~1.3 s behind the
  sound (a 1 s frame needs half a second after each moment).
- **Chart** under the waterfall: the strongest bin over its floor with the threshold dashed, THR in a frame; the mouse
  wheel over it moves THR by 0.5 dB. Satellites at the same time each in a lane of their own.
- **Satellites** (`meteor_sat.py`): a ±8 kHz spectrum always runs beside the meteor detector. A long, smooth streak that
  drifts faster than an aircraft or runs further from the carrier than an aircraft can is a **SAT** echo: one row per
  pass, its pieces not counted as meteors. **Which satellite:** its bistatic Doppler GRAVES → satellite → station is
  compared with every satellite with public orbital elements (CelesTrak *active*, *visual*, *stations*,
  `data\graves_tle.txt`, downloaded once a day, plus the elements of SATELLITES), with the receiver offset fitted. Name,
  NORAD, AZ / EL / distance and the fit; debris and objects without public elements stay *?*. Needs the station location.
- **Aircraft** (`meteor_air.py`, ADS-B key): a PLANE echo is compared with the aircraft adsb.fi (else adsb.lol) sees
  within 250 NM of the middle of the path (only that point is sent), moved to the time of the echo; flight,
  registration, type, FL and distance shown, a click on the callsign opens the aircraft on adsb.fi. The receiver offset is
  learned from the satellites identified surely.
- **Classification:** an aircraft near the middle of the path (~0 Hz, no drift) is not an overdense meteor (a meteor
  starts at once, an aircraft is already there weakly at its Doppler); meteors in a burst at one Doppler and a meteor right
  after an aircraft stay meteors; a long overdense echo whose Doppler jumps a bin is not an aircraft (it must drift by
  3 bins); a short echo sweeping through the band is a satellite; a head echo braking onto its trail is not a satellite.
- **Head echoes:** the **HEAD ECHO** key adds a ±5 kHz spectrum with ~15 ms frames for fast head echoes (a straight
  streak going one way onto the trail, away from the carrier and from the echo's own Doppler); a **slow head echo** (a
  curved streak braking onto the trail, tens to hundreds of Hz) is found in the fine cells from where the trail really
  starts back in time, also when the detector started on the head echo; a short steep one the detector started on is
  taken from its own track. Marked **HEAD ECHO** in the table.
- **AFC** (on by default): the meteors show where the GRAVES carrier really is (a receiver off by some ppm); all the
  detectors follow it, the VFO is not retuned. Without meteors the carrier is looked for in the wide spectrum.
- **Echoes:** NOW (the last 500), an earlier UTC **day from the daily log**, or the **marked** ones (☆ keeps an echo with
  its detail and sound in `data\meteor_marks\<VFO>`). Filters METEORS / SAT / PLANE / head echo / minimum dB, CLR. The
  type column names how an echo was found (HEAD ECHO, FAST BURST, KNOWN (TLE), UNKNOWN LINE / LINE); the log line has the
  satellite or aircraft found and H for a head echo.
- **Detail of an echo:** short echoes in the fine cells, the ±5 kHz head echo spectrum on the same time axis, every part
  with the colour levels of the fine cells; a satellite in its own band (its track ±400 Hz), enhanced by itself (each
  frame averaged with the 8 before it along the drift of the track, its own colour levels); the calculated Doppler
  (satellite, aircraft, head echo) as two bright green dashed lines over and under the track.
- **Sound:** ▶ plays the echo as on 143.049 MHz USB (the carrier = 1 kHz tone), WAV saves it. A satellite is followed
  along its Doppler track (only ±60 Hz around it kept, so a weak one is heard over the noise) and sounds as a tone that
  follows its Doppler; a sweep wider than 2 kHz is squeezed into the audio band.
- **Weak echoes** (`meteor_weak.py`, SETTINGS › DETECTOR, each off by default):
  - **FAST:** pings of a few tens of ms in the time signal (the carrier ±150 Hz in 32 ms spectra every 8 ms, as in the
    BRAMS network); a reference band rejects impulse noise, a burst that sweeps is left out. Counted as underdense,
    **FAST BURST** in the table (F in the log); no false ping in 25 minutes of noise.
  - **SAT·TLE:** the ±8 kHz spectrum summed along the bistatic Doppler of every satellite GRAVES lights over the station
    (every 15 s, the last 40 s): streaks too weak for the tracker, the satellite already known (**KNOWN (TLE)**).
  - **SAT·LINES:** weak straight streaks (80–600 Hz/s) by a Hough transform over 6 s windows, joined to tracks and
    identified like the tracker's (**UNKNOWN LINE** / **LINE**); a track within ±350 Hz is an aircraft (PLANE), slow lines
    (under 80 Hz/s) are looked for there too. Threshold z 8.5 (no false line in 10 minutes of noise).
  - What the tracker or the meteor detector already has is not reported twice.
- **STATS:** echoes per hour over 48 hours and per day over the year (per hour of monitoring, the showers marked),
  RESET STATS. **SETTINGS:** ROTOR (the rotor dial, POINT along the path GRAVES → ROTOR, the rotor source **GRAVES** in
  RCTRL › SETTINGS), RECEIVER (TUNE 143.049 USB), DETECTOR (THR, AFC, HEAD ECHO, ADS-B, FAST, SAT·TLE, SAT·LINES), blocks
  in the STATION style.

#### COMPOSITE map and decoder maps

- **COMPOSITE map** (**COM** key in DECODE, tab COMPOSITE, purple): one map with everything that has a position from the
  decoders running on all VFOs – ADS-B, ACARS / VDL2, HFDL, AIS, SONDE. Aircraft, ships and sondes with the icons and
  labels of their own maps; the **same aircraft** from more VFOs / decoders becomes one (ICAO address, registration,
  flight number – ACARS / HFDL IATA `LH0123` = ADS-B ICAO `DLH123` –, or an uncommon squawk within 150 km and 15 min).
  A click shows the details on the right with **SOURCES (n)**. Each VFO server keeps 6 h of positions in
  `data\composite_<VFO>.json`, read back after a restart; `GET /api/positions`, **JSON** downloads the merged feed;
  ↗ opens it in a new tab. See `docs/composite.md`.
- **COMPOSITE map: settings, lists, sharing** *(by Brano, [brjanicek](https://github.com/brjanicek))*: ⚙ **Settings**
  in sections – **Sources** per kind (the local decoders and **Sharing**: **adsb.fi** aircraft, **aisstream.io** ships
  with a free API key, **SondeHub** radiosondes, each with a filter), **Map** (base maps, darken, OpenSeaMap, own GeoJSON /
  KML / GPX layers in `data\maplayers`, **A/D map** rings, **ADS-B range**), **Weather** (precipitation loop, MTG
  infrared clouds of EUMETSAT), **Aircrafts**, **Radiosondes**, **Ships** and **Labels** (trails full / fading / radar
  echo, icon size, prediction line, colours, label items). Selected object orange; squawk 7500 / 7600 / 7700 red.
  Labels can be dragged; status row under the map; **lists** beside it (sortable).
- **COMPOSITE map: tracks, Track menu, tracker bars** *(by Brano, PR #23)*: counts Total / Local / Sharing per kind, a
  **Show** checkbox per kind, the selected track kept in view; a **Track menu** per track (label, font, prediction,
  trail, note, **Lock**); **Tracks** and **Tracker** bars over the map (labels, Center, clouds, precipitation, A/D map,
  **Find track**, Unlock); more map settings with **Restore default** (`static/com_defaults.js`).
- **Vector maps** *(by Brano, PR #24)* on the COMPOSITE map and the other decoder maps, offline: openAIP airspaces,
  airports, navaids, reporting points and obstacles; OurAirports airports, runways and frequencies; OpenStreetMap
  transmitter sites; FUA activated areas of Slovakia; IFR waypoints (EUROCONTROL FRA points plus the INSPIRE points of
  SK / DE / AT / FI); MEMORIES channels with a location; own GeoJSON / KML / GPX files. Each country downloaded with
  Update into `data\vectormaps`; a tree of parts and objects, zoom bars per layer, a style editor with ICAO chart
  symbols, an FL filter, own names and notes per object; the Maps bar with Map memory (10 setups, export / import), Map
  info and Map edit; stored on the server for all browsers. It replaces the raster OpenAIP layer; new default COMPOSITE
  settings.
- **Precipitation radar on the maps** of VDL2 / ACARS, HFDL, ADS-B, SONDE and COMPOSITE: the RainViewer radar (only the
  map tiles are asked), the last 30 minutes animated, opacity slider; off by default. **Trails** switch on the VDL2,
  HFDL, ADS-B and COMPOSITE maps.
- **Decoder maps keep their view** (FT8, PACKET, ACARS / VDL2, HFDL, ADS-B, AIS, SONDE): centre and zoom per map after a
  switch of the VFO or tab or a reload.
- **Decoder maps:** dark bubbles like those of FT8 / WSPR; a click on a mark or its label draws a red dotted line from the
  QTH to it, with the distance and azimuth (SONDE, PACKET, ACARS / VDL2, HFDL, AIS, ADS-B), following a moving plane or
  ship.

#### Propagation and DX

- **PROPAGATION tab (PROP key):** space weather from NOAA SWPC (solar flux, X-ray, solar wind, Kp and A, R / S / G
  scales, alerts) as blocks in the STATION style, charts of Kp (3 days with the forecast), X-ray (6 h) and the
  **magnetogram of Kiruna**. **HF BANDS · ESTIMATE NEXT 24 H:** the bands 160–6 m against the next 24 hours from an own
  model (foF2 from the solar flux and the sun, absorption, storms), corrected by the **GIRO ionosondes** up to 1000 km
  (via KC2G; sporadic E from foEs) and by what **FT8 and WSPR** of all VFOs hear. **FT8 BAND TEST** listens on each band
  and returns the VFO afterwards. A chip under the S-meter shows SFI · Kp · A · R S G. See docs/propagation.md.
- **DX CLUSTER** (**DX** key in the PROP group, its own tab): the spots of the last 30 minutes from HamQTH (read once a
  minute for the whole station by `dxcluster.py`), split into HF / VHF / UHF with a filter; the same DX on one frequency
  is one row with the number of spotters. A click on a spot tunes the active VFO there with its mode; the spots are pink
  marks with the DX call at the bottom of the spectrum.

#### Satellites and rotor

- **SATELLITES › SUN NOISE** (`sunnoise.py`): G/T of the station by the Y factor on the Sun with the rotor, measured on
  the **noise floor of the whole band** (the median of the spectrum without edges and centre, ~12 a second), in 1–20
  cycles, the Sun's flux estimated from today's F10.7 or typed in. **SUN SCAN** sweeps across the Sun without stopping,
  there and back (**Scan ±°**, **Sweeps ×**), in about a minute; the beam is fitted for each direction, so a lag cancels
  and is shown in seconds. **APPLY TO ROTOR CALIBRATION** shifts the AZ calibration; in elevation it sets the new **EL
  offset** of RCTRL › SETTINGS (used by the readings, targets and satellite tracking). See docs/satellites.md.
- **SATELLITES: the Moon (EME).** MOON (EME) is one more satellite (SETUP tab **Moon (EME)**), its position from the new
  `moon.py` (Meeus' lunar theory, about 0.01° and 50 km against JPL Horizons). Passes, map and the rotor (TRACK) work as
  for a satellite; the pass detail shows the distance, the own echo's Doppler at 144 / 432 / 1296 MHz and the path loss;
  TRACK has keys for the EME frequencies (50.19 MHz to 5760.1 MHz) and shows the echo shift, path loss and echo delay.
- **Rotor dial** (`static/rotdial.js`): one block with the polar plot and the elevation column for RCTRL › SETTINGS,
  SUN NOISE and GRAVES; a click in a plot turns the rotor. New rotor source **GRAVES** in RCTRL › SETTINGS.
- **AD satellite tracking** (`static/satad.js`): while the Doppler correction tunes the VFO, the AD under the clock shows
  a small polar plot of the pass, the satellite, the frequency received and the rotor tracking.

#### Recording

- **PRE-REC: tuning back in time** (PRE-REC key under REC IQ, `retro.py`): the raw IQ of the dongle of the last 10–300 s
  (60 s default) kept in RAM (the waterfall mark *PRE-REC 60 s*); **Alt+click on the waterfall** plays that moment at that
  frequency, up to 20 s demodulated with the mode, filter and all the AUDIO keys of the VFO as set now, while the live
  audio is turned down. **SAVE IQ** (SETTINGS › GENERAL › RECORDINGS) writes the whole buffer as an IQ WAV
  (`…_IQ_PREREC.wav`). RTL at 2.4 MS/s needs 290 MB for 60 s, only while PRE-REC is on.
- **RECORDINGS: day folders, browse, sort, delete, playlist, stars.** Every recording goes to `<recordings>\YYYY\MM\DD`
  of its start – REC, REC SQ, the scan and DAB as MP3, REC IQ as WAV in its `iq` subfolder; the source is in the name
  (`_SQ`, `_SCAN`). The tab browses the tree, has a **Source** column, sorting by any column, ticks + **DELETE**, ⤓
  download, the folder as a **playlist** (PLAY, **AUTO-NEXT**, `3 / 17`) and a **star** for a recording (`starred.json`,
  a filter shows only the starred ones). The recordings of the flat folders before 1.1 are moved into the day folders
  once at the first start and the old WAV of the scan become MP3.

#### Settings, logs and data

- **SETTINGS: compact cards in the look of STATION, notes behind an "i":** smaller cards, the title small in capitals,
  every card in the colour of its kind as in STATION (grey when its main switch is off); the explaining notes behind an
  **i** icon at the right of the title (bubble on mouse over or click). Pages GENERAL, STATION, SDR SOURCES, VFO,
  RTL_TCP SERVER, DATA/LOG, DEBUG.
- **SETTINGS › GENERAL › BACKUP:** the settings of the whole station to a ZIP file and back, chosen by ticks: VFO
  settings, VFO sources, memories, station (location, antennas, rotor, recordings folder), satellites, ISM devices, map
  API keys (secret, not ticked by default) and the page settings of the browser. **Restore** from a file or from
  `RADIMCOM\backup\`: the VFOs restart with the settings and the page reloads; a VFO whose dongle is not on this PC stays
  without a source, with a warning. **Factory reset** in two steps (type RESET): a full backup goes to
  `RADIMCOM\backup\` first, then RADIMCOM restarts like a new installation (logs, recordings and decoder pictures stay).
- **SETTINGS › DATA/LOG** (new): **FILES** browses the folders LOGS, WEFAX, SSTV, DAB (songs), SERVER, WIND and SONDE IQ
  with their sizes, shows a file (the end of a text file with a line filter; an image), ⤓ downloads it; **DELETE**,
  **⇩ ZIP** export and **⇧ UPLOAD** import. **LOGGING**: a table decoder × VFO with the LOG switch of each and the logs
  that are always written with how long they are kept. **HISTORY**: the COMPOSITE history of each VFO and the ADS-B range
  with **EXPORT**, **IMPORT** (merged) and **CLEAR**. API `/api/data/*` and `/api/history/<composite | adsb_range>`.
- **Logs in day folders:** `data\logs\<source>\YYYY\MM\DD\<source>_YYYY-MM-DD.txt` (UTC) for the decoders, ACARS / VDL2
  (before in `data\acars`), the scan (`.csv`) and the radiosonde flights (`<date>_<serial>.jsonl`); the flat logs of older
  versions are moved there once at the first start.

#### Page and window

- **Tooltips:** one dark tooltip of RADIMCOM for every title of the page (`static/tooltip.js`), kept current while the
  mouse wheel changes a value.
- **Bottom tabs:** a red **×** closes a tab (and switches its key off), never wrapping to a second line; no strip of the
  waterfall at their bottom edge; a **Loading…** bubble in the middle of the pane while a read takes over a quarter of a
  second (recordings, maps with history, decoder logs).
- **Hidden lower part pauses the spectrum and waterfall:** with the lower part hidden (VIEW key) the servers stop sending
  this tab the spectrum rows, as with PAUSE but without the key lit; audio, S-meter and decoders go on.
- **Band keys** remember the frequency and mode last tuned inside their band (band stacking; kept in the browser, common
  to all VFOs) and are momentary (no lit key and no LED after the click).
- **A VFO switch shows the waterfall** (or DECODERS when a decoder runs on it, the DAB / DSD tab in those modes), never
  the tab that VFO had last; a double click on a memory switches to SPECTRUM too. A VFO picked under SETTINGS › VFO
  stays on SETTINGS.
- **RADIMCOM.exe:** starts in full screen (F11 or the key beside the logo for the window; `--window` starts in the
  window); a small start-up window (*Starting RADIMCOM…* with the pulsing icon) grows to full screen only when the page is
  ready, also after a restart of the server (*Restarting RADIMCOM…*). **POWER and FULL SCREEN keys** at the top of the
  master section.
- **CPU / MEM indicator: RADIMCOM against the whole PC, as Task Manager counts** (`CPU 9/21%`, `MEM 0.5/14G`), split in
  the tooltip (the server by VFO, the window); from another PC the numbers of the server PC (**SRV**).
- **Spectrum:** the label above the passband shows the current SNR of the channel and the bandwidth.
- **SCAN:** the squelch threshold of each channel measured as a short line in the spectrum (green, red when open).

#### Development

- Git workflow for working on one version branch together without conflicts: pull requests from short topic branches
  rebased onto the version branch, the change log written by the maintainer from the PR description, line endings fixed
  by `.gitattributes`. Rules in CONTRIBUTING.md (Git workflow), CLAUDE.md for AI assistants and DEVELOPER_GUIDE.md (how
  we build RADIMCOM: workflow, versions, names, style, tests, checks).

### Fixes

- **SCAN stopped too often on noise (ASQ):** a channel opened on one block (85 ms) over its threshold, so a click, a burst
  or a rise of the whole band stopped the scan for nothing. A channel now opens only after 2 blocks in a row over its
  threshold, and its own learned floor never counts below the noise of the band in the current block. Test in
  `tests/test_scanner.py`.

## Ver. 1.0

Released after the test betas (GitHub branches `1.0beta1`, `1.0beta2`) and the release candidate (`1.0rc1`); continues 0.115.

### Main Features

- **SETTINGS › STATION – a live scheme of the whole receiver:** one row per VFO from the antenna through the dongle
  (TUNER, A/D, the AGC+ loop), IQ, mixer, SP, filter, demodulator and audio to the MAIN / CUE buses and the decoders,
  drawn from the real state – what is on, where each decoder takes its signal, what a raw-IQ decoder bypasses.
- **AGC+ reworked, inspired by the auto gain of OnAir:** keeps an A/D headroom target by the signal kind and band instead of
  driving the A/D to the top, cuts at once on an overload and climbs back, stops when more gain buys nothing; a meter
  strip with a clip lamp, warnings and *why this gain*. New **ADC bar** in every VFO window.
- **New audio tools:** **NB** noise blanker, **DNR** spectral noise reduction (also under speech), **HUM** mains hum
  filter, **SAM** synchronous AM (DSB / one sideband), a steep **LPF**; automatic LSB / USB / AM by band.
  **Note:** the former DNR key (quiet between words) is renamed **NTH**, as on factory receivers; DNR is now the new
  noise reduction.
- **Improved function of ATU in SSB:** it tunes the suppressed carrier onto the red line, snapped to a whole kHz
  (e.g. 14.265 MHz).
- **Radiosondes:** the decoders of rs1729 (RS41, DFM, M10 / M20 and six more types), **MULTI** (all sondes in the
  spectrum at once), **TYPES**, a bad GPS position dropped, flight **prediction with the GFS wind** and a corrected
  fall, profile with **wind**, altitude / time chart, HISTORY 1D / 7D – and the rotor follows a sonde (**SONDE TRACKER**).
- **DSD (digital voice):** AFC onto the signal, a narrower filter, DEBUG output of DSD-FME, a redesigned tab with talk
  group names, caller countries and callsigns.
- **Recording:** **REC IQ** (the whole band of the dongle to WAV, SDR# style), DAB recorded by REC / REC SQ, the scanner
  records MP3, RECS / SCAN RECS in RECORDINGS.
- **Station:** the **antennas of the station** with their ranges (ANT warns outside them), **MUTE** of each VFO, the rotor
  settings in the RCTRL tab, any RTL-SDR dongle renamed in the SDR setup.
- **FT8 map** with a locator grid and our reports; **DAB** song history and buffering shown; **about a third less CPU**
  in the browser.

### Changes

#### SETTINGS › STATION: the scheme of the whole receiver

- **SETTINGS › STATION:** a simplified live scheme of the whole receiver. On top the station (QTH, rotor with azimuth /
  elevation and tracking, satellite Doppler); below one row per VFO with its frequency, from the antenna to the
  speaker:
  - **ANTENNA** (out of range, rotor), the dongle as one block (RTL-SDR + serial, upconverter, bias-tee, ppm) with
    **TUNER** (gain, AGC+ / manual / auto) and **A/D** (sample rate, peak, clipping in red) inside, **AGC+** under the
    dongle in a blue loop (the A/D peak in, the gain up into the TUNER; the headroom and its target; by the owner VFO
    on a shared dongle; → ASQ when it switched the auto squelch on); a dashed line from the VFO frequency forks into
    the TUNER (centre of the dongle) and the MIXER (offset from the centre).
  - **IQ** (DC → NB in their order; *pass* with both off), **SPECTRUM · WATERFALL** under it (fed from between DC and
    NB, as in sdr.py), **MIXER** (digital mixer, ÷ 64), **SP** (spur removal on the baseband), **FILTER**, **DEMOD**
    with a small picture of the demodulation (AM / SAM carrier and sidebands, DSB, USB / LSB, CW, the FM / WFM
    waveform, the OFDM block of DAB, the 4-level symbols of DSD; SAM lock, stereo, RDS), **S-METER** under FILTER /
    DEMOD (the channel power after the filter in S units and dBFS).
  - **AUDIO** with its stages joined by arrows in the order the sound goes through them (HUM → NF → DNR → ALC → NTH →
    AFI → LPF → HPF → SQL), squelch open / closed; a SQL line and an ASQ line fed by the S-METER, each with the channel
    power and the level it opens at (no ASQ line without a squelch, e.g. in USB or DSD). With DSD the voice decoder is
    its own block **DSD** (protocol, errors) between DEMOD and AUDIO (then only LPF → HPF).
  - **MAIN and CUE buses:** out of AUDIO of each VFO two wires into two vertical buses over all the rows – OUT into the
    green MAIN bus (green and connected while the VFO is MAIN, grey and open otherwise) and CUE into the orange CUE
    bus; **MUTED** (red, dashed, open) by the MUTE key of the VFO or while a raw-IQ decoder mutes the audio. Speaker
    heads on top with the levels of the MAIN and CUE faders. REC and SCAN beside the VFO name.
  - **DECODERS** before the buses, fed where they really take the signal: the baseband decoders (FT8, CW, RTTY,
    PACKET, POCSAG, WEFAX, ACARS, SONDE without MULTI) by a violet line from between SP and FILTER, SSTV
    (demodulated audio) by a wire from AUDIO. Decoders on the raw IQ (VDL2, DAB, ISM, HFDL, AIS, ADS-B, SONDE MULTI)
    branch off the A/D output into their own block **IQ DECODERS**; while one of them or DAB runs, the blocks it
    bypasses are faded and hatched with the reason in their tip, the chain up to the filter stays active (it still
    feeds the S-meter, e.g. to turn the antenna for the strongest DAB signal). The DAB audio line leaves IQ DECODERS
    on its right into OUT, or into CUE when the VFO is heard on CUE only. With the RX Doppler on, an orange line
    DOPPLER → VFO leads back into the VFO.
  - Each kind of block has its own colour and a small framed icon; the columns stretch over the whole width of the
    tab. Read-only and static (no animation, a click does not jump anywhere). The VFO state also carries `sonde_multi`.
- **SETTINGS › VFO › SDR DONGLE and AGC+ diagrams in the look of the STATION scheme:** each block in the colour of its
  kind with a soft gradient and (in the dongle diagram) a small icon; static; the blocks still find their cards by a
  click, grey when not for this dongle or VFO.

#### Gain and tuning: AGC+, ATU, ADC

- **AGC+ reworked, inspired by the auto gain of OnAir** (adswill/OnAir, the ideas, no code; new `gainctl.py`):
  - **Measurement** of every block: the clipped share and the peak of the A/D, a **robust peak** (the 99.9 % point of the
    samples, one spike does not decide), a 2 s peak-hold; from the spectrum of the whole band the **noise floor over the A/D's
    own quantisation noise** (8 bits RTL, 12 bits Airspy / Lime), the **SNR of the channel** against its flanks and the strongest
    signal outside the channel.
  - **AUTO** (the AGC+ key) keeps an **A/D headroom target** instead of driving the A/D to −2 dBFS (which gave intermodulation on
    HF and near FM stations): narrow channel 14 dB, FM broadcast 9, DAB 7.5, ADS-B 3 from the peak-hold; HF +3 dB, the FM band
    (not WFM) +3, VHF +1, above 1 GHz −2, a band much wider than the channel +2. An overload cuts at once by how bad it is (at
    least 3 dB, 6 / 9 / 14 / 30 dB at 0.1 / 1 / 5 / 20 % clipped) and leaves a **soft ceiling** 3 dB under that gain for 20 s
    (90 s after three overloads in a minute); then the gain **climbs back** to where it was (4 dB per 1.2 s). Too hot: down by the
    error every 0.8 s. **Gain wasted**: no step up while the floor is 15 dB over its goal (narrow 10, FM 5, DAB 8, ADS-B 12; HF −2),
    3 dB more takes a step down; a floor under its goal raises the gain 3 dB inside the dead band. **Hysteresis**: after a step
    down, a step up needs 1.5× the dead band for 8 s; the first 8 s after a start or a retune climb faster.
  - SETTINGS › VFO › ADVANCED › AGC+: a **meter strip** (A/D level bar with the target tick, green / amber / red / blue, a
    **CLIP lamp** held 2 s, headroom, floor over the A/D, channel SNR, signal kind and band), the first **warning** in plain words
    (clipping, a strong signal nearby with its frequency, gain too low, antenna noise far over the A/D's) and **why** the gain is
    where it is (*limited by the headroom – strong signal at 144.500 MHz*, *more gain buys nothing*, the last decision); sliders
    (headroom ±, dead band, clipping limit, cut, up, between steps, gain wasted, settle) with a legend of the units, presets
    (CONSERV. +6 dB headroom, CAREFUL +3, MODERATE, BOLD −4) and DEFAULT (= MODERATE). Old AGC+ settings are not taken over.
  - **Diagram *Where AGC+ and ALC work*** beside the AGC+ card: the path of the signal (tuner → A/D → DC · SP → NB → channel
    filter → demodulator → NOTCH → DNR → ALC → AFI → HPF · LPF → SQL) with the AGC+ loop, what AUTO decides by the headroom
    and by the floor (live marks on both scales), an overload and the way back in time; a click on a block or a setting
    highlights its slider or card. The STATION scheme shows the headroom and its target in the AGC+ block.
  - `tests/test_sagc.py`: a simulated front end (R820T table, antenna and radio noise, a strong neighbour and its third-order
    product, a clipping 8-bit A/D): convergence from three start gains without hunting, gain wasted on a noisy HF band, the
    way back after an overload burst, the presets.
- **ADC bar in the VFO window** under RF GAIN: the A/D converter level in dBFS (the 99.9 % peak AGC+ measures, else the
  block peak), scale −40 … 0 dBFS in the colours of the AGC+ meter – green around the AGC+ headroom target of the signal
  kind and band, blue too quiet, amber too hot, red the last dB and clipping (the zones on whole segments); the value
  coloured the same, the tooltip with both peaks, clipping and the target. **RF** renamed **RF GAIN**; labels, bars and
  values of RF GAIN, ADC and SQL in one grid (same start and width), the window taller by the new row.
- **Improved function of ATU in SSB – onto the carrier, snapped to a whole kHz or rounded to 100 Hz:** the edge of the voice band on the
  carrier side is found in a held spectrum of the channel (max-hold over 0.5 s windows falling 0.6 dB a window, so the
  pauses of speech do not break it; smoothed over 250 Hz; walking down from the band's peak to where it falls to 40 % of
  the peak's height in dB, so splatter and noise under the voice do not pull it down), the carrier 120 Hz beyond it,
  then snapped onto a whole kHz when within 300 Hz of it (SSB stations sit on whole kHz, e.g. 14.265 MHz), otherwise
  rounded to 100 Hz. Checked on 39 real 40 m LSB, 20 m and 17 m SSB stations tuned by ear: about 60 Hz from the tuning
  by ear (median) where the first version was always too low (up to 630 Hz); `tests/test_atu.py` on a synthetic voice.
  ATU keeps its last 8 analysed blocks in `data/logs/atu` (a few MB) to check it on real signals.
- **ATU on = autotune now:** switching the ATU key on (AM / USB / LSB) autotunes the frequency tuned at that moment at once.

#### Audio and demodulation

- **NB – noise blanker.** The **NB** key (AUDIO, right of NTH; all modes except WFM and DAB) blanks pulses (ignition,
  electric fences, switching supplies, radar) in the wideband samples of the dongle, before the channel filter, where
  they are a few µs long. Detection on the jump of the magnitude out of the envelope of the band (13 µs average), only
  short runs (≤ 100 µs), so a strong station is never blanked; the pulse ± *Width* µs set to zero. Level 1–10 and width
  1–50 µs in SETTINGS › VFO › AUDIO, *Now* = pulses a second and % blanked. The waterfall stays unblanked. Synthetic
  test at 2.4 MS/s: pulses 10× the noise 6 dB lower in the channel, 30× 15 dB lower; 6–10 % of a CPU core while on.
  Config / API `nb`, `nb_level`, `nb_width_us`; state `nb_rate`, `nb_frac`.
- **DNR – digital noise reduction; the old DNR is now NTH.** The **DNR** key (AUDIO, under NTH) takes the noise out of the
  audio in AM / LSB / USB / CW all the time, also under speech: short-time spectrum (27 ms frames), the noise of each band
  from the minimum of its smoothed power over 1.5 s (minimum statistics), a Wiener gain from the decision-directed SNR
  (Ephraim–Malah, no "musical" noise) with a floor; after NF, before the ALC. Level 1–10 (noise lowered by at most 6–24 dB,
  default 5 = 14 dB), *Now* shows the reduction. On synthetic speech in SSB noise, level 5: SNR under speech +3.4 to
  +4.6 dB, noise in pauses −12 to −14 dB; ~2 % of a CPU core. The former DNR key (expander between words + soft limiter)
  is renamed **NTH** (noise threshold), so the names follow factory receivers (DNR = noise reduction, NTH = noise
  threshold, as on the G7250); it works as before (config / API `dyn…` unchanged). New `dnr`, `dnr_level`, state
  `dnr_reduction_db`.
- **HUM – mains hum filter.** The **HUM** key (AUDIO, under NB; AM / LSB / USB) runs a comb notch (`sdr.HumFilter`):
  narrow notches at the mains and every multiple, no delay; the mains of the transmitter is followed (±1 Hz) from the
  phase of the harmonics while hum is there (49.96 Hz found on a station on 6050 kHz). Synthetic −40 … −48 dB, real
  recordings −11 … −14 dB around the harmonics, speech −0.5 dB at the default width 4 Hz. Mains 50 / 60 Hz and width
  1–8 Hz in SETTINGS › VFO › AUDIO; config / API `hum`, `hum_base`, `hum_width`, state `hum_hz`, `hum_removed_db`.
  tests/test_hum.py.
- **SAM – synchronous AM** against the distortion of selective fading on shortwave: **SAM** (an option of the mode AM,
  `sam`) and under it **DSB / SB-L / SB-U** (`sam_sb`) in the 5th column of MODE (the keys are now FM WFM LSB **AM SAM** /
  DAB DSD USB CW DSB). An NCO kept on the carrier by a frequency loop (±400 Hz), the carrier from a narrow 30 Hz filter
  (the flywheel through a fade), coherent demodulation; SB-L / SB-U through a complex band-pass of one side. Synthetic
  test (carrier fading to 15 % under the sidebands): envelope 4 dB, SAM 43 dB of clean audio; an interferer 2.5 kHz under
  the carrier −34 dB in SB-U. The VFO window shows SAM / SAM-L / SAM-U; state `sam_offset_hz`, `sam_locked`. SAM follows
  an AGC+ gain step again in 150–180 ms. tests/test_sam.py.
- **LPF steep:** a linear-phase FIR like the channel filter (−6 dB at the cutoff, −82 dB 100 Hz above, flat below; ~17 ms
  delay) instead of a 6th-order Butterworth (only −18 dB 600 Hz above). HPF stays the IIR. tests/test_lpf.py.
- **Automatic LSB / USB / AM by band** (SETTINGS › GENERAL › TUNING, the page was called TOUCHPAD; on by default):
  tuning into another ham band (IARU Region 1) in LSB or USB switches to its usual sideband (LSB on 160, 80 and 40 m, USB
  on 60 m, 30 m and above); tuning into a shortwave broadcast band (ITU 120 … 11 m) in LSB, USB, CW or FM switches to AM,
  from it into a ham band to the sideband of that band. Only on entering a band, so a mode chosen by hand inside a band
  stays; band keys and memories keep their own mode; LW and MW are left alone.
- **Audio settings inactive while they have no effect:** while a raw-IQ decoder (VDL2, ISM, HFDL, AIS, ADS-B, ACARS,
  SONDE) or DAB runs on a VFO, its keys S/M, NF, HPF, LPF, ALC, NTH, AFI, ASQ, TSQ-C, TSQ-D, DNR, HUM (with DAB also
  FILTER, NB and SP) are disabled with the reason first in their tip, and SETTINGS › VFO › AUDIO is faded under a note.
  With a raw-IQ decoder FILTER, NB and SP stay active (*this changes only the S-meter*). The settings are kept.
- **S-meter:** the reading under it (S9+… dB · dBFS) is red above S9.

#### VFO window

- **CUE and REC above the unit:** CUE moved out of the annunciator row to just above the kHz / MHz unit (orange when on;
  a click toggles CUE for that VFO); **REC** in the same style above it replaces the red dot of the top row. NB, NTH and
  DNR in the annunciator row.
- **ADC bar** under RF GAIN (see *Gain and tuning*); **ANT** amber outside the range of the antenna (see *Antennas*).

#### Antennas of the station

- **SETTINGS › GENERAL › ANTENNAS:** a list of the antennas (name, type, bands – several for a multiband dipole or a
  dual-band vertical, e.g. `144-146, 430-440` MHz –, polarization, gain, height, outdoor / indoor, on the rotor, the
  chain to the dongle, note), shared by all VFOs in `data\antennas.json`. The VFO keys in each row choose which VFOs
  receive on that antenna; one VFO can also choose it in **SETTINGS › VFO › SDR DONGLE › ANTENNA**. **ANT** in the VFO
  window is green while the VFO is tuned within the range of its antenna and **amber** outside it.

#### Audio output and recording

- **MUTE of each VFO:** the keys under the VFO windows are VFO (narrower), **MUTE** (red LED) and CUE. MUTE silences that
  VFO in this browser, as MAIN and as CUE (the receiver, its decoders, recording and the scanner go on); its display shows
  the red struck-through speaker. Remembered in the browser per VFO; the STATION scheme shows it. The CUE key of the AUDIO
  group is gone (it duplicated CUE under the VFO windows).
- **MONITOR:** the CUE / MAIN faders, the dB scale and the L · R meter as tall as the speaker and RECORD keys beside them.
- **REC IQ** (under REC SQ, dark blue LED): the whole IQ of the dongle – the full band at its sample rate – to WAV as SDR#
  records it: I left, Q right, 8 bit unsigned from an RTL-SDR, 16 bit from LimeSDR / Airspy; in the subfolder `iq` of the
  recordings folder, named `RADIMCOM_<VFO>_<YYYYMMDD_HHMMSS>Z_<centre>Hz_IQ.wav` (UTC), with an `auxi` chunk for HDSDR; a
  new file on a change of the centre or sample rate and before 2 GB. The tooltip shows the size and blocks lost; the
  STATION scheme shows a REC IQ chip. API: `rec_iq` in `/api/set`, `iq_rec` in the state.
- **DAB recording:** REC and REC SQ record DAB – the MP3 of the station playing (welle-cli, 160 kbit/s) written as it comes,
  no re-encoding; named by the station, a new file when the station or channel changes and every 15 min; REC SQ records DAB
  like REC. tests/test_recorder.py.
- **RECORDINGS: RECS / SCAN RECS** choose the folder: the MP3 of REC / REC SQ or the recordings of the scanner (subfolder
  `scan`; the file the scan writes now marked and not deletable). **The scanner records MP3** (64 kbit/s mono, about 8×
  smaller than the WAV); older WAV files are still listed and played. API `?kind=rec|scan` on `/api/recordings`.
- **Recording shown the same everywhere:** the REC / REC SQ keys and REC in the VFO window blink only while audio goes
  into the file (REC from the press on, REC SQ while the squelch is open) and stay steady while REC SQ waits; all REC
  blinking 1 s on, 1 s off. RECORDINGS: play and pause icons of the same size (nothing moves when a file starts).

#### DSD (digital voice)

- **DSD AFC:** during a call the mean of the FM discriminator gives the offset of the signal from the tuned frequency;
  the DSD head shows it, and with **AFC** on (default) an offset over 120 Hz retunes the VFO onto the signal (at most
  3 kHz at a time; on a hotspot / simplex only the slots with a carrier are measured; not while the satellite Doppler
  correction tunes). A DMR repeater tuned 400 Hz off decoded the ID in 23 % of the calls, tuned onto it in 95 %.
  Kept per VFO (`dsd_afc`).
- **DSD FILTER:** the width of the channel filter before the FM discriminator (12.5 / 11 / 10 / 9 / 8 kHz, per VFO as
  `dsd_filter`); on a weak DMR signal 10 kHz lets about 1 dB less noise into the decoder.
- **DSD DEBUG:** the raw output of DSD-FME (the last 400 lines, polled only while on): sync lines dim, link control (TG,
  ID, alias) green, bursts that failed a CRC / FEC / RS check red, the number of sync lines and errors of the last minute.
  `GET /api/dsd?debug=<seq>`.
- **DSD tab:** the calls on air as cards (slot, protocol, the talk group with its name, the caller with the country of its
  ID, the alias with the callsign in green, the running time); in the head the signal state, protocol and DMR colour
  code; the list with protocols and slots in colour, TG in amber with its name (World-wide, Europe, SK national …),
  private calls in cyan, encrypted calls reddish, short calls dimmed, a duration bar; **TALK GROUPS** heard with the
  number of calls (a click filters); the number of stations heard; a filter and **hide short**; a click on the frequency
  of a call tunes the VFO there.

#### DAB

- **Buffering shown:** until the sound plays after choosing a station or switching to a VFO with DAB, **DAB** on the VFO
  display and the **DAB** key blink (on an inactive VFO with CUE on its grey DAB). Switching to a VFO whose DAB station plays
  on CUE (and away from one with CUE on) keeps the running stream: no new buffering.
- **History of the songs:** **PLAYED** under the station card lists the DLS texts of the station with the time, newest first.
  The server records the DLS of every station of the ensemble (also with the page closed) into `data\dab_history\` (one
  file per station); the same text again within 30 minutes is not recorded again.
- **VIEW with DAB:** with the lower part hidden, the station card (logo or slide, name, NOW ON AIR) moves under the key row
  into a small recessed window behind glass.

#### Radiosondes (SONDE)

- **Decoded by rs1729's decoders:** the baseband of the VFO channel and of each MULTI channel goes as float32 I/Q through a
  pipe into the decoders of rs1729 ([github.com/rs1729/RS](https://github.com/rs1729/RS), GPL v3, separate programs in
  `lib\sonde`, static UCRT64 builds by `installer/build_sonde.sh`; `sonde_ext.py`). Types: RS41, DFM (also DFM-06 / PS-15),
  Meteomodem M10 / M20 and **new LMS6-403, iMet-54, MRZ-N1 / MP3-H1, iMS-100 / RS-11G, MTS01, CF-06 / HT03**; M20 serial as on
  the label, M10 / M20 temperature, humidity and pressure, DFM serial, type, temperature and battery. ~1.4 % of a CPU core
  per decoder; channels under 44 kHz go to them at twice the rate. IQ recording of the sonde channel:
  `POST /api/sonde {"action": "rec_iq", "secs": 120}` → `data\sonde_iq\*.cf32`, replayed by `tests/sonde_replay.py`.
- **SONDE > TYPES:** check boxes for the types the decoder listens for; tick only those launched in your area to save CPU
  (until one decodes, every decoder program runs on each channel). Kept per VFO (`sonde_types`).
- **MULTI: several sondes at once** (on by default): every sonde signal in the visible part of the waterfall (inside
  400–406 MHz, up to 6) gets its own decoder; found once a second in a max-hold spectrum (the short M20 bursts count
  too) and cut out of the dongle samples by one FFT channelizer. Their frequencies are listed above the SONDES table with
  the type, serial, frames and level; the channel the VFO is on is decoded by the VFO only (it shows the VFO's sonde; no
  frame yet: *signal, no frame yet* with the possible reasons). The audio of the VFO is muted while SONDE is on.
- **A bad GPS position is dropped:** fewer than 4 satellites, altitude under −100 m or over 45 km, an impossible fall, a
  jump from the last good position (after 30 jumps in a row the new place is believed); the rest of the frame stays,
  FRAMES shows *position dropped* and why. Applied to the logs read back too.
- **Flight prediction:** above the sonde (before the burst) and below the lowest layer heard it uses the **GFS wind** on 44
  pressure levels from Open-Meteo.com (CC-BY 4.0), joined to the sonde's own measured winds; only the 0.25° cells along the
  predicted path are downloaded (from the position of the sonde, nothing of the station), once per GFS run, kept in
  `data\wind` (2 days); `wind.py`, `GET /api/wind`. Without internet as before (own winds only). **The fall after the burst**
  follows v = v0 · ρ^−a fitted to the fall heard (it came out 3–5× too long): on 12 logged flights median 0.99× of the real
  fall time (was 1.38×), worst 2.1× (was 5×).
- **Profile with wind and an altitude / time chart** (MAP): the left panel temperature, humidity and **wind speed** (the drift
  of the sonde from its GPS positions over 30 s) on one axis, the right panel the **wind direction** (where it blows from);
  also for sondes without temperature. Under it the altitude against UTC time (ascent bright, descent fainter, top marked,
  average ascent and descent rates). Both share the height of the panel, no scrolling.
- **The sonde for the charts chosen by hand only** (the list above the charts, a click on the sonde on the map, a row of
  the table or a flight from the log); remembered over a reload and a restart (CLEAR drops it).
- **HISTORY OFF / 1D / 7D** in the header beside SONDES / MAP / FRAMES: the flights of the last day / week from the
  radiosonde log in grey in the table and as blue paths on the map; a click opens one (`/api/sonde/history`).
- **Map:** a rising sonde is a **light blue balloon** (was green like the launch sites); the label under the balloon /
  parachute shows the **frequency** too. FRAMES: the FRAME column fits the 10-digit counter of an M20. SONDES table with
  wider UTC, Serial and MHz columns.

#### Rotor

- **SONDE TRACKER** – a fourth source in RCTRL › SETTINGS, **disconnected by default**; connected, the rotor follows the sonde
  chosen in DECODERS › SONDE: azimuth and elevation from its GPS position and altitude and the QTH on the WGS84 ellipsoid
  (the curvature of the Earth included), at most every 5 s and only for a change of 2° or more.
- **Rotor settings in the RCTRL tab:** ROTOR CONTROL has two pages, MAP and **SETTINGS** – the sources that move the rotor
  (was the CONNECTION page) as a small block scheme like SETTINGS › STATION, and the rotor controller (ON / OFF, serial port,
  polar plot and elevation column, STOP / RESET / MONITOR, azimuth calibration; was SETTINGS › GENERAL › ROTOR): all the
  rotor in one place, without scrolling.

#### FT8 map

- **WW locator grid:** a faint Maidenhead grid under the stations (fields always, squares from zoom 5, subsquares from zoom 10).
- **Our report:** the SNR we hear a station with as a chip coloured by strength next to the call, in the list and in the popup.
- **GRID / RX keys** (bar STATIONS) switch the grid and our report on / off.

#### Other decoders

- **One decoder on the IQ of a VFO:** DAB, ACARS, VDL2, ISM, AIS, ADS-B, HFDL and SONDE take the IQ for themselves and mute
  the audio, so one of them at a time: switching one on switches the others off (their sample rate, centre and gain come
  back). A config with several on keeps the first of DAB, ADS-B, VDL2, ACARS, ISM, HFDL, AIS, SONDE.
- **ACARS / VDL2:** the description hidden under an **INFO** key (like HFDL, AIS, ISM).

#### Settings and setup

- **DEFAULT keys** by each group of adjustable values: AGC+ (= MODERATE), Remove DC peak, SP (the learned lines stay), S9,
  HPF / LPF, AFI, DNR, ASQ margin, wheel speed, waterfall colours, the scan options and FM scan LISTEN. Values of the station
  (location, ppm, LO, rotor calibration, scan range) have none.
- **SDR setup: rename any RTL-SDR dongle:** SERIAL NUMBERS lists every connected RTL-SDR; a new serial (up to the length of
  the old one; letters, digits and - _ .) is written with WRITE TO EEPROM (only the changed ones, each EEPROM backed up to
  `data\eeprom_backup`, no serial twice). A dongle on a VFO stays on it under the new number; dongles with the same or an
  empty number are marked SAME with a unique number offered.
- **What's new: MORE INFO** of a test version (beta / rc) opens the CHANGELOG of its own GitHub branch, a release that of `main`.

#### Performance

- **Less CPU in the browser** (Edge, 1920 x 1080, the main page: about 56 % of a core before, 36 % now): the S-meter is
  redrawn only while the needle moves, the level meter touches only the LEDs that change, the S-meter, VU, waterfall and
  spectrum each in their own layer on one shared frame clock (at most 30 frames a second); nothing is drawn while the page or
  the lower part is hidden (the waterfall is painted from the whole-band history when shown again); the logo LED and the
  sonde launch sites glow without pulsing.

### Fixes

- **AGC+ no longer hunts on HF** (quick fix after the release): with a strong station on 40 m / 80 m it went up and down
  every ~2.5 s (gain 0 ↔ 3.7 dB), a line across the whole waterfall each time, because the low gain steps of an R820T move
  the A/D far more than the table says (0 → 3.7 dB by ~15 dB). AGC+ now measures how far each step really moved the
  headroom (per band, also a chain of steps) and steps up only when that keeps it in the dead band; a step down within 10 s
  of a step up holds the gain for 30 s while it learns.
- **AGC+ only BOLD** (quick fix 2 after the release): the defaults are now the former preset BOLD (−4 dB headroom, clipping up
  to 0.03 %, faster steps up); CONSERV., CAREFUL and MODERATE set too little gain (on HF the A/D's own noise limited the
  sensitivity) and are no longer offered. A VFO saved with one of them gets the defaults; DEFAULT sets them. The warning and
  the *why* line of the AGC+ card keep their place (the whole text in the tooltip), so the keys below no longer jump.
- **A frozen dongle recovers by itself:** a dongle that stays on USB but stops sending data was only closed and opened again
  every few seconds, which does not wake it. After 3 failed attempts in a row its USB device is now reset (with administrator
  rights `pnputil /restart-device`, like replugging it; otherwise `libusb_reset_device`), then again every 30 attempts; the
  server log has a line for a dongle error, each USB reset and the moment the dongle sends data again.
- **Server log with time and VFO on every line:** `15.11.2026 07:24:11.123 [A] …` (no letter = the launcher); each VFO process
  writes through its own pipe, so the lines of different VFOs and of the C libraries no longer get mixed.
- **Restart server from the tray icon** ended with "`console.log` … is being used by another process": the log file of the
  previous start is now closed first (or a `console_<pid>.log` used).
- **WEFAX no longer stops the receiver:** on noise the decoder failed with `max() iterable argument is empty` and the dongle
  of the VFO was reopened every few seconds.
- **CUE of a VFO with DAB** was silent (CUE took only the normal audio, DAB sound is welle-cli's MP3): it now plays the DAB
  station of that VFO at CUE level.
- **DSD under DAB:** a VFO in the DSD mode with DAB on kept dsd-fme running beside welle-cli; dsd-fme now runs only without DAB.
- **SONDE: a DFM sonde drawn twice** after a server restart (the entry named by the frequency stayed beside the real one).

## Ver. 0.115

Released after the test beta (GitHub branch `0.115beta1`) and the release candidate (`0.115rc1`). Many parts are contributed by **Brano, [brjanicek](https://github.com/brjanicek)** (marked *by Brano*).

### Extra: setup instead of ZIP – easier installation and upgrades

Until 0.114 RADIMCOM came as a ZIP: unzip, run `install.bat`, which needed Python installed on the PC, created a `.venv`
and downloaded all Python packages from the internet (numpy, scipy, …); an upgrade was a second ZIP with its own script.
That was the most common source of problems (a missing or wrong Python, a blocked download, a broken `.venv`).
From 0.115 a release has one file, **`RADIMCOM_Setup_v<version>.exe`**, a normal Windows setup:

- **Nothing to download or install first:** Python 3.13 and all packages are inside the setup, it works offline
  and without administrator rights.
- **A few clicks:** USB drivers, DSD-FME, desktop shortcut and start with Windows are check boxes; at the end the SDR setup
  opens in a window (dongles dragged onto VFO A–D).
- **Upgrade = run the newer setup into the same folder:** `data\` (settings, memories, logs, recordings) stays,
  the program files are replaced completely. This also works for a ZIP installation of 0.114 or older.
- **RADIMCOM as a Windows app:** RADIMCOM.exe with its own window and taskbar icon, the receiver keeps running in the tray,
  uninstall from Windows Settings.

Details:

- **Python included:** the setup brings its own Python 3.13 with all packages in `python\` (no Python installation, no internet, no `.venv` that can break). No administrator rights: installed to `C:\RADIMCOM` by default (or a folder of your choice; an older zip installation there is upgraded in place, a development copy with `.git` is refused). Languages English, Slovak, Czech.
- **Wizard:** the USB drivers (Zadig for RTL-SDR, FTDI D3XX for LimeSDR), downloading DSD-FME, a desktop shortcut and starting with Windows (in the tray) are check boxes; at the end the SDR setup (new installation) and RADIMCOM. Start menu: RADIMCOM, SDR setup, data folder, RADIMCOM in a console (`start.bat`, troubleshooting), uninstall.
- **One setup for a new installation and an upgrade:** it installs over the same folder; `data\` (settings, memories, logs, recordings) and an installed DSD-FME stay; Python and the web interface are replaced completely. Uninstall in Windows Settings › Apps asks whether to delete `data\` too.
- **RADIMCOM.exe:** the page in its own window (WebView2, the Edge engine of Windows) with the RADIMCOM icon on the taskbar, so it can be pinned; the server without a console window (its output in `data\server_logs`, the first lines in `console.log`). Window size and position remembered; the window **keeps the aspect ratio of the page** when an edge or corner is dragged (that of the screen, so the page looks like in full screen, only smaller; with the lower part hidden that of the head; VIEW then fits the height to the width), so the page is never stretched; maximized and full screen are not limited. No scroll bar on the right of the page any more (one left over from resizing took 15 px). Closing the window leaves the server running in the **tray** (decoders, recordings go on; the page in the window stops, no sound); the tray menu: open, open in the web browser, data folder, server log, SDR setup, **Start / Stop / Restart server** (stopped: the dongles are free, RADIMCOM.exe stays in the tray, the window offers START SERVER), **Exit RADIMCOM** (stops the receivers gracefully). **Full screen** (F11 or the small ⛶ icon in the top right corner of the logo section, orange while on; no frame, over the taskbar; remembered for the next start, `--fullscreen` too) and **MAIN = the green LED of the logo**: under the mouse it stops pulsing, turns red and shows *MAIN OFF*; a click switches RADIMCOM off after a confirmation, like Exit in the tray; its tooltip and the confirmation say that this stops the whole RADIMCOM server (all VFOs with their receivers, decoders and recordings) and closes the app, nothing stays in the tray (the letters still open GitHub); both only in the app window, in a browser the logo stays as it was. A second start only brings the window up; when a server already runs (e.g. `start.bat`), the window just shows it. All server processes are in a job object: they end with RADIMCOM.exe. Links to other sites open in the normal browser; sound starts without a click. A development copy can build it with `python installer/make_installer.py --exe` (it then uses `.venv`).
- **SDR setup in a window** (`setup_web.py`, `static/setup.html`) instead of the console: the connected dongles as cards that are **dragged onto VFO A–D** (or clicked, then a VFO clicked; dropped on an occupied VFO the two swap, dragged back or ✕ takes it off), then per VFO ppm, HF upconverter LO and the name; an empty VFO can *share the dongle of VFO X*; **IDENTIFY** places the dongle you unplug; unique RTL-SDR serial numbers written into the EEPROM (backup first); prefilled from the saved `vfos.json` (a saved dongle that is not connected shows as "not connected"); empty VFOs between used ones are skipped when saving; SAVE moves the old settings to `data\config_backup` and starts RADIMCOM. Opened from the tray menu (*SDR setup…*), the Start menu (`RADIMCOM.exe --setup`) and at the end of a new installation; it stops the receiver first and starts it again after SAVE / CANCEL / closing the window. `setup_sdr.py` (console, `setup.bat`) stays and shares the same functions.
- **Upgrade from 0.114 or older (zip installation):** a release has only the setup now (no install / upgrade zips). Run it and install into the folder of the old installation: the setup recognizes it (`data\config.json` without `RADIMCOM.exe`) and says on its first page, the folder page and the last page that the older RADIMCOM is upgraded and becomes the RADIMCOM app; `data\` stays, `.venv` and the upgrade scripts go.
- **New installation or upgrade** is told by the chosen folder (`RADIMCOM.exe` or `data\config.json`). An upgrade skips the SDR setup at the end and does not offer the DSD-FME download; only an installed DSD-FME of another version than this RADIMCOM needs is offered for update (`install_dsd.py` writes `lib\dsd-fme\VERSION.txt`). A RADIMCOM still running from the folder in a console (`start.bat`) is found too, not only RADIMCOM.exe.
- **No upgrade from the page any more:** when a newer version is released, the page shows it with **DOWNLOAD SETUP** and **RELEASE PAGE**; the user closes RADIMCOM and runs the setup. The UPGRADE key, the upgrade zip download and `upgrade_helper.py` are gone (`POST /api/update` too).
- **Icon:** a spectrum with a strong carrier on top and a waterfall of the same carriers below, on a dark square (`installer/make_icon.py`), also the favicon of the page. The `.ico` has the sizes below 256 px as classic bitmaps (Explorer and the combined taskbar buttons showed the default icon for PNG ones); the window sets its icons itself (WM_SETICON, also after full screen).
- Build: `make_installer.py` takes Python and the WebView2 SDK from NuGet (cached in `installer/cache`), installs the packages isolated (`python -I`), compiles RADIMCOM.exe with `csc.exe` of the .NET Framework and runs Inno Setup 6 (`installer/radimcom.iss`); the install / upgrade zips only on request (`--zips`, `--zip-only`). NOTICE.md lists the bundled Python, packages and WebView2 SDK; the sources zip adds lameenc.

### Main Features

- **Radiosonde decoder** (by Brano, brjanicek; new DECODERS page **SONDE**, `sonde.py`, details in [docs/decoders/sonde.md](docs/decoders/sonde.md)). Weather balloons on 400–406 MHz from the baseband of the VFO, independent of the mode and filter, both polarities. **Vaisala RS41** (the sonde of Wien, Prostějov, Budapest, Poprad, Praha…): header search, de-whitening, Reed–Solomon RS(255,231) correction of up to 12 wrong bytes in each half of a frame, CRC of each block; serial, frame number, battery, GPS time, position, altitude, speed, direction, climb, satellites; RS41-SGM frames marked encrypted. **Graw DFM** (experimental; no serial number yet): Hamming(8,4) correction, position, altitude, speed, direction, climb. Views **SONDES** (newest data of each sonde with distance, azimuth and elevation from the station, state rising / falling / landed / lost), **MAP** (balloon or parachute, flight path, burst point, □ opens it in a new tab `?map=sonde`) and **FRAMES**; automatic log `data\logs\radiosonde` (see the telemetry entry below), memories can start it, `/api/sonde`. Tested on the RS41-SG and DFM-17 I/Q recordings of the Signal Identification Wiki (both sondes on the ground): every frame decoded with a good CRC / Hamming check; not yet on a sonde in flight. Unit tests `tests/test_sonde.py`.
- **Radiosonde telemetry: temperature and humidity (RS41).** The decoder collects the calibration the RS41 sends in 51 pieces (one a frame, per serial) and turns the raw sensor values into air temperature (°C, as rs41mod: reference resistors → resistance → polynomial) and relative humidity (%, empirical formula, approximate). Columns **T °C** and **RH %** in SONDES and FRAMES (until the calibration is there the T column shows the pieces known, e.g. *12/51*; tooltip: calibration and humidity sensor temperature), in the map popup and in the daily log; the sonde type RS41-SG / RS41-SGP from the calibration. Pressure not decoded. In **MAP**, on the right of the map (instead of the list of sondes), the **profile** of one sonde chosen in a list above it (orange icon on the map; its flight path keeps its green; **Auto** = the sonde decoded on the tuned frequency, a click on a sonde on the map chooses it, a click on the map goes back to Auto): a tall plot with altitude on the vertical axis and two panels side by side, **temperature °C** and **humidity %**; the descent after the burst fainter, the right edge labels the altitude with the pressure of the standard atmosphere (hPa, only an orientation, not measured), hover shows altitude, time, T, RH and hPa; the points come from the flight path (every 2 s, also kept by the server, now up to 3.3 h = a whole flight). The altitude axis is fixed 0–41 km and the plot fills the height of the page (no scrolling). **Radiosonde log** `data\logs\radiosonde\<YYYY-MM-DD>_<serial>.jsonl`: every frame of every sonde is written automatically (whatever the LOG key; one JSON line: time, position, speeds, T, RH, satellites, battery, frequency, VFO); after a server restart the sondes of the last 24 h heard by that VFO are read back with their flight paths (*from log* in SONDES), and the list above the profile offers the logged flights (`/api/sonde/logs`, `/api/sonde/log?file=`) – a chosen one is drawn in the profile and on the map. It replaces the daily text log `sonde_YYYY-MM-DD.txt` and the LOG key of the SONDE page (removed). Unit tests in `tests/test_sonde.py`.
- **SONDE MAP: flight prediction.** For every sonde in the air (also one no longer heard) a red dashed line from the last decoded point to the predicted landing: points **+1 h, +2 h, +3 h after the launch** (with the altitude), the burst (yellow ring, time) and the **landing** (✕, time UTC and hours after the launch). No weather model and no internet: the wind comes from the sonde's own flight path (its drift between frames averaged in 500 m layers; above the highest layer heard the top one is kept, below the lowest one (a sonde first heard high up) its speed falls off linearly to a half at the ground; in a layer heard on the way down too the wind of the fall wins (later, over the landing area), so during the ascent the prediction gets better as the sonde climbs, after the burst the fall goes through the winds already measured), the ascent rate from the last 5 min of the climb, the burst at 33 km (unknown before it happens; the real one when it happened), the fall from the measured descent rate (mean of the last five steps between decoded points), slowing down as the air gets thicker (ISA density; before the burst 5 m/s at sea level); the ground taken at 400 m. The launch time is counted back from the first frame heard. **Landing area**: a red dashed circle around the ✕ holding 90 % of 60 more runs of the same flight with the inputs scattered by their likely errors (each 500 m wind layer: half the spread of its samples + 1.5 m/s, much more outside the layers heard; descent rate ±15 % or the spread of the last five steps; ascent ±10 %; burst ±3 km while unknown; ground ±250 m); the label gives the landing time span (5–95 %) and the radius. Same data = same circle (seeded), computed again only with a new point.
- **POCSAG pager decoder** (by Brano, brjanicek; new DECODERS page **POCSAG**, `pocsag.py`, details in [docs/decoders/pocsag.md](docs/decoders/pocsag.md)). From the baseband of the VFO, independent of the mode and filter: 512, 1200 and 2400 Bd at once, both polarities; BCH(31,21) corrects one or two wrong bits per codeword, a codeword that cannot be corrected is a red **?** in its message. Numeric or alphanumeric is guessed from the function bits and the characters (the other reading in the tooltip). Views **MESSAGES** and **ADDRESSES** (the newest message of each RIC), filter (a click on a RIC shows only it), **NO TONE**, daily log `pocsag_YYYY-MM-DD.txt`, memories can start it. Tested on a 4 min recording of the 1200 Bd network on 162.47 MHz heard in Bratislava: 36 messages, alphanumeric texts and time messages read cleanly. Unit tests `tests/test_pocsag.py`.
- **FT8 station map.** The FT8 page is split: the table on the left, a map of the stations heard on the right (Leaflet, dark OpenStreetMap). Each station is a ▲ at its locator (from CQ and answer messages; the transmitting station of each message is found, a locator from an earlier message stays): green = calling CQ, cyan = in a QSO, red = selected (dashed line from the QTH), pale = not heard lately, white glow = just heard; stations of one 4-character square are spread inside it. Above the map **10 min / 30 min / 1 h / 12 h / 24 h** (the stations heard in that time) and **CLR**; the station count and the farthest station. On the right a list of the stations (call, locator, km, SNR, age; stations without a locator yet are pale); a click shows the station, its popup has the distance, azimuth, newest message, band and links to QRZ and PSK Reporter. Call labels from zoom 5. The □ key opens the map in a new tab (`?map=ft8`). The server keeps the stations of the last 24 h (`/api/ft8/stations`; not kept over a restart).
- **ISM at 868 MHz: Wireless M-Bus meters, weaker sensors** (by Brano, brjanicek). The **868.30** preset now has two rtl_433 channels of 256 kS/s: **868.30** (LaCrosse, Bresser…) and **868.95 MHz** (Wireless M-Bus T1 / C1 meters, e.g. heat cost allocators in a block of flats), both with `-Y autolevel` (FSK: it finds the weaker devices; at 433 MHz OOK it only added false decodes, so it stays off there). Measured on a 2.5 min recording: the 868.95 channel decoded 219 wM-Bus messages of 178 meters, the whole band with autolevel 22 and without it none (512k / 1024k channels: 192 / 101); live about 105 messages a minute instead of 10. Rate and autolevel are set per channel (`CHANNELS` in `ism.py`); the counter tooltip and `ismstate` show the channels and their rates (`channel_rates`), also right after a small retune.
  - **Fewer rows:** a wM-Bus meter is one row for an hour with its latest message (mostly encrypted: shown compactly as mode, manufacturer, type, "encrypted"); the same message of any device within 1 min of its previous one joins its row (×N, also with other devices in between), and the row moves to the top with the time of its last message (the first in the tooltip); the list keeps 500 rows.
  - **Two decoders, one packet:** names learnt from one packet (e.g. LaCrosse TX29IT / TX35DTHIT) also join later packets read by only one of them; only on the same channel and with the same device ID, never with a wM-Bus meter (a sensor row once collected a meter and a Honeywell of the same level).
  - **RAW at FSK:** a package at the frequency (±10 kHz) of a decoded one at the same time is not shown as RAW (the analyzer measures FSK levels differently, so the level alone did not match).
- **ISM page redesigned: devices, timeline** (details in [docs/decoders/ism.md](docs/decoders/ism.md)).
  - **Views MESSAGES | DEVICES | TIMELINE.** **DEVICES**: a card per device (model + ID + channel) with its latest values in large digits (temperature, humidity, wind with a compass, then pressure, rain, UV, lux, power…), a **24 h curve** of temperature and humidity, battery (a red blinking battery when LOW), signal bars from the SNR, the age of its last message, how often it sends and its message count. Cards of devices gone quiet fade (3 intervals, at least 5 min; grey after 30 min), a new message lights the card up. All cards are equally high with the same layout (values, one line of the other fields with all of them in the tooltip, curve, footer); a device without temperature or humidity shows its messages as ticks (1 h) or bars per 5 min (6 h / 24 h) in place of the curve. **1 h / 6 h / 24 h** in the header (DEVICES, TIMELINE and the device tab, remembered) sets the time of the curves, the activity, the timeline and the charts. **TIMELINE**: at 1 h a dot for each message of each device, at 6 h / 24 h a block for each 5 minutes with messages (brighter = more, the count in its tooltip), and its typical interval (a click on the name opens the device's tab).
  - **Device tab with charts:** a click on a card (or a name in TIMELINE) opens a tab of that device next to the views (its name with ✕ closes it): its values in large digits, model, ID / channel, frequency and modulation, signal, when heard first / last, message count and interval, message check, battery, ✎ ☆ ⊘; below a chart for every number it sends over **1 h / 6 h / 24 h** (temperature, humidity, wind with gusts, wind direction as dots, pressure, rain, UV, light, power, energy, battery voltage; other numbers such as switch or button IDs, codes and counters are no charts but values in the head of the tab, and a device of the category Other has no field charts at all), **Signal** (RSSI and SNR) and **Messages per 1 / 5 / 15 min**. Each chart shows the latest value, min, average and max; no line across a silence. Charts by **uPlot** 1.6.31 (MIT, `static/uplot`, loaded with the first device tab): one cursor for all charts with the values at that time in each chart's legend, **dragging over a chart zooms all of them in**, a double click goes back; a click on a legend entry hides that curve; new messages update the charts without losing the zoom. The server keeps one point per minute for 24 h per device (the last values of the minute and its message count).
  - **Names, pins, hiding** (✎ ☆ ⊘ on a card): station-wide in `data\ism_devices.json` (all VFOs, also shown in the message rows); **HIDDEN** shows the hidden ones. **NEW** (a glowing badge for 10 min) = a device not heard on this PC in the last 60 days (`data\ism_known.json`).
  - **Categories** from the model and fields (🌡 weather, 🚗 TPMS, 🔑 remotes, 🚪 security, 🔥 alarms, ⚡ meters, 📡 other, ❓ RAW) as chips with counts that show / hide them, a filter field; both apply to all three views.
  - **Statistics:** messages per minute in the last hour (bar sparkline), number of devices, the three models with the most messages.
  - **Message rows:** category icon, signal bars, ✓ when the device's message check (CRC / parity) passed, a new or repeated message flashes the row and its ×N; RAW rows have a small picture of their pulses (from the triq.org/pdv code, else from the demodulated bits). The description moved under **INFO**.
  - API: `ism` messages carry `fields` (values as numbers) and `dev` (device key); new event `ismdev` (a device with `times` of the last hour and `series` [t, °C, %] in 5 min steps for 24 h, up to 300 devices) and `ismnames`; `/api/ism` gives `devices` and `names`, `/api/ism?dev=<key>` one device with its `hist` ([minute, messages, rssi, snr, {field: number}] for 24 h), POST action `name` (`key`, `name` / `pin` / `hide`); `ismstate` has `rate` (60 minutes).
- **CW decoder rebuilt: soft decisions and a skimmer** (`cw.py`, details in [docs/decoders/cw.md](docs/decoders/cw.md)).
  - **Skimmer, always:** up to 16 stations at once, in the filter passband or SPAN Wide ±3.4 kHz. The CW page is a table of the stations (frequency, call, WPM, SNR and as much of the text as the width takes, the newest at the right); a click opens a row with the whole text (up to 4000 characters), the operator profile and TUNE, and makes it the followed station (LOG, audio spectrum bubble, TUNE in the header; AUTO = the strongest again; CLR empties the table, stations on the air come back with empty text). Stations with their calls (or WPM) at the bottom of the spectrum. A new station first decodes the last 3 s from the buffer, so its first characters are not lost. The keying sidebands and key clicks of a strong station are not taken as stations (a peak within 80 Hz and 10 dB, or 250 Hz and 20 dB, of a stronger one), and two channels that the tone tracking pulls onto one station are merged.
  - **Signal:** each station mixed to 0 Hz and decimated by a CIC to 2 ms steps (its nulls fall where the other stations would alias), a Gaussian matched filter sized by the speed, fine tracking of the tone drift; noise from the spectrum through the real noise gain of the filters.
  - **Soft decisions:** mark level tracked by a Kalman filter on log A (its uncertainty grows in pauses: fading), mark/space log likelihood ratio per step (Rice vs Rayleigh), 2-state Viterbi with a delayed decision instead of a fixed threshold.
  - **Timing:** the operator's profile learnt separately for dot, dash and the three gaps (log-normal); the gaps re-fitted from the recent ones (Farnsworth: character gap 6 dots, word gap 14 – the old decoder broke each letter into a word). Speed from the dot + element gap period (independent of where the threshold cuts the edges). Key type from the jitter: paddle, bug, straight key.
  - **Characters:** beam search over the readings of the elements; a character is written when all likely readings agree. Each character has a confidence (agreement × level of its marks): the text is bright / amber / grey by it; characters made only of noise blips are dropped.
  - **Measured** (`tests/cw_bench.py`, synthetic CW, 10 cases × 7 SNR × 3 texts): mean character error rate 50 % → 19 %; 0 % at SNR ≥ 3 dB in 500 Hz for paddle 12–35 WPM, drift, a neighbour station and static crashes; 35 WPM at 6 dB 23 % → 0 %, Farnsworth 58 % → 3 %, bug 9 % → 1 %, paddle 20 WPM at −3 dB 204 % → 14 %, deep QSB at 0 dB 139 % → 48 %. Unit tests `tests/test_cw.py`.
  - **Block diagram** [docs/images/cw_decoder.png](docs/images/cw_decoder.png) (`docs/cw_diagram.py`): where the decoder takes the signal (after AGC+, Remove DC and SPUR removal, before the channel filter, ALC and DNR) and how it works inside.
  - API: new `cwchan` event (characters of each station); `cwtext` has the confidences `c`; `/api/cw` gives `channels`, `station`, `conf`, `?id=` the whole text of a station; POST actions `follow` and `options` (span saved in the config).
- **RTTY page in the style of an old terminal, with tuning indicators.**
  - **Tuning indicator** right of the text, switchable (remembered in the browser): **CROSS** (crossed ellipses like on old RTTY terminals: mark horizontal, space vertical, a sharp + = well tuned), **WF** (mini waterfall of the passband with the found tones M / S), **BARS** (LED columns of the mark and space level above the noise, needle of the tuning error ±50 Hz), **EYE** (eye diagram ±1 bit around each bit decision). Phosphor persistence; on a narrow screen the indicator is above the text.
  - **Click = tune:** a click into the mini waterfall makes the decoder look for the tone pair only around that point (useful with two RTTY signals in the passband); **AUTO** = the whole passband again (cyan ▲ marks the point).
  - **Text:** characters come out one by one at the speed of the signal (teletype) before a blinking cursor █; characters after recent framing errors are dim amber; the UTC time in the left margin at each new line and after a pause of 6 s.
  - **Info line:** backlit badges Bd / Hz / NORM-REV / LTRS-FIGS (green while locked, blinking while searching, FIGS amber), SNR as an LED bar, the known transmission at the frequency (DWD Pinneberg 147.3 / 4583 / 7646 / 10100.8 / 11039 / 14467.3 kHz, amateur RTTY segments 80–10 m).
  - **KNOWN… list** in the RTTY header: the known transmissions (DWD Pinneberg 147.3 – 14467.3 kHz, amateur RTTY segments 80–10 m); choosing one tunes USB with the signal in the passband (a station in its middle, an amateur segment from its start) and switches the decoder on. `GET /api/rtty` gives `stations` (name, group, kind, hz); the list is `STATIONS` in `rtty.py`.
  - **NO BAUDOT:** a strong FSK signal whose characters keep failing the start / stop check (synchronous or encrypted data, e.g. 75 Bd / 850 Hz on 8204 kHz) is recognised: with Auto speed the other speeds are tried first (amber blinking **CHECKING Bd**), then the amber **NO BAUDOT** badge and no text instead of garbage; it clears by itself when the frames fit again. Measured on synthetic signals: random data at 50 / 75 Bd marked within ~30 s with 6–8 stray characters, Baudot 45.45 / 50 Bd from 22 to 45 dB SNR never marked. Random bits pass the stop-bit check about half the time (0.4–0.6 of the frames), Baudot ~1.0.
  - **Fix:** the Auto speed estimate jumped from 45.45 to 50 Bd mid-text with noise and stayed there (the text turned to garbage); a 50 Bd signal was never recognised below ~9 dB (noise edges made every speed fail).
- **RTTY decoder more reliable** (tuned with the new bench `tests/rtty_bench.py` and a 150 s recording of the WAE contest on 40 m): mean character error rate **45 % → 29 %** over clean, 50 Bd / 450 Hz, contest, selective fading and neighbour cases at −3…20 dB.
  - **ATC** (Kok Chen's optimal automatic threshold correction, as in fldigi): each tone has its own envelope and noise floor and the threshold sits between them, so a selectively faded tone still decides right. Fading at 12 dB 57 % → 28 %.
  - **Squelch per character:** how clearly the tones decided its 7 bits (signal 0.77–0.92, noise between overs 0.33–0.37); opens at 0.55, while open lets through down to 0.42, closes after 3 weaker characters. The garbage decoded from the noise between contest overs is gone, and those noise frames no longer count for NO BAUDOT (in the contest they triggered it and the text stopped).
  - **The start of an over is not lost:** after a new lock, a returning signal or a new speed the buffered last 3.5 s are decoded again (without repeating text already written). After a new lock the text waits 1.5–4 s until the speed is confirmed; a corrected lock or speed then decodes the start again instead of leaving garbage. Clean signal at 6–20 dB 9–14 % → 0–2 %, 50 Bd / 450 Hz 20–82 % → 0 % from 6 dB.
  - **Each over on its own line** (with its UTC time in the margin): a new line whenever the squelch opens again (a new over, or another station after the AFC moved to it); a run of fewer than 3 characters after the squelch opened (a key-up transient between overs) is dropped. A correction of the lock during an over does not break the line.
  - **Speed estimate:** soft match of the segment lengths (mean cosine in half bits) with a margin over the current speed; the "too many short segments" test is relative to the noise.
  - **Contest / several stations:** the AFC prefers a tone pair with a standard shift (170 / 200 / 425 / 450 / 850 Hz ±12) and does not leave a standard lock for an odd pair for 20 s (it paired tones of two stations, e.g. 368 Hz, while the followed station listened). Contest 6–20 dB 18–34 % → 4–7 %; neighbour 6 dB weaker 260 Hz away 25–28 % → 0–6 % from 6 dB.
  - API: `rttytext` has the confidences `q` ("1" sure / "0"); `/api/rtty` gives `q`, `figs`, `sync`, `probing`, `frames_ok`, `focus_hz`, `station`; POST actions `viz` (the page asks for the indicator data every 2 s, event `rttyviz` 10× a second, only while asked) and `focus` (`hz` from the tuned frequency, `null` = whole passband).

### Changes

- **Dragging the spectrum / waterfall keeps the tuned frequency:** a drag outside the passband moves only the shown section, the passband moves on the screen with the signals (dragged further, it stays at the left / right edge of the section and the frequency changes with the drag). Before, the passband stayed in place and the frequency changed under it. Dragging the passband itself tunes as before.
- **"What's new" window** on the first start of a new version: the changes of this version (its part of INSTALL.txt), **MORE INFO** opens the whole CHANGELOG on GitHub, **CLOSE** (or ✕) hides it until the next version (`data\whatsnew.json`, `/api/whatsnew` on the launcher and the receiver).
- **Maps: a click on the map drops the selection** (SONDE, ADS-B, ACARS / VDL2, HFDL, AIS, FT8): the selected mark and its trail were red until another one was chosen; a click anywhere on the map (not on a mark) now gives them their own colors back.
- **Maps: full size after switching the VFO or the view** (all Leaflet maps: SONDE, ADS-B, ACARS / VDL2, HFDL, AIS, FT8, PACKET, ROTOR CONTROL, memories): a map drawn while its pane was hidden stayed a small corner of tiles in the top left until the window was resized; every map now follows the size of its box.
- **ISM: third channel 434.42 MHz** at the 433.92 preset (434.31–434.53 MHz): car keys at 434.40 MHz (e.g. VW / Škoda / Audi) fell between the channels and were not even seen as RAW. Most keys send rolling codes rtl_433 cannot decode: they show only with **RAW** on, not in DEVICES. One more rtl_433 process.
- **ISM: mark a RAW signal with a name** (✎ at the end of a RAW row), e.g. your car key: the signature (frequency ±30 kHz, modulation guess, pulse count ±30 %) is saved in `data\ism_devices.json` and later matching packages show with that name and become a device in DEVICES and TIMELINE (category RAW). An empty name removes the mark.
- **DAB: channels in memory are green** in the CHANNEL list (the tooltip names their memories); the list itself is green while such a channel is chosen.
- **SONDE: 403 MHz key** in the header of the page: tunes the VFO to 403.000 MHz (the middle of the radiosonde band 400–406 MHz) in FM and switches the decoder on; lit while the VFO is there.
- **SONDE map: radiosonde launch sites in Europe** (switch *Launch sites* on the map). A click on a site: WMO number, height, the sondes it launches with their frequency (green = decoded by RADIMCOM), launch times (UTC), the next launch and whether its sonde is probably in the air, usual ascent / burst / descent, distance and azimuth from the QTH. Green pulsing = launched within 2.5 h, amber = launch within 1 h. The list comes from SondeHub (`sondehub.org`), downloaded by the server when the map first needs it and kept a week in `data\sonde_sites.json` (`sonde_sites.py`, `GET /api/sonde/sites`); **own sites** (e.g. military ones SondeHub does not list) or changes of a listed one in `data\sonde_sites_extra.json`, format in [docs/decoders/sonde.md](docs/decoders/sonde.md#own-sites-datasonde_sites_extrajson).
- **Fix: auto squelch noise floor from the spectrum** (by Brano, brjanicek, PR #17): the line that sets `asq_spec` and `wf_power` at the start of the receiver had been glued into the comment of the line before it, so it never ran.
- **Map tabs no longer stop the main window.** The browser (and the window of RADIMCOM.exe) keeps at most 6 connections to one receiver for all its windows; the main window holds the events and the audio of each VFO and every map opened in a new tab (□ key: APRS, ACARS, HFDL, AIS, ADS-B, FT8) held its own event stream to every VFO. With 3–4 map tabs the connections ran out: the audio stopped and the page did not respond, as if the server froze. Now the main window passes its events on to the map tabs (BroadcastChannel; not the waterfall rows and meters); a map tab opens its own stream (only of its VFO) only while no main window is open.
- **FT8 table redesigned:** fixed column widths with every header aligned like its column (numbers right); SNR as a value + coloured bar (−24…+20 dB, red / amber / green); DT amber over 0.5 s, red over 1 s; audio offset as a marker in the 0–3 kHz passband; the message in coloured tokens (CQ badge, callsigns, grid locator, report, 73 / RR73) and a coloured edge by its kind; the cycle separator shows the number of decodes, the slot (even / odd) and a strip with a tick per decode at its audio offset.
- **Zoom 64×** for the spectrum and waterfall (24 kHz at 1.536 MS/s): the section is taken from a finer FFT of 65536 points (23 Hz per point, 3 segments with 50 % overlap), not stretched from the 32× points; computed only at 64×.
- **Server log to a file:** the console window shows only where the log is; the output of the launcher and of all VFO processes (messages, errors with tracebacks, output of the SDR libraries and helper programs) goes to `data\server_logs\logs_DDMMYYYY_HHMMSS.log`, a new file at each start (date and time of the start), shared by all VFOs (`serverlog.py`). Lines of successful web requests (the page polls several times a second) are left out, failed ones (4xx, 5xx) stay.

- Band keys have no LED window any more; the lit band key is only pressed in with a yellow legend.
- FILTER in DSD (one key, 12.5 kHz): a key of normal size in the upper row like ATU and DEC, not one tall key.
- ISM ON turns RTL2832 AGC and tuner AGC on (AGC+ and Remove DC peak off); ISM OFF gives back the gain, RTL AGC, AGC+ and Remove DC peak from before.
- SCAN → CHANNELS (memories): keys **☑ ALL** / **☐ NONE** tick / untick SCAN of every memory listed at once.
- SCAN: the whole tab scrolls – the tiles and the channel chips go up and away, the bar of keys (START / STOP,
  HOLD, SKIP, LOCK OUT, ◀ ▶, status) stays on top and CHANNELS / ACTIVITY / HEATMAP fill the rest of the height.
  The wheel over the table first scrolls the tiles away, then the rows.
- SCAN → ACTIVITY: the table uses the full width of the tab (Name takes the free space, Note a share).
- SCAN → CHANNELS: the table uses the full width of the tab (Name takes the free space, long names are cut later).
- SCAN → ACTIVITY: wider Name column (long channel names are cut later).
- SCAN → ACTIVITY: the filter, CSV and the player stay on top while the rows scroll (the column heads under them).
- SCAN → HEATMAP: the table uses the full width (the hour columns share the free space, wider Name column).
- SCAN → HEATMAP: sorted by occupancy, the busiest frequency first (was by frequency).
- SCAN: after switching the VFO, CHANNELS / ACTIVITY / HEATMAP could still show the scan of the previous VFO
  (a late answer of the previous VFO was taken). Answers of the VFO switched away from are now dropped.
- SCAN → HEATMAP, THIS SCAN: a timeline - one column per hour from the start of the scan, a row of days above
  the hours; a scan longer than 24 h no longer sums the same hours of different days. The table scrolls sideways
  (Frequency / Name / Total stay in place) and follows the newest hour; at most the last 14 days.
  Older history (SHOW 1 day...) stays hours of the day 0-23 summed over the days.
- VFO windows: the SQL bar is a slightly darker orange (like the green RF bar).
- Waterfall settings: new colour scheme **Matrix** – like Ice, but green (black – deep green – phosphor green –
  pale green-white).
## Ver. 0.114

Released after the test beta (GitHub branch `0.114beta1`). Many parts are contributed by **Brano, [brjanicek](https://github.com/brjanicek)** (marked *by Brano*).

### Package fix (13 Nov 2026)

- The first 0.114 package was missing `adsb.py`, so the server did not start (`No module named 'adsb'`). The packages were rebuilt; the package builder now stops when a module imported by the program is not packaged.
- Windows Defender could report the upgrade zip as `Trojan:Script/Sabsik.FL.A!ml` (a false positive of its automatic heuristic). The program no longer starts PowerShell for this: the DSD decoder download falls back only to `curl.exe` of Windows, the upgrade from the page ends leftover decoders through the Windows API, and install.bat makes the desktop shortcuts without `-ExecutionPolicy Bypass`. The `.bat` files in the package have Windows line endings.

### Main Features

- **DNR key (Dynamic Noise Reduction) – weak HF voices out of the noise.** A new key **DNR** in **AUDIO**, right of ALC, for AM / LSB / USB / CW. It makes weak signals easier to hear in the noise: the noise between words is turned down, the speech stays at its full level, so the voice stands out of the noise instead of drowning in it. Two parts, both on by default and ticked in SETTINGS › AUDIO › DNR:
  - **EXP – expander with a voice detector.** Every 8 ms the audio goes through an FFT; each frequency of the passband has its own noise floor. Speech has harmonics that stand out of the noise even when it is hardly louder than the noise, the HF noise is flat – so speech is told apart from noise also at a low signal-to-noise ratio. On speech it opens at once (in time for the start of a syllable), after it holds a while and closes in 80 ms to the *depth*. In CW it watches only the CW passband.
  - **EXP AUTO** (on by default) sets the expander by itself: an opening on a noise blip lowers the sensitivity, weak speech left closed raises it, a reopening soon after closing in the middle of speech (a chop) makes the hold longer (180–350 ms), and the depth follows the measured speech-to-noise ratio (8–18 dB). It settles in about 2–3 s; after a retune or a new mode it starts again in a fast mode. *Now* in the settings shows the values in use. AUTO off: depth 3–30 dB (default 12), sensitivity 1–10 (default 5) and hold 20–1000 ms (default 100) by hand; the measured SNR is shown in *Now* in both modes.
  - **LIM – soft limiter** instead of the hard clipping: the peaks are rounded, not cut; with ALC +4 dB louder.
  - **Smooth ALC gain** (SETTINGS › SDR DONGLE › ADVANCED, by AGC+, on by default): the ALC gain rises in a smooth ramp instead of steps – no clicks and no zipper noise; it still falls at once.
  - The VFO window shows **DNR** in green (annunciator row after ALC, AFI moved after ASQ) while DNR is on; **ATU** moved to the right end of the CTCSS / DCS row, right-aligned with CONV under it.
  - The AUDIO key group has 7 columns now; the gaps between the key groups are a little smaller so the row fits. SETTINGS › AUDIO is rearranged: HPF / LPF and AFI, ASQ and TSQ, DNR in its own column.
  - Server: keys `dyn`, `dyn_exp`, `dyn_exp_auto`, `dyn_exp_db`, `dyn_exp_sens`, `dyn_exp_hold_ms`, `dyn_lim`, `agc_smooth` in `/api/set` and the state, `dyn_exp_info` (the values in use) in the state.
- **New look – a front panel like a real rack receiver.** The head is laid out anew: **one glass over all the displays** (S-meter, the four VFO windows, the clock with the AD), the **VFO keys under their windows**, each with its own **CUE** key, the **function keys as modules of two rows** with the legend over each group, the **master column at the right** (logo, MONITOR faders with the level meter, speaker, RECORD) and the **band keys across the whole width**; rack ears with screws at both edges, the lower part with the tabs sunk deeper into the panel.
  - **Keys with an LED window and a colour for each key group** (VIEW white, MODE yellow, FILTER orange, GAIN green, STEP cyan, TUNE lime, AUDIO violet, DECODE fuchsia, TRACKING blue, MENU teal); the lit tab of the lower part and the accents inside it have the colour of the group whose key opens it.
  - **Details of a real set:** the clock with faint unlit segments, the date and LOC / UTC; faders with a dB scale and ribbed caps; the level meter with dB numbers, peak hold and a CLIP LED for each channel; the logo printed on the panel; in the VFO windows the mode is aligned with RX and the unlit CTCSS / DCS are as dark as the other annunciators.
- **ISM: about twice as many messages, RAW packages** (by Brano, brjanicek). rtl_433 does not filter: it finds pulses in the envelope of everything it gets, so with the whole 2.048 MS/s the noise of 2 MHz and all transmitters in it merged into long "packages", of which at most one device was decoded. RADIMCOM now cuts **narrow channels of 256 kS/s** out of the dongle samples (mixed down, 129-tap low-pass, decimated by 8, in the thread that feeds each channel) and runs one rtl_433 for each: **433.92** and **433.42 MHz** (Somfy and others) at the 433.92 preset, **868.30 MHz** at the 868.30 preset; the tooltip of the counter shows them. Measured on a 5 min recording at 433.92 MHz: 107 messages from the whole band, 236 from the 256 kS/s channel (the rtl_433 options `-Y autolevel / minsnr / magest / minmax` did not help at 2.048 MS/s), and rtl_433 needs about 6× less CPU. **RAW** checkbox: rtl_433 also runs its pulse analyzer (`-A`), and a package of at least 20 pulses that no decoder read is shown as a grey row – modulation guess, pulses, length, the demodulated bits, the flex decoder hint in the tooltip and **⧉** to see the pulses at triq.org/pdv (not written to the log); packages of one kind within ±15 kHz in 10 s are one row with ×N (an unknown transmitter or interference that keeps sending). One packet read by two decoders of rtl_433 (same level and frequency, e.g. LaCrosse TX29IT / TX35DTHIT, Auriol-AHFL / Vauno-EN8822C) is **one row** with both names; a repeated message joins its row (×N) also when another device sent in between; units are converted to SI by rtl_433 (`-C si`: °C instead of °F, km/h, mm). rtl_433 messages and errors are read with `-F log`. API: `ism_raw` in `/api/set` and the state, `raw`, `raw_count`, `channels` in `ismstate`. Tests in `tests/test_ism.py`.
- **SCAN: scanner of memories, frequency ranges and the FM broadcast band** (the design in `data\poznamky_scan.md`). New key **SCAN** in the MENU group shows the **SCAN** tab (one switch for all VFOs, like MEM and RECS; the LED of the key blinks in the colour of its lit legend while the active VFO scans, the tab has a green ●) with the pages **CHANNELS**, **ACTIVITY** and **HEATMAP**. The scan runs on one VFO, the other VFOs keep working.
  - **How it scans:** not channel by channel. Every block (~85 ms) the power of **all channels in the band the dongle receives** is measured from the waterfall FFT (with the spur mask when SP is on), so the whole tuner window is checked at once – tens of channels per second for memories, the 2280 channels of the airband (118–137 MHz, 8.33 kHz) in about 17 tuner windows. The tuner is retuned only to reach the next window (0.75 × sample rate, the centre away from the channels when it can be; 2 blocks are thrown away after a retune). After listening the scan goes on with the next window, so one busy band does not hold it.
  - **What is scanned – four tiles** (MEMORY / VISIBLE BAND / RANGE / FM BCAST), the one chosen is lit and only its settings are shown: **MEMORY** = ALL MEMORIES, FAVOURITES or one GROUP, each channel in its own mode; **VISIBLE BAND** = the part of the spectrum shown now (taken at START; bandwidth of the VFO for the mode, grid of half the width; **the tuner is not moved**, the spectrum and waterfall stay as they are and the whole band shown is scanned at once); **RANGE** = FROM / TO / STEP / MODE / BW with presets (Airband 118–137 MHz AM 8.33 kHz, PMR446, 2 m, 70 cm, LPD433, Marine VHF, CB 27 MHz). VISIBLE BAND and RANGE scan in **AM or FM** only – the MODE keys choose it and switch the VFO to it too (SSB and CW have no carrier for the squelch of the scan, WFM has its own tile; a range saved with another mode is read as AM, WFM as FM). **PICK** NEXT / STRONGEST for a band / range. The lit tile points with an arrow at the card with its settings (memory groups and presets are chips, each tile shows its number of channels); a click on another tile while scanning stops the scan, a click on another chip or mode key continues with it (the VFO shows the mode scanned at once).
  - **FM BCAST – search the FM broadcast band:** a fourth tile right of RANGE, scans **88–108 MHz in WFM** with its own algorithm, made for broadcast stations: the grid is 50 kHz (the 100 kHz raster and the stations between it), only the **core ±18 kHz** of each channel is measured (the energy of a broadcast FM signal is the densest at its centre) and a station is taken only where it is the **strongest point ±100 kHz around**, so the VFO lands on the **centre of the station**, not on its side; the tuner centre is put halfway between two grid points (the DC spike is out of every core). A station is on the air for good, so it is heard **LISTEN** seconds (8 s) and the scan goes on to the next station up the band, after the top of the band from 88 MHz again (no carrier lockout, no jump to the next window while the window has more stations). The bandwidth tuned is that of the VFO for WFM (at least 150 kHz). A station found is measured 3 more blocks and the strongest point ±100 kHz summed over them is tuned (the core power of FM goes up and down with the audio, one block could pick its side: 98.45 instead of 98.5 MHz), and the grid point just above the station heard is not taken as another station. **STORE FOUND** stores each station as a WFM memory in the group **FM YYYY-MM-DD**, named by its **RDS PS** when it was received; ACTIVITY shows the PS too. **◀ ▶** step to the previous / next station found.
  - **Squelch of each channel:** new optional memory fields **`scan`** (false = never scanned), **`scan_sq`** (own level, dBFS), **`scan_asq`** (own auto squelch margin, dB) and **`scan_prio`** (priority channel); older versions ignore them. **AUTO SQUELCH** (on by default) gives the channels without their own SQ the auto squelch: the noise floor of each channel = a low percentile of its own last 40 measurements (it learns spurs, the DC spike and local noise; it learns only while the channel is quiet, so a long transmission does not end itself), before that the noise density of the spectrum; + **MARGIN** (6 dB). Without it a channel uses the squelch level of its mode; when that squelch is off too, the auto squelch is used (no channel is left out or held open by noise). Channels left out at START (SCAN unchecked, DAB / DSD, out of the range of the VFO) show the reason in the State column, also when no channel is left to scan.
  - **Keys:** **START / STOP** is one key; **HOLD / CONTINUE**, **SKIP**, **✕ LOCK OUT** (the channel heard now is left out until STOP, as ✕ in its row – no need to look for its row in the table) and **◀ ▶** (hold on the previous / next channel) are shown only while scanning; **● REC**; tuning by hand (or recalling a memory) holds the scan. The seldom changed settings (AUTO SQUELCH + MARGIN, CONTINUE, PRIORITY EVERY, CARRIER LOCKOUT, PICK, KEEP HISTORY) are behind **⚙**, whose key shows their summary. REC, STORE FOUND and the ⚙ settings changed while scanning go into the running scan at once; what is scanned changes only with START. The status display beside the keys shows the state, the channel and a bar with its level and squelch.
  - **CONTINUE:** AFTER SIGNAL (2 s after the signal drops, replies are heard), AT ONCE or AFTER TIME (after the set time even while the signal lasts).
  - **Priority channels:** in the same tuner window they win at once over the channel heard; in another window the scan looks at them every **PRIORITY EVERY** s (3 s; the audio stops for ~0.3 s, the look does not count into the hang).
  - **Lockouts:** **SKIP** (leave the channel and skip it for 5 min), **✕** in a row of the table (locked out until STOP, again = back in), and **CARRIER LOCKOUT** (OFF, 30 s … 30 min; 3 min): a channel open longer than this without a break – a carrier or a spur – is locked out until STOP and written to the activities.
  - **REC:** each activity is recorded to a WAV file in the subfolder `scan` of the recordings folder (SETTINGS › GENERAL › RECORDINGS), with the 0.5 s before the signal came back in the hang (the start of a reply is not cut off); ▶ in ACTIVITY plays it.
  - **STORE (search & store)** for a range: every frequency heard for at least 1 s is stored as a memory in the group **Scan YYYY-MM-DD**, unless a memory is already there (same mode within 50 Hz).
  - **Page CHANNELS:** for memories all channels of the source with **SCAN ☑, SQ, ASQ, PRIO** editable in place (saved in the memory and taken by a running scan at once); for a band / range the channels heard, active or locked out. Live level, noise, squelch, hits, last activity, ✕, state; the channel heard has a speaker icon. While scanning the rows are not rebuilt under the mouse and ✕ reacts on pressing the button, with a larger hit area, so it is easy to hit. The columns of the SCAN tables are as wide as their content (not stretched over the page); long names are cut (full name in the tooltip).
  - **Pages ACTIVITY and HEATMAP:** every activity (time, VFO, frequency, name, mode, length, max. level, SNR, file, note) is always written to `data\logs\scan_YYYY-MM-DD.csv` (UTC, all VFOs; there is no LOG switch). **SHOW › THIS SCAN** (default) shows only what the scan of this VFO heard on the source it runs: a START of **another source, group or range** (another visible band too) begins a new scan session, so ACTIVITY and HEATMAP start empty; **CLR** empties them by hand. TODAY / 7 DAYS / 31 DAYS / ALL KEPT show the history; it is deleted (with the WAV recordings of the scan) after **KEEP HISTORY** days (31). Filter, CSV export, ▶ plays the recording, a double click tunes. A row at the frequency of a stored channel (nearest within 500 Hz, the same mode first) shows its name when the row has none (a RANGE / FM BCAST scan; the RDS PS stays) and its note in the Note column, before the note of the scan (carrier lockout); also in the filter and the CSV.
  - **HEATMAP:** occupancy from the log, frequency × hour of the day (local time) for 1, 7 or 31 days, the 60 busiest frequencies; a click tunes it.
  - Only frequency, mode and width of a memory are used (its decoder and recording are ignored); the baseband decoders of the scanning VFO pause (FT8, WEFAX, CW, RTTY, PACKET, SSTV, ACARS), DAB / VDL2 / ISM / HFDL / AIS must be off (they hold the dongle). A chained VFO scans only the channels in the band of its shared dongle. New module `scanner.py` (runs in the receiver thread), API `/api/scan`, `/api/scan/log`, `/api/scan/heatmap`, `/api/scan/rec/<file>`, FM BCAST: option `fm_s`, source `fmbc`; options saved per VFO (`config_X.json` → `scan`), tests `tests/test_scanner.py`. Not tested on a real signal yet. Not done: the SCAN / SQ / ASQ / PRIO columns in the MEM editor, CTCSS / DCS as a scan condition, satellite Doppler scan.
- **ADS-B decoder: aircraft on 1090 MHz** (by Brano, brjanicek). A new **ADS-B** page in DECODERS (between AIS and ISM). **ON** (or the **1090.000** key) takes the VFO to 1090 MHz at **2.4 MS/s** (an Airspy stays at 2.5 MS/s), mutes its audio and turns off ACARS, VDL2, DAB, ISM, HFDL and AIS, which need the dongle elsewhere (and they turn ADS-B off); OFF gives the previous sample rate back. Decoded in RADIMCOM itself, numpy only, no external program (new module `adsb.py`): the magnitude of the raw samples is integrated, so the energy of each half microsecond is read at any sample rate from 2 MS/s up; preambles (pulses at 0, 1, 3.5, 4.5 µs) are found in the whole block at once, each is sliced at 5 sub-sample phases into 56 / 112 bits, and the 24-bit CRC of all candidates is computed at once from a table of the syndrome of each bit. A wrong single bit is corrected by its syndrome, and up to 3 of the 5 least certain bits are tried for a DF17 – both only for an aircraft already heard (counted as "fixed"). Messages: **DF17 / DF18** ADS-B (flight and emitter category, airborne and surface positions with **CPR** decoding – global from an even and an odd message within 10 s, then local from the last position, with a speed check –, barometric and GNSS altitude, ground speed and track or airspeed and heading, vertical rate, squawk and emergency, selected altitude and QNH, TIS-B / ADS-R marked), **DF11** all-call replies (an unknown address needs two) and the radar replies **DF0 / 4 / 16 / 20** (altitude) and **DF5 / 21** (squawk), accepted by their parity = the address of an aircraft already heard. Three views: **AIRCRAFT** (flag from the ICAO address, ICAO → globe.adsb.fi, flight → adsb.lol, squawk – 7500 / 7600 / 7700 in red, the row too –, altitude with ▲▼, V/S, GS, track, position, **distance and azimuth from the station location**, category, signal, messages, age; grey after 1 min, dropped after 10 min), **MAP** (dark OpenStreetMap, aircraft turned to their track with flight + altitude labels, their tracks, the QTH with range rings 50 / 100 / 200 / 300 km, the list beside it; □ opens it alone in a new tab, `?map=adsb`) and **MESSAGES** (the last 300: UTC, signal, ICAO, DF, kind, decoded data, hex; a click holds the list still). **LOG** writes one line per aircraft at most once a minute to `data\logs\adsb_YYYY-MM-DD.txt`. **adsb.fi**: each aircraft is looked up once on adsb.fi (adsb.lol when adsb.fi does not answer; 1 request a second at most, needs internet) for its registration and type (new column **Reg / Type**, the description in the tooltip); an aircraft heard here without a position of its own (only radar replies, or no position message yet) is looked up again every 30 s and shown with the position adsb.fi sees – blue in the list (position, distance, azimuth, call sign) and a blue aircraft on the MAP. **RANGE** on the MAP: the farthest positions decoded here, in 2° sectors around the station, as four outlines – aircraft up to **10 000 ft** (green), **20 000 ft** (yellow), **30 000 ft** (orange) and at any altitude (**max**, violet), the farthest point of each with its distance, altitude and time in a tooltip; only positions confirmed by a previous one count, and for an aircraft heard here (a valid message within 30 s) without a position of its own the position adsb.fi sees; kept over restarts in `data\adsb_range.json` (saved once a minute and at OFF, merged with the file, started again when the station location moves more than 2 km); **CLR RANGE** (two clicks) empties it; `GET /api/adsb_range`, `POST /api/adsb {"action": "clear_range"}`. Narrow scrollbars (6 px) in the card, like MEMORIES and ROTOR CONTROL. The memory decoder field has **ADS-B** too. Server: `/api/adsb` (GET, POST clear), events `adsb` (once a second: changed aircraft, new messages) and `adsbstate`, keys `adsb` in `/api/set` and the state, `adsb_freq`. Tests in `tests/test_adsb.py` (known messages, CPR, the demodulator on synthetic pulses at 2.0 / 2.4 / 2.5 MS/s, noise). Tested on a real signal with an RTL-SDR at 2.4 MS/s: about 80–150 messages a second, 0 dropped blocks, range up to 270 km. → [ADS-B](docs/decoders/adsb.md)
- **DAB and DSD are modes with their own tabs** (by Brano, brjanicek). MODE has a new key **DAB** (between CW and DSD): it turns DAB on and opens the **DAB** tab next to SPECTRUM with the DAB+ card (the ON key of the card is gone); another mode, a band button or a memory that is not DAB turns DAB off and the tab goes away. **DSD** opens its own **DSD** tab (green ● = a new call while it is not open) instead of the DSD page of DECODERS. The DAB and DSD pages are gone from DECODERS. While DAB is on, the DAB key is lit in MODE and the VFO window shows DAB; the FILTER keys are empty (fixed width). A VFO whose saved tab was DAB / DSD opens it again when the mode is still on.
- **MEMORIES: modes DAB and DSD** (by Brano, brjanicek). The mode of a channel is chosen from AM, FM, WFM, LSB, USB, CW, **DAB** and **DSD**. **DAB**: the DAB channel is chosen in the form (the frequency is its centre and cannot be typed), recalling the memory turns DAB on with that channel; the DAB channel field is off for the other modes, and another mode chosen for a DAB memory ends its DAB channel. DAB and DSD have a fixed width (1536 / 12.5 kHz, the field is off). Memories saved with a DAB channel and another mode (older versions) are read as DAB; an import with the mode DAB and no `dab_channel` takes the channel whose centre is at the frequency. CHANNELS, the IMPORT / EXPORT lists and ＋ SAVE CURRENT (while DAB is on) use the mode DAB; in the IMPORT / EXPORT lists the frequency cell of a DAB row is a dropdown of the DAB channels too, and exported DAB channels carry the centre frequency as well.
- **MEMORIES: simpler channel form** (by Brano, brjanicek). Two columns: the channel and its groups. The basics are the name, the mode, the frequency (or the DAB channel for the mode DAB, as a dropdown in the same place) and the groups; **ADVANCED** shows the other fields (bandwidth, decoder, record, colour, favourite, tag, LAT / LON with CHOOSE ON MAP, note) under the basics, which do not move. Shown or hidden is remembered in the browser.
- **DAB now on air in the AD window.** While a DAB station plays, the AD (additional display) under the S-meter shows it in the place of RDS, in the same colours: the **DAB / DAB+** tag, the station name, the **SNR** of the ensemble (green from 12 dB, yellow from 8 dB, red below) and under them the **DLS text** (artist / song); a text wider than the window runs to its end and back. Priority of the AD: 1. errors, 2. rotor AZ / EL (MONITOR), 3. DAB, 4. RDS.
- **ROTOR CONTROL: page CONNECTION – which sources move the rotor.** The RCTRL tab has the pages **MAP** (the map as before) and **CONNECTION**: a block diagram of the three sources of the wanted AZ / EL – **SAT TRACKER** (SATELLITES › TRACK), **MEMORY RECALL** (a recalled channel with a location) and **RCTRL MAP** (a click on the map, a point or the list) – each wired through a **knife switch** to one AZ / EL bus and on to the **ROTOR** block (a compass dial with the antenna needle and the target mark, AZ / EL readout, an elevation bar, the port and its state, an ACTIVE / ISOLATED badge). A click on a source card or its switch connects / disconnects it: the lever swings closed / open, a connected source, its wires and the bus are green with a running flow towards the rotor (LINKED), a disconnected one grey and dashed (OPEN). The diagram is drawn once and then only updated, so the needle turns smoothly with the rotor. The rotor block **glows green** while at least one source is connected, **grey** when none is. A disconnected source does not move the rotor: the SAT TRACKER only calculates the pass (TRACK shows **CALC ONLY**, and the rotor takes hand commands again), a recalled memory only tunes (the rotor and the RCTRL tab stay – so going through a band does not swing the antenna at every stored channel), a click on the map only draws the target. The switches belong to the station: saved in `data\rotor.json` (key `links`), for all VFOs and browsers; the server refuses a `goto` of a disconnected source (`/api/rotor` POST `{"links": {...}}`, `goto` with `"source": "map" / "mem"`). Tests in `tests/test_rotor_settings.py`.
- **ROTOR CONTROL from a recalled memory.** Recalling a MEMORIES channel that has a location (LAT / LON) – a row of MEMORIES › CHANNELS, a memory tag in the spectrum, RECALL in the editor or the memory step – opens the **ROTOR CONTROL** tab (the RCTRL key goes on), centres the map on the channel and turns the rotor to its azimuth from the QTH (elevation 0), as a click on its point would. Channels without a location work as before. A DAB channel with a location turns the rotor too, but the **DAB** tab stays in front.
- **ROTOR CONTROL: the points are the MEMORIES channels** (by Brano, brjanicek). The map shows every channel of MEMORIES with a location (LAT / LON) instead of the overlay lists; beside the map **GROUPS** has one row with a checkbox per group of these channels (with their number, *(no group)* for channels without a group, **ALL** / **NONE**), remembered in the browser; a channel in several groups is shown while any of them is on. The list (nearest first, azimuth, distance, filter) and the tooltips show the frequency, mode, groups and note; a click still turns the rotor and scrolls the list to the row of the point; the channel aimed at last is selected and scrolled into view in MEMORIES › CHANNELS when that tab opens next. A change in MEMORIES shows on the map at once. The **OVERLAYS** page and **+ ADD POINT** are gone, and with them the built-in lists (`static/overlays/`), `overlays.py`, the API `/api/overlays` and `tests/test_overlays.py`; own groups saved in `data\overlays\` are no longer read (the folder can be deleted). The scrollbars of the group box and the list are narrow (6 px).
- **Station location moved to SETTINGS › GENERAL › LOCATION** (new page beside UI and ROTOR). The locator or latitude / longitude, **CHOOSE ON MAP** (OpenStreetMap) and the altitude were on SATELLITES › SETUP; now they are one setting for the whole receiver, used by the satellites (passes, Doppler, rotor tracking), the packet decoder (APRS distances and map), HFDL and AIS (maps). Saved in `data\location.json` (new module `location.py`, API `/api/location`); it works without the sgp4 package, so the decoder maps get the QTH even without satellite tracking. A new installation starts at **0.0 / 0.0**; an existing installation takes over the station saved in `sat_setup.json`. SATELLITES › SETUP shows the location with a **LOCATION…** key that opens the page, and a warning while it is 0.0 / 0.0; the minimum elevation of a pass stays there.
- **SETTINGS split into GENERAL and VFO.** **GENERAL** holds what belongs to the whole station: **SKINS**, **S-METER** (layout), **TOUCHPAD**, **LOCATION**, **ROTOR** and **RECORDINGS**, side by side (the UI page with its own second row is gone). **VFO** holds the settings of one VFO: on the left the keys **VFO-A … VFO-D** in the style of the VFO keys beside the S-meter, the lit one joined to the card on the right (same background, no border between them, like an open folder tab); the card has the pages **SDR DONGLE**, **ADVANCED** (dongle list, SP, AGC+ and now the **S9 calibration** of the S-meter, moved from the S-METER page), **AUDIO** and **TX** (LimeSDR). A VFO key there switches the active VFO and SETTINGS stays open. The pages open last time are remembered, also those saved by older versions.
- **One rotor for the whole station, no longer tied to a VFO.** Its settings (ON / OFF, port, azimuth calibration, the last K3NG azimuth) moved from the config of one VFO (`config_X.json`, key `rotor`) to **`data\rotor.json`**; the launcher moves them at the first start. The serial port is held by the receiver of the first VFO in `vfos.json` (`/api/vfos` marks it `"rotor": true`), and the page sends all rotor commands, the ROTOR page, MONITOR and the satellite rotor tracking (TRACK) there, whichever VFO is active; the Doppler correction stays with its VFO. The other VFOs answer `/api/rotor` and `/api/sat/rotor` with 409 and the name of the rotor VFO. **MONITOR** is one switch for all VFOs (it took over the setting of the active VFO).
- **ROTOR CONTROL: aim the rotor from a map.** The key group SAT is renamed **TRACKING** and has a new key **RCTRL** that shows the **ROTOR CONTROL** tab (one switch for all VFOs, like MEM and RECS). Page **MAP**: a dark OpenStreetMap map (as AIS / HFDL); a click anywhere (crosshair), on an overlay point or on a row of the list beside the map turns the station rotor (from any VFO) to the azimuth of that place from the QTH (great circle), elevation 0. A dashed line shows the wanted azimuth to the target (stays until **CLEAR**, remembered in the browser); a green sector of the antenna beam width (**BEAM**, default 30°) shows where the antenna points now and turns with the rotor; STOP stops the motors. When the rotor cannot take the command (off, fault, satellite tracking running) the target is drawn and the reason is shown. Groups of points switched on beside the map; the three built-in default groups are **DAB+ SR** (15 sites with channel, power and programmes), **FM BCAST SK/CZ** (51 main sites with their FM programmes) and **HAM repeaters SK/CZ** (163); the list shows the points of the overlays that are on, nearest first, with azimuth and distance, and a filter. **+ ADD POINT** puts the map target into a chosen group. Page **OVERLAYS**: the groups are editable – **+ NEW GROUP**, **IMPORT AS NEW GROUP**, and on each card **EDIT** (name, colour, a table of the points: add, change, delete; the position as lat / lon or a QTH locator; **+ MAP TARGET**), **IMPORT** (replaces the points), **EXPORT**, **RESET** (an edited built-in group back to its built-in list) or **DELETE** (own group); edited and own groups are saved in `data\overlays\`. Built-in lists in `static/overlays/` (from Wikipedia, przemienniki.net and cq.sk, 2026-11-11), new module `overlays.py`, API `/api/overlays`.
- **Folder of the recordings selectable: SETTINGS › GENERAL › RECORDINGS** (new page after ROTOR). A full path on this PC (for example `D:\Recordings`; a missing folder is created and must be writable), **SAVE**, or **DEFAULT** back to `data\recordings` (shown on the page). One folder for all VFOs: REC / REC SQ of every VFO write there and the RECORDINGS tab lists it; a recording that is running finishes its file in the old folder, already recorded files are not moved. Saved in `data\recordings.json`, API `/api/recording_folder`.
- **Tone squelch: TSQ-C (CTCSS) and TSQ-D (DCS)**, two new keys in the AUDIO group, for FM. They add to the squelch of the SQL bar or ASQ: the audio passes only while that squelch is open **and** the set tone / code is received (without the SQL bar and ASQ the tone alone opens it); one of them at a time. **CTCSS** – all 50 standard tones 67.0–254.1 Hz; the power at the tone over 0.45 s against the power ±5–11 Hz around it, so even the closest tones (67.0 / 69.3 Hz) are told apart. **DCS** – the 104 standard codes, polarity N or I; the 23-bit Golay codeword at 134.4 bit/s is folded over its period and correlated with the set code at all shifts. Both open about 0.3 s after the tone starts and close about 0.5 s after it stops; with a key on, the tone is filtered out of what you hear (300 Hz high-pass). The tone and code are chosen in **SETTINGS › VFO › AUDIO** or with the **mouse wheel over the key**. The VFO window has a new row between the frequency and the info row: **CTCSS 88.5** and **DCS 023N**, dark like the unlit annunciators = off (or not FM), orange = on, lit orange box = received now. New module `tonesq.py`, API keys `ctcss`, `ctcss_hz`, `dcs`, `dcs_code`, tests `tests/test_tonesq.py`. Not tested on a real signal yet.
- **ACARS / VDL2: MESSAGES / AIRCRAFT / MAP views**, like HFDL. **AIRCRAFT** lists every aircraft heard, newest first, with its newest data: last time, flag, flight, registration, ICAO address, type, model, flight level, speed and squawk from ADS-B, newest position (a click shows it on the MAP), its source and age, the VDL2 ground station of the last message and the number of messages. **MAP** shows the aircraft with a known position on the dark OpenStreetMap map, turned to their heading, with their tracks (white; red = selected), the label flight + type, the QTH and a list beside the map (flag, flight, registration, ICAO, type, flight level, age; a click centres the aircraft and opens its popup with the ADS-B data and adsb.fi / adsb.lol links). Positions come from **ADS-B** (looked up at the time of the message), **ADS-C** reports (FANS in ACARS and now also ATN ADS-C over VDL2) and, on VDL2, from the **XID frames**: the approximate location an aircraft sends when it sets up or hands off its link – so also aircraft that send no ACARS. Ground stations that broadcast their position in XID are drawn as green ▲. The same aircraft seen by its ICAO address, registration and flight is joined into one. The **□ key** in the top right corner opens the map alone in a new tab (`?map=acars`). Server: `vdl2.py` reads the XID positions (`on_pos`), `acars.py` keeps the last 3000 (`/api/acars` → `positions`, `gs_pos`; event `acarspos`); CLR clears them.

### Minor Fixes

- **New screenshots in the docs** for the 0.114 look: main screen and WFM with RDS (with the whole waterfall), all SATELLITES pages, and new ones of SCAN, ROTOR CONTROL (MAP, CONNECTION), MEMORIES (CHANNELS, GROUPS), RECORDINGS, SETTINGS (SKINS, S-METER, VFO) and the SSTV / WEFAX galleries; README has four more in Screenshots.
- **RECS key tooltip** showed a broken path (`data` + line break + `ecordings`); it says `data\recordings` again.
- **Keys inside the tabs in the colour of the tab:** the lit keys of the `.bands` kind (the band and view keys of the decoders: FT8, ACARS, HFDL, AIS, ADS-B, WEFAX, ISM, SSTV, PACKET) had a yellow LED line instead of the colour of the tab; the gold keys in RECORDINGS (play) and SETTINGS (SAVE of the location and the recordings folder) are keys like the others with the legend in the colour of the tab, and the new row flash in the decoder tables, the edited row in MEMORIES and the block diagram in SETTINGS follow the tab colour too.
- **DECODERS: page keys in groups** (by Brano, brjanicek). The page keys are ordered CW, FT8, PACKET, RTTY, SSTV, WEFAX | ACARS, ADS-B, HFDL, VDL2 | AIS | ISM, with a thin vertical separator between the groups (HF digital modes, aircraft, ships, ISM). The default page of a VFO without a saved page stays FT8.
- **AGC+: PRESETS CAREFUL / MODERATE / BOLD and a higher gain by default.** Above the sliders in SETTINGS › VFO › ADVANCED › AGC+ there are three preset keys, from careful to bold; the one matching the sliders is lit (the DEFAULTS key is gone, MODERATE is the default). **CAREFUL** = the old behaviour, no A/D clipping tolerated (clipping above 20 ppm, down 3 dB, hold 0.2 s, up below −8 dBFS, target −5 dBFS). **MODERATE** (new default) = the gain goes up to an A/D peak of about −2…−5 dBFS and short clipping up to 100 ppm does not turn it down (heavy above 2000 ppm, down 2.5 dB, hold 0.5 s). **BOLD** = new setting **Bold: up while clipping ≤** (ppm, `allow_ppm`): after each hold the gain goes one step up while the clipping stays at or under 20 ppm, even with the A/D peak at full scale; between it and 300 ppm it holds, above it goes down (heavy: 4 dB) and waits 4× hold (1 s) before going up again; a gain that clipped above 300 ppm is not tried again for 60× hold (1 min), so BOLD does not see-saw. VFOs with their own AGC+ settings keep them. In a simulation with a strong carrier MODERATE ends 2.5–4 dB higher than CAREFUL with no gain change after settling, BOLD 3–7 dB higher with a try of the gain above about once a minute. **WFM stereo no longer turns to noise on a gain step:** the transient of the tuner bent the pilot phase measured over the block, so L−R was decoded wrong; the blocks around an AGC+ gain step (also on chained VFOs of the dongle) are played in mono, the stereo lock stays. The slider *Clipping above* now goes to 1000 ppm. Fixed: AGC+ could stay below the wanted level when the next gain step of the tuner was bigger than the step wanted (e.g. 44.5 → 48.0 dB on the R820T); it now takes that step when the A/D peak still stays 1 dB under full scale.
- **RF bar red on A/D clipping (manual gain).** With AGC and AGC+ off, the receiver now watches the A/D converter also at a manual RF gain; while it clips, the whole RF segment bar of the VFO window and its dB value turn red (held 1 s), so the gain can be set just under clipping. The tooltip of the value shows the A/D peak in dBFS.
- **VIEW key** at the far left of the key row: hides the whole lower part with the tabs (SPECTRUM, DECODERS, SATELLITES …) with a slide and shows it again; the key is lit while the lower part is hidden, and only the bottom strip of the panel with its screws stays. A key that opens a tab (DECODE, MEM, SCAN, RCTRL …) shows it again. Remembered in the browser. With the lower part hidden the window can be made as low as the head; a lower or narrower window shrinks the panel as a whole (same aspect ratio, centred).
- **The keys no longer overflow into a second line** in a window wider than 1920 × 820: the compact keys are kept on while the full-size ones would not fit on one line. Where even the compact keys do not fit (macOS, whose system font is wider), the whole panel is drawn a little smaller instead of a second row.
- **MEMORIES › CHANNELS: the form of an existing channel is titled "Edit channel"** (Brano, brjanicek; was "Channel"), so it reads apart from **New channel**.
- **WFM filters 50, 75, 150 and 200 kHz** (were 100, 150 and 200 kHz), default 200 kHz (the full broadcast signal: least distortion, best stereo and RDS). 150 kHz is a compromise, 50–75 kHz only for a weak station next to a strong one (distorted, usually without stereo and RDS); any width up to 250 kHz can still be set by dragging the filter edge.
- **Location of a memory channel** (Brano, brjanicek): a channel can keep the location of its station, **LAT** / **LON** in decimal degrees in the channel form (both or neither; empty = none), or **CHOOSE ON MAP** (an OpenStreetMap map in place of the table, a click fills them). Saved as `lat` / `lon` in `memories.json` (`null` without a location), in the JSON and CSV export (**LAT/LON** column to include it) and import, and in the memories API. The CHANNELS table shows LAT, LON and the **azimuth** and **distance** from the station location of SETTINGS › GENERAL › LOCATION (sortable). The channel form takes the full height of the CHANNELS page.
- **Fewer STEP keys** (the key rows overflowed into a second line after TSQ-C / TSQ-D): every mode, WFM included, has the same four keys 10 Hz, 100 Hz, 1 kHz and 10 kHz (WFM had seven: also 500 Hz, 5 kHz and 9 kHz). WFM remembers its own chosen step in the browser, the other modes share one; a step saved before that is not one of the four becomes the nearest one.
- **AIS: positions, MMSI and message types were wrong** (Brano, brjanicek): the bits of every byte of a frame were reversed, but the HDLC deframer already assembles each byte LSB first as AIS sends it, so the payload came out scrambled – MMSI with 10 digits, types 8 / 2 / 33 instead of 1 / 4 / 5, ships somewhere in the Pacific. The bytes are now taken as they are (`ais.py`: payload bits, `!AIVDM` armouring and the plausibility test of a damaged frame); checked on live frames from the Danube in Bratislava, test `test_live_frames` in `tests/test_ais.py`. Messages logged before this fix have wrong `!AIVDM` sentences.
- **The default S-meter layout is the amber needle** (only when none was chosen in this browser yet; SETTINGS › GENERAL › S-METER).
- **Annotated screenshots in the docs:** the main screen (`docs/images/main_annotated.png`), SATELLITES › TRACK (`satellites_annotated.png`) and DAB (`dab_annotated.png`) with yellow callouts and lines to each part, linked from README, Controls, Satellite tracking and DAB. Drawn by `docs/annotate.py` (Chrome or Edge, standard library only).

## Ver. 0.113

Released after two test betas (GitHub branches `0.113beta1`, `0.113beta2`). The memory editor is contributed by **Brano, [brjanicek](https://github.com/brjanicek)**.

### Main Features

- **New look: brushed black anodized aluminium.** The whole receiver is one aluminium panel (horizontal hairline brushing, a sheen of light, screws in the corners, engraved labels and grooves between the rows). All displays in the top part (S-meter and its window, multifunction display, VFO windows, clock, level meter) are windows milled about 2 mm into the panel, with sharp edges, a shaded floor and glass. Keys have height and travel: a lit key stays pressed in with a coloured LED line at its bottom (yellow; blue for SAT, red for AGC+ while the A/D clips). The spectrum, the waterfall and their tabs (SPECTRUM, DECODERS, SATELLITES) are a display sunk into the panel behind glass, with the tabs drawn on the screen. The floating window (new version offer) has an aluminium title bar. The style is one section at the end of `static/style.css`.
- **Skins (SET → SKINS tab):** besides the dark brushed aluminium, the panel can be **black brushed aluminium** (one shade darker), **light brushed aluminium** (dark print and logo), **mahogany** (wood grain, satin varnish, cream print) or **paint**: sprayed in one colour, picked from a RAL chart (36 common RAL Classic shades, screen approximations) or any own colour; on a light paint the print and the logo turn dark by themselves. Keys, displays and the screen stay the same. Remembered in the browser, applied before the page is drawn.
- **Every VFO is one dark display window** with all its information: on top VFO-x (boxed, yellow on the active VFO), the name of the memory / band plan / satellite transponder (lit on the active VFO; a memory name in the memory's own tag colour from the memory editor), the recording dot, the muted speaker and the connection state; the frequency; an **info row** (RX / TX, filter width, audio **HPF** and **LPF** with their cutoffs, **ST** stereo pilot, **SQL** green while open, **CONV / BYPASS**); **annunciators** lit like LCD segments when on, dark when off or not used in the mode (mode, AGC with an always present **+** lit only with AGC+, NF, SP, ALC, AFI, ASQ, ATU, a satellite icon for the Doppler correction, CUE); and **RF / SQL segment bars** (drag, click or mouse wheel, also on inactive VFOs). Every item has a fixed place, so no text moves. A click on an inactive window selects that VFO.
- **Connection state as a USB icon** in the VFO window: green = running, blinking orange = connecting (waiting, opening the dongle, LimeSDR calibration), grey = disconnected or error (details in the tooltip).
- **VFO keys beside the S-meter.** The flags beside the S-meter (RX, mode, width, ST, ALC, CONV, SQL) are gone, their information is in the VFO windows; in their place four keys VFO-A … VFO-D one under another, as high as the other keys and centred on the S-meter; the active one is lit, an inactive one with an open squelch has a green line, a transmitting one is red. The S-meter is wider.
- **Multifunction display** under the S-meter and the VFO keys (as wide as both, its bottom level with the VFO windows): RDS now (station name, RadioText, PI, PTY, TP/TA); empty without RDS. The S reading, dBFS and the CPU / memory bars are in their own window under the S-meter.
- **SP key learns the spurs by itself.** Pressing SP (when off) forgets all stored spur lines of the VFO, runs LEARN on the band received now and switches the removal on: the key blinks red while learning (~5 s) and then stays lit yellow. Pressing it again switches the removal off. The settings and LEARN / CLEAR in SET (DONGLE tab) work as before.
- **Waterfall speed (vertical zoom).** A vertical bar in the top right corner of the waterfall, in the style of the frequency zoom (WF, − / +, cells, mouse wheel): 1/8, 1/4, 1/2, 1×, 2×, 4×. Below 1× several rows are averaged into one line (slower, longer history), above 1× each row is drawn taller (faster). Kept in the browser.
- **Waterfall settings by the waterfall.** A gear in a square above the speed bar (top right corner of the waterfall); with the mouse over it a half transparent window opens: **colour scheme** (Classic, Inferno, Viridis, Turbo, Ice — only new rows take the new colours), **colour range** and **colour offset** (moved here from SET, DISPLAY tab). Kept in the browser.
- **Spectrum settings by the spectrum.** The same gear and vertical bar in the top right corner of the spectrum. The bar (dB, − / +, cells, mouse wheel) moves the **zero** – the bottom edge of the spectrum – against the noise floor in 5 dB steps, −20 … +20 dB (+ hides the noise, − shows more of it). The gear opens the **colour schemes** of the spectrum, background always a gradient / curve: Graphite (grey / white, as before), Waterfall (follows the waterfall scheme), Night blue (cyan), Phosphor (green), Amber, Dusk (magenta), Ember (yellow), Steel (ice white). The fill under the curve and its glow take the curve colour. Kept in the browser.
- **SETTINGS tab instead of the floating SET window.** The SET key is a gear now; while it is lit, the bottom part has a **SETTINGS** tab beside SPECTRUM, DECODERS and SATELLITES, with page keys DONGLE, AUDIO, DISPLAY, ROTOR, SKINS (TX) like the pages of SATELLITES. The settings cover the spectrum and waterfall (those keep running), only the page scrolls. The open page is remembered in the browser, the gear key is one switch for all VFOs.
- **AD (additional display) instead of the RDS window.** The window under the S-meter and the VFO keys shows, by priority: **1. error messages** (red; they stay until accepted by the small framed **OK**, the frame of the window blinks red with a period of 0.5 s meanwhile; more waiting messages show *+n*), **2. the rotor AZ / EL** (MONITOR on the ROTOR page; the requested direction only while the rotor is on its way), **3. RDS**. The error messages that showed for 5 s under the logo (a refused setting, TX, recording, DAB on a dongle that cannot do it) go here now.
- **SETTINGS reorganised, without scrolling:** **SDR DONGLE** with sub-pages **BASIC** (dongle, upconverter, **bandwidth** – moved from DISPLAY, correction ppm, upconverter LO, tuner gain, RTL2832 digital gain, remove DC peak, bias-tee, **RESET SDR DONGLE** with a short description) and **ADVANCED** (**SP – Spurs removal** and **AGC+**, no longer marked *test*, its sliders in two columns); **AUDIO** (AFI, ASQ margin, HPF / LPF; the squelch slider is gone, the squelch is set by the SQL bar of the VFO window); **UI** with sub-pages **SKINS**, **S-METER** (layout and S9 calibration) and **TOUCHPAD** (wheel speed); **ROTOR**; TX. The DISPLAY and SKINS pages are gone (their content is on SDR DONGLE and UI). The open sub-pages are remembered in the browser.
- **ROTOR page redone.** On top, at the left, **ON / OFF** for this VFO (replaces the *Rotor link on, for this VFO* switch): OFF only says that the rotor configuration of the VFO is off, everything else is hidden; ON opens the link with the chosen port. With ON: a **polar plot** like on the TRACK page (without the pass) and beside it an **elevation column** 0–180° with a grid; orange cross / arrow = the antenna now, green ring = the requested direction (only while the rotor is on its way); beside them the **actual** AZ / EL (orange) and the **requested** AZ / EL (green), with a short note that a click in the plot or the column starts turning the rotor. A click on the polar plot turns the antenna there, a click on the column sets only the elevation (refused while TRACK moves the rotor) – it replaces *Position* and *Go to*. Keys **STOP**, **RESET** (always there, orange on a fault) and **MONITOR** (on: AZ / EL in the AD, per VFO, remembered in the browser). Then the azimuth calibration. The shown position is filtered (average + a dead band of 2.5° AZ / 1.5° EL), so the ~1 % noise of the K3NG readings no longer makes the numbers and the crosses flicker; while the rotor turns the readings pass at once.
- **ATU in SSB puts the edge of the signal on the red line** (the tuned frequency): the lower edge of the voice band in USB, the upper one in LSB, within a few Hz, after ~2 s of speech (was: the suppressed carrier estimated from the voice). Wheel, arrow key, drag or digit tuning now starts ATU from a move of 150 Hz (was 250 Hz), so it works when scrolling too.
- **Memory editor** (contributed by **Brano, [brjanicek](https://github.com/brjanicek)**). See [Memory editor](docs/controls.md#memory-editor).
  - **Channels** can be in several groups, and have a **decoder** (switched on with its page shown when the channel is recalled), a **record** setting (OFF by default; ON = REC, SQ = REC SQ, ASQ = REC SQ with the auto squelch, started when the channel is recalled; switched off again by the next recalled memory only if a memory switched it on; its tag in the spectrum then has a red ● before the name), a **note**, their own **tag colour** in the spectrum and a switch to **hide the tag** (shown and green by default). The table sorts by a click on a column header (again = reversed; by Groups with a section per group), has fixed column widths (a longer text whole in the tooltip), shows only the **duplicates** (same frequency and mode) on request and marks them with ⧉. A form edits one channel; ticked channels can be added to or removed from a group (chosen from a list of all groups or ＋ new group…), starred, shown / hidden, coloured, deleted or put on the export list.
  - **Groups** with a **note**, also empty ones: add, rename, copy (with copies of the channels), merge the ticked groups, delete (with or without their channels).
  - **Import** through a list: one **LOAD FILE…** key recognises each file by its content (RADIMCOM JSON or CSV, SDR# `frequencies.xml`, **SDR++** frequency manager, **gqrx** `bookmarks.csv`, **CHIRP** CSV): edit the channels there, see the new ones, duplicates and errors, import only the selected ones (all by default); the rest stay in the list for later. Group notes from JSON come along.
  - **Export** of whole groups and chosen channels through a list: edit, untick, and choose per channel whether the tag colour, tag on / off and note are exported (and the note of each group). JSON with groups and notes, or CSV for Excel.
  - Files: `data\memory_groups.json` is new; `memories.json` keeps the first group in the old `group` field, so older versions still read it, and is copied to `memories.json.bak` before the first change.
  - HTTP API: new fields of a memory, `/api/memories/bulk`, `/api/memory_groups`, `/api/memories/preview`, `/api/memories/import_entries`; `PATCH /api/memories/<id>` takes every field.
  - The channel form is in three columns (fields | decoder, record, star, tag | groups) and fits the tab without scrolling; it asks before unsaved changes are dropped. With no channel ticked, the bar above the table acts on the channel open in the form.
- **MEMORIES tab instead of the floating MEM window.** While the MEM key is lit, the bottom part has a **MEMORIES** tab beside DECODERS, SATELLITES and SETTINGS, with the pages **CHANNELS**, **GROUPS**, **IMPORT** and **EXPORT** (the memory editor). CHANNELS is also the list to recall from (Brano, brjanicek): a click on a row selects it (Ctrl+click adds more), a double click recalls the channel, ✎ opens it in the form, the tuned channel is highlighted and scrolled into view, **★ only** shows the starred channels, **＋ SAVE CURRENT** and **＋ NEW** open a new channel in the form (with the tuned frequency, mode, width and DAB channel, or empty). The MEM key is one switch for all VFOs, the open page is remembered in the browser.
- **RTL-SDR Blog V4 tunes from 0.5 MHz.** The dongle is recognised by its USB product name (*Blog V4*) when it is opened; its lower limit is then 0.5 MHz instead of 24 MHz. Below 28.8 MHz its driver switches on the built-in upconverter, so HF needs no external converter (upconverter off in `vfos.json`). Other RTL dongles keep 24 MHz.
- **Dongles and VFOs list** in SETTINGS › SDR DONGLE › ADVANCED: every dongle from `data\vfos.json` (type, serial number, the VFOs it serves including chained ones, note), its state from the VFO receiver (✓ running, error with the reason in the tooltip), connected RTL dongles not assigned to any VFO (*free*) and the number of RTL dongles on USB. The dongle the settings apply to (the active VFO, or the VFO owning the dongle of a chained VFO) is highlighted. ⟳ searches again.
- **HFDL decoder** (aircraft data link on HF, **2.9–22 MHz**): a new **HFDL** page in the DECODERS tab, decoded by [dumphfdl](https://github.com/szpajder/dumphfdl) 1.7.0 (`lib\hfdl\`, built with MSYS2 by `installer\build_hfdl.sh`). Multichannel: all HFDL channels of the ground station table (`lib\hfdl\systable.conf`, 16 stations) within ±(sample rate / 2) of the VFO centre are decoded at once, so 2.4 MS/s covers a whole band. The audio of the VFO is muted while HFDL runs (like ACARS / VDL2), the sample rate stays; the **band buttons** (2.9, 4.7, 5.5, 6.5, 8.8, 10, 11, 13, 15, 18, 22 MHz) centre and tune the VFO on the middle of a band. The card shows the channels decoded now, the ground stations heard (from their squitters every 32 s) and a table of all ground stations with their frequencies. Table: UTC, channel, signal and bit rate, ↑ / ↓, ground station, flight, registration, ICAO, message type, ACARS label, position (map link) and text; SHOW (All / ACARS / With position / Logon) and a text filter. Like the ACARS card, each aircraft is looked up on **ADS-B** (adsb.fi / adsb.lol, by its ICAO address or the registration from ACARS): country flag, squawk, type, model, flight level and speed in blue, the ICAO / registration filled in when HFDL lacks it; a click on the flight, registration or ICAO opens the map in a new tab (globe.adsb.fi / adsb.lol). Three views: **MESSAGES** (long messages shown in 3 lines with ▾ more, a click on a row holds the list still like ACARS / VDL2), **AIRCRAFT** (the newest data of each aircraft heard) and **MAP** (OpenStreetMap, darkened, with the aircraft turned to their heading, flight and type labels, tracks of their known positions from HFDL and ADS-B, the HFDL ground stations with the heard ones green, and the aircraft list beside it; a click selects an aircraft); LOG to `data\logs\hfdl_YYYY-MM-DD.txt`. Works with RTL-SDR (V4 or with an upconverter), LimeSDR and Airspy; not on a chained VFO. HTTP API: `hfdl`, `hfdl_band` in `/api/settings`, `GET` / `POST /api/hfdl`. → [HFDL](docs/decoders/hfdl.md)
- **AIS decoder** (ships, **161.975 / 162.025 MHz**): a new **AIS** page in the DECODERS tab, decoded by RADIMCOM itself (`ais.py`: numpy, no external program) from the raw samples of the VFO: each channel is taken out by a complex band-pass with polyphase decimation to 48 kHz, FM demodulated and fed to the bit clock and HDLC deframer of the packet decoder (GMSK 9600 Bd, NRZI, CRC-16). The **162.000** button centres the VFO between the two channels (FM), so both are decoded at once; the audio of the VFO is muted while AIS runs (like HFDL), the sample rate stays. Messages decoded: position reports class A (1–3), B (18, 19) and long-range (27), base stations (4, 11), static and voyage data (5, 24), SAR aircraft (9), safety text (12, 14), aids to navigation (21); the others show their type. Table: UTC, channel A / B, signal (peak level in dBFS), country flag from the MMSI, MMSI (click → MarineTraffic), name (click → VesselFinder), call sign, ship type, message type (BASE / AtoN / SAR / STATIC tags, the NMEA `!AIVDM` sentence in the tooltip), navigational status, position (map link), SOG, COG, heading, destination and details (IMO, size, draught, ETA, rate of turn); name, call sign, type and destination known from an earlier static message are shown in blue in the position reports. SHOW (All / With position / Static data / Base stations / Other), a text filter, scroll pause, INFO. Three views: **MESSAGES**, **SHIPS** (the newest data of each station: position with its age, course, speed, destination, ETA, size, draught, number of messages; a click on the position opens the MAP) and **MAP** (OpenStreetMap, darkened: ships as yellow arrows turned to their heading, stopped ships as circles, ▲ base stations, ◆ aids to navigation, SAR aircraft, white trails of the reported positions, the selected station red, 30 min without a message grey, the QTH; the list beside the map selects a station with a popup and links). LOG to `data\logs\ais_YYYY-MM-DD.txt` with the NMEA sentence of each message. The memory editor knows the AIS decoder. Works with RTL-SDR, LimeSDR and Airspy; not on a chained VFO. HTTP API: `ais`, `ais_center` in `/api/set`, `GET` / `POST /api/ais`, events `ais` and `aisstate`. → [AIS](docs/decoders/ais.md)
- **RECORDINGS tab (RECS key in the AUDIO group):** the MP3 files recorded by REC / REC SQ (`data\recordings`, shared by all VFOs) in a table, newest first: start time, memory name, frequency, mode, length, size and file name, with a file being written marked by a blinking red dot (its length grows while the tab is open). A click on a row plays the file in the browser with the player in the head of the tab (seek, its own volume, not through MAIN); **NEXT** continues with the next older file when one ends (handy for the short sessions of REC SQ), a filter narrows the list by name, memory, kHz, mode or date, ✕ deletes a file (not one being written), ⟳ reads the folder again. Like MEM, the key shows or hides the tab and is remembered in the browser. HTTP API: `GET /api/recordings`, `GET` / `DELETE /api/recordings/<file>`.
- **Block diagram in SETTINGS › SDR DONGLE › BASIC:** the receive chain antenna → upconverter (LO) → bias-tee → tuner (gain) → A/D RTL2832 (digital gain, bandwidth) → USB → DC removal → SP spurs removal → spectrum / VFOs, with the crystal (ppm) clocking the tuner and the A/D and the AGC+ loop from the A/D level back to the tuner gain. The blocks are numbered 1 – 11 (SP = 10 and AGC+ = 11 are cards on the ADVANCED page; a click on them switches there) and each setting card (in the ppm / LO card each field) has the same number as a badge; a click on a block highlights its card. Blocks without a setting for this dongle or VFO are grey. Shown for RTL-SDR dongles only (not LimeSDR or Airspy).
- **Waterfall keeps the history of the whole band when zooming.** Zoomed in, the server also sends a coarse line of the whole SDR band (`full`, `fc`, `fspan` in the `wf` event); the browser keeps it as a hidden whole-band waterfall that scrolls with the shown one. After zooming out (or in), or after dragging the section aside, the parts that were hidden are drawn from this history at once instead of an empty background (coarser than the zoomed picture; new rows have the full resolution). The picture shown before the zoom change is kept sharp, scaled to its place over the history.
- **Maps in a new tab.** The maps of PACKET (APRS), HFDL and AIS have a □ key (square with an arrow) in their top right corner: it opens the same map alone over the whole browser tab (`/?map=packet|hfdl|ais&vfo=X`), with the list beside it (HFDL, AIS), live from the same VFO. That tab plays no audio, draws no spectrum, ignores the space bar (PTT) and saves nothing in the browser, so the main window keeps its tabs and settings.

### Minor Fixes

- **Speaker, REC and REC SQ** under the faders are raised keys: the speaker has a green LED line, muted it is pressed in with a red line; REC / REC SQ are pressed in with a red line and a red LED while recording (blinking while a file is written, steady while REC SQ waits for the squelch). The faders have a metal knob.
- **RADIMCOM logo:** raised white letters with a 3D side, the green ring LED above the I raised too (its dark body stays when it pulses off). The author line under the logo is replaced by the version (*Ver. 0.113*); logo and version are centred above the clock, a newer version blinks beside the version.
- **The waterfall settings gear no longer shows through the DECODERS and SATELLITES tabs.**
- **Grey texts on the panel are lighter** (key group labels, RF / SQL labels, CPU / MEM, version).
- **The AFI tag above the frequency unit and the muted speaker above the frequency** moved into the VFO window (AFI annunciator, speaker in the top row).
- **ST shows the real stereo state.** With S/M set to mono the **ST** annunciator in the VFO window stayed lit as long as the 19 kHz pilot was there, so S/M looked as if it did nothing (the audio was mono). ST is now lit only while L−R is really decoded (pilot and S/M on), grey with S/M off or without a pilot; its tooltip tells which. `/api/status`: `stereo` = stereo decoded, new `pilot` = pilot locked.
- **A damaged VFO settings file no longer stops the VFO.** A power cut right after saving could leave `config_X.json` full of zero bytes and the VFO receiver ended at start with `JSONDecodeError`. Saving now flushes the file to disk (`fsync`) and keeps the previous version as `config_X.json.bak`; at start the launcher keeps a damaged file as `.broken` and restores `.bak`, or creates new settings from `config.json` + `init` in `vfos.json`.
- **AD window has a fixed height** (as with RDS), so an error message, the rotor AZ / EL or RDS no longer make it higher or lower.
- **Recording started by a memory stops when you leave it** (Brano, brjanicek). A recording (and ASQ) that recalling a memory with RECORD ON / SQ / ASQ switched on now stops as soon as the VFO leaves that memory (tuning, another mode or DAB channel), not only when another memory is recalled. A recording switched on with REC / REC SQ by hand keeps running while tuning; pressing REC, REC SQ or ASQ during a memory recording takes it over by hand too.

## Ver. 0.112

### Main Features

- **ASQ key (auto squelch)** in the AUDIO group, for AM, FM and WFM: the squelch level follows the noise in the channel plus a margin. The noise is measured in the spectrum of the dongle band (the quietest 10 % of its points, converted to the channel bandwidth), so a signal in the channel, even a long one, does not raise the level and close it; in a crowded band (e.g. FM broadcast) the quietest channel power over the last 15 s is used when it is lower. The margin is 6 dB by default, set in SET, AUDIO tab (2–30 dB). The measurement starts again after a change of frequency, mode, bandwidth or gain. The SQUELCH slider (SET and the VFO list) shows AUTO and the level in use; the yellow mark on the S-meter follows it.
- **ATU key (autotune)** in a new TUNE group, for USB, LSB and AM. With ATU on, a click on a signal in the spectrum or waterfall tunes to the clicked point (without the step grid), listens for a moment and moves the tuning onto the carrier; the key blinks while listening and the passband label shows the shift (e.g. *ATU +130 Hz*) or *no signal*. Tuning by the wheel, the arrow keys, dragging or the VFO display digits starts it too, 0.7 s after the tuning rests, when it moved by more than 250 Hz (smaller moves are fine tuning by ear and are left alone). AM: the carrier is measured in a fine FFT near the click (±3 kHz), result within a few Hz in under 1 s. SSB: the suppressed carrier is found from the voice itself — the lower edge of the voice band gives a coarse estimate, then the harmonics of voiced speech (at exactly carrier + k·pitch, with the pitch changing from frame to frame) fix it, usually within ±10–20 Hz after 2–3 s of speech (up to 6.5 s when the station is quiet). When the best carrier does not stand clearly above the one a pitch step away, it keeps listening (up to 6.5 s). Without clear speech only the coarse estimate (~±100 Hz) is used; a very steady voice can still end one pitch step (~100–200 Hz) off — click again. Tuning elsewhere during listening cancels it.
- **AGC+ key** (GAIN group, next to AGC): smart AGC. The receiver measures the raw samples of the A/D converter (the whole band of the dongle, also strong signals outside the channel) and sets the tuner gain: on clipping it goes down by 3–6 dB at once, after 2 s without clipping and with peaks under −8 dBFS it goes up by at most 6 dB, aiming at about −5 dBFS. The tuner AGC (AGC key) of the R820T only protects its LNA and mixer and keeps the IF gain fixed, so it does not see the A/D; the RTL2832 digital AGC acts after the A/D and is turned off with AGC+. AGC, a manual gain or the RTL AGC end AGC+. RTL-SDR, Airspy and LimeSDR; on a chained VFO the owner of the dongle regulates. The tooltip shows the gain and the A/D peak, a red underline on the key = clipping. Its settings (clipping thresholds, steps down and up, the level for going up, target, hold time, settle blocks) can be tried in SET, DONGLE tab, with the gain and A/D level shown live; DEFAULTS returns them.
- **AGC+ with the squelch set switches to auto squelch:** a fixed level would not fit the gain AGC+ keeps changing, so while AGC+ is on, a squelch set by the slider works as auto squelch (ASQ lights up). The slider then only turns it on / off; ASQ pressed in this state turns the squelch off.
- **AGC+: faster rise.** The default hold before going up (SET, DONGLE tab, *Hold before up*) is 0.2 s instead of 2 s, so after a strong signal goes away the gain comes back up within about a second.
- **PACKET decoder** (new page in the DECODERS tab): AX.25 packet radio at **1200 Bd AFSK** (Bell 202: APRS on 144.800 MHz, the ISS digipeater on 145.825 MHz, packet nodes) and **9600 Bd FSK / GFSK / GMSK G3RUH** (satellites), both at once by default (**BAUD**). It demodulates the FM itself from the baseband of the VFO, so it works in any mode and filter width (9600 Bd needs a sample rate of at least 1.536 MS/s). 1200 Bd: two tone filters one bit long and four slicers with different weights of the 2200 Hz tone, so transmitters with and without pre-emphasis are both decoded; a PLL on the edges recovers the clock. 9600 Bd: a 20 ms moving average removes the tuning error (**AFC**, shown in kHz for the last 9600 Bd frame, + = the signal is above the tuned frequency), so a satellite burst that starts off frequency is caught within a few flags; **SCRAMBLER** Auto tries with and without the G3RUH scrambler at once. Frames with a wrong checksum (and a valid address field) are only counted (*bad CRC*); the same frame from several slicers is shown once. **APRS** is decoded: positions (plain, compressed, Mic-E) with course, speed and altitude, objects and items, weather, messages, status and telemetry, in km/h, m, °C and hPa. Three views: **FRAMES** (time, speed, from, to, path, the APRS meaning in blue over the raw text; telemetry that is not text as hex; 9600 Bd in green), **STATIONS** (the newest state of each station: number of packets, distance and bearing from the station set in SATELLITES › SETUP, path, last report; a click on a station shows it on the map) and **MAP** (OpenStreetMap). **filter** shows only frames and stations containing the text. **LOG** writes valid frames to `data\logs\packet_YYYY-MM-DD.txt` (TNC2 format). Turned on by hand, e.g. for a satellite pass; about 3 % of one CPU core for both speeds. On the right of the lists a small **SPECTRUM** of the received signal around the tuned frequency (±14 kHz at 2.048 MS/s, 63 Hz resolution, averaged about 1 s, **MAX** hold, 10 dB / 2 kHz grid): FSK shows its wide side lobes, GFSK / GMSK a narrow steep spectrum; below it the S/N, the 99 % bandwidth and its centre, and the live 9600 Bd AFC (green dashed line). The second view is an **EYE** diagram in real time (**9600** / **1200**): the demodulated signal around each bit sampling instant, many bits on top of each other as a density (persistence) display, so the noise between frames stays dim and the bands of a clean signal are bright; a clean signal draws an open eye, the faint lines are the nominal levels (mark / space, ± deviation). Below it the eye opening now and in the block of the last good frame, and at 9600 Bd the deviation and the live AFC. The data of the graph are sent only while the PACKET page is open.
- **DECODERS tab with a page for each decoder.** The DECODE group has one **DECODE** key (now before SAT): like SAT, it shows and opens the DECODERS tab, and off hides the tab (running decoders keep running); remembered per VFO. The tab has page keys like SATELLITES: FT8, WEFAX, CW, RTTY, SSTV, ACARS, VDL2, DAB, ISM and DSD; each page shows the card of its decoder, also while it is off, with its **ON** key in the card's top left corner (it replaces the OFF keys of DAB and ISM). Decoders the receiver of the VFO cannot run (VDL2, DAB and ISM on a LimeSDR, an Airspy or a chained VFO) have their page key greyed out and struck through (tooltip *Unsupported on this dongle*), and their page gives the reason instead of the card. A green ● on a page key = a new message there, not seen yet.
- SATELLITES: data transmitters with the mode FSK, GFSK, GMSK or MSK (also variants such as GMSK USP or AX.100 Mode 5) are tuned in **FM** (was USB).

### Minor Fixes

- **WEFAX: AFC retunes the VFO.** New **AFC VFO** option (on by default, saved per VFO): once the decoder locks on a WEFAX signal (both black and white levels seen) and its centre is more than 25 Hz off 1900 Hz, the VFO is retuned by the difference (at most once every 4 s), so the signal sits in the middle of the USB passband. The decoder moves its own centre by the same amount, so the image goes on without a break. Only in USB, not while the Doppler correction or ATU is tuning; the info line shows the last correction (e.g. *VFO −120 Hz*).
- **WEFAX: gallery of saved images, like SSTV.** Next to the live image (which keeps its own scrollbar) the last 12 images saved in `data\wefax` are shown as thumbnails; a click opens the image in a new tab, × (shown on hover) deletes it, **DEL ALL** deletes all of them (with a confirmation).
- **CW in the audio spectrum bubble.** In CW mode the bubble (mouse over the passband label) shows the decoded text under the audio spectrum, the last two lines; it starts empty with each opening and is erased when the bubble closes. With the CW decoder on its text is used (tone and speed already locked); with it off the server runs a separate peek decoder only while the bubble is open (renewed by the browser every 2 s, it stops by itself 4 s after the last renewal); its text does not go to the CW card or the log. The first characters come after ~1–3 s, once the tone and speed are found.
- **SATELLITES, TRACK: one TRACK key for the rotor.** The CTRL key is gone: **TRACK** plans the passes of the shown satellite and turns the rotor control on (and the rotor link, with the port saved in SET); a second press ends the tracking and stops the rotor. **STOP** stops both motors and ends the tracking. The flag beside *Rotor* shows **TRACKING** (green, the rotor follows the satellite), **CALC ONLY** (yellow, the tracking runs but the rotor does not move: the link failed, a fault or STOP in SET) or **NOT TRACKING** (grey). The rotor part is shorter (pass and plan on two lines), and the polar plot and the elevation chart stand side by side with the facts of the pass in two columns below, so the chart is seen without scrolling. On the right of the Rotor line a big countdown: **AOS in 2:45** before the pass, **LOS in 4:10** (green) during it.
- **ZOOM key removed** from the top row; zoom stays on the bar in the top right corner of the frequency scale. The open page is remembered per VFO.
- **DAB: slide aspect ratio.** The picture box takes the slide's own ratio instead of a fixed 4:3. Some stations send 16:9 pictures (video stills) squeezed into 320x240; a click on the slide shows it as 16:9, a second click returns the original ratio. Remembered per station in the browser.
- **CPU and memory indicator.** Small bars under the S-meter show the CPU load and memory use of the PC running RADIMCOM, every 3 s (amber over 70 %, red over 90 %; the tooltip gives the memory in GB).
- **BAND key.** In the MENU group next to MEM: shows or hides the row of band keys (HF HAM, HF BROADCAST, VHF / UHF HAM, OTHER). The row slides closed and the spectrum and waterfall take the freed space; it slides open again. Remembered in the browser.
- **Arrow keys up / down** recall the next memory above / below the tuned frequency, among those visible in the spectrum.
- **RADIMCOM logo:** a click opens the project on GitHub in a new tab. When a newer version is released, the logo turns **red**; the tooltip says which version is available (*click here for the latest version*) and a click opens its release page in a new tab. The new version number (e.g. *0.113*) blinks in an orange block above the version under the logo, so the logo does not move.
- **Doppler: fine steps in all modes.** The Doppler correction retunes the VFO beyond 5 Hz in every mode (was 20 Hz in SSB and CW, 500 Hz in AM, 1 kHz in FM, 5 kHz in WFM), still at most once a second.
- **Shorter README, documentation in `docs/`.** The README now has a quick start, a table of supported hardware (with the RTL-SDR Blog V4 on the roadmap and the receiver bandwidth of each SDR), the main features in two groups (receiver, user interface) and screenshots. The details moved unchanged to `docs/`: installation, HF upconverter, controls, configuration, satellite tracking, development, one page per decoder (aircraft data link, DAB, DSD, ISM) and a complete feature list (`docs/features.md`) with a table of all decoders. Functions missing from the old README were added: ASQ, ATU (experimental), AFI key, WEFAX slant / AFC VFO / gallery, CW text in the audio spectrum bubble, BAND key, ↑ ↓ memories, CPU and memory indicator, squawk and pausing in ACARS / VDL2.
- **ROADMAP:** RTL-SDR Blog V4 support added.

## Ver. 0.111

### Main Features

- **Satellite tracking without Gpredict: everything in the SATELLITES tab.** Gpredict is no longer needed and no longer in the package (the GP key, `apps\gpredict` and the rotctld / rigctld TCP links on ports 4533 / 4532 are gone; an `apps\gpredict` folder left from an older version can be deleted).
  - **The tab:** a new tab next to SPECTRUM and DECODERS, opened also by the **SAT** key. The floating SAT window (dials, 3D view) is gone.
  - **PASSES:** a timeline of the passes of the chosen satellites over the next 12, 24 or 48 hours (brighter bars for higher passes) and a list of them. A click on a pass shows its track on a polar plot, the elevation over time with a hover readout, the nearest distance, the Doppler shift at 145.9 and 435 MHz, the position now and the transmitters of the satellite. A **TRACK** key opens the satellite on the TRACK page.
  - **MAP:** a world map (Natural Earth, in the package, works offline) with the satellites switched on by keys above it, each with its footprint (yellow while it is above our horizon), the night side and the station. The chosen satellite shows its ground track, and beside the map its position, altitude, azimuth and elevation from here, distance, Doppler shift, next pass and transmitters, with a **TRACK** key. Moves every second. TRACK on MAP and PASSES adds a satellite that is not on the timeline yet.
  - **TRACK, Doppler:** a click on a transmitter (SatNOGS DB: downlink, mode, transponder or beacon) tunes the VFO, sets its mode and keeps it on the downlink as the satellite comes and goes (retuned beyond 20 Hz in SSB and CW, 500 Hz in AM, 1 kHz in FM, at most once a second); OFF stops it. Tuning by hand moves the frequency within the transponder.
  - **TRACK, rotor:** each pass is planned ahead and simulated with the measured speeds of the rotor, so a pass across the north no longer makes the K3NG unwind in the middle: it uses the overlap (past 360°, up to K3NG 450°), the flipped way (elevation over 90°, the antenna looking back) or, near the zenith, the azimuth standing still with the elevation going 0 → 180°. **TRACK** turns the rotor to the start of the next pass in time (the move begins its estimated duration plus 30 s before AOS), follows it and waits for the next one. While the rotor follows another satellite, TRACK switches it to the one shown. The rotor moves only while **CTRL** is on; with CTRL off it only calculates. **STOP** stops both motors and turns CTRL off. Tested on the rotor: a pass across the north in the overlap, pointing error median 3.4°, no unwinding.
  - **TRACK, plots:** the polar plot and the elevation chart (0–180°) show the real position of the antenna as a red cross. A click on the polar plot turns the antenna there, a click on the elevation chart sets only the elevation; a purple cross shows where a click would go. Refused while TRACK moves the rotor.
  - **SETUP:** the station by locator, latitude and longitude, or a click on an OpenStreetMap map (CHOOSE ON MAP); the satellites on the timeline, chosen in tabs by CelesTrak group: Amateur Radio, Weather, CubeSats, Space & Earth Science, Galileo, GLONASS, GPS, Iridium NEXT. **SELECT ACTIVE** ticks the satellites of the AMSAT lists (LINEAR, FM, IMAGE, MISC), **CLEAR** unticks all.
  - **LINEAR, FM, IMAGE, MISC:** the lists of active satellites from [AMSAT](https://www.amsat.org/), with frequencies and comments. Links open in a new browser tab. The server downloads the lists when the tab is opened, keeps them for 12 hours in `data\satellites.json` and shows the last copy without internet; **REFRESH** downloads them again.
  - **Data:** the orbital elements come from CelesTrak once a day, the transmitters from SatNOGS DB once a week; both work offline from the last copy. Positions with SGP4 (Python package `sgp4`, installed by `upgrade.bat`).
  - **HTTP API:** `/api/sat/passes`, `/api/sat/pass`, `/api/sat/map`, `/api/sat/setup`, `/api/sat/transmitters`, `/api/sat/doppler`, `/api/sat/rotor`, `/api/satellites`; `/api/gpredict` is gone. Setting the antenna uses `goto` in `/api/rotor` as before.
- **Airspy R2 (first test version, receive only).** A VFO can use an Airspy R2, `setup.bat` finds it. 2.5 MS/s, gain as the presets 0–21 or AGC, bias-tee, upconverter, ppm and chained VFOs work as on the other SDRs. VDL2, DAB and ISM are not available on it (RTL-SDR only); the 10 MS/s rate is not offered yet.

### Minor Fixes

- **Upgrade from the page.** After each start RADIMCOM asks GitHub Releases once for a newer version; if there is one, a small window offers it. **UPGRADE** downloads the upgrade zip to `data\update\`, closes the receiver and installs it in its own console window (unzips the program over the RADIMCOM folder, ends decoders still running from `lib\`, runs `upgrade.bat`), then starts RADIMCOM again and the page reloads. `data\` and the settings stay. **LATER** asks again at the next start, **SKIP THIS VERSION** not before a still newer one; the yellow "→ 0.1xx available" beside the version under the logo opens the window again. Without internet nothing is shown. Off with `"update_check": false` in `data\vfos.json`. Not offered in a development copy (git). It works from this version on: the upgrade to 0.111 itself is still done by hand. HTTP API: `/api/update`.
- **Rotor: azimuth calibration.** New in SET (ROTOR tab): the true azimuth of the antenna at K3NG 0 and at K3NG 450, for a rotor whose left stop is not exactly north. The position, the tracking and GO then use true azimuths. RADIMCOM follows the whole K3NG range 0–450 (K3NG reports only modulo 360) and saves it, and chooses the command so that K3NG, which takes the shorter way, ends nearest the wanted direction. HTTP API: `az_cal` in `/api/rotor`, `k3ng_az` and `k3ng_guess` in its state.
- **Long rotor moves no longer stop halfway.** The K3NG controller ends any single move after its operation timeout (60 s on the tested unit), so a move longer than that, such as the elevation from 0 to 180 degrees (about 72 s), stopped and RADIMCOM reported "no movement". RADIMCOM now sends the same target again every 30 s until the rotor gets there.

## Ver. 0.110

### Main Features

- **Recording to MP3 on the PC, two keys.** The REC key that downloaded a WAV through the browser is replaced by two keys that save to `data\recordings` as MP3, 128 kbps, named by frequency, mode and start time (`145.500000MHz_FM_20261105_155300.mp3`), with the name of the memory first if the frequency is in the memories (`Piestany_TWR_118.575000MHz_AM_20261105_155300.mp3`). **REC** records everything until switched off, with a new file after 15 minutes. **REC SQ** records only while the squelch is open, each session in its own file (a session ends after 1 s of closed squelch; bursts under 0.3 s are dropped). Each VFO records on its own, also with the page closed; a red dot in the corner of its display blinks while writing and is steady while waiting for the squelch. New Python package: lameenc (`upgrade.bat` installs it). HTTP API: `rec`, `rec_sq` in `/api/set`, `recording` in the state.
- **ISM decoder: 433 and 868 MHz devices.** New **ISM** key under DECODE, after DAB, decodes weather sensors, remote controls, tyre sensors and other small devices with [rtl_433](https://github.com/merbanan/rtl_433). The card has preset buttons **433.92** and **868.30** MHz (the VFO runs at 2.048 MS/s around them, so about ±1 MHz is decoded at once, with its audio muted), a table of messages (device, ID, channel, level, data; a message the device repeats is one row with ×N) and a LOG checkbox (`data\logs\ism_YYYY-MM-DD.txt`). ISM turns ACARS, VDL2 and DAB off, and turning it off restores the sample rate. RTL-SDR only, not on a chained VFO. HTTP API: `/api/ism`, `ism` and `ism_hz` in `/api/set`, `ism` and `ismstate` events.
- **Antenna rotor and Gpredict link.** Tested so far only with the [K3NG rotor controller](https://github.com/k3ng/k3ng_rotator_controller); other GS-232 compatible rotors have not been tested yet. New **ROTOR** tab in SET connects a K3NG rotor controller
  (GS-232 commands over USB serial, 9600 baud): position, go to AZ/EL and STOP. RADIMCOM also acts as a rotor (rotctld protocol, TCP 4533) and a receive-only radio
  (rigctld protocol, TCP 4532) for Gpredict, which does the satellite tracking and Doppler VFO frequency correction. The rotor stops on a disconnected Gpredict, an impossible position
  jump or a move without progress. The name frame of the VFO shows the satellite and transponder selected in Gpredict in blue, and the SAT window shows the time to its next AOS or LOS (both need our patched build of Gpredict). New **SAT** key opens a floating window with the azimuth and elevation (0 to 180 degrees) of the antenna on two dials, a 3D view of a 5 element Yagi from the south and from 45 degrees above, and a **CTRL** key for rotor control: the rotor follows Gpredict only with CTRL on; a fault, a lost connection and STOP in SET turn it off, the position stays visible. New **GP** key opens and closes Gpredict (`apps\gpredict`, in the package: Gpredict 2.7 with our changes, see `installer/GPREDICT.txt`). New Python package: pyserial (`upgrade.bat` installs it). HTTP API: `/api/rotor`.
- **Remove DC peak in SET (DONGLE tab).** Removes the peak of the dongle in the centre of the band, from the waterfall and from the received signal. On by default. A **Width** slider (up to 1000 Hz) also takes out the wide skirts of the LimeSDR peak, at the price of weakening signals that close to the centre. A **Suppression** slider (0–60 dB) sets how deep the removal goes. Each VFO keeps its own setting. HTTP API: `dc_remove`, `dc_hz`, `dc_db`.
- **Remove spurs: SP key under AUDIO, settings in SET (DONGLE tab).** For spurs from local sources such as a switching power supply, useful for dongles with an HF upconverter: **LEARN** finds lines at a regular spacing of 12 kHz or more in the band received now and leaves other peaks alone; each line gets a band-stop filter set by the **Width**, **Edge**, **Shift** and **Depth** sliders, which takes the line down to the noise around it, following its shape, so it leaves no hole in the noise. Cleans the waterfall and the channel you listen to (not WFM and wide FM). A signal on a spur is removed with it. Each VFO keeps its own lines. HTTP API: `spur_on`, `spur_hz`, `spur_edge`, `spur_shift`, `spur_db`, `spur_learn`, `spur_clear`.
- **VDL2: EU and US channels, new centre.** New **EU** and **US** buttons in the VDL2 card choose which channels are decoded, one region at a time. EU now decodes 136.700–136.975 MHz in 25 kHz steps (today's channels and those planned from January 2027) plus 136.675 MHz, dropped automatically on 1 January 2027 when it becomes a guard channel. US decodes 136.100, 136.300, 136.650, 136.800 and 136.975 MHz. The VFO centre moves from 136.850 to 136.500 MHz, because 136.850 is now a channel and would sit on the DC spike. The card header shows the number of channels, with the list in the tooltip. See [issue #1](https://github.com/om2amr/RADIMCOM/issues/1); thanks to Sergi for the channel information. HTTP API: `vdl2_region`, `vdl2_region_freqs`.
- **DAB card redesigned.** Station list with coloured tiles and a mark on the station playing; a large now-playing panel with the slideshow picture, chips for programme type, DAB / DAB+, bitrate, language and error protection, the codec and the DLS text. New panels: **SIGNAL** (SNR with a quality mark, frequency correction, FIC errors), **ENSEMBLE** (name, country flag, ID, stations, local time and UTC) and **MULTIPLEX CAPACITY** (share of each station). **The last channel and the last station of each channel are remembered** per VFO, and the station plays again by itself. The slideshow picture keeps its correct proportions. HTTP API: more fields in `/api/dab`, `dab_sids` in the state, `dab_sid` in `/api/set`.

### Minor Fixes

- **Dragging the passband in the spectrum.** Dragging the marked passband or its label now moves only the passband and tunes with it, up to the edge of the shown section; the spectrum stays in place. Dragging elsewhere in the spectrum and in the waterfall moves the band as before.
- **3D logo.** The letters of the logo have depth and shading, and the green ring above the I pulses slowly.
- **Memory import from JSON.** New **⇧ IMPORT JSON** in MEM → Import / export reads a file in the format of EXPORT; duplicates and invalid entries are skipped. The MEM window is a little wider. HTTP API: `POST /api/memories/import_json`.
- **DAB channel in memories.** ＋ SAVE CURRENT in MEM with DAB on stores the channel too. Recalling the memory turns DAB on with that channel, and recalling any other memory ends DAB.
- **DAB: HE-AAC v2 stations play at the right speed.** They played at half speed, because welle-cli took their stereo audio for mono. welle-cli is now built with a small patch (`installer/welle_radimcom.patch`).
- **ACARS and VDL2 mute the audio of the VFO**, like ISM. While one of these decoders runs, a small red struck-through speaker shows in the VFO display above AFI and MHz, which move slightly down. REC records nothing meanwhile. HTTP API: `audio_muted` in the state.
- **ACARS / VDL2: a line appears complete.** A new message is shown only after its ADS-B data and flag have arrived, instead of filling in later. Without an answer it appears after about 15 s (3 s more at most for the flag), and late ADS-B data is still filled in. The rows stay in the order of reception. HTTP API: `lookup` in the messages.
- **ACARS / VDL2: pause the message list.** A click on a message marks it with a lighter background and holds the list still, with **SCROLL PAUSED** in the header of the card; new messages keep coming in above it. Turning the mouse wheel over the messages resumes the list and goes back to the newest message.
- **The SET and MEM windows float.** Move them by the title bar; the radio stays usable behind them, so a click outside no longer closes them (✕, their key or Esc do). They remember their place in the browser. SET has a smaller font, a narrower window and more uniform cards.
- **install_dsd.bat works on a PC without the needed root certificate.** Python stopped with `CERTIFICATE_VERIFY_FAILED`. It now falls back to `curl` or PowerShell of Windows, which verify the certificate too; the SHA-256 check of the file stays. Other download errors give a short message instead of a traceback. Thanks to Dano OM1ATS for finding this issue.
- **install.bat repairs a broken `.venv`.** A `.venv` pointing to a Python that is not there (left from an earlier attempt, or a removed Python) stopped step 2 with "did not find executable" and a wrong hint about the internet. It is now tested by running it and created again if needed; if a new one does not start either, the installer says so and shows which Python it used. Found thanks to tests by Dano OM1ATS.

## Ver. 0.109

- **DSD mode: digital voice (first test version, it still needs more testing).** New **DSD** key under MODE decodes DMR, P25, D-Star, YSF, NXDN, dPMR, M17 and more with
  [DSD-FME](https://github.com/lwvmobile/dsd-fme): voice in the audio output, a list of calls (talk group, ID, talker alias) in the DECODERS tab,
  optional daily log. AUTO finds DMR, P25, D-Star, YSF and X2-TDMA; the others are selected in the card. Encrypted calls are marked and stay
  muted. D-Star: callsigns from the radio header, or the caller from a GPS frame; readable text from the radio in Alias.
  DSD-FME is **not in the package** (patent notice in `NOTICE.md`): **run `install_dsd.bat`** to download it (separate, optional step in the installation; the upgrade
  zip keeps an installed one, and `upgrade.bat` reminds you if it is missing). It refuses to replace a decoder in use and leaves the installed version
  as it was. Tested on real signals with DMR and D-Star; other protocols, both TDMA slots at once and long runs not yet.
  HTTP API: `/api/dsd`, `dsd` in the state, `dsdcall` event.
- **S-meter layouts in SET (DISPLAY tab):** six new layouts besides **Needle**, chosen by clicking a small sample of each: **Bar graph** (curved row of segments),
  **LED bar** (straight row of segments), **VFD display** (glowing cyan bars), **Amber needle** (backlit dial), **7-segment** (large reading with a thin bar) and **Peak bar**
  (continuous bar, a white mark holds the last peak). All have the same scale, calibration and response, and a squelch mark (dark blue on Amber needle, yellow elsewhere).
  **Needle** stays the default; the choice is remembered in the browser, for all VFOs.
- **S-meter reacts faster:** it now gets a level with every block of samples, as often as the spectrum (about 12 times per second at 1.536 MS/s), instead of
  only one block in three. Short peaks are no longer missed, and the attack is faster. HTTP API: new `meter` event in `/api/events`.
- **S-meter reading stays in place:** the text under the meter no longer jumps when the level goes above S9.
- **SET is a large window with tabs** instead of a narrow side panel: **DONGLE** (dongle, upconverter, LO, ppm, gain, bias-tee, reset), **AUDIO** (squelch, LPF, HPF, AFI),
  **DISPLAY** (display width, S-meter, waterfall, touchpad wheel speed) and **TX** (only for a dongle that can transmit). The open tab is remembered in the browser.
- **Block diagram of all components in the README**, updated for this version; `docs/block_diagram.py` draws it.

## Ver. 0.108

- **Project files for GitHub:** code of conduct, contributing guide, security policy, issue forms and pull request template.
- **Licence files:** `LICENSE` is now the plain MIT text. The radio transmission notice moved to the new `NOTICE.md`, which also lists all third-party
  components and their licences. `RADIMCOM_sources_v<version>.zip` on the release page has the source code of the GPL and LGPL components (new `installer/make_sources.py`).
- **ZOOM is one key** instead of a row of buttons. It shows the zoom and is lit only above 1×. A click turns it off (back to 1× at once)
  or on (last value above 1×, remembered in the browser); the **mouse wheel over the key** changes it up and down (1×–32×).
- **LPF and HPF keys** (filter curve icons) in the AUDIO group: audio low-pass and high-pass filter, in all modes except DAB; on/off and
  frequency remembered per VFO. The key shows the cutoff. Change it with the **mouse wheel over the key** or type it in **SET**
  (LPF 100–15000 Hz, default 3000; HPF 20–5000 Hz, default 300). 6th-order Butterworth (36 dB per octave), both on = band-pass;
  HPF always stays below LPF. Changes crossfade without a click. The audio spectrum bubble darkens the part they cut off.
  You hear and REC the filtered audio, decoders still get the full audio (new `PassFilter` in `sdr.py`).
- HTTP API: `lpf`, `lpf_hz`, `hpf`, `hpf_hz` in `/api/set` and `/api/state`.
- **Shorter AUDIO keys** so the key row fits on one line: **STEREO** is now **S/M**, **NOTCH** is now **NF**.
- **DAB key moved to the DECODE group** (from the OTHER band group); the **CB ch19** band button is now just **CB**.
- **Memory name above the VFO:** new frame on top of each VFO window, as wide as the VFO. When the VFO frequency matches
  a memory (within 50 Hz, like the MEM list), it shows the name; the tooltip adds the group, mode and bandwidth. More memories on
  one frequency: the one with the same mode wins, then a favourite. Inactive VFOs too.
- Without a memory on the frequency the frame shows the **band plan** instead (axis label of the narrowest band, e.g. `HAM 70cm`, in grey;
  the tooltip lists all bands on the frequency). Outside the band plan it stays empty.
- **Squelch closes faster:** the hold after the signal drops below the level is 20 ms instead of 200 ms.
- **ACARS / VDL2 Squawk column:** new column between ICAO and ACFT type, the transponder code from ADS-B (adsb.fi / adsb.lol).
- **Emergency squawks:** a row with squawk 7500, 7600 or 7700 gets a red frame in the ACARS / VDL2 table.
- **ACARS / VDL2 daily logs:** the `[ADS-B ...]` part now has all ADS-B values from the table, in the column order: registration
  (ATN messages), callsign, ICAO, squawk, type, model, flight level with feet, speed; position last. The field order changed.
- **ACARS / VDL2 Ground Station column:** new column after Description, also in the daily logs (`| BTS/LZIB` after the description; ATN
  lines after the header). Airport of the VDL2 ground station (IATA/ICAO), found by its address in the ground station list, ARINC and SITA
  stations alike, so all stations of an airport have the same location; classic ACARS shows `-`. ACARS log lines also have the address
  (`| BUD/LHBP (1191BA)`). The card has the city of the airport under it, in small blue (not in the logs).
  New `airports.py` (IATA to ICAO and city tables, OurAirports, public domain).
- **VDL2 Ground Station filter:** pull-down in the card header with the locations of the messages in the table; shows only the selected
  location, together with the type tags. Remembered in the browser; the ✕ of FILTER ON clears it too.
- **Ground station list:** new `VDL2_Ground_Stations.txt` (2519 stations: address, airport, position and channel when known, city), source: [ACARS-VDL2 group](https://acars-vdl2.groups.io/), redistributed with approval. Thank you Sergi for amazing work. If you come across any new ground station that is not included in the list, please let us know. Thank you. The
  tooltip of a Ground Station cell shows the address and the list entry. A station not in the list falls back to decoding the address
  (SITA stations only); the program also works that way without the file.
- HTTP API: `vdl2.gs` (ground station address), `vdl2.gs_loc` (location), `vdl2.gs_city` (city) and `vdl2.gs_info` (list entry) in the `/api/acars` and `/api/cpdlc` messages.
- **One size for all flags:** the flags at the S-meter and in the VFO windows (USB / state, mode, CUE, AGC / gain, squelch) have the
  same height and letter size in every state; the RF GAIN and SQUELCH frames match them.
- **Speaker and REC** under the volume faders are now flag-sized buttons, one above the other, as wide as the faders.
  The speaker is green with sound on and red when muted.
- **Slower wheel on a touchpad:** VFO digits, spectrum and waterfall tuning, ZOOM, LPF and HPF now add up the small touchpad scroll
  movements and take one step per 150 px of scrolling at the default speed. A mouse wheel notch is still exactly one step.
  **SET → Touchpad wheel speed** (1–10, default 4; left = slower) changes it, remembered in the browser.

## Ver. 0.107

- **AFI – audio frequency inversion** (voice inversion scrambler / descrambler): new **AFI** key in the AUDIO group.
  The demodulated audio is mirrored around the inversion frequency F (f → 2·F − f, band 0 … 2·F): low-pass,
  mix with a 2·F carrier, low-pass again (new `FreqInverter` in `sdr.py`). Inversion is its own inverse, so the same
  setting scrambles and descrambles. All modes except WFM; on/off and frequency remembered per VFO.
  Applied before the squelch, so REC and the decoders get the descrambled audio.
- SET: **AFI – inversion frequency (Hz)**, 500–4000 Hz, default 1750 Hz (band up to 3500 Hz).
- HTTP API: `afi` (true / false) and `afi_hz` in `/api/set` and `/api/state`.
- **DAB / DAB+ digital radio**: new **DAB** button in the OTHER band group. The VFO goes to 2.048 MS/s on the
  centre of a Band III channel (5A–13F, default 12C) and a **DAB+** card opens on the DECODERS tab: channel select,
  ensemble name, SNR, station list (DAB / DAB+, bitrate); click a station to play it, with its DLS text
  ("now playing") and slideshow picture. Audio plays through MAIN volume (REC does not record DAB).
  - Decoding by **welle-cli** 2.7 (welle.io, GPLv2+) in `lib\dab\`, built with MSYS2 UCRT64
    (`installer\build_dab.sh`, sources and licences in `installer\DAB.txt`, `lib\dab\README.txt` in the package).
  - The dongle stays in RADIMCOM: new module `dab.py` runs a local rtl_tcp server (127.0.0.1, free port) that
    welle-cli connects to; its tuning requests retune the VFO, the gain stays the VFO's. Services, DLS, slides
    and the MP3 stream come from welle-cli's web server and are passed on by RADIMCOM.
  - DAB turns ACARS and VDL2 off; the DAB button again (toggle), another band button or OFF in the card turns DAB off and restores the
    previous sample rate. RTL-SDR only (not on LimeSDR or a chained VFO).
- HTTP API: `dab`, `dab_channel` in `/api/set` and `/api/state` (+ `dab_error`, `dab_channels`), new
  `GET /api/dab`, `/api/dab/audio/<sid>` (MP3), `/api/dab/slide/<sid>`, event `dabstate`.
- **WEFAX slant correction**: new **SLANT** field (ppm, -3000 to 3000) and **ALIGN** key in the WEFAX card: click two points on a
  line that should be vertical and the correction is computed. It compensates the sample clock error of the VFO's SDR, also
  straightens the image received so far and is kept after a restart. HTTP API: `slant_ppm` in `/api/wefax`, event `wefaxreload`.
- Passband label in the spectrum has two rows: tuned frequency, then demodulation and bandwidth (`LSB · 3 kHz`).
- **Audio spectrum bubble**: hover over the passband label to see the audio spectrum of the active VFO, up to the end of
  the passband. It is taken before the volume and MUTE. In WFM it shows the demodulated MPX signal to 20 kHz, with the
  19 kHz pilot (the audio itself ends at 15 kHz). HTTP API: new `GET /api/mpx`.

## Ver. 0.106

- **VFO chaining: one dongle for several VFOs.** A VFO can use the dongle of another VFO, e.g. one dongle for
  VFO A–D, or two dongles with two VFOs each (`"chain": "A"` in `vfos.json` instead of a serial number).
  - The owner VFO opens the dongle and sends its samples to the chained VFOs over a local socket
    (`127.0.0.1`, VFO port + 100; new module `iqshare.py`). Each chained VFO has its own frequency, mode, filter,
    squelch, decoders, waterfall and audio.
  - The owner's tuning sets the band the dongle receives (centre ± 95 % of half the sample rate). A chained VFO can be
    tuned anywhere: inside the band it shows a green **CHAIN** flag instead of the USB icon; outside (also when the
    owner moves away) it is silent and shows an orange **OOR** flag ("out of range VFO-A" on hover).
  - Gain, RTL AGC, bias-tee, ppm and sample rate belong to the dongle: changed on a chained VFO, they are applied
    on the owner VFO and so to every VFO on that dongle. VDL2 and TX are not available on a chained VFO.
  - SDR setup (`setup.bat`): for each VFO type a device number, unplug a device, or type the letter of an earlier
    VFO (e.g. `A`) to share its dongle; the wizard now offers all four VFOs even with fewer dongles.
  - The launcher starts the VFOs with their own dongle first, then the chained ones.
- ATN CPDLC (VDL2): click a message to see all decoded fields under the compact lines: the CPDLC / CM / ADS-C
  message first (header with date and time, ASN.1 element names and values), then the VDL2 frame
  (AVLC addresses, X.25, CLNP, COTP, session / association). Click again to collapse.
- Direction arrows in the ACARS / VDL2 card coloured: ↓ downlink (from the aircraft) green, ↑ uplink (from the
  ground) orange.
- VDL2 key greyed out on a LimeSDR VFO (VDL2 runs on RTL-SDR only).
- Message filter in the ACARS / VDL2 card: click the ACARS / CPDLC / ADS-C tags at the top of the card
  to show only those messages (tags can be combined; CPDLC and ADS-C include the ATN versions). "FILTER ON · N of M shown" with ✕ to show all again;
  the filter is remembered.
- ACARS / VDL2 card fills the DECODERS tab and only the message list scrolls; the header with the keys,
  filters and notes stays in place.
- ATN CPDLC rows: the Aircraft column waits for the ADS-B lookup ("…") and then shows the registration, instead of
  showing the ICAO address first and rewriting it.
- ATN ADS-C (ADS-C reports over VDL2) decoded like FANS ADS-C: report type, position, altitude, time, accuracy,
  contract; track, ground speed, vertical rate; heading, Mach, IAS; wind and temperature; next waypoints with times;
  planned trajectory (fixes, levels, ETA, Mach, start of climb / descent). Shown with the purple ADS-C tag.
- Tags unified: ATN CPDLC messages have the same green CPDLC tag as FANS CPDLC (the Description column still says
  "ATN CPDLC"); rows, filter and description use the same colours.
- The tag (ACARS / CPDLC / ADS-C) has its own first column "Type" in the message table. Fixed column widths:
  the table keeps its layout when a filter is switched on or off.
- New **Country** column (between Frequency and Aircraft): flag and code of the country of registration, worked out
  from the aircraft's 24-bit ICAO address (ICAO Annex 10 address blocks, `static/icao_countries.js`), like the adsb.fi
  map does. ATN messages: from the address in the message; ACARS: from the ADS-B lookup. Flag images from flagcdn.com.
- Aircraft column renamed **Callsign** (registration only, linked to the map). Column order: Type, UTC, Freq, Country,
  Flight, Callsign, **ICAO** (24-bit address), and from ADS-B **ACFT type**, **Model**, **FL**, **Speed**; then Label,
  Description, Message. The position is no longer shown. "Frequency" shortened to "Freq".
- **Memory names on the spectrum**: memories in the visible part of the spectrum get a green ▲ marker at the top edge
  (under the band-name strip) pointing at their frequency, with a name tag below it. Tags are placed in up to three rows
  so they do not overlap each other or the mode / bandwidth label; favourites get a place first, a memory that does not
  fit shows only its marker. Hover a tag for the full name, frequency, mode and group; click it to recall the memory
  (frequency, mode, bandwidth).
- **One design for all decoder cards** (FT8, ACARS / VDL2, CW, RTTY, WEFAX, SSTV): the card fills the height of the
  DECODERS tab, the header, settings and notes stay in place and only the black content box (table, text, image)
  scrolls with its own scrollbar. Several cards on at once share the height. SSTV: the live image stays in view and
  the gallery of saved images scrolls next to it.
- **Page scales with the window**: the whole page is laid out in a "virtual window" of at least 1920 × 820 px and
  scaled to the browser window, so the layout no longer reflows on small windows and browser zoom has no effect.
  Spectrum and waterfall stay sharp at any scale.
- **CW decoder more reliable** with weak signals, fading (QSB) and static crashes (QRN):
  - automatic minimum threshold from the noise floor measured in the receiver passband, so noise alone does not
    produce characters (no more random E / T / I after the station stops);
  - the mark level is taken from the decoded marks and falls back quickly after a pause, so a fade no longer leaves the
    threshold too high; lower on/off thresholds let faded marks through;
  - noise blanker: short static crashes are removed before the filters (long bursts are kept, a strong station is
    never blanked);
  - the decoder starts on weaker signals (tone SNR from 6 dB instead of 8 dB);
  - the speed estimate no longer locks onto noise (it is used only when at least 80 % of the marks fit dots and dashes).
  On simulated signals the character error rate fell on average from 40 % to 15 % (e.g. 20 WPM at 0 dB / 500 Hz:
  46 % → 15 %, fading 10 dB at 25 WPM: 21 % → 2 %, static crashes with fading: 24 % → 2 %). The ALC setting does
  not affect the decoder: it works on the receiver signal before the audio and has its own level tracking.
- **Band plan on the spectrum axis** extended and moved to a local table `static/bandplan.js` (Europe / ITU Region 1;
  sources: ITU RR Art. 5, CEPT ERC Report 25 / ECA, ERC/REC 70-03, IARU Region 1 band plan, 3GPP / ETSI, ICAO Annex 10,
  WMO). New bands: UHF military airband (225–400 MHz), VOR/ILS, DME/TACAN, SSR 1030, ADS-B 1090, TETRA, VHF low /
  military (30–87.5 MHz), DAB (Band III), DVB-T/T2 (470–694 MHz), LTE 700 / 800, GSM-900 / 1800, UMTS 2100 (UL / DL),
  LPD433, SRD 868 / LoRaWAN, ISM 2.4 GHz / Wi-Fi, weather satellites (137 MHz, HRPT 1.7 GHz), radiosondes
  (400.15–406 MHz and L-band), COSPAS-SARSAT 406, GNSS L1 / L2 / L5, Inmarsat, Iridium, marine VHF, AIS, NAVTEX,
  2182 kHz, paging 169 MHz, DCF77, NDB, LW / MW broadcast, 13 cm ham. Narrow bands are drawn over wide ones
  (e.g. ADS-B inside DME); hover the axis for a tooltip with the descriptions of all bands at that frequency.
- **Memory import / export** (MEM drawer → Import / export):
  - **⇧ IMPORT SDR#**: enter the SDR# installation folder (remembered by the browser) and import its memories. Reads
    `frequencies.xml` in the folder and in profile subfolders of newer SDR# versions (e.g. `Instances\Profile1`); a single
    profile folder or `frequencies.xml` can be given too. Entries with any frequency shift are imported; duplicates
    (same frequency and name), out-of-range frequencies and unsupported modes are skipped; a broken file does not stop
    the others. The note shows how many were imported / skipped and from which profiles. The command-line import
    (`python memories.py …`) still takes only HF upconverter entries.
  - **⇩ EXPORT ★** downloads the starred memories, **⇩ EXPORT <group>** the group selected in the filter (All = every
    memory), with one click, as a JSON file in the `memories.json` format.
- **HTTP API description** in `API/API.md` (ports, state, settings, events, audio, decoders, memories, examples);
  linked from the README and included in the install / upgrade zips.
- **LimeSDR TX limited to allowed bands**: the receiver (server side, not only the page) allows PTT only when the
  whole emission (tuned frequency ±5 kHz) is inside ham 160 m – 10 m, 6 m, 4 m, 2 m, 70 cm, 23 cm (IARU Region 1),
  CB 26.960–27.410 MHz or PMR446 446.0–446.2 MHz. Retuning during TX ends the transmission.
- **TX disclaimer**: red "IMPORTANT – transmitting disclaimer" in SET (licence required under ITU / CEPT / FCC /
  national rules, operator fully responsible, software provided AS IS). Enable TX asks to accept it, the server
  refuses TX without it and remembers when it was accepted; TX enabled by an older version is switched off until
  the disclaimer is accepted.
- **MIT licence** (`LICENSE`, also in the install / upgrade zips) with a radio transmission notice: anyone who
  modifies or removes the TX limits is solely responsible.
- All remaining Slovak comments in the code (`static\app.js`, `style.css`, `index.html`, `bandplan.js`, batch files)
  translated to English.

## Ver. 0.105

- **VDL2 decoder** (VDL Mode 2, 136.725–136.975 MHz): the digital data link that carries most airline ACARS over
  Europe and the European ATN CPDLC. New **VDL2** key under DECODE: the VFO goes to 2.1 MS/s around 136.850 MHz
  and all five European VDL2 channels are decoded at once; spectrum, waterfall and audio keep working.
  Decoding is done by [dumpvdl2](https://github.com/szpajder/dumpvdl2) 2.7.0 (GPLv3, built for Windows with MSYS2,
  `lib\vdl2\`), which runs as a separate program fed with the raw samples (`vdl2.py`).
- ACARS messages from VDL2 go through the same decoding as classic ACARS: FANS-1/A CPDLC and ADS-C inside,
  ADS-B lookup, daily logs (tagged `VDL2`). European **ATN CPDLC** is shown in a compact form:
  message number, answered message, time, "ack required", and the elements with their values
  (e.g. `dM6 REQUEST FL360`, `dM0 WILCO`), plus connect / abort / release.
- **ADS-C decoder** (`adsc.py`, ARINC 745): position reports (position, altitude, time, accuracy), track,
  ground speed and vertical rate, heading and Mach, wind and temperature, predicted route, projected intent,
  flight ID, contract requests and acknowledgements. Field layouts checked against libacars and live reports.
- **One card for all aircraft messages.** ACARS and VDL2 are two keys (one link at a time) that open the same
  card; the CPDLC key and card are gone. Coloured tags: ACARS (plain message), CPDLC, ADS-C, ATN CPDLC.
  The card title and buttons follow the link: ACARS channel buttons, or one 136.850 button for VDL2.
  One LOG writes both `acars_` and `cpdlc_` daily logs.
- ATN CPDLC messages carry only the aircraft's 24-bit ICAO address: registration, type, position and callsign
  are now looked up on ADS-B by that address (adsb.fi / adsb.lol), shown in the Aircraft and Flight columns and
  written to the CPDLC log.
- 2.1 MS/s added to the sample rates (needed by VDL2).

## Ver. 0.104

- **CPDLC decoder** (FANS-1/A, ARINC 622): controller-pilot messages carried in ACARS (labels AA/BA/H1)
  are decoded to the standard message text, e.g. "CLIMB TO AND MAINTAIN FL350",
  "AT VANDA CONTACT CHRISTCHURCH CONTROL 128.100 MHz", and position reports with fixes, ETA, winds and temperature.
  Shows the message number (MIN), the answered message (MRN), the ground station and the CRC check.
  Long messages split into several ACARS blocks are joined.
- CPDLC card with its own **CPDLC** key under DECODE; it works with the ACARS card off. The decoded CPDLC text
  is also shown in the ACARS card. Click a message to see the raw ARINC 622 text.
- CPDLC daily log: `data\acars\cpdlc_YYYY-MM-DD.txt` (UTC) when LOG is on.
- Command-line test: `python cpdlc.py u AA "/AKLCDYA.AT1.9V-SVG21D0755D84AD067448398722949A7521C8AB4A1C8EAB5CE393"`.
- New file `CHANGELOG.md` (this file).

## Ver. 0.103

- Settings, memories, logs, saved images and backups moved to the `data\` folder (program files stay in the
  main folder). Older installations: the files are moved to `data\` automatically at the first start.

## Ver. 0.102

- Decoders (FT8, WEFAX, SSTV, ACARS) moved to a second tab DECODERS next to SPECTRUM, no more scrolling down.
  The tab shows the number of running decoders and a green dot when something new arrives; turning a decoder on
  opens the tab.
- The open tab (SPECTRUM / DECODERS) is remembered for each VFO and restored when switching VFO; a VFO without
  a saved tab opens DECODERS when a decoder is running on it.
- RTTY decoder (Baudot/ITA2) with automatic detection of shift (90–1000 Hz), speed (45.45/50/75/100 Bd) and
  polarity; each can also be set by hand. E.g. amateur RTTY 45.45 Bd / 170 Hz, DWD weather 50 Bd / 450 Hz
  (4583, 7646, 10100.8 kHz). Text shown like on an old green phosphor terminal.
- CW decoder is now a card in the DECODERS tab; CW and RTTY text fills the whole tab.
- LOG checkbox in every decoder card: daily log `logs\<decoder>_YYYY-MM-DD.txt` (UTC, one line per message;
  WEFAX/SSTV log the names of saved images). ACARS logs to `acars\` only when LOG is on.

## Ver. 0.101

- ACARS decoder (VHF airband, 131.725 MHz etc.): coherent MSK demodulation, CRC check, message description in
  plain English, long messages collapsed (click to expand).
- ACARS: aircraft type and position looked up on ADS-B (adsb.fi / adsb.lol), shown in blue; click the
  registration or flight to open the live map.
- ACARS daily log: `acars\acars_YYYY-MM-DD.txt` (UTC), including the ADS-B data.
- SQUELCH slider under RF GAIN for every VFO (dimmed in modes without squelch).
- FM filter widths 500 Hz – 50 kHz (buttons 0.5 / 3 / 6 / 12 / 25 / 50 kHz).
- Grey RDS logo when no RDS is received; inactive ALC/SQL flags no longer larger.
- Setup: upconverter LO is checked (30–1000 MHz, Hz input converted); LO/ppm can be fixed in SET even when the
  dongle is in error.
- FT8 works without PyAudio (newer Python); a missing PyFT8 no longer stops the receiver.
- Installer shows the download progress of the Python packages.

## Ver. 0.1

- First release: 4 VFOs, spectrum/waterfall, AM/FM/WFM/SSB/CW, WFM stereo + RDS, upconverter, CUE, REC,
  FT8/WEFAX/CW/SSTV decoders, memories, LimeSDR TX, installer with SDR setup.
