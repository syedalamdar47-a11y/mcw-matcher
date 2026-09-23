"""Structure-only discovery of SimplePractice's client resources.

Question being answered: can the authenticated JSON API tell us, for a phone
number we already hold in HubSpot, whether that person exists as a client, and
what happened to their first appointment? To answer it we need to know:

  * the clients list endpoint, its pagination, and which attribute (or related
    resource) holds the phone number, and in what format;
  * whether the list can be searched server-side, and whether inactive /
    prospective clients are included;
  * how an appointment links to its client, and whether filter[clientId] is
    honoured (verified by comparing ids, never trusted from a 200 alone);
  * the exact attendanceStatus vocabulary, including what a future
    appointment carries.

PHI POSTURE: prints KEY NAMES, TYPES, COUNTS and MASKED SHAPES only. Every
string value is reduced to a shape (digits -> N, letters -> A, anything
non-ASCII -> ?) before it can reach stdout; dict keys and resource types are
printed only when they look like identifiers. Two deliberate exceptions, both
practice-wide and value-free: the attendanceStatus enum counts (already consumed
by the calendar feed) and SimplePractice's own parameter-validation error
titles (run through safety.scrub_text). Nothing is written to disk. Read-only
GETs, no redirects followed, paced, host-checked, budget-capped at 40.

Reuses the saved session cookies only. Never signs in, never refreshes the
session, never takes the session lock — on an expired session it stops (exit 3)
so it can never race the live scheduler.

Run from /app on the gateway machine:
    fly ssh console --app mcw-sp-gateway -C "python -m src.tools.discover_clients"
Exit codes: 0 ok · 1 unexpected error · 2 no saved session · 3 session expired.
"""

from __future__ import annotations

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
_IDENT = re.compile(r"[A-Za-z][A-Za-z0-9_\-\[\]\.]{0,40}")


class SessionExpired(RuntimeError):
    pass


# ---------------------------------------------------------------- masking --

def _shape(v, depth: int = 0):
    """Reduce any JSON value to a value-free description."""
    if depth > 5:
        return "…"
    if v is None or isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return "num"
    if isinstance(v, str):
        # Per character, Unicode-aware: any digit -> N, any letter -> A, and
        # anything that is not printable ASCII punctuation -> ?, so accented,
        # non-Latin and control characters can never pass through.
        s = "".join(
            "N" if ch.isdigit() else "A" if ch.isalpha()
            else (ch if (ch.isascii() and ch.isprintable()) else "?")
            for ch in v
        )
        return f"str<{len(v)}>:{s[:24]}"
    if isinstance(v, list):
        return [len(v), _shape(v[0], depth + 1) if v else None]
    if isinstance(v, dict):
        return {_ident(k): _shape(x, depth + 1) for k, x in list(v.items())[:40]}
    return type(v).__name__


def _ident(k) -> str:
    """A dict key or resource type is printed only if it looks like an identifier;
    a key that is itself a value (a map keyed by phone number, say) is shaped."""
    return k if isinstance(k, str) and _IDENT.fullmatch(k) else str(_shape(k))


def _keys(d) -> list[str]:
    return sorted(_ident(k) for k in (d or {}).keys()) if isinstance(d, dict) else []


def _types(items) -> Counter:
    return Counter(_ident(i.get("type")) for i in (items or []) if isinstance(i, dict))


def _errors(body) -> str:
    """SimplePractice's parameter-validation titles (e.g. 'Invalid field'), the
    only thing a rejected guess can teach us. scrub_text masks anything shaped
    like a name, phone or email should one ever appear."""
    if not isinstance(body, dict):
        return ""
    out = []
    for e in (body.get("errors") or [])[:3]:
        e = e if isinstance(e, dict) else {"title": str(e)}
        raw = f"{e.get('status', '')} {e.get('code', '')} {e.get('title', '')} {e.get('detail', '')} {e.get('source') or ''}"
        out.append(safety.scrub_text(raw.strip(), max_len=160))
    return "; ".join(out)


def _rel_data(item, rel):
    return ((item.get("relationships") or {}).get(rel) or {}).get("data")


def _attrs(item) -> dict:
    return item.get("attributes") or {}


# ------------------------------------------------------------------ http ----

