# Feature Plan: Milestone 3b, Custom Fields and the Location Map

*Status: approved on 2026-11-09. Planning only: no code has been written yet.*
*Parent plan: [docs/PROJECT_PLAN.md](../PROJECT_PLAN.md), milestone 3 gaps (split into [M3a](milestone-3a-archive-delete.md), M3b and M3c). Builds on [M8](milestone-8-comparisons.md) comparisons.*

Facts are labelled **Verified** (checked on 2026-11-07/09), **Estimate** or **Assumption**.

---

## 1. Feature summary and user story

Categories get their own fields, managed by staff on a new **Categories** page. Item forms show the chosen category's fields. **Location** is a special type: a pin on an OpenStreetMap map plus an address. Values appear on the item page and in comparisons, and a comparison with locations gets one map with every item.

*As a household member, I want to record what matters for each kind of thing I track (area, rooms and where a flat is, the brand of a product), so I can compare options on more than price.*

## 2. Scope

**In scope**
- Categories page (staff only): add, rename, delete unused categories; default period; add / edit / reorder / remove fields.
- 5 field types: Text, Number (with unit), Yes/No, Choice list, **Location** (at most one per category).
- Starter fields, only for categories that have none.
- Custom fields in Add item, Add by link and Edit item.
- Item page display (with a small map); comparison columns when all items share a category; comparison map with numbered pins.

**Out of scope:** auto-filling from websites (M3c, incl. location), per-user categories, required fields, "price per m²", filtering/sorting by field values, maps in the item list or dashboard.

## 3. Requirements and acceptance criteria

**Fields:** label ≤ 40 characters, unique per category; unit for numbers; choices as a comma-separated list; at most 10 fields and one Location per category. Each field gets a stable internal **key** from its first label (`area`); renaming keeps values. The type can't change after creation. Removing a field hides its values but keeps them.

**Starter fields**

| Category | Fields |
|---|---|
| Rent | Area (number, m²), Rooms (number), Location, Furnished (yes/no) |
| Apartment for sale | Area (number, m²), Rooms (number), Year built (number), Location |
| Product | Brand (text) |
| Subscription | Plan (text) |

**Item forms:** the chosen category's fields appear under the details and switch with the category. Only the chosen category's values are saved; other categories' stored values stay hidden. All optional. Validation: numbers must be numbers; choices must be an option; text ≤ 200; location latitude −90…90, longitude −180…180, address optional ≤ 200.

**Location input:** a map (centred on Bucharest when empty); click places the pin, drag moves it. "Search address" + Search button (only on press, never while typing): up to 5 results in Romania; choosing one moves the pin and fills the address (editable). "Clear location". Offline: the address box works and a note says the map is unavailable.

**Display:** item page "Tracking details" values ("Area 32 m²", "Furnished Yes"); location as a small map, address and "Open in OpenStreetMap" link. Comparison table: one column per field when all active items share a category; Location column shows the short address and pin number. Comparison map above the table when at least one item has a location: numbered pins matching table rows; clicking shows name and price in the viewer's currency. Every map shows "© OpenStreetMap contributors".

**Security:** Categories pages staff only ("Page not found" otherwise; sidebar link only for staff). Item forms keep the existing owner rules.

**Acceptance criteria**
1. Staff can create "Fuel" with a "Litres" number field; it appears in item forms, without code changes.
2. Non-staff users get "Page not found" on Categories pages and see no sidebar link, but can use every category.
3. After the migration the four categories above have their starter fields; categories that already had fields are unchanged.
4. Rent item with Area "32" and Furnished ticked shows "Area 32 m²" and "Furnished Yes"; "abc" in Area shows an error and saves nothing.
5. A choice field accepts only its options; a tampered value is rejected.
6. Switching from Rent to Product before saving shows Brand and saves only Product's values.
7. Renaming "Area" to "Surface" keeps values; a removed field's values are hidden but stored; an existing field's type can't change.
8. A second Location field or an 11th field shows a form error.
9. Clicking the map or picking a search result saves pin, latitude, longitude and address; latitude "200" is rejected.
10. An item with a location shows the map, address and an OpenStreetMap link; offline, the address and coordinates still show as text.
11. A Rent group shows Area / Rooms / Location / Furnished columns and a map with numbered pins; a mixed-category group shows neither.
12. Deleting a used category shows "Used by N items"; an unused one can be deleted after confirmation.
13. Existing items, prices and comparisons are unchanged; items without values show "—".
14. The full suite passes; `makemigrations --check` shows no unexpected changes.

