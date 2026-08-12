# Live Availability — Troubleshooting & FAQ

## What this is

Live Availability shows each clinician's next open SimplePractice appointment times right on their card in the Clinician Matcher, so front-desk operators (FDOs) can see at a glance who's open and roughly when. The times come from MCW's **public** SimplePractice booking page — the same page any prospective client sees — with **no login and no patient data** involved. A small always-on service reads that page every ~10 minutes and saves the results; the Matcher page displays them and updates itself live. It's a fast shortlist to speed up your call — **not** a booking, a hold, or the final word.

---

## Is it live yet? / What to do right now

**Not on the real website yet.** Today the pieces run in three places: the data collector (the "gateway," always on in the cloud), the database that stores the times, and a copy of the Matcher page on a developer's machine. The whole chain was tested end-to-end on 2026-08-10 and works — but until the Matcher page is hosted somewhere your FDOs can open, staff can't use it day-to-day.

**The one habit that never fails you, now and after go-live:** the card points you fast to who's open and roughly when. **Always confirm the exact time live in SimplePractice at the moment you commit it to a caller, and book it in SimplePractice.** The card never books anything and can be a little behind.

---

## Front Desk FAQ

### Reading the card

**What is the green time on a clinician's card?**
It's that clinician's soonest open appointment time, pulled from SimplePractice's own online booking page. Green with a time (like "Today 2:00pm" or "Tomorrow 9:30am") means we found at least one opening. It's your quick starting point for what to offer a caller — not a locked, held slot.

**Is that green time really open right now?**
It was open the last time we checked (see the little grey "3m ago" next to it). It's our best recent read, not a live lock. Before you promise it to the caller, confirm it in SimplePractice — bookings can land in the seconds between our check and your call.

**What does "3m ago" (or "40s ago", "2h ago") mean?**
That's how long ago we last checked SimplePractice for that clinician's openings. It counts up on its own every 15 seconds — you don't need to refresh. Hover it and it says "When we last checked SimplePractice." Smaller number = fresher. A few seconds or minutes is very fresh.

**Is 20 minutes old too old to trust?**
20 minutes is the whole board's cutoff: if our checker hasn't succeeded in 20 minutes, every card flips to "Live times unavailable." So if you can still see green times at all, the board as a whole is under 20 minutes old. One individual card can still read older (some clinicians refresh on a slower cycle). Rule of thumb: anything more than a few minutes old is probably still right, but confirm in SimplePractice before you commit.

**What do "+2 more" and "show less" do?**
A card shows the first 4 openings to keep it readable. "+2 more" (or whatever the number is) expands it to show up to 12. "show less" collapses it back to 4. It only changes how many you see — it doesn't book anything.

**One clinician shows a single green time with an age, but no list of other times. Why just one?**
That's a normal in-between state: we know their soonest opening but haven't pulled their full list yet. Offer that one time if it fits, and check SimplePractice for what else they have. The fuller list usually fills in on its own shortly.

**How far ahead do the listed times go — is the last one on the list reliable?**
The list shows up to 12 upcoming openings, soonest first. The soonest one or two are the freshest and safest to offer. The later ones are more likely to have moved since we checked, so lean on the earliest openings and confirm any time in SimplePractice before committing.

### When something looks off

**It says "No openings listed" but I know this clinician has openings — why?**
That means SimplePractice's online booking page isn't showing any bookable openings for them right now. Common reasons: their openings aren't offered for online self-booking, they're fully booked online, or a schedule change hasn't published yet. If you believe they have room, check their actual calendar in SimplePractice — some openings exist that just aren't offered online.

**It says "Not bookable online" — what does that mean for this clinician?**
We have no online-booking availability for that clinician at all — SimplePractice's public booking page doesn't carry them. It does **not** mean they have no openings; it means their availability isn't published for online self-booking. To offer them, check their schedule directly in SimplePractice.

**A clinician I know is completely missing their live times — no green, nothing.**
A card with no availability row shows "Not bookable online," meaning we have nothing from the online booking page for them. Some clinicians are intentionally left off online booking (for example, Travis McNulty). If it's someone who should be bookable online, check them directly in SimplePractice and flag it — their online availability may not be published.

