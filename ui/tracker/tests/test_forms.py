from django.test import SimpleTestCase

from tracker.forms import LinkForm

STORIA = "https://www.storia.ro/ro/oferta/garsoniera-cocheta-IDJ4zY"
EMAG = "https://www.emag.ro/gel-de-spalare/pd/DYQQPCBBM/"


class LinkFormTests(SimpleTestCase):
    def cleaned(self, text):
        form = LinkForm({"url": text})
        self.assertTrue(form.is_valid(), f"{text!r}: {form.errors.get('url')}")
        return form.cleaned_data["url"]

    def error(self, text):
        form = LinkForm({"url": text})
        self.assertFalse(form.is_valid(), text)
        return form.errors["url"][0]

    # Fix 1: accept links the way people paste them.
    def test_plain_link(self):
        self.assertEqual(self.cleaned(STORIA), STORIA)

    def test_link_without_https(self):
        self.assertEqual(self.cleaned("www.storia.ro/ro/oferta/garsoniera-cocheta-IDJ4zY"), STORIA)

    def test_bare_address(self):
        self.assertEqual(self.cleaned("storia.ro/ro/oferta/x-ID1"), "https://storia.ro/ro/oferta/x-ID1")

    def test_storia_app_share_text(self):
        text = f"garsoniera cocheta rond P-ta Kogalniceanu {STORIA}?session_olx=1a193fade58x3eb8294e"
        self.assertEqual(self.cleaned(text), STORIA)

    def test_emag_share_text_with_trailing_punctuation(self):
        self.assertEqual(self.cleaned(f"Uite ce am gasit pe eMAG: Gel de spalare ({EMAG}?ref=share)."), EMAG)

    def test_surrounding_spaces_and_line_breaks(self):
        self.assertEqual(self.cleaned(f"  \n{EMAG}#1000-ml \n"), EMAG)

    # Fix 2: long links are not cut.
    def test_long_link_with_tracking_is_accepted(self):
        long_link = (STORIA + "?session_long_olx=19adc41ec5cx3b1448f&session_olx=1a193fade58x3eb8294e"
                     "&search%5Bfilter_float_price%3Ato%5D=500&utm_source=app_share&utm_medium=" + "x" * 300)
        self.assertGreater(len(long_link), 400)
        self.assertEqual(self.cleaned(long_link), STORIA)

    def test_address_too_long_even_when_cleaned(self):
        too_long = "https://www.emag.ro/" + "produs-" * 30 + "/pd/ABC/"
        self.assertIn("too long to store", self.error(too_long))

    def test_field_has_no_browser_url_check_or_200_limit(self):
        html = str(LinkForm()["url"])
        self.assertIn('type="text"', html)
        self.assertIn('inputmode="url"', html)
        self.assertNotIn('maxlength="200"', html)

    # Still rejected.
    def test_text_without_a_link(self):
        self.assertEqual(self.error("garsoniera in Drumul Taberei"), "Paste a link that starts with https:// or www.")

    def test_unsupported_site(self):
        self.assertIn("isn't supported yet", self.error("https://www.olx.ro/d/oferta/x.html?sliderIndex=4"))

    def test_look_alike_domain(self):
        self.assertIn("isn't supported yet", self.error("https://www.emag.ro.example.com/x"))

    def test_scheme_only(self):
        self.assertEqual(self.error("https://"), "Paste a link that starts with https:// or www.")

    def test_malformed_address(self):
        # "www..emag.ro" ends in ".emag.ro", so only the URL check stops it.
        self.assertEqual(self.error("https://www..emag.ro/x/pd/A/"), "That doesn't look like a valid link.")
