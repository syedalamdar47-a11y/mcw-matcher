"""Browser session management for the SimplePractice gateway.

Two design decisions here are load-bearing for the PHI boundary:

1. NO PERSISTENT BROWSER PROFILE. Playwright's launch_persistent_context() keeps
   a Chromium profile directory on disk, and Chromium caches the pages and JSON
   responses it fetches into it. That would put client-level data at rest on the
   server — and inside every backup snapshot — without a single line of our code
   ever writing it. Instead we launch a throwaway browser with its cache disabled
   and restore only cookies via storage_state.

2. THE SAVED SESSION IS ENCRYPTED AT REST. storage_state contains live session
   cookies: anyone holding the file can act as the biller account until it
   expires. It is encrypted with SP_SESSION_KEY and written with an atomic
   replace so a crash cannot leave a half-written (or plaintext) file behind.

Only one process may hold the session at a time — enforced with an exclusive
lock file rather than left to convention.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlparse

from .config import ALLOWED_HOSTS, SP_APP_HOST, SP_LOGIN_HOST, Settings
from .safety import (
    LoginAttemptGuard,
    Pacer,
    RequestBudget,
    SafetyViolation,
    SessionBusy,
    assert_read_only,
    log,
)

LOGIN_URL = f"https://{SP_LOGIN_HOST}/"
STATE_FILENAME = "sp-session.enc"
LOCK_FILENAME = "sp-session.lock"
LOGIN_FAIL_FILENAME = "login-failures"
# Stop attempting well before SimplePractice's 5-consecutive-failure account
# lockout. A bad/rotated password, or a Sift device challenge, would otherwise
# make the feed retry a sign-in every cycle and march the account into a real
# lockout that also takes down billing work. This counter persists across cycles
# AND process restarts. Every submitted password is counted BEFORE it is sent;
# only a confirmed sign-in clears it. At the ceiling nothing signs in until a
# human reads the biller inbox, then deletes the file and runs one sign-in —
# BOTH as the gateway user (as root the files end up unreadable to the scheduler):
#   fly ssh console -a mcw-sp-gateway -u gateway -C "rm /data/login-failures"
#   fly ssh console -a mcw-sp-gateway -u gateway -C "python check_login.py --signin"
MAX_LOGIN_FAILURES = 2


def _login_fail_path(settings: Settings) -> Path:
    return settings.state_dir / LOGIN_FAIL_FILENAME


def login_failure_count(settings: Settings) -> int:
    """Consecutive failed sign-ins on record. Fails CLOSED: a counter file that
    exists but can't be read or parsed counts as the ceiling."""
    try:
        raw = _login_fail_path(settings).read_text()
    except FileNotFoundError:
        return 0
    except Exception:
        return MAX_LOGIN_FAILURES
    try:
        # An empty file only happens if a write was cut short — fail closed.
        return int(raw.strip())
    except ValueError:
        return MAX_LOGIN_FAILURES


def login_locked(settings: Settings) -> bool:
    """True once we've hit the consecutive-failure ceiling. Refuse to sign in."""
    return login_failure_count(settings) >= MAX_LOGIN_FAILURES


def _bump_login_failure(settings: Settings) -> bool:
    """Add one to the failure counter. True only when the new value is on disk —
    sign_in refuses to submit a password it could not count."""
    try:
        p = _login_fail_path(settings)
        n = login_failure_count(settings)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(str(n + 1))
        return login_failure_count(settings) == n + 1
    except Exception:
        return False


def clear_login_failures(settings: Settings) -> None:
    try:
        _login_fail_path(settings).unlink(missing_ok=True)
    except Exception:
        pass

# Chromium flags that keep fetched content out of the filesystem.
_NO_DISK_CACHE_ARGS = [
    "--disable-application-cache",
    "--disable-back-forward-cache",
    "--disk-cache-size=1",
    "--media-cache-size=1",
    "--disable-gpu-shader-disk-cache",
    # Containers default to a 64MB /dev/shm, which Chromium exhausts and then
    # crashes tabs. Fly's config exposes no shm knob, so redirect shared memory
    # to /tmp instead.
    "--disable-dev-shm-usage",
    # No crash dumps: a Chromium minidump contains process memory, and this
    # process's memory holds page content.
    "--disable-breakpad",
    "--no-first-run",
]


# --------------------------------------------------------------------------
# Encryption of the saved session
# --------------------------------------------------------------------------

