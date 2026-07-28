"""Build SOP-006 'Reset a Forgotten Password'."""
import datetime, json, sys
from pathlib import Path
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "sop-kit"))
import sop_docx as D

LINKS = json.loads((HERE / "links.json").read_text())
ANN = HERE / "screenshots_annotated" / "sop_006"
OUT = HERE / "output" / "SOP-006_Reset_a_Forgotten_Password.docx"
_t = datetime.date.today()
DATE = f"{_t.strftime('%B')} {_t.day}, {_t.year}"
def img(n): return ANN / f"step_{n:02d}.png"

d = D.SopDoc(LINKS, "SOP-006 — Reset a Forgotten Password")
d.title_page("SOP-006", "Reset a Forgotten Password",
    "How to reset your own password when you cannot sign in to the Clinician Matcher.",
    "1.0", DATE)
d.table_of_contents()

d.heading("Purpose")
d.rich_para(
    "This procedure explains how to reset your own password for the [[matcher|MCW Clinician Matcher]] if you have "
    "forgotten it and cannot sign in. Each staff member has their own login, so you can fix this yourself in a few "
    "minutes without waiting for a manager. If the self-service reset does not work, the Troubleshooting section "
    "explains the backup option.")

d.heading("Scope")
d.rich_para(
    "Performed by any staff member who already has a [[matcher|Clinician Matcher]] account and has forgotten their "
    "password. You do not need any special role to reset your own password. If you have never had an account, see "
    "the last Troubleshooting entry.")

d.heading("Prerequisites")
d.bullets([
    "You already have an account in the [[matcher|Clinician Matcher]] (an Admin or the Owner created one for you). "
    "Accounts cannot be self-created — see Troubleshooting if you have never had one.",
    "You can open your work email inbox, since the reset link is sent there.",
])

d.heading("Tools & Access Required")
d.rich_para("You only need the app's sign-in page and access to your work email.")
d.tools_table(["matcher"])

d.heading("Definitions / Glossary")
d.glossary([
    ("Clinician Matcher", "matcher", "The shared web app the front office uses to match clients to clinicians."),
    ("Reset link", None, "A secure, single-use web link the app emails to you. Clicking it lets you set a new password. It expires after a while and can only be used once."),
    ("Work email", None, "The email address your account was created with — usually your name at the practice's email domain."),
])

d.heading("Procedure")
d.rich_para("Follow these steps in order. Each step is one action.")

d.heading("Part A: Request a Reset Link", 2)
d.step(1, "Open the Sign-In Page and Click \"Forgot password?\"", img(1),
    "Go to the [[matcher|Clinician Matcher]] sign-in page. Below the \"Sign in\" button, click the \"Forgot password?\" link.",
    "The page changes to a \"Forgot password\" form with a single email box and a \"Send reset link\" button.")
d.step(2, "Enter Your Work Email", img(2),
    "Click the email box and type the work email address your account uses.",
    "Your email address appears in the box.")
d.step(3, "Send the Reset Link", img(3),
    "Click the \"Send reset link\" button.",
    "A green confirmation message replaces the form.")
d.step(4, "Check Your Email", img(4),
    "Open your work email inbox and look for a message from the app about resetting your password. Leave this browser tab open.",
    "The confirmation message on screen tells you a reset link is on its way to your email.",
    ("tip", "If the email is not in your inbox within a few minutes, check your spam or junk folder — the first message from a new service often lands there."))

d.heading("Part B: Set a New Password", 2)
d.step(5, "Open the Link and Enter a New Password", img(5),
    "In the reset email, click the link. It opens the app on a \"Choose a new password\" screen. Type a new password (at least 8 characters) in the \"New password\" box, then type the exact same password again in the \"Repeat new password\" box.",
    "Both boxes show dots for the characters you typed. The two entries must match.")
d.step(6, "Save the New Password", img(6),
    "Click the green \"Save new password\" button.",
    "Your password is changed and you are taken straight into the app, signed in. You are done — use this new password from now on.",
    ("ok", "Your new password works immediately on every device. There is nothing else to confirm."))

d.heading("Troubleshooting")
d.troubleshooting([
    ("The reset email never arrived.",
     "Check your spam or junk folder first. The email service also limits how many resets can be sent per hour across the whole practice, so if several people reset at once, wait a little and try again. As a backup, ask an Admin or the Owner to set a new password for you directly."),
    ("The link says it has expired or is invalid.",
     "Reset links can only be used once and expire after a while. Go back to the sign-in page, click \"Forgot password?\" again, and request a fresh link, then use it right away."),
    ("It says \"The two passwords don't match\" or \"Use at least 8 characters.\"",
     "Re-type the same password carefully in both boxes, and make sure it is at least 8 characters long. Then click \"Save new password\" again."),
    ("I have never had an account, so I have no password to reset.",
     "Accounts cannot be created by signing up — that is turned off for security. Ask the practice owner or an Admin to create an account for you (see SOP-004). You will then receive an invite email to set your first password."),
])

d.heading("Revision History")
d.revision_history([("1.0", DATE, "", "Initial release of SOP-006 Reset a Forgotten Password.")])

out = d.save(OUT)
print("Saved:", out)
print(json.dumps(D.verify_docx(out), indent=2))
