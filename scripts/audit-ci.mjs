// ============================================================
// MCW Clinician Matcher — CI / nightly auditor
// Runs the SAME rules as the in-app Health Check (audit.js) against:
//   1. SEED_DATA in the repo            (always)
//   2. The published Google Sheet CSV   (when SHEET_SYNC.csvUrl is set)
//   3. The LIVE Supabase roster         (when AUDITOR_EMAIL/AUDITOR_PASSWORD
//      env vars are set — add them as GitHub Actions secrets)
// Exits non-zero on any error-severity finding, which fails the workflow
// and triggers GitHub's failure-notification email to the repo owner.
// Zero dependencies — plain Node 20+.
// ============================================================

import { createRequire } from "module";
import { appendFileSync } from "fs";
const require = createRequire(import.meta.url);

const data = require("../data.js");
const audit = require("../audit.js");

const errors = [], warnings = [], infos = [];
const take = (issues, label) => issues.forEach(i => {
  const line = `[${label}] ${i.who}: ${i.message}`;
  if (i.severity === "error") errors.push(line);
  else if (i.severity === "warn") warnings.push(line);
  else infos.push(line);
});
const enumOpts = { priorityOrder: data.PRIORITY_ORDER, statusOrder: data.STATUS_ORDER };

// ---------- 1. Seed data (repo) ----------
take(audit.runAudit(data.SEED_DATA, enumOpts), "seed");

// ---------- 3. Live database (optional, before sheet so the sheet can be
// validated against the REAL roster rather than the seed) ----------
let roster = null;
const auditorEmail = process.env.AUDITOR_EMAIL;
const auditorPassword = process.env.AUDITOR_PASSWORD;
if (auditorEmail && auditorPassword && data.SUPABASE_URL) {
  try {
    const tokenResp = await fetch(`${data.SUPABASE_URL}/auth/v1/token?grant_type=password`, {
      method: "POST",
      headers: { apikey: data.SUPABASE_ANON_KEY, "Content-Type": "application/json" },
      body: JSON.stringify({ email: auditorEmail, password: auditorPassword }),
    });
    if (!tokenResp.ok) throw new Error(`auth failed: HTTP ${tokenResp.status}`);
    const { access_token } = await tokenResp.json();
    const rowsResp = await fetch(`${data.SUPABASE_URL}/rest/v1/clinicians?select=*`, {
      headers: { apikey: data.SUPABASE_ANON_KEY, Authorization: `Bearer ${access_token}` },
    });
    if (!rowsResp.ok) throw new Error(`roster fetch failed: HTTP ${rowsResp.status}`);
    roster = await rowsResp.json();
    if (!Array.isArray(roster) || roster.length === 0) {
      errors.push("[db] The live clinicians table returned no rows — the roster is empty or unreachable.");
      roster = null;
    } else {
      take(audit.runAudit(roster, enumOpts), "db");
    }
  } catch (e) {
    errors.push(`[db] Could not audit the live database: ${e.message}`);
  }
} else {
  infos.push("[db] AUDITOR_EMAIL/AUDITOR_PASSWORD not set — live-database checks skipped (add them as repo Actions secrets to enable).");
}

// ---------- 2. Published Google Sheet ----------
if (data.SHEET_SYNC && data.SHEET_SYNC.csvUrl) {
  try {
    const resp = await fetch(data.SHEET_SYNC.csvUrl, { redirect: "follow" });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const csv = await resp.text();
    const res = audit.auditSheet(csv, roster || data.SEED_DATA, data.SHEET_SYNC);
    res.errors.forEach(m => errors.push(`[sheet] ${m}`));
    res.warnings.forEach(m => warnings.push(`[sheet] ${m}`));
    res.info.forEach(m => infos.push(`[sheet] ${m}`));

    // Drift check: sheet value vs live DB value (normal between logins; a
    // warning here every night means nobody has synced in a while).
    if (roster) {
      const rows = audit.parseCsv(csv);
      const headers = rows[0].map(h => h.trim().toLowerCase());
      const idIdx = headers.indexOf(data.SHEET_SYNC.idColumn.toLowerCase());
      const prIdx = headers.indexOf(data.SHEET_SYNC.priorityColumn.toLowerCase());
      const acIdx = data.SHEET_SYNC.acceptingColumn ? headers.indexOf(data.SHEET_SYNC.acceptingColumn.toLowerCase()) : -1;
      for (let r = 1; r < rows.length; r++) {
        const id = (rows[r][idIdx] || "").trim();
        const c = roster.find(x => x.id === id);
        if (!c) continue;
        const pr = prIdx >= 0 ? audit.PRIORITY_ALIASES[(rows[r][prIdx] || "").trim().toLowerCase()] : null;
        const ac = acIdx >= 0 ? audit.ACCEPTING_ALIASES[(rows[r][acIdx] || "").trim().toLowerCase()] : null;
        if (pr && c.priority !== pr) warnings.push(`[drift] ${c.name}: sheet says priority "${pr}" but the app shows "${c.priority}" — sync hasn't run since the sheet changed.`);
        if (ac && c.accepting !== ac) warnings.push(`[drift] ${c.name}: sheet says "${ac}" but the app shows "${c.accepting}".`);
      }
    }
  } catch (e) {
    errors.push(`[sheet] Could not fetch/validate the published sheet: ${e.message} — priority sync is broken until this is fixed.`);
  }
}

// ---------- report ----------
const fmt = (title, list) => list.length ? `\n${title}\n${list.map(l => "  " + l).join("\n")}` : "";
console.log(`MCW audit: ${errors.length} error(s), ${warnings.length} warning(s), ${infos.length} info`);
console.log(fmt("ERRORS:", errors) + fmt("WARNINGS:", warnings) + fmt("INFO:", infos));

// GitHub Actions annotations + job summary
errors.forEach(m => console.log(`::error::${m}`));
warnings.forEach(m => console.log(`::warning::${m}`));
if (process.env.GITHUB_STEP_SUMMARY) {
  const md = [
    `## 🩺 MCW Matcher audit`,
    ``,
    `| Severity | Count |`,
    `|---|---|`,
    `| ❌ Errors | ${errors.length} |`,
    `| ⚠️ Warnings | ${warnings.length} |`,
    `| ℹ️ Info | ${infos.length} |`,
    ``,
    ...(errors.length ? ["### Errors", ...errors.map(m => `- ${m}`), ""] : []),
    ...(warnings.length ? ["### Warnings", ...warnings.map(m => `- ${m}`), ""] : []),
    ...(infos.length ? ["<details><summary>Info</summary>", "", ...infos.map(m => `- ${m}`), "", "</details>"] : []),
  ].join("\n");
  appendFileSync(process.env.GITHUB_STEP_SUMMARY, md + "\n");
}

process.exit(errors.length ? 1 : 0);
