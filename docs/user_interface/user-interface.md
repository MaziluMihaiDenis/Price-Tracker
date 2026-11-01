# User Interface Implementation Plan: Price Tracker

*Status: first implementation delivered on 2026-11-01. The Django + Bootstrap foundation is in place; currency conversion, automated checks and richer comparison charting remain future work.*
*Parent plan: docs/PROJECT_PLAN.md.*

Facts are labelled **Verified** when they are stated in the project documentation or present in the prototype. Proposed implementation details and assumptions are labelled accordingly.

---

## 1. Feature summary and user story

A server-rendered dashboard and set of supporting pages for the Price Tracker household app, built with Django templates and Bootstrap.

> *As a signed-in household member, I want to see my tracked products, rents, subscriptions and bills in one place, so I can understand price changes and compare alternatives in the currency I prefer.*

The accepted visual direction is represented by the standalone dashboard prototype created outside the project. The production UI will use the same calm green palette, compact navigation, clear status labels and responsive dashboard layout, while rendering real data through Django.

## 2. Problem, intended outcome, and scope

### Problem

The project tracks different kinds of costs and prices. A useful interface needs to make manual and automatic entries feel consistent, show each item’s price history, and explain when an item could not be checked.

### Intended outcome

- A responsive dashboard for the signed-in user.
- A consistent application shell with navigation, category links and account controls.
- Item list, item detail/history, manual price entry, comparison groups and settings pages as their planned data features become available.
- Bootstrap components for responsive layout and common controls, with a small project stylesheet for the Price Tracker visual identity.
- Django templates that render data and form errors from the server.

### In scope

- Shared Django base template and reusable template partials.
- Dashboard summary cards, latest check activity, recently tracked items and an item price-history chart.
- Item list and detail views, including categories, price period, current price and tracking status.
- Forms for manual prices and, when supported-site adapters exist, adding an item by URL.
- Comparison group pages when comparison models and behavior are implemented.
- Account preferences, including favourite currency, using Django’s account/profile behavior from the project plan.
- Responsive behavior, keyboard navigation and accessible labels/status messages.

### Out of scope

- Implementing or changing the database schema in this UI plan.
- Writing website adapters, scraping pages, scheduling checks or importing exchange rates; those belong to their planned milestones.
- Implementing authentication architecture beyond using Django’s planned login and user/profile features.
- Public hosting, email alerts, CSV import/export or other optional/future project features.
- Reusing the standalone HTML/CSS/JavaScript prototype as production code without review.

## 3. Requirements and acceptance criteria

### Functional requirements

| # | Requirement |
|---|---|
| FR1 | Signed-in users see only their own items, prices, activity and comparison groups. |
| FR2 | The dashboard shows tracked-item counts, recent price changes and items that need attention. |
| FR3 | The item list shows name, category, current price, currency, period, source, last check and status. |
| FR4 | Users can open an item and see its price history in a chart, with the values shown in their favourite currency. |
| FR5 | Users can record a manual price and see validation errors beside the relevant fields. |
| FR6 | Adding an item by URL is offered only for supported sites and when the adapter workflow is available. |
| FR7 | Users can move between the dashboard, items, comparisons and settings using consistent navigation. |
| FR8 | Empty, loading, success and failure states explain what happened and offer an appropriate next action. |
| FR9 | Layout and controls remain usable on desktop, tablet and phone-sized screens. |

### Non-functional requirements

- **Responsive:** Bootstrap’s grid and responsive utilities should support the project’s browser-on-home-Wi-Fi use case, including phones.
- **Accessible:** use semantic headings, labels, visible focus styles, keyboard-operable controls, sufficient contrast and text status indicators in addition to color.
- **Private:** Django views must scope data by the signed-in user; templates must not receive another user’s records.
- **Maintainable:** shared layout and repeated UI pieces should live in base templates and partials rather than copied markup.
- **Locally reliable:** production pages should load Bootstrap and project assets locally, without requiring a third-party CDN at runtime.

### Acceptance criteria

1. Given an authenticated user with items, when they open the dashboard, then the page shows only that user’s summary and recent items.
2. Given an account with no items, when the user opens the dashboard, then a clear empty state offers manual entry and, where available, URL tracking.
3. Given items with different currencies, when the user changes their favourite currency, then displayed amounts use the project’s date-specific conversion rules without changing stored original amounts.
4. Given a manual price form with invalid input, when the user submits it, then Django returns the form with field-level errors and preserves valid entered values.
5. Given an item whose latest check failed or whose listing was removed, when the user views it, then the status and next useful action are clear without implying a price was successfully read.
6. Given a user opens another account’s item URL, then the app does not reveal that item’s data.
7. Given the user views a price-history chart, then the plotted values and date labels correspond to that item’s saved price records.
8. Given a phone-sized viewport, then navigation can be opened and closed, summary cards stack, and wide tables remain usable through responsive scrolling.
9. The UI uses Django’s CSRF protection for state-changing forms and Django template auto-escaping for user-provided text.
10. All primary actions can be reached and used by keyboard, and focus remains visible.

