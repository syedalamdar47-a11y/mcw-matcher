-- ============================================================
-- MCW Clinician Matcher — multi-slot availability (one-time)
-- Paste into the Supabase SQL Editor and click Run. Safe to re-run.
--
-- Extends availability-setup.sql from "one next-available time per clinician"
-- to "the next N open times per clinician, N configurable, more on demand".
--
-- Run availability-setup.sql FIRST. This file assumes public.clinicians,
-- public.clinician_availability, public.gateway_health and
-- public.current_app_role() already exist.
--
-- Same data lane as before: MCW's PUBLIC SimplePractice booking page. No login
-- produces any of this, and it contains NO client information — only clinician
-- names, professions and open appointment times, exactly what a prospective
-- client sees when booking.
--
-- THE ONE DESIGN DECISION THIS FILE RESTS ON
-- A clinician's open times are stored as ONE ORDERED JSON ARRAY IN ONE ROW,
-- not as one row per slot. The reason is not storage, it is honesty under
-- failure. A row-per-slot table cannot be refreshed without a delete step, and
-- for the instant between the delete and the insert a clinician looks emptier
-- than they are — which, on a live phone call, means the front desk tells a
-- caller "she has nothing" about someone with five openings. An array in a
-- single column has no such instant: a reader sees the whole old list or the
-- whole new list and never a half-built one. See section 3 for the write.
-- ============================================================


-- ------------------------------------------------------------
-- 1) Structural refusal of anything that is not a time
--
-- This function is the check constraint behind the slots column. A clinician's
-- open appointment time is a timestamp, an optional end timestamp, and an
-- office id. Nothing in that list is free text, so the column is built so that
-- free text CANNOT BE STORED IN IT AT ALL. That is the same reasoning as
-- sp_name_is_short in availability-setup.sql, applied to a structure instead of
-- a string: a value that must match an ISO-8601 date pattern and be under 32
-- characters cannot be a person's name, an email address, a phone number or a
-- note. The refusal is enforced by the database, not by the gateway remembering.
--
-- Slot shape, deliberately short keys — every change to this row is pushed to
-- every open browser tab and billed per message, so the key names are paid for
-- once per slot per tab per change:
--     s = start  (ISO-8601 timestamp, required)
--     e = end    (ISO-8601 timestamp, optional)
--     o = office id (short string, optional)
-- ------------------------------------------------------------
create or replace function public.slots_shape_ok(v jsonb)
returns boolean language sql immutable as $$
  select case
    when v is null then false
    when jsonb_typeof(v) <> 'array' then false
    else coalesce((
      select bool_and(
             jsonb_typeof(el) = 'object'
         and el ? 's'
         -- No key other than s/e/o may exist. A future contributor cannot
         -- quietly start stashing a client name in here under a new key.
         and not exists (
               select 1 from jsonb_object_keys(el) k where k not in ('s','e','o')
             )
         and jsonb_typeof(el->'s') = 'string'
         and length(el->>'s') <= 32
         and el->>'s' ~ '^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}'
         and (el->'e' is null or (
               jsonb_typeof(el->'e') = 'string'
               and length(el->>'e') <= 32
               and el->>'e' ~ '^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}'))
         and (el->'o' is null or (
               jsonb_typeof(el->'o') = 'string' and length(el->>'o') <= 24))
      )
      from jsonb_array_elements(v) el
    ), true)   -- an empty array is valid: it means "checked, genuinely nothing open"
  end
$$;


