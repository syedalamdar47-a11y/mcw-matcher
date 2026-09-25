"""Nightly: the answered New Client callers checked directly in SimplePractice.

Keeps the FDO dashboard's sp_caller_checks table fresh (the Front Office
Scorecard's "Checked directly in SimplePractice" line and caller column). Same
code as the run-now tool src/tools/check_callers.py — the same caller list
(answered New Client menu calls in the dashboard's `calls` table), the same
SimplePractice matching (phone, exact name, couple record) and the same rows
(call ids, dates and statuses only; no names or numbers).

When: once a night, and only after tonight's sp_client_check has SUCCEEDED in
an earlier scheduler tick, so the two sweeps never run in the same tick (the
watchdog allows 30 minutes per tick) and the caller sweep does not run on a
night SimplePractice was down.

What: callers whose REAL first answered New Client call (looked up with an
extra LOOKBACK_DAYS of calls — Supabase only, no SimplePractice request) falls
in the last WINDOW_DAYS days, newest first, so a budget or time cut-off drops
the oldest callers, whose results rarely change. A failed lookup never
overwrites the last good result; eight failures in a row end the run as an
outage before anything is written. At most one re-auth per run.
"""

from __future__ import annotations

import time
from collections import Counter
from datetime import date, datetime, timedelta, timezone

from ..runner import feed
from ..safety import Pacer, RequestBudget, SafetyViolation, log
from ..tools.check_clients import SessionExpired
from . import client_check as cc

# NB: the scheduler runs feeds one at a time, in name order; the gate below does
# not rely on that order (it needs the client check to have finished in an
# EARLIER tick), but keep both names in mind if either feed is renamed.
HEALTH_FEED = "sp_caller_check"
WINDOW_DAYS = 35
LOOKBACK_DAYS = 60             # extra calls read to find each caller's real first call
RUN_DEADLINE = timedelta(minutes=20)
# One caller's worst case, twice (a re-auth retries the caller). Worst case =
# phone search + 3 name searches + 3 appointment lists + the couple re-check
# (2 base-clients searches + up to 3 couple appointment lists) = 12
# (check_callers.CALLER_MAX_REQUESTS). This feed runs on the scheduler's fixed
# per-run budget (500, never raised here): if fly logs show step='cutoff'
# reason='budget', raise budget.limit in _run like client_check does.
BUDGET_RESERVE = 24
MAX_CONSECUTIVE_ERRORS = 8
BATCH_SIZE = 200
MAX_ATTEMPTS_PER_NIGHT = 3
MIN_GAP_AFTER_CLIENT_CHECK_S = 60

_last_completed_night: date | None = None
_attempt_night: date | None = None
_attempts_tonight = 0


@feed(HEALTH_FEED, kind="authed_http", every=timedelta(minutes=30))
def sp_caller_check(settings=None, budget: RequestBudget = None, pacer: Pacer = None) -> int:
    global _last_completed_night, _attempt_night, _attempts_tonight
    from ..config import load_settings
    from ..sink import Sink

    settings = settings or load_settings()
    now_et = cc._now_et()
    night = cc._night_of(now_et)
    # Cheap gates: no request anywhere outside the night, once done tonight, or
    # until tonight's client check has succeeded in an earlier tick.
    if not cc._in_night_window(now_et) or _last_completed_night == night:
        return 0
    if cc._last_ok_night != night or time.monotonic() - cc._last_ok_monotonic < MIN_GAP_AFTER_CLIENT_CHECK_S:
        return 0
    if _attempt_night != night:
        _attempt_night, _attempts_tonight = night, 0
    _attempts_tonight += 1
    if _attempts_tonight > MAX_ATTEMPTS_PER_NIGHT:
        log(feed=HEALTH_FEED, status="gave_up_tonight", attempt=_attempts_tonight - 1)
        _last_completed_night = night
        return 0
    if not (settings.fdo_supabase_url and settings.fdo_supabase_service_key):
        log(feed=HEALTH_FEED, status="skipped", reason="fdo_supabase_not_configured")
        _last_completed_night = night
        return 0

    fdo = Sink(settings, url=settings.fdo_supabase_url, key=settings.fdo_supabase_service_key)
    matcher = Sink(settings)
    try:
        rows = _run(settings, fdo, budget, pacer, now_et)
    except Exception as exc:
        matcher.record_health(HEALTH_FEED, ok=False, note=type(exc).__name__)
        raise
    matcher.record_health(HEALTH_FEED, ok=True, rows=rows)
    _last_completed_night = night
    return rows


