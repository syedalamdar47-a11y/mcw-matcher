// ============================================================
// MCW Clinician Matcher — shared audit rules
// Loaded by BOTH the browser (classic <script>, between data.js and
// script.js) and Node CI (require via scripts/audit-ci.mjs). Keep it
// dependency-free and environment-agnostic: one source of truth for
// what "valid data" means, so the in-app Health Check, the push-time
// CI gate, and the nightly cloud audit can never disagree.
// ============================================================

const VALID_OFFICES = ["DTSP", "Tyrone", "Tampa", "Sarasota", "Virtual"];
const VALID_GROUPS = ["Individuals", "Couples", "Families", "Minors"];

const PRIORITY_ALIASES = {
  "high": "High Priority", "high priority": "High Priority", "h": "High Priority", "1": "High Priority",
  "medium": "Medium Priority", "medium priority": "Medium Priority", "med": "Medium Priority", "m": "Medium Priority", "2": "Medium Priority",
  "low": "Low Priority", "low priority": "Low Priority", "l": "Low Priority", "3": "Low Priority",
};
const ACCEPTING_ALIASES = {
  "accepting": "Accepting", "yes": "Accepting", "y": "Accepting", "open": "Accepting",
  "needs clients": "Needs Clients", "needs": "Needs Clients", "needs clients urgently": "Needs Clients",
  "not accepting": "Not Accepting", "no": "Not Accepting", "n": "Not Accepting", "closed": "Not Accepting", "full": "Not Accepting",
};

// Minimal RFC-4180 CSV parser: quoted fields, embedded commas/quotes, CRLF.
function parseCsv(text) {
  const rows = [];
  let row = [], field = "", inQuotes = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (inQuotes) {
      if (ch === '"') {
        if (text[i + 1] === '"') { field += '"'; i++; }
        else inQuotes = false;
      } else field += ch;
    } else if (ch === '"') {
      inQuotes = true;
    } else if (ch === ",") {
      row.push(field); field = "";
    } else if (ch === "\n" || ch === "\r") {
      if (ch === "\r" && text[i + 1] === "\n") i++;
      row.push(field); field = "";
      rows.push(row); row = [];
    } else {
      field += ch;
    }
  }
  if (field !== "" || row.length) { row.push(field); rows.push(row); }
  return rows.filter(r => r.some(c => c.trim() !== ""));
}

// Data + logic consistency checks over a clinician roster.
// Returns [{ severity: "error"|"warn"|"info", who, message }].
// opts.priorityOrder / opts.statusOrder override the browser globals (Node CI).
// opts.checkLocalStorage: browser-only orphaned-edits check (local mode).
function runAudit(clinicians, opts) {
  opts = opts || {};
  const PR = opts.priorityOrder || (typeof PRIORITY_ORDER !== "undefined" ? PRIORITY_ORDER : {});
  const ST = opts.statusOrder || (typeof STATUS_ORDER !== "undefined" ? STATUS_ORDER : {});
  const issues = [];
  const validPriority = Object.keys(PR);
  const validStatus = Object.keys(ST);
  const seen = {};
  (clinicians || []).forEach(c => {
    if (c.active === false) return; // deactivated clinicians are exempt from checks
    const who = c.profile || c.name || c.id || "(unknown)";
    if (seen[c.id]) issues.push({ severity: "error", who, message: `Duplicate id "${c.id}" — shared with ${seen[c.id]}. Their edits will collide.` });
    else seen[c.id] = who;

    ["name", "profile", "type", "schedule", "accepting", "priority"].forEach(f => {
      if (!c[f]) issues.push({ severity: "error", who, message: `Missing required field "${f}".` });
    });

    if (c.priority && !validPriority.includes(c.priority)) issues.push({ severity: "error", who, message: `Priority "${c.priority}" is not one of the allowed values — it will sort incorrectly.` });
    if (c.accepting && !validStatus.includes(c.accepting)) issues.push({ severity: "error", who, message: `Availability "${c.accepting}" is not an allowed value — it will sort incorrectly.` });
    if (c.type && c.type !== "therapy" && c.type !== "psychiatry") issues.push({ severity: "error", who, message: `Type "${c.type}" is not "therapy" or "psychiatry".` });
    (c.offices || []).forEach(o => { if (!VALID_OFFICES.includes(o)) issues.push({ severity: "warn", who, message: `Unknown office "${o}".` }); });

    if (!Array.isArray(c.groups) || c.groups.length === 0) issues.push({ severity: "warn", who, message: `No client groups listed — this clinician may be hidden by session-type filters.` });

    if (c.type === "therapy") {
      if (!c.specialties || c.specialties.length === 0) issues.push({ severity: "warn", who, message: `Therapist has no specialties listed.` });
      if (!c.modalities || c.modalities.length === 0) issues.push({ severity: "warn", who, message: `Therapist has no modalities listed.` });
    }

    const groups = c.groups || [];
    if (c.couples && !groups.includes("Couples")) issues.push({ severity: "warn", who, message: `Has a couples rate but "Couples" is not in their groups — the Couples filter will hide them.` });
    if (groups.includes("Couples") && !c.couples) issues.push({ severity: "info", who, message: `Lists the "Couples" group but has no couples rate.` });
    if (c.family && !groups.includes("Families")) issues.push({ severity: "warn", who, message: `Has a family rate but "Families" is not in their groups — the Family filter will hide them.` });
    if (groups.includes("Families") && !c.family) issues.push({ severity: "info", who, message: `Lists the "Families" group but has no family rate.` });
    if (c.type === "therapy" && (c.indiv || c.indivDisplay) && !groups.includes("Individuals")) issues.push({ severity: "info", who, message: `Has an individual rate but "Individuals" is not in their groups.` });
  });

  // Browser/local-mode only: saved edits whose id no longer matches any clinician.
  if (opts.checkLocalStorage && typeof localStorage !== "undefined" && typeof STORAGE_KEY !== "undefined") {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const saved = JSON.parse(raw);
        const ids = new Set((clinicians || []).map(c => c.id));
        Object.keys(saved).forEach(k => {
          if (!ids.has(k)) issues.push({ severity: "warn", who: "(saved data)", message: `Stored edits for "${k}" don't match any current clinician — orphaned and invisible.` });
        });
      }
    } catch {}
  }

  return issues;
}

