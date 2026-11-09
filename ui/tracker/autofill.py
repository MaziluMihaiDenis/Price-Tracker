"""Filling custom fields from the details a website gives (milestone 3c).

The adapters read details with standard names ("area", "rooms", "location"...) plus, for eMAG,
a specifications table ("Tip produs": "Gel de curatare"). Here they're matched to a
category's fields: by a list of known names, or for specifications by the field's label.
A detail is only used when its value fits the field's type; anything else is skipped.
"""

import unicodedata
from decimal import Decimal, InvalidOperation

from tracker import custom_fields as cf


def normalize(text):
    """'Suprafață utilă' -> 'suprafata utila'; 'Nr. camere' -> 'nr camere'; 'year_built' -> 'year built'."""
    text = unicodedata.normalize("NFKD", str(text))
    text = "".join(char for char in text if not unicodedata.combining(char)).lower()
    text = "".join(char if char.isalnum() else " " for char in text)
    return " ".join(text.split())


# Which field names receive which standard detail (compared after normalize()).
ALIASES = {
    "area": {"area", "suprafata", "suprafata utila", "surface"},
    "rooms": {"rooms", "camere", "nr camere", "numar camere", "number of rooms"},
    "year_built": {"year built", "an constructie", "anul constructiei"},
    "floor": {"floor", "etaj"},
    "heating": {"heating", "incalzire"},
    "brand": {"brand", "marca", "producator"},
    "furnished": {"furnished", "mobilat"},
}
YES = {"yes", "da", "true"}
NO = {"no", "nu", "false"}


def _found(definition, details):
    """(where it came from, the website's value) for this field, or (None, None).

    "Where" is a detail name ("area") or ("spec", label) for an eMAG specification row.
    """
    if definition["type"] == cf.LOCATION:
        return ("location", details["location"]) if "location" in details else (None, None)
    names = {normalize(definition["key"]), normalize(definition["label"])}
    for detail, aliases in ALIASES.items():
        if names & aliases and detail in details:
            return detail, details[detail]
    label = normalize(definition["label"])
    for spec_label, value in (details.get("specs") or {}).items():
        if normalize(spec_label) == label:
            return ("spec", spec_label), value
    return None, None


def _fitted(definition, value):
    """The value converted to the field's type, or None when it doesn't fit."""
    kind = definition["type"]
    if kind == cf.LOCATION:
        location = cf.valid_location(value)
        return location if location and location["lat"] is not None else None
    if kind == cf.NUMBER:
        try:
            number = Decimal(str(value).strip().replace(",", "."))
        except (InvalidOperation, ValueError):
            return None
        return f"{number.normalize():f}" if number.is_finite() else None
    if kind == cf.YES_NO:
        if isinstance(value, bool):
            return value
        word = normalize(value)
        return True if word in YES else False if word in NO else None
    if kind == cf.CHOICE:
        wanted = normalize(value)
        return next((option for option in definition["choices"] if normalize(option) == wanted), None)
    if isinstance(value, bool):  # e.g. "furnished" landing in a Text field
        return "Yes" if value else "No"
    if isinstance(value, (dict, list)):  # a location or a whole table never fits a text box
        return None
    text = " ".join(str(value).split())[:cf.MAX_TEXT]
    return text or None


def match_with_sources(details, category):
    """({field key: value}, {where each used value came from}) for the category's fields."""
    values, used = {}, set()
    if not details:
        return values, used
    for definition in cf.definitions(category):
        source, value = _found(definition, details)
        if source is None:
            continue
        fitted = _fitted(definition, value)
        if fitted is not None:
            values[definition["key"]] = fitted
            used.add(source)
    return values, used


def match(details, category):
    """{field key: value} for the category's fields the website's details can fill."""
    return match_with_sources(details, category)[0]


DETAIL_NAMES = {"area": "Area", "rooms": "Rooms", "year_built": "Year built", "floor": "Floor",
                "heating": "Heating", "brand": "Brand", "furnished": "Furnished", "location": "Location"}


def unused(details, used):
    """Readable "Label: value" lines for the details no field took (shown as "Not used")."""
    lines = []
    for detail, value in (details or {}).items():
        if detail == "specs":
            lines += [f"{label}: {text}" for label, text in value.items() if ("spec", label) not in used]
            continue
        if detail in used:
            continue
        if isinstance(value, dict):
            shown = value.get("address") or "map pin"
        elif isinstance(value, bool):
            shown = "Yes" if value else "No"
        else:
            shown = value
        lines.append(f"{DETAIL_NAMES.get(detail, detail)}: {shown}")
    return lines
