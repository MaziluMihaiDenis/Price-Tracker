"""Site adapters: each one knows how to read the price from one website.

To support a new site, add a SiteAdapter subclass and list it in ADAPTERS.
"""

from urllib.parse import urlsplit, urlunsplit

from tracker.adapters.emag import EmagAdapter
from tracker.adapters.storia import StoriaAdapter

ADAPTERS = (EmagAdapter(), StoriaAdapter())


def adapter_for(url):
    """Return the adapter for this URL's website, or None if the site isn't supported."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    for adapter in ADAPTERS:
        if adapter.handles(parts.hostname):
            return adapter
    return None


def clean_url(url):
    """Drop tracking parameters and fragments ("?ref=...", "#..."): the page is the same."""
    parts = urlsplit(url.strip())
    return urlunsplit((parts.scheme, parts.netloc.lower(), parts.path, "", ""))


def supported_site_names():
    return ", ".join(adapter.name for adapter in ADAPTERS)