**The times look wrong, or like they're in the wrong timezone.**
All times on the card are **Eastern** (the practice's timezone), always — no matter where you or the caller are sitting. "Today 2:00pm" means 2:00pm Eastern. If a time still looks wrong after accounting for that, don't offer it; confirm in SimplePractice.

**I clicked a green time and nothing happened.**
That's expected right now — the times are display-only. They're there for you to read and offer, not to click or book. To actually book, do it in SimplePractice as usual.

**The times on a card changed while I was looking at it — is that a glitch?**
No. The board updates itself live, usually within a couple of seconds of a change, without any reload. If a time appeared, disappeared, or shifted, that's the card catching up to SimplePractice. Trust the newest view, and confirm before committing.

**A time I saw a second ago is now gone.**
Two harmless reasons: someone just booked it (it dropped off), or the list refreshed and re-sorted. Either way, offer the next open time and confirm live in SimplePractice. A vanished time means don't offer that one.

### The "unavailable" banner

**What does "Live times unavailable — check SimplePractice before offering a time" mean, and what do I do?**
It means our live-times checker hasn't reported a healthy result recently, so we're hiding times rather than risk showing you a stale one. Every card shows this at once when it happens. **What to do:** open SimplePractice and read availability straight from there for now. Nothing is broken on your end — the system is being cautious on purpose.

**Every card says "Live times unavailable" at the same time — is the whole system down?**
It means our times checker isn't reporting healthy right now, so the board hides all times as a safety measure — better a blank than a wrong time read to a caller. SimplePractice itself is unaffected: read and book availability directly there until the cards come back on their own.

### Getting it right on the call

**I offered a time and the caller said yes, but it turned out to be already taken. Why, and what do I do?**
SimplePractice doesn't notify us the instant a slot is booked, so there's always a small lag between a real booking and the time disappearing from the card. Someone booked it (online or another operator) in that gap. **What to do:** apologize, offer the next open time, and always confirm the slot live in SimplePractice at the moment you commit it. The card is a shortlist, not the final word.

**Am I seeing the same times as the coworker next to me?**
Yes. Everyone reads from the same shared live source, so two operators looking at the same clinician see the same openings at the same time. That also means two of you can offer the same slot at once — so confirm in SimplePractice before you commit, every time.

**Do I still need to open SimplePractice?**
Yes. The card speeds up finding who's open and roughly when, but it never books anything and can be a little behind. Always confirm and book the actual appointment in SimplePractice before you commit a time to a caller.

**Bottom line — how much should I trust the green times?**
Trust them to point you fast to who's open and roughly when. Don't treat them as a booking or a hold. The one habit that never fails you: confirm the exact time live in SimplePractice at the moment you commit it to the caller.

---

## Admin / Owner FAQ

**Is this live for my staff yet?**
Not yet. It runs in three places today: (1) the Fly gateway (app `mcw-sp-gateway`) — this IS live, always-on, and has been collecting data; (2) Supabase, which stores it; and (3) a local copy of the Matcher web page on a developer's machine, which is what displays the times. The piece your front-desk operators would actually open — the Matcher page on a real website — is not deployed yet. The whole chain was tested end-to-end on 2026-08-10 and works (a live change reached an open browser in about 2 seconds), but until the Matcher page is hosted somewhere your FDOs can reach, staff can't use it. Nothing is on the real site yet.

**Does it depend on my computer being on?**
No. The data collection runs entirely on Fly.io (app `mcw-sp-gateway`, in Ashburn/iad), always on, with no public internet address. If every computer in the office is off, the gateway keeps polling SimplePractice and writing to Supabase. The only thing currently tied to a local machine is the Matcher web page during development — and once that page is deployed to a real website, no office computer is needed at all.

**How fresh is the availability data really? Be honest.**
Treat it as "very recent," not "real-time." Two delays stack and there's a floor we can't go below. First, our polling: the roster sweep that checks all clinicians runs every 10 minutes. Second, SimplePractice's own cache lag: we read their freshness stamp (`sp_computed_at`) and their number can already be a few minutes old when we get it. SimplePractice offers no push/webhook, so the soonest a booking can disappear from a card is **poll interval + their cache lag** — always some minutes. One more wrinkle: if a booking takes a clinician's 3rd or 4th slot rather than their soonest, our cheap every-cycle sweep can't see it; it corrects on the next detailed refresh (up to about 2 hours, sooner if their soonest opening moved). That's why every card shows a grey "Xm ago" age label, and why the standing rule is: confirm the time in SimplePractice before you actually offer it.

**How much does it cost?**
A few dollars a month (~$5) for the always-on Fly machine, and $0 for Supabase on its free plan. Two things to watch on the free Supabase plan: it pauses a project after 7 days of no activity (a normal busy week keeps it awake, but a long office shutdown could trip it), and its live-update (Realtime) messages are quota-limited. Important cost note: the availability feature touches **no patient data** and needs no HIPAA add-on. There's a separate, not-yet-built reports feature that would read actual patient data — that one would add Fly's HIPAA/BAA compliance add-on at roughly $99/month — but that cost belongs to that future feature, not to availability.

**Is any patient data involved in the availability feature?**
No. It reads only MCW's **public** SimplePractice booking page (`mcnultycw.clientsecure.me/request`) — the exact same page any prospective client sees when they go to book. No login, no patient records, no protected health information on this lane. It's the public "next open appointment" information a stranger could already read by visiting your booking link. (The gateway is built to also run a separate, credentialed reports lane later, but that's a different feature and is not what powers these cards.)

**How do I know it's working, and how do I check?**
Three ways, easiest first. (1) On screen: each card shows a small grey age label like "3m ago" that ticks up every 15 seconds. Small, moving numbers mean data is flowing. If every card instead reads "Live times unavailable — check SimplePractice before offering a time," the feed has gone stale and the app has safely blanked itself. (2) In the database: open the `gateway_health` table in Supabase — `last_ok_at` is the last successful run, `last_status` should say `ok`, and `consecutive_failures` should be 0. (3) In the logs: run `fly logs --app mcw-sp-gateway`; every line is `key='value'` and `status='ok'` is healthy. `fly status --app mcw-sp-gateway` confirms the machine is running. You'll never see a client name in those logs — the logger is built so it cannot print one. (See the 60-second health check below.)

**What happens if it breaks while I'm asleep?**
It fails safe. If the gateway stops or starts failing, then within 20 minutes (or after 3 failures in a row) every clinician card automatically flips to "Live times unavailable — check SimplePractice before offering a time." Your FDOs simply fall back to checking SimplePractice directly, which is the safe default anyway. The specific danger this design guards against is **silent staleness** — the screen confidently showing three-week-old times because nobody noticed the job stopped — and that's exactly what the freshness check prevents. The honest gap: nothing pages you automatically today. Whoever opens the Matcher next sees the safe "unavailable" message, but nobody gets a 3am text. If you want an automatic alert, that's a small piece we'd need to add.

**How often will it break?**
Roughly every few months. The gateway relies on an undocumented SimplePractice booking interface that they can change without warning. When they change it, the feed stops and cards drop to the safe "unavailable" state — this is expected and planned for, not a sign something deeper is wrong. A restart (`fly machine restart --app mcw-sp-gateway`) fixes a transient hang, but a page-structure change needs a small code update to match SimplePractice's new page. Budget for a short developer touch a few times a year.

**A new clinician joined, or one left — what do I do?**
It's a tiny mapping edit, but it needs a developer today (not self-service yet). Each SimplePractice clinician (`sp_clinician_id`) is hand-linked to a row in your `clinicians` table (`clinician_id`). When a new clinician appears on the public booking page, the gateway picks up their availability automatically — but their card won't connect to a Matcher profile until someone adds that one mapping row. When a clinician leaves and drops off the booking page, their row simply stops updating. Concrete precedent: 32 of 33 clinicians are mapped, and Travis McNulty (SimplePractice id 1065521) is intentionally left unmapped. So the action is: tell the developer the new clinician's name, and they add one mapping row.

**Can my staff book or accidentally change anything from these cards?**
No. The time chips are display-only text, not buttons — an FDO cannot click a time to book it — and the Matcher only ever reads the availability data; it never writes back to SimplePractice. Two real limitations to know about: there's no commit-check that re-verifies a slot at the exact moment an FDO offers it, and no soft-hold to stop two FDOs from offering the same open time to two different clients at once. Until those exist, the rule holds: confirm the time in SimplePractice before you promise it to anyone.

**When can we put it on the real website, and what happens then?**
The gateway and database are already production-ready and running; the remaining work is hosting the Matcher page on a site your FDOs open instead of a developer's machine. Once it's live: (1) staff get live times without any office computer being on; (2) more browsers reading Supabase's live updates uses more of the free-plan message quota — worth watching, and it's the natural trigger to consider a paid Supabase tier; and (3) the honesty rules stay on — the "Xm ago" age label and the "check SimplePractice before offering a time" guard don't go away, because the freshness floor doesn't change. Before go-live I'd recommend two things: add an automatic alert so a breakage reaches a human without waiting for someone to open the page, and decide whether the Supabase free plan's quotas and 7-day-pause risk are acceptable for a customer-facing tool or whether to move to the paid tier.

---

## 60-second health check

Run this whenever you want to confirm the feature is alive. **PASS = fresh `last_ok_at` + green chips on cards + recent `selected`/`fetched` log lines.**

**1. (0–15s) Check the freshness stamp in Supabase.**
Supabase Table Editor (project ref `gazzhqtqnmpyjejwujei`) → `gateway_health` table → the row where `feed = 'clinician_availability'`. Confirm `last_ok_at` is within the last ~10–20 minutes and `consecutive_failures = 0`, with `last_status = ok`. This one field is the whole health signal: if it's fresh, the feature is live.

**2. (15–35s) Look at the Matcher on screen.**
Confirm cards show green time chips with a grey "Nm ago" age label — **not** the banner "Live times unavailable — check SimplePractice before offering a time" on every card. A few "No openings listed" / "Not bookable online" cards are normal.

**3. (35–60s) Check the gateway logs.**

```bash
fly logs --app mcw-sp-gateway
```

Confirm recent (last ~10 min) lines like:

```
step='slots' status='selected' count=<n> rows=<n>
step='slots' status='fetched' count=<n>
```

and **no** repeating `status='request_failed'`, `status='non_200'`, or `reason='headers_not_captured'`.

> **Normal, not a fault:** `step='availability' status='networkidle_timeout'` prints most cycles by design (the booking page keeps analytics sockets open and never goes idle) — ignore it. Times rendering in Eastern on a non-Eastern machine is also correct.

### When it breaks — the 3 commands

Run these from `D:\Clinican Modeliaitlities\sp-gateway` in PowerShell:

```bash
fly logs --app mcw-sp-gateway              # what happened
fly status --app mcw-sp-gateway            # is it running
fly machine restart --app mcw-sp-gateway   # the usual fix
```

A machine restart is the usual fix for a transient hang. If the empty-harvest error (`note='empty_harvest'`, or the log "the booking page shape has probably changed") persists **after** a restart, SimplePractice changed their undocumented booking API and the feed's markers/selectors in `availability.py` need a small developer update. Expect this roughly every few months.

**Unhealthy signals to act on:** `last_ok_at` older than 20 minutes, OR `consecutive_failures` ≥ 3, OR the "Live times unavailable" banner on **every** card, OR repeating failure log lines. Any one of these → go to the 3 commands above.

---

## Bug scenarios

Sorted most-likely first. **Safe** = the card blanks to "Live times unavailable" or hides the time (no wrong time shown). **Wrong** = the card can show a bad/stale time as if it were fresh — this is where the "confirm in SimplePractice" habit saves you.

| # | Trigger | What you see | Safe or Wrong | How to spot it | Fix |
|---|---------|--------------|:---:|----------------|-----|
| 1 | A slot is booked (online or by another FDO) and offered again before the next detailed refresh. Chips are display-only, with no commit-check or soft-hold. | Two FDOs read the same chip aloud, or one offers a slot taken minutes ago. Chip still shows the taken time with no warning. | **Wrong** | No automated cue. The grey age label shows how old the list is; the only ground truth is opening SimplePractice. | Add a Phase-2 commit-check (re-fetch that clinician's slots when an FDO clicks to offer) plus a short soft-hold row. Until then, keep the "check SimplePractice before offering" habit. |
| 2 | A booking removes a clinician's 3rd/4th opening, not their soonest. The cheap sweep only sees the soonest, so it doesn't flag them; their stale list lingers up to ~2h. | First chip is correct, but a later chip behind "+N more" is an already-booked time. Age label may read up to "2h ago." | **Wrong** | The grey age label on that card growing toward 2h. No log fires — it's a correct-by-design skip. | Lower `SLOT_MAX_AGE` or raise `MAX_DETAIL_PER_CYCLE` so the rotating sweep covers everyone faster; or add a per-clinician slot-count check to the cheap sweep. |
| 3 | **Root-cause gap:** trust is judged globally (whole feed healthy or not) and per-card age uses our fetch time, not SimplePractice's own freshness stamp (`sp_computed_at`). A card's own data can be stale while the feed overall is healthy. | A card whose individual data is frozen/skipped/lagged renders as fully trusted with a reassuring small age label. Displayed age understates true staleness by SP's cache lag. | **Wrong** | Compare a row's `fetched_at` against the newest row's `fetched_at`, and `now − sp_computed_at`, in the DB. The UI surfaces neither. This underlies scenarios 2, 4, 8, 9. | Make the card trust per-row freshness: treat a row whose `fetched_at` lags the newest (or whose `sp_computed_at` is old) as untrustworthy, and show `sp_computed_at` age. |
| 4 | A clinician is **removed** from SimplePractice and drops off the roster. There's no delete/reap path, so their old row is never touched or cleaned up. | ~~Card keeps showing frozen green chips as if live.~~ **FIXED 2026-08-10:** their card now shows "Not bookable online" instead. | **Safe** ✅ | Their row's `fetched_at` stops advancing while every other row advances each cycle. | **Done.** The card now checks each row's own `fetched_at` against the feed's last success (`rowIsCurrent`, margin 45 min): a row that has fallen behind is treated as departed and blanked to the safe state. |
| 5 | A single clinician's detailed slots call fails (non-200 or throws). The code logs and skips, deliberately leaving their previous slot list in place. | That one clinician keeps their previous (possibly stale) slot list while their soonest-time chip still refreshes. Everyone else is fine. | **Wrong** | Log `slots status='non_200'` or `request_failed`; that clinician's `slots_fetched_at` lags. Re-selected next cycle, so it self-heals. | Tolerable for a transient blip. If a clinician fails repeatedly, clear their stale slots so they fall back to the single soonest-time chip instead of an old list. |
| 6 | The detailed call returns 200 but **zero** spots for a clinician who had some (all booked between sweeps). The list is correctly emptied, but the earlier soonest-time value may still be set. | The multi-chip list correctly disappears (good), but a single fallback chip may still show a soonest time the same-cycle check already found empty. | **Mixed** | A row with empty slots but a non-null soonest time, both stamped this cycle. Self-heals next cycle. | When slots come back empty, also treat the soonest-time value as suspect that cycle — suppress the fallback chip or show "No openings listed." |
| 7 | An FDO leaves the tab open and idle while the live connection is dead. | ~~Chips linger past the 20-min cutoff on an idle tab.~~ **FIXED 2026-08-10:** the tab now blanks itself within 15s of crossing the cutoff, no click needed. | **Safe** ✅ | Was: age label exceeding 20m with chips still shown. Now self-corrects. | **Done.** The 15-second age ticker now also re-checks trust and repaints when the verdict flips, so an idle tab enforces the 20-min cutoff on its own. |
| 8 | The gateway process dies or the Fly machine is stopped, so it stops writing entirely. | After 20 min all cards show "Live times unavailable" — now including idle tabs (see #7). | **Safe** ✅ | `gateway_health.last_ok_at` stops advancing; `fly status` shows the machine stopped. | Idle-blank now covered (#7). Still a good future add: a Fly health-check auto-restart and an external alert when `last_ok_at` ages past 20 min (nobody is paged today). |
| 9 | The api-version header capture fails one cycle, so the detailed pass is skipped. Clinicians who already had a list keep it untouched; only never-listed clinicians show the single fallback chip. | Clinicians with an existing list keep showing that **stale** "+N more" list with an aging label. Others show just the single soonest-time chip. | **Wrong** | Log `slots status='skipped' reason='headers_not_captured'`; `slots_fetched_at` stops advancing while `fetched_at` keeps advancing. | Broaden the header capture (more request types, or capture from the slots/next-slots request), or reuse the previous run's headers instead of skipping. |
| 10 | A clinician is **added** in SimplePractice with no hand-mapped `clinician_id`. Their availability is written but the Matcher skips rows with no mapping. | That clinician's live times are simply missing from the Matcher. **No wrong time is ever shown** — just absent data. (Same by-design path as Travis McNulty.) | **Safe** | A `clinician_availability` row with `clinician_id` NULL and a populated `sp_name`. | Add the `sp_clinician_id → clinician_id` mapping row (and a `clinicians`-table entry if needed). One developer edit. |
| 11 | The health counter that should count consecutive failures was never incremented on failure. The "≥ 3 failures" guard was dead code. | ~~Fast-fail guard never fires; only the 20-min rule blanks cards.~~ **FIXED 2026-08-10:** the counter now increments on each failure. | **Safe** ✅ | `gateway_health.consecutive_failures` now climbs during an outage. | **Done.** `record_health` reads the current count and increments it on failure, so the guard fires. The 20-min staleness rule remains the primary safety net. |
| 12 | The live (Realtime) connection drops or hits its free-plan quota. Live push stops; the screen holds its last state. | Updates stop arriving. On reconnect it re-fetches and recovers. If it never reconnects, staleness only blanks the cards if a render is triggered (see #7). | **Safe** | Console shows the channel error/timeout; updates stop arriving in ~2s and resume after reconnect. | Recovery is built in; pair with the idle-render fix (#7) so staleness self-enforces without waiting for a reconnect. |
| 13 | Supabase project paused (free-tier 7-day idle) or otherwise unreachable. | Every card shows "Live times unavailable." The roster still loads; only the times degrade. | **Safe** | Gateway logs a Supabase error; browser shows 4xx/5xx from `*.supabase.co`. Because the gateway writes every 10 min it won't idle-pause, so a pause implies the gateway is also down. | Upgrade off the free plan for always-on, or add a keep-alive ping. The UI already degrades safely. |
| 14 | SimplePractice changes the booking page/API shape so nothing parses. The feed records a failed run and raises. | After 20 min all cards show the safe "Live times unavailable" state — and it holds even for idle tabs, because a failed-health row is written every cycle and forces a re-render. | **Safe** | Log `empty_harvest` then `breaker_open reason=repeated_failure`; `last_status='failed'`. (A lone `networkidle_timeout` is normal, not this.) | Update the response markers/parse in `availability.py` to the vendor's new page shape. Expected roughly every few months. |

---

## Known limits we accept

- **No push from SimplePractice.** There's no webhook, so there's always a delay between a real booking and the slot disappearing — our poll interval (~10 min) plus SimplePractice's own cache lag. We observe that lag but can't remove it.
- **Chips are display-only.** No commit-check re-verifies a slot at the moment an FDO offers it, and no soft-hold stops two FDOs from offering the same time. The standing rule — confirm in SimplePractice before you commit — is what covers this.
- **Deeper bookings correct slowly.** If a booking takes a clinician's 3rd/4th slot instead of their soonest, the cheap every-cycle sweep can't see it; it corrects on the next detailed refresh (up to ~2h, sooner if their soonest opening moved).
- **Per-card freshness isn't surfaced.** Trust is judged for the whole feed, and the age label uses our fetch time, not SimplePractice's own freshness stamp — so an individually stale card can look fresh while the feed overall is healthy.
- **No automatic alert yet.** Breakages fail safe (cards blank), but nobody gets paged — the next person to open the Matcher sees the safe "unavailable" state. An external alert is a small future add.
- **New clinicians need a developer.** Mapping a newly-added clinician to their Matcher card is a one-row edit, not self-service today. (A *removed* clinician now self-blanks — see bug #4.)
- **Free-plan caveats.** Supabase free pauses a project after 7 days of no activity and quota-limits live-update messages — worth revisiting before go-live and as more browsers connect.
- **Undocumented dependency.** The gateway relies on an undocumented SimplePractice booking API that can change without notice — budget for a short developer touch a few times a year.
- **Not on the live site yet.** Today this is local Matcher + Fly gateway + Supabase. Staff can't use it until the Matcher page is hosted.