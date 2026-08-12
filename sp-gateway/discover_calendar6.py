"""Find how to get the clinician for a CLIENT appointment. Client appointments
come back with no clinician linkage under the current query. Try include=clinician
and dump one client appointment's relationship structure (keys + the clinician id
only — no client ids, no names).

Usage: fly ssh console --app mcw-sp-gateway -C "python discover_calendar6.py"
"""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src import config, safety, session  # noqa: E402

API = "https://secure.simplepractice.com/frontend"
HDR = {"accept": "application/vnd.api+json", "api-version": "2026-05-25"}


def clin_id(it):
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
            af = "async ([u,h]) => { const r = await fetch(u,{headers:h}); return r.ok ? await r.json() : {__e:r.status}; }"

            for label, params in [
                ("A) include=clinician", {
                    "filter[timeRange]": tr,
                    "fields[appointments]": "startTime,endTime,attendanceStatus,thisType",
                    "include": "clinician"}),
                ("B) no fields restriction, include=clinician", {
                    "filter[timeRange]": tr, "include": "clinician"}),
            ]:
                res = page.evaluate(af, [f"{API}/appointments?" + urlencode(params), HDR])
                if not isinstance(res, dict) or "data" not in res:
                    print(f"\n{label}: FAILED {res}")
                    continue
                data = res["data"]
                clients = [a for a in data if a.get("attributes", {}).get("thisType") == "Appointment"]
                with_clin = [a for a in clients if clin_id(a).get("id")]
                print(f"\n{label}: {len(data)} appts, {len(clients)} client, "
                      f"{len(with_clin)} of those now HAVE a clinician id")
                if clients:
                    rels = (clients[0].get("relationships") or {})
                    print("  a client appointment's relationship keys:", sorted(rels.keys()))
                    print("  its clinician linkage:", clin_id(clients[0]) or "(empty)")
                if with_clin:
                    print("  sample clinician ids on client appts:",
                          [clin_id(a).get("id") for a in with_clin[:5]])
                    break
            page.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