-- ------------------------------------------------------------
-- 2) The slot list — one row per clinician, in its own table
--
-- WHY A SEPARATE TABLE RATHER THAN A COLUMN ON clinician_availability
-- The two facts are refreshed on genuinely different schedules. The cheap
-- roster-wide call re-confirms the FIRST open time every minute; the expensive
-- per-clinician call re-confirms the WHOLE LIST every fifteen. If both lived in
-- one row they would share one fetched_at, and every fast write would restamp
-- the slow data as if it had just been checked. The UI would then say slots
-- #2-#4 were verified seconds ago when they were verified a quarter of an hour
-- ago. Splitting the tables makes that particular lie unrepresentable rather
-- than merely discouraged.
--
-- It also keeps the hot path small: the once-a-minute write touches a ~250-byte
-- row instead of dragging the whole slot array through the replication stream
-- and out to every open tab.
-- ------------------------------------------------------------
create table if not exists public.clinician_slots (
  -- Same natural key as clinician_availability, so the write is an idempotent
  -- upsert and a missed cycle repairs itself on the next one. The foreign key
  -- means the gateway must write clinician_availability BEFORE clinician_slots
  -- in a cycle; a slot list for a clinician we have never seen is a bug, and
  -- failing loudly here is better than orphaning it.
  sp_clinician_id  text primary key
                   references public.clinician_availability(sp_clinician_id)
                   on delete cascade,

  -- The whole list, ordered ascending by start. Replacing this column IS the
  -- refresh: there is no separate delete of the times that are gone.
  slots            jsonb not null default '[]'::jsonb,

  -- Convenience only, for eyeballing the table in the Supabase editor and for
  -- the sweep queue in section 6. The UI must use future_slot_count from the
  -- view in section 7 instead, because this counts slots that may have elapsed.
  slot_count       integer generated always as (
                     case when jsonb_typeof(slots) = 'array'
                          then jsonb_array_length(slots) else 0 end
                   ) stored,

  -- How far ahead we actually looked. Without this, "only 2 times" is
  -- ambiguous between "she is nearly full" and "we only asked about this week",
  -- and the front desk cannot tell which. When horizon_end has elapsed the list
  -- is not short, it is expired — see the blanking rule in section 7.
  horizon_start    timestamptz,
  horizon_end      timestamptz,

  -- Which appointment type this list was priced for. SimplePractice returns
  -- different openings per CPT code, so a list without this is unattributable.
  cpt_code_id      text,

  -- WHEN WE LAST RE-CONFIRMED THIS LIST. Advances on every successful
  -- per-clinician fetch even when nothing changed, because "we looked again and
  -- it is still true" is the single most useful thing the UI can tell an
  -- operator. This is the tier-2 freshness clock.
  slots_checked_at timestamptz not null default now(),

  -- When the list last actually changed. Set by the trigger in section 3, never
  -- by the writer, so it cannot drift from reality.
  slots_changed_at timestamptz not null default now(),

  -- SimplePractice's OWN freshness stamp for this list, distinct from ours.
  sp_computed_at   timestamptz,

  constraint slots_is_array check (jsonb_typeof(slots) = 'array'),
  -- A hard ceiling on how big one Realtime message can get. A vendor change
  -- that starts returning six months of openings would otherwise quietly turn
  -- a 1 KB push into a 200 KB push, multiplied by every open tab.
  constraint slots_bounded  check (jsonb_typeof(slots) <> 'array'
                                   or jsonb_array_length(slots) <= 40),
  constraint slots_shape    check (public.slots_shape_ok(slots)),
  constraint cpt_code_short check (cpt_code_id is null or length(cpt_code_id) <= 40)
);

-- The rotating sweep asks "who has not been checked longest?" every cycle.
create index if not exists clinician_slots_checked_idx
  on public.clinician_slots (slots_checked_at asc);


