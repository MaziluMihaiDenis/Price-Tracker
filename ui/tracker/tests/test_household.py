import json
import os
import socket
import subprocess
import sys
import tempfile
from datetime import date, timedelta
from io import StringIO
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TransactionTestCase, override_settings

from app import household
from tracker import backups
from tracker.models import Category, Item

UI_DIR = Path(settings.BASE_DIR)
DEV_KEY = "local-development-key-change-before-any-public-deployment"

# Runs in a separate Python process, because household mode is chosen when settings load.
HOUSEHOLD_PROBE = r"""
import hashlib, json, os, socket, django
os.environ["DJANGO_SETTINGS_MODULE"] = "app.settings"
django.setup()
from django.conf import settings
from django.test import Client
client = Client()
host = socket.gethostname()
not_found = client.get("/no-such-page/", HTTP_HOST=host)
stranger = client.get("/no-such-page/", HTTP_HOST="evil.example")
print(json.dumps({
    "debug": settings.DEBUG,
    "dev_key": settings.SECRET_KEY == %r,
    "key_hash": hashlib.sha256(settings.SECRET_KEY.encode()).hexdigest(),
    "whitenoise": "whitenoise.middleware.WhiteNoiseMiddleware" in settings.MIDDLEWARE,
    "hosts_ok": host in settings.ALLOWED_HOSTS and "localhost" in settings.ALLOWED_HOSTS,
    "not_found": [not_found.status_code, "URLconf" in not_found.content.decode() or "Traceback" in not_found.content.decode()],
    "stranger": stranger.status_code,
}))
""" % DEV_KEY


