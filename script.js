// ============================================================
// MCW Client Matcher — vanilla JS app
// ============================================================

// Supabase client — null when data.js has no SUPABASE_URL, in which case the
// app runs in legacy local mode (per-browser localStorage + shared password).
const sb = (typeof SUPABASE_URL !== "undefined" && SUPABASE_URL && typeof supabase !== "undefined")
  ? supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY)
  : null;

const state = {
  authed: sessionStorage.getItem("mcw_auth") === "1",
  loginPw: "",
  loginEmail: "",
  loginBusy: false,
  loginError: false,
  loadError: "",
  clinicians: [],
  loading: true,
  search: "",
  offices: [],
  sessionTypes: [],
  selectedSpecs: [],
  selectedMods: [],
  typeFilter: "therapy",
  sortBy: "priority",
  specSearch: "",
  modSearch: "",
  adminOpen: false,
  adminEdits: null,
  adminOriginal: null,
  editingCardId: null,
  cardEdit: null,
  specsModalId: null,
  modsModalId: null,
  modalSpecs: null,
  modalNewSpec: "",
  modalMods: null,
  modalNewMod: "",
  expandedSpecs: new Set(),
  healthOpen: false,
  healthResults: null,
  editorId: null,      // clinician id being edited, or "__new__"
  editorDraft: null,   // buffered field values for the editor form
  editorErrors: null,  // validation / save errors shown in the editor
  editorBusy: false,
};

const SPEC_LIMIT = 5;

// ---------- helpers ----------
function escapeHtml(s) {
  if (s == null) return "";
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

async function loadClinicians() {
  if (sb) {
    state.loadError = "";
    try {
      const { data, error } = await sb.from("clinicians").select("*").order("name");
      if (error) throw error;
      state.clinicians = (data || []).map(r => ({ ...r }));
    } catch (e) {
      state.loadError = (e && e.message) || "Could not reach the database.";
      state.clinicians = [];
    }
    state.loading = false;
    return;
  }
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const saved = JSON.parse(raw);
      state.clinicians = SEED_DATA.map(c => ({ ...c, ...(saved[c.id] || {}) }));
    } else {
      state.clinicians = SEED_DATA.map(c => ({ ...c }));
    }
  } catch {
    state.clinicians = SEED_DATA.map(c => ({ ...c }));
  }
  state.loading = false;
}

// Saves the editable fields. In shared mode, writes ONLY the changed rows to the
// database (pass the changed id(s)); writing unchanged rows would clobber a
// colleague's concurrent edits with stale values.
function persist(changedIds) {
  if (sb) {
    const ids = changedIds || state.clinicians.map(c => c.id);
    const rows = state.clinicians.filter(c => ids.includes(c.id));
    Promise.all(rows.map(c =>
      sb.from("clinicians").update({
        accepting: c.accepting,
        priority: c.priority,
        notes: c.notes,
        specialties: c.specialties,
        modalities: c.modalities,
      }).eq("id", c.id).select("id")
    )).then(results => {
      // .select("id") makes a remotely-deleted row detectable (0 rows updated)
      const failures = results.filter(r => !r || r.error || !r.data || r.data.length === 0);
      if (failures.length) {
        const withMsg = failures.find(r => r && r.error);
        alert(
          failures.length + " change(s) could NOT be saved to the shared database" +
          (withMsg ? " (" + withMsg.error.message + ")" : " (the clinician may have been removed)") +
          ". Reloading the latest data."
        );
        loadClinicians().then(() => render());
      }
    }).catch(() => {
      alert("Could not reach the database — your change was NOT saved. Reloading the latest data.");
      loadClinicians().then(() => render());
    });
    return;
  }
  try {
    const map = {};
    state.clinicians.forEach(c => {
      map[c.id] = {
        accepting: c.accepting,
        priority: c.priority,
        notes: c.notes,
        specialties: c.specialties,
        modalities: c.modalities,
      };
    });
    localStorage.setItem(STORAGE_KEY, JSON.stringify(map));
  } catch {}
}

// Live sync: when a colleague edits a clinician, update this screen too.
let realtimeChannel = null;
let realtimeDropped = false;
function subscribeRealtime() {
  if (!sb || realtimeChannel) return;
  realtimeChannel = sb
    .channel("clinicians-live")
    .on("postgres_changes", { event: "*", schema: "public", table: "clinicians" }, (payload) => {
      if (payload.eventType === "DELETE") {
        const oldId = payload.old && payload.old.id;
        if (oldId) state.clinicians = state.clinicians.filter(c => c.id !== oldId);
      } else if (payload.new && payload.new.id) {
        const i = state.clinicians.findIndex(c => c.id === payload.new.id);
        if (i >= 0) state.clinicians[i] = { ...state.clinicians[i], ...payload.new };
        else state.clinicians.push({ ...payload.new });
      }
      render();
    })
    .subscribe((status) => {
      // Events missed while the socket was down are not replayed —
      // refetch the roster whenever the channel comes back.
      if (status === "SUBSCRIBED" && realtimeDropped) {
        realtimeDropped = false;
        loadClinicians().then(() => render());
      } else if (status === "CHANNEL_ERROR" || status === "TIMED_OUT" || status === "CLOSED") {
        realtimeDropped = true;
      }
    });
}

function uniqueSorted(arr) {
  return [...new Set(arr)].filter(Boolean).sort();
}

// ---------- clinician editor (add / edit details / deactivate / delete) ----------
// Requires shared mode: the database is the source of truth for the roster.
const VALID_GROUPS = ["Individuals", "Couples", "Families", "Minors"];

// Stable, unique, immutable id from a name: "Jane O'Brien" -> "jane_o_brien"
// (suffixesed if taken). Ids never change after creation — the Google-Sheet
// sync (goal 3) and saved edits both key on them.
function generateId(name) {
  const base = String(name).toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "") || "clinician";
  const taken = new Set(state.clinicians.map(c => c.id));
  if (!taken.has(base)) return base;
  let n = 2;
  while (taken.has(base + "_" + n)) n++;
  return base + "_" + n;
}

function draftFromClinician(c) {
  return {
    name: c.name || "",
    profile: c.profile || "",
    type: c.type || "therapy",
    offices: (c.offices || []).slice(),
    virtual: !!c.virtual,
    indiv: c.indiv == null ? "" : String(c.indiv),
    indivDisplay: c.indivDisplay || "",
    couples: c.couples == null ? "" : String(c.couples),
    family: c.family == null ? "" : String(c.family),
    schedule: c.schedule || "",
    groups: (c.groups || []).slice(),
  };
}

function blankDraft() {
  return { name: "", profile: "", type: "therapy", offices: [], virtual: false, indiv: "", indivDisplay: "", couples: "", family: "", schedule: "", groups: [] };
}

// Parses a rate input: "" -> null, otherwise must be a positive number.
function parseRate(v) {
  const s = String(v).trim().replace(/^\$/, "");
  if (!s) return { ok: true, value: null };
  const n = Number(s);
  if (!isFinite(n) || n <= 0) return { ok: false };
  return { ok: true, value: n };
}

