"""Builds RADIMCOM_Setup_v<version>.exe in the dist folder (new installation and upgrade, also of an older zip
installation). The old zips on request: RADIMCOM_install_v<version>.zip and RADIMCOM_upgrade_v<version>.zip
(program only: no config.json, install.bat or drivers, so data/ and the configuration stay untouched).
The version is taken from the logo in static/index.html (<span class="r-ver">Ver. 0.1xx</span>); the folder in the zip stays RADIMCOM.

  python installer/make_installer.py                 (setup)
  python installer/make_installer.py --zips          (setup and the zips; --zip-only: only the zips)
  python installer/make_installer.py --exe           (RADIMCOM.exe for this development copy)
  python installer/make_installer.py --upgrade-from dist/RADIMCOM_install_v0.103.zip   (upgrade zip from an older full zip)

Only the program, web interface, libraries and drivers go into the package. Not the settings of this PC
(vfos.json, config_X.json, memories, EEPROM backups, recordings); the new PC creates those during installation.
"""
import ast
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TOP = "RADIMCOM"


def read_version():
    html = open(os.path.join(ROOT, "static", "index.html"), encoding="utf-8").read()
    m = re.search(r'class="r-ver">\s*Ver\.\s*([0-9.]+(?:beta\d+)?)\s*<', html)
    if not m:
        sys.exit("version not found in static/index.html (.r-ver)")
    return m.group(1)


VERSION = read_version()
DIST = os.path.join(ROOT, "dist")
OUT = os.path.join(DIST, f"RADIMCOM_install_v{VERSION}.zip")
SETUP_OUT = os.path.join(DIST, f"RADIMCOM_Setup_v{VERSION}.exe")
# setup: Python and WebView2 from NuGet, kept in installer/cache
CACHE = os.path.join(HERE, "cache")
PYTHON_VERSION = "3.13.14"
WEBVIEW2_VERSION = "1.0.4258.31"
WEBVIEW2_FILES = {"Microsoft.Web.WebView2.Core.dll": "lib/net462/Microsoft.Web.WebView2.Core.dll",
                  "Microsoft.Web.WebView2.WinForms.dll": "lib/net462/Microsoft.Web.WebView2.WinForms.dll",
                  "WebView2Loader.dll": "runtimes/win-x64/native/WebView2Loader.dll"}
CSC = os.path.expandvars(r"%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe")
ICON = os.path.join(HERE, "radimcom.ico")
# left out of the upgrade zip: the configuration template, the installer and the drivers
UPGRADE_SKIP_FILES = ("config.json", "install.bat")
UPGRADE_SKIP_DIRS = ("data/", "drivers/")
UPGRADE_TXT = r"""RADIMCOM - upgrade
==================
This zip updates an existing RADIMCOM installation. It contains only the program;
your settings, memories, logs and recordings (data\ folder) and the configuration are not touched.

1. Close the receiver.
2. Unzip into the folder that CONTAINS your RADIMCOM folder (e.g. C:\ for C:\RADIMCOM)
   and allow overwriting files.
3. Run upgrade.bat in the RADIMCOM folder (updates the Python packages if needed).
4. Start the receiver as usual.

New program folders (e.g. lib\dab with the DAB decoder) come with the zip as well.

DSD mode (digital voice, first test version, it still needs more testing): its decoder DSD-FME is not in this zip.
If you have it in lib\dsd-fme, it stays there and nothing has to be done. If not and you want it, run install_dsd.bat:
it shows a patent notice and downloads it.

What is new: see INSTALL.txt or CHANGELOG.md.
"""
UPGRADE_BAT = r"""@echo off
rem RADIMCOM upgrade: updates the Python packages in .venv; data\ and the configuration stay untouched.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (echo .venv not found - for a new installation use the install zip and install.bat & pause & exit /b 1)
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check --only-binary=numpy,scipy,lameenc -r requirements.txt
if errorlevel 1 (echo Package installation failed - check the internet connection. & pause & exit /b 1)
echo Upgrade done. Start the receiver with the RADIMCOM shortcut (or start.bat).
if not exist "lib\dsd-fme\dsd-fme.exe" echo Optional, for the DSD mode (digital voice): run install_dsd.bat, it downloads the decoder.
pause
"""


