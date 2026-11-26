"""Meteor counter on the GRAVES space radar (143.050 MHz, continuous carrier, south of Dijon, France).

From Central Europe GRAVES is below the horizon; what is heard is its carrier reflected by the ionised trails of meteors:
short pings (underdense, < 1 s) and longer echoes (overdense, seconds), a few tens of Hz off the carrier (Doppler).

Detection on the complex baseband of the VFO (dial = 0 Hz), only around the carrier (GRAVES_HZ - dial):
  - spectrum of N samples (N = power of two near fs/8, about 4-8 Hz per bin) every N/4 samples (about 30 ms);
  - each frame is divided by its median over the band, so a gain step of the receiver / AGC+ or broadband impulse noise
    lifts all bins together and changes nothing;
  - the power of each bin is smoothed over 4 frames and compared with the floor of that bin (a slow average: a steady
    carrier, the direct GRAVES signal on a tropo opening or a birdie are learned into the floor and do not trigger);
  - an echo starts when the strongest bin is THRESHOLD_DB above its floor, lasts while it stays 3 dB lower than that,
    and ends after GAP_S below; frames where more than WIDE_FRAC of the band is up at once (broadband) are left out;
  - echoes of aircraft are long and their Doppler drifts: longer than PLANE_S, or longer than 2 s with a drift over
    PLANE_DRIFT Hz/s, or at the Doppler of an aircraft echo seen a little earlier, are aircraft and are not counted;
  - a meteor trail drifts only a few Hz/s with the wind: an echo drifting straight at SLOW_SAT_HZ_S or more for
    SLOW_SAT_S (all its points, a weak one has few over the threshold) is a satellite, and the echoes that start on its
    line within SWEEP_JOIN_S after it (it fades in and out) are its pieces; none of them is counted.
  - the bounds and the weighing of the evidence come from the physics of each target (meteor_phys.py): a drift is a
    class only when it is beyond the bound by two standard errors; an echo on a satellite's line (or on its track in the
    wide spectrum) is its piece only when its own drift and the chance of a meteor there (the station's own meteor
    rate and Doppler, learnt live) say so (Bayes factor); an aircraft is never further than AIR_DOP_MAX off the carrier.

Counts per UTC hour (underdense, overdense, seconds monitored) are kept in data/meteors_<VFO>.json for LONG_DAYS.

The detail of each echo (the ECHOES table, a click on a row): the frames of the detector at full resolution (one per
hop, ~30 ms, not smoothed) from DETAIL_PRE_S before the echo to DETAIL_POST_S after it, kept for the last DETAIL_N
echoes. An echo is reported DETAIL_POST_S after its end, when that detail is complete.

HEAD (optional, set_head): the head echo, the reflection from the meteoroid itself, sweeps fast (kHz in a fraction of a
second) just before the trail echo. A second spectrum with short frames (~15 ms, ~70 Hz bins) over ±HEAD_HZ is kept for
the HEAD_PRE_S before the echo; a chain of strong points with a steep slope in it marks the echo as with a head echo.

SAT (meteor_sat.py): a wide spectrum (±8 kHz) always runs for the echoes of satellites. A meteor echo that is part of
a satellite track is not counted (it waits for the end of the track, SAT_WAIT_S at most); the track is reported as one
echo of kind "sat" after a thread found which satellite it was (orbital elements, the bistatic Doppler).
The page can show this wide spectrum as its waterfall too (?wide=1, WFW_BINS rows).

The waterfall of the page (meteor_fine.py): the meteor band ±FINE_HZ in cells of 1 Hz x 16 ms, sharp in time and in
frequency at once (a reassigned spectrogram of two frame lengths); ±NARROW_HZ is a part of it. The page asks for one
column per screen pixel; the views up to VIEW_FINE_S get every column, the longer ones the max over FINE_COARSE_S. The
detail of a short echo gets these cells too (DETAIL_FINE_N of them). Only for the page: the detector does not use it.

AFC (optional, set_afc, on by default): the trails are at ~0 Hz (the wind moves them some tens of Hz), so the meteors
show where the carrier really is when the receiver is off (ppm). The first meteor of AFC_FIRST_DB moves the carrier of
all the detectors to its Doppler, then the median of the last meteors trims it (AFC_STEP_HZ or more). With no meteor
for AFC_DEAF_S, the carrier is looked for in the wide spectrum: AFC_WIDE_N short flashes without drift at one
frequency. The VFO is not retuned; the floor moves with the carrier by whole bins (no new learning).
"""
import collections
import base64
import json
import math
import os
import threading
import time

import numpy as np

import meteor_air
import meteor_audio
import meteor_fine
import meteor_head
import meteor_phys as mp
import meteor_size
import meteor_store
import meteor_weak
from meteor_store import log_name  # noqa: F401  (app.py: the log line of an echo)
from meteor_sat import ID_OFFSET_HZ, LINK_DF, tle_evidence, SAT_HZ, SAT_DIV, SAT_SMOOTH, SAT_THR_DB, SAT_RING_S, Spec, SatTracker, identify, tle_state
from paths import data

GRAVES_HZ = 143050000.0
GRAVES_LAT, GRAVES_LON = 47.348, 5.515    # the transmitter near Broyes-lès-Pesmes (Haute-Saône)
METEOR_KM = 100.0                       # height of the meteor trails
EARTH_KM = 6371.0
DIAL_USB_HZ = GRAVES_HZ - 1000.0        # USB dial: the carrier is heard as a 1 kHz tone
BAND_HZ = 500.0                         # watched around the carrier (meteor Doppler is mostly within ±150 Hz)
THRESHOLD_DB = 10.0                     # noise alone: the strongest of ~130 bins is ~5.5 dB, 99.9 % under 8.5 dB
HYST_DB = 3.0                           # an echo lasts while its own bins (±TRACK_BINS) stay this much under
TRACK_BINS = 2
GAP_S = 0.3                             # shorter gaps join one echo
WIDE_FRAC = 0.3
SMOOTH = 4                              # frames averaged per bin
LEARN_S = 4.0                           # the first seconds only learn the floor (a plain average)
TAU_S = 10.0                            # floor time constant (quiet bin)
TAU_HOT_S = 120.0                       # floor time constant while the bin is up (a carrier is learned in ~minutes)
FLOOR_UP_DB_S = 0.2                     # … but the floor rises at most this fast (a 30 dB echo of 10 s lifts it 2 dB;
                                        # without it a 33 dB echo lifted it ~8 dB in 0.3 s: cut short, decay too fast)
UNDER_S = 1.0                           # shorter = underdense
PLANE_S = 20.0
PLANE_DRIFT = 5.0                       # Hz/s
PLANE_MEMORY_S = 30.0
PLANE_DOPPLER_HZ = 15.0
PLANE_PRE_S = (1.5, 0.3)                # a meteor starts at once; an aircraft is there before its strong part: from
PLANE_PRE_RATIO = 2.5                   # … 1.5 to 0.3 s before the echo, its own bins (±1) this much over the floor
                                        # (the median frame; noise alone ~1.3: the frames are kept clipped at 0 dB)
PRE_RING_S = 3.0                        # the frames kept for it (power over the frame median, all bins)
PLANE_PRE_MEM = 2.0                     # the next piece of an aircraft just heard: at least this before it
PLANE_MOVE_BINS = 3                     # drifting: its Doppler moves at least this many bins (one is noise)
SWEEP_PTS = 6                           # a short echo sweeping through (a satellite): at least this many points …
SWEEP_HZ_S = 150.0                      # … moving at least this fast in both halves, the same way …
SWEEP_RMS_HZ = 12.0                     # … and straight
SLOW_SAT_HZ_S = 25.0                    # a trail drifting straight at least this fast (live: meteor trails up to ~17 Hz/s
SLOW_SAT_S = 0.6                        # … with the wind, satellites -34…-59) for at least this long is a satellite
SLOW_SAT_RMS_HZ = 25.0                  # … (straight within this)
SWEEP_JOIN_S = 10.0                     # an echo starting this soon after a satellite piece of the detector …
SWEEP_JOIN_HZ = 40.0                    # … on its line (within this + SWEEP_JOIN_HZ_S per second after it) is its
SWEEP_JOIN_HZ_S = 6.0                   # … next piece: not a meteor, not reported again
LONG_DAYS = 400
SCOPE_S = 3600                          # the chart and the waterfall keep an hour; the page asks for 30 s … 1 h
SCOPE_RATE = 4                          # points per second
VIEW_COLS = 480                         # what the page gets: at most this many points / columns (max of each bucket)
WF_HZ = BAND_HZ                         # the small waterfall: the whole watched band, one column per scope point
WF_DB = 30.0                            # its scale: 0..WF_DB dB over the floor -> 0..255
SAVE_S = 60.0
RING_S = 30.0                           # the full-resolution frames kept for the detail of the next echo
DETAIL_PRE_S = 1.0
DETAIL_POST_S = 1.0
DETAIL_MAX_S = 20.0                     # a longer echo (aircraft): only its last DETAIL_MAX_S
DETAIL_N = 200
HEAD_HZ = 5000.0                        # the head echo spectrum: ±HEAD_HZ around the carrier (less if the VFO band is narrow)
HEAD_PRE_S = 1.5                        # its window: from HEAD_PRE_S before the echo …
HEAD_POST_S = 0.5                       # … to HEAD_POST_S after its start
HEAD_SKIP_HZ = 150.0                    # the trail echo itself (near the carrier) is not a head echo
HEAD_MIN_PTS = 5
HEAD_MIN_SLOPE = 2000.0                 # Hz/s: slower is wind drift or an aircraft
HEAD_MIN_SPAN_HZ = 300.0
SAT_WAIT_S = 200.0                      # an echo waits at most this long for the end of the track it is part of
SAT_PRE_S = 2.0                         # the detail of a satellite: from this before its track to this after it
SAT_COLS = 600                          # … in at most this many columns
OFFSET_RMS_HZ = 20.0                    # a satellite fit this good measures the receiver offset …
OFFSET_N = 10                           # … the median of the last this many is used for the aircraft
TLE_OFFSET_SD_HZ = 15.0                 # … and is known within this (the orbital elements as evidence, _tle_lbf)
TLE_Q_PRIOR = 0.3                       # satellites seen without public elements (debris, classified): before any …
TLE_Q_W = 10                            # … counted as this many, then learnt from the last TLE_Q_N identifications
TLE_Q_N = 100
SAT_DETAIL_N = 30                      # (~0.6 MB each) the details of the last this many satellites are kept
SAT_AUDIO_S = 60.0                      # the sound of a satellite: at most this long (around its strongest point)
AFC_STEP_HZ = 8.0                      # AFC: a smaller correction of the carrier is not made (the floor is learned again)
AFC_FIRST_DB = 13.0                     # the first meteor at least this strong sets the carrier …
AFC_N = 12                              # … then the median Doppler of the last meteors (at least AFC_MIN of them) trims it
AFC_MIN = 5
AFC_MAX_HZ = SAT_HZ                     # the correction stays within the wide spectrum
AFC_DEAF_S = 600.0                      # no meteor this long: the carrier is looked for in the wide spectrum, where
AFC_WIDE_N = 3                          # … this many short flashes without drift …
AFC_WIDE_HZ = 40.0                      # … this close to each other …
AFC_WIDE_S = 1200.0                     # … within this time are the carrier (meteors), further off than ±BAND_HZ
AFC_FLASH_S = 1.5                       # a flash: a closed track of the wide spectrum shorter than this,
AFC_FLASH_HZ = 60.0                     # … over at most this many Hz,
AFC_FLASH_DB = 12.0                     # … and at least this strong
WFW_BINS = 1024                         # the waterfall ±SAT_HZ (satellites): at most this many columns (all ~16 Hz bins)
FINE_HZ = BAND_HZ                       # the waterfall of the meteor band (meteor_fine.py): ±FINE_HZ, 1 Hz x 16 ms
WIDE1K_HZ = 1000.0                      # … and a part of the wide one (±8 kHz) around the carrier
NARROW_HZ = 250.0                       # … and its narrower view
VIEW_FINE_S = 180                       # every column is kept this long (the views of up to 2 minutes) …
FINE_COARSE_S = 0.128                   # … and the max over this for the whole SCOPE_S (the longer ones)
WFW_DT = 0.032                          # the wide one: its frames (about) …
WFW_COARSE_S = 1.0 / SCOPE_RATE         # … and its max over this for the whole SCOPE_S
VIEW_LAG_S = 3.0                        # the page draws a little in the past (~2.3 s): this much more is sent
MAX_COLS = 4000                         # the page asks for one column per screen pixel, at most this many
DETAIL_FINE_MAX_S = 6.0                 # an echo up to this long gets the fine waterfall in its detail …
DETAIL_FINE_N = 50                      # … the newest this many of them (and the marked ones, kept with the mark) …
DETAIL_FINE_HZ = 150.0                  # … ± this around the echo (and its head echo): ~1 Hz a pixel in the detail
SAT_DETAIL_MARGIN_HZ = 400.0            # the detail of a satellite: its track ± this …
SAT_DETAIL_MIN_HZ = 1200.0              # … at least this wide
FINE_WAIT_S = 6.0                      # an echo waits at most this long for its fine cells, then is reported without
# a slow head echo in the fine cells (_head_fine): the Doppler of the meteor coming down to that of its trail just
# before it, too slow and too narrow for the head echo spectrum (HEAD_MIN_SLOPE, its ~70 Hz bins)
HEAD_FINE_DB = 10.0                     # a cell of the path at least this over its floor
HEAD_FINE_STEP_HZ = 30.0                # the next cell (16 ms on) within this (~1.9 kHz/s: its steep start)
HEAD_FINE_GAP = 3                       # cells without a point the path may jump over
HEAD_FINE_PTS = 6                       # points away from the trail's Doppler (HEAD_FINE_FLAT_HZ) at least
HEAD_FINE_FLAT_HZ = 8.0
HEAD_FINE_SLOPE = 150.0                 # Hz/s at least …
HEAD_FINE_SPAN_HZ = 40.0                # … over at least this …
HEAD_FINE_RMS_HZ = 8.0                  # … and smooth (the rms off a parabola: it slows down onto the trail) …
HEAD_FINE_NEARER = 0.8                  # … nearer to the trail from cell to cell (most of them)
HEAD_FINE_POST_S = 0.3                  # the path starts on the trail this long after the echo starts
HEAD_FINE_TRAIL_HZ = 10.0               # the trail in the fine cells: lit within this of its Doppler …
HEAD_FINE_TRAIL_N = 6                   # … in this many of the next cells (+3) …
HEAD_FINE_TRAIL_S = 1.0                 # … looked for up to this long after the detector's start
HEAD_FINE_BACK_HZ = 12.0               # the path ends where it comes this much back towards the trail
CLOCK_RESYNC_S = 3.0                    # the sample clock (_clock) this far behind the wall clock: samples were lost
CLOCK_CREEP = 0.002                     # … closer to the wall clock by this part of the time of each block
HEAD_JUMP_HZ = 150.0                   # an echo goes on in a much stronger bin this near (a head echo onto its trail) …
HEAD_JUMP_DB = 3.0                      # … this much stronger than its own bins
HEAD_TRACK_HZ = 30.0                    # a head echo from the detector's own track: its first points this far off the trail …
HEAD_TRACK_PTS = 2                      # … at least this many, each nearer to the trail than the one before
HEAD_TRACK_S = 0.4                      # … within this
# the weak detectors (meteor_weak.py, each switched on in SETTINGS › DETECTOR)
WEAK_RAW_S = (meteor_weak.TLE_WIN_S + meteor_weak.TLE_LAG_S + meteor_weak.TLE_STEP_S + 10.0)   # unsmoothed wide frames kept
WEAK_LINES_WAIT_S = meteor_weak.TLE_STEP_S + meteor_weak.TLE_LAG_S + 5.0   # a SAT·LINES track waits: SAT·TLE may name it
WEAK_WAIT_MAX_S = 60.0                  # … and at most this while a track of the tracker still going on lies on it
WEAK_RECENT_N = 60                      # the satellites reported last (from any detector): the same one is not reported again
PLANE_MAX_HZ = 350.0                    # a SAT·LINES track all within this is an aircraft (2 v / λ ≤ ~270 Hz at 143 MHz)
FAST_WAIT_S = 1.5                      # a FAST ping waits this long: an echo of the meteor detector at that time has it
FAST_NEAR_S = 0.3                       # … within this of it


