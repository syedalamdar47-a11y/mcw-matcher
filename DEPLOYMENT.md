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

Only these four files are needed for the site to work:

| File | Purpose |
|---|---|
| `index.html` | Entry point — loads CSS and JS |
| `style.css` | All styles |
| `data.js` | Seed clinician data, storage key, and login password |
| `script.js` | App state, rendering, and event handlers |

## Files to ignore / never deploy

- `.claude/` — local Claude Code config (launch.json, settings)
- `MCW_Clinician_Matcher.jsx` — legacy React version, kept for reference only
- `DEPLOYMENT.md` — this file (safe to commit; Netlify just ignores it)
- Any `node_modules/`, `dist/`, or `.env` files if they ever appear

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

4. **Data is per-browser.** The app uses `localStorage` (persistent per browser) for clinician edits and `sessionStorage` for login state. There is no shared backend. Do not add localStorage writes that assume cross-user sync.

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
- Password to log in to the live app: see `LOGIN_PASSWORD` in `data.js`
