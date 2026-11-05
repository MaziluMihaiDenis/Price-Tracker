"""Shared logic for site adapters: reading a price from a downloaded page.

Adapted from the Milestone 1 spike (spikes/scraping/extract.py). Only the two methods
that proved reliable on eMAG and Storia are kept: structured data (JSON-LD) first,
then price meta tags.
"""

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from bs4 import BeautifulSoup

CURRENCY_ALIASES = {"RON": "RON", "LEI": "RON", "LEU": "RON", "EUR": "EUR", "€": "EUR", "EURO": "EUR"}


@dataclass
class PageResult:
    """What an adapter found on a page."""

    title: str
    price: Decimal
    currency: str | None  # "RON", "EUR", or None when the page didn't say
    available: bool = True


def normalize_currency(code):
    if not code:
        return None
    return CURRENCY_ALIASES.get(str(code).strip().upper())


def parse_machine_price(value):
    """Parse a structured-data price such as "2499.99" (dot for decimals)."""
    try:
        amount = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None
    return amount if amount > 0 else None


def _walk(node):
    """Yield every dict inside a JSON structure, however deeply nested."""
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk(item)


class SiteAdapter:
    """Base class: one subclass per supported website."""

    name = ""
    domains = ()
    default_currency = None
    default_period = "one_time"

    def handles(self, host):
        host = host.lower()
        return any(host == domain or host.endswith("." + domain) for domain in self.domains)

    def extract(self, html):
        """Return a PageResult, or None if no price could be read."""
        soup = BeautifulSoup(html, "html.parser")
        result = self._from_structured_data(soup) or self._from_meta_tags(soup)
        if result and not result.title:
            result.title = self._page_title(soup)
        return result

    def _from_structured_data(self, soup):
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
            except json.JSONDecodeError:
                continue
            title = ""
            for node in _walk(data):
                if not title and isinstance(node.get("name"), str) and "offers" in node:
                    title = node["name"].strip()
                amount = parse_machine_price(node.get("price", node.get("lowPrice")))
                if amount is None:
                    continue
                availability = str(node.get("availability", ""))
                return PageResult(
                    title=title,
                    price=amount,
                    currency=normalize_currency(node.get("priceCurrency")),
                    available="OutOfStock" not in availability and "SoldOut" not in availability,
                )
        return None

    def _from_meta_tags(self, soup):
        amount = parse_machine_price(self._meta(soup, "product:price:amount", "og:price:amount"))
        if amount is None:
            return None
        currency = self._meta(soup, "product:price:currency", "og:price:currency")
        return PageResult(title="", price=amount, currency=normalize_currency(currency))

    def _page_title(self, soup):
        og_title = self._meta(soup, "og:title")
        if og_title:
            return og_title.strip()
        if soup.title and soup.title.string:
            return soup.title.string.strip()
        return ""

    @staticmethod
    def _meta(soup, *names):
        for name in names:
            tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
            if tag and tag.get("content"):
                return tag["content"]
        return None