## 4. Current architecture (Verified)

| What | Where | Relevance |
|---|---|---|
| `Category.field_definitions` (list), `Item.custom_values` (dict), both empty everywhere | `ui/tracker/models.py` | No schema change |
| Categories shared; editable only in the admin | `models.py`, `admin.py` | Staff-only page matches today |
| `ItemForm`, `AutomaticItemForm`, `item_create`, `item_update`, `item_add_link` | `forms.py`, `views.py` | Get the custom-field blocks |
| Shared `_form_fields.html` | `templates/tracker/` | Reused |
| Chart.js / Bootstrap copied into `static/vendor/` with licenses | `ui/tracker/static/vendor/` | Same pattern for Leaflet |
| No referrer setting → Django's default `same-origin` | `ui/app/settings.py` | Affects map tiles (risks) |
| M8 comparison table and chart | `comparisons.py`, `comparison_detail.html` | Columns and map |

## 5. Proposed solution

```
Category.field_definitions = [
  {"key": "area", "label": "Area", "type": "number", "unit": "m²"},
  {"key": "location", "label": "Location", "type": "location"}, ...]
Item.custom_values = {"area": "32", "furnished": true,
  "location": {"lat": 44.44264, "lon": 26.053036, "address": "Strada Gheorghe Ranetti, Militari"}}
```

- **`custom_fields.py`** (new): keys from labels, definition validation (limits, duplicates, one Location), Django form fields per type, value cleaning, display formatting.
- **Item forms:** one hidden block per category; a small script shows the chosen one; the server validates only the chosen block and merges its values into `custom_values`.
- **Categories page:** category form + a formset of field rows (label, type, unit, choices, order, remove); existing types locked; keys in hidden inputs, checked on the server.
- **Maps:** Leaflet 1.9.4 copied into `static/vendor/leaflet/`; drawn markers (no images). Scripts: `custom-fields.js`, `location-picker.js`, `location-map.js`.
- **Address search:** the browser calls `nominatim.openstreetmap.org` once per button press (Romania, ≤ 5 results); only coordinates and address reach the server on save.
- **Starter fields:** data migration `0005`, only where `field_definitions` is empty; reverse is a no-op.

## 6. Technologies

| What | New? | Notes |
|---|---|---|
| Django forms/formsets, JSON fields | Existing | No schema change |
| Leaflet 1.9.4 (BSD-2, ~150 KB) | New, copied in | Download approved 2026-11-09 |
| OpenStreetMap tiles | New outside service | Credit, valid Referer, light use |
| Nominatim search | New outside service | ≤ 1 request/s, no search-as-you-type, credit |

Architectural gate not triggered.

## 7. Files likely to change

| File | Change |
|---|---|
| `ui/tracker/custom_fields.py` | **New** |
| `ui/tracker/migrations/0005_starter_fields.py` | **New** data migration |
| `ui/tracker/forms.py` | `CategoryForm`, field formset, custom-value forms; item forms |
| `ui/tracker/views.py` | Category views (staff); item create/update/add-link; item page; comparison columns and map |
| `ui/tracker/urls.py` | `categories/`, `categories/add/`, `categories/<id>/edit/`, `categories/<id>/delete/` |
| Templates | **New** `category_list.html`, `category_form.html`, `category_confirm_delete.html`, `_custom_fields.html`, `_location_input.html`; changed `item_form.html`, `item_link_form.html`, `item_detail.html`, `comparison_detail.html`, `base.html` |
| `ui/tracker/static/vendor/leaflet/` | **New** `leaflet.js`, `leaflet.css`, `LICENSE` |
| `ui/tracker/static/tracker/js/` | **New** `custom-fields.js`, `location-picker.js`, `location-map.js` |
| `ui/tracker/static/tracker/css/app.css` | Field blocks, maps, numbered pins |
| Tests | **New** `test_custom_fields.py`; more in `test_views.py` |
| `README.md`, `docs/PROJECT_PLAN.md` | Description, roadmap |

