# POCSAG

Decoder of POCSAG pager messages (`pocsag.py`), page **POCSAG** in the DECODERS tab.

## Use

1. Tune the VFO onto the pager channel (12.5 kHz channel; the mode and filter do not matter, the decoder takes the
   baseband of the VFO). Around Bratislava a 1200 Bd network is heard on about **162.47 MHz**.
2. Switch **ON** on the POCSAG page. 512, 1200 and 2400 Bd run at once, in both polarities; **BAUD** limits it to one speed.
3. **MESSAGES**: every message (UTC, speed, RIC, function bits F, text). **ADDRESSES**: the newest message of each RIC with
   the count. A click on a RIC filters to it (again = all), **NO TONE** hides address-only pages, **LOG** writes
   `data\logs\pocsag_YYYY-MM-DD.txt`.

A text in blue is the numeric reading, white the alphanumeric one; grey italics = tone only (no message codewords).
POCSAG does not say which of the two a message is: it is guessed from the function bits (often 0 = numeric,
3 = alphanumeric) and from the characters; the tooltip shows the other reading, the speed, polarity and the corrected bits.

## How it works

- Channel filter ±7 kHz → FM discriminator (Hz) → for each speed a low-pass (0.6 × baud) → slicer whose threshold is the
  middle of the signal envelope (follows a tuning offset) → bit clock (PLL of the packet decoder).
- Framer for each polarity: the sync codeword `0x7CD215D8` with at most 2 wrong bits starts a batch of 16 codewords
  (8 frames × 2); following batches start with a sync codeword with at most 4 wrong bits. A batch with 6 codewords
  that cannot be corrected (noise passes the check about every second codeword) ends the transmission.
- Each codeword is BCH(31,21) + even parity: syndrome tables correct one and two wrong bits (two only when the parity
  agrees); otherwise it is lost and shown as `?`. Address codeword: RIC = 18 address bits × 8 + frame number.
  An address that needed two corrected bits is shown only when a clean message follows it.
- The same message (RIC, F, text) within 10 s is shown once.

## Tests

`python -m unittest tests.test_pocsag`: codewords and error correction, numeric / alphanumeric / tone messages over
several batches, lost codewords, the whole chain on synthetic FSK at 512 / 1200 / 2400 Bd, both polarities,
37.5 kHz baseband, a weak signal, noise only, duplicates.
