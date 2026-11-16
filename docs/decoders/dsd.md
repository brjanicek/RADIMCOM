[← README](../../README.md) · [Documentation](../README.md)

# DSD: digital voice

The **DSD** key in the MODE group decodes digital voice with [DSD-FME](https://github.com/lwvmobile/dsd-fme), which runs as a
separate program (`dsd.py` feeds it the FM discriminator and takes the voice back).

> [!WARNING]
> **First test version, it still needs more testing.**
> - **Tested on real signals:** DMR and D-Star voice and call information, on one multi-mode repeater.
> - **Not tested yet:** P25, YSF, NXDN, dPMR, M17, ProVoice and X2-TDMA; two TDMA slots talking at once; long runs; CUE with a VFO in DSD.
> - One call may show up as several short rows in the list of calls.
>
> Reports are welcome, also when a protocol works: please open an [issue](https://github.com/om2amr/RADIMCOM/issues/new/choose) with the protocol,
> the frequency band and what you saw.

> [!IMPORTANT]
> **Installation: tick "Download the DSD-FME decoder" in the setup, or run `install_dsd.bat`.** DSD-FME is **not part of the RADIMCOM package**
> (neither the setup nor the zips contain it); `install.bat` does not install it, so this is a separate step. It needs internet.

Why it is separate: the voice codec of DSD-FME (mbelib, AMBE+2) may be covered by patents, see [NOTICE.md](../../NOTICE.md). `install_dsd.bat` shows the
notice, and after you type YES it downloads the release of the author (about 38 MB, checked by SHA-256) into `lib\dsd-fme`. Without it the DSD mode
stays silent and the card says what to do; if the mode is already selected, the decoder starts by itself a few seconds after the installation. To
replace a version, first switch every VFO out of the DSD mode: a decoder in use cannot be replaced, and the script then leaves the installed version as it was.

**Upgrade of RADIMCOM:** the setup does not touch `lib\dsd-fme`, so an installed DSD-FME stays. When a new RADIMCOM needs another DSD-FME version, the setup offers to update it (`install_dsd.py` writes its version to `lib\dsd-fme\VERSION.txt`). If it is not installed yet, run `install_dsd.bat`.
The script always installs the one version tested with this RADIMCOM; if a new RADIMCOM needs a newer one, the change log says to run `install_dsd.bat` again.

**New, empty folder:** `lib\dsd-fme` is not in `data\`, so a clean installation has no decoder. Run `install_dsd.bat` there as well.

- Tune to the centre of the channel and press **DSD**. The channel is fixed at 12.5 kHz. The **DSD** tab (next to SPECTRUM, there only while the mode DSD is on) opens with the DSD card.
- **Protocol:** AUTO finds DMR, P25 (phase 1 and 2), D-Star, YSF and X2-TDMA. NXDN48, NXDN96, dPMR, M17 and ProVoice have to be selected.
- **Slot** (DMR, P25 phase 2): voice of slot 1, slot 2 or both. Both talking at once: slot 1 on the left, slot 2 on the right. A change of the
  protocol or the slot restarts the decoder, which takes about a second.
- The card shows the running calls and a list of the finished ones: protocol, slot, talk group or private ID, caller and talker alias, if the
  radio sends one. **LOG** writes them to `data\logs\dsd_YYYY-MM-DD.txt`. DMR and D-Star have been tested on real signals so far; other protocols may show
  less. D-Star: the radio header gives To and From; without it the caller comes from a GPS frame, if the radio sends one, and To stays empty.
- The running calls are cards (one per slot) with the talk group, the caller, the alias and the running time. In the list the
  protocols and slots have colours, a talk group its name (TG 91 World-wide, 92 Europe, a national one by its country code, e.g.
  TG 231 = SK national), the caller ID the country of its first 3 digits (the MCC of the RadioID numbering; only a hint – an ID
  may be reused), the callsign in the alias is green. **TALK GROUPS** lists the talk groups of the list with the number of
  calls; a click shows only that one. The filter finds a TG, ID, callsign or protocol; **hide short** hides the calls under 1 s
  without a talk group and caller (noise). A click on the frequency of a call tunes the VFO there.
- **AFC** (on by default): 4FSK decodes badly a few hundred Hz off the signal – the talk group, the ID and the alias
  are lost first while the voice still comes. During a call the mean of the FM discriminator is the offset of the signal
  from the tuned frequency (the symbols are symmetric around the carrier; on a hotspot or simplex only the slots with a
  carrier are measured). The head shows it (*offset −380 Hz*, amber over 120 Hz); with AFC on an offset over 120 Hz
  retunes the VFO onto the signal (at most 3 kHz at a time, not while the satellite Doppler correction tunes) and the head
  shows *AFC +380 Hz ✓*. Measured on 2026-11-16: a DMR repeater tuned 400 Hz off gave the ID in 23 % of the calls,
  tuned onto it in 95 %.
- **Filter:** width of the channel filter before the FM discriminator, 12.5 kHz by default. DMR occupies about ±4.5 kHz,
  so on a weak signal **10k** lets about 1 dB less noise into the decoder; narrower cuts the outer symbols. Compare the
  errors in DEBUG. D-Star and NXDN48 are narrower (8k is enough), P25 phase 1 and YSF need at least 10k.
- **DEBUG** shows the raw output of DSD-FME under the list filter (the last 400 lines, updated once a second only while
  it is ticked): sync lines grey, link control (talk group, ID, alias) green, bursts that failed a CRC / FEC /
  Reed-Solomon check red. The head counts the sync lines and errors of the last minute. Many errors with a steady sync =
  bad bits at the input (noise, too much gain, a wrong protocol); few sync lines = the decoder loses the signal.
- **ENC** marks an encrypted call: it stays muted, RADIMCOM has no decryption. No trunking: the VFO stays on its frequency.
- Squelch, AFI, notch and ALC do not apply in this mode; LPF and HPF work on the decoded voice. Transmitting is blocked.
- Bad decoding: check the tuning (the channel centre) and the RF gain; too much gain distorts digital signals earlier than it is heard in FM.
  Select the protocol instead of AUTO when it is known: on a DMR repeater on 2026-11-16 AUTO gave the talk group and ID in
  3 of 10 calls, DMR in 7 of 8 (AUTO looks for the sync patterns of all protocols and loses more bursts).
