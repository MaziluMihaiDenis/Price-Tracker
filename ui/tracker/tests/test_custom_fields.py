from django.test import SimpleTestCase

from tracker import custom_fields as cf
from tracker.models import Category, Item

RENT_FIELDS = [
    {"key": "area", "label": "Area", "type": "number", "unit": "m²"},
    {"key": "rooms", "label": "Rooms", "type": "number"},
    {"key": "location", "label": "Location", "type": "location"},
    {"key": "furnished", "label": "Furnished", "type": "yes_no"},
    {"key": "heating", "label": "Heating", "type": "choice", "choices": ["central", "own boiler"]},
    {"key": "notes", "label": "Notes", "type": "text"},
]


def category(fields=RENT_FIELDS, pk=4):
    return Category(pk=pk, name="Rent", field_definitions=fields)


def submit(data, values=None, cat=None):
    """Post `data` (without prefix) to the custom-values form of `cat`."""
    cat = cat or category()
    prefixed = {f"cf{cat.pk}-{name}": value for name, value in data.items()}
    return cf.CustomValuesForm(prefixed, category=cat, values=values)


class KeyAndChoiceTests(SimpleTestCase):
    def test_keys_come_from_labels_and_are_unique(self):
        self.assertEqual(cf.make_key("Year built", set()), "year_built")
        self.assertEqual(cf.make_key("Area", {"area"}), "area_2")
        self.assertEqual(cf.make_key("Suprafață utilă", set()), "suprafata_utila")
        self.assertEqual(cf.make_key("?!", set()), "field")

    def test_choices_are_split_trimmed_and_deduplicated(self):
        self.assertEqual(cf.parse_choices(" central,  own   boiler , Central,, "), ["central", "own boiler"])

    def test_malformed_definitions_are_ignored(self):
        broken = category([{"key": "a", "label": "A", "type": "colour"}, "nonsense",
                           {"key": "c", "label": "C", "type": "choice", "choices": []},
                           {"key": "ok", "label": "OK", "type": "text"}])
        self.assertEqual([d["key"] for d in cf.definitions(broken)], ["ok"])


class ValueFormTests(SimpleTestCase):
    def test_valid_values(self):
        """Acceptance criterion 4."""
        form = submit({"area": "32", "rooms": "1", "furnished": "true", "heating": "central", "notes": " Quiet ",
                       "location__lat": "44.43", "location__lon": "26.05",
                       "location__address": " Strada  Exemplului "})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.values(), {
            "area": "32", "rooms": "1", "furnished": True, "heating": "central", "notes": "Quiet",
            "location": {"lat": 44.43, "lon": 26.05, "address": "Strada Exemplului"}})

    def test_everything_is_optional(self):
        form = submit({})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(all(value is None for value in form.values().values()))

    def test_text_in_a_number_is_rejected(self):
        """Acceptance criterion 4."""
        form = submit({"area": "abc"})
        self.assertFalse(form.is_valid())
        self.assertIn("area", form.errors)

    def test_only_listed_choices_are_accepted(self):
        """Acceptance criterion 5."""
        self.assertFalse(submit({"heating": "gas"}).is_valid())

    def test_yes_no_has_three_answers(self):
        form = submit({"furnished": "false"})
        self.assertTrue(form.is_valid())
        self.assertIs(form.values()["furnished"], False)
        form = submit({"furnished": "unknown"})
        self.assertTrue(form.is_valid())
        self.assertIsNone(form.values()["furnished"])

    def test_location_must_be_on_earth(self):
        """Acceptance criterion 9: latitude 200 is rejected."""
        form = submit({"location__lat": "200", "location__lon": "26"})
        self.assertFalse(form.is_valid())
        self.assertIn("location__lat", form.errors)

    def test_location_needs_both_coordinates(self):
        form = submit({"location__lat": "44.4", "location__address": "Militari"})
        self.assertFalse(form.is_valid())
        self.assertIn("choose a point on the map", str(form.non_field_errors()))

    def test_an_address_without_a_pin_is_kept(self):
        """Offline: the map can't load, but the typed address is saved and shown."""
        form = submit({"location__address": "Militari, București"})
        self.assertTrue(form.is_valid(), form.errors)
        value = form.values()["location"]
        self.assertEqual(value, {"lat": None, "lon": None, "address": "Militari, București"})
        self.assertEqual(cf.display_value(cf.location_definition(category()), value), "Militari, București")

    def test_long_text_is_rejected(self):
        self.assertFalse(submit({"notes": "x" * 201}).is_valid())

    def test_stored_values_are_shown_as_initial_values(self):
        form = cf.CustomValuesForm(category=category(), values={
            "area": "32", "furnished": True, "location": {"lat": 44.4, "lon": 26.0, "address": "Militari"}})
        self.assertEqual(form["area"].value(), "32")
        self.assertIn('value="true" selected', str(form["furnished"]))
        self.assertEqual([field.value() for field in form.location_fields(cf.location_definition(category()))],
                         [44.4, 26.0, "Militari"])


