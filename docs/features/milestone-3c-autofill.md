# Feature Plan: Milestone 3c, Filling Item Details from the Website

*Status: approved on 2026-11-09. Planning only: no code has been written yet.*
*Parent plan: [docs/PROJECT_PLAN.md](../PROJECT_PLAN.md), milestone 3 gaps (split into [M3a](milestone-3a-archive-delete.md), [M3b](milestone-3b-custom-fields.md) and M3c). Builds on M3b custom fields.*

Facts are labelled **Verified** (checked on 2026-11-09), **Estimate** or **Assumption**.

---

## 1. Feature summary and user story

When you add a Storia or eMAG item by link, the details the page gives (area, rooms, year built, floor, heating, location, brand…) are **pre-filled** in the Details section for you to check before saving. On existing items, **"Fill from website"** reads the page once, **records today's price** like Check now, and shows a **preview** where you confirm which empty fields to fill. Values you typed are never replaced.

*As a household member, I want the app to copy the details a listing already shows (area, rooms, where it is), so I don't retype them and my comparisons are complete.*

## 2. Scope

**In scope**
- Reading details: Storia (location pin + address, area, rooms, year built, floor, heating, furnished when stated); eMAG (brand, specification table).
- Matching details to the category's fields: built-in name matches + eMAG specs by field label.
- Plain-English names for Storia codes (`ground_floor` → "Ground floor").
- Pre-fill in Add by link; "Fill from website" with preview, confirm and price recording.
- Data migration adding **Floor** and **Heating** (text) to Rent and Apartment for sale, only where missing.

**Out of scope:** filling during the daily check, creating fields automatically, other sites, overwriting typed values, updating details that changed on the website.

## 3. Requirements and acceptance criteria

**Matching** — a detail fills a field only when:
1. The category has a field whose **key or label** matches (case- and accent-insensitive):

   | Detail | Matching names |
   |---|---|
   | Area | area, suprafață, suprafață utilă, surface |
   | Rooms | rooms, camere, nr. camere |
   | Year built | year built, an construcție, anul construcției |
   | Floor | floor, etaj |
   | Heating | heating, încălzire |
   | Brand | brand, marcă, producător |
   | Furnished | furnished, mobilat |
   | Location | any Location-type field |

   eMAG specifications match a field with the **same label** (field "Tip produs" ← row "Tip produs").
2. The value **fits the field type**: number → a number; Yes/No → yes/no/da/nu; choice → one of the options; text ≤ 200 characters; location → valid coordinates. Otherwise skipped.
3. Multi-value specs ("Uscat / Normal") are joined as "Uscat, Normal".

**Storia codes:** Floor → "Ground floor", "Floor 1"…"Floor 10", "Above floor 10", "Basement", "Attic"; Heating → "Gas", "District heating", "Building boiler", "Electric", "Tiled stove", "Other"; unknown codes tidied (`own_boiler` → "Own boiler").

**Storia address:** street (if given) + Storia's area names, e.g. "Strada Gheorghe Ranetti, Militari, Sectorul 6, Bucuresti".

**Add by link:** in the preview step every category block is pre-filled with its matched details; nothing is saved until **Save and track**, with normal validation.

**Fill from website** (item page, next to Check now; automatic items only):
1. Reads the page once and **records the price like Check now**, with the same 10-minute pause.
2. A **preview** lists matched fields (field, your value, website value, status: ☑ will be filled / kept, you already have a value), plus unmatched details as "Not used".
3. **Confirm** fills only ticked fields that are still empty, then returns to the item page ("Filled Area and Location from Storia.").
4. Values come from what the server read, kept in the session until confirmation; values sent back by the browser are never trusted.
5. If reading fails: the usual Check now message, no preview.
6. Nothing matched: "The page didn't have any details for this category's fields." (price still recorded).

**Floor and Heating:** data migration adds them to Rent and Apartment for sale unless a field with that key or label exists; never changes existing fields; reverse is a no-op.

