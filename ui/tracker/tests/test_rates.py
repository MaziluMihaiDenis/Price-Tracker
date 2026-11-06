from datetime import date, datetime
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from tracker import rates
from tracker.models import Category, ExchangeRate, Item, PricePoint
from tracker.tests.helpers import FakeBnr, fixture


class ParseRatesTests(SimpleTestCase):
    def test_reads_http_namespace_file(self):
        parsed = rates.parse_rates(fixture("bnr_year_http.xml"))
        self.assertEqual(parsed, [(date(2025, 12, 30), "EUR", Decimal("5.0963")),
                                  (date(2025, 12, 31), "EUR", Decimal("5.0985"))])

    def test_reads_https_namespace_file(self):
        self.assertEqual(rates.parse_rates(fixture("bnr_daily_https.xml")),
                         [(date(2026, 11, 5), "EUR", Decimal("5.3398"))])

    def test_applies_multiplier(self):
        parsed = rates.parse_rates(fixture("bnr_year_http.xml"), currencies=("HUF",))
        self.assertEqual(parsed[0], (date(2025, 12, 30), "HUF", Decimal("0.013195")))

    def test_only_requested_currencies(self):
        codes = {code for _, code, _ in rates.parse_rates(fixture("bnr_daily_https.xml"))}
        self.assertEqual(codes, {"EUR"})

    def test_broken_file_raises_clear_error(self):
        with self.assertRaises(rates.RatesUnavailable):
            rates.parse_rates("<html>Maintenance</html")


class ImportRatesTests(TestCase):
    def setUp(self):
        today = timezone.localdate()
        self.bnr = FakeBnr({rates.DAILY_URL: fixture("bnr_daily_https.xml")})
        for year in range(2024, today.year + 1):
            self.bnr.files[rates.YEAR_URL.format(year=year)] = fixture("bnr_year_http.xml")
        patcher = mock.patch.object(rates, "fetch", self.bnr)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_history_starts_the_year_before_2025(self):
        rates.import_rates()
        self.assertEqual(self.bnr.requested[0], rates.YEAR_URL.format(year=2024))
        self.assertEqual(self.bnr.requested[-1], rates.DAILY_URL)
        self.assertEqual(ExchangeRate.objects.get(date=date(2026, 11, 5)).ron_per_unit, Decimal("5.3398"))

    def test_older_prices_extend_the_history(self):
        user = get_user_model().objects.create_user("ana", password="test-pass-123")
        item = Item.objects.create(owner=user, category=Category.objects.get(name="Rent"), name="Rent")
        PricePoint.objects.create(item=item, amount=Decimal("400"), currency="EUR",
                                  recorded_at=timezone.make_aware(datetime(2023, 6, 1, 12, 0)))
        self.bnr.files[rates.YEAR_URL.format(year=2022)] = fixture("bnr_year_http.xml")
        self.bnr.files[rates.YEAR_URL.format(year=2023)] = fixture("bnr_year_http.xml")
        rates.import_rates()
        self.assertEqual(self.bnr.requested[0], rates.YEAR_URL.format(year=2022))

    def test_importing_twice_never_duplicates(self):
        """Acceptance criterion 7."""
        rates.import_rates()
        count = ExchangeRate.objects.count()
        rates.import_rates()
        self.assertEqual(ExchangeRate.objects.count(), count)
        self.assertEqual(count, 3)  # 30 Dec, 31 Dec, 5 Nov; RON itself is never stored

    def test_revised_rate_is_updated(self):
        rates.import_latest_rates()
        self.bnr.files[rates.DAILY_URL] = fixture("bnr_daily_https.xml").replace("5.3398", "5.3401")
        rates.import_latest_rates()
        self.assertEqual(ExchangeRate.objects.get(date=date(2026, 11, 5)).ron_per_unit, Decimal("5.3401"))

    def test_bnr_down_raises(self):
        self.bnr.down = True
        with self.assertRaises(rates.RatesUnavailable):
            rates.import_latest_rates()
        self.assertFalse(ExchangeRate.objects.exists())


class FetchTests(SimpleTestCase):
    def test_http_error_becomes_rates_unavailable(self):
        with mock.patch("httpx.get", return_value=mock.Mock(status_code=503, text="")):
            with self.assertRaisesMessage(rates.RatesUnavailable, "HTTP 503"):
                rates.fetch(rates.DAILY_URL)
