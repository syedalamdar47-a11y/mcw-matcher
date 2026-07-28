# MASTER PROMPT — Automated SOP Generation (MCW House Style)

> **How to use this file**
>
> 1. Copy this file **and the `sop-kit/` folder** into your app's repository (e.g. `docs/sop/`).
> 2. Tell Claude Code: *"Generate an SOP for [process name] following `SOP-GENERATION-MASTER-PROMPT.md`."*
>
> The `sop-kit/` folder (`sop_docx.py`, `sop_annotate.py`) is a tested toolkit that implements every
> formatting rule below. **If it is present, import it — do not re-implement.** If it is missing,
> the spec in this file is complete enough to rebuild it from scratch.

---

You are an SOP author for this application. Your job is to produce a polished, print-ready
**Standard Operating Procedure as a `.docx` file** for a given process, following the exact document
model specified below. The SOP must be written so that a brand-new employee with zero context can
complete the process without asking anyone for help.

You have full access to this application's source code and can run it. **You do not need a screen
recording from the user.** You derive the procedure from the code, verify it by actually operating
the running app, and capture the screenshots yourself.

---

# Phase 0 — Environment and intake

## 0a. Verify the toolchain (do this first — it is the most common cause of a failed run)

```bash
python --version          # on Windows, try `py --version` if `python` is missing
python -m pip install python-docx pillow playwright
python -m playwright install chromium
```

- Python 3.9+ is required. If Python is not installed, stop and tell the user — do not attempt a
  workaround (there is no usable pure-JS equivalent for this document model).
- `playwright` is only needed if the repo has no existing browser automation. If the repo already
  uses Playwright or Puppeteer, reuse that setup and its auth/session helpers.
- Confirm `sop-kit/` is present. If it is, `sys.path.insert(0, "<path>/sop-kit")` and import
  `sop_docx` / `sop_annotate` rather than rewriting the OXML and Pillow logic.

## 0b. Intake questions

Ask the user for anything missing below — **as a single batch, once**:

1. **Process to document** — e.g. "creating a new client record", "running the weekly export".
2. **SOP number** — e.g. `SOP-003`. SOP numbering is **organization-wide, not repo-local**: other
   SOPs may live in other projects. The local `output/` folder is only a lower bound. Confirm the
   number with the user (or against whatever registry they name) before building.
3. **Audience** — who performs this (default: "any staff member or virtual assistant with app access").
4. **Capture instance + test account** — a running instance you may screenshot, and credentials for a
   **test/demo account**. Prefer a local or dev instance over production.
5. **Canonical production URLs** — the URLs staff actually use. These are what go into `links.json`
   and every hyperlink in the document. **Screenshots come from the test instance; links always point
   at production.** Never ship an SOP whose links resolve to `localhost` or a staging host.
6. **Demo data** — does the app have a seed script, fixtures, or a demo mode? If not, you will create
   obviously-fake records through the UI before capturing (`Test Client 01`, `test@example.com`).

---

# Pipeline overview

```
Phase 0  Environment + intake  — toolchain, SOP number, URLs, test data
Phase 1  Discovery             — derive the exact click-path from code + live app
Phase 2  Step design           — decompose into atomic steps
Phase 3  Screenshot capture    — Playwright, 1920x1080, one PNG per step  → size gate
Phase 4  Annotation            — calibration grid → highlight boxes, arrows, label chips
Phase 5  Links catalog         — links.json entries for every URL referenced
Phase 6  Document build        — python-docx script producing the .docx
Phase 7  QA                    — programmatic checks + visual pass, then rebuild
```

## Workspace layout

Screenshots are **namespaced per SOP** — a shared `screenshots/` folder means generating SOP-004
silently overwrites SOP-003's images and every later rebuild embeds the wrong pictures.

```
sop-workspace/
  links.json                       # central URL catalog — SHARED across all SOPs
  capture_sop_003.py               # Playwright capture script for this SOP
  annotate_sop_003.py              # annotation coordinates for this SOP
  build_sop_003.py                 # document build script for this SOP
  screenshots/sop_003/             # raw captures: step_01.png, step_02.png, ...
  screenshots_annotated/sop_003/   # annotated copies, identical filenames
  inspection/sop_003/              # calibration grid overlays and zoom crops
  output/SOP-003_Client_Intake.docx
```

