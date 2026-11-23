# How we build RADIMCOM

The working rules of the project, for Brano (brjanicek) and om2amr, and for the Claude sessions that help them. It also
keeps a copy of the rules from the maintainer's Claude memory, in case that memory is lost.

The short form of the git rules is in [CLAUDE.md](CLAUDE.md), and the rules for people are in
[CONTRIBUTING.md](CONTRIBUTING.md). The code map and the `data\` folder are described in
[docs/development.md](docs/development.md). This file covers everything around them: workflow, versions, style, names,
tests and the checks before a build.

> This repository is public. Do not put private things here: e-mail addresses, the station locator or coordinates,
> dongle serial numbers, server addresses, API keys. Private notes and plans go to the private repository
> `om2amr/RADIMCOM-todo` (folder `C:\RADIMCOM\todo\`, ignored in this repository).

---

## 1. Language

- Code, comments, docs, changelog, commit messages and UI texts are in **English**.
- Chat with om2amr is in **Slovak** (Claude answers in Slovak unless asked otherwise).
- Menu paths are written with `›`: *SETTINGS › GENERAL › BACKUP*. In INSTALL.txt (plain text) use `>`.
- Key names are written as on the key, in capitals: **AGC+**, **DEC**, **REC SQ**, **NO SDR**.

## 2. Branches and versions

- `main` holds only releases. Work goes to the **current version branch**, now **`1.1rc3`**. Check
  `git branch -r` for the newest one.
- The order of versions: `1.1beta1` → `1.1beta2` → `1.1rc1` → `1.1rc2` → `1.1rc3` → `1.1`. rc sorts between beta and release
  (`update_check._key`: `1.1rc1` → `(1, 1, 0, 101)`; the setup's file version is then `1.1.0.101`).
  Never use a version number that compares lower than the last release (that is why 0.115 was followed by 1.0, not 0.2).
- The version is the `.r-ver` text in `static/index.html` (`Ver. 1.1rc3`). The installer, the update check and the
  *What's new* window all read it from there.
- Only om2amr decides when the version goes up. Do not ask about it or bump it on your own.

### A new beta or rc (maintainer)

1. Commit and push the old branch, then build its setup.
2. **Lock** the old branch on GitHub (branch protection `lock_branch` + `enforce_admins`), for example:
   ```
   gh api -X PUT repos/om2amr/RADIMCOM/branches/<old>/protection --input - <<'EOF'
   {"required_status_checks":null,"enforce_admins":true,"required_pull_request_reviews":null,"restrictions":null,"lock_branch":true}
   EOF
   ```
3. `git switch -c <new>` from the last commit of the old branch, then make these changes:
   - **New beta:** add new sections `Ver. <new>` to `CHANGELOG.md` and `installer/INSTALL.txt`.
   - **rc:** rename the sections of the last beta to `Ver. <rc>`. Earlier betas keep their own sections.
   - Set `.r-ver` to the new version.
   - In `docs/block_diagram.py`, update the caption (`... Ver. <new>`) and run `python docs/block_diagram.py`, which
     redraws `docs/images/block_diagram.png` (Chrome or Edge is needed).
   - Put the branch name in `CLAUDE.md` (4 places) and in `CONTRIBUTING.md` (the example).
4. Commit, then `git push -u origin <new>`, then build the setup.
5. Betas and rcs get **no GitHub release**, only the branch. Brano's PRs go to the new branch from then on.

### A release (maintainer)

1. Merge the rc branch into `main` with a merge commit.
2. Fold the beta and rc sections into one `Ver. 1.x` section that describes the end state: **Main Features**, then
   **Changes** grouped by block (`####`), then **Fixes**.
3. Set `.r-ver` to `Ver. 1.x`.
4. Build the setup and run `gh release create v1.x dist\RADIMCOM_Setup_v1.x.exe --title "RADIMCOM Ver. 1.x" --notes-file dist\RELEASE_NOTES_v1.x.md`.
   The release has **only the Setup exe**: no zips and no sources zip. The asset name must be exactly
   `RADIMCOM_Setup_v<ver>.exe`, because the update check looks for it.
