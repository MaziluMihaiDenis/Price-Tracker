"""The "Price Tracker" desktop icon (milestone 9): open the app, starting it first if needed.

pythonw.exe runs this without a console window. If the server isn't answering (for example
the startup task hasn't run), it's started in the background and the browser opens once it
answers. A second server is never started.
"""

import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
URL = "http://localhost:8000/"
WAIT_SECONDS = 20


def server_running(url=URL, timeout=2):
    """True when the app answers (any HTTP reply counts: the login page, a redirect...)."""
    try:
        urllib.request.urlopen(url, timeout=timeout).close()
        return True
    except urllib.error.HTTPError:
        return True  # it answered, just not with 200
    except (urllib.error.URLError, OSError):
        return False


def start_server():
    """Start scripts/serve.py with pythonw.exe, detached: it keeps running after this exits."""
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
    subprocess.Popen([str(pythonw), str(ROOT / "scripts" / "serve.py")], cwd=ROOT,
                     creationflags=flags, close_fds=True)


def ensure_running(is_running=server_running, start=start_server, sleep=time.sleep, wait=WAIT_SECONDS):
    """True once the app answers. Starts it at most once, and only when it isn't answering."""
    if is_running():
        return True
    start()
    for _ in range(wait):
        sleep(1)
        if is_running():
            return True
    return False


def show_message(text):
    """A small Windows message box (no console under pythonw)."""
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, text, "Price Tracker", 0x30)
    except (ImportError, AttributeError, OSError):
        print(text)


def main():
    if ensure_running():
        webbrowser.open(URL)
        return 0
    show_message("Price Tracker didn't start within 20 seconds.\n\n"
                 f"Look at the end of {ROOT / 'logs' / 'server.log'} for the reason, "
                 "or ask the person who set it up.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
