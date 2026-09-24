"""Check the answered NEW CLIENT callers straight against SimplePractice.

Question (Alam, 2026-09-24): of the people who called the New Client line and
were answered, how many really became SimplePractice clients — checked from
the call itself, without going through HubSpot — so HubSpot's count can then be
compared against it.

Input is a date range only. The callers come from the FDO dashboard's own
`calls` table (inbound, answered, IVR branch = one of the four New Client
options); names for the exact-name fallback come from the same row (Aircall's
contact name) and from HubSpot's synced contacts with that number. Nothing is
uploaded and no client value is ever on a command line.

For each distinct caller: search SimplePractice by the phone digits (a record
must carry that number, or be the single hit of a full 10-digit search), then by
exact first + last name. For a match: when the SimplePractice client record was
created RELATIVE to the caller's first New Client call (in days — "created 2
days after the call" means they became a client after calling; "created 400
days before" means they were already a client), and the first appointment on or
after the call day with its status.

OUTPUT: one JSON line per caller keyed by k = the Aircall call id of their
first answered New Client call (an Aircall record id, like the HubSpot ids we
print elsewhere) — never a name, a number, an e-mail, a SimplePractice id, or a
hash of a phone number (a 10-digit number's hash can be reversed in seconds). Read-only GETs via
check_clients' _get (host allow-list, no redirects, budget, pacing). Does not
sign in (exit 3 if the session has expired) unless run with --signin, which
renews the gateway's one session via src/tools/on_demand.py (guarded, at most
once per 30 minutes; must run as the gateway user: fly ssh console -u gateway).

    fly ssh console --app mcw-sp-gateway -C "python -u -m src.tools.check_callers 2026-09-01 2026-09-30"
    ... --write   also saves the results to the FDO dashboard's sp_caller_checks
                  table (one row per answered New Client call id; call ids,
                  dates and statuses only — no names or numbers), which the
                  Front Office Scorecard shows as "checked in SimplePractice".
"""

from __future__ import annotations

import sys
from collections import Counter
from datetime import date, datetime, timedelta
from urllib.parse import urlencode

from .. import config, safety, session
from ..sink import Sink
from .on_demand import refresh_on_demand
from .check_clients import (
    ET, NAME_FIELDS, SEARCH_PAGE, STATUS, SessionExpired, UpstreamError, _appointments, _attrs, _digits, _fold, _get,
    _ID_RE, _match_couple, _parse_dt, _search_clients, out,
)

NEW_CLIENT_BRANCHES = ("New Client", "New Client Psychiatry", "New Client Sarasota", "New Client Tampa")
MAX_CALLERS = 600
OUTPUT_TABLE = "sp_caller_checks"
FIRST_STATUS = frozenset({"attended", "no_show", "cancelled", "late_cancelled", "clinician_cancelled",
                          "upcoming", "no_appointment", "not_found", "error"})
MATCHED_BY = frozenset({"phone", "name", "couple"})
SP_STATUS = frozenset({"active", "inactive", "prospective", "other"})


def _load_callers(settings, start: date, end: date) -> list[dict]:
    fdo = Sink(settings, url=settings.fdo_supabase_url, key=settings.fdo_supabase_service_key)
    lo = datetime(start.year, start.month, start.day, tzinfo=ET).isoformat()
    hi = datetime(end.year, end.month, end.day, tzinfo=ET) + timedelta(days=1)
    rows = fdo.select("calls", params={
        "select": "aircall_call_id,started_at,phone_normalized,ivr_branch,direction,user_name,contact_first_name,contact_last_name",
        "direction": "eq.inbound",
        "ivr_branch": "in.(" + ",".join(f'"{b}"' for b in NEW_CLIENT_BRANCHES) + ")",
        "started_at": f"gte.{lo}",
        "and": f"(started_at.lt.{hi.isoformat()})",
        "order": "started_at",
    }, page_size=1000, max_pages=10)
    callers: dict[str, dict] = {}
    for r in rows:
        if not r.get("user_name"):          # answered calls only (an FDO took it)
            continue
        d = _digits(r.get("phone_normalized"))
        if len(d) != 10:
            continue
        dt = _parse_dt(r.get("started_at"))
        if not dt:
            continue
        day = dt.astimezone(ET).date()
        c = callers.setdefault(d, {"d": d, "first": day, "first_dt": dt, "cid": r.get("aircall_call_id"), "calls": 0, "names": [], "ids": []})
        c["calls"] += 1
        if str(r.get("aircall_call_id") or "").isdigit() and int(r["aircall_call_id"]) not in c["ids"]:
            c["ids"].append(int(r["aircall_call_id"]))
        if dt < c["first_dt"]:
            c["first"], c["first_dt"], c["cid"] = day, dt, r.get("aircall_call_id")
        nm = (str(r.get("contact_first_name") or "").strip(), str(r.get("contact_last_name") or "").strip())
        if nm[0] and nm[1] and nm not in c["names"]:
            c["names"].append(nm)
    # HubSpot names for the same numbers (synced copy), for the name fallback.
    ds = list(callers)
    for i in range(0, len(ds), 100):
        # The synced copy stores most numbers as 10 digits, some with a leading 1.
        forms = [f for d in ds[i:i + 100] for f in (d, "1" + d)]
        for r in fdo.select("dashboard_contacts", params={
            "select": "phone_normalized,first_name,last_name",
            "phone_normalized": "in.(" + ",".join(forms) + ")",
        }, page_size=1000, max_pages=2):
            d = _digits(r.get("phone_normalized"))
            nm = (str(r.get("first_name") or "").strip(), str(r.get("last_name") or "").strip())
            if d in callers and nm[0] and nm[1] and nm not in callers[d]["names"]:
                callers[d]["names"].append(nm)
    return sorted(callers.values(), key=lambda c: (c["first_dt"], str(c["cid"])))[:MAX_CALLERS]


