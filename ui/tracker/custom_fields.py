"""Category custom fields: what each category asks for (Area, Rooms, Location...) and the values.

Definitions live in `Category.field_definitions` and values in `Item.custom_values`, both JSON:

    [{"key": "area", "label": "Area", "type": "number", "unit": "m²"},
     {"key": "location", "label": "Location", "type": "location"}]
    {"area": "32", "furnished": true,
     "location": {"lat": 44.43, "lon": 26.05, "address": "Strada Exemplului"}}

A field's key is made once from its first label and never changes, so renaming "Area" to
"Surface" keeps every value. Removing a field only hides its values; they stay stored.
"""

from decimal import Decimal, InvalidOperation

from django import forms
from django.utils.text import slugify

TEXT, NUMBER, YES_NO, CHOICE, LOCATION = "text", "number", "yes_no", "choice", "location"
TYPE_CHOICES = [(TEXT, "Text"), (NUMBER, "Number"), (YES_NO, "Yes / No"), (CHOICE, "Choice list"),
                (LOCATION, "Location (map)")]
TYPES = {value for value, _ in TYPE_CHOICES}
MAX_FIELDS = 10
MAX_LABEL = 40
MAX_TEXT = 200
MAX_CHOICES = 20


# --- Definitions -------------------------------------------------------------------------

def make_key(label, taken):
    """A stable key from a label ("Year built" -> "year_built"), unique among `taken`."""
    base = slugify(label).replace("-", "_")[:30] or "field"
    key, number = base, 2
    while key in taken:
        key, number = f"{base}_{number}", number + 1
    return key


def parse_choices(text):
    """'central, own boiler' -> ['central', 'own boiler'] (blanks and repeats dropped)."""
    seen, result = set(), []
    for part in (text or "").split(","):
        option = " ".join(part.split())
        if option and option.lower() not in seen:
            seen.add(option.lower())
            result.append(option)
    return result


def definitions(category):
    """The category's valid field definitions, in order. Anything malformed is ignored."""
    result = []
    for definition in category.field_definitions or []:
        if (isinstance(definition, dict) and definition.get("type") in TYPES
                and isinstance(definition.get("key"), str) and definition.get("label")):
            if definition["type"] == CHOICE and not definition.get("choices"):
                continue
            result.append(definition)
    return result


def location_definition(category):
    return next((d for d in definitions(category) if d["type"] == LOCATION), None)


# --- Values: forms -----------------------------------------------------------------------

def fits(definition, value):
    """True when a stored value has the shape this field's type expects.

    A field can be removed and later added back under the same name with another type
    (the key is reused, so its old values return). A value that doesn't fit the new type is
    treated as empty: not shown, not put in the form, and not erased when the item is saved.
    """
    kind = definition["type"]
    if value is None:
        return False
    if kind == LOCATION:
        return valid_location(value) is not None
    if kind == YES_NO:
        return isinstance(value, bool)
    if kind == NUMBER:
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            return False
        try:
            return Decimal(str(value)).is_finite()
        except (InvalidOperation, ValueError):
            return False
    return isinstance(value, str)  # text and choice


def _location_parts(key):
    return f"{key}__lat", f"{key}__lon", f"{key}__address"


