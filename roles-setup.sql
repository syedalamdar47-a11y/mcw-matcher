-- ============================================================
-- MCW Clinician Matcher — Roles & permissions (one-time)
-- Paste into the Supabase SQL Editor and click Run.
--
-- Safe to run on the live system: it SEEDS existing users first, so nobody
-- loses access. Roles: owner > admin > frontdesk > viewer.
--   owner    — full control incl. delete + managing admins (that's you)
--   admin    — manage roster + invite/manage staff
--   frontdesk— daily updates: availability, priority, notes, specialties, modalities
--   viewer   — read-only board
-- ============================================================

-- 1) Roles table
create table if not exists public.user_roles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  email text,
  role text not null default 'frontdesk' check (role in ('owner','admin','frontdesk','viewer')),
  updated_at timestamptz not null default now()
);

-- 2) Seed EVERY existing user so no one is locked out.
--    You = owner; the nightly audit bot = viewer (read-only); everyone else = frontdesk.
insert into public.user_roles (user_id, email, role)
select id, email,
  case
    when email = 'syedalamdar47@gmail.com' then 'owner'
    when email = 'audit-bot@mcnultycounseling.com' then 'viewer'
    else 'frontdesk'
  end
from auth.users
on conflict (user_id) do nothing;

-- 3) Helper: the current user's role (SECURITY DEFINER so RLS policies can call it)
create or replace function public.current_app_role()
returns text language sql stable security definer set search_path = public as $$
  select role from public.user_roles where user_id = auth.uid()
$$;

-- 4) RLS on user_roles: everyone signed in can READ the team list; only
--    admins/owner can change roles, with anti-escalation guards.
alter table public.user_roles enable row level security;

drop policy if exists "read roles" on public.user_roles;
create policy "read roles" on public.user_roles
  for select to authenticated using (true);

-- Insert/update/delete limited to admin/owner. Owner-level rows and promoting
-- someone to 'owner' are reserved for an existing owner (stops an admin from
-- escalating themselves or hijacking the owner account).
drop policy if exists "admins manage roles" on public.user_roles;
create policy "admins manage roles" on public.user_roles
  for all to authenticated
  using (
    public.current_app_role() in ('owner','admin')
    and (role <> 'owner' or public.current_app_role() = 'owner')
  )
  with check (
    public.current_app_role() in ('owner','admin')
    and (role <> 'owner' or public.current_app_role() = 'owner')
  );

-- 5) Tighten clinicians RLS to respect roles.
alter table public.clinicians enable row level security;

drop policy if exists "staff can read" on public.clinicians;
create policy "staff can read" on public.clinicians
  for select to authenticated using (true);

-- Viewers cannot write; everyone else (frontdesk/admin/owner) can UPDATE.
drop policy if exists "staff can update" on public.clinicians;
create policy "editors can update" on public.clinicians
  for update to authenticated
  using (public.current_app_role() in ('owner','admin','frontdesk'))
  with check (public.current_app_role() in ('owner','admin','frontdesk'));

-- Only admin/owner can add or remove clinicians.
drop policy if exists "staff can insert" on public.clinicians;
create policy "admins can insert" on public.clinicians
  for insert to authenticated
  with check (public.current_app_role() in ('owner','admin'));

drop policy if exists "staff can delete" on public.clinicians;
create policy "admins can delete" on public.clinicians
  for delete to authenticated
  using (public.current_app_role() in ('owner','admin'));

-- 6) Column guard: front-desk UPDATEs may only touch the daily fields.
--    Editing rates/offices/schedule/name/deactivating is an admin/owner action.
create or replace function public.enforce_frontdesk_columns()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  if public.current_app_role() = 'frontdesk' then
    if new.name is distinct from old.name
       or new.profile is distinct from old.profile
       or new.type is distinct from old.type
       or new.offices is distinct from old.offices
       or new.virtual is distinct from old.virtual
       or new.indiv is distinct from old.indiv
       or new."indivDisplay" is distinct from old."indivDisplay"
       or new.couples is distinct from old.couples
       or new.family is distinct from old.family
       or new.schedule is distinct from old.schedule
       or new.groups is distinct from old.groups
       or new.active is distinct from old.active then
      raise exception 'Front-desk role may only edit availability, priority, notes, specialties and modalities.';
    end if;
  end if;
  return new;
end;
$$;

drop trigger if exists frontdesk_column_guard on public.clinicians;
create trigger frontdesk_column_guard
  before update on public.clinicians
  for each row execute function public.enforce_frontdesk_columns();