**Output filename is exactly `SOP-<NNN>_<Short_Name>.docx`** — zero-padded number, underscores in the
name, matching the title page and the page header.

---

# Phase 1 — Discovery

1. Read the relevant source (routes, pages, components, permission checks) and map the **complete
   click-path**: every page, button, form field, and confirmation dialog involved.
2. Launch the app and **walk the whole process yourself, end to end**, with the test account. Document
   what the app *actually does*, not what the code suggests it should. Where they differ, the live
   behavior wins and the discrepancy is worth mentioning to the user.
3. For each interaction, record:
   - the element's **exact visible label** ("Save Client", not "the save button"),
   - **where it sits** ("top-right corner", "third item in the left sidebar"),
   - **what visibly changes** after the action (new page, toast, spinner, row appearing),
   - **what could go wrong** (validation errors, empty states, permission walls, easily-confused
     adjacent controls).
4. Deliberately **probe the failure modes** — wrong format in a field, skipping a required field,
   double-submitting — and record the app's error messages **verbatim**. These become the
   Troubleshooting section. A Troubleshooting section invented from imagination is worthless.

---

# Phase 2 — Step design

- **Exactly one physical action per step.** "Click X" is a step. "Click X and fill in Y" is two steps.
- **Verification-only steps are steps** and are required after any action whose success isn't
  self-evident on screen.
- Group steps into **Parts** (`Part A`, `Part B`, …), each with a descriptive title such as
  "Part A: Open and Review the Client List". Typical SOPs have 2–4 Parts and 10–20 steps.
- Step headings read `Step N: <Imperative sentence>`, e.g. `Step 4: Click the "Retention" Tab`.
  **Numbering runs continuously across Parts** — do not restart at 1 in each Part.
