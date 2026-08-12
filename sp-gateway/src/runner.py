"""Job runner and feed registry for the SimplePractice gateway.

The point of this module is the FEED REGISTRY. Alam's stated goal was:

    "if in future we have to import anything else from simple practice we don't
     have to do it again instead we can directly do it from the connected source"

So adding a new kind of data must be a small, isolated change — one file, one
decorator — and must NOT require touching the session, the safety rails, or the
scheduler. What is deliberately NOT provided is a generic "fetch any URL"
pass-through: that would make every future consumer a potential recipient of
client data and make "what does this system expose?" unanswerable. Adding a
CONSUMER is free; adding a FEED is a reviewed change. That asymmetry is the
design.

Two feed kinds exist, and they are kept rigorously apart:

  PUBLIC  — hits SimplePractice's unauthenticated booking API. No credential is
            ever attached. This is where Matcher availability comes from.
  AUTHED  — needs the biller session. Everything it touches may contain client
            data, so its output must be reduced to aggregates before it leaves
            the browser page.
"""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Literal

from .config import Settings, load_settings
from .safety import (
    LoginAttemptGuard,
    Pacer,
    RequestBudget,
    SafetyViolation,
    log,
    log_exception,
)

# public     — no credential, public booking API (availability fallback)
# authed      — needs the biller session in a live browser (Mothership reports)
# authed_http — needs the biller session cookies, but polls via httpx with NO
#               browser in the hot path; refreshes the session with a browser
#               only when cookies expire. This is what makes 30s calendar
#               polling affordable.
FeedKind = Literal["public", "authed", "authed_http"]


@dataclass(frozen=True)
class Feed:
    name: str
    kind: FeedKind
    interval: timedelta
    run: Callable[..., int]
    """Returns the number of aggregate rows emitted. Must never return raw rows."""


_REGISTRY: dict[str, Feed] = {}


def feed(name: str, *, kind: FeedKind, every: timedelta):
    """Register a feed.

    Adding a new import is exactly this:

        @feed("attendance_weekly", kind="authed", every=timedelta(days=1))
        def attendance_weekly(ctx, emit) -> int:
            ...
    """

    def decorator(fn: Callable[..., int]) -> Callable[..., int]:
        if name in _REGISTRY:
            raise ValueError(f"Feed {name!r} is already registered")
        _REGISTRY[name] = Feed(name=name, kind=kind, interval=every, run=fn)
        return fn

    return decorator


def registered_feeds() -> list[Feed]:
    return sorted(_REGISTRY.values(), key=lambda f: f.name)


# --------------------------------------------------------------------------
# Scheduling
# --------------------------------------------------------------------------

@dataclass
class _Slot:
    feed: Feed
    next_due: datetime
    consecutive_failures: int = 0
    # After repeated failures we stop trying rather than hammer SimplePractice.
    # A tripped breaker is a loud, visible state — not a silent retreat.
    breaker_open_until: datetime | None = None