## 4. Current architecture and relevant project context

**Verified in docs/PROJECT_PLAN.md:**

- The planned application uses Python and Django, with Django templates and Bootstrap as the recommended optional style toolkit.
- SQLite is planned initially; PostgreSQL is a possible later move if the app becomes public.
- Chart.js is the planned chart library.
- The app includes accounts, flexible categories, manual prices, automatic tracking, historical price points, currency conversion and comparison groups.
- Prices are stored in their original currency. Display conversion uses the exchange rate for the recorded date and the most recent earlier rate when no rate exists for that date.
- The design plan describes a local household app used from browsers on the home Wi-Fi.

**Verified in the current project files:**

- The project now has the Django project package at `ui/app` and core app at `ui/tracker`, with SQLite models, migrations, admin registration, built-in authentication routes and a profile signal.
- The tracker has authenticated, owner-scoped dashboard, item, comparison and settings views, Django forms, responsive templates and project-specific CSS.
- Bootstrap 5.3.8 and Chart.js 4.6.1 are served from local static assets. The standalone dashboard prototype remains a visual reference and is not used as production code.
- The initial migration seeds the documented category list. Price entry and history work in the original currency; conversion and automated scraping are future work.

**Assumptions for this plan:**

- A Django app will be created for the core tracker, but its app name and exact folder structure have not been established.
- The UI will use Bootstrap 5-compatible markup. The exact Bootstrap release should be selected and pinned when the Django project is set up.
- Existing model and route names will be confirmed during the milestones that create those features. Names below are proposed examples, not verified files.

## 5. Proposed technical solution and rationale

### Overall approach

Use Django views to prepare data, Django templates to render pages, and Bootstrap for the responsive layout and common controls. Keep the project’s colors, typography, spacing and small visual details in a focused stylesheet. Use Chart.js for price history, as selected in the project plan.

This fits a local Django app because the server already owns authentication, forms, database access and HTML rendering. It avoids creating a separate frontend application that would need its own build system and API layer.

### Proposed page structure

| Page | Main contents |
|---|---|
| Dashboard | Summary cards, recent updates, recently tracked items, one useful price-history preview and comparison-group shortcut |
| Item list | Search/filterable items with category, period, source, current price, latest change and status |
| Item detail | Item fields, price history chart, manual price-entry action and check history/status |
| Add/edit item | Django form for manual items; supported-site URL flow only after adapters exist |
| Comparison group | Selected items and a shared chart in the user’s preferred currency |
| Settings | Profile and favourite currency controls |

### Django template structure

**Proposed structure; exact names depend on the app created during setup:**

    tracker/
      templates/
        tracker/
          base.html
          dashboard.html
          item_list.html
          item_detail.html
          comparison_detail.html
          settings.html
          partials/
            _sidebar.html
            _topbar.html
            _summary_card.html
            _item_table.html
            _empty_state.html
      static/
        tracker/
          css/app.css
          js/dashboard.js
          js/price_history.js

