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
        self.assertEqual([d["label"] for d in cf.definitions(rent)], ["Area", "Rooms", "Location", "Furnished"])
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