def make_upgrade(full_zip):
    """Upgrade zip from a full install zip: the same files without the configuration, installer and drivers."""
    out = os.path.join(os.path.dirname(full_zip), os.path.basename(full_zip).replace("_install_", "_upgrade_"))
    if out == full_zip:
        sys.exit("not an install zip: " + full_zip)
    n = 0
    with zipfile.ZipFile(full_zip) as src, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as dst:
        for info in src.infolist():
            rel = info.filename.split("/", 1)[1] if "/" in info.filename else info.filename
            if rel in UPGRADE_SKIP_FILES or rel.startswith(UPGRADE_SKIP_DIRS) or info.is_dir():
                continue
            dst.writestr(info, src.read(info))
            n += 1
        dst.writestr(f"{TOP}/UPGRADE.txt", UPGRADE_TXT.replace("\n", "\r\n"))
        dst.writestr(f"{TOP}/upgrade.bat", UPGRADE_BAT.replace("\n", "\r\n"))
    print(f"{out}: {n + 2} files, {os.path.getsize(out) / 1e6:.1f} MB")


CODE = ["app.py", "launcher.py", "paths.py", "serverlog.py", "sdr.py", "autotune.py", "lime.py", "airspy.py", "rds.py", "cw.py", "rtty.py", "packet.py", "pocsag.py", "sonde.py", "aprs.py", "daylog.py", "ft8.py", "wefax.py", "sstv.py", "acars.py", "cpdlc.py", "cpdlc_schema.py", "adsc.py", "vdl2.py", "hfdl.py", "ais.py", "adsb.py", "tonesq.py", "scanner.py", "airports.py", "dab.py", "ism.py", "dsd.py", "recorder.py", "install_dsd.py", "install_dsd.bat",
        "memories.py", "satellites.py", "update_check.py", "sattrack.py", "satplan.py", "location.py", "sysload.py", "rotor.py", "iqshare.py", "eeprom_tool.py", "setup_sdr.py", "setup_web.py", "start.bat", "setup.bat", "README.md", "CHANGELOG.md",
        "LICENSE", "NOTICE.md", "API/API.md"]
LIBS = ["lib/librtlsdr.dll", "lib/libusb-1.0.dll"]
# VDL2: dumpvdl2 built with MSYS2 (see installer/VDL2.txt), with its MSYS2 runtime DLLs
LIBS += ["lib/vdl2/" + f for f in ("dumpvdl2.exe", "msys-2.0.dll", "msys-acars-2-2.dll", "msys-gcc_s-seh-1.dll",
                                   "msys-glib-2.0-0.dll", "msys-iconv-2.dll", "msys-intl-8.dll", "msys-pcre2-8-0.dll",
                                   "msys-xml2-16.dll", "msys-z.dll")]
# DAB: welle-cli built with MSYS2 UCRT64 (see installer/DAB.txt) with its DLLs - everything in lib/dab
LIBS += sorted("lib/dab/" + f for f in os.listdir(os.path.join(ROOT, "lib", "dab"))
               if f.lower().endswith((".exe", ".dll"))) if os.path.isdir(os.path.join(ROOT, "lib", "dab")) else []
# ISM: the static rtl_433 of its release (see installer/ISM.txt), no DLLs needed
LIBS += ["lib/ism/rtl_433.exe"]
# HFDL: dumphfdl built with MSYS2 (installer/build_hfdl.sh, see installer/HFDL.txt) with its DLLs and ground station table
LIBS += sorted("lib/hfdl/" + f for f in os.listdir(os.path.join(ROOT, "lib", "hfdl"))
               if f.lower().endswith((".exe", ".dll", ".conf"))) if os.path.isdir(os.path.join(ROOT, "lib", "hfdl")) else []
