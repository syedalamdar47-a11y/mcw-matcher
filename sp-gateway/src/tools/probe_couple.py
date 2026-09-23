"""Structure-only probe: are a couple record's `grantedUsers` ids the two
individual client records? If so, a couple can be matched to a HubSpot phone
through its members. Prints counts and masked shapes only.
    fly ssh console --app mcw-sp-gateway -C "python -m src.tools.probe_couple"
"""

from __future__ import annotations

import json
import re
import sys
from urllib.parse import urlencode

from .. import config, safety, session
from .discover_clients import _errors, _get, _keys, _range, _shape, SessionExpired


def main() -> int:
    settings = config.load_settings()
    cookies = session.cookies_from_state(settings)
    if not cookies:
        print("no saved session — stopping")
        return 2
    budget = safety.RequestBudget(limit=20)
    pacer = safety.Pacer(settings.min_delay_s, settings.max_delay_s)
    get = lambda p, res: _get(f"{res}?{urlencode(p)}", cookies, budget, pacer)  # noqa: E731

    # Couple ids seen in the last 30 days of appointments (linkage only).
    status, body = get({"filter[timeRange]": _range(-30, 0), "fields[appointments]": "thisType,client", "include": ""}, "appointments")
    couples = []
    if status == 200 and isinstance(body, dict):
        for a in body.get("data") or []:
            dd = ((a.get("relationships") or {}).get("client") or {}).get("data") or {}
            if isinstance(dd, dict) and dd.get("type") == "clientCouples" and re.fullmatch(r"[A-Za-z0-9\-]{1,64}", str(dd.get("id") or "")):
                if str(dd["id"]) not in couples:
                    couples.append(str(dd["id"]))
    print(f"couples with an appointment in the last 30 days: {len(couples)}")

    resolved = 0
    tested = 0
    for cid in couples[:3]:
        status, body = _get(f"client-couples/{cid}?{urlencode({'fields[clientCouples]': 'grantedUsers,dateFirstVisit,status'})}", cookies, budget, pacer)
        if status != 200 or not isinstance(body, dict):
            print(f"  couple: HTTP {status} {_errors(body)}")
            continue
        attrs = (body.get("data") or {}).get("attributes") or {}
        raw = attrs.get("grantedUsers")
        try:
            ids = json.loads(raw) if isinstance(raw, str) else (raw or [])
        except Exception:
            ids = []
        ids = [str(i) for i in ids if re.fullmatch(r"[0-9]{1,20}", str(i))]
        print(f"  couple: grantedUsers count {len(ids)} · shape {_shape(raw)}")
        for mid in ids[:2]:
            tested += 1
            s2, b2 = _get(f"clients/{mid}?{urlencode({'fields[clients]': 'defaultPhoneNumber,status,createdAt'})}", cookies, budget, pacer)
            if s2 == 200 and isinstance(b2, dict):
                resolved += 1
                at = (b2.get("data") or {}).get("attributes") or {}
                print(f"    member -> clients/<id> HTTP 200 · has defaultPhoneNumber: {bool(at.get('defaultPhoneNumber'))} · keys {_keys(at)}")
            else:
                print(f"    member -> clients/<id> HTTP {s2} {_errors(b2)}")
    print(f"members tested {tested} · resolved as client records {resolved} · requests {budget.used}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except SessionExpired as exc:
        print(f"SESSION EXPIRED ({exc})")
        sys.exit(3)
    except BaseException as exc:  # noqa: BLE001
        print(f"stopped: {type(exc).__name__}")
        sys.exit(1)
