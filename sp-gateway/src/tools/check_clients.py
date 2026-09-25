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
import unicodedata
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
NAME_FIELDS = CLIENT_FIELDS + ",firstName,lastName,preferredName"
# The most SimplePractice requests _check_item can make for ONE contact:
# 3 individual searches (phone, e-mail, name) + 2 couple searches (phone, name)
# + up to MAX_MATCHES appointment lists each for the individual records, their
# couple-map couples (feed, when enabled) and the matched couple records.
# Callers reserve twice this (a re-auth re-runs the contact) before starting one.
ITEM_MAX_REQUESTS = 5 + 3 * MAX_MATCHES

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


def _fold(s) -> str:
    """Name comparison key: accents stripped, letters only, lower-case."""
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z]", "", s.lower())


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


def _strings_of(v, depth: int = 0):
    """Every string inside a JSON value — in-memory matching only, never printed."""
    if depth > 5:
        return
    if isinstance(v, str):
        yield v
    elif isinstance(v, list):
        for x in v:
            yield from _strings_of(x, depth + 1)
    elif isinstance(v, dict):
        for x in v.values():
            yield from _strings_of(x, depth + 1)


def _search_couples(term: str, cookies, budget, pacer) -> list[dict]:
    """Couples therapy is filed under a clientCouples record that /clients never
    returns. SimplePractice's own top-bar search (utility-bar/client-search)
    queries base-clients with thisType Client,ClientCouple; so do we, and keep
    only the couple records. Verified 2026-09-24: all 6 September couples the
    individual search missed come back, by name and by phone."""
    qs = "base-clients?" + urlencode({
        "filter[search]": term,
        "filter[thisType]": "Client,ClientCouple",
        "filter[includePartial]": "true",
        "page[size]": str(SEARCH_PAGE),
    })
    data = (_get(qs, cookies, budget, pacer).get("data")) or []
    return [c for c in data if isinstance(c, dict) and c.get("type") == "clientCouples"]


def _words(s) -> list[str]:
    """The name words of a string: accents stripped, lower-case, split on
    anything that is not a letter ("Kathleen & Joann Brown" -> kathleen, joann,
    brown)."""
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return [w for w in re.split(r"[^a-z]+", s) if w]


def _name_words(attributes) -> set[str]:
    """Every whole name word of a record's NAME attributes only — the top-level
    keys ending in "name" (a couple's preferredName "Name & Name", firstName,
    lastName, ...). E-mail, address, phones and notes never count."""
    if not isinstance(attributes, dict):
        return set()
    return {w for k, v in attributes.items()
            if isinstance(k, str) and k.lower().endswith("name") and isinstance(v, str)
            for w in _words(v)}


def _name_in(part, words: set[str]) -> bool:
    """A HubSpot first or last name is in a record when it is a WHOLE word there
    ("Ann" is not in "Joann", "Lee" not in "Kathleen", "Smith" not in
    "Smithson"), or every word of a multi-part name is ("Mary-Jane", "De La Cruz")."""
    parts = _words(part)
    return bool(parts) and ("".join(parts) in words or all(p in words for p in parts))


def _opened_near(c: dict, booked: datetime) -> bool:
    """The record was created around this booking: from 30 days before the
    Date Booked to LOOKAHEAD_DAYS after it (a new booking opens its file then)."""
    dt = _parse_dt(_attrs(c).get("createdAt"))
    return bool(dt) and booked - timedelta(days=30) <= dt <= booked + timedelta(days=LOOKAHEAD_DAYS)


def _match_couple(it: dict, cookies, budget, pacer) -> list[dict]:
    """A couple record for this HubSpot contact: by the phone digits (the record
    carries the number, or is the single couple a full 10-digit search returns),
    then by first + last name — BOTH must be whole words of the couple's name
    attributes. A shared surname alone, or a name hidden inside another name
    ("Ann" in "Joann"), never matches."""
    ph = it.get("ph") or ""
    if len(ph) == 10:
        hits = _search_couples(ph, cookies, budget, pacer)
        carrying = [c for c in hits if ph in {_digits(s) for s in _strings_of(c.get("attributes"))}]
        if carrying or len(hits) == 1:
            return carrying or hits
    first, last = it.get("first"), it.get("last")
    if _fold(first) and _fold(last):
        term = f"{str(first or '').strip()} {str(last or '').strip()}"
        named = []
        for c in _search_couples(term, cookies, budget, pacer):
            words = _name_words(c.get("attributes"))
            if _name_in(first, words) and _name_in(last, words):
                named.append(c)
        return named
    return []


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