class Scheduler:
    """A deliberately boring loop.

    No threads, no async, no parallelism. Feeds run strictly one at a time,
    which is what makes the "never more than one request in flight to
    SimplePractice" promise true by construction rather than by discipline.
    """

    MAX_FAILURES_BEFORE_BREAK = 3
    BREAKER_COOLDOWN = timedelta(hours=1)

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        now = _utcnow()
        self.slots = [_Slot(feed=f, next_due=now) for f in registered_feeds()]

    def run_forever(self) -> None:
        log(step="scheduler", status="started", count=len(self.slots))
        if not self.slots:
            log(step="scheduler", status="idle", reason="no_feeds_registered")

        # Fly sends SIGINT (then SIGTERM) on every deploy and restart. Without
        # this, the interpreter unwinds through time.sleep() and prints a
        # KeyboardInterrupt traceback on the way out. Harmless in itself, but
        # this process is built on the rule that tracebacks never reach the
        # logs — an operator who learns to scroll past a routine one will scroll
        # past a real one too.
        import signal

        stopping = False

        def _stop(signum, _frame):
            nonlocal stopping
            stopping = True
            log(step="scheduler", status="stopping", reason=f"signal_{signum}")

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, _stop)
            except (ValueError, OSError):  # pragma: no cover - non-main thread
                pass

        while not stopping:
            self.tick()
            for _ in range(15):
                if stopping:
                    break
                time.sleep(1)
        log(step="scheduler", status="stopped")

    def tick(self) -> None:
        now = _utcnow()
        for slot in self.slots:
            if slot.breaker_open_until and now < slot.breaker_open_until:
                continue
            if now < slot.next_due:
                continue
            self._run_slot(slot, now)

    def _run_slot(self, slot: _Slot, now: datetime) -> None:
        started = time.monotonic()
        budget = RequestBudget(limit=self.settings.per_run_request_budget)
        pacer = Pacer(self.settings.min_delay_s, self.settings.max_delay_s)
        try:
            rows = _execute(slot.feed, self.settings, budget, pacer)
            slot.consecutive_failures = 0
            slot.breaker_open_until = None
            log(
                feed=slot.feed.name,
                status="ok",
                rows=rows,
                budget_used=budget.used,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        except SafetyViolation as exc:
            # A safety rail fired. This is never retried away — it means the
            # code tried to do something it promised not to.
            slot.breaker_open_until = now + self.BREAKER_COOLDOWN
            log_exception(exc, feed=slot.feed.name, status="halted")
        except Exception as exc:  # noqa: BLE001 - we log a scrubbed summary, never a traceback
            slot.consecutive_failures += 1
            log_exception(
                exc,
                feed=slot.feed.name,
                status="failed",
                attempt=slot.consecutive_failures,
            )
            if slot.consecutive_failures >= self.MAX_FAILURES_BEFORE_BREAK:
                slot.breaker_open_until = now + self.BREAKER_COOLDOWN
                log(feed=slot.feed.name, status="breaker_open",
                    reason="repeated_failure")
        finally:
            slot.next_due = _utcnow() + slot.feed.interval


def _execute(f: Feed, settings: Settings, budget: RequestBudget, pacer: Pacer) -> int:
    """Run one feed, giving it only the context its kind entitles it to."""
    if f.kind == "public":
        # No credential is constructed at all for a public feed. It is not that
        # we decline to pass one — there is none in scope.
        return f.run(budget=budget, pacer=pacer)

    if f.kind == "authed_http":
        # No browser here. The feed uses saved session cookies over httpx and
        # refreshes the session with a browser itself only when they expire.
        return f.run(settings=settings, budget=budget, pacer=pacer)

    from .session import browser_context, exclusive_session_lock, is_signed_in, sign_in

    guard = LoginAttemptGuard()
    with exclusive_session_lock(settings):
        with browser_context(settings, budget, pacer) as ctx:
            if not is_signed_in(ctx):
                if not sign_in(ctx, settings, guard):
                    raise RuntimeError(
                        "SimplePractice session unavailable; feed skipped without retry"
                    )
            return f.run(context=ctx, budget=budget, pacer=pacer)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="SimplePractice gateway runner")
    ap.add_argument("--serve", action="store_true", help="run the scheduler forever")
    ap.add_argument("--once", metavar="FEED", help="run a single feed once and exit")
    ap.add_argument("--list", action="store_true", help="list registered feeds")
    args = ap.parse_args()

    settings = load_settings()

    # Importing the feeds package is what populates the registry.
    try:
        from . import feeds  # noqa: F401
    except ImportError:
        log(step="startup", status="no_feeds_module")

    if args.list:
        for f in registered_feeds():
            print(f"  {f.name:<28} kind={f.kind:<7} every={f.interval}")
        return 0

    if args.once:
        match = _REGISTRY.get(args.once)
        if not match:
            log(step="run_once", status="unknown_feed")
            return 2
        budget = RequestBudget(limit=settings.per_run_request_budget)
        pacer = Pacer(settings.min_delay_s, settings.max_delay_s)
        try:
            rows = _execute(match, settings, budget, pacer)
            log(feed=match.name, status="ok", rows=rows, budget_used=budget.used)
            return 0
        except Exception as exc:  # noqa: BLE001
            log_exception(exc, feed=match.name, status="failed")
            return 1

    Scheduler(settings).run_forever()
    return 0

# Deliberately no `if __name__ == "__main__"` block: see src/__main__.py.
# Invoke this as `python -m src`, never `python -m src.runner`.