def graves_path(lat, lon):
    """Where to point the antenna from (lat, lon): the azimuth of GRAVES, the distance and the elevation of the meteor
    zone (~100 km high) over the middle of the path, where most forward-scatter echoes come from."""
    p1, p2, dl = math.radians(lat), math.radians(GRAVES_LAT), math.radians(GRAVES_LON - lon)
    az = math.degrees(math.atan2(math.sin(dl) * math.cos(p2),
                                 math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl))) % 360
    c = math.acos(max(-1.0, min(1.0, math.sin(p1) * math.sin(p2) + math.cos(p1) * math.cos(p2) * math.cos(dl))))
    km = EARTH_KM * c
    half = c / 2                        # elevation of a point METEOR_KM high over the middle of the path
    el = math.degrees(math.atan2(math.cos(half) - EARTH_KM / (EARTH_KM + METEOR_KM), math.sin(half)))
    return {"az": round(az, 1), "km": round(km), "el": round(max(0.0, el), 1)}


def hour_key(t):
    return time.strftime("%Y-%m-%dT%H", time.gmtime(t))


class MeteorCounter:
    def __init__(self, tag="", on_echo=None, path=None):
        self.tag = tag
        self.marks = None               # meteor_store.Marks (register)
        self.on_echo = on_echo
        self.path = path or data(f"meteors_{tag or 'main'}.json")
        self.enabled = False
        self.error = ""
        self.threshold_db = THRESHOLD_DB
        self.lock = threading.Lock()
        self.events = collections.deque(maxlen=500)
        self.hours = {}                 # "YYYY-MM-DDTHH" (UTC) -> [underdense, overdense, seconds monitored]
        self.scope = collections.deque(maxlen=SCOPE_S * SCOPE_RATE)    # (t, max SNR dB)
        self.wf_hz = []                 # Doppler of the detector's bins as in a detail (Hz, low -> high)
        self.status = ""
        self.planes = 0
        self._dirty = False
        self._saved = 0.0
        self._fs = None
        self._dial = None
        self.head = False               # the head echo spectrum (set_head)
        self.head_hz = 0.0              # its band as set up (± Hz), 0 = off or does not fit
        self._hs = None                 # its state (_head_setup)
        self.details = collections.OrderedDict()    # ts of an echo -> its detail (_cut)
        self._pending = []              # closed echoes waiting for DETAIL_POST_S of frames
        self._ring = collections.deque()            # (t, uint8 bytes): full-resolution frames, RING_S
        self._ws = None                 # the wide spectrum (meteor_sat.Spec) and its tracks (SatTracker)
        self._trk = SatTracker()
        self.sat_hz = 0.0               # its band as set up (± Hz), 0 = does not fit
        self.sats = 0                   # satellite echoes since the start (not counted as meteors)
        self.station = None             # () -> (lat, lon) or None: for which satellite / aircraft it was (register)
        self.air = True                 # aircraft echoes looked up on adsb.fi (set_air)
        self.rx_offsets = []            # [[t, Hz]]: the receiver offset measured on satellites (rx_offset)
        # the waterfalls of the page (meteor_fine.Tiered: every column for the short views, the max for the long ones)
        self.wfw = meteor_fine.Tiered(WFW_DT, VIEW_FINE_S, WFW_COARSE_S, SCOPE_S)     # the wide one ±SAT_HZ
        self.wff = meteor_fine.Tiered(meteor_fine.CELL_S, VIEW_FINE_S, FINE_COARSE_S, SCOPE_S)  # the meteor band
        self._fn = None                 # its spectrum (meteor_fine.Fine)
        self._fine_wait = []            # [ts, t_start, t_end]: details waiting for their fine cells
        self._deferred = {}             # ts -> (ev, e): echoes reported when their fine cells are there
        self.afc = True                 # AFC: the carrier found from the meteors (set_afc)
        self.afc_hz = 0.0               # how far the carrier is from where the dial says (the receiver's error)
        self.afc_locked = False         # a meteor confirmed it since the start
        self._afc_dops = collections.deque(maxlen=AFC_N)
        self._afc_flash = collections.deque(maxlen=200)                # (t, Hz) flashes in the wide spectrum
        self._afc_met = None            # the time of the last meteor (or of the start)
        self._resetup = False           # the carrier moved: set up again with the next block
        self.sat_tle = False            # SAT·TLE: weak satellites along their predicted Doppler (set_weak)
        self.sat_lines = False          # SAT·LINES: weak straight streaks (set_weak)
        self.fast = False               # FAST: short pings in the time signal (set_weak)
        self.fasts = 0                  # FAST pings counted since the start
        self._weak = None               # meteor_weak.WeakWorker (started with the first frames when one is on)
        self._weak_wait = []            # [t_in, item, pts]: what it found, waiting for the tracker (_weak_step)
        self._sat_recent = collections.deque(maxlen=WEAK_RECENT_N)    # {"pts"}: the satellites reported last
        self._plane_recent = collections.deque(maxlen=WEAK_RECENT_N)  # … and the aircraft of the meteor detector
        self._prior = mp.DopplerPrior()  # the station's own meteors: their rate and Doppler (meteor_phys.py)
        self._size = meteor_size.SizeEstimator()     # the estimated size of each meteoroid (meteor_size.py)
        self._sat_known = collections.deque(maxlen=TLE_Q_N)    # satellites seen: identified from TLE or not
        self._fast = None               # meteor_weak.Fast
        self._fast_wait = []            # its pings waiting for the meteor detector (_fast_step)
        self._recent_ev = collections.deque(maxlen=100)               # (t0, t1) of the last echoes of the detector
        self._recent_det = collections.deque(maxlen=100)              # (t0, t1, Doppler) of them
        self._load()

    # ----- settings -----
    def set_enabled(self, on):
        on = bool(on)
        if on and not self.enabled:
            self._fs = None             # a new start: learn the floor again
        if not on and self.enabled:
            self._close_event()
            self._flush()
            self.save()
        self.enabled = on

    def set_threshold(self, db):
        self.threshold_db = min(30.0, max(3.0, float(db)))

    def set_head(self, on):
        self.head = bool(on)
        self._hs = None                 # set up again (on) or dropped (off) with the next block
        self.head_hz = 0.0

    def set_afc(self, on):
        on = bool(on)
        if on != self.afc:
            self.afc = on
            self.afc_locked = False
            self._afc_dops.clear()
            self._afc_flash.clear()
            with self.lock:
                self.rx_offsets = []    # measured against the other carrier
            self._resetup = True
            self._dirty = True

    def set_weak(self, sat_tle=None, sat_lines=None, fast=None):
        """The weak detectors on / off (meteor_weak.py); None leaves one as it is."""
        if sat_tle is not None:
            self.sat_tle = bool(sat_tle)
        if sat_lines is not None:
            self.sat_lines = bool(sat_lines)
        if fast is not None:
            self.fast = bool(fast)
            if not self.fast:
                self._fast, self._fast_wait = None, []
        ws = self._ws
        if ws is not None:              # the unsmoothed frames are kept only while a satellite search needs them
            if (self.sat_tle or self.sat_lines) and ws.raw is None:
                ws.raw = collections.deque(maxlen=int(WEAK_RAW_S / ws.dt) + 1)
            elif not (self.sat_tle or self.sat_lines):
                ws.raw = None
        if not (self.sat_tle or self.sat_lines):
            self._weak_wait = []
        self._dirty = True

    # ----- AFC: where the carrier really is (the meteor trails are at ~0 Hz, the wind moves them a few tens of Hz) -----
    def _afc_move(self, d):
        new = max(-AFC_MAX_HZ, min(AFC_MAX_HZ, self.afc_hz + d))
        if abs(new - self.afc_hz) < AFC_STEP_HZ:
            return
        self.afc_hz = round(new, 1)
        self._afc_dops.clear()
        self._afc_flash.clear()
        with self.lock:
            self.rx_offsets = []        # measured against the old carrier
        self._resetup = True
        self._dirty = True

    def _afc_meteor(self, e, t, afc_then):
        """A meteor echo was counted: its Doppler trims the carrier (only one measured against the carrier as it is now)."""
        self._afc_met = t
        if not self.afc or afc_then != self.afc_hz:
            return
        if not self.afc_locked:
            if e["snr"] >= AFC_FIRST_DB:
                self.afc_locked = True
                self._afc_move(e["doppler"])
            return
        self._afc_dops.append(e["doppler"])
        if len(self._afc_dops) >= AFC_MIN:
            m = float(np.median(self._afc_dops))
            if abs(m) >= AFC_STEP_HZ:
                self._afc_move(m)

    def _afc_wide(self, tr, now):
        """A closed track of the wide spectrum: when no meteor is heard, short flashes far off the carrier find it."""
        if not self.afc or self._afc_met is None or now - self._afc_met < AFC_DEAF_S:
            return
        pts = tr["pts"]
        if len(pts) < 2 or tr["t1"] - tr["t0"] > AFC_FLASH_S or max(p[2] for p in pts) < AFC_FLASH_DB:
            return
        ff = [p[1] for p in pts]
        if max(ff) - min(ff) > AFC_FLASH_HZ:
            return
        f = float(np.median(ff))
        if abs(f) < BAND_HZ * 0.8:      # the meteor detector sees there itself
            return
        fl = self._afc_flash
        fl.append((tr["t0"], f))
        while fl and fl[0][0] < now - AFC_WIDE_S:
            fl.popleft()
        best = []
        for _, a in fl:
            near = [b for _, b in fl if abs(a - b) <= AFC_WIDE_HZ]
            if len(near) > len(best):
                best = near
        if len(best) >= AFC_WIDE_N:
            self.afc_locked = False     # the first meteor there trims it
            self._afc_move(float(np.median(best)))
            self._afc_met = now

    # ----- signal -----
    def _setup(self, fs, dial_hz, keep=False):
        """keep: only the AFC moved the carrier: the waterfalls are kept (their bins are within a few Hz of before)."""
        self._fs = fs
        self._dial = dial_hz
        self.n = 1 << int(round(math.log2(max(256.0, fs / 8.0))))
        self.hop = self.n // 4
        self.win = np.hanning(self.n).astype(np.float32)
        self._buf = np.zeros(0, np.complex64)
        old = (self.floor, self.f_off, self.t_learn) if keep and getattr(self, "floor", None) is not None else None
        self.f_off = GRAVES_HZ - dial_hz + (self.afc_hz if self.afc else 0.0)
        self._resetup = False
        self._afc_met = None            # the time of the first block (_feed)
        bw = fs / self.n                # the same number of bins wherever the carrier is (the AFC keeps the waterfall)
        ks = np.arange(-int(BAND_HZ // bw), int(BAND_HZ // bw) + 1) + int(round(self.f_off / bw))
        self.idx = ks % self.n
        self.bin_hz = ks * bw - self.f_off              # Doppler of each watched bin
        self.dt = self.hop / fs
        self._floor_up = 10 ** (FLOOR_UP_DB_S * self.dt / 10)
        self._hist = collections.deque(maxlen=SMOOTH)
        self.floor = None
        self.t_learn = 0.0
        if old is not None and len(old[0]) == len(self.idx):
            # the AFC moved the carrier: the floor moves with it by whole bins (its edges as they were), not learned again
            sh = int(round((self.f_off - old[1]) / (fs / self.n)))
            f = np.roll(old[0], -sh)
            if sh > 0:
                f[-sh:] = old[0][-1]
            elif sh < 0:
                f[:-sh] = old[0][0]
            self.floor, self.t_learn = f, old[2]
        self._ev = None
        self._last_hot = None
        self._sweep_last = None         # (t, Hz, Hz/s) the end of the last satellite piece of the detector (_on_sweep)
        self._scope_t = 0.0
        self._scope_max = -99.0
        self.wf_sel = np.arange(len(self.idx))          # WF_HZ = BAND_HZ: all of them, always as many
        self._ring = collections.deque(maxlen=int(RING_S / self.dt) + 1)
        self._pre_ring = collections.deque(maxlen=int(PRE_RING_S / self.dt) + 1)
        if keep and getattr(self, "_aud", None) is not None and self._aud.fs_in == fs:
            self._aud.f_off = self.f_off         # the AFC moved the carrier: the sound goes on
        else:
            self._aud = meteor_audio.Ring(fs, self.f_off)
        self._hs = None
        self._ws = None
        self._trk = SatTracker()
        self._wfw_keep = keep
        if keep and getattr(self, "_fn", None) is not None and self._fn.scales[0].fs == fs:
            self._fn.retune(self.f_off)  # the AFC moved the carrier: the fine spectrum follows it
        else:
            if getattr(self, "_fn", None) is not None:
                self._fine_flush()      # the echoes waiting for it are reported with what there is
            self._fn = None             # made again around the new carrier (it learns ~5 s)
            with self.lock:
                self.wff.clear()
        self.wf_hz = [round(float(h), 1) for h in self.bin_hz[self.wf_sel]]
        if abs(self.f_off) + BAND_HZ > fs / 2 * 0.9:
            self.status = f"GRAVES {GRAVES_HZ / 1e6:.3f} MHz is outside the band of this VFO: tune to {DIAL_USB_HZ / 1e6:.3f} USB"
            self.idx = self.idx[:0]
        else:
            self.status = "learning the noise floor…"

    def feed(self, base, fs, dial_hz, now=None):
        """base: complex baseband (dial = 0 Hz) at fs; now: the time of the end of the block (tests)."""
        if not self.enabled:
            return
        try:
            self._feed(base, fs, dial_hz, self._clock(len(base), fs, time.time() if now is None else now))
        except Exception as e:          # never take the receiver down
            self.error = f"meteor: {e}"

    def _clock(self, n, fs, now):
        """The time of the end of this block from the samples counted, the wall clock only anchoring it. The blocks come
        late by a varying lag (the decoders before this one, a busy CPU) and then quickly one after another: stamped
        with the wall clock each, the frames of different lengths (64 ms, 128 ms, 1 s) and the sound would get times
        that disagree by that lag (a detail 0.5 s off its echo). Never ahead of the wall clock; follows a slower
        sample clock by CLOCK_CREEP of the time; a dropout of samples (CLOCK_RESYNC_S) starts it again."""
        c = getattr(self, "_clk", None)
        t = None if c is None or fs != getattr(self, "_clk_fs", None) else c + n / fs
        if t is None or now - t > CLOCK_RESYNC_S or t > now:
            t = now
        else:
            t += min(now - t, CLOCK_CREEP * n / fs)
        self._clk, self._clk_fs = t, fs
        return t

    def _feed(self, base, fs, dial_hz, now):
        if fs != self._fs or dial_hz != self._dial or self._resetup:
            keep = fs == self._fs and dial_hz == self._dial     # only the AFC moved: the waterfalls go on
            self._close_event()
            self._flush()
            self._setup(fs, dial_hz, keep)
        if self._afc_met is None:
            self._afc_met = now
        self._prior.start(now)
        if not len(self.idx):
            return
        base = np.asarray(base, np.complex64)
        # first the wide spectrum and the head echo spectrum: their frames up to now are there when an echo is cut
        self._aud.feed(base, now)       # the sound of the echoes (meteor_audio.py)
        self._wide_feed(base, now)
        self._fine_feed(base, now)
        if self.fast:
            self._fast_feed(base, now)
        if self.head:
            self._head_feed(base, now)
        else:
            self._hs = None
        buf = np.concatenate((self._buf, base))
        nfr = (len(buf) - self.n) // self.hop + 1 if len(buf) >= self.n else 0
        for i in range(nfr):
            seg = buf[i * self.hop:i * self.hop + self.n]
            t = now - (len(buf) - i * self.hop - self.n) / fs        # the end of this frame
            self._frame(np.abs(np.fft.fft(seg * self.win)[self.idx]) ** 2, t)
        self._buf = buf[nfr * self.hop:]
        self._count_time(len(base) / fs, now)

    def _frame(self, p, t):
        med = float(np.median(p))
        if med <= 0:
            return
        self._hist.append(p / med)
        s = np.mean(self._hist, axis=0)
        if self.floor is None:
            self.floor = s.copy()
        self.t_learn += self.dt
        learning = self.t_learn < LEARN_S
        ratio = s / np.maximum(self.floor, 1e-12)
        thr = 10 ** (self.threshold_db / 10)
        hot = ratio >= thr
        tau = self.t_learn if learning else np.where(hot, TAU_HOT_S, TAU_S)
        inst = (p / med)[self.wf_sel] / np.maximum(self.floor[self.wf_sel], 1e-12)     # this frame alone: the detail
        self._ring.append((t, self._db8(inst)))
        self._pre_ring.append((t, (p / med).astype(np.float16)))       # the power over the frame median (_pre_level)
        while self._pending and t >= self._pending[0][0]["t1"] + DETAIL_POST_S:
            ev = self._pending[0][0]
            if "link" not in ev:        # once: the track has all its points up to now
                ev["link"] = self._trk.link(ev["track"]) if self._ws else None
            tr = ev["link"]
            if tr is not None and self._trk.is_open(tr) and t < ev["t1"] + SAT_WAIT_S:
                break                   # part of a track still going on: a satellite or not is told when it ends
            self._finish(*self._pending.pop(0), tr)
        new = self.floor + (s - self.floor) * (self.dt / tau)
        if not learning:                # a strong echo must not lift its own floor (it would end early, its decay
            # would look faster): under an echo the floor rises at most FLOOR_UP_DB_S (a steady carrier is still
            # learned in minutes); not in the noise, its ups and downs would bias the floor low (false pings)
            new = np.where(hot, np.minimum(new, self.floor * self._floor_up), new)
        self.floor = new
        if learning:
            return
        if self.status.startswith("learning"):
            self.status = "listening"
        k = int(np.argmax(ratio))
        snr = 10 * math.log10(max(ratio[k], 1e-6))
        wide = np.count_nonzero(ratio >= thr / 2) > WIDE_FRAC * len(ratio)
        self._scope(t, -99.0 if wide else snr)
        if wide:
            return
        ev = self._ev
        if ev is None:
            if snr >= self.threshold_db:
                self._ev = {"t0": t, "t1": t, "peak": snr, "dop": float(self.bin_hz[k]), "k": k, "track": [(t, float(self.bin_hz[k]))],
                            "trace": [(t, float(self.bin_hz[k]), snr)], "afc": self.afc_hz}
            return
        a = max(0, ev["k"] - TRACK_BINS)
        j = a + int(np.argmax(ratio[a:ev["k"] + TRACK_BINS + 1]))        # the echo's own bins (its Doppler moves)
        snr_j = 10 * math.log10(max(ratio[j], 1e-6))
        if (snr >= self.threshold_db and snr >= snr_j + HEAD_JUMP_DB
                and abs(float(self.bin_hz[k] - self.bin_hz[ev["k"]])) <= HEAD_JUMP_HZ):
            j, snr_j = k, snr            # a head echo coming onto its trail (much stronger, near): the echo goes on there
        if snr_j >= self.threshold_db - HYST_DB:
            ev["t1"] = t
            ev["k"] = j
            ev["trace"].append((t, float(self.bin_hz[j]), snr_j))     # all its points (a weak one: its drift)
            if snr_j >= self.threshold_db:
                ev["track"].append((t, float(self.bin_hz[j])))
            if snr_j > ev["peak"]:
                ev["peak"], ev["dop"] = snr_j, float(self.bin_hz[j])
        elif t - ev["t1"] > GAP_S:
            self._close_event()

    def _scope(self, t, snr):
        self._scope_max = max(self._scope_max, snr)
        if t - self._scope_t >= 1.0 / SCOPE_RATE:
            with self.lock:
                self.scope.append((round(t, 2), round(max(self._scope_max, -20.0), 1)))
            self._scope_t = t
            self._scope_max = -99.0

    def _close_event(self):
        ev, self._ev = getattr(self, "_ev", None), None
        if ev is None:
            return
        dur = ev["t1"] - ev["t0"] + self.dt
        tr = ev["track"]
        trace = ev.get("trace") or [(p[0], p[1], ev["peak"]) for p in tr]
        bw = abs(float(self.bin_hz[1] - self.bin_hz[0])) if len(self.bin_hz) > 1 else 8.0
        # the drift of the trail itself (without a head echo coming onto it at the start); a weak echo has too few
        # points over the threshold: then all its points
        corr = (self.n // self.hop + SMOOTH - 1) * self.dt      # the detector's correlation time (frame + smoothing)
        fit = self._drift(tr, ev["dop"], bw, corr) or self._drift(trace, ev["dop"], bw, corr)
        drift, rms, half, se = fit if fit else (0.0, 0.0, 0.0, 0.0)
        ev["fit"] = fit
        pre = self._pre_level(ev)       # an aircraft is there (weak) before its strong part, a meteor starts at once
        sweep = self._sweep(tr)
        # faster than any trail in the wind or aircraft can drift, by two standard errors (meteor_phys.SAT_RATE_MIN)
        slow = (fit is not None and dur >= SLOW_SAT_S and abs(drift) >= SLOW_SAT_HZ_S and rms <= SLOW_SAT_RMS_HZ
                and half >= SLOW_SAT_HZ_S / 2 and abs(drift) * dur >= PLANE_MOVE_BINS * bw
                and mp.faster_than(drift, se, mp.SAT_RATE_MIN))
        # a head echo onto it (kHz/s, ending on the trail's Doppler): only a meteoroid does that, no satellite (<= ~100
        # Hz/s) or aircraft (meteor_phys.py): a meteor, whatever its line or track says
        head = self._head_now(ev)
        if head:
            ev["head_now"] = head
            kind = "under" if dur < UNDER_S else "over"
        elif dur > PLANE_S and not slow:
            kind = "plane"
        elif self._on_sweep(trace, fit, bw, corr, ev["dop"]):
            kind = "sat"                # the next piece of a satellite the detector just had: not a meteor
            ev["sat_piece"] = True
        elif slow:
            kind = "sat"                # drifting straight much faster than a trail in the wind: a satellite
            if self._ws is not None:
                ev["sweep"] = drift
            else:
                ev["sat_piece"] = True
        elif (dur > 2.0 and abs(drift) > PLANE_DRIFT and abs(drift) * dur >= PLANE_MOVE_BINS * bw
              and mp.faster_than(drift, se, PLANE_DRIFT) and abs(ev["dop"]) <= mp.AIR_DOP_MAX + 2 * bw):
            kind = "plane"              # drifting by more than a bin or two, surely (a jump of one bin is not drift),
                                        # and within the Doppler an aircraft can have
        elif (self._last_hot and ev["t0"] - self._last_hot[0] < PLANE_MEMORY_S and pre >= PLANE_PRE_MEM
              and abs(ev["dop"] - self._last_hot[1]) < PLANE_DOPPLER_HZ + PLANE_DRIFT * (ev["t0"] - self._last_hot[0])):
            kind = "plane"              # the next piece of the aircraft just heard (still there between the pieces)
        elif pre >= PLANE_PRE_RATIO:
            kind = "plane"              # already there before: an aircraft (at the middle of the path: ~0 Hz, no drift)
        elif sweep and self._ws is not None:
            kind = "sat"                # sweeping through the band all along: a satellite (_finish: unless the tracker has it)
            ev["sweep"] = sweep
        else:
            kind = "under" if dur < UNDER_S else "over"
        if kind == "sat":               # where its line goes on (the next piece after a fade)
            s = self._sweep_last
            slope = drift if fit is not None and abs(drift) >= SLOW_SAT_HZ_S / 2 else (s[2] if s else ev.get("sweep", 0.0))
            if slope:
                self._sweep_last = (trace[-1][0], trace[-1][1], slope)
        if kind == "plane":
            self._last_hot = (ev["t1"], ev["dop"])
            self._plane_recent.append({"pts": sorted(tuple(p) for p in tr)})     # SAT·LINES does not report it again
        e = {"ts": round(ev["t0"], 2), "time": time.strftime("%H:%M:%S", time.gmtime(ev["t0"])), "dur": round(dur, 2),
             "snr": round(ev["peak"], 1), "doppler": round(ev["dop"]), "drift": round(drift, 1), "kind": kind,
             "freq_hz": round(GRAVES_HZ + ev["dop"]), "det": False, "head": None}
        dec = mp.decay(trace)           # the exponential decay of the trail (meteor_phys.decay): tau, how straight in dB
        if dec:
            e["tau"], e["tau_r2"] = round(dec[0], 3), round(dec[1], 2)
            if kind == "under":
                self._size.add_tau(*dec)
        est = self._size.estimate(kind, ev["peak"], dur, self.threshold_db)      # meteor_size.py: an estimate only
        if est:
            e["est"] = est
        self._recent_ev.append((ev["t0"], ev["t1"]))                   # a FAST ping at that time is this echo
        self._recent_det.append((ev["t0"], ev["t1"], ev["dop"]))       # … and a SAT·LINES aircraft there too
        self._pending.append((ev, e))   # reported when its detail is complete (DETAIL_POST_S later)

    def _pre_level(self, ev):
        """The power ratio over the floor of the echo's first bin (±1) from PLANE_PRE_S[0] to PLANE_PRE_S[1] s before
        it (the full-resolution frames): the median of the frames (an aircraft is there all the time, a meteor just
        before is not); 0 if there are too few frames or another echo of the detector was there then."""
        a, b = ev["t0"] - PLANE_PRE_S[0], ev["t0"] - PLANE_PRE_S[1]
        f = ev["track"][0][1]
        if any(t0 <= b and t1 >= a - 0.3 and abs(d - f) <= 3 * PLANE_DOPPLER_HZ for t0, t1, d in self._recent_det):
            return 0.0                  # a meteor just before at that Doppler, not an aircraft
        k = int(np.argmin(np.abs(self.bin_hz - f)))
        rows = [c for t, c in self._pre_ring if a <= t <= b]
        if len(rows) < 5:
            return 0.0
        # the power over the median of each frame, not over the floor (a slow aircraft lifts its own floor within
        # seconds, one gone leaves it lifted for a while): noise ~1.35, an aircraft much more
        arr = np.stack(rows).astype(np.float32)
        return float(np.median(np.mean(arr[:, max(0, k - 1):k + 2], axis=1)))

    @staticmethod
    def _drift(pts, dop, bw, corr):
        """The straight fit (Theil-Sen, meteor_phys.slope: robust to odd points) of the trail from the first point near
        its peak Doppler on: (Hz/s, rms Hz around it, the slower of its two halves in Hz/s, 0 if they go opposite ways,
        the standard error of the Hz/s), None if too short (fewer than 4 points or 0.5 s). A meteor fading out wanders
        over the noise at its end: its first half stays flat."""
        i0 = next((i for i, p in enumerate(pts) if abs(p[1] - dop) <= 2.5 * bw), 0)
        trl = pts[i0:]
        if len(trl) < 4 or trl[-1][0] - trl[0][0] <= 0.5:
            return None
        r = mp.slope(trl, corr, bw)
        if r is None:
            return None
        s, se, _, rms = r
        h = len(trl) // 2
        half = 0.0
        a, b = (mp.slope(trl[:h], corr, bw), mp.slope(trl[h:], corr, bw)) if h >= 3 and len(trl) - h >= 3 else (None, None)
        if a and b:
            half = min(abs(a[0]), abs(b[0])) if a[0] * s > 0 and b[0] * s > 0 else 0.0
        return s, rms, half, se

    @staticmethod
    def _trail(pts, dop, bw):
        """The points of the trail itself: from the first one near its peak Doppler on (a head echo coming onto it at
        the start is not its drift; as _drift)."""
        i0 = next((i for i, p in enumerate(pts) if abs(p[1] - dop) <= 2.5 * bw), 0)
        return pts[i0:]

    def _head_now(self, ev):
        """The head echo of the echo just closed: from the detector's own track (_head_track) or, with HEAD on, from
        the head echo spectrum before it (_head_find, as the detail does later; a faint one too weak for its points:
        meteor_head.weak, the power along the lines ending at the trail) -> head dict or None."""
        h = self._head_track(ev)
        hs = self._hs
        if h is None and self.head and hs and hs.ring:
            a, b = ev["t0"] - HEAD_PRE_S, ev["t0"] + HEAD_POST_S
            hrows = [(t, c) for t, c in hs.ring if a <= t <= b and len(c) == len(hs.hz)]
            if hrows:
                h = self._head_find(hrows, hs, ev["t0"], ev["dop"])
            if h is None and hs.raw:
                raw = [(t, r) for t, r in hs.raw if a <= t <= b]
                h = meteor_head.weak(raw, hs.hz, hs.dt, hs.bin, ev["t0"], ev["dop"], HEAD_SKIP_HZ)
        return h

    def _on_sweep(self, trace, fit, bw, corr, dop):
        """Is the echo the next piece of the satellite piece just before? It must start on its line (SWEEP_JOIN_*);
        then the evidence is weighed (meteor_phys.py, log Bayes factors added up): its own drift, like the line's or like
        a trail's in the wind (measured, or roughly from its few points when it is short), and the chance that one of
        the station's meteors falls there by accident (their rate and Doppler, learnt live)."""
        s = self._sweep_last
        if not s:
            return False
        t, f = trace[0][0], trace[0][1]
        dt = t - s[0]
        if not -0.5 <= dt <= SWEEP_JOIN_S:
            return False
        win = SWEEP_JOIN_HZ + SWEEP_JOIN_HZ_S * abs(dt)
        if abs(f - (s[1] + s[2] * dt)) > win:
            return False
        if fit is not None:
            sl, se = fit[0], fit[3]
        else:
            r = mp.slope(self._trail(trace, dop, bw), corr, bw)
            sl, se = (r[0], r[1]) if r else (None, None)
        lbf = -self._prior.chance_log_bf(f, t, 2 * win, bw)            # > 0: rather the satellite
        if sl is not None:
            if fit is not None and sl * s[2] <= 0:
                return False            # measured drifting the other way
            lbf += mp.same_line(sl, se, s[2])
        lbf += self._tle_lbf(trace, bw)
        return lbf > 0

    def _q_unknown(self):
        """The part of the satellites seen that have no public elements (debris, classified): learnt from the
        identifications (TLE_Q_PRIOR counted as TLE_Q_W of them before)."""
        k = list(self._sat_known)
        return (TLE_Q_PRIOR * TLE_Q_W + k.count(False)) / (TLE_Q_W + len(k))

    def _tle_lbf(self, pts, bw):
        """The orbital elements as evidence (meteor_sat.tle_evidence): log Bayes factor > 0 for a satellite, 0 without
        the station location or the elements. The receiver offset is known within ~15 Hz after a sure
        identification, else only within ID_OFFSET_HZ (weak evidence then)."""
        try:
            qth = self.station() if self.station else None
            with self.lock:
                offs = [o for _, o in self.rx_offsets]
            off, sd = (float(np.median(offs)), TLE_OFFSET_SD_HZ) if offs else (0.0, ID_OFFSET_HZ / 2)
            return tle_evidence([(p[0], p[1]) for p in pts], qth, (GRAVES_LAT, GRAVES_LON), GRAVES_HZ, off, sd,
                                self._q_unknown(), bw)[0]
        except Exception as x:          # no evidence then, the echo is judged without it
            self.error = f"meteor TLE: {x}"
            return 0.0

    def _judge_track(self, tr):
        """A closed track of the wide spectrum in pieces: a satellite by the drift of its pieces (meteor_sat._stitched)
        and the orbital elements together (log Bayes factors added). -> is it a satellite."""
        if tr.get("shape") and tr.get("stitch_lbf") is not None and not tr.get("head") and not tr.get("dup"):
            tr["sat"] = tr["stitch_lbf"] + self._tle_lbf(tr["pts"], self._ws.bin if self._ws else 16.0) >= 0
            tr["stitched"] = not tr["sat"]
        return tr["sat"]

    def _part_of(self, ev, tr):
        """Is the echo linked to the satellite track tr (its points lie on it) a piece of it, or a meteor that came
        just where the satellite was? The log Bayes factors of its own drift against the track's there and of the
        chance of a meteor at that Doppler (meteor_phys.py): a trail does not drift with the satellite."""
        bw = abs(float(self.bin_hz[1] - self.bin_hz[0])) if len(self.bin_hz) > 1 else 8.0
        corr = (self.n // self.hop + SMOOTH - 1) * self.dt
        fit = ev.get("fit")
        trace = ev.get("trace") or ev["track"]
        if fit is not None:
            sl, se = fit[0], fit[3]
        else:
            r = mp.slope(self._trail(trace, ev["dop"], bw), corr, bw)
            sl, se = (r[0], r[1]) if r else (None, None)
        near =[p for p in tr["pts"] if ev["t0"] - 1.0 <= p[0] <= ev["t1"] + 1.0]
        r = mp.slope(near, corr, bw) if len(near) >= 3 else None
        s_tr = r[0] if r else tr.get("slope", 0.0)
        lbf = -self._prior.chance_log_bf(ev["dop"], ev["t0"], 2 * LINK_DF, bw)
        if sl is not None:
            lbf += mp.same_line(sl, se, s_tr)
        lbf += self._tle_lbf(trace, bw)
        return lbf > 0

    @staticmethod
    def _sweep(tr):
        """A short echo sweeping through the band all along (its Doppler moving the same way at SWEEP_HZ_S at least in
        both halves, straight): a satellite -> its Hz/s, else 0. A head echo comes to the trail's Doppler and stays."""
        if len(tr) < SWEEP_PTS or tr[-1][0] - tr[0][0] < 0.15:
            return 0.0
        tt = np.array([p[0] for p in tr]) - tr[0][0]
        ff = np.array([p[1] for p in tr])
        h = len(tr) // 2
        if tt[h - 1] <= 0 or tt[-1] <= tt[h]:
            return 0.0
        s1 = float(np.polyfit(tt[:h], ff[:h], 1)[0])
        s2 = float(np.polyfit(tt[h:], ff[h:], 1)[0])
        c = np.polyfit(tt, ff, 1)
        rms = float(np.sqrt(np.mean((ff - np.polyval(c, tt)) ** 2)))
        if min(abs(s1), abs(s2)) >= SWEEP_HZ_S and s1 * s2 > 0 and rms <= SWEEP_RMS_HZ:
            return float(c[0])
        return 0.0

    def _flush(self):
        """Reports the waiting echoes with the frames there are (stop, retune); the open tracks end."""
        if self._ws:
            for tr in self._trk.close_all(self._ws.bin):
                if self._judge_track(tr):
                    self._sat_found(tr)
        while self._pending:
            ev = self._pending[0][0]
            tr = ev["link"] if "link" in ev else (self._trk.link(ev["track"]) if self._ws else None)
            self._finish(*self._pending.pop(0), tr)
        self._fine_flush()

    def _finish(self, ev, e, tr=None):
        """An echo is complete: counted, or left out as a piece of a satellite track (that track is reported). A short
        one waits for its fine cells (~1.5 s): its detail and a slow head echo in them (_fine_cut), then reported."""
        if tr is not None and tr.get("sat") and not ev.get("head_now") and self._part_of(ev, tr):
            tr["pieces"] = tr.get("pieces", 0) + 1
            return
        if ev.get("sat_piece"):         # the next piece of the satellite just reported: not a meteor, not again
            return
        if ev.get("sweep"):             # a satellite the tracker did not report: reported as one (identified)
            tp = ev.get("trace") if len(ev.get("trace") or []) > len(ev["track"]) else None
            pts = [(p[0], p[1], p[2]) for p in tp] if tp else [(p[0], p[1], ev["peak"]) for p in ev["track"]]
            if self._ws is not None and not any(self._on_track(s, pts) for s in self._sat_recent):
                self._sat_found({"pts": pts, "t0": pts[0][0], "t1": pts[-1][0], "slope": ev["sweep"]}, "sweep")
            return
        try:
            if self._cut(ev, e):
                self._deferred[e["ts"]] = (ev, e)
                return
        except Exception as x:          # the echo is counted even if its detail fails
            self.error = f"meteor detail: {x}"
        self._publish(ev, e)

    def _publish(self, ev, e):
        if e["kind"] == "plane" and self.station and self.air:
            with self.lock:
                self.planes += 1
            e["air"] = None             # which aircraft: asked from adsb.fi in a thread, reported then
            threading.Thread(target=self._air_publish, args=(e, [(p[0], p[1]) for p in ev["track"]]), daemon=True,
                             name="meteor-air").start()
            return
        with self.lock:
            self.events.append(e)
            if e["kind"] == "plane":
                self.planes += 1
            else:
                h = self.hours.setdefault(hour_key(ev["t0"]), [0, 0, 0.0])
                h[0 if e["kind"] == "under" else 1] += 1
                self._dirty = True
                if e.get("fast"):
                    self.fasts += 1
        if e["kind"] != "plane" and not e.get("fast"):     # a FAST ping does not move the carrier
            self._afc_meteor(e, ev["t1"], ev.get("afc", self.afc_hz))
            self._prior.add(ev["t0"], ev["dop"])
        if self.on_echo:
            self.on_echo(e)

    @staticmethod
    def _db8(ratio):
        """Power ratios -> uint8 bytes, 0..WF_DB dB over the floor."""
        db = 10 * np.log10(np.maximum(ratio, 1.0))
        return np.clip(db * (255.0 / WF_DB), 0, 255).astype(np.uint8).tobytes()

    # ----- the detail of an echo -----
    def _cut(self, ev, e):
        """Keeps the full-resolution frames around the echo (and the head echo spectrum before it)."""
        t_end = ev["t1"] + DETAIL_POST_S
        t_start = max(ev["t0"] - DETAIL_PRE_S, t_end - DETAIL_MAX_S)
        rows = [(t, c) for t, c in self._ring if t_start <= t <= t_end]
        if not rows:
            return
        n = len(rows[-1][1])
        rows = [(t, c) for t, c in rows if len(c) == n]
        det = {"ts": e["ts"], "t0": rows[0][0], "dt": self.dt, "hz": [round(float(h), 1) for h in self.bin_hz[self.wf_sel]],
               "rows": b"".join(c for _, c in rows), "n": len(rows), "echo": e, "head": None}
        hs = self._hs
        if hs and hs.ring and ev["t1"] - ev["t0"] < DETAIL_MAX_S:
            a, b = ev["t0"] - HEAD_PRE_S, ev["t0"] + HEAD_POST_S
            hrows = [(t, c) for t, c in hs.ring if a <= t <= b and len(c) == len(hs.hz)]
            if hrows:
                det["head"] = {"t0": hrows[0][0], "dt": hs.dt, "hz": hs.hz_list, "rows": b"".join(c for _, c in hrows),
                               "n": len(hrows)}
                e["head"] = self._head_find(hrows, hs, ev["t0"], ev["dop"]) or ev.get("head_now")
        e["det"] = True
        try:                            # its sound (▶ in the detail): as on 143.049 USB
            clip = self._aud.clip(t_start + DETAIL_PRE_S / 2, t_end - DETAIL_POST_S / 2) if self._aud else None
            if clip:
                det["wav"] = meteor_audio.wav_bytes(clip[0], clip[1], self._aud.fs)
        except Exception as x:
            self.error = f"meteor audio: {x}"
        with self.lock:
            self.details[e["ts"]] = det
            self._trim_details()
        if self._fn is not None and ev["t1"] - ev["t0"] <= DETAIL_FINE_MAX_S and e["kind"] != "plane":
            # its fine cells come ~1 s later (from HEAD_PRE_S before it: a slow head echo is looked for there)
            self._fine_wait.append((e["ts"], min(t_start, ev["t0"] - HEAD_PRE_S), t_end))
            return True
        return False

    def audio(self, ts):
        """The WAV of the echo ts (bytes) while its detail is kept, else None."""
        with self.lock:
            d = self.details.get(ts)
            if d is None:
                near = [k for k in self.details if abs(k - ts) < 0.01]
                d = self.details[near[0]] if near else None
        return d.get("wav") if d else None

    def _trim_details(self):
        """(under self.lock) Only the last DETAIL_N details; an echo whose detail goes says so ("det" False), so the
        page does not step onto it with PREV / NEXT (the echo dict is the same one as in self.events)."""
        while len(self.details) > DETAIL_N:
            self.details.popitem(last=False)[1]["echo"]["det"] = False

    def detail(self, ts):
        """The detail of the echo ts (its "ts"), for the page: rows as base64 of uint8 (0..WF_DB dB), None if gone."""
        with self.lock:
            d = self.details.get(ts)
            if d is None:               # a float from the page: the nearest within 10 ms
                near = [k for k in self.details if abs(k - ts) < 0.01]
                d = self.details[near[0]] if near else None
        if d is None:
            return None
        out = {k: v for k, v in d.items() if k not in ("rows", "head", "wav", "fine")}
        out["audio"] = bool(d.get("wav"))
        out["rows"] = base64.b64encode(d["rows"]).decode()
        fine = d.get("fine")
        if fine:                        # the fine waterfall (1 Hz x 16 ms) instead of the detector's frames
            out.update(fine, rows=base64.b64encode(fine["rows"]).decode(), fine=True)
        elif d["echo"].get("kind") == "sat" and d.get("hz") and d.get("n"):
            out.update(self._sat_crop(d))
        out["db"] = WF_DB
        h = d.get("head")
        out["head"] = dict(h, rows=base64.b64encode(h["rows"]).decode()) if h else None
        return out

    @staticmethod
    def _sat_crop(d):
        """The detail of a satellite only around its track (and its calculated Doppler) ± SAT_DETAIL_MARGIN_HZ, at least
        SAT_DETAIL_MIN_HZ wide: over the whole ±8 kHz a track of a few hundred Hz is one pixel high."""
        e, hz, n = d["echo"], np.array(d["hz"], float), int(d["n"])
        fs = [e.get("f0"), e.get("f1"), e.get("doppler")]
        t_end = d["t0"] + n * d["dt"]
        fs += [f for t, f in (d.get("curve") or []) if d["t0"] - d["dt"] <= t <= t_end]
        fs = [float(f) for f in fs if f is not None]
        if not fs or len(hz) < 2:
            return {}
        lo, hi = min(fs) - SAT_DETAIL_MARGIN_HZ, max(fs) + SAT_DETAIL_MARGIN_HZ
        if hi - lo < SAT_DETAIL_MIN_HZ:
            mid = (lo + hi) / 2
            lo, hi = mid - SAT_DETAIL_MIN_HZ / 2, mid + SAT_DETAIL_MIN_HZ / 2
        sel = np.nonzero((hz >= lo) & (hz <= hi))[0]
        arr = np.frombuffer(d["rows"], np.uint8)
        if len(sel) < 2 or len(arr) != n * len(hz):
            return {}
        part = arr.reshape(n, len(hz))[:, sel[0]:sel[-1] + 1]
        return {"hz": [round(float(f), 1) for f in hz[sel[0]:sel[-1] + 1]],
                "rows": base64.b64encode(np.ascontiguousarray(part).tobytes()).decode()}

    # ----- the wide spectrum: satellites (meteor_sat.py) -----
    def _band(self, want):
        """± Hz around the carrier that fit in the VFO band, at most want; 0 if under 1 kHz."""
        band = min(want, self._fs / 2 * 0.9 - abs(self.f_off))
        return float(band) if band >= 1000 else 0.0

    def _wide_feed(self, base, now):
        ws = self._ws
        if ws is None:
            band = self._band(SAT_HZ)
            if not band:
                self.sat_hz = 0.0
                return
            n = 1 << int(round(math.log2(max(128.0, self._fs / SAT_DIV))))
            ws = self._ws = Spec(self._fs, self.f_off, n, n // 2, band, SAT_SMOOTH, SAT_RING_S, True, WF_DB,
                                 WEAK_RAW_S if self.sat_tle or self.sat_lines else 0.0)
            self._trk = SatTracker()
            self.sat_hz = band
            nb = len(ws.hz)
            self._wfw_edges = np.linspace(0, nb, min(WFW_BINS, nb) + 1)[:-1].astype(int)
            mid = [(a + b) / 2 for a, b in zip(self._wfw_edges, list(self._wfw_edges[1:]) + [nb])]
            hz = [round(float(np.interp(m - 0.5, np.arange(nb), ws.hz)), 1) for m in mid]
            with self.lock:
                if not (getattr(self, "_wfw_keep", False) and len(hz) == len(self.wfw.hz)):
                    self.wfw.clear()
                    self.wfw.hz = hz
        thr = 10 ** (SAT_THR_DB / 10)
        for t, ratio in ws.feed(base, now, thr):
            for tr in self._trk.frame(t, ratio, ws.hz, thr, ws.bin):
                if self._judge_track(tr):
                    self._sat_found(tr)
                else:
                    self._afc_wide(tr, t)
            self._wfw_add(t, ratio)
        if self.sat_tle or self.sat_lines or self._weak_wait:
            self._weak_step(now)

    # ----- SAT·TLE, SAT·LINES (meteor_weak.py): weak satellites the tracker misses -----
    def _weak_get(self):
        """For the thread: (the wide spectrum, the station, the receiver offset, SAT·TLE on, SAT·LINES on) or None."""
        if not self.enabled or not (self.sat_tle or self.sat_lines):
            return None
        return self._ws, (self.station() if self.station else None), self.rx_offset(), self.sat_tle, self.sat_lines

    def _weak_err(self, text):
        self.error = text

    @staticmethod
    def _on_track(tr, pts):
        """Do the points (t, Hz, …) lie on the track (a quarter of them at least)?"""
        return bool(tr.get("pts")) and SatTracker._hits(tr, pts, 0.1, 0.0) >= max(2, len(pts) // 4)

    def _weak_step(self, now):
        """What the thread found: reported unless a satellite reported already lies on it; it waits while a track of
        the tracker still going on lies on it (and a SAT·LINES one also for SAT·TLE, which names it)."""
        if self._weak is None:
            self._weak = meteor_weak.WeakWorker(self._weak_get, [], (GRAVES_LAT, GRAVES_LON), GRAVES_HZ, self._weak_err)
        for it in self._weak.take():
            pts = sorted(tuple(p) for p in it.get("pts") or [])
            if len(pts) >= 2:
                self._weak_wait.append([now, it, pts])
        keep = []
        for w in self._weak_wait:
            t_in, it, pts = w
            if any(self._on_track(s, pts) for s in self._sat_recent):
                continue                # the tracker (or the other search) has it
            # an aircraft: slow (a satellite crossing 0 Hz near its closest point may stay within ±PLANE_MAX_HZ too;
            # live, satellites near 0 Hz drift -34…-59 Hz/s, aircraft a few Hz/s: SLOW_SAT_HZ_S tells them apart)
            plane = (it["how"] == "lines" and max(abs(p[1]) for p in pts) <= PLANE_MAX_HZ
                     and abs((pts[-1][1] - pts[0][1]) / max(pts[-1][0] - pts[0][0], 1e-3)) < SLOW_SAT_HZ_S)
            if plane and (any(self._on_track(s, pts) for s in self._plane_recent) or self._det_has(pts)):
                continue                # the meteor detector has this aircraft
            late = now - t_in
            if late < WEAK_WAIT_MAX_S and (
                    (it["how"] == "lines" and not plane and late < WEAK_LINES_WAIT_S)
                    or any(self._on_track(tr, pts) for tr in self._trk.open)):
                keep.append(w)
                continue
            if plane:
                self._weak_plane(it, pts)
                continue
            tt = np.array([p[0] for p in pts]) - pts[0][0]
            ff = np.array([p[1] for p in pts])
            tr = {"pts": pts, "t0": pts[0][0], "t1": pts[-1][0],
                  "slope": float(np.polyfit(tt, ff, 1)[0]) if tt[-1] > 0 else 0.0}
            known = None
            if it["how"] == "tle":      # SAT·TLE knows which satellite it was
                known = {k: it[k] for k in ("norad", "name", "offset", "az", "el", "km", "z")}
                known.update(how="tle", lit=True, others=0, curve=[[round(p[0], 2), round(p[1], 1)] for p in pts])
            self._sat_found(tr, it["how"], known, it.get("z"))
        self._weak_wait = keep

    def _det_has(self, pts):
        """Is a SAT·LINES aircraft (its points) an echo the meteor detector had (a long overdense one: flat too)?"""
        f = float(np.median([p[1] for p in pts]))
        a, b = pts[0][0], pts[-1][0]
        return any(t0 <= b and t1 >= a and abs(d - f) <= 60.0 for t0, t1, d in self._recent_det)

    def _weak_plane(self, it, pts):
        """A SAT·LINES track within the Doppler an aircraft can have: a PLANE echo (looked up on adsb.fi as the others)."""
        self._plane_recent.append({"pts": pts})
        k = max(range(len(pts)), key=lambda i: pts[i][2])
        tt = np.array([p[0] for p in pts]) - pts[0][0]
        ff = np.array([p[1] for p in pts])
        drift = float(np.polyfit(tt, ff, 1)[0]) if tt[-1] > 0 else 0.0
        t0, t1 = pts[0][0], pts[-1][0]
        ev = {"t0": t0, "t1": t1, "peak": pts[k][2], "dop": pts[k][1], "k": 0, "track": [(p[0], p[1]) for p in pts],
              "afc": self.afc_hz}
        e = {"ts": round(t0, 2), "time": time.strftime("%H:%M:%S", time.gmtime(t0)), "dur": round(t1 - t0, 2),
             "snr": round(pts[k][2], 1), "doppler": round(pts[k][1]), "drift": round(drift, 1), "kind": "plane",
             "freq_hz": round(GRAVES_HZ + pts[k][1]), "det": False, "head": None, "how": "lines", "z": it.get("z")}
        self._finish(ev, e)             # its detail while the frames are kept, then reported (_publish)

    # ----- FAST (meteor_weak.py): short pings in the time signal -----
    def _fast_feed(self, base, now):
        fa = self._fast
        if fa is None or fa.fs != float(self._fs) or fa.f_off != float(self.f_off):
            fa = self._fast = meteor_weak.Fast(self._fs, self.f_off)
        self._fast_wait += fa.feed(base, now)
        keep = []
        for p in self._fast_wait:
            a, b = p["t0"] - FAST_NEAR_S, p["t1"] + FAST_NEAR_S
            if any(t0 <= b and t1 >= a for t0, t1 in self._recent_ev):
                continue                # the meteor detector has it
            if now - p["t1"] < FAST_WAIT_S or (self._ev is not None and self._ev["t0"] <= b and now - p["t1"] < 30.0):
                keep.append(p)          # its echo may still come (or is still open)
                continue
            if self._ev is not None and self._ev["t0"] <= b:
                continue
            self._fast_ping(p)
        self._fast_wait = keep

    def _fast_ping(self, p):
        """A FAST ping no echo of the meteor detector has: an underdense echo of its own (its detail as any other)."""
        ev = {"t0": p["t0"], "t1": p["t1"], "peak": p["snr"], "dop": p["dop"], "k": 0, "track": [(p["t0"], p["dop"])],
              "afc": self.afc_hz}
        e = {"ts": round(p["t0"], 2), "time": time.strftime("%H:%M:%S", time.gmtime(p["t0"])), "dur": round(p["dur"], 3),
             "snr": round(p["snr"], 1), "doppler": round(p["dop"]), "drift": 0.0, "kind": "under",
             "freq_hz": round(GRAVES_HZ + p["dop"]), "det": False, "head": None, "fast": True}
        self._recent_ev.append((p["t0"], p["t1"]))
        i = len(self._pending)          # in the order of their ends (_frame reports the first one first)
        while i > 0 and self._pending[i - 1][0]["t1"] > p["t1"]:
            i -= 1
        self._pending.insert(i, (ev, e))

    def _wfw_add(self, t, ratio):
        """The wide waterfall (±SAT_HZ, the satellites): every frame, the max of each group of bins (all ~16 Hz bins
        when there are no more than WFW_BINS)."""
        col = np.frombuffer(self._db8(np.maximum.reduceat(ratio, self._wfw_edges)), np.uint8)
        with self.lock:
            self.wfw.add(t, col)

    # ----- the waterfall of the meteor band (meteor_fine.py): ±FINE_HZ, 1 Hz x 16 ms, always -----
    def _fine_feed(self, base, now):
        fn = self._fn
        if fn is None:
            if abs(self.f_off) + FINE_HZ + 50 > self._fs / 2:
                return
            fn = self._fn = meteor_fine.Fine(self._fs, self.f_off, FINE_HZ, WF_DB)
            with self.lock:
                if fn.hz != self.wff.hz:
                    self.wff.clear()
                self.wff.hz = fn.hz
        cols = fn.feed(base, now)
        if cols:
            with self.lock:
                for t, b in cols:
                    self.wff.add(t, b)
        t_last = cols[-1][0] if cols else -np.inf
        # details whose fine cells are all there (or that waited too long: reported without them)
        while self._fine_wait and (self._fine_wait[0][2] <= t_last or self._fine_wait[0][2] < now - FINE_WAIT_S):
            self._fine_cut(*self._fine_wait.pop(0))

    def _fine_flush(self):
        """Stop, retune: the echoes waiting for their fine cells are reported with what there is."""
        while self._fine_wait:
            self._fine_cut(*self._fine_wait.pop(0))
        for ev, e in list(self._deferred.values()):
            self._publish(ev, e)
        self._deferred.clear()

    def _fine_cut(self, ts, a, b):
        """The fine waterfall from a to b into the detail of the echo ts (only the newest DETAIL_FINE_N keep it): around
        the echo (±DETAIL_FINE_HZ and a head echo), a slow head echo looked for in it; then the echo is reported."""
        try:
            with self.lock:
                times, rows = self.wff.fine.since(a, b)
                hz = np.array(self.wff.hz)
                det = self.details.get(ts)
            item = self._deferred.get(ts)
            if det is not None and len(times) and rows.shape[1] == len(hz):
                e = det["echo"]
                lo, hi = e["doppler"] - DETAIL_FINE_HZ, e["doppler"] + DETAIL_FINE_HZ
                if item is not None and not e.get("head"):
                    h = self._head_fine(times, rows, hz, item[0]["t0"], e["doppler"]) or self._head_track(item[0])
                    if h:
                        e["head"] = h
                        lo, hi = min(lo, h["f0"] - 30, h["f1"] - 30), max(hi, h["f0"] + 30, h["f1"] + 30)
                sel = np.nonzero((hz >= lo) & (hz <= hi))[0]
                keep = times >= det["t0"] - self.dt          # the detail from where the detector's frames start
                if len(sel) and keep.any():
                    part = rows[keep][:, sel[0]:sel[-1] + 1]
                    with self.lock:
                        det["fine"] = {"t0": float(times[keep][0]), "dt": meteor_fine.CELL_S,
                                       "hz": [round(float(f), 1) for f in hz[sel[0]:sel[-1] + 1]],
                                       "rows": np.ascontiguousarray(part).tobytes(), "n": int(keep.sum())}
                        have = [k for k, d in self.details.items() if "fine" in d]
                        for k in have[:-DETAIL_FINE_N]:
                            del self.details[k]["fine"]
        except Exception as x:
            self.error = f"meteor fine detail: {x}"
        item = self._deferred.pop(ts, None)
        if item is not None:
            self._publish(*item)

    def _head_track(self, ev):
        """A short steep head echo (a few tens of ms: too few fine cells) seen by the detector itself: the echo started
        on it, HEAD_TRACK_HZ or more off the trail, and came onto the trail point by point -> head dict or None."""
        tr, dop = ev["track"], ev["dop"]
        bw = abs(float(self.bin_hz[1] - self.bin_hz[0])) if len(self.bin_hz) > 1 else 8.0
        i0 = next((i for i, p in enumerate(tr) if abs(p[1] - dop) <= 2.5 * bw), None)
        if i0 is None or i0 < HEAD_TRACK_PTS or len(tr) - i0 < 3:      # the trail after it: a few points at least
            return None
        head = tr[:i0]
        d = [p[1] - dop for p in head]
        if (abs(d[0]) < HEAD_TRACK_HZ or any(x * d[0] <= 0 for x in d)
                or any(abs(b) > abs(a) - bw / 2 for a, b in zip(d, d[1:])) or tr[i0][0] - head[0][0] > HEAD_TRACK_S):
            return None                 # far off, one side, nearer at every point (another meteor stays), short
        pts = head + [tr[i0]]
        dt = pts[-1][0] - pts[0][0]
        if dt <= 0:
            return None
        return {"slope": round((pts[-1][1] - pts[0][1]) / dt), "f0": round(pts[0][1]), "f1": round(pts[-1][1]),
                "t": round(float(ev["t0"] - pts[0][0]), 2), "fine": True,
                "pts": [[round(float(p[0]), 3), round(float(p[1]), 1)] for p in pts]}

    def _head_fine(self, times, rows, hz, t0, dop):
        """A slow head echo in the fine cells: from the start of the echo back in time, a path of strong cells
        (HEAD_FINE_DB) that comes to the echo's Doppler, each within HEAD_FINE_STEP_HZ of the next, gaps of at most
        HEAD_FINE_GAP cells; smooth (a parabola: it slows down onto the trail), always nearer to the trail, at least
        HEAD_FINE_SLOPE Hz/s on average over HEAD_FINE_SPAN_HZ. It starts on the trail HEAD_FINE_POST_S after the echo's
        start (the detector may start on the end of the head echo itself). -> head dict or None."""
        lim = HEAD_FINE_DB * 255.0 / WF_DB
        # where the trail itself starts in the fine cells (the detector may have started on a slow head echo, the trail
        # comes later): lit at its Doppler in most of the next cells; the path starts a little after it
        near = np.abs(hz - dop) <= HEAD_FINE_TRAIL_HZ
        on = (rows[:, near].max(axis=1) >= lim) if near.any() else np.zeros(len(times), bool)
        look = np.nonzero((times >= t0 - HEAD_FINE_POST_S) & (times <= t0 + HEAD_FINE_TRAIL_S))[0]
        w = HEAD_FINE_TRAIL_N
        start = t0 + HEAD_FINE_POST_S
        for i in look:
            if on[i] and np.count_nonzero(on[i:i + w + 3]) >= w:
                start = max(start, float(times[i]) + HEAD_FINE_POST_S)
                break
        pre = np.nonzero((times >= t0 - HEAD_PRE_S) & (times <= start))[0]
        if len(pre) < HEAD_FINE_PTS:
            return None
        f, gap, pts = float(dop), 0, []
        for i in pre[::-1]:                     # backwards from the start of the echo
            m = np.abs(hz - f) <= HEAD_FINE_STEP_HZ * (gap + 1)
            if not m.any():
                break
            v = rows[i].astype(int)
            k = np.nonzero(m)[0][int(np.argmax(v[m]))]
            if v[k] >= lim:
                f, gap = float(hz[k]), 0
                pts.append((float(times[i]), f))
            else:
                gap += 1
                if gap > HEAD_FINE_GAP:
                    break
        # back in time the head echo only goes further from the trail, on one side: it ends where the path turns back
        # (noise it jumped to)
        keep, far, side = [], 0.0, 0.0
        for p in pts:
            d = p[1] - dop
            if abs(d) >= HEAD_FINE_FLAT_HZ:
                if (side and np.sign(d) != side) or abs(d) < far - HEAD_FINE_BACK_HZ:
                    break
                side, far = np.sign(d), max(far, abs(d))
            keep.append(p)
        pts = [p for p in keep if abs(p[1] - dop) >= HEAD_FINE_FLAT_HZ]    # not the start of the trail itself
        if len(pts) < HEAD_FINE_PTS:
            return None
        pts.reverse()
        # its oldest end may be noise next to it the path jumped to: off the line of the next few points
        while len(pts) > HEAD_FINE_PTS:
            nx = pts[1:6]
            a, b = np.polyfit([p[0] for p in nx], [p[1] for p in nx], 1)
            if abs(a * pts[0][0] + b - pts[0][1]) <= 3 * HEAD_FINE_RMS_HZ:
                break
            del pts[0]
        for _ in range(4):              # a few cells of noise the path picked up on the way are left out
            if len(pts) < HEAD_FINE_PTS:
                return None
            tt = np.array([p[0] for p in pts]) - pts[0][0]
            ff = np.array([p[1] for p in pts])
            if tt[-1] <= 0:
                return None
            # its shape: a parabola, or an exponential onto the trail (|f - trail| = A e^(-t/τ), as it brakes)
            fits = [np.polyval(np.polyfit(tt, ff, 2 if len(pts) >= 8 else 1), tt)]
            dd = ff - dop
            if np.all(dd > 0) or np.all(dd < 0):
                sg = 1.0 if dd[0] > 0 else -1.0
                a, b = np.polyfit(tt, np.log(np.abs(dd)), 1)
                fits.append(dop + sg * np.exp(a * tt + b))
            rmss = [float(np.sqrt(np.mean((ff - f_) ** 2))) for f_ in fits]
            fit, rms = fits[int(np.argmin(rmss))], min(rmss)
            res = np.abs(ff - fit)
            if res.max() <= 3 * HEAD_FINE_RMS_HZ:
                break
            del pts[int(np.argmax(res))]
        slope = float((fit[-1] - fit[0]) / tt[-1])                    # on average (of the fit: no noisy end)
        d = np.abs(fit - dop)                                         # its distance from the trail goes down
        nearer = float(np.mean(np.diff(d) <= 1.0)) if len(d) > 1 else 0.0
        if (abs(slope) < HEAD_FINE_SLOPE or ff.max() - ff.min() < HEAD_FINE_SPAN_HZ or rms > HEAD_FINE_RMS_HZ
                or nearer < HEAD_FINE_NEARER):
            return None
        return {"slope": round(slope), "f0": round(float(fit[0])), "f1": round(float(fit[-1])),
                "t": round(float(t0 - pts[0][0]), 2), "fine": True,
                "pts": [[round(float(p[0]), 3), round(float(f), 1)] for p, f in list(zip(pts, fit))[::max(1, len(pts) // 30)]]}

    def _sat_found(self, tr, how=None, known=None, z=None):
        """A satellite track ended: its echo, its detail (the wide spectrum) and, in a thread, which satellite it was.
        how: "tle" / "lines" found by meteor_weak.py (z its score), known: the satellite SAT·TLE found (no identify)."""
        pts = tr["pts"]
        self._sat_recent.append({"pts": sorted(tuple(p) for p in pts)})
        k = max(range(len(pts)), key=lambda i: pts[i][2])
        snr = pts[k][2]
        if how in ("tle", "lines"):     # a weak one: its median level along the track (noise ~ -0.5 dB), at its
            k = len(pts) // 2           # middle; the strongest point is a meteor it crosses at the carrier or noise
            snr = meteor_weak.level_db(pts)
        t0, t1 = tr["t0"], tr["t1"]
        e = {"ts": round(t0, 2), "time": time.strftime("%H:%M:%S", time.gmtime(t0)), "dur": round(t1 - t0, 2),
             "snr": round(snr, 1), "doppler": round(pts[k][1]), "drift": round(tr["slope"], 1), "kind": "sat",
             "freq_hz": round(GRAVES_HZ + pts[k][1]), "det": False, "head": None,
             "f0": round(pts[0][1]), "f1": round(pts[-1][1]), "sat": None}
        if how:
            e["how"], e["z"] = how, z
        cut = self._ws.rows(t0 - SAT_PRE_S, t1 + SAT_PRE_S, SAT_COLS)
        step = max(1, len(pts) // 400)
        det = None
        if cut:
            det = {"ts": e["ts"], "t0": cut[0], "dt": cut[1], "n": cut[2], "rows": cut[3], "hz": self._ws.hz_list,
                   "echo": e, "head": None, "pts": [[round(p[0], 3), round(p[1], 1)] for p in pts[::step]], "curve": None}
            e["det"] = True
        self.sats += 1
        clip = None                     # its sound: at most SAT_AUDIO_S around the strongest point (made in the thread)
        if self._aud and det is not None:
            a = max(t0, min(pts[k][0] - SAT_AUDIO_S / 2, t1 - SAT_AUDIO_S))
            clip = self._aud.clip(a - 0.5, min(t1, a + SAT_AUDIO_S) + 0.5)
        threading.Thread(target=self._sat_publish, args=(e, det, [(p[0], p[1]) for p in pts], clip, known), daemon=True,
                         name="meteor-sat").start()

    def _sat_publish(self, e, det, pts, clip=None, known=None):
        if clip and det is not None:
            try:                        # a tone following its Doppler track (meteor_audio.track_wav)
                r = meteor_audio.track_wav(clip[0], clip[1], self._aud.fs if self._aud else meteor_audio.RING_FS, pts)
                if r:
                    det["wav"], det["wav_shift"], det["wav_k"] = r
                    det["wav_t0"] = clip[0]
            except Exception as x:
                self.error = f"meteor audio: {x}"
        try:
            qth = self.station() if self.station else None
            res = dict(known) if known else identify(pts, qth, (GRAVES_LAT, GRAVES_LON), GRAVES_HZ)
        except Exception as x:          # the echo is reported anyway
            res = {"norad": None, "why": f"identification failed: {x}"}
        if det is not None:
            det["curve"] = res.pop("curve", None)
        else:
            res.pop("curve", None)
        e["sat"] = res
        if "candidates" in res:         # compared with the elements: identified or not (_q_unknown)
            self._sat_known.append(bool(res.get("norad")))
        if res.get("norad") and not res.get("others") and res.get("rms", 99) <= OFFSET_RMS_HZ:
            with self.lock:             # a sure fit measures the receiver offset (for the aircraft)
                self.rx_offsets = (self.rx_offsets + [[round(e["ts"]), res["offset"]]])[-OFFSET_N:]
                self._dirty = True
        with self.lock:
            if det is not None:
                self.details[e["ts"]] = det
                sat = [k for k, v in self.details.items() if v["echo"]["kind"] == "sat"]
                for k in sat[:-SAT_DETAIL_N]:           # the big ones: only the last few
                    self.details.pop(k)["echo"]["det"] = False
                self._trim_details()
            self.events.append(e)
        if self.on_echo:
            self.on_echo(e)

    # ----- which aircraft (meteor_air.py, adsb.fi) -----
    def rx_offset(self):
        """The receiver offset at 143 MHz (Hz) measured on the satellites identified surely, 0 before any."""
        with self.lock:
            offs = [o for _, o in self.rx_offsets]
        return float(np.median(offs)) if offs else 0.0

    def _air_publish(self, e, pts):
        try:
            qth = self.station() if self.station else None
            if not qth:
                res = {"hex": None, "why": "the station location is not set (SETUP › LOCATION)"}
            else:
                mid = meteor_air.midpoint(qth[0], qth[1], GRAVES_LAT, GRAVES_LON)
                t_now, ac = meteor_air.fetch(*mid)
                res = meteor_air.identify(pts, qth, (GRAVES_LAT, GRAVES_LON), GRAVES_HZ, ac, t_now, self.rx_offset())
        except Exception as x:          # no internet, adsb.fi down: the echo is reported anyway
            res = {"hex": None, "why": f"adsb.fi: {x}"}
        curve = res.pop("curve", None)
        e["air"] = res
        with self.lock:
            det = self.details.get(e["ts"])
            if det is not None:
                det["curve"] = curve
            self.events.append(e)
        if self.on_echo:
            self.on_echo(e)

    # ----- the head echo spectrum -----
    def _head_feed(self, base, now):
        hs = self._hs
        if hs is None:
            band = self._band(HEAD_HZ)
            if not band:
                self.head_hz = 0.0
                return
            n = 1 << int(round(math.log2(max(64.0, self._fs / 64.0))))
            hs = self._hs = Spec(self._fs, self.f_off, n, n // 2, band, 1, RING_S, False, WF_DB,
                                 HEAD_PRE_S + HEAD_POST_S + 1.5)     # + the plain power for a weak head (meteor_head)
            self.head_hz = band
        hs.feed(base, now, 10 ** (self.threshold_db / 10))

    def _head_find(self, hrows, hs, t_echo, dop=0.0):
        """A head echo: a chain of strong points (THR dB, away from the carrier and from the echo's own Doppler: a
        strong echo spreads over the short frames of this spectrum) before the echo, steep, straight, going one way
        and coming to the trail. Returns {"slope": Hz/s, "f0", "f1": Hz, "t": s before the echo} or None."""
        lim = int(min(255, self.threshold_db * 255.0 / WF_DB))
        hz = hs.hz
        away = (np.abs(hz) >= HEAD_SKIP_HZ) & (np.abs(hz - dop) >= HEAD_SKIP_HZ)
        pts = []
        for t, c in hrows:
            if t > t_echo + 0.2:
                break
            v = np.frombuffer(c, np.uint8)
            if len(v) != len(hz):
                continue
            k = int(np.argmax(np.where(away, v, 0)))
            if v[k] >= lim:
                pts.append((t, float(hz[k])))
        chains = []                     # each point continues the chain that ended last within 3 frames and 1 kHz
        for t, f in pts:
            best = None
            for ch in chains:
                lt, lf = ch[-1]
                if 0 < t - lt <= 3.5 * hs.dt and abs(f - lf) <= 1000.0 and (best is None or ch[-1][0] > best[-1][0]):
                    best = ch
            if best is None:
                chains.append([(t, f)])
            else:
                best.append((t, f))
        chains = [c for c in chains if len(c) >= HEAD_MIN_PTS]
        if not chains:
            return None
        ch = max(chains, key=len)
        tt = np.array([p[0] for p in ch]) - ch[0][0]
        ff = np.array([p[1] for p in ch])
        slope, icpt = np.polyfit(tt, ff, 1)
        rms = float(np.sqrt(np.mean((ff - (slope * tt + icpt)) ** 2)))
        steps = np.diff(ff)
        steps = steps[np.abs(steps) > hs.bin / 2]
        one_way = float(np.mean(np.sign(steps) == np.sign(slope))) if len(steps) else 0.0
        if (abs(slope) < HEAD_MIN_SLOPE or ff.max() - ff.min() < HEAD_MIN_SPAN_HZ or rms > 1.5 * hs.bin
                or one_way < 0.75 or abs(ff[-1] - dop) >= abs(ff[0] - dop)):
            return None                 # a few scattered points, back and forth, or going away from the trail
        return {"slope": round(float(slope)), "f0": round(float(ff[0])), "f1": round(float(ff[-1])),
                "t": round(float(t_echo - ch[0][0]), 2)}

    def _count_time(self, secs, now):
        with self.lock:
            h = self.hours.setdefault(hour_key(now), [0, 0, 0.0])
            h[2] += secs
            self._dirty = True
        if now - self._saved > SAVE_S:
            self.save(now)

    # ----- stats -----
    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                d = json.load(f)
            self.hours = {k: [int(v[0]), int(v[1]), float(v[2])] for k, v in (d.get("hours") or {}).items()}
            self.threshold_db = float(d.get("threshold_db", THRESHOLD_DB))
            self.head = bool(d.get("head", False))
            self.air = bool(d.get("air", True))
            self.sat_tle = bool(d.get("sat_tle", False))
            self.sat_lines = bool(d.get("sat_lines", False))
            self.fast = bool(d.get("fast", False))
            self.rx_offsets = [[float(a), float(b)] for a, b in d.get("rx_offsets", [])][-OFFSET_N:]
            self.afc = bool(d.get("afc", True))
            self.afc_hz = float(d.get("afc_hz", 0.0)) if self.afc else 0.0
            if "afc_hz" not in d:       # before the AFC: the offsets may have been measured with a wrong ppm
                self.rx_offsets = []
        except (OSError, ValueError, TypeError, IndexError, AttributeError):
            self.hours = {}

    def save(self, now=None):
        now = time.time() if now is None else now
        self._saved = now
        if not self._dirty:
            return
        cut = hour_key(now - LONG_DAYS * 86400)
        with self.lock:
            self.hours = {k: v for k, v in self.hours.items() if k >= cut}
            d = {"graves_hz": GRAVES_HZ, "threshold_db": self.threshold_db, "head": self.head, "air": self.air, "rx_offsets": self.rx_offsets,
                 "afc": self.afc, "afc_hz": self.afc_hz, "sat_tle": self.sat_tle, "sat_lines": self.sat_lines, "fast": self.fast,
                 "hours": {k: [v[0], v[1], round(v[2], 1)] for k, v in self.hours.items()}}
            self._dirty = False
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(d, f, separators=(",", ":"))
            os.replace(tmp, self.path)
        except OSError as e:
            self.error = f"meteor: {e}"

    def clear(self):
        """Clears the recent echoes (the hourly statistics stay)."""
        with self.lock:
            self.events.clear()

    def reset_stats(self):
        with self.lock:
            self.hours = {}
            self._dirty = True
        self.save()

    @staticmethod
    def bucket_s(span):
        """Seconds per point / column for a view of span seconds (VIEW_COLS of them, not finer than the scope)."""
        span = min(float(SCOPE_S), max(10.0, float(span)))
        return max(1.0 / SCOPE_RATE, span / VIEW_COLS)

    def waterfall(self, since_k=-1, span=120, wide=False, cols=VIEW_COLS):
        """The small waterfall for a view of span seconds in about cols columns (the page: one per screen pixel):
        columns k (start k × b s) from since_k on, each the max of its raw columns, base64 of uint8 (0..WF_DB dB over the
        floor). The newest column may still grow: the page replaces it. A column is never shorter than what is kept
        (meteor_fine.Tiered: every column for VIEW_FINE_S, the max over a coarser step for the whole SCOPE_S).
        wide: True / "wide" the wide spectrum ±SAT_HZ (satellites), "narrow" the meteor band ±NARROW_HZ, else all of it
        ±FINE_HZ (1 Hz x 16 ms)."""
        span = min(float(SCOPE_S), max(10.0, float(span)))
        cols = min(MAX_COLS, max(100, int(cols or VIEW_COLS)))
        src = self.wfw if wide in (True, "wide", "wide1k") else self.wff
        with self.lock:
            tier, dt = src.pick(span / cols if span <= VIEW_FINE_S else max(span / cols, src.coarse_dt))
            b = max(dt, span / cols)
            t_from = max(since_k * b, time.time() - span - b - VIEW_LAG_S)
            times, arr = tier.since(t_from)
            hz = list(src.hz)
        if wide in ("narrow", "wide1k") and hz:          # a part: ±NARROW_HZ of the fine one, ±WIDE1K_HZ of the wide one
            lim = NARROW_HZ if wide == "narrow" else WIDE1K_HZ
            sel = [i for i, h in enumerate(hz) if abs(h) <= lim]
            hz = [hz[i] for i in sel]
            arr = arr[:, sel[0]:sel[-1] + 1] if len(arr) else arr
        out = []
        if len(times) and arr.shape[1] == len(hz):
            ks = np.floor(times / b).astype(np.int64)
            starts = np.r_[0, np.nonzero(np.diff(ks))[0] + 1]
            mx = np.maximum.reduceat(arr, starts, axis=0)
            out = [[int(ks[i]), base64.b64encode(m.tobytes()).decode()] for i, m in zip(starts, mx) if ks[i] >= since_k]
        return {"hz": hz, "db": WF_DB, "bucket_s": b, "now": time.time(), "cols": out}

    @property
    def info(self):
        if not self.enabled:
            return ""
        h = self.hours.get(hour_key(time.time()))
        n = h[0] + h[1] if h else 0
        return f"{n} this hour · {self.status}"

    def summary(self, now=None, span=120):
        """Everything the GRAVES page shows; the chart (scope) for the last span seconds, the max of each bucket."""
        now = time.time() if now is None else now
        hh = [hour_key(now - i * 3600) for i in range(47, -1, -1)]
        with self.lock:
            hours = [[k] + list(self.hours.get(k, [0, 0, 0.0])) for k in hh]
            for h in hours:
                h[3] = round(h[3])
            days = {}
            for k, v in self.hours.items():
                d = days.setdefault(k[:10], [0, 0, 0.0])
                d[0] += v[0]
                d[1] += v[1]
                d[2] += v[2]
            events = list(self.events)[-400:]
            b = self.bucket_s(span)
            t_from = now - min(float(span), SCOPE_S) - b - VIEW_LAG_S
            scope, last_k = [], None
            for t, v in self.scope:
                if t < t_from:
                    continue
                k = int(t // b)
                if k == last_k:
                    scope[-1][1] = max(scope[-1][1], v)
                else:
                    scope.append([round(k * b, 2), v])
                    last_k = k
        last60 = sum(1 for e in events if e["kind"] in ("under", "over") and now - e["ts"] < 3600)
        today = days.get(hh[-1][:10], [0, 0, 0.0])
        return {"enabled": self.enabled, "status": self.status, "error": self.error, "threshold_db": self.threshold_db,
                "head": self.head, "head_hz": self.head_hz, "air": self.air, "rx_offset": round(self.rx_offset(), 1),
                "rx_offset_n": len(self.rx_offsets), "afc": self.afc, "afc_hz": self.afc_hz, "afc_locked": self.afc_locked,
                "sat_hz": self.sat_hz, "sats": self.sats, "tle": tle_state(),
                "sat_tle": self.sat_tle, "sat_lines": self.sat_lines, "fast": self.fast, "fasts": self.fasts,
                "graves_hz": GRAVES_HZ, "dial_usb_hz": DIAL_USB_HZ, "now": now, "planes": self.planes,
                "this_hour": hours[-1][1] + hours[-1][2], "last_hour": hours[-2][1] + hours[-2][2],
                "last_60min": last60, "today": today[0] + today[1],
                "hours": hours, "days": sorted([k, v[0], v[1], round(v[2])] for k, v in days.items()),
                "events": events, "scope": scope, "span_s": span}


def register(app, counter, station=None):
    """station: () -> (lat, lon) or None. GET /api/meteors: the page (with the path to GRAVES); DELETE clears the recent echoes (?stats=1 also the statistics);
    POST {threshold_db, head}: the detection threshold, the head echo spectrum on/off. GET /api/meteors/echo?ts=: the
    detail of one echo."""
    from flask import jsonify, request
    counter.station = station           # which satellite a satellite echo was (meteor_sat.identify)
    meteor_store.register(app, counter, counter.tag)      # the history from the log, the marked echoes

    @app.route("/api/meteors", methods=["GET", "POST", "DELETE"])
    def api_meteors():
        if request.method == "DELETE":
            counter.clear()
            if request.args.get("stats") == "1":
                counter.reset_stats()
            return jsonify(ok=True)
        if request.method == "POST":
            body = request.get_json(force=True, silent=True) or {}
            if "threshold_db" in body:
                try:
                    counter.set_threshold(body["threshold_db"])
                except (TypeError, ValueError):
                    return jsonify({"error": "threshold_db must be a number"}), 400
                counter._dirty = True
                counter.save()
            if "head" in body:
                counter.set_head(body["head"])
                counter._dirty = True
                counter.save()
            if "air" in body:
                counter.air = bool(body["air"])
                counter._dirty = True
                counter.save()
            if "afc" in body:
                counter.set_afc(body["afc"])
                counter.save()
            if any(k in body for k in ("sat_tle", "sat_lines", "fast")):
                counter.set_weak(body.get("sat_tle"), body.get("sat_lines"), body.get("fast"))
                counter.save()
        try:
            span = float(request.args.get("span", 120) or 120)
        except ValueError:
            span = 120.0
        out = counter.summary(span=span)
        qth = station() if station else None
        out["path"] = graves_path(*qth) if qth else None
        return jsonify(out)

    @app.route("/api/meteors/wf")
    def api_meteors_wf():
        """The small waterfall of the GRAVES page: ?span=<s>&since=<k> only the columns from k on (k of the span's buckets)."""
        try:
            since = int(request.args.get("since", -1) or -1)
            span = float(request.args.get("span", 120) or 120)
        except ValueError:
            since, span = -1, 120.0
        w = request.args.get("wide", "")
        try:
            ncol = int(request.args.get("cols", VIEW_COLS) or VIEW_COLS)
        except ValueError:
            ncol = VIEW_COLS
        return jsonify(counter.waterfall(since, span, {"1": "wide", "250": "narrow", "1000": "wide1k"}.get(w, False), ncol))

    @app.route("/api/meteors/echo")
    def api_meteors_echo():
        try:
            ts = float(request.args.get("ts", ""))
        except ValueError:
            return jsonify({"error": "ts must be a number"}), 400
        d = counter.detail(ts)
        if d is None and counter.marks:
            d = counter.marks.detail(ts)            # a marked echo keeps its detail
        if d is None:
            return jsonify({"error": "no detail of this echo (only the last ones are kept, not over a restart; ☆ keeps one)"}), 404
        return jsonify(d)
