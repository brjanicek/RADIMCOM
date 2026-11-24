[← README](../README.md) · [Documentation](README.md)

# Configuration

## `vfos.json`: assigning dongles to VFOs

```json
{
  "port": 8434,
  "vfos": [
    { "name": "A", "serial": "SDR00001", "port": 8441, "config": "config_A.json",
      "note": "HF via upconverter",
      "init": { "upconv": "auto", "lo_offset_hz": 100000000, "ppm": 0 } },
    { "name": "B", "serial": "SDR00002", "port": 8442, "config": "config_B.json", "init": { "ppm": 0 } },
    { "name": "C", "serial": "SDR00003", "port": 8443, "config": "config_C.json", "init": { "ppm": 0 } },
    { "name": "D", "driver": "lime", "serial": "1D3C...", "port": 8444, "config": "config_D.json",
      "note": "LimeSDR, VHF/UHF direct" }
  ]
}
```

- `serial` is the dongle's serial number in EEPROM (for a LimeSDR its serial number, `driver: "lime"`; for an Airspy its 64-bit serial number as 16 hex digits, `driver: "airspy"`).
  Network sources: `driver: "rtltcp"` with `serial` = `host:port` or `SERIAL@host` (a dongle of an rtl_tcp server), and
  `driver: "spyserver"` with `serial` = `host:port` (an Airspy SpyServer). The servers to look at are in
  `"rtltcp_servers"` (SpyServers as `sdr://host:port`).
- `port` is the port of that VFO's receiver. The page talks to it directly.
- `config` is the VFO settings file. On first start it is created from `config.json` plus the values from `init`.
  After that each VFO remembers its own tuning, mode, filters, squelch, gain and ppm.

## SDR SOURCES: assigning sources to VFOs

**SETTINGS › SDR SOURCES** writes `vfos.json` from the running RADIMCOM (the former SDR setup window):

- **Sources:** the local devices (RTL-SDR, LimeSDR, Airspy on USB) and the network ones as cards. A USB dongle open in a running
  VFO is shown with its USB name, index, tuner and *in use by VFO X* (the VFO reports it; a busy dongle cannot be read over USB).
  ⟳ looks again.
- **Network servers:** type their addresses (commas between them) and FIND. A host alone is an rtltcp-manager (all its
  dongles), `host:port` is asked by its protocol – an rtl_tcp server sends its `RTL0` header at once, a SpyServer waits for the
  client – so a SpyServer on any port is found and saved as `sdr://host:port`.