class HouseholdEnvTests(SimpleTestCase):
    def test_secret_key_is_created_once_and_reused(self):
        """Acceptance criterion 2."""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "household.env"
            first = household.ensure_env(path)["DJANGO_SECRET_KEY"]
            again = household.ensure_env(path)["DJANGO_SECRET_KEY"]
            self.assertEqual(first, again)
            self.assertGreater(len(first), 50)
            self.assertNotEqual(first, DEV_KEY)
            self.assertIn("BACKUP_DIR=", path.read_text(encoding="utf-8"))

    def test_a_file_without_a_key_keeps_its_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "household.env"
            path.write_text("# mine\nBACKUP_DIR=D:\\Backups\n", encoding="utf-8")
            values = household.ensure_env(path)
            self.assertEqual(values["BACKUP_DIR"], "D:\\Backups")
            self.assertTrue(values["DJANGO_SECRET_KEY"])

    def test_reading_ignores_comments_and_quotes(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "household.env"
            path.write_text('# BACKUP_DIR=nope\nBACKUP_DIR="C:\\My backups"\n\njunk line\n', encoding="utf-8")
            self.assertEqual(household.read_env(path), {"BACKUP_DIR": "C:\\My backups"})
        self.assertEqual(household.read_env(Path(folder) / "missing.env"), {})

    def test_local_hosts(self):
        hosts = household.local_hosts("DESKTOP-TEST")
        self.assertEqual(hosts[:5], ["localhost", "127.0.0.1", "DESKTOP-TEST", "desktop-test", "desktop-test.local"])
        self.assertEqual(len(hosts), len(set(hosts)))

    def test_household_env_is_ignored_by_git(self):
        """Acceptance criterion 2: the secret key file can never be committed."""
        result = subprocess.run(["git", "check-ignore", "-q", str(UI_DIR / "household.env")],
                                cwd=UI_DIR, capture_output=True)
        self.assertEqual(result.returncode, 0)


class HouseholdModeTests(SimpleTestCase):
    """Acceptance criteria 1-3, checked in real household mode (a separate Python process)."""

    def probe(self, env_file):
        env = {**os.environ, "PRICE_TRACKER_HOUSEHOLD": "1", "PRICE_TRACKER_ENV_FILE": str(env_file)}
        result = subprocess.run([sys.executable, "-c", HOUSEHOLD_PROBE], cwd=UI_DIR, env=env,
                                capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        return json.loads(result.stdout.strip().splitlines()[-1])

    def test_styles_and_scripts_can_be_prepared(self):
        """Acceptance criterion 1: collectstatic with version-stamped names succeeds (found in the trial)."""
        script = r"""
import os, django, sys
os.environ["DJANGO_SETTINGS_MODULE"] = "app.settings"
django.setup()
from django.core.management import call_command
from django.test.utils import override_settings
from django.templatetags.static import static
with override_settings(STATIC_ROOT=sys.argv[1]):
    call_command("collectstatic", interactive=False, verbosity=0)
    print(static("tracker/css/app.css"))
"""
        with tempfile.TemporaryDirectory() as folder:
            env = {**os.environ, "PRICE_TRACKER_HOUSEHOLD": "1", "PRICE_TRACKER_ENV_FILE": str(Path(folder) / "h.env")}
            result = subprocess.run([sys.executable, "-c", script, str(Path(folder) / "static")], cwd=UI_DIR,
                                    env=env, capture_output=True, text=True, timeout=300)
            self.assertEqual(result.returncode, 0, result.stderr[-2000:])
            stamped = result.stdout.strip().splitlines()[-1]
            self.assertRegex(stamped, r"^/static/tracker/css/app\.[0-9a-f]{12}\.css$")  # a version-stamped name
            self.assertTrue((Path(folder) / "static" / "vendor" / "leaflet" / "leaflet.js").exists())

    def test_household_mode(self):
        with tempfile.TemporaryDirectory() as folder:
            env_file = Path(folder) / "household.env"
            first = self.probe(env_file)
            second = self.probe(env_file)
        self.assertFalse(first["debug"])
        self.assertFalse(first["dev_key"])
        self.assertTrue(first["whitenoise"])
        self.assertTrue(first["hosts_ok"])
        self.assertEqual(first["not_found"], [404, False])  # a plain page, no internal details
        self.assertEqual(first["stranger"], 400)  # an unknown host name is refused
        self.assertEqual(first["key_hash"], second["key_hash"])  # same key after a restart


@override_settings(BACKUP_KEEP=14)
class BackupTests(TransactionTestCase):
    """Acceptance criteria 4-6 (TransactionTestCase: backups read committed data, like the live app)."""

    serialized_rollback = True  # keep the categories the migrations created, between tests

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.user = get_user_model().objects.create_user("ana", password="test-pass-123")
        self.item = Item.objects.create(owner=self.user, category=Category.objects.get(name="Product"), name="Gel")

    def test_backup_is_written_checked_and_old_ones_pruned(self):
        """Acceptance criterion 4."""
        today = date(2026, 11, 9)
        for days in range(1, 16):  # 15 older backups
            (self.folder / backups.backup_name(today - timedelta(days=days))).write_bytes(b"old")
        (self.folder / "notes.txt").write_text("not a backup")
        path = backups.make_backup(self.folder, today=today)
        self.assertEqual(path.name, "db-2026-11-09.sqlite3")
        backups.check_file(path)  # a healthy Price Tracker database
        kept = sorted(p.name for p in self.folder.iterdir() if backups.NAME.match(p.name))
        self.assertEqual(len(kept), 14)
        self.assertEqual(kept[-1], "db-2026-11-09.sqlite3")
        self.assertEqual(kept[0], "db-2026-10-27.sqlite3")
        self.assertTrue((self.folder / "notes.txt").exists())
        self.assertFalse(any(p.name.endswith(".partial") for p in self.folder.iterdir()))

    def test_missing_folder_is_only_a_warning(self):
        """Acceptance criterion 4."""
        with self.assertRaises(backups.BackupError):
            backups.make_backup(self.folder / "missing")
        with override_settings(BACKUP_DIR=str(self.folder / "missing")), \
                self.assertLogs("tracker.backups", level="WARNING") as logs:
            self.assertIsNone(backups.backup_if_configured("test"))
        self.assertIn("doesn't exist", logs.output[0])

    def test_nothing_happens_without_a_backup_folder(self):
        with override_settings(BACKUP_DIR=""):
            self.assertIsNone(backups.backup_if_configured("test"))

    def test_daily_check_makes_a_backup(self):
        """Acceptance criterion 5."""
        from tracker import daily, rates
        with override_settings(BACKUP_DIR=str(self.folder)), \
                mock.patch.object(rates, "fetch", side_effect=rates.RatesUnavailable("offline")):
            daily.run_daily_checks(sleep=lambda seconds: None)
        self.assertTrue(backups.backed_up_today(self.folder))

    def test_restore_brings_the_backup_back_and_keeps_a_safety_copy(self):
        """Acceptance criterion 6."""
        path = backups.make_backup(self.folder)
        Item.objects.create(owner=self.user, category=self.item.category, name="Added after the backup")
        self.item.delete()
        safety = backups.restore(path, safety_folder=self.folder)
        self.assertEqual(list(Item.objects.values_list("name", flat=True)), ["Gel"])
        backups.check_file(safety)
        self.assertTrue(safety.name.startswith("db.before-restore-"))

    def test_restore_refuses_broken_or_foreign_files(self):
        broken = self.folder / "db-2026-01-01.sqlite3"
        broken.write_bytes(b"this is not a database at all, just text" * 100)
        with self.assertRaises(backups.BackupError):
            backups.restore(broken, safety_folder=self.folder)
        import sqlite3
        foreign = self.folder / "other.sqlite3"
        with sqlite3.connect(foreign) as other:
            other.execute("CREATE TABLE notes (text TEXT)")
        other.close()
        with self.assertRaisesMessage(backups.BackupError, "isn't a Price Tracker database"):
            backups.restore(foreign, safety_folder=self.folder)
        self.assertEqual(Item.objects.count(), 1)

    def test_commands(self):
        out = StringIO()
        call_command("backup_db", "--to", str(self.folder), stdout=out)
        self.assertIn("Backup saved and checked", out.getvalue())
        with override_settings(BACKUP_DIR=""), self.assertRaisesMessage(CommandError, "No backup folder"):
            call_command("backup_db")
        backup = next(p for p in self.folder.iterdir() if backups.NAME.match(p.name))
        with mock.patch("builtins.input", return_value="no"), self.assertRaisesMessage(CommandError, "Nothing was changed"):
            call_command("restore_db", str(backup))


def _load_script(name):
    """Import scripts/<name> (also .pyw files) as a module, without running it."""
    from importlib.machinery import SourceFileLoader
    from importlib.util import module_from_spec, spec_from_loader
    path = UI_DIR.parent / "scripts" / name
    loader = SourceFileLoader(name.split(".")[0], str(path))
    module = module_from_spec(spec_from_loader(loader.name, loader))
    loader.exec_module(module)
    return module


class DesktopIconTests(SimpleTestCase):
    """Acceptance criterion 7: open the app, start it only when needed, never twice."""

    def setUp(self):
        self.app = _load_script("open_app.pyw")
        self.started = []

    def test_running_server_is_just_opened(self):
        self.assertTrue(self.app.ensure_running(is_running=lambda: True, start=lambda: self.started.append(1)))
        self.assertEqual(self.started, [])

    def test_stopped_server_is_started_once_and_waited_for(self):
        answers = iter([False, False, False, True])
        ok = self.app.ensure_running(is_running=lambda: next(answers), start=lambda: self.started.append(1),
                                     sleep=lambda seconds: None)
        self.assertTrue(ok)
        self.assertEqual(self.started, [1])

    def test_gives_up_after_the_wait(self):
        ok = self.app.ensure_running(is_running=lambda: False, start=lambda: self.started.append(1),
                                     sleep=lambda seconds: None, wait=3)
        self.assertFalse(ok)
        self.assertEqual(self.started, [1])

    def test_server_running_checks_the_address(self):
        import urllib.error
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("refused")):
            self.assertFalse(self.app.server_running())
        with mock.patch("urllib.request.urlopen",
                        side_effect=urllib.error.HTTPError(self.app.URL, 302, "Found", None, None)):
            self.assertTrue(self.app.server_running())


class ServeScriptTests(SimpleTestCase):
    def test_port_in_use(self):
        serve = _load_script("serve.py")
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            port = listener.getsockname()[1]
            self.assertTrue(serve.port_in_use(port))
        self.assertFalse(serve.port_in_use(port))


@override_settings(BACKUP_KEEP=14)
class BackupFolderNameTests(TransactionTestCase):
    """Review of M9, medium: folder names with #, %, spaces or Romanian letters."""

    serialized_rollback = True

    def test_any_folder_name_works(self):
        get_user_model().objects.create_user("ana", password="test-pass-123")
        with tempfile.TemporaryDirectory() as base:
            for name in ("Backups #1", "50% done", "Copii de siguranță", "Price Tracker backups"):
                folder = Path(base) / name
                folder.mkdir()
                path = backups.make_backup(folder)
                backups.check_file(path)
                safety = backups.restore(path, safety_folder=folder)
                backups.check_file(safety)
            # Nothing may be created outside the backup folders (the old bug made a stray "Backups" file).
            self.assertEqual(sorted(p.name for p in Path(base).iterdir()),
                             sorted(["Backups #1", "50% done", "Copii de siguranță", "Price Tracker backups"]))
