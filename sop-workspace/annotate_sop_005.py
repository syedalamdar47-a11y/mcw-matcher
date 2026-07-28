"""Annotate SOP-005 screenshots (sheet + app; explicit per-step placement)."""
import json, sys
from pathlib import Path
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "sop-kit"))
from sop_annotate import annotate_all, check_sizes

SRC = HERE / "screenshots" / "sop_005"
OUT = HERE / "screenshots_annotated" / "sop_005"
b = json.loads((HERE / "boxes_sop_005.json").read_text())

CFG = {
    # sheet: chip below, arrow up to the column header / cell
    "step_01.png": ('The "priority" column', (1090, 455), ((1250, 450), (1250, b["step_01.png"][3]))),
    "step_02.png": ("Change the priority here", (1055, 455), ((1250, 450), (1250, b["step_02.png"][3]))),
    # app
    "step_03.png": ('Click "Sync from Sheet"', (250, 900), ((300, 946), (b["step_03.png"][2], 946))),
    "step_04.png": ("See exactly what changed", (335, 402), ((700, 420), (b["step_04.png"][0], 420))),
    "step_05.png": ("Card now shows the new priority", (620, 62), ((615, 150), (b["step_05.png"][2], 150))),
}
steps = {n: [{"box": tuple(b[n]), "arrow": arrow, "label": label, "label_pos": lp}]
         for n, (label, lp, arrow) in CFG.items()}

if __name__ == "__main__":
    check_sizes(SRC)
    annotate_all(SRC, OUT, steps)
    print("annotated SOP-005")
