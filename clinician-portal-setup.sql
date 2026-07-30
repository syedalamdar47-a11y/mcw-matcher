-- ============================================================
-- MCW Clinician Matcher — Clinician self-service portal (one-time)
-- Paste into the Supabase SQL Editor and click Run. Safe to re-run.
--
-- Adds a 5th role, "clinician", for therapists/psychiatrists who log in to
-- maintain their OWN specialties and modalities. A clinician can:
--   * see ONLY their own record (never the roster, rates, notes or priorities)
--   * SUBMIT proposed changes — they can never write to the live record
-- An Admin/Owner (or Emily as clinical director) reviews and approves, which
-- is what Patrick asked for in the 07/29 management meeting.
-- ============================================================

-- 1) Allow the new role
alter table public.user_roles drop constraint if exists user_roles_role_check;
alter table public.user_roles
  add constraint user_roles_role_check
  check (role in ('owner','admin','frontdesk','viewer','clinician'));

-- 2) Link a login to the clinician record it owns (null for staff logins)
alter table public.user_roles
  add column if not exists clinician_id text references public.clinicians(id) on delete set null;

-- 3) Helper: which clinician record does the current user own?
create or replace function public.current_clinician_id()
returns text language sql stable security definer set search_path = public as $$
  select clinician_id from public.user_roles where user_id = auth.uid()
$$;

-- 4) Proposed-changes queue
create table if not exists public.clinician_change_requests (
  id uuid primary key default gen_random_uuid(),
  clinician_id text not null references public.clinicians(id) on delete cascade,
  submitted_by uuid references auth.users(id) on delete set null,
  submitted_at timestamptz not null default now(),
  proposed_specialties jsonb not null default '[]'::jsonb,
  proposed_modalities jsonb not null default '[]'::jsonb,
  note text not null default '',
  status text not null default 'pending' check (status in ('pending','approved','rejected')),
  reviewed_by uuid references auth.users(id) on delete set null,
  reviewed_at timestamptz,
  review_note text not null default ''
);
create index if not exists ccr_pending_idx on public.clinician_change_requests (status, submitted_at desc);

-- 5) RLS on the queue
alter table public.clinician_change_requests enable row level security;

drop policy if exists "clinician sees own requests" on public.clinician_change_requests;
create policy "clinician sees own requests" on public.clinician_change_requests
  for select to authenticated
  using (
    public.current_app_role() in ('owner','admin','frontdesk','viewer')
    or clinician_id = public.current_clinician_id()
  );

drop policy if exists "clinician submits own requests" on public.clinician_change_requests;
create policy "clinician submits own requests" on public.clinician_change_requests
  for insert to authenticated
  with check (
    clinician_id = public.current_clinician_id()
    and status = 'pending'
  );

drop policy if exists "admins review requests" on public.clinician_change_requests;
create policy "admins review requests" on public.clinician_change_requests
  for update to authenticated
  using (public.current_app_role() in ('owner','admin'))
  with check (public.current_app_role() in ('owner','admin'));

-- 6) Clinicians table: a "clinician" login sees ONLY their own row.
--    Staff roles keep full read access.
drop policy if exists "staff can read" on public.clinicians;
create policy "staff can read" on public.clinicians
  for select to authenticated
  using (
    public.current_app_role() in ('owner','admin','frontdesk','viewer')
    or id = public.current_clinician_id()
  );

-- Note: the existing update/insert/delete policies already exclude 'clinician'
-- (they require owner/admin/frontdesk), so a clinician can never write to the
-- live roster — only submit a change request. Nothing to change there.

-- 7) Convenience view for the review screen: pending requests + current values
create or replace view public.pending_change_review as
  select r.id, r.clinician_id, c.name, c.profile,
         c.specialties as current_specialties, c.modalities as current_modalities,
         r.proposed_specialties, r.proposed_modalities,
         r.note, r.submitted_at, r.status
  from public.clinician_change_requests r
  join public.clinicians c on c.id = r.clinician_id
  where r.status = 'pending';
