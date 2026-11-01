"""Scraping spike: try to read title, price and currency from each page in urls.csv.

Round 1 (simple download with httpx):   python spike.py
Round 2 (hidden browser, failed pages): python spike.py --browser

Each run writes results/run-YYYY-MM-DD[-browser].csv and saves page copies in pages/.
"""

import argparse
import csv
import time
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from extract import extract, parse_price

HERE = Path(__file__).parent
URLS_FILE = HERE / "urls.csv"
PAGES_DIR = HERE / "pages"
RESULTS_DIR = HERE / "results"

TIMEOUT_SECONDS = 20
PAUSE_SECONDS = 5
# Ordinary browser headers: we look like a normal visit, nothing more.
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/141.0 Safari/537.36"),
    "Accept-Language": "ro-RO,ro;q=0.9,en;q=0.8",
}
# Text that suggests a bot-protection page instead of the real one.
BLOCK_MARKERS = ("captcha", "are you a robot", "just a moment", "access denied")
BLOCK_PAGE_MAX_SIZE = 50_000  # characters
# Text that suggests a removed listing.
REMOVED_MARKERS = ("anunț inactiv", "anunt inactiv", "nu mai este disponibil", "anunțul nu mai")

RESULT_COLUMNS = [
    "run_date", "method", "site", "url", "final_url", "http_status", "outcome",
    "title", "price", "currency", "extracted_by", "availability",
    "browser_price", "auto_match", "checked_by_you", "notes",
]


def polite_pause():
    """Wait between requests so we never hammer a site."""
    time.sleep(PAUSE_SECONDS)


def load_urls():
    """Read urls.csv into a list of dicts with keys site, url, browser_price."""
    with open(URLS_FILE, encoding="utf-8", newline="") as file:
        return [row for row in csv.DictReader(file) if row.get("url")]


def robots_for(site_root, fetch, cache):
    """Fetch and parse robots.txt once per site. Returns a parser, or None if unreachable.

    Uses the same fetch function as the pages, so the browser round reads robots.txt
    through the browser too. Following Google's convention: a missing robots.txt (404)
    allows everything, while an unreachable one means we don't fetch the site at all.
    """
    if site_root in cache:
        return cache[site_root]
    parser = RobotFileParser()
    try:
        status, _, text = fetch(f"{site_root}/robots.txt")
        if status >= 500 or status == 0:
            parser = None
        elif status >= 400:
            parser.allow_all = True
        else:
            # A browser wraps plain text in HTML; get_text() strips that back off.
            if "<pre" in text[:500].lower():
                from bs4 import BeautifulSoup
                text = BeautifulSoup(text, "html.parser").get_text()
            parser.parse(text.splitlines())
    except Exception:  # timeouts, connection resets, browser errors
        parser = None
    cache[site_root] = parser
    polite_pause()
    return parser


def fetch_simple(url, client):
    """Round 1: download with httpx. Returns (status, final_url, html)."""
    response = client.get(url)
    return response.status_code, str(response.url), response.text


def fetch_browser(url, page):
    """Round 2: open the page in a hidden Chromium browser. Returns (status, final_url, html)."""
    response = page.goto(url, timeout=TIMEOUT_SECONDS * 1000, wait_until="domcontentloaded")
    # Give scripts a moment to put the price on the page.
    page.wait_for_timeout(3000)
    status = response.status if response else 0
    return status, page.url, page.content()


def classify(status, html):
    """Decide whether a page looks blocked, removed, or fine."""
    lowered = html.lower()
    # Real pages mention "captcha" in their scripts too, so the text markers only
    # count on small pages: block pages are a few KB, product pages hundreds of KB.
    looks_like_block_page = len(html) < BLOCK_PAGE_MAX_SIZE and any(
        marker in lowered for marker in BLOCK_MARKERS)
    if status in (403, 429, 503) or looks_like_block_page:
        return "blocked"
    if status in (404, 410) or any(marker in lowered for marker in REMOVED_MARKERS):
        return "removed"
    if status >= 400:
        return "error"
    if len(html) < 500:
        return "empty"
    return "ok"


def auto_match(result, browser_price):
    """Compare our price with the one typed in urls.csv. You still confirm by hand."""
    expected = parse_price(browser_price)
    if not result or not expected:
        return ""
    return "yes" if (result["price"], result["currency"]) == expected else "no"


def save_page(html, site, number, method):
    """Save a copy of the page for later tests. pages/ is ignored by Git."""
    PAGES_DIR.mkdir(exist_ok=True)
    path = PAGES_DIR / f"{date.today()}_{site}_{number}_{method}.html"
    path.write_text(html, encoding="utf-8")


def latest_failures():
    """Rows from the newest round-1 results file that did not get a price."""
    files = sorted(f for f in RESULTS_DIR.glob("run-*.csv") if "browser" not in f.name)
    if not files:
        raise SystemExit("No round-1 results yet: run `python spike.py` first.")
    with open(files[-1], encoding="utf-8", newline="") as file:
        failed = {row["url"] for row in csv.DictReader(file) if not row["price"]}
    print(f"Using {files[-1].name}: {len(failed)} failed page(s).")
    return failed


