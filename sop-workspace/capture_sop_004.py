"""Capture screenshots for SOP-004 'Invite a Staff Member & Set Their Role'.
The Team screen is shared-mode UI; in the local demo we inject a fake team so
no real staff emails appear."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8010/index.html"
HERE = Path(__file__).parent
SHOTS = HERE / "screenshots" / "sop_004"
SHOTS.mkdir(parents=True, exist_ok=True)
BOXES_OUT = HERE / "boxes_sop_004.json"

FAKE_TEAM = ("state.teamUsers=["
    "{user_id:'u1',email:'owner@mcnultycounseling.com',role:'owner'},"
    "{user_id:'u2',email:'jordan.lead@example.com',role:'admin'},"
    "{user_id:'u3',email:'sam.frontdesk@example.com',role:'frontdesk'},"
    "{user_id:'u4',email:'casey.viewer@example.com',role:'viewer'}];")

STEPS = [
    # step_01 — sidebar; the "Manage team" button
    ("state.search=''; render();", '[data-action="team-open"]', False),
    # step_02 — team modal open; the invite email box
    (FAKE_TEAM + "state.teamOpen=true; state.teamError=''; state.inviteMsg=''; render();",
     "#invite-email", False),
    # step_03 — email typed; the role dropdown
    ("state.inviteEmail='new.staff@mcnultycounseling.com'; render();",
     '[data-action="invite-role-select"]', False),
    # step_04 — role chosen; the Send invite button
    ("state.inviteRole='frontdesk'; render();", '[data-action="invite-send"]', False),
    # step_05 — confirmation message after sending
    ("state.inviteMsg='Invite sent to new.staff@mcnultycounseling.com. They will get an email to set their password.';"
     "state.teamUsers.push({user_id:'u5',email:'new.staff@mcnultycounseling.com',role:'frontdesk'}); render();",
     ".reset-done", False),
    # step_06 — change an existing member's role (row dropdown)
    ("render();", '[data-action="team-role-change"]', True),
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
