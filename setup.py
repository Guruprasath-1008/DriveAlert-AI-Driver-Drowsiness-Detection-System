"""
DriveAlert - One-click setup and launcher.
Installs dependencies, patches MediaPipe for Python 3.13, downloads the model,
and starts the Flask server.

Usage:
    python setup.py
"""

import subprocess
import sys
import os
import urllib.request
import socket

ROOT = os.path.dirname(os.path.abspath(__file__))
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "face_landmarker/face_landmarker/float16/1/face_landmarker.task"
)
MODEL_PATH = os.path.join(ROOT, "face_landmarker.task")
PY = sys.executable


def run(cmd):
    print("  $", " ".join(cmd))
    subprocess.check_call(cmd)


def banner(msg):
    print("\n" + "=" * 58)
    print(f"  {msg}")
    print("=" * 58)


# Step 1 - Install requirements
banner("Step 1 - Installing Python packages")
run([PY, "-m", "pip", "install", "--upgrade", "pip"])
run([PY, "-m", "pip", "install", "-r", os.path.join(ROOT, "requirements.txt")])


# Step 2 - Patch MediaPipe for Python 3.13
banner("Step 2 - Patching MediaPipe for Python 3.13+ compatibility")

py_major, py_minor = sys.version_info[:2]
if py_major >= 3 and py_minor >= 13:
    try:
        import mediapipe
        pkg_root = os.path.dirname(mediapipe.__file__)
        bindings_path = os.path.join(
            pkg_root, "tasks", "python", "core", "mediapipe_c_bindings.py"
        )
        with open(bindings_path, "r", encoding="utf-8") as f:
            src = f.read()

        BROKEN = "  _shared_lib.free.argtypes = [ctypes.c_void_p]\n  _shared_lib.free.restype = None"
        FIXED = (
            "  # Python 3.13 fix: load free() from the system C runtime\n"
            "  if sys.platform == 'win32':\n"
            "    _crt = ctypes.CDLL('msvcrt')\n"
            "  elif sys.platform == 'darwin':\n"
            "    _crt = ctypes.CDLL(ctypes.util.find_library('c') or 'libc.dylib')\n"
            "  else:\n"
            "    _crt = ctypes.CDLL(ctypes.util.find_library('c') or 'libc.so.6')\n"
            "  _crt.free.argtypes = [ctypes.c_void_p]\n"
            "  _crt.free.restype = None\n"
            "  _shared_lib.free = _crt.free"
        )
        ALREADY_PATCHED = ("_sys.platform" in src or
                           "# Python 3.13 fix" in src or
                           "_shared_lib.free = _crt.free" in src)

        if ALREADY_PATCHED:
            print("  [OK] Patch already applied - nothing to do.")
        elif BROKEN in src:
            patched = src.replace(BROKEN, FIXED)
            with open(bindings_path, "w", encoding="utf-8") as f:
                f.write(patched)
            print("  [OK] Patch applied to", bindings_path)
        else:
            print("  [WARN] Could not locate patch target - MediaPipe source may have changed.")
    except ImportError:
        print("  [WARN] mediapipe not importable yet - skipping patch.")
else:
    print(f"  [OK] Python {py_major}.{py_minor} - no patch needed.")


# Step 3 - Download model
banner("Step 3 - Downloading face_landmarker.task model")

if os.path.exists(MODEL_PATH) and os.path.getsize(MODEL_PATH) > 100000:
    print(f"  [OK] Model already present ({os.path.getsize(MODEL_PATH) // 1024} KB) - skipping.")
else:
    print(f"  Downloading from:\n    {MODEL_URL}")
    try:
        def _progress(count, block, total):
            pct = min(count * block * 100 // total, 100)
            bar = "#" * (pct // 5) + "." * (20 - pct // 5)
            print(f"\r  [{bar}] {pct}%", end="", flush=True)

        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH, _progress)
        print(f"\n  [OK] Saved to {MODEL_PATH}")
    except Exception as e:
        print(f"\n  [FAIL] Download failed: {e}")
        print("  Please download manually:")
        print(f"    {MODEL_URL}")
        print(f"  and save it as: {MODEL_PATH}")
        sys.exit(1)


# Step 4 - Launch Flask
banner("Step 4 - Starting DriveAlert server")

def _local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "unknown"

local_ip = _local_ip()
print(f"""
  DriveAlert is starting...

    Local   -> https://127.0.0.1:5000  (or http://127.0.0.1:5000 if --http)
    Network -> https://{local_ip}:5000

  Open one of those URLs in your browser.
  Press Ctrl+C to stop the server.
""")

os.chdir(ROOT)
subprocess.call([PY, os.path.join(ROOT, "app.py")])
