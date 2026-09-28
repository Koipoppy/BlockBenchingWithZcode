"""Build 虚空之矛 (void_spear) as a Blockbench project.

    python 兵器/void_spear/build_void_spear.py [--no-preview]

An End spear: an endstone haft banded in obsidian and purpur, an ender eye
burning in the socket, and a blade that is not attached to it at all -- three
tapered purpur segments and a point, each hanging in the air above the last
with a 1.2-unit gap, held together by nothing you can see. The End is the
dimension of things that float and teleport; a blade that levitates says that
faster than any texture.

That floating blade is why this model's MCP validation whitelists free
elements: `blade0*` .. `blade3*` and `shard*` touch nothing by design. The
segments are each their own group, so the idle clip can bob and turn them out
of phase with one another, and the shards drift around them.

The set (人工建模参考/兵器) has no spear. Between undead_scythe (bone, green,
crescent), infernal_flail (blackstone, magma orange, a mace head) and this
(endstone, purpur, teal) the three share the house hardware -- a two-handed
haft, a socket, an emissive accent, an idle clip -- and nothing else.

Palette: endstone, purpur, obsidian (near-black with a violet sheen), a
deep-violet grip wrap, ender teal for every glow, and chorus stems for the
tassels under the socket.
"""
from __future__ import annotations

import argparse
import math
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.dont_write_bytecode = True
REPO = HERE
while not os.path.isfile(os.path.join(REPO, "tools", "bbmodel_kit.py")):
    parent = os.path.dirname(REPO)
    if parent == REPO:
        raise SystemExit(f"repo root not found above {HERE}")
    REPO = parent
sys.path.insert(0, os.path.join(REPO, "tools"))
from bbmodel_kit import (FACES, V, walk_groups,  # noqa: E402
                         coplanar_conflicts, posed_contacts, stretch_report)
from bbmodel_build import (FM, S, TEX_BODY, TEX_GLOW, at, blobs, build_atlases,  # noqa: E402
                           check_painted, cube, edge_lit, group, hoop, kf, link,
                           make_animation, ramp, rect_key, render_previews,
                           rng_for, streaks, tint, write_model)

OUT_DIR = HERE
MODEL_NAME = "void_spear"
GLOW_MATERIALS = {"ender", "spark", "shard_glow"}

# --- palette ---------------------------------------------------------------
END_HI, END, END_MID, END_DK = (238, 232, 202), (214, 208, 174), (182, 176, 142), (146, 140, 110)
PURP_HI, PURP, PURP_DK, PURP_DEEP = (198, 138, 208), (162, 100, 174), (118, 66, 132), (78, 40, 90)
OBS_HI, OBS, OBS_DK, OBS_DEEP = (86, 70, 118), (52, 42, 76), (34, 26, 52), (20, 15, 32)
CLOTH_HI, CLOTH, CLOTH_DK = (104, 80, 140), (70, 52, 100), (46, 33, 68)
CHOR_HI, CHOR, CHOR_DK = (214, 196, 168), (170, 150, 126), (120, 104, 88)
TEAL_HI, TEAL, TEAL_MID, TEAL_DK = (186, 255, 232), (92, 236, 194), (44, 186, 152), (16, 104, 88)
VOID = (14, 10, 24)


# --- painters --------------------------------------------------------------
def paint_endstone(cv, r, key):
    a = at(cv, r)
    rng = rng_for(key)
    ramp(a, [(0.0, END_HI), (0.26, END), (0.75, END_MID), (1.0, END_DK)])
    blobs(a, rng, END_MID, 3, 1, 2)
    blobs(a, rng, END_HI, 2, 1, 1)
    tint(a, rng, END_MID, 0.08)
    edge_lit(a, top=(250, 246, 226), bottom=(120, 114, 90))