FROM_INSTALLER = ["install.bat", "requirements.txt", "config.json", "DRIVERS.txt", "INSTALL.txt", "VDL2_Ground_Stations.txt"]
# files from this PC that are bundled (target in the package: source)
EXTERNAL = {
    "lib/LimeSuite.dll": r"C:\Program Files\PothosSDR\bin\LimeSuite.dll",
    "lib/airspy.dll": r"C:\Program Files\PothosSDR\bin\airspy.dll",
    "lib/pthreadVC2.dll": r"C:\Program Files\PothosSDR\bin\pthreadVC2.dll",   # needed by airspy.dll
    "drivers/zadig.exe": os.path.expanduser(r"~\Downloads\sdrsharp-x64\zadig.exe"),
}
D3XX_ZIP = os.path.expanduser(r"~\Downloads\FTD3XXDriver_WHQLCertified_v1.3.0.4_Installer.exe_.zip")
D3XX_EXE = "FTD3XXDriver_WHQLCertified_v1.3.0.4_Installer.exe"
# no station marks may remain in the package (serial numbers, recordings…) except the author's signature on the page
FORBIDDEN = [b"OM2AMR", b"om2amr", "OM2AMR".encode("utf-16-le")]
# signature, public repository link, copyright line in LICENSE (wanted by the author)
ALLOWED = [b"By Radim Mutina OM2AMR", b"github.com/om2amr/RADIMCOM", b"api.github.com/repos/om2amr/RADIMCOM", b"Copyright (c) 2026 Radim Mutina (OM2AMR)",
           b"img.shields.io/github/v/release/om2amr/RADIMCOM", b"img.shields.io/github/license/om2amr/RADIMCOM"]   # README badges


def copy(src, dst_rel, build):
    dst = os.path.join(build, dst_rel)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if dst.lower().endswith(".bat"):       # cmd.exe wants CRLF (with LF, labels and goto can misfire)
        with open(src, "rb") as f:
            body = f.read().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        with open(dst, "wb") as f:
            f.write(body)
        shutil.copystat(src, dst)
    else:
        shutil.copy2(src, dst)


def unpackaged_imports():
    """Local .py modules imported (also indirectly) by app.py / launcher.py that are not in CODE."""
    local = {f for f in os.listdir(ROOT) if f.endswith(".py")}
    seen, todo = set(), ["app.py", "launcher.py"]
    while todo:
        f = todo.pop()
        if f in seen:
            continue
        seen.add(f)
        with open(os.path.join(ROOT, f), encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                mods = [a.name for a in n.names]
            elif isinstance(n, ast.ImportFrom) and n.module and not n.level:
                mods = [n.module]
            else:
                mods = []
            todo += [m.split(".")[0] + ".py" for m in mods if m.split(".")[0] + ".py" in local]
    return sorted(seen - set(CODE))


def nuget(package, version):
    """A NuGet package (a zip) from the cache, downloaded the first time."""
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, f"{package}.{version}.nupkg")
    if not os.path.exists(path):
        url = f"https://api.nuget.org/v3-flatcontainer/{package}/{version}/{package}.{version}.nupkg"
        print(f"downloading {url}")
        with urllib.request.urlopen(url, timeout=120) as r, open(path + ".part", "wb") as f:
            shutil.copyfileobj(r, f)
        os.replace(path + ".part", path)
    return path


def build_shell(out_dir):
    """RADIMCOM.exe (installer/shell/RADIMCOM.cs) with the WebView2 DLLs into out_dir."""
    if not os.path.exists(CSC):
        sys.exit(f"missing {CSC} (.NET Framework 4.x)")
    with zipfile.ZipFile(nuget("microsoft.web.webview2", WEBVIEW2_VERSION)) as z:
        for name, member in WEBVIEW2_FILES.items():
            with z.open(member) as s, open(os.path.join(out_dir, name), "wb") as d:
                shutil.copyfileobj(s, d)
        with z.open("LICENSE.txt") as s, open(os.path.join(out_dir, "WebView2_LICENSE.txt"), "wb") as d:
            shutil.copyfileobj(s, d)
    refs = ["System.dll", "System.Drawing.dll", "System.Windows.Forms.dll", "System.Web.Extensions.dll",
            os.path.join(out_dir, "Microsoft.Web.WebView2.Core.dll"), os.path.join(out_dir, "Microsoft.Web.WebView2.WinForms.dll")]
    cmd = [CSC, "-nologo", "-target:winexe", "-platform:x64", "-optimize+", "-out:" + os.path.join(out_dir, "RADIMCOM.exe"),
           "-win32icon:" + ICON, "-resource:" + ICON + ",radimcom.ico"] + ["-r:" + r for r in refs] + [os.path.join(HERE, "shell", "RADIMCOM.cs")]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        sys.exit("csc failed:\n" + r.stdout + r.stderr)
    print(f"{os.path.join(out_dir, 'RADIMCOM.exe')}")