- **DIRECTORY:** the public SpyServers of the Airspy directory (<https://airspy.com/directory/>), sorted by the distance from
  the QTH, with device, range, IQ rate, clients, full control and antenna; filters for text, device, band, a free slot and full
  control. A click on a row adds it to the servers and FINDs it.
- **VFO A–D:** drag a source onto a VFO (or click it, then the VFO); onto a VFO that has one, the two swap; ✕ takes it off.
  An empty VFO can *share* the dongle of an earlier VFO (chaining) or IDENTIFY a USB dongle by unplugging it. Per VFO:
  ppm, HF upconverter with its LO (not for a network source) and the name on the VFO key. Each VFO shows RUNNING, STOPPED or
  CHANGED.
- **APPLY** writes `vfos.json` and restarts **only the VFOs that change** (a bubble in the middle of the screen shows them
  starting, then the page reloads); the others keep running. A VFO that keeps its source keeps its settings – frequency,
  mode, AGC and the rest of `config_X.json` – also when it moves to another letter (two VFOs that swap dongles swap their
  settings with them); a new ppm or LO restarts only that VFO; a new name restarts nothing. A new source starts from the
  defaults; the old settings of a changed VFO go to `data\config_backup\<time>\`. **REVERT** goes back to what runs.
- **SERIAL NUMBERS:** the EEPROM serials of the RTL-SDR dongles (as in the window below); a dongle open in a VFO cannot be
  written, **STOP USB VFOs** frees them first (APPLY starts them again).

## Network sources: rtl_tcp and SpyServer

- **rtl_tcp** (`driver: "rtltcp"`): an RTL-SDR dongle on another computer, with all its settings over the network; see
  SETTINGS › RTL_TCP SERVER for the server.
- **SpyServer** (`driver: "spyserver"`, spyserver.py, own client of the SpyServer protocol): an Airspy SpyServer (Airspy
  R2 / Mini / HF+ or an RTL-SDR behind it). The VFO uses the rates the server offers; a server with a narrow band (e.g. an
  HF+ with 228 kHz) is upsampled to at least 0.5 MS/s, and the VFO keeps its tuning inside the real band. On a shared server
  (no full control) the gain is set by the server and the frequency only inside the band of its owner.
- In SETTINGS › VFO › RX CHAIN the **Source** card (after the bias-tee) shows the kind, address and device; with a network
  source the antenna, upconverter LO and bias-tee are greyed (they are at the server), with a shared SpyServer the gain too.
- **VFO window:** a network icon instead of the USB one. On a SpyServer VFO a **click on the icon pauses** it: RADIMCOM
  disconnects from the server (no data, the client slot is free for others), the icon turns amber with ⏸; another click
  connects again with the same settings. The pause is kept over a restart. The tooltip shows the data rate.

## VFO chaining: one dongle for several VFOs

A VFO with `"chain": "A"` instead of `serial` has no dongle of its own: it uses the samples of VFO A's dongle.
Any combination works, e.g. one dongle for VFO A–D, or two dongles with two VFOs each:

```json
{ "name": "A", "serial": "SDR00001", "port": 8441, "config": "config_A.json" },
{ "name": "B", "chain": "A", "port": 8442, "config": "config_B.json", "note": "chained to VFO A" },
{ "name": "C", "serial": "SDR00002", "port": 8443, "config": "config_C.json" },
{ "name": "D", "chain": "C", "port": 8444, "config": "config_D.json", "note": "chained to VFO C" }
```

- The owner VFO (A) controls the dongle: its tuning sets the centre of the received band. A chained VFO
  receives only inside that band (centre ± 95 % of half the sample rate, e.g. ±0.97 MHz at 2.048 MS/s). It can be
  tuned anywhere, but outside the band (or when VFO A moves away) it is silent and shows an orange **OOR** flag
  ("out of range VFO-A" on hover) until the frequency is inside the band again.
- Gain, RTL AGC, bias-tee, ppm and the sample rate belong to the dongle: changed on a chained VFO, they are sent to
  the owner VFO and apply to all VFOs on that dongle.
- A chained VFO shows a green **CHAIN** flag instead of the USB icon. VDL2 and TX are not available on it.
- The owner sends the samples to its chained VFOs over a local socket (`127.0.0.1`, VFO port + 100, e.g. 8541;
  `"iq_port"` in the owner's entry changes it).

## Initial setup: `setup_sdr.py`

```bash
python setup_sdr.py
```

The wizard (`setup.bat` on Windows) finds the connected RTL-SDRs, LimeSDRs and Airspys and assigns them to VFO A, B, C, D:
the device for a VFO is chosen by number or by unplugging it for a moment (the wizard detects which one is
missing). Typing the letter of an earlier VFO (e.g. `A`) chains the new VFO to that VFO's dongle, so one dongle
can serve several VFOs. Then it asks about the upconverter and ppm and writes `vfos.json`. If the dongles share the same serial
number (commonly `00000001`), it offers to write a unique number to the EEPROM. Old `vfos.json` and `config_X.json`
are moved to `data\config_backup\`. The receiver must be stopped during setup. With RADIMCOM running, use SETTINGS › SDR SOURCES.

ppm correction can also be set later in the SET menu of each VFO.

## Transmitting (LimeSDR)

> [!CAUTION]
> **IMPORTANT – transmitting disclaimer.** Transmitting is legal only for a holder of a valid amateur radio
> licence (or another authorisation required in your country), within the privileges of that licence and the
> regulations based on the ITU Radio Regulations, CEPT (T/R 61-01, T/R 61-02, ERC/REC 70-03), FCC Part 97 or your
> national authority. PMR446 and CB may require type-approved equipment, so an SDR transmitter may not be allowed
> there at all. An SDR is not a certified transmitter and can emit harmonics and spurious signals, so use a
> suitable filter and antenna or a dummy load. **You, the operator, are fully and solely responsible for every
> transmission and its consequences.** The software is provided "AS IS", without any warranty, and the author
> accepts no liability (see [LICENSE](../LICENSE)). Anyone who modifies or removes the TX band limits is solely
> responsible for any transmission outside the bands they are licensed for.

For a VFO with a LimeSDR, SET has an **Enable TX** switch (off by default). You can turn it on only after
you accept the disclaimer above. When enabled, PTT is holding the space bar: in FM a test message from
`data\tx_audio\test_message.wav` is sent (if it exists), otherwise a carrier.
Transmitting works only without the upconverter. Retuning ends the transmission.

The receiver allows TX only when the whole emission (tuned frequency ±5 kHz) is inside one of these bands:
ham 160 m, 80 m, 60 m, 40 m, 30 m, 20 m, 17 m, 15 m, 12 m, 10 m, 6 m, 4 m, 2 m, 70 cm, 23 cm (IARU Region 1),
CB 26.960–27.410 MHz and PMR446 446.0–446.2 MHz. Your national band plan may be narrower.

## Dongle serial numbers: `eeprom_tool.py`

```bash
python eeprom_tool.py
```

Lists the connected dongles and backs up their EEPROM to `data\eeprom_backup\`.

```bash
python eeprom_tool.py write INDEX SERIAL
```

Writes a new serial number. It may be shorter than the original, not longer (the EEPROM has a fixed place for it). After writing, unplug and replug the dongle.

```bash
python eeprom_tool.py restore INDEX FILE
```

Restores the EEPROM from a backup.

## Importing memories from SDR#

Easiest from the web page: MEMORIES tab → IMPORT → LOAD FILE… and pick `frequencies.xml` from the SDR# folder. From the command line (HF upconverter entries only):

```bash
python memories.py C:\sdrsharpSW\frequencies.xml
```

## HTTP API

Everything the web page does goes through an HTTP API on each VFO's port (tuning, mode, decoders, events,
audio, memories), so the receivers can be controlled from scripts or other programs too. Description and examples:
[API/API.md](../API/API.md).
