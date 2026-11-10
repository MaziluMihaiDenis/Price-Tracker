"""Database backups (milestone 9): one checked copy per day, the newest 14 kept.

SQLite's own backup function copies the database safely even while the app is running
(a plain file copy could catch it halfway through a write). Every copy is checked with
SQLite's built-in self-test before it counts.
"""

import logging
import re
import sqlite3
from contextlib import closing
from pathlib import Path

from django.conf import settings
from django.db import connection
from django.utils import timezone

logger = logging.getLogger("tracker.backups")
NAME = re.compile(r"^db-\d{4}-\d{2}-\d{2}\.sqlite3$")


class BackupError(Exception):
    """A backup or restore couldn't be done; the message says why, in plain words."""


def _live_database():
    """The app's own open SQLite connection (Django's), so we copy exactly what it sees."""
    connection.ensure_connection()
    return connection.connection


def check_file(path):
    """Raise BackupError unless `path` is a healthy Price Tracker database."""
    path = Path(path)
    if not path.is_file():
        raise BackupError(f"{path} doesn't exist.")
    try:
        with closing(sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)) as database:
            result = database.execute("PRAGMA integrity_check").fetchone()[0]
            tables = {row[0] for row in database.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    except sqlite3.DatabaseError as error:
        raise BackupError(f"{path.name} isn't a readable database ({error}).") from error
    if result != "ok":
        raise BackupError(f"{path.name} failed SQLite's integrity check: {result}")
    if "tracker_item" not in tables:
        raise BackupError(f"{path.name} isn't a Price Tracker database.")


def backup_name(day):
    return f"db-{day:%Y-%m-%d}.sqlite3"


def backed_up_today(folder, today=None):
    return (Path(folder) / backup_name(today or timezone.localdate())).exists()


def make_backup(folder=None, keep=None, today=None):
    """Write today's checked backup into `folder` and keep the newest `keep`. Returns its path."""
    folder = Path(folder or settings.BACKUP_DIR)
    keep = keep or settings.BACKUP_KEEP
    if not str(folder).strip() or not folder.is_dir():
        raise BackupError(f"The backup folder {folder} doesn't exist. Create it, or fix BACKUP_DIR in household.env.")
    target = folder / backup_name(today or timezone.localdate())
    partial = target.with_name(target.name + ".partial")
    try:
        with closing(sqlite3.connect(partial)) as copy:
            _live_database().backup(copy)
        check_file(partial)
        partial.replace(target)  # only a checked copy gets the real name
    except (OSError, sqlite3.Error) as error:
        raise BackupError(f"Couldn't write the backup to {folder}: {error}") from error
    finally:
        partial.unlink(missing_ok=True)
    for old in sorted(path for path in folder.iterdir() if NAME.match(path.name))[:-keep]:
        old.unlink()
    return target


def restore(backup_file, now=None, safety_folder=None):
    """Put `backup_file` back as the app's database. Returns the safety copy of the old one.

    Stop the server first (see the README): restoring under a running app is safe for
    SQLite, but pages open at that moment would show a mix of old and new data.
    """
    backup_file = Path(backup_file)
    check_file(backup_file)
    now = timezone.localtime(now or timezone.now())
    safety_folder = Path(safety_folder or settings.BASE_DIR)  # ui/, next to db.sqlite3
    safety = safety_folder / f"db.before-restore-{now:%Y%m%d-%H%M%S}.sqlite3"
    try:
        with closing(sqlite3.connect(safety)) as copy:
            _live_database().backup(copy)
        with closing(sqlite3.connect(f"file:{backup_file.as_posix()}?mode=ro", uri=True)) as source:
            source.backup(_live_database())
    except (OSError, sqlite3.Error) as error:
        raise BackupError(f"Couldn't restore {backup_file.name}: {error}. "
                          f"Your previous database is in {safety.name}.") from error
    return safety


def backup_if_configured(reason, log=logger):
    """Make today's backup when BACKUP_DIR is set. Never raises: problems are only logged."""
    if not settings.BACKUP_DIR:
        return None
    try:
        path = make_backup()
    except BackupError as error:
        log.warning("Backup (%s) skipped: %s", reason, error)
        return None
    log.info("Backup (%s) saved: %s", reason, path)
    return path
