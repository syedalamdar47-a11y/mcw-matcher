-- ============================================================
-- MCW Clinician Matcher — "pick a future date" support (one-time)
-- Paste into the Supabase SQL Editor and click Run. Safe to re-run.
--
-- Adds a per-clinician 2-week grid of open slots grouped by day, so the front
-- desk can browse any upcoming date, not just the soonest openings. The default
-- card view is unchanged — it still reads the existing `slots` column. This just
-- adds the fuller calendar behind a date picker.
-- ============================================================

alter table public.clinician_availability
  add column if not exists days jsonb not null default '[]'::jsonb;

-- Guard rail: an ordered array of at most ~14 day-buckets. Keeps a single
-- clinician row from ballooning a Realtime broadcast if the upstream shape ever
-- changes unexpectedly.
alter table public.clinician_availability
  drop constraint if exists days_is_bounded;
alter table public.clinician_availability
  add constraint days_is_bounded
  check (jsonb_typeof(days) = 'array' and jsonb_array_length(days) <= 21);