def python_runtime():
    """Python of the NuGet package "python" (a complete, relocatable Python without the installer) with the packages
    of requirements.txt and PyFT8, kept in the cache (a new one when the version or requirements change)."""
    req = open(os.path.join(HERE, "requirements.txt"), "rb").read()
    tag = hashlib.sha1(req + PYTHON_VERSION.encode() + b"PyFT8").hexdigest()[:10]
    out = os.path.join(CACHE, f"python-{PYTHON_VERSION}-{tag}")
    if os.path.exists(os.path.join(out, "python.exe")):
        return out
    tmp = out + ".tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    with zipfile.ZipFile(nuget("python", PYTHON_VERSION)) as z:
        for m in z.infolist():
            if m.filename.startswith("tools/") and not m.is_dir():
                dst = os.path.join(tmp, *m.filename[len("tools/"):].split("/"))
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                with z.open(m) as s, open(dst, "wb") as d:
                    shutil.copyfileobj(s, d)
    py = os.path.join(tmp, "python.exe")
    # -I: isolated, the user site-packages of this PC (%APPDATA%\Python) must not count as installed
    pip = [py, "-I", "-m", "pip", "install", "--disable-pip-version-check", "--no-warn-script-location"]
    subprocess.run(pip + ["--only-binary=numpy,scipy,lameenc", "-r", os.path.join(HERE, "requirements.txt")], check=True)
    subprocess.run(pip + ["--no-deps", "PyFT8"], check=True)      # FT8 decoder; PyAudio is not needed
    # the .exe launchers of the packages have the path of this build folder in them; python -m works without them
    shutil.rmtree(os.path.join(tmp, "Scripts"), ignore_errors=True)
    for dirpath, dirs, _ in os.walk(tmp):
        for d in [d for d in dirs if d in ("tests", "test") and "site-packages" in dirpath]:
            shutil.rmtree(os.path.join(dirpath, d), ignore_errors=True)
            dirs.remove(d)
    subprocess.run([py, "-I", "-c", "import flask, numpy, scipy, serial, lameenc, sgp4; print('python ok')"], check=True)
    for _ in range(30):              # the virus scanner still holds the new files for a while
        try:
            os.replace(tmp, out)
            break
        except PermissionError:
            time.sleep(2)
    else:
        shutil.copytree(tmp, out)
        shutil.rmtree(tmp, ignore_errors=True)
    return out


def numeric_version(v):
    """0.115beta1 -> 0.115.0.1, 0.115 -> 0.115.1.0 (Windows file versions are numbers; a beta is older than its release)."""
    m = re.fullmatch(r"(\d+)\.(\d+)(?:beta(\d+))?", v)
    return f"{m.group(1)}.{m.group(2)}." + (f"0.{m.group(3)}" if m.group(3) else "1.0")


