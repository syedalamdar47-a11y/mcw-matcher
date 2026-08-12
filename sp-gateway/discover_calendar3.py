"""Final format probe — capture-and-reuse pattern (proven in probe #2, avoids 400s).

Captures the app's OWN /frontend/appointments and /frontend/availabilities
requests, then refetches them reusing the exact query but with TIME-ONLY fields,
and prints a few full sample rows so the free/busy engine is built against real
formats.

PHI SAFETY:
  * Appointments refetched with fields[appointments]=startTime,endTime,duration,
    thisType,attendanceStatus,isBusy and NO client fields / NO include — proven
    in probe #2 to return zero client identity. Sample rows carry only times +
    the clinician relationship id, so they are safe to print in full.
  * Availabilities are clinician working-hours (staff), not client data.
  * team-members gives clinician id -> first name (staff names) for mapping.
Usage (on Fly):
    fly ssh console --app mcw-sp-gateway -C "python discover_calendar3.py"
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src import config, safety, session  # noqa: E402

CAL_URL = "https://secure.simplepractice.com/calendar"
API = "https://secure.simplepractice.com/frontend"
HDR = {"accept": "application/vnd.api+json", "api-version": "2026-05-25"}


def main() -> int:
    settings = config.load_settings()
    budget = safety.RequestBudget(limit=80)
    pacer = safety.Pacer(settings.min_delay_s, settings.max_delay_s)
    guard = safety.LoginAttemptGuard()

    captured: dict[str, dict] = {}

    with session.exclusive_session_lock(settings):
        with session.browser_context(settings, budget, pacer) as ctx:
            if not session.is_signed_in(ctx):
                if not session.sign_in(ctx, settings, guard):
                    print("Could not sign in.")
                    return 2
            page = ctx.new_page()

            def on_request(req):
                for name in ("appointments", "availabilities", "team-members"):
                    if f"/frontend/{name}" in req.url and name not in captured:
                        p = urlparse(req.url)
                        captured[name] = parse_qs(p.query)

            page.on("request", on_request)
            pacer.wait()
            page.goto(CAL_URL, wait_until="domcontentloaded", timeout=60_000)
            try:
                page.wait_for_load_state("networkidle", timeout=25_000)
            except Exception:
                pass
            page.wait_for_timeout(6_000)

            def flat(q):
                return {k: (v[0] if len(v) == 1 else v) for k, v in q.items()}

            async_fetch = """async ([u,h]) => { const r = await fetch(u,{headers:h});
                 return {status:r.status, body: r.ok ? await r.json() : (await r.text()).slice(0,200)}; }"""

            # ---- Appointments: reuse app query, override to time-only fields ----
            print("\n=== APPOINTMENTS (time-only, reused query) ===")
            if "appointments" in captured:
                q = flat(captured["appointments"])
                q = {k: v for k, v in q.items()
                     if k.startswith("filter[") or k == "filter[timeRange]"}
                q["fields[appointments]"] = "startTime,endTime,duration,thisType,attendanceStatus,isBusy"
                q["include"] = ""
                res = page.evaluate(async_fetch, [f"{API}/appointments?{urlencode(q)}", HDR])
                print("HTTP", res["status"])
                data = (res["body"] or {}).get("data", []) if isinstance(res["body"], dict) else []
                print("count:", len(data))
                for item in data[:4]:
                    print(json.dumps(item, indent=1)[:700]); print("---")
            else:
                print("appointments not captured")

            # ---- Availabilities: reuse app query verbatim ----
            print("\n=== AVAILABILITIES (reused query) ===")
            if "availabilities" in captured:
                q = flat(captured["availabilities"])
                q.pop("filter[clinicianId]", None)  # want all clinicians
                res = page.evaluate(async_fetch, [f"{API}/availabilities?{urlencode(q)}", HDR])
                print("HTTP", res["status"])
                body = res["body"] if isinstance(res["body"], dict) else {}
                data = body.get("data", [])
                print("count:", len(data))
                for item in data[:3]:
                    print(json.dumps(item, indent=1)[:1200]); print("---")
                inc = body.get("included", [])
                print("included types:", sorted({i.get("type") for i in inc}))
            else:
                print("availabilities not captured on calendar load")

            # ---- team-members: clinician id -> first name (staff, for mapping) ----
            print("\n=== TEAM-MEMBERS (id -> name map, staff) ===")
            if "team-members" in captured:
                q = flat(captured["team-members"])
                res = page.evaluate(async_fetch, [f"{API}/team-members?{urlencode(q)}", HDR])
                body = res["body"] if isinstance(res["body"], dict) else {}
                data = body.get("data", [])
                print("HTTP", res["status"], "count:", len(data))
                for item in data[:3]:
                    print(json.dumps(item, indent=1)[:300]); print("---")

            page.close()
    safety.log(step="discover3", status="done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
