"""Clinician availability — the PUBLIC lane. No credential is ever used here.

WHERE THIS DATA COMES FROM
MCW's SimplePractice client portal (https://mcnultycw.clientsecure.me) runs a
new-client booking flow at /request. That page is a single-page app backed by an
unauthenticated JSON API under /client-portal-api/. It is the same data any
member of the public sees when booking an appointment: clinician names,
professions, and open appointment times. It contains **no client data of any
kind** — which is exactly why availability lives on this lane rather than being
derived from the logged-in appointment calendar. Deriving it the authenticated
way would mean reading rows carrying client identity in order to compute a
number the public endpoint gives us for free.

HOW WE CALL IT
The API rejects requests without an `api-version` header, and the value is not
published. We do NOT guess it: probing a vendor's server for accepted header
values is indistinguishable from an attack, and this is the practice's own
vendor. Instead we let SimplePractice's page make its own first request and read
the headers off it — the same thing a developer does in DevTools — then reuse
those headers. That inherits whatever the app currently sends and keeps working
when they change it.

REQUEST SHAPE (two tiers, because they cost very differently)
  Tier 1  POST /clinician-search/next-slots
          ONE request covering all ~33 clinicians. Gives each one's soonest
          opening. Cheap, so it runs every cycle.
  Tier 2  GET  /slots?filter[clinicianId]&filter[cptCodeId]&filter[officeId]
                      &filter[startDate]&filter[endDate]&filter[timeZone]
          One request PER CLINICIAN, returning every open time. Expensive, so it
          runs only for clinicians whose soonest opening actually moved, plus a
          small rotating sweep so nobody's later slots go stale forever.
          filter[cptCodeId] takes the id from availability_block.cptCodeRateIds
          (verified: they are the same id space).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from ..config import SP_PORTAL_HOST
from ..runner import feed
from ..safety import log

BOOKING_URL = f"https://{SP_PORTAL_HOST}/request"

_NEXT_SLOTS_MARKER = "/clinician-search/next-slots"
_CLINICIANS_MARKER = "/client-portal-api/clinicians"

# How many clinicians may have their full slot list refreshed in one cycle.
# This is the ceiling on our load: everything else is a single request.
MAX_DETAIL_PER_CYCLE = 8
# Refresh a clinician's slot list at least this often even if nothing changed.
SLOT_MAX_AGE = timedelta(hours=2)
# How far ahead to ask for openings.
SLOT_WINDOW = timedelta(days=30)
# How many slots to keep. The card shows 4; the rest back the "show more".
SLOT_KEEP = 12


@feed("clinician_availability", kind="public", every=timedelta(minutes=10))
def clinician_availability(budget, pacer, settings=None) -> int:
    from ..config import load_settings
    from ..session import public_browser_context
    from ..sink import Sink

    settings = settings or load_settings()
    sink = Sink(settings)

    next_slots: list[dict[str, Any]] = []
    clinicians: dict[str, dict[str, Any]] = {}
    api_headers: dict[str, str] = {}
    computed_at: str | None = None

    with public_browser_context(settings, budget, pacer) as ctx:
        page = ctx.new_page()

        def on_request(req) -> None:
            # Capture the app's own headers from its first API call.
            if "client-portal-api" in req.url and not api_headers:
                try:
                    h = req.all_headers()
                except Exception:
                    return
                for k in ("accept", "api-version", "application-build-version",
                          "application-platform", "content-type"):
                    if k in h:
                        api_headers[k] = h[k]

        def on_response(response) -> None:
            url = response.url
            if _NEXT_SLOTS_MARKER not in url and _CLINICIANS_MARKER not in url:
                return
            try:
                payload = response.json()
            except Exception:
                return
            nonlocal computed_at
            if _NEXT_SLOTS_MARKER in url:
                next_slots.extend(payload.get("data") or [])
                computed_at = (payload.get("meta") or {}).get("computed_at") or computed_at
            else:
                for rec in payload.get("data") or []:
                    if rec.get("id"):
                        clinicians[str(rec["id"])] = rec.get("attributes") or {}

        page.on("request", on_request)
        page.on("response", on_response)

        pacer.wait()
        page.goto(BOOKING_URL, wait_until="domcontentloaded", timeout=60_000)
        # networkidle is best-effort: this page keeps analytics sockets open and
        # frequently never goes idle, so a timeout here is normal, not a failure.
        try:
            page.wait_for_load_state("networkidle", timeout=25_000)
        except Exception:
            log(step="availability", status="networkidle_timeout")
        page.wait_for_timeout(3_000)

        fetched_at = datetime.now(timezone.utc).isoformat()
        rows = _build_rows(next_slots, clinicians, computed_at, fetched_at)
        if not rows:
            sink.record_health("clinician_availability", ok=False, note="empty_harvest")
            raise RuntimeError(
                "Availability harvest returned no clinicians - the booking page "
                "shape has probably changed"
            )

        # Tier 2 — only for clinicians who need it.
        wanted = _select_for_detail(rows, sink)
        if wanted and not api_headers.get("api-version"):
            log(step="slots", status="skipped", reason="headers_not_captured")
        elif wanted:
            _fetch_slots(page, wanted, api_headers, pacer)

        page.close()

    # Two writes, not one. PostgREST requires every object in a bulk upsert to
    # carry identical keys, and only the handful of clinicians refreshed this
    # cycle have a new slot list. Sending mixed shapes returns a bare HTTP 400.
    #
    # Splitting also means an untouched clinician's existing slots are left
    # alone rather than being overwritten with nothing — which is what a single
    # uniform payload would have done.
    base = [{k: v for k, v in r.items() if k not in ("slots", "slots_fetched_at")}
            for r in rows]
    written = sink.upsert("clinician_availability", base,
                          on_conflict="sp_clinician_id") or len(base)

    with_slots = [
        {"sp_clinician_id": r["sp_clinician_id"],
         "slots": r["slots"],
         "slots_fetched_at": r["slots_fetched_at"]}
        for r in rows if r.get("slots_fetched_at")
    ]
    if with_slots:
        sink.upsert("clinician_availability", with_slots,
                    on_conflict="sp_clinician_id")

    sink.record_health("clinician_availability", ok=True, rows=written)
    return written


def _build_rows(next_slots, clinicians, computed_at, fetched_at) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for entry in next_slots:
        sp_id = str(entry.get("clinician_id") or "")
        if not sp_id:
            continue
        attrs = clinicians.get(sp_id, {})
        block = entry.get("availability_block") or {}
        seen[sp_id] = {
            "sp_clinician_id": sp_id,
            # A clinician's name is public professional information, not PHI.
            "sp_name": " ".join(
                p for p in (attrs.get("firstName"), attrs.get("lastName")) if p
            ) or None,
            "profession": attrs.get("globalProfessionName"),
            "next_available_at": entry.get("next_available_at"),
            "weekdays": block.get("weekdays") or [],
            "office_ids": block.get("officeIds") or [],
            "sp_computed_at": computed_at,
            "fetched_at": fetched_at,
            "_cpt": (block.get("cptCodeRateIds") or [None])[0],
            "_office": (block.get("officeIds") or [None])[0],
        }
    return list(seen.values())


def _select_for_detail(rows, sink) -> list[dict[str, Any]]:
    """Pick the few clinicians whose full slot list is worth re-fetching.

    A clinician qualifies when their soonest opening moved (so the rest of their
    list almost certainly moved too), when we have no list for them yet, or when
    their list has simply aged out. Capped per cycle so our load on
    SimplePractice stays roughly one request per clinician per couple of hours,
    not one per clinician per cycle.
    """
    existing = sink.fetch_existing_slots()
    candidates = []
    now = datetime.now(timezone.utc)
    for r in rows:
        if not r.get("next_available_at") or not r["_cpt"] or not r["_office"]:
            continue
        prev = existing.get(r["sp_clinician_id"]) or {}
        changed = prev.get("next_available_at") != r["next_available_at"]
        empty = not prev.get("slots")
        stamp = prev.get("slots_fetched_at")
        try:
            aged = not stamp or (now - datetime.fromisoformat(stamp)) > SLOT_MAX_AGE
        except Exception:
            aged = True
        if changed or empty or aged:
            candidates.append(r)

    # Oldest-refreshed first, so the rotation is fair rather than alphabetical.
    candidates.sort(key=lambda r: (existing.get(r["sp_clinician_id"], {}) or {})
                    .get("slots_fetched_at") or "")
    picked = candidates[:MAX_DETAIL_PER_CYCLE]
    log(step="slots", status="selected", count=len(picked), rows=len(candidates))
    return picked


def _fetch_slots(page, rows, headers, pacer) -> None:
    """One /slots request per clinician, in series, reusing the app's headers."""
    start = datetime.now(timezone.utc)
    end = start + SLOT_WINDOW
    stamp = start.isoformat()

    for r in rows:
        qs = {
            "filter[clinicianId]": r["sp_clinician_id"],
            "filter[cptCodeId]": str(r["_cpt"]),
            "filter[officeId]": str(r["_office"]),
            "filter[startDate]": start.isoformat().replace("+00:00", "Z"),
            "filter[endDate]": end.isoformat().replace("+00:00", "Z"),
            # Always the practice's timezone, never the machine's: this server
            # runs in UTC and the front desk is in Florida.
            "filter[timeZone]": "America/New_York",
        }
        pacer.wait()
        try:
            res = page.evaluate(
                """async ([q, h]) => {
                     const p = new URLSearchParams(q).toString();
                     const r = await fetch('/client-portal-api/slots?' + p, {headers: h});
                     if (!r.ok) return {status: r.status};
                     return {status: 200, data: await r.json()};
                   }""",
                [qs, headers],
            )
        except Exception:
            log(step="slots", status="request_failed")
            continue

        if res.get("status") != 200:
            log(step="slots", status="non_200", http_status=res.get("status"))
            continue

        spots: list[dict[str, str]] = []
        for day in (res.get("data") or {}).get("data") or []:
            for s in (day.get("attributes") or {}).get("spots") or []:
                if s.get("start"):
                    spots.append({"start": s["start"], "end": s.get("end")})
        spots.sort(key=lambda s: s["start"])
        r["slots"] = spots[:SLOT_KEEP]
        r["slots_fetched_at"] = stamp

    log(step="slots", status="fetched", count=sum(1 for r in rows if r.get("slots")))