class CustomValuesForm(forms.Form):
    """The custom fields of one category, as a normal Django form.

    A Location becomes three inputs (latitude, longitude, address) that the map fills in.
    Use a prefix per category, so every category's block can be on the same page.
    """

    def __init__(self, *args, category, values=None, **kwargs):
        kwargs.setdefault("prefix", f"cf{category.pk}")
        super().__init__(*args, **kwargs)
        self.category = category
        self.field_definitions = definitions(category)
        values = values or {}
        for definition in self.field_definitions:
            key, label, kind = definition["key"], definition["label"], definition["type"]
            stored = values.get(key)
            if not fits(definition, stored):
                stored = None  # a value of another shape is never shown in the form
            if kind == LOCATION:
                lat_name, lon_name, address_name = _location_parts(key)
                location = stored or {}
                self.fields[lat_name] = forms.DecimalField(
                    required=False, min_value=-90, max_value=90, max_digits=10, decimal_places=7,
                    label=f"{label}: latitude", initial=location.get("lat"))
                self.fields[lon_name] = forms.DecimalField(
                    required=False, min_value=-180, max_value=180, max_digits=11, decimal_places=7,
                    label=f"{label}: longitude", initial=location.get("lon"))
                self.fields[address_name] = forms.CharField(
                    required=False, max_length=MAX_TEXT, label=f"{label}: address",
                    initial=location.get("address", ""))
                continue
            if kind == NUMBER:
                unit = definition.get("unit", "")
                field = forms.DecimalField(required=False, max_digits=15, decimal_places=4,
                                           label=f"{label} ({unit})" if unit else label)
            elif kind == YES_NO:
                # Three answers, not a checkbox: "not filled in" must differ from "No".
                widget = forms.NullBooleanSelect()
                widget.choices = [("unknown", "—"), ("true", "Yes"), ("false", "No")]
                field = forms.NullBooleanField(required=False, label=label, widget=widget)
            elif kind == CHOICE:
                options = definition["choices"]
                field = forms.ChoiceField(required=False, label=label,
                                          choices=[("", "—")] + [(option, option) for option in options])
            else:
                field = forms.CharField(required=False, max_length=MAX_TEXT, label=label)
            field.initial = stored
            self.fields[key] = field
        for field in self.fields.values():
            css = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            field.widget.attrs.setdefault("class", css)

    def clean(self):
        cleaned = super().clean()
        for definition in self.field_definitions:
            if definition["type"] != LOCATION:
                continue
            lat_name, lon_name, _ = _location_parts(definition["key"])
            if (cleaned.get(lat_name) is None) != (cleaned.get(lon_name) is None):
                raise forms.ValidationError(
                    f"{definition['label']}: choose a point on the map, or clear the location.")
        return cleaned

    def layout(self):
        """What the template draws, in order: a field, or a Location's three inputs."""
        rows = []
        for definition in self.field_definitions:
            if definition["type"] == LOCATION:
                rows.append({"definition": definition, "location": self.location_fields(definition)})
            else:
                rows.append({"definition": definition, "field": self[definition["key"]]})
        return rows

    def location_fields(self, definition):
        """The three bound inputs of a Location field, for the map template."""
        return [self[name] for name in _location_parts(definition["key"])]

    def values(self):
        """The cleaned values, keyed by field key. Empty fields map to None."""
        result = {}
        for definition in self.field_definitions:
            key, kind = definition["key"], definition["type"]
            if kind == LOCATION:
                lat_name, lon_name, address_name = _location_parts(key)
                lat, lon = self.cleaned_data.get(lat_name), self.cleaned_data.get(lon_name)
                address = " ".join((self.cleaned_data.get(address_name) or "").split())
                if lat is not None and lon is not None:
                    result[key] = {"lat": float(lat), "lon": float(lon), "address": address}
                else:  # no pin (e.g. the map couldn't load): an address alone is still useful
                    result[key] = {"lat": None, "lon": None, "address": address} if address else None
            elif kind == NUMBER:
                number = self.cleaned_data.get(key)
                result[key] = _number_text(number) if number is not None else None
            elif kind == YES_NO:
                result[key] = self.cleaned_data.get(key)
            else:
                result[key] = (self.cleaned_data.get(key) or "").strip() or None
        return result


def _number_text(number):
    """Decimal('32.5000') -> '32.5', Decimal('100') -> '100'."""
    return f"{number.normalize():f}"


def merge_values(stored, category, new_values):
    """Stored values updated with one category's new values; other categories' stay untouched."""
    merged = dict(stored or {})
    for definition in definitions(category):
        value = new_values.get(definition["key"])
        if value is None:
            # Clear the value, unless it has another shape: the form didn't show it, so an
            # empty answer doesn't mean the user removed it.
            if fits(definition, merged.get(definition["key"])):
                merged.pop(definition["key"], None)
        else:
            merged[definition["key"]] = value
    return merged


# --- Values: display ---------------------------------------------------------------------

def valid_location(value):
    """A stored location as {"lat", "lon", "address"}, or None when missing or malformed.

    lat and lon are None for an address saved without a pin.
    """
    if not isinstance(value, dict):
        return None
    address = str(value.get("address") or "")[:MAX_TEXT]
    if value.get("lat") is None and value.get("lon") is None:
        return {"lat": None, "lon": None, "address": address} if address else None
    try:
        lat, lon = float(value.get("lat")), float(value.get("lon"))
    except (TypeError, ValueError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return {"lat": lat, "lon": lon, "address": address}


def display_value(definition, value):
    """How a stored value reads on a page, or "" when there's nothing (valid) to show."""
    kind = definition["type"]
    if value == "" or not fits(definition, value):
        return ""
    if kind == NUMBER:
        try:
            number = _number_text(Decimal(str(value)))
        except (InvalidOperation, ValueError):
            return ""
        unit = definition.get("unit", "")
        return f"{number} {unit}" if unit else number
    if kind == YES_NO:
        return {True: "Yes", False: "No"}.get(value, "")
    if kind == LOCATION:
        location = valid_location(value)
        if location is None:
            return ""
        return location["address"] or f"{location['lat']:.5f}, {location['lon']:.5f}"
    return str(value)[:MAX_TEXT]


def display_rows(item):
    """[(definition, text)] for the item's category fields that have a value."""
    values = item.custom_values or {}
    rows = []
    for definition in definitions(item.category):
        text = display_value(definition, values.get(definition["key"]))
        if text:
            rows.append((definition, text))
    return rows


def item_location(item):
    """The item's location (from its category's Location field), or None."""
    definition = location_definition(item.category)
    if definition is None:
        return None
    return valid_location((item.custom_values or {}).get(definition["key"]))
