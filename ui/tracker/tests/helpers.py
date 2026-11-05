"""Shared test helpers: fixture pages and a fake internet for offline tests."""

from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"

ALLOW_ALL_ROBOTS = (200, "User-agent: *\nAllow: /")


def fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


class FakeInternet:
    """Stands in for tracker.checks.http_get. Maps URL -> (status, text) or an exception.

    robots.txt answers "allow everything" unless a test sets it. Every requested URL
    is remembered in .requested, so tests can assert what was (not) fetched.
    """

    def __init__(self, pages=None):
        self.pages = dict(pages or {})
        self.requested = []

    def __call__(self, url):
        self.requested.append(url)
        if url.endswith("/robots.txt") and url not in self.pages:
            return ALLOW_ALL_ROBOTS
        response = self.pages.get(url, (404, "not found"))
        if isinstance(response, Exception):
            raise response
        return response
