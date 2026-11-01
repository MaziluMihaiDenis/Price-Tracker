from django.db import migrations


def seed_categories(apps, schema_editor):
    Category = apps.get_model("tracker", "Category")
    for name, period in [
        ("Apartment for sale", "one_time"),
        ("Groceries", "one_time"),
        ("Product", "one_time"),
        ("Rent", "monthly"),
        ("Service", "one_time"),
        ("Subscription", "monthly"),
        ("Utility", "monthly"),
    ]:
        Category.objects.get_or_create(name=name, defaults={"default_period": period})


def keep_categories(apps, schema_editor):
    # Seeded categories may have user-created items after this migration runs.
    pass


class Migration(migrations.Migration):
    dependencies = [("tracker", "0001_initial")]

    operations = [migrations.RunPython(seed_categories, keep_categories)]
