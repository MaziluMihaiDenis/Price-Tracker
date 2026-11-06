from datetime import date, datetime, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from tracker.indicators import attach_summaries, summarize
from tracker.models import Category, Item, PricePoint
from tracker.money import RateBook

# Real BNR rates (RON per 1 EUR).
BOOK = RateBook([
    (date(2026, 10, 30), "EUR", Decimal("5.3426")),
    (date(2026, 11, 5), "EUR", Decimal("5.3398")),
])
EMPTY_BOOK = RateBook()
START = timezone.make_aware(datetime(2026, 11, 1, 12))


def history(*prices):
    """Unsaved price points, one per day from 1 Nov 2026. A price is a number (RON) or (amount, currency)."""
    points = []
    for day, price in enumerate(prices):
        amount, currency = price if isinstance(price, tuple) else (price, "RON")
        points.append(PricePoint(amount=Decimal(str(amount)), currency=currency,
                                 recorded_at=START + timedelta(days=day)))
    return points


class ChangeTests(SimpleTestCase):
    def test_drop_against_the_previous_price(self):
        """Acceptance criterion 1."""
        points = history("129.99", "119.99")
        change = summarize(points, BOOK).change
        self.assertEqual((change.direction, change.percent), ("down", Decimal("7.7")))
        self.assertIs(change.previous, points[0])
        self.assertEqual(change.since, points[1].recorded_at)

    def test_repeats_before_the_change_do_not_matter(self):
        """Acceptance criterion 2."""
        change = summarize(history(100, 100, 100, 110), BOOK).change
        self.assertEqual((change.direction, change.percent), ("up", Decimal("10.0")))

    def test_since_is_when_the_current_price_first_appeared(self):
        points = history("129.99", "119.99", "119.99", "119.99")
        change = summarize(points, BOOK).change
        self.assertEqual(change.since, points[1].recorded_at)
        self.assertIs(change.previous, points[0])

    def test_compares_with_the_previous_different_price_not_the_first(self):
        points = history(100, 120, 120, 90)
        change = summarize(points, BOOK).change
        self.assertIs(change.previous, points[2])
        self.assertEqual((change.direction, change.percent), ("down", Decimal("25.0")))

    def test_one_price_or_no_change_has_no_indicator(self):
        """Acceptance criterion 3."""
        for points in (history(100), history(100, 100, 100), []):
            summary = summarize(points, BOOK)
            self.assertIsNone(summary.change)
            self.assertFalse(summary.is_lowest_ever)

    def test_unchanged_eur_rent_has_no_arrow_although_the_rate_moved(self):
        """Acceptance criterion 4: compared in its own currency, not the viewer's."""
        points = history((470, "EUR"), (470, "EUR"))
        points[0].recorded_at = timezone.make_aware(datetime(2026, 10, 30, 12))  # rate 5.3426
        points[1].recorded_at = timezone.make_aware(datetime(2026, 11, 5, 12))  # rate 5.3398
        summary = summarize(points, BOOK)
        self.assertIsNone(summary.change)
        self.assertFalse(summary.is_lowest_ever)

    def test_mixed_currencies_are_compared_in_ron_at_each_days_rate(self):
        """Acceptance criterion 5: 500 RON -> 100 EUR (533.98 RON on 5 Nov) = up 6.8%."""
        points = history(500, (100, "EUR"))
        points[1].recorded_at = timezone.make_aware(datetime(2026, 11, 5, 12))
        change = summarize(points, BOOK).change
        self.assertEqual((change.direction, change.percent), ("up", Decimal("6.8")))

    def test_mixed_currencies_without_a_rate_have_no_arrow(self):
        """Acceptance criterion 5 (missing rate)."""
        summary = summarize(history(500, (100, "EUR")), EMPTY_BOOK)
        self.assertIsNone(summary.change)
        self.assertFalse(summary.is_lowest_ever)

    def test_small_changes_keep_one_decimal(self):
        change = summarize(history("250.00", "249.00"), BOOK).change
        self.assertEqual(change.percent, Decimal("0.4"))


class LowestEverTests(SimpleTestCase):
    def test_back_at_the_lowest_price(self):
        """Acceptance criterion 6."""
        points = history(120, 110, 115, 110)
        summary = summarize(points, BOOK)
        self.assertTrue(summary.is_lowest_ever)
        self.assertIs(summary.lowest, points[1])  # the first time 110 appeared
        self.assertIs(summary.highest, points[0])

    def test_not_at_the_lowest_price(self):
        """Acceptance criterion 6."""
        points = history(120, 110, 115)
        summary = summarize(points, BOOK)
        self.assertFalse(summary.is_lowest_ever)
        self.assertIs(summary.lowest, points[1])

    def test_highest_tie_keeps_the_first_date(self):
        points = history(130, 100, 130)
        self.assertIs(summarize(points, BOOK).highest, points[0])

    def test_mixed_currencies_use_ron_values(self):
        points = history(500, (100, "EUR"))  # 100 EUR on 2 Nov = 534.26 RON (30 Oct rate)
        summary = summarize(points, BOOK)
        self.assertIs(summary.lowest, points[0])
        self.assertIs(summary.highest, points[1])


class AttachSummariesTests(TestCase):
    def test_one_query_for_any_number_of_items(self):
        user = get_user_model().objects.create_user("ana", password="test-pass-123")
        category = Category.objects.get(name="Product")
        items = []
        for number in range(10):
            item = Item.objects.create(owner=user, category=category, name=f"Item {number}")
            for point in history(100, 90):
                point.item = item
                point.save()
            items.append(item)
        with self.assertNumQueries(1):
            attach_summaries(items, BOOK)
        self.assertTrue(all(item.price_summary.change.direction == "down" for item in items))

    def test_no_items_no_query(self):
        with self.assertNumQueries(0):
            self.assertEqual(attach_summaries([], BOOK), [])
