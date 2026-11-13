[← README](../README.md) · [Documentation](README.md)

# Installation and running

Backup, upgrade and reinstall (the `data\` folder): see [Data folder](development.md#data-folder-data).

## Setup (recommended)

`RADIMCOM_Setup_v<version>.exe` from [Releases](https://github.com/om2amr/RADIMCOM/releases):

- **Brings its own Python 3.13** with all packages in `python\`: nothing else to install, no internet needed.
- **No administrator rights:** installed to `C:\RADIMCOM` by default, or a folder of your choice (not a development copy
  with `.git`). An older zip installation in that folder is upgraded in place (`data\` stays).
- **New installation or upgrade:** the setup looks into the chosen folder. `RADIMCOM.exe` there (installed by the setup)
  or `data\config.json` (an older zip installation, 0.114 and older) means an upgrade; the first page, the folder page and
  the last page before installing say which (a zip installation: "an older RADIMCOM ... is upgraded and becomes the
  RADIMCOM app"). An upgrade skips the SDR setup at the end and does not offer the DSD-FME download; only when the
  installed DSD-FME is of another version than this RADIMCOM needs (`lib\dsd-fme\VERSION.txt`, written by
  `install_dsd.py`), it offers to update it. A RADIMCOM still running from the folder (RADIMCOM.exe, or `start.bat` in a
  console) must be closed first; the setup says so.
- **Languages:** English, Slovak, Czech, by the language of Windows (otherwise it asks).
- **Options:** Zadig (WinUSB driver for RTL-SDR and Airspy), FTDI D3XX (LimeSDR), downloading DSD-FME (DSD mode, patent
  notice), desktop shortcut, start with Windows (in the tray). The drivers ask for administrator rights themselves.
- At the end of a new installation it opens the **SDR setup** in the RADIMCOM window (see below) and then starts RADIMCOM.
- **Start menu:** RADIMCOM, RADIMCOM SDR setup (`RADIMCOM.exe --setup`), RADIMCOM data folder, RADIMCOM in a console (`start.bat`), uninstall.
- **Upgrade:** the setup of a newer version installs over the same folder: `data\` and `lib\dsd-fme` stay, `python\`
  and `static\` are replaced completely. When a newer version is released, the page says so with a link to its setup
  (nothing is installed from the page; see [Data folder](development.md#data-folder-data)).
- **Uninstall:** Windows Settings › Apps › RADIMCOM; it asks whether to delete `data\` too.
- The setup is not signed: Windows SmartScreen may show "Windows protected your PC" → *More info* → *Run anyway*.

### RADIMCOM.exe

- Starts the server (`python\python.exe app.py`, without a console window) and shows the page in its **own window**
  (WebView2, the Edge engine of Windows 10/11) with the RADIMCOM icon on the taskbar, so it can be pinned there.
  When a server already answers on the port (e.g. started by `start.bat`), the window only shows it.
- **Closing the window** leaves the server running in the **tray** (decoders, logs and recordings go on; the page in
  the window stops, so no sound). Tray icon: left click opens the window; right click: *Open RADIMCOM*, *Open in the
  web browser*, *Data folder*, *Server log*, *SDR setup…*, *Start server*, *Stop server* (the receivers close and the
  dongles are free, e.g. for another program; RADIMCOM.exe stays in the tray and its window offers START SERVER),
  *Restart server*, *Exit RADIMCOM* (stops the receivers gracefully, after 20 s by force).
- **Full screen:** F11 or the ⛶ key beside the RADIMCOM logo (lit while on): no frame, over the taskbar of its monitor.
  It is remembered for the next start; `RADIMCOM.exe --fullscreen` starts in it too.
- **MAIN** key beside the logo: the power switch; after a confirmation it switches RADIMCOM off (as *Exit RADIMCOM*).
  Both keys are only in the app window, not when the page is open in a browser (placement provisional).
- A second start only brings the window up.

### SDR setup in the window

Tray menu *SDR setup…*, Start menu *RADIMCOM SDR setup* or `RADIMCOM.exe --setup` (a running RADIMCOM switches to it).
It stops the receiver (the dongles must be free), runs `setup_web.py` (port 8433, only from this PC) and shows one page:

- **Connected SDR dongles:** every connected RTL-SDR, LimeSDR and Airspy as a card with its serial number; REFRESH after replugging.
- **Serial numbers:** RTL-SDR dongles with the same or an empty serial cannot be told apart; WRITE TO EEPROM gives them
  unique numbers of the same length (each EEPROM is backed up to `data\eeprom_backup` first), then replug them.
- **VFO A–D:** drag a dongle card onto a VFO (or click the card, then the VFO). Dropped on a VFO that has one, the two
  VFOs swap their dongles; dragged back to the list (or ✕) it is taken off. An empty VFO can *share the dongle of VFO X*
  (chaining). Then per VFO: ppm, HF upconverter with its LO in MHz (30–1000; a value in Hz is converted) and the name on
  the VFO key. **IDENTIFY** on an empty VFO: unplug the dongle you want there, it is found and placed by itself (up to
  30 s), then plug it back in. Prefilled from `vfos.json`; a saved dongle that is not connected shows as "not connected"
  (plug it in and REFRESH, or ✕). Empty VFOs between used ones are skipped when saving (the letters move up).
- **SAVE AND START RADIMCOM** writes `data\vfos.json` (the previous VFO settings are moved to `data\config_backup\<time>`)
  and starts the receiver; **CANCEL** or closing the window starts it with the settings it had.

The console wizard `setup_sdr.py` (`setup.bat`) does the same with questions and answers. `RADIMCOM.exe --tray` starts into the tray (used by the autostart option),
  `--exit` stops a running RADIMCOM (used by the uninstaller).
- All processes of the server run in a job object: if RADIMCOM.exe ends, they end too.
- **Resizing** keeps the aspect ratio of the page: dragging an edge or a corner changes the other side with it
  (that of the screen, so the page looks like in full screen, only smaller; with the lower part hidden by VIEW that of the head, and the window height follows at once; also after restoring from maximized or full screen). Maximized
  and full screen are not limited (the page then stretches as in a browser).
- Links to other web sites open in the normal browser; sound starts without a click; window size and position are
  kept in `data\window.txt`, the WebView2 profile in `data\webview2\`.
- If WebView2 is missing (very old Windows 10 without updates), the page opens in the default browser instead.
- What the server prints before its log opens (or why it could not start) is in `data\server_logs\console.log`.

### Building the setup

`python installer/make_installer.py` builds `dist\RADIMCOM_Setup_v<version>.exe`, the only package of a release from
0.115 on (it also upgrades the older zip installations); the old install and upgrade zips only on request (`--zips`,
`--zip-only`). It needs Inno Setup 6 (`winget install JRSoftware.InnoSetup`) and the
.NET Framework 4.x `csc.exe` (part of Windows). Python (NuGet package `python`) and the WebView2 SDK are downloaded once
into `installer\cache\`; the packages are installed there in isolated mode. `python installer/make_installer.py --exe` builds
only `RADIMCOM.exe` into this folder for a development copy (it then runs `.venv\Scripts\python.exe`).
`installer\make_icon.py` draws the icon (`installer\radimcom.ico`, `static\favicon.png`).

## Requirements

- Windows 10/11. With the setup nothing else. From the sources: Python 3.9+, by hand:

  ```bash
  pip install -r installer\requirements.txt
  pip install --no-deps PyFT8
  ```

  (`flask`, `numpy`, `scipy`, `pyserial`, `lameenc`, `sgp4`; `PyFT8` is needed only for the FT8 decoder, `pyserial` only for the antenna rotor, `lameenc` only for recording, `sgp4` only for the pass prediction.)

- RTL-SDR dongles with the WinUSB driver (installed with Zadig).
- LimeSDR Mini with the FTDI D3XX driver.
- Airspy R2 with the WinUSB driver, receive only: 2.5 MS/s, gain as the presets 0–21 (not dB), bias-tee. VDL2, DAB and ISM are not available on it; the 10 MS/s rate is not offered yet.

Third-party binaries are **not in this git repository** (folders `lib\` and `drivers\` are in `.gitignore`).
The setup (`RADIMCOM_Setup_v<version>.exe`, download it from
[Releases](https://github.com/om2amr/RADIMCOM/releases)) contains them all. When running from the git sources,
put them there yourself:

| File | Purpose | Source |
|---|---|---|
| `lib\librtlsdr.dll`, `lib\libusb-1.0.dll` | required for RTL-SDR | Windows release of the RTL-SDR Blog driver (`rtl-sdr-blog`, supports the V4) |
| `lib\LimeSuite.dll` | only for LimeSDR | PothosSDR (`C:\Program Files\PothosSDR\bin`); if it is not in `lib\`, it is loaded from the PothosSDR installation |
| `lib\airspy.dll`, `lib\pthreadVC2.dll` | only for Airspy | PothosSDR (`C:\Program Files\PothosSDR\bin`); if they are not in `lib\`, they are loaded from the PothosSDR installation |
| `drivers\zadig.exe` | WinUSB driver for RTL-SDR | zadig.akeo.ie |
| `drivers\FTD3XXDriver_WHQLCertified_v1.3.0.4_Installer.exe` | D3XX driver for LimeSDR | FTDI (ftdichip.com, D3XX drivers) |
| `lib\dsd-fme\` | only for the DSD mode; **not in the installer package either** | run `install_dsd.bat`, see [DSD: digital voice](decoders/dsd.md) |

`installer\make_installer.py` takes the RTL-SDR DLLs from `lib\`, `LimeSuite.dll` and the Airspy DLLs from PothosSDR and the drivers
from `Downloads` on this PC.
- For FT8 the PC clock must be accurate (±1 s).

## Running

```bash
python app.py
```

Installed with the setup: **RADIMCOM.exe** (Start menu or taskbar), see above. From the sources: double-click
`start.bat` (the server in a console window) and open **http://localhost:8434** in the browser.

- If `data\vfos.json` exists, the **VFO launcher** (`launcher.py`) starts. It opens a separate receiver on its
  own port for each VFO and serves the page itself on port 8434. Closing the launcher also closes the receivers.
- Without `vfos.json` a single receiver runs with the settings from `data\config.json`.
- Only one such server can run at a time, because the dongles are shared.
- **Server log:** the window shows only where the log is; everything the launcher and the VFO receivers print
  (messages, errors with tracebacks, output of the SDR libraries and helper programs) goes to
  `data\server_logs\logs_DDMMYYYY_HHMMSS.log`, a new file at each start (date and time of the start), one for all
  VFOs. Lines of successful web requests are left out, failed ones (4xx, 5xx) stay.
- If the browser does not allow sound without a click, the page shows *"Click anywhere to start audio"*.
  Sound starts after the first click on the page.
