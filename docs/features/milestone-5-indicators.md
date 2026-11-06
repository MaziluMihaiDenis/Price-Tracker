# Feature Plan: Milestone 5, History and Indicators

*Status: approved on 2026-11-06. Planning only: no code has been written yet.*
*Parent plan: [docs/PROJECT_PLAN.md](../PROJECT_PLAN.md), milestone 5. Builds on the currency conversion from [milestone 4](milestone-4-currencies.md).*

Facts are labelled **Verified** (checked on 2026-11-06), **Estimate** or **Assumption**.

---

## 1. Feature summary and user story

Price change arrows ("↓ 7.7%") on the dashboard, item list and item page; a "Lowest ever" badge; lowest and highest prices (with dates) on the item page; and a "Price changes" panel on the dashboard listing this week's changes.

*As a household member, I want to see at a glance whether each price went up or down, and whether it's the lowest I've seen, so I know when it's a good moment to buy or renegotiate.*

## 2. Problem, outcome and scope

Today the app shows the current price but not whether it moved. Daily checks also store an unchanged price every day, so the "last change" is often further back than the two newest prices.

**In scope**
- Change arrow: current price vs the **previous different price**, measured in the price's **own currency**.
- "Lowest ever" badge (only once the item has had at least 2 different prices).
- Item page: "was … until …" line, plus "Lowest … on … · Highest … on …" (shown in the viewer's currency, original underneath).
- Dashboard "Price changes" panel: changes in the last 7 days, biggest % first, max 6. It replaces the decorative "A clearer picture, over time" placeholder card.

**Out of scope:** indicators on comparison pages (M8), alerts/notifications, sorting or filtering by change, "Highest ever" badges in lists, any database change.

## 3. Requirements and acceptance criteria

**Rules**
- Change = latest price vs the most recent earlier price that was different. Same currency → amounts compared directly. Different currencies → both converted to RON, each at its own date's BNR rate; a missing rate → no indicator.
- Percent = (new − old) ÷ old × 100, rounded to 1 decimal (half up), ".0" dropped: ↓ 7.7%, ↑ 12%, ↓ 0.4%.
- A drop is green ↓, a rise is orange-red ↑. The arrow and the word "down"/"up" (screen readers) are always present: meaning never relies on colour alone.
- "Since" = the day the current price **first** appeared (3 Nov change, unchanged checks on 4–5 Nov → since 3 Nov).
- No indicator with only one price, or when the price never changed.
- "Lowest ever": current price equals the lowest recorded price, and the item has had at least 2 different prices.
- Lowest/highest ties: the **first** date the price appeared is shown.
- Dates are Europe/Bucharest local dates, like the rest of the app.
- The arrow sits beside the price in the same cell (no new table column).
- Each user only ever sees their own items.

**Non-functional:** at most one extra database query per page for price histories, regardless of item count; works offline; follows the existing look.

**Acceptance criteria**
1. Given prices 129.99 then 119.99 RON, the item list shows **↓ 7.7%** in green.
2. Given 100, 100, 100, then 110, it shows **↑ 10%**.
3. Given one price, or a price that never changed, no arrow and no "Lowest ever" badge appear.
4. Given 470 EUR rent every month, viewed in RON, no arrow appears even though the euro rate moved.
5. Given 500 RON then 100 EUR, the change is computed in RON at each date's rate; with a missing rate, no arrow appears and the page still works.
6. Given 120, 110, 115, 110, "Lowest ever" shows; given 120, 110, 115, it doesn't.
7. A change 3 days ago appears in "Price changes"; a change 10 days ago doesn't; the bigger % change is listed first.
8. With two users, neither sees the other's items in the panel.
9. The item page shows lowest and highest with their dates, in the viewer's currency.
10. The full test suite passes, and the dashboard and item list use at most one extra query for prices, the same with 1 item or 10.

## 4. Current architecture (Verified)

| What | Where | Relevance |
|---|---|---|
| Item, PricePoint models | `ui/tracker/models.py` | All data needed; no schema change |
| `_items_for()` prefetches only the 2 newest prices | `ui/tracker/views.py` | Not enough for "previous different" or "lowest ever" |
| Dashboard, item list, item page views | `ui/tracker/views.py` | Get the indicators |
| Item page already loads all prices and a RateBook | `item_detail` | No extra query needed there |
| `RateBook.convert()`, `display_price()` | `ui/tracker/money.py` | Mixed-currency comparison; showing lowest/highest |
| Lazy `rate_book` in every template | `ui/tracker/context_processors.py` | Views pass their own so rates load once |
| Decorative placeholder card | `dashboard.html` bottom panel | Replaced by the new panel |

## 5. Proposed solution

A new pure module `ui/tracker/indicators.py` (no database or HTML) takes one item's prices (oldest → newest) and a RateBook and returns a `PriceSummary` (change, is_lowest_ever, lowest, highest). `attach_summaries(items, book)` loads every price of the given items in **one query**, groups them per item, and sets `item.price_summary`. Views call it; templates show the result through one shared `_change.html` snippet.

```
/items/ → item_list view → your items (1 query, as today)
        → attach_summaries(): all prices of those items (1 query), grouped
            → summarize(points, book) per item → arrow, percent, lowest-ever
        → template: price + _change.html + "Lowest ever" badge
```

Dashboard panel: items whose `change.since` is within the last 7 days, sorted by absolute percent (descending), max 6, styled like the existing "Price activity" rows.

## 6. Technologies

Existing only: Django templates, Python `Decimal`, existing CSS. No new packages or services. The architectural gate was not triggered.

## 7. Files likely to change

| File | Change |
|---|---|
| `ui/tracker/indicators.py` | **New**: `summarize()`, `attach_summaries()` |
| `ui/tracker/templates/tracker/_change.html` | **New**: arrow + percent pill with a screen-reader label |
| `ui/tracker/tests/test_indicators.py` | **New**: unit tests |
| `ui/tracker/views.py` | Dashboard, item list, item page attach summaries; dashboard builds `price_changes`; views pass `rate_book` |
| `dashboard.html`, `item_list.html`, `item_detail.html` | Show arrows, badge, lowest/highest, new panel |
| `ui/tracker/static/tracker/css/app.css` | Arrow, badge and range styles; unused placeholder styles removed |
| `ui/tracker/tests/test_views.py` | New `IndicatorDisplayTests` |
| `README.md`, `docs/PROJECT_PLAN.md` | Current scope; M5 marked done |

## 8. Ordered tasks

| # | Task | Depends on |
|---|---|---|
| 1 | `summarize()` + unit tests (criteria 1–6) | – |
| 2 | `attach_summaries()` + one-query test | 1 |
| 3 | `_change.html` snippet + CSS | 1 |
| 4 | Item list view + template | 2, 3 |
| 5 | Item page view + template (criterion 9) | 1, 3 |
| 6 | Dashboard arrows + "Price changes" panel (criteria 7, 8) | 2, 3 |
| 7 | View tests (criteria 1, 7, 8, 9, 10) | 4–6 |
| 8 | Docs, full suite, real-page check | all |

Rollback: nothing is stored, so reverting the code changes undoes the feature. **Estimate:** 4–6 hours.

## 9. Testing

- `test_indicators.py`: ~12 unit tests for criteria 1–6 and edge cases (single price, equal prices, missing rate, lowest ties, "since" from first appearance).
- `test_views.py`: pages show arrows/badges; panel window and order; user isolation; lowest/highest on the item page; `assertNumQueries` equal with 1 and 10 items.
- Commands: `manage.py test tracker`, `manage.py check`, `manage.py makemigrations --check`.
- Manual: dashboard, item list and one item page on a database copy, in RON and EUR.

## 10. Risks

| Risk | Mitigation |
|---|---|
| Years of daily checks slow pages | One query per page; SQLite handles ~100k small rows fast; summaries could be stored later |
| Mixed RON/EUR percent reflects exchange rates | Documented rule; mixed items are rare |
| Colour-blind users | Arrow symbol + text; colour is extra |
| Another user's data in the panel | Built only from `_items_for(request.user)`; tested |
| Browser keeps an old `app.css` | Ctrl+F5 once after the update |

## 11. Assumptions and open questions

- **Verified:** full history already loaded on the item page; `RateBook.convert` handles RON; the placeholder card is purely decorative.
- **Assumption (confirmed by the user):** the panel replaces the placeholder; arrows sit beside the price.
- **Note:** a view's own context values take priority over context-processor values, so views can pass their loaded `rate_book`; confirmed by the query-count test.
- Open questions: none.

## 12. Decisions

| Decision | Status |
|---|---|
| Answers 1.A 2.A 3.A 4.A 5.A | Approved |
| Panel replaces placeholder; arrows beside price | Confirmed |
| No database change, no new packages | Part of this plan |
| The plan as a whole | **Approved 2026-11-06** |

## 13. What success looks like

The dashboard shows "Gel ↓ 7.7% since 3 Nov" under **Price changes**; the item list shows green/red arrows and "Lowest ever" badges; each item page shows the lowest and highest price ever seen; and 470 EUR rent stays quiet, with no fake arrows from exchange rates.
