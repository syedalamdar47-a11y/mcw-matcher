-- ============================================================
-- MCW Clinician Matcher — Phase 2 upgrade (one-time)
-- Paste into the Supabase SQL Editor and click Run.
-- Adds the "active" flag used by Deactivate/Reactivate
-- (soft-delete: hide a clinician from staff without losing data).
-- ============================================================

alter table public.clinicians
  add column if not exists active boolean not null default true;
