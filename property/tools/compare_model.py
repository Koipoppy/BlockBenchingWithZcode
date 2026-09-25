"""Score a .bbmodel against a reference render.

    python tools/compare_reference.py --model raiden_shogun/raiden_shogun.bbmodel \
        --landmarks _ref/raiden_landmarks.json --out _cmp

What it measures, and why this way
----------------------------------
The reference (a boss-scene render) puts a character in a busy dusk scene whose
colours overlap hers, so pixel segmentation is not reliable there. Instead the
reference is *measured once by hand* into a landmark file (see
`_ref/raiden_landmarks.json` for how), and this tool measures the model the
exact way it can be measured exactly -- from its own cube geometry:

  * vertical landmarks -- chin, shoulder, waist, hip, hem, boot top -- from the
    named cubes (`head`, `chest`, `obi`, hip/hem tiers, `boot_*`), as fractions
    of the model's height;
  * widths at those landmarks -- head, chest, waist, hip, thigh, knee, boot,
    foot -- from the cube x-extents, with the arm groups excluded for the body
    widths so a T-pose or A-pose does not distort them;
  * a 40-band silhouette width profile, again arms excluded, for the shape score;
  * smoothness of the leg taper -- mean |second difference| of the profile in
    the leg region, normalised: this is the "bamboo shoot" detector;
  * palette -- the rendered colour classes' area fractions (a model render is
    trivially keyed by the magenta background).

Scoring is a relative-gap score: 100 when the value matches the reference, 0
once the gap reaches the tolerance. Total is a weighted sum; pass >= 80.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

CLASSES = ("white", "dark", "purple", "gold", "skin", "maroon")


# --- model measurement ------------------------------------------------------
def load_cubes(doc: dict) -> list[dict]:
    """Cubes with their group name attached (groups come from the outliner)."""
    elements = {el["uuid"]: el for el in doc.get("elements") or []}
    groups = {g.get("uuid"): g for g in doc.get("groups") or []}
    out: list[dict] = []

    def walk(node, group, chain):
        source = node if ("origin" in node or "rotation" in node) else groups.get(node.get("uuid"), node)
        name = source.get("name") or group
        for child in node.get("children") or []:
            if isinstance(child, dict):
                if child.get("uuid") in elements:
                    el = dict(elements[child["uuid"]])
                    el["_group"] = name
                    el["_groups"] = chain + [name]
                    out.append(el)
                else:
                    walk(child, name, chain + [name])
            elif child in elements:
                el = dict(elements[child])
                el["_group"] = name
                el["_groups"] = chain + [name]
                out.append(el)

    for node in doc.get("outliner") or []:
        walk(node, "root", [])
    return out


def by_name(cubes: list[dict], *keys: str) -> list[dict]:
    return [c for c in cubes if any(k in c["name"] for k in keys)]


def model_features(cubes: list[dict]) -> dict:
    ys = [v for c in cubes for v in (c["from"][1], c["to"][1])]
    top, bottom = max(ys), min(ys)
    h = top - bottom
    f = {"h": h, "top": top, "bottom": bottom}

    def span(cs: list[dict], y0: float, y1: float) -> float:
        """Widest x extent of the cubes that overlap the band [y0, y1]."""
        lo, hi = None, None
        for c in cs:
            if c["to"][1] < y0 or c["from"][1] > y1:
                continue
            lo = c["from"][0] if lo is None else min(lo, c["from"][0])
            hi = c["to"][0] if hi is None else max(hi, c["to"][0])
        return 0.0 if lo is None else float(hi - lo)

    arms = [c for c in cubes if "_arm" in " ".join(c["_groups"])]
    back_only = ("bow_", "loop_", "tail_", "braid", "hair_back", "charm")
    body = [c for c in cubes
            if c not in arms and not any(k in c["name"] for k in back_only)]

    def hgt(y: float) -> float:
        return (y - bottom) / h            # fraction of height above ground

    # vertical landmarks from the named parts
    head = by_name(cubes, "head")[0] if by_name(cubes, "head") else None
    chest = by_name(cubes, "chest", "bust")[0] if by_name(cubes, "chest", "bust") else None
    obi = by_name(cubes, "obi", "sash", "waist")[0] if by_name(cubes, "obi", "sash", "waist") else None
    hip = by_name(cubes, "hip", "hem", "skirt")
    boot = by_name(cubes, "boot")
    f["chin"] = hgt(head["from"][1]) if head else 0.0
    f["head_top"] = hgt(head["to"][1]) if head else 1.0
    f["head_h"] = f["head_top"] - f["chin"]
    f["shoulder"] = hgt(chest["to"][1]) if chest else 0.0
    f["waist"] = hgt((obi["from"][1] + obi["to"][1]) / 2) if obi else 0.0
    f["hem"] = hgt(min(c["from"][1] for c in hip)) if hip else 0.0
    f["boot_top"] = hgt(max(c["to"][1] for c in boot)) if boot else 0.0

    # the hip landmark = the widest row of the lower garment
    if hip:
        ys = np.linspace(min(c["from"][1] for c in hip),
                         max(c["to"][1] for c in hip), 24)
        ws = np.array([span(hip, y - 0.2, y + 0.2) for y in ys])
        best_w = float(ws.max())
        best_y = float(ys[ws >= 0.995 * best_w].mean())
        f["hip_w"] = best_w / h
        f["hip"] = hgt(best_y)
    else:
        f["hip_w"], f["hip"] = 0.0, 0.0

    # widths at landmark heights (arms excluded: pose independent)
    def width_at(frac: float) -> float:
        y = bottom + frac * h
        return span(body, y - 0.25, y + 0.25) / h

    f["head_w"] = width_at(f["chin"] + 0.5 * f["head_h"])
    f["chest_w"] = width_at(max(0.0, f["shoulder"] - 0.06))
    f["waist_w"] = width_at(f["waist"])
    f["thigh_w"] = width_at(f["hem"] - 0.04)
    f["knee_w"] = width_at(0.5 * (f["boot_top"] + f["hem"]))
    f["boot_w"] = width_at(0.6 * f["boot_top"])
    f["foot_w"] = width_at(0.02)

    # 40-band silhouette profile, arms excluded (normalised by height)
    nb = 40
    prof = np.zeros(nb, np.float32)
    for i in range(nb):
        y0 = bottom + (i / nb) * h
        y1 = bottom + ((i + 1) / nb) * h
        prof[i] = span(body, y0, y1) / h
    f["profile"] = prof

    # stepiness: the biggest single width step in the leg region. Bands are
    # indexed from the ground up, so the leg region is prof[:hem band]; the band
    # right under the hem is dropped, since a garment hem is a legitimate
    # discontinuity in both the reference and the model.
    nb40 = prof.size
    lo = max(1, int(nb40 * f["hem"]) - 1)
    leg = prof[:lo]
    f["stepiness"] = float(np.abs(np.diff(leg)).max()) if leg.size > 2 else 0.0
    f["full_w"] = span(cubes, bottom, top) / h
    return f


def reference_stepiness(ref: dict, nb: int = 40) -> float:
    """How smooth the reference's own annotated leg taper is, measured the same
    way as the model's: interpolate its landmark widths over the bands and take
    the mean |second difference| of the leg region."""
    anchors = [(0.0, ref["foot_w"]), (ref["boot_top"], ref["boot_w"]),
               (0.5 * (ref["boot_top"] + ref["hem"]), ref["knee_w"]),
               (ref["hem"] - 0.04, ref["thigh_w"])]
    anchors.sort()
    xs = np.array([a for a, _ in anchors], np.float32)
    ws = np.array([b for _, b in anchors], np.float32)
    prof = np.interp((np.arange(nb) + 0.5) / nb, xs, ws)
    leg = prof[: int(nb * ref["hem"])]
    return float(np.abs(np.diff(leg)).mean()) if leg.size > 2 else 0.0


# --- palette ----------------------------------------------------------------
def classify(rgb: np.ndarray) -> dict[str, np.ndarray]:
    r = rgb[:, :, 0].astype(np.int16)
    g = rgb[:, :, 1].astype(np.int16)
    b = rgb[:, :, 2].astype(np.int16)
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    return {
        "white": (mn > 165) & (mx - mn < 62) & (r - b > 5),
        "purple": (b > r) & (r > g - 4) & (b - g > 18) & (mx > 70),
        "dark": (mx < 130) & (b - g > 20),
        "gold": (r > 175) & (g > 125) & (r - b > 55),
        "skin": (r > 175) & (r - b > 20) & (r - b < 85) & (r - g > 8),
        "maroon": (r - g > 22) & (r < 178) & (b - g > -5) & (g > 30),
    }


def palette_of(render_path: str, bg=(255, 0, 255)) -> dict:
    """Area fractions of the colour classes among the model's pixels. Classes
    are assigned exclusively in priority order, or a cream pixel would count as
    white and skin at once."""
    from PIL import Image
    rgb = np.asarray(Image.open(render_path).convert("RGB"))
    key = np.abs(rgb.astype(np.int16) - np.array(bg, np.int16)).sum(axis=2) > 24
    cls = classify(rgb)
    taken = np.zeros(key.shape, bool)
    counts = {}
    for c in CLASSES:
        m = cls[c] & key & ~taken
        counts[c] = int(m.sum())
        taken |= m
    inside = max(int(key.sum()), 1)
    return {c: counts[c] / inside for c in CLASSES}


# --- scoring ----------------------------------------------------------------
def rel_score(a: float, b: float, tol: float) -> float:
    if a <= 0 and b <= 0:
        return 100.0
    gap = abs(a - b) / max((a + b) / 2.0, 1e-6)
    return float(max(0.0, min(100.0, 100.0 * (1.0 - gap / tol))))


def score(ref: dict, mine: dict) -> dict:
    out: dict[str, float] = {}

    vert = {k: 0.10 for k in ("chin", "shoulder", "waist", "hip", "hem", "boot_top", "head_h")}
    out["vertical"] = {k: rel_score(ref[k], mine[k], tol) for k, tol in vert.items()}

    wid = {"head_w": 0.20, "chest_w": 0.28, "waist_w": 0.30, "hip_w": 0.26,
           "thigh_w": 0.30, "knee_w": 0.35, "boot_w": 0.35, "foot_w": 0.40}
    out["widths"] = {k: rel_score(ref[k], mine[k], tol) for k, tol in wid.items()}

    out["vertical_avg"] = float(np.mean(list(out["vertical"].values())))
    out["width_avg"] = float(np.mean(list(out["widths"].values())))

    # profile shape: compare our width profile against the reference landmarks
    # resampled to the same 40 bands (linear between the annotated points)
    anchors = [(0.0, ref["foot_w"]), (ref["boot_top"], ref["boot_w"]),
               (ref["knee_w"] / 2 * 0 + 0.35, ref["knee_w"]), (ref["hem"] - 0.04, ref["thigh_w"]),
               (ref["hip"], ref["hip_w"]), (ref["waist"], ref["waist_w"]),
               (ref["shoulder"] - 0.06, ref["chest_w"]),
               (ref["chin"] + 0.5 * ref["head_h"], ref["head_w"]),
               (1.0, ref["head_w"] * 0.6)]
    anchors.sort()
    xs = np.array([a for a, _ in anchors], np.float32)
    ws = np.array([b for _, b in anchors], np.float32)
    nb = mine["profile"].size
    want = np.interp((np.arange(nb) + 0.5) / nb, xs, ws)
    got = mine["profile"]
    denom = max((want.mean() + got.mean()) / 2.0, 1e-6)
    out["profile"] = float(max(0.0, min(100.0, 100.0 * (1.0 - np.abs(want - got).mean() / denom))))

    # the model's biggest single width step, against how fast the reference's own
    # leg tapers per band: <= 1x means no step is coarser than the reference's
    # natural taper (i.e. no visible "bamboo shoot" rings)
    ratio = mine["stepiness"] / max(ref["stepiness"], 1e-9)
    out["stepiness"] = float(min(100.0, 100.0 * min(1.0, 1.6 / max(ratio, 1e-9))))

    out["palette"] = float(max(0.0, 100.0 * (1.0 - 0.5 * sum(
        abs(ref["palette"][c] - mine["palette"][c]) for c in CLASSES))))

    # palette is compared against an eyeball estimate of the reference's colour
    # areas, so it carries less weight than the measured landmarks
    weights = {"vertical_avg": 0.26, "width_avg": 0.28, "profile": 0.14,
               "stepiness": 0.16, "palette": 0.16}
    out["total"] = float(sum(out[k] * w for k, w in weights.items()))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", required=True)
    ap.add_argument("--landmarks", required=True)
    ap.add_argument("--render", default=None,
                    help="model render with --bg 255,0,255 (made if omitted)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--min-score", type=float, default=80.0)
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    with open(args.landmarks, encoding="utf-8") as fh:
        ref = json.load(fh)

    with open(args.model, encoding="utf-8") as fh:
        doc = json.load(fh)
    mine = model_features(load_cubes(doc))

    if args.render is None:
        import preview_bbmodel as P
        ys = [v for el in doc["elements"] for v in (el["from"][1], el["to"][1])]
        mid, span = (min(ys) + max(ys)) / 2, max(1.0, max(ys) - min(ys))
        png = os.path.join(args.out, "render_front.png")
        P.render(doc, P.decode_textures(doc), size=900, eye=(0, mid, -(span * 1.9 + 20)),
                 target=(0, mid, 0), fov=45, ground=None, bg=(255, 0, 255),
                 unlit=True).save(png)
        args.render = png
    mine["palette"] = palette_of(args.render)
    ref.setdefault("palette", {"white": 0.30, "purple": 0.22, "dark": 0.20,
                               "gold": 0.07, "skin": 0.10, "maroon": 0.11})
    ref["stepiness"] = reference_stepiness(ref)

    sc = score(ref, mine)
    with open(os.path.join(args.out, "score.json"), "w", encoding="utf-8") as fh:
        json.dump({"score": sc, "model": {k: v for k, v in mine.items() if k != "profile"},
                   "reference": ref}, fh, indent=2, default=float)

    print(f"model height {mine['h']:.1f} units, full width/height {mine['full_w']:.3f}")
    print()
    print("  vertical landmarks (fraction of height)")
    for k, v in sc["vertical"].items():
        print(f"    {k:<10} {v:6.1f}   ref {ref[k]:.3f}  model {mine[k]:.3f}")
    print("  widths (fraction of height)")
    for k, v in sc["widths"].items():
        print(f"    {k:<10} {v:6.1f}   ref {ref[k]:.3f}  model {mine[k]:.3f}")
    print(f"  profile shape                {sc['profile']:6.1f}")
    print(f"  leg smoothness               {sc['stepiness']:6.1f}   "
          f"biggest step {mine['stepiness']:.4f} vs ref taper {ref['stepiness']:.4f} (fraction of height per band)")
    print(f"  palette                      {sc['palette']:6.1f}")
    print("      ref   " + "  ".join(f"{c} {ref['palette'][c]:.2f}" for c in CLASSES))
    print("      model " + "  ".join(f"{c} {mine['palette'][c]:.2f}" for c in CLASSES))
    print()
    verdict = "PASS" if sc["total"] >= args.min_score else "BELOW THRESHOLD"
    print(f"  TOTAL {sc['total']:.1f} / 100  (min {args.min_score:.0f})  -> {verdict}")
    return 0 if sc["total"] >= args.min_score else 1


if __name__ == "__main__":
    sys.exit(main())
