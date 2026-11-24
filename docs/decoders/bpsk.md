[← README](../../README.md) · [Documentation](../README.md)

# BPSK (satellite telemetry)

Telemetry of BPSK satellites at **1200, 2400, 4800 or 9600 Bd**, decoded from the baseband of the VFO by RADIMCOM's own
code (`bpsk.py`, `funcube.py`). It works in any mode: the decoder reads the baseband, not the audio.

## DECODERS › BPSK

- **ON**, **SPEED** (the symbol rate of the satellite) and **SEARCH** (±3, ±6 or ±12 kHz: how far from the tuned
  frequency the carrier is looked for; the Doppler is about ±3.5 kHz at 145 MHz and ±10 kHz at 435 MHz). 4800 and
  9600 Bd need a sample rate of the SDR of about 1.5 / 2 MS/s.
- **Satellite keys** (FUNcube-1 AO-73, Nayif-1 EO-88, JY1Sat JO-97) tune 1.5 kHz below the downlink in USB and set
  the speed.
- **LOG** writes every frame to `data\logs\bpsk\YYYY\MM\DD\bpsk_YYYY-MM-DD.txt` (UTC, shared by all VFOs). **CLR**
  clears the table.
- Above the table, the **realtime telemetry of FUNcube-1** from its last frame: battery voltage and temperature,
  currents, solar panels, RF and PA, reboots, eclipse / safe mode; fitter messages as text.
- The table (newest on top): UTC, MHz, Bd, framing, satellite or sender, content. A click on a row opens the bytes of
  the frame.

## How it works

1. **Carrier:** the squared signal of BPSK has a line at twice the carrier. It is looked for within SEARCH of the tuned
   frequency and followed segment by segment, so the decoder follows the Doppler by itself, with or without the Doppler
   correction of the satellite tracking.
2. The signal is mixed to 0 Hz, low-passed and resampled to 8 samples per symbol; the symbol timing comes from the
   power at the symbol rate (Oerder & Meyr).
3. **Differential detection** (each symbol against the one before) needs no carrier phase: it decodes DBPSK and the
   NRZI of AX.25 alike, and the 180° ambiguity of BPSK does not matter.
4. Every framing is tried on the same soft bits:
   - **AO-40 FEC** of the FUNcube family: 5200-symbol frames with a convolutional code, interleaver, scrambling and two
     Reed-Solomon codewords;
   - **AX.25** (HDLC with NRZI), plain or with the G3RUH scrambler, as used by BPSK CubeSats.
5. The last seconds of baseband are demodulated again every few seconds (robust against Doppler and fading); a frame
   found again in the next window is recognised by its time and shown once.

Checked on a recording of FUNcube-1: every frame decoded, about 5 bit errors per frame corrected. AX.25 is tested only
on generated signals so far (`tests/test_bpsk.py`).
