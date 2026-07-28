"""Annotate SOP-002 screenshots — targets sit on the left card; chips go right."""
import json, sys
from pathlib import Path
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "sop-kit"))
from sop_annotate import annotate_all, check_sizes

SRC = HERE / "screenshots" / "sop_002"
OUT = HERE / "screenshots_annotated" / "sop_002"
boxes = json.loads((HERE / "boxes_sop_002.json").read_text())

LABELS = {
    "step_01.png": 'Click "Edit status & priority"',
    "step_02.png": "Availability",
    "step_03.png": "Priority",
    "step_04.png": "Admin note (optional)",
    "step_05.png": 'Click "Save"',
    "step_06.png": "Updated status shows here",
}
CHIP_X = 640
steps = {}
for name, label in LABELS.items():
    x0, y0, x1, y1 = boxes[name]
    cy = (y0 + y1) // 2
    steps[name] = [{"box": (x0, y0, x1, y1),
                    "arrow": ((CHIP_X - 5, y0 + 14), (x1, cy)),
                    "label": label, "label_pos": (CHIP_X, max(12, y0 - 4))}]

if __name__ == "__main__":
    check_sizes(SRC)
    annotate_all(SRC, OUT, steps)
    print("annotated SOP-002")
