"""Live availability from the AUTHENTICATED SimplePractice calendar.

This is the real calendar view an FDO trusts — it reflects therapists blocking
their time, out-of-office, and existing-client appointments that the public
booking page never shows. It replaces the public lane as the availability source
while the session is healthy; the public lane stays running as the fallback.

CADENCE
  * appointments (the busy/blocked set) is the thing that changes when someone
    books, so it is polled every 30s — one bulk call covers the whole practice.
  * availabilities (each clinician's open hours) changes rarely, so it is cached
    and refreshed every 5 minutes.

PHI POSTURE (Alam's approved call, 2026-08-10)
  * appointments are fetched with TIME-ONLY fields — no title, no client fields,
    no client include. Discovery proved this returns zero client identity.
  * nothing client-level is ever parsed, logged, or written. A "block" vs a
    "booking" is distinguished only by counts/flags, never by who.

EFFICIENCY / ACCOUNT SAFETY
  * httpx with the saved session cookies — no Chromium in the 30s hot path.
  * business-hours only (no benefit at 3am, and it halves the footprint).
  * one request in flight at a time, budgeted, host-restricted, GET-only.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

from ..config import SP_APP_HOST
from ..runner import feed
from ..safety import Pacer, RequestBudget, SafetyViolation, assert_allowed_url, assert_read_only, log
from .. import calendar_engine as ce

API = f"https://{SP_APP_HOST}/frontend"
APIVER = "2026-05-25"  # observed; refreshed from the app if it ever changes
_HDR = {"accept": "application/vnd.api+json", "api-version": APIVER}

WINDOW_DAYS = 14           # how far ahead to compute openings
AVAIL_CACHE_TTL = timedelta(minutes=5)
BUSINESS_START_H = 6       # 6am ET (per Alam, 2026-08-10)
BUSINESS_END_H = 20        # 8pm ET

# Module-level cache for the slowly-changing availabilities, so the 30s loop
# only re-fetches them every AVAIL_CACHE_TTL. Persists because the scheduler
# runs the feed in one long-lived process.
_avail_cache: dict[str, Any] = {"at": None, "data": None}


class SessionExpired(RuntimeError):
    pass


def _now_et() -> datetime:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/New_York"))
    except Exception:
        # Container TZ is America/New_York, so local time is already ET.
        return datetime.now().astimezone()


def _within_business_hours(now_et: datetime) -> bool:
    return BUSINESS_START_H <= now_et.hour < BUSINESS_END_H


def _time_range(now_et: datetime) -> str:
    start = now_et.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=WINDOW_DAYS)
    return f"{start.isoformat()},{end.isoformat()}"


def _get(path_qs: str, cookies: dict[str, str], budget: RequestBudget, pacer: Pacer) -> dict:
    """Safety-checked authenticated GET. Returns parsed JSON or raises."""
    import httpx

    url = f"{API}/{path_qs}"
    assert_allowed_url(url)          # SimplePractice hosts only
    assert_read_only("GET", url)     # never anything but a read
    budget.spend()
    pacer.wait()                     # one at a time, human-paced

    with httpx.Client(timeout=30, follow_redirects=True) as client:
        resp = client.get(url, headers=_HDR, cookies=cookies)

    # A dead session redirects to the login/account host or returns HTML.
    final_host = resp.url.host or ""
    ctype = resp.headers.get("content-type", "")
    if resp.status_code in (401, 403) or "account.simplepractice.com" in final_host \
            or ("html" in ctype and "json" not in ctype):
        raise SessionExpired(f"session no longer valid (status {resp.status_code})")
    if resp.status_code >= 300:
        # SimplePractice returns a JSON validation error like
        # {"errors":[{"title":"filter[timeRange] is invalid"}]} — parameter-level,
        # no client data. Surface the titles so a 400 is diagnosable, not opaque.
        detail = ""
        try:
            errs = resp.json().get("errors") or []
            detail = "; ".join(str(e.get("title") or e.get("detail") or "")[:80] for e in errs[:3])
        except Exception:
            detail = ("html" if "html" in ctype else ctype)[:40]
        raise RuntimeError(f"calendar GET {resp.status_code}: {detail} [{path_qs.split('?')[0]}]")
    return resp.json()


def _fetch_appointments(tr: str, cookies, budget, pacer) -> list[dict]:
    qs = "appointments?" + urlencode({
        "filter[timeRange]": tr,
        # TIME ONLY plus the clinician RELATIONSHIP. The clinician field +
        # include=clinician is what attaches the owning clinician to CLIENT
        # appointments — without it, client bookings came back with no clinician
        # and were silently never subtracted, so booked times showed as free
        # (the Aug-2026 bug). It pulls the clinician id only, never client names.
        # isBusy is NOT requestable (causes "Invalid field"); busy is derived
        # from attendanceStatus in calendar_engine.
        "fields[appointments]": "startTime,endTime,duration,thisType,attendanceStatus,clinician",
        "include": "clinician",
    })
    return (_get(qs, cookies, budget, pacer).get("data")) or []


def _fetch_availabilities(tr: str, cookies, budget, pacer) -> list[dict]:
    qs = "availabilities?" + urlencode({"filter[timeRange]": tr, "include": ""})
    return (_get(qs, cookies, budget, pacer).get("data")) or []


@feed("calendar_availability", kind="authed_http", every=timedelta(seconds=30))
def calendar_availability(settings=None, budget: RequestBudget = None, pacer: Pacer = None) -> int:
    from ..config import load_settings
    from ..session import cookies_from_state, refresh_session
    from ..sink import Sink

    settings = settings or load_settings()
    now_et = _now_et()

    # Cheap gate: outside business hours we make NO SimplePractice request.
    if not _within_business_hours(now_et):
        return 0

    sink = Sink(settings)
    tr = _time_range(now_et)

    cookies = cookies_from_state(settings)
    if not cookies:
        if not refresh_session(settings):
            sink.record_health("calendar_availability", ok=False, note="no_session")
            raise RuntimeError("no SimplePractice session available")
        cookies = cookies_from_state(settings)

    def _with_refresh(fn):
        nonlocal cookies
        try:
            return fn(cookies)
        except SessionExpired:
            log(step="calendar", status="session_expired_reauth")
            if not refresh_session(settings):
                raise
            cookies = cookies_from_state(settings)
            return fn(cookies)

    appts = _with_refresh(lambda c: _fetch_appointments(tr, c, budget, pacer))

    # Availabilities: refresh at most every AVAIL_CACHE_TTL.
    cache_at = _avail_cache["at"]
    stale = cache_at is None or (now_et - cache_at) > AVAIL_CACHE_TTL
    if stale:
        avails = _with_refresh(lambda c: _fetch_availabilities(tr, c, budget, pacer))
        _avail_cache["at"] = now_et
        _avail_cache["data"] = avails
    else:
        avails = _avail_cache["data"] or []

    # Compute free slots (pure, offline-tested).
    now_utc = datetime.now(timezone.utc)
    stamp = now_utc.isoformat()
    slots_by_cid = ce.free_slots(avails, appts, now=now_utc)
    # Full 2-week grid grouped by day, for the "pick a future date" browser.
    days_by_cid = ce.free_slots_by_day(avails, appts, now=now_utc)

    if not avails:
        # Zero availability windows almost certainly means the page/shape changed
        # — fail loudly rather than blank every clinician silently.
        sink.record_health("clinician_availability", ok=False, note="empty_compute")
        raise RuntimeError("calendar produced no availability — shape may have changed")

    # CHANGE DETECTION — write ONLY the clinicians whose openings actually moved.
    #
    # Supabase Realtime is billed per message per open browser tab, and the free
    # plan has a monthly cap. Re-writing 32 rows every 30s (~1.4M messages/day
    # with a few tabs open) would blow it while telling the FDO nothing new. So
    # we compare against what is already stored and upsert only the differences —
    # which is exactly "the slot someone just booked disappeared". Freshness is
    # published separately by the single gateway_health heartbeat below (one row,
    # one message per cycle), which is what the UI reads for "checked Ns ago".
    existing = sink.fetch_existing_slots()
    roster = set(existing.keys()) | set(slots_by_cid.keys())
    changed = []
    for cid in roster:
        starts = slots_by_cid.get(cid, [])
        days = days_by_cid.get(cid, [])
        prev = existing.get(cid) or {}
        prev_starts = [s.get("start") for s in (prev.get("slots") or []) if isinstance(s, dict)]
        prev_days = prev.get("days") or []
        if starts == prev_starts and days == prev_days:
            continue  # unchanged — no write, no Realtime message
        changed.append({
            "sp_clinician_id": str(cid),
            "next_available_at": starts[0] if starts else None,
            "slots": [{"start": s, "end": None} for s in starts],
            "days": days,
            "slots_fetched_at": stamp,
            "fetched_at": stamp,
            "sp_computed_at": stamp,
        })

    if changed:
        sink.upsert("clinician_availability", changed, on_conflict="sp_clinician_id")

    # The heartbeat the Matcher UI trusts for freshness + safe-blanking. Written
    # every cycle regardless of whether any slot changed, so "checked Ns ago"
    # reflects the true 30s cadence. One row → one Realtime message per cycle.
    sink.record_health("clinician_availability", ok=True, rows=len(changed))
    log(step="calendar", status="ok", rows=len(changed),
        count=len(appts), budget_used=budget.used)
    return len(changed)
