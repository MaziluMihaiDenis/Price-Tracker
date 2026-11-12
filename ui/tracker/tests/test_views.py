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

    def test_archived_link_points_to_the_archived_item(self):
        """Milestone 3a review: an archived item's link is recognised and the user is told how to restore it."""
        archived = self.automatic_item(archived_at=timezone.make_aware(datetime(2026, 11, 7, 10, 0)))
        response = self.client.post(self.url, {"step": "preview", "url": EMAG_URL})
        self.assertContains(response, "You archived this item on 7 Nov 2026. Open it to restore it.")
        self.assertNotContains(response, "You already track this link.")
        self.assertContains(response, reverse("item-detail", args=[archived.pk]))
        self.assertEqual(self.internet.requested, [])  # the page isn't read again
        self.assertEqual(Item.objects.filter(owner=self.user).count(), 1)  # no second item

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


class IndicatorDisplayTests(ViewTestCase):
    """Milestone 5: price change arrows, "Lowest ever", and the "Price changes" panel."""

    def item_with_prices(self, name, *amounts, owner=None, days_ago=None):
        """An item with RON prices one day apart; the last price is `days_ago` days old (default: today)."""
        item = Item.objects.create(owner=owner or self.user, category=self.product, name=name)
        last = timezone.now() - timedelta(days=days_ago or 0)
        for position, amount in enumerate(amounts):
            PricePoint.objects.create(item=item, amount=Decimal(amount), currency="RON",
                                      recorded_at=last - timedelta(days=len(amounts) - 1 - position))
        return item

    def test_item_list_shows_a_green_drop(self):
        """Acceptance criterion 1."""
        self.item_with_prices("Gel", "129.99", "119.99")
        response = self.client.get(reverse("item-list"))
        self.assertContains(response, 'class="price-change change-down"')
        self.assertContains(response, '<span class="visually-hidden">down</span> 7.7%')

    def test_repeats_then_a_rise(self):
        """Acceptance criterion 2."""
        self.item_with_prices("Detergent", "100", "100", "100", "110")
        response = self.client.get(reverse("item-list"))
        self.assertContains(response, '<span class="visually-hidden">up</span> 10%')

    def test_no_indicator_for_a_single_or_unchanged_price(self):
        """Acceptance criterion 3."""
        self.item_with_prices("Once", "50")
        self.item_with_prices("Same", "70", "70")
        for page in ("item-list", "dashboard"):
            response = self.client.get(reverse(page))
            self.assertNotContains(response, "price-change change-")
            self.assertNotContains(response, "Lowest ever")

    def test_lowest_ever_badge(self):
        """Acceptance criterion 6, on the item list."""
        self.item_with_prices("Back at lowest", "120", "110", "115", "110")
        self.item_with_prices("Not lowest", "120", "110", "115")
        response = self.client.get(reverse("item-list"))
        self.assertContains(response, '<span class="lowest-badge">Lowest ever</span>', count=1)

    def test_price_changes_panel_window_and_order(self):
        """Acceptance criterion 7."""
        self.item_with_prices("Small drop", "100", "95", days_ago=1)  # 5%
        self.item_with_prices("Big rise", "100", "130", days_ago=3)  # 30%
        self.item_with_prices("Old change", "100", "50", days_ago=10)  # outside the 7 days
        response = self.client.get(reverse("dashboard"))
        names = [item.name for item in response.context["price_changes"]]
        self.assertEqual(names, ["Big rise", "Small drop"])
        self.assertNotContains(response, "No price changes in the last 7 days.")

    def test_change_counts_from_when_the_new_price_first_appeared(self):
        """Unchanged daily checks after an old change don't bring it back into the panel."""
        item = self.item_with_prices("Old drop", "100", "80", days_ago=10)
        for days_ago in (2, 1, 0):
            PricePoint.objects.create(item=item, amount=Decimal("80"), currency="RON",
                                      recorded_at=timezone.now() - timedelta(days=days_ago))
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.context["price_changes"], [])
        self.assertContains(response, "No price changes in the last 7 days.")

    def test_panel_shows_only_your_own_items(self):
        """Acceptance criterion 8."""
        self.item_with_prices("Ana's gel", "100", "90")
        self.item_with_prices("Bogdan's rent", "2000", "2500", owner=self.other)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual([item.name for item in response.context["price_changes"]], ["Ana's gel"])
        self.assertNotContains(response, "Bogdan&#x27;s rent")
        self.client.force_login(self.other)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual([item.name for item in response.context["price_changes"]], ["Bogdan's rent"])
        self.assertNotContains(response, "Ana&#x27;s gel")

    def test_item_page_shows_change_lowest_and_highest(self):
        """Acceptance criterion 9."""
        item = self.item_with_prices("Gel", "120", "110", "130", "119.99")
        response = self.client.get(reverse("item-detail", args=[item.pk]))
        self.assertContains(response, '<span class="visually-hidden">down</span> 7.7%')
        self.assertContains(response, "Was 130.00 RON until")
        self.assertContains(response, "Lowest: <strong>110.00 <small>RON</small></strong>")
        self.assertContains(response, "Highest: <strong>130.00 <small>RON</small></strong>")

    def test_item_page_converts_lowest_and_highest_to_the_viewers_currency(self):
        """Acceptance criterion 9 (EUR viewer)."""
        ExchangeRate.objects.create(date=datetime(2026, 11, 5).date(), currency="EUR", ron_per_unit=Decimal("5.3398"))
        Profile.objects.filter(user=self.user).update(favorite_currency="EUR")
        item = Item.objects.create(owner=self.user, category=self.product, name="Gel")
        for day, amount in ((5, "119.99"), (6, "129.99")):
            PricePoint.objects.create(item=item, amount=Decimal(amount), currency="RON",
                                      recorded_at=timezone.make_aware(datetime(2026, 11, day, 12)))
        response = self.client.get(reverse("item-detail", args=[item.pk]))
        self.assertContains(response, 'Lowest: <strong>22.47 <small>EUR</small><span class="price-original">119.99 RON</span>')

    def test_unchanged_eur_rent_has_no_arrow_for_a_ron_viewer(self):
        """Acceptance criterion 4, through the page."""
        ExchangeRate.objects.create(date=datetime(2026, 10, 30).date(), currency="EUR", ron_per_unit=Decimal("5.3426"))
        ExchangeRate.objects.create(date=datetime(2026, 11, 5).date(), currency="EUR", ron_per_unit=Decimal("5.3398"))
        rent = Item.objects.create(owner=self.user, category=self.rent, name="Rent")
        for day in (datetime(2026, 10, 30, 12), datetime(2026, 11, 5, 12)):
            PricePoint.objects.create(item=rent, amount=Decimal("470"), currency="EUR",
                                      recorded_at=timezone.make_aware(day))
        for url in (reverse("item-list"), reverse("item-detail", args=[rent.pk])):
            self.assertNotContains(self.client.get(url), "price-change change-")

    def test_query_count_does_not_grow_with_items(self):
        """Acceptance criterion 10: one query loads every item's history."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        def queries(page):
            with CaptureQueriesContext(connection) as captured:
                self.assertEqual(self.client.get(reverse(page)).status_code, 200)
            rate_loads = [q for q in captured if 'FROM "tracker_exchangerate"' in q["sql"]]
            self.assertEqual(len(rate_loads), 1, "the view's rate book is shared with the templates")
            return len(captured)

        self.item_with_prices("First", "100", "90")
        with_one = {page: queries(page) for page in ("dashboard", "item-list")}
        for number in range(9):
            self.item_with_prices(f"Item {number}", "100", "90", "95")
        self.assertEqual({page: queries(page) for page in ("dashboard", "item-list")}, with_one)

    def test_prices_saved_at_the_same_minute_use_the_last_saved_one(self):
        """The current price and the arrow agree when several prices share one time."""
        item = Item.objects.create(owner=self.user, category=self.product, name="Pillow")
        same_time = timezone.now() - timedelta(hours=1)
        for amount in ("150.00", "149.99"):
            PricePoint.objects.create(item=item, amount=Decimal(amount), currency="RON", recorded_at=same_time)
        self.assertEqual(Item.objects.get(pk=item.pk).current_price.amount, Decimal("149.99"))
        response = self.client.get(reverse("item-list"))
        self.assertContains(response, "149.99 <small>RON</small>")
        self.assertNotContains(response, "150.00 <small>RON</small>")


class ComparisonTests(ViewTestCase):
    """Milestone 8: the group chart, Per month, Cheapest, editing, deleting and "Add to comparison"."""

    def setUp(self):
        super().setUp()
        self.when = timezone.make_aware(datetime(2026, 11, 5, 12))
        ExchangeRate.objects.create(date=self.when.date(), currency="EUR", ron_per_unit=Decimal("5.3398"))

    def priced_item(self, name, *prices, owner=None, period=Item.Period.MONTHLY):
        item = Item.objects.create(owner=owner or self.user, category=self.rent, name=name, period=period)
        for days, (amount, currency) in enumerate(prices):
            PricePoint.objects.create(item=item, amount=Decimal(amount), currency=currency,
                                      recorded_at=self.when - timedelta(days=len(prices) - 1 - days))
        return item

    def group(self, *items, name="Studios", owner=None):
        group = ComparisonGroup.objects.create(owner=owner or self.user, name=name)
        group.items.set(items)
        return group

    def detail(self, group):
        return self.client.get(reverse("comparison-detail", args=[group.pk]))

    def test_chart_has_one_line_per_item_in_the_viewers_currency(self):
        """Acceptance criterion 1."""
        group = self.group(self.priced_item("TV RON", ("2500", "RON"), period=Item.Period.ONE_TIME),
                           self.priced_item("TV EUR", ("470", "EUR"), period=Item.Period.ONE_TIME))
        response = self.detail(group)
        chart = response.context["chart_data"]
        self.assertEqual(chart["currency"], "RON")
        self.assertEqual({series["name"]: series["points"][0]["y"] for series in chart["series"]},
                         {"TV RON": "2500.00", "TV EUR": "2509.71"})
        self.assertContains(response, 'id="comparisonChart"')
        self.assertContains(response, "comparison-chart.js")

    def test_mixed_periods_show_the_warning_and_per_month(self):
        """Acceptance criterion 3."""
        group = self.group(self.priced_item("Gym", ("1200", "RON"), period=Item.Period.YEARLY),
                           self.priced_item("Rent", ("2500", "RON")))
        response = self.detail(group)
        self.assertContains(response, "this group mixes Monthly and Yearly prices")
        self.assertContains(response, "<th>Per month</th>")
        self.assertContains(response, "100.00 <small>RON</small>")

    def test_monthly_only_group_has_no_warning_or_per_month(self):
        """Acceptance criterion 3 (the negative case)."""
        response = self.detail(self.group(self.priced_item("A", ("2500", "RON")), self.priced_item("B", ("2800", "RON"))))
        self.assertNotContains(response, "Different periods")
        self.assertNotContains(response, "Per month")

    def test_cheapest_and_percent_above_it(self):
        """Acceptance criterion 4."""
        response = self.detail(self.group(self.priced_item("Flat A", ("2500", "RON")),
                                          self.priced_item("Flat B", ("2800", "RON"))))
        self.assertContains(response, '<span class="cheapest-badge">Cheapest</span>', count=1)
        self.assertContains(response, '<span class="vs-cheapest">+12% vs cheapest</span>', count=1)

    def test_one_time_and_monthly_are_not_compared(self):
        """Acceptance criterion 5."""
        response = self.detail(self.group(self.priced_item("TV", ("3000", "RON"), period=Item.Period.ONE_TIME),
                                          self.priced_item("Rent", ("2500", "RON"))))
        self.assertNotContains(response, "cheapest-badge")
        self.assertNotContains(response, "vs cheapest")

    def test_table_shows_change_arrows(self):
        """Acceptance criterion 6."""
        response = self.detail(self.group(self.priced_item("Flat", ("2600", "RON"), ("2500", "RON"))))
        self.assertContains(response, '<span class="visually-hidden">down</span> 3.8%')
        self.assertContains(response, '<span class="lowest-badge">Lowest ever</span>')

    def test_rename_and_change_items(self):
        """Acceptance criterion 7."""
        first, second = self.priced_item("A", ("1", "RON")), self.priced_item("B", ("2", "RON"))
        group = self.group(first)
        response = self.client.post(reverse("comparison-update", args=[group.pk]),
                                    {"name": "Flats", "items": [second.pk]})
        self.assertRedirects(response, reverse("comparison-detail", args=[group.pk]))
        group.refresh_from_db()
        self.assertEqual((group.name, list(group.items.all())), ("Flats", [second]))

    def test_duplicate_name_shows_a_friendly_error(self):
        """Acceptance criterion 7: a form error, not a crash."""
        self.group(name="Studios")
        response = self.client.post(reverse("comparison-create"), {"name": "studios"})
        self.assertContains(response, "You already have a comparison with this name.")
        other = self.group(name="Flats")
        response = self.client.post(reverse("comparison-update", args=[other.pk]), {"name": "Studios"})
        self.assertContains(response, "You already have a comparison with this name.")
        self.assertEqual(ComparisonGroup.objects.filter(owner=self.user).count(), 2)

    def test_renaming_to_its_own_name_is_fine(self):
        group = self.group(name="Studios")
        response = self.client.post(reverse("comparison-update", args=[group.pk]), {"name": "Studios"})
        self.assertRedirects(response, reverse("comparison-detail", args=[group.pk]))

    def test_another_user_may_use_the_same_name(self):
        self.group(name="Studios", owner=self.other)
        response = self.client.post(reverse("comparison-create"), {"name": "Studios"})
        self.assertEqual(response.status_code, 302)

    def test_delete_needs_confirmation_and_keeps_items(self):
        """Acceptance criterion 8."""
        item = self.priced_item("Flat", ("2500", "RON"))
        group = self.group(item)
        response = self.client.get(reverse("comparison-delete", args=[group.pk]))
        self.assertContains(response, "Your items and their prices are kept.")
        self.assertTrue(ComparisonGroup.objects.filter(pk=group.pk).exists())  # GET deletes nothing
        response = self.client.post(reverse("comparison-delete", args=[group.pk]))
        self.assertRedirects(response, reverse("comparison-list"))
        self.assertFalse(ComparisonGroup.objects.filter(pk=group.pk).exists())
        self.assertTrue(Item.objects.filter(pk=item.pk).exists())
        self.assertEqual(item.price_points.count(), 1)

    def test_add_to_comparison_from_the_item_page(self):
        """Acceptance criterion 9."""
        item = self.priced_item("Flat", ("2500", "RON"))
        group = self.group(name="Studios")
        page = self.client.get(reverse("item-detail", args=[item.pk]))
        self.assertContains(page, "Not in any comparison yet.")
        self.assertContains(page, reverse("item-add-to-comparison", args=[item.pk]))
        response = self.client.post(reverse("item-add-to-comparison", args=[item.pk]), {"group": group.pk})
        self.assertRedirects(response, reverse("item-detail", args=[item.pk]), fetch_redirect_response=False)
        self.assertIn(item, group.items.all())
        page = self.client.get(reverse("item-detail", args=[item.pk]))
        self.assertContains(page, "Added to Studios.")
        self.assertContains(page, reverse("comparison-detail", args=[group.pk]))
        self.assertNotContains(page, reverse("item-add-to-comparison", args=[item.pk]))  # no group left to add to

    def test_item_page_without_groups_offers_to_create_one(self):
        """Acceptance criterion 9."""
        item = self.priced_item("Flat", ("2500", "RON"))
        page = self.client.get(reverse("item-detail", args=[item.pk]))
        self.assertContains(page, "Create a comparison")
        self.assertNotContains(page, reverse("item-add-to-comparison", args=[item.pk]))

    def test_add_to_comparison_only_accepts_post(self):
        item = self.priced_item("Flat", ("2500", "RON"))
        self.assertEqual(self.client.get(reverse("item-add-to-comparison", args=[item.pk])).status_code, 405)

    def test_other_users_cannot_touch_your_groups(self):
        """Acceptance criterion 10."""
        group = self.group(self.priced_item("Flat", ("2500", "RON")))
        self.client.force_login(self.other)
        for name in ("comparison-detail", "comparison-update", "comparison-delete"):
            self.assertEqual(self.client.get(reverse(name, args=[group.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("comparison-delete", args=[group.pk])).status_code, 404)
        response = self.client.post(reverse("comparison-update", args=[group.pk]), {"name": "Mine"})
        self.assertEqual(response.status_code, 404)
        self.assertTrue(ComparisonGroup.objects.filter(pk=group.pk, name="Studios").exists())

    def test_items_cannot_cross_between_users(self):
        """Acceptance criterion 10."""
        mine = self.priced_item("Mine", ("1", "RON"))
        my_group = self.group(name="Mine")
        theirs = self.priced_item("Theirs", ("2", "RON"), owner=self.other)
        their_group = self.group(name="Theirs", owner=self.other)
        # Your item into their group: refused.
        self.client.post(reverse("item-add-to-comparison", args=[mine.pk]), {"group": their_group.pk})
        self.assertFalse(their_group.items.exists())
        # Their item into your group: that item page isn't yours.
        response = self.client.post(reverse("item-add-to-comparison", args=[theirs.pk]), {"group": my_group.pk})
        self.assertEqual(response.status_code, 404)
        # Their item through your edit form: not a valid choice.
        response = self.client.post(reverse("comparison-update", args=[my_group.pk]),
                                    {"name": "Mine", "items": [theirs.pk]})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(my_group.items.exists())

    def test_empty_group_and_group_without_prices(self):
        """Acceptance criterion 11."""
        response = self.detail(self.group(name="Empty"))
        self.assertContains(response, "This group is empty")
        self.assertNotContains(response, 'id="comparisonChart"')
        no_price = Item.objects.create(owner=self.user, category=self.rent, name="No price")
        response = self.detail(self.group(no_price, name="No prices"))
        self.assertContains(response, "No price recorded")
        self.assertNotContains(response, 'id="comparisonChart"')

    def test_query_count_does_not_grow_with_items(self):
        """Acceptance criterion 12."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        group = self.group(self.priced_item("A", ("100", "RON"), ("90", "RON")),
                           self.priced_item("B", ("110", "EUR")))

        def queries():
            with CaptureQueriesContext(connection) as captured:
                self.assertEqual(self.detail(group).status_code, 200)
            return len(captured)

        with_two = queries()
        for number in range(8):
            group.items.add(self.priced_item(f"Item {number}", ("100", "RON"), ("95", "RON")))
        self.assertEqual(queries(), with_two)


