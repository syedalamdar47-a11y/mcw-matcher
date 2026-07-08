# MCW Clinician Matcher — User Guide & SOPs

**App address:** https://matcher.mcnultycounseling.com
(the old address, mcw-clinician-matcher.netlify.app, still works and shows the same thing)

**Who this guide is for:** front-office staff (daily use) and the practice owner/admin (managing clinicians, staff accounts, and the Google Sheet).

---

## 1. What this system does

The Clinician Matcher is the front office's single source of truth for **who is taking clients right now** and **who fits a new client best**. Everyone sees the same live data:

| Capability | Who uses it |
|---|---|
| Search, filter, and sort clinicians to match a new client | All staff |
| Update a clinician's availability, priority, and admin notes | All staff |
| Edit specialties and modalities | All staff |
| **Add a new clinician, edit their details, deactivate or delete them** | Admin (any signed-in account can, but treat it as an admin task) |
| **Priorities update automatically from the practice's Google Sheet** | Automatic (sheet is maintained by the owner) |
| Health Check — one-click scan for data problems | All staff |
| Nightly automated audit with email alerts | Automatic |

Key facts:

- **Everything is shared and live.** When one person marks a clinician "Not Accepting," every other screen in the practice updates within seconds — no refresh needed.
- **Each staff member has their own login** (email + password). There is no shared password anymore.
- The app works on phones and tablets too.

---

## 2. Signing in

1. Go to **matcher.mcnultycounseling.com**
2. Enter your **work email** and the **password you were given**
3. Click **Sign in**

**There is no self–sign-up, on purpose.** Only accounts created by the practice admin exist. If sign-ups were open, anyone who found the page could register and see the roster, rates, and internal notes. If you need an account, ask the practice owner (SOP in section 7).

**Signing out:** bottom of the left sidebar → **Sign out**. Do this on shared computers at the end of the day.

---

## 3. Daily use — matching a client

### Finding the right clinician

The left sidebar filters the list in real time:

| Filter | What it means |
|---|---|
| **Search by name** | Type any part of the clinician's name |
| **Provider type** | Therapy / Psychiatry tabs |
| **Office** | DTSP, Tyrone, Tampa, Sarasota (virtual-only clinicians appear under every office they serve) |
| **Session type** | Individual, Couples, Family, Minors — matches what the clinician actually offers |
| **Specialty** | Anxiety, Trauma, OCD… (therapy only) |
| **Modality** | CBT, EMDR, Gottman… (therapy only) |

The default sort is **Priority + Availability**, so the clinicians the practice most wants filled appear first. Cards show: schedule, rates, session groups, modalities, specialties, and any admin note (yellow box).

> Tip: if the list looks strangely empty, check the top bar for leftover filter chips and click their **×**, or hit **Clear all filters**.

### After you place a client

If a clinician's availability changed (e.g. they just took their last open slot), update them right away so colleagues see it:

1. On their card, click **Edit status & priority**
2. Change **Availability** (Accepting / Needs Clients / Not Accepting) and, if needed, **Priority** and the **Admin note**
3. **Save** — all other staff screens update automatically

The same card has **edit** buttons next to Specialties and Modalities.

> **Note on priority:** priority is normally driven by the **Google Sheet** (section 6). A manual priority change in the app lasts only until the next sheet sync — put lasting priority changes in the sheet.

---

## 4. SOP — Adding a new clinician

**When:** a new clinician joins the practice.
**Time:** ~3 minutes.

1. Sign in → bottom of the sidebar → **+ Add clinician**
2. Fill in the form:
   - **Name** — e.g. `Jane Doe`
   - **Profile** — name + credentials as it should appear on the card, e.g. `Jane Doe, LMHC`
   - **Provider type** — Therapy or Psychiatry
   - **Schedule** — e.g. `Mon-Fri` or `Mon-Wed in-person, Thurs telehealth`
   - **Offices** — check every office they serve (check Virtual too if telehealth-only)
   - **Session groups** — check what they offer: Individuals / Couples / Families / Minors. ⚠️ This drives the Session-type filters — if you skip it, they won't show up in filtered searches.
   - **Rates** — individual rate as a number (e.g. `185`), or use the "rate as text" box for sliding scales (e.g. `$100-$150 (sliding scale)`); couples/family rates optional
