"""Build 亡灵战斧 (undead_battle_axe) as a Blockbench project.

    python 兵器/undead_battle_axe/build_undead_battle_axe.py [--no-preview]

Writes <this folder>/undead_battle_axe.bbmodel (body map + emissive eye map,
both embedded as data URIs), undead_battle_axe.png + undead_battle_axe_glow.png,
and the preview renders.

A one-handed undead war axe, designed from the weapon's own anatomy rather than
from any earlier model in this repo (PREFERENCES.md 8): a bearded axe is a
curved EDGE fan on a straight haft, so --

  * the haft is a FACETED TUBE: three runs of 8 outward-facing plates (bone /
    leather grip / bone) around a hidden core, one skin per span, butted ends
    -- no stacked bands, no bamboo joints;
  * the head is an iron collar the blade roots into, and the blade is a fan of
    seven overlapping bone-steel plates chained about Z: the spine leaves the
    collar near-horizontal and lifts 18 deg to the toe, while the chords fall
    from a 17-unit beard at the haft to a 6-unit toe -- the crescent edge and
    the beard live in the plates' accumulated orientation and their chord
    profile, not in stepped boxes; each plate carries a thin bevel band along
    its cutting edge;
  * a short tapering back spike counters it, and a tapering shear caps the
    butt (both hand-built from whole-unit segments that overlap by one unit);
  * a skull crowns the collar -- cranium as a dome() plate arc over a buried
    core, brow / cheeks / maxilla rooted into it, two tusks, and ONE light:
    the eye sockets, ice-blue on the emissive map (PREFERENCES.md 5: a single
    cold self-emission; no orange anywhere in the palette).

Painting is in MODEL space (field3 over rect_grid coordinates + one global
vertical gradient, darkest at the butt, brightest at the crown): pieces at
different places are never identical and plates continue each other across the
seams; the leather wrap's bands are a function of world Y, so they run
unbroken across all eight grip plates.

Intentional overlaps (ISSUE.md 5 -- construction, not mistakes): blade plates
tuck 5 units into their predecessor (a chained fan that merely abuts opens
wedge gaps); blade root / back spike / butt shear sink into the collar or cap
ring; skull face plates bury into the cranium core; the neck tube and the core
pass through the collar; every tube run butts the next with one skin per span.
Blade plate thickness steps 3% per plate so the shingle always has a z-fight
winner (a Z rotation never moves z, ISSUE.md 3.1); sockets / eyes / tusks carry
sub-unit dims as documented trades. check_grid_xy holds the in-plane dims to
whole units and unrotated positions to the 0.5 grid; the thickness dim and the
exempt prefixes are listed as trades instead.

Validation: coplanar_conflicts == 0, zfight_world == 0, blade tuck exact,
check_solids / check_painted clean; stretch_report aggregated.
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.dont_write_bytecode = True
REPO = HERE
while not os.path.isfile(os.path.join(REPO, "tools", "bbmodel_kit.py")):
    parent = os.path.dirname(REPO)
    if parent == REPO:
        raise SystemExit(f"repo root not found above {HERE}")
    REPO = parent
sys.path.insert(0, os.path.join(REPO, "tools"))
from bbmodel_kit import V, walk_groups, coplanar_conflicts, stretch_report, zfight_world  # noqa: E402
from bbmodel_build import (S, TEX_BODY, TEX_GLOW, at, bounds, build_atlases,  # noqa: E402
                           check_painted, dome, edge_lit, field3, group, box, ring,
                           rect_grid, render_previews, rng_for, streaks, tint,
                           unit_mask, write_model, add_mirrors)

OUT_DIR = HERE
MODEL_NAME = "undead_battle_axe"
GLOW_MATERIALS = {"eye"}

Y_TOP = 110.0        # the vertical gradient's ceiling (crown); butt is darkest

# in-plane dims of these prefixes carry documented sub-unit trades (small
# facial features); everything else is held to whole units / the 0.5 grid
TRADE_PREFIXES = ("socket_", "eye_", "fang")


# --- palette (no orange anywhere; the only emission is the ice-blue eye) -----
BONE_HI, BONE = (238, 233, 216), (216, 208, 186)
BONE_MID, BONE_DK, BONE_DEEP = (186, 176, 152), (148, 138, 114), (100, 91, 70)
MOSS = (116, 128, 98)
IRON_HI, IRON, IRON_DK, IRON_DEEP = (132, 138, 144), (98, 104, 110), (62, 67, 72), (32, 35, 38)
STEEL_HI, STEEL_MID, STEEL_DEEP = (226, 232, 228), (152, 162, 158), (104, 112, 108)
LEATH_HI, LEATH, LEATH_DK, LEATH_DEEP = (122, 94, 66), (94, 70, 48), (60, 44, 30), (38, 28, 20)
HOLLOW = (14, 15, 17)
EYE_HI, EYE_DEEP = (224, 242, 255), (34, 62, 96)


# --- painters: model-space fields, no per-cube stamping ----------------------
def _grad(Y, lo, hi):
    """Global vertical gradient: t=0 at the butt, 1 at the crown."""
    t = np.clip(Y / Y_TOP, 0.0, 1.0)[..., None]
    return np.array(lo, float) * (1 - t) + np.array(hi, float) * t


def _paint_base(cv, r, key, lo, hi, scale=9.0, seed=17, mossy=False):
    """Shared body painter: Y gradient x field3 mottle x optional moss."""
    a = at(cv, r)
    rng = rng_for(key)
    X, Y, Z = rect_grid(key, r)
    col = _grad(Y, lo, hi)
    f = field3(X, Y, Z, scale=scale, seed=seed)
    col = col * (0.90 + 0.20 * f[..., None])
    if mossy:
        m = field3(X, Y, Z, scale=4.5, seed=41) > 0.78
        col[m] = col[m] * 0.5 + np.array(MOSS, float) * 0.5
    mm = unit_mask(a.shape[:2], rng, 0.05)
    col[mm] = col[mm] * 0.84
    a[:, :, :3] = np.clip(col, 0, 255).astype(np.uint8)
    a[:, :, 3] = 255
    return a, rng


def paint_bone(cv, r, key):
    a, rng = _paint_base(cv, r, key, BONE_DK, BONE_HI, mossy=True)
    streaks(a, rng, BONE_DEEP, max(1, a.shape[1] // (4 * S)), vertical=True, lo=3, hi=6)
    edge_lit(a, top=BONE_HI, bottom=BONE_DEEP)


def paint_bone_dark(cv, r, key):
    a, rng = _paint_base(cv, r, key, (78, 72, 58), BONE_MID, seed=29)
    tint(a, rng, BONE_DEEP, 0.10)
    edge_lit(a, top=BONE_MID, bottom=BONE_DEEP)


def paint_iron(cv, r, key):
    a, rng = _paint_base(cv, r, key, IRON_DK, IRON_HI, scale=7.0, seed=53)
    streaks(a, rng, IRON_DEEP, max(1, a.shape[1] // (3 * S)), vertical=False, lo=2, hi=4)
    edge_lit(a, top=IRON_HI, bottom=IRON_DEEP)


def paint_iron_dark(cv, r, key):
    a, rng = _paint_base(cv, r, key, (18, 20, 22), IRON_DK, scale=7.0, seed=61)
    tint(a, rng, (10, 11, 13), 0.12)
    edge_lit(a, top=IRON, bottom=(12, 13, 15))


def paint_steel(cv, r, key):
    """The cutting bevel: cold pale steel on the global gradient, with bites
    taken out of it on the wide faces."""
    a = at(cv, r)
    rng = rng_for(key)
    X, Y, Z = rect_grid(key, r)
    col = _grad(Y, STEEL_MID, STEEL_HI)
    f = field3(X, Y, Z, scale=6.0, seed=71)
    col = col * (0.94 + 0.10 * f[..., None])
    a[:, :, :3] = np.clip(col, 0, 255).astype(np.uint8)
    a[:, :, 3] = 255
    w = key[2]                       # the face's width in model units
    if w >= 6:
        ph = a.shape[0]
        for _ in range(2):
            x = rng.randrange(max(1, a.shape[1] // S)) * S
            d = rng.randint(1, max(1, ph // S - 1)) * S
            a[ph - d:, x:x + S, :3] = np.array(STEEL_DEEP, np.uint8)
    edge_lit(a, top=STEEL_DEEP, bottom=(244, 248, 246))


def paint_leather(cv, r, key):
    """Grip wrap whose bands are a function of WORLD Y -- they run unbroken
    across all eight grip plates."""
    a = at(cv, r)
    rng = rng_for(key)
    X, Y, Z = rect_grid(key, r)
    col = _grad(Y, LEATH_DK, LEATH_HI)
    band = (Y % 5.0) < 1.4
    stitch = (Y % 5.0) < 2.2
    col[band] = np.array(LEATH_DEEP, float)
    col[stitch & ~band] = np.array(LEATH, float)
    f = field3(X, Y, Z, scale=5.0, seed=83)
    col = col * (0.92 + 0.14 * f[..., None])
    a[:, :, :3] = np.clip(col, 0, 255).astype(np.uint8)
    a[:, :, 3] = 255
    edge_lit(a, top=LEATH, bottom=LEATH_DEEP)


def paint_fang(cv, r, key):
    a = at(cv, r)
    X, Y, Z = rect_grid(key, r)
    col = _grad(Y, BONE_MID, (246, 242, 228))
    f = field3(X, Y, Z, scale=4.0, seed=97)
    col = col * (0.94 + 0.10 * f[..., None])
    a[:, :, :3] = np.clip(col, 0, 255).astype(np.uint8)
    a[:, :, 3] = 255
    edge_lit(a, top=(250, 248, 238), bottom=BONE_DK)


def paint_hollow(cv, r, key):
    a = at(cv, r)
    X, Y, Z = rect_grid(key, r)
    col = _grad(Y, (8, 9, 10), (26, 28, 30))
    f = field3(X, Y, Z, scale=5.0, seed=103)
    col = col * (0.9 + 0.2 * f[..., None])
    a[:, :, :3] = np.clip(col, 0, 255).astype(np.uint8)
    a[:, :, 3] = 255


def paint_eye(cv, r, key):
    """The one emissive: an ice-blue burn, hottest at the core (glow map)."""
    a = at(cv, r)
    h, w = a.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    d = np.clip(np.sqrt(((yy - (h - 1) / 2) / max(1.0, h * 0.62)) ** 2 +
                        ((xx - (w - 1) / 2) / max(1.0, w * 0.62)) ** 2), 0, 1)
    col = (np.array(EYE_HI, float) * (1 - d[..., None]) +
           np.array(EYE_DEEP, float) * d[..., None])
    a[:, :, :3] = np.clip(col, 0, 255).astype(np.uint8)
    a[:, :, 3] = 255


PAINTERS = {"bone": paint_bone, "bone_dark": paint_bone_dark, "iron": paint_iron,
            "iron_dark": paint_iron_dark, "steel": paint_steel, "leather": paint_leather,
            "fang": paint_fang, "hollow": paint_hollow, "eye": paint_eye}


# --- geometry ----------------------------------------------------------------
# Haft: one hidden core, tube skins per span (outer surface = exactly one layer).
CORE = box("haft_core", "bone_dark", (-1.0, 6.0, -1.0), (1.0, 93.0, 1.0))

SPINE_Y = 78.0        # the blade's back line (inside the collar)
BLADE_X0 = -2.5       # root joint, buried half a unit into the collar wall
PLATE_LEN, PLATE_STEP = 10.0, 5.0
ANGLE0, ANGLE_STEP = 0.0, -3.0           # near-straight spine, lifting to the toe
CHORDS = [17, 16, 14, 12, 10, 8, 6]      # deep beard at the haft -> shallow toe
BODY_Z, EDGE_Z, EDGE_H = 1.1, 0.6, 2


def build_haft():
    """Three tube runs + the leather grip: one skin per span, butted ends."""
    return (
        [CORE]
        + ring("haft_lo", 26.0, 2.0, 2.0, 8, 32, 1.0, "bone")     # y 10..42
        + ring("grip", 50.0, 2.4, 2.4, 8, 16, 1.0, "leather")     # y 42..58
        + ring("haft_mid", 66.0, 2.0, 2.0, 8, 16, 1.0, "bone")    # y 58..74
        + ring("neck", 88.5, 1.75, 1.75, 8, 8, 1.0, "bone")       # y 84.5..92.5
    )


def build_butt():
    """Iron cap ring and a slim bone peg sinking into the hidden core
    (whole-unit segment, on the 0.5 grid)."""
    cap = ring("buttcap", 8.0, 2.3, 2.3, 8, 4, 1.0, "iron_dark")  # y 6..10
    peg = box("buttshear0", "iron", (-0.5, 1.0, -0.5), (0.5, 7.0, 0.5))
    return cap + [peg]


def build_collar():
    """The axe eye: an iron ring the blade, the back spike and the neck
    all socket into."""
    return ring("collar", 79.5, 2.5, 2.5, 8, 11, 1.0, "iron")     # y 74..85


def build_back_spike():
    """Two whole-unit segments, the second tapering a full step in both cross
    axes and overlapping the first by one; the root sits half a unit into the
    collar wall (clear of the ring plates' inner plane)."""
    return [
        box("backspike0", "iron", (2.5, 77.0, -1.0), (6.5, 79.0, 1.0)),
        box("backspike1", "iron", (5.0, 77.5, -0.5), (10.0, 78.5, 0.5)),
    ]


def build_blade():
    """Nine overlapping plates chained about Z. Each plate = body band + thin
    bevel band, butted (opposite-facing, legal); thickness steps 3% per plate
    so the shingle always has a z-fight winner."""
    n = len(CHORDS)
    groups = None
    for i in reversed(range(n)):            # blade0 ends up outermost, carrying
        jx = BLADE_X0 - i * PLATE_STEP      # ANGLE0; each deeper group adds
        chord = CHORDS[i]                   # ANGLE_STEP -- the fan accumulates
        f = 1.0 + 0.03 * (n - 1 - i)        # 26deg at the beard -> -38 at the toe
        zb, ze = BODY_Z * f, EDGE_Z * f     # 26deg at the beard -> -38 at the toe
        cubes = [
            box(f"plate{i}_body", "bone",
                (jx - PLATE_LEN, SPINE_Y - (chord - EDGE_H), -zb), (jx, SPINE_Y, zb)),
            box(f"plate{i}_edge", "steel",
                (jx - PLATE_LEN, SPINE_Y - chord, -ze), (jx, SPINE_Y - (chord - EDGE_H), ze)),
        ]
        rot = [0.0, 0.0, ANGLE0] if i == 0 else [0.0, 0.0, ANGLE_STEP]
        groups = group(f"blade{i}", cubes=cubes,
                       children=[groups] if groups else [],
                       origin=(jx, SPINE_Y, 0.0), rotation=rot)
    return group("blade", children=[groups], origin=(0.0, SPINE_Y, 0.0))


def build_skull():
    """Crown skull: dome arc over a buried core; brow / sockets / cheeks /
    maxilla rooted into it; two tusks; ONE light in the sockets."""
    parts = (
        dome("cranium", (0.0, 93.5, 0.5), 5.0, 8, -100.0, 100.0, 7, 1.0, "bone")
        + [box("cranium_core", "bone_dark", (-3.0, 88.0, -2.5), (3.0, 95.0, 2.5)),
           box("brow", "bone", (-4.0, 91.5, -4.5), (4.0, 93.5, -2.0)),
           box("socket_l", "hollow", (-2.9, 89.5, -4.6), (-1.1, 91.5, -2.0)),
           box("eye_l", "eye", (-2.7, 89.8, -4.8), (-1.4, 91.2, -3.6)),
           box("cheek_l", "bone", (-3.5, 87.5, -4.5), (-1.5, 89.5, -2.0)),
           box("maxilla", "bone", (-1.5, 87.5, -4.0), (1.5, 89.5, -2.0))]
    )
    parts.append(box("fang_l", "fang", (-1.5, 85.5, -4.0), (-0.5, 87.5, -3.0)))
    # fang_r comes from add_mirrors() -- authoring it here too would duplicate it
    return parts


def build_tree():
    head = group("head", origin=(0.0, 74.0, 0.0),
                 cubes=build_collar() + build_back_spike(),
                 children=[build_blade(),
                           group("skull", cubes=build_skull(), origin=(0.0, 92.0, 0.0))])
    root = group(MODEL_NAME, origin=(0.0, 0.0, 0.0),
                 children=[group("butt", cubes=build_butt(), origin=(0.0, 8.0, 0.0)),
                           group("haft", cubes=build_haft(), origin=(0.0, 10.0, 0.0)),
                           head])
    return add_mirrors(root)   # complete the ring/dome left halves


def check_blade_tuck(tree):
    """Plate i+1 must tuck `reach` units into plate i once the whole fan is
    posed -- exact, via the ancestor-chain transforms."""
    pose, boxes = {}, {}
    for path, c, R, t in walk_groups(tree):
        pose[path] = (R, t)
        boxes[path] = (V(*c["from"]), V(*c["to"]))
    reach = PLATE_LEN - PLATE_STEP
    def blade_path(i, part):
        chain = "/".join(f"blade{k}" for k in range(0, i + 1))
        return f"/{MODEL_NAME}/head/blade/{chain}/plate{i}_{part}"
    for i in range(len(CHORDS) - 1):
        nxt, chord = i + 1, CHORDS[i + 1]
        jx = BLADE_X0 - nxt * PLATE_STEP
        # sample down to the deepest depth BOTH plates share -- my chords rise
        # to a belly then fall, so the deeper of the pair legitimately hangs
        # past the shallower one's edge
        shared = min(CHORDS[i], chord)
        for depth, where in ((0.5, "the spine"), (shared - 0.5, "the bevel")):
            world = None
            for part in ("body", "edge"):
                p_new = blade_path(nxt, part)
                if p_new not in pose:
                    continue
                R_n, t_n = pose[p_new]
                world = R_n @ V(jx - reach * 0.5, SPINE_Y - depth, 0.0) + t_n
                hits = []
                for part2 in ("body", "edge"):
                    p_old = blade_path(i, part2)
                    R_o, t_o = pose[p_old]
                    loc = R_o.T @ (world - t_o)
                    lo, hi = boxes[p_old]
                    if all(lo[k] - 1e-6 <= loc[k] <= hi[k] + 1e-6 for k in range(3)):
                        hits.append(part2)
                if not hits:
                    raise AssertionError(
                        f"blade plate {nxt} does not tuck into plate {i} at {where}")
    return reach


def check_grid_xy(tree):
    """Whole-unit in-plane sizes (dims 0/1) on every cube, 0.5-grid positions on
    unrotated cubes. Documented trades: blade-plate thickness lives on z (the
    shingle taper), and the TRADE_PREFIXES' small facial features carry
    sub-unit dims/positions -- both reported as trades instead of failures."""
    bad, trades = [], []
    for path, c, _R, _t in walk_groups(tree):
        name = path.rsplit("/", 1)[1]
        if not c.get("rotation"):
            for k in range(3):
                for v in (c["from"][k], c["to"][k]):
                    if abs(v * 2 - round(v * 2)) <= 1e-6:
                        continue
                    if name.startswith("plate") and k == 2:
                        trades.append((path, "pos z", v))
                    elif name.startswith(TRADE_PREFIXES):
                        trades.append((path, f"pos {'xyz'[k]}", v))
                    else:
                        bad.append((path, "off-grid", v))
        for k in (0, 1):
            d = c["to"][k] - c["from"][k]
            if d <= 1e-6:
                bad.append((path, "degenerate", k))
            elif abs(d - round(d)) > 1e-6:
                if name.startswith(TRADE_PREFIXES):
                    trades.append((path, k, d))
                else:
                    bad.append((path, f"non-unit size {d:.3f}", k))
        d2 = c["to"][2] - c["from"][2]
        if abs(d2 - round(d2)) > 1e-6:
            trades.append((path, 2, d2))
    return bad, trades


def check_solids(tree):
    bad = []
    for path, c, _R, _t in walk_groups(tree):
        d = [c["to"][k] - c["from"][k] for k in range(3)]
        if any(v <= 1e-6 for v in d):
            bad.append((path, "degenerate"))
        elif min(d) < 0.5:
            bad.append((path, f"thin {min(d):.2f}"))
    return bad


PREVIEWS = [
    ("", 208.0, 10.0, 175.0, (-12.0, 52.0, 0.0)),
    ("_front", 180.0, 6.0, 175.0, (-12.0, 52.0, 0.0)),
    ("_back", 0.0, 6.0, 175.0, (-12.0, 52.0, 0.0)),
    ("_side", 248.0, 6.0, 165.0, (0.0, 52.0, 0.0)),
    ("_head", 204.0, 16.0, 60.0, (0.0, 88.0, 0.0)),
    ("_face", 180.0, 10.0, 50.0, (0.0, 90.0, 0.0)),
    ("_blade", 216.0, 20.0, 80.0, (-16.0, 72.0, 0.0)),
]


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

    zf = zfight_world(tree)
    if zf:
        for pi, pj, ta, tb, _n, coord in zf[:20]:
            print(f"  world z-fight: {pi} / {pj} ({ta}/{tb}) at {coord:.3f}")
        raise SystemExit(f"{len(zf)} world-space coplanar overlaps")

    bad, trades = check_grid_xy(tree)
    if bad:
        for path, why, v in bad[:20]:
            print(f"  grid: {path}: {why} ({v})")
        raise SystemExit(f"{len(bad)} grid violations")
    if trades:
        print(f"documented sub-unit trades: {len(trades)}")
        for path, k, d in trades[:12]:
            axis = k if isinstance(k, str) else 'xyz'[k]
            print(f"  {axis} = {d:.3f}  {path.rsplit('/', 1)[-1]}")

    bad = check_solids(tree)
    if bad:
        for path, why in bad[:20]:
            print(f"  solid: {path}: {why}")
        raise SystemExit(f"{len(bad)} bad cubes")

    reach = check_blade_tuck(tree)
    print(f"blade tuck ok (overlap {reach:.1f} units per joint)")

    stretched = stretch_report(tree)
    agg: dict = {}
    for _path, _face, want, got in stretched:
        agg[(round(want, 2), got)] = agg.get((round(want, 2), got), 0) + 1
    print(f"stretched faces (rounded uv vs true size): {len(stretched)}")
    for (want, got), n in sorted(agg.items()):
        print(f"  {want:6.2f} -> {got} px   x{n}")

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
    cubes = write_model(model_path, tree, atlases, images, MODEL_NAME, GLOW_MATERIALS)
    used = {idx: sum(w * h for _x, _y, w, h in a.rects.values()) for idx, a in atlases.items()}
    print(f"{model_path}  ({cubes} cubes, res {atlases[TEX_BODY].size // S}, "
          f"body {atlases[TEX_BODY].size}px {len(atlases[TEX_BODY].rects)} rects "
          f"{used[TEX_BODY]}px, glow {len(atlases[TEX_GLOW].rects)} rects {used[TEX_GLOW]}px)")

    if not args.no_preview:
        render_previews(model_path, OUT_DIR, MODEL_NAME, PREVIEWS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