def table_rows_of(c: dict, row: dict, stamp: str) -> list[dict]:
    """sp_caller_checks rows for one caller: the caller's result on every one of
    their answered New Client call ids. Vocabulary-checked; no client value."""
    return [{
        "aircall_call_id": cid,
        "first_call": row["first_call"],
        "checked_at": stamp,
        "found": int(row.get("found") or 0),
        "matched_by": row.get("matched_by") if row.get("matched_by") in MATCHED_BY else None,
        "created_rel_days": row.get("created_rel_days") if isinstance(row.get("created_rel_days"), int) else None,
        "sp_status": row.get("sp_status") if row.get("sp_status") in SP_STATUS else None,
        "first_appointment": row.get("first"),
        "first_status": row["first_status"] if row["first_status"] in FIRST_STATUS else "error",
        "appointments": int(row.get("appts") or 0),
        "source": "gateway",
    } for cid in c["ids"]]


def _check(c: dict, cookies, budget, pacer, now: datetime) -> dict:
    day = datetime(c["first"].year, c["first"].month, c["first"].day, tzinfo=ET)
    row = {"k": str(c["cid"]), "first_call": c["first"].isoformat(), "calls": c["calls"], "found": 0,
           "matched_by": None, "created_rel_days": None, "sp_status": None, "first": None,
           "first_status": "not_found", "appts": 0, "ambiguous": False}
    hits = _search_clients(c["d"], cookies, budget, pacer)
    matches = [x for x in hits if _digits(_attrs(x).get("defaultPhoneNumber")) == c["d"]] or (hits if len(hits) == 1 else [])
    matched_by = "phone" if matches else None
    for first, last in c["names"][:3]:
        if matches:
            break
        qs = "clients?" + urlencode({"filter[search]": f"{first} {last}", "fields[clients]": NAME_FIELDS, "page[size]": str(SEARCH_PAGE)})
        f, l = _fold(first), _fold(last)
        for x in (_get(qs, cookies, budget, pacer).get("data")) or []:
            a = _attrs(x)
            if (_fold(a.get("firstName")) == f and _fold(a.get("lastName")) == l) or _fold(a.get("preferredName")) == f + l:
                matches.append(x)
        matched_by = "name" if matches else None
    if not matches:
        first, last = (c["names"][0] if c["names"] else ("", ""))
        matches = _match_couple({"ph": c["d"], "first": first, "last": last}, cookies, budget, pacer)
        matched_by = "couple" if matches else None
    matches = [x for x in matches if _ID_RE.fullmatch(str(x.get("id") or ""))]
    row["found"] = len(matches)
    row["ambiguous"] = len(matches) > 1
    row["matched_by"] = matched_by if matches else None
    if not matches:
        return row
    # the newest record decides "new vs already a client" (a family member on
    # the same number may be an old client), then keep at most 3 for sessions
    newest = max(matches, key=lambda x: _parse_dt(_attrs(x).get("createdAt")) or datetime.min.replace(tzinfo=ET))
    matches = [newest] + [x for x in matches if x is not newest][:2]
    created = _parse_dt(_attrs(newest).get("createdAt"))
    if created:
        row["created_rel_days"] = (created.astimezone(ET).date() - c["first"]).days
    st = str(_attrs(newest).get("status") or "").strip().lower()
    row["sp_status"] = st if st in ("active", "inactive", "prospective") else ("other" if st else None)
    appts = []
    for x in matches:
        for a in _appointments(str(x["id"]), day, cookies, budget, pacer):
            dt = _parse_dt(_attrs(a).get("startTime"))
            if dt and dt >= day:
                appts.append((dt, STATUS.get(str(_attrs(a).get("attendanceStatus")), "unknown_status")))
    appts.sort(key=lambda t: t[0])
    row["appts"] = len(appts)
    if not appts:
        row["first_status"] = "no_appointment"
    else:
        dt, st2 = appts[0]
        row["first"] = dt.astimezone(ET).date().isoformat()
        row["first_status"] = "upcoming" if (st2 == "attended" and dt > now) else st2
    return row


