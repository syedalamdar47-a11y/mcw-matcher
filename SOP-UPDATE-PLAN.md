# SOP Update Plan — what changed, what's stale, what's missing

**Date:** 2026-08-11
**Why:** Since the six SOPs were written (Jul 28–29), the app changed in two big ways:
1. **The settings/admin interface was redesigned.** Every admin action that used to be a separate button *in the green sidebar* now lives behind one **⚙ Admin & tools** button at the bottom-left. So the sidebar navigation steps and screenshots in most SOPs are out of date.
2. **New features were added** that no SOP covers yet: **Live Availability** (SimplePractice times on each card) and the **Clinician self-service portal** (clinicians edit their own specialties/modalities, admins approve).

---

## The one change that touches almost every SOP

**Old way (in the SOPs):** admin actions were buttons at the bottom of the sidebar — "+ Add clinician," "Manage team," "Sync from Sheet," etc.

**New way (now):** click **⚙ Admin & tools** (bottom-left of the sidebar) → a panel opens with everything grouped:

| Section | Buttons now inside ⚙ Admin & tools |
|---|---|
| **Clinicians** | + Add clinician · ⚙ Update all clinicians · ⟳ Sync from Sheet |
| **Team** | 👥 Manage team · 📝 Clinician change requests *(new)* |
| **Tools** | 🩺 Health check · ⬇ Export a snapshot · ⬆ Restore from a file |
| **Account** | shows your email + role |

Any SOP step that says *"in the sidebar, click …"* now needs to say *"click ⚙ Admin & tools, then click …"* — and the screenshots need re-capturing against the new panel.

---

## SOP-by-SOP status

| SOP | Still accurate? | What's stale | Action |
|---|---|---|---|
| **001 — Add a New Clinician** | Content ✅, navigation ❌ | "+ Add clinician at the bottom of the sidebar" → now inside ⚙ Admin & tools → Clinicians. Screenshots show old sidebar. | Update the open-the-form step + re-capture screenshots. |
| **002 — Update Availability & Priority** | Mostly ✅, but a **naming clash** | This SOP's "Availability" means the manual **Accepting status** (Accepting / Needs Clients / Not Accepting). The card now *also* shows **live SimplePractice times**. Readers will confuse the two. Card screenshots are stale (cards now show time chips + "Pick a date"). | Add a clear note: *"this is the manual accepting status, not the live SimplePractice times (see the new Live Availability SOP)."* Re-capture card screenshots. Mention the ⚙ → "Update all clinicians" bulk option. |
| **003 — Deactivate or Remove a Clinician** | Content ✅, navigation ❌ | Opening the editor is now "Edit details" on the card (admin/owner only); reactivation path moved off the old sidebar. Screenshots stale. | Update navigation + re-capture. |
| **004 — Invite a Staff Member** | Content ✅, navigation ❌ | "In the sidebar, click Manage team" → now ⚙ Admin & tools → Team → 👥 Manage team. Screenshots stale. | Update the one navigation step + re-capture. |
| **005 — Sync Priorities from the Sheet** | Content ✅, navigation ❌ | "In the sidebar, click Sync" → now ⚙ Admin & tools → Clinicians → ⟳ Sync from Sheet. Screenshots stale. | Update the one navigation step + re-capture. |
| **006 — Reset a Forgotten Password** | ✅ Fully accurate | Nothing — this is the sign-in page "Forgot password?" flow, untouched by the redesign. | Verify screenshots still match; likely no change. |

---

## New SOPs that don't exist yet

| Proposed | Covers | Source material that already exists |
|---|---|---|
| **SOP-007 — Using Live Availability (front desk)** | How to read the SimplePractice times on each card, the "checked Ns ago" freshness, "Pick a date" for future days, what "Live times unavailable" means, and the golden rule: **confirm the exact time in SimplePractice before committing it to a caller.** | ~80% already written in **AVAILABILITY-TROUBLESHOOTING.md** and **AVAILABILITY-BRIEFING.md** — just needs shaping into the SOP format. |
| **SOP-008 — Clinician Self-Service & Approving Changes** | The clinician portal (a clinician logs in and updates their own specialties/modalities), and how an admin/owner reviews and approves the requests via ⚙ Admin & tools → 📝 Clinician change requests. | New — needs writing from scratch, but the flow is built and testable. |

---

## Recommended order (post-meeting)

1. **SOP-007 (Live Availability)** first — it's the biggest real change to the front-desk workflow, and the content mostly exists.
2. **SOP-001–005 navigation refresh** — mostly a re-capture of screenshots against the ⚙ Admin & tools panel + a couple of edited steps each. The wording and logic are still sound.
3. **SOP-002 naming-clash note** — small but important, prevents confusion between "accepting status" and "live times."
4. **SOP-008 (Clinician portal)** — once you decide to roll the portal out.
5. **SOP-006** — quick screenshot check, probably no change.

The capture/build scripts in `sop-workspace/` still work — regenerating is mostly re-running the capture against the current UI and editing the changed steps, not starting over.
