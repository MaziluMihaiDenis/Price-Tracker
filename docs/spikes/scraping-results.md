# Scraping Spike: Results (Milestone 1)

*Runs: 2026-11-01 (day 1) and 2026-11-05 (day 2). Plan: [docs/features/milestone-1-scraping-spike.md](../features/milestone-1-scraping-spike.md).*
*Raw data: `spikes/scraping/results/` (4 CSV files). Saved pages: `spikes/scraping/pages/` (local only, not in Git).*

## Summary

| Site | Simple method (httpx) | Browser (Playwright) | Correct on both days? | Classification |
|---|---|---|---|---|
| **eMAG** | ✅ 2/2 pages, structured data | not needed | Yes (4/4) | **Works**, but its terms forbid automated extraction (see below) |
| **Storia** | ✅ 3/3 pages, structured data | not needed | Yes (6/6) | **Works** |
| **OLX** | ❌ 403 "Request blocked" | Loads, but the price is converted to RON | No: original currency lost | **Unclear** |
| **Altex** | ❌ 403 "Access Denied" | ❌ connection refused (`ERR_HTTP2_PROTOCOL_ERROR`) | – | **Blocked** |
| **imobiliare.ro** | ❌ 403 Cloudflare "Attention Required" | ❌ 403 Cloudflare | – | **Blocked** |

**Technical winners:** eMAG (shop) and Storia (property). Both work with the simplest, most robust method: structured data read with a plain download.

**Decision (2026-11-05): eMAG + Storia** for the MVP, accepting eMAG's terms-of-use risk for personal use (see "Decision for the MVP" below).

## Results per page

### Day 1 (2026-11-01)

| Site | Page | Your browser | Extracted | Method | Match |
|---|---|---|---|---|---|
| eMAG | CeraVe cleansing gel 976 ml | 89.49 LEI | 89.49 RON | structured | ✅ |
| eMAG | CeraVe moisturising lotion 976 ml | 194.40 LEI | 194.4 RON | structured | ✅ |
| Storia | Studio, Grozăvești | 460 €/month | 460 EUR | structured | ✅ |
| Storia | Studio, Kogălniceanu | 399 €/month | 399 EUR | structured | ✅ |
| Storia | Studio, Drumul Taberei | 390 €/month | 390 EUR | structured | ✅ |
| OLX | Studio, Drumul Taberei | 400 € | 2142 RON (browser round) | structured | ❌ |
| Altex | PS5 Slim / Logitech G413 | 3699.90 / 279.00 lei | – | – | blocked |
| imobiliare.ro | Studio, Grozăvești / Politehnica | 400 / 450 €/month | – | – | blocked |

### Day 2 (2026-11-05)

| Site | Page | Visible on the page | Extracted | Change since day 1 |
|---|---|---|---|---|
| eMAG | CeraVe cleansing gel | 119,99 Lei | 119.99 RON | ↑ +34% |
| eMAG | CeraVe lotion | 189,92 Lei | 189.92 RON | ↓ −2.3% |
| Storia | Studio, Grozăvești | 550 € | 550 EUR | ↑ +20% |
| Storia | Studio, Kogălniceanu | 399 € | 399 EUR | = |
| Storia | Studio, Drumul Taberei | 380 € | 380 EUR | ↓ −2.6% |
| OLX | Studio, Drumul Taberei | 400 € | 2134 RON (browser round) | Fake change: rent unchanged, RON value moved |
| Altex, imobiliare.ro | – | – | blocked again | – |

Day-2 prices were checked against the **price visible on the saved page**, not against a browser. The CSV's `auto_match` column says "no" for changed prices because it compares with the day-1 browser prices.

## Findings

1. **Structured data is reliable where it exists.** On eMAG and Storia it gave the correct title, price and currency on all 10 page loads, including when prices changed. This is the method Milestone 6 adapters should use first.
2. **Prices really do move.** In 4 days, 4 of 5 tracked prices changed, some by 20–34%. That's good evidence the app is worth building.
3. **OLX's structured data converts the price to RON.** The rent shown as 400 € appears as 2142 RON on day 1 and 2134 RON on day 2, so OLX applies its own daily exchange rate (about 5.335–5.355). Reading this value would create **fake price trends**. If OLX is ever supported, the adapter must read the visible price (`[data-testid=ad-price-container]`, "400 €") instead.
4. **Three sites actively block automated visitors.** Altex (Akamai-style "Access Denied", then a refused browser connection), imobiliare.ro (Cloudflare) and OLX (a CloudFront "Request blocked" page) block simple requests. We didn't try to get around these blocks, as the plan requires.
5. **Bot-protection words appear on normal pages.** eMAG and Storia load reCAPTCHA scripts, so "captcha" in a page doesn't mean it's blocked. The fixed check only treats such words as a block on small pages (< 50 KB); real block pages were 0.5–6 KB.

## Terms of use (skimmed 2026-11-05, not legal advice)

- **eMAG:** its "Termene si conditii" ([emag.ro/info/termeni-si-conditii](https://www.emag.ro/info/termeni-si-conditii)) lists among forbidden uses, in point *j*, using any robot, algorithm or other automated means to extract data from the site. **Automatic tracking of eMAG would go against its terms**, even for low-volume personal use.
- **Storia:** the "Condiții de utilizare aplicabile utilizatorilor privați" (on help.storia.ro, published by OLX) had **no clause about robots, scraping, crawling or automated data extraction** in a keyword search. Absence in a keyword search isn't permission. Re-check before going public, and stay low-volume.
- **Altex, OLX, imobiliare.ro:** not checked. They block automated access technically, which already rules them out.

## Decision for the MVP

**Chosen on 2026-11-05: eMAG + Storia (option B).** The owner chose to proceed with eMAG despite its terms, because the app is for personal use only. Keep the volume low (one check per item per day), and **re-evaluate eMAG before any public release**.

The options that were considered:

| Option | What it means | Trade-off |
|---|---|---|
| **A. Storia automatic + shops manual** *(recommended)* | MVP automatic tracking supports Storia only. Shop products use manual entry, which the plan already includes. | Respects every site's terms. Less automation for shopping, but the adapter design still makes adding a shop later a small, separate job. |
| B. eMAG + Storia as planned | Build both adapters | Technically easiest, but knowingly breaks eMAG's terms, which is riskier still if the app goes public |
| C. Storia + look for another shop | Find a shop whose terms allow it, or one that offers an official product feed or API | More research first. An eMAG affiliate or partner feed **may** exist, but that's not verified. |

## Limitations of this spike

- Few pages: 2 per site, and **only 1 for OLX**.
- Python's built-in `robots.txt` reader ignores `*` wildcards in rules. That didn't matter here, because all tested URLs were plain paths without query strings (tracking parameters were removed from `urls.csv`), but the real app should use a reader that supports wildcards.
- Results were gathered from one home connection on two days. Sites can change their protection at any time.
- The terms of use were skimmed with keyword searches, not read in full.
