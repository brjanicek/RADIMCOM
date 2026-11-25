[← README](../../README.md) · [Documentation](../README.md)

# GRAVES (meteors, satellites, aircraft)

Echoes of the French space surveillance radar **GRAVES**. Its transmitter near Dijon sends a continuous carrier on
**143.050 MHz**. From Central Europe (about 900 km away) the transmitter is below the horizon, so it is heard only when
something reflects the carrier:

- a **meteor trail** about 100 km high: a short echo a few tens of Hz off the carrier (the Doppler); RADIMCOM counts
  them per hour and per day and marks the meteor showers on a yearly chart;
- the **meteoroid itself** (a *head echo*): a streak sweeping onto the trail's Doppler just before the trail echo;
- a **satellite**: a long streak sweeping over hundreds of Hz to kHz, identified from public orbital elements;
- an **aircraft**: a long echo within ±250 Hz, looked up on adsb.fi.

Modules: `meteor.py` (the detector, classification, detail), `meteor_fine.py` (the fine waterfall), `meteor_sat.py`
(the wide spectrum, satellite tracks and their identification), `meteor_air.py` (aircraft), `meteor_weak.py` (FAST,
SAT·TLE, SAT·LINES), `meteor_audio.py` (the sound of the echoes), `meteor_store.py` (the daily log and the marked
echoes).

## DECODERS › GRAVES

The head of the page: **ON** switches the counter on, **LOG** writes every echo to a daily log
(`data\logs\meteor\YYYY\MM\DD\meteor_YYYY-MM-DD.txt`, UTC, with the satellite or aircraft found and H for a head echo),
**i** opens a short guide, **?** a sub-page of how each echo is classified (the rules of the meteor detector in their
order, the satellite tracker with TLE, the weak detectors; again **?**: back). The counts are shown on every page next to the tabs: **HOUR**, **PREV** (the previous UTC
hour), **60 MIN**, **TODAY**, **PLANES** and **SATS** (since the start, not counted as meteors).

### LIVE

- **Waterfall** (fills the height of the block), with the chart under it.
  - Width: **±250 Hz** and **±500 Hz** are the meteor band in the fine cells of **1 Hz × 16 ms** (below); **±1 kHz** is a
    part of the wide spectrum (aircraft and slow satellites larger); **±8 kHz** is the wide spectrum where the satellites
    are looked for (~16 Hz bins).
  - Time: **10 S**, **30 S**, **1 M**, **2 M**, **10 M**, **1 H**. One column per screen pixel; every 16 ms cell is kept
    for 3 minutes, longer views take the strongest value of each column. It scrolls smoothly.
  - ⚙: colour schemes and levels like the main waterfall (*Dark under*, *Full colour at*). A new installation starts
    with ±500 Hz, 1 minute, Classic, 10 dB and 25 dB.
  - A faint grid: horizontal lines at the carrier (a little brighter) and at steps of the Doppler shift, drawn as the
    background from the start; every signal covers it.
  - The page always shows the VFO where GRAVES runs (named in the status when it is not the active VFO), so its
    waterfall and history stay when another VFO is chosen.
  - The ±250 / ±500 Hz views are about **1.3 s behind the sound**: a 1 s frame needs half a second of signal after each
    moment before its cell is final. The ±1 kHz and ±8 kHz views are about 1.2 s behind (the chart's answers come once a
    second).
- **Chart:** the strongest bin over its floor, the threshold **THR** dashed (its value in a frame); the mouse wheel over the
  chart moves THR by 0.5 dB. Echoes are marked; satellites at the same time each in a lane of their own.
- **ECHOES**: **NOW** (the last 500 since the start), **DAY…** (an earlier UTC day from the daily log; no detail unless
  marked) or **★ MARKED** (☆ on a row keeps the echo with its detail and sound for good in `data\meteor_marks\<VFO>`).
  Filters **ALL**, **METEORS**, **SAT**, **PLANE**, **H** (with a head echo), a minimum SNR, and **CLR** (clears NOW;
  statistics, log and marks stay). The *Type* column has a coloured tag in the colours of the charts: **UNDER** (green),
  **OVER** (amber), **PLANE** (blue; flight / registration after it, a click on it opens the aircraft on adsb.fi), **SAT**
  (violet; the satellite found, *?* when none), **HEAD** (pink, a head echo found), and how it was found: **FAST BURST**,
  **KNOWN (TLE)**, **UNKNOWN LINE** / **LINE** (a PLANE with LINE: a slow line near the carrier found by SAT·LINES).
