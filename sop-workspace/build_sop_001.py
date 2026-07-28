"""
Build SOP-001 "Add a New Clinician" as a .docx in the MCW house style.
Run:  python sop-workspace/build_sop_001.py
"""
import datetime
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "sop-kit"))
import sop_docx as D

LINKS = json.loads((HERE / "links.json").read_text())
ANN = HERE / "screenshots_annotated" / "sop_001"
OUT = HERE / "output" / "SOP-001_Add_a_New_Clinician.docx"

_t = datetime.date.today()
DATE = f"{_t.strftime('%B')} {_t.day}, {_t.year}"


def img(n):
    return ANN / f"step_{n:02d}.png"


d = D.SopDoc(LINKS, "SOP-001 — Add a New Clinician")

# 1. Title page
d.title_page(
    "SOP-001", "Add a New Clinician",
    "How to create a new clinician record in the Clinician Matcher so front-office staff can find and match clients to them.",
    "1.0", DATE,
)

# 2. Table of Contents
d.table_of_contents()

# 3. Purpose
d.heading("Purpose")
d.rich_para(
    "This procedure explains how to add a new clinician to the [[matcher|MCW Clinician Matcher]] so that "
    "front-office staff can see them and match clients to them. Adding a clinician correctly matters: a clinician "
    "who is never added — or who is added without their session groups and specialties — will not appear when staff "
    "filter for the kind of client they can help, so referrals may be missed or sent to the wrong provider. "
    "Because the Matcher is shared, a clinician you add here becomes visible to every staff member immediately."
)

# 4. Scope
d.heading("Scope")
d.rich_para(
    "This SOP is performed in the [[matcher|Clinician Matcher]] by any user with an Admin or Owner role, whenever a "
    "new clinician joins the practice. Front Desk and Viewer users cannot add clinicians. Completing this procedure "
    "makes the new clinician immediately available in searches, filters, and matching for the whole front office."
)

# 5. Prerequisites
d.heading("Prerequisites")
d.bullets([
    "You are signed in to the [[matcher|Clinician Matcher]] with an Admin or Owner account.",
    "The “+ Add clinician” button is visible at the bottom of the green sidebar on the left. If it is not, "
    "your account does not have permission to add clinicians — stop and ask the practice owner to add the "
    "clinician or to change your role.",
    "You have the new clinician’s details ready: full name, credentials (e.g., LMHC, LCSW), provider type "
    "(therapy or psychiatry), office(s), weekly schedule, which session types they offer, session rates, and their "
    "specialties and treatment modalities.",
])

# 6. Tools & Access Required
d.heading("Tools & Access Required")
d.rich_para(
    "Before you begin, click the link below and confirm you can open the app and see the “+ Add clinician” "
    "button. If you get a sign-in screen, sign in first; if you can open the app but the button is missing, contact "
    "the practice owner — your account role needs to be changed."
)
d.tools_table(["matcher"])

# 7. Definitions / Glossary
d.heading("Definitions / Glossary")
d.glossary([
    ("Clinician Matcher", "matcher", "The web app used by the front office to search for clinicians and match them to clients."),
    ("Provider type", None, "Whether the clinician is a therapist (“Therapy”) or a psychiatric provider (“Psychiatry”). It controls which tab of the app they appear under."),
    ("Profile", None, "The clinician’s name plus their credentials, exactly as it should read on their card — for example, “Jane Doe, LMHC”."),
    ("Session groups", None, "The client types a clinician works with: Individuals, Couples, Families, and/or Minors. These control the “Session type” filters, so a clinician with no session groups is hidden from filtered searches."),
    ("Office", None, "A physical location (DTSP, Tyrone, Tampa, or Sarasota) or “Virtual” for telehealth. A clinician can serve more than one."),
    ("Specialty", None, "A clinical focus area the clinician works with, such as Anxiety, Trauma, or OCD."),
    ("Modality", None, "A treatment method or approach the clinician uses, such as CBT, EMDR, or DBT."),
    ("Priority", None, "How much the practice wants a clinician’s caseload filled: High, Medium, or Low. New clinicians start at “Medium Priority” and can be changed later."),
    ("Availability (Accepting status)", None, "Whether a clinician is taking new clients: “Accepting,” “Needs Clients,” or “Not Accepting.” New clinicians start at “Needs Clients.”"),
])

# 8. Procedure
d.heading("Procedure")
d.rich_para(
    "Follow these steps in order. Each step contains exactly one action. Do not skip any step — even the "
    "verification-only step at the end is required to confirm the clinician was added correctly."
)

d.heading("Part A: Open the Add Clinician Form", 2)
d.step(1, "Click the “+ Add clinician” Button", img(1),
       "In the green sidebar on the left, click the green “+ Add clinician” button at the bottom.",
       "A pop-up window titled “Add clinician” opens in the center of the screen, with the note “Creates a new clinician for all staff.”")