function validateDraft(d) {
  const errors = [];
  if (!d.name.trim()) errors.push("Name is required.");
  if (!d.profile.trim()) errors.push("Profile is required (e.g. \"Jane Doe, LMHC\").");
  if (!d.schedule.trim()) errors.push("Schedule is required (e.g. \"Mon-Fri\").");
  if (d.type !== "therapy" && d.type !== "psychiatry") errors.push("Type must be therapy or psychiatry.");
  if (!d.offices.length) errors.push("Pick at least one office (Virtual counts).");
  if (!d.groups.length) errors.push("Pick at least one session group — clinicians with no groups are hidden by the session-type filters.");
  if (!parseRate(d.indiv).ok) errors.push("Individual rate must be a number (or leave it blank and use the rate text instead).");
  if (!parseRate(d.couples).ok) errors.push("Couples rate must be a number or blank.");
  if (!parseRate(d.family).ok) errors.push("Family rate must be a number or blank.");
  return errors;
}

// The editor owns ONLY the identity/detail fields. Status, priority, notes,
// specialties, and modalities keep their own editors so concurrent edits by
// different staff don't overwrite each other.
function draftToFields(d) {
  return {
    name: d.name.trim(),
    profile: d.profile.trim(),
    type: d.type,
    offices: d.offices,
    virtual: d.virtual,
    indiv: parseRate(d.indiv).value,
    indivDisplay: d.indivDisplay.trim() || null,
    couples: parseRate(d.couples).value,
    family: parseRate(d.family).value,
    schedule: d.schedule.trim(),
    groups: d.groups,
  };
}

function closeEditor() {
  state.editorId = null;
  state.editorDraft = null;
  state.editorErrors = null;
  state.editorBusy = false;
}

// ---------- automated auditor ----------
// Pure function: runs data + logic consistency checks over the current roster.
// Returns [{ severity: "error"|"warn"|"info", who, message }]. Shared by the
// in-app Health Check panel now; the same rules can later feed a CI/cron runner.
const VALID_OFFICES = ["DTSP", "Tyrone", "Tampa", "Sarasota", "Virtual"];
function runAudit(clinicians) {
  const issues = [];
  const validPriority = Object.keys(PRIORITY_ORDER);
  const validStatus = Object.keys(STATUS_ORDER);
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

  // Runtime-only check (local mode): saved edits whose id no longer matches any clinician.
  if (sb) return issues;
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

  return issues;
}