- **Detail** (a click on a row): the title with the same tags; **◀ PREV** / **NEXT ▶** (fixed at its left) open the
  echo before / after it among those the table shows (its source, kinds and minimum SNR).
  - a meteor: the fine cells (1 Hz × 16 ms) around its Doppler from 1 s before to 1 s after, dashed lines at its start
    and end; with **HEAD ECHO** on also the ±5 kHz head echo spectrum on the same time axis under it. All parts get the
    colour levels of the fine cells, so they look alike. A head echo reaching out of the band shown: its Hz widened to
    the whole head echo, the rest filled from the head echo spectrum (thin lines at the edges of the band);
  - a satellite: its own band (its track ±400 Hz) over the whole track, enhanced by itself (each frame averaged with the
    8 before it along the drift of the track, its own colour levels), so a weak streak shows without touching the levels
    of the waterfall;
  - a head echo, a satellite's calculated Doppler or an aircraft's Doppler from adsb.fi: two bright green dashed lines
    just over and under the track, which stays clear between them.
  - **SAVE**: this echo into the recordings folder (as REC below).
  - **▶ PLAY** / **WAV**: the echo as on 143.049 MHz USB (the carrier = a 1 kHz tone). A satellite is followed along its
    Doppler track: only ±60 Hz around it is kept (a weak one is heard over the noise), and it sounds as a tone that
    follows its Doppler; a sweep wider than 2 kHz is squeezed into the audio band.

### STATS

- **LAST 48 HOURS:** the echoes per UTC hour, underdense in green, overdense in amber; the thin bar underneath shows how
  much of the hour was monitored.
- **YEAR:** the echoes per hour of monitoring for each day, so a day with only a short watch compares fairly. The peaks
  of the main showers are marked (QUA, LYR, ETA, ARI, ZPE, PER, DRA, ORI, LEO, GEM, URS); radio also hears the daytime
  showers. Even without a shower the rate changes every day, with the most echoes around 6 h local time and the fewest
  around 18 h.

Counts per UTC hour (underdense, overdense, seconds monitored) are kept for 400 days in `data\meteors_<VFO>.json`.

### SETTINGS

Blocks in the style of STATION (lit when in use, amber when something needs attention):

- **ROTOR · AZ / EL** (optional): the rotor dial with the bearing to GRAVES from the QTH (about 265° from Slovakia) and
  the elevation of the meteor zone over the middle of the path (about 10°). **GRAVES → ROTOR** shows the path in
  RCTRL › SETTINGS (linked or open); **POINT** turns the rotor to GRAVES through it; **RCTRL** opens the rotor settings.
- **RECORDINGS:** **REC** (also REC at the head of ECHOES, the same setting): while it is on, every echo of the chosen
  kinds (METEORS / SAT / PLANE) is saved to the RECORDINGS tab (day folder, source GRAVES) as MP3
  (`METEOR_<MHz>MHz_USB_<time>_GRAVES.mp3`, 1 s before and after); **IQ ECHO** adds its IQ (±8 kHz, `iq\…_IQ_GRAVES.wav`,
  playable in the IQ PLAYER), **IQ BAND** the IQ of the whole dongle band from PRE-REC (switched on for at least 30 s,
  `…_IQ_GRAVESBAND.wav`, at most 8 s).
- **RECEIVER:** the dial and the mode; **TUNE 143.049 USB**. The counter reads the baseband of the VFO, not the audio,
  so any mode works with the dial within about ±10 kHz of the carrier.
