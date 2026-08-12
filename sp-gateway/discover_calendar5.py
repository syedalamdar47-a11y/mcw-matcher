"""Why are CLIENT appointments not being subtracted? Dump every appointment in
Aimee's tomorrow-midday window with its clinician id, type, and status — so we
can see whether client appointments (thisType=Appointment) are present, what
clinician id they carry, and whether that id matches her availability.

PHI-safe: times, ids, type, status ONLY. No titles, no client fields, no names.

Usage: fly ssh console --app mcw-sp-gateway -C "python discover_calendar5.py"
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src import config, safety, session  # noqa: E402
from collections import Counter

API = "https://secure.simplepractice.com/frontend"
HDR = {"accept": "application/vnd.api+json", "api-version": "2026-05-25"}
AIMEE = "1912048"


def cid(it):
    return ((it.get("relationships") or {}).get("clinician") or {}).get("data", {}).get("id")


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
            data = page.evaluate(af, [f"{API}/appointments?" + urlencode({
                "filter[timeRange]": tr,
                "fields[appointments]": "startTime,endTime,attendanceStatus,thisType",
                "include": "",
            }), HDR])
            appts = data.get("data", []) if isinstance(data, dict) else []
            meta = data.get("meta") if isinstance(data, dict) else None

            print(f"\nTOTAL appointments returned: {len(appts)}")
            print("meta (look for pagination/total):", str(meta)[:200])
            print("thisType breakdown:", dict(Counter(a.get("attributes", {}).get("thisType") for a in appts)))
            print("status breakdown:", dict(Counter(a.get("attributes", {}).get("attendanceStatus") for a in appts)))

            # everything on Aug 11 between 10:00 and 14:30 ET, any clinician
            print("\n=== Aug 11, 10:00-14:30 window (all clinicians) ===")
            n = 0
            for a in appts:
                at = a.get("attributes", {})
                st = at.get("startTime") or ""
                if st.startswith("2026-08-11") and "10:00" <= st[11:16] <= "14:30":
                    n += 1
                    print(f"  cid={str(cid(a)):<10} {st[11:16]}-{(at.get('endTime') or '')[11:16]} "
                          f"[{at.get('attendanceStatus')}] {at.get('thisType')}")
                if n > 30:
                    break

            print(f"\n=== appointments carrying Aimee's id {AIMEE} (any day) ===")
            for a in appts:
                if str(cid(a)) == AIMEE:
                    at = a.get("attributes", {})
                    print(f"  {(at.get('startTime') or '')[:16]} [{at.get('attendanceStatus')}] {at.get('thisType')}")
            page.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
