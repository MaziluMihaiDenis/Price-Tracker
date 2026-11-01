# Scraping spike (throwaway)

**This folder is not part of the Price Tracker app.** It is a one-off experiment for
Milestone 1 that answers one question: *which sites can a program reliably read prices
from?* The plan is in [docs/features/milestone-1-scraping-spike.md](../../docs/features/milestone-1-scraping-spike.md)
and the findings go in `docs/spikes/scraping-results.md`.

## Setup (Windows, run from this folder)

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m playwright install chromium   # only for round 2
```

## Cleaning up afterwards

- Delete `.venv/` in this folder to remove the Python packages.
- Playwright's browsers live **outside this project**, in
  `C:\Users\<you>\AppData\Local\ms-playwright` (about 720 MB). Delete that folder too,
  unless another project uses Playwright.

## Files

| File | What it is |
|---|---|
| `urls.csv` | The pages to test: site, URL, and the price your browser shows |
| `extract.py` | Price parser and the extraction methods |
| `test_extract.py` | Automated tests for the price parser |
| `spike.py` | The main script |
| `results/` | One CSV of results per run (committed) |
| `pages/` | Saved copies of downloaded pages (**never committed**, may contain personal data) |

## Running

```bash
.venv/Scripts/python -m unittest test_extract   # run the tests
.venv/Scripts/python spike.py                   # round 1: simple download
.venv/Scripts/python spike.py --browser         # round 2: Playwright, failed pages only
.venv/Scripts/python spike.py --reprocess       # re-analyse today's saved pages, no downloads
```

## Rules this spike follows

- Checks each site's `robots.txt` and skips disallowed pages.
- One request per page, about 5 seconds apart, never in parallel.
- No CAPTCHA solving, proxies or "stealth" tricks: if a site blocks us, that is the result.