- **DETECTOR:**
  - **THR**: the threshold in dB above the noise floor (default 10 dB; noise alone stays under about 8.5 dB).
  - **RESET STATS** deletes the hourly and daily statistics of this VFO.
  - **AFC** (on by default): the meteor trails are at ~0 Hz, so they show where the carrier really is when the receiver
    is a few ppm off. How it works:
    - The trails drift only a few tens of Hz with the wind, so their Doppler is the receiver's error.
    - **First lock:** the first meteor of at least 13 dB SNR moves the carrier of all the detectors to its Doppler.
    - **Trim:** the median Doppler of the last 12 meteors (at least 5) moves it again when it is 8 Hz or more off;
      smaller corrections are not made, so the noise floor is not learned again for nothing.
    - **Lost carrier:** with no meteor for 10 minutes, the carrier is looked for in the ±8 kHz spectrum. Three short
      flashes (under 1.5 s, at most 60 Hz of drift, 12 dB or more) within 40 Hz of each other in 20 minutes are
      meteors, and the carrier moves to their median. The next strong meteor locks it again.
    - Only the counter's carrier moves; the VFO is not retuned. The waterfalls, the floor, the fine spectrum and the
      sound go on around the new carrier without learning again. A meteor found before a move does not trim it.
    - The correction stays within the wide spectrum and is kept across restarts. Switching AFC off goes back to the
      dial. More than a few hundred Hz off: set the PPM of the dongle.
  - **HEAD ECHO**: the ±5 kHz spectrum with ~15 ms frames for fast head echoes (kHz per second).
  - **ADS-B**: aircraft echoes looked up on adsb.fi (else adsb.lol) around the middle of the path (only that point is
    sent).
  - **Weak echoes**, each off by default:
    - **FAST**: pings of a few tens of ms in the time signal (the carrier ±150 Hz in 32 ms spectra every 8 ms, as in the
      BRAMS network), which the meteor detector's ~0.25 s dilutes; a reference band rejects impulse noise, a burst that
      sweeps is left out. Counted as underdense (**FAST BURST**, F in the log).
    - **SAT·TLE**: the ±8 kHz spectrum summed along the bistatic Doppler of every satellite GRAVES lights over the
      station (every 15 s, the last 40 s): streaks too weak for the tracker, with the satellite already known
      (**KNOWN (TLE)**). Needs the station location. With thousands of lit satellites some curve always fits the noise
      by chance, so a streak needs a z score of 10 and a median level of 1.5 dB along it.
    - **SAT·LINES**: weak straight streaks (80–600 Hz/s) by a Hough transform over 6 s windows, joined to tracks and
      identified like the tracker's (**UNKNOWN LINE** / **LINE**). A track within ±350 Hz (the Doppler an aircraft can
      have) drifting under 25 Hz/s is an aircraft; slow lines (under 80 Hz/s) are looked for there too, so a weak
      aircraft without drift is found.
    - The SNR of a weak satellite is the median level along its streak on its own bin (noise alone about −0.5 dB), not
      its strongest point (a meteor it crosses at the carrier).
    - What the tracker or the meteor detector already has is not reported twice.

## How it works

### The meteor detector

1. The baseband of the VFO goes through a spectrum of N samples (N a power of two near fs/8, about 4–8 Hz per bin),
   every N/4 samples (about 30 ms). Only ±500 Hz around the carrier is used.
2. Each frame is divided by its median over that band: a gain step (AGC+) or broadband impulse noise lifts all bins
   together and so changes nothing.
3. The power of each bin is averaged over 4 frames and compared with the noise floor of that bin, a slow average: 10 s
   while the bin is quiet and 120 s while it is up. A steady carrier (the direct GRAVES signal on a tropo opening,
   birdies) is learned into the floor and does not trigger. The first 4 s only learn the floor. Under an echo the floor
   rises at most 0.2 dB/s, so a strong echo does not lift its own floor (it would end early and its decay would look
   too fast).
4. An echo starts when the strongest bin is THR above its floor. It lasts while its own bins (±2) stay within 3 dB below
   that, and ends after 0.3 s below. A much stronger bin within 150 Hz (a head echo coming onto its trail) takes the echo
   over. Frames where more than 30 % of the band is up at once are left out as broadband.
5. The times of all spectra and of the sound come from the samples counted (the wall clock only anchors them), so blocks
   that arrive late and then all at once do not shift one spectrum against another.

