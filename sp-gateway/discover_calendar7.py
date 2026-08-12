"""Two candidate fixes for attaching the clinician to CLIENT appointments,
without pulling client names. Reports which one works.

V1: add the 'clinician' RELATIONSHIP to the sparse fieldset (still times-only for
    attributes) — keeps the single bulk call.
V2: filter appointments by clinicianId (per-clinician) — we then KNOW the owner
    because we asked for it; fallback if V1 fails.

PHI-safe: attributes requested are times/status/type only; we print ids/counts.

Usage: fly ssh console --app mcw-sp-gateway -C "python discover_calendar7.py"
"""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src import config, safety, session  # noqa: E402

API = "https://secure.simplepractice.com/frontend"
HDR = {"accept": "application/vnd.api+json", "api-version": "2026-05-25"}
AIMEE = "1912048"


def clin(it):
    return ((it.get("relationships") or {}).get("clinician") or {}).get("data") or {}


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
            af = "async ([u,h]) => { const r = await fetch(u,{headers:h}); return {s:r.status, j: r.ok ? await r.json() : (await r.text()).slice(0,120)}; }"

            # V1 — clinician in the sparse fieldset
            v1 = page.evaluate(af, [f"{API}/appointments?" + urlencode({
                "filter[timeRange]": tr,
                "fields[appointments]": "startTime,endTime,attendanceStatus,thisType,clinician",
                "include": "clinician",
            }), HDR])
            print("\n=== V1: clinician in fields[appointments] ===")
            if isinstance(v1.get("j"), dict) and "data" in v1["j"]:
                d = v1["j"]["data"]
                cl = [a for a in d if a.get("attributes", {}).get("thisType") == "Appointment"]
                haveid = [a for a in cl if clin(a).get("id")]
                print(f"  HTTP {v1['s']}  total={len(d)} client={len(cl)} client-with-clinician-id={len(haveid)}")
                if cl:
                    print("  client appt relationship keys:", sorted((cl[0].get('relationships') or {}).keys()))
                if haveid:
                    print("  >>> V1 WORKS. sample clinician ids:", [clin(a).get('id') for a in haveid[:5]])
            else:
                print(f"  HTTP {v1['s']} -> {v1.get('j')}")

            # V2 — per-clinician filter for Aimee
            v2 = page.evaluate(af, [f"{API}/appointments?" + urlencode({
                "filter[timeRange]": tr,
                "filter[clinicianId]": AIMEE,
                "fields[appointments]": "startTime,endTime,attendanceStatus,thisType",
                "include": "",
            }), HDR])
            print("\n=== V2: filter[clinicianId]=Aimee ===")
            if isinstance(v2.get("j"), dict) and "data" in v2["j"]:
                d = v2["j"]["data"]
                cl = [a for a in d if a.get("attributes", {}).get("thisType") == "Appointment"]
                print(f"  HTTP {v2['s']}  total={len(d)} client={len(cl)}")
                print("  >>> V2 WORKS if client>0 (per-clinician filter returns her client appts).")
                for a in cl[:6]:
                    at = a.get("attributes", {})
                    print(f"     {(at.get('startTime') or '')[:16]} [{at.get('attendanceStatus')}] Appointment")
            else:
                print(f"  HTTP {v2['s']} -> {v2.get('j')}")
            page.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
