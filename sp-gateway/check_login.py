"""Supervised connectivity check for the SimplePractice gateway.

Two modes, deliberately separated:

  --probe    Loads the sign-in page and reports its STRUCTURE only. Submits
             nothing, types nothing, and spends none of the five sign-in
             attempts that lock a SimplePractice account. Safe to run freely.

  --signin   Performs exactly ONE real sign-in attempt, then reports whether it
             landed. Never retries. Run this while watching the biller account's
             inbox so you can see any device-verification mail it triggers.

Neither mode navigates to reports, so no client data is fetched.

Usage:
    python check_login.py --probe
    python check_login.py --signin [--headed]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src import config, safety, session  # noqa: E402


def probe(headed: bool) -> int:
    """Load the sign-in page and describe the form. Submits nothing."""
    settings = config.load_settings()
    settings = settings.__class__(**{**settings.__dict__, "headless": not headed})
    budget = safety.RequestBudget(limit=25)
    pacer = safety.Pacer(settings.min_delay_s, settings.max_delay_s)

    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=settings.headless,
                                     args=session._NO_DISK_CACHE_ARGS)
        try:
            ctx = browser.new_context(locale="en-US", timezone_id="America/New_York")
            session._install_request_guard(ctx, budget, pacer)
            page = ctx.new_page()
            page.goto(session.LOGIN_URL, wait_until="domcontentloaded", timeout=45_000)
            page.wait_for_timeout(2500)

            safety.log(step="probe", status="loaded", url_kind=_url_kind(page.url))

            inputs = page.evaluate(
                """() => [...document.querySelectorAll('input')]
                     .filter(i => i.type !== 'hidden')
                     .map(i => ({type: i.type, name: i.name, id: i.id,
                                 placeholder: i.placeholder, visible: !!i.offsetParent}))"""
            )
            buttons = page.evaluate(
                """() => [...document.querySelectorAll('button,input[type=submit]')]
                     .map(b => (b.innerText || b.value || '').trim()).filter(Boolean).slice(0,10)"""
            )
            hidden_names = page.evaluate(
                """() => [...document.querySelectorAll('input[type=hidden]')]
                     .map(i => i.name).filter(Boolean).slice(0,15)"""
            )
            print("\n--- visible inputs ---")
            for i in inputs:
                print(f"  type={i['type']:<10} name={i['name']!r:<28} id={i['id']!r:<24} visible={i['visible']}")
            print("\n--- buttons ---")
            for b in buttons:
                print(f"  {b!r}")
            print("\n--- hidden field names (fingerprinting/CSRF indicators) ---")
            for h in hidden_names:
                print(f"  {h}")
            print(f"\n--- requests used: {budget.used}/{budget.limit} ---")
            ctx.close()
            return 0
        finally:
            browser.close()


def signin(headed: bool) -> int:
    """Exactly one real sign-in attempt."""
    import os

    if hasattr(os, "geteuid") and os.geteuid() == 0:
        # As root the saved session and the failure counter would be written
        # root-owned, unreadable/unwritable for the scheduler (user `gateway`).
        print("refusing to sign in as root — run: fly ssh console -a mcw-sp-gateway -u gateway "
              "-C \"python check_login.py --signin\"")
        return 2
    settings = config.load_settings()
    if not settings.configured:
        safety.log(step="signin", status="skipped", reason="credentials_not_set")
        print("SP_Email / SP_Password are not set in .env.local", file=sys.stderr)
        return 2
    settings = settings.__class__(**{**settings.__dict__, "headless": not headed})

    budget = safety.RequestBudget(limit=60)
    pacer = safety.Pacer(settings.min_delay_s, settings.max_delay_s)
    guard = safety.LoginAttemptGuard()

    with session.exclusive_session_lock(settings):
        with session.browser_context(settings, budget, pacer) as ctx:
            if session.is_signed_in(ctx):
                safety.log(step="signin", status="already_active")
                return 0
            ok = session.sign_in(ctx, settings, guard)
            if not ok:
                safety.log(step="signin", status="failed", budget_used=budget.used)
                return 1

            # Independent confirmation, on a fresh page load. sign_in() has
            # twice now reported success on a run that had not actually signed
            # in — once from a URL heuristic, once with the final SAML POST
            # blocked. A claim of success is worth nothing unless something
            # other than the claimant checks it.
            confirmed = session.is_signed_in(ctx)
            safety.log(step="signin",
                       status="ok" if confirmed else "unconfirmed",
                       budget_used=budget.used)
            return 0 if confirmed else 1


def _url_kind(url: str) -> str:
    """Describe a URL without echoing tokens or account hints."""
    low = url.lower()
    if "sign-in" in low or "signin" in low or "login" in low:
        return "login_page"
    if "verify" in low or "challenge" in low or "device" in low:
        return "verification_challenge"
    return "app_page"


def verify(headed: bool) -> int:
    """Prove the saved session really is an authenticated one.

    Loads the application root and reports STRUCTURE only — final host, page
    title, whether a password field is present, and how many navigation links
    exist. Deliberately reads no page content: a signed-in SimplePractice page
    can show client names, and this tool must never put those on a terminal.
    """
    settings = config.load_settings()
    settings = settings.__class__(**{**settings.__dict__, "headless": not headed})
    budget = safety.RequestBudget(limit=20)
    pacer = safety.Pacer(settings.min_delay_s, settings.max_delay_s)

    with session.exclusive_session_lock(settings):
        with session.browser_context(settings, budget, pacer) as ctx:
            page = ctx.new_page()
            try:
                page.goto(session.LOGIN_URL, wait_until="domcontentloaded", timeout=45_000)
                # This is a JavaScript app: the signed-in navigation does not
                # exist at domcontentloaded. An earlier version checked too early
                # and read a half-built page as "not authenticated".
                try:
                    page.wait_for_load_state("networkidle", timeout=25_000)
                except Exception:
                    pass
                page.wait_for_timeout(4_000)

                from urllib.parse import urlparse

                host = (urlparse(page.url).hostname or "").lower()
                try:
                    pw = page.locator("input[type='password']").count()
                except Exception:
                    pw = -1

                # Link PATHS only — never link text, which on a signed-in page
                # can carry client names.
                paths = page.evaluate(
                    """() => [...document.querySelectorAll('a[href]')]
                         .map(a => { try { return new URL(a.href, location.href).pathname; }
                                     catch (e) { return ''; } })
                         .filter(Boolean)"""
                )
                uniq = sorted(set(paths))
                title = (page.title() or "")[:60]

                # The decisive signal: authenticated-only application areas.
                # Sign-out lives behind a menu button, not an <a>, so looking
                # for a logout link was wrong. These pages, by contrast, simply
                # do not exist for a signed-out visitor.
                app_areas = ("/calendar", "/clients", "/billings", "/reports",
                             "/tasks", "/practice_settings", "/inquiries",
                             "/request-management", "/activity-log")
                hits = [p for p in uniq if any(p.startswith(a) for a in app_areas)]
                signed_in = host == config.SP_APP_HOST and pw == 0 and len(hits) >= 3

                safety.log(step="verify", host=host, count=len(hits),
                           status="authenticated" if signed_in else "not_authenticated")
                print(f"\n  final host              : {host}")
                print(f"  page title              : {title}")
                print(f"  password fields on page : {pw}")
                print(f"  authenticated app areas : {len(hits)}  {hits[:6]}")
                print(f"  link paths seen ({len(uniq)}):")
                for p in uniq[:25]:
                    print(f"      {p[:70]}")
                print(f"\n  => {'AUTHENTICATED' if signed_in else 'NOT authenticated'}\n")
                return 0 if signed_in else 1
            finally:
                page.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--probe", action="store_true", help="inspect the form; submit nothing")
    g.add_argument("--signin", action="store_true", help="ONE real sign-in attempt")
    g.add_argument("--verify", action="store_true", help="prove the saved session works")
    ap.add_argument("--headed", action="store_true", help="show the browser window")
    args = ap.parse_args()
    try:
        if args.probe:
            return probe(args.headed)
        if args.verify:
            return verify(args.headed)
        return signin(args.headed)
    except safety.SafetyViolation as exc:
        safety.log_exception(exc, step="aborted")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
