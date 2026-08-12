"""Diagnose why a BOOKED slot shows as free. Hypothesis: appointment clinician
ids and availability clinician ids are different id spaces, so busy time never
gets subtracted from the right clinician.

PHI-safe: appointments requested time-only (start/end/status + clinician id).
No titles, no client fields. Availability is clinician working hours.

Usage (on Fly):
    fly ssh console --app mcw-sp-gateway -C "python discover_calendar4.py"
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src import config, safety, session  # noqa: E402

API = "https://secure.simplepractice.com/frontend"
HDR = {"accept": "application/vnd.api+json", "api-version": "2026-05-25"}
AIMEE = "1912048"  # Aimee Yasin's sp_clinician_id (from availability mapping)


def cid(item):
    return ((item.get("relationships") or {}).get("clinician") or {}).get("data", {}).get("id")


def main() -> int:
    settings = config.load_settings()
    budget = safety.RequestBudget(limit=60)
    pacer = safety.Pacer(settings.min_delay_s, settings.max_delay_s)
    guard = safety.LoginAttemptGuard()

    captured = {}
    with session.exclusive_session_lock(settings):
        with session.browser_context(settings, budget, pacer) as ctx:
            if not session.is_signed_in(ctx):
                if not session.sign_in(ctx, settings, guard):
                    print("sign-in failed"); return 2
            page = ctx.new_page()

            def on_request(req):
                for n in ("appointments", "availabilities"):
                    if f"/frontend/{n}" in req.url and n not in captured:
                        captured[n] = parse_qs(urlparse(req.url).query)

            page.on("request", on_request)
            pacer.wait()
            page.goto("https://secure.simplepractice.com/calendar",
                      wait_until="domcontentloaded", timeout=60_000)
            try:
                page.wait_for_load_state("networkidle", timeout=25_000)
            except Exception:
                pass
            page.wait_for_timeout(5_000)

            tr = captured.get("appointments", {}).get("filter[timeRange]", [None])[0]
            if not tr:
                now = datetime.now().astimezone()
                start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                tr = f"{start.isoformat()},{(start+timedelta(days=7)).isoformat()}"

            af = "async ([u,h]) => { const r = await fetch(u,{headers:h}); return r.ok ? await r.json() : {__e:r.status}; }"

            appts = page.evaluate(af, [f"{API}/appointments?" + urlencode({
                "filter[timeRange]": tr,
                "fields[appointments]": "startTime,endTime,attendanceStatus,thisType",
                "include": "",
            }), HDR]).get("data", [])
            avails = page.evaluate(af, [f"{API}/availabilities?" + urlencode({
                "filter[timeRange]": tr, "include": "",
            }), HDR]).get("data", [])

            appt_cids = [str(cid(a)) for a in appts if cid(a)]
            avail_cids = [str(cid(a)) for a in avails if cid(a)]
            appt_set, avail_set = set(appt_cids), set(avail_cids)

            print("\n=== CLINICIAN ID SPACES ===")
            print("appointment clinician ids (sample):", sorted(appt_set)[:6])
            print("availability clinician ids (sample):", sorted(avail_set)[:6])
            print(f"appt ids: {len(appt_set)} distinct | avail ids: {len(avail_set)} distinct")
            overlap = appt_set & avail_set
            print(f"OVERLAP: {len(overlap)} ids in BOTH")
            print(">>> If overlap is 0, that's the bug: busy never matches availability.\n")

            print(f"=== AIMEE ({AIMEE}) ===")
            aa = [a for a in appts if str(cid(a)) == AIMEE]
            av = [a for a in avails if str(cid(a)) == AIMEE]
            print(f"appointments under id {AIMEE}: {len(aa)}")
            for a in aa[:6]:
                at = a.get("attributes", {})
                print(f"   {at.get('startTime')} -> {at.get('endTime')}  "
                      f"[{at.get('attendanceStatus')}] {at.get('thisType')}")
            print(f"availability windows under id {AIMEE}: {len(av)}")
            for a in av[:4]:
                at = a.get("attributes", {})
                print(f"   {at.get('startTime')}..{at.get('endTime')} occ={at.get('occurrences')}")
            print("\nIf Aimee has a 10am appointment above but under a DIFFERENT id than her "
                  "availability, that's why 10am shows free.")
            page.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
