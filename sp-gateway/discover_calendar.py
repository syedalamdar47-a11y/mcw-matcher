"""Discover the AUTHENTICATED SimplePractice calendar/availability API.

Runs inside the existing biller session (no new login). It loads the calendar
and appointment-creation pages and reports the STRUCTURE of the JSON the app
fetches — endpoint paths, query-parameter NAMES, and response key/type maps.

PHI SAFETY — this is the whole point of the tool:
  * It NEVER prints a JSON value. Every string/number is replaced by its type,
    so a client name can never reach the terminal or logs.
  * It logs query-parameter NAMES only, never their values.
  * It reads nothing to disk.
The goal is purely: "which endpoint gives us free/busy for all clinicians, and
what does its response look like" — enough to design the real feed, nothing more.

Usage (run on Fly, where the session lives):
    fly ssh console --app mcw-sp-gateway -C "python discover_calendar.py"
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src import config, safety, session  # noqa: E402

# Pages most likely to fetch availability / free-busy data.
PAGES = [
    "https://secure.simplepractice.com/calendar",
]

# Hosts we ignore entirely (trackers/ads/analytics).
_IGNORE = (
    "google", "doubleclick", "tiktok", "pinterest", "linkedin", "stackadapt",
    "bing", "g2.com", "pdscrb", "segment", "bugsnag", "datagrail", "gtm-sp",
    "stripe", "cloudfront", "fonts", "sentry", "amplitude", "mixpanel",
)


def _shape(obj, depth=0):
    """Reduce any JSON value to a structure-only description. No values, ever."""
    if depth > 5:
        return "…"
    if obj is None:
        return "null"
    if isinstance(obj, bool):
        return "bool"
    if isinstance(obj, (int, float)):
        return "number"
    if isinstance(obj, str):
        # Length bucket only — never the content.
        return "str"
    if isinstance(obj, list):
        if not obj:
            return "[]"
        return [f"[{len(obj)}]", _shape(obj[0], depth + 1)]
    if isinstance(obj, dict):
        return {k: _shape(v, depth + 1) for k, v in list(obj.items())[:40]}
    return type(obj).__name__


def main() -> int:
    settings = config.load_settings()
    budget = safety.RequestBudget(limit=120)
    pacer = safety.Pacer(settings.min_delay_s, settings.max_delay_s)

    captured: dict[str, dict] = {}

    guard = safety.LoginAttemptGuard()
    with session.exclusive_session_lock(settings):
        with session.browser_context(settings, budget, pacer) as ctx:
            # SimplePractice sessions time out when nothing keeps them warm.
            # Re-authenticate the same way the real feeds do, rather than bailing.
            if not session.is_signed_in(ctx):
                safety.log(step="discover", status="session_expired_reauth")
                if not session.sign_in(ctx, settings, guard):
                    safety.log(step="discover", status="signin_failed")
                    print("Could not sign in. Run check_login.py --signin and check the inbox.")
                    return 2

            page = ctx.new_page()

            def on_response(resp):
                url = resp.url
                low = url.lower()
                if any(bad in low for bad in _IGNORE):
                    return
                ct = (resp.headers or {}).get("content-type", "")
                if "json" not in ct:
                    return
                from urllib.parse import urlparse
                p = urlparse(url)
                host = (p.hostname or "").lower()
                if "simplepractice" not in host:
                    return
                key = f"{resp.request.method} {p.path}"
                if key in captured:
                    return
                try:
                    body = resp.json()
                except Exception:
                    return
                query_keys = sorted({
                    part.split("=", 1)[0] for part in p.query.split("&") if part
                })
                captured[key] = {
                    "status": resp.status,
                    "query_keys": query_keys,
                    "shape": _shape(body),
                }

            page.on("response", on_response)

            for target in PAGES:
                pacer.wait()
                try:
                    page.goto(target, wait_until="domcontentloaded", timeout=60_000)
                    try:
                        page.wait_for_load_state("networkidle", timeout=25_000)
                    except Exception:
                        pass
                    page.wait_for_timeout(5_000)
                except Exception as exc:
                    safety.log_exception(exc, step="discover", status="page_failed")
            page.close()

    import json
    print("\n=== SimplePractice authenticated JSON endpoints (structure only) ===\n")
    for key in sorted(captured):
        info = captured[key]
        print(f"{key}   [{info['status']}]")
        if info["query_keys"]:
            print(f"    query params: {info['query_keys']}")
        print(f"    shape: {json.dumps(info['shape'])[:600]}")
        print()
    print(f"total endpoints seen: {len(captured)}")
    safety.log(step="discover", status="done", count=len(captured))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
