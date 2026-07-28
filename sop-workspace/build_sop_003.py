"""Build SOP-003 'Deactivate or Remove a Clinician'."""
import datetime, json, sys
from pathlib import Path
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "sop-kit"))
import sop_docx as D

LINKS = json.loads((HERE / "links.json").read_text())
ANN = HERE / "screenshots_annotated" / "sop_003"
OUT = HERE / "output" / "SOP-003_Deactivate_or_Remove_a_Clinician.docx"
_t = datetime.date.today()
DATE = f"{_t.strftime('%B')} {_t.day}, {_t.year}"
def img(n): return ANN / f"step_{n:02d}.png"

d = D.SopDoc(LINKS, "SOP-003 — Deactivate or Remove a Clinician")
d.title_page("SOP-003", "Deactivate or Remove a Clinician",
    "How to hide a clinician who has left or gone on leave (reversible), bring one back, and when to permanently delete.",
    "1.0", DATE)
d.table_of_contents()

d.heading("Purpose")
d.rich_para(
    "This procedure explains how to remove a clinician from the [[matcher|MCW Clinician Matcher]] when they leave the "
    "practice or go on leave. It matters because a clinician who has left but still appears in the app can have new "
    "clients routed to them by mistake. The safe, everyday way to do this is to \"Deactivate\" the clinician, which "
    "hides them from all staff but keeps their record so you can bring them back. Permanently deleting a clinician is "
    "a separate, rarely-needed action that cannot be undone.")

d.heading("Scope")
d.rich_para(
    "Performed in the [[matcher|Clinician Matcher]] by an Admin or Owner. Front Desk and Viewer accounts cannot "
    "deactivate, delete, or reactivate clinicians. Permanent deletion is reserved for the Owner account only.")

d.heading("Prerequisites")
d.bullets([
    "You are signed in to the [[matcher|Clinician Matcher]] with an Admin or Owner account.",
    "You can see an \"Edit details\" button at the bottom of each clinician's card. If you cannot, your account does "
    "not have permission — ask the practice owner.",
    "You know which action you need: Deactivate (hide, reversible) in almost all cases, or Delete (permanent) only "
    "for a record created by mistake.",
])

d.heading("Tools & Access Required")
d.rich_para("Open the app and confirm you can see the clinician cards and the \"Edit details\" button.")
d.tools_table(["matcher"])

d.heading("Definitions / Glossary")
d.glossary([
    ("Clinician Matcher", "matcher", "The shared web app the front office uses to match clients to clinicians."),
    ("Deactivate", None, "Hide a clinician from all staff while keeping their record. Reversible at any time. This is the recommended way to remove someone who has left or is on leave."),
    ("Reactivate", None, "Bring a deactivated clinician back so they appear on the board again, with all their details intact."),
    ("Delete", None, "Permanently erase a clinician and all their data for everyone. Cannot be undone. Only the Owner account can do this, and only for records created by mistake."),
])

d.heading("Procedure")
d.rich_para("Follow these steps in order. Each step is one action. Do not skip the verification steps.")

d.heading("Part A: Deactivate (Hide) a Clinician", 2)
d.step(1, "Open the Clinician's Details", img(1),
    "Find the clinician (type their name in the search box to locate them quickly), then click \"Edit details\" at the bottom of their card.",
    "The \"Edit details\" window opens, showing the clinician's information and — at the bottom — \"Deactivate\" and \"Delete\" buttons.")
d.step(2, "Click \"Deactivate\"", img(2),
    "At the bottom of the window, click the yellow \"Deactivate\" button. A confirmation box appears asking you to confirm — click \"OK.\"",
    "The window closes and you return to the clinician list.",
    ("warn", "Use \"Deactivate,\" not the red \"Delete\" button next to it. Deactivate hides the clinician but keeps their record so you can undo it. Delete erases everything permanently and cannot be reversed."))
d.step(3, "Confirm the Clinician Is Hidden", img(3),
    "Type the clinician's name in the search box at the top of the sidebar.",
    "The list shows \"0 clinicians\" — the deactivated clinician no longer appears anywhere on the board for any staff member.")

d.heading("Part B: Bring a Deactivated Clinician Back", 2)
d.step(4, "Open \"Update All Clinicians\"", img(4),
    "In the sidebar, click the \"Update all clinicians\" button.",
    "The \"Update all clinicians\" window opens, listing every clinician.")
d.step(5, "Click \"Reactivate\"", img(5),
    "Scroll to the bottom of the window to the section labeled \"Deactivated (hidden from staff).\" Find the clinician and click the \"Reactivate\" button next to their name.",
    "The clinician is removed from the \"Deactivated\" section.")
d.step(6, "Confirm the Clinician Is Back", img(6),
    "Close the window and type the clinician's name in the search box.",
    "The clinician's card appears again with all their original details. You are done.",
    ("ok", "Reactivating restores everything — the clinician's specialties, rates, and notes were never lost while they were deactivated."))

d.heading("Troubleshooting")
d.troubleshooting([
    ("There is no \"Edit details\" button on the clinician cards.",
     "Your account is a Front Desk or Viewer role, which cannot manage the roster. Ask an Admin or the practice owner to deactivate or reactivate the clinician for you."),
    ("I deactivated the wrong clinician.",
     "Nothing is lost. Click \"Update all clinicians,\" scroll to the \"Deactivated\" section at the bottom, and click \"Reactivate\" next to the clinician's name. They return exactly as they were."),
    ("I only see a \"Deactivate\" button, not a \"Delete\" button.",
     "Permanent deletion is limited to the Owner account. If you genuinely need to delete a record created by mistake, ask the practice owner. In every other case, \"Deactivate\" is the correct choice anyway."),
    ("I clicked Deactivate and got an error message about the database.",
     "The app could not reach the shared database, usually a brief internet issue. Nothing was changed. Check the internet connection and try again."),
])

d.heading("Revision History")
d.revision_history([("1.0", DATE, "", "Initial release of SOP-003 Deactivate or Remove a Clinician.")])

out = d.save(OUT)
print("Saved:", out)
print(json.dumps(D.verify_docx(out), indent=2))