// ---------- backup / restore ----------
// Exports the same field set persist() writes, so import round-trips exactly.
function exportBackup() {
  const map = {};
  state.clinicians.forEach(c => {
    map[c.id] = { accepting: c.accepting, priority: c.priority, notes: c.notes, specialties: c.specialties, modalities: c.modalities };
  });
  const blob = new Blob([JSON.stringify(map, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const d = new Date();
  const stamp = `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, "0")}${String(d.getDate()).padStart(2, "0")}`;
  const a = document.createElement("a");
  a.href = url;
  a.download = `mcw-matcher-backup-${stamp}.json`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function importBackup() {
  if (sb) {
    alert("Restore from file isn't needed anymore — clinician data now lives in the shared database, so every browser sees the same live data.");
    return;
  }
  const input = document.createElement("input");
  input.type = "file";
  input.accept = "application/json,.json";
  input.onchange = () => {
    const file = input.files && input.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const parsed = JSON.parse(reader.result);
        if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("bad shape");
        localStorage.setItem(STORAGE_KEY, JSON.stringify(parsed));
        loadClinicians();
        render();
        alert("Backup imported — clinician edits have been restored on this browser.");
      } catch {
        alert("Could not import that file. It doesn't look like a valid MCW backup (expected a .json file exported from this app).");
      }
    };
    reader.readAsText(file);
  };
  input.click();
}

function getFiltered() {
  // active === false means deactivated (soft-deleted); reactivate from the admin panel
  let res = state.clinicians.filter(c => c.type === state.typeFilter && c.active !== false);
  if (state.search.trim()) {
    const q = state.search.toLowerCase();
    res = res.filter(c => (c.name || "").toLowerCase().includes(q) || (c.profile || "").toLowerCase().includes(q));
  }
  if (state.offices.length) {
    res = res.filter(c => state.offices.some(o => c.offices.includes(o)));
  }
  if (state.sessionTypes.length) {
    // Map the sidebar labels to the plural group names used in the data,
    // and filter on `groups` as the single source of truth (not rate presence).
    const GROUP_FOR = { Individual: "Individuals", Couples: "Couples", Family: "Families", Minors: "Minors" };
    res = res.filter(c => state.sessionTypes.every(st => (c.groups || []).includes(GROUP_FOR[st] || st)));
  }
  if (state.selectedSpecs.length) {
    res = res.filter(c => state.selectedSpecs.some(s => c.specialties.includes(s)));
  }
  if (state.selectedMods.length) {
    res = res.filter(c => state.selectedMods.some(m => c.modalities.includes(m)));
  }
  res.sort((a, b) => {
    if (state.sortBy === "priority") {
      const pd = (PRIORITY_ORDER[a.priority] ?? 1) - (PRIORITY_ORDER[b.priority] ?? 1);
      if (pd !== 0) return pd;
      const sd = (STATUS_ORDER[a.accepting] ?? 1) - (STATUS_ORDER[b.accepting] ?? 1);
      if (sd !== 0) return sd;
      return a.name.localeCompare(b.name);
    }
    if (state.sortBy === "name") return a.name.localeCompare(b.name);
    if (state.sortBy === "office") return (a.offices[0] || "").localeCompare(b.offices[0] || "");
    return 0;
  });
  return res;
}

function priorityClass(p) {
  if (p === "High Priority") return "high";
  if (p === "Medium Priority") return "medium";
  return "low";
}
function badgeStatusClass(s) {
  if (s === "Accepting") return "badge-Accepting";
  if (s === "Needs Clients") return "badge-NeedsClients";
  return "badge-NotAccepting";
}
function badgePriorityClass(p) {
  if (p === "High Priority") return "badge-High";
  if (p === "Medium Priority") return "badge-Medium";
  return "badge-Low";
}
function officeClass(o) {
  if (o === "DTSP" || o === "Tyrone" || o === "Tampa" || o === "Sarasota" || o === "Virtual") return "office-" + o;
  return "office-other";
}

// ---------- render: login ----------
function renderLogin() {
  return `
    <div class="login-wrap">
      <div class="login-card">
        <div class="login-header">
          <img src="logo.png" alt="McNulty Counseling and Wellness" class="login-logo" />
          <p class="login-title">Clinician Matcher</p>
          <p class="login-sub">Front office scheduling</p>
        </div>
        <form data-action="login-submit">
          ${sb ? `
          <label class="login-label" for="login-email">Email</label>
          <input
            id="login-email"
            type="email"
            class="login-input ${state.loginError ? "error" : ""}"
            placeholder="you@mcnultycounseling.com"
            value="${escapeHtml(state.loginEmail)}"
            data-action="login-email-input"
            autocomplete="username"
            autofocus
          />
          ` : ""}
          <label class="login-label" for="login-pw">Password</label>
          <input
            id="login-pw"
            type="password"
            class="login-input ${state.loginError ? "error" : ""}"
            placeholder="Enter password…"
            value="${escapeHtml(state.loginPw)}"
            data-action="login-input"
            ${sb ? `autocomplete="current-password"` : "autofocus"}
          />
          ${state.loginError ? `<p class="login-error">${sb ? "Sign-in failed. Check your email and password." : "Incorrect password. Please try again."}</p>` : ""}
          <button type="submit" class="login-btn" ${state.loginBusy ? "disabled" : ""}>${state.loginBusy ? "Signing in…" : "Sign in"}</button>
        </form>
      </div>
    </div>
  `;
}

// ---------- render: sidebar ----------
function renderSidebar() {
  const allSpecs = uniqueSorted(state.clinicians.flatMap(c => c.specialties));
  const allMods = uniqueSorted(state.clinicians.flatMap(c => c.modalities));
  const filteredSpecs = allSpecs.filter(s => s.toLowerCase().includes(state.specSearch.toLowerCase()));
  const filteredMods = allMods.filter(m => m.toLowerCase().includes(state.modSearch.toLowerCase()));
  const hasFilters = state.offices.length || state.sessionTypes.length || state.selectedSpecs.length || state.selectedMods.length || state.search;

  return `
    <div class="sidebar">
      <div class="sidebar-head">
        <img src="logo.png" alt="McNulty Counseling and Wellness" class="sidebar-logo" />
        <p class="sidebar-sub">Clinician Matcher</p>
      </div>
      <div class="sidebar-body">
        <input id="search-input" class="side-input" type="text" placeholder="Search by name…" value="${escapeHtml(state.search)}" data-action="search-input" />

        <div>
          <p class="side-label">Provider type</p>
          <div class="type-toggle">
            <button data-action="type-set" data-type="therapy" class="${state.typeFilter === "therapy" ? "active" : ""}">therapy</button>
            <button data-action="type-set" data-type="psychiatry" class="${state.typeFilter === "psychiatry" ? "active" : ""}">psychiatry</button>
          </div>
        </div>

        <div>
          <p class="side-label">Office</p>
          <div class="side-checklist">
            ${["DTSP","Tyrone","Tampa","Sarasota"].map(o => `
              <label class="check-row">
                <input type="checkbox" data-action="office-toggle" data-office="${o}" ${state.offices.includes(o) ? "checked" : ""} />
                <span>${o}</span>
              </label>
            `).join("")}
          </div>
        </div>

        <div>
          <p class="side-label">Session type</p>
          <div class="side-checklist">
            ${["Individual","Couples","Family","Minors"].map(st => `
              <label class="check-row">
                <input type="checkbox" data-action="session-toggle" data-session="${st}" ${state.sessionTypes.includes(st) ? "checked" : ""} />
                <span>${st}</span>
              </label>
            `).join("")}
          </div>
        </div>

        ${state.typeFilter === "therapy" ? `
          <div>
            <p class="side-label">Specialty</p>
            <input id="spec-search-input" class="side-input sm" type="text" placeholder="Search…" value="${escapeHtml(state.specSearch)}" data-action="spec-search-input" />
            <div class="side-checklist scrolly">
              ${filteredSpecs.map(s => `
                <label class="check-row">
                  <input type="checkbox" data-action="spec-toggle" data-spec="${escapeHtml(s)}" ${state.selectedSpecs.includes(s) ? "checked" : ""} />
                  <span>${escapeHtml(s)}</span>
                </label>
              `).join("")}
            </div>
            ${state.selectedSpecs.length > 0 ? `<button class="clear-link" data-action="specs-clear">Clear</button>` : ""}
          </div>

          <div>
            <p class="side-label">Modality</p>
            <input id="mod-search-input" class="side-input sm" type="text" placeholder="Search…" value="${escapeHtml(state.modSearch)}" data-action="mod-search-input" />
            <div class="side-checklist scrolly">
              ${filteredMods.map(m => `
                <label class="check-row">
                  <input type="checkbox" data-action="mod-toggle" data-mod="${escapeHtml(m)}" ${state.selectedMods.includes(m) ? "checked" : ""} />
                  <span>${escapeHtml(m)}</span>
                </label>
              `).join("")}
            </div>
            ${state.selectedMods.length > 0 ? `<button class="clear-link" data-action="mods-clear">Clear</button>` : ""}
          </div>
        ` : ""}

        ${hasFilters ? `<button class="clear-all-btn" data-action="clear-all">Clear all filters</button>` : ""}
      </div>
      <div class="sidebar-foot">
        ${sb ? `<button class="admin-btn add-btn" data-action="editor-open" data-id="__new__">+ Add clinician</button>` : ""}
        <button class="admin-btn" data-action="admin-open">⚙ Update all clinicians</button>
        <div class="foot-utils">
          <button data-action="health-open" title="Run automated data checks">🩺 Health</button>
          <button data-action="export-backup" title="Download a backup of all edits">⬇ Backup</button>
          <button data-action="import-backup" title="Restore edits from a backup file">⬆ Restore</button>
        </div>
        <button class="signout-btn" data-action="signout">Sign out</button>
      </div>
    </div>
  `;
}

// ---------- render: card ----------
function renderCard(c) {
  const rates = [];
  if (c.indivDisplay) rates.push(c.indivDisplay);
  else if (c.indiv) rates.push(`Indiv: $${c.indiv}`);
  if (c.couples) rates.push(`Couples: $${c.couples}`);
  if (c.family) rates.push(`Family: $${c.family}`);

  const expanded = state.expandedSpecs.has(c.id);
  const hidden = c.specialties.length - SPEC_LIMIT;
  const visible = expanded ? c.specialties : c.specialties.slice(0, SPEC_LIMIT);
  const isEditing = state.editingCardId === c.id;
  const ed = isEditing ? state.cardEdit : null;

  return `
    <div class="card">
      <div class="card-bar ${priorityClass(c.priority)}"></div>
      <div class="card-body">
        <div class="card-head">
          <div class="card-name-wrap">
            <p class="card-name">${escapeHtml(c.profile)}</p>
            <div class="office-row">
              ${c.offices.map(o => `<span class="office-tag ${officeClass(o)}">${escapeHtml(o)}</span>`).join("")}
              ${c.virtual ? `<span class="office-tag tag-virtual">Virtual</span>` : ""}
              ${c.type === "psychiatry" ? `<span class="office-tag tag-psych">Psychiatry</span>` : ""}
            </div>
          </div>
          <div class="badges">
            <span class="badge ${badgeStatusClass(c.accepting)}">${escapeHtml(c.accepting)}</span>
            <span class="badge ${badgePriorityClass(c.priority)}">${escapeHtml(c.priority)}</span>
          </div>
        </div>

        <div class="meta-list">
          <div class="meta-row"><span class="icon">📅</span><span>${escapeHtml(c.schedule)}</span></div>
          ${rates.length ? `<div class="meta-row"><span class="icon">💲</span><span>${escapeHtml(rates.join(" · "))}</span></div>` : ""}
          ${c.groups.length ? `<div class="meta-row"><span class="icon">👥</span><span>${escapeHtml(c.groups.join(", "))}</span></div>` : ""}
        </div>

        <div class="section">
          <div class="section-head">
            <span class="section-title">Modalities</span>
            <button class="section-edit" data-action="mods-modal-open" data-id="${escapeHtml(c.id)}">edit</button>
          </div>
          ${c.modalities.length
            ? `<p class="modalities-text">${escapeHtml(c.modalities.join(" · "))}</p>`
            : `<button class="section-edit" data-action="mods-modal-open" data-id="${escapeHtml(c.id)}">+ Add modalities</button>`
          }
        </div>

        ${c.type === "therapy" ? `
          <div class="section">
            <div class="section-head">
              <span class="section-title">Specialties</span>
              <button class="section-edit" data-action="specs-modal-open" data-id="${escapeHtml(c.id)}">edit</button>
            </div>
            <div class="spec-tags">
              ${visible.map(s => `<span class="spec-tag">${escapeHtml(s)}</span>`).join("")}
              ${!expanded && hidden > 0 ? `<button class="more-btn" data-action="specs-expand" data-id="${escapeHtml(c.id)}">+${hidden} more</button>` : ""}
              ${expanded && hidden > 0 ? `<button class="less-btn" data-action="specs-collapse" data-id="${escapeHtml(c.id)}">show less</button>` : ""}
            </div>
          </div>
        ` : ""}

        ${c.notes ? `<div class="note-box"><p><strong>Note: </strong>${escapeHtml(c.notes)}</p></div>` : ""}
      </div>

      ${isEditing ? `
        <div class="card-edit">
          <div class="edit-grid">
            <div>
              <label>Availability</label>
              <select data-action="card-edit-accepting">
                <option ${ed.accepting === "Accepting" ? "selected" : ""}>Accepting</option>
                <option ${ed.accepting === "Needs Clients" ? "selected" : ""}>Needs Clients</option>
                <option ${ed.accepting === "Not Accepting" ? "selected" : ""}>Not Accepting</option>
              </select>
            </div>
            <div>
              <label>Priority</label>
              <select data-action="card-edit-priority">
                <option ${ed.priority === "High Priority" ? "selected" : ""}>High Priority</option>
                <option ${ed.priority === "Medium Priority" ? "selected" : ""}>Medium Priority</option>
                <option ${ed.priority === "Low Priority" ? "selected" : ""}>Low Priority</option>
              </select>
            </div>
          </div>
          <div class="edit-input-wrap">
            <label>Admin note</label>
            <input id="card-edit-notes-${escapeHtml(c.id)}" class="edit-input" type="text" value="${escapeHtml(ed.notes || "")}" data-action="card-edit-notes" />
          </div>
          <div class="edit-actions">
            <button class="btn-save" data-action="card-edit-save" data-id="${escapeHtml(c.id)}">Save</button>
            <button class="btn-cancel" data-action="card-edit-cancel">Cancel</button>
          </div>
        </div>
      ` : `
        <div class="card-foot">
          <button data-action="card-edit-start" data-id="${escapeHtml(c.id)}">Edit status &amp; priority</button>
          ${sb ? `<button data-action="editor-open" data-id="${escapeHtml(c.id)}">Edit details</button>` : ""}
        </div>
      `}
    </div>
  `;
}

// ---------- render: main pane ----------
function renderMainPane() {
  const filtered = getFiltered();
  return `
    <div class="main-pane">
      <div class="main-bar">
        <div class="main-bar-left">
          <span class="count-text"><strong>${filtered.length}</strong> clinician${filtered.length !== 1 ? "s" : ""}</span>
          ${state.selectedSpecs.map(sp => `
            <span class="chip chip-spec">${escapeHtml(sp)}<button data-action="spec-toggle" data-spec="${escapeHtml(sp)}">×</button></span>
          `).join("")}
          ${state.selectedMods.map(m => `
            <span class="chip chip-mod">${escapeHtml(m)}<button data-action="mod-toggle" data-mod="${escapeHtml(m)}">×</button></span>
          `).join("")}
        </div>
        <div class="sort-wrap">
          <label>Sort:</label>
          <select data-action="sort-change">
            <option value="priority" ${state.sortBy === "priority" ? "selected" : ""}>Priority + Availability</option>
            <option value="name" ${state.sortBy === "name" ? "selected" : ""}>Name A–Z</option>
            <option value="office" ${state.sortBy === "office" ? "selected" : ""}>Office</option>
          </select>
        </div>
      </div>
      <div class="cards-area">
        ${filtered.length === 0 ? `
          <div class="empty-state">
            <p>No clinicians match</p>
            <button data-action="clear-all">Clear filters</button>
          </div>
        ` : `
          <div class="cards-grid">
            ${filtered.map(renderCard).join("")}
          </div>
        `}
      </div>
    </div>
  `;
}

// ---------- render: modals ----------
function renderSpecsModal() {
  if (!state.specsModalId) return "";
  const c = state.clinicians.find(x => x.id === state.specsModalId);
  if (!c) return "";
  const all = uniqueSorted(state.clinicians.flatMap(x => x.specialties));
  const merged = uniqueSorted([...all, ...state.modalSpecs]);
  return `
    <div class="modal-overlay">
      <div class="modal">
        <div class="modal-head">
          <span class="title">Specialties — ${escapeHtml(c.name)}</span>
          <button class="modal-close" data-action="specs-modal-close">&times;</button>
        </div>
        <div class="modal-body">
          <p style="font-size:12px;color:#64748b;margin:0 0 12px;">Check to include, uncheck to remove. Add new specialties below.</p>
          <div class="spec-grid">
            ${merged.map(s => `
              <label class="spec-check-row">
                <input type="checkbox" data-action="modal-spec-toggle" data-spec="${escapeHtml(s)}" ${state.modalSpecs.includes(s) ? "checked" : ""} />
                ${escapeHtml(s)}
              </label>
            `).join("")}
          </div>
          <div class="modal-section">
            <p class="label">Add a specialty not listed above</p>
            <div class="modal-add-row">
              <input id="modal-spec-input" type="text" placeholder="Type and press Enter…" value="${escapeHtml(state.modalNewSpec)}" data-action="modal-spec-newinput" />
              <button data-action="modal-spec-add">Add</button>
            </div>
          </div>
          <div class="modal-actions">
            <button class="btn-save" data-action="modal-spec-save">Save specialties</button>
            <button class="btn-cancel" data-action="specs-modal-close">Cancel</button>
          </div>
        </div>
      </div>
    </div>
  `;
}

function renderModsModal() {
  if (!state.modsModalId) return "";
  const c = state.clinicians.find(x => x.id === state.modsModalId);
  if (!c) return "";
  return `
    <div class="modal-overlay">
      <div class="modal">
        <div class="modal-head">
          <span class="title">Modalities — ${escapeHtml(c.name)}</span>
          <button class="modal-close" data-action="mods-modal-close">&times;</button>
        </div>
        <div class="modal-body">
          <div class="mod-list">
            ${state.modalMods.map(m => `
              <div class="mod-list-row">
                <span>${escapeHtml(m)}</span>
                <button data-action="modal-mod-remove" data-mod="${escapeHtml(m)}">✕</button>
              </div>
            `).join("")}
            ${state.modalMods.length === 0 ? `<p class="mod-empty">No modalities listed</p>` : ""}
          </div>
          <div class="modal-section">
            <p class="label">Add a modality</p>
            <div class="modal-add-row">
              <input id="modal-mod-input" type="text" placeholder="e.g. EMDR, DBT, Somatic…" value="${escapeHtml(state.modalNewMod)}" data-action="modal-mod-newinput" />
              <button data-action="modal-mod-add">Add</button>
            </div>
          </div>
          <div class="modal-actions">
            <button class="btn-save" data-action="modal-mod-save">Save modalities</button>
            <button class="btn-cancel" data-action="mods-modal-close">Cancel</button>
          </div>
        </div>
      </div>
    </div>
  `;
}

function renderAdminModal() {
  if (!state.adminOpen) return "";
  const therapy = state.clinicians.filter(c => c.type === "therapy" && c.active !== false);
  const psych = state.clinicians.filter(c => c.type === "psychiatry" && c.active !== false);
  const inactive = state.clinicians.filter(c => c.active === false);
  const row = (c) => {
    // A clinician can arrive via realtime while the modal is open — seed a
    // buffer lazily so render doesn't crash and edits to them still work.
    if (!state.adminEdits[c.id]) {
      state.adminEdits[c.id] = { accepting: c.accepting, priority: c.priority, notes: c.notes };
      if (state.adminOriginal) state.adminOriginal[c.id] = { accepting: c.accepting, priority: c.priority, notes: c.notes };
    }
    const ed = state.adminEdits[c.id];
    return `
      <div class="admin-row">
        <div class="admin-row-head">
          <p class="admin-row-name">${escapeHtml(c.profile)}</p>
          ${c.offices.map(o => `<span class="office-tag ${officeClass(o)}">${escapeHtml(o)}</span>`).join("")}
        </div>
        <div class="edit-grid">
          <div>
            <label>Availability</label>
            <select data-action="admin-accepting" data-id="${escapeHtml(c.id)}">
              <option ${ed.accepting === "Accepting" ? "selected" : ""}>Accepting</option>
              <option ${ed.accepting === "Needs Clients" ? "selected" : ""}>Needs Clients</option>
              <option ${ed.accepting === "Not Accepting" ? "selected" : ""}>Not Accepting</option>
            </select>
          </div>
          <div>
            <label>Priority</label>
            <select data-action="admin-priority" data-id="${escapeHtml(c.id)}">
              <option ${ed.priority === "High Priority" ? "selected" : ""}>High Priority</option>
              <option ${ed.priority === "Medium Priority" ? "selected" : ""}>Medium Priority</option>
              <option ${ed.priority === "Low Priority" ? "selected" : ""}>Low Priority</option>
            </select>
          </div>
        </div>
        <div class="edit-input-wrap">
          <label>Admin notes</label>
          <input id="admin-notes-${escapeHtml(c.id)}" class="edit-input" type="text" value="${escapeHtml(ed.notes || "")}" data-action="admin-notes" data-id="${escapeHtml(c.id)}" />
        </div>
      </div>
    `;
  };
  return `
    <div class="modal-overlay">
      <div class="modal lg">
        <div class="modal-head">
          <div>
            <p class="title">Update all clinicians</p>
            <p class="sub">Edit status, priority, and notes for the whole team — save in one click</p>
          </div>
          <button class="modal-close" data-action="admin-close">&times;</button>
        </div>
        <div class="modal-body">
          <p class="admin-section-label">Therapists</p>
          ${therapy.map(row).join("")}
          <p class="admin-section-label spaced">Psychiatry</p>
          ${psych.map(row).join("")}
          ${inactive.length ? `
            <p class="admin-section-label spaced">Deactivated (hidden from staff)</p>
            ${inactive.map(c => `
              <div class="admin-row admin-row-inactive">
                <div class="admin-row-head">
                  <p class="admin-row-name">${escapeHtml(c.profile || c.name)}</p>
                  <button class="btn-warn" data-action="editor-reactivate" data-id="${escapeHtml(c.id)}">Reactivate</button>
                </div>
              </div>
            `).join("")}
          ` : ""}
        </div>
        <div class="modal-foot">
          <button class="btn-save" data-action="admin-save">Save all changes</button>
          <button class="btn-cancel" data-action="admin-close">Cancel</button>
        </div>
      </div>
    </div>
  `;
}

function renderEditorModal() {
  if (!state.editorId || !state.editorDraft) return "";
  const d = state.editorDraft;
  const isNew = state.editorId === "__new__";
  const existing = isNew ? null : state.clinicians.find(c => c.id === state.editorId);
  const check = (arr, v) => arr.includes(v) ? "checked" : "";
  return `
    <div class="modal-overlay">
      <div class="modal modal-editor">
        <div class="modal-head">
          <div>
            <span class="title">${isNew ? "Add clinician" : "Edit details — " + escapeHtml(existing ? existing.name : state.editorId)}</span>
            <p class="sub">${isNew ? "Creates a new clinician for all staff." : "Status, priority, notes, specialties and modalities are edited from the card itself."}</p>
          </div>
          <button class="modal-close" data-action="editor-cancel">&times;</button>
        </div>
        <div class="modal-body">
          ${state.editorErrors && state.editorErrors.length ? `
            <div class="editor-errors">${state.editorErrors.map(e => `<p>• ${escapeHtml(e)}</p>`).join("")}</div>
          ` : ""}
          <div class="editor-grid">
            <div class="ed-field">
              <label for="ed-name">Name *</label>
              <input id="ed-name" class="edit-input" type="text" value="${escapeHtml(d.name)}" data-action="editor-field" data-field="name" placeholder="Jane Doe" />
            </div>
            <div class="ed-field">
              <label for="ed-profile">Profile (name + credentials) *</label>
              <input id="ed-profile" class="edit-input" type="text" value="${escapeHtml(d.profile)}" data-action="editor-field" data-field="profile" placeholder="Jane Doe, LMHC" />
            </div>
            <div class="ed-field">
              <label>Provider type</label>
              <div class="ed-type">
                <button data-action="editor-type" data-type="therapy" class="${d.type === "therapy" ? "active" : ""}">Therapy</button>
                <button data-action="editor-type" data-type="psychiatry" class="${d.type === "psychiatry" ? "active" : ""}">Psychiatry</button>
              </div>
            </div>
            <div class="ed-field">
              <label for="ed-schedule">Schedule *</label>
              <input id="ed-schedule" class="edit-input" type="text" value="${escapeHtml(d.schedule)}" data-action="editor-field" data-field="schedule" placeholder="Mon-Fri" />
            </div>
            <div class="ed-field ed-span">
              <label>Offices *</label>
              <div class="ed-checks">
                ${VALID_OFFICES.map(o => `
                  <label><input type="checkbox" ${check(d.offices, o)} data-action="editor-office" data-office="${o}" /> ${o}</label>
                `).join("")}
                <label class="ed-virtual"><input type="checkbox" ${d.virtual ? "checked" : ""} data-action="editor-virtual" /> Offers telehealth (virtual)</label>
              </div>
            </div>
            <div class="ed-field ed-span">
              <label>Session groups * <span class="ed-hint">(what the Session type filters match on)</span></label>
              <div class="ed-checks">
                ${VALID_GROUPS.map(g => `
                  <label><input type="checkbox" ${check(d.groups, g)} data-action="editor-group" data-group="${g}" /> ${g}</label>
                `).join("")}
              </div>
            </div>
            <div class="ed-field">
              <label for="ed-indiv">Individual rate ($)</label>
              <input id="ed-indiv" class="edit-input" type="text" inputmode="decimal" value="${escapeHtml(d.indiv)}" data-action="editor-field" data-field="indiv" placeholder="185" />
            </div>
            <div class="ed-field">
              <label for="ed-indivdisplay">…or rate as text <span class="ed-hint">(sliding scale etc.)</span></label>
              <input id="ed-indivdisplay" class="edit-input" type="text" value="${escapeHtml(d.indivDisplay)}" data-action="editor-field" data-field="indivDisplay" placeholder="$100-$150 (sliding scale)" />
            </div>
            <div class="ed-field">
              <label for="ed-couples">Couples rate ($)</label>
              <input id="ed-couples" class="edit-input" type="text" inputmode="decimal" value="${escapeHtml(d.couples)}" data-action="editor-field" data-field="couples" placeholder="235 or blank" />
            </div>
            <div class="ed-field">
              <label for="ed-family">Family rate ($)</label>
              <input id="ed-family" class="edit-input" type="text" inputmode="decimal" value="${escapeHtml(d.family)}" data-action="editor-field" data-field="family" placeholder="235 or blank" />
            </div>
          </div>
          ${isNew ? `<p class="ed-note">New clinicians start as “Needs Clients / Medium Priority” with no specialties — set those from their card after saving.</p>` : ""}
        </div>
        <div class="modal-foot editor-foot">
          <div>
            <button class="btn-save" data-action="editor-save" ${state.editorBusy ? "disabled" : ""}>${state.editorBusy ? "Saving…" : (isNew ? "Add clinician" : "Save changes")}</button>
            <button class="btn-cancel" data-action="editor-cancel">Cancel</button>
          </div>
          ${!isNew ? `
          <div class="editor-danger">
            ${existing && existing.active === false
              ? `<button class="btn-warn" data-action="editor-reactivate" data-id="${escapeHtml(state.editorId)}">Reactivate</button>`
              : `<button class="btn-warn" data-action="editor-deactivate" data-id="${escapeHtml(state.editorId)}" title="Hide from all staff — reversible">Deactivate</button>`}
            <button class="btn-danger" data-action="editor-delete" data-id="${escapeHtml(state.editorId)}" title="Permanently delete — cannot be undone">Delete</button>
          </div>
          ` : ""}
        </div>
      </div>
    </div>
  `;
}

function renderHealthModal() {
  if (!state.healthOpen) return "";
  const issues = state.healthResults || [];
  const errors = issues.filter(i => i.severity === "error");
  const warns = issues.filter(i => i.severity === "warn");
  const infos = issues.filter(i => i.severity === "info");
  const rank = { error: 0, warn: 1, info: 2 };
  const sorted = [...issues].sort((a, b) => rank[a.severity] - rank[b.severity]);
  return `
    <div class="modal-overlay">
      <div class="modal">
        <div class="modal-head">
          <div>
            <span class="title">🩺 Health check</span>
            <p class="sub">Automated data &amp; logic checks on the current roster</p>
          </div>
          <button class="modal-close" data-action="health-close">&times;</button>
        </div>
        <div class="modal-body">
          ${issues.length === 0 ? `<p class="audit-ok">✓ All checks passed — no issues found.</p>` : `
            <div class="audit-summary">
              <span class="audit-count err">${errors.length} error${errors.length !== 1 ? "s" : ""}</span>
              <span class="audit-count warn">${warns.length} warning${warns.length !== 1 ? "s" : ""}</span>
              <span class="audit-count info">${infos.length} info</span>
            </div>
            ${sorted.map(i => `
              <div class="audit-item audit-${i.severity}">
                <span class="audit-who">${escapeHtml(i.who)}</span>
                <span>${escapeHtml(i.message)}</span>
              </div>
            `).join("")}
          `}
        </div>
        <div class="modal-foot">
          <button class="btn-cancel" data-action="health-close">Close</button>
        </div>
      </div>
    </div>
  `;
}

// ---------- render: top ----------
function render() {
  // preserve focus
  const active = document.activeElement;
  const activeId = active && active.id;
  const selStart = active && "selectionStart" in active ? active.selectionStart : null;
  const selEnd = active && "selectionEnd" in active ? active.selectionEnd : null;

  const root = document.getElementById("app");
  if (!state.authed) {
    root.innerHTML = renderLogin();
  } else if (state.loading) {
    root.innerHTML = `<div style="display:flex;align-items:center;justify-content:center;height:100vh;color:#94a3b8;font-size:14px;">Loading…</div>`;
  } else if (state.loadError) {
    root.innerHTML = `
      <div style="display:flex;flex-direction:column;gap:12px;align-items:center;justify-content:center;height:100vh;color:#991b1b;font-size:14px;padding:20px;text-align:center;">
        <div>Could not load clinicians: ${escapeHtml(state.loadError)}</div>
        <button class="login-btn" style="max-width:200px;" data-action="retry-load">Retry</button>
        <button class="btn-cancel" style="max-width:200px;" data-action="signout">Sign out</button>
      </div>`;
  } else {
    root.innerHTML = `
      <div class="app-shell">
        ${renderSidebar()}
        ${renderMainPane()}
      </div>
      ${renderSpecsModal()}
      ${renderModsModal()}
      ${renderAdminModal()}
      ${renderHealthModal()}
      ${renderEditorModal()}
    `;
  }

  // restore focus
  if (activeId) {
    const el = document.getElementById(activeId);
    if (el) {
      el.focus();
      if (selStart != null && el.setSelectionRange) {
        try { el.setSelectionRange(selStart, selEnd); } catch {}
      }
    }
  }
}

// ---------- actions ----------
function toggleArr(arr, val) {
  return arr.includes(val) ? arr.filter(x => x !== val) : [...arr, val];
}

function clearAllFilters() {
  state.search = "";
  state.offices = [];
  state.sessionTypes = [];
  state.selectedSpecs = [];
  state.selectedMods = [];
}

function handleAction(action, el, ev) {
  switch (action) {
    case "login-input":
      state.loginPw = el.value;
      state.loginError = false;
      return;
    case "login-email-input":
      state.loginEmail = el.value;
      state.loginError = false;
      return;
    case "login-submit":
      ev.preventDefault();
      if (sb) {
        if (state.loginBusy) return;
        const email = state.loginEmail.trim();
        const password = state.loginPw;
        if (!email || !password) { state.loginError = true; render(); return; }
        state.loginBusy = true;
        state.loginError = false;
        render();
        // On success, onAuthStateChange (boot) is the single place that loads
        // data and subscribes — it fires before this promise resolves, so doing
        // it here too would double-load.
        sb.auth.signInWithPassword({ email, password }).then(({ error }) => {
          state.loginBusy = false;
          if (error) {
            state.loginError = true;
            state.loginPw = "";
          } else {
            state.loginPw = "";
            state.loginEmail = "";
          }
          render();
        }).catch(() => {
          state.loginBusy = false;
          state.loginError = true;
          render();
        });
        return;
      }
      if (state.loginPw === LOGIN_PASSWORD) {
        sessionStorage.setItem("mcw_auth", "1");
        state.authed = true;
        state.loginPw = "";
        state.loginError = false;
        if (state.clinicians.length === 0) loadClinicians();
      } else {
        state.loginError = true;
        state.loginPw = "";
      }
      render();
      return;
    case "signout":
      if (sb) {
        sb.auth.signOut();
        state.clinicians = [];
      }
      sessionStorage.removeItem("mcw_auth");
      state.authed = false;
      render();
      return;
    case "retry-load":
      state.loading = true;
      render();
      loadClinicians().then(() => render());
      return;
    case "search-input":
      state.search = el.value; render(); return;
    case "type-set":
      state.typeFilter = el.dataset.type; render(); return;
    case "office-toggle":
      state.offices = toggleArr(state.offices, el.dataset.office); render(); return;
    case "session-toggle":
      state.sessionTypes = toggleArr(state.sessionTypes, el.dataset.session); render(); return;
    case "spec-search-input":
      state.specSearch = el.value; render(); return;
    case "spec-toggle":
      state.selectedSpecs = toggleArr(state.selectedSpecs, el.dataset.spec); render(); return;
    case "specs-clear":
      state.selectedSpecs = []; render(); return;
    case "mod-search-input":
      state.modSearch = el.value; render(); return;
    case "mod-toggle":
      state.selectedMods = toggleArr(state.selectedMods, el.dataset.mod); render(); return;
    case "mods-clear":
      state.selectedMods = []; render(); return;
    case "clear-all":
      clearAllFilters(); render(); return;
    case "sort-change":
      state.sortBy = el.value; render(); return;

    // card actions
    case "specs-expand":
      state.expandedSpecs.add(el.dataset.id); render(); return;
    case "specs-collapse":
      state.expandedSpecs.delete(el.dataset.id); render(); return;
    case "card-edit-start": {
      const c = state.clinicians.find(x => x.id === el.dataset.id);
      state.editingCardId = el.dataset.id;
      state.cardEdit = { accepting: c.accepting, priority: c.priority, notes: c.notes };
      render();
      return;
    }
    case "card-edit-accepting":
      state.cardEdit.accepting = el.value; return; // no re-render
    case "card-edit-priority":
      state.cardEdit.priority = el.value; return;
    case "card-edit-notes":
      state.cardEdit.notes = el.value; return;
    case "card-edit-save": {
      const id = el.dataset.id;
      state.clinicians = state.clinicians.map(c => c.id === id ? { ...c, ...state.cardEdit } : c);
      persist([id]);
      state.editingCardId = null;
      state.cardEdit = null;
      render();
      return;
    }
    case "card-edit-cancel":
      state.editingCardId = null;
      state.cardEdit = null;
      render();
      return;

    // specs modal
    case "specs-modal-open": {
      const c = state.clinicians.find(x => x.id === el.dataset.id);
      state.specsModalId = el.dataset.id;
      state.modalSpecs = [...c.specialties];
      state.modalNewSpec = "";
      render();
      return;
    }
    case "specs-modal-close":
      state.specsModalId = null;
      state.modalSpecs = null;
      state.modalNewSpec = "";
      render();
      return;
    case "modal-spec-toggle":
      state.modalSpecs = toggleArr(state.modalSpecs, el.dataset.spec);
      render();
      return;
    case "modal-spec-newinput":
      state.modalNewSpec = el.value;
      return;
    case "modal-spec-add": {
      const t = state.modalNewSpec.trim();
      if (t && !state.modalSpecs.includes(t)) state.modalSpecs.push(t);
      state.modalNewSpec = "";
      render();
      return;
    }
    case "modal-spec-save": {
      const id = state.specsModalId;
      state.clinicians = state.clinicians.map(c => c.id === id ? { ...c, specialties: state.modalSpecs.slice() } : c);
      persist([id]);
      state.specsModalId = null;
      state.modalSpecs = null;
      render();
      return;
    }

    // mods modal
    case "mods-modal-open": {
      const c = state.clinicians.find(x => x.id === el.dataset.id);
      state.modsModalId = el.dataset.id;
      state.modalMods = [...c.modalities];
      state.modalNewMod = "";
      render();
      return;
    }
    case "mods-modal-close":
      state.modsModalId = null;
      state.modalMods = null;
      state.modalNewMod = "";
      render();
      return;
    case "modal-mod-remove":
      state.modalMods = state.modalMods.filter(x => x !== el.dataset.mod);
      render();
      return;
    case "modal-mod-newinput":
      state.modalNewMod = el.value;
      return;
    case "modal-mod-add": {
      const t = state.modalNewMod.trim();
      if (t && !state.modalMods.includes(t)) state.modalMods.push(t);
      state.modalNewMod = "";
      render();
      return;
    }
    case "modal-mod-save": {
      const id = state.modsModalId;
      state.clinicians = state.clinicians.map(c => c.id === id ? { ...c, modalities: state.modalMods.slice() } : c);
      persist([id]);
      state.modsModalId = null;
      state.modalMods = null;
      render();
      return;
    }

    // clinician editor (add / edit details / deactivate / delete)
    case "editor-open": {
      if (!sb) { alert("Adding and editing clinicians requires the shared database (currently in local fallback mode)."); return; }
      const id = el.dataset.id;
      if (id === "__new__") {
        state.editorDraft = blankDraft();
      } else {
        const c = state.clinicians.find(x => x.id === id);
        if (!c) return;
        state.editorDraft = draftFromClinician(c);
      }
      state.editorId = id;
      state.editorErrors = null;
      state.editorBusy = false;
      render();
      return;
    }
    case "editor-cancel":
      closeEditor();
      render();
      return;
    case "editor-field":
      if (state.editorDraft) state.editorDraft[el.dataset.field] = el.value;
      return;
    case "editor-type":
      if (state.editorDraft) { state.editorDraft.type = el.dataset.type; render(); }
      return;
    case "editor-office":
      if (state.editorDraft) { state.editorDraft.offices = toggleArr(state.editorDraft.offices, el.dataset.office); render(); }
      return;
    case "editor-group":
      if (state.editorDraft) { state.editorDraft.groups = toggleArr(state.editorDraft.groups, el.dataset.group); render(); }
      return;
    case "editor-virtual":
      if (state.editorDraft) { state.editorDraft.virtual = !state.editorDraft.virtual; render(); }
      return;
    case "editor-save": {
      if (!state.editorDraft || state.editorBusy) return;
      const errors = validateDraft(state.editorDraft);
      if (errors.length) { state.editorErrors = errors; render(); return; }
      const fields = draftToFields(state.editorDraft);
      const isNew = state.editorId === "__new__";
      state.editorBusy = true;
      state.editorErrors = null;
      render();
      if (isNew) {
        const record = {
          id: generateId(fields.name),
          ...fields,
          accepting: "Needs Clients",
          priority: "Medium Priority",
          specialties: [],
          modalities: [],
          notes: "",
        };
        sb.from("clinicians").insert(record).select("id").then(({ error }) => {
          if (error) { state.editorBusy = false; state.editorErrors = ["Could not add: " + error.message]; render(); return; }
          const i = state.clinicians.findIndex(c => c.id === record.id);
          if (i < 0) state.clinicians.push(record); // realtime may have added it already
          closeEditor();
          render();
        }).catch(() => { state.editorBusy = false; state.editorErrors = ["Could not reach the database — check your connection."]; render(); });
      } else {
        const id = state.editorId;
        sb.from("clinicians").update(fields).eq("id", id).select("id").then(({ data, error }) => {
          if (error || !data || !data.length) {
            state.editorBusy = false;
            state.editorErrors = ["Could not save: " + (error ? error.message : "the clinician may have been deleted by a colleague.")];
            render();
            return;
          }
          state.clinicians = state.clinicians.map(c => c.id === id ? { ...c, ...fields } : c);
          closeEditor();
          render();
        }).catch(() => { state.editorBusy = false; state.editorErrors = ["Could not reach the database — check your connection."]; render(); });
      }
      return;
    }
    case "editor-deactivate": {
      const id = el.dataset.id;
      const c = state.clinicians.find(x => x.id === id);
      if (!c) return;
      if (!confirm(`Deactivate ${c.name}? They will be hidden from all staff, but can be reactivated from “Update all clinicians” at any time.`)) return;
      sb.from("clinicians").update({ active: false }).eq("id", id).select("id").then(({ data, error }) => {
        if (error || !data || !data.length) {
          alert("Could not deactivate" + (error ? ": " + error.message : "") + (error && /active/i.test(error.message) ? "\n\n(The database needs the Phase 2 upgrade — run phase2-upgrade.sql in the Supabase SQL editor.)" : ""));
          return;
        }
        state.clinicians = state.clinicians.map(x => x.id === id ? { ...x, active: false } : x);
        closeEditor();
        render();
      }).catch(() => alert("Could not reach the database — nothing was changed."));
      return;
    }
    case "editor-reactivate": {
      const id = el.dataset.id;
      sb.from("clinicians").update({ active: true }).eq("id", id).select("id").then(({ data, error }) => {
        if (error || !data || !data.length) { alert("Could not reactivate" + (error ? ": " + error.message : "")); return; }
        state.clinicians = state.clinicians.map(x => x.id === id ? { ...x, active: true } : x);
        closeEditor();
        render();
      }).catch(() => alert("Could not reach the database — nothing was changed."));
      return;
    }
    case "editor-delete": {
      const id = el.dataset.id;
      const c = state.clinicians.find(x => x.id === id);
      if (!c) return;
      if (!confirm(`PERMANENTLY delete ${c.name}? This cannot be undone — their notes, specialties, and history are gone for all staff.\n\nIf you just want to hide them, use Deactivate instead.`)) return;
      if (!confirm(`Really delete ${c.name} forever?`)) return;
      sb.from("clinicians").delete().eq("id", id).then(({ error }) => {
        if (error) { alert("Could not delete: " + error.message); return; }
        state.clinicians = state.clinicians.filter(x => x.id !== id);
        closeEditor();
        render();
      }).catch(() => alert("Could not reach the database — nothing was deleted."));
      return;
    }

    // health check + backup
    case "health-open":
      state.healthResults = runAudit(state.clinicians);
      state.healthOpen = true;
      render();
      return;
    case "health-close":
      state.healthOpen = false;
      render();
      return;
    case "export-backup":
      exportBackup();
      return;
    case "import-backup":
      importBackup();
      return;

    // admin panel
    case "admin-open": {
      state.adminEdits = {};
      state.adminOriginal = {};
      state.clinicians.forEach(c => {
        state.adminEdits[c.id] = { accepting: c.accepting, priority: c.priority, notes: c.notes };
        state.adminOriginal[c.id] = { accepting: c.accepting, priority: c.priority, notes: c.notes };
      });
      state.adminOpen = true;
      render();
      return;
    }
    case "admin-close":
      state.adminOpen = false;
      state.adminEdits = null;
      state.adminOriginal = null;
      render();
      return;
    case "admin-accepting":
      state.adminEdits[el.dataset.id].accepting = el.value;
      return;
    case "admin-priority":
      state.adminEdits[el.dataset.id].priority = el.value;
      return;
    case "admin-notes":
      state.adminEdits[el.dataset.id].notes = el.value;
      return;
    case "admin-save": {
      // Only apply/save rows the admin actually changed — writing untouched
      // rows would overwrite colleagues' concurrent edits with a stale snapshot.
      const changed = Object.keys(state.adminEdits).filter(id => {
        const ed = state.adminEdits[id];
        const orig = (state.adminOriginal && state.adminOriginal[id]) || {};
        return ed.accepting !== orig.accepting || ed.priority !== orig.priority || ed.notes !== orig.notes;
      });
      state.clinicians = state.clinicians.map(c => {
        return changed.includes(c.id) ? { ...c, ...state.adminEdits[c.id] } : c;
      });
      if (changed.length) persist(changed);
      state.adminOpen = false;
      state.adminEdits = null;
      state.adminOriginal = null;
      render();
      return;
    }
  }
}

// ---------- event delegation ----------
function findActionEl(target) {
  let el = target;
  while (el && el !== document.body) {
    if (el.dataset && el.dataset.action) return el;
    el = el.parentElement;
  }
  return null;
}

document.addEventListener("click", (ev) => {
  const el = findActionEl(ev.target);
  if (!el) return;
  const action = el.dataset.action;
  // skip click handling for inputs that have their own handlers
  if (el.tagName === "INPUT" && (el.type === "text" || el.type === "password" || el.type === "email")) return;
  if (el.tagName === "SELECT") return;
  // checkboxes are handled by change
  if (el.tagName === "INPUT" && el.type === "checkbox") return;
  // form submit handled separately
  if (action === "login-submit") return;
  handleAction(action, el, ev);
});

document.addEventListener("input", (ev) => {
  const el = findActionEl(ev.target);
  if (!el) return;
  if (el.tagName !== "INPUT") return;
  if (el.type !== "text" && el.type !== "password" && el.type !== "email") return;
  handleAction(el.dataset.action, el, ev);
});

document.addEventListener("change", (ev) => {
  const el = findActionEl(ev.target);
  if (!el) return;
  if (el.tagName === "INPUT" && el.type === "checkbox") {
    handleAction(el.dataset.action, el, ev);
  } else if (el.tagName === "SELECT") {
    handleAction(el.dataset.action, el, ev);
  }
});

document.addEventListener("submit", (ev) => {
  const el = findActionEl(ev.target);
  if (!el) return;
  if (el.dataset.action === "login-submit") {
    handleAction("login-submit", el, ev);
  }
});

// Escape-to-close for any open modal
document.addEventListener("keydown", (ev) => {
  if (ev.key !== "Escape") return;
  if (state.editorId) { closeEditor(); render(); }
  else if (state.healthOpen) { state.healthOpen = false; render(); }
  else if (state.adminOpen) { state.adminOpen = false; state.adminEdits = null; state.adminOriginal = null; render(); }
  else if (state.specsModalId) { state.specsModalId = null; state.modalSpecs = null; state.modalNewSpec = ""; render(); }
  else if (state.modsModalId) { state.modsModalId = null; state.modalMods = null; state.modalNewMod = ""; render(); }
});

// Enter-to-add for modal text inputs
document.addEventListener("keydown", (ev) => {
  if (ev.key !== "Enter") return;
  const el = ev.target;
  if (!el.dataset || !el.dataset.action) return;
  if (el.dataset.action === "modal-spec-newinput") {
    ev.preventDefault();
    handleAction("modal-spec-add", el, ev);
  } else if (el.dataset.action === "modal-mod-newinput") {
    ev.preventDefault();
    handleAction("modal-mod-add", el, ev);
  }
});

// ---------- init ----------
async function boot() {
  if (sb) {
    // Shared mode: session comes from Supabase Auth, not sessionStorage.
    state.authed = false;
    state.loading = true;
    render(); // show something immediately instead of a blank page
    try {
      const { data } = await sb.auth.getSession();
      state.authed = !!(data && data.session);
    } catch {
      state.authed = false;
    }
    // Single place that reacts to sign-in/sign-out (fires during
    // signInWithPassword, before its promise resolves).
    sb.auth.onAuthStateChange((_event, session) => {
      const nowAuthed = !!session;
      if (nowAuthed === state.authed) return;
      state.authed = nowAuthed;
      if (nowAuthed) {
        state.loading = true;
        render();
        loadClinicians().then(() => { state.loading = false; render(); subscribeRealtime(); });
      } else {
        render(); // session expired or signed out elsewhere
      }
    });
    if (state.authed) {
      await loadClinicians();
      subscribeRealtime();
    }
    state.loading = false;
    render();
    return;
  }
  loadClinicians();
  render();
}
boot();
