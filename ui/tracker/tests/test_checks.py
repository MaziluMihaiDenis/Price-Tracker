from datetime import datetime, timedelta
from decimal import Decimal
from unittest import mock

import httpx
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from tracker import checks
from tracker.models import Category, CheckAttempt, Item, PricePoint
from tracker.tests.helpers import FakeInternet, fixture

EMAG_URL = "https://www.emag.ro/gel/pd/TEST/"
EMAG_ROBOTS = "https://www.emag.ro/robots.txt"


class CheckItemTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user("ana", password="test-pass-123")
        self.item = Item.objects.create(
            owner=user, category=Category.objects.get(name="Product"), name="Gel",
            url=EMAG_URL, source=Item.Source.AUTOMATIC,
        )
        # A fixed midday time, so "30 minutes ago" is always the same day whenever tests run.
        self.now = timezone.make_aware(datetime(2026, 11, 5, 12, 0))

    def check(self, internet, now=None):
        with mock.patch.object(checks, "http_get", internet):
            return checks.check_item(self.item, now=now or self.now)

    def add_point(self, amount, when):
        return PricePoint.objects.create(item=self.item, amount=Decimal(amount), currency="RON",
                                         recorded_at=when, source=PricePoint.Source.AUTOMATIC)

    def test_first_check_stores_price(self):
        result = self.check(FakeInternet({EMAG_URL: (200, fixture("emag_product.html"))}))
        self.assertEqual(result.outcome, "ok")
        point = self.item.price_points.get()
        self.assertEqual((point.amount, point.currency, point.source), (Decimal("119.99"), "RON", "automatic"))
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, Item.Status.ACTIVE)
        self.assertEqual(self.item.last_checked, self.now)
        self.assertEqual(self.item.check_attempts.get().outcome, CheckAttempt.Outcome.OK)

    def test_changed_price_adds_point(self):
        self.add_point("89.49", self.now - timedelta(hours=1))
        result = self.check(FakeInternet({EMAG_URL: (200, fixture("emag_product.html"))}))
        self.assertEqual(self.item.price_points.count(), 2)
        self.assertIn("New price: 119.99 RON (was 89.49 RON)", result.message)

    def test_same_price_same_day_adds_no_point(self):
        self.add_point("119.99", self.now - timedelta(minutes=30))
        result = self.check(FakeInternet({EMAG_URL: (200, fixture("emag_product.html"))}))
        self.assertIsNone(result.price_point)
        self.assertEqual(self.item.price_points.count(), 1)
        self.assertEqual(self.item.check_attempts.count(), 1)  # the check itself is still recorded
        self.assertIn("Price unchanged", result.message)

    def test_same_price_new_day_adds_point(self):
        self.add_point("119.99", self.now - timedelta(days=1))
        self.check(FakeInternet({EMAG_URL: (200, fixture("emag_product.html"))}))
        self.assertEqual(self.item.price_points.count(), 2)

    def test_blocked_page_needs_attention_and_keeps_history(self):
        self.add_point("89.49", self.now - timedelta(days=1))
        result = self.check(FakeInternet({EMAG_URL: (403, "<html>Access Denied</html>")}))
        self.assertEqual(result.outcome, CheckAttempt.Outcome.BLOCKED)
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, Item.Status.ERROR)
        self.assertIn("refused", self.item.last_error)
        self.assertEqual(self.item.price_points.count(), 1)

    def test_temporarily_unavailable_is_not_called_blocked(self):
        # Seen live on 2026-11-05: eMAG served a "Black Friday" holding page with HTTP 503.
        result = self.check(FakeInternet({EMAG_URL: (503, "<html><title>eMAG Black Friday</title></html>")}))
        self.assertEqual(result.outcome, CheckAttempt.Outcome.ERROR)
        self.assertIn("temporarily unavailable", result.message)

    def test_big_page_mentioning_captcha_is_not_blocked(self):
        html = fixture("emag_product.html").replace("</body>", "<script src='recaptcha.js'></script>" + " " * 60_000 + "</body>")
        self.assertEqual(self.check(FakeInternet({EMAG_URL: (200, html)})).outcome, "ok")

    def test_removed_listing(self):
        result = self.check(FakeInternet({EMAG_URL: (404, "not found")}))
        self.assertEqual(result.outcome, CheckAttempt.Outcome.REMOVED)
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, Item.Status.REMOVED)

    def test_unreadable_price(self):
        result = self.check(FakeInternet({EMAG_URL: (200, "<html>" + "x" * 60_000 + "</html>")}))
        self.assertEqual(result.outcome, CheckAttempt.Outcome.ERROR)
        self.item.refresh_from_db()
        self.assertEqual(self.item.last_error, "Couldn't read the price on this page.")

    def test_timeout_does_not_crash(self):
        result = self.check(FakeInternet({EMAG_URL: httpx.ReadTimeout("slow")}))
        self.assertEqual(result.outcome, CheckAttempt.Outcome.ERROR)
        self.assertIn("didn't respond in time", result.message)

    def test_robots_disallow_means_no_fetch(self):
        internet = FakeInternet({EMAG_ROBOTS: (200, "User-agent: *\nDisallow: /gel/")})
        result = self.check(internet)
        self.assertIn("robots.txt", result.message)
        self.assertNotIn(EMAG_URL, internet.requested)

    def test_recovers_after_an_error(self):
        self.item.status, self.item.last_error = Item.Status.ERROR, "old problem"
        self.item.save()
        self.check(FakeInternet({EMAG_URL: (200, fixture("emag_product.html"))}))
        self.item.refresh_from_db()
        self.assertEqual((self.item.status, self.item.last_error), (Item.Status.ACTIVE, ""))

    def test_paused_and_manual_items_are_skipped(self):
        internet = FakeInternet()
        self.item.status = Item.Status.PAUSED
        self.assertEqual(self.check(internet).outcome, "skipped")
        self.item.status, self.item.source = Item.Status.ACTIVE, Item.Source.MANUAL
        self.assertEqual(self.check(internet).outcome, "skipped")
        self.assertEqual(internet.requested, [])

    def test_redirect_to_other_site_is_refused(self):
        fake_response = mock.Mock(is_redirect=True, headers={"location": "http://localhost/admin"})
        with mock.patch("httpx.Client.get", return_value=fake_response) as fake_get:
            with self.assertRaises(checks.UnsafeRedirect):
                checks.http_get(EMAG_URL)
        fake_get.assert_called_once_with(EMAG_URL)  # localhost was never requested

    def test_cooldown(self):
        self.assertEqual(checks.seconds_until_next_check(self.item, self.now), 0)
        self.item.last_checked = self.now - timedelta(minutes=4)
        self.assertEqual(checks.seconds_until_next_check(self.item, self.now), 6 * 60)
        self.item.last_checked = self.now - timedelta(minutes=11)
        self.assertEqual(checks.seconds_until_next_check(self.item, self.now), 0)
