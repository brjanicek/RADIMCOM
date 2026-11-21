"""Puts RNNoise (the neural network noise reduction of the DNR algorithm RNN, nrx.py) into lib\\rnnoise\\rnnoise.dll.

The DLL is the Windows x64 build of RNNoise (Xiph.Org, BSD-3-Clause, https://github.com/xiph/rnnoise) shipped in the
pyrnnoise 0.4.6 wheel on PyPI (Zhendong Peng, Apache-2.0, https://github.com/pengzhendong/pyrnnoise). The wheel is
downloaded with pip, checked against its SHA-256 and only the DLL is taken out of it (pyrnnoise itself is not installed).

Run from the RADIMCOM folder:  python installer\\get_rnnoise.py
"""
import hashlib
import os
import subprocess
import sys
import tempfile
import zipfile

WHEEL = "pyrnnoise-0.4.6-py3-none-win_amd64.whl"
WHEEL_SHA256 = "f34c07815581e110a84e820e7abf452578ad6d2d8af4b4178e2541d247e2d634"
DLL_IN_WHEEL = "pyrnnoise-0.4.6.data/purelib/pyrnnoise/rnnoise.dll"
DLL_SHA256 = "2ed431c1e2924d7f8c0e2b785d8f3a55a84b9cdda649b0e7a82392636244ec1d"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(ROOT, "lib", "rnnoise", "rnnoise.dll")


def sha256(b):
    return hashlib.sha256(b).hexdigest()


def main():
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.check_call([sys.executable, "-m", "pip", "download", "pyrnnoise==0.4.6", "--no-deps",
                               "--only-binary=:all:", "--platform", "win_amd64", "-d", tmp])
        path = os.path.join(tmp, WHEEL)
        with open(path, "rb") as f:
            if sha256(f.read()) != WHEEL_SHA256:
                sys.exit("the downloaded wheel does not match its SHA-256: nothing installed")
        dll = zipfile.ZipFile(path).read(DLL_IN_WHEEL)
    if sha256(dll) != DLL_SHA256:
        sys.exit("rnnoise.dll does not match its SHA-256: nothing installed")
    os.makedirs(os.path.dirname(DEST), exist_ok=True)
    with open(DEST, "wb") as f:
        f.write(dll)
    print(f"{DEST} ({len(dll) // 1024} kB). Restart RADIMCOM, then SETTINGS › VFO › AUDIO › DNR › Algorithm RNN.")


if __name__ == "__main__":
    main()
