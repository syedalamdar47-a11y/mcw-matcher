"""Annotate SOP-003 screenshots (explicit per-step chip placement)."""
import json, sys
from pathlib import Path
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "sop-kit"))
from sop_annotate import annotate_all, check_sizes

SRC = HERE / "screenshots" / "sop_003"
OUT = HERE / "screenshots_annotated" / "sop_003"
b = json.loads((HERE / "boxes_sop_003.json").read_text())

# name: (label, label_pos, (arrow_tail, arrow_tip))
CFG = {
    "step_01.png": ('Click "Edit details"', (600, 335), ((595, 368), (b["step_01.png"][2], 368))),
    "step_02.png": ('Click "Deactivate"', (1285, 895), ((1280, 925), (1150, 955))),
    "step_03.png": ('Now shows "0" - clinician hidden', (330, 8), ((325, 24), (b["step_03.png"][2], 24))),
    "step_04.png": ('Click "Update all clinicians"', (250, 942), ((245, 986), (b["step_04.png"][2], 986))),
    "step_05.png": ('Click "Reactivate"', (1285, 878), ((1280, 900), (b["step_05.png"][2], 900))),
    "step_06.png": ("Clinician is back on the board", (620, 62), ((615, 150), (b["step_06.png"][2], 150))),
}
steps = {n: [{"box": tuple(b[n]), "arrow": arrow, "label": label, "label_pos": lp}]
         for n, (label, lp, arrow) in CFG.items()}

if __name__ == "__main__":
    check_sizes(SRC)
    annotate_all(SRC, OUT, steps)
    print("annotated SOP-003")
