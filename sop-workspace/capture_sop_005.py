"""Capture screenshots for SOP-005 'Sync Priorities from the Google Sheet'.
Sheet screenshots come from a demo mock (fake clinicians); app screenshots
come from the local demo app with an injected sync report."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

SHEET = "http://localhost:8010/mock-sheet.html"
APP = "http://localhost:8010/index.html"
HERE = Path(__file__).parent
SHOTS = HERE / "screenshots" / "sop_005"
SHOTS.mkdir(parents=True, exist_ok=True)
BOXES_OUT = HERE / "boxes_sop_005.json"

REPORT = ("state.sheetSyncReport={at:new Date(), updated:"
    "['Sam Taylor: priority -> High Priority','Jordan Bennett: priority -> Low Priority'],"
    "unchanged:3, unmatched:[], invalid:[], missingFromSheet:[], error:null};"
    "state.sheetReportOpen=true; render();")

SHEET_STEPS = [
    # step_01 — the sheet; the "priority" column header
    (None, 'tr.headrow td:nth-child(4)'),
    # step_02 — the specific priority cell being changed
    (None, 'td.sel'),
]
APP_STEPS = [
    # step_03 — the "Sync from Sheet" button in the app
    ("state.search=''; render();", '[data-action="sheet-sync"]', False),
    # step_04 — the sync report
    (REPORT, ".modal", False),
    # step_05 — the clinician card now shows the new priority
    ("state.sheetReportOpen=false; state.clinicians.find(x=>x.id==='demo3').priority='High Priority'; state.search='Sam Taylor'; render();",
     ".card", False),
]


def box_of(page, selector, scroll=False):
    if scroll:
        page.eval_on_selector(selector, "el => el.scrollIntoView({block:'center'})")
        page.wait_for_timeout(250)
    return page.eval_on_selector(selector,
        "el => {const r=el.getBoundingClientRect(); return {x:r.x,y:r.y,w:r.width,h:r.height};}")


def save(page, name, bb, boxes):
    page.screenshot(path=str(SHOTS / name))
    pad = 6
    boxes[name] = [round(bb["x"]-pad), round(bb["y"]-pad), round(bb["x"]+bb["w"]+pad), round(bb["y"]+bb["h"]+pad)]
    print(f"  {name}  {boxes[name]}")


def main():
    boxes = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
        page = ctx.new_page()
        page.on("dialog", lambda d: d.dismiss())

        # --- sheet phase ---
        page.goto(SHEET)
        page.wait_for_selector("td.sel")
        page.wait_for_timeout(300)
        for i, (_, selector) in enumerate(SHEET_STEPS, start=1):
            save(page, f"step_{i:02d}.png", box_of(page, selector), boxes)

        # --- app phase ---
        page.goto(APP)
        page.wait_for_selector("#login-pw")
        page.fill("#login-pw", "mcw2025")
        page.click(".login-btn")
        page.wait_for_selector(".card", timeout=8000)
        page.wait_for_timeout(400)
        for i, (setup, selector, scroll) in enumerate(APP_STEPS, start=3):
            page.evaluate(setup)
            page.wait_for_timeout(300)
            save(page, f"step_{i:02d}.png", box_of(page, selector, scroll), boxes)

        browser.close()
    BOXES_OUT.write_text(json.dumps(boxes, indent=2))
    print(f"Wrote {len(boxes)} screenshots + boxes")


if __name__ == "__main__":
    main()
