-- ============================================================
-- MCW Clinician Matcher — live availability from SimplePractice (one-time)
-- Paste into the Supabase SQL Editor and click Run. Safe to re-run.
--
-- Filled by the sp-gateway service running on Fly.io, which reads MCW's PUBLIC
-- SimplePractice booking page. No login is used to produce this data and it
-- contains NO client information — only clinician names, professions and open
-- appointment times, exactly what any prospective client sees when booking.
-- ============================================================

-- 1) The table the gateway writes to
create table if not exists public.clinician_availability (
  -- SimplePractice's own clinician id. This is the natural key and it is what
  -- makes writes idempotent: a re-run overwrites rather than duplicating, so a
  -- missed cycle repairs itself on the next one.
  sp_clinician_id  text primary key,

  -- Our Matcher id. SimplePractice ids and Matcher ids are UNRELATED
  -- namespaces, so this is mapped deliberately (see step 4) and never
  -- auto-matched on name — a wrong match would show one clinician's openings
  -- under another's name, which is worse than showing none.
  clinician_id     text references public.clinicians(id) on delete set null,

  sp_name          text,
  profession       text,
  next_available_at timestamptz,
  weekdays         jsonb not null default '[]'::jsonb,
  office_ids       jsonb not null default '[]'::jsonb,

  -- SimplePractice's OWN freshness stamp, distinct from ours. Our poll interval
  -- is only half the staleness story; without this the app would claim data is
  -- fresher than it really is.
  sp_computed_at   timestamptz,
  fetched_at       timestamptz not null default now(),

  -- Structural refusal of client-level data. A clinician's name is public
  -- professional information; a 200-character free-text blob is not something
  -- this table should ever be able to hold.
  constraint sp_name_is_short check (sp_name is null or length(sp_name) <= 120)
);

create index if not exists clinician_availability_next_idx
  on public.clinician_availability (next_available_at nulls last);

-- 2) Freshness / health, so the app can say "checked 3 minutes ago" and go quiet
--    when the gateway dies rather than showing stale times as if they were live.
create table if not exists public.gateway_health (
  feed          text primary key,
  last_ok_at    timestamptz,
  last_status   text not null default 'unknown',
  last_row_count integer not null default 0,
  consecutive_failures integer not null default 0,
  note          text not null default ''
);

-- 3) Row-level security
alter table public.clinician_availability enable row level security;
alter table public.gateway_health enable row level security;

-- Everyone signed in may READ availability: it is public information and the
-- front desk needs it. Nobody may write it through the API — the gateway uses
-- the service role, which bypasses RLS entirely.
drop policy if exists "staff read availability" on public.clinician_availability;
create policy "staff read availability" on public.clinician_availability
  for select to authenticated using (true);

drop policy if exists "staff read gateway health" on public.gateway_health;
create policy "staff read gateway health" on public.gateway_health
  for select to authenticated using (true);

-- Deliberately NO insert/update/delete policies for authenticated users.
-- Availability is machine-written only; a human editing it by hand would create
-- exactly the confident-but-wrong answer this whole design exists to prevent.

-- 4) Map SimplePractice ids to Matcher ids.
--    Verified by hand on 2026-07-31 against the live booking page. Two are name
--    variants rather than different people: SimplePractice shows "Ashley
--    Sullivan" where the Matcher has "Ashe Sullivan", and "Theodosia Soula
--    Hareas" where the Matcher has "Soula Hareas".
--    Travis McNulty (sp id 1065521) is bookable in SimplePractice but has no
--    Matcher record, so he is intentionally absent below.
insert into public.clinician_availability (sp_clinician_id, clinician_id) values
  ('1912048','aimee'),            ('1859219','albena'),
  ('1693298','alyssa'),           ('1863098','amanda'),
  ('1812352','amy'),              ('1894267','anna'),
  ('1691551','ashe'),             ('822983','bjorn'),
  ('1912046','brittany'),         ('1912044','carolyn'),
  ('2044735','christine_farina'), ('1787526','christopher'),
  ('976347','emily_c'),           ('1075893','emily_t'),
  ('1829576','jamilah'),          ('1913042','jasmine'),
  ('1200524','joy'),              ('2045974','judy_franks'),
  ('1392089','kelly'),            ('1690553','kevin'),
  ('1228368','kiesa'),            ('1977587','lena'),
  ('2022030','levi_draper'),      ('2024521','lisa_smotherman'),
  ('1465566','madison'),          ('1071085','nicole'),
  ('949586','rachel'),            ('1175147','sarah'),
  ('1173740','shea'),             ('1097812','soula'),
  ('2022050','stephen_rochon'),   ('2037517','yasmin_panjwani')
on conflict (sp_clinician_id) do update set clinician_id = excluded.clinician_id;

-- 5) Let the Matcher receive availability changes over the Realtime connection
--    it already has open, instead of polling.
alter publication supabase_realtime add table public.clinician_availability;
alter publication supabase_realtime add table public.gateway_health;