def check_page(row, number, method, fetch, robots):
    """Run every step for one page and return one results row."""
    site, url = row["site"], row["url"]
    out = {column: "" for column in RESULT_COLUMNS}
    out.update(run_date=str(date.today()), method=method, site=site, url=url,
               browser_price=row.get("browser_price", ""))

    if robots is None:
        out.update(outcome="robots-unreachable", notes="robots.txt could not be fetched")
        return out
    if not robots.can_fetch("*", url):
        out.update(outcome="skipped-robots", notes="disallowed by robots.txt")
        return out

    try:
        status, final_url, html = fetch(url)
    except Exception as error:  # timeouts, connection resets, browser errors
        out.update(outcome="error", notes=f"{type(error).__name__}: {error}"[:200])
        return out

    save_page(html, site, number, method)
    return analyse(out, status, final_url, html)


def analyse(out, status, final_url, html):
    """Classify a downloaded page and extract its price into the results row."""
    out.update(http_status=status, final_url=final_url, outcome=classify(status, html))
    if final_url.rstrip("/") != out["url"].rstrip("/"):
        out["notes"] = "redirected"

    result = extract(html, out["site"]) if out["outcome"] == "ok" else None
    if result:
        out.update(title=result["title"] or "", price=result["price"],
                   currency=result["currency"] or "unclear",
                   extracted_by=result["extracted_by"], availability=result["availability"])
    elif out["outcome"] == "ok":
        out["outcome"] = "no-price"
    out["auto_match"] = auto_match(result, out["browser_price"])
    return out


def run(use_browser):
    rows = load_urls()
    if use_browser:
        failed = latest_failures()
        rows = [row for row in rows if row["url"] in failed]
    method = "browser" if use_browser else "simple"
    results = []
    robots_cache = {}
    per_site_count = {}

    with httpx.Client(headers=HEADERS, timeout=TIMEOUT_SECONDS, follow_redirects=True) as client:
        browser = page = None
        if use_browser:
            from playwright.sync_api import sync_playwright  # only installed for round 2
            playwright = sync_playwright().start()
            browser = playwright.chromium.launch()
            page = browser.new_page(user_agent=HEADERS["User-Agent"], locale="ro-RO")
            fetch = lambda url: fetch_browser(url, page)
        else:
            fetch = lambda url: fetch_simple(url, client)

        try:
            for row in rows:
                per_site_count[row["site"]] = per_site_count.get(row["site"], 0) + 1
                parts = urlsplit(row["url"])
                robots = robots_for(f"{parts.scheme}://{parts.netloc}", fetch, robots_cache)
                result = check_page(row, per_site_count[row["site"]], method, fetch, robots)
                results.append(result)
                print(f"{result['site']:<12} {result['outcome']:<18} "
                      f"{result['price']} {result['currency']}  {result['notes']}")
                polite_pause()
        finally:
            if browser:
                browser.close()
                playwright.stop()

    write_results(results, use_browser)


def results_file(use_browser):
    suffix = "-browser" if use_browser else ""
    return RESULTS_DIR / f"run-{date.today()}{suffix}.csv"


def write_results(results, use_browser):
    RESULTS_DIR.mkdir(exist_ok=True)
    out_file = results_file(use_browser)
    with open(out_file, "w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=RESULT_COLUMNS)
        writer.writeheader()
        writer.writerows(results)
    print(f"\nSaved {len(results)} result(s) to {out_file.relative_to(HERE)}")


def reprocess(use_browser):
    """Re-analyse today's saved pages without downloading anything again.

    Useful after fixing a bug in classify() or extract(), to avoid extra requests.
    """
    with open(results_file(use_browser), encoding="utf-8", newline="") as file:
        old_rows = list(csv.DictReader(file))
    method = "browser" if use_browser else "simple"
    per_site_count = {}
    results = []
    for row in old_rows:
        per_site_count[row["site"]] = per_site_count.get(row["site"], 0) + 1
        page_file = PAGES_DIR / f"{date.today()}_{row['site']}_{per_site_count[row['site']]}_{method}.html"
        if not row["http_status"] or not page_file.exists():
            results.append(row)  # never downloaded (robots, error): keep as it was
            continue
        out = {column: "" for column in RESULT_COLUMNS}
        out.update({key: row[key] for key in ("run_date", "method", "site", "url", "browser_price")})
        html = page_file.read_text(encoding="utf-8")
        results.append(analyse(out, int(row["http_status"]), row["final_url"], html))
        print(f"{out['site']:<12} {out['outcome']:<18} {out['price']} {out['currency']}")
    write_results(results, use_browser)


if __name__ == "__main__":
    arguments = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    arguments.add_argument("--browser", action="store_true",
                           help="use Playwright for pages that failed round 1")
    arguments.add_argument("--reprocess", action="store_true",
                           help="re-analyse today's saved pages instead of downloading")
    options = arguments.parse_args()
    if options.reprocess:
        reprocess(options.browser)
    else:
        run(options.browser)
