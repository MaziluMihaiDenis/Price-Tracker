"""Run Price Tracker for the household (milestone 9): Waitress on the home network, port 8000.

Started by the "Price Tracker server" task when Windows starts, or by the desktop icon.
Under pythonw.exe there is no window: everything goes to logs/server.log.

    .venv\\Scripts\\python.exe scripts\\serve.py      (with a window, to watch it run)
"""

import logging
import logging.handlers
import os
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UI_DIR = ROOT / "ui"
LOG_FILE = ROOT / "logs" / "server.log"
PORT = int(os.environ.get("PRICE_TRACKER_PORT", "8000"))  # change only for trials; phones use 8000

logger = logging.getLogger("price_tracker.server")


def port_in_use(port=PORT, host="127.0.0.1"):
    """True when something (usually an already running Price Tracker) answers on the port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(1)
        return probe.connect_ex((host, port)) == 0


def setup_logging():
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S"))
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    if sys.stdout is not None:  # a console exists (python.exe): show it there too
        root.addHandler(logging.StreamHandler(sys.stdout))
    else:  # pythonw.exe: libraries that print must not crash
        sys.stdout = sys.stderr = open(os.devnull, "w", encoding="utf-8")


def main():
    setup_logging()
    if port_in_use():
        logger.info("Port %d is already in use (Price Tracker is probably running); not starting again.", PORT)
        return 0

    os.environ["PRICE_TRACKER_HOUSEHOLD"] = "1"
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.settings")
    os.chdir(UI_DIR)
    sys.path.insert(0, str(UI_DIR))

    import django
    from django.core.management import call_command

    django.setup()
    from django.conf import settings
    from django.db.migrations.executor import MigrationExecutor
    from django.db import connection

    executor = MigrationExecutor(connection)
    pending = executor.migration_plan(executor.loader.graph.leaf_nodes())
    if pending:  # never changes the database by itself: the README explains backup + migrate
        logger.warning("%d database update(s) not applied yet. Back up, then run: "
                       ".venv\\Scripts\\python.exe ui\\manage.py migrate", len(pending))

    call_command("collectstatic", interactive=False, verbosity=0)  # styles and scripts, version-stamped

    from tracker.backups import backed_up_today, backup_if_configured
    if settings.BACKUP_DIR and Path(settings.BACKUP_DIR).is_dir() and not backed_up_today(settings.BACKUP_DIR):
        backup_if_configured("server start, none today yet")  # catch-up when the PC was off at 17:00
    elif settings.BACKUP_DIR and not Path(settings.BACKUP_DIR).is_dir():
        logger.warning("The backup folder %s doesn't exist; no backups until it does.", settings.BACKUP_DIR)

    from waitress import serve
    from app.wsgi import application

    logger.info("Price Tracker is running: http://%s:%d/ (also http://localhost:%d/). Allowed names: %s",
                socket.gethostname(), PORT, PORT, ", ".join(settings.ALLOWED_HOSTS))
    serve(application, host="0.0.0.0", port=PORT, threads=8, ident="Price Tracker")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001 - make sure the reason ends up in the log
        logger.exception("The server stopped because of an error.")
        sys.exit(1)
