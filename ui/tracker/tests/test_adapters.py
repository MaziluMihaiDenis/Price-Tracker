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


class DetailTests(SimpleTestCase):
    """Milestone 3c: the extra details read for custom fields."""

    def test_storia_details(self):
        """Acceptance criterion 1."""
        details = StoriaAdapter().extract(fixture("storia_listing.html")).details
        self.assertEqual(details, {
            "area": "38", "rooms": "1", "year_built": "2017", "floor": "Ground floor", "heating": "Gas",
            "location": {"lat": 44.43, "lon": 26.05,
                         "address": "Strada Exemplului, Militari, Sectorul 6, Bucuresti"}})

    def test_emag_details(self):
        """Acceptance criterion 2 (the test page uses a made-up brand)."""
        details = EmagAdapter().extract(fixture("emag_product.html")).details
        self.assertEqual(details["brand"], "ExampleBrand")
        self.assertEqual(details["specs"], {"Tip produs": "Gel de curatare", "Tipul de ten": "Uscat, Normal",
                                            "Set": "Nu", "Cantitate": "1000 ml"})

    def test_storia_codes_read_as_words(self):
        from tracker.adapters.storia import FLOORS, HEATING, readable
        self.assertEqual(readable("floor_3", FLOORS), "Floor 3")
        self.assertEqual(readable("urban", HEATING), "District heating")
        self.assertEqual(readable("own_boiler", HEATING), "Own boiler")

    def test_missing_or_broken_details_keep_the_price(self):
        """Acceptance criterion 9."""
        page = fixture("storia_listing.html")
        start = page.index('<script id="__NEXT_DATA__"')
        without = page[:start] + page[page.index("</script>", start) + len("</script>"):]
        broken = page.replace('"coordinates": {"latitude": 44.43', '"coordinates": {"latitude": "north"')
        garbage = page.replace('{"props"', '{"props" oops', 1)
        result = StoriaAdapter().extract(without)
        self.assertEqual((result.price, result.details), (Decimal("399"), {}))
        with self.assertLogs("tracker.adapters", level="WARNING"):  # logged, not raised
            result = StoriaAdapter().extract(garbage)
        self.assertEqual((result.price, result.details), (Decimal("399"), {}))
        result = StoriaAdapter().extract(broken)
        self.assertEqual(result.price, Decimal("399"))
        self.assertNotIn("location", result.details)  # only the broken detail is skipped
        self.assertEqual(result.details["area"], "38")

    def test_emag_page_without_specs(self):
        page = fixture("emag_product.html")
        html = page[:page.index('<div class="specifications-body">')] + "</body></html>"
        self.assertEqual(EmagAdapter().extract(html).details, {"brand": "ExampleBrand"})
