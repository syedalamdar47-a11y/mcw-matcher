"""Nightly HubSpot-vs-SimplePractice client check, written to the FDO dashboard.

WHAT IT ANSWERS
  For every HubSpot contact the FDO dashboard marks "Booked" in the last 120
  days: does a SimplePractice client with that phone (or e-mail) exist, and
  what became of their first appointment on/after the HubSpot Date Booked —
  attended, no-show, cancelled, still upcoming, or never scheduled? Neither
  system can answer that on its own.

WHERE THE LOGIC LIVES
  The per-client logic is src/tools/check_clients.py — the reviewed one-off
  that was run by hand first. This feed IMPORTS it rather than re-implementing
  it, so there is exactly one place that decides what "matched" and "first
  appointment" mean. This module adds only the schedule, the two Supabase legs,
  the couple map and the per-client error isolation.

TWO SUPABASE PROJECTS
  Input (HubSpot bookings) and output (sp_client_checks) both live in the FDO
  dashboard project, which is NOT the Matcher project the rest of the gateway
  writes to. A second Sink instance is pointed at it. Health still goes to the
  Matcher project's gateway_health row, like every other feed, so there is one
  place to look for "is the gateway alive".

RUN WINDOW
  The scheduler cannot schedule a time of day, so the feed is registered every
  30 minutes and gates itself: it works only between 21:00 and 05:00 ET, and
  only once per night. The calendar feed makes no requests outside 6am–8pm ET,
  so for these ~10 minutes this feed is the only user of the session. It does
  block the single-threaded scheduler for that long — acceptable at 2am, and
  the RUN_DEADLINE keeps it well inside the 30-minute watchdog.

PHI POSTURE
  Nothing client-level is logged: only counts, fixed vocabularies and dates.
  The output rows carry the HubSpot contact id (already the dashboard's own
  key), dates, counts and vocabulary words — never a name, number, e-mail,
  note or SimplePractice id. Errors are logged by class name only, because an
  upstream message can quote a resource path.
"""

from __future__ import annotations

import json
import re
import time
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable
from urllib.parse import urlencode

from ..runner import feed
from ..safety import Pacer, RequestBudget, SafetyViolation, log
from ..tools.check_clients import (
    ET,
    LOOKAHEAD_DAYS,
    SessionExpired,
    UpstreamError,
    _attrs,
    _check_item,
    _digits,
    _get,
)

NIGHT_START_H = 21            # 9pm ET — the calendar feed has been idle since 8pm
NIGHT_END_H = 5               # 5am ET — an hour's margin before it wakes at 6am
BOOKED_WINDOW_DAYS = 120      # how far back a HubSpot "Booked" contact is re-checked
PAGE_SIZE = 1000              # PostgREST page for the contacts read
BATCH_SIZE = 200              # rows per upsert
# Live probe 2026-09-23 (src/tools/probe_couple.py): a couple record's
# grantedUsers are NOT client records (clients/<id> -> 404), so the map below
# can never link an individual to their couple. Kept for the day SimplePractice
# exposes the members; off until then so no nightly requests are spent on it.
COUPLE_MAP_ENABLED = False
COUPLE_LOOKUP_CAP = 80        # couple records fetched per run (+ up to 2 member lookups each)
COUPLE_CHUNK_DAYS = 60        # appointments are pulled in chunks this wide to build the couple map
RUN_DEADLINE = timedelta(minutes=22)   # stop starting new clients; the watchdog fires at 30
MAX_CONSECUTIVE_ERRORS = 8    # this many clients failing in a row is an outage, not bad data
SEARCH_STYLE = "digits"       # phone search spelling, proven by the one-off tool's self-test

INPUT_TABLE = "dashboard_contacts"
OUTPUT_TABLE = "sp_client_checks"
HEALTH_FEED = "sp_client_check"

# Column vocabularies of sp_client_checks. A value outside them is written as
# the neutral member (None / "error"), never passed through. In particular the
# tool's "unknown_status" (an attendanceStatus we have not seen) is not a
# column value and lands on "error".
FIRST_STATUS = frozenset({
    "attended", "no_show", "cancelled", "late_cancelled", "clinician_cancelled",
    "upcoming", "no_appointment", "not_found", "error",
})
MATCHED_BY = frozenset({"phone", "email", "couple"})
SP_STATUS = frozenset({"active", "inactive", "prospective", "other"})

