# Price Tracker

A private, server-rendered household price tracker built with Django, SQLite and Bootstrap. The current app supports manual item and price entry, automatic price tracking for eMAG and Storia links with a daily check, price history, comparison groups, and a per-user display-currency preference.

## Run locally

1. Create a virtual environment:

   ```powershell
   py -m venv .venv
   ```

2. Install the pinned application dependencies:

   ```powershell
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

3. Create the database and initial categories:

   ```powershell
   .\.venv\Scripts\python.exe ui\manage.py migrate
   ```

4. Create the first household account:

   ```powershell
   .\.venv\Scripts\python.exe ui\manage.py createsuperuser
   ```

5. Start the local development server:

   ```powershell
   .\.venv\Scripts\python.exe ui\manage.py runserver
   ```

Open <http://127.0.0.1:8000/> and sign in with the account created above. The Django admin is available at `/admin/` for category and account management.

## Daily price checks

Items added by link (eMAG and Storia) are re-checked automatically every day at 17:00 by Windows Task Scheduler, or as soon as the PC is on if 17:00 was missed. Each household member's dashboard shows the result of the latest run for their own items.

Register the task once, from the project folder:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\register_daily_check.ps1
```

The task runs only while you are logged in to Windows, so no password is stored. Output is appended to `logs\daily_check.log`.

Run a check by hand (`--force` also re-checks items checked in the last 20 hours):

```powershell
.\.venv\Scripts\python.exe ui\manage.py check_prices --force
```

Remove the task:

```powershell
Unregister-ScheduledTask -TaskName 'Price Tracker daily check' -Confirm:$false
```

## Exchange rates

Every price is shown in each person's display currency (RON or EUR, set under Preferences), converted at the official National Bank of Romania (BNR) rate for the day the price was recorded. On weekends and holidays the previous banking day's rate is used. Saved prices are never changed; the original amount is shown underneath.

Load the rate history once (BNR yearly files, from the year before your oldest price or 2025):

```powershell
.\.venv\Scripts\python.exe ui\manage.py import_rates
```

After that, the daily check (above) fetches the latest rates before checking prices. If BNR is unreachable, it logs a warning and still checks prices.

## Categories, custom fields and maps

Each category can have its own fields (text, number with a unit, yes/no, choice list, and one Location), for example Area, Rooms and Location for Rent. Staff accounts manage them under **Categories** in the sidebar; categories are shared by the whole household. The first `migrate` adds starter fields to Rent, Apartment for sale, Product and Subscription.

Location fields use a map: click to place a pin, drag it, or search an address. Maps come from OpenStreetMap ([Leaflet](https://leafletjs.com) 1.9.4 is bundled in `ui/tracker/static/vendor/leaflet/`). Privacy: when a map is shown, your browser loads map images from `tile.openstreetmap.org`, and an address search sends the typed text to `nominatim.openstreetmap.org`. Both see your IP address and the area or address involved, never your prices, items or account. Without internet the forms still work: type the address or the coordinates.

Details from the website: when you add a Storia listing or an eMAG product by link, the details the page gives (Storia: area, rooms, year built, floor, heating, location; eMAG: brand and the specifications table) are pre-filled in the matching fields of the category you pick. On an existing item, **Fill from website** checks today's price (like Check now) and shows what the page offers; you choose which empty fields to fill. Your own values are never replaced. Fields are matched by name (English or Romanian, e.g. Area / Suprafață), and eMAG specifications by a field with the same name (e.g. "Tip produs").

## Current scope

Prices can be entered manually, or read automatically from eMAG product pages and Storia listings ("Add by link", "Check now" and the daily check). Prices are shown in each person's display currency (RON or EUR) at BNR's historical rates. Each price shows how it changed since the previous different price ("↓ 7.7%", compared in the price's own currency, so exchange-rate movement never creates an arrow), a "Lowest ever" badge, and the item page shows the lowest and highest prices; the dashboard lists this week's price changes. Comparison groups show every item on one chart in your currency, mark the cheapest option (recurring items by their per-month price, one-time purchases only with each other), warn when periods are mixed, and can be edited, deleted, or added to from an item's page. Items can be archived (hidden and no longer checked, restorable later) and, once archived, deleted permanently; single prices can be deleted from an item's history. Categories can have custom fields, including a Location shown on a map on item and comparison pages. Django's development server is for local development; review deployment settings before making the app reachable outside a trusted network.