def _is_couples(it: dict) -> bool:
    """HubSpot's Type of Therapy names couples work ("Couples/Marriage Therapy").
    Held in memory only, like the number and e-mail; never printed or written."""
    return "couple" in str(it.get("therapy") or "").lower()


def _narrow(matches: list[dict], booked: datetime) -> list[dict]:
    """Well-formed ids only; when a number is shared, prefer the records created
    around the booking (a new booking creates its record near that date); at
    most MAX_MATCHES, so no contact can fan out into a roster of lookups."""
    matches = [c for c in matches if _ID_RE.fullmatch(str(c.get("id") or ""))]
    if len(matches) > 1:
        matches = [c for c in matches if _opened_near(c, booked)] or matches
    return matches[:MAX_MATCHES]


def _sessions(ids: list[str], booked: datetime, cookies, budget, pacer) -> list[tuple[datetime, str]]:
    """(start, status) of every session on/after `booked` across these records
    (a parent's number may book for two children), oldest first. One request
    per id."""
    appts: list[tuple[datetime, str]] = []
    for cid in ids:
        for a in _appointments(cid, booked, cookies, budget, pacer):
            at = _attrs(a)
            dt = _parse_dt(at.get("startTime"))
            if dt and dt >= booked:   # belt-and-braces on the server's timeRange
                appts.append((dt, STATUS.get(str(at.get("attendanceStatus")), "unknown_status")))
    appts.sort(key=lambda x: x[0])
    return appts


def _couple_sessions(it: dict, booked: datetime, cookies, budget, pacer,
                     opened_near: bool = False) -> tuple[list[dict], list[tuple[datetime, str]]]:
    """The contact's clientCouples record(s) — matched exactly as _match_couple
    does (the phone digits, or BOTH first and last name as whole words) — and
    their sessions on/after `booked`. ([], []) when no couple record matches;
    then no appointment list is requested. Shared with check_callers.

    opened_near=True (an individual record was already found and the booking is
    not couples therapy): only a couple file opened around this booking counts
    (_opened_near). A family shares one number, so a child booked on a parent's
    phone must not inherit the parents' long-standing couple record and its
    sessions; the partner-record case (the couple file is opened at booking)
    still passes. Rejected records cost no appointment request."""
    couples = _match_couple(it, cookies, budget, pacer)
    if opened_near:
        couples = [c for c in couples if _opened_near(c, booked)]
    couples = _narrow(couples, booked)
    if not couples:
        return [], []
    return couples, _sessions([str(c["id"]) for c in couples], booked, cookies, budget, pacer)


def _find_individual(it: dict, style: str | None, row: dict, cookies, budget, pacer) -> tuple[list[dict], str | None]:
    """The contact's individual client record(s): phone digits, then e-mail,
    then exact first + last name. Search is fuzzy, so a match must actually
    carry the number / e-mail / name we asked for. Sets row["hits"]."""
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
    first, last = _fold(it.get("first")), _fold(it.get("last"))
    if not matches and first and last:
        # Last resort: the exact first + last name. SimplePractice often holds
        # a different number or e-mail than HubSpot (the client's own mobile vs
        # the number they called from); on 2026-09-24 this found 6 of 16
        # "missing" clients. Both names must match exactly — a surname alone
        # never counts.
        qs = "clients?" + urlencode({
            "filter[search]": f"{str(it.get('first') or '').strip()} {str(it.get('last') or '').strip()}",
            "fields[clients]": NAME_FIELDS,
            "page[size]": str(SEARCH_PAGE),
        })
        hits = (_get(qs, cookies, budget, pacer).get("data")) or []
        matches = [c for c in hits
                   if (_fold(_attrs(c).get("firstName")) == first and _fold(_attrs(c).get("lastName")) == last)
                   or _fold(_attrs(c).get("preferredName")) == first + last]
        matched_by = "name" if matches else None
    return matches, matched_by