**Acceptance criteria**
1. Storia test page → location (44.44264, 26.053036, "Strada Gheorghe Ranetti, … Bucuresti"), area 38, rooms 1, year built 2017, floor "Ground floor", heating "Gas".
2. eMAG test page → brand "CeraVe" and specification rows, multi-line values joined.
3. Add by link (Storia) → Rent block pre-filled with Area 38, Rooms 1, Floor, Heating and Location; Save stores them.
4. Product category with "Tip produs" field → an eMAG link fills "Gel de curatare".
5. Already-filled Area → preview shows "kept"; confirming doesn't change it.
6. Fill from website records a price like Check now; a second press within 10 minutes is refused with the same message.
7. An unticked field isn't filled; tampered values in the request are ignored.
8. A choice value not among the options, or "abc" for a number, is skipped.
9. A page without the data block, or with broken data, still gives a price; details are empty; no error page.
10. Another user's item → "Page not found"; manual items have no button.
11. After the migration Rent and Apartment for sale have Floor and Heating; a category that already had "Floor" is unchanged.
12. The full test suite passes.

## 4. Current architecture (Verified)

| What | Where | Relevance |
|---|---|---|
| `PageResult(title, price, currency, available)`; `SiteAdapter.extract()` (structured data / meta tags) | `ui/tracker/adapters/base.py` | Gets `details` + a details reader |
| `StoriaAdapter`, `EmagAdapter` (settings only) | `adapters/storia.py`, `emag.py` | Site-specific readers |
| `read_page()` → `ReadResult(page)`; `check_item()` → `CheckResult` without the page | `ui/tracker/checks.py` | `CheckResult` must carry the page |
| `item_check` view (cooldown, messages) | `ui/tracker/views.py` | Reused by Fill |
| Add by link session preview (`LINK_PREVIEW_KEY`) | `views.py` | Same pattern for Fill |
| `custom_fields.fits()`, `definitions()`, `merge_values()` | `ui/tracker/custom_fields.py` | Type checks, saving |
| Storia `__NEXT_DATA__`: `ad.characteristics` (`m`, `rooms_num`, `build_year`, `floor_no`, `heating`…), `ad.location.coordinates`, `ad.location.address.street`, `ad.location.reverseGeocoding` | Saved page 2026-11-05 | Storia details |
| eMAG JSON-LD `brand.name`; `.specifications-body` table rows | Saved page 2026-11-05 | eMAG details |
| Trimmed, anonymised test pages | `ui/tracker/tests/fixtures/` | Need a small Storia data block and eMAG spec table |

## 5. Proposed solution

- **Adapters:** `PageResult.details` (`area`, `rooms`, `year_built`, `floor`, `heating`, `furnished`, `brand`, `location`, plus `specs`); `SiteAdapter.extract()` calls each adapter's `_details(soup)`; each detail read in its own try, so details never break the price.
- **`autofill.py`** (new, pure): `match(details, category)` → `{field key: value}` for matching, fitting fields; aliases and code translations.
- **Add by link:** preview step builds each block with `initial = match(page.details, category)`; details stored in the preview session (JSON-safe).
- **Fill from website:**
```
[Fill from website] POST /items/<id>/fill/
  → Check now rules (owner, automatic, 10-minute pause)
  → check_item(): price recorded; CheckResult now carries the page
  → match(details, item.category) → session (per item)
  → GET /items/<id>/fill/ preview with ticks
  → POST /items/<id>/fill/confirm/: ticked keys only, still-empty fields only, values from the session
  → merge_values() → saved → item page with a message
```
- **Data migration `0006`** for Floor and Heating.

## 6. Technologies

Existing only: BeautifulSoup, Django sessions and forms. No new packages. Architectural gate not triggered.

## 7. Files likely to change

