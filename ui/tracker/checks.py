"""Automatic price checks: download a supported page, read its price, record the result.

check_item() is the single entry point for "check this item now". It contains no
web-request code, so a scheduled daily job (Milestone 7) can call it too.
"""

from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from django.db import transaction
from django.utils import timezone

from tracker.adapters import adapter_for
from tracker.adapters.base import PageResult
from tracker.models import CheckAttempt, Item, PricePoint

TIMEOUT_SECONDS = 20
MAX_REDIRECTS = 5
CHECK_COOLDOWN = timedelta(minutes=10)
# Ordinary browser headers: we look like a normal visit, nothing more.
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/141.0 Safari/537.36"),
    "Accept-Language": "ro-RO,ro;q=0.9,en;q=0.8",
}
# Normal pages mention "captcha" in their scripts too, so these words only count on
# small pages: block pages are a few KB, product pages hundreds of KB (spike finding).
BLOCK_MARKERS = ("captcha", "are you a robot", "just a moment", "access denied")
BLOCK_PAGE_MAX_SIZE = 50_000
REMOVED_MARKERS = ("anunț inactiv", "anunt inactiv", "nu mai este disponibil", "anunțul nu mai")


class UnsafeRedirect(Exception):
    """A supported page redirected to a site we don't support."""


class RobotsUnavailable(Exception):
    """The site's robots.txt could not be read (server error)."""


@dataclass
class ReadResult:
    outcome: str  # one of CheckAttempt.Outcome values
    message: str
    page: PageResult | None = None


@dataclass
class CheckResult:
    outcome: str
    message: str
    price_point: PricePoint | None = None


def http_get(url):
    """Download a URL and return (status code, text).

    Redirects are followed by hand so that every hop stays on a supported site.
    Tests replace this function, so they never touch the internet.
    """
    with httpx.Client(headers=HEADERS, timeout=TIMEOUT_SECONDS, follow_redirects=False) as client:
        for _ in range(MAX_REDIRECTS + 1):
            response = client.get(url)
            if not response.is_redirect:
                return response.status_code, response.text
            url = urljoin(url, response.headers.get("location", ""))
            if adapter_for(url) is None:
                raise UnsafeRedirect(url)
    raise UnsafeRedirect("too many redirects")


def robots_allows(url):
    """Check the site's robots.txt. A missing file (4xx) allows everything."""
    parts = urlsplit(url)
    status, text = http_get(f"{parts.scheme}://{parts.netloc}/robots.txt")
    if status >= 500:
        raise RobotsUnavailable(status)
    if status >= 400:
        return True
    parser = RobotFileParser()
    parser.parse(text.splitlines())
    return parser.can_fetch("*", url)


def classify(status, html):
    lowered = html.lower()
    looks_like_block_page = len(html) < BLOCK_PAGE_MAX_SIZE and any(
        marker in lowered for marker in BLOCK_MARKERS)
    # 503 is "temporarily unavailable" (e.g. eMAG's Black Friday holding page), not a block.
    if status in (403, 429) or (status != 503 and looks_like_block_page):
        return CheckAttempt.Outcome.BLOCKED
    if status in (404, 410) or any(marker in lowered for marker in REMOVED_MARKERS):
        return CheckAttempt.Outcome.REMOVED
    if status >= 400:
        return CheckAttempt.Outcome.ERROR
    return CheckAttempt.Outcome.OK


