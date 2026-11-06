from datetime import date

from django.core.management.base import BaseCommand, CommandError

from tracker.rates import RatesUnavailable, default_start, import_rates


class Command(BaseCommand):
    help = "Load BNR exchange-rate history (yearly files) plus the latest published day."

    def add_arguments(self, parser):
        parser.add_argument(
            "--since", type=date.fromisoformat,
            help="Earliest date to cover, as YYYY-MM-DD (default: oldest price, or 2025-01-01).",
        )

    def handle(self, *args, since=None, **options):
        since = since or default_start()
        self.stdout.write(f"Importing BNR rates from {since.year - 1} (covering {since}) up to today...")
        try:
            saved = import_rates(since)
        except RatesUnavailable as error:
            raise CommandError(str(error)) from error
        for source, count in saved.items():
            self.stdout.write(f"  {source}: {count} rate(s)")
        self.stdout.write(self.style.SUCCESS(f"Done: {sum(saved.values())} rate(s) saved or updated."))
