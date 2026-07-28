"""
sop_annotate.py — screenshot annotation toolkit for SOPs in the MCW house style.

Yellow translucent highlight boxes, red arrows, and yellow label chips, composited
so that fills sit under the borders/arrows/labels.

Also provides the two calibration utilities the workflow depends on:
  grid_overlay()  — labelled pixel grid, used to read off annotation coordinates
  check_sizes()   — hard gate that every screenshot is exactly the expected size

Requires: pillow  (pip install pillow)
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# --------------------------------------------------------------------------
# House-style constants — do not change without updating the spec.
# --------------------------------------------------------------------------
YELLOW_FILL = (255, 235, 59, 90)      # translucent highlight fill (overlay layer)
YELLOW_BORDER = (255, 152, 0, 255)    # orange highlight border (top layer)
RED_ARROW = (220, 38, 38, 255)
LABEL_BG = (255, 235, 59, 255)
LABEL_BORDER = (120, 80, 0, 255)
LABEL_TXT = (0, 0, 0, 255)
LABEL_SHADOW = (0, 0, 0, 110)

PRIMARY_BORDER_W = 6      # boxes that carry an arrow + label
SECONDARY_BORDER_W = 4    # context-only boxes
ARROW_W = 7
ARROW_HEAD_LEN = 26
ARROW_HEAD_ANGLE = math.pi / 7
LABEL_FONT_SIZE = 28
LABEL_PAD_X, LABEL_PAD_Y = 14, 8
SHADOW_OFFSET = 4

EXPECTED_SIZE = (1920, 1080)

# Bold-first font resolution, cross-platform. No bitmap fallback: an illegible
# label is worse than a loud failure.
FONT_CANDIDATES = (
    "arialbd.ttf", "Arial Bold.ttf",                      # Windows / macOS
    "segoeuib.ttf",                                        # Windows
    "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf",      # Linux
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",   # macOS absolute
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
)


def load_font(size: int = LABEL_FONT_SIZE) -> ImageFont.FreeTypeFont:
    for name in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    raise RuntimeError(
        "No bold TrueType font found for annotation labels. Install one of: "
        + ", ".join(FONT_CANDIDATES)
        + " — do NOT fall back to ImageFont.load_default(); its bitmap glyphs are "
          "illegible at screenshot scale."
    )


# --------------------------------------------------------------------------
# Drawing primitives
# --------------------------------------------------------------------------
def draw_highlight(overlay_draw, top_draw, box, border_width: int = PRIMARY_BORDER_W) -> None:
    overlay_draw.rectangle(list(box), fill=YELLOW_FILL)
    top_draw.rectangle(list(box), outline=YELLOW_BORDER, width=border_width)


def draw_arrow(draw, start, end, color=RED_ARROW, width: int = ARROW_W,
               head_len: int = ARROW_HEAD_LEN, angle_offset: float = ARROW_HEAD_ANGLE) -> None:
    """Arrow from `start` to `end`; the head (solid triangle) sits at `end`."""
    sx, sy = start
    ex, ey = end
    draw.line([start, end], fill=color, width=width)
    angle = math.atan2(ey - sy, ex - sx)
    h1 = (ex - head_len * math.cos(angle - angle_offset),
          ey - head_len * math.sin(angle - angle_offset))
    h2 = (ex - head_len * math.cos(angle + angle_offset),
          ey - head_len * math.sin(angle + angle_offset))
    draw.polygon([(ex, ey), h1, h2], fill=color)


def draw_label(draw, pos, text: str, font) -> None:
    """`pos` is the chip's TOP-LEFT corner, not the text baseline."""
    x, y = pos
    bb = draw.textbbox((0, 0), text, font=font)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    box = (x, y, x + tw + 2 * LABEL_PAD_X, y + th + 2 * LABEL_PAD_Y)
    draw.rectangle(
        (box[0] + SHADOW_OFFSET, box[1] + SHADOW_OFFSET,
         box[2] + SHADOW_OFFSET, box[3] + SHADOW_OFFSET),
        fill=LABEL_SHADOW,
    )
    draw.rectangle(box, fill=LABEL_BG, outline=LABEL_BORDER, width=3)
    # subtract bb[1] to cancel the font's top bearing, else text sits too low
    draw.text((x + LABEL_PAD_X, y + LABEL_PAD_Y - bb[1]), text, fill=LABEL_TXT, font=font)


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------
def annotate(img_path, out_path, annotations, label_font_size: int = LABEL_FONT_SIZE) -> Path:
    """Annotate one screenshot.

    `annotations` is a list of dicts, each of which may contain:
        box        (x0, y0, x1, y1)   highlight rectangle
        border     int               border width (default 6; use 4 for context boxes)
        arrow      ((sx, sy), (ex, ey))  red arrow, head at the second point
        label      str               chip text
        label_pos  (x, y)            chip top-left corner
    """
    img_path, out_path = Path(img_path), Path(out_path)
    img = Image.open(img_path).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    top = Image.new("RGBA", img.size, (0, 0, 0, 0))
    overlay_draw, top_draw = ImageDraw.Draw(overlay), ImageDraw.Draw(top)
    font = load_font(label_font_size)

    for a in annotations:
        if "box" in a:
            draw_highlight(overlay_draw, top_draw, a["box"], a.get("border", PRIMARY_BORDER_W))
        if "arrow" in a:
            draw_arrow(top_draw, a["arrow"][0], a["arrow"][1])
        if "label" in a:
            if "label_pos" not in a:
                raise ValueError(f"Annotation has 'label' but no 'label_pos': {a}")
            draw_label(top_draw, a["label_pos"], a["label"], font)

    out = Image.alpha_composite(img, overlay)     # fills under
    out = Image.alpha_composite(out, top)         # borders/arrows/labels over
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.convert("RGB").save(out_path, "PNG", optimize=True)
    return out_path


