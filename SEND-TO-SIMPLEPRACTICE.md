# Questions to send SimplePractice

**Why:** we want to stop downloading these reports by hand every day. This letter asks
SimplePractice what they *support* — an API, scheduled report delivery, SFTP — because if
any of those exist, we should buy that instead of building anything. It is a purchasing
question with an upside.

**Deliberately NOT asked:** an earlier draft asked whether automating a login with a
role-limited account would violate their Terms of Service. That question was removed on
purpose. SimplePractice has no API to sell a practice this size, so the likely reply is
"no, don't do that" — in writing, dated, and on file. That would convert a grey area into
a documented refusal and make any later automation a knowing violation, which is a worse
position than asking nothing. Ask what they *support*; don't ask them to rule on what we
might otherwise do.

**How to send:** SimplePractice Help Centre → *Contact Support* (or your account manager
if you have one). Send it as a support ticket so there is a written record.
**Keep the reply.** Save it next to your BAA records.

**Timing:** send this before we build the automated login. If the answer is "no", we change
the approach rather than discover the problem after it is built.

---

## Copy from here

Subject: **Automated export of our own practice reporting data — is it supported?**

Hello,

We are a group practice (practice ID **226118**, McNulty Counseling and Wellness) with
approximately 33 clinicians.

Every day we manually download financial and attendance reports from SimplePractice and
enter the figures into an internal operations dashboard. We would like to automate that
step. Before we do anything, we want to make sure we do it in a way SimplePractice supports.

Four questions:

1. **Does SimplePractice offer any supported way to retrieve our own practice-level
   reporting data on a schedule** — an API, a scheduled report delivery, an SFTP drop, or a
   data export feature? If this is available on a higher plan tier, we are willing to pay
   for it.

2. **What is the supported way for a practice to get its own operational data out of
   SimplePractice on a schedule?** We are happy to change how we work to match whatever
   route SimplePractice supports.

3. Please **confirm that our Business Associate Agreement with SimplePractice is current
   and on file.**

Thank you,

Alam Naqvi
McNulty Counseling and Wellness

## Copy to here

---

## Two smaller things to check while you are in the account

These do not need SimplePractice support — you can check them yourself in a couple of
minutes, and both change what gets built.

**A. Which type of two-factor authentication is offered?**
Go to your account/profile settings and look for *Two-Factor Authentication* or *Security*.
Report back which options appear:
- "Authenticator app" / "Google Authenticator" / "scan this QR code" → **ideal**, the
  gateway can generate its own codes and never needs you again.
- "Text message" / "SMS" only → workable, but a person has to re-authorise every few weeks.

**B. What can the biller account actually see?**
Log in as the biller account and try to open one client's chart. Note whether you can see:
the client's name, date of birth, address, insurance details, and any clinical/progress
notes. Also run the financial activity report and the attendance report, and note whether
the rows list **individual client names** or only totals.

This matters because it decides whether the gateway ever touches protected health
information, which in turn decides how strictly it has to be built.