_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_ID_RE = re.compile(r"[A-Za-z0-9\-]{1,64}")
_NUM_RE = re.compile(r"[0-9]{1,20}")

# The night this feed last completed. Lives in the process only, so a restart
# forgets it and the first night after a deploy always runs — the intended
# failure direction (an extra check, never a missed one).
_last_completed_night: date | None = None
# A night whose SimplePractice sweep keeps failing at the write step must not
# be swept again every 30 minutes until the breaker: three tries, then give up
# until the next night. (The breaker would allow ~9 sweeps in one night.)
MAX_ATTEMPTS_PER_NIGHT = 3
_attempt_night: date | None = None
_attempts_tonight = 0


def _now_et() -> datetime:
    return datetime.now(ET)


def _night_of(now_et: datetime) -> date:
    """The calendar date a night belongs to.

    The window straddles midnight, so 23:50 and 00:20 must count as the SAME
    night or the feed would run twice. Shifting by NIGHT_END_H makes every
    instant of one night fall on the date the night started.
    """
    return (now_et - timedelta(hours=NIGHT_END_H)).date()


def _in_night_window(now_et: datetime) -> bool:
    return now_et.hour >= NIGHT_START_H or now_et.hour < NIGHT_END_H


# --------------------------------------------------------------------------
# Input: HubSpot bookings from the FDO dashboard
# --------------------------------------------------------------------------

def _valid_date(s: str) -> bool:
    """A real calendar date, not merely date-shaped (2026-13-45 must not pass)."""
    if not _DATE_RE.fullmatch(s):
        return False
    try:
        date.fromisoformat(s)
        return True
    except ValueError:
        return False


def _load_contacts(fdo, since: date) -> tuple[list[dict], int]:
    """Contacts booked on/after `since`, reduced to exactly what the check needs.

    Returns (items, skipped). A row without a usable contact id or booking
    date cannot be reported on and is counted rather than guessed at; so is a
    repeated contact id, because two rows with one primary key in a single
    upsert make PostgREST reject the whole batch.
    """
    raw = fdo.select(INPUT_TABLE, params={
        "select": "hubspot_contact_id,phone_normalized,email,date_booked",
        "client_status": "eq.Booked",
        "date_booked": f"gte.{since.isoformat()}",
        "order": "hubspot_contact_id",
    }, page_size=PAGE_SIZE)
    items: list[dict] = []
    seen: set[str] = set()
    skipped = 0
    for r in raw:
        cid = str(r.get("hubspot_contact_id") or "").strip()
        booked = str(r.get("date_booked") or "")[:10]
        if not _ID_RE.fullmatch(cid) or not _valid_date(booked) or cid in seen:
            skipped += 1
            continue
        seen.add(cid)
        items.append({
            "i": cid,
            "ph": _digits(r.get("phone_normalized")),          # 10 digits, or "" -> e-mail only
            "em": str(r.get("email") or "").strip().lower(),
            "booked": booked,
        })
    return items, skipped


# --------------------------------------------------------------------------
# Couples: individual client id -> clientCouples id
# --------------------------------------------------------------------------

