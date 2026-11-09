"""Floor and Heating fields for Rent and Apartment for sale (milestone 3c).

Storia gives both for most listings. They are only added where the category has no field
with that key or name yet; existing fields are never changed. Going backwards does nothing.
"""

from django.db import migrations

NEW_FIELDS = [
    {"key": "floor", "label": "Floor", "type": "text"},
    {"key": "heating", "label": "Heating", "type": "text"},
]
MAX_FIELDS = 10  # as in tracker.custom_fields


def add_floor_and_heating(apps, schema_editor):
    Category = apps.get_model("tracker", "Category")
    for category in Category.objects.filter(name__in=["Rent", "Apartment for sale"]):
        fields = list(category.field_definitions or [])
        keys = {str(field.get("key", "")).lower() for field in fields if isinstance(field, dict)}
        labels = {str(field.get("label", "")).strip().lower() for field in fields if isinstance(field, dict)}
        added = False
        for field in NEW_FIELDS:
            if field["key"] in keys or field["label"].lower() in labels or len(fields) >= MAX_FIELDS:
                continue
            fields.append(dict(field))
            added = True
        if added:
            category.field_definitions = fields
            category.save(update_fields=["field_definitions"])


class Migration(migrations.Migration):
    dependencies = [("tracker", "0005_starter_fields")]

    operations = [migrations.RunPython(add_floor_and_heating, migrations.RunPython.noop)]
