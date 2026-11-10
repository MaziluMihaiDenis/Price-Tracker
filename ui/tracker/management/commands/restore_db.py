from django.core.management.base import BaseCommand, CommandError

from tracker.backups import BackupError, restore


class Command(BaseCommand):
    help = ("Put a backup back as the app's database. Stop the server task first. "
            "Your current database is kept as db.before-restore-<time>.sqlite3.")

    def add_arguments(self, parser):
        parser.add_argument("backup_file", help="The backup to restore, e.g. ...\db-2026-11-09.sqlite3")
        parser.add_argument("--yes", action="store_true", help="Don't ask for confirmation.")

    def handle(self, *args, backup_file, yes=False, **options):
        if not yes:
            answer = input(f"Replace the app's data with {backup_file}? Your current data is kept "
                           "as a safety copy. Type 'yes' to continue: ")
            if answer.strip().lower() != "yes":
                raise CommandError("Nothing was changed.")
        try:
            safety = restore(backup_file)
        except BackupError as error:
            raise CommandError(str(error)) from error
        self.stdout.write(self.style.SUCCESS(
            f"Restored {backup_file}. Your previous data is in {safety}. Start the server again."))