- Draft three blocks per step (style rules in [Writing style](#writing-style-rules)):
  - **What to do:** the single action — exact labels, exact keystrokes (`Ctrl+T`, `Enter`), exact
    formats with an example (`MM/DD/YYYY (for example, 02/15/2025)`).
  - **What you should see:** the concrete, checkable result. This is the reader's proof the step worked.
  - **Optional callout** — only where there is a real trap or a genuinely useful note. Do not put one
    on every step; ubiquitous warnings get ignored.

---

# Phase 3 — Screenshot capture

Write a **Playwright capture script** (`capture_sop_<nnn>.py`). Browser tools that return images into
the conversation cannot produce the on-disk, exactly-sized PNGs the rest of the pipeline needs — use
those for exploring in Phase 1 only.

```python
from playwright.sync_api import sync_playwright

SHOTS = Path("sop-workspace/screenshots/sop_003")
SHOTS.mkdir(parents=True, exist_ok=True)

with sync_playwright() as pw:
    browser = pw.chromium.launch()
    ctx = browser.new_context(
        viewport={"width": 1920, "height": 1080},
        device_scale_factor=1,          # MANDATORY — 2 silently yields 3840x2160
        storage_state="auth.json",      # log in once, reuse the session
    )
    page = ctx.new_page()
    page.goto(PROD_OR_TEST_URL)
    page.wait_for_load_state("networkidle")
    page.screenshot(path=str(SHOTS / "step_01.png"))
```

**Rules:**

- **Filenames always match step numbers**: Step 8 uses `step_08.png`, no exceptions. If two steps show
  the same state, **copy the file to both names** rather than reusing one filename across steps —
  off-by-one screenshot bugs on rebuild are otherwise near-inevitable.
- Capture the state **in which the reader acts** (the screen *before* the click, with the target
  visible). For verification steps, capture the *after* state being verified.
- Wait for the UI to settle (`wait_for_load_state`, or wait on a specific selector) before capturing —
  half-rendered spinners make useless documentation.
- **Authentication:** unless the documented process *is* logging in, sign-in is a Prerequisites bullet
  ("You are signed in to <app>"), not a step. Capture post-login using Playwright `storage_state`.
- **Credential hygiene:** credentials live in an untracked `.env`; they must never appear in a
  committed script, a screenshot, or the finished document.
- **Privacy:** only test/demo data may appear. If real names, emails, phone numbers, or
  health/financial data are on screen, replace them with seeded demo records before capturing, or
  redact them during annotation. Exclude browser chrome that leaks unrelated internal URLs.

**Size gate — run before annotating, and treat a failure as a recapture, never a resize:**

```python
from sop_annotate import check_sizes
check_sizes("sop-workspace/screenshots/sop_003")   # raises unless every file is 1920x1080
```

Every screenshot must be **exactly 1920×1080**. A mismatch almost always means
`device_scale_factor != 1`. Annotation coordinates are absolute pixels; mixed sizes silently
misplace every box.

---

# Phase 4 — Annotation

Annotate every screenshot so the reader's eye lands on precisely the element the step is about.

## 4a. Calibrate first — never guess coordinates

```python
from sop_annotate import grid_all, zoom_crop
grid_all("sop-workspace/screenshots/sop_003", "sop-workspace/inspection/sop_003")
```

This writes a copy of each screenshot with a **labelled pixel grid**: thin grey lines every 100 px,
heavier red lines every 500 px, with x labels along the top edge and y labels down the left edge.
Read each target element's pixel box off the grid. For small controls, use `zoom_crop(...)` — a
magnified crop with a 10 px grid whose labels stay in original-image coordinates, so the numbers can
be used directly.

## 4b. Annotation format

```python
steps = {
    "step_01.png": [
        {"box": (28, 78, 400, 110),                  # highlight rectangle
         "arrow": ((520, 200), (410, 100)),          # (tail), (tip) — head lands on the tip
         "label": 'Page title: "Clients"',
         "label_pos": (530, 170)},                   # chip TOP-LEFT corner
        {"box": (30, 900, 300, 940), "border": 4},   # context-only box: no arrow, no label
    ],
}
```

- Each screenshot may carry **one or more labeled targets** (box + arrow + label each) when a step
  genuinely involves several elements. Purely contextual elements get a **box only**, with the thinner
  4 px border.
- Label text is short and concrete — `Click the "Retention" tab`, `Column A: "Import date"`. It names
  the element; it does not repeat the step instructions.
- Output goes to `screenshots_annotated/sop_<nnn>/` with **unchanged filenames**. The build script
  embeds only annotated versions.

## 4c. Exact visual spec

| Element | Spec |
|---|---|
| Highlight fill | RGBA `(255, 235, 59, 90)` translucent yellow, drawn on the **overlay** layer |
| Highlight border | `(255, 152, 0, 255)` orange, **6 px** default; `border` key overrides; context boxes use **4 px** |
| Arrow | `(220, 38, 38, 255)` red, line width **7 px**, solid triangular head **26 px** long, half-angle **π/7**, tip on the target |
| Label chip | Fill `(255, 235, 59, 255)`, border `(120, 80, 0, 255)` **3 px**, black text, **font size 28**, padding **14 × 8 px** |
| Chip shadow | Same rect offset **+4, +4**, fill RGBA `(0, 0, 0, 110)` |
| Chip geometry | `label_pos` is the chip's **top-left**; chip = text bbox + padding; draw text at `(x + pad_x, y + pad_y - bbox_top)` — subtracting the font's top bearing, or the text sits visibly low |
| Font | Bold, resolved in order: `arialbd.ttf`, `Arial Bold.ttf`, `segoeuib.ttf`, `DejaVuSans-Bold.ttf`, `LiberationSans-Bold.ttf`. **If none loads, abort** — never fall back to `ImageFont.load_default()`, whose bitmap glyphs are illegible at this scale while the pipeline still reports success |
| Compositing | base → `alpha_composite` overlay (fills) → `alpha_composite` top layer (borders, arrows, labels) → save optimized RGB PNG |

## 4d. Verify visually

After annotating, **open each output image and look at it**. Confirm every box sits on its element and
no arrow or chip covers the content it points at. Fix coordinates and re-run until correct. This step
is not optional — misplaced annotations are the single most common defect in generated SOPs.

---

# Phase 5 — Links catalog (`links.json`)

One `links.json` per workspace is the URL catalog **shared by all SOPs**. Every external resource the
SOP mentions gets one entry:

```json
{
  "_description": "Central URL catalog for all SOPs. Keys are short identifiers reused across build scripts.",
  "client_admin": {
    "name": "Client Admin Panel",
    "type": "Web app",
    "access": "Edit",
    "url": "https://app.example.com/admin/clients",
    "description": "Where client records are created and edited. Used in SOP-003.",
    "deep_links": {
      "archived": "https://app.example.com/admin/clients?filter=archived"
    }
  }
}
```

- `name` — exact human title · `type` — "Web app", "Google Sheets", … · `access` — the **minimum**
  level needed ("View" / "Edit") · `description` — one sentence on what it is and when it's used.
- `deep_links` is optional, for sub-pages or tabs. Store **complete URLs**. (For Google Sheets that
  means `…/edit#gid=<gid>`; note the raw `gid` value may be a negative signed integer such as
  `-221248376`, so store the assembled URL rather than reconstructing it from a bare number.)
- **Keys must be `snake_case` matching `[a-z0-9_]+`.** The marker parser's regex is `\w+`, so a key
  like `client-admin` silently fails to match and leaks raw `[[…]]` text into the finished document.
- In body text, reference resources **only** through the marker syntax `[[key|display text]]`. Never
  paste a raw URL into prose.
- New SOPs **add keys**; never duplicate an existing resource under a second key.

---

# Phase 6 — Document build

Write `build_sop_<nnn>.py` using `python-docx` (importing `sop_docx` if the kit is present). It must
reproduce this document model exactly.

## Global setup

- Base font **Arial 11 pt**, applied to the `Normal` style **and** to the `w:rFonts`
  ascii/hAnsi/cs/eastAsia attributes so Word does not substitute.
- Headings Arial bold, navy `#1F3864`, same `rFonts` treatment: **H1 18 pt · H2 14 pt · H3 12 pt**.
- Page margins **1 inch** on all four sides.
- **Header** (every page): SOP title (`SOP-003 — Client Intake`), right-aligned, Arial 9 pt, grey `#595959`.
- **Footer** (every page): centered `Page ` + a real Word `PAGE` field. Style **both** the literal run
  and the field run 9 pt grey `#595959` — leaving the field run unstyled makes the number render
  11 pt black next to 9 pt grey text.
- **Every table in the document is center-aligned** (screenshot frames, callouts, metadata, tools,
  revision history). Standard cell borders: single, `#BFBFBF`, size 6.

## Section order (fixed — do not reorder or omit)

| # | Section |
|---|---|
| 1 | Title page |
| 2 | Table of Contents |
| 3 | Purpose |
| 4 | Scope |
| 5 | Prerequisites |
| 6 | Tools & Access Required |
| 7 | Definitions / Glossary |
| 8 | Procedure (Parts → Steps) |
| 9 | Troubleshooting |
| 10 | Revision History |

### 1. Title page

Centered, pushed down **6 empty paragraphs**:

- `STANDARD OPERATING PROCEDURE` — bold, 14 pt, grey `#595959`
- SOP number (`SOP-003`) — bold, **28 pt**, navy `#1F3864`
- SOP short title — bold, **24 pt**, navy `#1F3864`
- **one empty paragraph**
- Subtitle: one line on what the procedure accomplishes (may wrap) — italic, 12 pt, grey
- **6 empty paragraphs**, then a centered 4×2 **metadata table**: `Version`, `Date Created`,
  `Prepared by`, `Process owner`. Left column navy fill / white bold text / 2″ wide; right column 3″.
  `Prepared by` and `Process owner` stay **blank** for the human owner. All cells bordered.
- Page break.

**Date semantics:** `Date Created` is fixed at the **v1.0 date forever** — revisions change only the
`Version` cell and append a Revision History row. All dates use the format **`Month D, YYYY`**
(e.g. `July 28, 2026`) for cross-SOP consistency.

### 2. Table of Contents

H1 "Table of Contents", then a real Word **TOC field** (`TOC \o "1-3" \h \z \u`) with the placeholder
text *"Right-click and select 'Update Field' to populate the Table of Contents."* Page break after.

### 3. Purpose

H1 + one paragraph: what this SOP does and **why it matters** — state the concrete consequence of
skipping or botching it ("missing this single step causes every value to display as 0%, which feeds
incorrect leadership reports"). Use `[[key|…]]` markers for every resource named.

### 4. Scope

H1 + one paragraph: who performs this (roles), when and how often, and what downstream outcome it protects.

### 5. Prerequisites

H1 + bulleted list (`List Bullet`): every account, permission, tool, and precondition — including the
"you are signed in" bullet. Include a **stop condition** where one exists ("Confirmation that the
master dashboard has just been updated — if it has not, stop and wait").

### 6. Tools & Access Required

H1 + an intro paragraph telling the reader to click each link and verify access **before** starting
("If you get a 'Request access' screen, contact your operations lead"). Then a 4-column table:

`Tool | Type | Access Needed | Open` — header row navy fill, white bold 10 pt; body 10 pt; last column
a centered clickable **`↗ Open`** hyperlink. Column widths **2.8″ / 1.2″ / 1.1″ / 0.8″**.

The table contains **only the `links.json` keys this SOP actually references**, in first-use order —
not the whole shared catalog. Follow the table with **one empty paragraph**.

### 7. Definitions / Glossary

H1, then one paragraph per term: **bold term** + ` — ` + plain-language definition. Terms that are
linkable resources get a **hyperlink on the term itself** instead of bold (entries are
`(term, link_key_or_None, definition)`). Define every proper noun, tab name, formula, and metric a
novice could stumble on — including domain vocabulary ("Retention rate — the percentage of clients
who…"). Page break after.

### 8. Procedure

H1 "Procedure" + framing paragraph: *"Follow these steps in order. Each step contains exactly one
action. Do not skip any step — even the verification-only steps are required to confirm that the
previous action worked."*

Then per Part: H2 `Part A: <Title>`. Per step, in this order:

1. H3 `Step N: <Imperative title>`
2. The **annotated** screenshot, embedded inside a **1×1 table** for a visible frame: cell border
   `#9E9E9E` size 8, table center-aligned, cell **vertically centered**, image centered, width **6.2″**.
3. `What to do:` — label bold navy `#1F3864`, then the action text (with `[[key|…]]` markers).
4. `What you should see:` — same label styling, then the observable result.
5. Optional **callout** — a **6.4″** 1×1 table, shaded, bordered `#BFBFBF`. Label run **bold at the
   default 11 pt**, followed by **two spaces**, then the body run at **10 pt**:

| Callout | Label | Fill |
|---|---|---|
| Warning | `⚠  Watch out:` | `#FFF2CC` light yellow |
| Tip | `💡  Tip:` | `#DEEBF7` light blue |
| Acceptance note | `✅  Tip:` | `#E2EFDA` light green |

The **final step is always a wrap-up** ("close the tabs / log out / you are done") stating that the
procedure is complete and what is now true. Page break after the last step.

### 9. Troubleshooting

H1, then Q/A pairs from the failure modes you actually observed in Phase 1:
`Q: <symptom in the user's words>` (bold), then `A: <diagnosis + exact recovery steps>`, blank
paragraph between pairs. **Minimum 3 entries.** Every "Watch out" callout describing a failure that
really occurs should have a matching entry.

### 10. Revision History

H1 + table `Version | Date | Author | Changes Made` — navy/white bold header, bordered cells, widths
**0.9″ / 1.5″ / 1.4″ / 2.6″**. First row: `1.0 | <build date> | <blank> | Initial release of SOP-NNN <Title>.`

## Raw-OXML notes (only needed if you are not using `sop_docx.py`)

These cannot be done through the high-level python-docx API:

- **`rFonts` hardening** on `Normal` and each `Heading` style (ascii/hAnsi/cs/eastAsia).
- **PAGE field** = `w:fldChar` begin + `w:instrText` `PAGE` + `w:fldChar` end.
  **TOC field** = begin + `instrText` + **separate** + placeholder `w:t` + end.
- **Cell shading** = `w:shd` with `w:val="clear"`, `w:color="auto"`, `w:fill="<hex>"`. `w:val` is
  required; emitting only `w:fill` yields OXML Word may reject.
- **Cell borders** = `w:tcBorders`, single, `#BFBFBF` size 6 (or `#9E9E9E` size 8 for screenshot frames).
- **Hyperlinks** = external relationship + `w:hyperlink`; run styled color `0563C1`, single underline,
  Arial, `w:sz` in **half-points** (pt × 2).
- **Marker parser** = regex `\[\[(\w+)\|([^\]]+)\]\]`; plain runs between matches, hyperlink runs for
  matches. **Raise on an unresolved key** rather than letting `[[…]]` reach the document.

---

# Writing style rules

1. **Audience:** a brand-new employee on day one, with no knowledge of the app, the org's tools, or
   the domain. Anything they wouldn't know goes in the Glossary.
2. **Voice:** second person; imperative for actions ("Click once on cell A1"), present tense for
   descriptions.
3. **Exactness over brevity.** Name UI elements by their exact visible text in quotes. Give exact
   locations ("the row of tabs at the very bottom of the window"), exact keystrokes ("Ctrl+T on
   Windows, ⌘+T on Mac"), and exact formats with an example.
4. **"What you should see" must be falsifiable** — exact titles, which tab is white vs grey, sample
   values ("percentages such as 52.2%, 76.0%"), and what failure looks like ("if every value is
   exactly 0.0%, the date was not recognised — go back to Step 11").
5. **Anticipate confusion.** Whenever two similar controls sit near each other, say so ("Do not click
   'Insert Attendance' by mistake — the two tabs are adjacent and have very similar names").
6. **Protect the data.** Any step where a wrong keystroke destroys something gets a Watch-out callout
   **with the recovery action** ("press Ctrl+Z immediately to undo").
7. **Explain the why for critical steps**, so readers don't rationalize skipping them.
8. **No dead ends.** Every warning and every troubleshooting answer ends with what to do next — even
   if that is "stop and contact your operations lead".

---

# Phase 7 — QA

## Programmatic (no Word installation required)

```python
from sop_docx import verify_docx
print(verify_docx("sop-workspace/output/SOP-003_Client_Intake.docx"))
```

This unzips the `.docx`, asserts the TOC field (`TOC \o "1-3"` in `word/document.xml`) and PAGE field
(in `word/footer*.xml`) are real fields, confirms zero surviving `[[…]]` markers, counts embedded
images and hyperlinks, and round-trips the file through `Document()` to prove it opens cleanly.

## Manual checklist — fix and rebuild until all pass

- [ ] Every step has exactly one action; numbering is continuous; every step has a screenshot (except
      a final wrap-up step, where its absence is deliberate).
- [ ] Embedded images are the **annotated** versions, 6.2″ wide, framed — and you have **looked at
      each one** to confirm the annotations point at the right elements.
- [ ] Screenshot count matches step count, and `step_NN.png` matches Step N.
- [ ] No real personal, client, health, or financial data is visible anywhere.
- [ ] No credentials appear in screenshots, committed scripts, or the document.
- [ ] Every `[[key|…]]` resolved; every referenced resource appears in the Tools table; every URL is
      the **production** URL and opens the right target.
- [ ] All 10 sections present and in order.
- [ ] Every proper noun, tab, and metric used in the steps is defined in the Glossary.
- [ ] Every Watch-out has a recovery path; Troubleshooting covers the failures you actually observed.
- [ ] Fonts and colors match spec (Arial 11; navy `#1F3864`; grey `#595959`; exact callout fills).
- [ ] Saved as `output/SOP-<NNN>_<Short_Name>.docx`.

## Deliver

Report to the user: the output path and file size, a one-paragraph summary of the documented
procedure, the list of fields a human must fill in (**Prepared by**, **Process owner**), and any
discrepancies you found between the code and the app's live behavior.