d.heading("Part B: Enter the Clinician’s Basic Details", 2)
d.step(2, "Type the Clinician’s Name", img(2),
       "Click the “Name” box and type the clinician’s full name — for example, Test Clinician 01.",
       "The name you typed appears in the “Name” box.")
d.step(3, "Type the Profile (Name + Credentials)", img(3),
       "Click the “Profile (name + credentials)” box and type the name followed by a comma and their credentials — for example, Test Clinician 01, LMHC.",
       "The full profile text appears in the “Profile” box. This is exactly what will show as the clinician’s title on their card.")
d.step(4, "Choose the Provider Type", img(4),
       "Click “Therapy” or “Psychiatry” under “Provider type.” For a therapist, leave “Therapy” selected.",
       "The chosen button turns solid green and the other stays white.")
d.step(5, "Enter the Schedule", img(5),
       "Click the “Schedule” box and type the clinician’s working days — for example, Mon-Fri.",
       "The schedule text appears in the “Schedule” box.")
d.step(6, "Select the Office(s)", img(6),
       "Under “Offices,” click the checkbox for each location the clinician works at (DTSP, Tyrone, Tampa, or Sarasota). If they see clients by telehealth, also check “Offers telehealth (virtual).”",
       "A checkmark appears in each box you selected.")
d.step(7, "Select the Session Groups", img(7),
       "Under “Session groups,” click the checkbox for every client type the clinician works with: Individuals, Couples, Families, and/or Minors.",
       "A checkmark appears next to each group you selected.",
       ("warn", "You must select at least one session group. A clinician with no session groups is hidden whenever staff filter by “Session type,” so they will seem to disappear from searches."))
d.step(8, "Enter the Individual Rate", img(8),
       "Click the “Individual rate ($)” box and type the session fee as a number — for example, 185. If the clinician uses a sliding scale instead, leave this blank and type the range in the “…or rate as text” box (for example, $100-$150 (sliding scale)). Add couples and family rates too if they apply.",
       "The rate you typed appears in the box.")

d.heading("Part C: Choose Specialties and Modalities", 2)
d.step(9, "Check the Clinician’s Specialties", img(9),
       "Scroll down to “Specialties” and click the checkbox next to each specialty the clinician works with (for example, Anxiety, Depression, Trauma). If one is missing from the list, type it in the “Add one that isn’t listed…” box and click “Add.”",
       "A checkmark appears next to each specialty you selected, and the count in the label (“___ selected”) goes up.")
d.step(10, "Check the Clinician’s Modalities", img(10),
       "Scroll to “Modalities” and click the checkbox next to each treatment approach the clinician uses (for example, CBT, DBT). Use the “Add one that isn’t listed…” box for anything missing.",
       "A checkmark appears next to each modality you selected.")

d.heading("Part D: Save and Confirm", 2)
d.step(11, "Click “Add clinician”", img(11),
       "Scroll to the bottom of the form and click the green “Add clinician” button.",
       "The form closes and returns you to the main list of clinicians.",
       ("tip", "If a red box appears listing missing fields instead of closing, a required field (Name, Profile, Schedule, at least one Office, or at least one Session group) is empty. Fill the listed fields and click “Add clinician” again."))
d.step(12, "Confirm the New Clinician Appears", img(12),
       "In the search box at the top of the sidebar, type the new clinician’s name to find their card quickly.",
       "The new clinician’s card appears in the list, showing their name, schedule, offices, specialties, and modalities. They start as “Needs Clients” and “Medium Priority.” You are done — the clinician is now visible to all staff.",
       ("ok", "The clinician has been created for everyone. If your practice manages priority through the Google Sheet, remember to add the new clinician there too (open “Edit details” to copy their ID)."))

# 9. Troubleshooting
d.heading("Troubleshooting")
d.troubleshooting([
    ("I don’t see the “+ Add clinician” button anywhere.",
     "Your account is a Front Desk or Viewer role, which cannot add clinicians. Ask an Admin or the practice owner to add the clinician for you, or to change your role to Admin. Only Admin and Owner accounts see the button."),
    ("I clicked “Add clinician” and a red box appeared instead of the form closing.",
     "A required field is empty. The red box lists exactly which ones — usually Name, Profile, Schedule, at least one Office, or at least one Session group. Fill in the listed fields, then click “Add clinician” again."),
    ("I added the clinician, but they don’t show up when I filter by session type (for example, “Individual”).",
     "Their session groups were not set. Find the clinician’s card, click “Edit details,” check the correct boxes under “Session groups,” and click “Save changes.” They will then appear in filtered searches."),
    ("The new clinician’s priority isn’t updating from the Google Sheet.",
     "New clinicians are not in the sheet yet, so the sync leaves them at “Medium Priority.” Open the clinician’s “Edit details” to copy their ID, then add a row for them in the priority Google Sheet using that ID."),
])

# 10. Revision History
d.heading("Revision History")
d.revision_history([
    ("1.0", DATE, "", "Initial release of SOP-001 Add a New Clinician."),
])

out = d.save(OUT)
print("Saved:", out)
print(json.dumps(D.verify_docx(out), indent=2))
