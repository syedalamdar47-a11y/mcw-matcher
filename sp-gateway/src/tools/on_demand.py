"""On-demand sign-in for the run-now tools.

Alam (2026-09-24): "build a system so you can log in whenever you want". Until
now a run-now tool that met an expired session stopped with exit 3 and waited
for the scheduler, which only renews the session in business hours — so at
night nothing could be checked.

This adds nothing new to HOW the gateway signs in. It calls the scheduler's
own session.refresh_session, which already:
  * uses the gateway's saved credentials (Fly secrets) — nobody types them;
  * holds the single-instance session lock, so it can never run at the same
    time as the scheduler's sign-in (a held lock refuses instead of waiting);
  * checks first whether the saved session is still alive, and only signs in
    if it is not;
  * stops for good after 2 consecutive failures (SimplePractice locks an
    account after 5), until a human clears it.
On top of that, a run-now tool may trigger it at most once every 30 minutes
(a marker file on the gateway's volume), so a loop of runs can never become a
loop of sign-ins.
"""

from __future__ import annotations

import time

from .. import safety, session

COOLDOWN_S = 30 * 60
MARKER = "on-demand-signin"
_real_refresh = session.refresh_session


# Off until the review findings of 2026-09-24 are fixed (lock race with the
# scheduler's breaker, failure counting after submit, lock left by a killed
# process, runs off the gateway, catch only a busy lock). --signin is refused.
ENABLED = False


def refresh_on_demand(settings) -> bool:
    """Renew the gateway's one SimplePractice session now, if allowed. True = session usable."""
    if not ENABLED:
        safety.log(step="on_demand_signin", status="disabled_pending_review")
        return False
    marker = settings.state_dir / MARKER
    try:
        last = marker.stat().st_mtime
    except OSError:
        last = 0.0
    wait = COOLDOWN_S - (time.time() - last)
    if wait > 0:
        safety.log(step="on_demand_signin", status="cooldown", value=int(wait // 60), unit="minutes_left")
        return False
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()
    except OSError:
        safety.log(step="on_demand_signin", status="marker_unwritable")
        return False                      # no marker = no cooldown = refuse
    try:
        ok = bool(_real_refresh(settings))
    except safety.SafetyViolation:
        # The session lock is held: the scheduler is signing in right now.
        safety.log(step="on_demand_signin", status="busy")
        return False
    safety.log(step="on_demand_signin", status="ok" if ok else "failed")
    return ok