def _fernet(settings: Settings):
    try:
        from cryptography.fernet import Fernet  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise SafetyViolation(
            "The 'cryptography' package is required to store the SimplePractice "
            "session safely. Install it (pip install cryptography) — the session "
            "will not be written in plaintext."
        ) from exc
    if not settings.session_key:
        raise SafetyViolation(
            "SP_SESSION_KEY is not set. The saved session contains live login "
            "cookies and is never written unencrypted. Generate one with:\n"
            "  python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\""
        )
    return Fernet(settings.session_key.reveal().encode())


def save_state(settings: Settings, state: dict[str, Any]) -> Path:
    settings.state_dir.mkdir(parents=True, exist_ok=True)
    target = settings.state_dir / STATE_FILENAME
    blob = _fernet(settings).encrypt(json.dumps(state).encode("utf-8"))
    # Atomic replace: never leave a partial file that a reader might trust.
    fd, tmp = tempfile.mkstemp(dir=str(settings.state_dir), suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(blob)
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    try:
        os.chmod(target, 0o600)
    except OSError:
        pass  # best effort on Windows
    return target


def load_state(settings: Settings) -> dict[str, Any] | None:
    target = settings.state_dir / STATE_FILENAME
    if not target.exists():
        return None
    try:
        return json.loads(_fernet(settings).decrypt(target.read_bytes()).decode("utf-8"))
    except SafetyViolation:
        raise
    except Exception:
        # A corrupt or key-mismatched session is not an error worth crashing on;
        # it just means we sign in again.
        log(step="load_state", status="unreadable", reason="discarded")
        return None


# --------------------------------------------------------------------------
# Single-instance lock
# --------------------------------------------------------------------------

def clear_stale_lock_at_boot(settings: Settings) -> None:
    """Remove a lock file left behind by a force-killed predecessor.

    Called ONLY at --serve startup. At that moment this container has just
    booted, so no process in it can legitimately hold the lock: the volume
    attaches to exactly one machine, and a machine restart kills every process
    in the container together. A lock created by the previous container whose
    process died between lock-create and cleanup (e.g. the hung process that
    was force-killed on 2026-08-31) is therefore always stale here. Left in
    place it blocks every sign-in with a SafetyViolation until a human deletes
    it over ssh — which is how a 30-second restart becomes a day-long outage.
    """
    lock_path = settings.state_dir / LOCK_FILENAME
    try:
        if lock_path.exists():
            lock_path.unlink()
            log(step="startup", status="cleared_stale_lock")
    except Exception:
        log(step="startup", status="stale_lock_not_cleared")


# A sign-in takes a minute or two. A lock older than this belongs to a process
# that hung or died without cleaning up.
LOCK_STALE_AFTER_S = 30 * 60


def _lock_is_stale(lock_path: Path) -> bool:
    """True when the lock file's holder is gone (or has held it absurdly long)."""
    try:
        age = time.time() - lock_path.stat().st_mtime
    except FileNotFoundError:
        return True
    if age > LOCK_STALE_AFTER_S:
        return True
    if os.name == "posix":          # os.kill(pid, 0) would TERMINATE a process on Windows
        try:
            pid = int(lock_path.read_text().strip())
        except (OSError, ValueError):
            return False            # can't tell yet: treat as held
        if pid <= 0:
            return True
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True             # the holder is dead (killed tool, dropped ssh)
        except OSError:
            return False            # alive, e.g. owned by another user
        return False
    return False


@contextmanager
def exclusive_session_lock(settings: Settings) -> Iterator[None]:
    """One process at a time may drive a SimplePractice sign-in.

    An O_EXCL lock file that is DELETED after use, so no long-lived file can end
    up owned by the wrong user (run-now tools connect over ssh as root; the
    scheduler runs as `gateway`). A lock whose holder died — a killed tool, a
    dropped ssh session — or that is older than LOCK_STALE_AFTER_S is cleared
    and taken over once. A held lock raises SessionBusy (a SafetyViolation the
    scheduler retries on its next tick instead of opening its breaker).
    """
    settings.state_dir.mkdir(parents=True, exist_ok=True)
    lock_path = settings.state_dir / LOCK_FILENAME
    fd = None
    for attempt in (1, 2):
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            break
        except FileExistsError as exc:
            if attempt == 1:
                try:
                    seen = lock_path.stat()
                except FileNotFoundError:
                    continue            # released meanwhile: just try again
                if _lock_is_stale(lock_path):
                    # Remove it only if it is still the SAME stale file — never
                    # a lock another contender took over a moment ago.
                    try:
                        now_st = lock_path.stat()
                        if (now_st.st_ino, now_st.st_mtime_ns) == (seen.st_ino, seen.st_mtime_ns):
                            lock_path.unlink()
                            log(step="session_lock", status="cleared_stale")
                    except OSError:
                        pass
                    continue
            raise SessionBusy(
                f"Another gateway process holds the SimplePractice session ({lock_path}). "
                "Only one may sign in at a time."
            ) from exc
    me = str(os.getpid())
    try:
        os.write(fd, me.encode())
        os.close(fd)
        yield
    finally:
        # Release only OUR lock: if ours was judged stale and taken over, the
        # file now belongs to someone else and must stay.
        try:
            if lock_path.read_text().strip() == me:
                lock_path.unlink()
        except OSError:
            pass


# --------------------------------------------------------------------------
# Browser + request gating
# --------------------------------------------------------------------------

def _host_allowed(host: str, resource_type: str) -> bool:
    """Which hosts may be contacted, by request kind.

    Documents and data (xhr/fetch) are restricted to SimplePractice: those are
    the requests that carry our session and return practice data, so they must
    never reach a third party.

    Passive page assets — scripts, styles, fonts, images — are allowed to load
    from wherever SimplePractice's own login page references them. This is
    deliberate: the sign-in page populates a hidden ``user[encrypted_device]``
    fingerprint and is fronted by fraud detection. Blocking those scripts makes
    the browser look *less* like a normal one and raises the risk of a
    step-up challenge or a lockout. The login page is pre-authentication and
    carries no practice data, so letting its assets load costs us nothing.
    """
    if host in ALLOWED_HOSTS:
        return True
    return resource_type in ("script", "stylesheet", "font", "image", "media", "other")


def _install_request_guard(context, budget: RequestBudget, pacer: Pacer) -> None:
    """Enforce read-only + allow-listed hosts + pacing at the network layer.

    Doing this as a route handler rather than at each call site means a future
    contributor cannot accidentally bypass it.
    """

    def handler(route, request):
        url = request.url
        if url.startswith(("data:", "blob:", "about:")):
            return route.continue_()
        from urllib.parse import urlparse

        host = (urlparse(url).hostname or "").lower()
        # Navigations (resource_type "document") are allowed to POST.
        #
        # Signing in is a chain of form POSTs and redirects between
        # account.simplepractice.com and secure.simplepractice.com, and the
        # exact callback paths are SimplePractice's business and change without
        # notice. Maintaining an allow-list of them was a losing game: each
        # missing path silently half-completed the login.
        #
        # The promise still holds, because the promise was never about the
        # browser's redirect handshake. Our code changes data only by calling an
        # API, and every such call is an xhr/fetch — which is still refused
        # unless explicitly allow-listed as a read query.
        is_navigation = request.resource_type == "document"
        if not is_navigation:
            try:
                assert_read_only(request.method, url)
            except SafetyViolation:
                log(step="request_blocked", reason="non_get", host=host)
                return route.abort()

        if not _host_allowed(host, request.resource_type):
            log(step="request_blocked", reason="host_not_allowed", host=host,
                url_kind=request.resource_type)
            return route.abort()
        # Count, but never sleep, here.
        #
        # This handler runs on Playwright's driver loop. Blocking it — as an
        # earlier version did by calling pacer.wait() — stalls the browser's
        # whole request pipeline, so a page that needs ~50 subresources quietly
        # delivers one and then hangs. The symptom is an empty harvest that
        # looks exactly like "the vendor changed their page".
        #
        # Politeness belongs at the level of deliberate actions we take (one
        # navigation, one API interaction), not at the level of subresources the
        # browser fetches to render a single page. Feeds call pacer.wait()
        # themselves before each navigation.
        if request.resource_type in ("document", "xhr", "fetch"):
            try:
                budget.spend()
            except SafetyViolation:
                log(step="request_blocked", reason="budget_exhausted")
                return route.abort()
        return route.continue_()

    context.route("**/*", handler)


@contextmanager
def browser_context(settings: Settings, budget: RequestBudget, pacer: Pacer) -> Iterator[Any]:
    """Yield a Playwright BrowserContext with guards installed and no disk cache."""
    from playwright.sync_api import sync_playwright

    state = load_state(settings)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=settings.headless, args=_NO_DISK_CACHE_ARGS)
        try:
            context = browser.new_context(
                storage_state=state,
                locale="en-US",
                timezone_id="America/New_York",
                viewport={"width": 1440, "height": 900},
            )
            _install_request_guard(context, budget, pacer)
            try:
                yield context
            finally:
                context.close()
        finally:
            browser.close()


