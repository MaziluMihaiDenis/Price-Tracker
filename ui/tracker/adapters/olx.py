import logging

from tracker.adapters.base import SiteAdapter, read_detail

logger = logging.getLogger(__name__)


class OlxAdapter(SiteAdapter):
    """OLX listings: a JSON-LD Product block with an Offer."""

    name = "OLX"
    domains = ("olx.ro",)
    default_currency = "EUR"
    default_period = "one_time"

    def _details(self, soup):
        details = {}
        read_detail(details, "description", lambda: self._description(soup))
        logger.warning("DEBUG OLX details: %s", details)    
        return details

    @staticmethod
    def _description(soup):
        """The listing's description text (OLX marks it with data-cy="ad_description")."""
        box = soup.select_one('text-background-action-primary')
        if box is None:
            return None
        return " ".join(box.get_text(" ", strip=True).split())   # one line, single spaces