| File | Change |
|---|---|
| `ui/tracker/adapters/base.py` | `PageResult.details`; safe `_details()` hook |
| `ui/tracker/adapters/storia.py`, `emag.py` | Details readers |
| `ui/tracker/autofill.py` | **New** |
| `ui/tracker/checks.py` | `CheckResult.page` |
| `ui/tracker/views.py` | Add-by-link pre-fill; `item_fill`, `item_fill_confirm` |
| `ui/tracker/urls.py` | `items/<id>/fill/`, `items/<id>/fill/confirm/` |
| `ui/tracker/templates/tracker/item_fill_preview.html` | **New** |
| `item_detail.html` | Button |
| `ui/tracker/migrations/0006_floor_heating_fields.py` | **New** |
| `ui/tracker/tests/fixtures/storia_listing.html`, `emag_product.html` | Anonymised details |
| Tests | **New** `test_autofill.py`; more in `test_adapters.py`, `test_views.py` |
| `README.md`, `docs/PROJECT_PLAN.md` | Description; roadmap (M3 done, M9 next) |

## 8. Ordered tasks

| # | Task | Depends on |
|---|---|---|
| 1 | Extend test pages (anonymised) | – |
| 2 | `PageResult.details` + adapter readers + tests (criteria 1, 2, 9) | 1 |
| 3 | `autofill.py` + tests (criteria 4, 8) | – |
| 4 | Add-by-link pre-fill + tests (criterion 3) | 2, 3 |
| 5 | `CheckResult.page`, Fill views, template, button + tests (criteria 5, 6, 7, 10) | 2, 3 |
| 6 | Migration `0006` + test (criterion 11) | – |
| 7 | Docs, full suite, database-copy check (one real Storia read) | all |

Rollback: `0006` only adds missing fields, reverse no-op; filled values are ordinary custom values. **Back up `db.sqlite3` before `migrate`.** **Estimate:** 6–8 hours.

## 9. Testing

- Adapter tests: details from anonymised Storia and eMAG pages; broken/missing data still gives a price.
- `test_autofill.py`: aliases (accents, case), type fit, choice options, spec labels, translations.
- View tests: Add-by-link pre-fill; Fill preview (price recorded, 10-minute pause, kept fields, unticked, tampered values ignored, other users, no button on manual items, nothing matched).
- Migration test: added once; existing "Floor" untouched.
- Commands: `manage.py test tracker`, `check`, `makemigrations --check`.
- Manual: one real Fill from website on a Storia item, on a database copy.

## 10. Risks

| Risk | Mitigation |
|---|---|
| Storia redesign breaks details | Each detail read safely; price uses separate data; tests use a fixed copy |
| Wrong value fills a field | Empty fields only; confirmed preview; type fit required |
| Tampered values on confirm | Server-side session values only |
| Too many site requests | One Check now per Fill, with the 10-minute pause and robots.txt rule |
| Real seller data in test pages | Trimmed and anonymised fixtures |

## 11. Assumptions and open questions

- **Verified:** Storia data block and keys, eMAG brand and spec table, `check_item` not returning the page.
- **Assumptions:** Storia's `furniture` detail appears only on some listings (otherwise Furnished stays empty); Floor and Heating are text fields.
- Open questions: none.

## 12. Decisions

| Decision | Status |
|---|---|
| Pre-fill at Add by link + Fill button; built-in matches + eMAG labels; never overwrite | Approved earlier (4.A, 5.A) |
| 1.B preview first · 2.B record the price · 3.A English names · 4.A add Floor and Heating | Approved |
| Migration `0006`; `CheckResult` carries the page | Part of this plan |
| The M3c plan as a whole | **Approved 2026-11-09** |

## 13. What success looks like

You paste a Storia link and pick Rent: Area 38, Rooms 1, Ground floor, Gas and the Militari pin are already there; you press Save. On an older flat you press **Fill from website**, see today's price recorded and a table of what Storia offers, untick what you don't want and confirm. On an eMAG product your "Tip produs" field fills itself.
