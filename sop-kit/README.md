# sop-kit

Tested toolkit for generating SOPs in the MCW house style. Used by
`SOP-GENERATION-MASTER-PROMPT.md` — copy **both** into your app's repo.

```bash
python -m pip install python-docx pillow playwright
python -m playwright install chromium
```

```python
import sys; sys.path.insert(0, "path/to/sop-kit")
import sop_docx as D, sop_annotate as A
```

## `sop_annotate.py` — screenshots

| Function | Purpose |
|---|---|
| `check_sizes(folder)` | **Gate before annotating.** Raises unless every `step_*.png` is exactly 1920×1080. |
| `grid_all(src, out)` | Labelled pixel-grid overlays (100 px thin / 500 px heavy) for reading off coordinates. |
| `zoom_crop(img, out, box, scale=3)` | Magnified crop with a 10 px grid; labels stay in original coordinates. |
| `annotate_all(src, out, steps)` | Applies the per-image annotation dicts. Missing source files raise. |

Annotation dict keys: `box` `(x0,y0,x1,y1)` · `border` (6 primary / 4 context) ·
`arrow` `((tail),(tip))` · `label` · `label_pos` (chip top-left).

## `sop_docx.py` — document

```python
d = D.SopDoc(links, "SOP-003 — Client Intake")
d.title_page("SOP-003", "Client Intake", "Creating and verifying a new client record",
             "1.0", "July 28, 2026")
d.table_of_contents()
d.heading("Purpose"); d.rich_para("Covers the [[client_admin|Client Admin Panel]].")
d.heading("Prerequisites"); d.bullets(["Edit access to [[client_admin|the panel]]."])
d.heading("Tools & Access Required"); d.tools_table(["client_admin"])
d.heading("Definitions / Glossary"); d.glossary([("Intake", None, "Onboarding a client.")])
d.heading("Procedure")
d.heading("Part A: Create the Record", 2)
d.step(1, "Open the panel", ann_dir / "step_01.png",
       "Open [[client_admin|Client Admin Panel]].",
       'A page titled "Clients" loads.',
       ("warn", "If you see a login screen, sign in first."))
d.heading("Troubleshooting"); d.troubleshooting([("Save is greyed out.", "A required field is empty.")])
d.heading("Revision History")
d.revision_history([("1.0", "July 28, 2026", "", "Initial release of SOP-003 Client Intake.")])
out = d.save("output/SOP-003_Client_Intake.docx")
print(D.verify_docx(out))
```

Callout kinds: `warn` (yellow) · `tip` (blue) · `ok` (green).
`d.link_keys_used` gives first-use order for `tools_table`.

## Guard rails

These raise rather than producing a quietly-wrong document:

- screenshots that aren't 1920×1080 (`device_scale_factor` mistakes)
- missing screenshot files
- `[[key|…]]` markers with no matching `links.json` key
- no bold TrueType font available (never falls back to illegible bitmap glyphs)
- `verify_docx` — missing TOC/PAGE fields, surviving `[[…]]` markers, corrupt archive
