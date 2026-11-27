# Notices

This file is not part of the licence terms in [LICENSE](LICENSE).

## Radio transmission notice

The Software can control radio transmitting hardware. Transmitting is legal only for a holder of a valid licence or
other authorisation required in the country of operation, within its privileges and the applicable regulations (ITU,
CEPT, FCC or the national authority). The operator is fully and solely responsible for every transmission and its
consequences. Anyone who modifies or removes the transmit frequency limits of the Software is solely responsible for
any transmission outside the bands they are licensed for.

## Third-party components

The code of RADIMCOM itself is under the MIT License. The components below keep their own licences. The git repository
does not contain the binaries; the release packages do, except where noted.

| Component | Used for | Licence | Source |
|---|---|---|---|
| dumpvdl2 2.7.0 | VDL2 decoder (separate program) | GPL v3 | <https://github.com/szpajder/dumpvdl2> |
| libacars 2.2.1 | used by dumpvdl2 and dumphfdl | MIT | <https://github.com/szpajder/libacars> |
| dumphfdl 1.7.0 (with its ground station table `systable.conf`) | HFDL decoder (separate program) | GPL v3 | <https://github.com/szpajder/dumphfdl> |
| wsprd from WSJT-X 2.7.0 (K1JT, K9AN and the WSJT Development Group), not changed, built statically by `installer/build_wspr.sh` with FFTW 3.3.11 and the GCC runtime | WSPR decoder in `lib\wspr` (separate program, reads a WAV file of each 2-minute cycle) | GPL v3 (FFTW: GPL v2 or later; GCC runtime: GPL with GCC Runtime Library Exception) | <https://sourceforge.net/projects/wsjt/> |
| jt9 from WSJT-X 2.7.0 (K1JT and the WSJT Development Group), sources not changed (the Qt shared memory replaced by a stub), built statically by `installer/build_jt9.sh` with FFTW 3.3.11, Boost.CRC and the GCC runtime | Q65 / JT65 decoder in `lib\jt9` (separate program, reads a WAV file of each T/R period) | GPL v3 (FFTW: GPL v2 or later; Boost: BSL 1.0; GCC runtime: GPL with GCC Runtime Library Exception) | <https://sourceforge.net/projects/wsjt/> |
| LDPC (128,90) code tables of WSJT-X (`ldpc_128_90_reordered_parity.f90`, `ldpc_128_90_generator.f90`; K1JT and the WSJT Development Group), converted to Python in `msk144_ldpc.py` | MSK144 decoder (`msk144.py`, own code) | GPL v3 (that file) | <https://sourceforge.net/projects/wsjt/> |
| liquid-dsp 1.8.3 | used by dumphfdl | MIT | <https://github.com/jgaeddert/liquid-dsp> |
| rs1729 radiosonde decoders (RS, commit ce44855, `demod/mod`: rs41mod, dfm09mod, m10m20mod, lms6Xmod, imet54mod, mp3h1mod, meisei100mod, mts01mod, cf06ht03mod), not changed, built by `installer/build_sonde.sh` | radiosonde decoders in `lib\sonde` (separate programs, fed through a pipe) | GPL v3 | <https://github.com/rs1729/RS> |
| FFTW 3.3.10 | used by dumphfdl | GPL v2 or later | <https://www.fftw.org> |
| libconfig 1.7.3 | used by dumphfdl | LGPL v2.1 or later | <https://github.com/hyperrealm/libconfig> |
| welle-cli (welle.io 2.7), **modified** (`installer/welle_radimcom.patch`) | DAB / DAB+ decoder (separate program) | GPL v2 or later | <https://github.com/AlbrechtL/welle.io> |
| rtl_433 25.12 (release build of its author, not changed) | ISM decoder, 433 / 868 MHz (separate program) | GPL v2 or later | <https://github.com/merbanan/rtl_433> |
| rtl-sdr 2.0.2, libusb 1.0.29 | linked into `rtl_433.exe` | GPL v2 or later; LGPL v2.1 or later | <https://github.com/osmocom/rtl-sdr>, <https://github.com/libusb/libusb> |
| FFTW, FAAD2 | used by welle-cli | GPL v2 or later | MSYS2 packages |
| mpg123, LAME | used by welle-cli | LGPL | MSYS2 packages |
| MSYS2 runtime | runs dumpvdl2 and dumphfdl | LGPL v3 | <https://github.com/msys2/msys2-runtime> |
| GLib, libiconv, gettext (libintl) | used by dumpvdl2 and dumphfdl | LGPL | MSYS2 packages |
| libxml2, PCRE2, zlib, winpthreads | used by dumpvdl2, dumphfdl and welle-cli | MIT, BSD, zlib | MSYS2 packages |
| GCC runtime libraries | used by dumpvdl2, dumphfdl and welle-cli | GPL with GCC Runtime Library Exception | MSYS2 packages |
| librtlsdr | RTL-SDR access | GPL v2 or later | see the note below |
| libusb 1.0.29 | USB access for librtlsdr | LGPL v2.1 or later | <https://github.com/libusb/libusb> |
| Zadig 2.4 | installs the WinUSB driver | GPL v3 | <https://github.com/pbatard/libwdi> (tag `b721`) |
| LimeSuite | LimeSDR access | Apache 2.0 | <https://github.com/myriadrf/LimeSuite> |
| libairspy | Airspy access | BSD 3-Clause | <https://github.com/airspy/airspyone_host> |
| pthreads-win32 | used by airspy.dll | LGPL v2.1 or later | <https://sourceware.org/pthreads-win32/> |
| FTDI D3XX driver | LimeSDR USB driver | FTDI driver licence | <https://ftdichip.com/drivers/d3xx-drivers/> |
| PyFT8 | FT8 decoder; in the Python of the setup (`python\`), `install.bat` installs it from PyPI | GPL v3 or later | <https://github.com/G1OJS/PyFT8m> |
| Flask, NumPy, SciPy, pyserial | Python packages; in the Python of the setup (`python\`), `install.bat` installs them from PyPI | BSD (NumPy/SciPy include OpenBLAS: BSD, GCC runtime: GPL with GCC Runtime Library Exception) | PyPI |
| Python 3.13 | runs RADIMCOM; the setup brings it in `python\` (NuGet package "python") | PSF License | <https://www.python.org> |
| Microsoft Edge WebView2 SDK | the app window of `RADIMCOM.exe` (`Microsoft.Web.WebView2.*.dll`, `WebView2Loader.dll`) | Microsoft WebView2 SDK licence (`WebView2_LICENSE.txt`), redistributable | <https://www.nuget.org/packages/Microsoft.Web.WebView2> |
| rs1729 radiosonde decoders (RS) | not included: the M10 / M20 frame layouts, checksum, serial numbers, temperature, humidity and pressure (m10mod.c, m20mod.c; the M20 humidity is DF9DQ's formula from ra-firmware) and the DFM serial, type, temperature and battery (dfm09mod.c, conf_out) were reimplemented in `sonde.py` after them | GPL v3 | <https://github.com/rs1729/RS> · <https://github.com/projecthorus/radiosonde_auto_rx> |
| SondeHub launch sites | radiosonde launch sites on the SONDE map: downloaded at run time from `api.v2.sondehub.org/sites` into `data/sonde_sites.json`, not part of the package; type names from the SondeHub tracker | tracker code MIT | <https://sondehub.org> · <https://github.com/projecthorus/sondehub-tracker> |
| uPlot 1.6.31 | charts of the ISM device tab; in `static/uplot` | MIT (`static/uplot/LICENSE`) | <https://github.com/leeoniya/uPlot> |
| Leaflet 1.9.4 | map for choosing the station place (SATELLITES tab, SETUP); in `static/leaflet` | BSD 2-Clause (`static/leaflet/LICENSE`) | <https://leafletjs.com> |
| Natural Earth 1:50m land and country borders | world map (SATELLITES tab, MAP); simplified in `static/world.js` by `installer/make_world.py` | public domain | <https://www.naturalearthdata.com/> |
| Natural Earth 1:50m admin 0 countries | the country of a SpyServer in SETTINGS › SDR SOURCES › DIRECTORY; outer borders simplified in `countries.json` by `installer/make_countries.py` | public domain | <https://www.naturalearthdata.com/> |
| sgp4 | satellite positions (SATELLITES tab, PASSES); in the Python of the setup (`python\`), `install.bat` installs it from PyPI | MIT | <https://github.com/brandon-rhodes/python-sgp4> |
| lameenc (with the LAME MP3 encoder) | MP3 recording; in the Python of the setup (`python\`), `install.bat` installs it from PyPI | LGPL v3 or later (LAME: LGPL) | <https://github.com/chrisstaite/lameenc> |
| OpenFlights airline database (`openflights_airlines.dat`) | ATC speech to text: the radio telephony of the airlines → ICAO callsigns (`atc.py`) | Open Database License (ODbL) 1.0 | <https://openflights.org/data> |
| faster-whisper 1.2.1 (with CTranslate2, PyAV, ONNX Runtime, tokenizers, huggingface_hub) | ATC speech to text; not in the package: downloaded from PyPI into `lib\whisper` by the setup's optional task or `install_atc.bat` | MIT (PyAV: BSD 3-Clause, FFmpeg in it: LGPL v2.1 or later; tokenizers, huggingface_hub, CTranslate2: Apache 2.0 / MIT) | <https://github.com/SYSTRAN/faster-whisper> |
| Whisper model fine-tuned on ATC speech (`jacktol/whisper-medium.en-fine-tuned-for-ATC-faster-whisper`, from OpenAI Whisper medium.en) | ATC speech to text; not in the package: downloaded from Hugging Face into the user's cache | see its model card (Whisper: MIT) | <https://huggingface.co/jacktol/whisper-medium.en-fine-tuned-for-ATC-faster-whisper> |

### Not in the package: DSD-FME

The DSD mode uses [DSD-FME](https://github.com/lwvmobile/dsd-fme) (ISC, parts GPL v2; see `COPYRIGHT` there) as a separate
program. It is **not distributed with RADIMCOM**; `install_dsd.bat` downloads the release of its author into `lib\dsd-fme` at
the user's own decision. DSD-FME contains [mbelib](https://github.com/szechyjs/mbelib), an implementation of the AMBE+2 and IMBE
voice codecs. According to the mbelib notice, its functions may be covered by patents owned by Digital Voice Systems, Inc., and compiling or using it
may infringe patent rights in your jurisdiction and/or require a licence. Check this for your country before installing it.

### Source code

The source code of the GPL and LGPL components in a release, in the exact versions used, with the build instructions
(`installer/VDL2.txt`, `installer/DAB.txt`, `installer/build_dab.sh`, `installer/welle_radimcom.patch`), is available
**on request**: write to radim.mutina@gmail.com and name the RADIMCOM version. This offer is valid to anyone who received
that release, for at least three years after it was published. The source package is built by `installer/make_sources.py`
(its list of contents is `SOURCES.txt`); the releases Ver. 0.108 – 0.114 also have it attached as
`RADIMCOM_sources_v<version>.zip`.

**librtlsdr:** the exact source of the `librtlsdr.dll` in the packages is still being confirmed; ask for it at the same address.

### Data

- The VDL2 ground station list (`VDL2_Ground_Stations.txt`) comes from <https://acars-vdl2.groups.io/>, redistributed
  with approval.
- The airport tables in `airports.py` come from OurAirports (public domain).
- DNR NR4 (`nrx.py`) is own code after the ideas of libspecbleach (L. Romero, LGPL v2.1, <https://github.com/lucianodato/libspecbleach>); no code of it is used.
- The SATELLITES tab shows pages of AMSAT (<https://www.amsat.org/>), downloaded by the running program. They belong to AMSAT and are not in the repository or the release packages.
- The orbital elements for pass prediction (TLE, amateur group) come from CelesTrak (<https://celestrak.org/>), downloaded by the running program once a day into `data\sat_tle.txt`; they are not in the repository or the release packages.
- The list of satellite transmitters (SATELLITES tab, TRACK) comes from SatNOGS DB (<https://db.satnogs.org/>, Libre Space Foundation; data under CC BY-SA 4.0), downloaded by the running program once a week into `data\sat_transmitters.json`; it is not in the repository or the release packages.
- The PROPAGATION tab (PROP key) shows space weather from the NOAA Space Weather Prediction Center
  (<https://www.swpc.noaa.gov>, public domain), downloaded by the running program into `data\spacewx`, including the
  OVATION aurora forecast and its map of the northern hemisphere, shown as NOAA draws it.
- The same tab shows the newest values of the ionosondes near the station from GIRO, the Global Ionospheric Radio
  Observatory (Lowell DIDBase, <https://giro.uml.edu>, CC BY-NC-SA 4.0; B. W. Reinisch and I. A. Galkin, Global Ionospheric
  Radio Observatory (GIRO), Earth, Planets and Space 63, 377–381, 2011, doi:10.5047/eps.2011.03.001), as collected by KC2G
  (<https://prop.kc2g.com>), downloaded by the running program for its own use only. None of these data are in the repository
  or the release packages.
- The DX CLUSTER tab (DX key) shows the spots of the public DX cluster feed of HamQTH (<https://www.hamqth.com>), read by the
  running program at most once a minute and kept in memory for 30 minutes; nothing about the station is sent and the spots are
  not in the repository or the release packages.
- The magnetogram in the same tab shows the 1-minute values of the magnetometer of the Kiruna geophysical observatory of the
  Swedish Institute of Space Physics (IRF, <https://www2.irf.se/maggraphs/>), downloaded by the running program into
  `data\spacewx` for its own use only; they are not in the repository or the release packages.
- The detail of an aircraft on the COMPOSITE map shows a small photo from Planespotters.net (<https://www.planespotters.net>),
  asked for by the browser through its public photo API by the ICAO address or registration, shown as Planespotters.net asks:
  linked to its page there with the photographer's name. The photos stay with Planespotters.net and their photographers;
  only the answer (the link) is remembered in the browser for a week. None are in the repository or the release packages.
- The DIRECTORY list in SETTINGS › SDR SOURCES shows the public SpyServers of the Airspy receiver directory
  (<https://airspy.com/directory/>), downloaded by the running program only while that list is used (at most every 5 minutes)
  and kept in memory only; the owners' e-mail addresses are not shown. Nothing of it is in the repository or the release packages.
- The map for choosing the station place (SATELLITES tab, SETUP, CHOOSE ON MAP) shows tiles of OpenStreetMap (<https://www.openstreetmap.org/copyright>), © OpenStreetMap contributors, loaded by the browser from tile.openstreetmap.org only while that map is open; nothing of it is in the package.
- The vector maps of the decoder maps (Map settings › Vector maps, `vectormaps.py`) are downloaded by the running program only when the person presses Update, into `data\vectormaps`; none of them are in the repository or the release packages, and each is credited on the map while it is shown: openAIP (<https://www.openaip.net>, CC BY-NC 4.0, with the person's own API key), OurAirports (<https://ourairports.com>, public domain), OpenStreetMap through the Overpass API (<https://www.openstreetmap.org/copyright>, © OpenStreetMap contributors, ODbL), FUA areas and IFR waypoints of LPS SR, š. p. (<https://gis.lps.sk>, information only), IFR waypoints of DFS Deutsche Flugsicherung GmbH (CC BY 4.0), Austro Control (INSPIRE, no conditions) and Traficom (CC BY 4.0), and the Free Route Airspace points list of EUROCONTROL (<https://www.eurocontrol.int>, not for operational use).
