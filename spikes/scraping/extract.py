"""Price parsing and extraction for the scraping spike (throwaway code).

Three extraction methods are tried in order, from most to least robust:
  1. structured data - JSON-LD blocks (<script type="application/ld+json">)
  2. meta tags       - e.g. <meta property="product:price:amount" content="...">
  3. html            - a hand-written CSS selector per site (SITE_RULES)
"""

import json
import re
from decimal import Decimal, InvalidOperation

from bs4 import BeautifulSoup

# Words and symbols that identify each currency, in lowercase.
CURRENCY_WORDS = {
    "RON": ("lei", "ron", "leu"),
    "EUR": ("€", "eur", "euro"),
}

# Site-specific CSS selectors for method 3. Filled in during run 1 (task 7),
# only for sites where methods 1 and 2 found nothing.
SITE_RULES = {}

# A number as people write it: starts with a digit, may contain . , and spaces.
NUMBER_PATTERN = re.compile(r"\d[\d.,\s ]*")


def detect_currency(text):
    """Return "RON", "EUR" or None from free text like "2.499,99 lei"."""
    lowered = text.lower()
    for code, words in CURRENCY_WORDS.items():
        for word in words:
            # Symbols match anywhere; words must stand alone ("lei", not "leipzig").
            if word == "€" and word in lowered:
                return code
            if re.search(rf"\b{re.escape(word)}\b", lowered):
                return code
    return None


def normalize_currency(code):
    """Turn a machine currency code like "RON" or "lei" into "RON"/"EUR", else None."""
    if not code:
        return None
    return detect_currency(str(code))


def parse_number(raw):
    """Turn a human-written number into a Decimal, understanding Romanian format.

    "2.499,99" -> 2499.99   "85.000" -> 85000   "1 250" -> 1250   "12.5" -> 12.5
    """
    cleaned = raw.replace(" ", "").replace(" ", "").strip(".,")
    if not cleaned:
        return None
    if "." in cleaned and "," in cleaned:
        # Both present: whichever comes last is the decimal separator.
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        # Only commas: "450,50" is decimal, "1,250" is thousands.
        parts = cleaned.split(",")
        if len(parts) == 2 and len(parts[1]) in (1, 2):
            cleaned = cleaned.replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "." in cleaned:
        # Only dots: groups of exactly 3 digits mean thousands ("85.000").
        parts = cleaned.split(".")
        if all(len(part) == 3 for part in parts[1:]):
            cleaned = cleaned.replace(".", "")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def parse_price(text):
    """Parse visible price text like "2.499,99 lei" into (Decimal, currency).

    Returns None when there is no usable positive price ("Preț la cerere", "0 lei").
    The currency is "RON", "EUR" or None ("unclear").
    """
    if not text:
        return None
    match = NUMBER_PATTERN.search(text)
    if not match:
        return None
    amount = parse_number(match.group())
    if amount is None or amount <= 0:
        return None
    return amount, detect_currency(text)


def parse_machine_price(value):
    """Parse a price from structured data, which uses a dot for decimals ("2499.99")."""
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


def extract_structured(soup):
    """Method 1: look for a price in JSON-LD blocks. Returns a result dict or None."""
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except json.JSONDecodeError:
            continue
        name = None
        for node in _walk(data):
            if name is None and isinstance(node.get("name"), str) and "offers" in node:
                name = node["name"]
            raw = node.get("price", node.get("lowPrice"))
            if raw is None:
                continue
            amount = parse_machine_price(raw)
            if amount is None:
                continue
            availability = str(node.get("availability", "")).rsplit("/", 1)[-1]
            return {
                "title": name,
                "price": amount,
                "currency": normalize_currency(node.get("priceCurrency")),
                "availability": availability,
                "extracted_by": "structured",
            }
    return None


def _meta_content(soup, *names):
    """Return the content of the first <meta> tag matching any property/name/itemprop."""
    for name in names:
        tag = (soup.find("meta", attrs={"property": name})
               or soup.find("meta", attrs={"name": name})
               or soup.find(attrs={"itemprop": name}))
        if tag and tag.get("content"):
            return tag["content"]
    return None


def extract_meta(soup):
    """Method 2: look for price meta tags (Open Graph or microdata)."""
    raw = _meta_content(soup, "product:price:amount", "og:price:amount", "price")
    if raw is None:
        return None
    amount = parse_machine_price(raw)
    if amount is None:
        return None
    currency = _meta_content(soup, "product:price:currency", "og:price:currency", "priceCurrency")
    return {
        "title": None,
        "price": amount,
        "currency": normalize_currency(currency),
        "availability": "",
        "extracted_by": "meta",
    }


def extract_html(soup, site):
    """Method 3: use the hand-written CSS selector for this site, if there is one."""
    selector = SITE_RULES.get(site)
    if not selector:
        return None
    element = soup.select_one(selector)
    if element is None:
        return None
    parsed = parse_price(element.get_text(" ", strip=True))
    if parsed is None:
        return None
    amount, currency = parsed
    return {
        "title": None,
        "price": amount,
        "currency": currency,
        "availability": "",
        "extracted_by": "html",
    }


def page_title(soup):
    """Best-effort page title: og:title first, then <title>."""
    og_title = _meta_content(soup, "og:title")
    if og_title:
        return og_title.strip()
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    return None


def extract(html, site):
    """Try all three methods in order. Returns a result dict, or None if all fail."""
    soup = BeautifulSoup(html, "html.parser")
    for method in (extract_structured, extract_meta):
        result = method(soup)
        if result:
            break
    else:
        result = extract_html(soup, site)
    if result and not result["title"]:
        result["title"] = page_title(soup)
    return result