def annotate_all(src_dir, out_dir, steps: dict, label_font_size: int = LABEL_FONT_SIZE) -> list[Path]:
    """steps: {"step_01.png": [ann, ...], ...}. Missing source files are a hard error."""
    src_dir, out_dir = Path(src_dir), Path(out_dir)
    written = []
    missing = [n for n in steps if not (src_dir / n).exists()]
    if missing:
        raise FileNotFoundError(f"Screenshots missing from {src_dir}: {', '.join(sorted(missing))}")
    for name, anns in steps.items():
        written.append(annotate(src_dir / name, out_dir / name, anns, label_font_size))
        print(f"  -> {name}")
    return written


def grid_overlay(img_path, out_path, step: int = 100, major: int = 500) -> Path:
    """Render a labelled pixel grid over a screenshot, for reading off coordinates.

    Thin grey lines every `step` px, heavier red lines every `major` px, with x
    labels along the top edge and y labels down the left edge.
    """
    img_path, out_path = Path(img_path), Path(out_path)
    img = Image.open(img_path).convert("RGBA")
    w, h = img.size
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    try:
        font = load_font(16)
    except RuntimeError:
        font = ImageFont.load_default()  # labels only; acceptable for calibration

    for x in range(0, w, step):
        is_major = x % major == 0
        d.line([(x, 0), (x, h)], fill=(255, 0, 0, 150) if is_major else (0, 0, 0, 70),
               width=2 if is_major else 1)
        d.text((x + 3, 3), str(x), fill=(255, 0, 0, 255) if is_major else (0, 0, 0, 200), font=font)
    for y in range(0, h, step):
        is_major = y % major == 0
        d.line([(0, y), (w, y)], fill=(255, 0, 0, 150) if is_major else (0, 0, 0, 70),
               width=2 if is_major else 1)
        d.text((3, y + 3), str(y), fill=(255, 0, 0, 255) if is_major else (0, 0, 0, 200), font=font)

    out = Image.alpha_composite(img, layer)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.convert("RGB").save(out_path, "PNG", optimize=True)
    return out_path


def grid_all(src_dir, out_dir, step: int = 100, major: int = 500) -> list[Path]:
    src_dir, out_dir = Path(src_dir), Path(out_dir)
    return [grid_overlay(p, out_dir / p.name, step, major)
            for p in sorted(src_dir.glob("step_*.png"))]


def zoom_crop(img_path, out_path, box, scale: int = 3) -> Path:
    """Magnified crop with its own local grid — for pinning down small UI elements.

    `box` is in ORIGINAL image coordinates; grid labels stay in original coordinates
    so the numbers you read can be used directly in annotations.
    """
    img_path, out_path = Path(img_path), Path(out_path)
    img = Image.open(img_path).convert("RGB")
    x0, y0, x1, y1 = box
    crop = img.crop(box).resize(((x1 - x0) * scale, (y1 - y0) * scale), Image.LANCZOS)
    d = ImageDraw.Draw(crop)
    try:
        font = load_font(14)
    except RuntimeError:
        font = ImageFont.load_default()
    for x in range(x0 - x0 % 10, x1, 10):
        cx = (x - x0) * scale
        major = x % 50 == 0
        d.line([(cx, 0), (cx, crop.height)], fill=(255, 0, 0) if major else (160, 160, 160), width=1)
        if major:
            d.text((cx + 2, 2), str(x), fill=(255, 0, 0), font=font)
    for y in range(y0 - y0 % 10, y1, 10):
        cy = (y - y0) * scale
        major = y % 50 == 0
        d.line([(0, cy), (crop.width, cy)], fill=(255, 0, 0) if major else (160, 160, 160), width=1)
        if major:
            d.text((2, cy + 2), str(y), fill=(255, 0, 0), font=font)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    crop.save(out_path, "PNG", optimize=True)
    return out_path


def check_sizes(folder, expected: tuple[int, int] = EXPECTED_SIZE) -> dict:
    """Hard gate before annotation: every screenshot must be exactly `expected`.

    A deviation almost always means device_scale_factor != 1 in the capture script.
    Recapture — never resize, and never plan coordinates against mixed sizes.
    """
    folder = Path(folder)
    files = sorted(folder.glob("step_*.png"))
    if not files:
        raise FileNotFoundError(f"No step_*.png files found in {folder}")
    sizes = {}
    wrong = []
    for f in files:
        with Image.open(f) as im:
            sizes[f.name] = im.size
        if sizes[f.name] != expected:
            wrong.append(f"{f.name}={sizes[f.name][0]}x{sizes[f.name][1]}")
    if wrong:
        raise ValueError(
            f"Screenshots are not {expected[0]}x{expected[1]}: {', '.join(wrong)}. "
            "Recapture with device_scale_factor=1 and a 1920x1080 viewport."
        )
    return sizes
