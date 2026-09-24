"""Structure-only discovery: how does SimplePractice's own search box find COUPLES?

Why: the nightly client check could not find 6 of 10 September couples. Alam
searched one of them by hand in SimplePractice's search box and it came straight
up as a "Couple" result listing both partners. So SimplePractice CAN search
couples; we only need to learn which request its search box makes and what a
couple result looks like, then teach the check to do the same.

Three questions, answered without printing any client value:
  A. Which API paths does the web app itself use for search / couples? Read the
     app's own JavaScript bundles (static code, never a page that could carry
     client data) and list the short string literals that mention "search" or
     "couple", digit runs masked.
  B. Do the search endpoints return couple records? For each HubSpot contact
     given (by HubSpot id; name and phone are read here from the FDO dashboard's
     synced copy and held in memory only) print: result counts by type, the
     attribute / relationship KEY names of non-individual results, the included
     resource types, and yes/no values — "the surname and first partner appear",
     "every partner appears", "this phone number appears".
  C. For one MATCHED couple record: its attribute keys and value TYPES, and
     whether appointments?filter[clientId]=<couple id> lists sessions owned by
     exactly that record (type AND id checked).

PHI POSTURE: key names, types, counts, booleans only. Server error output is
reduced to status + code + title with every value this tool sent blanked out.
No input file: HubSpot ids go on the command line and nothing else does, so no
name ever travels through a shell, a command string or a file. Read-only GETs,
https app host only, no redirects, paced, budget-capped at 60; stops on 429 or
5xx. Reuses the saved session; never signs in (exit 3 if it has expired).

    fly ssh console --app mcw-sp-gateway -C "python -u -m src.tools.discover_couple_search <hubspot id> [<hubspot id> ...]"
"""

from __future__ import annotations

import logging
import re
import sys
from collections import Counter
from urllib.parse import urlencode, urljoin, urlparse

from .. import config, safety, session
from ..sink import Sink
from .check_clients import _digits, _fold
from .discover_clients import SessionExpired, _get, _ident, _keys, _range

APP = f"https://{config.SP_APP_HOST}"
BUDGET = 60
MAX_ITEMS = 6
MAX_PAGES = 5
MAX_SCRIPTS = 12
_HS_ID = re.compile(r"[0-9]{1,20}")
_ID_RE = re.compile(r"[A-Za-z0-9\-]{1,64}")
# A JS string literal: same quote both ends, path-ish characters only.
_LITERAL = re.compile(r"""(["'`])([A-Za-z0-9_\-/.\[\]?=&:{}$]{3,80})\1""")
_WANTED = re.compile(r"search|couple", re.I)
_AUTH_PATH = re.compile(r"sign_in|sign_out|saml|logout|login", re.I)
_PARTNERS = re.compile(r"\s*(?:&|\band\b|/|\+|,)\s*", re.I)


class Stop(RuntimeError):
    """Rate limit / server error: stop instead of hammering. Fixed messages only."""


# ------------------------------------------------------------------ output --

def _mask_literal(lit: str) -> str:
    lit = re.split(r"[?=]", lit)[0]                  # never a query value
    return re.sub(r"\d{3,}", "N", lit)               # never an id or a number


def _mask_path(path: str) -> str:
    segs = [("<seg>" if (re.search(r"\d", s) or len(s) > 40) else s) for s in path.split("/")]
    return "/".join(segs)[:120]


def _safe_errors(body, sent: list[str]) -> str:
    """status + code + title only (never detail/source), with every value this
    tool sent — and anything id- or number-shaped — blanked out."""
    if not isinstance(body, dict):
        return ""
    parts = []
    for e in (body.get("errors") or [])[:3]:
        if isinstance(e, dict):
            parts.append(f"{e.get('status', '')} {e.get('code', '')} {e.get('title', '')}".strip())
    s = " ; ".join(parts)
    for v in sorted({x for x in sent if x and len(x) >= 2}, key=len, reverse=True):
        s = re.sub(re.escape(v), "<v>", s, flags=re.I)
    s = re.sub(r"\b(?=[A-Za-z0-9\-]*\d)[A-Za-z0-9\-]{3,}\b", "<id>", s)   # ids, numbers, mixed tokens
    return safety.scrub_text(s, max_len=120)


def _dicts(x) -> list[dict]:
    return [i for i in x if isinstance(i, dict)] if isinstance(x, list) else []


def _strings(v, depth: int = 0):
    """Every string inside a JSON value (in-memory matching only)."""
    if depth > 6:
        return
    if isinstance(v, str):
        yield v
    elif isinstance(v, list):
        for x in v:
            yield from _strings(x, depth + 1)
    elif isinstance(v, dict):
        for x in v.values():
            yield from _strings(x, depth + 1)