def read_page(url):
    """Fetch one supported page and read its price. Never raises for network problems."""
    Outcome = CheckAttempt.Outcome
    adapter = adapter_for(url)
    if adapter is None:
        return ReadResult(Outcome.ERROR, "This site isn't supported for automatic tracking.")
    try:
        if not robots_allows(url):
            return ReadResult(Outcome.ERROR, "The site's robots.txt asks automated visitors not to read this page.")
        status, html = http_get(url)
    except httpx.TimeoutException:
        return ReadResult(Outcome.ERROR, f"{adapter.name} didn't respond in time. Try again later.")
    except (httpx.HTTPError, RobotsUnavailable):
        return ReadResult(Outcome.ERROR, f"Couldn't connect to {adapter.name}. Check your internet connection.")
    except UnsafeRedirect:
        return ReadResult(Outcome.ERROR, "The page redirected to a site that isn't supported.")

    outcome = classify(status, html)
    if outcome == Outcome.BLOCKED:
        return ReadResult(outcome, f"{adapter.name} refused the automated visit (HTTP {status}).")
    if outcome == Outcome.REMOVED:
        return ReadResult(outcome, "This listing is no longer available.")
    if outcome == Outcome.ERROR:
        if status == 503:
            return ReadResult(outcome, f"{adapter.name} is temporarily unavailable (HTTP 503). Try again later.")
        return ReadResult(outcome, f"{adapter.name} returned an error (HTTP {status}).")

    page = adapter.extract(html)
    if page is None:
        return ReadResult(Outcome.ERROR, "Couldn't read the price on this page.")
    message = ""
    if page.currency is None:
        page.currency = adapter.default_currency
        message = f"The page didn't state a currency; assumed {page.currency}."
    return ReadResult(Outcome.OK, message, page)


def seconds_until_next_check(item, now=None):
    """0 if the item may be checked now, else how many seconds to wait."""
    if item.last_checked is None:
        return 0
    remaining = item.last_checked + CHECK_COOLDOWN - (now or timezone.now())
    return max(0, int(remaining.total_seconds()))


def can_be_checked(item):
    return (item.source == Item.Source.AUTOMATIC and bool(item.url)
            and item.status not in (Item.Status.PAUSED, Item.Status.REMOVED))


def _needs_new_point(latest, page, now):
    """Add a point when the price changed, or the latest one is from an earlier day."""
    if latest is None:
        return True
    if (latest.amount, latest.currency) != (page.price, page.currency):
        return True
    return timezone.localdate(latest.recorded_at) != timezone.localdate(now)


def _record(item, outcome, message, now, run=None):
    item.last_checked = now
    item.save(update_fields=["status", "last_error", "last_checked", "updated_at"])
    CheckAttempt.objects.create(item=item, run=run, attempted_at=now, outcome=outcome, message=message[:240])


@transaction.atomic
def start_tracking(item, page, now=None):
    """Save a new automatic item with the price read during the preview."""
    now = now or timezone.now()
    item.source = Item.Source.AUTOMATIC
    item.status = Item.Status.ACTIVE
    item.last_error = ""
    item.save()
    point = PricePoint.objects.create(item=item, amount=page.price, currency=page.currency,
                                      recorded_at=now, source=PricePoint.Source.AUTOMATIC)
    _record(item, CheckAttempt.Outcome.OK, "First price read when the item was added.", now)
    return point


def check_item(item, now=None, run=None):
    """Check one automatic item: read today's price and update its status and history.

    `run` is the daily CheckRun this check belongs to, or None for a manual "Check now".
    """
    Outcome = CheckAttempt.Outcome
    if not can_be_checked(item):
        return CheckResult("skipped", "This item isn't checked automatically.")
    now = now or timezone.now()
    result = read_page(item.url)

    with transaction.atomic():
        if result.outcome != Outcome.OK:
            item.status = Item.Status.REMOVED if result.outcome == Outcome.REMOVED else Item.Status.ERROR
            item.last_error = result.message[:240]
            _record(item, result.outcome, result.message, now, run)
            return CheckResult(result.outcome, result.message)

        page = result.page
        latest = item.price_points.order_by("-recorded_at", "-id").first()
        point = None
        if _needs_new_point(latest, page, now):
            point = PricePoint.objects.create(item=item, amount=page.price, currency=page.currency,
                                              recorded_at=now, source=PricePoint.Source.AUTOMATIC)
        if latest and (latest.amount, latest.currency) != (page.price, page.currency):
            message = f"New price: {page.price} {page.currency} (was {latest.amount} {latest.currency})."
        else:
            message = f"Price unchanged: {page.price} {page.currency}."
        if result.message:
            message = f"{message} {result.message}"
        item.status = Item.Status.ACTIVE
        item.last_error = ""
        _record(item, Outcome.OK, message, now, run)
    return CheckResult(Outcome.OK, message, point)
