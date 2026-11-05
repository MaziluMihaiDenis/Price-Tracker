from decimal import Decimal

from django.test import SimpleTestCase

from tracker.adapters import adapter_for, clean_url
from tracker.adapters.emag import EmagAdapter
from tracker.adapters.storia import StoriaAdapter
from tracker.tests.helpers import fixture


class AdapterLookupTests(SimpleTestCase):
    def test_supported_sites_are_found(self):
        self.assertIsInstance(adapter_for("https://www.emag.ro/x/pd/ABC/"), EmagAdapter)
        self.assertIsInstance(adapter_for("https://emag.ro/x/pd/ABC/"), EmagAdapter)
        self.assertIsInstance(adapter_for("https://www.storia.ro/ro/oferta/x-ID1"), StoriaAdapter)

    def test_unsupported_sites_are_rejected(self):
        for url in (
            "https://www.olx.ro/d/oferta/x.html",
            "https://altex.ro/x/cpd/1/",
            "https://emag.ro.evil.example/x",   # look-alike domain
            "https://notemag.ro/x",             # different site ending in emag.ro
            "ftp://www.emag.ro/x",              # not a web link
            "http://localhost/admin",
        ):
            self.assertIsNone(adapter_for(url), url)

    def test_clean_url_drops_tracking_parts(self):
        self.assertEqual(
            clean_url("https://WWW.emag.ro/gel/pd/DYQ/?ref=fam#1000-ml"),
            "https://www.emag.ro/gel/pd/DYQ/",
        )
        self.assertEqual(
            clean_url("https://www.storia.ro/ro/oferta/x-IDISlZ?session_olx=abc&session_long_olx=def"),
            "https://www.storia.ro/ro/oferta/x-IDISlZ",
        )


class ExtractionTests(SimpleTestCase):
    def test_emag_product_page(self):
        result = EmagAdapter().extract(fixture("emag_product.html"))
        self.assertEqual(result.price, Decimal("119.99"))
        self.assertEqual(result.currency, "RON")
        self.assertEqual(result.title, "Gel de spalare hidratant, 976 ml")
        self.assertTrue(result.available)

    def test_storia_listing_page(self):
        result = StoriaAdapter().extract(fixture("storia_listing.html"))
        self.assertEqual(result.price, Decimal("399"))
        self.assertEqual(result.currency, "EUR")
        self.assertEqual(result.title, "Garsoniera de inchiriat, 3 min metrou")

    def test_meta_tags_are_the_fallback(self):
        html = """<meta property="og:title" content="Laptop">
        <meta property="product:price:amount" content="2499.99">
        <meta property="product:price:currency" content="RON">"""
        result = EmagAdapter().extract(html)
        self.assertEqual((result.price, result.currency, result.title), (Decimal("2499.99"), "RON", "Laptop"))

    def test_out_of_stock_is_reported(self):
        html = fixture("emag_product.html").replace("InStock", "OutOfStock")
        self.assertFalse(EmagAdapter().extract(html).available)

    def test_page_without_price_gives_nothing(self):
        self.assertIsNone(EmagAdapter().extract("<html><title>Pagina</title></html>"))

    def test_broken_json_is_skipped(self):
        self.assertIsNone(StoriaAdapter().extract('<script type="application/ld+json">{oops</script>'))

    def test_zero_or_text_price_is_rejected(self):
        for price in ('"0"', '"la cerere"'):
            html = f'<script type="application/ld+json">{{"name": "x", "offers": {{"price": {price}}}}}</script>'
            self.assertIsNone(StoriaAdapter().extract(html), price)
