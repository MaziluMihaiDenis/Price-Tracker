import tempfile
from datetime import timedelta
from io import StringIO
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from tracker import checks, daily
from tracker.models import Category, CheckAttempt, CheckRun, Item, PricePoint
from tracker.tests.helpers import FakeInternet, fixture

EMAG_URL = "https://www.emag.ro/gel/pd/TEST/"
STORIA_URL = "https://www.storia.ro/ro/oferta/garsoniera-IDTEST"


class DailyChecksTestCase(TestCase):
    def setUp(self):
        users = get_user_model().objects
        self.ana = users.create_user("ana", password="test-pass-123")
        self.bogdan = users.create_user("bogdan", password="test-pass-456")
        self.product = Category.objects.get(name="Product")
        self.internet = FakeInternet({
            EMAG_URL: (200, fixture("emag_product.html")),
            STORIA_URL: (200, fixture("storia_listing.html")),
        })
        patcher = mock.patch.object(checks, "http_get", self.internet)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.sleeps = []

    def item(self, owner, url, **fields):
        values = {"owner": owner, "category": self.product, "name": f"Item {url[-6:]}",
                  "url": url, "source": Item.Source.AUTOMATIC}
        values.update(fields)
        return Item.objects.create(**values)

    def run_checks(self, **kwargs):
        return daily.run_daily_checks(sleep=self.sleeps.append, **kwargs)


class RunDailyChecksTests(DailyChecksTestCase):
    def test_checks_everyones_items_and_skips_recent_ones(self):
        """Acceptance criterion 1."""
        ana_item = self.item(self.ana, EMAG_URL)
        bogdan_item = self.item(self.bogdan, STORIA_URL)
        recent = self.item(self.ana, EMAG_URL.replace("TEST", "RECENT"),
                           last_checked=timezone.now() - timedelta(hours=2))
        run = self.run_checks()
        self.assertEqual((run.checked, run.ok, run.skipped), (2, 2, 1))
        self.assertIsNotNone(run.finished_at)
        self.assertEqual(set(run.attempts.values_list("item", flat=True)), {ana_item.pk, bogdan_item.pk})
        self.assertFalse(recent.check_attempts.exists())
        self.assertEqual(PricePoint.objects.filter(source=PricePoint.Source.AUTOMATIC).count(), 2)

    def test_items_checked_over_20_hours_ago_are_checked(self):
        self.item(self.ana, EMAG_URL, last_checked=timezone.now() - timedelta(hours=21))
        self.assertEqual(self.run_checks().checked, 1)

    def test_force_checks_recent_items_too(self):
        """Acceptance criterion 4."""
        self.item(self.ana, EMAG_URL, last_checked=timezone.now() - timedelta(minutes=5))
        run = self.run_checks(force=True)
        self.assertEqual((run.checked, run.skipped), (1, 0))

    def test_one_failing_site_does_not_stop_the_others(self):
        """Acceptance criterion 2."""
        self.internet.pages[EMAG_URL] = (503, "<html><title>eMAG Black Friday</title></html>")
        emag = self.item(self.ana, EMAG_URL)
        storia = self.item(self.ana, STORIA_URL)
        run = self.run_checks()
        self.assertEqual((run.checked, run.ok, run.attention), (2, 1, 1))
        emag.refresh_from_db()
        storia.refresh_from_db()
        self.assertEqual(emag.status, Item.Status.ERROR)
        self.assertEqual(storia.status, Item.Status.ACTIVE)

    def test_unexpected_crash_is_recorded_and_run_continues(self):
        first = self.item(self.ana, EMAG_URL)
        second = self.item(self.ana, STORIA_URL)
        real_check_item = checks.check_item

        def flaky_check_item(item, **kwargs):
            if item.pk == first.pk:
                raise RuntimeError("something odd")
            return real_check_item(item, **kwargs)

        with mock.patch.object(daily, "check_item", flaky_check_item), \
                self.assertLogs("tracker.daily", level="ERROR") as logs:
            run = self.run_checks()
        self.assertIn("CRASHED", logs.output[0])
        self.assertEqual((run.checked, run.ok, run.attention), (2, 1, 1))
        attempt = first.check_attempts.get()
        self.assertEqual((attempt.outcome, attempt.run), (CheckAttempt.Outcome.ERROR, run))
        self.assertIn("RuntimeError: something odd", attempt.message)
        first.refresh_from_db()
        self.assertEqual(first.status, Item.Status.ERROR)
        self.assertEqual(second.check_attempts.get().outcome, CheckAttempt.Outcome.OK)

    def test_second_run_while_one_is_in_progress_is_refused(self):
        """Acceptance criterion 3."""
        self.item(self.ana, EMAG_URL)
        CheckRun.objects.create(started_at=timezone.now() - timedelta(minutes=10))
        with self.assertRaises(daily.AlreadyRunning):
            self.run_checks()
        self.assertEqual(self.internet.requested, [])

    def test_old_unfinished_run_does_not_block(self):
        CheckRun.objects.create(started_at=timezone.now() - timedelta(hours=2))  # e.g. PC shut down mid-run
        self.item(self.ana, EMAG_URL)
        self.assertEqual(self.run_checks().checked, 1)

    def test_manual_paused_and_removed_items_are_not_checked(self):
        Item.objects.create(owner=self.ana, category=self.product, name="Rent")  # manual
        self.item(self.ana, EMAG_URL, status=Item.Status.PAUSED)
        self.item(self.ana, STORIA_URL, status=Item.Status.REMOVED)
        run = self.run_checks()
        self.assertEqual((run.checked, run.skipped), (0, 0))
        self.assertEqual(self.internet.requested, [])

    def test_no_items_still_records_a_run(self):
        run = self.run_checks()
        self.assertEqual(run.checked, 0)
        self.assertIsNotNone(run.finished_at)

    def test_pauses_between_items_not_before_the_first(self):
        self.item(self.ana, EMAG_URL)
        self.item(self.ana, STORIA_URL)
        self.run_checks()
        self.assertEqual(self.sleeps, [daily.PAUSE_SECONDS])

    def test_manual_checks_are_not_linked_to_a_run(self):
        item = self.item(self.ana, EMAG_URL)
        checks.check_item(item)
        self.assertIsNone(item.check_attempts.get().run)


class CheckPricesCommandTests(DailyChecksTestCase):
    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(daily.time, "sleep")  # the command uses the real default pause
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_prints_a_summary(self):
        self.item(self.ana, EMAG_URL, name="Gel")
        out = StringIO()
        call_command("check_prices", stdout=out)
        text = out.getvalue()
        self.assertIn("Daily check started: 1 automatic item(s).", text)
        self.assertIn("Gel (ana): Price unchanged: 119.99 RON.", text)
        self.assertIn("1 checked, 1 OK, 0 need attention, 0 removed, 0 skipped.", text)

    def test_log_file_is_appended(self):
        self.item(self.ana, STORIA_URL, name="Garsoniera Militari")
        with tempfile.TemporaryDirectory() as folder:
            log = Path(folder) / "logs" / "daily_check.log"  # the folder doesn't exist yet
            call_command("check_prices", "--log-file", str(log))
            call_command("check_prices", "--log-file", str(log), "--force")
            text = log.read_text(encoding="utf-8")
        self.assertEqual(text.count("Daily check started"), 2)
        self.assertIn("Garsoniera Militari (ana)", text)

    def test_already_running_exits_quietly(self):
        CheckRun.objects.create(started_at=timezone.now())
        out = StringIO()
        call_command("check_prices", stdout=out)
        self.assertIn("already running", out.getvalue())
        self.assertEqual(CheckRun.objects.count(), 1)