def main(argv: list[str]) -> int:
    import logging

    logging.getLogger("httpx").setLevel(logging.WARNING)      # request URLs carry numbers and names
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    allow_signin = "--signin" in argv
    write = "--write" in argv
    argv = [a for a in argv if a not in ("--signin", "--write")]
    if len(argv) != 2:
        print("usage: python -m src.tools.check_callers <from YYYY-MM-DD> <to YYYY-MM-DD>")
        return 2
    try:
        start, end = date.fromisoformat(argv[0]), date.fromisoformat(argv[1])
    except ValueError:
        print("dates must be YYYY-MM-DD")
        return 2
    if end < start or (end - start).days > 92:
        print("range must be 0-92 days")
        return 2
    settings = config.load_settings()
    if not (settings.fdo_supabase_url and settings.fdo_supabase_service_key):
        print("FDO_SUPABASE_URL / FDO_SUPABASE_SERVICE_KEY not set")
        return 2
    # Who to check first: no callers = no reason to touch SimplePractice at all.
    callers = _load_callers(settings, start, end)
    out({"callers": len(callers), "calls": sum(c["calls"] for c in callers)})
    if not callers:
        return 0
    cookies = session.cookies_from_state(settings)
    probe_budget = safety.RequestBudget(limit=2)
    probe_pacer = safety.Pacer(settings.min_delay_s, settings.max_delay_s)
    try:
        if not cookies:
            raise SessionExpired("no saved session")
        _get("clients?" + urlencode({"page[size]": "1", "fields[clients]": "status"}), cookies, probe_budget, probe_pacer)
    except SessionExpired:
        # Renew only when asked (--signin): the gateway's own guarded sign-in,
        # at most once per 30 minutes. Otherwise stop and let the scheduler do it.
        if not (allow_signin and refresh_on_demand(settings)):
            raise
        cookies = session.cookies_from_state(settings)
        if not cookies:
            raise
    budget = safety.RequestBudget(limit=8 * len(callers) + 20)
    pacer = safety.Pacer(settings.min_delay_s, settings.max_delay_s)
    now = datetime.now(ET)
    totals: Counter = Counter()
    errors: Counter = Counter()
    stamp = datetime.now(ET).astimezone().isoformat()
    table_rows: list[dict] = []
    for c in callers:
        try:
            row = _check(c, cookies, budget, pacer, now)
        except (SessionExpired, safety.SafetyViolation):
            raise
        except Exception as exc:  # noqa: BLE001 — one bad lookup must not sink the run; class name only
            row = {"k": str(c["cid"]), "first_call": c["first"].isoformat(), "found": 0, "first_status": "error"}
            errors[type(exc).__name__] += 1
        totals[f"{row.get('matched_by') or 'none'}:{row['first_status']}"] += 1
        out(row)
        table_rows.extend(table_rows_of(c, row, stamp))
    out({"totals": dict(totals), "errors": dict(errors), "requests": budget.used})
    if write and table_rows:
        fdo = Sink(settings, url=settings.fdo_supabase_url, key=settings.fdo_supabase_service_key)
        for i in range(0, len(table_rows), 200):
            fdo.upsert(OUTPUT_TABLE, table_rows[i:i + 200], on_conflict="aircall_call_id")
        out({"written": len(table_rows), "table": OUTPUT_TABLE})
    return 0


if __name__ == "__main__":
    code = 1
    try:
        code = main(sys.argv[1:])
    except SessionExpired:
        print("SESSION EXPIRED — the on-demand sign-in did not run; see the on_demand_signin log line "
              "(cooldown / busy / locked_needs_human / not_on_gateway / run_as_gateway_user)"
              if "--signin" in sys.argv[1:]
              else "SESSION EXPIRED — stopping; the scheduler renews it in business hours (or re-run with --signin as -u gateway)")
        code = 3
    except safety.SafetyViolation as exc:
        print("stopped:", safety.scrub_text(str(exc)))
    except BaseException as exc:  # noqa: BLE001 — never a traceback (locals hold names)
        print(f"stopped: {type(exc).__name__}")
    sys.exit(code)
