"""Capture screenshots for SOP-003 'Deactivate or Remove a Clinician'."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8010/index.html"
HERE = Path(__file__).parent
SHOTS = HERE / "screenshots" / "sop_003"
SHOTS.mkdir(parents=True, exist_ok=True)
BOXES_OUT = HERE / "boxes_sop_003.json"

STEPS = [
    # step_01 — one card; the "Edit details" button
    ("state.search='Alex Rivera'; closeEditor(); render();",
     '[data-action="editor-open"][data-id="demo1"]', False),
    # step_02 — editor open; the "Deactivate" button
    ("handleAction('editor-open', {dataset:{id:'demo1'}}, new Event('click'));",
     '[data-action="editor-deactivate"]', True),
    # step_03 — after deactivating, searching the name shows 0 results
    ("state.clinicians.find(x=>x.id==='demo1').active=false; closeEditor(); state.search='Alex Rivera'; render();",
     ".count-text", False),
    # step_04 — to restore: the "Update all clinicians" button
    ("state.search=''; render();", '[data-action="admin-open"]', False),
    # step_05 — admin panel Deactivated section; the "Reactivate" button
    ("handleAction('admin-open', document.body, new Event('click'));",
     '[data-action="editor-reactivate"]', True),
    # step_06 — clinician is back on the board
    ("state.clinicians.find(x=>x.id==='demo1').active=true; state.adminOpen=false; state.adminEdits=null; state.search='Alex Rivera'; render();",
     ".card", False),
]


def box_of(page, selector, scroll):
    if scroll:
        page.eval_on_selector(selector, "el => el.scrollIntoView({block:'center'})")
        page.wait_for_timeout(250)
    return page.eval_on_selector(selector,
        "el => {const r=el.getBoundingClientRect(); return {x:r.x,y:r.y,w:r.width,h:r.height};}")


def main():
    boxes = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
        page = ctx.new_page()
        page.on("dialog", lambda d: d.dismiss())
        page.goto(BASE)
        page.wait_for_selector("#login-pw")
        page.fill("#login-pw", "mcw2025")
        page.click(".login-btn")
        page.wait_for_selector(".card", timeout=8000)
        page.wait_for_timeout(400)
        for i, (setup, selector, scroll) in enumerate(STEPS, start=1):
            page.evaluate(setup)
            page.wait_for_timeout(300)
            name = f"step_{i:02d}.png"
            bb = box_of(page, selector, scroll)
            page.screenshot(path=str(SHOTS / name))
            pad = 6
            boxes[name] = [round(bb["x"]-pad), round(bb["y"]-pad), round(bb["x"]+bb["w"]+pad), round(bb["y"]+bb["h"]+pad)]
            print(f"  {name}  {boxes[name]}")
        browser.close()
    BOXES_OUT.write_text(json.dumps(boxes, indent=2))
    print(f"Wrote {len(boxes)} screenshots + boxes")


if __name__ == "__main__":
    main()
