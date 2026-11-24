"""WF GAIN COMP: the waterfall and spectrum rows corrected for the tuner gain, so their colours do not jump when AGC+
(or a hand) changes the RF gain.

The rows are dBFS (the level in the A/D): 10 dB more gain makes the whole band 10 dB brighter. Here each row gets the
gain of its moment taken off, so it shows the level at the input instead. It is done when the row is made, so the
history of the waterfall stays consistent by itself: an old row keeps the correction of its own time.

The gain table of a tuner is nominal: R820T steps differ from it by 1-2 dB, more at some steps. So a step is measured:
the median of the whole band (the noise floor, signals barely move it) before the step and after the blocks that may
still carry the old gain (sdr.gain_glitch) is taken as the real step. A measurement far from the nominal step (a strong
signal came or went just then) is not trusted and the nominal one is used. What a gain was measured as is kept, so
going back to a gain gives the same offset again and small errors do not add up.

Tuner AGC ("auto") has no known gain: no correction then.
"""
import numpy as np

REF_DB = 30.0           # the gain at which a row is the same as without correction, when the top of the range is not
                        # known; else the top (2026-11-23: with 30 dB every VFO at 49.6 dB showed the band 20 dB
                        # lower, which looked like a deafer receiver; at the top the rows are as without correction)
TRUST_DB = 3.0          # a measured step is used when within max(this, half the nominal step) of the nominal one
LEARN = 0.3             # weight of a new measurement against what was kept for that gain


class GainComp:
    def __init__(self):
        self.reset()

    def reset(self):
        self.gain = None            # the gain the offset belongs to (dB)
        self.offset = 0.0           # dB taken off every row now
        self.cal = {}               # gain dB -> offset dB learned for it
        self.step = None            # (old gain, new gain, median before, offset before) while a step settles
        self.med = None             # median of the band in the last settled row (dB)

    def update(self, cfg, power, glitch, unit=1.0, top=None):
        """The offset in dB to take off the row of this block. power: the linear spectrum of the block;
        glitch: blocks that may still have the old gain (sdr.Receiver.gain_glitch); unit: dB per gain unit;
        top: the highest gain of the tuner (in its units), the gain at which the rows are not corrected."""
        ref = float(top) * unit if top is not None else REF_DB
        if ref != getattr(self, "ref", ref):
            self.reset()                            # another tuner: what was learned does not fit
        self.ref = ref
        g = cfg.get("gain", "auto")
        if not cfg.get("wf_comp", True) or g == "auto":
            self.reset()
            return 0.0
        g = float(g) * unit
        med = float(10 * np.log10(np.median(power) + 1e-20))
        if self.gain is None:                       # first block: the nominal offset
            self.gain, self.offset = g, self.cal.get(g, g - ref)
            self.cal[g] = self.offset
        elif g != self.gain:                        # a new gain: hold the offset until the step has landed
            if self.step is None:
                self.step = (self.gain, g, self.med if self.med is not None else med, self.offset)
            else:                                   # another step before the last one settled: chain them
                self.step = (self.step[0], g, self.step[2], self.step[3])
            self.gain = g
        if self.step is not None:
            if glitch > 0:
                return self.offset
            old, new, med0, off0 = self.step
            nominal = new - old
            measured = med - med0
            delta = measured if abs(measured - nominal) <= max(TRUST_DB, abs(nominal) / 2) else nominal
            est = off0 + delta
            if new in self.cal:
                est = (1 - LEARN) * self.cal[new] + LEARN * est
            self.cal[new] = self.offset = est
            self.step = None
        self.med = med
        return self.offset
