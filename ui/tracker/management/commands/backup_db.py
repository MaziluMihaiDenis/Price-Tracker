from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from tracker.backups import BackupError, make_backup


class Command(BaseCommand):
    help = "Save today's checked copy of the database (keeps the newest 14). The 17:00 task runs it too."

    def add_arguments(self, parser):
        parser.add_argument("--to", help="Backup folder (default: BACKUP_DIR from household.env).")
        parser.add_argument("--keep", type=int, default=settings.BACKUP_KEEP,
                            help="How many daily backups to keep (default: 14).")

    def handle(self, *args, to=None, keep=14, **options):
        if not (to or settings.BACKUP_DIR):
            raise CommandError("No backup folder: set BACKUP_DIR in ui/household.env, or use --to FOLDER.")
        if keep < 1:
            raise CommandError("--keep must be at least 1.")
        try:
            path = make_backup(to, keep)
        except BackupError as error:
            raise CommandError(str(error)) from error
        self.stdout.write(self.style.SUCCESS(f"Backup saved and checked: {path}"))
