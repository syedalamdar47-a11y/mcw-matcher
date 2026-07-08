# Deployment Guide

This document explains how the MCW Client Matcher is deployed and how to push changes live. If you're an AI agent or LLM reading this, follow these instructions exactly — do not invent new deployment steps.

## TL;DR for agents

1. Edit files locally (`index.html`, `style.css`, `data.js`, `script.js`)
2. Commit and push to the `main` branch on GitHub
3. Netlify auto-deploys within ~30 seconds — no manual deploy step needed

**Do not** run build commands, bundlers, or frameworks. This is plain static HTML/CSS/JS with no build step.

---

## Project overview

- **Type**: Static website (vanilla HTML + CSS + JS, no framework, no build step)
- **Live URL**: https://mcw-clinician-matcher.netlify.app
- **GitHub repo**: https://github.com/syedalamdar47-a11y/mcw-matcher
- **Host**: Netlify (free tier)
- **Deploy branch**: `main`
- **Auto-deploy**: Enabled — any push to `main` triggers a Netlify rebuild

## Files that get deployed

These files are needed for the site to work:

| File | Purpose |
|---|---|
| `index.html` | Entry point — loads CSS and JS |
| `style.css` | All styles |
| `data.js` | Seed clinician data, storage key, and login password |
| `script.js` | App state, rendering, event handlers, auditor, backup/restore |
| `logo.png` | Logo + favicon (referenced by `index.html` and the app) |
| `_headers` | Netlify security headers (CSP, X-Frame-Options, etc.) |

## Files to ignore / never deploy

- `.claude/` — local Claude Code config (launch.json, settings)
- `DEPLOYMENT.md` — this file (safe to commit; Netlify just ignores it)
- Any `node_modules/`, `dist/`, or `.env` files if they ever appear

> The old `MCW_Clinician_Matcher.jsx` legacy React duplicate was removed (it was a
> stale, gitignored copy that drifted from production and held a second copy of the
> password). There is now a single source of truth.

---

## How to make changes and deploy them

### Option A: Edit locally + push via git

```bash
# from D:\Clinican Modeliaitlities
git add index.html style.css data.js script.js
git commit -m "describe your change"
git push origin main
```

Netlify picks up the push automatically and rebuilds. Check the deploy status at:
https://app.netlify.com/projects/mcw-clinician-matcher/deploys

### Option B: Edit directly on GitHub (no local clone needed)

1. Go to https://github.com/syedalamdar47-a11y/mcw-matcher
2. Click the file you want to edit
3. Click the pencil icon (Edit)
4. Make changes
5. Scroll down, click **Commit changes**
6. Netlify auto-deploys within ~30 seconds

### Verifying a deploy

- Open the Netlify dashboard: https://app.netlify.com/projects/mcw-clinician-matcher
- Check the **Deploys** tab — the latest commit should show "Published"
- Visit https://mcw-clinician-matcher.netlify.app to see the change
- If the site looks unchanged, hard-refresh (Ctrl+Shift+R) to bypass browser cache

---

## Common change recipes

### Change the login password

Edit line 2 of `data.js`:

```js
const LOGIN_PASSWORD = "mcw2025"; // change this string
```

Commit and push. That's it.

### Add or remove a clinician

Edit the `SEED_DATA` array in `data.js`. Each clinician is one object in the array. Follow the existing shape exactly — required fields include `id`, `name`, `profile`, `type`, `offices`, `schedule`, `accepting`, `priority`, `groups`, `modalities`, `specialties`, `notes`.

**Important**: `id` must be unique. Changing an existing clinician's `id` will orphan any edits users have made in `localStorage`.

### Change styles

Edit `style.css`. Classes follow a clear naming convention — inspect the element in browser devtools to find the class name before editing.

### Change behavior / rendering

Edit `script.js`. The file is organized into sections with `// ----------` header comments:
- helpers
- render functions (login, sidebar, card, main pane, modals)
- actions (`handleAction` switch statement)
- event delegation (click/input/change/keydown/submit)
- init

---

## Important constraints

1. **No build step.** Do not add webpack, vite, esbuild, rollup, parcel, etc. Netlify serves files as-is from the repo root. If you need to add a build step, you must also update Netlify's build settings — ask the user first.

2. **No npm dependencies.** Keep the project zero-dependency. If you think you need a library, ask first. For small utilities, write inline JS instead.

3. **Password is client-side.** `LOGIN_PASSWORD` in `data.js` is visible to anyone who views source. Do not treat this as real auth. If stronger access control is needed, use Netlify's paid visitor password feature or add server-side auth (a bigger architectural change — discuss with user first).