# -------------------------------------------------------------------- http --

def _get_text(url: str, cookies, budget, pacer) -> tuple[int, str, str, str]:
    """GET a page or script on the app host over https. (status, ctype, text, location)"""
    import httpx

    u = urlparse(url)
    if u.scheme != "https" or u.hostname != config.SP_APP_HOST:
        raise safety.SafetyViolation("refusing non-https or off-host fetch")
    safety.assert_allowed_url(url)
    safety.assert_read_only("GET", url)
    budget.spend()
    pacer.wait()
    with httpx.Client(timeout=60, follow_redirects=False) as client:
        resp = client.get(url, cookies=cookies)
    if resp.status_code == 429 or resp.status_code >= 500:
        raise Stop(f"HTTP {resp.status_code}")
    return resp.status_code, resp.headers.get("content-type", ""), resp.text, resp.headers.get("location", "")


def _api(path_qs: str, cookies, budget, pacer):
    status, body = _get(path_qs, cookies, budget, pacer)
    if status == 429 or status >= 500:
        raise Stop(f"HTTP {status}")
    return status, body


# --------------------------------------------------------------- A: code ----

def _script_sources(html: str, base: str) -> list[str]:
    found = re.findall(r"""<script[^>]+src=["']([^"']+)["']""", html)
    found += re.findall(r"""<link[^>]+href=["']([^"']+\.js(?:\?[^"']*)?)["']""", html)
    out = []
    for src in found:
        try:
            url = urljoin(base, src)
        except ValueError:
            continue
        if url not in out:
            out.append(url)
    return out


def _step_a(cookies, budget, pacer) -> None:
    pages = ["/calendar", "/clients", "/"]
    seen: set[str] = set()
    scripts: list[str] = []
    fetches = 0
    while pages and fetches < MAX_PAGES and not scripts:
        path = pages.pop(0)
        if path in seen:
            continue
        seen.add(path)
        status, ctype, text, location = _get_text(APP + path, cookies, budget, pacer)
        fetches += 1
        loc = None
        if location:
            try:
                loc = urlparse(urljoin(APP + path, location))
            except ValueError:
                loc = None
        to_auth = bool(loc and (loc.hostname != config.SP_APP_HOST or _AUTH_PATH.search(loc.path or "")))
        print(f"\n== GET app page {_mask_path(path)} -> HTTP {status} · {ctype.split(';')[0]}"
              + (f" · redirect (same host: {bool(loc and loc.hostname == config.SP_APP_HOST)}, to sign-in: {to_auth})" if location else ""))
        if status in (401, 403) or to_auth:
            raise SessionExpired(f"status {status}")
        if loc and 300 <= status < 400:
            pages.insert(0, loc.path or "/")           # same-host, non-auth redirect
            continue
        if status == 200 and "html" in ctype:
            scripts = _script_sources(text, APP + path)   # only <script src>/<link href=.js>; page text is never scanned
    ok = [u for u in scripts if (p := urlparse(u)).scheme == "https" and p.hostname == config.SP_APP_HOST
          and p.path.endswith(".js") and not _AUTH_PATH.search(p.path)]
    external = [u for u in scripts if urlparse(u).scheme == "https" and urlparse(u).hostname != config.SP_APP_HOST]
    print(f"   script sources {len(scripts)} · fetchable on app host {len(ok)} · external https {len(external)}")
    for u in external[:10]:
        p = urlparse(u)
        print(f"   external script: https://{p.hostname}{_mask_path(p.path)}")
    rank = lambda u: (1 if re.search(r"vendor|runtime|polyfill|analytics|sentry|chunk-vendors", u, re.I) else 0)  # noqa: E731
    ok.sort(key=rank)
    literals: Counter = Counter()
    for u in ok[:MAX_SCRIPTS]:
        status, _, text, _ = _get_text(u, cookies, budget, pacer)
        print(f"   script {_mask_path(urlparse(u).path)} -> HTTP {status} · {len(text)} chars")
        if status == 200:
            for _, lit in _LITERAL.findall(text):
                if _WANTED.search(lit):
                    literals[_mask_literal(lit)] += 1
    if len(ok) > MAX_SCRIPTS:
        print(f"   ({len(ok) - MAX_SCRIPTS} further scripts not read)")
    couple = sorted(k for k in literals if re.search("couple", k, re.I))
    search = sorted(k for k in literals if k not in couple and "/" in k)
    print(f"\n== string literals: {len(literals)} mention search/couple · couple {len(couple)} · search paths {len(search)}")
    for k in couple[:120]:
        print(f"   {literals[k]:>4}  {k}")
    for k in search[:120]:
        print(f"   {literals[k]:>4}  {k}")


