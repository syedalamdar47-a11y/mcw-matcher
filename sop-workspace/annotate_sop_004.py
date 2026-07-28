"""Annotate SOP-004 screenshots (explicit per-step chip placement)."""
import json, sys
from pathlib import Path
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "sop-kit"))
from sop_annotate import annotate_all, check_sizes

SRC = HERE / "screenshots" / "sop_004"
OUT = HERE / "screenshots_annotated" / "sop_004"
b = json.loads((HERE / "boxes_sop_004.json").read_text())

CFG = {
    "step_01.png": ('Click "Manage team"', (250, 900), ((300, 946), (b["step_01.png"][2], 946))),
    "step_02.png": ("Type the new person's email", (690, 356), ((790, 402), (840, 418))),
    "step_03.png": ("Choose their role", (955, 356), ((1045, 402), (1050, 418))),
    "step_04.png": ('Click "Send invite"', (1120, 356), ((1215, 402), (1150, 418))),
    "step_05.png": ("Confirmation the invite was sent", (340, 402), ((700, 416), (734, 416))),
    "step_06.png": ("Change a role, or Remove access", (1290, 512), ((1285, 550), (b["step_06.png"][2], 550))),
}
steps = {n: [{"box": tuple(b[n]), "arrow": arrow, "label": label, "label_pos": lp}]
         for n, (label, lp, arrow) in CFG.items()}

if __name__ == "__main__":
    check_sizes(SRC)
    annotate_all(SRC, OUT, steps)
    print("annotated SOP-004")