def _run(settings, fdo, budget: RequestBudget, pacer: Pacer, now_et: datetime) -> int:
    from ..session import cookies_from_state, refresh_session
    from ..tools.check_callers import OUTPUT_TABLE, _check, _load_callers, table_rows_of

    started = time.monotonic()
    end = now_et.date()
    window_start = end - timedelta(days=WINDOW_DAYS)
    everyone = _load_callers(settings, window_start - timedelta(days=LOOKBACK_DAYS), end)
    # real first call inside the window; newest first
    callers = sorted((c for c in everyone if c["first"] >= window_start), key=lambda c: c["first_dt"], reverse=True)
    log(feed=HEALTH_FEED, step="callers", count=len(callers))
    if not callers:
        return 0

    cookies = cookies_from_state(settings)
    refreshed = False
    if not cookies:
        refreshed = True           # this is the run's one re-auth
        if not refresh_session(settings):
            raise RuntimeError("no SimplePractice session available")
        cookies = cookies_from_state(settings)

    stamp = datetime.now(timezone.utc).isoformat()
    rows: list[dict] = []
    totals: Counter = Counter()
    errors: Counter = Counter()
    streak = 0
    left, stop_reason = 0, None
    for n, c in enumerate(callers):
        if time.monotonic() - started > RUN_DEADLINE.total_seconds():
            left, stop_reason = len(callers) - n, "deadline"
            break
        if budget.used + BUDGET_RESERVE > budget.limit:
            left, stop_reason = len(callers) - n, "budget"
            break
        try:
            try:
                row = _check(c, cookies, budget, pacer, now_et)
            except SessionExpired:
                if refreshed:
                    raise
                refreshed = True
                log(feed=HEALTH_FEED, step="caller_check", status="session_expired_reauth")
                if not refresh_session(settings):
                    raise
                cookies = cookies_from_state(settings)
                if budget.used + BUDGET_RESERVE > budget.limit:
                    left, stop_reason = len(callers) - n, "budget"
                    break
                row = _check(c, cookies, budget, pacer, now_et)
            streak = 0
        except (SessionExpired, SafetyViolation):
            raise
        except Exception as exc:  # noqa: BLE001 - one caller's bad request must not sink the run
            errors[type(exc).__name__] += 1
            streak += 1
            if streak >= MAX_CONSECUTIVE_ERRORS:
                # Every caller failing is an outage: write nothing, keep last
                # night's results, and let the scheduler retry.
                raise RuntimeError("consecutive caller checks failed; treating as an outage") from exc
            totals["error"] += 1
            continue                  # never overwrite a caller's last good result with "error"
        totals[row["first_status"]] += 1
        rows.extend(table_rows_of(c, row, stamp))

    for i in range(0, len(rows), BATCH_SIZE):
        fdo.upsert(OUTPUT_TABLE, rows[i:i + BATCH_SIZE], on_conflict="aircall_call_id")
    for status, k in sorted(totals.items()):
        log(feed=HEALTH_FEED, step="totals", metric=status, value=k)
    for name, k in sorted(errors.items()):
        log(feed=HEALTH_FEED, step="errors", error_type=name, count=k)
    if left:
        log(feed=HEALTH_FEED, step="cutoff", status="truncated", reason=stop_reason, count=left)
    log(feed=HEALTH_FEED, step="caller_check", status="ok", rows=len(rows),
        budget_used=budget.used, duration_ms=int((time.monotonic() - started) * 1000))
    return len(rows)