def paint_purpur(cv, r, key):
    a = at(cv, r)
    rng = rng_for(key)
    ramp(a, [(0.0, PURP_HI), (0.30, PURP), (0.78, PURP_DK), (1.0, PURP_DEEP)])
    streaks(a, rng, PURP_DK, max(1, a.shape[1] // (3 * S)), vertical=True, lo=3)
    tint(a, rng, PURP_HI, 0.10)
    edge_lit(a, top=(216, 168, 226), bottom=(58, 30, 68))


def paint_obsidian(cv, r, key):
    a = at(cv, r)
    rng = rng_for(key)
    ramp(a, [(0.0, OBS_HI), (0.22, OBS), (0.78, OBS_DK), (1.0, OBS_DEEP)])
    streaks(a, rng, OBS_HI, 2, vertical=True, lo=2, hi=4)
    tint(a, rng, OBS_HI, 0.08)
    edge_lit(a, top=(112, 92, 148), bottom=(12, 9, 20))


def paint_cloth_void(cv, r, key):
    a = at(cv, r)
    rng = rng_for(key)
    ramp(a, [(0.0, CLOTH_HI), (0.32, CLOTH), (1.0, CLOTH_DK)])
    h = a.shape[0]
    for y in range(S, h, 5 * S):
        a[y:y + S, :, :3] = np.array(CLOTH_DK, np.uint8)
        a[y + S:y + 2 * S, :, :3] = np.array((124, 100, 164), np.uint8)
    tint(a, rng, CLOTH_DK, 0.10)
    edge_lit(a, bottom=CLOTH_DK)


def paint_chorus(cv, r, key):
    a = at(cv, r)
    rng = rng_for(key)
    ramp(a, [(0.0, CHOR_HI), (0.5, CHOR), (1.0, CHOR_DK)])
    streaks(a, rng, CHOR_DK, max(1, a.shape[1] // (2 * S)), vertical=True, lo=2, hi=3)
    tint(a, rng, PURP, 0.06)
    edge_lit(a, top=CHOR_HI, bottom=(96, 82, 70))


def paint_ender(cv, r, key):
    """Emissive: the eye -- white-hot teal core out to a cold rim."""
    a = at(cv, r)
    h, w = a.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    d = np.clip(np.sqrt(((yy - (h - 1) / 2) / max(1.0, h * 0.6)) ** 2 +
                        ((xx - (w - 1) / 2) / max(1.0, w * 0.6)) ** 2), 0, 1)
    col = (np.array(TEAL_HI, float) * (1 - d[..., None]) ** 1.6 +
           np.array(TEAL_DK, float) * d[..., None] ** 1.3)
    a[:, :, :3] = np.clip(col, 0, 255).astype(np.uint8)
    a[:, :, 3] = 255
    rng = rng_for(key)
    a[0:S, :, :3] = np.array((8, 44, 40), np.uint8)
    a[-S:, :, :3] = np.array((8, 44, 40), np.uint8)
    tint(a, rng, TEAL_HI, 0.10)


def paint_spark(cv, r, key):
    """Emissive: the void spark on a blade segment."""
    a = at(cv, r)
    h, w = a.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    d = np.clip(np.sqrt(((yy - (h - 1) / 2) / max(1.0, h * 0.7)) ** 2 +
                        ((xx - (w - 1) / 2) / max(1.0, w * 0.7)) ** 2), 0, 1)
    col = (np.array((226, 255, 248), float) * (1 - d[..., None]) +
           np.array(TEAL, float) * d[..., None])
    a[:, :, :3] = np.clip(col, 0, 255).astype(np.uint8)
    a[:, :, 3] = 255


def paint_shard_glow(cv, r, key):
    """Emissive: a shard's inner light, seen through its own cracks."""
    a = at(cv, r)
    a[:, :, :3] = np.array(TEAL_DK, np.uint8)
    a[:, :, 3] = 255
    rng = rng_for(key)
    h, w = a.shape[:2]
    for _ in range(3):
        x, y = rng.randrange(max(1, w)), rng.randrange(max(1, h))
        a[y, x:x + S, :3] = np.array(TEAL, np.uint8)
    tint(a, rng, TEAL_MID, 0.16)


PAINTERS = {
    "endstone": paint_endstone, "purpur": paint_purpur, "obsidian": paint_obsidian,
    "cloth_void": paint_cloth_void, "chorus": paint_chorus, "ender": paint_ender,
    "spark": paint_spark, "shard_glow": paint_shard_glow,
}

# --- the weapon ------------------------------------------------------------
# Haft y 0..84, socket 84..89.8, the eye 89.8..93.8, and then the blade, which
# hangs in the air: segments at 95, 99.2, 103.2 and the point at 107.
# segments taller than they are wide, or the blade reads as stacked plates
SEG_Y = ((95.0, 99.5), (101.1, 105.6), (107.2, 111.4))
SEG_HW = ((1.9, 1.5), (1.6, 1.25), (1.3, 1.0))


def build_haft():
    """Endstone, obsidian and purpur: butt, bands, grip, and the socket the eye
    burns in."""
    end = FM(all="endstone")
    obs = FM(all="obsidian")
    pur = FM(all="purpur")
    parts = [
        cube("butt_spike", (-1.2, 0.0, -1.2), (1.2, 1.4, 1.2), obs),
        cube("butt_cap", (-2.0, 1.4, -2.0), (2.0, 6.4, 2.0), obs),
    ]
    parts += hoop("butt_ring", 5.4, 6.8, 2.2, 0.6, pur)
    parts += [
        # starts inside the butt ring, not on top of it: a ring whose bars sit
        # outside the shaft only touches it along an edge, i.e. not at all
        cube("haft_lo", (-1.6, 5.8, -1.6), (1.6, 30.0, 1.6), end),
        cube("haft_mid", (-1.55, 29.4, -1.55), (1.55, 50.6, 1.55), end),
        cube("grip_cloth", (-1.78, 32.0, -1.78), (1.78, 48.0, 1.78),
             FM(sides="cloth_void", tb="cloth_void")),
        cube("haft_up", (-1.5, 50.0, -1.5), (1.5, 66.0, 1.5), end),
        cube("haft_top", (-1.42, 66.0, -1.42), (1.42, 84.0, 1.42), end),
    ]
    parts += hoop("band_lo", 20.0, 21.6, 1.85, 0.5, obs)
    parts += hoop("band_hi", 57.0, 58.6, 1.75, 0.5, obs)
    parts += hoop("grip_ring0", 30.0, 32.0, 1.85, 0.6, pur)
    parts += hoop("grip_ring1", 48.0, 50.0, 1.85, 0.6, pur)
    # the socket: a purpur block with obsidian claws, open at the top for the eye
    parts += [
        cube("socket", (-2.6, 84.0, -2.6), (2.6, 89.8, 2.6), pur),
        cube("socket_collar", (-2.9, 86.0, -2.9), (2.9, 87.2, 2.9), obs),
        cube("socket_lip", (-2.2, 90.0, -2.2), (2.2, 91.2, 2.2), obs),
    ]
    parts += hoop("socket_claw", 85.4, 86.8, 3.3, 0.8, obs)
    for i, (dx, dz) in enumerate(((1, 1), (1, -1), (-1, 1), (-1, -1))):
        parts.append(cube(f"claw{i}", (dx * 2.2, 88.6, dz * 2.2), (dx * 3.0, 92.0, dz * 3.0),
                          obs))
    # chorus tassels under the socket
    for i, (dx, dz) in enumerate(((1.8, -0.6), (-1.8, 0.6), (0.0, 2.2))):
        parts += [
            cube(f"chorus{i}_stem", (dx - 0.5, 76.6, dz - 0.5), (dx + 0.5, 84.4, dz + 0.5),
                 FM(all="chorus")),
            cube(f"chorus{i}_bud", (dx - 0.9, 74.4, dz - 0.9), (dx + 0.9, 76.6, dz + 0.9),
                 FM(all="chorus")),
        ]
    return parts


def build_blade():
    """The eye, and the blade that floats above it: three tapered segments (each
    a cross of two boxes, so it reads as a blade and not as a stick), a spark on
    each, and an obsidian point. Every segment is its own group, pivoting on its
    own centre, so the clip can bob and turn them out of phase."""
    pur = FM(all="purpur")
    obs = FM(all="obsidian")
    eye = group("eye", cubes=[
        cube("eye_core", (-2.3, 89.8, -2.3), (2.3, 93.8, 2.3), FM(all="ender")),
    ], origin=(0.0, 91.8, 0.0))
    groups = [eye]
    for i, ((y0, y1), (x0, z0)) in enumerate(zip(SEG_Y, SEG_HW)):
        # the void seam is the segment's own top face, lit -- a stud would eat
        # the gap that makes the whole blade read as levitating
        lit = FM(all="purpur", up="spark")
        cubes = [
            cube(f"blade{i}_a", (-x0, y0, -z0), (x0, y1, z0), lit),
            cube(f"blade{i}_b", (-z0, y0 + 0.05, -x0), (z0, y1 - 0.05, x0), lit),
        ]
        groups.append(group(f"blade{i}", cubes=cubes, origin=(0.0, (y0 + y1) / 2, 0.0)))
    tip = group("blade3", cubes=[
        cube("blade3_pt", (-1.0, 113.0, -1.0), (1.0, 115.2, 1.0), obs),
        cube("blade3_needle", (-0.55, 115.2, -0.55), (0.55, 117.0, 0.55),
             FM(all="obsidian", up="spark")),
    ], origin=(0.0, 113.8, 0.0))
    groups.append(tip)
    return groups


def build_shards():
    """Three shards drifting around the blade, deliberately detached."""
    obs = FM(all="obsidian")
    out = []
    for i, (x, y, z, w, h) in enumerate(((-5.4, 100.5, -1.6, 2.4, 4.4),
                                         (5.2, 96.0, 2.0, 2.2, 4.0),
                                         (-4.4, 104.5, 2.8, 2.0, 3.4))):
        out += [
            cube(f"shard{i}", (x, y, z), (x + w, y + h, z + w * 0.6), obs),
            cube(f"shard{i}_glow", (x + 0.4, y + 0.6, z + w * 0.6),
                 (x + w - 0.4, y + h - 0.6, z + w * 0.6 + 0.5), FM(all="shard_glow")),
        ]
    return out


def build_tree():
    eye, seg0, seg1, seg2, tip = build_blade()
    root = group(MODEL_NAME, children=[
        group("haft", cubes=build_haft(), origin=(0.0, 0.0, 0.0)),
        eye, seg0, seg1, seg2, tip,
        group("shards", cubes=build_shards(), origin=(0.0, 98.0, 0.0)),
    ], origin=(0.0, 0.0, 0.0))
    return root


# --- self checks -----------------------------------------------------------
def check_solids(tree):
    bad = []
    for path, c, _R, _t in walk_groups(tree):
        d = [c["to"][k] - c["from"][k] for k in range(3)]
        if any(v <= 1e-6 for v in d):
            bad.append((path, "degenerate"))
        elif min(d) < 0.5 and not any(k in path for k in ("chorus", "claw")):
            bad.append((path, f"thin {min(d):.2f}"))
    return bad


def check_float_gaps(tree, min_gap=0.8):
    """The blade is meant to float -- but the gaps have to be *visible* gaps:
    two segments sitting 0.1 apart look like a bad model, not a void blade."""
    boxes = []
    for path, c, R, t in walk_groups(tree):
        if "blade" in path or "/eye/" in path:
            boxes.append((path, V(*c["from"]), V(*c["to"])))
    gaps = []
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            pi, fi, ti = boxes[i]
            pj, fj, tj = boxes[j]
            if pi.split("/")[-2] == pj.split("/")[-2]:
                continue
            dz = max(fj[1] - ti[1], fi[1] - tj[1])
            dx = max(fj[0] - ti[0], fi[0] - tj[0])
            dzz = max(fj[2] - ti[2], fi[2] - tj[2])
            if dx < 0 and dzz < 0 and 0 < dz < min_gap:
                gaps.append((pi, pj, round(dz, 2)))
    return gaps


def bounds(tree):
    lo = np.array([1e9] * 3)
    hi = np.array([-1e9] * 3)
    for _path, c, R, t in walk_groups(tree):
        for x in (c["from"][0], c["to"][0]):
            for y in (c["from"][1], c["to"][1]):
                for z in (c["from"][2], c["to"][2]):
                    p = R @ V(x, y, z) + t
                    lo, hi = np.minimum(lo, p), np.maximum(hi, p)
    return lo, hi


PREVIEWS = [
    ("", 222.0, 12.0, 148.0, (0.0, 58.0, 0.0)),
    ("_front", 180.0, 6.0, 148.0, (0.0, 58.0, 0.0)),
    ("_side", 268.0, 6.0, 148.0, (0.0, 58.0, 0.0)),
    ("_head", 228.0, 16.0, 70.0, (0.0, 100.0, 0.0)),
    ("_grip", 232.0, 12.0, 54.0, (0.0, 44.0, 0.0)),
]


# --- animation -------------------------------------------------------------
def build_animations(by_name: dict) -> list:
    """A two-second idle: the spear drifts, the eye pulses, and the four blade
    pieces bob and turn out of phase -- they are not attached to anything, so
    they should not move like one object."""
    # each helper returns ONE channel's keyframes; a bone's track is the list of
    # its channels (make_animation flattens one level, not two)
    def bob(keys):
        return [kf("position", t, (0, v, 0), "catmullrom") for t, v in keys]

    def turn(keys):
        return [kf("rotation", t, (0, v, 0), "catmullrom") for t, v in keys]

    return [make_animation("animation.void_spear.idle", 2.0, {
        "void_spear": [bob(((0.0, 0), (1.0, 0.8), (2.0, 0)))],
        "eye": [[kf("scale", t, (v, v, v), "catmullrom")
                 for t, v in ((0.0, 1.0), (0.5, 1.09), (1.0, 0.95),
                              (1.5, 1.05), (2.0, 1.0))],
                [kf("rotation", t, (0, v, 0), "catmullrom")
                 for t, v in ((0.0, 0), (2.0, 90))]],
        "blade0": [bob(((0.0, 0), (0.7, 0.9), (1.5, -0.4), (2.0, 0))),
                   turn(((0.0, 0), (1.1, 10), (2.0, 0)))],
        "blade1": [bob(((0.0, 0), (0.9, 1.1), (1.7, -0.5), (2.0, 0))),
                   turn(((0.0, 0), (0.8, -12), (2.0, 0)))],
        "blade2": [bob(((0.0, 0), (0.5, 1.3), (1.3, -0.6), (2.0, 0))),
                   turn(((0.0, 0), (1.5, 14), (2.0, 0)))],
        "blade3": [bob(((0.0, 0), (1.2, 1.5), (1.9, -0.5), (2.0, 0))),
                   turn(((0.0, 0), (0.6, -16), (2.0, 0)))],
        "shards": [bob(((0.0, 0), (0.8, 1.6), (1.6, -0.8), (2.0, 0))),
                   [kf("rotation", 0.0, (0, 0, 0), "catmullrom"),
                    kf("rotation", 2.0, (0, 40, 0), "catmullrom")]],
    }, by_name)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-preview", action="store_true")
    args = ap.parse_args()

    tree = build_tree()

    bad = coplanar_conflicts(tree)
    if bad:
        for pi, pj, axis, tag, coord in bad[:20]:
            print(f"  z-fight risk: {pi} / {pj} on {axis}={coord:.3f} ({tag})")
        raise SystemExit(f"{len(bad)} coplanar same-facing overlaps")

    stretched = stretch_report(tree)
    if stretched:
        agg: dict = {}
        for _path, _face, want, got in stretched:
            agg[(round(want, 2), got)] = agg.get((round(want, 2), got), 0) + 1
        print(f"stretched faces: {len(stretched)}")
        for (want, got), n in sorted(agg.items()):
            print(f"  {want:6.2f} -> {got} px   x{n}")

    thin = check_solids(tree)
    if thin:
        for path, why in thin[:10]:
            print(f"  solid: {path}: {why}")
        raise SystemExit(f"{len(thin)} bad cubes")

    gaps = check_float_gaps(tree)
    if gaps:
        print("blade gaps too small to read as deliberate:")
        for pi, pj, dz in gaps[:8]:
            print(f"  {dz}  {pi.split('/')[-1]} / {pj.split('/')[-1]}")
        raise SystemExit(f"{len(gaps)} cramped gaps")

    lo, hi = bounds(tree)
    print(f"bounds  x {lo[0]:7.2f}..{hi[0]:7.2f}  y {lo[1]:7.2f}..{hi[1]:7.2f}  "
          f"z {lo[2]:7.2f}..{hi[2]:7.2f}   (h {hi[1] - lo[1]:.1f})")

    atlases = build_atlases(tree, PAINTERS, GLOW_MATERIALS)
    for idx, atlas in atlases.items():
        unpainted = check_painted(atlas)
        if unpainted:
            raise SystemExit(f"texture {idx} rects left unpainted: {unpainted}")
    images = {idx: atlas.image() for idx, atlas in atlases.items()}
    for idx, name in ((TEX_BODY, f"{MODEL_NAME}.png"), (TEX_GLOW, f"{MODEL_NAME}_glow.png")):
        images[idx].save(os.path.join(OUT_DIR, name))

    model_path = os.path.join(OUT_DIR, f"{MODEL_NAME}.bbmodel")
    cubes = write_model(model_path, tree, atlases, images, MODEL_NAME, GLOW_MATERIALS,
                        animations=build_animations)
    used = {idx: sum(w * h for _x, _y, w, h in a.rects.values()) for idx, a in atlases.items()}
    print(f"{model_path}  ({cubes} cubes, res {atlases[TEX_BODY].size // S}, "
          f"body {atlases[TEX_BODY].size}px {len(atlases[TEX_BODY].rects)} rects "
          f"{used[TEX_BODY]}px, glow {len(atlases[TEX_GLOW].rects)} rects {used[TEX_GLOW]}px)")

    if not args.no_preview:
        render_previews(model_path, OUT_DIR, MODEL_NAME, PREVIEWS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
