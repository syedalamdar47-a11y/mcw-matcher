"""Compute real free slots from the authenticated SimplePractice calendar.

  free = each clinician's AVAILABILITY windows  −  their BUSY appointments/blocks

This module is PURE: it takes already-fetched JSON (times only, no client data)
and returns free slot start-times per clinician. No network, no session, no PHI —
which is exactly why it is unit-tested offline against synthetic data.

Clinician identity: the calendar's clinician relationship id is the SAME id space
as the public booking clinician id (verified 2026-08-10: e.g. 1075893 = Emily
Tripp in both). So it maps straight onto `clinician_availability.sp_clinician_id`,
no extra lookup.

Data shapes (from discovery):
  availability item:
    attributes.startTime / endTime  -> window time-of-day span (duration)
    attributes.occurrences[]        -> concrete start datetimes within the range
    relationships.clinician.data.id -> sp_clinician_id
  appointment item:
    attributes.startTime / endTime / duration
    attributes.attendanceStatus     -> cancelled ones DON'T block
    attributes.isBusy / thisType    -> whether it blocks time
    relationships.clinician.data.id -> sp_clinician_id
"""

from __future__ import annotations

from datetime import datetime, timedelta

# Appointments in these states have freed their time — they do NOT block.
_CANCELLED = {"Cancelled", "Late Cancelled", "Clinician Cancelled"}

# Slotting grid. Without a per-service duration from SimplePractice we assume a
# standard session: offer starts every STEP minutes, each needing SLOT_MIN
# minutes of clear time inside an availability window. Both tunable.
SLOT_STEP_MIN = 30
SLOT_MIN_MINUTES = 50


def _parse(dt: str) -> datetime | None:
    if not dt or not isinstance(dt, str):
        return None
    try:
        return datetime.fromisoformat(dt)
    except ValueError:
        return None


def _clinician_id(item: dict) -> str | None:
    rel = (item.get("relationships") or {}).get("clinician") or {}
    data = rel.get("data") or {}
    cid = data.get("id")
    return str(cid) if cid is not None else None


def availability_windows(avail_items: list[dict]) -> dict[str, list[tuple[datetime, datetime]]]:
    """Concrete [start, end] open windows per clinician, from occurrences."""
    out: dict[str, list[tuple[datetime, datetime]]] = {}
    for item in avail_items or []:
        cid = _clinician_id(item)
        if not cid:
            continue
        a = item.get("attributes") or {}
        w_start = _parse(a.get("startTime"))
        w_end = _parse(a.get("endTime"))
        if not w_start or not w_end:
            continue
        duration = w_end - w_start
        if duration <= timedelta(0):
            continue
        for occ in a.get("occurrences") or []:
            start = _parse(occ)
            if not start:
                continue
            out.setdefault(cid, []).append((start, start + duration))
    return out


def busy_intervals(appt_items: list[dict]) -> dict[str, list[tuple[datetime, datetime]]]:
    """Blocking [start, end] intervals per clinician (excludes cancellations)."""
    out: dict[str, list[tuple[datetime, datetime]]] = {}
    for item in appt_items or []:
        cid = _clinician_id(item)
        if not cid:
            continue
        a = item.get("attributes") or {}
        if a.get("attendanceStatus") in _CANCELLED:
            continue  # cancelled → the time is free again
        start = _parse(a.get("startTime"))
        if not start:
            continue
        end = _parse(a.get("endTime"))
        if not end:
            # Fall back to duration, then to a 50-min default. A malformed
            # duration (non-numeric) must NOT crash the whole feed — that would
            # blank every clinician. Treat it as the default instead.
            try:
                dur = int(a.get("duration"))
            except (TypeError, ValueError):
                dur = 50
            end = start + timedelta(minutes=dur if dur > 0 else 50)
        if end <= start:
            continue
        out.setdefault(cid, []).append((start, end))
    return out


def _merge(intervals: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    if not intervals:
        return []
    ordered = sorted(intervals)
    merged = [ordered[0]]
    for s, e in ordered[1:]:
        ls, le = merged[-1]
        if s <= le:
            merged[-1] = (ls, max(le, e))
        else:
            merged.append((s, e))
    return merged


def _subtract(window: tuple[datetime, datetime],
              busy: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    """window minus busy → list of free sub-intervals."""
    ws, we = window
    free = [(ws, we)]
    for bs, be in busy:
        nxt = []
        for fs, fe in free:
            if be <= fs or bs >= fe:      # no overlap
                nxt.append((fs, fe))
            else:
                if bs > fs:
                    nxt.append((fs, bs))  # keep the part before the busy block
                if be < fe:
                    nxt.append((be, fe))  # keep the part after
        free = nxt
    return free


def compute_free(avail_items: list[dict], appt_items: list[dict], *, now: datetime,
                 step_min: int = SLOT_STEP_MIN,
                 slot_min: int = SLOT_MIN_MINUTES) -> dict[str, list[datetime]]:
    """ALL future open slot starts per clinician, sorted (no cap).

    A start qualifies only if [start, start+slot_min] lies entirely inside an
    availability window, overlaps no busy interval, and is in the future.
    This is the single source of truth; free_slots() and free_slots_by_day()
    are both thin views over it.
    """
    windows = availability_windows(avail_items)
    busy = busy_intervals(appt_items)
    step = timedelta(minutes=step_min)
    need = timedelta(minutes=slot_min)

    result: dict[str, list[datetime]] = {}
    for cid, wins in windows.items():
        clinician_busy = _merge(busy.get(cid, []))
        starts: set[datetime] = set()
        for win in _merge(wins):
            for fs, fe in _subtract(win, clinician_busy):
                t = fs
                while t + need <= fe:
                    if t >= now:
                        starts.add(t)
                    t += step
        ordered = sorted(starts)
        if ordered:
            result[cid] = ordered
    return result


def free_slots(avail_items: list[dict], appt_items: list[dict], *, now: datetime,
               keep: int = 12, step_min: int = SLOT_STEP_MIN,
               slot_min: int = SLOT_MIN_MINUTES) -> dict[str, list[str]]:
    """The next `keep` open slot start-times (ISO strings) per clinician."""
    return {
        cid: [t.isoformat() for t in starts[:keep]]
        for cid, starts in compute_free(avail_items, appt_items, now=now,
                                        step_min=step_min, slot_min=slot_min).items()
    }


def free_slots_by_day(avail_items: list[dict], appt_items: list[dict], *, now: datetime,
                      day_tz: str = "America/New_York", max_per_day: int = 16,
                      max_days: int = 14, step_min: int = SLOT_STEP_MIN,
                      slot_min: int = SLOT_MIN_MINUTES) -> dict[str, list[dict]]:
    """Open slots grouped by calendar DAY (practice timezone), per clinician.

    Returns {cid: [{"date": "YYYY-MM-DD", "slots": [iso, ...]}, ...]} — the data
    behind the "pick a future date" browser. Days are in the practice's timezone
    so a slot lands on the day an FDO would call it.
    """
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(day_tz)
    except Exception:
        tz = None

    out: dict[str, list[dict]] = {}
    for cid, starts in compute_free(avail_items, appt_items, now=now,
                                    step_min=step_min, slot_min=slot_min).items():
        by_day: dict[str, list[str]] = {}
        for t in starts:
            local = t.astimezone(tz) if tz else t
            key = local.strftime("%Y-%m-%d")
            by_day.setdefault(key, [])
            if len(by_day[key]) < max_per_day:
                by_day[key].append(t.isoformat())
        days = [{"date": d, "slots": by_day[d]} for d in sorted(by_day)][:max_days]
        if days:
            out[cid] = days
    return out
