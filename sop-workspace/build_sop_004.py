"""Build SOP-004 'Invite a Staff Member & Set Their Role'."""
import datetime, json, sys
from pathlib import Path
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "sop-kit"))
import sop_docx as D

LINKS = json.loads((HERE / "links.json").read_text())
ANN = HERE / "screenshots_annotated" / "sop_004"
OUT = HERE / "output" / "SOP-004_Invite_a_Staff_Member.docx"
_t = datetime.date.today()
DATE = f"{_t.strftime('%B')} {_t.day}, {_t.year}"
def img(n): return ANN / f"step_{n:02d}.png"

d = D.SopDoc(LINKS, "SOP-004 — Invite a Staff Member & Set Their Role")
d.title_page("SOP-004", "Invite a Staff Member & Set Their Role",
    "How to invite a new front-office user by email, choose what they are allowed to do, and change or remove access later.",
    "1.0", DATE)
d.table_of_contents()

d.heading("Purpose")
d.rich_para(
    "This procedure explains how to give a new front-office team member their own login to the "
    "[[matcher|MCW Clinician Matcher]] and set what they are allowed to do. Giving each person their own account "
    "(instead of sharing one) means the practice can see who changed what and can remove one person's access without "
    "affecting anyone else. Choosing the right role also protects the data: most staff only need to update day-to-day "
    "status, not manage the roster or other people's accounts.")

d.heading("Scope")
d.rich_para(
    "Performed in the [[matcher|Clinician Matcher]] by an Admin or Owner. Front Desk and Viewer accounts cannot "
    "invite or manage other users. Only the Owner can create another Admin; an Admin can invite Front Desk and "
    "Viewer users.")

d.heading("Prerequisites")
d.bullets([
    "You are signed in to the [[matcher|Clinician Matcher]] with an Admin or Owner account.",
    "You can see a \"Manage team\" button in the sidebar. If you cannot, your account is not an Admin or Owner — "
    "ask the practice owner.",
    "You know the new person's work email address and which role they should have (see the Glossary).",
])

d.heading("Tools & Access Required")
d.rich_para("Open the app and confirm you can see the \"Manage team\" button in the sidebar.")
d.tools_table(["matcher"])

d.heading("Definitions / Glossary")
d.glossary([
    ("Clinician Matcher", "matcher", "The shared web app the front office uses to match clients to clinicians."),
    ("Owner", None, "Full control, including deleting clinicians and managing Admins. Usually the practice owner. There is one Owner, and the Owner cannot be removed from the team screen."),
    ("Admin", None, "Can manage the clinician roster (add, edit, deactivate) and manage staff (invite, change roles, remove). Cannot delete a clinician permanently."),
    ("Front Desk", None, "The everyday role for front-office staff. Can update a clinician's availability, priority, notes, specialties, and modalities, but cannot add or remove clinicians or manage staff."),
    ("Viewer", None, "Read-only. Can search and see the board but cannot change anything. Good for someone in training or a supervisor who only needs to look."),
    ("Invite", None, "An email the app sends to a new user with a secure link. When they click it, they choose their own password and can then sign in."),
])

d.heading("Procedure")
d.rich_para("Follow these steps in order. Each step is one action.")

d.heading("Part A: Invite a New Team Member", 2)
d.step(1, "Open the Team Screen", img(1),
    "In the sidebar, click the \"Manage team\" button.",
    "The \"Manage team\" window opens, showing an \"Invite someone\" box at the top and the current team list below.")
d.step(2, "Enter the Person's Email", img(2),
    "In the \"Invite someone\" box, click the email field and type the new person's work email address — for example, new.staff@mcnultycounseling.com.",
    "The email you typed appears in the box.")
d.step(3, "Choose Their Role", img(3),
    "Click the role dropdown next to the email field and choose the role for this person (see the Glossary for what each role can do). For most front-office staff, choose \"Front Desk.\"",
    "The dropdown shows the role you chose.")
d.step(4, "Send the Invite", img(4),
    "Click the green \"Send invite\" button.",
    "A green confirmation message appears and the person is added to the team list below with the role you chose.",
    ("tip", "The new person must open the invitation email and click its link to choose a password before they can sign in. If they don't get it within a few minutes, ask them to check their spam folder."))
d.step(5, "Confirm the Invite Was Sent", img(5),
    "Read the green message that appears under the invite box.",
    "It confirms the invite was sent to the email you entered and that the person will receive an email to set their password. You have finished inviting them.")

d.heading("Part B: Change or Remove Someone's Access", 2)
d.step(6, "Change a Role or Remove a Person", img(6),
    "In the team list, use the dropdown next to a person's name to change their role, or click \"Remove\" to revoke their access entirely. To change a role, just pick the new one — it saves immediately.",
    "The person's role badge updates to the new role, or (if you clicked Remove and confirmed) they disappear from the list and can no longer sign in.",
    ("warn", "\"Remove\" permanently deletes that person's login. If you only want to stop someone from making changes — for example, while they are on leave — set their role to \"Viewer\" instead, which keeps their account but makes it read-only."))

d.heading("Troubleshooting")
d.troubleshooting([
    ("There is no \"Manage team\" button in the sidebar.",
     "Your account is a Front Desk or Viewer role, which cannot manage staff. Ask an Admin or the practice owner to invite the person for you."),
    ("The person I invited never received the invitation email.",
     "First, have them check their spam or junk folder. The email service also limits how many invites can be sent per hour, so wait a little and try again if needed. As a fallback, the Owner can set a password for the account directly in the Supabase dashboard (Authentication > Users)."),
    ("I can't choose \"Admin\" from the role dropdown.",
     "Only the Owner account can create another Admin. Admin users can invite Front Desk and Viewer roles only. Ask the practice owner if someone needs Admin access."),
    ("A staff member left the practice and I need to cut off their access right now.",
     "Open \"Manage team,\" find their name, and click \"Remove.\" Their login stops working immediately on every device. If you might bring them back, set them to \"Viewer\" instead so the account stays but can't change anything."),
])

d.heading("Revision History")
d.revision_history([("1.0", DATE, "", "Initial release of SOP-004 Invite a Staff Member & Set Their Role.")])

out = d.save(OUT)
print("Saved:", out)
print(json.dumps(D.verify_docx(out), indent=2))