# ------------------------------------------------------------ B/C: search ----

def _load_people(settings, ids: list[str]) -> list[dict]:
    fdo = Sink(settings, url=settings.fdo_supabase_url, key=settings.fdo_supabase_service_key)
    rows = fdo.select("dashboard_contacts", params={
        "select": "hubspot_contact_id,first_name,last_name,phone_normalized",
        "hubspot_contact_id": f"in.({','.join(ids)})",
    }, page_size=100, max_pages=1)
    by = {str(r.get("hubspot_contact_id")): r for r in rows if isinstance(r, dict)}
    return [by[i] for i in ids if i in by]


def _matches(item: dict, included: list[dict], partners: list[str], last: str, phone: str) -> tuple[bool, bool, bool]:
    """(first partner + surname appear, every partner + surname appear, phone appears)"""
    rel_ids = set()
    for rel in (item.get("relationships") or {}).values():
        d = (rel or {}).get("data") if isinstance(rel, dict) else None
        for x in (d if isinstance(d, list) else [d]):
            if isinstance(x, dict):
                rel_ids.add((x.get("type"), str(x.get("id"))))
    linked = [i for i in included if (i.get("type"), str(i.get("id"))) in rel_ids]
    blob = list(_strings(item.get("attributes"))) + [s for i in linked for s in _strings(i.get("attributes"))]
    folded = " ".join(_fold(s) for s in blob)
    digits = {_digits(s) for s in blob} | {_digits(m) for s in blob for m in re.findall(r"[\d()\-. +]{10,}", s)}
    has_last = bool(last) and last in folded
    first_ok = has_last and bool(partners) and partners[0] in folded
    all_ok = has_last and bool(partners) and all(p in folded for p in partners)
    return first_ok, all_ok, bool(phone) and phone in digits


def _describe(label: str, body, partners, last, phone) -> list[tuple[dict, bool]]:
    data = _dicts(body.get("data")) if isinstance(body, dict) else []
    incl = _dicts(body.get("included")) if isinstance(body, dict) else []
    tcount = Counter(_ident(d.get("type")) for d in data)
    print(f"   {label}: results {len(data)} · types {dict(tcount)} · included {dict(Counter(_ident(i.get('type')) for i in incl))}")
    out = []
    for d in data:
        first_ok, all_ok, ph_ok = _matches(d, incl, partners, last, phone)
        if d.get("type") != "clients" or first_ok or ph_ok:
            out.append((d, first_ok or ph_ok))
    for d, _ in out[:4]:
        first_ok, all_ok, ph_ok = _matches(d, incl, partners, last, phone)
        print(f"     - type {_ident(d.get('type'))} · surname+first partner {first_ok} · every partner {all_ok} · phone {ph_ok}")
        print(f"       attribute keys {_keys(d.get('attributes'))} · relationship keys {_keys(d.get('relationships'))}")
    return [(d, m) for d, m in out if d.get("type") != "clients"]