4. **Data is per-browser.** The app uses `localStorage` (persistent per browser) for clinician edits and `sessionStorage` for login state. There is no shared backend. Do not add localStorage writes that assume cross-user sync. Use the **⬇ Backup** button (sidebar footer) to export edits to a JSON file and **⬆ Restore** to import them on another browser until a shared backend exists.

7. **Do NOT change `STORAGE_KEY`** (`data.js` line 1). Renaming it makes the app read a non-existent key and silently fall back to seed data, wiping every staff edit on every browser with no migration. Treat it as a permanent value.

8. **Run the 🩺 Health check** (sidebar footer) after editing `data.js` — it flags duplicate ids, missing/invalid fields, and rate/group mismatches before they cause wrong filter results.

5. **Preserve focus across re-renders.** `script.js` has a focus-preservation pattern in `render()` that restores the active input after re-render. If you add new text inputs, give them a unique `id` attribute so focus preservation works.

6. **Escape user input.** All dynamic text goes through `escapeHtml()` before being inserted into template strings. Never concatenate unescaped strings into innerHTML.

---

## Rolling back a broken deploy

If a deploy breaks the site:

1. Go to https://app.netlify.com/projects/mcw-clinician-matcher/deploys
2. Find the last working deploy in the list
3. Click it, then click **Publish deploy** — this instantly rolls back the live site
4. Separately, fix the bad commit on GitHub (revert or force-correct) so the next push doesn't re-break it

---

## Netlify settings (reference only — do not change without user approval)

- Build command: (empty)
- Publish directory: (empty / repo root)
- Branch: `main`
- Node version: N/A (no build)
- Environment variables: none

If Netlify ever tries to run a build command, something has gone wrong — check the repo for a stray `package.json` or `netlify.toml` and remove it.

---

## Contact / ownership

- GitHub owner: `syedalamdar47-a11y`
- Netlify project slug: `mcw-clinician-matcher`
- Live domains: `matcher.mcnultycounseling.com` (custom, via Cloudflare DNS CNAME → Netlify)
  and `mcw-clinician-matcher.netlify.app`
- Sign-in: per-staff email+password accounts in Supabase (see below). The old
  `LOGIN_PASSWORD` in `data.js` is used ONLY if `SUPABASE_URL` is emptied (local mode).

---

## Shared backend (Supabase) — active since July 2026

The app runs in **shared mode**: clinician data lives in a Supabase Postgres table
(`clinicians`) and every staff member signs in with their own email+password.
Edits save to the shared database and appear on colleagues' screens live.

- **Project:** `mcw-matcher`, ref `gazzhqtqnmpyjejwujei` (supabase.com dashboard)
- **Config:** `SUPABASE_URL` + `SUPABASE_ANON_KEY` at the top of `data.js`. The
  publishable/anon key is safe to be public — Row Level Security means signed-out
  visitors get zero rows. Emptying `SUPABASE_URL` reverts the app to the legacy
  per-browser localStorage mode (useful as an emergency fallback).
- **Library:** `supabase.min.js` is vendored in the repo (supabase-js v2.110.0,
  pinned — do not swap for a CDN tag; CSP allows same-origin scripts only).
- **Schema/setup:** `supabase-setup.sql` re-creates the table, RLS policies,
  realtime publication, and seed data from scratch (one paste in the SQL editor).
- **Add/remove staff:** Supabase dashboard → Authentication → Users. Public
  sign-up should stay OFF (Authentication → Sign In / Providers).
- **SEED_DATA in `data.js` is now only a fallback** for local mode. The database
  is the source of truth for clinician data in shared mode.

---

## Google Sheet -> priority sync

Configured via `SHEET_SYNC` at the top of `data.js`. When `csvUrl` is set to a
published-to-web CSV URL, the app syncs clinician **priority** (and optionally
**accepting**) from the sheet — automatically at sign-in and via the sidebar's
"⟳ Sync from Sheet" button, which also shows a report of what changed.

Rules:
- The sheet MUST have an `id` column with the stable clinician ids
  (see `sheet-template.csv` for the current list). Matching is by id only —
  never by name (the roster has duplicate first names).
- Priority values accepted: High/Medium/Low (any casing, "High Priority",
  or 1/2/3). Accepting values: Accepting/yes/open, Needs Clients,
  Not Accepting/no/closed/full. Anything else is REPORTED and skipped —
  never guessed.
- The sheet only ever changes priority/accepting. Other fields are untouched.
- Only rows that actually differ are written, and changes propagate live to
  all staff screens.
- The published-CSV URL is public to anyone who has it; it exposes whatever
  columns the published tab contains. Keep that tab minimal (id, name,
  priority, accepting).
