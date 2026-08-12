"""Offline tests for the free/busy engine. No network, no session, no PHI."""

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import calendar_engine as ce  # noqa: E402


def _avail(cid, start, end, occurrences):
    return {"attributes": {"startTime": start, "endTime": end, "occurrences": occurrences},
            "relationships": {"clinician": {"data": {"id": cid}}}}


def _appt(cid, start, end, status="Show"):
    return {"attributes": {"startTime": start, "endTime": end, "attendanceStatus": status},
            "relationships": {"clinician": {"data": {"id": cid}}}}


NOW = datetime.fromisoformat("2026-08-10T00:00:00-04:00")


def test_free_when_no_appointments():
    # 9:00-12:00 window, nothing booked → 09:00, 09:30, 10:00, 10:30, 11:00 (11:00+50=11:50<=12:00)
    av = [_avail("100", "2024-01-01T09:00:00-04:00", "2024-01-01T12:00:00-04:00",
                 ["2026-08-11T09:00:00-04:00"])]
    slots = ce.free_slots(av, [], now=NOW)
    got = [s[11:16] for s in slots["100"]]
    assert got == ["09:00", "09:30", "10:00", "10:30", "11:00"], got


def test_busy_block_removes_slots():
    # same window, but 10:00-11:00 is booked → 10:00 and 10:30 must disappear
    av = [_avail("100", "2024-01-01T09:00:00-04:00", "2024-01-01T12:00:00-04:00",
                 ["2026-08-11T09:00:00-04:00"])]
    ap = [_appt("100", "2026-08-11T10:00:00-04:00", "2026-08-11T11:00:00-04:00")]
    got = [s[11:16] for s in ce.free_slots(av, ap, now=NOW)["100"]]
    # 09:00 ok; 09:30 -> ends 10:20 overlaps 10:00 busy -> out; 10:00/10:30 busy;
    # 11:00 -> 11:50 free -> in
    assert "10:00" not in got and "10:30" not in got, got
    assert "09:00" in got and "11:00" in got, got


def test_non_client_block_counts_as_busy():
    # a therapist blocking personal time (no client) must still remove the slot
    av = [_avail("100", "2024-01-01T09:00:00-04:00", "2024-01-01T11:00:00-04:00",
                 ["2026-08-11T09:00:00-04:00"])]
    block = _appt("100", "2026-08-11T09:00:00-04:00", "2026-08-11T10:00:00-04:00")
    got = [s[11:16] for s in ce.free_slots(av, [block], now=NOW)["100"]]
    assert "09:00" not in got and "09:30" not in got, got


def test_cancelled_appointment_frees_time():
    av = [_avail("100", "2024-01-01T09:00:00-04:00", "2024-01-01T11:00:00-04:00",
                 ["2026-08-11T09:00:00-04:00"])]
    cancelled = _appt("100", "2026-08-11T09:00:00-04:00", "2026-08-11T10:00:00-04:00",
                      status="Cancelled")
    got = [s[11:16] for s in ce.free_slots(av, [cancelled], now=NOW)["100"]]
    assert "09:00" in got, got  # cancellation should NOT block


def test_past_slots_excluded():
    av = [_avail("100", "2024-01-01T09:00:00-04:00", "2024-01-01T12:00:00-04:00",
                 ["2026-08-09T09:00:00-04:00"])]  # yesterday relative to NOW
    slots = ce.free_slots(av, [], now=NOW)
    assert "100" not in slots or slots["100"] == [], slots


def test_two_clinicians_isolated():
    av = [_avail("100", "2024-01-01T09:00:00-04:00", "2024-01-01T10:00:00-04:00",
                 ["2026-08-11T09:00:00-04:00"]),
          _avail("200", "2024-01-01T14:00:00-04:00", "2024-01-01T15:00:00-04:00",
                 ["2026-08-11T14:00:00-04:00"])]
    # 100 is fully booked, 200 is free
    ap = [_appt("100", "2026-08-11T09:00:00-04:00", "2026-08-11T10:00:00-04:00")]
    slots = ce.free_slots(av, ap, now=NOW)
    assert slots.get("100", []) == [], slots
    assert slots.get("200"), slots


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        try:
            fn(); print(f"  PASS  {fn.__name__}"); passed += 1
        except Exception:
            print(f"  FAIL  {fn.__name__}"); traceback.print_exc()
    print(f"\n{passed}/{len(fns)} passed")
    raise SystemExit(0 if passed == len(fns) else 1)
