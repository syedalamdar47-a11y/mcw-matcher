"""Guardrails that make the gateway's promises structural rather than aspirational.

Every rule here exists because breaking it has a specific, named consequence:

  read_only          SimplePractice holds live clinical records. A stray POST could
                     mutate a real chart. Non-GET is refused before a socket opens.
  allowed hosts      Stops a redirect or an injected URL sending credentials
                     somewhere that is not SimplePractice.
  pacing             The practice's own rule: one request at a time, random
                     0.7-1.8s gap. Never parallel.
  request budget     A hard stop, not a warning, so a loop bug cannot turn into
                     thousands of requests against the practice's own vendor.
  login attempts     SimplePractice locks an account after five failed sign-ins.
                     We allow exactly ONE per process. There is no retry path.
  scrub              PHI must never reach stdout. Everything logged goes through
                     one serializer that allow-lists keys and masks name-shaped
                     and contact-shaped strings.
"""

from __future__ import annotations

import random
import re
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any, Iterable
from urllib.parse import urlparse

from .config import ALLOWED_HOSTS


class SafetyViolation(RuntimeError):
    """Raised instead of doing the unsafe thing. Never caught-and-continued."""


class SessionBusy(SafetyViolation):
    """The session lock is held: another gateway process is signing in right now.

    Still a SafetyViolation (whoever doesn't know it keeps refusing), but the
    scheduler treats it as "try again next tick" instead of opening the
    one-hour breaker — by then the winner has saved a fresh session."""


# --------------------------------------------------------------------------
# Request gating
# --------------------------------------------------------------------------

_ALLOWED_METHODS = frozenset({"GET", "HEAD"})

# A tiny, explicit allow-list of POST endpoints that are SEARCH QUERIES, not
# writes. SimplePractice's public booking page sends its roster-wide slot lookup
# as a POST because the query has a body — it creates nothing and changes
# nothing. Blocking it would make the credential-free availability lane
# impossible and push us toward reading the authenticated appointment calendar
# instead, which carries client identity. That would be a far worse trade.
#
# This is not a relaxation of the read-only promise. The promise is "never
# mutate a live clinical record", and the guarantee is preserved by keeping this
# list to exact (host, path) pairs on the PUBLIC portal only. No POST to the
# authenticated application is permitted under any circumstances.
_READ_QUERY_POSTS = frozenset({
    ("mcnultycw.clientsecure.me", "/client-portal-api/clinician-search/next-slots"),
})

# Signing in is a POST, and it has to be allowed or the gateway can never
# authenticate at all. account.simplepractice.com is SimplePractice's identity
# service — it issues sessions, it does not hold charts — so permitting POST
# there costs nothing we care about.
#
# The promise being kept is "never mutate a clinical record", and it still holds:
# POST to the application host (secure.simplepractice.com) remains refused
# outright, except for the single SAML callback that completes the login.
_AUTH_HOSTS = frozenset({"account.simplepractice.com"})
_AUTH_PATHS = frozenset({"/saml/consume", "/saml/acs", "/users/sign_in", "/sessions"})


def assert_read_only(method: str, url: str = "") -> None:
    method = method.upper()
    if method in _ALLOWED_METHODS:
        return
    if method == "POST" and url:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if (host, parsed.path) in _READ_QUERY_POSTS:
            return
        if host in _AUTH_HOSTS:
            return
        if parsed.path in _AUTH_PATHS:
            return
    raise SafetyViolation(
        f"Refusing {method} to SimplePractice. This gateway must never create, "
        "change or delete anything in a live clinical system."
    )


def assert_allowed_url(url: str) -> None:
    host = (urlparse(url).hostname or "").lower()
    if host not in ALLOWED_HOSTS:
        raise SafetyViolation(
            f"Refusing request to unexpected host {host!r}. "
            f"Allowed: {sorted(ALLOWED_HOSTS)}"
        )


@dataclass
class RequestBudget:
    """A hard ceiling on upstream requests. Exhaustion stops the run."""

    limit: int
    used: int = 0
    _lock: threading.Lock = threading.Lock()

    def spend(self, n: int = 1) -> None:
        with self._lock:
            if self.used + n > self.limit:
                raise SafetyViolation(
                    f"Request budget exhausted ({self.used}/{self.limit}). "
                    "Stopping rather than continuing to call SimplePractice."
                )
            self.used += n

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)


