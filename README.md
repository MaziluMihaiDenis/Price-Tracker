# Price Tracker

A private, server-rendered household price tracker built with Django, SQLite and Bootstrap. The current app supports manual item and price entry, price history, comparison groups, and a per-user display-currency preference.

## Run locally

1. Create a virtual environment:

   ```powershell
   py -m venv .venv
   ```

2. Install the pinned application dependency:

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

## Current scope

Prices are entered manually and shown in their original currency. Saved listing URLs are references only. Website adapters, scheduled checks, exchange-rate imports and historical currency conversion are future work. Django's development server is for local development; review deployment settings before making the app reachable outside a trusted network.
