"""
Annotate SOP-001 screenshots. Highlight boxes come from the MEASURED target
boxes captured by capture_sop_001.py; label chips sit in the empty margins
beside the centered modal, with arrows pointing at each target.

Run:  python sop-workspace/annotate_sop_001.py
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "sop-kit"))
from sop_annotate import annotate_all, check_sizes

SRC = HERE / "screenshots" / "sop_001"
OUT = HERE / "screenshots_annotated" / "sop_001"
boxes = json.loads((HERE / "boxes_sop_001.json").read_text())

# label + which margin the chip goes in (targets inside the centered modal)
LABELS = {
    "step_02.png": ("Name", "left"),
    "step_03.png": ("Profile", "right"),
    "step_04.png": ("Provider type", "left"),
    "step_05.png": ("Schedule", "right"),
    "step_06.png": ("Offices", "left"),
    "step_07.png": ("Session groups", "left"),
    "step_08.png": ("Individual rate", "left"),
    "step_09.png": ("Specialties", "left"),
    "step_10.png": ("Modalities", "left"),
    "step_11.png": ('Click "Add clinician"', "left"),
}

steps = {}

# Form-field steps: chip in the margin, arrow to the box edge.
for name, (label, side) in LABELS.items():
    x0, y0, x1, y1 = boxes[name]
    cy = (y0 + y1) // 2
    if side == "left":
        label_pos = (55, max(12, y0 - 4))
        arrow = ((520, y0 + 14), (x0, cy))
    else:  # right margin
        label_pos = (1330, max(12, y0 - 4))
        arrow = ((1325, y0 + 14), (x1, cy))
    steps[name] = [{"box": (x0, y0, x1, y1), "arrow": arrow, "label": label, "label_pos": label_pos}]

# step_01 — the "+ Add clinician" button, bottom-left; chip on the board area to its right
x0, y0, x1, y1 = boxes["step_01.png"]
steps["step_01.png"] = [{
    "box": (x0, y0, x1, y1),
    "arrow": ((300, (y0 + y1) // 2), (x1, (y0 + y1) // 2)),
    "label": 'Click "+ Add clinician"',
    "label_pos": (285, y0 - 48),
}]

# step_12 — the new clinician card; chip to its right
x0, y0, x1, y1 = boxes["step_12.png"]
steps["step_12.png"] = [{
    "box": (x0, y0, x1, y1),
    "arrow": ((640, y0 + 60), (x1, y0 + 40)),
    "label": "New clinician appears",
    "label_pos": (620, y0 + 20),
}]

if __name__ == "__main__":
    check_sizes(SRC)
    written = annotate_all(SRC, OUT, steps)
    print(f"\nAnnotated {len(written)} screenshots -> {OUT}")
