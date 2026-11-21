[← README](../../README.md) · [Documentation](../README.md)

# METEORS (GRAVES)

A meteor counter on the French space surveillance radar **GRAVES**. Its transmitter near Dijon sends a continuous carrier
on **143.050 MHz**. From Central Europe (about 900 km away) the transmitter is below the horizon, so it is heard only for
a moment when a meteor trail about 100 km high reflects the carrier. Each such reflection is one echo, a few tens of Hz
off the carrier (the Doppler). RADIMCOM counts the echoes per hour and per day and marks the meteor showers on a yearly
chart (`meteor.py`).

## DECODERS › METEORS

The page is built from blocks in the style of STATION:

- **ON** switches the counter on. **LOG** writes every echo to a daily log
  (`data\logs\meteor\YYYY\MM\DD\meteor_YYYY-MM-DD.txt`). **i** opens a short guide.
- **RECEIVER** shows the dial and the mode.
  - **TUNE** sets 143.049 MHz USB, where the carrier is an audible 1 kHz tone.
  - The counter reads the baseband of the VFO, not the audio, so any mode works when the dial is within about ±10 kHz of
    the carrier.
  - The block lights up when GRAVES is near the dial.
- **ROTOR** is optional and is only used when a rotor is connected.
  - It shows the bearing to GRAVES from the QTH (SETUP › LOCATION): about 265° from Slovakia. It also shows the
    elevation of the meteor zone over the middle of the path, about 10°.
  - It shows the state of the path **METEORS → ROTOR** in RCTRL › SETTINGS: LINKED or OPEN.
  - **POINT** turns the rotor to GRAVES. It works only while the path is linked.
  - **RCTRL** opens the rotor settings.
  - The block lights up when the antenna points at GRAVES.
- **DETECTOR** shows the state and has these controls:
  - **THR** is the threshold in dB above the noise floor. The default is 10 dB; noise alone stays under about 8.5 dB.
  - **CLR** clears the list of echoes.
  - **RESET** deletes the statistics.
- **COUNTS** shows the echoes in this UTC hour, the previous hour, the last 60 minutes and today, plus the echoes
  recognised as aircraft.
- **LAST 2 MINUTES** plots the strongest bin above its noise floor, with the threshold (red, dashed) and the echoes as
  shaded bands.
- **LAST 48 HOURS** shows the echoes per UTC hour: underdense in green, overdense in amber. The thin bar underneath shows
  how much of the hour was monitored.
- **YEAR** shows the echoes per hour of monitoring for each day, so a day with only a short watch compares fairly. The
  peaks of the main showers are marked (QUA, LYR, ETA, ARI, ZPE, PER, DRA, ORI, LEO, GEM, URS); radio also hears the
  daytime showers. Even without a shower the rate changes every day, with the most echoes around 6 h local time and the
  fewest around 18 h.
- **ECHOES** lists each echo, newest on top: UTC, peak SNR, duration, Doppler, drift and type (UNDERDENSE, OVERDENSE,
  AIRCRAFT).

Counts per UTC hour (underdense, overdense, seconds monitored) are kept for 400 days in `data\meteors_<VFO>.json`.

## How it works

1. The baseband of the VFO goes through a spectrum of N samples (N is a power of two near fs/8, about 4–8 Hz per bin),
   computed every N/4 samples (about 30 ms). Only ±500 Hz around the carrier is used.
2. Each frame is divided by its median over that band. A gain step (AGC+) or broadband impulse noise lifts all bins
   together and so changes nothing.
3. The power of each bin is averaged over 4 frames and compared with the noise floor of that bin. The floor is a slow
   average: 10 s while the bin is quiet and 120 s while it is up. A steady carrier is therefore learned into the floor
   and does not trigger. This covers the direct GRAVES signal on a tropo opening and birdies. The first 4 s only learn
   the floor.
4. An echo starts when the strongest bin is THR above its floor. It lasts while its own bins (±2) stay within 3 dB
   below that, and it ends after 0.3 s below. Frames where more than 30 % of the band is up at once are left out as
   broadband.
5. Each echo is classified:
   - **underdense**: shorter than 1 s;
   - **overdense**: longer than 1 s;
   - **aircraft**: longer than 20 s; or longer than 2 s with a Doppler drift over 5 Hz/s; or at the Doppler of an
     aircraft echo seen within the last 30 s. Aircraft echoes are listed but not counted.

Simulated results:

- a 0.3 s ping 20 dB above the noise in one bin is counted as one underdense echo;
- a 3 s echo is counted as overdense;
- a steady carrier, a 10 dB broadband step and 8 minutes of noise gave no echo;
- an echo drifting 30 Hz/s is classified as aircraft.

## Tips

- A 2 m Yagi pointed west at low elevation gives the most echoes; a vertical or a turnstile also works.
- Keep the gain fixed, or AGC+ on. The counter ignores the steps.
- Hourly counts from different stations or antennas cannot be compared directly. Compare the shape over the day and the
  rise during a shower.
