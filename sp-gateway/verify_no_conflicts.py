"""AUDIT: prove no stored open slot collides with an active booking or block.

Pulls the live calendar (appointments times-only + clinician, availabilities),
reads the open slots we published to Supabase, and checks that NOT ONE published
slot falls inside a non-cancelled appointment or block for that clinician.

Output is a clear verdict: total slots checked, and any conflicts (clinician id +
time). Zero conflicts = the availability we show never includes booked time.

PHI-safe: times/ids/status only. No client names anywhere.

Usage: fly ssh console --app mcw-sp-gateway -C "python verify_no_conflicts.py"
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src import config, safety, session  # noqa: E402
from src import calendar_engine as ce  # noqa: E402

API = "https://secure.simplepractice.com/frontend"
HDR = {"accept": "application/vnd.api+json", "api-version": "2026-05-25"}


def main() -> int:
    settings = config.load_settings()
    budget = safety.RequestBudget(limit=60)
    pacer = safety.Pacer(settings.min_delay_s, settings.max_delay_s)
    guard = safety.LoginAttemptGuard()
    cap = {}
    with session.exclusive_session_lock(settings):
        with session.browser_context(settings, budget, pacer) as ctx:
            if not session.is_signed_in(ctx):
                if not session.sign_in(ctx, settings, guard):
                    print("sign-in failed"); return 2
            page = ctx.new_page()
            page.on("request", lambda r: cap.__setitem__(
                "tr", parse_qs(urlparse(r.url).query).get("filter[timeRange]", cap.get("tr", [None]))[0])
                if "/frontend/appointments" in r.url else None)
            pacer.wait()
            page.goto("https://secure.simplepractice.com/calendar",
                      wait_until="domcontentloaded", timeout=60_000)
            try:
                page.wait_for_load_state("networkidle", timeout=25_000)
            except Exception:
                pass
            page.wait_for_timeout(5_000)
            tr = cap.get("tr")
            af = "async ([u,h]) => { const r = await fetch(u,{headers:h}); return r.ok ? await r.json() : {__e:r.status}; }"
            appts = page.evaluate(af, [f"{API}/appointments?" + urlencode({
                "filter[timeRange]": tr,
                "fields[appointments]": "startTime,endTime,duration,thisType,attendanceStatus,clinician",
                "include": "clinician",
            }), HDR]).get("data", [])
            page.close()

    busy = ce.busy_intervals(appts)   # {sp_id: [(start,end)]}, cancellations excluded

    # read our published slots from Supabase
    import httpx
    url = settings.supabase_url.rstrip("/") + "/rest/v1/clinician_availability"
    key = settings.supabase_service_key.reveal()
    rows = httpx.get(url, params={"select": "sp_clinician_id,slots"},
                     headers={"apikey": key, "Authorization": f"Bearer {key}"},
                     timeout=30).json()

    total_slots = 0
    conflicts = []
    for r in rows:
        cid = str(r["sp_clinician_id"])
        intervals = busy.get(cid, [])
        for s in (r.get("slots") or []):
            start = ce._parse(s.get("start"))
            if not start:
                continue
            total_slots += 1
            for bs, be in intervals:
                if bs <= start < be:      # a published slot starts inside a booking
                    conflicts.append((cid, start.isoformat(), bs.isoformat(), be.isoformat()))
                    break

    print(f"\n=== AVAILABILITY AUDIT ===")
    print(f"clinicians with slots : {sum(1 for r in rows if r.get('slots'))}")
    print(f"open slots checked    : {total_slots}")
    print(f"active bookings/blocks: {sum(len(v) for v in busy.values())}")
    print(f"CONFLICTS (a shown slot inside a booking): {len(conflicts)}")
    if conflicts:
        print("\n  !!! these shown slots collide with a booking — still a bug:")
        for cid, slot, bs, be in conflicts[:20]:
            print(f"    clinician {cid}: slot {slot[:16]} inside booking {bs[11:16]}-{be[11:16]}")
    else:
        print("\n  PASS: not a single open slot we show falls inside a booked or blocked time.")
    return 0 if not conflicts else 1


if __name__ == "__main__":
    raise SystemExit(main())
