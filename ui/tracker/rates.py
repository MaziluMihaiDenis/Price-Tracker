"""Official exchange rates from the National Bank of Romania (BNR).

BNR publishes, for each banking day, how many RON one unit of a currency costs.
RON is the base currency, so only the other currencies (today: EUR) are stored.
"""

import xml.etree.ElementTree as ET
from datetime import date
from decimal import Decimal, InvalidOperation

import httpx
from django.db import transaction
from django.utils import timezone

from tracker.models import ExchangeRate, PricePoint

DAILY_URL = "https://curs.bnr.ro/nbrfxrates.xml"
YEAR_URL = "https://curs.bnr.ro/files/xml/years/nbrfxrates{year}.xml"
TIMEOUT_SECONDS = 20
# Currencies stored besides RON (the base). Must match PricePoint.Currency.
CURRENCIES = tuple(code for code in PricePoint.Currency.values if code != "RON")
# History starts no later than this, even when there are no older prices.
HISTORY_START = date(2025, 1, 1)


class RatesUnavailable(Exception):
    """BNR's file could not be downloaded or read."""


def fetch(url):
    """Download one BNR file. Tests replace this function, so they stay offline."""
    try:
        response = httpx.get(url, timeout=TIMEOUT_SECONDS)
    except httpx.HTTPError as error:
        raise RatesUnavailable(f"Couldn't download {url}: {type(error).__name__}") from error
    if response.status_code != 200:
        raise RatesUnavailable(f"BNR returned HTTP {response.status_code} for {url}")
    return response.text


def _local_name(tag):
    """'{https://www.bnr.ro/xsd}Cube' -> 'Cube'. BNR files differ in this prefix (http/https)."""
    return tag.rsplit("}", 1)[-1]


def parse_rates(xml_text, currencies=CURRENCIES):
    """Return [(date, currency, RON per unit)] from a BNR daily or yearly file."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as error:
        raise RatesUnavailable(f"BNR file is not valid XML: {error}") from error
    rates = []
    for cube in root.iter():
        if _local_name(cube.tag) != "Cube" or not cube.get("date"):
            continue
        day = date.fromisoformat(cube.get("date"))
        for rate in cube:
            code = rate.get("currency")
            if _local_name(rate.tag) != "Rate" or code not in currencies:
                continue
            try:
                value = Decimal(rate.text.strip())
            except (AttributeError, InvalidOperation):
                continue
            multiplier = int(rate.get("multiplier", "1"))  # e.g. HUF is quoted per 100 units
            rates.append((day, code, value / multiplier))
    return rates


@transaction.atomic
def save_rates(rates):
    """Store rates; re-importing the same day updates it instead of duplicating it."""
    for day, code, ron_per_unit in rates:
        ExchangeRate.objects.update_or_create(date=day, currency=code, defaults={"ron_per_unit": ron_per_unit})
    return len(rates)


def default_start():
    """The earlier of the oldest saved price and HISTORY_START."""
    oldest = PricePoint.objects.order_by("recorded_at").values_list("recorded_at", flat=True).first()
    if oldest is None:
        return HISTORY_START
    return min(timezone.localdate(oldest), HISTORY_START)


def import_latest_rates():
    """Import BNR's latest published day (the daily file). Returns the number of rates saved."""
    return save_rates(parse_rates(fetch(DAILY_URL)))


def import_rates(since=None):
    """Import history from the year before `since` up to today, then the latest day.

    The year before is included because BNR's first rate of a year is around 3 January:
    a price from 1 January needs the previous year's last rate.
    Returns {source: number of rates saved}.
    """
    since = since or default_start()
    saved = {}
    for year in range(since.year - 1, timezone.localdate().year + 1):
        saved[str(year)] = save_rates(parse_rates(fetch(YEAR_URL.format(year=year))))
    saved["latest"] = import_latest_rates()
    return saved
