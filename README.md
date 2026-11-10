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

## Household use on the home Wi-Fi

In household mode the app runs with Waitress on port 8000 for everyone on the home Wi-Fi, with development mode off, a private secret key, and daily backups. Development (`runserver`, above) is unaffected.

### For family members

1. Connect your phone to the home Wi-Fi.
2. Open **http://PC-NAME:8000/** in the browser (the admin tells you the PC's name; if that doesn't work, use the PC's address, e.g. http://192.168.1.20:8000/).
3. Sign in with the account the admin created for you. You only see your own items, prices and comparisons.
4. Add it to your home screen: **Android (Chrome)** ⋮ menu > *Add to home screen*; **iPhone (Safari)** Share button > *Add to Home Screen*.

The app is reachable only on the home Wi-Fi, and only while the PC is on.

### For the admin: one-time setup

Steps 2 and 3 change Windows settings, so they need an **administrator** terminal (right-click Start > *Terminal (Admin)*), opened in this project folder.

1. **Install the packages** (adds Waitress and WhiteNoise):

   ```powershell
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

2. **Allow phones through Windows Firewall**, on private networks only:

   ```powershell
   New-NetFirewallRule -DisplayName "Price Tracker (port 8000)" -Direction Inbound -Protocol TCP -LocalPort 8000 -Profile Private -Action Allow
   ```

   Your home Wi-Fi must be a *Private* network: Settings > Network & internet > Wi-Fi > (your network) > *Private network*. Remove the rule later with `Remove-NetFirewallRule -DisplayName "Price Tracker (port 8000)"`.

3. **Start the app whenever Windows starts** (before anyone signs in; Windows doesn't store your password):

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\register_server.ps1
   ```

   Run it from your own account's admin terminal: the task runs as the account that registers it.

4. **Desktop icon** (normal terminal, no admin needed):

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\create_shortcut.ps1
   ```

5. **Backup folder.** The first household start creates `ui\household.env` (private and git-ignored: it holds the secret key). Open it in Notepad and set the folder, ideally outside this PC's disk, e.g. in OneDrive:

   ```
   BACKUP_DIR=C:\Users\you\OneDrive\Price Tracker backups
   ```

   Create that folder, then restart the app (restart the PC, or in Task Scheduler right-click *Price Tracker server* > *End*, then *Run*).

6. **Accounts for the family:** open http://localhost:8000/admin/ > *Users* > *Add user*, choose a username and password, save. Leave **Staff status** unticked (staff can change the shared categories and use the admin). Each person sets their favourite currency under *Preferences*.

7. **Find the PC's name** for the family: `hostname` in a terminal. The server log (`logs\server.log`) also lists every name and address it accepts.

### Backups and restore

- Every day the 17:00 check saves `db-YYYY-MM-DD.sqlite3` in `BACKUP_DIR` after checking prices, and keeps the newest 14. If the PC was off at 17:00, the next app start makes the day's backup. Problems (e.g. a missing folder) appear in `logs\daily_check.log` or `logs\server.log`; they never stop the app.
- Back up by hand: `.\.venv\Scripts\python.exe ui\manage.py backup_db`
- **Restore** a backup:
  1. Stop the app: Task Scheduler > *Price Tracker server* > *End*.
  2. `.\.venv\Scripts\python.exe ui\manage.py restore_db "C:\...\db-2026-11-09.sqlite3"` and type `yes`. Your current data is kept as `ui\db.before-restore-<time>.sqlite3`.
  3. Start it again: right-click *Price Tracker server* > *Run* (or restart the PC).

### Updating the app

After pulling new code: back up, then `.\.venv\Scripts\python.exe -m pip install -r requirements.txt` and `.\.venv\Scripts\python.exe ui\manage.py migrate`, then restart the *Price Tracker server* task. The app never changes the database structure by itself; `logs\server.log` warns if a `migrate` is due. Styles and scripts update automatically (no Ctrl+F5).

### If a phone can't connect

- Check the phone is on the home Wi-Fi (not mobile data) and the PC is on.
- Open http://localhost:8000/ on the PC. If that fails, read the end of `logs\server.log`.
- Use the PC's address instead of its name (`ipconfig` > *IPv4 Address*). To stop it changing, reserve it for the PC in your router's settings (often called *DHCP reservation*).
- Check the firewall rule (step 2) and that the Wi-Fi is a *Private* network.

Security note: the app uses plain http on the home Wi-Fi, protected by the Wi-Fi's own encryption. Don't make it reachable from the internet as it is.

## Current scope

Prices can be entered manually, or read automatically from eMAG product pages and Storia listings ("Add by link", "Check now" and the daily check). Prices are shown in each person's display currency (RON or EUR) at BNR's historical rates. Each price shows how it changed since the previous different price ("↓ 7.7%", compared in the price's own currency, so exchange-rate movement never creates an arrow), a "Lowest ever" badge, and the item page shows the lowest and highest prices; the dashboard lists this week's price changes. Comparison groups show every item on one chart in your currency, mark the cheapest option (recurring items by their per-month price, one-time purchases only with each other), warn when periods are mixed, and can be edited, deleted, or added to from an item's page. Items can be archived (hidden and no longer checked, restorable later) and, once archived, deleted permanently; single prices can be deleted from an item's history. Categories can have custom fields, including a Location shown on a map on item and comparison pages. Django's development server is for local development; review deployment settings before making the app reachable outside a trusted network.