def _couple_map(start: datetime, end: datetime, cookies, budget, pacer) -> tuple[dict[str, str], Counter]:
    """Which individual clients sit in a couple that had a session in [start, end].

    There is no list or search endpoint for couples (client-couples?... is a
    404). The only way in is the `client` relationship on appointments, whose
    type is "clientCouples" for couples sessions, then the couple record's
    grantedUsers — a JSON list of two numeric ids. Whether those are the two
    member CLIENT ids was still being probed when this was written, so both
    outcomes are handled: a granted id that resolves as clients/<id> (HTTP 200)
    is mapped; a couple none of whose ids resolve is counted and skipped; and
    after two such couples in a row we stop spending requests on the rest,
    since the ids are then evidently something else (portal users, say).
    """
    stats: Counter = Counter()
    couples: list[str] = []
    t = start
    while t < end:
        u = min(t + timedelta(days=COUPLE_CHUNK_DAYS), end)
        qs = "appointments?" + urlencode({
            "filter[timeRange]": f"{t.isoformat()},{u.isoformat()}",
            "fields[appointments]": "client",     # the linkage only: no times, no names
            "include": "",
        })
        for a in (_get(qs, cookies, budget, pacer).get("data")) or []:
            dd = ((a.get("relationships") or {}).get("client") or {}).get("data") or {}
            if not isinstance(dd, dict) or dd.get("type") != "clientCouples":
                continue
            kid = str(dd.get("id") or "")
            if _ID_RE.fullmatch(kid) and kid not in couples:
                couples.append(kid)
        t = u
    stats["couples_seen"] = len(couples)

    members: dict[str, str] = {}
    unresolved_streak = 0
    for kid in couples[:COUPLE_LOOKUP_CAP]:
        if unresolved_streak >= 2:
            stats["couples_skipped"] += 1
            continue
        try:
            body = _get("client-couples/%s?%s" % (kid, urlencode(
                {"fields[clientCouples]": "grantedUsers,dateFirstVisit,status"})),
                cookies, budget, pacer)
        except UpstreamError:
            stats["couples_unreadable"] += 1
            continue
        raw = _attrs(body.get("data") or {}).get("grantedUsers")
        try:
            granted = json.loads(raw) if isinstance(raw, str) else (raw or [])
        except ValueError:
            granted = []
        granted = [str(g) for g in (granted if isinstance(granted, list) else []) if _NUM_RE.fullmatch(str(g))][:2]
        resolved = 0
        for mid in granted:
            try:
                _get("clients/%s?%s" % (mid, urlencode({"fields[clients]": "status"})),
                     cookies, budget, pacer)
            except UpstreamError:      # 404: not a client id
                continue
            members[mid] = kid
            resolved += 1
        if resolved:
            stats["couples_mapped"] += 1
            unresolved_streak = 0
        else:
            stats["couples_unresolved"] += 1
            unresolved_streak += 1
    if len(couples) > COUPLE_LOOKUP_CAP:
        stats["couples_skipped"] += len(couples) - COUPLE_LOOKUP_CAP
    return members, stats


# --------------------------------------------------------------------------
# Output rows
# --------------------------------------------------------------------------

def _table_row(it: dict, row: dict, stamp: str) -> dict[str, Any]:
    """Map the tool's result row onto the sp_client_checks columns, exactly."""
    matched_by = row.get("matched_by")
    sp_status = row.get("sp_status")
    first_status = row.get("first_status")
    return {
        "hubspot_contact_id": it["i"],
        "date_booked": it["booked"],
        "checked_at": stamp,
        "found": int(row.get("found") or 0),
        "matched_by": matched_by if matched_by in MATCHED_BY else None,
        "sp_status": sp_status if sp_status in SP_STATUS else None,
        "sp_created_month": row.get("sp_created"),
        "couple": bool(row.get("couple")),
        "ambiguous": bool(row.get("ambiguous")),
        "first_appointment": row.get("first"),
        "first_status": first_status if first_status in FIRST_STATUS else "error",
        "appointments": int(row.get("appts") or 0),
        "source": "gateway",
    }


# --------------------------------------------------------------------------
# The feed
# --------------------------------------------------------------------------

