# Feature Plan: Milestone 9, Household Rollout

*Status: approved on 2026-11-09. Planning only: no code has been written yet.*
*Parent plan: [docs/PROJECT_PLAN.md](../PROJECT_PLAN.md), milestone 9 (the last one). Uses the daily task from [milestone 7](milestone-7-daily-checks.md).*

Facts are labelled **Verified** (checked on 2026-11-09), **Estimate** or **Assumption**.

---

## 1. Feature summary and user story

When the PC is switched on, the app starts by itself (before anyone signs in) and serves the household on the home Wi-Fi. A desktop icon opens it in your browser. Family members use it from their phones. The database is backed up every day to a folder you choose, with a tested way to restore it.

*As the household's admin, I want the tracker running on the home network whenever the PC is on, safely configured and backed up, so the family can use it from their phones without me starting anything.*

## 2. Scope

**In scope**
- Household mode: **Waitress**, development mode **off**, a real secret key, **WhiteNoise** for styles and scripts.
- Starting at boot: a Task Scheduler task at Windows startup, **without storing a password** (S4U), registered by you as administrator.
- A "Price Tracker" desktop icon that opens the app (starting it first if needed).
- Daily backups to a chosen folder (e.g. OneDrive), keeping 14 days, plus a restore command.
- README instructions: connecting a phone, adding to the home screen, family accounts, the firewall rule, backup and restore.

**Out of scope:** https and internet access (home Wi-Fi only), GitHub code backup (answer 5.B), an invite page, another database, a real Windows service tool.

## 3. Requirements and acceptance criteria

**Household mode** (only when started by the server script; development unchanged)
- Development mode off: plain error pages, never internal details.
- Secret key generated once (random) into the git-ignored `ui/household.env`; never shown or committed; logins survive restarts.
- Allowed addresses: `localhost`, `127.0.0.1`, the PC's network name and current local addresses, detected at start.
- WhiteNoise with version-stamped file names (browsers fetch new versions after updates).
- Server log in `logs/server.log` (1 MB, 3 kept).