-- ------------------------------------------------------------
-- 3) Making the write atomic, monotonic and quiet
--
-- ATOMIC. The refresh is a single upsert (see the statement at the bottom of
-- this section). Six times becoming three is one new value for one column: the
-- three that are gone cannot linger, because there is nowhere for them to
-- linger. A crash part-way through the batch aborts the whole statement, so
-- some clinicians keep an older list — never a list mixing old and new times.
-- There is no delete step to crash between, and no window in which a clinician
-- reads as emptier than they are.
--
-- MONOTONIC. Cycles overlap: a slow response from one cycle can land after a
-- fast response from the next. Without a guard, the older list silently wins
-- and the board goes backwards. The trigger drops any write whose
-- slots_checked_at is older than what is already stored.
--
-- QUIET. Returning NULL from a BEFORE UPDATE trigger skips the write entirely,
-- so no row version is created, no WAL is written, and no Realtime message is
-- billed or pushed to any tab. Used only for exact duplicate writes here; an
-- unchanged list with a NEWER check time still writes, because re-confirmation
-- is real information the UI needs.
-- ------------------------------------------------------------
create or replace function public.guard_slot_write()
returns trigger language plpgsql as $$
begin
  -- Out-of-order arrival: an older observation must never overwrite a newer one.
  if new.slots_checked_at < old.slots_checked_at then
    return null;
  end if;

  -- Exact duplicate (a retried request): nothing to say, say nothing.
  if new.slots_checked_at = old.slots_checked_at
     and new.slots is not distinct from old.slots then
    return null;
  end if;

  -- The writer never sets slots_changed_at; it is derived here so it cannot
  -- disagree with the data it describes.
  if new.slots is distinct from old.slots then
    new.slots_changed_at := new.slots_checked_at;
  else
    new.slots_changed_at := old.slots_changed_at;
  end if;

  return new;
end
$$;

drop trigger if exists guard_slot_write on public.clinician_slots;
create trigger guard_slot_write
  before update on public.clinician_slots
  for each row execute function public.guard_slot_write();


-- The companion guard on the FAST table. The roster-wide call runs every minute
-- and re-sends all 33 clinicians whether or not anything moved. Writing rows
-- that did not change would push ~31,700 Realtime messages per open tab per day
-- carrying no news. This suppresses them, which means fetched_at on that table
-- now reads as "when this clinician's first opening last CHANGED". Liveness —
-- "is the feed still running at all" — comes from gateway_health instead, and
-- is one row rather than thirty-three.
create or replace function public.suppress_unchanged_availability()
returns trigger language plpgsql as $$
begin
  if  new.clinician_id      is not distinct from old.clinician_id
  and new.sp_name           is not distinct from old.sp_name
  and new.profession        is not distinct from old.profession
  and new.next_available_at is not distinct from old.next_available_at
  and new.weekdays          is not distinct from old.weekdays
  and new.office_ids        is not distinct from old.office_ids then
    return null;
  end if;
  return new;
end
$$;

drop trigger if exists suppress_unchanged_availability on public.clinician_availability;
create trigger suppress_unchanged_availability
  before update on public.clinician_availability
  for each row execute function public.suppress_unchanged_availability();

-- THE WRITE, for reference. The gateway sends this as a PostgREST upsert with
-- on_conflict=sp_clinician_id, which is exactly the existing Sink.upsert() call
-- with a different table name — no new plumbing in the gateway.
--
--   insert into public.clinician_slots
--     (sp_clinician_id, slots, horizon_start, horizon_end,
--      cpt_code_id, slots_checked_at, sp_computed_at)
--   values (...)
--   on conflict (sp_clinician_id) do update set
--     slots            = excluded.slots,
--     horizon_start    = excluded.horizon_start,
--     horizon_end      = excluded.horizon_end,
--     cpt_code_id      = excluded.cpt_code_id,
--     slots_checked_at = excluded.slots_checked_at,
--     sp_computed_at   = excluded.sp_computed_at;
--
-- TWO RULES THE WRITER MUST FOLLOW, and they are the only two:
--   (a) A clinician who was queried and has nothing open is written with
--       slots = '[]'. NOT skipped. Skipping is how a clinician who just got
--       fully booked keeps advertising yesterday's times.
--   (b) A clinician who was NOT queried this cycle is not written at all. Their
--       row keeps its older list and its older slots_checked_at, and the
--       staleness rule in section 7 decides whether it is still fit to show.


