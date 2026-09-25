# SimplePractice Gateway

One always-online, **read-only** connection to SimplePractice that other MCW projects
read from — so we never build SimplePractice access twice.

It runs on Fly.io, not on anyone's desktop. If every computer in the office is off,
it keeps running.

---

## The rules it operates under

These are enforced in code, not by good intentions. Each exists because breaking it
has a specific consequence.

| Rule | Where | Why |
|---|---|---|
| Only GET/HEAD to SimplePractice | `safety.assert_read_only` | It holds live clinical records. A stray write could alter a real chart. |
| Only SimplePractice hosts for data | `session._host_allowed` | Stops a redirect sending the session somewhere else. |
| One request at a time, 0.7–1.8s apart | `safety.Pacer` | Looks like a person. The lock is held across the sleep, so parallel use is impossible, not merely discouraged. |
| Hard request ceiling per run | `safety.RequestBudget` | A loop bug becomes a stop, not thousands of requests against the practice's own vendor. |
| Exactly one sign-in attempt | `safety.LoginAttemptGuard` | SimplePractice locks an account after five failures. There is no retry path. |
| Nothing client-level to disk | `session._NO_DISK_CACHE_ARGS` | Chromium caches fetched pages by default. That would be patient data at rest, written by no line of our code. |
| Nothing client-level to logs | `safety.log` / `log_exception` | The only sanctioned stdout path. Allow-lists keys, masks name/email/phone/DOB shapes, and never prints a traceback — tracebacks render locals, and locals hold page content. |
| Session encrypted at rest | `session.save_state` | The saved cookie *is* the account until it expires. |
| One process holds the session | `session.exclusive_session_lock` + the Fly volume | Two concurrent sign-ins is how an account gets flagged. |

**Credentials.** `SP_Email` / `SP_Password` live in `.env.local` locally (gitignored) and
in Fly secrets in production. They are never written anywhere else, never logged, and
`config.Secret` makes them print as `<Secret ****>` even inside an f-string.

---

## First deploy

Run these from `D:\Clinican Modeliaitlities\sp-gateway` in PowerShell.

**1. Install flyctl** (not currently installed on this machine)

```powershell
iwr https://fly.io/install.ps1 -useb | iex
```

Close and reopen PowerShell afterwards so it lands on your PATH.

**2. Sign in and create the app**

```powershell
fly auth login
fly apps create mcw-sp-gateway
```

**3. Enable the HIPAA / Compliance add-on and sign the BAA — do this BEFORE anything logs in.**

This is in the Fly dashboard under your organisation's settings (~$99/month).
The obligation starts the moment a machine first holds a credential that can reach
patient data, not at go-live. Do not skip ahead of it.

**4. Create the volume for the encrypted session**

```powershell
fly volumes create sp_gateway_state --app mcw-sp-gateway --region iad --size 1 --yes
```

**5. Push the secrets** (reads `.env.local`, prints names only, never values)

```powershell
.\deploy\set-secrets.ps1
```

**6. Give it a stable outbound address**

```powershell
fly ips allocate-v4 --app mcw-sp-gateway
```

A consistent source IP looks like one ordinary machine rather than a rotating swarm.

**7. Deploy**

```powershell
fly deploy --app mcw-sp-gateway --remote-only
```

`--remote-only` builds on Fly's builders, so Docker is not needed locally.

---

## The first sign-in — do this supervised

Have the biller account's inbox open on screen while you run it. If SimplePractice
sends a device-verification email, you want to see it arrive in real time.

```powershell
fly ssh console --app mcw-sp-gateway -C "python check_login.py --signin"
```

| Output | What it means | What to do |
|---|---|---|
| `status='ok'` | Signed in, session saved encrypted | Nothing — tell me and I'll build the report feeds |
| `status='challenged'` | A device/step-up check fired | Check that inbox and tell me exactly what arrived |
| `status='failed'` | Credentials or page-structure problem | **Do not re-run.** Send me the output first — you have five attempts before lockout |

To inspect the sign-in page structure without spending an attempt (safe any time,
submits nothing):

```powershell
fly ssh console --app mcw-sp-gateway -C "python check_login.py --probe"
```

---

## When it breaks

It will, roughly every few months — SimplePractice changes their pages without notice.
That is expected and budgeted for, not a sign something is wrong.

```powershell
fly logs --app mcw-sp-gateway          # what happened
fly status --app mcw-sp-gateway        # is it running
fly machine restart --app mcw-sp-gateway   # the usual fix
```

Reading the logs: every line is `key='value'` pairs. `status='ok'` is healthy.
`status='failed'` with `error_type=` tells you the class of problem. You will never
see a client name in there — the logger cannot emit one.

**The failure that actually matters is silent staleness** — the dashboard confidently
showing three-week-old numbers because nobody noticed the job stopped. That is why the
design writes a freshness record, and why consumers are expected to show "last checked"
rather than assume the data is current.

---

## Status

