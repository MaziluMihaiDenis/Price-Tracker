from importlib import import_module

from django.apps import apps
from django.test import TestCase

from tracker import custom_fields as cf
from tracker.models import Category

starter = import_module("tracker.migrations.0005_starter_fields")


class StarterFieldsTests(TestCase):
    """Milestone 3b, acceptance criterion 3."""

    def test_seeded_categories_have_their_starter_fields(self):
        # The test database is built by running every migration, including 0005.
        rent = Category.objects.get(name="Rent")
        # 0005's starter fields first (0006 then adds Floor and Heating after them).
        self.assertEqual([d["label"] for d in cf.definitions(rent)][:4], ["Area", "Rooms", "Location", "Furnished"])
        self.assertEqual(cf.location_definition(Category.objects.get(name="Apartment for sale"))["key"], "location")
        self.assertEqual([d["key"] for d in cf.definitions(Category.objects.get(name="Product"))], ["brand"])
        self.assertEqual(Category.objects.get(name="Groceries").field_definitions, [])

    def test_categories_that_already_have_fields_are_left_alone(self):
        mine = [{"key": "size", "label": "Size", "type": "text"}]
        Category.objects.filter(name="Rent").update(field_definitions=mine)
        Category.objects.filter(name="Product").update(field_definitions=[])
        starter.add_starter_fields(apps, None)  # running it again
        self.assertEqual(Category.objects.get(name="Rent").field_definitions, mine)
        self.assertEqual(Category.objects.get(name="Product").field_definitions, starter.STARTER_FIELDS["Product"])


floor_heating = import_module("tracker.migrations.0006_floor_heating_fields")


class FloorHeatingFieldsTests(TestCase):
    """Milestone 3c, acceptance criterion 11."""

    def test_rent_and_apartment_get_floor_and_heating(self):
        for name in ("Rent", "Apartment for sale"):
            labels = [d["label"] for d in cf.definitions(Category.objects.get(name=name))]
            self.assertEqual(labels[-2:], ["Floor", "Heating"], name)
        self.assertNotIn("Floor", [d["label"] for d in cf.definitions(Category.objects.get(name="Product"))])

    def test_existing_fields_are_kept_and_not_duplicated(self):
        mine = [{"key": "etaj", "label": "floor", "type": "number"}]
        Category.objects.filter(name="Rent").update(field_definitions=mine)
        floor_heating.add_floor_and_heating(apps, None)
        floor_heating.add_floor_and_heating(apps, None)  # running twice adds nothing more
        self.assertEqual(Category.objects.get(name="Rent").field_definitions,
                         mine + [{"key": "heating", "label": "Heating", "type": "text"}])
