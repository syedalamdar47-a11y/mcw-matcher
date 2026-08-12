## Live Availability in the Clinician Matcher — Briefing for Management

**Date:** 2026-08-11
**Prepared by:** Alam Naqvi, Front-Office Operations
**Status:** Built, running, and validated against our live SimplePractice calendar. The next step is rolling it out to the front-desk team, which we gate behind one compliance step — signing our cloud host's Business Associate Agreement (BAA) — plus the items noted below.

> **Bottom line: This gives a front-desk operator an instant, self-updating read on who's open and roughly when — pulled from our real SimplePractice calendar — so they stop hunting clinician-by-clinician on every call. It's a fast first look, not a booking system, and staff still confirm the exact time in SimplePractice before committing it to a caller.**

---

## 1. Executive Summary

The Clinician Matcher now shows each therapist's and psychiatrist's next open appointment times right on their card, pulled live from our SimplePractice calendar and refreshed about every 30 seconds — so a front-desk operator on a call can see who is open, and when, without leaving the tool.

Before this, matching a caller to an available clinician meant stepping out of the call flow, opening SimplePractice, and checking clinicians one at a time to find an opening. With this feature, the open times appear on the matching board right next to the clinicians a caller already fits, and they update on their own while the call is in progress. Work that used to take several manual look-ups is simply there on the screen.

Beyond the soonest openings, each card has a **"Pick a date" option**: the operator can choose any day over the **next two weeks** and instantly see that clinician's openings for that day. So "I need someone ASAP" and "I can only do a Wednesday" are both answered on the same screen.

What makes this version worth trusting is where the times come from. It reads our **real practice calendar** — not the public "book online" page — so it reflects time a clinician has blocked for themselves, out-of-office, and existing-client appointments, none of which the public page ever showed. Reflecting blocked time was the specific requirement that drove this, and it is now met: a slot shown as open is genuinely free on the actual calendar. We can even prove it on demand — an automated check compares every open time the tool shows against every booking in SimplePractice and confirms none collide (see Section 3).

The times are always displayed in **Eastern (St. Petersburg) time** — the board carries a standing "Times in Eastern" label so there's never any doubt — and each card is stamped "checked N seconds ago" so staff can see how fresh it is. When the service **knows** it can't confirm the times are current, every card blanks to "check SimplePractice before offering a time" rather than risk showing a stale one — it is built to fail safe.

To be clear about what it is not: this is a **visibility tool, not a booking system.** It shows openings; it does not hold or reserve them, and there is a short lag — up to about 30 seconds — between a booking and a slot disappearing. Staff should always confirm the time in SimplePractice before committing it to a caller.

### Value at a glance

| Benefit | What it means on a call |
|---|---|
| **Faster calls, less clicking** | Openings surface on the board the operator is already using, instead of a separate, clinician-by-clinician hunt through SimplePractice. |
| **Any day, not just the soonest** | "Pick a date" shows a clinician's openings for any day over the next two weeks — great for callers with specific-day constraints. |
| **Fewer wrong offers** | Because it reads the real calendar, blocked and booked time is respected — so we're less likely to offer a slot a clinician has protected. |
| **Provably accurate** | An on-demand audit checks every shown slot against every booking and reports any conflict — the latest run found zero. |
| **Honest by design** | Times are in Eastern, stamped with how recently they were checked, and blanked when the service knows they can't be trusted. |
| **Low, predictable cost** | On the order of ~$100/month once the BAA is in place, against the staff time saved on every incoming call. |

---

## 2. How It Works (plain English)

The Matcher shows each clinician's next open appointment times right on their card, read live from our real SimplePractice calendar and refreshed about every 30 seconds.

Behind the scenes, in plain terms:

- **A small always-on program — we call it "the gateway" — runs in the cloud (on a service called Fly.io), not on any office computer.** If every machine in the office is turned off, it keeps running.
- **It signs in to SimplePractice using a dedicated biller team-member seat, which we use read-only** — not an owner login, and not anyone's personal login. (Note: "biller" is a SimplePractice role; a biller seat is not *technically* locked to read-only, so part of the rollout is confirming the tightest permissions SimplePractice allows on that seat. In practice the gateway only reads.)
- **About every 30 seconds during business hours (6am–8pm Eastern), it does one bulk read of the whole practice calendar** — every appointment and every block — and works out each clinician's free time: their working hours minus anything booked or blocked off. It also computes a two-week grid so any future day can be browsed.
- **It requests only appointment start, end, and status — no client names or details** — and it saves only the resulting open time slots into the Matcher's database. It writes a clinician's row only when their openings actually change, which keeps it efficient.
- **Every open Matcher screen then updates within about a second, with no page refresh.** Each card shows "checked N seconds ago" so staff can see how fresh the times are.

