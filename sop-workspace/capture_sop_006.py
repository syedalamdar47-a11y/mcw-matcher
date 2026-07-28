"""Capture screenshots for SOP-006 'Reset a Forgotten Password'.
Captured against the real app (shared mode) at :8000 — these are pre-login
screens with no clinician data. State flags are driven directly; no real
email or token is used."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8000/index.html"
HERE = Path(__file__).parent
SHOTS = HERE / "screenshots" / "sop_006"
SHOTS.mkdir(parents=True, exist_ok=True)
BOXES_OUT = HERE / "boxes_sop_006.json"

DEMO_EMAIL = "your.name@mcnultycounseling.com"
STEPS = [
    # step_01 — login screen; the "Forgot password?" link
    ("state.resetMode=false; state.recoveryMode=false; state.loginError=false; render();",
     '[data-action="reset-open"]', False),
    # step_02 — reset request form; the email box
    ("handleAction('reset-open', document.body, new Event('click'));", "#login-email", False),
    # step_03 — email entered; the "Send reset link" button
    (f"state.loginEmail='{DEMO_EMAIL}'; render();",
     'form[data-action="reset-send"] button[type="submit"]', False),
    # step_04 — confirmation that the link was sent
    ("state.resetBusy=false; state.resetSent=true; render();", ".reset-done", False),
    # step_05 — the new-password screen (reached from the email link); new password box
    ("state.resetMode=false; state.resetSent=false; state.recoveryMode=true; render();",
     "#new-pw", False),
    # step_06 — passwords entered; the "Save new password" button
    ("state.recoveryPw='NewPass2026!'; state.recoveryPw2='NewPass2026!'; render();",
     'form[data-action="recovery-save"] button[type="submit"]', False),
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
        page.wait_for_selector('[data-action="reset-open"]', timeout=10000)  # shared-mode login
        page.wait_for_timeout(500)
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
