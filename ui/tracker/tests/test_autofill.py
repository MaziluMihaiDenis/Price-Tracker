from django.test import SimpleTestCase

from tracker import autofill
from tracker.models import Category

STORIA = {"area": "38", "rooms": "1", "year_built": "2017", "floor": "Ground floor", "heating": "Gas",
          "location": {"lat": 44.43, "lon": 26.05, "address": "Strada Exemplului, Militari"}}
EMAG = {"brand": "CeraVe", "specs": {"Tip produs": "Gel de curatare", "Tipul de ten": "Uscat, Normal", "Set": "Nu"}}
RENT = [
    {"key": "area", "label": "Area", "type": "number", "unit": "m²"},
    {"key": "rooms", "label": "Rooms", "type": "number"},
    {"key": "location", "label": "Location", "type": "location"},
    {"key": "furnished", "label": "Furnished", "type": "yes_no"},
    {"key": "floor", "label": "Floor", "type": "text"},
    {"key": "heating", "label": "Heating", "type": "text"},
]


def category(fields):
    return Category(pk=1, name="Test", field_definitions=fields)


class MatchTests(SimpleTestCase):
    def test_storia_details_fill_rent_fields(self):
        """Acceptance criteria 1 and 3 (matching part)."""
        self.assertEqual(autofill.match(STORIA, category(RENT)), {
            "area": "38", "rooms": "1", "floor": "Ground floor", "heating": "Gas",
            "location": {"lat": 44.43, "lon": 26.05, "address": "Strada Exemplului, Militari"}})

    def test_romanian_and_accented_labels_match(self):
        fields = [{"key": "suprafata", "label": "Suprafață utilă", "type": "number"},
                  {"key": "nr_camere", "label": "Nr. camere", "type": "number"},
                  {"key": "an", "label": "Anul construcției", "type": "number"},
                  {"key": "etaj", "label": "ETAJ", "type": "text"}]
        self.assertEqual(autofill.match(STORIA, category(fields)),
                         {"suprafata": "38", "nr_camere": "1", "an": "2017", "etaj": "Ground floor"})

    def test_emag_brand_and_specifications_by_label(self):
        """Acceptance criterion 4."""
        fields = [{"key": "brand", "label": "Brand", "type": "text"},
                  {"key": "tip_produs", "label": "Tip produs", "type": "text"},
                  {"key": "set", "label": "Set", "type": "yes_no"},
                  {"key": "colour", "label": "Colour", "type": "text"}]
        self.assertEqual(autofill.match(EMAG, category(fields)),
                         {"brand": "CeraVe", "tip_produs": "Gel de curatare", "set": False})

    def test_values_that_dont_fit_are_skipped(self):
        """Acceptance criterion 8."""
        fields = [{"key": "heating", "label": "Heating", "type": "choice", "choices": ["central", "own boiler"]},
                  {"key": "area", "label": "Area", "type": "number"},
                  {"key": "floor", "label": "Floor", "type": "number"}]
        details = {"heating": "Gas", "area": "abc", "floor": "Ground floor"}
        self.assertEqual(autofill.match(details, category(fields)), {})

    def test_choice_matches_ignoring_case_and_accents(self):
        fields = [{"key": "heating", "label": "Heating", "type": "choice", "choices": ["Gaz", "Gas", "District heating"]}]
        self.assertEqual(autofill.match({"heating": "district HEATING"}, category(fields)),
                         {"heating": "District heating"})

    def test_numbers_with_a_comma_and_bad_locations(self):
        fields = [{"key": "area", "label": "Area", "type": "number"}, {"key": "loc", "label": "Where", "type": "location"}]
        self.assertEqual(autofill.match({"area": "38,5", "location": {"lat": 300, "lon": 0}}, category(fields)),
                         {"area": "38.5"})

    def test_no_details_no_values(self):
        self.assertEqual(autofill.match({}, category(RENT)), {})
        self.assertEqual(autofill.match(STORIA, category([])), {})

    def test_unused_details_are_listed(self):
        fields = [{"key": "surface", "label": "Surface", "type": "number"}, {"key": "tip", "label": "Tip produs", "type": "text"}]
        values, used = autofill.match_with_sources({**STORIA, **EMAG}, category(fields))
        self.assertEqual(values, {"surface": "38", "tip": "Gel de curatare"})
        lines = autofill.unused({**STORIA, **EMAG}, used)
        self.assertNotIn("Area: 38", lines)  # used by "Surface"
        self.assertIn("Rooms: 1", lines)
        self.assertIn("Location: Strada Exemplului, Militari", lines)
        self.assertIn("Tipul de ten: Uscat, Normal", lines)
        self.assertNotIn("Tip produs: Gel de curatare", lines)

    def test_text_fields_get_words_not_raw_data(self):
        """Review of M3, low 2."""
        fields = [{"key": "furnished", "label": "Furnished", "type": "text"},
                  {"key": "location", "label": "Location", "type": "text"}]
        details = {"furnished": True, "location": STORIA["location"]}
        self.assertEqual(autofill.match(details, category(fields)), {"furnished": "Yes"})
        self.assertEqual(autofill.match({"furnished": False}, category(fields[:1])), {"furnished": "No"})