## 8. Ordered tasks

| # | Task | Depends on |
|---|---|---|
| 1 | `custom_fields.py` + unit tests | – |
| 2 | Data migration `0005` + test that edited categories are untouched | 1 |
| 3 | Categories pages (staff only), sidebar link | 1 |
| 4 | Item forms: blocks, switching script, save only the chosen category | 1 |
| 5 | Leaflet download; Location input (map, click, drag, search, clear) | 4 |
| 6 | Item page display with small map and offline text | 1, 5 |
| 7 | Comparison columns and numbered map | 1, 5 |
| 8 | View tests (criteria 1–14), browser check, docs, full suite, database-copy check | all |

Rollback: the data migration only fills empty categories and reverses as a no-op; values sit in existing JSON slots. **Back up `db.sqlite3` before `migrate`.** **Estimate:** 12–15 hours.

## 9. Testing

- `test_custom_fields.py`: keys, per-type validation, limits, display.
- View tests: staff-only access; category create/edit (locked type); delete used/unused; saving and showing values; category switching; removed fields hidden; comparison columns and map data; other users refused; starter-field migration.
- JavaScript: no JS test setup exists (adding one would be a new tool) → browser checks of pin click/drag, address search (one real Nominatim request), category switching, offline note, comparison map.
- Commands: `manage.py test tracker`, `manage.py check`, `manage.py makemigrations --check`.

## 10. Risks

| Risk | Mitigation |
|---|---|
| Tiles blocked without a Referer (Django default sends none cross-site) | Leaflet `referrerPolicy: 'strict-origin-when-cross-origin'` on the tile layer and search requests (**assumption until verified in the browser**) |
| OSM usage rules | Search on button press only, one request at a time, credit shown, light use |
| Privacy: OSM sees viewed map areas, searched addresses, IP | Nothing else sent; documented in the README |
| Staff edit hides fields others use | Removing hides values, keeps them; re-adding restores |
| Leaflet inside a hidden block | `invalidateSize()` when the block becomes visible |
| Tampered JSON | Server-side validation; display ignores malformed values |
| Offline | Forms still save; maps show a note and text |

## 11. Assumptions and open questions

- **Verified:** custom-field slots empty; vendor copy-in pattern; no referrer setting; one shared form template.
- **Assumptions:** the `referrerPolicy` fix is enough for OSM tiles; Bucharest default centre; search limited to Romania.
- Open questions: none.

## 12. Decisions

| Decision | Status |
|---|---|
| Earlier answers (Categories page + starter fields, 4 types + choice, item page + comparison columns, Leaflet + OSM, pin + search) | Approved |
| This round: 1.A 2.A 3.A 4.A 5.A | Approved |
| Staff-only Categories page; types locked | Kept |
| Leaflet 1.9.4 copied in (download approved 2026-11-09); OSM tiles and Nominatim from the browser | Approved |
| Data migration `0005` | Part of this plan |
| The M3b plan as a whole | **Approved 2026-11-09** |

## 13. What success looks like

You add a flat under Rent, type 38 in Area, search "Strada Gheorghe Ranetti" and the pin lands in Militari. The item page shows "Area 38 m²", the address and a small map. "Garsoniere Militari" shows Area, Rooms and Location columns and a map with pins 1 and 2 matching the rows. When you start tracking fuel, you add a "Fuel" category with a Litres field in a minute, with no code change.
