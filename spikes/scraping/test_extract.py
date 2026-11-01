"""Tests for extract.py. Run with:  .venv/Scripts/python -m unittest test_extract"""

import unittest
from decimal import Decimal

from extract import extract, parse_price


class ParsePriceTests(unittest.TestCase):
    # The seven cases from the spike plan.
    def test_romanian_thousands_and_decimals(self):
        self.assertEqual(parse_price("2.499,99 lei"), (Decimal("2499.99"), "RON"))

    def test_euro_with_thousands_dot(self):
        self.assertEqual(parse_price("85.000 €"), (Decimal("85000"), "EUR"))

    def test_space_as_thousands_separator(self):
        self.assertEqual(parse_price("1 250 RON"), (Decimal("1250"), "RON"))

    def test_monthly_rent_with_symbol_first(self):
        self.assertEqual(parse_price("€ 450 / lună"), (Decimal("450"), "EUR"))

    def test_price_on_request_has_no_price(self):
        self.assertIsNone(parse_price("Preț la cerere"))

    def test_zero_is_rejected(self):
        self.assertIsNone(parse_price("0 lei"))

    def test_text_without_numbers_is_rejected(self):
        self.assertIsNone(parse_price("abc"))

    # Extra cases found while writing the parser.
    def test_non_breaking_space(self):
        self.assertEqual(parse_price("3 199,00 Lei"), (Decimal("3199.00"), "RON"))

    def test_unknown_currency_is_unclear(self):
        self.assertEqual(parse_price("99 $"), (Decimal("99"), None))

    def test_small_decimal_with_dot(self):
        self.assertEqual(parse_price("12.5 lei"), (Decimal("12.5"), "RON"))


class ExtractTests(unittest.TestCase):
    def test_structured_data_wins(self):
        html = """<html><head><title>Page</title>
        <script type="application/ld+json">
        {"@type": "Product", "name": "Televizor X", "offers": {"@type": "Offer",
         "price": "2499.99", "priceCurrency": "RON",
         "availability": "https://schema.org/InStock"}}
        </script></head></html>"""
        result = extract(html, "emag")
        self.assertEqual(result["price"], Decimal("2499.99"))
        self.assertEqual(result["currency"], "RON")
        self.assertEqual(result["title"], "Televizor X")
        self.assertEqual(result["availability"], "InStock")
        self.assertEqual(result["extracted_by"], "structured")

    def test_meta_tags_used_when_no_structured_data(self):
        html = """<html><head>
        <meta property="og:title" content="Apartament 2 camere">
        <meta property="product:price:amount" content="85000">
        <meta property="product:price:currency" content="EUR">
        </head></html>"""
        result = extract(html, "storia")
        self.assertEqual(result["price"], Decimal("85000"))
        self.assertEqual(result["currency"], "EUR")
        self.assertEqual(result["title"], "Apartament 2 camere")
        self.assertEqual(result["extracted_by"], "meta")

    def test_broken_json_is_skipped(self):
        html = '<script type="application/ld+json">{not json</script>'
        self.assertIsNone(extract(html, "olx"))

    def test_no_price_anywhere(self):
        self.assertIsNone(extract("<html><title>Nimic</title></html>", "altex"))


if __name__ == "__main__":
    unittest.main()
