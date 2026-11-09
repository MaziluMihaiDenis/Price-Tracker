# Feature Plan: Milestone 3a, Archive and Delete

*Status: approved on 2026-11-07. Planning only: no code has been written yet.*
*Parent plan: [docs/PROJECT_PLAN.md](../PROJECT_PLAN.md), milestone 3 gaps. M3 was split into **M3a** (this plan: archive and delete), **M3b** (custom fields with a Location field and a Leaflet + OpenStreetMap map) and **M3c** (auto-fill from websites), each planned separately.*

Facts are labelled **Verified** (checked on 2026-11-07), **Estimate** or **Assumption**.

---

## 1. Feature summary and user story

Archive and restore items, permanently delete archived items, and delete single prices.

*As a household member, I want to put away items I no longer care about (and bring them back if I change my mind), permanently remove ones I'm sure about, and delete wrong prices, so my lists, charts and comparisons stay accurate.*

## 2. Scope

**In scope:** archive / restore; permanent delete (archived items only, with confirmation); delete one price (with confirmation); "Archived" option in the item list's status filter.

**Out of scope:** custom fields, map and auto-fill (M3b, M3c), bulk delete, undoing a permanent delete, automatic clean-up of old archived items.

## 3. Requirements and acceptance criteria

**Archive**
- An **Archive** button in the item page heading, with no confirmation (it's reversible). Message: "Archived. It's hidden from your lists and won't be checked."
- An archived item is hidden from: the item list (unless filtered by "Archived"), the dashboard (counts, Recently tracked, Price activity, Price changes), comparison groups (table and chart), the comparison form's checkboxes, and the "Add to comparison" card.
- The daily check skips it, and **Check now** is hidden.
- Its page still opens, with the banner "Archived on 7 Nov 2026" and **Restore** / **Delete permanently** buttons.
- Group membership is kept: restoring puts it back in its groups, and editing a group never drops archived members.
- Pasting the link of an archived item in Add by link shows the existing "already tracking" message pointing to it.

**Permanent delete**
- Only for archived items; otherwise redirect to the item page with "Archive the item first."
- GET shows the confirmation ("Delete 'X' permanently? Its 12 prices and check history will be removed. This can't be undone."); only POST deletes the item, its prices, its check history and its group links. Then: item list with "Deleted 'X'."

**Delete a price**
- A 🗑 button on each price history row (screen-reader label "Delete price of 5 Nov 2026") opens a confirmation page showing amount and date; only POST deletes. Back to the item page; indicators and chart recalculate. Removing the last price is allowed ("No price yet").

**Security:** every new view checks the item belongs to you and the price belongs to that item, otherwise "Page not found". Archive and restore are POST only.

**Acceptance criteria**
1. Archiving removes the item from the item list, dashboard (incl. counts and Price changes), comparison groups and the comparison form.
2. An archived automatic item isn't checked by the daily check, and has no Check now button.
3. Restoring brings it back everywhere with the same status and comparison groups.
4. Editing and saving a group that contains an archived item keeps that item as a member.
5. The "Archived" filter shows only archived items.
6. Confirming "Delete permanently" on an archived item removes the item, its prices and check history; GET deletes nothing; a non-archived item can't be permanently deleted.
7. Deleting one price removes only that price and the indicators update; deleting the last price shows "No price yet".
8. Another user gets "Page not found" for archive, restore, delete and price delete, and nothing changes.
9. The migration adds the archive date with every existing item not archived.
10. The full test suite passes.

## 4. Current architecture (Verified)

| What | Where | Relevance |
|---|---|---|
| `Item`; PricePoint and CheckAttempt are CASCADE-deleted; M2M group links removed automatically | `ui/tracker/models.py` | Permanent delete needs no extra clean-up |
| `_items_for(user)` | `ui/tracker/views.py` | One place to hide archived items |
| `get_object_or_404(..., owner=request.user)` pattern | `ui/tracker/views.py` | Same safety pattern for new views |
| `can_be_checked()` | `ui/tracker/checks.py` | One place to skip archived items (daily check + Check now) |
| `ComparisonGroupForm`, `AddToComparisonForm` | `ui/tracker/forms.py` | Hide archived items; keep archived members on save |
| Item list status filter | `item_list.html` | Gets an "Archived" option |
| `comparison_delete` (M8) | `views.py` | Confirmation pattern to follow |

## 5. Proposed solution

- **Database:** new nullable `Item.archived_at` (empty = not archived). Migration `0004` only adds an empty column.
- **One place to hide:** `_items_for(user)` excludes archived items; the item page uses a variant that includes them. `can_be_checked()` returns False for archived items.
- **New views:**

| URL | GET | POST |
|---|---|---|
| `items/<id>/archive/` | 405 | set `archived_at` = now |
| `items/<id>/restore/` | 405 | clear `archived_at` |
| `items/<id>/delete/` | confirmation (archived only) | delete |
| `items/<id>/prices/<price id>/delete/` | confirmation | delete that price |

- **Archived group members:** the group form shows only active items and re-adds the group's archived members on save.

## 6. Technologies

Existing only (Django). No new packages. One small migration. Architectural gate not triggered.

## 7. Files likely to change

| File | Change |
|---|---|
| `ui/tracker/models.py` | `archived_at`, `is_archived` |
| `ui/tracker/migrations/0004_item_archived_at.py` | **New** |
| `ui/tracker/views.py` | `_items_for`, Price activity, 4 new views, list filter |
| `ui/tracker/checks.py` | `can_be_checked()` |
| `ui/tracker/forms.py` | Comparison forms |
| `ui/tracker/urls.py` | 4 routes |
| `item_detail.html`, `item_list.html` | Buttons, banner, 🗑, filter |
| `item_confirm_delete.html`, `price_confirm_delete.html` | **New** |
| `ui/tracker/tests/test_views.py`, `test_daily.py` | Tests |
| `README.md`, `docs/PROJECT_PLAN.md` | Description; roadmap split M3a/M3b/M3c |

## 8. Ordered tasks

| # | Task | Depends on |
|---|---|---|
| 1 | `archived_at` + migration | – |
| 2 | Hide archived items (`_items_for`, Price activity, `can_be_checked`, comparison forms) | 1 |
| 3 | Archive / Restore views, banner, buttons, list filter | 2 |
| 4 | Permanent delete page | 3 |
| 5 | Delete-a-price page | – |
| 6 | Tests for all criteria incl. security and daily check | 2–5 |
| 7 | Docs, roadmap, full suite, check on a database copy | all |

Rollback: the migration is reversible. **Back up `ui/db.sqlite3` before running `migrate` on the real database** (`db.backup-*.sqlite3` is git-ignored). Permanent deletes can't be undone by design, hence archive-first and a confirmation. **Estimate:** 3–4 hours.

## 9. Testing

- View tests: archive/restore everywhere; Archived filter; archived group members kept on edit; permanent delete (GET does nothing, non-archived refused, prices and attempts removed); price delete incl. last price; other user → 404.
- Daily check test: archived item not checked.
- Commands: `manage.py test tracker`, `manage.py check`, `manage.py makemigrations --check`.
- Manual: on a database copy.

## 10. Risks

| Risk | Mitigation |
|---|---|
| Deleting the wrong item | Archive first, confirmation naming the item and its price count, POST only |
| Archived item dropped from a group on edit | Form re-adds archived members; tested |
| Deleting another user's data via URL | Owner checks everywhere; tested |
| Migration on the real database | Only adds an empty column; back up first |

## 11. Assumptions and open questions

- **Verified:** CASCADE/PROTECT rules, `_items_for`, `can_be_checked`, the M8 delete pattern.
- **Assumption:** archiving needs no confirmation.
- Open questions: none.

## 12. Decisions

| Decision | Status |
|---|---|
| Split M3 into M3a / M3b / M3c; answers 1.C 2.C 3.C 4.A 5.A and 1.A 2.A 3.A 4.A 5.A | Approved |
| `archived_at` for archiving | Kept |
| Migration `0004` | Part of this plan |
| The M3a plan as a whole | **Approved 2026-11-07** |

## 13. What success looks like

You archive "TEST Garsoniera" and it vanishes from your lists and the Militari comparison; later you open it from the "Archived" filter and delete it permanently. On another item you remove one wrong price in two clicks. Everything else stays exactly as it was.
