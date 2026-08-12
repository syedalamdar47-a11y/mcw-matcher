-- ============================================================
-- MCW Clinician Matcher — security patch (one-time)
-- Paste into the Supabase SQL Editor and click Run. Safe to re-run.
--
-- WHY: the review-queue view public.pending_change_review was created with the
-- default "security definer" behaviour, which runs as the view's OWNER and so
-- BYPASSES the row-level security on the underlying table. PostgREST also grants
-- the anonymous (public) key read access to views by default. Together that meant
-- the pending-changes queue (clinician name, profile, proposed specialties /
-- modalities and the free-text note) was readable WITHOUT logging in.
--
-- FIX: make the view respect the caller's own permissions (security_invoker),
-- so it enforces the same RLS as the base table — only owner/admin/frontdesk/
-- viewer logins, or the clinician who owns the row, can read it. Then revoke the
-- anonymous grant as belt-and-braces.
-- ============================================================

-- 1) Run the view with the caller's privileges + RLS (Postgres 15+, i.e. Supabase).
alter view public.pending_change_review set (security_invoker = on);

-- 2) No anonymous access to the queue. Authenticated staff keep it via RLS.
revoke all on public.pending_change_review from anon;
grant select on public.pending_change_review to authenticated;

-- 3) Same posture for the base table, in case anon was granted on it directly.
revoke all on public.clinician_change_requests from anon;