-- ------------------------------------------------------------
-- 4) How many to show, and when to stop believing the data
--
-- One row, editable by an admin without a deploy. Alam asked for four and for a
-- "show more"; hard-coding four means the next number is an engineering ticket.
-- The staleness limits live here too, expressed as MISSED CYCLES rather than
-- absolute seconds. That matters: the gateway slows down overnight when nobody
-- is booking, and an absolute 5-minute ceiling would blank the entire board
-- every night for a feed that is working perfectly.
-- ------------------------------------------------------------
create table if not exists public.availability_settings (
  -- Single-row table. The check on a boolean primary key is the cheapest way to
  -- make a second row impossible.
  id                  boolean primary key default true check (id),
  slots_shown         integer not null default 4  check (slots_shown between 1 and 20),
  slots_max           integer not null default 12 check (slots_max between 1 and 40),
  -- Tier 1 (first opening) is dead after this many missed roster-wide cycles.
  tier1_missed_cycles integer not null default 3  check (tier1_missed_cycles between 1 and 20),
  -- Tier 2 (the full list) is dead after this many missed full sweeps.
  tier2_missed_sweeps integer not null default 2  check (tier2_missed_sweeps between 1 and 10),
  -- Never blank faster than this, however short the interval, so a one-off
  -- slow cycle does not make the board flicker mid-call.
  min_stale_floor_s   integer not null default 180 check (min_stale_floor_s between 30 and 3600),
  -- SimplePractice's own cache lag we are willing to pass on to a caller.
  -- Beyond this the number is theirs, not ours, and it is too old to say aloud.
  sp_lag_max_s        integer not null default 900 check (sp_lag_max_s between 60 and 7200),
  updated_at          timestamptz not null default now()
);

insert into public.availability_settings (id) values (true)
on conflict (id) do nothing;


-- ------------------------------------------------------------
-- 5) Health, extended so "broken" and "slow" are different answers
--
-- last_ok_at alone cannot distinguish "our gateway died" from "SimplePractice
-- is refusing us". Those need different people to do different things, so the
-- feed records the last ATTEMPT separately from the last SUCCESS:
--   attempt recent, ok old  -> SimplePractice is the problem; we are still trying
--   attempt old,    ok old  -> our gateway is the problem; nothing is trying
-- expected_interval_s is the feed declaring its own current cadence, which is
-- what lets the staleness rule adapt when the schedule slows down overnight.
-- ------------------------------------------------------------
alter table public.gateway_health
  add column if not exists last_attempt_at     timestamptz,
  add column if not exists last_duration_ms    integer,
  add column if not exists expected_interval_s integer;

-- The note field is the ONLY free-form column anywhere in this pipeline, which
-- makes it the only place client data could ever accidentally land — typically
-- by someone logging an exception message that quoted an HTTP response body.
-- Constraining it to a single lowercase snake_case token makes that structurally
-- impossible: no spaces, no capitals, no @, no dot, and it must begin with a
-- letter. A name, an email address, a phone number and a URL are all unable to
-- satisfy it. Current vocabulary:
--   page_load_timeout  shape_changed   empty_harvest   network_error
--   http_429  http_403  http_5xx       budget_exhausted
--   breaker_open  sweep_partial  sp_cache_stale  stopped
alter table public.gateway_health drop constraint if exists gateway_health_note_is_a_code;
alter table public.gateway_health add  constraint gateway_health_note_is_a_code
  check (note = '' or note ~ '^[a-z][a-z0-9_]{0,39}$');

alter table public.gateway_health drop constraint if exists gateway_health_status_vocab;
alter table public.gateway_health add  constraint gateway_health_status_vocab
  check (last_status in ('unknown','ok','failed','blocked','shape_changed',
                         'breaker_open','stopped'));

