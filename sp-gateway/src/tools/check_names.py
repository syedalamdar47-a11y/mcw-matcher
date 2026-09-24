"""Second-pass lookup for HubSpot clients the phone/e-mail check did not find.

For each item it tries, in order: every phone number HubSpot holds for the
contact (phone AND mobile — the first pass only used one), then the contact's
first + last name. A name hit counts only when SimplePractice's first and last
name both equal HubSpot's (case- and accent-insensitive), so a common surname
alone never matches. It then reports the first appointment on/after the
HubSpot Date Booked, exactly like check_clients.

OUTPUT: one JSON line per input index — matched_by (phone2 | name | none),
counts, dates and the fixed status vocabulary. Never a name, number, e-mail,
id or SimplePractice free text. Read-only GETs via check_clients' _get (host
allow-list, no redirects, budget, pacing). The input file is deleted on read.

    fly ssh console -C "python -u -m src.tools.check_names /tmp/sp-names-input.json"
"""

from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
from collections import Counter
from datetime import datetime
from urllib.parse import urlencode

from .. import config, safety, session
from .check_clients import (
    ET, STATUS, SessionExpired, UpstreamError, _appointments, _attrs, _digits, _get, _ID_RE, _parse_dt, out,
)

FIELDS = "status,createdAt,defaultPhoneNumber,firstName,lastName,preferredName"


def _fold(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z]", "", s.lower())


def _search(term: str, cookies, budget, pacer) -> list[dict]:
    qs = "clients?" + urlencode({"filter[search]": term, "fields[clients]": FIELDS, "page[size]": "10"})
    return (_get(qs, cookies, budget, pacer).get("data")) or []


def _load(path: str) -> list[dict]:
    with open(path, encoding="utf-8-sig") as fh:
        raw = fh.read()
    try:
        os.remove(path)          # holds names/numbers: gone before any network call
    except OSError:
        out({"input_deleted": False})
    items = json.loads(raw)
    if not isinstance(items, list):
        raise ValueError("input must be a list")
    return items


def _check(it: dict, cookies, budget, pacer, now: datetime) -> dict:
    booked = datetime.strptime(str(it["booked"])[:10], "%Y-%m-%d").replace(tzinfo=ET)
    row = {"i": it["i"], "matched_by": "none", "found": 0, "sp_created": None,
           "first": None, "first_status": "not_found", "appts": 0}
    matches: list[dict] = []
    for p in {_digits(x) for x in (it.get("phones") or []) if x}:
        if len(p) != 10:
            continue
        hits = _search(p, cookies, budget, pacer)
        matches = [c for c in hits if _digits(_attrs(c).get("defaultPhoneNumber")) == p] or (hits if len(hits) == 1 else [])
        if matches:
            row["matched_by"] = "phone2"
            break
    first, last = _fold(it.get("first")), _fold(it.get("last"))
    if not matches and first and last:
        term = f"{it.get('first', '').strip()} {it.get('last', '').strip()}"
        for c in _search(term, cookies, budget, pacer):
            a = _attrs(c)
            pref = _fold(a.get("preferredName"))
            if (_fold(a.get("firstName")) == first and _fold(a.get("lastName")) == last) or pref == first + last:
                matches.append(c)
        if matches:
            row["matched_by"] = "name"
    matches = [c for c in matches if _ID_RE.fullmatch(str(c.get("id") or ""))][:3]
    row["found"] = len(matches)
    if not matches:
        return row
    created = _parse_dt(_attrs(matches[0]).get("createdAt"))
    row["sp_created"] = created.strftime("%Y-%m") if created else None
    appts = []
    for c in matches:
        for a in _appointments(str(c["id"]), booked, cookies, budget, pacer):
            dt = _parse_dt(_attrs(a).get("startTime"))
            if dt and dt >= booked:
                appts.append((dt, STATUS.get(str(_attrs(a).get("attendanceStatus")), "unknown_status")))
    appts.sort(key=lambda x: x[0])
    row["appts"] = len(appts)
    if not appts:
        row["first_status"] = "no_appointment"
    else:
        dt, st = appts[0]
        row["first"] = dt.astimezone(ET).strftime("%Y-%m-%d")
        row["first_status"] = "upcoming" if (st == "attended" and dt > now) else st
    return row


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: python -m src.tools.check_names <input.json>")
        return 2
    settings = config.load_settings()
    items = _load(argv[0])
    cookies = session.cookies_from_state(settings)
    if not cookies:
        print("no saved session — stopping (this tool never signs in)")
        return 2
    budget = safety.RequestBudget(limit=6 * len(items) + 10)
    pacer = safety.Pacer(settings.min_delay_s, settings.max_delay_s)
    now = datetime.now(ET)
    totals: Counter = Counter()
    for it in items:
        try:
            row = _check(it, cookies, budget, pacer, now)
        except UpstreamError:
            row = {"i": it.get("i"), "matched_by": "error", "first_status": "error"}
        totals[f"{row['matched_by']}:{row['first_status']}"] += 1
        out(row)
    out({"totals": dict(totals), "items": len(items), "requests": budget.used})
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    code = 1
    try:
        code = main(args)
    except SessionExpired as exc:
        print(f"SESSION EXPIRED ({exc})")
        code = 3
    except safety.SafetyViolation as exc:
        print("stopped:", safety.scrub_text(str(exc)))
    except BaseException as exc:  # noqa: BLE001 — never a traceback (locals hold names)
        print(f"stopped: {type(exc).__name__}")
    finally:
        if len(args) == 1:
            try:
                os.remove(args[0])
            except OSError:
                pass
    sys.exit(code)
