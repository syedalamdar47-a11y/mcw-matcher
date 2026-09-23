"""Check HubSpot's booked clients against SimplePractice — the third source.

For each HubSpot client booked in the period (given as an input file with an
opaque index, the phone digits, the e-mail and the Date Booked), answer:
  * does a SimplePractice client with that phone (or e-mail) exist?
  * when is/was their first appointment on or after the booking?
  * what happened to it — attended, no-show, cancelled, still upcoming?

OUTPUT is one JSON line per input index plus totals. It carries the index,
counts, appointment DATES and a fixed status vocabulary — never a name, phone,
e-mail, id or free text. SimplePractice's own values never reach stdout.

Read-only GETs to the app host only, no redirects, paced, budget-capped.
Reuses the saved session cookies; never signs in or refreshes the session
(exit 3 if it has expired). The input file is deleted the moment it is read.
One failed request marks that item "error" and the run continues; only an
expired session or a safety rail stops it.

The per-client helpers below (_get, _search_clients, _appointments,
_check_item, ...) are also what the nightly feed src/feeds/client_check.py
runs, so there is exactly one definition of "matched" and "first appointment".
Keep them pure: no printing, no session refresh, no scheduling.

Usage (from /app on the gateway machine):
    fly ssh console -C "sh -c 'cat > /tmp/sp-check-input.json'" < sp-check-input.json
    fly ssh console -C "python -u -m src.tools.check_clients /tmp/sp-check-input.json"
Exit codes: 0 ok · 1 unexpected error · 2 no saved session / bad input · 3 session expired.
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timedelta
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from .. import config, safety, session

API = f"https://{config.SP_APP_HOST}/frontend"
HDR = {"accept": "application/vnd.api+json", "api-version": "2026-05-25"}
ET = ZoneInfo("America/New_York")
_ID_RE = re.compile(r"[A-Za-z0-9\-]{1,64}")
MAX_MATCHES = 3          # family members share a number; look at a few, never a roster
SEARCH_PAGE = 10         # fuzzy search may return more than the exact match
LOOKAHEAD_DAYS = 120     # how far past the booking date a "first appointment" may sit
CLIENT_FIELDS = "status,createdAt,defaultPhoneNumber,defaultEmailAddress"

# SimplePractice attendanceStatus -> our fixed vocabulary. Anything else is
# reported as unknown_status rather than echoed.
STATUS = {
    "Show": "attended",
    "No Show": "no_show",
    "Cancelled": "cancelled",
    "Late Cancelled": "late_cancelled",
    "Clinician Cancelled": "clinician_cancelled",
}
SP_STATUS = ("active", "inactive", "prospective")


class SessionExpired(RuntimeError):
    pass


class UpstreamError(RuntimeError):
    """A non-auth HTTP error. Message = status code + resource name only."""


class BadInput(RuntimeError):
    """Messages are fixed literals only — never an input value."""


def out(obj) -> None:
    print(json.dumps(obj, separators=(",", ":")), flush=True)


def _digits(v) -> str:
    d = re.sub(r"\D", "", str(v or ""))
    return d[1:] if len(d) == 11 and d.startswith("1") else d


def _get(path_qs: str, cookies, budget, pacer):
    import httpx

    url = f"{API}/{path_qs}"
    safety.assert_allowed_url(url)
    safety.assert_read_only("GET", url)
    budget.spend()
    pacer.wait()
    with httpx.Client(timeout=30, follow_redirects=False) as client:
        resp = client.get(url, headers=HDR, cookies=cookies)
    ctype = resp.headers.get("content-type", "")
    if resp.status_code in (401, 403) or 300 <= resp.status_code < 400 \
            or ("html" in ctype and "json" not in ctype):
        raise SessionExpired(f"status {resp.status_code}")
    if resp.status_code >= 300:
        raise UpstreamError(f"HTTP {resp.status_code} on {path_qs.split('?')[0]}")
    return resp.json()


def _search_clients(term: str, cookies, budget, pacer) -> list[dict]:
    qs = "clients?" + urlencode({
        "filter[search]": term,
        "fields[clients]": CLIENT_FIELDS,
        "page[size]": str(SEARCH_PAGE),
    })
    return (_get(qs, cookies, budget, pacer).get("data")) or []


def _appointments(client_id: str, booked: datetime, cookies, budget, pacer) -> list[dict]:
    qs = "appointments?" + urlencode({
        "filter[clientId]": client_id,
        "filter[timeRange]": f"{booked.isoformat()},{(booked + timedelta(days=LOOKAHEAD_DAYS)).isoformat()}",
        "fields[appointments]": "startTime,attendanceStatus,thisType",
        "include": "",
    })
    data = (_get(qs, cookies, budget, pacer).get("data")) or []
    return [a for a in data if (a.get("attributes") or {}).get("thisType") == "Appointment"]


def _parse_dt(s) -> datetime | None:
    if not isinstance(s, str) or not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=ET)
    except ValueError:
        return None


def _attrs(c) -> dict:
    return c.get("attributes") or {}


def _phone_style(term_digits: str, style: str) -> str:
    d = term_digits
    if style == "formatted":
        return f"({d[:3]}) {d[3:6]}-{d[6:]}"
    if style == "tail7":
        return f"{d[3:6]}-{d[6:]}"
    return d


def _selftest(cookies, budget, pacer) -> str | None:
    """Does filter[search] find a client by phone, and in which spelling? Uses
    the first roster client with a phone; prints only the outcome."""
    try:
        roster = (_get("clients?" + urlencode({"page[size]": "5", "fields[clients]": "defaultPhoneNumber"}),
                       cookies, budget, pacer).get("data")) or []
        probe = next((c for c in roster if len(_digits(_attrs(c).get("defaultPhoneNumber"))) == 10), None)
        if not probe:
            # Can't prove anything either way — plain digits is the best guess.
            out({"selftest": "no_roster_phone", "style": "digits"})
            return "digits"
        d = _digits(_attrs(probe).get("defaultPhoneNumber"))
        for style in ("digits", "formatted", "tail7"):
            hits = _search_clients(_phone_style(d, style), cookies, budget, pacer)
            if str(probe.get("id")) in {str(c.get("id")) for c in hits}:
                out({"selftest": "phone", "style": style})
                return style
    except UpstreamError as exc:
        out({"selftest": "error", "detail": safety.scrub_text(str(exc), max_len=40), "style": "digits"})
        return "digits"
    # Proven: no spelling of the number finds the client — search by e-mail only.
    out({"selftest": "phone", "style": None})
    return None


def _load_input(path: str) -> list[dict]:
    # utf-8-sig: a file written by Windows PowerShell 5.1 carries a BOM.
    with open(path, encoding="utf-8-sig") as fh:
        raw = fh.read()
    # The input holds phone numbers and e-mails and has served its purpose the
    # moment it is read. Delete it NOW, before the multi-minute network loop:
    # `finally` never runs on SIGHUP (ssh disconnect) / SIGTERM (machine stop).
    try:
        os.remove(path)
    except OSError:
        out({"input_deleted": False})
    items = json.loads(raw)
    if not isinstance(items, list):
        raise BadInput("input must be a list")
    result = []
    for it in items:
        if not isinstance(it, dict) or "i" not in it:
            raise BadInput("each item needs an index 'i'")
        booked = it.get("booked")
        if not (isinstance(booked, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", booked)):
            raise BadInput("each item needs booked=YYYY-MM-DD")
        result.append({
            "i": int(it["i"]),
            "ph": _digits(it.get("ph")) if it.get("ph") else "",
            "em": str(it.get("em") or "").strip().lower(),
            "booked": booked,
        })
    return result


def _check_item(it: dict, style: str | None, cookies, budget, pacer, now: datetime,
                couple_of: dict[str, str] | None = None) -> dict:
    """One HubSpot contact -> one result row of counts, dates and vocabulary.

    `couple_of` maps an individual client id to the clientCouples record it
    sits in (built once per run by the feed; None for the one-off tool). It is
    consulted only when a matched individual has no sessions of their own.
    """
    booked = datetime.strptime(it["booked"], "%Y-%m-%d").replace(tzinfo=ET)
    row = {"i": it["i"], "found": 0, "hits": 0, "matched_by": None, "sp_status": None,
           "sp_created": None, "couple": False, "first": None, "first_status": "not_found",
           "appts": 0, "ambiguous": False}

    # 1. Find the client: by phone digits first, then e-mail. Search is fuzzy,
    #    so a match must actually carry the number / e-mail we asked for.
    matches: list[dict] = []
    matched_by = None
    if it["ph"] and len(it["ph"]) == 10 and style:
        hits = _search_clients(_phone_style(it["ph"], style), cookies, budget, pacer)
        row["hits"] = len(hits)
        matches = [c for c in hits if _digits(_attrs(c).get("defaultPhoneNumber")) == it["ph"]]
        if not matches and len(hits) == 1 and style == "digits":
            # A minor is filed under a parent's number: the search still finds
            # the record (through its related phones), but the record's own
            # defaultPhoneNumber differs or is empty. A full 10-digit term that
            # returns exactly ONE record is that record, not fuzzy noise. This
            # was the first run's blind spot, confirmed by hand afterwards.
            matches = list(hits)
        matched_by = "phone" if matches else None
    if not matches and it["em"]:
        hits = _search_clients(it["em"], cookies, budget, pacer)
        row["hits"] = max(row["hits"], len(hits))
        matches = [c for c in hits if str(_attrs(c).get("defaultEmailAddress") or "").strip().lower() == it["em"]]
        matched_by = "email" if matches else None
    matches = [c for c in matches if _ID_RE.fullmatch(str(c.get("id") or ""))]
    row["couple"] = any((c.get("type") or "clients") != "clients" for c in matches)
    # A new booking creates a client record near the booking date: when a
    # number is shared, prefer the records created around the booking.
    if len(matches) > 1:
        near = [c for c in matches
                if (dt := _parse_dt(_attrs(c).get("createdAt"))) and booked - timedelta(days=30) <= dt <= booked + timedelta(days=LOOKAHEAD_DAYS)]
        matches = near or matches
    matches = matches[:MAX_MATCHES]
    row["found"] = len(matches)
    row["ambiguous"] = len(matches) > 1
    row["matched_by"] = matched_by if matches else None
    if not matches:
        return row

    newest = max(matches, key=lambda c: _parse_dt(_attrs(c).get("createdAt")) or datetime.min.replace(tzinfo=ET))
    created = _parse_dt(_attrs(newest).get("createdAt"))
    row["sp_created"] = created.strftime("%Y-%m") if created else None
    st = str(_attrs(newest).get("status") or "").strip().lower()
    row["sp_status"] = st if st in SP_STATUS else ("other" if st else None)

    # 2. First appointment on/after the booking, across the matched clients
    #    (a parent's number may book for two children).
    appts: list[tuple[datetime, str]] = []

    def _collect(client_id: str) -> None:
        for a in _appointments(client_id, booked, cookies, budget, pacer):
            at = _attrs(a)
            dt = _parse_dt(at.get("startTime"))
            if dt and dt >= booked:   # belt-and-braces on the server's timeRange
                appts.append((dt, STATUS.get(str(at.get("attendanceStatus")), "unknown_status")))

    ids = [str(c["id"]) for c in matches]
    for cid in ids:
        _collect(cid)
    # 2b. Couples therapy is booked on a separate clientCouples record that the
    #     client search never returns and that OWNS the sessions. A matched
    #     individual with no sessions of their own but a seat in a couple gets
    #     the couple's sessions. The match itself (phone / e-mail) stands.
    if not appts and couple_of:
        couples = sorted({couple_of[cid] for cid in ids if cid in couple_of})
        for kid in couples:
            _collect(kid)
        row["couple"] = row["couple"] or bool(couples)
    appts.sort(key=lambda x: x[0])
    row["appts"] = len(appts)
    if not appts:
        row["first_status"] = "no_appointment"
        return row
    dt, status = appts[0]
    row["first"] = dt.astimezone(ET).strftime("%Y-%m-%d")
    # SimplePractice pre-marks future appointments "Show": scheduled, not attended.
    row["first_status"] = "upcoming" if (status == "attended" and dt > now) else status
    return row


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: python -m src.tools.check_clients <input.json>")
        return 2
    settings = config.load_settings()
    items = _load_input(argv[0])           # deletes the file as soon as it is read
    cookies = session.cookies_from_state(settings)
    if not cookies:
        print("no saved session — stopping (this tool never signs in)")
        return 2
    budget = safety.RequestBudget(limit=max(settings.per_run_request_budget, 5 * len(items) + 20))
    pacer = safety.Pacer(settings.min_delay_s, settings.max_delay_s)
    now = datetime.now(ET)

    style = _selftest(cookies, budget, pacer)
    if style is None:
        out({"warning": "phone search unavailable — matching by e-mail only"})

    totals: Counter = Counter()
    errors: Counter = Counter()
    for it in items:
        try:
            row = _check_item(it, style, cookies, budget, pacer, now)
        except UpstreamError as exc:      # one bad request must not sink the run
            row = {"i": it["i"], "first_status": "error"}
            errors[safety.scrub_text(str(exc), max_len=40)] += 1
        totals[row["first_status"]] += 1
        out(row)

    out({"totals": dict(totals), "errors": dict(errors), "items": len(items),
         "search_style": style, "requests": budget.used})
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    code = 1
    try:
        code = main(args)
    except SessionExpired as exc:
        print(f"SESSION EXPIRED ({exc}) — stopping; the scheduler will refresh it")
        code = 3
    except BadInput as exc:
        print("bad input:", safety.scrub_text(str(exc)))
        code = 2
    except UpstreamError as exc:          # only from the self-test; message is status + resource
        print("upstream:", safety.scrub_text(str(exc)))
        code = 1
    except safety.SafetyViolation as exc:   # our own messages, no page content
        print("stopped:", safety.scrub_text(str(exc)))
        code = 1
    except BaseException as exc:  # noqa: BLE001 — never print a traceback (locals hold page content)
        print(f"stopped: {type(exc).__name__}")
        code = 1
    finally:
        # Belt-and-braces: _load_input already removed it on the normal path.
        if len(args) == 1:
            try:
                os.remove(args[0])
            except OSError:
                pass
    sys.exit(code)
