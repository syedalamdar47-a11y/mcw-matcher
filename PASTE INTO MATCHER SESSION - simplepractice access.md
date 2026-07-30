# Paste this into the Claude Code session on the Matcher machine

> **How to use:** copy everything below the line into that session as your first
> message. It explains the goal, how SimplePractice access works, and the exact
> recipe. You only have to do one thing yourself: log in to SimplePractice once
> when it asks (same email and password you always use).

---

## What we are building

I run **Matcher** (matcher.mcnultycounseling.com) — a clinician matching site for
McNulty Counseling & Wellness. The front office filters by provider type,
location, session type, specialty and modality, and gets a list of matching
therapists sorted by priority.

**What I need you to add: live SimplePractice availability inside Matcher.**

The team asked for this in our management meeting. Right now the front office has
Matcher on one screen and SimplePractice on the other — they find a good therapist
match, then flip to SimplePractice to hunt for open slots while the client waits on
the phone.

**Goal:** next to each clinician in Matcher, show their **next 3 open appointment
slots**, read live from SimplePractice. So "I need someone ASAP" and "I can only do
Wednesdays" can both be answered without leaving the page.

---

## How SimplePractice access works (this part is already solved — just reuse it)

SimplePractice has **no public API**. But its own web app talks to an internal
JSON API, and once a browser is logged in you can call those same endpoints. That
is how my other project (Mothership) pulls all its data, and it has been running
nightly for weeks.

**The recipe:**

1. Use **Playwright** with a **persistent context** — a folder that keeps the
   browser profile and cookies, so we log in once and stay logged in:

   ```js
   import { chromium } from "playwright";
   const ctx = await chromium.launchPersistentContext("./.sp-profile", { headless: true });
   const page = ctx.pages()[0] ?? (await ctx.newPage());
   ```

2. **Sign in if needed** (only the first time, or when the session expires):

   ```js
   await page.goto("https://account.simplepractice.com", { waitUntil: "domcontentloaded", timeout: 150000 });
   await page.waitForTimeout(3000);
   if (/sign in/i.test(await page.title())) {
     await page.locator("#user_email").fill(process.env.SP_EMAIL);
     await page.locator("#user_password").fill(process.env.SP_PASSWORD);
     await page.locator("#user_password").press("Enter");
     await page.waitForTimeout(6000);
   }
   // then land on the app so same-origin fetches are allowed:
   await page.goto("https://secure.simplepractice.com/calendar", { waitUntil: "domcontentloaded", timeout: 150000 });
   await page.waitForTimeout(6000);
   ```

3. **Call the internal API from inside the page** (this is the key trick — the
   fetch must run in the page, not in Node, so it carries the session):

   ```js
   const res = await page.evaluate(async (url) => {
     const r = await fetch(url, { headers: { Accept: "application/vnd.api+json" } });
     return { status: r.status, body: await r.text() };
   }, "/frontend/team-members?page%5Bsize%5D=250");
   ```

**Endpoints that matter for this project:**

| What | Path |
|---|---|
| Clinician ids + names | `/frontend/team-members?page%5Bsize%5D=250` |
| Set availability (open hours) | `/frontend/availabilities?filter%5BtimeRange%5D=<startISO>,<endISO>` |
| Appointments (what is already booked) | `/frontend/appointments?filter%5BtimeRange%5D=<startISO>,<endISO>` |

**Open slots = set availability MINUS existing appointments.** Availability
occurrences come back pre-materialised; overlapping availability blocks for the
same clinician must be merged (interval union) before subtracting appointments, or
hours get double counted.

**Credentials:** I will put `SP_EMAIL` and `SP_PASSWORD` in this project's
`.env.local` myself. Never print them, never commit them, and never write them into
any file other than `.env.local`.

---

## Rules you must follow (these are non-negotiable)

1. **Be polite to SimplePractice.** Requests strictly one at a time, never in
   parallel, with a random **0.7–1.8 second pause** between them. No fast retry
   loops. If a request fails, wait 10 seconds, try once more, then give up and log
   it. SimplePractice must never see anything that looks like a bot hammering it.
2. **Read only.** Never POST, PUT, PATCH or DELETE to SimplePractice. We never
   modify anything in the practice's records.
3. **Never store client names or any client details.** This is protected health
   information. For slot-finding you only need *times*, never who is in them. If
   you must handle a client identifier in memory, hash it and never write it to a
   database, log or file.
4. **Only one process can hold the browser profile at a time.** If a second script
   tries to use `.sp-profile` while another is running, it fails. So put SP access
   behind ONE long-running service and have the app call that service — don't have
   the web app launch browsers per request.
5. **Cache.** The front office may look at many clinicians in a row. Cache slots per
   clinician for a few minutes so one busy phone call doesn't trigger dozens of
   calls to SimplePractice.

---

## What I want you to build

1. A small **service** that owns the logged-in SimplePractice session and exposes a
   local HTTP endpoint like:

   ```
   GET /next-slots?clinician=<name or id>&count=3
   -> { clinician: "...", slots: ["2026-08-03T14:00Z", "2026-08-03T15:00Z", ...] }
   ```

   It should serialise all SimplePractice calls through one queue with the pacing
   rules above, cache results for a few minutes, and re-login by itself if the
   session expires. Bind it to 127.0.0.1 and require a token.

2. Matcher calls that endpoint and shows the next 3 slots next to each clinician in
   the filtered list.

3. A short SOP file telling me how to start the service, how to check it is healthy,
   and what to do if SimplePractice logs us out.

**Start by asking me anything you need, then build it step by step and show me it
working on real data before wiring it into the site.**

---

## Notes

- I already have this exact pattern working in my other project. If something is
  unclear, ask me and I can bring the working version over.
- On the machine where Mothership runs, the same idea is already a service called
  the "SP gateway" — if you want, I can copy that folder here as a starting point
  instead of writing it from scratch.