-- Success. Resets the failure counter and moves both clocks.
create or replace function public.record_feed_ok(
  p_feed        text,
  p_row_count   integer,
  p_interval_s  integer,
  p_duration_ms integer default null,
  p_note        text    default ''
) returns void language sql security definer set search_path = public as $$
  insert into public.gateway_health as g
    (feed, last_ok_at, last_attempt_at, last_status, last_row_count,
     consecutive_failures, expected_interval_s, last_duration_ms, note)
  values
    (p_feed, now(), now(), 'ok', greatest(coalesce(p_row_count,0),0),
     0, greatest(coalesce(p_interval_s,60),1), p_duration_ms, coalesce(p_note,''))
  on conflict (feed) do update set
    last_ok_at           = now(),
    last_attempt_at      = now(),
    last_status          = 'ok',
    last_row_count       = excluded.last_row_count,
    consecutive_failures = 0,
    expected_interval_s  = excluded.expected_interval_s,
    last_duration_ms     = excluded.last_duration_ms,
    note                 = excluded.note;
$$;

-- Failure. Deliberately does NOT touch last_ok_at or last_row_count: those
-- describe the last time we actually knew something, and a failure is precisely
-- the moment they must stop moving. Writing them here is the bug that would
-- make a dead feed look alive.
create or replace function public.record_feed_fail(
  p_feed   text,
  p_status text,
  p_note   text default ''
) returns void language sql security definer set search_path = public as $$
  insert into public.gateway_health as g
    (feed, last_status, last_attempt_at, consecutive_failures, note)
  values (p_feed, p_status, now(), 1, coalesce(p_note,''))
  on conflict (feed) do update set
    last_status          = excluded.last_status,
    last_attempt_at      = now(),
    consecutive_failures = g.consecutive_failures + 1,
    note                 = excluded.note;
$$;

-- Only the gateway may write health. A signed-in front-desk user forging an
-- "ok" would re-enable exactly the stale times this whole design exists to
-- suppress, so the grant is removed from everyone else.
revoke execute on function public.record_feed_ok(text,integer,integer,integer,text)
  from public, anon, authenticated;
revoke execute on function public.record_feed_fail(text,text)
  from public, anon, authenticated;
grant  execute on function public.record_feed_ok(text,integer,integer,integer,text)
  to service_role;
grant  execute on function public.record_feed_fail(text,text)
  to service_role;

-- Seed the two feed rows so the UI has something to read before the first cycle.
insert into public.gateway_health (feed, last_status, expected_interval_s) values
  ('sp_next_slots', 'unknown', 60),
  ('sp_slots',      'unknown', 900)
on conflict (feed) do nothing;


-- ------------------------------------------------------------
-- 6) The sweep queue — which clinicians the expensive call should fetch next
--
-- The cheap roster-wide call costs one request and covers everyone. The
-- expensive per-clinician call costs one request EACH. This view turns that
-- asymmetry into an ordering, so the gateway asks the database "who next?"
-- rather than carrying its own scheduling state.
--
--   priority 0 — we have never fetched this clinician's list, or the cheap tier
--                now reports a first opening that disagrees with the first entry
--                in the stored list. That disagreement is a booking or a
--                cancellation we can SEE, and it is worth a request immediately.
--   priority 1 — everyone else, oldest check first.
--
-- The honest limit of priority 0: it can only detect changes to the FIRST
-- opening. If slot #3 is booked, the first opening is unchanged and this view
-- notices nothing. That is not a flaw to be fixed, it is the reason the
-- priority-1 rotation exists, and it is why slots #2 onward are shown with a
-- different freshness stamp than slot #1.
--
-- ONE THING TO WATCH. /slots is asked for a specific CPT code and office;
-- next-slots is not. If the CPT mapping is wrong, slot #0 will disagree with
-- next_available_at for EVERYONE and every clinician will sit at priority 0
-- forever. That does not break anything — the ordering falls back to
-- oldest-checked-first and the queue degrades into a plain rotation — but the
-- gateway should log a warning when the priority-0 count stays near the full
-- roster, because it means the mapping needs another look rather than that the
-- practice is unusually busy.
-- ------------------------------------------------------------
create or replace view public.slots_sweep_queue
with (security_invoker = true) as
select
  a.sp_clinician_id,
  a.clinician_id,
  a.next_available_at,
  s.slots_checked_at,
  case
    when s.sp_clinician_id is null then 0
    when a.next_available_at is distinct from (s.slots->0->>'s')::timestamptz then 0
    else 1
  end as priority,
  coalesce(s.slots_checked_at, 'epoch'::timestamptz) as order_key
