import logging
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from tracker.daily import AlreadyRunning, logger, run_daily_checks


class Command(BaseCommand):
    help = "Check today's price for every automatic item. Windows Task Scheduler runs this daily."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force", action="store_true",
            help="Also check items that were checked in the last 20 hours.",
        )
        parser.add_argument(
            "--log-file",
            help="Append the output to this file instead of printing it "
                 "(needed under pythonw.exe, which has no console).",
        )

    def handle(self, *args, force=False, log_file=None, **options):
        if log_file:
            path = Path(log_file)
            path.parent.mkdir(parents=True, exist_ok=True)
            handler = logging.FileHandler(path, encoding="utf-8")
        else:
            handler = logging.StreamHandler(self.stdout)
        handler.setFormatter(logging.Formatter("%(asctime)s %(message)s", "%Y-%m-%d %H:%M:%S"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
        try:
            run_daily_checks(force=force)
        except AlreadyRunning:
            logger.warning("Another daily check is already running; nothing to do.")
        except Exception as error:
            logger.exception("The daily check crashed.")
            raise CommandError(f"The daily check crashed: {error}") from error
        finally:
            logger.removeHandler(handler)
            handler.close()
