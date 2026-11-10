"""The daily price check for every household item, run by `manage.py check_prices`.

Windows Task Scheduler starts it at 17:00 (or as soon as the PC is on after a missed
start). Each item goes through the same check_item() as the "Check now" button.
"""

import logging
import time
from datetime import timedelta

from django.utils import timezone

from tracker import rates
from tracker.backups import backup_if_configured
from tracker.checks import can_be_checked, check_item
from tracker.models import CheckAttempt, CheckRun, Item

# Skip items checked recently, so a catch-up run and the 17:00 run never double-check.
SKIP_IF_CHECKED_WITHIN = timedelta(hours=20)
PAUSE_SECONDS = 5
# An unfinished run younger than this is treated as still running.
RUN_TIMEOUT = timedelta(hours=1)

logger = logging.getLogger("tracker.daily")


class AlreadyRunning(Exception):
    """Another daily check started less than RUN_TIMEOUT ago and hasn't finished."""


def running_check(now=None):
    """The daily check currently in progress, or None."""
    now = now or timezone.now()
    return CheckRun.objects.filter(finished_at__isnull=True, started_at__gt=now - RUN_TIMEOUT).first()


def _tally(run, outcome):
    run.checked += 1
    if outcome == CheckAttempt.Outcome.OK:
        run.ok += 1
    elif outcome == CheckAttempt.Outcome.REMOVED:
        run.removed += 1
    else:
        run.attention += 1


def _record_crash(item, run, error):
    """Safety net: an unexpected error on one item is recorded, and the run moves on."""
    message = f"Unexpected error during the daily check: {type(error).__name__}: {error}"[:240]
    now = timezone.now()
    Item.objects.filter(pk=item.pk).update(status=Item.Status.ERROR, last_error=message, last_checked=now)
    CheckAttempt.objects.create(item=item, run=run, attempted_at=now,
                                outcome=CheckAttempt.Outcome.ERROR, message=message)
    return message


def _update_exchange_rates():
    """Fetch BNR's latest rates first. A failure is only a warning: prices are still checked."""
    try:
        saved = rates.import_latest_rates()
    except Exception as error:  # noqa: BLE001 - BNR being down must never stop the price checks
        logger.warning("Couldn't update exchange rates (%s); prices are still checked.", error)
    else:
        logger.info("Exchange rates updated: %d rate(s) from BNR.", saved)


def run_daily_checks(force=False, pause_seconds=PAUSE_SECONDS, sleep=time.sleep):
    """Update exchange rates, then check every household item. Returns the finished CheckRun.

    force=True also checks items checked in the last 20 hours (useful for testing).
    """
    if running_check():
        raise AlreadyRunning()
    run = CheckRun.objects.create(started_at=timezone.now())
    _update_exchange_rates()
    items = [item for item in Item.objects.select_related("owner").order_by("id") if can_be_checked(item)]
    logger.info("Daily check started: %d automatic item(s).", len(items))

    checked_any = False
    for item in items:
        if not force and item.last_checked and timezone.now() - item.last_checked < SKIP_IF_CHECKED_WITHIN:
            run.skipped += 1
            logger.info("  skipped   %s (%s): checked at %s", item.name, item.owner,
                        timezone.localtime(item.last_checked).strftime("%Y-%m-%d %H:%M"))
            continue
        if checked_any:
            sleep(pause_seconds)  # be polite: one page every few seconds
        checked_any = True
        try:
            result = check_item(item, now=timezone.now(), run=run)
            outcome, message = result.outcome, result.message
        except Exception as error:  # noqa: BLE001 - one item must never stop the others
            outcome, message = CheckAttempt.Outcome.ERROR, _record_crash(item, run, error)
            logger.exception("  CRASHED   %s (%s)", item.name, item.owner)
        _tally(run, outcome)
        logger.info("  %-9s %s (%s): %s", outcome, item.name, item.owner, message)

    run.finished_at = timezone.now()
    run.save()
    logger.info("Daily check finished: %d checked, %d OK, %d need attention, %d removed, %d skipped.",
                run.checked, run.ok, run.attention, run.removed, run.skipped)
    backup_if_configured("daily check", log=logger)  # after the prices, so today's are in it
    return run
