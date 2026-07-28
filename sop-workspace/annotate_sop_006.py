"""Annotate SOP-006 screenshots — centered login card; chips in the right margin."""
import json, sys
from pathlib import Path
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "sop-kit"))
from sop_annotate import annotate_all, check_sizes

SRC = HERE / "screenshots" / "sop_006"
OUT = HERE / "screenshots_annotated" / "sop_006"
b = json.loads((HERE / "boxes_sop_006.json").read_text())

LABELS = {
    "step_01.png": 'Click "Forgot password?"',
    "step_02.png": "Type your work email",
    "step_03.png": 'Click "Send reset link"',
    "step_04.png": "Then check your email",
    "step_05.png": "Type a new password (twice)",
    "step_06.png": 'Click "Save new password"',
}
CHIP_X = 1200
steps = {}
for name, label in LABELS.items():
    x0, y0, x1, y1 = b[name]
    cy = (y0 + y1) // 2
    steps[name] = [{"box": (x0, y0, x1, y1),
                    "arrow": ((CHIP_X - 5, y0 + 14), (x1, cy)),
                    "label": label, "label_pos": (CHIP_X, max(12, y0 - 4))}]

if __name__ == "__main__":
    check_sizes(SRC)
    annotate_all(SRC, OUT, steps)
    print("annotated SOP-006")
