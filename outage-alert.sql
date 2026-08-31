-- ============================================================
-- MCW Clinician Matcher — automated gateway-outage email alerts
-- Paste into the Supabase SQL Editor and Run. Safe to re-run.
--
-- WHAT: every 5 minutes, Supabase itself checks the gateway heartbeat
-- (gateway_health.last_ok_at). If the gateway has been silent for more than
-- 20 minutes DURING BUSINESS HOURS (6:30am-8pm Eastern — overnight silence is
-- by design), it emails Alam through Resend. One email per outage, a reminder
-- every 24h while it stays down, and a "recovered" email when it's back.
--
-- WHY THIS LIVES IN SUPABASE: the watchman must not live on the machine it
-- watches. The gateway (Fly) is the thing that dies; Supabase holds the
-- heartbeat anyway and runs scheduled jobs for free. No new accounts needed.
--
-- ONE-TIME STEP BEFORE RUNNING: store the Resend API key in Vault by running
-- this single line FIRST (paste your real key, then delete the line from the
-- editor so it isn't saved anywhere):
--
--     select vault.create_secret('re_YOUR_RESEND_KEY_HERE', 'resend_key');
--
-- (Same key you used for SMTP. If you prefer a fresh one: resend.com → API
--  Keys → Create. To rotate later: vault.update_secret / recreate.)
-- ============================================================

create extension if not exists pg_cron;
create extension if not exists pg_net;

-- Single-row state so we alert once per outage, not every 5 minutes.
create table if not exists public.gateway_alert_state (
  id int primary key default 1 check (id = 1),
  outage_open boolean not null default false,
  outage_started_at timestamptz,
  last_email_at timestamptz
);
insert into public.gateway_alert_state (id) values (1) on conflict do nothing;

-- Nobody outside the job needs this table.
alter table public.gateway_alert_state enable row level security;
revoke all on public.gateway_alert_state from anon, authenticated;

create or replace function public.check_gateway_and_alert()
returns text
language plpgsql
security definer
set search_path = public
as $$
declare
  hb timestamptz;
  st public.gateway_alert_state;
  et_now time;
  in_hours boolean;
  is_stale boolean;
  api_key text;
  msg text;
  subj text;
  did text := 'ok: nothing to do';
begin
  select last_ok_at into hb
    from public.gateway_health
    where feed = 'clinician_availability';
  select * into st from public.gateway_alert_state where id = 1;

  et_now  := (now() at time zone 'America/New_York')::time;
  -- 6:30 start gives the 6am wake-up half an hour of grace.
  in_hours := et_now between time '06:30' and time '20:00';
  is_stale := hb is null or hb < now() - interval '20 minutes';

  select decrypted_secret into api_key
    from vault.decrypted_secrets where name = 'resend_key' limit 1;
  if api_key is null then
    return 'ERROR: no vault secret named resend_key — run vault.create_secret first';
  end if;

  if in_hours and is_stale then
    if not st.outage_open then
      subj := '🔴 Matcher live times are DOWN';
      msg  := 'The availability gateway has not checked in since '
              || coalesce(to_char(hb at time zone 'America/New_York', 'Mon DD, HH12:MI am') || ' ET', 'ever')
              || '. The board is showing "Live times unavailable" to the front desk.'
              || E'\n\nTo restart it, run on the desktop:\n'
              || E'  C:\\Users\\hp\\.fly\\bin\\flyctl.exe auth login   (if asked)\n'
              || E'  cd "D:\\Clinican Modeliaitlities\\sp-gateway"\n'
              || E'  C:\\Users\\hp\\.fly\\bin\\flyctl.exe deploy --app mcw-sp-gateway\n'
              || E'\nYou will get a green "recovered" email when it is back.';
      update public.gateway_alert_state
        set outage_open = true, outage_started_at = now(), last_email_at = now()
        where id = 1;
      did := 'sent DOWN email';
    elsif st.last_email_at < now() - interval '24 hours' then
      subj := '🔴 Matcher live times are STILL down';
      msg  := 'Reminder: the availability gateway has been down since '
              || to_char(st.outage_started_at at time zone 'America/New_York', 'Mon DD, HH12:MI am')
              || ' ET. Restart it with fly deploy (see the first alert email).';
      update public.gateway_alert_state set last_email_at = now() where id = 1;
      did := 'sent 24h reminder';
    else
      return 'outage already alerted';
    end if;
  elsif (not is_stale) and st.outage_open then
    subj := '🟢 Matcher live times RECOVERED';
    msg  := 'The availability gateway is checking in again as of '
            || to_char(hb at time zone 'America/New_York', 'Mon DD, HH12:MI am')
            || ' ET. Live times are back on the board. (Outage began '
            || to_char(st.outage_started_at at time zone 'America/New_York', 'Mon DD, HH12:MI am')
            || ' ET.)';
    update public.gateway_alert_state
      set outage_open = false, outage_started_at = null, last_email_at = now()
      where id = 1;
    did := 'sent RECOVERED email';
  else
    return did;
  end if;

  perform net.http_post(
    url     := 'https://api.resend.com/emails',
    headers := jsonb_build_object(
      'Authorization', 'Bearer ' || api_key,
      'Content-Type',  'application/json'
    ),
    body    := jsonb_build_object(
      'from',    'Matcher Watchdog <noreply@send.mcnultycw.com>',
      'to',      jsonb_build_array('alam@mcnultycw.com', 'syedalamdar47@gmail.com'),
      'subject', subj,
      'text',    msg
    )
  );
  return did;
end;
$$;

-- Run every 5 minutes, forever, inside Supabase.
do $$
begin
  if exists (select 1 from cron.job where jobname = 'gateway-outage-watch') then
    perform cron.unschedule('gateway-outage-watch');
  end if;
end $$;
select cron.schedule('gateway-outage-watch', '*/5 * * * *',
                     $$select public.check_gateway_and_alert()$$);

-- Fire one check right now (with the gateway currently down, this should
-- send the DOWN email immediately — that's your proof it works):
select public.check_gateway_and_alert();