@contextmanager
def public_browser_context(settings: Settings, budget: RequestBudget,
                           pacer: Pacer) -> Iterator[Any]:
    """A browser for the PUBLIC lane, which never carries a credential.

    Note what is absent: storage_state is not passed, and the encrypted session
    is not even read. It is not that this context declines to use the biller
    session — the session is not in scope here at all. That is the difference
    between a rule and a structure, and it is why availability data can never
    accidentally be fetched as a logged-in user.
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=settings.headless, args=_NO_DISK_CACHE_ARGS)
        try:
            context = browser.new_context(
                locale="en-US",
                timezone_id="America/New_York",  # slot times must be practice-local
                viewport={"width": 1440, "height": 900},
            )
            _install_request_guard(context, budget, pacer)
            try:
                yield context
            finally:
                context.close()
        finally:
            browser.close()


def _looks_like_login_url(url: str) -> bool:
    """Is this URL part of the sign-in flow?

    Note "/saml/auth": secure.simplepractice.com redirects to
    account.simplepractice.com/saml/auth?SAMLRequest=..., which contains none of
    the words "login", "signin" or "sign-in". An earlier version tested only
    those three and therefore reported a fresh, signed-OUT browser as already
    authenticated.
    """
    low = url.lower()
    return any(k in low for k in ("sign-in", "signin", "login", "/saml/auth", "/sessions/new"))


def cookies_from_state(settings: Settings) -> dict[str, str] | None:
    """Extract SimplePractice session cookies from the saved state.

    Lets a lightweight httpx client poll the authenticated JSON API every 30s
    without paying Chromium's startup cost each cycle. The browser is only spun
    up on refresh_session() when these cookies stop working.
    """
    state = load_state(settings)
    if not state:
        return None
    jar: dict[str, str] = {}
    for c in state.get("cookies", []) or []:
        if "simplepractice.com" in (c.get("domain") or "") and c.get("name"):
            jar[c["name"]] = c.get("value", "")
    return jar or None


def refresh_session(settings: Settings) -> bool:
    """Open a browser, ensure we are signed in, and persist fresh cookies.

    Called only when the httpx cookies have expired — occasionally, not every
    cycle. Holds the single-instance lock for the duration.
    """
    from .safety import LoginAttemptGuard, Pacer, RequestBudget

    budget = RequestBudget(limit=80)
    pacer = Pacer(settings.min_delay_s, settings.max_delay_s)
    guard = LoginAttemptGuard()
    with exclusive_session_lock(settings):
        with browser_context(settings, budget, pacer) as ctx:
            if is_signed_in(ctx):
                # The session is healthy. Below the ceiling the counter can be
                # reset (and the reset is logged); AT the ceiling only a person
                # (or a real, confirmed sign-in) may clear it — a live cookie
                # does not reset SimplePractice's own failure count.
                n = login_failure_count(settings)
                if 0 < n < MAX_LOGIN_FAILURES:
                    clear_login_failures(settings)
                    log(step="login_failures", status="cleared", value=n)
                save_state(settings, ctx.storage_state())  # refresh cookie expiry
                return True
            if sign_in(ctx, settings, guard):
                return True
    return False


# An alias nothing monkeypatches: the run-now tools replace
# session.refresh_session in-process, and the on-demand path must still reach
# the real implementation regardless of import order.
_refresh_session_impl = refresh_session


def is_signed_in(context) -> bool:
    """Load the app root and decide whether we hold a live session.

    The URL alone is not trusted. The decisive test is whether a password field
    is on the page: if SimplePractice is asking for a password, we are not
    signed in, whatever the address bar says.
    """
    page = context.new_page()
    try:
        page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=45_000)
        page.wait_for_timeout(2_000)

        password_visible = False
        try:
            password_visible = page.locator(
                "#user_password, input[type='password']"
            ).first.is_visible(timeout=4_000)
        except Exception:
            # Fail CLOSED. If we cannot tell, assume we are signed out: a wrong
            # "expired" costs one clean sign-in, whereas a wrong "active" sends
            # every authenticated feed against a logged-out browser and fails
            # later, somewhere less obvious.
            password_visible = True

        signed_in = not password_visible and not _looks_like_login_url(page.url)
        log(step="session_probe", session="active" if signed_in else "expired",
            url_kind="login_page" if _looks_like_login_url(page.url) else "app_page")
        return signed_in
    finally:
        page.close()


def sign_in(context, settings: Settings, guard: LoginAttemptGuard) -> bool:
    """Attempt exactly ONE interactive sign-in.

    Returns True on success. On failure it returns False and does NOT retry —
    SimplePractice locks an account after five consecutive failures, so a retry
    loop here is how automation takes real billing work offline.

    A persistent counter (login_locked) stops attempts entirely after
    MAX_LOGIN_FAILURES so repeated failures across cycles can never reach the
    lockout. That state requires a human to clear.
    """
    if login_locked(settings):
        log(step="sign_in", status="locked_out",
            reason="too_many_failures_needs_human")
        return False
    guard.claim()
    page = context.new_page()
    try:
        page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=45_000)
        page.wait_for_timeout(1200)

        # Selectors confirmed by check_login.py --probe against the live page:
        #   input#user_email  / input#user_password / input#submitBtn
        # The form is single-step: both fields render together.
        email = page.locator("#user_email, input[name='user[email]']").first
        email.wait_for(state="visible", timeout=20_000)
        pwd = page.locator("#user_password, input[name='user[password]']").first
        pwd.wait_for(state="visible", timeout=20_000)

        # A cookie-consent banner can overlay the form. We do NOT click "Accept"
        # — consenting on the practice's behalf is not ours to do, and tracker
        # requests are blocked at the network layer regardless. If it genuinely
        # intercepts the submit we surface that rather than clicking through it.
        email.fill(settings.sp_email.reveal())
        pwd.fill(settings.sp_password.reveal())

        submit = page.locator("#submitBtn, input[name='commit']").first
        # Count the attempt BEFORE the password leaves the browser: a timeout,
        # crash or kill after this point must still count toward the ceiling
        # (SimplePractice has already seen the attempt). Only a confirmed
        # success below clears it.
        if not _bump_login_failure(settings):
            # The counter is the hard rail against SimplePractice's account
            # lockout: never send a password we could not count.
            log(step="sign_in", status="counter_unwritable")
            return False
        try:
            submit.click(timeout=10_000)
        except Exception:
            log(step="sign_in", status="submit_intercepted",
                reason="overlay_blocking_submit")
            return False

        try:
            page.wait_for_load_state("networkidle", timeout=60_000)
        except Exception:
            # A slow page is not a verdict: judge the outcome below from the URL
            # and the password field, so a real success still clears the
            # counter and saves the session.
            log(step="sign_in", status="slow_load")
        page.wait_for_timeout(2_500)

        url = page.url.lower()
        on_login = _looks_like_login_url(url)
        challenged = any(k in url for k in ("verify", "challenge", "device", "otp",
                                            "two_factor", "2fa"))

        if challenged:
            # A step-up challenge is NOT a credential failure, but retrying it in a
            # loop is still how an account gets locked — so it counts toward the
            # ceiling (already counted before submit) and needs a human to read
            # the biller account's inbox.
            log(step="sign_in", status="challenged",
                reason="step_up_verification_required")
            return False
        if on_login:
            # No detail logged: the page may render the account identity.
            log(step="sign_in", status="failed", reason="still_on_login_page")
            return False

        # Do not declare success from the URL alone. A previous version did, and
        # reported status='ok' on a run where the sign-in POST had actually been
        # blocked before it left the browser — the address simply never became
        # something that looked like a login page. Success now means a password
        # field is genuinely gone from the page.
        try:
            still_asking = page.locator(
                "#user_password, input[type='password']"
            ).first.is_visible(timeout=3_000)
        except Exception:
            still_asking = False
        if still_asking:
            log(step="sign_in", status="failed", reason="password_field_still_present")
            return False

        clear_login_failures(settings)   # a clean sign-in resets the ceiling
        save_state(settings, context.storage_state())
        log(step="sign_in", status="ok")
        return True
    finally:
        page.close()
