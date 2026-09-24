"""On-demand sign-in for the run-now tools.

Alam (2026-09-24): "build a system so you can log in whenever you want". Until
now a run-now tool that met an expired session stopped with exit 3 and waited
for the scheduler, which only renews the session in business hours — so at
night nothing could be checked.

This adds nothing new to HOW the gateway signs in. It calls the scheduler's
own session.refresh_session, which already:
  * uses the gateway's saved credentials (Fly secrets) — nobody types them;
  * holds the single-instance session lock (an flock the kernel releases if
    the process dies), so it can never run at the same time as the
    scheduler's sign-in — a held lock refuses instead of waiting;
  * checks first whether the saved session is still alive, and only signs in
    if it is not;
  * counts every submitted attempt before it is sent, and stops for good after
    2 consecutive failures (SimplePractice locks an account after 5), until a
    human clears it.
On top of that, it:
  * runs ONLY on the gateway machine (never from a laptop: that would be a
    second device and a second lock/counter);
  * refuses straight away when the failure ceiling is reached (needs a human);
  * lets a run-now tool trigger a sign-in at most once every 30 minutes (a
    marker file on the gateway's volume) — a busy lock does not use up the
    cooldown.
"""

from __future__ import annotations

import os
import time

from .. import safety, session

ENABLED = True
COOLDOWN_S = 30 * 60
MARKER = "on-demand-signin"
GATEWAY_APP = "mcw-sp-gateway"


def refresh_on_demand(settings) -> bool:
    """Renew the gateway's one SimplePractice session now, if allowed. True = session usable."""
    if not ENABLED:
        safety.log(step="on_demand_signin", status="disabled")
        return False
    if os.environ.get("FLY_APP_NAME") != GATEWAY_APP:
        safety.log(step="on_demand_signin", status="not_on_gateway")
        return False
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        # `fly ssh console` connects as root by default; files a root sign-in
        # writes (session, counter) would be unreadable to the scheduler, which
        # runs as `gateway`. Run the tool with: fly ssh console -u gateway -C "..."
        safety.log(step="on_demand_signin", status="run_as_gateway_user")
        return False
    if session.login_locked(settings):
        safety.log(step="on_demand_signin", status="locked_needs_human")
        return False
    marker = settings.state_dir / MARKER
    try:
        last = marker.stat().st_mtime
    except OSError:
        last = None
    wait = COOLDOWN_S - (time.time() - (last or 0.0))
    if last is not None and wait > 0:
        safety.log(step="on_demand_signin", status="cooldown", value=int(wait // 60), unit="minutes_left")
        return False
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()
    except OSError:
        safety.log(step="on_demand_signin", status="marker_unwritable")
        return False                      # no marker = no cooldown = refuse
    try:
        ok = bool(session._refresh_session_impl(settings))
    except safety.SessionBusy:
        # The scheduler is signing in right now: give the cooldown back.
        try:
            if last is None:
                marker.unlink()
            else:
                os.utime(marker, (last, last))
        except OSError:
            pass
        safety.log(step="on_demand_signin", status="busy")
        return False
    safety.log(step="on_demand_signin", status="ok" if ok else "failed")
    return ok
