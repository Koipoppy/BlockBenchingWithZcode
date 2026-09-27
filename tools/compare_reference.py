"""Score a rendered .bbmodel against a reference render.

    python tools/compare_reference.py --reference _ref/raiden_reference.png \
        --model raiden_shogun/raiden_shogun.bbmodel --out _cmp

What it does
------------
1. Keys the character out of the reference image (the reference is a scene
   render, so the mask is colour-classified, then only the component anchored at
   the image centre is kept -- that drops the sky, the ground and the floating
   effects) and out of our own render (rendered with `--bg 255,0,255`).
2. Normalises both to the same height and measures:
     * `total`   width profile -- the full horizontal extent per row (arms included)
     * `central` width profile -- the run containing the body centre per row,
       which ignores raised arms / hanging sleeves
     * landmarks -- head height and width, shoulder / waist / hip / thigh / ankle
       widths, crotch row (leg length), boot-top row, all as fractions of height
     * stepiness -- mean |second difference| of the leg-region width profile,
       i.e. how "bamboo shoot" the leg silhouette is; lower is better
     * palette -- area fractions of white / purple / dark / gold / skin / maroon
3. Scores each against the reference and prints a weighted total (pass >= 80).

Outputs `<out>/score.png` (4-panel mask comparison), `<out>/profile.png`
(overlaid width profiles), `<out>/score.json` and a printed report.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

BG = (255, 0, 255)          # our render's key colour
CLASSES = ("white", "purple", "dark", "gold", "skin", "maroon")


# --- masks ------------------------------------------------------------------
def classify(rgb: np.ndarray) -> dict[str, np.ndarray]:
    """Per-pixel colour classes, tuned to the measured values of the reference
    render (a dim scene: kimono white ~ (205,190,172), leggings lavender-grey
    ~ (150,135,165), hair ~ (50,36,66), stone grey ~ (90..130 neutral)) and of
    our own renders (same palette, flat lit)."""
    r = rgb[:, :, 0].astype(np.int16)
    g = rgb[:, :, 1].astype(np.int16)
    b = rgb[:, :, 2].astype(np.int16)
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    white = (mn > 165) & (mx - mn < 62) & (r - b > 5)
    # dark violet only: the scene's dark wood/stone/foliage is warm (b <= g)
    dark = (mx < 130) & (b - g > 20)
    # lavender / violet / magenta, but not the neutral grey background
    purple = (b > r) & (r > g - 4) & (b - g > 18) & (mx > 70)
    gold = (r > 175) & (g > 125) & (r - b > 55)
    # skin and warm cream: the wood is darker, so brightness separates them
    skin = (r > 175) & (r - b > 20) & (r - b < 85) & (r - g > 8)
    # warm gold/brown trim (the outfit's collar band and sash edges); without it
    # the head section is severed from the chest and never joins the mask
    trim = (r > 118) & (g > 78) & (r - b > 34) & (r - g < 55)
    # crimson cords: mid red with a violet cast (the archway's red is not)
    maroon = (r - g > 22) & (r < 178) & (b - g > 20) & (g > 45)
    return {"white": white, "purple": purple, "dark": dark,
            "gold": gold, "skin": skin, "trim": trim, "maroon": maroon}


def reference_mask(rgb: np.ndarray, roi: tuple[float, float, float, float] | None = None
                   ) -> np.ndarray:
    """Core character mask out of a scene render.

    The reference is a busy scene (dusk lighting, an archway, floating effects,
    giant hands) whose colours overlap the character's, so per-pixel classes are
    not enough on their own. The figure is one centred column:

      1. union of the colour classes (see `classify`); a `trim` class catches the
         warm gold/brown collar band that would otherwise split the head off;
      2. restrict to the ROI (a normal prior for a character render: the figure
         occupies a known region of frame) and, per row, keep only the runs that
         cross the central body band -- scenery is wider than the band, and the
         raised arms / floating effects sit outside it;
      3. keep the component at the body centre and merge anything within 7 px of
         it (the head sits above the collar band), then drop components that
         barely intersect the ROI (the floating ornaments), fill holes.

    The result is the pose-independent *core* silhouette (head, torso, hips,
    legs) -- exactly what the proportion and leg scores are computed on.
    """
    cls = classify(rgb)
    cand = np.zeros(rgb.shape[:2], bool)
    for c in cls.values():
        cand |= c

    h, w = cand.shape
    if roi is not None:
        rx0, ry0, rx1, ry1 = (int(roi[0] * w), int(roi[1] * h),
                              int(roi[2] * w), int(roi[3] * h))
        inside = np.zeros_like(cand)
        inside[ry0:ry1, rx0:rx1] = True
    else:
        inside = np.ones_like(cand)

    bx0, bx1 = int(0.425 * w), int(0.585 * w)
    core = np.zeros_like(cand)
    for y in range(h):
        for (a, b) in runs_of(cand[y]):
            if (b < bx0 or a > bx1) or not inside[y, a]:
                continue
            core[y, a:b + 1] = True
    core &= inside
    core = ndimage.binary_opening(core, np.ones((3, 3)))
    # the boots are near-black: the classes catch them in fragments, so bridge
    # the rows vertically (nothing laterally adjacent can join this way)
    core = ndimage.binary_closing(core, np.ones((13, 1)))

    lab, n = ndimage.label(core, structure=np.ones((3, 3)))
    if n == 0:
        raise SystemExit("reference: no candidate pixels")
    anchor = (int(h * 0.62), int(w * 0.505))
    seed_label = lab[anchor]
    if seed_label == 0:
        ys, xs = np.nonzero(lab)
        k = np.argmin((ys - anchor[0]) ** 2 + (xs - anchor[1]) ** 2)
        seed_label = lab[ys[k], xs[k]]
    keep = lab == seed_label
    for _ in range(3):
        near = ndimage.binary_dilation(keep, np.ones((15, 15)))
        touching = np.unique(lab[near])
        touching = touching[touching > 0]
        # a body part fills its ROI slice; a floating ornament clips the ROI edge
        sizes = np.bincount(lab.ravel())
        good = [t for t in touching if sizes[t] > 150]
        add = np.isin(lab, good)
        if (add & ~keep).sum() == 0:
            break
        keep = keep | add
    keep = ndimage.binary_closing(keep, np.ones((5, 5)))
    keep = ndimage.binary_fill_holes(keep)
    ys, xs = np.nonzero(keep)
    print(f"reference mask: {int(keep.sum())} px, "
          f"x {xs.min()}-{xs.max()} y {ys.min()}-{ys.max()} "
          f"(figure height {ys.max() - ys.min()} px of {h})")
    return keep


def render_mask(rgb: np.ndarray) -> np.ndarray:
    d = np.abs(rgb.astype(np.int16) - np.array(BG, np.int16)).sum(axis=2)
    m = d > 24
    m = ndimage.binary_closing(m, np.ones((3, 3)))
    return ndimage.binary_fill_holes(m)


def crop_scale(mask: np.ndarray, height: int = 600):
    """Bounding-box crop, then nearest-neighbour scale to a common height."""
    ys, xs = np.nonzero(mask)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    sub = mask[y0:y1, x0:x1]
    scale = height / sub.shape[0]
    width = max(1, int(round(sub.shape[1] * scale)))
    img = Image.fromarray((sub * 255).astype(np.uint8)).resize((width, height), Image.NEAREST)
    return np.asarray(img) > 127, (y1 - y0), (x1 - x0)


# --- features ---------------------------------------------------------------
def runs_of(row: np.ndarray) -> list[tuple[int, int]]:
    idx = np.nonzero(row)[0]
    if idx.size == 0:
        return []
    breaks = np.nonzero(np.diff(idx) > 1)[0]
    starts = np.concatenate(([0], breaks + 1))
    ends = np.concatenate((breaks, [idx.size - 1]))
    return [(int(idx[s]), int(idx[e])) for s, e in zip(starts, ends)]


def smooth(x: np.ndarray, k: int = 5) -> np.ndarray:
    if k <= 1 or x.size < k:
        return x
    ker = np.ones(k, np.float32) / k
    return np.convolve(x, ker, mode="same")


def features(mask: np.ndarray, rgb: np.ndarray | None = None) -> dict:
    h, w = mask.shape
    cx = w // 2
    total = np.zeros(h, np.float32)
    central = np.zeros(h, np.float32)
    nruns = np.zeros(h, int)
    for y in range(h):
        rs = runs_of(mask[y])
        nruns[y] = len(rs)
        if not rs:
            continue
        total[y] = rs[-1][1] - rs[0][0] + 1
        pick = None
        for (a, b) in rs:
            if a <= cx <= b:
                pick = (a, b)
                break
        if pick is None:                # body centre not inside a run: nearest run
            pick = min(rs, key=lambda ab: min(abs(ab[0] - cx), abs(ab[1] - cx)))
        central[y] = pick[1] - pick[0] + 1

    ts, cs = smooth(total), smooth(central)
    f = {"h": float(h), "w": float(w), "total": ts, "central": cs}

    def band(a: float, b: float) -> tuple[int, int]:
        return int(h * a), max(int(h * b), int(h * a) + 1)

    # head: from the top down to the first strong pinch of the central profile
    top_band = cs[: int(h * 0.30)]
    head_max = float(top_band.max())
    neck = None
    for y in range(6, int(h * 0.30)):
        if cs[y] <= cs[y - 1] and cs[y] <= cs[y + 1] and cs[y] < 0.80 * head_max:
            neck = y
            break
    neck = neck if neck is not None else int(h * 0.18)
    f["head_h"] = float(neck)
    f["head_w"] = float(cs[:neck].max()) if neck > 2 else float(cs[:6].max())

    lo, hi = band(0.10, 0.30)           # shoulder frame, below the neck
    f["shoulder_w"] = float(cs[lo:hi].max())
    lo, hi = band(0.34, 0.55)
    f["waist_w"] = float(cs[lo:hi].min())
    lo, hi = band(0.46, 0.66)
    f["hip_w"] = float(cs[lo:hi].max())

    # where the legs begin: the row where the total width first drops below 62%
    # of the hip width and stays there (robust whether or not the legs separate)
    hip_lo, hip_hi = band(0.46, 0.66)
    hip_w = f["hip_w"]
    leg_top = int(h * 0.66)
    for y in range(hip_hi, int(h * 0.92)):
        if ts[y] < 0.62 * hip_w and ts[y] < 0.62 * hip_w:
            leg_top = y
            break
    f["leg_top"] = float(leg_top)
    f["leg_len"] = float(h - leg_top)

    def width_at(frac: float) -> float:
        y = int(h * frac)
        return float(ts[max(0, min(h - 1, y))])

    f["thigh_w"] = width_at(0.72)
    f["ankle_w"] = width_at(0.95)

    # stepiness: how much the leg silhouette wobbles (bamboo-shoot detector)
    leg = ts[leg_top:]
    if leg.size > 4:
        f["stepiness"] = float(np.abs(np.diff(leg, 2)).mean() / max(leg.mean(), 1e-6))
    else:
        f["stepiness"] = 0.0

    # boot top: first row in the leg region where dark/maroon pixels dominate
    f["boot_top"] = float(h)
    if rgb is not None:
        cls = classify(rgb)
        darkish = cls["dark"] | cls["maroon"]
        for y in range(leg_top, h):
            rs = runs_of(mask[y])
            if not rs:
                continue
            a, b = rs[0][0], rs[-1][1]
            seg = darkish[y, a:b + 1]
            if seg.size and seg.mean() > 0.55:
                f["boot_top"] = float(y)
                break
    f["boot_h"] = float(h - f["boot_top"])

    if rgb is not None:
        cls = classify(rgb)
        inside = mask.sum()
        f["palette"] = {c: float((cls[c] & mask).sum()) / max(inside, 1) for c in CLASSES}
    return f


# --- scoring ----------------------------------------------------------------
def rel_score(a: float, b: float, tol: float) -> float:
    """100 when equal, 0 when the relative gap reaches `tol`."""
    if a <= 0 and b <= 0:
        return 100.0
    gap = abs(a - b) / max((a + b) / 2.0, 1e-6)
    return float(max(0.0, min(100.0, 100.0 * (1.0 - gap / tol))))


def profile_score(a: np.ndarray, b: np.ndarray, lo: int, hi: int) -> float:
    seg_a, seg_b = a[lo:hi], b[lo:hi]
    n = min(seg_a.size, seg_b.size)
    if n == 0:
        return 0.0
    seg_a, seg_b = seg_a[:n], seg_b[:n]
    denom = max((seg_a.mean() + seg_b.mean()) / 2.0, 1e-6)
    mad = np.abs(seg_a - seg_b).mean()
    return float(max(0.0, min(100.0, 100.0 * (1.0 - mad / denom))))


def compare(ref: dict, mine: dict) -> dict:
    h = ref["h"]
    out: dict[str, float] = {}

    # legs (below the hem) and hips: total extent, pose-independent
    lo, hi = int(ref["leg_top"]), int(h)
    out["leg_profile"] = profile_score(ref["total"], mine["total"], lo, hi)
    # torso band between the neck pinch and the hem: the central run, so raised
    # arms / hanging sleeves do not count
    lo, hi = int(ref["head_h"]), int(ref["leg_top"])
    out["torso_profile"] = profile_score(ref["central"], mine["central"], lo, hi)
    lo, hi = 0, int(ref["head_h"])
    out["head_profile"] = profile_score(ref["central"], mine["central"], lo, hi)

    lm = {
        "head_h": (ref["head_h"], mine["head_h"], 0.20),
        "head_w": (ref["head_w"], mine["head_w"], 0.25),
        "shoulder_w": (ref["shoulder_w"], mine["shoulder_w"], 0.30),
        "waist_w": (ref["waist_w"], mine["waist_w"], 0.35),
        "hip_w": (ref["hip_w"], mine["hip_w"], 0.30),
        "leg_len": (ref["leg_len"], mine["leg_len"], 0.15),
        "thigh_w": (ref["thigh_w"], mine["thigh_w"], 0.35),
        "ankle_w": (ref["ankle_w"], mine["ankle_w"], 0.40),
        "boot_h": (ref["boot_h"], mine["boot_h"], 0.35),
    }
    out["landmarks"] = {k: rel_score(a, b, tol) for k, (a, b, tol) in lm.items()}
    out["landmark_avg"] = float(np.mean(list(out["landmarks"].values())))

    ratio = mine["stepiness"] / max(ref["stepiness"], 1e-6)
    out["stepiness"] = float(min(100.0, 100.0 * min(1.0, 1.25 / max(ratio, 1e-6))))

    if "palette" in ref and "palette" in mine:
        tv = 0.5 * sum(abs(ref["palette"][c] - mine["palette"][c]) for c in CLASSES)
        out["palette"] = float(max(0.0, 100.0 * (1.0 - tv)))
    else:
        out["palette"] = 0.0

    weights = {"leg_profile": 0.26, "torso_profile": 0.12, "head_profile": 0.06,
               "landmark_avg": 0.24, "stepiness": 0.18, "palette": 0.14}
    out["total"] = float(sum(out[k] * wt for k, wt in weights.items()))
    return out


# --- reporting --------------------------------------------------------------
def panel(ref_rgb, ref_mask, my_rgb, my_mask, out_path) -> None:
    def to_img(rgb, mask):
        vis = rgb.copy()
        edge = mask & ~ndimage.binary_erosion(mask, np.ones((3, 3)))
        vis[edge] = (255, 60, 60)
        return Image.fromarray(vis)
    imgs = [to_img(ref_rgb, ref_mask), to_img(my_rgb, my_mask)]
    h = 480
    scaled = [im.resize((max(1, int(im.width * h / im.height)), h), Image.NEAREST) for im in imgs]
    W = sum(im.width for im in scaled) + 30
    canvas = Image.new("RGB", (W, h + 26), (24, 24, 28))
    x = 10
    d = ImageDraw.Draw(canvas)
    for im, label in zip(scaled, ("reference (mask in red)", "render (mask in red)")):
        canvas.paste(im, (x, 22))
        d.text((x + 4, 6), label, fill=(230, 230, 235))
        x += im.width + 10
    canvas.save(out_path)


def profile_plot(ref: dict, mine: dict, out_path) -> None:
    h = 600
    W = 460
    img = Image.new("RGB", (W, h + 24), (24, 24, 28))
    d = ImageDraw.Draw(img)
    d.text((8, 6), "central width profile  (ref = cyan, model = magenta)", fill=(230, 230, 235))
    maxv = max(ref["central"].max(), mine["central"].max(), 1.0)
    for y in range(h):
        d.line((10, 24 + y, 10 + 120 * ref["central"][y] / maxv, 24 + y), fill=(80, 200, 220))
        d.line((10, 24 + y, 10 + 120 * mine["central"][y] / maxv, 24 + y), fill=(230, 90, 200))
    for y in range(h):
        d.line((250, 24 + y, 250 + 120 * ref["total"][y] / maxv, 24 + y), fill=(80, 200, 220))
        d.line((250, 24 + y, 250 + 120 * mine["total"][y] / maxv, 24 + y), fill=(230, 90, 200))
    d.text((250, 6), "total extent profile", fill=(230, 230, 235))
    img.save(out_path)


def load_model_posed(path: str, arm_deg: float, out_path: str) -> str:
    """Write a copy of the model with the arms rotated out to `arm_deg` from
    vertical -- the reference stands in a T-pose, so the shoulder / arm-span
    landmarks are only comparable if our model is posed the same way.
    The arm cubes' own `origin` is the shoulder pivot, so a Z rotation about it
    swings the whole arm (deltoid, arm, sleeve, hand) as one piece."""
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    for el in doc.get("elements") or []:
        if "_right" in el["name"] or "_left" in el["name"]:
            if not any(k in el["name"] for k in ("arm", "sleeve", "hand")):
                continue
            sign = -1.0 if "_left" in el["name"] else 1.0
            el["rotation"] = [0.0, 0.0, sign * arm_deg]
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1)
    return out_path


def render_model(model_path: str, out_png: str, size: int = 900) -> str:
    """Render a model front-on with the magenta key background."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import preview_bbmodel as P                     # noqa: E402  (sibling script)
    with open(model_path, encoding="utf-8") as fh:
        doc = json.load(fh)
    h = max(1.0, float(doc.get("resolution", {}).get("height", 64)))
    ys = [c for el in doc.get("elements") or [] for c in (el["from"][1], el["to"][1])]
    mid = (min(ys) + max(ys)) / 2.0
    span = max(1.0, max(ys) - min(ys))
    eye = (0.0, mid, -(span * 1.9 + 20.0))
    img = P.render(doc, P.decode_textures(doc), size=size, eye=eye, target=(0.0, mid, 0.0),
                   fov=45.0, ground=None, bg=BG)
    img.save(out_png)
    return out_png


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--reference", required=True)
    ap.add_argument("--render", help="our render, made with --bg 255,0,255")
    ap.add_argument("--model", help="model to render instead of --render")
    ap.add_argument("--pose-arms", type=float, default=72.0,
                    help="pose the arm groups out to this angle for the comparison")
    ap.add_argument("--roi", default=None,
                    help="reference figure region as x0,y0,x1,y1 fractions "
                         "(needed when the reference is a scene rather than a "
                         "clean turnaround)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--min-score", type=float, default=80.0)
    args = ap.parse_args()
    if not args.render and not args.model:
        ap.error("give --render or --model")

    os.makedirs(args.out, exist_ok=True)
    roi = tuple(float(v) for v in args.roi.split(",")) if args.roi else None
    if args.model:
        posed = os.path.join(args.out, "render_posed.bbmodel")
        args.render = render_model(load_model_posed(args.model, args.pose_arms, posed),
                                   os.path.join(args.out, "render_front.png"))

    ref_rgb = np.asarray(Image.open(args.reference).convert("RGB"))
    my_rgb = np.asarray(Image.open(args.render).convert("RGB"))

    rmask = reference_mask(ref_rgb, roi)
    mmask = render_mask(my_rgb)
    rsub, rh, rw = crop_scale(rmask)
    msub, mh, mw = crop_scale(mmask)
    rrgb, _ = crop_scale_rgb(ref_rgb, rmask)
    mrgb, _ = crop_scale_rgb(my_rgb, mmask)

    rf = features(rsub, rrgb)
    mf = features(msub, mrgb)
    scores = compare(rf, mf)

    panel(ref_rgb, rmask, my_rgb, mmask, os.path.join(args.out, "score.png"))
    profile_plot(rf, mf, os.path.join(args.out, "profile.png"))
    with open(os.path.join(args.out, "score.json"), "w", encoding="utf-8") as fh:
        json.dump({"scores": {k: v for k, v in scores.items() if k != "landmarks"},
                   "landmarks": scores["landmarks"],
                   "reference": {k: v for k, v in rf.items()
                                 if k not in ("total", "central")},
                   "model": {k: v for k, v in mf.items() if k not in ("total", "central")}},
                  fh, indent=2)

    print(f"reference {args.reference}: figure {rw}x{rh}px")
    print(f"model     {args.render}: figure {mw}x{mh}px   "
          f"aspect ref {rw / rh:.3f} vs model {mw / mh:.3f}")
    print()
    print(f"  leg profile (below crotch)  {scores['leg_profile']:6.1f}")
    print(f"  torso profile (central)     {scores['torso_profile']:6.1f}")
    print(f"  head profile                {scores['head_profile']:6.1f}")
    print(f"  landmarks                   {scores['landmark_avg']:6.1f}")
    for k, v in scores["landmarks"].items():
        print(f"      {k:<12} {v:6.1f}   ref {rf[k]:7.1f}  model {mf[k]:7.1f}")
    print(f"  leg smoothness (stepiness)  {scores['stepiness']:6.1f}   "
          f"ref {rf['stepiness']:.4f}  model {mf['stepiness']:.4f}")
    print(f"  palette                     {scores['palette']:6.1f}")
    if "palette" in rf:
        print("      ref   " + "  ".join(f"{c} {rf['palette'][c]:.2f}" for c in CLASSES))
        print("      model " + "  ".join(f"{c} {mf['palette'][c]:.2f}" for c in CLASSES))
    print()
    verdict = "PASS" if scores["total"] >= args.min_score else "BELOW THRESHOLD"
    print(f"  TOTAL {scores['total']:.1f} / 100  (min {args.min_score:.0f})  -> {verdict}")
    print(f"  wrote {args.out}/score.png, {args.out}/profile.png, {args.out}/score.json")
    return 0 if scores["total"] >= args.min_score else 1


def crop_scale_rgb(rgb: np.ndarray, mask: np.ndarray, height: int = 600):
    ys, xs = np.nonzero(mask)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    sub = rgb[y0:y1, x0:x1]
    scale = height / sub.shape[0]
    width = max(1, int(round(sub.shape[1] * scale)))
    img = Image.fromarray(sub).resize((width, height), Image.NEAREST)
    return np.asarray(img), (y1 - y0, x1 - x0)


if __name__ == "__main__":
    sys.exit(main())
