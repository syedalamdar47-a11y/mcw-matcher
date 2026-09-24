"""Run the SimplePractice client check NOW instead of waiting for the night.

Same code as the nightly feed (src/feeds/client_check.py): same matching,
same first-appointment logic, same upsert into the FDO dashboard's
sp_client_checks table. Differences, on purpose:

  * no night-window / once-per-night gate, and the nightly schedule is left
    untouched (it still runs tonight);
  * --days N limits it to bookings from the last N days (default 30, which is
    ~150 clients and ~5-8 minutes), so a daytime run stays short;
  * by default it does not sign in: if the session has lapsed the run stops
    with exit 3 and the scheduler renews it in business hours. With --signin
    it renews the gateway's one session itself through src/tools/on_demand.py
    (the scheduler's own sign-in, under the session lock, 2-failure ceiling,
    at most once every 30 minutes) — so a check can run at any hour.

    fly ssh console --app mcw-sp-gateway -C "python -u -m src.tools.run_client_check --days 30"
    fly ssh console --app mcw-sp-gateway -C "python -u -m src.tools.run_client_check --days 30 --signin"

Prints only the feed's scrubbed log lines (counts, never names or numbers).
Exit codes: 0 ok · 1 error · 2 not configured · 3 session expired.
"""

from __future__ import annotations

import argparse
import sys

from .. import config, safety, session
from ..feeds import client_check as cc
from ..sink import Sink
from .check_clients import SessionExpired
from .on_demand import refresh_on_demand


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="run_client_check")
    ap.add_argument("--days", type=int, default=30, help="bookings from the last N days (1-120)")
    ap.add_argument("--signin", action="store_true",
                    help="if the session has expired, renew it now (gateway's own sign-in; at most once per 30 min)")
    args = ap.parse_args(argv)
    days = max(1, min(120, args.days))

    settings = config.load_settings()
    if not (settings.fdo_supabase_url and settings.fdo_supabase_service_key):
        print("FDO_SUPABASE_URL / FDO_SUPABASE_SERVICE_KEY not set — nothing to do")
        return 2

    if args.signin:
        # The feed's one re-auth goes through the guarded on-demand path
        # (session lock, 2-failure ceiling, 30-minute cooldown).
        session.refresh_session = refresh_on_demand  # type: ignore[assignment]
    else:
        # Default: no sign-in from this process — an expired session surfaces
        # as SessionExpired (exit 3) and the scheduler renews it.
        session.refresh_session = lambda _settings: False  # type: ignore[assignment]
    cc.BOOKED_WINDOW_DAYS = days
    cc.RECENT_DAYS = days

    fdo = Sink(settings, url=settings.fdo_supabase_url, key=settings.fdo_supabase_service_key)
    budget = safety.RequestBudget(limit=settings.per_run_request_budget)
    pacer = safety.Pacer(settings.min_delay_s, settings.max_delay_s)
    rows = cc._run(settings, fdo, budget, pacer, cc._now_et())
    safety.log(feed="sp_client_check", step="on_demand", status="ok", rows=rows,
               budget_used=budget.used, value=days, unit="days")
    return 0


if __name__ == "__main__":
    code = 1
    try:
        code = main(sys.argv[1:])
    except SessionExpired:
        print("SESSION EXPIRED — stopping; the scheduler will refresh it within a minute or two")
        code = 3
    except RuntimeError as exc:
        # The feed raises RuntimeError("no SimplePractice session available")
        # when cookies are missing and refresh is refused.
        print("stopped:", safety.scrub_text(str(exc)))
        code = 3 if "session" in str(exc).lower() else 1
    except safety.SafetyViolation as exc:
        print("stopped:", safety.scrub_text(str(exc)))
    except BaseException as exc:  # noqa: BLE001 — never a traceback
        print(f"stopped: {type(exc).__name__}")
    sys.exit(code)
