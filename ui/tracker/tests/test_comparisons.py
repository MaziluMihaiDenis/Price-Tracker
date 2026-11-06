from datetime import date, datetime
from decimal import Decimal

from django.test import SimpleTestCase
from django.utils import timezone

from tracker.comparisons import ONE_TIME, RECURRING, chart_data, mixed_periods, table_rows
from tracker.models import Item, PricePoint
from tracker.money import RateBook

# Real BNR rates (RON per 1 EUR).
BOOK = RateBook([
    (date(2026, 10, 30), "EUR", Decimal("5.3426")),
    (date(2026, 11, 5), "EUR", Decimal("5.3398")),
])
NOV_5 = timezone.make_aware(datetime(2026, 11, 5, 12))


def item(name, period, *prices, when=NOV_5):
    """An unsaved item with its price history. A price is a number (RON) or (amount, currency)."""
    result = Item(name=name, period=period)
    result.price_history = []
    for price in prices:
        amount, currency = price if isinstance(price, tuple) else (price, "RON")
        result.price_history.append(PricePoint(amount=Decimal(str(amount)), currency=currency, recorded_at=when))
    return result


MONTHLY, YEARLY, ONCE = Item.Period.MONTHLY, Item.Period.YEARLY, Item.Period.ONE_TIME


class MixedPeriodTests(SimpleTestCase):
    def test_one_period_is_not_mixed(self):
        self.assertEqual(mixed_periods([item("A", MONTHLY), item("B", MONTHLY)]), [])

    def test_mixed_periods_are_listed_in_order(self):
        """Acceptance criterion 3 (the warning)."""
        group = [item("Gym", YEARLY), item("Rent", MONTHLY), item("TV", ONCE)]
        self.assertEqual(mixed_periods(group), ["One-time", "Monthly", "Yearly"])


class TableRowTests(SimpleTestCase):
    def test_per_month_values(self):
        """Acceptance criterion 3: 1200 RON/year -> 100.00 per month."""
        rows = table_rows([item("Gym", YEARLY, 1200), item("Rent", MONTHLY, 2500), item("TV", ONCE, 3000)],
                          "RON", BOOK)
        self.assertEqual([row.per_month for row in rows], [Decimal("100.00"), Decimal("2500.00"), None])
        self.assertEqual([row.kind for row in rows], [RECURRING, RECURRING, ONE_TIME])

    def test_cheapest_and_percent_above_it(self):
        """Acceptance criterion 4."""
        rows = table_rows([item("Flat A", MONTHLY, 2500), item("Flat B", MONTHLY, 2800)], "RON", BOOK)
        self.assertEqual([(row.is_cheapest, row.vs_cheapest) for row in rows],
                         [(True, None), (False, Decimal("12.0"))])

    def test_one_time_and_recurring_are_never_compared(self):
        """Acceptance criterion 5."""
        rows = table_rows([item("TV", ONCE, 3000), item("Rent", MONTHLY, 2500)], "RON", BOOK)
        self.assertEqual([(row.is_cheapest, row.vs_cheapest) for row in rows], [(False, None), (False, None)])

    def test_each_kind_is_compared_separately(self):
        rows = table_rows([item("TV A", ONCE, 3000), item("Rent", MONTHLY, 2500), item("TV B", ONCE, 2400),
                           item("Gym", YEARLY, 1200)], "RON", BOOK)
        by_name = {row.item.name: (row.is_cheapest, row.vs_cheapest) for row in rows}
        self.assertEqual(by_name, {"TV A": (False, Decimal("25.0")), "TV B": (True, None),
                                   "Rent": (False, Decimal("2400.0")), "Gym": (True, None)})

    def test_yearly_is_compared_by_its_per_month_value(self):
        rows = table_rows([item("Yearly plan", YEARLY, 1200), item("Monthly plan", MONTHLY, 110)], "RON", BOOK)
        self.assertEqual([(row.is_cheapest, row.vs_cheapest) for row in rows], [(True, None), (False, Decimal("10.0"))])

    def test_a_tie_gives_both_the_badge(self):
        rows = table_rows([item("A", MONTHLY, 2500), item("B", MONTHLY, 2500)], "RON", BOOK)
        self.assertTrue(all(row.is_cheapest for row in rows))

    def test_mixed_currencies_are_compared_in_the_viewers_currency(self):
        """470 EUR on 5 Nov = 2509.71 RON, so it beats 2600 RON by 3.6%."""
        rows = table_rows([item("Studio EUR", MONTHLY, (470, "EUR")), item("Studio RON", MONTHLY, 2600)],
                          "RON", BOOK)
        self.assertEqual(rows[0].per_month, Decimal("2509.71"))
        self.assertEqual([(row.is_cheapest, row.vs_cheapest) for row in rows], [(True, None), (False, Decimal("3.6"))])

    def test_missing_rate_or_no_price_is_left_out(self):
        rows = table_rows([item("No rate", MONTHLY, (470, "EUR")), item("No price", MONTHLY),
                           item("Rent", MONTHLY, 2500)], "RON", RateBook())
        self.assertEqual([(row.per_month, row.is_cheapest) for row in rows],
                         [(None, False), (None, False), (Decimal("2500.00"), False)])
        self.assertIsNone(rows[1].price)

    def test_uses_the_latest_price(self):
        rows = table_rows([item("Gel", ONCE, 129.99, 119.99)], "RON", BOOK)
        self.assertEqual(rows[0].price.amount, Decimal("119.99"))


class ChartDataTests(SimpleTestCase):
    def test_one_series_per_item_in_the_viewers_currency(self):
        """Acceptance criterion 1."""
        data = chart_data([item("TV RON", ONCE, 2500), item("TV EUR", ONCE, (470, "EUR")), item("Empty", ONCE)],
                          "RON", BOOK)
        self.assertEqual(data["currency"], "RON")
        self.assertEqual([series["name"] for series in data["series"]], ["TV RON", "TV EUR"])  # no line without prices
        self.assertEqual(data["series"][1]["points"][0]["y"], "2509.71")
        self.assertEqual(data["series"][1]["points"][0]["original"], "470.00 EUR")
        self.assertEqual(data["series"][0]["points"][0]["original"], "")

    def test_dates_are_real_timestamps(self):
        """Acceptance criterion 2: 20 Oct and 6 Nov are 17 days apart.

        Plus one hour: Romania moved from summer to winter time on 25 Oct 2026.
        """
        early = item("A", ONCE, 100, when=timezone.make_aware(datetime(2026, 10, 20, 12)))
        late = item("B", ONCE, 100, when=timezone.make_aware(datetime(2026, 11, 6, 12)))
        data = chart_data([early, late], "RON", BOOK)
        gap = data["series"][1]["points"][0]["x"] - data["series"][0]["points"][0]["x"]
        self.assertEqual(gap, (17 * 24 + 1) * 60 * 60 * 1000)

    def test_prices_without_a_rate_are_skipped_and_counted(self):
        data = chart_data([item("EUR", ONCE, (470, "EUR")), item("RON", ONCE, 100)], "RON", RateBook())
        self.assertEqual(data["missing"], 1)
        self.assertEqual([series["name"] for series in data["series"]], ["RON"])