5. Lock the beta and rc branches.

## 3. Git workflow

### Brano (pull requests from the fork)

1. Start each topic on a new branch: `git fetch upstream && git switch -c <topic> upstream/1.1rc3`.
2. One topic per branch and per PR. Keep it short: days, not weeks.
3. Before the PR, and whenever the maintainer asks: `git fetch upstream && git rebase upstream/1.1rc3`, then
   `git push --force-with-lease` (to your own topic branch only). Never merge the version branch into the topic.
4. Open the PR against the version branch, not `main`.
5. Write the changelog text in the PR description under `## Changelog`. **Do not edit** `CHANGELOG.md`,
   `installer/INSTALL.txt`, the version number, `installer/make_installer.py` or release packages.
6. After the merge, delete the topic branch and start the next topic from step 1.

### om2amr (directly on the version branch)

- The local git config has `pull.rebase=true`, `rebase.autoStash=true`, `rerere.enabled=true` and `fetch.prune=true`.
- Pull before starting work and again before every push. Commit in small steps. **Never force-push** the version branch
  or `main`.
- If a PR conflicts, ask Brano to rebase (step 3). Do not resolve the conflict in the merge.
- After a merge:
  - copy the PR's `## Changelog` text into `CHANGELOG.md` and `installer/INSTALL.txt` with the credit "*by Brano*";
  - add a README line and the Contributors line where the feature is notable;
  - check that the new files are in the `CODE` list of `installer/make_installer.py` (this has been missed before).

### "setup, commit, push" (what om2amr means by it)

1. `git fetch` and `git pull`, so merged PRs come in first.
2. Run the checks of section 9 on everything.
3. Commit **all** uncommitted and untracked files in the working tree, also the work of other sessions. Several commits
   by topic are better than one big one.
4. Pull again (rebase), then `git push`.
5. Build the setup (`python installer/make_installer.py`) after the push, so it contains the rebased state.
6. Say what was included.

### Never commit

These are ignored, see `.gitignore`:

