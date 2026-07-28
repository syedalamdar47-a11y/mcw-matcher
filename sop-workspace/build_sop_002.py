"""Build SOP-002 'Update a Clinician's Availability & Priority'."""
import datetime, json, sys
from pathlib import Path
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "sop-kit"))
import sop_docx as D

LINKS = json.loads((HERE / "links.json").read_text())
ANN = HERE / "screenshots_annotated" / "sop_002"
OUT = HERE / "output" / "SOP-002_Update_Availability_and_Priority.docx"
_t = datetime.date.today()
DATE = f"{_t.strftime('%B')} {_t.day}, {_t.year}"
def img(n): return ANN / f"step_{n:02d}.png"

d = D.SopDoc(LINKS, "SOP-002 — Update Availability & Priority")
d.title_page("SOP-002", "Update a Clinician's Availability & Priority",
    "How to change whether a clinician is accepting clients, their priority, and their internal note so the whole front office sees the current status.",
    "1.0", DATE)
d.table_of_contents()

d.heading("Purpose")
d.rich_para(
    "This procedure explains how to update a clinician's availability, priority, and internal note in the "
    "[[matcher|MCW Clinician Matcher]]. This is the most common daily task in the app. Keeping it current matters: "
    "if a clinician is full but still shows as \"Accepting,\" staff may route a new client to someone who has no room, "
    "and the client waits or is turned away. Because the Matcher is shared, the moment you save, every other staff "
    "member's screen updates automatically.")

d.heading("Scope")
d.rich_para(
    "Performed in the [[matcher|Clinician Matcher]] by any Front Desk, Admin, or Owner user, whenever a clinician's "
    "availability or priority changes (for example, they fill their caseload, open a slot, or go on leave). Viewer "
    "accounts can see the board but cannot make changes.")

d.heading("Prerequisites")
d.bullets([
    "You are signed in to the [[matcher|Clinician Matcher]] with a Front Desk, Admin, or Owner account.",
    "You can see an \"Edit status & priority\" button at the bottom of each clinician's card. If you do not, your "
    "account is a Viewer (read-only) — ask an Admin to change your role.",
    "You know the change you need to make (the new availability, and whether the priority should change).",
])

d.heading("Tools & Access Required")
d.rich_para("Open the app and confirm you can see the clinician cards and the \"Edit status & priority\" buttons.")
d.tools_table(["matcher"])

d.heading("Definitions / Glossary")
d.glossary([
    ("Clinician Matcher", "matcher", "The shared web app the front office uses to match clients to clinicians."),
    ("Availability (Accepting status)", None, "Whether a clinician is taking new clients: \"Accepting\" (open), \"Needs Clients\" (wants more), or \"Not Accepting\" (full)."),
    ("Priority", None, "How much the practice wants this clinician's caseload filled: \"High Priority,\" \"Medium Priority,\" or \"Low Priority.\" It affects where the clinician sorts in the list."),
    ("Admin note", None, "A short internal note shown on the clinician's card (for example, \"No new evenings\"). Visible only to signed-in staff."),
    ("Google Sheet sync", None, "The app can update priority (and availability) automatically from the practice's Google Sheet. If your practice uses this, a manual change here lasts only until the next sync — see the note in Step 3."),
])

d.heading("Procedure")
d.rich_para("Follow these steps in order. Each step is one action. Do not skip the final verification step.")

d.heading("Part A: Open the Status Editor", 2)
d.step(1, "Open the Clinician's Status Editor", img(1),
    "At the bottom of the clinician's card, click \"Edit status & priority.\" (Tip: type the clinician's name in the search box at the top of the sidebar first, to find their card quickly.)",
    "The bottom of the card expands to show three fields: \"Availability,\" \"Priority,\" and \"Admin note,\" plus \"Save\" and \"Cancel\" buttons.")

d.heading("Part B: Set the New Status", 2)
d.step(2, "Choose the Availability", img(2),
    "Click the \"Availability\" dropdown and choose one: \"Accepting,\" \"Needs Clients,\" or \"Not Accepting.\"",
    "The dropdown shows your choice.")
d.step(3, "Choose the Priority", img(3),
    "Click the \"Priority\" dropdown and choose \"High Priority,\" \"Medium Priority,\" or \"Low Priority.\"",
    "The dropdown shows your choice.",
    ("warn", "If your practice controls priority through the Google Sheet, a change you make here is temporary — the next sheet sync will overwrite it. For a lasting priority change, update the clinician's row in the Google Sheet instead."))
d.step(4, "Add an Admin Note (Optional)", img(4),
    "If you need to leave an internal note, click the \"Admin note\" box and type it — for example, \"Full through August - not taking new clients.\" Leave it blank if there is nothing to add.",
    "Your note text appears in the \"Admin note\" box.")

d.heading("Part C: Save and Confirm", 2)
d.step(5, "Save the Changes", img(5),
    "Click the green \"Save\" button.",
    "The editing fields close and the card returns to its normal view.")
d.step(6, "Confirm the Card Updated", img(6),
    "Look at the top of the clinician's card.",
    "The availability and priority badges now show your new values, and any note you added appears in a highlighted box on the card. You are done — every staff member now sees the updated status.",
    ("ok", "The change is already live for the whole team. There is nothing else to save or send."))

d.heading("Troubleshooting")
d.troubleshooting([
    ("There is no \"Edit status & priority\" button on the cards.",
     "Your account is a Viewer, which is read-only. Ask an Admin or the practice owner to change your role to Front Desk (or higher) if you need to make changes."),
    ("I changed a clinician's priority, but later it went back to what it was before.",
     "Your practice is driving priority from the Google Sheet, and a sync overwrote your manual change. To make the change stick, update that clinician's row in the priority Google Sheet instead of (or as well as) in the app."),
    ("My change doesn't appear on a co-worker's screen.",
     "Saved changes normally appear on every screen within a second or two. Ask them to refresh the page (Ctrl+Shift+R). If it still doesn't appear, there may be an internet connection problem on one of the computers — check the connection and try again."),
])

d.heading("Revision History")
d.revision_history([("1.0", DATE, "", "Initial release of SOP-002 Update a Clinician's Availability & Priority.")])

out = d.save(OUT)
print("Saved:", out)
print(json.dumps(D.verify_docx(out), indent=2))