def _check_item(it: dict, style: str | None, cookies, budget, pacer, now: datetime,
                couple_of: dict[str, str] | None = None) -> dict:
    """One HubSpot contact -> one result row of counts, dates and vocabulary.

    Two places a booking can live in SimplePractice, tried in turn until one
    has a session on/after the Date Booked:
      * the individual client record (phone -> e-mail -> exact name), and
      * a clientCouples record (base-clients search: phone digits, or both
        names as whole words). Couples therapy is filed there and the couple
        record OWNS the sessions — the phone search meanwhile finds ONE
        PARTNER's individual record, whose appointment list is empty (verified
        on August 2026 data).
    Individual first; the couple record first when HubSpot's Type of Therapy
    says couples. The couple search runs at most once per contact. When neither
    record has a session, the first record found is reported (no_appointment);
    when neither is found, not_found.

    Guards: after an individual record was found (booking not couples therapy),
    only a couple file opened around the booking counts (_couple_sessions
    opened_near). If the couple step fails (UpstreamError) the other place is
    still tried and a session found there is used; with no session anywhere the
    failure is re-raised, so the row is "error", not no_appointment.

    `couple_of` maps an individual client id to the clientCouples record it
    sits in (built once per run by the feed; None for the one-off tool). It is
    consulted only when a matched individual has no sessions of their own.

    Request cost: at most ITEM_MAX_REQUESTS; the couple step adds 1-2 searches
    (+1 appointment list per matched couple, at most MAX_MATCHES) and runs only
    for a contact whose individual record is missing or has no session.
    """
    booked = datetime.strptime(it["booked"], "%Y-%m-%d").replace(tzinfo=ET)
    row = {"i": it["i"], "found": 0, "hits": 0, "matched_by": None, "sp_status": None,
           "sp_created": None, "couple": False, "first": None, "first_status": "not_found",
           "appts": 0, "ambiguous": False}

    # Every record set found, in the order tried: (records, matched_by, sessions, in_couple).
    found: list[tuple[list[dict], str, list[tuple[datetime, str]], bool]] = []

    def _try_individual() -> None:
        matches, matched_by = _find_individual(it, style, row, cookies, budget, pacer)
        matches = _narrow(matches, booked)
        if not matches:
            return
        ids = [str(c["id"]) for c in matches]
        sessions = _sessions(ids, booked, cookies, budget, pacer)
        in_couple = False
        # The couple map (feed, when enabled): a matched individual with no
        # sessions of their own but a seat in a couple gets the couple's
        # sessions. The match itself (phone / e-mail / name) stands.
        if not sessions and couple_of:
            kids = sorted({couple_of[cid] for cid in ids if cid in couple_of})
            sessions = _sessions(kids, booked, cookies, budget, pacer)
            in_couple = bool(kids)
        found.append((matches, matched_by, sessions, in_couple))

    def _try_couple() -> None:
        # An individual record already found, booking not couples therapy: only
        # a couple file opened around this booking may take over (a child on a
        # parent's number must not inherit the parents' couple sessions).
        couples, sessions = _couple_sessions(it, booked, cookies, budget, pacer,
                                             opened_near=bool(found) and not _is_couples(it))
        if couples:
            found.append((couples, "couple", sessions, False))

    couple_failed: UpstreamError | None = None
    for step in ((_try_couple, _try_individual) if _is_couples(it) else (_try_individual, _try_couple)):
        try:
            step()
        except UpstreamError as exc:
            if step is not _try_couple:
                raise
            # The couple search (base-clients) or a couple's session list
            # failed. The other place may still hold the session; only when
            # neither does is the failure re-raised below.
            couple_failed = exc
            continue
        if found and found[-1][2]:
            break               # this record has a session: the other is never searched
    if couple_failed is not None and not any(f[2] for f in found):
        # No session anywhere we could read, and one place we could NOT read:
        # "error", never a misleading no_appointment / not_found. (The nightly
        # feed then keeps the contact's previous row.)
        raise couple_failed

    if not found:
        return row
    matches, matched_by, appts, in_couple = next((f for f in found if f[2]), found[0])
    row["found"] = len(matches)
    row["ambiguous"] = len(matches) > 1
    row["matched_by"] = matched_by
    # True when the contact sits in a couple record we saw — even one without
    # sessions, next to a reported individual record.
    row["couple"] = in_couple or any((c.get("type") or "clients") != "clients" for f in found for c in f[0])

    newest = max(matches, key=lambda c: _parse_dt(_attrs(c).get("createdAt")) or datetime.min.replace(tzinfo=ET))
    created = _parse_dt(_attrs(newest).get("createdAt"))
    row["sp_created"] = created.strftime("%Y-%m") if created else None
    st = str(_attrs(newest).get("status") or "").strip().lower()
    row["sp_status"] = st if st in SP_STATUS else ("other" if st else None)

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