def iscc():
    for p in (os.path.expandvars(r"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"),
              r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe", r"C:\Program Files\Inno Setup 6\ISCC.exe"):
        if os.path.exists(p):
            return p
    sys.exit("Inno Setup 6 not found (winget install JRSoftware.InnoSetup)")


def dsd_version():
    """VERSION of install_dsd.py: the setup offers to update an installed DSD-FME of another version."""
    m = re.search(r'^VERSION = "(\w+)"', open(os.path.join(ROOT, "install_dsd.py"), encoding="utf-8").read(), re.M)
    if not m:
        sys.exit("VERSION not found in install_dsd.py")
    return m.group(1)


def build_setup(build):
    """RADIMCOM_Setup_v<version>.exe: the staged program + Python + RADIMCOM.exe, by Inno Setup (installer/radimcom.iss)."""
    compiler = iscc()
    py = python_runtime()
    print("copying Python")
    shutil.copytree(py, os.path.join(build, "python"))
    build_shell(build)
    os.makedirs(DIST, exist_ok=True)
    cmd = [compiler, "/Qp", f"/DAppVersion={VERSION}", f"/DVersionNumeric={numeric_version(VERSION)}",
           f"/DBuildDir={build}", f"/DOutDir={DIST}", f"/DIconFile={ICON}", f"/DDsdVersion={dsd_version()}",
           os.path.join(HERE, "radimcom.iss")]
    print("Inno Setup (a few minutes: LZMA2 ultra)…")
    subprocess.run(cmd, check=True)
    print(f"{SETUP_OUT}: {os.path.getsize(SETUP_OUT) / 1e6:.1f} MB")


def stage(build):
    missing = [p for p in list(EXTERNAL.values()) + [D3XX_ZIP] if not os.path.exists(p)]
    if missing:
        sys.exit("missing: " + ", ".join(missing))
    lost = unpackaged_imports()
    if lost:
        sys.exit("imported but not in CODE: " + ", ".join(lost))
    for f in CODE + LIBS:
        copy(os.path.join(ROOT, f), f, build)
    for f in FROM_INSTALLER:
        copy(os.path.join(HERE, f), f, build)
    copy(os.path.join(HERE, "VDL2.txt"), "lib/vdl2/README.txt", build)   # licences and sources of dumpvdl2
    copy(os.path.join(HERE, "DAB.txt"), "lib/dab/README.txt", build)     # licences and sources of welle-cli
    copy(os.path.join(HERE, "ISM.txt"), "lib/ism/README.txt", build)     # licences and sources of rtl_433
    copy(os.path.join(HERE, "HFDL.txt"), "lib/hfdl/README.txt", build)   # licences and sources of dumphfdl
    shutil.copytree(os.path.join(ROOT, "static"), os.path.join(build, "static"))
    for dst, src in EXTERNAL.items():
        copy(src, dst, build)
    with zipfile.ZipFile(D3XX_ZIP) as z:
        with z.open(D3XX_EXE) as s, open(os.path.join(build, "drivers", D3XX_EXE), "wb") as d:
            shutil.copyfileobj(s, d)
    # check for traces
    bad = []
    for dirpath, _, files in os.walk(build):
        for f in files:
            data = open(os.path.join(dirpath, f), "rb").read()
            for ok in ALLOWED:
                data = data.replace(ok, b"")
            if any(x in data for x in FORBIDDEN):
                bad.append(os.path.relpath(os.path.join(dirpath, f), build))
    if bad:
        sys.exit("forbidden text found in: " + ", ".join(bad))


def make_zips(build):
    tmp = os.path.dirname(build)
    os.makedirs(DIST, exist_ok=True)
    if os.path.exists(OUT):
        os.remove(OUT)
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for dirpath, _, files in os.walk(build):
            for f in sorted(files):
                p = os.path.join(dirpath, f)
                z.write(p, os.path.relpath(p, tmp))
    n = sum(len(fs) for _, _, fs in os.walk(build))
    print(f"{OUT}: {n} files, {os.path.getsize(OUT) / 1e6:.1f} MB")
    make_upgrade(OUT)


def main(zips=True, setup=True):
    with tempfile.TemporaryDirectory() as tmp:
        build = os.path.join(tmp, TOP)
        stage(build)
        if zips:
            make_zips(build)          # before Python and RADIMCOM.exe go into the build folder
        if setup:
            build_setup(build)


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) == 2 and a[0] == "--upgrade-from":
        make_upgrade(os.path.abspath(a[1]))
    elif a == ["--exe"]:
        build_shell(ROOT)         # RADIMCOM.exe for this development copy (it uses .venv)
    else:
        # from 0.115 a release has only the setup (also the upgrade of a zip installation); the zips on request
        main(zips="--zips" in a or "--zip-only" in a, setup="--zip-only" not in a)
