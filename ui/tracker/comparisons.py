"""Comparison groups: the group chart, the "Per month" column and "Cheapest".

Pure calculations: the items must come from indicators.attach_summaries(), which sets
`item.price_history` (oldest first) with a single query. Every amount here is in the
viewer's currency, each price converted at its own day's BNR rate.

Fair comparisons only: recurring items (monthly, yearly) are compared by their per-month
value, and one-time purchases only with each other, never a rent with a TV.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from tracker import custom_fields
from tracker.indicators import TENTH
from tracker.models import Item
from tracker.money import CENT, DisplayPrice, display_price

RECURRING = "recurring"
ONE_TIME = "one_time"
MONTHS_PER_PERIOD = {Item.Period.MONTHLY: 1, Item.Period.YEARLY: 12}


@dataclass
class Row:
    item: Item
    price: DisplayPrice | None  # the current price as the viewer sees it; None: no price yet
    kind: str  # RECURRING or ONE_TIME
    per_month: Decimal | None = None  # recurring items with a usable price only
    is_cheapest: bool = False
    vs_cheapest: Decimal | None = None  # percent above the cheapest of the same kind

    @property
    def comparable(self):
        """True when this price can be compared: it exists and is in the viewer's currency."""
        return self.price is not None and not self.price.missing_rate


def mixed_periods(items):
    """The period labels in the group, e.g. ["Monthly", "Yearly"], when there is more than one."""
    periods = {item.period for item in items}
    if len(periods) < 2:
        return []
    return [label for value, label in Item.Period.choices if value in periods]


def _shown(point, currency, book):
    return display_price(point.amount, point.currency, point.recorded_at, currency, book)


def table_rows(items, currency, book):
    """One Row per item, with "Per month", "Cheapest" and "+X% vs cheapest" worked out."""
    rows = []
    for item in items:
        history = item.price_history
        price = _shown(history[-1], currency, book) if history else None
        kind = ONE_TIME if item.period == Item.Period.ONE_TIME else RECURRING
        row = Row(item, price, kind)
        if kind == RECURRING and row.comparable:
            row.per_month = (price.amount / MONTHS_PER_PERIOD[item.period]).quantize(CENT, rounding=ROUND_HALF_UP)
        rows.append(row)

    for kind in (RECURRING, ONE_TIME):
        values = [(row, row.per_month if kind == RECURRING else row.price.amount)
                  for row in rows if row.kind == kind and row.comparable]
        if len(values) < 2:  # nothing to compare with
            continue
        cheapest = min(value for _, value in values)
        for row, value in values:
            if value == cheapest:
                row.is_cheapest = True  # a tie gives every cheapest item the badge
            elif cheapest > 0:
                row.vs_cheapest = ((value - cheapest) / cheapest * 100).quantize(TENTH, rounding=ROUND_HALF_UP)
    return rows


def chart_data(items, currency, book):
    """One series per item for comparison-chart.js. Dates are milliseconds, for a real time axis."""
    data = {"currency": currency, "series": [], "missing": 0}
    for item in items:
        points = []
        for point in item.price_history:
            shown = _shown(point, currency, book)
            if shown.missing_rate:  # never mix currencies on one chart
                data["missing"] += 1
                continue
            points.append({
                "x": int(point.recorded_at.timestamp() * 1000),
                "y": str(shown.amount),
                "original": f"{shown.original_amount:.2f} {shown.original_currency}" if shown.converted else "",
            })
        if points:
            data["series"].append({"name": item.name, "points": points})
    return data


def field_columns(rows):
    """Custom-field columns and map pins for a group whose items all share one category.

    Returns (definitions, map_points). Each row gets `row.field_cells`, one per column:
    {"text": ..., "pin": n} where `pin` is set on the Location cell when the item has a pin.
    The pin number is the row number, so the map and the table match.
    With mixed categories there are no columns and no map.
    """
    for row in rows:
        row.field_cells = []
    categories = {row.item.category_id for row in rows}
    if len(categories) != 1:
        return [], []
    definitions = custom_fields.definitions(rows[0].item.category)
    points = []
    for number, row in enumerate(rows, start=1):
        values = row.item.custom_values or {}
        location = custom_fields.item_location(row.item)
        has_pin = bool(location and location["lat"] is not None)
        row.field_cells = [{"text": custom_fields.display_value(d, values.get(d["key"])),
                            "pin": number if has_pin and d["type"] == custom_fields.LOCATION else None}
                           for d in definitions]
        if has_pin:
            price = f"{row.price.amount:.2f} {row.price.currency}" if row.price else "No price yet"
            points.append({"lat": location["lat"], "lon": location["lon"], "number": number,
                           "name": row.item.name, "price": price, "address": location["address"]})
    return definitions, points