// Validates a published-sheet CSV against a clinician roster (same rules the
// in-app sync applies). Returns { errors, warnings, info } message arrays.
function auditSheet(csvText, clinicians, sheetConfig) {
  const errors = [], warnings = [], info = [];
  const rows = parseCsv(csvText);
  if (rows.length < 2) { errors.push("The published sheet is empty (no data rows)."); return { errors, warnings, info }; }
  const headers = rows[0].map(h => h.trim().toLowerCase());
  const idIdx = headers.indexOf(sheetConfig.idColumn.toLowerCase());
  const prIdx = headers.indexOf(sheetConfig.priorityColumn.toLowerCase());
  const acIdx = sheetConfig.acceptingColumn ? headers.indexOf(sheetConfig.acceptingColumn.toLowerCase()) : -1;
  if (idIdx < 0) { errors.push(`Sheet is missing the "${sheetConfig.idColumn}" column.`); return { errors, warnings, info }; }
  if (prIdx < 0) errors.push(`Sheet is missing the "${sheetConfig.priorityColumn}" column.`);

  const rosterIds = new Set((clinicians || []).map(c => c.id));
  const seen = new Set();
  for (let r = 1; r < rows.length; r++) {
    const rawId = (rows[r][idIdx] || "").trim();
    if (!rawId) continue;
    if (seen.has(rawId)) errors.push(`Row ${r + 1}: duplicate id "${rawId}" in the sheet — the later row silently wins.`);
    seen.add(rawId);
    if (rosterIds.size && !rosterIds.has(rawId)) warnings.push(`Row ${r + 1}: id "${rawId}" doesn't match any clinician.`);
    if (prIdx >= 0) {
      const rawPr = (rows[r][prIdx] || "").trim();
      if (rawPr && !PRIORITY_ALIASES[rawPr.toLowerCase()]) errors.push(`Row ${r + 1} (${rawId}): priority "${rawPr}" not recognized.`);
    }
    if (acIdx >= 0) {
      const rawAc = (rows[r][acIdx] || "").trim();
      if (rawAc && !ACCEPTING_ALIASES[rawAc.toLowerCase()]) errors.push(`Row ${r + 1} (${rawId}): availability "${rawAc}" not recognized.`);
    }
  }
  (clinicians || []).forEach(c => {
    if (c.active !== false && !seen.has(c.id)) info.push(`${c.name} is in the app but not in the sheet (sync leaves them unchanged).`);
  });
  return { errors, warnings, info };
}

if (typeof module !== "undefined") {
  module.exports = { VALID_OFFICES, VALID_GROUPS, PRIORITY_ALIASES, ACCEPTING_ALIASES, parseCsv, runAudit, auditSheet };
}
