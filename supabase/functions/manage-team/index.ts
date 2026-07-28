// ============================================================
// MCW Clinician Matcher — team management Edge Function
// Handles inviting and removing staff. Runs on Supabase's servers so it can
// hold the service-role key (which must NEVER be in the browser).
//
// Deploy (one time), either via the CLI:
//   supabase functions deploy manage-team --project-ref gazzhqtqnmpyjejwujei
// or by pasting this file into Dashboard → Edge Functions → New function
// named exactly "manage-team". The service role key is available to the
// function automatically as SUPABASE_SERVICE_ROLE_KEY — no secret to set.
// ============================================================
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SERVICE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const ANON_KEY = Deno.env.get("SUPABASE_ANON_KEY")!;

const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { ...cors, "Content-Type": "application/json" } });

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  try {
    // 1) Identify the caller from their JWT and look up their role.
    const authHeader = req.headers.get("Authorization") || "";
    const asCaller = createClient(SUPABASE_URL, ANON_KEY, { global: { headers: { Authorization: authHeader } } });
    const { data: userData, error: userErr } = await asCaller.auth.getUser();
    if (userErr || !userData?.user) return json({ error: "Not signed in." }, 401);
    const caller = userData.user;

    const admin = createClient(SUPABASE_URL, SERVICE_KEY);
    const { data: callerRoleRow } = await admin.from("user_roles").select("role").eq("user_id", caller.id).maybeSingle();
    const callerRole = callerRoleRow?.role;
    if (callerRole !== "owner" && callerRole !== "admin") return json({ error: "Only Admins and the Owner can manage the team." }, 403);
    const isOwner = callerRole === "owner";

    const body = await req.json();
    const action = body?.action;

    // 2) Invite a new staff member.
    if (action === "invite") {
      const email = String(body.email || "").trim().toLowerCase();
      let role = String(body.role || "frontdesk");
      if (!email) return json({ error: "Email is required." }, 400);
      // Admins may only invite frontdesk/viewer; owner may also invite admin. Nobody invites an owner.
      const allowed = isOwner ? ["admin", "frontdesk", "viewer"] : ["frontdesk", "viewer"];
      if (!allowed.includes(role)) role = "frontdesk";

      const site = Deno.env.get("SITE_URL") || "https://matcher.mcnultycounseling.com";
      const { data: invited, error: inviteErr } = await admin.auth.admin.inviteUserByEmail(email, { redirectTo: site });
      if (inviteErr || !invited?.user) return json({ error: inviteErr?.message || "Could not send the invite." }, 400);

      const { error: roleErr } = await admin.from("user_roles").upsert(
        { user_id: invited.user.id, email, role },
        { onConflict: "user_id" },
      );
      if (roleErr) return json({ error: "User invited but role not set: " + roleErr.message }, 400);
      return json({ ok: true, user_id: invited.user.id, role });
    }

    // 3) Remove a staff member.
    if (action === "remove") {
      const targetId = String(body.user_id || "");
      if (!targetId) return json({ error: "user_id is required." }, 400);
      if (targetId === caller.id) return json({ error: "You can't remove yourself." }, 400);
      const { data: targetRow } = await admin.from("user_roles").select("role").eq("user_id", targetId).maybeSingle();
      if (targetRow?.role === "owner") return json({ error: "The practice owner can't be removed." }, 403);
      if (targetRow?.role === "admin" && !isOwner) return json({ error: "Only the Owner can remove an Admin." }, 403);

      const { error: delErr } = await admin.auth.admin.deleteUser(targetId); // user_roles row cascades
      if (delErr) return json({ error: delErr.message }, 400);
      return json({ ok: true });
    }

    return json({ error: "Unknown action." }, 400);
  } catch (e) {
    return json({ error: (e as Error).message }, 500);
  }
});
