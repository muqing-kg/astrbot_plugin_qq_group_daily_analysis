# -*- coding: utf-8 -*-
"""Fill curated jx3 stickers into square chips for ATRI-style object-fit:cover."""

# Large blank chips happened when source margins (~10% each side) were kept
# verbatim: cover then still shows empty transparent padding. We content-crop
# with a soft pad and cover-fill mildly so faces fill the frame without the
# old 1.06 ear/chin tear.
from __future__ import annotations

import io
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image

ICON_DIR = Path("assets/custom/jx3_qban/icons")
OUT = 160
SOURCE_REVS = ("91f8e4f",)
# Keep in sync with scripts/apply_jx3_qban_template.py FIXED_EMOJI_IDS.
FIXED_EMOJI_IDS: tuple[int, ...] = (1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 12, 20)
SOFT_PAD = 8  # keep soft edge / ears / chin
COVER_ZOOM = 1.02  # mild fill for rounded chips; avoid old 1.06 tear


def content_mask(im: Image.Image) -> np.ndarray:
    arr = np.asarray(im.convert("RGBA"))
    rch, gch, bch, a = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2], arr[:, :, 3]
    opaque = a > 18
    near_white = (rch >= 245) & (gch >= 245) & (bch >= 245) & (a > 200)
    mask = opaque & ~near_white
    if not mask.any():
        mask = opaque
    return mask


def content_bbox(im: Image.Image) -> tuple[int, int, int, int]:
    ys, xs = np.where(content_mask(im))
    if len(xs) == 0:
        return 0, 0, im.width - 1, im.height - 1
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


def face_cover(im: Image.Image, out: int = OUT) -> Image.Image:
    """object-fit:cover into out x out, keep alpha, fill the chip."""
    im = im.convert("RGBA")
    minx, miny, maxx, maxy = content_bbox(im)
    minx = max(0, minx - SOFT_PAD)
    miny = max(0, miny - SOFT_PAD)
    maxx = min(im.width - 1, maxx + SOFT_PAD)
    maxy = min(im.height - 1, maxy + SOFT_PAD)
    crop = im.crop((minx, miny, maxx + 1, maxy + 1))
    tw, th = crop.size
    scale = max(out / tw, out / th) * COVER_ZOOM
    nw = max(out, int(round(tw * scale)))
    nh = max(out, int(round(th * scale)))
    resized = crop.resize((nw, nh), Image.Resampling.LANCZOS)
    left = (nw - out) // 2
    top = (nh - out) // 2
    # tiny upward bias keeps ears; do not over-bias chin off
    top = max(0, top - int(out * 0.01))
    if top + out > nh:
        top = nh - out
    return resized.crop((left, top, left + out, top + out)).convert("RGBA")


def load_source(i: int) -> Image.Image | None:
    for rev in SOURCE_REVS:
        for ext in ("webp", "png"):
            rel = f"assets/custom/jx3_qban/icons/emoji_{i:02d}.{ext}"
            try:
                data = subprocess.check_output(
                    ["git", "show", f"{rev}:{rel}"], stderr=subprocess.DEVNULL
                )
                return Image.open(io.BytesIO(data)).convert("RGBA")
            except Exception:
                continue
    return None


def main() -> None:
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    for pth in ICON_DIR.glob("emoji_*"):
        pth.unlink()
    for pth in ICON_DIR.glob("icon_*"):
        pth.unlink()

    written: list[int] = []
    for i in FIXED_EMOJI_IDS:
        im = load_source(i)
        if im is None:
            raise SystemExit(f"missing source emoji_{i:02d} in revs {SOURCE_REVS}")
        fixed = face_cover(im)
        fixed.save(ICON_DIR / f"emoji_{i:02d}.png", format="PNG", optimize=True)
        fixed.save(ICON_DIR / f"emoji_{i:02d}.webp", format="WEBP", quality=92, method=6)
        written.append(i)
        arr = np.asarray(fixed)
        white = ((arr[:, :, 3] > 20) & (arr[:, :, 0] >= 245) & (arr[:, :, 1] >= 245) & (arr[:, :, 2] >= 245)).mean()
        trans = (arr[:, :, 3] < 20).mean()
        bbox = fixed.split()[-1].getbbox() or (0, 0, OUT, OUT)
        fill_w = (bbox[2] - bbox[0]) / OUT
        fill_h = (bbox[3] - bbox[1]) / OUT
        touches = bbox[0] <= 1 or bbox[1] <= 1 or bbox[2] >= OUT - 1 or bbox[3] >= OUT - 1
        print(
            f"emoji_{i:02d} white={white:.3f} trans={trans:.3f} "
            f"fill={fill_w:.3f}x{fill_h:.3f} touches={touches} bbox={bbox}"
        )
    print("written", len(written), written)


if __name__ == "__main__":
    main()