from public.clinician_availability a
left join public.clinician_slots s using (sp_clinician_id)
order by priority asc, order_key asc;

-- The gateway's whole scheduling decision, once per cycle. Repeat the ORDER BY
-- at the call site: a view's own ordering is not contractually preserved once
-- an outer query wraps it.
--   select sp_clinician_id from public.slots_sweep_queue
--   order by priority, order_key limit :n;


-- ------------------------------------------------------------
-- 7) The one place that decides what is fit to show
--
-- Alam's rule, made mechanical: when the data is too old, the app goes BLANK
-- rather than showing times that may already be booked. A blank cell makes an
-- operator check SimplePractice. A stale time makes them promise it to a caller.
--
-- The rule is written once, here, as a view, so the definition cannot drift
-- between the SQL and the JavaScript. The app reads this view on load; because
-- Realtime pushes changes on the BASE tables, script.js re-applies the same
-- rule client-side on each push — this view is the specification it implements.
--
-- security_invoker makes the view run with the caller's own permissions, so the
-- existing RLS still applies through it. Without that flag the view would run
-- as its owner and would hand availability to anon.
-- ------------------------------------------------------------
create or replace view public.availability_live
with (security_invoker = true) as
with cfg as (
  select * from public.availability_settings where id
),
h1 as (
  select last_ok_at, last_attempt_at, last_status, consecutive_failures,
         coalesce(expected_interval_s, 60) as interval_s
  from public.gateway_health where feed = 'sp_next_slots'
),
h2 as (
  select last_ok_at, last_status, consecutive_failures,
         coalesce(expected_interval_s, 900) as interval_s
  from public.gateway_health where feed = 'sp_slots'
)
select
  a.sp_clinician_id,
  a.clinician_id,
  a.sp_name,
  a.profession,

  ---------------------------------------------------------------- freshness
  -- Tier 1 is a single roster-wide call, so "when was this clinician's first
  -- opening last re-confirmed" is the same instant for everyone: the feed's own
  -- last success. There is no per-clinician variation to store.
  h1.last_ok_at                                       as next_slot_confirmed_at,
  extract(epoch from now() - h1.last_ok_at)::int      as tier1_age_s,

  -- Tier 2 IS per-clinician, because the expensive call is selective.
  s.slots_checked_at                                  as slots_confirmed_at,
  extract(epoch from now() - s.slots_checked_at)::int as tier2_age_s,
  s.slots_changed_at,

  -- The lag decomposition. These three are the whole staleness story and they
  -- must be reported separately, because only one of them is ours to fix:
  --   sp_cache_lag_s  how stale SimplePractice's OWN answer already was at the
  --                   moment we asked. A fixed property of the observation, not
  --                   something that grows while we sit here. Not ours.
  --   our_poll_lag_s  how long ago we asked. Ours; shrinks if we poll faster.
  --   total_lag_s     what the caller is actually exposed to = the sum.
  extract(epoch from a.fetched_at - a.sp_computed_at)::int as sp_cache_lag_s,
  extract(epoch from now() - h1.last_ok_at)::int           as our_poll_lag_s,
  extract(epoch from now() - a.sp_computed_at)::int        as total_lag_s,

  ---------------------------------------------------------------- liveness
  (h1.last_status = 'ok'
   and h1.consecutive_failures = 0
   and h1.last_ok_at is not null
   and now() - h1.last_ok_at <= make_interval(secs =>
         greatest(cfg.min_stale_floor_s, cfg.tier1_missed_cycles * h1.interval_s))
  ) as gateway_live,

  ---------------------------------------------------------------- what to show
  -- Tier 1. Blanked when the gateway is not live, or when SimplePractice's own
  -- cache lag has pushed the total past what we are willing to say aloud.
  case when (h1.last_status = 'ok'
             and h1.consecutive_failures = 0
             and h1.last_ok_at is not null
             and now() - h1.last_ok_at <= make_interval(secs =>
                   greatest(cfg.min_stale_floor_s, cfg.tier1_missed_cycles * h1.interval_s))
             and (a.sp_computed_at is null
                  or now() - a.sp_computed_at <= make_interval(secs => cfg.sp_lag_max_s)))
       then a.next_available_at end                        as next_available_at,

  -- Tier 2. Everything tier 1 requires, PLUS its own per-clinician check age,
  -- PLUS the horizon still being in the future. Slots that have already elapsed
  -- are dropped here rather than left for the client to notice.
  case when (h1.last_status = 'ok'
             and h1.consecutive_failures = 0
             and h1.last_ok_at is not null
             and now() - h1.last_ok_at <= make_interval(secs =>
                   greatest(cfg.min_stale_floor_s, cfg.tier1_missed_cycles * h1.interval_s))
             and (a.sp_computed_at is null
                  or now() - a.sp_computed_at <= make_interval(secs => cfg.sp_lag_max_s))
             and s.slots_checked_at is not null
             and now() - s.slots_checked_at <= make_interval(secs =>
                   greatest(cfg.min_stale_floor_s, cfg.tier2_missed_sweeps * h2.interval_s))
             and (s.horizon_end is null or s.horizon_end > now()))
       then fs.future_slots else '[]'::jsonb end           as slots,

  fs.future_count                                          as future_slot_count,
  cfg.slots_shown,
  cfg.slots_max,
  s.horizon_end,

  -- Why it is blank. Without this an operator sees an empty cell and cannot
  -- tell "she is booked solid" from "the feed is down", which are opposite
  -- instructions for what to do next.
  case
    when h1.last_ok_at is null                                   then 'never_fetched'
    when h1.last_status <> 'ok' or h1.consecutive_failures > 0   then 'gateway_failing'
    when now() - h1.last_ok_at > make_interval(secs =>
           greatest(cfg.min_stale_floor_s, cfg.tier1_missed_cycles * h1.interval_s))
                                                                 then 'gateway_down'
    when a.sp_computed_at is not null
     and now() - a.sp_computed_at > make_interval(secs => cfg.sp_lag_max_s)
                                                                 then 'sp_cache_stale'
    when s.slots_checked_at is null                              then 'slots_never_fetched'
    when now() - s.slots_checked_at > make_interval(secs =>
           greatest(cfg.min_stale_floor_s, cfg.tier2_missed_sweeps * h2.interval_s))
                                                                 then 'slots_stale'
    when s.horizon_end is not null and s.horizon_end <= now()     then 'horizon_elapsed'
    else 'ok'
  end                                                            as blank_reason

