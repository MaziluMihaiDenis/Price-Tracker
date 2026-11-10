"""Household mode (milestone 9): the settings used when the app serves the family's phones.

Kept free of Django imports, because settings.py uses it before Django is set up.

`ui/household.env` holds the household settings, one KEY=value per line:
    DJANGO_SECRET_KEY  created automatically, once, at random. Keep it secret: it signs logins.
    BACKUP_DIR         where daily database backups go, e.g. a folder in your OneDrive.
The file is git-ignored and never printed.
"""

import os
import secrets
import socket
from pathlib import Path

# Tests point PRICE_TRACKER_ENV_FILE at a temporary file, so they never touch the real one.
ENV_FILE = Path(os.environ.get("PRICE_TRACKER_ENV_FILE")
                or Path(__file__).resolve().parent.parent / "household.env")

TEMPLATE = """# Price Tracker household settings (git-ignored; keep this file private).
# DJANGO_SECRET_KEY was created automatically: don't share it or change it
# (changing it signs everyone out).
DJANGO_SECRET_KEY={key}

# Folder for the daily database backups. Set it to a folder outside this PC's
# disk if you can, for example inside your OneDrive folder:
# BACKUP_DIR=C:\\Users\\you\\OneDrive\\Price Tracker backups
BACKUP_DIR=
"""


def read_env(path):
    """KEY=value pairs from the file ({} if it doesn't exist). '#' starts a comment line."""
    path = Path(path)
    if not path.exists():
        return {}
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def ensure_env(path):
    """The household settings, creating the file with a new random secret key if needed."""
    path = Path(path)
    values = read_env(path)
    if values.get("DJANGO_SECRET_KEY"):
        return values
    key = secrets.token_urlsafe(50)
    if path.exists():  # a file without a key: add one, keep everything else
        with path.open("a", encoding="utf-8") as file:
            file.write(f"\nDJANGO_SECRET_KEY={key}\n")
    else:
        path.write_text(TEMPLATE.format(key=key), encoding="utf-8")
    return read_env(path)


def local_hosts(hostname=None):
    """The names and addresses phones on the home network may use to reach this PC."""
    hostname = hostname or socket.gethostname()
    hosts = ["localhost", "127.0.0.1", hostname, hostname.lower(), f"{hostname.lower()}.local"]
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(hostname, None, socket.AF_INET)}
    except OSError:
        addresses = set()
    hosts += sorted(addresses)
    return list(dict.fromkeys(hosts))  # without repeats, in order
