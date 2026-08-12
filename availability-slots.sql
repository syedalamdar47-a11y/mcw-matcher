-- ============================================================
-- MCW Clinician Matcher — multiple open slots per clinician (one-time)
-- Paste into the Supabase SQL Editor and click Run. Safe to re-run.
--
-- Run availability-setup.sql first. This adds the next N openings per
-- clinician, not just the soonest one, so the front desk can offer a choice.
-- ============================================================

-- Slots live as an ordered JSON array on the clinician's existing row rather
-- than in a child table. Three reasons:
--   * one row per clinician means one Realtime message per change, and Realtime
--     is billed per message per open browser tab
--   * replacing the whole array is atomic, so a clinician can never be seen
--     half-updated with a mix of old and new times
--   * "show 4, then expand" is a slice of an array, needing no second query
alter table public.clinician_availability
  add column if not exists slots jsonb not null default '[]'::jsonb;

-- When the SLOT LIST was last refreshed. Distinct from fetched_at, which covers
-- the cheap roster sweep. The two run on different schedules, so collapsing them
-- into one timestamp would overstate how fresh the later slots are.
alter table public.clinician_availability
  add column if not exists slots_fetched_at timestamptz;

-- Guard rail: this column holds appointment START/END times only. Capping the
-- array length stops an upstream change quietly turning a clinician row into a
-- multi-megabyte Realtime broadcast to every open tab.
alter table public.clinician_availability
  drop constraint if exists slots_is_bounded;
alter table public.clinician_availability
  add constraint slots_is_bounded
  check (jsonb_typeof(slots) = 'array' and jsonb_array_length(slots) <= 60);
