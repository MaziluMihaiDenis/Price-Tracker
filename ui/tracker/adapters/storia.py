import json

from tracker.adapters.base import SiteAdapter, read_detail

# Storia gives some details as codes; these read better in the app (milestone 3c).
FLOORS = {"ground_floor": "Ground floor", "cellar": "Basement", "garret": "Attic",
          "floor_higher_10": "Above floor 10"}
HEATING = {"gas": "Gas", "urban": "District heating", "boiler_room": "Building boiler",
           "electrical": "Electric", "tiled_stove": "Tiled stove", "other": "Other"}
FURNISHED = {"yes": True, "no": False, "furnished": True, "unfurnished": False}


def readable(code, names):
    """'ground_floor' -> 'Ground floor'; 'floor_3' -> 'Floor 3'; unknown codes are tidied."""
    code = str(code).strip()
    if code in names:
        return names[code]
    if code.startswith("floor_") and code[6:].isdigit():
        return f"Floor {int(code[6:])}"
    return code.replace("_", " ").strip().capitalize()


class StoriaAdapter(SiteAdapter):
    """Storia listings: a JSON-LD @graph whose listing node has an Offer (usually EUR)."""

    name = "Storia"
    domains = ("storia.ro",)
    default_currency = "EUR"
    default_period = "monthly"  # most tracked listings are rentals; editable in the preview

    def _details(self, soup):
        """Area, rooms, floor... and the map pin, from the data block Storia's own page uses.

        This block can change when Storia redesigns its pages; every detail is read on its
        own, so a missing one is simply skipped (the price comes from elsewhere).
        """
        script = soup.find("script", id="__NEXT_DATA__")
        if script is None or not script.string:
            return {}
        ad = json.loads(script.string)["props"]["pageProps"]["ad"]
        values = {item["key"]: item.get("value") for item in ad.get("characteristics") or []
                  if isinstance(item, dict) and item.get("key")}
        details = {}
        read_detail(details, "area", lambda: str(values["m"]).strip())
        read_detail(details, "rooms", lambda: str(values["rooms_num"]).strip())
        read_detail(details, "year_built", lambda: str(values["build_year"]).strip())
        read_detail(details, "floor", lambda: readable(values["floor_no"], FLOORS))
        read_detail(details, "heating", lambda: readable(values["heating"], HEATING))
        read_detail(details, "furnished", lambda: FURNISHED[str(values["furniture"]).strip().lower()])
        read_detail(details, "location", lambda: self._location(ad["location"]))
        return details

    @staticmethod
    def _location(location):
        coordinates = location["coordinates"]
        lat, lon = float(coordinates["latitude"]), float(coordinates["longitude"])
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return None
        parts = []
        street = ((location.get("address") or {}).get("street") or {})
        if street.get("name"):
            parts.append(" ".join(filter(None, [street["name"], str(street.get("number") or "")])).strip())
        areas = ((location.get("reverseGeocoding") or {}).get("locations") or [])
        if areas and areas[-1].get("fullName"):
            parts.append(areas[-1]["fullName"])  # the most precise one, e.g. "Militari, Sectorul 6, Bucuresti"
        return {"lat": lat, "lon": lon, "address": ", ".join(parts)[:200]}