from public.clinician_availability a
left join public.clinician_slots s using (sp_clinician_id)
cross join cfg
left join h1 on true
left join h2 on true
left join lateral (
  -- Past times are dropped, and the order is re-established on read so a
  -- writer that forgot to sort cannot produce a mis-ordered board.
  select coalesce(
           jsonb_agg(el order by (el->>'s')::timestamptz), '[]'::jsonb
         ) as future_slots,
         count(*)::int as future_count
  from jsonb_array_elements(coalesce(s.slots, '[]'::jsonb)) el
  where (el->>'s')::timestamptz > now()
) fs on true;


-- ------------------------------------------------------------
-- 8) Row-level security
--
-- Identical posture to availability-setup.sql: signed-in staff may READ,
-- nobody may WRITE through the API. Availability is machine-written only,
-- because a human editing it by hand produces exactly the confident-but-wrong
-- answer this design exists to prevent. The gateway uses the service role,
-- which bypasses RLS entirely.
-- ------------------------------------------------------------
alter table public.clinician_slots        enable row level security;
alter table public.availability_settings  enable row level security;

drop policy if exists "staff read slots" on public.clinician_slots;
create policy "staff read slots" on public.clinician_slots
  for select to authenticated using (true);

drop policy if exists "staff read availability settings" on public.availability_settings;
create policy "staff read availability settings" on public.availability_settings
  for select to authenticated using (true);

