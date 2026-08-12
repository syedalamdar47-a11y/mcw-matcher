"""Deeper, PHI-SAFE probe of the authenticated calendar endpoints.

Answers the exact questions needed to build the free/busy engine:
  1. What is the request shape of /frontend/appointments — the fields[] and
     filter[timeRange] format the app actually sends?
  2. In the appointments response: how is a BLOCK distinguished from a client
     BOOKING? (counts only — presence of a client relationship, title null/present)
     and what attendanceStatus / thisType values occur?
  3. Can /frontend/availabilities be fetched for ALL clinicians in one call, or
     only per-clinician?
  4. Does a minimal fields[appointments]=startTime,endTime,duration request return
     times WITHOUT any client-identifying keys? (proves the times-only posture)

PHI SAFETY — enforced, not promised:
  * NEVER prints an appointment title, client name, or any string VALUE from a
    record. Only COUNTS, ENUM values (status/type), DATES, and KEY NAMES.
  * Query values that are logged are limited to dates, ids, and field lists.
Usage (on Fly, where the session lives):
    fly ssh console --app mcw-sp-gateway -C "python discover_calendar2.py"
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src import config, safety, session  # noqa: E402

CAL_URL = "https://secure.simplepractice.com/calendar"
API = "https://secure.simplepractice.com/frontend"


def main() -> int:
    settings = config.load_settings()
    budget = safety.RequestBudget(limit=120)
    pacer = safety.Pacer(settings.min_delay_s, settings.max_delay_s)
    guard = safety.LoginAttemptGuard()

    seen_requests: dict[str, dict] = {}

    with session.exclusive_session_lock(settings):
        with session.browser_context(settings, budget, pacer) as ctx:
            if not session.is_signed_in(ctx):
                if not session.sign_in(ctx, settings, guard):
                    print("Could not sign in.")
                    return 2

            page = ctx.new_page()

            def on_request(req):
                if "/frontend/appointments" in req.url or "/frontend/availabilities" in req.url:
                    from urllib.parse import urlparse, parse_qs
                    p = urlparse(req.url)
                    base = p.path
                    if base in seen_requests:
                        return
                    # Query VALUES here are dates / ids / field-lists — not PHI.
                    seen_requests[base] = {
                        "method": req.method,
                        "query": parse_qs(p.query),
                        "headers": {k: v for k, v in (req.all_headers() or {}).items()
                                    if k in ("accept", "api-version", "content-type")},
                    }

            page.on("request", on_request)

            pacer.wait()
            page.goto(CAL_URL, wait_until="domcontentloaded", timeout=60_000)
            try:
                page.wait_for_load_state("networkidle", timeout=25_000)
            except Exception:
                pass
            page.wait_for_timeout(6_000)

            # ---- 1. Report the exact request shapes the app used ----
            print("\n=== A. Request shapes the app sent ===")
            for path, info in seen_requests.items():
                print(f"\n{info['method']} {path}")
                print(f"  headers: {info['headers']}")
                for k, v in info["query"].items():
                    val = v[0] if len(v) == 1 else v
                    print(f"  {k} = {str(val)[:120]}")

            # ---- 2. Appointments semantics (counts only) ----
            appt_req = seen_requests.get("/frontend/appointments")
            if appt_req:
                # Re-issue the SAME query the app used, but ask for MINIMAL fields
                # and no client include, to (a) analyse semantics and (b) prove the
                # times-only request returns no client keys.
                from urllib.parse import urlencode
                q = {k: (v[0] if len(v) == 1 else v) for k, v in appt_req["query"].items()}
                # Keep the app's timeRange; strip client fields/includes.
                minimal = {
                    "fields[appointments]": "startTime,endTime,duration,attendanceStatus,thisType,fullDay,title,officeId",
                    "include": "",
                }
                if "filter[timeRange]" in q:
                    minimal["filter[timeRange]"] = q["filter[timeRange]"]
                url = f"{API}/appointments?" + urlencode(minimal)
                res = page.evaluate(
                    """async ([u, h]) => {
                         const r = await fetch(u, {headers: h});
                         return {status: r.status, body: r.ok ? await r.json() : null};
                       }""",
                    [url, {"accept": "application/vnd.api+json",
                           "api-version": appt_req["headers"].get("api-version", "")}],
                )
                print("\n=== B. Appointments semantics (minimal fields, counts only) ===")
                print(f"minimal-fields request HTTP {res['status']}")
                data = (res.get("body") or {}).get("data") or []
                print(f"appointment count: {len(data)}")
                statuses = Counter()
                types = Counter()
                title_present = 0
                client_rel_present = 0
                fullday = 0
                top_attr_keys = set()
                top_rel_keys = set()
                for item in data:
                    a = item.get("attributes", {}) or {}
                    r = item.get("relationships", {}) or {}
                    top_attr_keys |= set(a.keys())
                    top_rel_keys |= set(r.keys())
                    statuses[a.get("attendanceStatus")] += 1
                    types[a.get("thisType")] += 1
                    if a.get("title") not in (None, "", False):
                        title_present += 1
                    if a.get("fullDay") in (True, "true"):
                        fullday += 1
                    # a client booking has a non-empty clients/appointmentClients rel
                    for rk in ("clients", "appointmentClients", "clientCouples"):
                        d = (r.get(rk) or {}).get("data")
                        if d:
                            client_rel_present += 1
                            break
                print(f"attribute keys returned: {sorted(top_attr_keys)}")
                print(f"relationship keys returned: {sorted(top_rel_keys)}")
                print(f"distinct attendanceStatus: {dict(statuses)}")
                print(f"distinct thisType: {dict(types)}")
                print(f"with a title present: {title_present}  (blocks/bookings — NOT shown)")
                print(f"with a client relationship: {client_rel_present}  (= bookings)")
                print(f"without client rel (blocks/avail): {len(data) - client_rel_present}")
                print(f"fullDay items: {fullday}")
                # Prove no client-identifying keys leaked into a times-only request:
                leaked = top_rel_keys & {"clients", "appointmentClients", "clientCouples"}
                print(f"client relationship keys STILL present with minimal request: "
                      f"{sorted(leaked) if leaked else 'NONE (times-only is clean)'}")

            # ---- 3. Availabilities: all clinicians in one call? ----
            avail_req = seen_requests.get("/frontend/availabilities")
            print("\n=== C. Availabilities coverage ===")
            if avail_req:
                q = {k: (v[0] if len(v) == 1 else v) for k, v in avail_req["query"].items()}
                print(f"app sent clinicianId filter: {'filter[clinicianId]' in q}")
                # Try WITHOUT the clinician filter to see if all come back at once.
                from urllib.parse import urlencode
                base_q = {k: v for k, v in q.items() if not k.startswith("filter[clinicianId]")}
                url = f"{API}/availabilities?" + urlencode(base_q)
                res = page.evaluate(
                    """async ([u, h]) => {
                         const r = await fetch(u, {headers: h});
                         return {status: r.status, count: r.ok ? ((await r.json()).data||[]).length : null};
                       }""",
                    [url, {"accept": "application/vnd.api+json",
                           "api-version": avail_req["headers"].get("api-version", "")}],
                )
                print(f"availabilities WITHOUT clinician filter: HTTP {res['status']}, "
                      f"items={res['count']}  (if many, one call covers all clinicians)")
            else:
                print("availabilities was not called on the calendar page load "
                      "(may need the scheduling/availability view).")

            page.close()

    safety.log(step="discover2", status="done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