### Classification

Tuning this is demanding: it builds on scientific work on meteor radar, bistatic radar and statistical decision
(below) and on our own remarks from the live echoes. The physics is in `meteor_phys.py`.

**The physical bounds** (bistatic Doppler f = −(1/λ)·d(R_T + R_R)/dt, its rate v⊥²/(λR), λ = 2.096 m; Willis,
*Bistatic Radar*; Skolnik, *Radar Handbook*):

| Target | Doppler off the carrier | Drift | Shape |
|---|---|---|---|
| meteor trail | the wind's, ≲ 95 Hz | a few Hz/s (twisted overdense trails more) | rises at once, underdense decays exponentially (McKinley, *Meteor Science and Engineering*; Ceplecha et al. 1998) |
| aircraft (≤ 300 m/s) | ≤ ~286 Hz | ≤ ~6 Hz/s | there for tens of seconds, comes up gradually |
| LEO satellite (7.5 km/s) | up to kHz | near the carrier ≥ ~18 Hz/s, at most ~121 Hz/s | long, fades in and out with the GRAVES beam |
| head echo (the meteoroid) | kHz | ≥ ~0.5 kHz/s, onto the trail's Doppler | tens to hundreds of ms just before the trail |

A drift is measured robustly (**Theil-Sen**: the median of the slopes of the pairs of points at least half its length apart, as the
Doppler is quantised to bins, so the end of a head
echo or noise as the trail fades does not tilt it) with its standard error (the robust spread of the points, the bin
quantisation, the frames of the detector are not independent) and decides a class only when it is beyond the bound by
**two standard errors**.

**Decay time τ:** an underdense trail's amplitude falls as exp(−t/τ), τ = λ² sec²φ / (32π²D) with D the ambipolar
diffusion (McKinley). τ is fitted on the power after the peak with the noise taken out (the detector's frames and
smoothing keep the rate of an exponential); the detail shows it and whether the decay is exponential (r² ≥ 0.9:
underdense) or not (an overdense plateau, a fading signal). Measurable from about 0.15 s; shorter pings are not
measured.

- **Head echo → meteor:** an echo with a head echo is always a meteor (UNDERDENSE / OVERDENSE), whatever else it looks
  like; nothing else sweeps onto the trail at kHz per second.
- **PLANE** (listed, not counted): longer than 20 s (and not drifting like a satellite); or longer than 2 s drifting
  surely over 5 Hz/s by at least 3 bins, within the Doppler an aircraft can have; or the next piece of an aircraft just
  heard at its Doppler; or already there weakly at its Doppler before its strong part (a meteor starts at once). A
  meteor just before at the same Doppler does not make the next one an aircraft.
- **SAT**: an echo drifting straight at 25 Hz/s or more for at least 0.6 s (surely faster than ~18 Hz/s); a short echo
  sweeping through the band all along; a part of a satellite track of the wide spectrum; the next piece of a satellite
  on its line within 10 s.
- **Is an echo on a satellite's line (or track) its piece, or a meteor that came there?** The evidence is weighed by
  Bayes factors (Jeffreys; Kass & Raftery 1995), added up:
  - its own drift: like the line's or still like a trail in the wind (measured, or roughly from a short ping);
  - the chance of a meteor there by accident: the station's own meteor rate and Doppler distribution, learnt live
    (100 meteors an hour around the carrier before there are enough);
  - the orbital elements: is a satellite lit by GRAVES and over the station predicted there? How often that happens by
    chance is measured on the same points shifted in frequency. Near the carrier about 230 of ~470 lit satellites are
    within ±300 Hz, so a short ping is not decided by TLE, a longer track is. The share of satellites without public
    elements (debris) is learnt from the identifications (30 % before).
- **A "satellite" track made of meteors:** the tracker can join meteors at different Dopplers into one curve. Each
  piece of a track is weighed: a satellite drifts along its curve in every piece, meteors stand still; with the TLE
  evidence added.
- **UNDERDENSE** (shorter than 1 s) and **OVERDENSE** otherwise.

### Satellites

