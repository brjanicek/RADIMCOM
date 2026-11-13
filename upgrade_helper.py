"""RADIMCOM upgrade, second half (started by update_check.py, from a copy in data\\update\\, in its own console):
waits until RADIMCOM has closed, ends decoders still running from lib\\, unzips the upgrade zip over the
RADIMCOM folder (data\\ is never touched), runs upgrade.bat (Python packages) and starts start.bat again.

  python -I upgrade_helper.py --pid <RADIMCOM pid> --base <RADIMCOM folder> --zip <upgrade zip> --version 0.1xx

Standard library only: it runs with the Python of .venv while upgrade.bat updates the packages there.
"""
import argparse
import ctypes
import os
import subprocess
import sys
import time
import zipfile

TOP = "RADIMCOM/"
WAIT_EXIT_S = 60
LOCK_RETRY_S = 30


def wait_exit(pid, timeout):
    """True when the process pid has ended (or never was)."""
    k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(0x00100000, False, pid)      # SYNCHRONIZE
    if not h:
        return True
    try:
        return k32.WaitForSingleObject(h, int(timeout * 1000)) == 0
    finally:
        k32.CloseHandle(h)


def end_lib_programs(base):
    """Decoders started from lib\\ (welle-cli, rtl_433, dumpvdl2, dumphfdl, dsd-fme) that outlived RADIMCOM hold their files.
    Only processes whose program file lies in this RADIMCOM's lib\\ folder are ended (Windows API, no shell)."""
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    k32.QueryFullProcessImageNameW.argtypes = (wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD))
    k32.TerminateProcess.argtypes = (wintypes.HANDLE, wintypes.UINT)
    k32.CloseHandle.argtypes = (wintypes.HANDLE,)
    lib =os.path.normcase(os.path.join(os.path.abspath(base), "lib")) + os.sep
    pids = (wintypes.DWORD * 4096)()
    got = wintypes.DWORD()
    if not k32.K32EnumProcesses(pids, ctypes.sizeof(pids), ctypes.byref(got)):
        return
    for pid in pids[:got.value // ctypes.sizeof(wintypes.DWORD)]:
        h = k32.OpenProcess(0x1000 | 0x0001, False, pid)     # PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_TERMINATE
        if not h:
            continue
        try:
            buf = ctypes.create_unicode_buffer(1024)
            size = wintypes.DWORD(len(buf))
            if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)) and \
                    os.path.normcase(buf.value).startswith(lib):
                print(f"  ending {buf.value}")
                k32.TerminateProcess(h, 1)
        finally:
            k32.CloseHandle(h)


def unzip(path, base):
    base_n = os.path.normcase(os.path.abspath(base))
    n = 0
    with zipfile.ZipFile(path) as z:
        for m in z.infolist():
            if not m.filename.startswith(TOP):
                continue
            rel = m.filename[len(TOP):]
            if not rel or rel.startswith("data/"):
                continue
            dst = os.path.abspath(os.path.join(base, *rel.split("/")))
            if not os.path.normcase(dst).startswith(base_n + os.sep):
                raise RuntimeError(f"bad path in the zip: {m.filename}")
            if m.is_dir():
                os.makedirs(dst, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            body = z.read(m)
            until = time.time() + LOCK_RETRY_S
            while True:
                try:
                    with open(dst, "wb") as f:
                        f.write(body)
                    break
                except PermissionError:
                    if time.time() > until:
                        raise RuntimeError(f"{rel} is in use by another program; close it and run the upgrade again")
                    time.sleep(1.0)
            n += 1
    return n


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--pid", type=int, required=True)
    a.add_argument("--base", required=True)
    a.add_argument("--zip", required=True)
    a.add_argument("--version", default="")
    args = a.parse_args()
    ctypes.windll.kernel32.SetConsoleTitleW(f"RADIMCOM upgrade to {args.version}")
    print(f"RADIMCOM upgrade to {args.version}\n{'=' * 40}\nFolder: {args.base}\n")
    print("Waiting for the receiver to close...")
    if not wait_exit(args.pid, WAIT_EXIT_S):
        raise RuntimeError("the receiver did not close within a minute; close it and run the upgrade again")
    time.sleep(2.0)          # the VFO processes end after the launcher
    end_lib_programs(args.base)
    print("Unzipping the program (data\\ stays as it is)...")
    print(f"  {unzip(args.zip, args.base)} files")
    print("Running upgrade.bat (Python packages)...\n")
    r = subprocess.run(["cmd", "/c", os.path.join(args.base, "upgrade.bat")], cwd=args.base, input=b"\r\n" * 5, check=False)
    if r.returncode:
        raise RuntimeError("upgrade.bat failed (see above); start the receiver by hand after fixing it")
    try:
        os.remove(args.zip)
    except OSError:
        pass
    print("\nDone. Starting RADIMCOM...")
    subprocess.Popen(["cmd", "/c", "start", "", os.path.join(args.base, "start.bat")], cwd=args.base, close_fds=True)
    time.sleep(3.0)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nUpgrade FAILED: {e}")
        try:
            input("Press Enter to close this window.")
        except EOFError:
            pass
        sys.exit(1)