@feed(HEALTH_FEED, kind="authed_http", every=timedelta(minutes=30))
def sp_client_check(settings=None, budget: RequestBudget = None, pacer: Pacer = None) -> int:
    global _last_completed_night, _attempt_night, _attempts_tonight
    from ..config import load_settings
    from ..sink import Sink

    settings = settings or load_settings()
    now_et = _now_et()
    night = _night_of(now_et)

    # Cheap gates: outside the night window, or already done tonight, we make
    # NO request anywhere.
    if not _in_night_window(now_et) or _last_completed_night == night:
        return 0
    if _attempt_night != night:
        _attempt_night, _attempts_tonight = night, 0
    _attempts_tonight += 1
    if _attempts_tonight > MAX_ATTEMPTS_PER_NIGHT:
        log(feed=HEALTH_FEED, status="gave_up_tonight", attempt=_attempts_tonight - 1)
        _last_completed_night = night
        return 0
    if not (settings.fdo_supabase_url and settings.fdo_supabase_service_key):
        # Counted as tonight's run so this logs once per night, not every 30
        # minutes. Setting the secrets restarts the process, which resets it.
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

    started = time.monotonic()
    items, skipped = _load_contacts(fdo, now_et.date() - timedelta(days=BOOKED_WINDOW_DAYS))
    log(feed=HEALTH_FEED, step="contacts", status="ok", count=len(items))
    if skipped:
        log(feed=HEALTH_FEED, step="contacts", status="skipped_rows", count=skipped)
    if not items:
        return 0
    # Rotate the starting point nightly. Order does not matter for the result
    # (rows are keyed by contact id), but if RUN_DEADLINE ever truncates a run
    # it must not be the same tail that goes unchecked every night.
    k = _night_of(now_et).toordinal() % len(items)
    items = items[k:] + items[:k]

    # The scheduler hands every feed the same per-run ceiling. This one's work
    # is proportional to the contact list (≤5 requests each) plus the couple
    # map, so the ceiling is raised on the budget we were given — raised, not
    # replaced, so the scheduler's own budget_used log line stays truthful.
    budget.limit = max(budget.limit, 5 * len(items) + 200)

    cookies = cookies_from_state(settings)
    if not cookies:
        if not refresh_session(settings):
            raise RuntimeError("no SimplePractice session available")
        cookies = cookies_from_state(settings)
    refreshed = False

    def with_refresh(fn: Callable[[dict], Any]):
        # Same shape as the calendar feed's _with_refresh, but at most ONE
        # re-auth per run: a second expiry minutes after a fresh sign-in is a
        # real problem to surface, not something to sign in through again.
        nonlocal cookies, refreshed
        try:
            return fn(cookies)
        except SessionExpired:
            if refreshed:
                raise
            refreshed = True
            log(feed=HEALTH_FEED, step="client_check", status="session_expired_reauth")
            if not refresh_session(settings):
                raise
            cookies = cookies_from_state(settings)
            return fn(cookies)

    # Couple map, once per run. Its failure is not the run's failure: without
    # it, couples-only clients simply read "no_appointment" tonight.
    couple_of: dict[str, str] = {}
    couple_stats: Counter = Counter()
    if COUPLE_MAP_ENABLED:
        try:
            start = min(datetime.strptime(it["booked"], "%Y-%m-%d").replace(tzinfo=ET) for it in items)
            end = now_et.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=LOOKAHEAD_DAYS)
            couple_of, couple_stats = with_refresh(lambda c: _couple_map(start, end, c, budget, pacer))
        except (SessionExpired, SafetyViolation):
            raise
        except Exception as exc:  # noqa: BLE001 - class name only, never the message
            log(feed=HEALTH_FEED, step="couples", status="failed", error_type=type(exc).__name__)

    stamp = datetime.now(timezone.utc).isoformat()
    results: list[dict[str, Any]] = []
    errors: Counter = Counter()
    streak = 0
    left_unchecked = 0
    for n, it in enumerate(items):
        if time.monotonic() - started > RUN_DEADLINE.total_seconds():
            left_unchecked = len(items) - n
            break
        try:
            row = with_refresh(lambda c: _check_item(it, SEARCH_STYLE, c, budget, pacer, now_et,
                                                     couple_of=couple_of))
            streak = 0
        except (SessionExpired, SafetyViolation):
            raise
        except Exception as exc:  # noqa: BLE001 - one client's bad request must not sink the run
            errors[type(exc).__name__] += 1
            streak += 1
            if streak >= MAX_CONSECUTIVE_ERRORS:
                # Every client erroring is an outage. Writing 150 "error" rows
                # and calling the night done would hide it until tomorrow;
                # failing the run makes the scheduler retry in 30 minutes.
                raise RuntimeError("consecutive client checks failed; treating as an outage") from exc
            row = {"first_status": "error"}
        results.append(_table_row(it, row, stamp))

    for i in range(0, len(results), BATCH_SIZE):
        fdo.upsert(OUTPUT_TABLE, results[i:i + BATCH_SIZE], on_conflict="hubspot_contact_id")

    totals = Counter(r["first_status"] for r in results)
    for status, n in sorted(totals.items()):
        log(feed=HEALTH_FEED, step="totals", metric=status, value=n)
    for k, n in sorted(couple_stats.items()):
        log(feed=HEALTH_FEED, step="couples", metric=k, value=n)
    for k, n in sorted(errors.items()):
        log(feed=HEALTH_FEED, step="errors", error_type=k, count=n)
    if left_unchecked:
        log(feed=HEALTH_FEED, step="deadline", status="truncated", count=left_unchecked)
    log(feed=HEALTH_FEED, step="client_check", status="ok", rows=len(results),
        count=len(items), budget_used=budget.used,
        duration_ms=int((time.monotonic() - started) * 1000))
    return len(results)