- `data\` (settings, memories, logs and recordings of the station)
- `dist\`, `lib\`, `apps\`, `drivers\` (third-party binaries)
- `backup\`, `todo\`, `.venv\`
- the development `RADIMCOM.exe` with its WebView2 DLLs
- anything from your own station

Do not touch line endings: `.gitattributes` (`* text=auto`) handles them, and the index is LF.

## 4. Keeping conflicts away

- A new feature goes in **its own module** (`xyz.py`, its own JS block and its own CSS block). Add only the few lines
  needed to register it in the shared files `app.py`, `launcher.py`, `static/app.js`, `static/index.html` and
  `static/style.css`.
- Do not reformat, reorder, move or rename existing code in the shared files. A change like that is agreed first and
  done while no PR is open.
- Brano's areas (memory editor, rtl_tcp and `rpi/`, COMPOSITE map) are changed only after agreeing with him.

## 5. Changelog and documentation

- **Changelog** goes in two places, under the section of the version shown in the UI:
  - `CHANGELOG.md`: detailed, Markdown.
  - `installer/INSTALL.txt`: short, plain text, lines up to about 120 characters. The setup shows this section in the
    *What's new* window, so its header must match `.r-ver` exactly, for example `Ver. 1.1rc1`.
- When to write it: once a **topic is finished**, meaning om2amr moves on or says it is OK. Do not write it after every
  tuning step, and do not leave it until the commit either.
- A version section has these parts:
  - **Main Features** first (with the credit for contributors);
  - then **Changes**, including UI and look changes, not only new functions;
  - then **Fixes**.
- **Docs** (`docs/*.md`, `README.md`): only after a feature is tuned and confirmed.
  - New functions go to `docs/features.md` and to their detail page: `controls.md`, `configuration.md`,
    `installation.md`, `decoders/*.md`, `satellites.md`, `composite.md`, `propagation.md`.
  - A notable function also gets one README line.
  - Text that describes the old behaviour must be fixed or removed: grep `docs/` for it.
- **Credits** that must stay:
  - Brano (memory editor, rtl_tcp, COMPOSITE, …);
  - the VDL2 ground station list: source https://acars-vdl2.groups.io/, with the line "Thank you Sergi for amazing work"
    and the request to report new stations, in the file header, README, CHANGELOG and INSTALL.txt;
  - Open-Meteo.com (GFS, NOAA), CC-BY 4.0, on the sonde map and in the docs;
  - ionosondes GIRO / KC2G, CC BY-NC-SA;
  - Natural Earth (`countries.json`);
  - OpenStreetMap on every map;
  - the third-party programs in `NOTICE.md`. When a bundled binary changes, update its version in `NOTICE.md`.

## 6. Names in the UI

Use these names in code comments, docs and the changelog.

**Head of the panel** (fixed layout "A · REFERENCE"; no layout switcher):

- S-meter;
- the **VFO windows A–D**, with the VFO keys under them;
- the clock and A/D display;
- **function keys** as 2-row modules: MODE, GAIN (AGC, **AGC+**), TUNE (ATU), STEP, DECODE (**DEC**, **COM**), AUDIO,
  TRACKING, MENU (**SET** gear, **MEM**, **BAND**), VIEW;
- the master column (logo, MONITOR with the MAIN / CUE faders, RECORD);
- the band keys at full width.

The lower part (the tabs) must look like a display sunk into the panel.

**Bottom tabs:** SPECTRUM, DECODERS, SATELLITES, SETTINGS, MEMORIES, RECORDINGS, SCAN, ROTOR CONTROL, PROPAGATION,
COMPOSITE, and the DAB and DSD tabs, which exist only while that mode is on. A red **×** closes a tab and switches its
key off.

**DECODERS pages**, in groups:

- HF digital: CW, FT8, PACKET, POCSAG, RTTY, SSTV, WEFAX, WSPR
- aircraft: ACARS, ADS-B, HFDL, VDL2
- ships: AIS
- radiosondes: SONDE
- ISM

Only **one decoder runs per VFO**. The tab names the running one (*DECODERS FT8*) and its key has a green bar.
DAB and DSD are modes (MODE), not decoders.

**SETTINGS pages:**

- **GENERAL**: SKINS, S-METER, TUNING, LOCATION, ANTENNAS, ROTOR, RECORDINGS, BACKUP
- **STATION**: block scheme of the receiver
- **SDR SOURCES**: drag sources onto VFO A–D; DIRECTORY of SpyServers
- **VFO**: VFO keys joined to the card of that VFO: dongle, AUDIO, TX, RX CHAIN
- **RTL_TCP SERVER**
- **DATA/LOG**

**SATELLITES pages:** PASSES, MAP, TRACK, SETUP.

**Decoder maps:** FT8, WSPR, PACKET, ACARS / VDL2, HFDL, AIS, ADS-B, SONDE and COMPOSITE. On these maps:

- the view (centre and zoom) is kept;
- the **□** key opens the map alone in a new tab: `?map=<kind>&vfo=A` (`MAP_ONLY`; that tab saves nothing to the
  browser);
- the bubbles are dark;
- a click on a mark or on its label draws a red dotted line from the QTH to it.

**Windows (RADIMCOM.exe):**

- the start splash *Starting / Restarting RADIMCOM…*;
- the SDR setup (`setup_web.py`, port 8433), in a window in the middle of the screen. It starts by itself when
  `data\vfos.json` is missing;
- the *What's new* window (`.wn-win`), shown on the first start of a new version.

**Statuses:** a VFO without a source shows **NO SDR** (driver `"none"`, dark, silent). A paused SpyServer shows
**PAUSED**.

## 7. Style of the code

### General

- Comments explain **why** and what the user sees, in plain English sentences. A function gets a short `"""docstring"""`
  in Python or a `/** … */` comment in JS.
- Keep the existing style of the file: names, quotes, spacing. Do not reformat.
- New UI texts are short. A long explanation goes into the tooltip (`title`).

### Python

- Paths to the data of the station always go through `paths.data(...)`, never as hard-coded paths.
- Every helper exe started from a VFO process needs `stdin=subprocess.DEVNULL`. The VFO's stdin is the pipe from the
  launcher, and a child that inherits it hangs at start (wsprd did).
- Ports:
  - launcher (the page): **8434**;
  - VFO processes: 8441–8444 (`app.py --vfo A..D`, port + 7 for A);
  - SDR setup: 8433.
- RADIMCOM.exe stops the server by closing its stdin (`RADIMCOM_SHELL`). Exit code **75** means restart, or the SDR
  setup when `vfos.json` is missing.
- Never send the station location to an outside service. For example, sonde wind is asked only for the cells along the
  sonde path.
- `installer/shell/RADIMCOM.cs` is compiled by the .NET Framework `csc`, so it is **C# 5 only** (no `$""`, no `?.`).

### JavaScript (`static/app.js`, one file, sections marked `// ---------- NAME ----------`)