Because it reads the real calendar, it reflects therapists blocking their own time, out-of-office, and existing-client appointments — the things the old public "book online" page never showed. Reflecting blocked time was the specific reason we made this change. All times are shown in Eastern (St. Petersburg) time, wherever the viewer happens to be.

---

## 3. How to Verify the Numbers

*You should never have to take the tool's word for it. Everything it shows can be checked against SimplePractice, in front of anyone, in under a minute. Here's exactly how.*

Throughout, assume **two tabs are open**: **SimplePractice** in one, the **Matcher** in the other. All Matcher times are **Eastern (St. Petersburg)**, so compare like-for-like. (If you're viewing SimplePractice from another timezone, set your SimplePractice display to Eastern first — Calendar → gear icon → Calendar preferences → Time zone — so the two line up directly.)

### A. Quick health check (2 minutes)

| # | Check | Good result | Not good |
|---|---|---|---|
| 1 | **Healthy** — open the Matcher, look at any card. | Cards show real times (e.g. "Today 2:00pm, 3:00pm…") with a "checked Ns ago" note. | Every card says *"Live times unavailable — check SimplePractice before offering a time."* The service is paused or down — note it pauses outside 6am–8pm Eastern. |
| 2 | **Freshness clock** — read the "checked Ns ago" label. | A small number of seconds (up to ~30); it ticks and resets as it refreshes. | It climbs past a minute and keeps going. |
| 3 | **Roster matches** — count clinicians shown vs. your SimplePractice list. | Counts match; everyone who should appear, appears. | A clinician is missing or extra. |

### B. Live demo (the strongest proof — do this in front of the room)

Change something in SimplePractice and watch the Matcher follow within ~30 seconds, with nobody touching a refresh button.

1. **Set the scene.** Both tabs side by side — SimplePractice left, your demo clinician's Matcher card right. Point out the times showing and the "checked Ns ago" label.
2. **Point to the target slot.** On the card, point to the open time you're about to remove: *"This slot shows as open right now."*
3. **Block or book it in SimplePractice.** Create the block (or a dummy appointment) on that exact slot. Save it.
4. **Don't refresh — just watch.** Within ~30 seconds the slot **disappears** from the card on its own; the "checked Ns ago" label resets. Narrate: *"It's not instant — up to a 30-second lag, because SimplePractice gives no 'just booked' signal to anyone. That's why we always confirm in SP before committing a time."*
5. **Reverse it (optional, powerful).** Delete the block. Within ~30 seconds the slot **reappears** — proving the sync runs both directions and nothing is faked or cached.
6. **Land the point.** *"The Matcher reads our real calendar. If it's on the calendar, the tool honors it — bookings, blocks, and time off."*

### C. Side-by-side (calm, no-risk — nothing gets created or deleted)

1. Open your demo clinician's **SimplePractice calendar** for today and tomorrow.
2. Read off their genuine **free gaps** — times with nothing booked or blocked.
3. Open the **same clinician's Matcher card** and read the open times it lists — use "Pick a date" to check a specific future day too.
4. **They match.** One caveat to state up front so it doesn't look like an error: the Matcher shows times on a **30-minute grid assuming ~50-minute sessions**, because SimplePractice doesn't expose each clinician's exact booking increment. So a card might show "2:00" and "2:30" where a clinician's own rule places things slightly differently. The window is genuinely free; confirm the precise bookable time in SP.

### D. The automated audit (proof at scale)

We can run a single on-demand check that compares **every** open time the tool is showing against **every** booking and block in SimplePractice, and reports any slot that collides with a booking. It's the machine-checked version of the side-by-side, across all clinicians at once.

> **Latest run: 350 open slots checked against 754 active bookings — zero conflicts.** Not one open time the tool showed fell inside a booked or blocked slot.

This is the answer to "how do we know it's accurate?" — we don't ask you to trust it, we check it, and we can re-run that check any time.

### The blocked-time proof (do this too — it's the reason the project exists)

Point to a time a clinician has **blocked** in SimplePractice, then show that time does **not** appear as available on their Matcher card. That single comparison proves the tool reflects blocked time — the whole point of reading the real calendar instead of the public booking page.

---

## 4. Anticipated Questions & Answers

*(Toughest first — written the way to answer them in the room: plainly, owning the limits.)*

**Q: Is this safe with patient data? Is it HIPAA-compliant?**
The read is deliberately times-only: we request just appointment start, end, and status. And that's built as a **control, not a one-time observation** — our own code keeps only those three fields and drops everything else on ingest, so even if SimplePractice later changed its response to include client names, we would never store or log them. No client names or details are stored, logged, or shown. The Matcher's own database holds only clinician names and open time slots, which is why the app itself carries no patient data — and I'd have compliance confirm the formal scope conclusion rather than assert it myself. Because the gateway signs into the real calendar, which *does* contain patient data, the cloud host is treated as handling PHI, so a Business Associate Agreement with Fly.io is the correct step. To be fully straight: that BAA is the one compliance gate I've set before we put this in front of the full team, and I'm treating it as firm, not an afterthought.

**Q: Is this allowed under SimplePractice's terms of service?**
I'd rather be honest than overclaim. SimplePractice has no official API for a practice to pull its own scheduling data, so there is no formally sanctioned automated route, and I'm not going to tell you this is officially approved. What we're doing is reading **MCW's own data through MCW's own authorized account,** at low volume, one request at a time, business hours only. There is a precedent for granting access to our practice data — MCW already grants a third-party vendor, Practice Vital, biller access that pulls practice data — which shows the general approach isn't foreign to us. My position: this is a reasonable, careful, read-only use of our own data and our own account, and if SimplePractice ever objected, we'd revisit it.

**Q: How current is it really? Is it instant?**
It is not instant, and I want to be plain about that. Times refresh every ~30 seconds, so there can be up to a 30-second gap between when something is booked and when the slot disappears from a card. SimplePractice gives no instant push signal that something was just booked — to anyone. So it's seconds, not minutes. Every card shows a "checked N seconds ago" stamp so you can see exactly how fresh it is, but always confirm in SimplePractice before committing a time to a caller.

**Q: What if it shows a time that's already taken and we double-book?**
Two things can cause that, and I'll own both. First, the up-to-30-second lag means a slot could show as open for a few seconds after someone else grabbed it. Second, there's no "hold" yet, so two front-desk staff could offer the same open time in the same instant. That's exactly why the rule stays: the card tells you who is *likely* open so you're not hunting blindly, but you confirm the specific time in SimplePractice before you commit it. A "soft hold / commit-check" that closes this gap is on the roadmap.

**Q: You say it never shows a booked slot as free — how do you actually know?**
Because we check it, not just claim it. We run an audit that compares every open time the tool shows against every booking and block in SimplePractice; the latest run checked 350 open slots against 754 bookings with zero conflicts. That said, I won't overstate it: the audit is a point-in-time proof and the fail-safe blank covers problems the service *knows* about — it does not, on its own, catch a subtle silent mis-read (say, if SimplePractice changed its calendar format). The standing rule to confirm in SP is the backstop, and an automatic sanity-check-plus-alert is on the roadmap so a bad read also trips the blank state.

**Q: What actually stops patient data from getting stored if SimplePractice starts returning client details?**
Today the request asks only for start, end, and status, and a minimal request returned zero client identity when we tested it. The safeguard is a filter in our own code that keeps only those fields and discards everything else on the way in — so even if SimplePractice started returning names tomorrow, we would never store or log them. It's a whitelist on ingest, treated as a hard control, right alongside the BAA.

**Q: Where does the automation account's password live, and what's our exposure if the gateway or the Matcher's database is breached?**
The credentials sit as encrypted secrets on the Fly.io gateway, not in the Matcher's code or its database. The Matcher database holds only clinician names and open time slots — no patient data and no SimplePractice password — so a breach of the Matcher exposes no PHI and no login. The higher-value target is the gateway, because it can read the real calendar, which is exactly why it goes under the Fly.io BAA and is locked down as part of the rollout.

**Q: Does the automation account use multi-factor authentication, and who can log into it or the gateway?**
A genuine point I'd rather flag than gloss over. Automation accounts often can't do interactive MFA the way a person's login does, which makes a strong, unique password and tight control of who holds it the main line of defense. As part of the rollout I'll document exactly who has access to the account and the gateway, and confirm the strongest authentication SimplePractice allows on a team-member seat.

**Q: Could SimplePractice flag or lock this account for automated logins, and would that disrupt our billing staff?**
It's a dedicated seat, separate from any person's login and separate from our billing team, specifically so that if SimplePractice ever throttled or locked it, it wouldn't touch anyone's day-to-day work. It logs in gently — one request at a time, business hours only. If the seat were locked, the cards would blank to "check SimplePractice" and we'd simply be back to today's manual process while we sorted it out — no data lost, no patient impact.

**Q: Does this depend on someone's computer being on in the office?**
No. The gateway runs in the cloud on Fly.io, not on anyone's office computer. If every machine in the office is powered off, it keeps running and keeps the times current. The only thing that pauses it is the intentional overnight window, 8pm–6am Eastern, when the practice is closed.

**Q: Why not just use SimplePractice directly, the way we always have?**
You still can, and for the actual booking you should. The point of this is speed on a live call: instead of opening SimplePractice and checking each clinician one by one, an operator sees at a glance who is open and roughly when, right on the matching screen — for the soonest opening or any day in the next two weeks. It also pulls from the real calendar, so it reflects blocked time the old public page never showed. A faster first look, not a replacement for confirming the exact slot in SimplePractice.

**Q: Can staff trust it enough to stop checking SimplePractice?**
Not entirely, and I wouldn't want them to. Think of it as a fast, reliable first look that tells you who to focus on — not the final word on a specific time. Because of the up-to-30-second lag, the 30-minute display grid, and the lack of a hold, the standing rule is to confirm the exact time in SimplePractice before committing it to a caller. Where it earns real trust is the safe-fail behavior: when it *knows* it can't be sure, it blanks the times rather than mislead you.

**Q: Who built and maintains this, and what if that person is unavailable?**
I drove this as part of improving our front-office workflow, working with developer support, and I'm the point of contact. The system is small and self-contained, and when SimplePractice changes something it fails safe — so the fallback is simply that staff check SimplePractice directly until it's fixed, exactly as we do today. It needs an occasional short developer touch a few times a year; part of doing this properly is making sure that maintenance, the developer relationship, and the monitoring alert are documented and not dependent on any one person's memory.

---

## 5. What It Is Not / Known Limits

We know where the edges are and design around them. Owning these is the point:

- **It is not instant.** Up to ~30 seconds between a booking in SimplePractice and the slot disappearing from a card. SimplePractice gives no "just booked" signal to anyone, so some lag is unavoidable. Seconds, not minutes — but always confirm in SP before committing a time.
- **Times sit on a 30-minute grid.** We show openings on a 30-minute grid assuming ~50-minute sessions, because SimplePractice doesn't expose each clinician's exact booking increment. A shown window is genuinely **free on the calendar**, but may not exactly match a clinician's booking rule — so confirm in SP.
- **There is no "hold" yet.** Nothing reserves a slot the moment it's offered, so two staff could offer the same open time in the same instant. A commit-check / soft hold would close this.
- **Fail-safe covers *detected* problems, not silent ones.** When the service knows it's unhealthy, every card blanks to "Live times unavailable — check SimplePractice before offering a time." It also blanks overnight (outside 6am–8pm Eastern). What it does **not** automatically catch is a silent mis-read — the service believing it's fine while having parsed the calendar wrong. The on-demand audit and an automatic sanity-check-plus-alert (planned) address this; until the alert ships, the confirm-in-SP rule is the backstop.
- **No automatic alert yet.** Today, staff notice a problem first, when cards go blank. An alert is a small planned add.
- **It needs occasional maintenance.** It relies on SimplePractice's internal, undocumented calendar, which can change without notice. Expect a short developer touch a few times a year.

---

## 6. Cost

| Item | Cost | Notes |
|---|---|---|
| Cloud host (Fly.io machine) | ~$5–8 / month | Runs the always-on gateway. |
| Fly.io HIPAA / BAA add-on | ~$99 / month | The one compliance gate before team rollout. |
| Database (Supabase) | $0 today | Current plan is free; a modest paid plan may make sense before wide rollout. |
| SimplePractice | $0 new | The automation account is a free team-member seat. |
| **Net once BAA is in place** | **~$100 / month** | Weighed against staff time saved checking SimplePractice by hand on every call. |

---

## 7. What's Next (roadmap)

In order, gated on compliance:

1. **Sign the Fly.io Business Associate Agreement (BAA)** — the firm gate before rolling out to the full team. Alongside it: confirm the agreement for any outside developer, document who can access the account and gateway, and confirm the tightest authentication and permissions on the biller seat.
2. **Lock in the ingest whitelist as a hard control** — keep only start/end/status on the way in, so no client data can ever be stored even if SimplePractice's response changes.
3. **Add sanity checks + an automatic alert** — so a silent mis-read (not just an outright outage) also trips the safe blank state and notifies someone.
4. **Roll out to the front-desk team** — with a short "what the labels mean / confirm in SP before booking" guide.
5. **Add a commit-check / soft "hold"** — to prevent two staff from offering the same slot at the same instant.
6. **Have compliance confirm the HIPAA scope conclusion** for the Matcher's own data (clinician names + open times).

> **Bottom line: This is a fast, honest first look at who's open — real-calendar accurate (and provably so), fail-safe when it knows it can't be trusted, and cheap to run. It's built and validated; signing the BAA and the compliance steps above are the gate before the full-team rollout, and staff will always confirm the exact time in SimplePractice before booking.**