def _get(path_qs: str, cookies, budget, pacer):
    import httpx

    url = f"{API}/{path_qs}"
    safety.assert_allowed_url(url)
    safety.assert_read_only("GET", url)
    budget.spend()
    pacer.wait()
    # No redirects: a live JSON API never needs one, and following one could
    # open a socket to a host the allow-list never saw. A 3xx (e.g. a bounce to
    # the login host) therefore reads as "session gone" and stops the run.
    with httpx.Client(timeout=30, follow_redirects=False) as client:
        resp = client.get(url, headers=HDR, cookies=cookies)
    ctype = resp.headers.get("content-type", "")
    if resp.status_code in (401, 403) or 300 <= resp.status_code < 400 \
            or ("html" in ctype and "json" not in ctype):
        raise SessionExpired(f"status {resp.status_code}")
    try:
        body = resp.json()
    except Exception:
        body = None
    return resp.status_code, body


def _range(days_back: int, days_ahead: int) -> str:
    """tz-aware ET midnight with offset — the only format proven against
    /frontend/appointments (calendar.py._time_range)."""
    start = datetime.now(ET).replace(hour=0, minute=0, second=0, microsecond=0)
    return f"{(start + timedelta(days=days_back)).isoformat()},{(start + timedelta(days=days_ahead)).isoformat()}"


# ------------------------------------------------------------------ main ----

