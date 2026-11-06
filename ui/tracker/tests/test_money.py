from datetime import date, datetime
from decimal import Decimal

from django.test import SimpleTestCase
from django.utils import timezone

from tracker.money import RateBook, display_price

# Real BNR rates (RON per 1 EUR).
BOOK = RateBook([
    (date(2025, 12, 31), "EUR", Decimal("5.0985")),
    (date(2026, 11, 5), "EUR", Decimal("5.3398")),  # Thursday
    (date(2026, 11, 6), "EUR", Decimal("5.3412")),  # Friday (illustrative value)
])


def at(year, month, day, hour=12):
    return timezone.make_aware(datetime(year, month, day, hour))


class ConversionTests(SimpleTestCase):
    def test_acceptance_example_eur_to_ron(self):
        """Acceptance criterion 1: 100 EUR on 2026-11-05 at 5.3398 -> 533.98 RON."""
        shown = display_price(Decimal("100"), "EUR", at(2026, 11, 5), "RON", BOOK)
        self.assertEqual((shown.amount, shown.currency), (Decimal("533.98"), "RON"))
        self.assertEqual((shown.original_amount, shown.original_currency), (Decimal("100"), "EUR"))
        self.assertTrue(shown.converted)

    def test_ron_to_eur(self):
        """Acceptance criterion 4 (the conversion part)."""
        shown = display_price(Decimal("119.99"), "RON", at(2026, 11, 5), "EUR", BOOK)
        self.assertEqual((shown.amount, shown.currency), (Decimal("22.47"), "EUR"))  # 119.99 / 5.3398

    def test_weekend_uses_fridays_rate(self):
        """Acceptance criterion 2."""
        self.assertEqual(BOOK.ron_per_unit("EUR", date(2026, 11, 7)), Decimal("5.3412"))
        self.assertEqual(BOOK.ron_per_unit("EUR", date(2026, 11, 8)), Decimal("5.3412"))

    def test_new_year_uses_last_years_rate(self):
        """Acceptance criterion 3: 1 January -> 31 December's rate."""
        self.assertEqual(BOOK.ron_per_unit("EUR", date(2026, 1, 1)), Decimal("5.0985"))

    def test_no_rate_before_history(self):
        """Acceptance criterion 5."""
        shown = display_price(Decimal("400"), "EUR", at(2020, 6, 1), "RON", BOOK)
        self.assertTrue(shown.missing_rate)
        self.assertFalse(shown.converted)
        self.assertEqual((shown.amount, shown.currency), (Decimal("400"), "EUR"))

    def test_same_currency_is_not_converted(self):
        shown = display_price(Decimal("89.49"), "RON", at(2020, 1, 1), "RON", BOOK)
        self.assertEqual((shown.amount, shown.converted, shown.missing_rate), (Decimal("89.49"), False, False))

    def test_empty_rate_book(self):
        shown = display_price(Decimal("400"), "EUR", at(2026, 11, 5), "RON", RateBook())
        self.assertTrue(shown.missing_rate)

    def test_ron_is_always_one(self):
        self.assertEqual(RateBook().ron_per_unit("RON", date(1999, 1, 1)), Decimal(1))

    def test_rate_is_chosen_by_local_date(self):
        # 23:30 UTC on 4 Nov is already 01:30 on 5 Nov in Bucharest, so 5 Nov's rate applies.
        late_utc = datetime(2026, 11, 4, 23, 30, tzinfo=timezone.get_fixed_timezone(0))
        shown = display_price(Decimal("100"), "EUR", late_utc, "RON", BOOK)
        self.assertEqual(shown.amount, Decimal("533.98"))

    def test_display_is_rounded_but_original_is_kept(self):
        shown = display_price(Decimal("470"), "EUR", at(2026, 11, 5), "RON", BOOK)
        self.assertEqual(shown.amount, Decimal("2509.71"))  # 470 x 5.3398 = 2509.706
        self.assertEqual(shown.original_amount, Decimal("470"))