-- The ONE thing a human is allowed to change: how many times to show, and how
-- old is too old. Restricted to admin/owner because loosening sp_lag_max_s is
-- how someone well-meaning re-enables stale times for the whole practice.
drop policy if exists "admins tune availability settings" on public.availability_settings;
create policy "admins tune availability settings" on public.availability_settings
  for update to authenticated
  using      (public.current_app_role() in ('owner','admin'))
  with check (public.current_app_role() in ('owner','admin'));

-- Deliberately NO insert/update/delete policies on clinician_slots.


-- ------------------------------------------------------------
-- 9) Realtime
--
-- Wrapped in a guard because ALTER PUBLICATION ... ADD TABLE errors if the
-- table is already a member, which would make this file fail on a second run.
-- (availability-setup.sql has that problem at its final two lines.)
-- ------------------------------------------------------------
do $$
begin
  if not exists (
    select 1 from pg_publication_tables
    where pubname = 'supabase_realtime'
      and schemaname = 'public' and tablename = 'clinician_slots'
  ) then
    execute 'alter publication supabase_realtime add table public.clinician_slots';
  end if;

  if not exists (
    select 1 from pg_publication_tables
    where pubname = 'supabase_realtime'
      and schemaname = 'public' and tablename = 'availability_settings'
  ) then
    execute 'alter publication supabase_realtime add table public.availability_settings';
  end if;
end
$$;


-- ------------------------------------------------------------
-- 10) OPTIONAL — the commit check's memory
--
-- When an operator clicks a time to offer it, the app re-verifies THAT EXACT
-- SLOT against SimplePractice before it is spoken aloud. This table records
-- only the OUTCOME, and exists for one reason: it is the only measurement of
-- how often the pipeline is actually wrong. Without it, "is 15 minutes good
-- enough?" stays an opinion.
--
-- It records NOTHING about the caller. Not a name, not a number, not a reason.
-- The question it answers is "was this time still there?", and the caller's
-- identity is not part of that question. There is no column that could hold it.
-- ------------------------------------------------------------
create table if not exists public.slot_commit_checks (
  id              bigint generated always as identity primary key,
  sp_clinician_id text not null,
  slot_start      timestamptz not null,
  checked_at      timestamptz not null default now(),
  -- still_open: the offer was safe. taken: we caught a booking the feed had not
  -- yet seen. unknown: SimplePractice did not answer in time.
  outcome         text not null check (outcome in ('still_open','taken','unknown')),
  -- How stale the list was at the moment of the click. This is the number that
  -- tells you whether the poll interval needs to change.
  slot_age_s      integer,
  latency_ms      integer
);

create index if not exists slot_commit_checks_recent_idx
  on public.slot_commit_checks (checked_at desc);

alter table public.slot_commit_checks enable row level security;

drop policy if exists "staff read commit checks" on public.slot_commit_checks;
create policy "staff read commit checks" on public.slot_commit_checks
  for select to authenticated using (true);

drop policy if exists "staff log commit checks" on public.slot_commit_checks;
create policy "staff log commit checks" on public.slot_commit_checks
  for insert to authenticated with check (true);

-- Not added to supabase_realtime: nobody needs to watch these arrive, and every
-- row would be a push to every open tab for no operational benefit.