def main() -> int:
    settings = config.load_settings()
    cookies = session.cookies_from_state(settings)
    if not cookies:
        print("no saved session — stopping (this tool never signs in)")
        return 2
    budget = safety.RequestBudget(limit=40)
    pacer = safety.Pacer(settings.min_delay_s, settings.max_delay_s)

    def get(params: dict, resource: str = "clients"):
        return _get(f"{resource}?{urlencode(params)}", cookies, budget, pacer)

    # 1. Clients list: does it exist, how does it page, what attributes/relationships.
    client_id = None
    client_type = "clients"
    attr_keys: list[str] = []
    rel_keys: list[str] = []
    for params in ({"page[size]": "2"}, {"page[size]": "2", "page[number]": "1"}):
        status, body = get(params)
        print(f"\n== GET clients?{urlencode(params)} -> HTTP {status}")
        if status == 200 and isinstance(body, dict) and "data" in body:
            print("   top-level keys:", _keys(body))
            print("   meta:", _shape(body.get("meta")))
            print("   links:", _shape(body.get("links")))
            data = body.get("data") or []
            print(f"   data: list of {len(data)}")
            if data:
                first = data[0]
                cid = str(first.get("id") or "")
                client_id = cid if _ID_RE.fullmatch(cid) else None   # only a plain id may enter a URL path
                client_type = _ident(first.get("type")) if first.get("type") else client_type
                attr_keys = [k for k in _attrs(first).keys() if isinstance(k, str) and _IDENT.fullmatch(k)]
                rel_keys = [k for k in (first.get("relationships") or {}).keys() if isinstance(k, str) and _IDENT.fullmatch(k)]
                print("   item keys:", _keys(first), "type:", client_type)
                print("   attributes:", _shape(_attrs(first)))
                print("   relationships:", sorted(rel_keys))
            print("   included types:", _types(body.get("included")))
            break
        print("   errors:", _errors(body))
    if not client_id:
        print("   NO CLIENT ID LEARNED — steps needing one are skipped")

    # 2. Sparse fields, grounded in what step 1 observed (fallback to guesses).
    wanted = [k for k in attr_keys if re.search(r"phone|mobile|email|creat|status|archiv|active|prospect", k, re.I)]
    for fields in ([",".join(wanted)] if wanted else []) + ["phone,email,createdAt", "phoneNumber,email,createdAt"]:
        status, body = get({"page[size]": "2", "fields[clients]": fields})
        print(f"\n== GET clients?fields[clients]={fields} -> HTTP {status}")
        if status == 200 and isinstance(body, dict):
            d = body.get("data") or []
            print("   attributes:", _shape(_attrs(d[0])) if d else None)
            break
        print("   errors:", _errors(body))

    # 3. Phones/emails may be related resources: include names grounded in step 1.
    inc_candidates = [k for k in rel_keys if re.search(r"phone|email|contact", k, re.I)] or \
        ["phones", "phoneNumbers", "emails", "contactDetails"]
    if client_id:
        for inc in inc_candidates[:4]:
            status, body = _get(f"clients/{client_id}?{urlencode({'include': inc})}", cookies, budget, pacer)
            print(f"\n== GET clients/<id>?include={inc} -> HTTP {status}")
            if status == 200 and isinstance(body, dict):
                data = body.get("data") or {}
                incl = body.get("included") or []
                print("   relationships:", _keys(data.get("relationships")))
                print("   included:", _types(incl))
                if incl:
                    print("   included[0].attributes:", _shape(_attrs(incl[0])))
                    break   # learned nothing unless something was actually included
            else:
                print("   errors:", _errors(body))

    # 4. Server-side search: an impossible value, so nothing is ever returned.
    #    200 + empty data = parameter accepted; 400 = rejected.
    for key in ("filter[search]", "filter[query]", "filter[q]", "filter[name]", "filter[phone]"):
        status, body = get({key: "zzqzq-no-such-client-000", "page[size]": "1"})
        n = len(body.get("data") or []) if status == 200 and isinstance(body, dict) else None
        print(f"\n== GET clients?{key}=<impossible> -> HTTP {status}" + (f" · data {n} (accepted)" if n is not None else f" · {_errors(body)}"))

    # 5. Client status: are inactive / prospective clients in the default list?
    for val in ("inactive", "prospective", "archived"):
        status, body = get({"filter[status]": val, "page[size]": "1"})
        n = len(body.get("data") or []) if status == 200 and isinstance(body, dict) else None
        meta = _shape(body.get("meta")) if status == 200 and isinstance(body, dict) else None
        print(f"\n== GET clients?filter[status]={val} -> HTTP {status}" + (f" · data {n} · meta {meta}" if n is not None else f" · {_errors(body)}"))

    # 6. How an appointment links to its client — linkage only, NO include, so
    #    no client identity is fetched. Then verify filter[clientId] by ids.
    tr7 = _range(-7, 0)
    linkage_rel = None
    for rel in ("client", "clients", "appointmentClients", "clientCouple"):
        status, body = get({"filter[timeRange]": tr7, "fields[appointments]": f"startTime,attendanceStatus,thisType,{rel}", "include": ""}, "appointments")
        print(f"\n== GET appointments (last 7d) relationship '{rel}' -> HTTP {status}")
        if status == 200 and isinstance(body, dict):
            appts = [a for a in (body.get("data") or []) if _attrs(a).get("thisType") == "Appointment"]
            linked = [a for a in appts if _rel_data(a, rel)]
            types = Counter()
            for a in linked:
                dd = _rel_data(a, rel)
                for x in (dd if isinstance(dd, list) else [dd]):
                    if isinstance(x, dict):
                        types[_ident(x.get("type"))] += 1
            print(f"   client appointments {len(appts)} · with '{rel}' linkage {len(linked)} · linked types {dict(types)}")
            if appts:
                print("   relationship keys:", _keys(appts[0].get("relationships")))
            if linked:
                linkage_rel = rel
                break
        else:
            print("   errors:", _errors(body))

    if client_id:
        fields = "startTime,attendanceStatus,thisType" + (f",{linkage_rel}" if linkage_rel else "")
        status, body = get({"filter[clientId]": client_id, "filter[timeRange]": _range(-365, 120), "fields[appointments]": fields, "include": ""}, "appointments")
        print(f"\n== GET appointments?filter[clientId]=<id> (-365d..+120d) -> HTTP {status}")
        if status == 200 and isinstance(body, dict):
            d = body.get("data") or []
            if linkage_rel:
                def _owner_ids(a):
                    dd = _rel_data(a, linkage_rel)
                    return [str(x.get("id")) for x in (dd if isinstance(dd, list) else [dd]) if isinstance(x, dict)]
                mine = sum(1 for a in d if client_id in _owner_ids(a))
                print(f"   items {len(d)} · belonging to that client {mine}" + ("" if mine == len(d) else "   <<< FILTER IGNORED"))
            else:
                print(f"   items {len(d)} (ownership unverifiable — no linkage relationship learned)")
        else:
            print("   errors:", _errors(body))

    # 7. attendanceStatus vocabulary: past 45 days and next 30 days (counts only).
    for label, a, b in (("past 45d", -45, 0), ("next 30d", 0, 30)):
        status, body = get({"filter[timeRange]": _range(a, b), "fields[appointments]": "attendanceStatus,thisType", "include": ""}, "appointments")
        print(f"\n== attendanceStatus, {label} -> HTTP {status}")
        if status == 200 and isinstance(body, dict):
            d = [x for x in (body.get("data") or []) if _attrs(x).get("thisType") == "Appointment"]
            print(f"   client appointments {len(d)}:", Counter(str(_attrs(x).get("attendanceStatus"))[:30] for x in d))
        else:
            print("   errors:", _errors(body))

    print(f"\nrequests used: {budget.used}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except SessionExpired as exc:
        print(f"SESSION EXPIRED ({exc}) — stopping; the scheduler will refresh it")
        sys.exit(3)
    except safety.SafetyViolation as exc:   # our own messages, no page content
        print("stopped:", safety.scrub_text(str(exc)))
        sys.exit(1)
    except BaseException as exc:  # noqa: BLE001 — never print a traceback (locals hold page content)
        print(f"stopped: {type(exc).__name__}")
        sys.exit(1)