**Built and working**
- Safety rails, credential handling, encrypted session store, single-instance lock
- Sign-in flow against the real page (SAML across two SimplePractice domains;
  selectors confirmed by live probe)
- Feed registry + scheduler, container, Fly config

**Not built yet — blocked on the first successful sign-in**
- The report feeds. Which reports the biller role can reach, and how their pages are
  structured, can only be discovered from inside a logged-in session. No report URLs or
  selectors have been invented here.
- The reducers that turn report rows into weekly aggregates
- The Supabase schema and the consumer contract
- Health/alerting wiring

**Unverified, worth checking rather than trusting**
- Fly's per-service BAA scope is not published the way some competitors publish theirs.
  Worth one written question to Fly asking whether Machines, Volumes and `fly logs` are
  all in scope.
- The `[[vm]]` sizing is a reasonable estimate for headless Chromium, not a measurement.

---

## Adding a new import later

This is the whole point of the thing. One decorated function:

```python
@feed("attendance_weekly", kind="authed", every=timedelta(days=1))
def attendance_weekly(context, budget, pacer) -> int:
    ...  # reduce to weekly aggregates INSIDE the page, return a row count
```

`kind="public"` feeds are never handed a credential — not "declines to use one",
but none exists in scope. Use it for anything that does not need a login.

There is deliberately **no** generic "fetch any URL" endpoint. Adding a *consumer*
(a project that reads our data) is meant to be trivial. Adding a *feed* (new data
pulled out of SimplePractice) is meant to be a reviewed change. That asymmetry is
what keeps the answer to "what patient data does this system touch?" answerable.

---

## Feed: `sp_client_check` (nightly, added 2026-09-23)

Checks every HubSpot client booked in the last 120 days against SimplePractice
(exists? first appointment on/after the booking? attended / no-show / cancelled /
upcoming?) and upserts one status row per contact into the **FDO dashboard**
Supabase table `sp_client_checks` (no names, numbers or e-mails). Runs once per
night between 21:00 and 05:00 ET, when the calendar feed is idle. Needs the Fly
secrets `FDO_SUPABASE_URL` and `FDO_SUPABASE_SERVICE_KEY` (see
`deploy/set-secrets.ps1`); without them it logs `fdo_supabase_not_configured`
once a night and does nothing. Couples therapy is filed under a separate
SimplePractice couple record (clientCouples) that owns the sessions; the phone
search usually finds one partner's individual record, which has none. So a
contact whose individual record is missing or has no session on/after Date
Booked is also looked up as a couple (base-clients search: the phone digits, or
both first and last name as whole words of the couple's name — "Ann" never
matches inside "Joann"), and the couple's first session is used when it has
one. Contacts whose HubSpot Type of Therapy says "Couples" try the couple record
first. When an individual record was already found and the booking is not
couples therapy, only a couple file opened around the booking (30 days before
Date Booked to 120 after) counts, so a child booked on a parent's number never
inherits the parents' couple record. If the couple search itself fails, a
session on the other record is still used; with none, the contact is an error
and its previous row is kept (a failed lookup never overwrites a good row; see
`step='errors' status='kept_previous_row'`). The same couple re-check runs in
`check_callers`.
Family bookings (added 2026-09-25): a parent books family therapy, the
parent's name is not a SimplePractice client, and the sessions sit on the
children's records, which the full 10-digit phone search returns (their own
default number is a different one). When that search returns 2-3 records whose
last name carries the HubSpot contact's surname as a whole word (every one of
them, or — for a Type of Therapy containing "Family" — those that do), they are
the family: the first session on/after Date Booked across them is reported with
`matched_by = 'family'` (no session: `no_appointment`, still found). More than 3
records is never a family. For any booking that is not Family therapy the family
is a last resort: it is looked at only when nothing else was found (neither the
contact's own record nor a couple record), and only records opened around the
booking count (30 days before Date Booked to 120 after) — relatives in
long-standing therapy on the same number never make a missing client "found".
A Family booking re-checks the family even when the contact's own record was
found without a session (like a couple for a Couples booking). Order:
individual → couple → family; Couples type: couple → individual → family;
Family type: individual → family → couple. It reuses the phone search (asking
for name fields only when the contact has a surname), so it adds only session
lists; the per-contact ceiling `ITEM_MAX_REQUESTS` is 17 (was 14; only a Family
booking can reach it). A failed family lookup follows the couple rule: another
place's session is used (after a failed family step, only a couple file opened
around the booking); otherwise error, previous row kept. `check_callers` has
its own matching path and does not use this rule.
Acceptance check after deploy (the whole-word last-name rule is stricter than
what the discovery run printed): the verified Family booking should read
`matched_by = 'family'` in `sp_client_checks`. If it is still `found = 0`,
suspect the last-name rule first (hyphenated / suffixed / apostrophe surnames
are deliberately not matched).
Watch `fly logs` for `feed='sp_client_check'` lines: `step='contacts'`,
`step='totals'`, and the final `status='ok'` with `budget_used`.