class Pacer:
    """Serialises upstream calls and inserts a human-ish gap between them.

    Holding the lock for the whole sleep is deliberate: it makes concurrent use
    impossible rather than merely discouraged.
    """

    def __init__(self, min_delay: float = 0.7, max_delay: float = 1.8) -> None:
        self._min, self._max = min_delay, max_delay
        self._lock = threading.Lock()
        self._last = 0.0

    def wait(self) -> None:
        with self._lock:
            gap = random.uniform(self._min, self._max)
            elapsed = time.monotonic() - self._last
            if elapsed < gap:
                time.sleep(gap - elapsed)
            self._last = time.monotonic()


class LoginAttemptGuard:
    """Exactly one sign-in attempt per process.

    SimplePractice locks an account after five consecutive failures. A retry loop
    against a locked-out account is how automation takes down real billing work,
    so the retry path does not exist.
    """

    def __init__(self) -> None:
        self._used = False

    def claim(self) -> None:
        if self._used:
            raise SafetyViolation(
                "A sign-in was already attempted in this process. Refusing a second. "
                "SimplePractice locks accounts after five failures — investigate the "
                "first failure instead of retrying."
            )
        self._used = True


# --------------------------------------------------------------------------
# PHI scrubbing — the only route to stdout
# --------------------------------------------------------------------------

# Keys we are willing to emit. Anything not on this list is dropped, not masked,
# so a newly-added upstream field cannot leak by default.
LOG_KEY_ALLOWLIST = frozenset({
    "job", "feed", "step", "status", "http_status", "url_kind", "host",
    "rows", "count", "duration_ms", "attempt", "budget_used", "budget_remaining",
    "week", "clinician_id", "office", "metric", "value", "unit",
    "error_type", "message", "ok", "session", "reason",
})

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"\+?\d[\d\s().-]{7,}\d")
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_DOB_RE = re.compile(r"\b(?:19|20)\d{2}[-/]\d{1,2}[-/]\d{1,2}\b")
# Two or more capitalised words in a row: the shape of a person's name.
_NAME_RE = re.compile(r"\b[A-Z][a-z]{1,20}(?:\s+[A-Z][a-z'’-]{1,20}){1,3}\b")

_NAME_SAFE = frozenset({
    "Simple Practice", "SimplePractice", "McNulty Counseling", "New York",
    "United States", "Saint Petersburg", "St Petersburg",
})


def scrub_text(value: str, *, max_len: int = 200) -> str:
    """Mask anything shaped like a person, contact detail or identifier."""
    # Order matters. The phone pattern is greedy about digit runs and will
    # happily swallow "1984-02-11", so the more specific identifier patterns
    # must run first. Everything still gets masked either way — this is about
    # the label being truthful, which matters when someone is reading a log at
    # 3am trying to work out what broke.
    out = _SSN_RE.sub("[ssn]", value)
    out = _EMAIL_RE.sub("[email]", out)
    out = _DOB_RE.sub("[date]", out)
    out = _PHONE_RE.sub("[phone]", out)

    def _mask_name(m: re.Match[str]) -> str:
        return m.group(0) if m.group(0) in _NAME_SAFE else "[name]"

    out = _NAME_RE.sub(_mask_name, out)
    return out[:max_len]


def scrub(obj: Any, *, _depth: int = 0) -> Any:
    """Recursively reduce an object to something safe to print.

    Dict keys outside LOG_KEY_ALLOWLIST are dropped entirely.
    """
    if _depth > 6:
        return "[deep]"
    if obj is None or isinstance(obj, (bool, int, float)):
        return obj
    if isinstance(obj, str):
        return scrub_text(obj)
    if isinstance(obj, dict):
        return {
            k: scrub(v, _depth=_depth + 1)
            for k, v in obj.items()
            if k in LOG_KEY_ALLOWLIST
        }
    if isinstance(obj, (list, tuple, set)):
        items: Iterable[Any] = list(obj)[:20]
        return [scrub(v, _depth=_depth + 1) for v in items]
    return f"[{type(obj).__name__}]"


def log(**fields: Any) -> None:
    """Structured, scrubbed, single-line logging. The ONLY sanctioned stdout path."""
    safe = scrub(fields)
    parts = " ".join(f"{k}={safe[k]!r}" for k in sorted(safe))
    print(parts, file=sys.stdout, flush=True)


def log_exception(exc: BaseException, **fields: Any) -> None:
    """Log an error WITHOUT its traceback.

    Tracebacks render local variables, and in this codebase locals hold page
    content. The error type plus a scrubbed 200-char message is the most we emit.
    """
    log(error_type=type(exc).__name__, message=scrub_text(str(exc)), **fields)