**Starting at boot**
- `scripts/register_server.ps1` (**you run it as administrator**) creates the task "Price Tracker server": starts at Windows startup, under your account, S4U ("run whether signed in or not, without storing a password": only this PC's resources; local files, the port and internet work), restarts up to 3 times, no time limit. The 17:00 task stays as it is.

**Firewall** (security setting: **you** run it as administrator; README gives the command): allow inbound port **8000** on **private** networks only; README shows how to check the Wi-Fi is "Private".

**Desktop icon**
- `scripts/create_shortcut.ps1` creates "Price Tracker" on the desktop. Clicking it: if `http://localhost:8000` answers, open the dashboard; otherwise start the server in the background, wait up to 20 s, then open it, or show a short message pointing to `logs/server.log`. Never a second server.

**Backups**
- `BACKUP_DIR` in `ui/household.env` (README: OneDrive example).
- `backup_db`: safe copy while running (SQLite backup function), `PRAGMA integrity_check`, named `db-2026-11-09.sqlite3`, keeps the 14 newest.
- Automatic: after the 17:00 daily check; catch-up at server start if no backup today.
- Failures (missing folder, full disk) only warn; never stop checks or the server.
- `restore_db <file>`: checks the backup, saves the current database as `db.before-restore-<time>.sqlite3`, copies the backup in. README: stop the server task, restore, start it again.

**README:** family (address, signing in, "Add to home screen" on Android/iPhone, own items only); admin (accounts in `/admin/`, family members **not** staff, firewall and Private network, registering tasks, backup/restore, phone can't connect → IP fallback and router reservation).

**Acceptance criteria**
1. Household mode: styles, scripts and maps load; an unknown address shows a plain "Not found"; the dev secret key is never used.
2. The secret key file is created once and reused after a restart (you stay signed in); it doesn't appear in `git status`.
3. The PC's name and local address are accepted; an unknown host name is refused (HTTP 400).
4. A backup is written to the chosen folder, passes the integrity check, only 14 kept; a missing folder only warns.
5. The daily check makes a backup after the prices; a server start with no backup today makes one.
6. Restoring brings back the backup's data and keeps a safety copy of the previous database.
7. The desktop icon opens the app when running, starts it and opens it when not, never starts a second server.
8. After a reboot the server is up before anyone signs in *(checked by you)*.
9. A family member's phone on the Wi-Fi can open the app, sign in and add an item *(project plan test, checked by you)*.
10. All existing tests pass; `runserver` development works as before.

## 4. Current architecture (Verified)

| What | Where | Relevance |
|---|---|---|
| `DEBUG` on by default; `SECRET_KEY` dev fallback; `ALLOWED_HOSTS` from settings | `ui/app/settings.py` | Household mode sets them |
| Only Django `staticfiles`; no WhiteNoise | `settings.py` | Styles would break with DEBUG off |
| Packages: Django, httpx, beautifulsoup4 | `requirements.txt` | Add Waitress, WhiteNoise |
| Daily task: `pythonw`, log file, only while signed in | `scripts/register_daily_check.ps1`, `check_prices` | Backups attach here; task unchanged |
| SQLite single file; `.gitignore` covers `db.backup-*`, `logs/`, `staticfiles/`, `.env` | `settings.py`, `.gitignore` | Safe backups; new ignored files fit |
| Project plan chose Waitress for M9 | `docs/PROJECT_PLAN.md` | No new architecture decision |

## 5. Proposed solution

```
Windows starts
  └─ Task "Price Tracker server" (S4U, no password stored)
       └─ pythonw scripts/serve.py
            ├─ reads ui/household.env (creates the secret key on first run)
            ├─ household mode: DEBUG off, allowed addresses, WhiteNoise versioned files
            ├─ collectstatic
            ├─ catch-up backup if none today
            └─ Waitress on 0.0.0.0:8000 → phones on the Wi-Fi

Desktop icon → pythonw scripts/open_app.pyw
  ├─ server answers? → open the browser
  └─ no → start serve.py in the background, wait ≤ 20 s, open the browser (or a message)

17:00 task → check_prices → prices → backup_db (if BACKUP_DIR set)
```

- Household mode is switched on only by `serve.py` (an environment variable read by `settings.py`), so `runserver` and the tests (which run with DEBUG off) keep working; versioned static names apply only in household mode.
- Backup/restore use Python's built-in `sqlite3` backup function.
- No Windows settings are changed by the implementation: the boot task and firewall rule are set up by you.

## 6. Technologies

| What | New? | Notes |
|---|---|---|
| Waitress | New package | Pure-Python server for Windows (project plan). Pinned at implementation **with your OK to install** |
| WhiteNoise | New package | Static files with versioned names. Same approval |
| `sqlite3`, `secrets`, `socket`, `webbrowser` | Built in | Backups, key, addresses, browser |
| Task Scheduler (S4U), Windows Firewall | Windows | Set up by you as administrator |

Architectural gate not triggered (Waitress approved in the project plan; database and accounts unchanged).

## 7. Files likely to change

| File | Change |
|---|---|
| `requirements.txt` | Pinned `waitress`, `whitenoise` |
| `ui/app/settings.py` | Household mode (env file, DEBUG off, hosts, WhiteNoise in household mode) |
| `ui/tracker/household.py` | **New**: key file, settings loading, addresses, backup/restore |
| `ui/tracker/management/commands/backup_db.py`, `restore_db.py` | **New** |
| `ui/tracker/management/commands/check_prices.py` | Backup after checks |
| `scripts/serve.py` | **New** |
| `scripts/open_app.pyw` | **New** |
| `scripts/register_server.ps1`, `scripts/create_shortcut.ps1` | **New** (run by you) |
| `.gitignore` | `ui/household.env` |
| Tests | **New** `test_household.py`; daily-check backup test |
| `README.md`, `docs/PROJECT_PLAN.md` | Household section; M9 status; open question 2 ("not now") |

## 8. Ordered tasks

| # | Task | Depends on |
|---|---|---|
| 1 | Install Waitress and WhiteNoise (**with your OK**), pin them | – |
| 2 | `household.py` + settings + tests (criteria 1–3, 10) | 1 |
| 3 | `backup_db`, `restore_db`, backup after `check_prices` + tests (criteria 4–6) | 2 |
| 4 | `serve.py` (Waitress, collectstatic, catch-up backup, log) | 2, 3 |
| 5 | `open_app.pyw`, `create_shortcut.ps1` + tests (criterion 7) | 4 |
| 6 | `register_server.ps1` (S4U, startup, restarts) | 4 |
| 7 | README and docs | all |
| 8 | Local trial on a database copy (via the PC's name, backup and restore); then **you**: firewall, task, reboot, phone (criteria 8, 9) | all |

Rollback: `Unregister-ScheduledTask -TaskName "Price Tracker server" -Confirm:$false`; remove the firewall rule with `Remove-NetFirewallRule`; development mode untouched; restore always keeps a safety copy. **Estimate:** 6–8 hours plus about 15 minutes on your side.

## 9. Testing

- Automated (`test_household.py`): key created once and reused; household settings (DEBUG off, hosts, unknown host refused); plain 404; backup (copy, integrity, 14 kept, missing folder warns); restore (data back, safety copy); `check_prices` backup; icon's "already running" check.
- Commands: `manage.py test tracker`, `manage.py check`, `manage.py check --deploy` in household mode (http-only warnings expected and listed).
- Manual (me): `serve.py` on a database copy via the PC's name; backup and restore.
- Manual (you): firewall, task, reboot, phone.

## 10. Risks

| Risk | Mitigation |
|---|---|
| Error pages leak details | DEBUG off in household mode; tested |
| Secret key in Git | Git-ignored, auto-created, never printed; tested |
| Anyone on the Wi-Fi reaches the login page | Accounts required; firewall private networks only; family non-staff |
| Password readable on the network | Plain http protected by Wi-Fi encryption; accepted for home use |
| Broken backup | SQLite backup + integrity check; restore re-checks and keeps a safety copy |
| Backups on the same disk | Chosen folder (OneDrive) |
| PC address changes | PC name; README fallback and router reservation |
| Boot task rights | S4U, your account, normal rights, no stored password, registered by you |

## 11. Assumptions and open questions

- **Verified:** settings behaviour, packages, `.gitignore`, daily task, Waitress in the project plan.
- **Assumptions:** the Wi-Fi is or can be "Private"; phones resolve the PC name (else IP fallback); an S4U task can listen on port 8000 and reach the internet (confirmed after a reboot).
- Open questions: none.

## 12. Decisions

| Decision | Status |
|---|---|
| Server at boot (S4U) + desktop icon; WhiteNoise; daily backups to a chosen folder; admin-created accounts; no GitHub for now | Approved |
| Waitress and WhiteNoise installed with your OK at implementation | Part of this plan |
| Boot task and firewall rule set up by you | Part of this plan |
| The M9 plan as a whole | **Approved 2026-11-09** |

## 13. What success looks like

You turn the PC on and walk away. A few minutes later your partner opens "Price Tracker" from their phone's home screen, signs in and sees their own items with arrows, maps and charts. On the PC, the desktop icon opens the dashboard. Every evening a dated backup appears in your OneDrive folder, and restoring one is three documented steps.