- **base.html** provides the document shell, Bootstrap assets, page container, shared navigation and messages area.
- **partials/** holds repeated pieces such as the sidebar, item row, summary card and empty state.
- Each page template extends **base.html** and fills named blocks such as the page title and main content.
- **app.css** contains brand colors, typography, small component adjustments and responsive refinements that are not already covered by Bootstrap.
- JavaScript is limited to interactions that need it, such as chart initialization and progressive enhancements. Form validation and data permissions remain server-side.

### Bootstrap usage

Use Bootstrap’s existing layout and components where they fit:

- **Grid:** dashboard columns on wider screens, stacked cards on narrow screens.
- **Navbar/offcanvas:** compact mobile navigation and the desktop sidebar shell.
- **Cards:** summary metrics, chart panel, updates and comparison preview.
- **Tables and responsive wrappers:** item lists that can scroll horizontally on narrow screens.
- **Forms:** aligned labels, help text, validation feedback and clear submit buttons.
- **Badges/alerts:** price movement and item status labels, always with readable text in addition to color.
- **Modal or dedicated form page:** add-item flow. Prefer a normal Django form page if the interaction becomes too complex for a modal; the server remains the source of truth either way.

The design should use a small set of Bootstrap classes consistently, with project-specific classes for the Price Tracker appearance. Avoid building a second component framework on top of Bootstrap.

**Asset delivery:** serve a pinned Bootstrap CSS and JavaScript bundle from the project’s static files. This keeps the local app usable without a third-party CDN and avoids sending page requests or metadata to a CDN provider. No extra Django Bootstrap integration package is required for the basic template approach.

### Dashboard data flow

    Browser request
      → Django URL pattern
      → authenticated dashboard view
      → user-scoped database queries
      → template context
      → Django template + Bootstrap markup
      → HTML response in browser

The view should pass prepared values rather than making templates perform database logic. For example, it can provide summary counts, recent price changes, recent items, and chart labels/values. Query patterns should be reviewed against the real models when they exist; use related-object loading or aggregation where that prevents one query per item.

### Form data flow

    User submits Django form
      → view checks authentication and ownership
      → Django form validates fields
      → valid data is saved through the planned models
      → redirect to the item page with a success message

If validation fails, the same template is rendered with the bound form and field errors. State-changing forms include Django’s CSRF token. URL submission must also validate allowed site domains and use the supported-adapter workflow; the UI must not make the server fetch arbitrary user-supplied addresses.

### Price history and currency

- The item detail view supplies the item’s saved price records in date order.
- The view prepares chart labels and values in the signed-in user’s favourite currency using the project’s historical conversion function.
- Chart.js renders the line and date axis in the browser.
- Provide a text summary or data table alongside the chart so the information is still available if the chart cannot render or for assistive technology.
- Stored price amounts remain in their original currency; changing the display currency must not rewrite historical records.

### Loading, empty and failure states

Django’s normal page response is server-rendered, so a separate loading screen is not needed for the first page load. The templates should still distinguish:

- No items yet.
- No history for this item yet.
- Unsupported URL or missing adapter.
- A page check that failed, timed out or was blocked.
- A listing marked removed.
- Missing exchange-rate data, with the documented earlier-rate fallback.
- A form validation error or a successful save.

Messages should state what the user can do next. A blocked or failed scrape must not be presented as a valid current price.

## 6. Technologies and dependencies

| Technology | Role in the UI | Status |
|---|---|---|
| Django templates | Render pages using server-provided data and form state | Selected in the project plan |
| Bootstrap | Responsive grid, form styling, navigation and common components | Optional/recommended in the project plan; explicitly requested for this implementation |
| Chart.js | Draw item history and comparison charts | Selected in the project plan |
| Django forms | Validate manual price and item forms on the server | Planned Django capability |
| SQLite | Stores the app’s users, items, price records and other planned data | Selected initially in the project plan |

**Bootstrap version:** Bootstrap 5.3.8 is included as a local static asset. Chart.js 4.6.1 is included for item history charts.

## 7. Files and components likely to change

The repository does not yet have the Django application structure, so these are proposed examples, not existing paths.

| Proposed path | Responsibility |
|---|---|
| tracker/templates/tracker/base.html | Shared shell and page blocks |
| tracker/templates/tracker/dashboard.html | Dashboard content |
| tracker/templates/tracker/item_list.html | Filterable item collection |
| tracker/templates/tracker/item_detail.html | Item data and price history |
| tracker/templates/tracker/partials/ | Reusable navigation, cards, item rows and empty states |
| tracker/views.py | Authenticated views and template context |
| tracker/urls.py | UI route definitions |
| tracker/forms.py | Manual item and price form validation |
| tracker/static/tracker/css/app.css | Brand styling and responsive refinements |
| tracker/static/tracker/js/price_history.js | Chart.js initialization |
| tracker/tests/test_views.py | Page rendering, ownership and form behavior tests |
| tracker/tests/test_templates.py | Empty, status and accessibility-relevant content checks |

The actual names and locations should follow the structure established during project setup. This UI plan should not create a parallel app if the project setup chooses a different Django app name.

## 8. Ordered implementation tasks

| # | Task | Depends on | Purpose | Done when |
|---|---|---|---|---|
| 1 | Confirm the Django app structure and Bootstrap asset strategy | Project setup | Use real project paths and a pinned local Bootstrap asset | Shared template loads Bootstrap without a third-party runtime request |
| 2 | Create the shared base template and navigation partials | 1 | Give each page one consistent shell | A placeholder page renders desktop and mobile navigation |
| 3 | Add dashboard view and template using existing models | Models and accounts | Replace prototype numbers with user-specific values | Authenticated user sees their own summary, updates and recent items |
| 4 | Add item list and detail templates | Item and PricePoint models | Make the tracker usable beyond the overview | Items and history render with clear source/status/period labels |
| 5 | Add manual entry forms and feedback states | Manual-entry milestone | Support the project’s always-available manual path | Valid prices save; invalid inputs return clear errors |
| 6 | Add Chart.js item history | Historical prices and conversion | Show trends using real dated values | Chart points match saved prices and selected display currency |
| 7 | Connect URL-based item creation | Supported adapters | Add automatic tracking without arbitrary URL fetching | Supported URLs use an adapter; unsupported URLs receive a clear message |
| 8 | Add comparison group UI | Comparison models and feature | Compare alternatives in the user’s currency | Group members appear together and mixed periods are identified |
| 9 | Review responsive behavior, accessibility and tests | 2–8 | Catch layout and interaction issues before household use | Acceptance checks pass at desktop and phone widths |

The sequence follows the project roadmap: core templates can start after project setup, manual entry after the core data milestone, real price charts after history/conversion work, URL tracking after adapters, and comparisons after comparison groups exist.

**Rollback:** template and static-asset work can be reverted independently of stored data. Do not delete or rewrite database records as part of rolling back a UI change.

## 9. Testing and verification strategy

### Automated checks

Use Django’s test client and test database to check:

- Authenticated dashboard and item pages return successfully.
- Unauthenticated users are sent through the planned login flow.
- A user cannot see another user’s items by changing an item URL.
- Empty collections and missing price history render their intended states.
- Manual forms accept valid positive decimal prices and reject invalid or non-positive values.
- Currency presentation uses the expected date-specific conversion result.
- Status messages distinguish blocked/error/removed items from successful checks.
- Chart data is generated from the item’s actual saved price records.
- Templates include labels, useful headings, text status indicators and CSRF tokens on state-changing forms.

### Manual checks

- Resize through desktop, tablet and phone widths.
- Use the main navigation, item filters, forms and dialogs with a keyboard.
- Check the chart at different currencies and verify a few displayed values against the conversion function.
- Confirm long item names, categories, error messages and empty states remain readable.
- Verify local Bootstrap assets load without an external CDN.

No production UI tests have been run; there is no Django UI implementation in the current repository to test.

## 10. Security, privacy and other risks

| Risk | Mitigation |
|---|---|
| One household member sees another member’s item | Apply ownership filters in every relevant view/query and test cross-user access |
| Cross-site form submission | Keep Django CSRF middleware enabled and include CSRF tokens in POST forms |
| User-entered text is rendered as markup | Rely on Django template auto-escaping; do not mark user content safe |
| URL form is used to make the server fetch an internal or unsupported address | Validate scheme and supported hostname, then dispatch only to known adapters |
| CDN outage or external requests reveal metadata | Serve Bootstrap assets locally |
| Price status is communicated only by color | Include plain text labels and icons with accessible names |
| Dashboard becomes slow as history grows | Limit dashboard history to the needed date window and use efficient related-object loading/aggregation |
| Chart is unavailable to screen readers | Include a concise text summary and an accessible table or equivalent data description |

## 11. Assumptions, dependencies and open questions

- **Verified:** Django templates are the project’s planned UI approach; Bootstrap is optional/recommended; Chart.js is the planned chart library. Source: docs/PROJECT_PLAN.md.
- **Verified:** the accepted visual direction is captured in the standalone dashboard prototype; it is not integrated into the Django app.
- **Assumption:** the eventual app will use a core Django app with a base template and namespaced static assets.
- **Assumption:** Bootstrap will be served locally as pinned static assets rather than loaded from a CDN.
- **Dependency:** the relevant models and authentication/profile flow must exist before real dashboard values can be shown.
- **Dependency:** chart, URL-add and comparison pages depend on their respective project milestones.
- **Open question:** confirm the final Django app name and template directory during project setup.
- **Open question:** decide whether item creation is a dedicated page or a modal after the real form fields and validation are known.
- **Open question:** confirm which two sites are selected for the MVP before showing a production “add by link” flow.

## 12. Decisions requiring approval

| Decision | Status |
|---|---|
| Django server-rendered templates | Selected in docs/PROJECT_PLAN.md |
| Bootstrap for responsive layout and common controls | Requested by the user; aligns with the project plan’s recommendation |
| Chart.js for history charts | Selected in docs/PROJECT_PLAN.md |
| Local, pinned Bootstrap assets instead of a CDN | Proposed for reliability and privacy; confirm during project setup |
| Exact route, template and app names | Deferred until the Django project structure exists |
| Dedicated add-item page versus modal | Deferred until real form behavior is implemented |

## 13. What success looks like

A household member can sign in, see only their own tracked items, understand each item’s current price and check status, enter a manual price, view correctly converted price history, and compare alternatives. The pages share a responsive Bootstrap-based layout, while Django remains responsible for authorization, validation and data. Automatic tracking appears only for supported sites after the adapter milestone is complete.
