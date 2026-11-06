from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from datetime import datetime

from tracker import checks, daily, rates
from tracker.models import Category, CheckAttempt, CheckRun, ComparisonGroup, ExchangeRate, Item, PricePoint, Profile
from tracker.tests.helpers import FakeBnr, FakeInternet, fixture

EMAG_URL = "https://www.emag.ro/gel/pd/TEST/"
STORIA_URL = "https://www.storia.ro/ro/oferta/garsoniera-IDTEST"


class ViewTestCase(TestCase):
    def setUp(self):
        users = get_user_model().objects
        self.user = users.create_user("ana", password="test-pass-123")
        self.other = users.create_user("bogdan", password="test-pass-456")
        self.client.force_login(self.user)
        self.product = Category.objects.get(name="Product")
        self.rent = Category.objects.get(name="Rent")
        self.internet = FakeInternet({
            EMAG_URL: (200, fixture("emag_product.html")),
            STORIA_URL: (200, fixture("storia_listing.html")),
        })
        self.bnr = FakeBnr({rates.DAILY_URL: fixture("bnr_daily_https.xml")})
        for patcher in (mock.patch.object(checks, "http_get", self.internet),
                        mock.patch.object(rates, "fetch", self.bnr)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def automatic_item(self, owner=None, **fields):
        values = {"owner": owner or self.user, "category": self.product, "name": "Gel",
                  "url": EMAG_URL, "source": Item.Source.AUTOMATIC}
        values.update(fields)
        return Item.objects.create(**values)


class AddByLinkTests(ViewTestCase):
    url = reverse("item-add-link")

    def test_preview_shows_what_was_read(self):
        response = self.client.post(self.url, {"step": "preview", "url": EMAG_URL + "?ref=fam#1000-ml"})
        self.assertContains(response, "We found this on eMAG")
        self.assertContains(response, "119.99")
        self.assertContains(response, 'value="Gel de spalare hidratant, 976 ml"')
        self.assertEqual(Item.objects.count(), 0)  # nothing saved yet
        self.assertEqual(self.client.session["link_preview"]["url"], EMAG_URL)  # tracking parts removed

    def test_save_creates_automatic_item_with_first_price(self):
        self.client.post(self.url, {"step": "preview", "url": STORIA_URL})
        response = self.client.post(self.url, {
            "step": "save", "name": "Studio near metro", "category": self.rent.pk, "period": "monthly",
        })
        item = Item.objects.get()
        self.assertRedirects(response, reverse("item-detail", args=[item.pk]))
        self.assertEqual((item.owner, item.source, item.status, item.url),
                         (self.user, "automatic", "active", STORIA_URL))
        point = item.price_points.get()
        self.assertEqual((point.amount, point.currency, point.source), (Decimal("399"), "EUR", "automatic"))
        self.assertEqual(item.check_attempts.get().outcome, CheckAttempt.Outcome.OK)
        self.assertIsNotNone(item.last_checked)
        self.assertNotIn("link_preview", self.client.session)

    def test_saved_price_comes_from_the_server_not_the_form(self):
        self.client.post(self.url, {"step": "preview", "url": EMAG_URL})
        self.client.post(self.url, {"step": "save", "name": "Gel", "category": self.product.pk,
                                    "period": "one_time", "price": "1.00"})
        self.assertEqual(PricePoint.objects.get().amount, Decimal("119.99"))

    def test_share_text_without_https_is_previewed(self):
        response = self.client.post(self.url, {"step": "preview",
                                               "url": "Garsoniera de inchiriat www.storia.ro/ro/oferta/garsoniera-IDTEST?session_olx=abc"})
        self.assertContains(response, "We found this on Storia")
        self.assertEqual(self.client.session["link_preview"]["url"], STORIA_URL)

    def test_unsupported_site_is_rejected_without_fetching(self):
        response = self.client.post(self.url, {"step": "preview", "url": "https://www.olx.ro/d/oferta/x.html"})
        self.assertContains(response, "This site isn")
        self.assertContains(response, "add it manually")
        self.assertEqual(self.internet.requested, [])

    def test_blocked_page_shows_reason(self):
        self.internet.pages[EMAG_URL] = (403, "<html>Access Denied</html>")
        response = self.client.post(self.url, {"step": "preview", "url": EMAG_URL})
        self.assertContains(response, "refused the automated visit")
        self.assertNotIn("link_preview", self.client.session)

    def test_duplicate_link_points_to_existing_item(self):
        existing = self.automatic_item()
        response = self.client.post(self.url, {"step": "preview", "url": EMAG_URL})
        self.assertContains(response, "You already track this link.")
        self.assertContains(response, reverse("item-detail", args=[existing.pk]))
        self.assertEqual(self.internet.requested, [])

    def test_another_users_link_is_not_a_duplicate(self):
        self.automatic_item(owner=self.other)
        response = self.client.post(self.url, {"step": "preview", "url": EMAG_URL})
        self.assertContains(response, "We found this on eMAG")


class CheckNowTests(ViewTestCase):
    def setUp(self):
        super().setUp()
        self.item = self.automatic_item()
        PricePoint.objects.create(item=self.item, amount=Decimal("89.49"), currency="RON",
                                  recorded_at=timezone.now() - timedelta(days=4))
        self.check_url = reverse("item-check", args=[self.item.pk])

    def test_detail_page_shows_button(self):
        self.assertContains(self.client.get(reverse("item-detail", args=[self.item.pk])), "Check now")

    def test_changed_price_is_added_to_history(self):
        response = self.client.post(self.check_url, follow=True)
        self.assertContains(response, "New price: 119.99 RON (was 89.49 RON).")
        self.assertEqual(self.item.price_points.count(), 2)
        self.assertContains(response, "Last check")

    def test_cooldown_blocks_a_second_check(self):
        self.client.post(self.check_url)
        requests_after_first = len(self.internet.requested)
        response = self.client.post(self.check_url, follow=True)
        self.assertContains(response, "You can check again in 10 minutes")
        self.assertEqual(len(self.internet.requested), requests_after_first)

    def test_blocked_check_needs_attention_on_dashboard(self):
        self.internet.pages[EMAG_URL] = (403, "<html>Access Denied</html>")
        response = self.client.post(self.check_url, follow=True)
        self.assertContains(response, "Couldn&#x27;t check the price")
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, Item.Status.ERROR)
        self.assertEqual(self.client.get(reverse("dashboard")).context["attention_count"], 1)

    def test_removed_listing_hides_button(self):
        self.internet.pages[EMAG_URL] = (404, "not found")
        self.client.post(self.check_url)
        response = self.client.get(reverse("item-detail", args=[self.item.pk]))
        self.assertContains(response, "Listing removed")
        self.assertNotContains(response, "Check now")

    def test_get_is_not_allowed(self):
        self.assertEqual(self.client.get(self.check_url).status_code, 405)

    def test_other_users_item_is_not_found(self):
        foreign = self.automatic_item(owner=self.other)
        response = self.client.post(reverse("item-check", args=[foreign.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertFalse(foreign.check_attempts.exists())

    def test_manual_item_has_no_button(self):
        manual = Item.objects.create(owner=self.user, category=self.product, name="Rent")
        self.assertNotContains(self.client.get(reverse("item-detail", args=[manual.pk])), "Check now")


class EditAutomaticItemTests(ViewTestCase):
    def test_link_must_stay_on_a_supported_site(self):
        item = self.automatic_item()
        response = self.client.post(reverse("item-update", args=[item.pk]), {
            "name": "Gel", "category": self.product.pk, "url": "https://www.olx.ro/d/x.html", "period": "one_time",
        })
        self.assertContains(response, "need a link from a supported site")
        item.refresh_from_db()
        self.assertEqual(item.url, EMAG_URL)


class AccessTests(ViewTestCase):
    """Basic safety checks for the whole app, added with the new test setup."""

    def test_pages_require_login(self):
        self.client.logout()
        for name in ("dashboard", "item-list", "item-add-link", "comparison-list", "settings"):
            response = self.client.get(reverse(name))
            self.assertRedirects(response, f"{reverse('login')}?next={reverse(name)}", msg_prefix=name)

    def test_users_cannot_see_each_others_items(self):
        foreign = self.automatic_item(owner=self.other, name="Bogdan's TV")
        self.assertEqual(self.client.get(reverse("item-detail", args=[foreign.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("item-update", args=[foreign.pk])).status_code, 404)
        self.assertNotContains(self.client.get(reverse("item-list")), "Bogdan")


class DailyCheckSummaryTests(ViewTestCase):
    def dashboard_text(self):
        return self.client.get(reverse("dashboard")).content.decode()

    def test_no_run_yet(self):
        """Acceptance criterion 6."""
        self.assertIn("No daily check has run yet.", self.dashboard_text())

    def test_counts_only_my_items(self):
        """Acceptance criterion 5."""
        mine = self.automatic_item(name="My gel")
        PricePoint.objects.create(item=mine, amount=Decimal("89.49"), currency="RON",
                                  recorded_at=timezone.now() - timedelta(days=2))
        self.automatic_item(name="My studio", url=STORIA_URL)
        theirs = self.automatic_item(owner=self.other, name="Their gel", url=EMAG_URL.replace("TEST", "OTHER"))
        self.internet.pages[theirs.url] = (403, "<html>Access Denied</html>")
        daily.run_daily_checks(sleep=lambda seconds: None)

        text = self.dashboard_text()
        self.assertIn("Last daily check:", text)
        # Both of mine are OK and both got a new price point; the other user's blocked item isn't counted.
        self.assertIn("2 OK · 2 new prices · 0 need attention", text)
        self.client.force_login(self.other)
        self.assertIn("0 OK · 0 new prices · 1 needs attention", self.dashboard_text())

    def test_run_in_progress(self):
        CheckRun.objects.create(started_at=timezone.now() - timedelta(minutes=2))
        self.assertIn("still running", self.dashboard_text())

    def test_interrupted_run(self):
        CheckRun.objects.create(started_at=timezone.now() - timedelta(hours=3))
        self.assertIn("did not finish", self.dashboard_text())


class CurrencyDisplayTests(ViewTestCase):
    """Milestone 4: prices shown in the viewer's favourite currency."""

    def setUp(self):
        super().setUp()
        ExchangeRate.objects.create(date=datetime(2026, 11, 5).date(), currency="EUR", ron_per_unit=Decimal("5.3398"))
        self.thursday = timezone.make_aware(datetime(2026, 11, 5, 12, 0))
        self.studio = self.automatic_item(name="Studio", url=STORIA_URL, category=self.rent)
        PricePoint.objects.create(item=self.studio, amount=Decimal("100"), currency="EUR", recorded_at=self.thursday)

    def use_currency(self, code, user=None):
        Profile.objects.filter(user=user or self.user).update(favorite_currency=code)

    def test_ron_viewer_sees_eur_price_converted_with_original_underneath(self):
        """Acceptance criterion 1, on the item page."""
        response = self.client.get(reverse("item-detail", args=[self.studio.pk]))
        self.assertContains(response, '533.98 <small>RON</small><span class="price-original">100.00 EUR</span>')

    def test_eur_viewer_sees_ron_price_and_chart_in_eur(self):
        """Acceptance criterion 4."""
        self.use_currency("EUR")
        gel = self.automatic_item(name="Gel")
        PricePoint.objects.create(item=gel, amount=Decimal("119.99"), currency="RON", recorded_at=self.thursday)
        PricePoint.objects.create(item=gel, amount=Decimal("100"), currency="EUR",
                                  recorded_at=self.thursday + timedelta(hours=1))
        response = self.client.get(reverse("item-detail", args=[gel.pk]))
        self.assertContains(response, '22.47 <small>EUR</small><span class="price-original">119.99 RON</span>')
        chart = response.context["chart_data"]
        self.assertEqual((chart["currency"], chart["values"], chart["missing"]), ("EUR", ["22.47", "100.00"], 0))
        self.assertEqual(chart["originals"], ["119.99 RON", ""])

    def test_same_currency_has_no_second_line(self):
        gel = self.automatic_item(name="Gel")
        PricePoint.objects.create(item=gel, amount=Decimal("119.99"), currency="RON", recorded_at=self.thursday)
        self.assertNotContains(self.client.get(reverse("item-detail", args=[gel.pk])), "price-original")

    def test_price_without_rate_shows_note_and_is_left_off_the_chart(self):
        """Acceptance criterion 5."""
        PricePoint.objects.create(item=self.studio, amount=Decimal("350"), currency="EUR",
                                  recorded_at=timezone.make_aware(datetime(2020, 6, 1, 12, 0)))
        response = self.client.get(reverse("item-detail", args=[self.studio.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "no rate")
        self.assertContains(response, "1 price without an exchange rate")
        self.assertEqual(response.context["chart_data"]["values"], ["533.98"])

    def test_two_users_see_their_own_currency(self):
        self.use_currency("EUR", self.other)
        theirs = self.automatic_item(owner=self.other, name="Their studio", url=STORIA_URL + "X", category=self.rent)
        PricePoint.objects.create(item=theirs, amount=Decimal("533.98"), currency="RON", recorded_at=self.thursday)
        self.assertContains(self.client.get(reverse("item-list")), "533.98 <small>RON</small>")
        self.client.force_login(self.other)
        self.assertContains(self.client.get(reverse("item-list")), "100.00 <small>EUR</small>")

    def test_dashboard_list_and_comparison_are_converted(self):
        group = ComparisonGroup.objects.create(owner=self.user, name="Studios")
        group.items.add(self.studio)
        for url in (reverse("dashboard"), reverse("item-list"), reverse("comparison-detail", args=[group.pk])):
            self.assertContains(self.client.get(url), '<span class="price-original">100.00 EUR</span>', msg_prefix=url)

    def test_check_now_message_includes_converted_amount(self):
        """Acceptance criterion 8."""
        self.use_currency("EUR")
        gel = self.automatic_item(name="Gel")
        response = self.client.post(reverse("item-check", args=[gel.pk]), follow=True)
        self.assertContains(response, "Price unchanged: 119.99 RON. (≈ 22.47 EUR in your currency)")
        self.assertEqual(gel.check_attempts.get().message, "Price unchanged: 119.99 RON.")  # history unchanged

    def test_add_by_link_message_includes_converted_amount(self):
        self.use_currency("EUR")
        self.client.post(reverse("item-add-link"), {"step": "preview", "url": EMAG_URL})
        response = self.client.post(reverse("item-add-link"), {
            "step": "save", "name": "Gel", "category": self.product.pk, "period": "one_time"}, follow=True)
        self.assertContains(response, "Now tracking Gel at 119.99 RON (≈ 22.47 EUR).")

    def test_settings_page_no_longer_says_conversion_is_off(self):
        self.assertNotContains(self.client.get(reverse("settings")), "not enabled yet")
