"""Price change indicators: "↓ 7.7%", "Lowest ever", and the lowest and highest prices.

Everything here is calculated from the saved price history whenever a page is shown;
nothing is stored. Prices are compared in their own currency, so a 470 EUR rent that
never changes shows no arrow even when the euro moves. Only when two prices are in
different currencies are both converted to RON, each at its own day's BNR rate.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone

from tracker.money import BASE_CURRENCY
from tracker.models import PricePoint

TENTH = Decimal("0.1")


@dataclass
class Change:
    direction: str  # "down" or "up"
    percent: Decimal  # always positive, rounded to one decimal
    previous: PricePoint  # the last price before the current one
    since: datetime  # when the current price first appeared


@dataclass
class PriceSummary:
    change: Change | None = None  # None: one price only, never changed, or no rate to compare
    is_lowest_ever: bool = False
    lowest: PricePoint | None = None  # the first time the lowest price appeared
    highest: PricePoint | None = None  # the first time the highest price appeared


def _same_price(a, b):
    return a.currency == b.currency and a.amount == b.amount


def _in_ron(point, book):
    """The price in RON at its own day's rate, or None when that rate is missing."""
    return book.convert(point.amount, point.currency, BASE_CURRENCY, timezone.localdate(point.recorded_at))


def _change(previous, current, since, book):
    if previous.currency == current.currency:
        old, new = previous.amount, current.amount
    else:
        old, new = _in_ron(previous, book), _in_ron(current, book)
        if old is None or new is None:
            return None
    if not old or new == old:
        return None
    percent = (abs(new - old) / old * 100).quantize(TENTH, rounding=ROUND_HALF_UP)
    return Change("down" if new < old else "up", percent, previous, since)


def _comparable_values(points, book):
    """(value, point) pairs on one scale: the amounts if all prices share a currency, else RON."""
    if len({point.currency for point in points}) == 1:
        return [(point.amount, point) for point in points]
    pairs = [(_in_ron(point, book), point) for point in points]
    return [(value, point) for value, point in pairs if value is not None]


def summarize(points, book):
    """Indicators for one item. `points` are its prices, oldest first; `book` is a RateBook."""
    points = list(points)
    summary = PriceSummary()
    if not points:
        return summary
    current = points[-1]

    # Walk back over repeats of the current price (daily checks save it again every day)
    # to find when it first appeared and which different price came before it.
    start = len(points) - 1
    while start > 0 and _same_price(points[start - 1], current):
        start -= 1
    if start > 0:
        summary.change = _change(points[start - 1], current, points[start].recorded_at, book)

    values = _comparable_values(points, book)
    if values:
        # Strict comparisons keep the first point when a price repeats.
        lowest_value, summary.lowest = values[0]
        highest_value, summary.highest = values[0]
        for value, point in values[1:]:
            if value < lowest_value:
                lowest_value, summary.lowest = value, point
            if value > highest_value:
                highest_value, summary.highest = value, point
        current_value = values[-1][0] if values[-1][1] is current else None
        summary.is_lowest_ever = current_value == lowest_value and lowest_value != highest_value
    return summary


def attach_summaries(items, book):
    """Set `item.price_summary` on each item, loading all their prices in one query."""
    items = list(items)
    by_item = defaultdict(list)
    if items:
        prices = PricePoint.objects.filter(item_id__in=[item.pk for item in items]).order_by("recorded_at", "id")
        for point in prices:
            by_item[point.item_id].append(point)
    for item in items:
        item.price_summary = summarize(by_item[item.pk], book)
    return items
