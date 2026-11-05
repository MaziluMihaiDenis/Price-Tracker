from tracker.adapters.base import SiteAdapter


class EmagAdapter(SiteAdapter):
    """eMAG product pages: a JSON-LD Product block with an Offer (price in RON)."""

    name = "eMAG"
    domains = ("emag.ro",)
    default_currency = "RON"
    default_period = "one_time"
