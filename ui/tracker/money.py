"""Showing prices in the viewer's favourite currency.

Prices are always stored in their original currency. They are converted only when shown,
at the BNR rate for the day each price was recorded (the latest rate on or before that day,
because BNR publishes nothing on weekends and holidays).
"""

from bisect import bisect_right
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone

from tracker.models import ExchangeRate, Profile

BASE_CURRENCY = "RON"  # BNR quotes every rate as "RON per unit"
CENT = Decimal("0.01")


class RateBook:
    """All known rates, loaded once, so a page with many prices needs a single query."""

    def __init__(self, rates=()):
        self._dates = {}
        self._values = {}
        for day, currency, ron_per_unit in sorted(rates):
            self._dates.setdefault(currency, []).append(day)
            self._values.setdefault(currency, []).append(ron_per_unit)

    @classmethod
    def load(cls):
        return cls(ExchangeRate.objects.values_list("date", "currency", "ron_per_unit"))

    def ron_per_unit(self, currency, day):
        """RON per unit of `currency` on `day` (or the latest earlier day), or None."""
        if currency == BASE_CURRENCY:
            return Decimal(1)
        dates = self._dates.get(currency, [])
        position = bisect_right(dates, day)
        return self._values[currency][position - 1] if position else None

    def convert(self, amount, currency, target, day):
        """`amount` in `currency` expressed in `target`, or None when a rate is missing."""
        if currency == target:
            return amount
        source_rate = self.ron_per_unit(currency, day)
        target_rate = self.ron_per_unit(target, day)
        if source_rate is None or target_rate is None:
            return None
        return amount * source_rate / target_rate


@dataclass
class DisplayPrice:
    amount: Decimal  # what to show large
    currency: str
    original_amount: Decimal
    original_currency: str
    converted: bool = False  # True when amount/currency differ from the original
    missing_rate: bool = False  # True when conversion was wanted but no rate exists


def display_price(amount, currency, recorded_at, target, book):
    """How one price should be shown to a viewer whose favourite currency is `target`."""
    original = DisplayPrice(amount, currency, amount, currency)
    if not target or target == currency or book is None:
        return original
    day = timezone.localdate(recorded_at) if isinstance(recorded_at, datetime) else recorded_at
    converted = book.convert(amount, currency, target, day)
    if converted is None:
        original.missing_rate = True
        return original
    return DisplayPrice(converted.quantize(CENT, rounding=ROUND_HALF_UP), target, amount, currency, converted=True)


def display_currency_for(user):
    """The user's favourite currency (a profile is created if an old account has none)."""
    profile, _ = Profile.objects.get_or_create(user=user)
    return profile.favorite_currency
