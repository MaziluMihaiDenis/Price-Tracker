"""Starter custom fields for the seeded categories (milestone 3b).

Only categories with no fields yet get them, so anything set up by hand is left alone.
Going backwards does nothing: removing fields someone may have filled in would hide data.
"""

from django.db import migrations

STARTER_FIELDS = {
    "Rent": [
        {"key": "area", "label": "Area", "type": "number", "unit": "m²"},
        {"key": "rooms", "label": "Rooms", "type": "number"},
        {"key": "location", "label": "Location", "type": "location"},
        {"key": "furnished", "label": "Furnished", "type": "yes_no"},
    ],
    "Apartment for sale": [
        {"key": "area", "label": "Area", "type": "number", "unit": "m²"},
        {"key": "rooms", "label": "Rooms", "type": "number"},
        {"key": "year_built", "label": "Year built", "type": "number"},
        {"key": "location", "label": "Location", "type": "location"},
    ],
    "Product": [{"key": "brand", "label": "Brand", "type": "text"}],
    "Subscription": [{"key": "plan", "label": "Plan", "type": "text"}],
}


def add_starter_fields(apps, schema_editor):
    Category = apps.get_model("tracker", "Category")
    for name, fields in STARTER_FIELDS.items():
        category = Category.objects.filter(name=name).first()
        if category is not None and not category.field_definitions:
            category.field_definitions = fields
            category.save(update_fields=["field_definitions"])


class Migration(migrations.Migration):
    dependencies = [("tracker", "0004_item_archived_at")]

    operations = [migrations.RunPython(add_starter_fields, migrations.RunPython.noop)]
