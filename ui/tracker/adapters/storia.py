from tracker.adapters.base import SiteAdapter


class StoriaAdapter(SiteAdapter):
    """Storia listings: a JSON-LD @graph whose listing node has an Offer (usually EUR)."""

    name = "Storia"
    domains = ("storia.ro",)
    default_currency = "EUR"
    default_period = "monthly"  # most tracked listings are rentals; editable in the preview