3. Click **Add clinician**
4. New clinicians start as **Needs Clients / Medium Priority** with no specialties. Open their card and use the **edit** buttons to add **Specialties** and **Modalities**, and *Edit status & priority* if needed.
5. **Add them to the Google Sheet** (so their priority is managed like everyone else's):
   - On their card, click **Edit details** — the top line shows **"ID for the Google Sheet"** (e.g. `jane_doe`). Copy it.
   - Open the practice's priority Google Sheet and add a row: paste the **id**, their name, and their priority (`High` / `Medium` / `Low`) and availability.
   - Until you do this, the sync simply leaves them unchanged (the sync report lists them under "in the app but not in the sheet" as a reminder).

---

## 5. SOP — Removing a clinician

There are two ways. **Deactivate is almost always the right choice.**

### Deactivate (reversible — use this)

**When:** a clinician goes on leave, stops taking new clients long-term, or leaves the practice.

1. On their card → **Edit details**
2. Click **Deactivate** → confirm
3. They disappear from every staff screen immediately, but **all their data is kept**

**To bring them back:** sidebar → **⚙ Update all clinicians** → scroll to the **"Deactivated (hidden from staff)"** section at the bottom → **Reactivate**.

### Delete (permanent — rarely needed)

**When:** only for true mistakes, e.g. you created a duplicate by accident.

1. **Edit details** → **Delete** → confirm **twice**
2. Everything about them is permanently erased for all staff. This cannot be undone.

Also remove/annotate their row in the Google Sheet either way, or the nightly audit will flag the unmatched row.

---

## 6. SOP — Managing priorities with the Google Sheet

The practice's Google Sheet is the **boss** for two fields: **priority** and **availability**. The app pulls from it:

- **Automatically** every time someone signs in
- **On demand** via the sidebar button **⟳ Sync from Sheet**, which also shows a report of exactly what changed

### Editing priorities

1. Open the Google Sheet (the tab with columns `id`, `name`, `priority`, `accepting`)
2. Change the `priority` cell — you can type `High`, `Medium`, `Low` (any capitalization, or `High Priority`, or even `1`/`2`/`3`)
3. Optionally change `accepting` — `Accepting`, `Needs Clients`, or `Not Accepting` (also flexible: `yes`, `open`, `no`, `full`…)
4. That's it. The app picks it up at the next sign-in or manual sync.

### Rules to know

- **Never change the `id` column.** It's how rows match clinicians. Two clinicians can share a first name — the id is the only safe key.
- Google caches the published sheet for **about 5 minutes** — a change may take a few minutes to be visible to the app. Use **⟳ Sync from Sheet** and check the report if you're in a hurry.
- Typos are safe: an unrecognized value (e.g. `Hgih`) is **reported and skipped, never guessed**. The sync report and the nightly audit will both tell you.
- A clinician missing from the sheet is left unchanged (and listed in the report).
- The sheet only ever touches priority/availability — it can't damage names, rates, notes, or anything else.

---

## 7. SOP — Staff accounts (admin only)

Staff accounts are managed in the **Supabase dashboard**: **supabase.com** → sign in → project **mcw-matcher** → **Authentication** (key icon) → **Users**.

### Add a staff member

1. Authentication → Users → **Add user** → **Create new user**
2. Enter their **work email** and set a **password** (check **Auto Confirm User** if shown)
3. Give them the password privately; they sign in at matcher.mcnultycounseling.com

### Someone forgot their password

There's no self-serve reset link on the login page (yet). The admin resets it:

1. Authentication → Users → click the person's email
2. Use the **⋮ / options menu** → **Update / reset password** if your dashboard shows it, and set a new one
3. If you don't see that option, the always-works fallback: **Delete** the user and **Add user** again with the same email and a new password. This is completely safe — staff accounts hold no data; the roster lives separately.

### Someone leaves the practice

**Same day:** Authentication → Users → **⋮** next to their name → **Delete user**. Their login stops working immediately on every device.

> Keep the **`audit-bot@mcnultycounseling.com`** user — that's the automated nightly auditor, not a person.

---

## 8. Built-in safety nets

| Tool | Where | What it does |
|---|---|---|
| **🩺 Health** | Sidebar footer | Instantly scans the roster for problems: duplicate ids, missing fields, invalid values, rate/group mismatches that would hide someone from filters |
| **Sync report** | Opens after **⟳ Sync from Sheet** (and automatically if a sync finds problems) | Shows exactly what the sheet changed, plus bad values and unmatched rows |
| **Push audit** | Automatic (GitHub) | Every code/data change is checked within a minute; a mistake that would blank the site gets flagged immediately |
| **Nightly audit** | Automatic, ~6–7 am ET | Checks the live database and the Google Sheet — including "sheet says X but the app shows Y" drift — and **emails the owner via GitHub if anything is wrong** |

If you get a GitHub "audit failed" email: open the link in it — the summary lists each problem in plain English (usually a sheet typo or an unmatched row).

---

## 9. Troubleshooting & FAQ

**The page looks outdated / a fix isn't showing.**
Hard-refresh once: **Ctrl+Shift+R** (Windows) or **Cmd+Shift+R** (Mac).

**"Could not load clinicians" with a Retry button.**
Usually a brief internet hiccup — click **Retry**. If it persists, supabase.com may be having an outage; the data is safe and will return.

**A clinician I know exists isn't in the list.**
1. Check filter chips at the top — clear them. 2. Check the right Provider-type tab. 3. Ask the admin to check **⚙ Update all clinicians → Deactivated** — they may have been deactivated.

**Why can't people sign themselves up on the login page?**
Security. The roster, rates, and internal routing notes are confidential — accounts exist only when the admin creates them.

**I changed the sheet but the app didn't update.**
Google publishes sheet changes with up to ~5 minutes' delay. Wait a few minutes, click **⟳ Sync from Sheet**, and read the report — it will either show your change or tell you exactly why it was skipped (typo, wrong id, etc.).

**Someone edited a clinician at the same time as me.**
Different fields can't collide (details, status, specialties, and modalities save independently). For the same field, the last save wins — the screens update live, so you'll see it happen.

**Emergency: the shared system is down and we need the list NOW.**
The old read-only fallback still exists: the developer can switch the app to "local mode" with a one-line change. Data would be per-browser and possibly stale — it's a break-glass option only.

---

## 10. For the developer / future maintenance

- Repo: github.com/syedalamdar47-a11y/mcw-matcher — pushing to `main` auto-deploys via Netlify
- `DEPLOYMENT.md` covers architecture, the Supabase backend, sheet-sync rules, and constraints
- Audit rules live in `audit.js` (shared by the in-app Health Check, the push gate, and the nightly run in `.github/workflows/audit.yml`)
- `supabase-setup.sql` rebuilds the database from scratch; `phase2-upgrade.sql` adds the `active` column

*Guide last updated: July 2026.*