- Helpers:
  - `$(id)` gets an element;
  - `escHtml()` escapes **every** text that goes into HTML;
  - `store(key, value)` / `recall(key)` read and write localStorage; `store` does nothing in a `MAP_ONLY` tab;
  - `satFetch()` and `fetch(vbase + "/api/…")` call the active VFO;
  - `send({...})` sends changes to the VFO.
- Remembered per VFO: keys like `decPage_A`.
- Maps (Leaflet 1.9.4 in `static/leaflet/`):
  - darkened OSM tiles with `className: "hfdl-dark"`;
  - `mapPopout(map, kind)` gives the view keep and the □ key;
  - `mapQthLink(map, qth)` and `mapLabelClicks(map)` give the dark bubbles, the line from the QTH and clickable labels;
  - `ft8LocGrid(map)` draws the locator grid.
- Leaflet pitfall: `layer.isTooltipOpen()` throws on a layer without a tooltip. Ask `getTooltip()` first.

### CSS (`static/style.css`)

- Colours come from the variables in `:root`:
  - background and lines: `--bg`, `--bezel`, `--screen`, `--line`, `--line2`;
  - text: `--text`, `--muted`, `--dim`;
  - colours: `--green`, `--yellow`, `--amber`, `--orange`, `--red`, `--blue`, `--ok`, `--accent`;
  - keys: `--key-a`, `--key-b` and the lit ones `--key-on-a`, `--key-on-b`.
  Use them; new fixed colours only where the existing blocks also use them.
- `color-scheme: dark`. The page is drawn in a virtual window scaled by `--k` (`fitStage`).
- Meaning of colours:

  | Colour | Means |
  | --- | --- |
  | green | on, running, OK, CQ |
  | amber | a warning to act on, a key that waits |
  | grey | information |
  | red `#ff4b3c` | selected mark, line from the QTH |
  | `#ff5a3c` with a black border | the QTH mark |
  | cyan `#5fd7ff` | calls, serial numbers |

- Popups and bubbles: dark `#11151b`, text `#d6dde5`, border `var(--line)`, class `ft8-popup`.
- Labels on maps: `.ft8-label`, `.ais-label`, `.hfdl-label` (dark, thin border).
- A feature's styles stay in their own block with a comment, for example `/* AIS */`, `.bk-*` for BACKUP, `.ais-*`.

### Diagrams and screenshots

`docs/block_diagram.py` draws the receiver scheme, `docs/cw_diagram.py` the CW diagram, and `docs/annotate.py` labels
screenshots.

## 8. Tests

They are in `tests/` and run from the RADIMCOM folder with the `.venv` Python. pytest is not installed; use unittest:

```
python -m unittest discover -s tests          # all, about 2 minutes, 202 tests
python -m unittest tests.test_sagc            # one module
```

| Test | What it covers |
| --- | --- |
| `test_sagc` | AGC+ (gainctl.py) on a simulated R820T front end: climbs while it does not clip, no hunting, gain wasted on a noisy band, holds a strong station at the clipping limit, recovery after a burst, presets |
| `test_scanner` | the scanner (squelch, hold, priority, FM broadcast centring) |
| `test_cw`, `test_packet`, `test_packet_demod`, `test_aprs`, `test_pocsag`, `test_hfdl`, `test_ais`, `test_adsb`, `test_ism`, `test_sonde` | the decoders |
| `test_dnr`, `test_nb`, `test_hum`, `test_lpf`, `test_sam`, `test_tonesq`, `test_atu` | the DSP blocks |
| `test_recorder`, `test_datafiles`, `test_antennas`, `test_rotor_settings` | files and settings |