A ±8 kHz spectrum (~64 ms frames) always runs beside the meteor detector. Its peaks are joined into tracks; a long,
smooth track that drifts faster than an aircraft or runs further from the carrier than an aircraft can is a satellite,
one row per pass (its pieces, as the beam of GRAVES moves on, are not counted as meteors). A short track that comes onto
one Doppler and stays there is a head echo braking onto its trail, not a satellite. Meteor echoes are reported a few
seconds later, when that is decided.

**Which satellite:** its bistatic Doppler GRAVES → satellite → station is compared with every satellite with public
orbital elements (CelesTrak *active*, *visual*, *stations* in `data\graves_tle.txt`, downloaded once a day, plus the
elements of SATELLITES), with the receiver offset fitted. Name, NORAD, AZ / EL / distance and the fit are shown. Debris
and objects without public elements stay *?*. Needs the station location.

### Aircraft

A PLANE echo is compared with the aircraft adsb.fi sees within 250 NM of the middle of the path, moved to the time of
the echo: flight, registration, type, FL and distance. An aircraft gives only ±250 Hz, so the receiver offset matters:
it is measured on the satellites identified surely (else 0). Near the middle of the path every aircraft is close to
0 Hz, so several may fit (shown as *others*).

### The fine waterfall and head echoes

The meteor band is also kept as a **reassigned spectrogram** (Auger & Flandrin) of 64 ms and 1 s frames: the power of
each bin is moved to the time and frequency where it really is, and in each cell of 1 Hz × 16 ms the smaller of the two
counts, so it is sharp in time and in frequency at once.

A **head echo** is looked for three ways:

- in the ±5 kHz spectrum (HEAD ECHO key): a straight steep streak (at least 2 kHz/s over 300 Hz) going one way onto the
  trail, away from the carrier and from the echo's own Doppler (a strong echo spreads over the short frames);
- in the fine cells: a path of strong cells from where the trail really starts back in time, coming onto the trail in a
  parabola or an exponential (it brakes), at least 150 Hz/s over 40 Hz, nearer to the trail from cell to cell;
- in the detector's own track: a short steep head echo the detector started on, coming onto the trail point by point;
- **a faint head echo** (`meteor_head.py`), too weak for its points to stand out one by one: the power of the ±5 kHz
  spectrum (not clipped) is summed along every straight line that ends at the trail's Doppler at about the start of
  the echo (0.48–80 kHz/s, the slopes so dense that a line is never more than half a bin off), and compared with the
  noise just before (track-before-detect, a Hough transform through one point; Carlson, Evans & Wilson 1994; Tonissen
  & Evans 1996). The threshold (9.5 σ) was set on noise alone with all the lines tried: under ~1 false head in 1000
  echoes. About 3.5 dB more sensitive; the detail says "faint … σ over the noise". It needs HEAD ECHO on.

The head echo is looked for when the echo ends, before it is classified (it decides a meteor).

### Simulated results (`tests/test_meteor.py`)

- a 0.3 s ping 20 dB above the noise in one bin is one underdense echo, a 3 s echo overdense;
- a steady carrier, a 10 dB broadband step and minutes of noise give no echo;
- a drifting echo, an aircraft without drift and a weak aircraft line are PLANE; meteors in a burst at one Doppler stay
  meteors;
- a satellite cut into pieces by the beam is one SAT echo; its sound follows its Doppler, also 15 dB under the noise of
  the audio band;
- a straight, a curved and a slow (1 s) head echo are found, the spread of a strong echo is not one;
- a short meteor on a slow satellite's line stays a meteor; a ping drifting with the line but with a head echo is a
  meteor; meteors joined into a curve are not a satellite, a satellite in pieces is one (`tests/test_meteor_phys.py`);
- a faint head echo too weak for its points is found, noise alone gives none (`tests/test_meteor_head.py`).

## Tips

- A 2 m Yagi pointed west at low elevation gives the most echoes; a vertical or a turnstile also works.
- Keep the gain fixed, or AGC+ on. The counter ignores the steps.
- Hourly counts from different stations or antennas cannot be compared directly. Compare the shape over the day and the
  rise during a shower.
