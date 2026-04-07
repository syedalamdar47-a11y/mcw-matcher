// ============================================================
// MCW Client Matcher — vanilla JS app
// ============================================================

const state = {
  authed: sessionStorage.getItem("mcw_auth") === "1",
  loginPw: "",
  loginError: false,
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
  editingCardId: null,
  cardEdit: null,
  specsModalId: null,
  modsModalId: null,
  modalSpecs: null,
  modalNewSpec: "",
  modalMods: null,
  modalNewMod: "",
  expandedSpecs: new Set(),
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

function loadClinicians() {
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

function persist() {
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

function uniqueSorted(arr) {
  return [...new Set(arr)].filter(Boolean).sort();
}

function getFiltered() {
  let res = state.clinicians.filter(c => c.type === state.typeFilter);
  if (state.search.trim()) {
    const q = state.search.toLowerCase();
    res = res.filter(c => c.name.toLowerCase().includes(q) || c.profile.toLowerCase().includes(q));
  }
  if (state.offices.length) {
    res = res.filter(c => state.offices.some(o => c.offices.includes(o)));
  }
  if (state.sessionTypes.length) {
    res = res.filter(c => state.sessionTypes.every(st => {
      if (st === "Couples") return !!c.couples;
      if (st === "Family") return !!c.family;
      if (st === "Minors") return c.groups.includes("Minors");
      return true;
    }));
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
          <label class="login-label" for="login-pw">Password</label>
          <input
            id="login-pw"
            type="password"
            class="login-input ${state.loginError ? "error" : ""}"
            placeholder="Enter password…"
            value="${escapeHtml(state.loginPw)}"
            data-action="login-input"
            autofocus
          />
          ${state.loginError ? `<p class="login-error">Incorrect password. Please try again.</p>` : ""}
          <button type="submit" class="login-btn">Sign in</button>
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
        <button class="admin-btn" data-action="admin-open">⚙ Update all clinicians</button>
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
            <button class="section-edit" data-action="mods-modal-open" data-id="${c.id}">edit</button>
          </div>
          ${c.modalities.length
            ? `<p class="modalities-text">${escapeHtml(c.modalities.join(" · "))}</p>`
            : `<button class="section-edit" data-action="mods-modal-open" data-id="${c.id}">+ Add modalities</button>`
          }
        </div>

        ${c.type === "therapy" ? `
          <div class="section">
            <div class="section-head">
              <span class="section-title">Specialties</span>
              <button class="section-edit" data-action="specs-modal-open" data-id="${c.id}">edit</button>
            </div>
            <div class="spec-tags">
              ${visible.map(s => `<span class="spec-tag">${escapeHtml(s)}</span>`).join("")}
              ${!expanded && hidden > 0 ? `<button class="more-btn" data-action="specs-expand" data-id="${c.id}">+${hidden} more</button>` : ""}
              ${expanded && hidden > 0 ? `<button class="less-btn" data-action="specs-collapse" data-id="${c.id}">show less</button>` : ""}
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
            <input id="card-edit-notes-${c.id}" class="edit-input" type="text" value="${escapeHtml(ed.notes || "")}" data-action="card-edit-notes" />
          </div>
          <div class="edit-actions">
            <button class="btn-save" data-action="card-edit-save" data-id="${c.id}">Save</button>
            <button class="btn-cancel" data-action="card-edit-cancel">Cancel</button>
          </div>
        </div>
      ` : `
        <div class="card-foot">
          <button data-action="card-edit-start" data-id="${c.id}">Edit status &amp; priority</button>
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
  const therapy = state.clinicians.filter(c => c.type === "therapy");
  const psych = state.clinicians.filter(c => c.type === "psychiatry");
  const row = (c) => {
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
            <select data-action="admin-accepting" data-id="${c.id}">
              <option ${ed.accepting === "Accepting" ? "selected" : ""}>Accepting</option>
              <option ${ed.accepting === "Needs Clients" ? "selected" : ""}>Needs Clients</option>
              <option ${ed.accepting === "Not Accepting" ? "selected" : ""}>Not Accepting</option>
            </select>
          </div>
          <div>
            <label>Priority</label>
            <select data-action="admin-priority" data-id="${c.id}">
              <option ${ed.priority === "High Priority" ? "selected" : ""}>High Priority</option>
              <option ${ed.priority === "Medium Priority" ? "selected" : ""}>Medium Priority</option>
              <option ${ed.priority === "Low Priority" ? "selected" : ""}>Low Priority</option>
            </select>
          </div>
        </div>
        <div class="edit-input-wrap">
          <label>Admin notes</label>
          <input id="admin-notes-${c.id}" class="edit-input" type="text" value="${escapeHtml(ed.notes || "")}" data-action="admin-notes" data-id="${c.id}" />
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
        </div>
        <div class="modal-foot">
          <button class="btn-save" data-action="admin-save">Save all changes</button>
          <button class="btn-cancel" data-action="admin-close">Cancel</button>
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
  } else {
    root.innerHTML = `
      <div class="app-shell">
        ${renderSidebar()}
        ${renderMainPane()}
      </div>
      ${renderSpecsModal()}
      ${renderModsModal()}
      ${renderAdminModal()}
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
    case "login-submit":
      ev.preventDefault();
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
      sessionStorage.removeItem("mcw_auth");
      state.authed = false;
      render();
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
      persist();
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
      persist();
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
      persist();
      state.modsModalId = null;
      state.modalMods = null;
      render();
      return;
    }

    // admin panel
    case "admin-open": {
      state.adminEdits = {};
      state.clinicians.forEach(c => {
        state.adminEdits[c.id] = { accepting: c.accepting, priority: c.priority, notes: c.notes };
      });
      state.adminOpen = true;
      render();
      return;
    }
    case "admin-close":
      state.adminOpen = false;
      state.adminEdits = null;
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
      state.clinicians = state.clinicians.map(c => {
        const ed = state.adminEdits[c.id];
        return ed ? { ...c, ...ed } : c;
      });
      persist();
      state.adminOpen = false;
      state.adminEdits = null;
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
  if (el.tagName === "INPUT" && (el.type === "text" || el.type === "password")) return;
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
  if (el.type !== "text" && el.type !== "password") return;
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
loadClinicians();
render();
