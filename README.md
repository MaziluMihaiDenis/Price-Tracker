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

## Current scope

Prices can be entered manually, or read automatically from eMAG product pages and Storia listings ("Add by link", "Check now" and the daily check). Prices are shown in their original currency; exchange-rate imports and currency conversion are future work. Django's development server is for local development; review deployment settings before making the app reachable outside a trusted network.
