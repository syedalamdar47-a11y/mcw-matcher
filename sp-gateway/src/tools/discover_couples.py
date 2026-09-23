"""Structure-only discovery for the two gaps the first client check found:

  * COUPLES — appointments can link to a `clientCouples` record that the
    /frontend/clients search never returns. Which endpoint lists couples, can it
    be searched, and how does a couple link to its two individual clients?
  * MINORS — a minor's own record may carry the parent's number only in the
    related `phones` resource, not in defaultPhoneNumber. Does a phone search
    hit such records, and does include=phones expose the number to compare?

Same posture as discover_clients: masked shapes, identifier-only keys, counts;
read-only GETs, no redirects, no sign-in, budget 30. Run from /app:
    fly ssh console --app mcw-sp-gateway -C "python -m src.tools.discover_couples"
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from urllib.parse import urlencode

from .. import config, safety, session
from .discover_clients import _errors, _get, _ident, _keys, _range, _shape, _types, SessionExpired


def main() -> int:
    settings = config.load_settings()
    cookies = session.cookies_from_state(settings)
    if not cookies:
        print("no saved session — stopping (this tool never signs in)")
        return 2
    budget = safety.RequestBudget(limit=30)
    pacer = safety.Pacer(settings.min_delay_s, settings.max_delay_s)

    def get(params: dict, resource: str):
        return _get(f"{resource}?{urlencode(params)}", cookies, budget, pacer)

    # 1. Which resource name lists couples?
    couple_id = None
    couple_resource = None
    for resource in ("client-couples", "clientCouples", "couples", "client_couples"):
        status, body = get({"page[size]": "2"}, resource)
        print(f"\n== GET {resource}?page[size]=2 -> HTTP {status}")
        if status == 200 and isinstance(body, dict) and "data" in body:
            data = body.get("data") or []
            print(f"   data: list of {len(data)} · top-level keys {_keys(body)}")
            if data:
                first = data[0]
                cid = str(first.get("id") or "")
                couple_id = cid if re.fullmatch(r"[A-Za-z0-9\-]{1,64}", cid) else None
                couple_resource = resource
                print("   type:", _ident(first.get("type")), "· item keys:", _keys(first))
                print("   attributes:", _shape(first.get("attributes")))
                print("   relationships:", _keys(first.get("relationships")))
            break
        print("   errors:", _errors(body))

    # 2. Fall back: take a couple id from a recent appointment's linkage.
    if not couple_id:
        status, body = get({"filter[timeRange]": _range(-14, 0), "fields[appointments]": "thisType,client", "include": ""}, "appointments")
        if status == 200 and isinstance(body, dict):
            for a in body.get("data") or []:
                dd = ((a.get("relationships") or {}).get("client") or {}).get("data") or {}
                if isinstance(dd, dict) and _ident(dd.get("type")) == "clientCouples":
                    cid = str(dd.get("id") or "")
                    couple_id = cid if re.fullmatch(r"[A-Za-z0-9\-]{1,64}", cid) else None
                    break
        print(f"\n== couple id from appointment linkage: {'found' if couple_id else 'none'}")

    # 3. A single couple record: how does it reference its clients / phones?
    if couple_id:
        for resource in ([couple_resource] if couple_resource else []) + ["client-couples", "clientCouples"]:
            for inc in ("", "clients", "phones"):
                status, body = _get(f"{resource}/{couple_id}?{urlencode({'include': inc})}", cookies, budget, pacer)
                print(f"\n== GET {resource}/<id>?include={inc} -> HTTP {status}")
                if status == 200 and isinstance(body, dict):
                    data = body.get("data") or {}
                    print("   attributes:", _shape(data.get("attributes")))
                    print("   relationships:", _keys(data.get("relationships")))
                    incl = body.get("included") or []
                    print("   included:", _types(incl))
                    if incl:
                        print("   included[0].attributes:", _shape(incl[0].get("attributes")))
                else:
                    print("   errors:", _errors(body))
            if status == 200:
                break

    # 4. Can couples be searched? (impossible term → accepted if 200)
    for resource in ([couple_resource] if couple_resource else ["client-couples"]):
        status, body = get({"filter[search]": "zzqzq-no-such-000", "page[size]": "1"}, resource)
        n = len(body.get("data") or []) if status == 200 and isinstance(body, dict) else None
        print(f"\n== GET {resource}?filter[search]=<impossible> -> HTTP {status}" + (f" · data {n} (accepted)" if n is not None else f" · {_errors(body)}"))

    # 5. Do appointments accept a couple id in filter[clientId]? (count only)
    if couple_id:
        status, body = get({"filter[clientId]": couple_id, "filter[timeRange]": _range(-365, 120),
                            "fields[appointments]": "thisType,client", "include": ""}, "appointments")
        n = len(body.get("data") or []) if status == 200 and isinstance(body, dict) else None
        owned = 0
        if n:
            for a in body["data"]:
                dd = ((a.get("relationships") or {}).get("client") or {}).get("data") or {}
                if isinstance(dd, dict) and str(dd.get("id")) == couple_id:
                    owned += 1
        print(f"\n== appointments?filter[clientId]=<couple id> -> HTTP {status} · items {n} · owned by that couple {owned}")

    # 6. Does the clients search find a minor whose number is only in `phones`?
    #    Take a client whose defaultPhoneNumber is empty but who has a phones record.
    status, body = get({"page[size]": "25", "fields[clients]": "defaultPhoneNumber", "include": "phones"}, "clients")
    print(f"\n== GET clients?page[size]=25&include=phones -> HTTP {status}")
    if status == 200 and isinstance(body, dict):
        data = body.get("data") or []
        incl = {str(i.get("id")): i for i in (body.get("included") or []) if isinstance(i, dict)}
        no_default = [c for c in data if not (c.get("attributes") or {}).get("defaultPhoneNumber")]
        print(f"   clients {len(data)} · without defaultPhoneNumber {len(no_default)} · included phones {len(incl)}")
        print("   relationship keys:", _keys(data[0].get("relationships")) if data else None)
        probe = None
        for c in no_default:
            rel = ((c.get("relationships") or {}).get("phones") or {}).get("data") or []
            for r in (rel if isinstance(rel, list) else [rel]):
                ph = incl.get(str((r or {}).get("id")))
                if ph and re.sub(r"\D", "", str((ph.get("attributes") or {}).get("number") or "")):
                    probe = (c, ph)
                    break
            if probe:
                break
        if probe:
            c, ph = probe
            digits = re.sub(r"\D", "", str(ph["attributes"]["number"]))
            digits = digits[1:] if len(digits) == 11 and digits.startswith("1") else digits
            status, body = get({"filter[search]": digits, "fields[clients]": "defaultPhoneNumber", "page[size]": "10"}, "clients")
            ids = {str(x.get("id")) for x in (body.get("data") or [])} if status == 200 and isinstance(body, dict) else set()
            print(f"   phone-only client: search by its phones.number digits -> HTTP {status} · hits {len(ids)} · includes that client: {str(c.get('id')) in ids}")
        else:
            print("   no client in this page has a phone only in `phones` — inconclusive")

    print(f"\nrequests used: {budget.used}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except SessionExpired as exc:
        print(f"SESSION EXPIRED ({exc}) — stopping")
        sys.exit(3)
    except safety.SafetyViolation as exc:
        print("stopped:", safety.scrub_text(str(exc)))
        sys.exit(1)
    except BaseException as exc:  # noqa: BLE001
        print(f"stopped: {type(exc).__name__}")
        sys.exit(1)