def _step_bc(people: list[dict], cookies, budget, pacer) -> None:
    chosen = None           # (couple id, type), from a MATCHED couple result first
    fallback = None
    for n, p in enumerate(people, 1):
        raw_first = str(p.get("first_name") or "").strip()
        raw_last = str(p.get("last_name") or "").strip()
        partners = [x for x in (_fold(s) for s in _PARTNERS.split(raw_first)) if x]
        last = _fold(raw_last)
        phone = _digits(p.get("phone_normalized"))
        term = f"{raw_first} {raw_last}".strip()
        sent = [raw_first, raw_last, term, phone, last] + partners
        print(f"\n== person {n} · first-name parts {len(partners)} · has surname {bool(last)} · has 10-digit phone {len(phone) == 10}")
        probes = []
        if partners and last:
            probes.append(("clients · full name", "clients", {"filter[search]": term, "page[size]": "10"}))
        if len(raw_last) >= 2:
            probes.append(("clients · surname only", "clients", {"filter[search]": raw_last, "page[size]": "10"}))
        if len(phone) == 10:
            probes.append(("clients · phone digits", "clients", {"filter[search]": phone, "page[size]": "10"}))
        if n == 1 and term:
            probes.append(("client-couples · full name", "client-couples", {"filter[search]": term, "page[size]": "10"}))
        if not probes:
            print("   skipped (no name and no phone)")
            continue
        for label, resource, params in probes:
            status, body = _api(f"{resource}?{urlencode(params)}", cookies, budget, pacer)
            if status != 200:
                print(f"   {label}: HTTP {status} {_safe_errors(body, sent)}")
                continue
            for d, matched in _describe(label, body, partners, last, phone):
                cid = str(d.get("id") or "")
                if not _ID_RE.fullmatch(cid):
                    continue
                if matched and not chosen:
                    chosen = (cid, str(d.get("type") or ""))
                elif not fallback:
                    fallback = (cid, str(d.get("type") or ""))
        if budget.used > BUDGET - 12:
            print("   (stopping searches — keeping budget for step C)")
            break

    if not chosen:
        print("\n== no MATCHED couple record returned by any search"
              + (" (an unmatched couple result was seen; not examined)" if fallback else ""))
        return
    cid, ctype_ = chosen
    resource = re.sub(r"(?<!^)(?=[A-Z])", "-", ctype_).lower()
    if re.fullmatch(r"[a-z][a-z\-]{1,40}", resource):
        status, body = _api(f"{resource}/{cid}", cookies, budget, pacer)
        print(f"\n== GET {resource}/<id> -> HTTP {status}")
        data = body.get("data") if isinstance(body, dict) else None
        if status == 200 and isinstance(data, dict):
            attrs = data.get("attributes") if isinstance(data.get("attributes"), dict) else {}
            print("   attribute types:", {_ident(k): type(v).__name__ for k, v in list(attrs.items())[:40]})
            print("   relationship keys:", _keys(data.get("relationships")))
        elif status != 200:
            print("   error:", _safe_errors(body, [cid]))
    else:
        print("\n== couple record GET skipped (unmapped type)")
    status, body = _api("appointments?" + urlencode({
        "filter[clientId]": cid, "filter[timeRange]": _range(-180, 90),
        "fields[appointments]": "startTime,attendanceStatus,thisType,client", "include": ""}), cookies, budget, pacer)
    print(f"\n== appointments?filter[clientId]=<couple id> (-180d..+90d) -> HTTP {status}")
    if status != 200:
        print("   error:", _safe_errors(body, [cid]))
        return
    appts = [a for a in _dicts(body.get("data") if isinstance(body, dict) else None)
             if (a.get("attributes") or {}).get("thisType") == "Appointment"]
    owners: Counter = Counter()
    owned = 0
    for a in appts:
        rel = ((a.get("relationships") or {}).get("client") or {}).get("data")
        if isinstance(rel, dict):
            owners[_ident(rel.get("type"))] += 1
            if str(rel.get("id")) == cid and rel.get("type") == ctype_:
                owned += 1
    print(f"   appointments {len(appts)} · owner types {dict(owners)} · owned by exactly that couple {owned}"
          f" · statuses {dict(Counter(str((a.get('attributes') or {}).get('attendanceStatus'))[:20] for a in appts))}")


def main(argv: list[str]) -> int:
    logging.getLogger("httpx").setLevel(logging.WARNING)      # never log request URLs (they carry names)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    ids = [a for a in argv if _HS_ID.fullmatch(a)][:MAX_ITEMS]
    if not ids or len(ids) != len(argv[:MAX_ITEMS]):
        print("usage: python -m src.tools.discover_couple_search <hubspot id> [<hubspot id> ...]  (digits only, max 6)")
        return 2
    settings = config.load_settings()
    if not (settings.fdo_supabase_url and settings.fdo_supabase_service_key):
        print("FDO_SUPABASE_URL / FDO_SUPABASE_SERVICE_KEY not set — cannot read the synced contacts")
        return 2
    cookies = session.cookies_from_state(settings)
    if not cookies:
        print("no saved session — stopping (this tool never signs in)")
        return 2
    budget = safety.RequestBudget(limit=BUDGET)
    pacer = safety.Pacer(settings.min_delay_s, settings.max_delay_s)
    people = _load_people(settings, ids)
    print(f"people loaded {len(people)} of {len(ids)}")
    _step_a(cookies, budget, pacer)
    _step_bc(people, cookies, budget, pacer)
    print(f"\nrequests used: {budget.used}")
    return 0


if __name__ == "__main__":
    code = 1
    try:
        code = main(sys.argv[1:])
    except SessionExpired as exc:
        print(f"SESSION EXPIRED ({exc}) — stopping; the scheduler will refresh it")
        code = 3
    except Stop as exc:
        print(f"stopped: {exc} from SimplePractice — not retrying")
    except safety.SafetyViolation as exc:
        print("stopped:", safety.scrub_text(str(exc)))
    except BaseException as exc:  # noqa: BLE001 — never a traceback (locals hold names)
        print(f"stopped: {type(exc).__name__}")
    sys.exit(code)
