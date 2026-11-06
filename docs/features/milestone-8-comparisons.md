# Feature Plan: Milestone 8, Comparison Groups

*Status: approved on 2026-11-06. Planning only: no code has been written yet.*
*Parent plan: [docs/PROJECT_PLAN.md](../PROJECT_PLAN.md), milestone 8. Builds on [milestone 4](milestone-4-currencies.md) (currencies) and [milestone 5](milestone-5-indicators.md) (indicators).*

Facts are labelled **Verified** (checked on 2026-11-06), **Estimate** or **Assumption**.

---

## 1. Feature summary and user story

A group chart (one line per item, in the viewer's currency), a mixed-period warning with a "Per month" column, "Cheapest" and "+X% vs cheapest" in the group table, editing and deleting groups, and an "Add to comparison" shortcut on the item page.

*As a household member, I want to put alternatives side by side, on one chart and in one table, so I can see which is cheapest and how they've moved over time.*

## 2. Problem, outcome and scope

Today a group can only be created and viewed as a table of latest prices. It can't be edited or deleted (although the empty-group message says "Edit the comparison"), and there is no chart, no indication of the cheapest option, and no warning when periods differ.

**In scope**
- Group chart: one line per item over a real time axis, in the viewer's currency.
- Mixed-period warning, plus a "Per month" column (monthly as is, yearly ÷ 12, one-time "—").
- "Cheapest" badge and "+X% vs cheapest": recurring items (monthly, yearly) compared by per-month value; one-time items compared only with each other.
- M5 ↓/↑ arrows and "Lowest ever" badges in the group table.
- Edit (rename, add/remove items) and delete (confirmation page; items kept).
- Friendly duplicate-name error.
- "Add to comparison" card on the item page.

**Out of scope:** sharing groups between household members, per-month values on the chart, choosing chart colours, deleting items (M3 gap), any database change.

## 3. Requirements and acceptance criteria

**Group chart**
- One coloured line per item: full price history in the viewer's currency, each price at its own day's BNR rate, with a legend of item names.
- Dates spaced by real time.
- Items without prices have no line; prices without a rate are skipped with the same note as the item page; no prices at all → no chart.
- The chart shows actual prices, not per-month values (confirmed).

**Mixed periods**
- When the group has more than one kind of period, show a warning, e.g. "This group mixes Monthly and Yearly prices, so they aren't directly comparable. The Per month column helps."
- The "Per month" column appears only then: monthly = price, yearly = price ÷ 12, one-time = "—".

**Cheapest** (in the viewer's currency)
- Recurring items compared by per-month value; one-time items only with each other (confirmed).
- "Cheapest" only when at least 2 items of the same kind have a price; ties both get it.
- Others: "+12% vs cheapest" (one decimal, ".0" dropped). Items whose price can't be converted are left out.

**Editing and deleting**
- "Edit" opens the create form, filled in. "Delete" opens a confirmation page ("Delete 'Studios'? Your items and their prices are kept."); only the POST button deletes (confirmed). Deleting never deletes items.
- Duplicate name → "You already have a comparison with this name." instead of a crash.

**Add to comparison**
- A "Comparisons" card on the item page (under "Tracking details"): the groups the item is in (links), a dropdown of the user's other groups, and "Add". No groups → "Create a comparison" link. After adding: back to the item page with "Added to Studios.".

**Security:** only your own groups can be viewed, edited, deleted or added to, and only with your own items; anything else returns "Page not found".

**Acceptance criteria**
1. Given two TVs priced in RON and EUR, the group shows one chart with two lines, both in the viewer's currency.
2. Given prices on 20 Oct and 6 Nov, they are 17 days apart on the chart.
3. Given monthly and yearly items, the warning and the Per month column appear (1200 RON/year → **100.00**); a monthly-only group shows neither.
4. Given flats at 2500 and 2800 RON/month, the 2500 one shows **Cheapest** and the other **+12% vs cheapest**.
5. A one-time TV and a monthly rent in the same group are never compared with each other.
6. The table shows M5 arrows and "Lowest ever" badges.
7. A group can be renamed and its items changed; a duplicate name shows a friendly error.
8. Delete removes the group only after confirming; items and prices remain; a GET request deletes nothing.
9. "Add to comparison" on the item page adds the item to the chosen group and lists its groups; with no groups, a create link shows.
10. Another user can't open, edit, delete or add to your groups ("Page not found"), and can't add their item to your group or vice versa.
11. An empty group, or one with no prices, shows the page without a chart and without errors.
12. The full suite passes; the group page uses one query for all items' price histories, whatever the item count.

## 4. Current architecture (Verified)

| What | Where | Relevance |
|---|---|---|
| `ComparisonGroup` (owner, name, items M2M; name unique per owner) | `ui/tracker/models.py` | All data needed; no schema change |
| `comparison_list`, `comparison_create`, `comparison_detail` | `ui/tracker/views.py` | Detail gets chart/table; new edit and delete views |
| `ComparisonGroupForm` (items limited to the owner) | `ui/tracker/forms.py` | Reused for editing; gets a duplicate-name check |
| URLs (no edit or delete) | `ui/tracker/urls.py` | 3 new routes |
| `attach_summaries()` (all prices in one query) | `ui/tracker/indicators.py` | Reused; also keeps each item's price list |
| `RateBook`, `display_price()` | `ui/tracker/money.py` | Conversion for chart and table |
| Chart.js 4.6.1, `price-history.js` | `ui/tracker/static/` | Pattern for the new group chart script |
| `extra_js` block | `templates/tracker/base.html` | Where page scripts load |

## 5. Proposed solution

New pure module `ui/tracker/comparisons.py` (no database or HTML):
- `mixed_periods(items)` → the different period labels (warning when more than one).
- `table_rows(items, currency, book)` → per item: shown price, per-month value, kind (recurring / one-time), Cheapest or +X% vs cheapest.
- `chart_data(items, currency, book)` → one series per item (timestamp, value in the viewer's currency, original), plus the count skipped for a missing rate.

`attach_summaries()` also sets `item.price_history`, so the chart needs no extra query.

```
/comparisons/3/ → comparison_detail: your group or 404
  → attach_summaries(group items, rate book)   ← 1 query for all prices
  → comparisons.table_rows(...) / chart_data(...)
  → template: warning, chart, table with arrows and badges
  → comparison-chart.js draws the lines with Chart.js
```

**Time axis without a new package:** dates become millisecond numbers on a linear axis, with a tick-label function that formats them as dates (no Chart.js date adapter needed).

**Pages:**
- `comparisons/<id>/edit/` — the create form, filled in.
- `comparisons/<id>/delete/` — GET shows the confirmation; POST deletes.
- `items/<id>/add-to-comparison/` — POST only; choices are the user's groups not yet containing the item.

## 6. Technologies

Existing only: Django, Chart.js 4.6.1, Bootstrap. No new packages. The architectural gate was not triggered.

## 7. Files likely to change

| File | Change |
|---|---|
| `ui/tracker/comparisons.py` | **New**: `mixed_periods`, `table_rows`, `chart_data` |
| `ui/tracker/static/tracker/js/comparison-chart.js` | **New**: multi-line chart, time axis, tooltips with originals |
| `ui/tracker/templates/tracker/comparison_confirm_delete.html` | **New**: confirmation page |
| `ui/tracker/tests/test_comparisons.py` | **New**: unit tests |
| `ui/tracker/indicators.py` | `attach_summaries()` sets `item.price_history` |
| `ui/tracker/forms.py` | Duplicate-name check; new `AddToComparisonForm` |
| `ui/tracker/views.py` | `comparison_detail`; new `comparison_update`, `comparison_delete`, `item_add_to_comparison`; `item_detail` card |
| `ui/tracker/urls.py` | 3 new routes |
| `comparison_detail.html`, `comparison_form.html`, `item_detail.html` | Chart, warning, columns, buttons, edit title, card |
| `ui/tracker/static/tracker/css/app.css` | Cheapest / vs-cheapest, legend area, card |
| `ui/tracker/tests/test_views.py` | New `ComparisonTests` |
| `README.md`, `docs/PROJECT_PLAN.md` | Description; M8 marked done |

## 8. Ordered tasks

| # | Task | Depends on |
|---|---|---|
| 1 | Test whether a duplicate name crashes today; add the friendly form check (criterion 7) | – |
| 2 | `comparisons.py` + unit tests (criteria 3–5) | – |
| 3 | `price_history` in `attach_summaries()`; `chart_data()` + tests (criteria 1, 2, 12) | 2 |
| 4 | Group page: view, template, `comparison-chart.js`, CSS (criteria 1–6, 11) | 2, 3 |
| 5 | Edit and delete pages + URLs (criteria 7, 8) | 1 |
| 6 | "Add to comparison" card + URL (criterion 9) | – |
| 7 | View tests incl. security (criteria 7–12) | 4–6 |
| 8 | Docs, full suite, real-page check on a database copy | all |

Rollback: no schema change. Deleting a group removes only the group and its item links, never items or prices. Reverting the code undoes the feature. **Estimate:** 6–8 hours.

## 9. Testing

- `test_comparisons.py`: ~12 unit tests (per month 1200/year → 100.00, Cheapest and +12% incl. ties, recurring vs one-time separation, missing rate, mixed-period detection, chart series with real timestamps).
- `test_views.py`: every new page; other user → 404; GET on delete deletes nothing; duplicate name; adding another user's item refused; empty group; query count equal with 2 or 10 items.
- Commands: `manage.py test tracker`, `manage.py check`, `manage.py makemigrations --check`.
- Manual: on a database copy, a group with the two Militari flats and the 390 EUR test flat — chart, Cheapest, edit, delete, item-page card.

## 10. Risks

| Risk | Mitigation |
|---|---|
| Reaching another user's group/item by changing the URL | Every view filters by owner → 404; tested |
| Deleting a group by accident | Confirmation page, POST only; items and prices never deleted |
| Very different prices make the chart hard to read | Period warning; the table stays the precise view |
| Many items clutter the chart | 8 distinct colours (cycled); legend click hides a line |
| Browser keeps an old `app.css` | Ctrl+F5 once after the update |

## 11. Assumptions and open questions

- **Verified:** `attach_summaries()` loads all prices in one query; Chart.js 4.6.1 is bundled.
- **Assumption (tested in task 1):** a duplicate group name currently crashes with an IntegrityError.
- **Confirmed by the user:** Cheapest compares recurring by per-month and one-time only with each other; the chart shows actual prices; delete uses a confirmation page.
- Open questions: none.

## 12. Decisions

| Decision | Status |
|---|---|
| Answers 1.A 2.B 3.A 4.A 5.A | Approved |
| Assumptions A, B, C | Confirmed |
| Time axis without a new package | Part of this plan |
| No database change | Part of this plan |
| The plan as a whole | **Approved 2026-11-06** |

## 13. What success looks like

Opening "Studios" shows the three flats as coloured lines on one chart in RON, the cheapest marked **Cheapest**, the others "+8.2% vs cheapest", and a ↓ arrow where a rent dropped. The group can be renamed or a flat removed in seconds, and a new listing can be added to the group straight from its item page.