Benches for tuning (not unit tests):

- `tests/cw_bench.py` and `tests/rtty_bench.py` (`--old <file>` compares with the old version);
- `tests/sonde_replay.py`.

Run the bench before and after you change a decoder's thresholds.

AGC+ is tuned **only on real signals**. Do not change `gainctl.py` because a simulated test fails: adjust the test to the
intended behaviour instead. The current smart clipping was tuned for hours on real short-wave signals.

## 9. Checks before a commit and before the build

1. Python syntax: `python -m py_compile <changed .py files>`.
2. JS syntax: `node --check static/app.js` (Node.js LTS is installed).
3. Tests: `python -m unittest discover -s tests`. All must pass. If one fails, find out why before you change the test.
4. Look at the diff for private data:
   - the callsign or e-mail in places that were not asked for;
   - API keys, the locator or coordinates of the station.
5. Scan the changed files for **lone CR or backspace bytes**. A Python script fed through a bash heredoc eats `\\`, so
   Windows paths such as `data\recordings` broke into `data<CR>ecordings`, and `\b` became a backspace. For text with
   backslashes use an editor, or a script file with `chr(92)`.
6. A new module or data file must be in the `CODE` list of `installer/make_installer.py`, or it will be missing from the
   setup.
7. `python installer/make_installer.py` (no arguments) builds `dist\RADIMCOM_Setup_v<ver>.exe` with Inno Setup.
   While building, it **fails** if the callsign appears in the package anywhere except the allowed strings (`FORBIDDEN` /
   `ALLOWED`): the page signature, the GitHub links and the LICENSE copyright line.
   `--exe` only rebuilds the development `RADIMCOM.exe` in the repository root.

### What to reload after a change

| Changed | Needed |
| --- | --- |
| only `static/` (`app.js`, `index.html`, `style.css`) | refresh the page (**Ctrl+F5**) |
| any `.py` file, or configuration read at start | **restart the server** (and Ctrl+F5) |
| `installer/shell/RADIMCOM.cs` | rebuild `RADIMCOM.exe` while it is closed |

## 10. Useful facts

- **Settings backup:** SETTINGS › GENERAL › BACKUP (`backup.py`). It saves VFO settings, sources, memories, station,
  satellites, ISM devices, map keys and the page settings. Map API keys (`data\mapkeys.json`) are secret and not ticked
  by default. A factory reset first saves a full backup to `RADIMCOM\backup\`.
- **SDR drivers:** `rtl`, `lime`, `airspy`, `rtltcp`, `spyserver`, and `none` (no source). SpyServer sources have the
  serial `host:port`, and a narrow band is upsampled (the HF+ 228 kS/s ×4).
- **AGC+** (`gainctl.py`, *smart clipping*, on by default except for SpyServer and rtl_tcp):
  - The mean clipping over 1 s decides; the limit is `clip_ppm` 1000 = 0.1 %.
  - Under the limit it tries the next tuner step. A failed try goes back and sets a ceiling, held longer after every
    failure (20, 40, 80 … s, at most 300 s).
  - ADS-B keeps the headroom logic.
- **Helper programs** in `lib\`:
  - `wsprd.exe` is built in MSYS2 **UCRT64** with `installer/build_wspr.sh`, statically linked;
  - `dumphfdl.exe` is built with `installer/build_hfdl.sh`;
  - DSD-FME is installed by `install_dsd.py`.
  `lib\` is not in git; the setup takes these files from the PC that builds it.
- **Rotor:** K3NG with GS-232. Do not send it backslash commands: its firmware starts a debug dump on them. Its settings
  are station-wide in `data\rotor.json`, and the port is held by VFO A.
- **Gpredict was removed** (replaced by our own satellite tracking). Do not bring it or the hamlib servers back.
- **No switchable layouts:** the head layout is fixed until om2amr says otherwise.
