"""Downloads what the ATC speech to text (atc.py) needs: the Python package faster-whisper into lib\\whisper and the
Whisper model fine-tuned on ATC speech (~1.5 GB) into the Hugging Face cache of the user.

Optional and a separate step: about 1.7 GB in all, only for the ATC key of the AUDIO window. lib\\whisper stays on an
upgrade of RADIMCOM (the setup replaces only python\\); PYTHON.txt says for which Python it was installed, the setup
offers to install it again when its Python changes. The model in the cache stays even after an uninstall
(%USERPROFILE%\\.cache\\huggingface).

    install_atc.py          asks before downloading
    install_atc.py --yes    no question (the setup: its check box was the question)
"""
import os
import re
import shutil
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(BASE, "lib", "whisper")
PACKAGE = "faster-whisper==1.2.1"
PY_TAG = f"{sys.version_info.major}.{sys.version_info.minor}"
IN_USE = ("The ATC speech to text is in use, so it cannot be replaced; nothing was changed.\n"
          "Close RADIMCOM (tray icon, right click, Exit RADIMCOM) and run this again.")


def model_name():
    """MODEL of atc.py (read, not imported: atc.py needs Flask and the rest of RADIMCOM)."""
    with open(os.path.join(BASE, "atc.py"), encoding="utf-8") as f:
        m = re.search(r'^MODEL = "([^"]+)"', f.read(), re.M)
    if not m:
        sys.exit("MODEL not found in atc.py")
    return m.group(1)


NOTICE = f"""
ATC speech to text for RADIMCOM (AUDIO window, ATC key)
  1. Python package {PACKAGE} with its libraries (CTranslate2, PyAV, ONNX Runtime): about 200 MB into
     {TARGET}
  2. Whisper model {model_name()} (Hugging Face): about 1.5 GB, once, into
     {os.path.join(os.path.expanduser("~"), ".cache", "huggingface")}
It runs on the CPU, on this PC only (no cloud). Without it RADIMCOM works as before, only the ATC key reports it missing.
"""


def install_package():
    """pip into a new folder, which replaces lib\\whisper only when everything is installed."""
    new = TARGET + ".new"
    shutil.rmtree(new, ignore_errors=True)
    r = subprocess.run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--no-warn-script-location",
                        "--only-binary=:all:", "--target", new, PACKAGE], check=False)
    if r.returncode or not os.path.exists(os.path.join(new, "faster_whisper", "__init__.py")):
        shutil.rmtree(new, ignore_errors=True)
        sys.exit("pip could not install faster-whisper (internet connection?); nothing was changed.")
    # the console launchers of the packages have the path of the .new folder in them and are not needed
    shutil.rmtree(os.path.join(new, "bin"), ignore_errors=True)
    with open(os.path.join(new, "PYTHON.txt"), "w") as f:      # the setup compares it with the Python it installs
        f.write(PY_TAG)
    old = TARGET + ".old"
    shutil.rmtree(old, ignore_errors=True)
    try:
        if os.path.exists(TARGET):
            os.replace(TARGET, old)
        os.replace(new, TARGET)
    except OSError:
        if os.path.exists(old) and not os.path.exists(TARGET):
            os.replace(old, TARGET)
        shutil.rmtree(new, ignore_errors=True)
        sys.exit(IN_USE)
    shutil.rmtree(old, ignore_errors=True)


def download_model():
    """The model into the Hugging Face cache, where atc.py looks for it (WhisperModel(MODEL) with the default cache)."""
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    sys.path.append(TARGET)       # appended: numpy & co. of RADIMCOM's own Python stay first, as in atc.py
    try:
        from faster_whisper import download_model as dl
        path = dl(model_name())
    except Exception as e:
        sys.exit(f"The model could not be downloaded: {e}\nThe package is installed; run this again, or switch ATC on in "
                 "RADIMCOM, it downloads the model the first time.")
    print(f"Model: {path}")


def main():
    print(NOTICE)
    if "--yes" not in sys.argv[1:] and input("Type YES to download and install it: ").strip() != "YES":
        print("Nothing was installed.")
        return
    os.makedirs(os.path.dirname(TARGET), exist_ok=True)
    print("Installing faster-whisper...")
    install_package()
    print("Downloading the model (about 1.5 GB, it takes a while)...")
    download_model()
    print(f"\nDone. In RADIMCOM tune an airband voice channel (AM) and press ATC in the AUDIO window.")


if __name__ == "__main__":
    main()
