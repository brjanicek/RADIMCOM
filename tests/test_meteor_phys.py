"""meteor_phys.py: the physical bounds and the weighing of the evidence (meteor / satellite / aircraft)."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import meteor_phys as mp  # noqa: E402
from meteor_sat import SatTracker  # noqa: E402


class PhysTest(unittest.TestCase):
    def test_bounds(self):
        self.assertAlmostEqual(mp.LAMBDA_M, 2.096, delta=0.001)
        self.assertAlmostEqual(mp.AIR_DOP_MAX, 286, delta=2)        # 2 v / lambda, v = 300 m/s
        self.assertAlmostEqual(mp.SAT_RATE_MIN, 17.9, delta=0.2)     # v^2 / lambda * 2 / R, 7.5 km/s, 3000 km
        self.assertLess(mp.AIR_RATE_MAX, mp.SAT_RATE_MIN)            # the classes do not overlap
        self.assertAlmostEqual(mp.TRAIL_DOP_MAX, 95, delta=1)

    def test_slope_and_its_error(self):
        rng = np.random.default_rng(1)
        t = np.arange(0, 2.0, 0.03)
        pts = [(a, 100 - 40 * a + rng.normal(0, 4)) for a in t]
        s, se, *_ = mp.slope(pts, 0.2, 8.0)
        self.assertAlmostEqual(s, -40, delta=3 * se)
        self.assertTrue(0.5 < se < 5, se)
        self.assertTrue(mp.faster_than(s, se, mp.SAT_RATE_MIN))
        # a short flat ping: its slope is uncertain (quantisation, few independent points)
        short = [(a, 0.0) for a in np.arange(0, 0.3, 0.03)]
        s, se, *_ = mp.slope(short, 0.2, 8.0)
        self.assertEqual(s, 0.0)
        self.assertGreater(se, 5)
        self.assertIsNone(mp.slope(short[:2], 0.2, 8.0))

    def test_theil_sen_robust(self):
        """A still trail (0 Hz/s) with the end of a head echo at its start and noise at its end (5 of 30 points):
        least squares would see a drift, Theil-Sen does not."""
        t = np.arange(0, 1.0, 0.033)
        f = np.zeros(len(t))
        f[:3] = [300.0, 180.0, 90.0]                     # a head echo coming onto the trail
        f[-2:] = [-150.0, 120.0]                         # noise as the trail fades
        pts = list(zip(t, f))
        s, se, robust, rms = mp.slope(pts, 0.2, 8.0)
        self.assertLess(abs(s), 1.0)
        self.assertLess(robust, 5.0)                     # the spread of the trail itself
        self.assertGreater(rms, 40.0)                    # the odd points are still seen as not straight
        ols = np.polyfit(t, f, 1)[0]
        self.assertGreater(abs(ols), mp.SAT_RATE_MIN)    # what least squares said: a "satellite"
        self.assertFalse(mp.faster_than(s, se, mp.SAT_RATE_MIN))

    def test_decay(self):
        """An underdense trail: power falling exponentially, tau (amplitude) = 0.12 s from its dB line; a plateau is
        not straight in dB; a rising echo has no decay."""
        t = np.arange(0, 0.6, 0.031)
        tau = 0.12
        # what the detector measures: (signal + noise) / noise in dB, the signal falling 0.6 s from 30 dB to -13 dB
        tr = [(a, 0.0, 10 * np.log10(1 + 10 ** ((30.0 - 20.0 / np.log(10) * a / tau) / 10))) for a in t]
        got, r2 = mp.decay(tr)
        self.assertAlmostEqual(got, tau, delta=0.005)
        self.assertGreater(r2, 0.99)
        plateau = [(a, 0.0, 30.0 if a < 0.45 else 30.0 - 200 * (a - 0.45)) for a in t]
        self.assertLess(mp.decay(plateau)[1], 0.7)
        self.assertIsNone(mp.decay([(a, 0.0, 10 + 10 * a) for a in t]))
        self.assertIsNone(mp.decay(tr[:3]))

    def test_same_line(self):
        self.assertGreater(mp.same_line(-55, 4, -56), 0)            # drifts with the line
        self.assertLess(mp.same_line(0, 4, -56), 0)                 # stands still: a trail
        self.assertLess(mp.same_line(0, 16, -56), 0)                # even roughly measured

    def test_prior_learns(self):
        p = mp.DopplerPrior()
        self.assertAlmostEqual(p.rate(1000.0), mp.PRIOR_RATE_H / 3600)
        p.start(0.0)
        for k in range(600):                                        # 600 meteors in an hour around +20 Hz
            p.add(k * 6.0, 20.0 + (k % 7 - 3) * 3)
        self.assertAlmostEqual(p.rate(3600.0), 600 / 3600, delta=0.01)
        self.assertGreater(p.pdf(20.0), 3 * p.pdf(-80.0))
        # a busy sky near the carrier: a meteor on a satellite's line is likely by chance; far off it is not
        self.assertGreater(p.chance_log_bf(20.0, 3600.0, 100.0), p.chance_log_bf(-200.0, 3600.0, 100.0) + 5)


class StitchTest(unittest.TestCase):
    def test_meteors_joined_are_not_a_satellite(self):
        """Three trails (flat, 0.6 s each) at 0, +120, +240 Hz a second apart: the gate of the tracker could join them
        into a 'satellite' drifting ~100 Hz/s."""
        tt, ff = [], []
        for k, f in enumerate((0.0, 120.0, 240.0)):
            for a in np.arange(0, 0.6, 0.032):
                tt.append(k * 1.2 + a)
                ff.append(f + (a * 37 % 1) * 4)
        tt, ff = np.array(tt), np.array(ff)
        c = np.polyfit(tt, ff, 3)
        self.assertLess(SatTracker._stitched(tt, ff, c, 16.0), 0)

    def test_satellite_in_pieces_is_one(self):
        tt = np.concatenate([np.arange(a, a + 2.0, 0.032) for a in (0.0, 3.0, 6.0)])
        ff = 1500 - 150 * tt
        c = np.polyfit(tt, ff, 3)
        self.assertGreater(SatTracker._stitched(tt, ff, c, 16.0), 0)
        self.assertIsNone(SatTracker._stitched(tt[:50], ff[:50], c, 16.0))     # one piece: nothing to weigh


class TleEvidenceTest(unittest.TestCase):
    def test_iss_there_or_not(self):
        """The ISS lit by GRAVES over the station: an echo at its predicted Doppler is evidence for a satellite (and it
        is named), one 1.5 kHz off it is evidence against; no station / no elements: no evidence."""
        from sgp4.api import Satrec, SatrecArray
        import meteor_sat as ms
        l1 = "1 25544U 98067A   26326.17166235  .00010101  00000+0  18757-3 0  9993"
        l2 = "2 25544  51.6321 238.2738 0007393  52.3454 307.8204 15.49546258596247"
        s = Satrec.twoline2rv(l1, l2)
        el = (SatrecArray([s]), ["ISS (ZARYA)"], [25544])
        tx, qth, f = (47.348, 5.515), (48.7, 17.9), 143050000.0
        ep = (s.jdsatepoch + s.jdsatepochF - 2440587.5) * 86400
        tt = np.arange(ep, ep + 2 * 86400, 5.0)
        _, r, v = ms._ecef(el[0], tt)
        e_t, a_t, _ = ms._look(r, ms._site(*tx))
        e_r = ms._look(r, ms._site(*qth))[0]
        lit = np.nonzero((e_t[0] > 15) & (e_t[0] < 40) & (a_t[0] > 100) & (a_t[0] < 260) & (e_r[0] > 5))[0]
        self.assertTrue(len(lit), "no lit pass in 2 days")
        t = tt[lit[0]] + np.arange(0, 1.0, 0.1)
        _, r, v = ms._ecef(el[0], t)
        fd = ms.bistatic_doppler(r[0], v[0], ms._site(*tx)[0], ms._site(*qth)[0], f)
        on = ms.tle_evidence(list(zip(t, fd + 37)), qth, tx, f, 37.0, 15.0, 0.3, elements=el)
        self.assertGreater(on[0], 2)
        self.assertEqual(on[1], "ISS (ZARYA)")
        off = ms.tle_evidence(list(zip(t, fd + 1537)), qth, tx, f, 37.0, 15.0, 0.3, elements=el)
        self.assertLess(off[0], 0)
        self.assertIsNone(off[1])
        self.assertEqual(ms.tle_evidence(list(zip(t, fd)), None, tx, f, 0.0, 15.0, 0.3, elements=el), (0.0, None))


if __name__ == "__main__":
    unittest.main()
