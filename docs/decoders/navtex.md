[← README](../../README.md) · [Documentation](../README.md)

# NAVTEX

NAVTEX sends maritime safety information: navigational and weather warnings, ice reports, search and rescue, weather
forecasts. RADIMCOM has its own decoder (`navtex.py`) of the signal, SITOR-B (CCIR 476 / ITU-R M.476, FEC mode B).

**DECODERS › NAVTEX** (DEC key):

- **ON** and the **frequency keys**: **518** kHz (international, English), **490** kHz (national language),
  **4209.5** kHz (HF NAVTEX) and the HF maritime safety information frequencies 6314, 8416.5, 12579, 16806.5, 19680.5,
  22376 and 26100.5 kHz. A key tunes the active VFO 1.7 kHz below in USB (the tones at 1615 / 1785 Hz). Below 24 MHz
  the dongle needs an upconverter or direct sampling, see [Shortwave (HF) reception](../hf-upconverter.md).
- **Messages**, newest on top: UTC, the header `B1B2B3B4` (B1 the station, B2 the subject – A navigational warning, B
  meteorological warning, C ice, D search and rescue, E weather forecast… – B3B4 the number) and the text; the **live
  text** shows what is being received. **Filter** shows only the messages with a text, a station or a subject (e.g.
  `MA`, `B`, `ISTANBUL`). **LOG** writes a daily log (`data\logs\navtex\YYYY\MM\DD\navtex_YYYY-MM-DD.txt`), **CLR**
  clears the messages and the live text.
- The decoder can be stored with a memory channel (MEMORIES) and shows in SETTINGS › STATION.

## How it works

The signal is FSK at 100 Bd with a 170 Hz shift (the higher tone = 1). Each character is a 7-bit word with exactly four
1s, so a wrong bit is seen. Mode B sends every character twice: the RX copy comes 5 positions after the DX one, so a
character lost in a fade is often taken from its other copy.

1. **AFC:** the decoder works on the baseband of the VFO, in any mode. The pair of tones 170 Hz apart with the most power
   over the noise within ±3 kHz of the tuned frequency is looked for every half second over the last 3 s. Both tones
   must stand out (a wide data signal is not locked on); a pair far from the lock is taken only when not in sync.
2. **Bits:** two correlators over one bit (mark, space); the bit clock follows the zero crossings of their difference.
3. **Words:** the boundary (and the polarity) is where 90 % of the last 20 words have four 1s; lost under 55 %.
4. **DX / RX:** the parity of the positions whose word comes again 5 later; each character from its DX copy, else from
   the RX one (`~` when both are wrong).
5. **Messages** from `ZCZC B1B2B3B4` to `NNNN` (or 60 s after the signal was lost).
