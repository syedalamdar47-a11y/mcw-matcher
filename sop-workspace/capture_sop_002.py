"""Capture screenshots for SOP-002 'Update a Clinician's Availability & Priority'."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8010/index.html"
HERE = Path(__file__).parent
SHOTS = HERE / "screenshots" / "sop_002"
SHOTS.mkdir(parents=True, exist_ok=True)
BOXES_OUT = HERE / "boxes_sop_002.json"

STEPS = [
    # step_01 — one card shown, before opening the inline editor
    ("state.search='Alex Rivera'; state.editingCardId=null; state.cardEdit=null; render();",
     '[data-action="card-edit-start"]', False),
    # step_02 — inline editor open; Availability dropdown
    ("handleAction('card-edit-start', {dataset:{id:'demo1'}}, new Event('click'));",
     '[data-action="card-edit-accepting"]', False),
    # step_03 — availability changed; Priority dropdown
    ("state.cardEdit.accepting='Not Accepting'; render();",
     '[data-action="card-edit-priority"]', False),
    # step_04 — priority changed; Admin note field
    ("state.cardEdit.priority='Low Priority'; render();",
     '[data-action="card-edit-notes"]', False),
    # step_05 — note typed; Save button
    ("state.cardEdit.notes='Full through August - not taking new clients'; render();",
     '[data-action="card-edit-save"]', False),
    # step_06 — saved; card shows the updated badges
    ("handleAction('card-edit-save', {dataset:{id:'demo1'}}, new Event('click'));",
     '.card', False),
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
