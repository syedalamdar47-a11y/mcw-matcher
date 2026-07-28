"""Build SOP-005 'Sync Priorities from the Google Sheet'."""
import datetime, json, sys
from pathlib import Path
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "sop-kit"))
import sop_docx as D

LINKS = json.loads((HERE / "links.json").read_text())
ANN = HERE / "screenshots_annotated" / "sop_005"
OUT = HERE / "output" / "SOP-005_Sync_Priorities_from_the_Google_Sheet.docx"
_t = datetime.date.today()
DATE = f"{_t.strftime('%B')} {_t.day}, {_t.year}"
def img(n): return ANN / f"step_{n:02d}.png"

d = D.SopDoc(LINKS, "SOP-005 — Sync Priorities from the Google Sheet")
d.title_page("SOP-005", "Sync Priorities from the Google Sheet",
    "How to update a clinician's priority in the practice's Google Sheet and pull those changes into the Clinician Matcher.",
    "1.0", DATE)
d.table_of_contents()

d.heading("Purpose")
d.rich_para(
    "The practice keeps each clinician's priority in a shared Google Sheet, and the "
    "[[matcher|MCW Clinician Matcher]] reads its priorities from that sheet. This procedure explains how to change a "
    "priority in the sheet and then pull the change into the app. It matters because staff route new clients partly by "
    "priority — if the app's priority is out of date, clients may be sent to the wrong clinician. The sheet is the "
    "\"source of truth\": whatever it says wins.")

d.heading("Scope")
d.rich_para(
    "Performed by any Front Desk, Admin, or Owner user, whenever a clinician's priority needs to change. The app "
    "also syncs automatically every time someone signs in, so in normal use changes flow in on their own — this "
    "procedure is for making a change and confirming it right away.")

d.heading("Prerequisites")
d.bullets([
    "You are signed in to the [[matcher|Clinician Matcher]] with a Front Desk, Admin, or Owner account, and you can "
    "see a \"Sync from Sheet\" button in the sidebar.",
    "You can open and edit the practice's priority Google Sheet (ask the practice owner for the link and access if "
    "you do not have it).",
    "You know which clinician's priority to change and the new value (High, Medium, or Low).",
])

d.heading("Tools & Access Required")
d.rich_para(
    "You need two things: the [[matcher|Clinician Matcher]] (below), and edit access to the practice's priority "
    "Google Sheet. The Google Sheet is private to the practice, so its link is kept by the practice owner rather "
    "than printed here.")
d.tools_table(["matcher"])

d.heading("Definitions / Glossary")
d.glossary([
    ("Clinician Matcher", "matcher", "The shared web app the front office uses to match clients to clinicians."),
    ("Priority Google Sheet", None, "The practice's private Google Sheet that holds each clinician's priority (and availability). The app reads its values from this sheet. It has one row per clinician with columns for id, name, priority, and accepting."),
    ("Priority", None, "How much the practice wants a clinician's caseload filled: High, Medium, or Low. In the sheet you can type \"High,\" \"Medium,\" or \"Low\" (the app also accepts \"High Priority,\" etc.)."),
    ("id column", None, "The first column of the sheet. It holds each clinician's unique ID, which is how the app matches a sheet row to a clinician. Never change these values."),
    ("Sync", None, "Pulling the latest priorities from the Google Sheet into the app. It happens automatically when staff sign in, and on demand with the \"Sync from Sheet\" button."),
    ("Sync report", None, "The summary the app shows after a sync: what changed, plus any values it could not understand or rows that did not match a clinician."),
])

d.heading("Procedure")
d.rich_para("Follow these steps in order. Each step is one action.")

d.heading("Part A: Update the Priority in the Google Sheet", 2)
d.step(1, "Open the Priority Google Sheet", img(1),
    "Open the practice's priority Google Sheet. Find the column headed \"priority.\"",
    "You see one row per clinician, with a \"priority\" value in the priority column for each.")
d.step(2, "Change the Clinician's Priority", img(2),
    "Click the priority cell in the clinician's row and type the new value: High, Medium, or Low. Press Enter.",
    "The cell shows the new priority value.",
    ("warn", "Never change the values in the \"id\" column — that is how the app matches each row to a clinician. Also note: Google can take up to about 5 minutes to publish a sheet change, so the app may not see it for a few minutes."))

d.heading("Part B: Pull the Change Into the App", 2)
d.step(3, "Click \"Sync from Sheet\"", img(3),
    "Switch to the [[matcher|Clinician Matcher]] and, in the sidebar, click the \"Sync from Sheet\" button.",
    "The app reads the sheet and a \"Sheet sync report\" window opens.")
d.step(4, "Read the Sync Report", img(4),
    "Read the report. The \"Updated from sheet\" section lists exactly which clinicians changed. If the report also lists any unrecognized values or rows that did not match a clinician, note them for the Troubleshooting steps.",
    "The report shows your change — for example, \"Sam Taylor: priority -> High Priority.\"",
    ("tip", "If your change is not listed and nothing else looks wrong, Google may not have published it yet. Wait a few minutes and click \"Sync from Sheet\" again."))
d.step(5, "Confirm the Card Updated", img(5),
    "Close the report, then find the clinician's card (type their name in the search box).",
    "The clinician's priority badge now shows the new value from the sheet. You are done — every staff member now sees the updated priority.",
    ("ok", "You normally only need to sync manually when you want the change reflected right away. Otherwise the app pulls the latest priorities automatically the next time anyone signs in."))

d.heading("Troubleshooting")
d.troubleshooting([
    ("There is no \"Sync from Sheet\" button in the sidebar.",
     "Either your account is a Viewer (read-only), or the Google Sheet has not been connected to the app yet. Ask the practice owner. If the sheet is connected, priorities still sync automatically when staff sign in."),
    ("I changed the sheet, but the sync report doesn't show my change.",
     "Google publishes sheet changes with up to about a 5-minute delay. Wait a few minutes and click \"Sync from Sheet\" again. Also double-check you edited the correct clinician's row."),
    ("The report says a priority value was \"not recognized.\"",
     "The app only understands High, Medium, and Low (it also accepts \"High Priority,\" etc.). A typo like \"Hgih\" is skipped, not guessed. Open the sheet, fix that clinician's priority cell to a valid value, and sync again."),
    ("The report says a clinician is \"in the app but not in the sheet.\"",
     "That clinician has no row in the sheet, so their priority is left unchanged. To manage them from the sheet, add a row using their exact ID (open the clinician's \"Edit details\" in the app to copy their ID)."),
    ("I changed a priority in the app, but it went back to the old value.",
     "The sheet overrides manual priority changes in the app. For a lasting change, update the clinician's row in the Google Sheet instead."),
])

d.heading("Revision History")
d.revision_history([("1.0", DATE, "", "Initial release of SOP-005 Sync Priorities from the Google Sheet.")])

out = d.save(OUT)
print("Saved:", out)
print(json.dumps(D.verify_docx(out), indent=2))
