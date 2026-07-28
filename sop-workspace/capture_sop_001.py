"""
Capture screenshots for SOP-001 "Add a New Clinician".
Drives the LOCAL DEMO instance (fake clinicians, no live DB) at 1920x1080,
walking the add-clinician flow and recording the exact pixel box of each
target element so annotation coordinates are measured, never guessed.

Run:  python sop-workspace/capture_sop_001.py
"""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8010/index.html"
HERE = Path(__file__).parent
SHOTS = HERE / "screenshots" / "sop_001"
SHOTS.mkdir(parents=True, exist_ok=True)
BOXES_OUT = HERE / "boxes_sop_001.json"

# Each step: (setup JS run before the shot, target selector, scroll-into-view?)
# The setup drives state.editorDraft + render() so the screenshot shows exactly
# the state the reader acts in (prior fields filled, this step's target visible).
STEPS = [
    # step_01 — board, before opening the form
    ("closeEditor(); render();", '[data-action="editor-open"][data-id="__new__"]', False),
    # step_02 — form open, empty; Name is the target
    ("handleAction('editor-open', {dataset:{id:'__new__'}}, new Event('click'));", "#ed-name", False),
    # step_03 — Name filled; Profile target
    ("state.editorDraft.name='Test Clinician 01'; render();", "#ed-profile", False),
    # step_04 — Profile filled; Provider type target
    ("state.editorDraft.profile='Test Clinician 01, LMHC'; render();", ".ed-type", False),
    # step_05 — type chosen (Therapy default); Schedule target
    ("state.editorDraft.type='therapy'; render();", "#ed-schedule", False),
    # step_06 — Schedule filled; Offices target
    ("state.editorDraft.schedule='Mon-Fri'; render();",
     '.ed-field:has(input[data-action="editor-office"]) .ed-checks', False),
    # step_07 — DTSP checked; Session groups target
    ("state.editorDraft.offices=['DTSP']; render();",
     '.ed-field:has(input[data-action="editor-group"]) .ed-checks', False),
    # step_08 — Individuals checked; Individual rate target
    ("state.editorDraft.groups=['Individuals']; render();", "#ed-indiv", False),
    # step_09 — rate filled; Specialties checklist target
    ("state.editorDraft.indiv='185'; render();",
     '.ed-check-grid:has(input[data-action="editor-spec-toggle"])', True),
    # step_10 — specialties checked; Modalities checklist target
    ("state.editorDraft.specialties=['Anxiety','Depression','Trauma','Self-esteem']; render();",
     '.ed-check-grid:has(input[data-action="editor-mod-toggle"])', True),
    # step_11 — modalities checked; Add clinician (save) target
    ("state.editorDraft.modalities=['CBT','DBT','Mindfulness-Based Therapy']; render();",
     '[data-action="editor-save"]', True),
    # step_12 — saved; new card on the board (add the demo record directly, since
    # the real save path talks to the DB which the local demo instance lacks)
    ("""state.clinicians.push({id:'test_clinician_01', name:'Test Clinician 01',
        profile:'Test Clinician 01, LMHC', type:'therapy', offices:['DTSP'], virtual:false,
        indiv:185, couples:null, family:null, schedule:'Mon-Fri', accepting:'Needs Clients',
        priority:'Medium Priority', groups:['Individuals'],
        modalities:['CBT','DBT','Mindfulness-Based Therapy'],
        specialties:['Anxiety','Depression','Trauma','Self-esteem'], notes:''});
        closeEditor(); state.search='Test Clinician 01'; render();""",
     '.card', False),
]


def box_of(page, selector, scroll):
    if scroll:
        page.eval_on_selector(selector, "el => el.scrollIntoView({block:'center'})")
        page.wait_for_timeout(250)
    bb = page.eval_on_selector(selector, """el => {
        const r = el.getBoundingClientRect();
        return {x:r.x, y:r.y, w:r.width, h:r.height};
    }""")
    return bb


def main():
    boxes = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
        page = ctx.new_page()
        page.on("dialog", lambda d: d.dismiss())
        page.goto(BASE)
        page.wait_for_selector("#login-pw")
        # log in (local demo password) — not a documented step, just a prerequisite
        page.fill("#login-pw", "mcw2025")
        page.click(".login-btn")
        page.wait_for_selector('[data-action="editor-open"][data-id="__new__"]', timeout=8000)
        page.wait_for_timeout(400)

        for i, (setup, selector, scroll) in enumerate(STEPS, start=1):
            page.evaluate(setup)
            page.wait_for_timeout(300)
            name = f"step_{i:02d}.png"
            bb = box_of(page, selector, scroll)
            page.screenshot(path=str(SHOTS / name))
            # pad the box a little so the highlight frames the element
            pad = 6
            boxes[name] = [round(bb["x"] - pad), round(bb["y"] - pad),
                           round(bb["x"] + bb["w"] + pad), round(bb["y"] + bb["h"] + pad)]
            print(f"  {name}  target box {boxes[name]}")

        browser.close()
    BOXES_OUT.write_text(json.dumps(boxes, indent=2))
    print(f"\nWrote {len(boxes)} screenshots to {SHOTS}")
    print(f"Wrote boxes to {BOXES_OUT}")


if __name__ == "__main__":
    main()