class MergeAndDisplayTests(SimpleTestCase):
    def test_merge_touches_only_this_categorys_fields(self):
        """Acceptance criteria 6 and 7: other categories' and removed fields' values stay stored."""
        product = Category(pk=3, name="Product", field_definitions=[{"key": "brand", "label": "Brand", "type": "text"}])
        stored = {"area": "32", "old_field": "kept", "brand": "Old"}
        self.assertEqual(cf.merge_values(stored, product, {"brand": "CeraVe"}),
                         {"area": "32", "old_field": "kept", "brand": "CeraVe"})
        self.assertEqual(cf.merge_values(stored, product, {"brand": None}), {"area": "32", "old_field": "kept"})

    def test_display_values(self):
        definitions = {d["key"]: d for d in RENT_FIELDS}
        self.assertEqual(cf.display_value(definitions["area"], "32"), "32 m²")
        self.assertEqual(cf.display_value(definitions["area"], "32.50"), "32.5 m²")
        self.assertEqual(cf.display_value(definitions["rooms"], "2"), "2")
        self.assertEqual(cf.display_value(definitions["furnished"], True), "Yes")
        self.assertEqual(cf.display_value(definitions["furnished"], False), "No")
        self.assertEqual(cf.display_value(definitions["location"], {"lat": 44.4, "lon": 26.05, "address": ""}),
                         "44.40000, 26.05000")
        self.assertEqual(cf.display_value(definitions["area"], "abc"), "")  # malformed stored value
        self.assertEqual(cf.display_value(definitions["location"], {"lat": 300, "lon": 0}), "")

    def test_values_of_another_shape_are_treated_as_empty(self):
        """Review finding: a field re-added under an old name with another type must not crash."""
        old_location = {"lat": 44.4, "lon": 26.0, "address": "Militari"}
        for kind, extra in (("yes_no", {}), ("text", {}), ("choice", {"choices": ["a"]}), ("number", {})):
            definition = {"key": "location", "label": "Location", "type": kind, **extra}
            for stored in (old_location, [1, 2], True if kind != "yes_no" else "yes"):
                self.assertFalse(cf.fits(definition, stored), (kind, stored))
                self.assertEqual(cf.display_value(definition, stored), "")
                form = cf.CustomValuesForm(category=category([definition]), values={"location": stored})
                str(form["location"])  # renders without an error
                self.assertIn(form["location"].value(), (None, ""))
        self.assertFalse(cf.fits({"type": "number"}, "NaN"))
        self.assertFalse(cf.fits({"type": "location"}, "Militari"))

    def test_saving_keeps_a_value_of_another_shape(self):
        """The form didn't show it, so an empty answer must not erase it."""
        definition = {"key": "location", "label": "Location", "type": "yes_no"}
        old = {"location": {"lat": 44.4, "lon": 26.0, "address": "Militari"}}
        self.assertEqual(cf.merge_values(old, category([definition]), {"location": None}), old)
        self.assertEqual(cf.merge_values(old, category([definition]), {"location": True}), {"location": True})
        self.assertEqual(cf.merge_values({"location": False}, category([definition]), {"location": None}), {})

    def test_display_rows_follow_the_current_definitions(self):
        """Acceptance criterion 7: renamed labels show, removed fields are hidden."""
        renamed = [dict(RENT_FIELDS[0], label="Surface")]
        item = Item(category=category(renamed), custom_values={"area": "32", "rooms": "1"})
        self.assertEqual([(d["label"], text) for d, text in cf.display_rows(item)], [("Surface", "32 m²")])

    def test_item_location(self):
        item = Item(category=category(), custom_values={"location": {"lat": "44.44", "lon": "26.05", "address": "X"}})
        self.assertEqual(cf.item_location(item), {"lat": 44.44, "lon": 26.05, "address": "X"})
        item.custom_values = {"location": "nonsense"}
        self.assertIsNone(cf.item_location(item))