class ArchiveAndDeleteTests(ViewTestCase):
    """Milestone 3a: archive, restore, permanent delete, and deleting one price."""

    def setUp(self):
        super().setUp()
        self.flat = Item.objects.create(owner=self.user, category=self.rent, name="Studio Militari",
                                        period=Item.Period.MONTHLY)
        now = timezone.now()
        self.old_price = PricePoint.objects.create(item=self.flat, amount=Decimal("2600"), currency="RON",
                                                   recorded_at=now - timedelta(days=2))
        self.new_price = PricePoint.objects.create(item=self.flat, amount=Decimal("2500"), currency="RON",
                                                   recorded_at=now - timedelta(days=1))
        self.group = ComparisonGroup.objects.create(owner=self.user, name="Studios")
        self.group.items.set([self.flat])

    def archive(self, item=None):
        return self.client.post(reverse("item-archive", args=[(item or self.flat).pk]))

    def test_archived_item_is_hidden_everywhere(self):
        """Acceptance criterion 1."""
        self.archive()
        self.flat.refresh_from_db()
        self.assertTrue(self.flat.is_archived)
        self.assertNotContains(self.client.get(reverse("item-list")), "Studio Militari")
        dashboard = self.client.get(reverse("dashboard"))
        self.assertNotContains(dashboard, "Studio Militari")
        self.assertEqual((dashboard.context["item_count"], dashboard.context["price_changes"]), (0, []))
        comparison = self.client.get(reverse("comparison-detail", args=[self.group.pk]))
        self.assertNotContains(comparison, "Studio Militari")
        self.assertContains(self.client.get(reverse("comparison-list")), "0 tracked items")
        form = self.client.get(reverse("comparison-update", args=[self.group.pk]))
        self.assertNotContains(form, "Studio Militari")
        page = self.client.get(reverse("item-detail", args=[self.flat.pk]))
        self.assertContains(page, "Archived on")
        self.assertNotContains(page, reverse("item-add-to-comparison", args=[self.flat.pk]))

    def test_archived_automatic_item_is_not_checked(self):
        """Acceptance criterion 2."""
        auto = self.automatic_item()
        self.archive(auto)
        page = self.client.get(reverse("item-detail", args=[auto.pk]))
        self.assertNotContains(page, "Check now")
        self.client.post(reverse("item-check", args=[auto.pk]))
        self.assertEqual(self.internet.requested, [])
        self.assertFalse(auto.check_attempts.exists())

    def test_restore_brings_it_back_unchanged(self):
        """Acceptance criterion 3."""
        Item.objects.filter(pk=self.flat.pk).update(status=Item.Status.PAUSED)
        self.archive()
        response = self.client.post(reverse("item-restore", args=[self.flat.pk]))
        self.assertRedirects(response, reverse("item-detail", args=[self.flat.pk]), fetch_redirect_response=False)
        self.flat.refresh_from_db()
        self.assertFalse(self.flat.is_archived)
        self.assertEqual(self.flat.status, Item.Status.PAUSED)
        self.assertEqual(list(self.group.items.all()), [self.flat])
        self.assertContains(self.client.get(reverse("comparison-detail", args=[self.group.pk])), "Studio Militari")
        self.assertContains(self.client.get(reverse("item-list")), "Studio Militari")

    def test_editing_a_group_keeps_its_archived_members(self):
        """Acceptance criterion 4."""
        other = Item.objects.create(owner=self.user, category=self.rent, name="Other flat")
        self.archive()
        response = self.client.post(reverse("comparison-update", args=[self.group.pk]),
                                    {"name": "Studios", "items": [other.pk]})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(set(self.group.items.all()), {self.flat, other})

    def test_archived_filter_shows_only_archived_items(self):
        """Acceptance criterion 5."""
        Item.objects.create(owner=self.user, category=self.rent, name="Active flat")
        self.archive()
        response = self.client.get(reverse("item-list"), {"status": "archived"})
        self.assertContains(response, "Studio Militari")
        self.assertNotContains(response, "Active flat")
        self.assertContains(response, '<option value="archived" selected>Archived</option>')

    def test_archive_and_restore_only_accept_post(self):
        for name in ("item-archive", "item-restore"):
            self.assertEqual(self.client.get(reverse(name, args=[self.flat.pk])).status_code, 405)
        self.flat.refresh_from_db()
        self.assertFalse(self.flat.is_archived)

    def test_permanent_delete_after_confirmation(self):
        """Acceptance criterion 6."""
        CheckAttempt.objects.create(item=self.flat, attempted_at=timezone.now(), outcome=CheckAttempt.Outcome.OK)
        self.archive()
        url = reverse("item-delete", args=[self.flat.pk])
        confirm = self.client.get(url)
        self.assertContains(confirm, "Its 2 prices and its check history will be removed, and it will leave 1 comparison.")
        self.assertTrue(Item.objects.filter(pk=self.flat.pk).exists())  # GET deletes nothing
        response = self.client.post(url)
        self.assertRedirects(response, reverse("item-list"), fetch_redirect_response=False)
        self.assertFalse(Item.objects.filter(pk=self.flat.pk).exists())
        self.assertFalse(PricePoint.objects.filter(item_id=self.flat.pk).exists())
        self.assertFalse(CheckAttempt.objects.filter(item_id=self.flat.pk).exists())
        self.assertTrue(ComparisonGroup.objects.filter(pk=self.group.pk).exists())
        self.assertFalse(self.group.items.exists())

    def test_items_that_are_not_archived_cannot_be_deleted(self):
        """Acceptance criterion 6."""
        for method in (self.client.get, self.client.post):
            response = method(reverse("item-delete", args=[self.flat.pk]))
            self.assertRedirects(response, reverse("item-detail", args=[self.flat.pk]), fetch_redirect_response=False)
        self.assertTrue(Item.objects.filter(pk=self.flat.pk).exists())

    def test_delete_one_price(self):
        """Acceptance criterion 7."""
        url = reverse("price-delete", args=[self.flat.pk, self.new_price.pk])
        self.assertContains(self.client.get(url), "2500.00 RON")
        self.assertTrue(PricePoint.objects.filter(pk=self.new_price.pk).exists())  # GET deletes nothing
        self.client.post(url)
        self.assertEqual(list(self.flat.price_points.all()), [self.old_price])
        page = self.client.get(reverse("item-detail", args=[self.flat.pk]))
        self.assertIsNone(page.context["summary"].change)  # the drop to 2500 is gone
        self.assertContains(page, "2600.00 <small>RON</small>")

    def test_delete_the_last_price(self):
        """Acceptance criterion 7."""
        for point in (self.new_price, self.old_price):
            self.client.post(reverse("price-delete", args=[self.flat.pk, point.pk]))
        page = self.client.get(reverse("item-detail", args=[self.flat.pk]))
        self.assertContains(page, "No price history yet")
        self.assertContains(self.client.get(reverse("item-list")), "No price recorded")

    def test_a_price_must_belong_to_the_item_in_the_address(self):
        other_item = Item.objects.create(owner=self.user, category=self.rent, name="Other")
        response = self.client.post(reverse("price-delete", args=[other_item.pk, self.new_price.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(PricePoint.objects.filter(pk=self.new_price.pk).exists())

    def test_other_users_cannot_archive_restore_or_delete(self):
        """Acceptance criterion 8."""
        self.client.force_login(self.other)
        pk = self.flat.pk
        for name in ("item-archive", "item-restore", "item-delete"):
            self.assertEqual(self.client.post(reverse(name, args=[pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("item-delete", args=[pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("price-delete", args=[pk, self.new_price.pk])).status_code, 404)
        self.flat.refresh_from_db()
        self.assertFalse(self.flat.is_archived)
        self.assertEqual(self.flat.price_points.count(), 2)
        # Not even an archived item of yours can be deleted by them.
        Item.objects.filter(pk=pk).update(archived_at=timezone.now())
        self.assertEqual(self.client.post(reverse("item-delete", args=[pk])).status_code, 404)
        self.assertTrue(Item.objects.filter(pk=pk).exists())


class CategoryPageTests(ViewTestCase):
    """Milestone 3b: the staff-only Categories pages."""

    def setUp(self):
        super().setUp()
        get_user_model().objects.filter(pk=self.user.pk).update(is_staff=True)

    def rows(self, *rows, initial=0):
        """Formset data: each row is a dict of label/type/unit/choices/key/ORDER/DELETE."""
        data = {"fields-TOTAL_FORMS": str(len(rows)), "fields-INITIAL_FORMS": str(initial),
                "fields-MIN_NUM_FORMS": "0", "fields-MAX_NUM_FORMS": "13"}
        for index, row in enumerate(rows):
            row = {"type": "text", **row}
            for name, value in row.items():
                if value is not None:
                    data[f"fields-{index}-{name}"] = value
        return data

    def create(self, name, *rows, period="one_time"):
        return self.client.post(reverse("category-create"),
                                {"name": name, "default_period": period, **self.rows(*rows)})

    def test_staff_create_a_category_with_fields(self):
        """Acceptance criterion 1."""
        response = self.create("Fuel", {"label": "Litres", "type": "number", "unit": "l", "ORDER": "1"},
                               {"label": "Station", "type": "choice", "choices": "Petrom, OMV", "ORDER": "2"})
        self.assertRedirects(response, reverse("category-list"))
        fuel = Category.objects.get(name="Fuel")
        self.assertEqual(fuel.field_definitions, [
            {"key": "litres", "label": "Litres", "type": "number", "unit": "l"},
            {"key": "station", "label": "Station", "type": "choice", "choices": ["Petrom", "OMV"]}])
        page = self.client.get(reverse("item-create"))
        self.assertContains(page, "Litres (l)")

    def test_non_staff_get_page_not_found_and_no_link(self):
        """Acceptance criterion 2."""
        self.client.force_login(self.other)
        rent = Category.objects.get(name="Rent")
        for url in (reverse("category-list"), reverse("category-create"),
                    reverse("category-update", args=[rent.pk]), reverse("category-delete", args=[rent.pk])):
            self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(reverse("category-delete", args=[rent.pk])).status_code, 404)
        self.assertNotContains(self.client.get(reverse("dashboard")), reverse("category-list"))
        self.assertContains(self.client.get(reverse("item-create")), "Rent")  # still usable

    def test_staff_see_the_sidebar_link(self):
        self.assertContains(self.client.get(reverse("dashboard")), reverse("category-list"))

    def test_rename_keeps_key_and_type_is_locked(self):
        """Acceptance criterion 7."""
        rent = Category.objects.get(name="Rent")
        response = self.client.post(reverse("category-update", args=[rent.pk]), {
            "name": "Rent", "default_period": "monthly",
            **self.rows({"key": "area", "label": "Surface", "type": "text", "unit": "m²", "ORDER": "1"},
                        {"key": "rooms", "label": "Rooms", "ORDER": "2"},
                        {"key": "location", "label": "Location", "ORDER": "3"},
                        {"key": "furnished", "label": "Furnished", "ORDER": "4", "DELETE": "on"}, initial=4)})
        self.assertRedirects(response, reverse("category-list"))
        rent.refresh_from_db()
        self.assertEqual(rent.field_definitions, [
            {"key": "area", "label": "Surface", "type": "number", "unit": "m²"},  # still a number
            {"key": "rooms", "label": "Rooms", "type": "number"},
            {"key": "location", "label": "Location", "type": "location"}])

    def test_limits(self):
        """Acceptance criterion 8."""
        response = self.create("Two places", {"label": "Home", "type": "location"}, {"label": "Work", "type": "location"})
        self.assertContains(response, "only one Location field")
        response = self.create("Too many", *[{"label": f"Field {n}"} for n in range(11)])
        self.assertContains(response, "at most 10 fields")
        response = self.create("Twins", {"label": "Size"}, {"label": "size"})
        self.assertContains(response, "Two fields are called")
        response = self.create("Empty choice", {"label": "Heating", "type": "choice"})
        self.assertContains(response, "enter its options")
        self.assertFalse(Category.objects.filter(name__in=["Two places", "Too many", "Twins", "Empty choice"]).exists())

    def test_readding_a_removed_field_brings_its_values_back(self):
        """Acceptance criterion 7: a new field named like a removed one gets the same key."""
        product = Category.objects.get(name="Product")
        Category.objects.filter(pk=product.pk).update(field_definitions=[])
        self.client.post(reverse("category-update", args=[product.pk]),
                         {"name": "Product", "default_period": "one_time", **self.rows({"label": "Brand"})})
        product.refresh_from_db()
        self.assertEqual(product.field_definitions[0]["key"], "brand")

    def test_duplicate_category_name(self):
        response = self.create("rent")
        self.assertContains(response, "A category with this name already exists.")

    def test_delete_only_unused_categories(self):
        """Acceptance criterion 12."""
        Item.objects.create(owner=self.other, category=self.rent, name="Their flat")
        response = self.client.get(reverse("category-delete", args=[self.rent.pk]))
        self.assertContains(response, "Used by 1 item, so it can’t be deleted.")
        self.client.post(reverse("category-delete", args=[self.rent.pk]))
        self.assertTrue(Category.objects.filter(pk=self.rent.pk).exists())
        fuel = Category.objects.create(name="Fuel")
        self.assertContains(self.client.get(reverse("category-delete", args=[fuel.pk])), "No items use this category.")
        self.assertTrue(Category.objects.filter(pk=fuel.pk).exists())  # GET deletes nothing
        response = self.client.post(reverse("category-delete", args=[fuel.pk]))
        self.assertRedirects(response, reverse("category-list"))
        self.assertFalse(Category.objects.filter(pk=fuel.pk).exists())


class CustomFieldValueTests(ViewTestCase):
    """Milestone 3b: custom values in the item forms, on the item page and in comparisons."""

    def manual_post(self, category, custom=None, **fields):
        data = {"name": "Studio", "category": category.pk, "period": "monthly", "description": "", "url": "",
                "price-amount": "2500", "price-currency": "RON", "price-recorded_at": "2026-11-05T12:00", "price-note": ""}
        data.update(fields)
        for name, value in (custom or {}).items():
            data[f"cf{category.pk}-{name}"] = value
        return self.client.post(reverse("item-create"), data)

    def test_create_with_values_and_show_them(self):
        """Acceptance criteria 4, 9 and 10."""
        response = self.manual_post(self.rent, {"area": "32", "furnished": "true", "location__lat": "44.43",
                                                "location__lon": "26.05", "location__address": "Strada Exemplului"})
        item = Item.objects.get(name="Studio")
        self.assertRedirects(response, reverse("item-detail", args=[item.pk]))
        self.assertEqual(item.custom_values, {"area": "32", "furnished": True, "location": {
            "lat": 44.43, "lon": 26.05, "address": "Strada Exemplului"}})
        page = self.client.get(reverse("item-detail", args=[item.pk]))
        self.assertContains(page, "<dt>Area</dt><dd>32 m²</dd>")
        self.assertContains(page, "<dt>Furnished</dt><dd>Yes</dd>")
        self.assertContains(page, "Strada Exemplului")
        self.assertContains(page, "https://www.openstreetmap.org/?mlat=44.430000&amp;mlon=26.050000")
        self.assertContains(page, 'data-static-map="item-map-data"')
        self.assertContains(page, "leaflet.js")
        self.assertContains(page, "44.43000, 26.05000")  # also as text, for when the map can't load

    def test_invalid_values_save_nothing(self):
        """Acceptance criteria 4, 5 and 9."""
        for custom in ({"area": "abc"}, {"location__lat": "200", "location__lon": "26"}):
            response = self.manual_post(self.rent, custom)
            self.assertEqual(response.status_code, 200)
        self.assertFalse(Item.objects.filter(name="Studio").exists())
        Category.objects.filter(pk=self.rent.pk).update(field_definitions=[
            {"key": "heating", "label": "Heating", "type": "choice", "choices": ["central", "own boiler"]}])
        self.manual_post(self.rent, {"heating": "gas"})  # a tampered option
        self.assertFalse(Item.objects.filter(name="Studio").exists())

    def test_only_the_chosen_categorys_values_are_saved(self):
        """Acceptance criterion 6: typed into Rent, then switched to Product."""
        data = {f"cf{self.rent.pk}-area": "32", f"cf{self.product.pk}-brand": "CeraVe"}
        self.manual_post(self.product, None, **data)
        self.assertEqual(Item.objects.get(name="Studio").custom_values, {"brand": "CeraVe"})

    def test_an_error_in_another_categorys_block_is_ignored(self):
        self.manual_post(self.product, None, **{f"cf{self.rent.pk}-area": "abc"})
        self.assertTrue(Item.objects.filter(name="Studio").exists())

    def test_editing_keeps_other_and_removed_values(self):
        """Acceptance criteria 6 and 7."""
        item = Item.objects.create(owner=self.user, category=self.rent, name="Flat", period="monthly",
                                   custom_values={"area": "32", "old_field": "kept", "brand": "Old brand"})
        response = self.client.post(reverse("item-update", args=[item.pk]), {
            "name": "Flat", "category": self.rent.pk, "period": "monthly", "description": "", "url": "",
            f"cf{self.rent.pk}-area": "34", f"cf{self.rent.pk}-rooms": ""})
        self.assertRedirects(response, reverse("item-detail", args=[item.pk]))
        item.refresh_from_db()
        self.assertEqual(item.custom_values, {"area": "34", "old_field": "kept", "brand": "Old brand"})
        self.assertNotContains(self.client.get(reverse("item-detail", args=[item.pk])), "kept")

    def test_edit_form_shows_stored_values(self):
        item = Item.objects.create(owner=self.user, category=self.rent, name="Flat",
                                   custom_values={"area": "32", "location": {"lat": 44.4, "lon": 26.0, "address": "Militari"}})
        page = self.client.get(reverse("item-update", args=[item.pk]))
        self.assertContains(page, f'name="cf{self.rent.pk}-area" value="32"')
        self.assertContains(page, f'name="cf{self.rent.pk}-location__address" value="Militari"')
        self.assertContains(page, "location-picker.js")

    def test_add_by_link_saves_custom_values(self):
        self.client.post(reverse("item-add-link"), {"step": "preview", "url": STORIA_URL})
        response = self.client.post(reverse("item-add-link"), {
            "step": "save", "name": "Studio near metro", "category": self.rent.pk, "period": "monthly",
            "description": "", f"cf{self.rent.pk}-rooms": "1"})
        item = Item.objects.get(name="Studio near metro")
        self.assertRedirects(response, reverse("item-detail", args=[item.pk]), fetch_redirect_response=False)
        self.assertEqual(item.custom_values, {"rooms": "1"})

    def test_items_without_values_are_unchanged(self):
        """Acceptance criterion 13."""
        item = Item.objects.create(owner=self.user, category=self.rent, name="Old flat")
        page = self.client.get(reverse("item-detail", args=[item.pk]))
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, "item-map")
        self.assertNotContains(page, "leaflet.js")

    def test_comparison_columns_and_numbered_map(self):
        """Acceptance criterion 11."""
        located = Item.objects.create(owner=self.user, category=self.rent, name="A flat", custom_values={
            "area": "38", "location": {"lat": 44.44, "lon": 26.05, "address": "Militari"}})
        plain = Item.objects.create(owner=self.user, category=self.rent, name="B flat", custom_values={"rooms": "2"})
        group = ComparisonGroup.objects.create(owner=self.user, name="Flats")
        group.items.set([located, plain])
        response = self.client.get(reverse("comparison-detail", args=[group.pk]))
        self.assertContains(response, '<th>Area <small class="text-lowercase">(m²)</small></th>')
        self.assertContains(response, "<th>Location</th>")
        self.assertContains(response, '<td class="field-cell">38 m²</td>')
        self.assertContains(response, '<span class="pin-badge" aria-label="Pin 1 on the map">1</span>Militari')
        points = response.context["map_data"]["points"]
        self.assertEqual([(p["number"], p["name"]) for p in points], [(1, "A flat")])
        self.assertContains(response, "location-map.js")

    def test_mixed_category_group_has_no_columns_or_map(self):
        """Acceptance criterion 11."""
        flat = Item.objects.create(owner=self.user, category=self.rent, name="Flat",
                                   custom_values={"location": {"lat": 44.4, "lon": 26.0, "address": "X"}})
        gel = Item.objects.create(owner=self.user, category=self.product, name="Gel")
        group = ComparisonGroup.objects.create(owner=self.user, name="Mixed")
        group.items.set([flat, gel])
        response = self.client.get(reverse("comparison-detail", args=[group.pk]))
        self.assertEqual((response.context["field_definitions"], response.context["map_data"]["points"]), ([], []))
        self.assertNotContains(response, "<th>Location</th>")
        self.assertNotContains(response, "comparison-map")


class CustomFieldReviewFixTests(ViewTestCase):
    """Milestone 3b review: values of another shape, and an unusual category number."""

    def test_field_re_added_with_another_type_does_not_crash(self):
        old_location = {"lat": 44.4, "lon": 26.0, "address": "Militari"}
        item = Item.objects.create(owner=self.user, category=self.rent, name="Flat",
                                   custom_values={"location": old_location, "area": "32"})
        Category.objects.filter(pk=self.rent.pk).update(field_definitions=[
            {"key": "area", "label": "Area", "type": "number", "unit": "m²"},
            {"key": "location", "label": "Location", "type": "yes_no"}])
        page = self.client.get(reverse("item-detail", args=[item.pk]))
        self.assertContains(page, "<dt>Area</dt><dd>32 m²</dd>")
        self.assertNotContains(page, "Militari")
        self.assertEqual(self.client.get(reverse("item-update", args=[item.pk])).status_code, 200)
        group = ComparisonGroup.objects.create(owner=self.user, name="Flats")
        group.items.set([item])
        comparison = self.client.get(reverse("comparison-detail", args=[group.pk]))
        self.assertNotContains(comparison, "Militari")  # the old location never leaks as raw data
        # Saving the form (the Yes/No left at "—") keeps the old location stored.
        self.client.post(reverse("item-update", args=[item.pk]), {
            "name": "Flat", "category": self.rent.pk, "period": "monthly", "description": "", "url": "",
            f"cf{self.rent.pk}-area": "32", f"cf{self.rent.pk}-location": "unknown"})
        item.refresh_from_db()
        self.assertEqual(item.custom_values, {"location": old_location, "area": "32"})

    def test_category_number_with_a_leading_zero_saves_its_values(self):
        """Review info 1: "04" is category 4 for the form, so block 4 is used too."""
        Item.objects.create(owner=self.user, category=self.rent, name="Flat")
        item = Item.objects.get(name="Flat")
        response = self.client.post(reverse("item-update", args=[item.pk]), {
            "name": "Flat", "category": f"0{self.rent.pk}", "period": "monthly", "description": "", "url": "",
            f"cf{self.rent.pk}-area": "40"})
        self.assertRedirects(response, reverse("item-detail", args=[item.pk]))
        item.refresh_from_db()
        self.assertEqual(item.custom_values, {"area": "40"})


class AutofillViewTests(ViewTestCase):
    """Milestone 3c: pre-fill in Add by link, and "Fill from website"."""

    LOCATION = {"lat": 44.43, "lon": 26.05, "address": "Strada Exemplului, Militari, Sectorul 6, Bucuresti"}

    def studio(self, **values):
        return self.automatic_item(name="Studio", url=STORIA_URL, category=self.rent, period="monthly",
                                   custom_values=values)

    def test_add_by_link_prefills_the_details(self):
        """Acceptance criterion 3."""
        page = self.client.post(reverse("item-add-link"), {"step": "preview", "url": STORIA_URL})
        prefix = f"cf{self.rent.pk}"
        self.assertContains(page, f'name="{prefix}-area" value="38"')
        self.assertContains(page, f'name="{prefix}-rooms" value="1"')
        self.assertContains(page, f'name="{prefix}-floor" value="Ground floor"')
        self.assertContains(page, f'name="{prefix}-heating" value="Gas"')
        self.assertContains(page, f'name="{prefix}-location__lat" value="44.43"')
        # Saving sends the (possibly edited) pre-filled values like any other form.
        self.client.post(reverse("item-add-link"), {
            "step": "save", "name": "Studio", "category": self.rent.pk, "period": "monthly", "description": "",
            f"{prefix}-area": "38", f"{prefix}-rooms": "1", f"{prefix}-floor": "Ground floor",
            f"{prefix}-location__lat": "44.43", f"{prefix}-location__lon": "26.05",
            f"{prefix}-location__address": self.LOCATION["address"]})
        item = Item.objects.get(name="Studio")
        self.assertEqual(item.custom_values["area"], "38")
        self.assertEqual(item.custom_values["location"], self.LOCATION)

    def test_emag_specifications_prefill_a_matching_label(self):
        """Acceptance criterion 4."""
        Category.objects.filter(pk=self.product.pk).update(field_definitions=[
            {"key": "brand", "label": "Brand", "type": "text"},
            {"key": "tip_produs", "label": "Tip produs", "type": "text"}])
        page = self.client.post(reverse("item-add-link"), {"step": "preview", "url": EMAG_URL})
        self.assertContains(page, f'name="cf{self.product.pk}-tip_produs" value="Gel de curatare"')
        self.assertContains(page, f'name="cf{self.product.pk}-brand" value="ExampleBrand"')

    def test_fill_records_a_price_and_shows_a_preview(self):
        """Acceptance criteria 5 and 6."""
        item = self.studio(area="40")
        response = self.client.post(reverse("item-fill", args=[item.pk]))
        self.assertRedirects(response, reverse("item-fill", args=[item.pk]))
        self.assertEqual(item.price_points.count(), 1)  # recorded like Check now
        self.assertEqual(item.check_attempts.count(), 1)
        page = self.client.get(reverse("item-fill", args=[item.pk]))
        self.assertContains(page, "Price checked:")
        self.assertContains(page, "kept, you already have a value")  # Area 40 is yours
        self.assertNotContains(page, 'name="fields" value="area"')
        self.assertContains(page, 'name="fields" value="rooms"')
        self.assertContains(page, "Strada Exemplului")
        # Within 10 minutes, a second press is refused like Check now.
        response = self.client.post(reverse("item-fill", args=[item.pk]), follow=True)
        self.assertContains(response, "Checked recently.")
        self.assertEqual(self.internet.requested.count(STORIA_URL), 1)  # the page was read once (plus robots.txt)

    def test_confirm_fills_only_ticked_empty_fields(self):
        """Acceptance criteria 5 and 7."""
        item = self.studio(area="40")
        self.client.post(reverse("item-fill", args=[item.pk]))
        response = self.client.post(reverse("item-fill-confirm", args=[item.pk]), {
            "fields": ["area", "rooms", "location"],  # area is yours: never replaced
            "rooms": "99", "location__lat": "0"})       # values from the browser are ignored
        self.assertRedirects(response, reverse("item-detail", args=[item.pk]), fetch_redirect_response=False)
        item.refresh_from_db()
        self.assertEqual(item.custom_values, {"area": "40", "rooms": "1", "location": self.LOCATION})
        self.assertContains(self.client.get(reverse("item-detail", args=[item.pk])),
                            "Filled Rooms and Location from Storia.")
        # The preview is used once.
        response = self.client.post(reverse("item-fill-confirm", args=[item.pk]), {"fields": ["floor"]}, follow=True)
        self.assertContains(response, "to read the page first")
        item.refresh_from_db()
        self.assertNotIn("floor", item.custom_values)

    def test_fill_never_replaces_a_hidden_older_value(self):
        """Review of M3, low 3: a value of another type (field re-added) is kept, and the preview says so."""
        old = {"lat": 1.0, "lon": 2.0, "address": "Old place"}
        Category.objects.filter(pk=self.rent.pk).update(field_definitions=[
            {"key": "area", "label": "Area", "type": "text"},  # was a number, now text...
            {"key": "rooms", "label": "Rooms", "type": "number"}])
        item = self.studio(area=old)  # ...holding an old location-shaped value
        self.client.post(reverse("item-fill", args=[item.pk]))
        page = self.client.get(reverse("item-fill", args=[item.pk]))
        self.assertContains(page, "kept: an older value of another type is stored")
        self.assertNotContains(page, 'name="fields" value="area"')
        self.client.post(reverse("item-fill-confirm", args=[item.pk]), {"fields": ["area", "rooms"]})
        item.refresh_from_db()
        self.assertEqual(item.custom_values, {"area": old, "rooms": "1"})

    def test_nothing_matched(self):
        Category.objects.filter(pk=self.rent.pk).update(field_definitions=[{"key": "notes", "label": "Notes", "type": "text"}])
        item = self.studio()
        self.client.post(reverse("item-fill", args=[item.pk]))
        page = self.client.get(reverse("item-fill", args=[item.pk]))
        self.assertContains(page, "The page didn’t have any details for this category’s fields.")
        self.assertContains(page, "Area: 38")  # listed under "Not used"
        self.assertEqual(item.price_points.count(), 1)

    def test_failed_read_shows_no_preview(self):
        self.internet.pages[STORIA_URL] = (503, "<html><title>Storia</title></html>")
        item = self.studio()
        response = self.client.post(reverse("item-fill", args=[item.pk]), follow=True)
        self.assertContains(response, "Couldn&#x27;t read the page:")
        self.assertRedirects(response, reverse("item-detail", args=[item.pk]))

    def test_other_users_manual_items_and_get_requests(self):
        """Acceptance criterion 10."""
        item = self.studio()
        manual = Item.objects.create(owner=self.user, category=self.rent, name="Manual flat")
        self.assertNotContains(self.client.get(reverse("item-detail", args=[manual.pk])), "Fill from website")
        self.assertContains(self.client.get(reverse("item-detail", args=[item.pk])), "Fill from website")
        # Opening the preview address without reading first just goes back to the item.
        self.assertRedirects(self.client.get(reverse("item-fill", args=[item.pk])), reverse("item-detail", args=[item.pk]))
        self.assertEqual(self.client.get(reverse("item-fill-confirm", args=[item.pk])).status_code, 405)
        self.client.force_login(self.other)
        for name in ("item-fill", "item-fill-confirm"):
            self.assertEqual(self.client.post(reverse(name, args=[item.pk])).status_code, 404)
        self.assertEqual(self.internet.requested, [])

    def test_a_preview_for_another_item_cant_be_used(self):
        first, second = self.studio(), self.automatic_item(name="Other", url=STORIA_URL.replace("TEST", "OTHER"),
                                                           category=self.rent)
        self.internet.pages[second.url] = self.internet.pages[STORIA_URL]
        self.client.post(reverse("item-fill", args=[first.pk]))
        self.client.post(reverse("item-fill-confirm", args=[second.pk]), {"fields": ["rooms"]})
        second.refresh_from_db()
        self.assertEqual(second.custom_values, {})


class AccountPageTests(ViewTestCase):
    """Whole-application review: no "reset by email" (the app can't send email)."""

    def test_email_reset_pages_are_gone(self):
        self.client.logout()
        for url in ("/accounts/password_reset/", "/accounts/password_reset/done/",
                    "/accounts/reset/MQ/set-password/", "/accounts/reset/done/"):
            self.assertEqual(self.client.get(url).status_code, 404, url)
        self.assertEqual(self.client.post("/accounts/password_reset/", {"email": "a@example.invalid"}).status_code, 404)

    def test_login_page_says_to_ask_the_admin(self):
        self.client.logout()
        page = self.client.get(reverse("login"))
        self.assertContains(page, "Forgot your password? Ask the person who set up Price Tracker to reset it.")

    def test_sign_in_change_password_and_sign_out_still_work(self):
        self.client.logout()
        response = self.client.post(reverse("login"), {"username": "ana", "password": "test-pass-123"})
        self.assertRedirects(response, reverse("dashboard"))
        self.assertEqual(self.client.get(reverse("password_change")).status_code, 200)
        response = self.client.post(reverse("password_change"), {
            "old_password": "test-pass-123", "new_password1": "a-longer-new-pass-456", "new_password2": "a-longer-new-pass-456"})
        self.assertRedirects(response, reverse("password_change_done"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("a-longer-new-pass-456"))
        self.assertRedirects(self.client.post(reverse("logout")), reverse("login"))
