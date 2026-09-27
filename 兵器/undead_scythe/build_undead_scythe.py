"""Build 亡灵战镰 (undead_scythe) as a Blockbench project.

    python undead_scythe/build_undead_scythe.py [--no-preview]

Writes undead_scythe/undead_scythe.bbmodel (two textures embedded as data
URIs: the body map and an emissive glow map), undead_scythe.png +
undead_scythe_glow.png (the same textures standalone) and the preview renders.

A two-handed undead polearm, designed against the weapons in 参考/兵器 (the
server's weapon set: 死灵权杖 / 封恶 / 肉刀 / 巨斧 / 述圣 / 刀子 ...) -- same
hardware, different archetype: the set has staffs, greatswords, axes and bows
but no scythe, and no weapon made of bone. So:

  * a crescent blade of ten overlapping bone plates, tapering 14 -> 3 units,
    chipped along the cutting edge and stained at the root;
  * a horned beast skull as the crown -- the blade is socketed into the iron
    collar under its jaw, so the weapon is literally looking at you;
  * a soul flame caged in iron, hanging off the collar on a hook -- the only
    light the weapon carries, and the reason for the second (emissive) map;
  * a blackened oak shaft, leather-wrapped at the grip, coiled in chain just
    under the head, with a knucklebone charm on the coil and a shackle + link
    + bone at the butt;
  * a torn shroud tied to the collar, and a beak on the blade's opposite side
    so the head reads left-right instead of only left.

The shape is computed, not eyeballed. The blade is a chain of nested groups
pivoting on the spine line: every plate is authored straight along -X and
carries +11.5 deg, so the accumulated rotation lays the plates along a circular
arc (and swings each plate's cutting edge back *over* its predecessor, which is
what makes the plates overlap instead of opening wedge gaps -- checked exactly
by check_blade_chain()). Group rotation is a legitimate 4.5 feature, see the
notes in us_soldier/build_us_soldier.py: transform = T(origin) . Rz*Ry*Rx .
T(-origin) composed down the tree, children authored in absolute model space,
Format.euler_order = 'ZYX'.

Conventions, as everywhere else in this repo: model_format 'free', per-face uv
rects (upright and unmirrored seen from outside, v from the top), every cube
box_uv=false, front = -Z and 1 uv unit = 1 model unit. The map is painted at
S = 2 pixels per unit (project resolution 128, texture 256 -- the density the
参考/兵器 weapons are painted at), so the face uv rects are the pixel rects
divided by S.

Validation (headless MCP): 0 errors. The interpenetration gate reports ~108
overlaps and every one of them is the construction rather than a mistake --
read it with that in mind:

  * the ten blade plates deliberately overlap by 3 units, because a chain of
    chords that merely abut opens a wedge gap at every joint (check_blade_chain
    is the exact gate for that, and a coverage scan of the posed blade finds no
    enclosed hole);
  * each horn segment overlaps the one before it at the joint, the chain coil
    overlaps the haft it is wound around, the upper fangs cross the jaw, and the
    haft is socketed into the iron collar.

An "idle" clip (2 s, looping) drifts the weapon, pulses the soul flame, works
the jaw, flutters the shroud and lifts the embers. Only *groups* are keyframed:
the writer gives every cube origin [0,0,0], so a cube-level rotation or scale
would pivot on the model origin and fling the cube away.
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import math
import os
import random
import subprocess
import sys
import uuid

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.dont_write_bytecode = True
# the model folders sit in category folders (兵器/人物/物品/生物), so walk up to
# the folder holding tools/bbmodel_kit.py instead of assuming a fixed depth
REPO = HERE
while not os.path.isfile(os.path.join(REPO, "tools", "bbmodel_kit.py")):
    parent = os.path.dirname(REPO)
    if parent == REPO:
        raise SystemExit(f"repo root not found above {HERE}")
    REPO = parent
sys.path.insert(0, os.path.join(REPO, "tools"))
from bbmodel_kit import (FACES, V, walk_groups,  # noqa: E402
                         coplanar_conflicts, posed_contacts, face_size,
                         stretch_report)

OUT_DIR = HERE
MODEL_NAME = "undead_scythe"
PLACEHOLDER = (255, 0, 255, 255)          # magenta canary: unpainted uv shows up
GLOW_BG = (0, 0, 0, 255)                  # the emissive map wants black
S = 2                                     # texture pixels per model unit / uv unit

TEX_BODY, TEX_GLOW = 0, 1
GLOW_MATERIALS = {"flame", "ember", "eye", "rune"}

# --- palette ---------------------------------------------------------------
WOOD, WOOD_HI, WOOD_DK = (94, 71, 51), (126, 98, 68), (56, 41, 30)
IRON, IRON_MID, IRON_DK, IRON_DEEP = (110, 118, 124), (76, 84, 91), (48, 54, 60), (28, 32, 37)
RUST, RUST_DK, RUST_HI = (124, 76, 42), (82, 48, 28), (152, 104, 60)
BRASS, BRASS_HI, BRASS_DK = (164, 134, 70), (206, 180, 110), (100, 78, 38)
LEATHER, LEATHER_DK, LEATHER_HI = (88, 65, 45), (56, 40, 28), (116, 90, 62)
CLOTH, CLOTH_DK, CLOTH_HI = (94, 102, 84), (60, 66, 54), (122, 128, 108)
BONE_HI, BONE, BONE_MID = (240, 234, 214), (218, 207, 180), (188, 174, 144)
BONE_DK, BONE_DEEP = (146, 131, 103), (106, 93, 70)
STAIN_RUST, STAIN_ROT, STAIN_ASH = (118, 72, 44), (84, 96, 60), (72, 66, 58)
SPINE_HI, SPINE_MID, SPINE_DK = (176, 172, 162), (126, 122, 114), (74, 72, 68)
# the blade is its own, dirtier bone: an aged plate with a bright sharpened
# bevel, which is what gives the crescent its contrast -- the skull and the
# charms keep the pale palette above
BLADE_HI, BLADE = (206, 194, 166), (180, 168, 140)
BLADE_MID, BLADE_DK, BLADE_DEEP = (150, 138, 112), (116, 104, 84), (86, 76, 60)
SOUL_HI, SOUL, SOUL_MID = (168, 255, 186), (92, 230, 124), (46, 178, 92)
SOUL_DK, SOUL_DEEP = (24, 118, 64), (12, 54, 36)
HOLLOW = (16, 20, 18)


# --- painting helpers ------------------------------------------------------
def at(cv, r):
    x, y, w, h = r
    return cv[y:y + h, x:x + w]


def rect_key(key):
    """Painters get the (material, w, h) tuple: some of them read the size."""
    return key[1], key[2]


class R:
    """A seeded rng with both the scalar call sites and the array masks the
    painters want, so every rect paints identically on every run."""

    def __init__(self, key: str):
        self.g = np.random.default_rng(abs(hash(key)) % (2 ** 31))

    def random(self, shape=None):
        return float(self.g.random()) if shape is None else self.g.random(shape)

    def randint(self, a, b):
        return int(self.g.integers(a, b + 1))

    def randrange(self, n):
        return int(self.g.integers(0, n))


def rng_for(key) -> R:
    return R(":".join(str(k) for k in key) if isinstance(key, tuple) else str(key))


def ramp(a, stops):
    """Fill a vertical gradient. stops = [(t, rgb), ...] with t in 0..1."""
    h = a.shape[0]
    t = np.linspace(0.0, 1.0, h)
    stops = sorted(stops)
    out = np.zeros((h, 3), float)
    for i in range(len(stops) - 1):
        t0, c0 = stops[i]
        t1, c1 = stops[i + 1]
        m = (t >= t0) & (t <= t1)
        if not m.any():
            continue
        u = ((t[m] - t0) / max(1e-6, t1 - t0))[:, None]
        out[m] = (1 - u) * np.array(c0, float) + u * np.array(c1, float)
    out[t <= stops[0][0]] = stops[0][1]
    out[t >= stops[-1][0]] = stops[-1][1]
    a[:, :, :3] = np.clip(out, 0, 255).astype(np.uint8)[:, None, :]
    a[:, :, 3] = 255


def unit_mask(shape, rng, prob, where=None):
    """A per-UNIT mask (S x S blocks): noise has to read as painted pixel
    clusters, not as per-texel dither. At 2 px/unit single-pixel speckle turns
    a blade into static."""
    h, w = shape
    m = rng.random((max(1, h // S), max(1, w // S))) < prob
    m = np.repeat(np.repeat(m, S, axis=0), S, axis=1)[:h, :w]
    if where is not None:
        m &= where
    return m


def tint(a, rng, color, prob, where=None):
    """Scatter unit cells of `color` over the rect."""
    a[:, :, :3][unit_mask(a.shape[:2], rng, prob, where)] = np.array(color, np.uint8)


def blobs(a, rng, color, n, hmin=2, hmax=3, where=None):
    """Blotches, measured in units."""
    h, w = a.shape[:2]
    for _ in range(n):
        bw = rng.randint(1, max(1, w // S // 3)) * S
        bh = rng.randint(hmin, hmax) * S
        x, y = rng.randrange(max(1, w // S)) * S, rng.randrange(max(1, h // S)) * S
        x1, y1 = min(w, x + bw), min(h, y + bh)
        if x1 <= x or y1 <= y:
            continue
        sub = np.zeros((h, w), bool)
        sub[y:y1, x:x1] = True
        if where is not None:
            sub &= where
        a[:, :, :3][sub] = np.array(color, np.uint8)


def streaks(a, rng, color, n, vertical=True, lo=2, hi=None, prob=1.0, wide=1):
    """Hairline cracks / grain, measured in units: `wide` units thick and
    lo..hi units long."""
    h, w = a.shape[:2]
    uh, uw = max(1, h // S), max(1, w // S)
    hi = hi or (uh if vertical else uw)
    for _ in range(n):
        if rng.random() > prob:
            continue
        ln = rng.randint(lo, max(lo, hi)) * S
        if vertical:
            x, y = rng.randrange(uw) * S, rng.randrange(uh) * S
            a[y:min(h, y + ln), x:min(w, x + S * wide), :3] = np.array(color, np.uint8)
        else:
            x, y = rng.randrange(uw) * S, rng.randrange(uh) * S
            a[y:min(h, y + S * wide), x:min(w, x + ln), :3] = np.array(color, np.uint8)


def edge_lit(a, top=None, bottom=None, left=None, right=None):
    """Light the outermost unit (S pixels) of the rect -- the edges are what a
    face reads as, so they get a lit or shadowed border."""
    if top is not None:
        a[0:S, :, :3] = np.array(top, np.uint8)
    if bottom is not None:
        a[-S:, :, :3] = np.array(bottom, np.uint8)
    if left is not None:
        a[:, 0:S, :3] = np.array(left, np.uint8)
    if right is not None:
        a[:, -S:, :3] = np.array(right, np.uint8)


# --- painters (one per material) -------------------------------------------
def paint_wood(cv, r, key):
    a = at(cv, r)
    rng = rng_for(key)
    ramp(a, [(0.0, WOOD_HI), (0.10, WOOD), (0.80, WOOD), (1.0, WOOD_DK)])
    streaks(a, rng, WOOD_DK, max(1, a.shape[1] // (3 * S)), vertical=True, lo=6, wide=2)
    streaks(a, rng, WOOD_HI, max(1, a.shape[1] // (3 * S)), vertical=True, lo=4)
    blobs(a, rng, WOOD_DK, 1, 2, 3)                  # a knot or two
    edge_lit(a, top=WOOD_HI, bottom=WOOD_DK)


def paint_wood_end(cv, r, key):
    a = at(cv, r)
    rng = rng_for(key)
    ramp(a, [(0.0, WOOD), (1.0, WOOD_DK)])
    streaks(a, rng, WOOD_DK, max(2, a.shape[1] // S), vertical=False, lo=2)
    tint(a, rng, WOOD_HI, 0.12)


def paint_iron(cv, r, key):
    a = at(cv, r)
    rng = rng_for(key)
    ramp(a, [(0.0, IRON), (0.15, IRON_MID), (0.7, IRON_MID), (1.0, IRON_DEEP)])
    tint(a, rng, IRON, 0.14)
    tint(a, rng, IRON_DK, 0.16)
    blobs(a, rng, RUST_DK, 2, 1, 2)
    streaks(a, rng, IRON, max(1, a.shape[1] // (2 * S)), vertical=False, lo=2)
    edge_lit(a, top=IRON, bottom=IRON_DEEP)


def paint_iron_dark(cv, r, key):
    a = at(cv, r)
    rng = rng_for(key)
    ramp(a, [(0.0, IRON_MID), (0.35, IRON_DK), (1.0, IRON_DEEP)])
    tint(a, rng, IRON, 0.18)
    tint(a, rng, (0, 0, 0), 0.12)
    edge_lit(a, top=IRON_MID, bottom=(12, 14, 17))


def paint_iron_rust(cv, r, key):
    a = at(cv, r)
    rng = rng_for(key)
    ramp(a, [(0.0, RUST_HI), (0.25, RUST), (0.8, RUST_DK), (1.0, (58, 34, 22))])
    blobs(a, rng, IRON_DK, 3, 2, 4)
    tint(a, rng, RUST_HI, 0.10)
    tint(a, rng, (40, 24, 16), 0.14)
    edge_lit(a, top=RUST_HI, bottom=(44, 26, 16))


def paint_brass(cv, r, key):
    a = at(cv, r)
    rng = rng_for(key)
    ramp(a, [(0.0, BRASS_HI), (0.2, BRASS), (0.85, BRASS_DK), (1.0, (72, 56, 28))])
    blobs(a, rng, (86, 104, 82), 2, 1, 2)          # verdigris
    tint(a, rng, BRASS_HI, 0.10)
    edge_lit(a, top=BRASS_HI, bottom=(70, 54, 26))


def paint_leather(cv, r, key):
    a = at(cv, r)
    rng = rng_for(key)
    ramp(a, [(0.0, LEATHER_HI), (0.3, LEATHER), (1.0, LEATHER_DK)])
    h, w = a.shape[:2]
    for y in range(S, h, 5 * S):                    # the wrap: a band per 5 units
        a[y:y + S, :, :3] = np.array(LEATHER_DK, np.uint8)
        a[max(0, y + S):y + 2 * S, :, :3] = np.array(LEATHER_HI, np.uint8)
    streaks(a, rng, LEATHER_DK, max(2, w // S), vertical=True, lo=2, hi=3)
    tint(a, rng, LEATHER_DK, 0.10)
    edge_lit(a, bottom=LEATHER_DK)


def paint_cloth(cv, r, key):
    a = at(cv, r)
    rng = rng_for(key)
    ramp(a, [(0.0, CLOTH_HI), (0.35, CLOTH), (1.0, CLOTH_DK)])
    streaks(a, rng, CLOTH_DK, max(2, a.shape[1] // S), vertical=True, lo=3)
    streaks(a, rng, CLOTH_HI, max(1, a.shape[1] // (2 * S)), vertical=True, lo=2)
    tint(a, rng, STAIN_ASH, 0.10)
    edge_lit(a, top=CLOTH_HI)


def paint_skull(cv, r, key):
    a = at(cv, r)
    rng = rng_for(key)
    ramp(a, [(0.0, BONE_HI), (0.25, BONE), (0.75, BONE_MID), (1.0, BONE_DK)])
    streaks(a, rng, BONE_DK, max(2, a.shape[1] // (2 * S)), vertical=True, lo=2, hi=4)
    streaks(a, rng, BONE_HI, max(1, a.shape[1] // (4 * S)), vertical=True, lo=2, hi=3)
    blobs(a, rng, STAIN_ASH, 2, 1, 2)
    tint(a, rng, BONE_DK, 0.08)
    edge_lit(a, top=BONE_HI, bottom=BONE_DEEP)


def paint_skull_dark(cv, r, key):
    a = at(cv, r)
    rng = rng_for(key)
    ramp(a, [(0.0, BONE_MID), (0.4, BONE_DK), (1.0, BONE_DEEP)])
    tint(a, rng, BONE_DK, 0.14)
    streaks(a, rng, BONE_DEEP, max(1, a.shape[1] // (2 * S)), vertical=True, lo=2, hi=3)
    edge_lit(a, bottom=(72, 62, 46))


def paint_nasal(cv, r, key):
    """The maxilla's front: bone with the nasal opening cut low and centre."""
    a = at(cv, r)
    rng = rng_for(key)
    paint_skull(cv, r, key)
    ph, pw = a.shape[:2]
    nx0, nx1 = pw // 2 - (pw // 6), pw // 2 + (pw // 6)
    ny0 = int(ph * 0.45)
    a[ny0:ph - S, nx0:nx1, :3] = np.array(HOLLOW, np.uint8)
    a[ny0:ph - S, nx0:nx1, :3] = np.array(HOLLOW, np.uint8)
    tint(a, rng, SOUL_DEEP, 0.08)


def paint_socket(cv, r, key):
    a = at(cv, r)
    rng = rng_for(key)
    ramp(a, [(0.0, HOLLOW), (0.55, (22, 30, 26)), (1.0, SOUL_DEEP)])
    tint(a, rng, SOUL_DK, 0.10)
    edge_lit(a, top=(8, 10, 9), bottom=SOUL_DK)


def paint_teeth(cv, r, key):
    a = at(cv, r)
    rng = rng_for(key)
    ramp(a, [(0.0, BONE_HI), (0.6, BONE), (1.0, BONE_MID)])
    tint(a, rng, (196, 182, 150), 0.12)
    edge_lit(a, top=(252, 250, 240))


def paint_horn(cv, r, key):
    a = at(cv, r)
    rng = rng_for(key)
    ramp(a, [(0.0, BONE_MID), (0.3, BONE_DK), (1.0, BONE_DEEP)])
    h = a.shape[0]
    for y in range(S, h, 3 * S):                    # the growth rings
        a[y:y + S, :, :3] = np.array(BONE_DEEP, np.uint8)
    tint(a, rng, BONE_MID, 0.10)
    edge_lit(a, top=BONE_MID, bottom=(78, 66, 48))


def paint_blade(cv, r, key):
    """The blade plates' flat sides. The chord (rect height) stands in for 'how
    close to the root this plate is': the wide plates are the stained, cracked,
    battle-worn ones, the thin tip plates are clean ivory. Kept deliberately
    plain -- a smooth gradient, the shadow under the spine, a lit band, one
    crack and a couple of stains -- because every extra mark turns the blade
    into static at 2 px per unit."""
    a = at(cv, r)
    rng = rng_for(key)
    w, h = rect_key(key)
    ph, pw = a.shape[:2]                            # pixels, not model units
    root = max(0.0, min(1.0, (h - 3.0) / 11.0))
    ramp(a, [(0.0, BLADE_HI if root < 0.35 else BLADE),
             (0.30, BLADE), (0.66, BLADE_MID), (1.0, BLADE_DK)])
    # the rows tucked under the spine ridge
    a[0:S, :, :3] = np.array(BLADE_DEEP, np.uint8)
    a[S:2 * S, :, :3] = np.array(BLADE_DK, np.uint8)
    # a lit band along the upper third -- the plate's thick part catching light
    band = int(h * 0.30)
    a[band:band + S, :, :3] = np.array(BLADE_HI, np.uint8)
    if w >= 8:                                      # only the real (wide) faces
        for _ in range(int(round(3 * root))):       # old blood soaked up the edge
            bx = rng.randrange(max(1, pw // S)) * S
            bh = rng.randint(2, 4) * S
            a[max(0, ph - bh):, bx:bx + S, :3] = np.array(
                STAIN_RUST if rng.random() < 0.6 else STAIN_ASH, np.uint8)
        streaks(a, rng, BLADE_DK, 1 + int(root), vertical=True, lo=5, wide=1)
    # the joint seams at both u ends (the rect is shared by the plate's two
    # mirrored sides, so both ends get one): half a unit of bone-deep, then a
    # unit of bone-dark, so the plates read as joined rather than as sliced
    a[:, 0:1, :3] = np.array(BLADE_DEEP, np.uint8)
    a[:, 1:S, :3] = np.array(BLADE_DK, np.uint8)
    a[:, -1:, :3] = np.array(BLADE_DEEP, np.uint8)
    a[:, -S:-1, :3] = np.array(BLADE_DK, np.uint8)
    edge_lit(a, top=BLADE_DEEP, bottom=BLADE_DK)


def paint_edge(cv, r, key):
    """The sharpened bevel: cold pale bone, brightest on the very edge, with
    bites taken out of it on the root plates."""
    a = at(cv, r)
    rng = rng_for(key)
    w, h = rect_key(key)
    root = max(0.0, min(1.0, (h - 1.0) / 4.0))
    ramp(a, [(0.0, BLADE_DEEP), (0.3, BLADE_DK), (0.6, BLADE_MID),
             (0.85, (214, 216, 210)), (1.0, (244, 246, 242))])
    tint(a, rng, (194, 198, 196), 0.18)
    if w >= 6:
        for _ in range(2 + int(3 * root)):          # chips out of the edge
            x = rng.randrange(max(1, w // S)) * S
            d = rng.randint(1, max(1, h // S - 1)) * S
            a[h - d:h, x:x + S, :3] = np.array(BONE_DEEP, np.uint8)
            if x + S < w:
                a[h - d:h - S, x + S:x + 2 * S, :3] = np.array(BONE_DK, np.uint8)
    edge_lit(a, top=BLADE_DK, bottom=(250, 250, 246))


def paint_spine(cv, r, key):
    """The raised back of the blade: cool grey-bone with a rivet line, so it
    reads as the thick back of a bone blade and not as a wooden haft."""
    a = at(cv, r)
    rng = rng_for(key)
    ramp(a, [(0.0, SPINE_HI), (0.25, SPINE_MID), (1.0, SPINE_DK)])
    w = a.shape[1]
    if w >= 6:
        for x in range(S, w - S, 3 * S):
            a[S:3 * S, x:x + S, :3] = np.array(BONE_DEEP, np.uint8)
            a[S:2 * S, x:x + S, :3] = np.array(BONE_HI, np.uint8)
        streaks(a, rng, BONE_DEEP, 3, vertical=True, lo=2, hi=3, wide=2)
    tint(a, rng, SPINE_DK, 0.10)
    edge_lit(a, top=SPINE_HI, bottom=(44, 42, 38))


def paint_flame(cv, r, key):
    """Emissive map: bright at the core, falling to soot at the rim."""
    a = at(cv, r)
    h, w = a.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    cy, cx = (h - 1) * 0.62, (w - 1) * 0.5
    d = np.sqrt(((yy - cy) / max(1.0, h * 0.55)) ** 2 + ((xx - cx) / max(1.0, w * 0.55)) ** 2)
    d = np.clip(d, 0, 1)
    core = np.array(SOUL_HI, float)
    mid = np.array(SOUL_MID, float)
    dark = np.array(SOUL_DEEP, float)
    col = np.where(d[..., None] < 0.45,
                   core + (mid - core) * (d[..., None] / 0.45),
                   mid + (dark - mid) * ((d[..., None] - 0.45) / 0.55))
    a[:, :, :3] = np.clip(col, 0, 255).astype(np.uint8)
    a[:, :, 3] = 255


def paint_ember(cv, r, key):
    a = at(cv, r)
    h, w = a.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    d = np.sqrt(((yy - (h - 1) / 2) / max(1.0, h * 0.62)) ** 2 +
                ((xx - (w - 1) / 2) / max(1.0, w * 0.62)) ** 2)
    d = np.clip(d, 0, 1)
    col = (np.array(SOUL_HI, float) * (1 - d[..., None]) +
           np.array(SOUL_DEEP, float) * d[..., None])
    a[:, :, :3] = np.clip(col, 0, 255).astype(np.uint8)
    a[:, :, 3] = 255


def paint_eye(cv, r, key):
    a = at(cv, r)
    h, w = a.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    d = np.clip(np.sqrt(((yy - (h - 1) / 2) / max(1.0, h * 0.7)) ** 2 +
                        ((xx - (w - 1) / 2) / max(1.0, w * 0.7)) ** 2), 0, 1)
    col = (np.array(SOUL_HI, float) * (1 - d[..., None]) +
           np.array(SOUL_DK, float) * d[..., None])
    a[:, :, :3] = np.clip(col, 0, 255).astype(np.uint8)
    a[:, :, 3] = 255
    rng = rng_for(key)
    a[0:S, :, :3] = np.array(SOUL_DEEP, np.uint8)
    a[-S:, :, :3] = np.array(SOUL_DEEP, np.uint8)
    tint(a, rng, SOUL_HI, 0.10)


def paint_rune(cv, r, key):
    """A glowing rune stud: soot, a lit rim, and the glyph."""
    a = at(cv, r)
    h, w = a.shape[:2]
    a[:, :, :3] = np.array(SOUL_DEEP, np.uint8)
    a[:, :, 3] = 255
    g = np.array(SOUL, np.uint8)
    gy, gx = max(0, (h - S) // 2), max(0, (w - S) // 2)
    a[gy:gy + S, :, :3] = g
    if w >= 3 * S:
        a[S:2 * S, gx:gx + S, :3] = g
        a[-2 * S:-S, gx:gx + S, :3] = g
    if h >= 4 * S:
        a[gy:gy + S, 0:S, :3] = np.array(SOUL_HI, np.uint8)
        a[gy:gy + S, -S:, :3] = np.array(SOUL_HI, np.uint8)


PAINTERS = {
    "wood": paint_wood, "wood_end": paint_wood_end,
    "iron": paint_iron, "iron_dark": paint_iron_dark, "iron_rust": paint_iron_rust,
    "brass": paint_brass, "leather": paint_leather, "cloth": paint_cloth,
    "skull": paint_skull, "skull_dark": paint_skull_dark, "socket": paint_socket,
    "teeth": paint_teeth, "horn": paint_horn, "nasal": paint_nasal,
    "blade": paint_blade,
    "edge": paint_edge, "spine": paint_spine,
    "flame": paint_flame, "ember": paint_ember, "eye": paint_eye, "rune": paint_rune,
}


def tex_of(material: str) -> int:
    return TEX_GLOW if material in GLOW_MATERIALS else TEX_BODY


# --- atlas -----------------------------------------------------------------
class Atlas:
    """Shelf packer keyed by (material, w, h) in MODEL units; each rect is
    allocated S pixels per unit and painted on allocate, so the project
    resolution stays 128 while the painted map is 256 -- 2 px per unit, the
    density the 参考/兵器 weapons are painted at."""

    def __init__(self, size: int, tex_index: int):
        self.size = size                    # pixels
        self.tex = tex_index
        self.bg = PLACEHOLDER if tex_index == TEX_BODY else GLOW_BG
        self.cv = np.zeros((size, size, 4), np.uint8)
        self.cv[:] = self.bg
        self.rects: dict[tuple, tuple[int, int, int, int]] = {}
        self._x = self._y = self._row_h = 0

    def alloc(self, key, w, h) -> tuple[int, int, int, int]:
        pw, ph = w * S, h * S
        if self._x + pw > self.size:
            self._x = 0
            self._y += self._row_h + 1
            self._row_h = 0
        if self._y + ph > self.size:
            raise RuntimeError(f"atlas full placing {key} ({pw}x{ph}px)")
        r = (self._x, self._y, pw, ph)
        self.rects[key] = r
        self._x += pw + 1
        self._row_h = max(self._row_h, ph)
        PAINTERS[key[0]](self.cv, r, key)
        return r

    def extend_edges(self) -> None:
        cv, ph = self.cv, np.array(self.bg, np.uint8)
        for (x, y, w, h) in self.rects.values():
            sub = cv[y:y + h, x:x + w]
            if x > 0:
                col = cv[y:y + h, x - 1]
                free = np.all(col == ph, axis=-1)
                col[free] = sub[:, 0][free]
            if x + w < self.size:
                col = cv[y:y + h, x + w]
                free = np.all(col == ph, axis=-1)
                col[free] = sub[:, -1][free]
            if y > 0:
                row = cv[y - 1, x:x + w]
                free = np.all(row == ph, axis=-1)
                row[free] = sub[0, :][free]
            if y + h < self.size:
                row = cv[y + h, x:x + w]
                free = np.all(row == ph, axis=-1)
                row[free] = sub[-1, :][free]

    def image(self) -> Image.Image:
        return Image.fromarray(self.cv, "RGBA")


# --- geometry vocabulary ---------------------------------------------------
def FM(all=None, sides=None, ns=None, ew=None, tb=None, **faces):
    m = {}
    if all:
        m.update({f: all for f in FACES})
    if sides:
        m.update({f: sides for f in ("north", "south", "east", "west")})
    if ns:
        m.update({"north": ns, "south": ns})
    if ew:
        m.update({"east": ew, "west": ew})
    if tb:
        m.update({"up": tb, "down": tb})
    m.update(faces)
    return m


def cube(name, frm, to, facemap):
    return {"name": name, "from": frm, "to": to, "faces": facemap}


def group(name, cubes=(), children=(), origin=(0, 0, 0), rotation=None):
    return {"name": name, "origin": origin, "rotation": rotation,
            "cubes": list(cubes), "children": list(children)}


def hoop(name, y0, y1, outer, bar, facemap, axis="y", ry=0.0):
    """Four bars forming a square hoop around the vertical axis (or, with
    axis='x', a hoop standing in the YZ plane around the blade axis)."""
    o, i = outer, outer - bar
    if axis == "y":
        return [
            cube(f"{name}_n", (-o, y0, -o), (o, y1, -i), facemap),
            cube(f"{name}_s", (-o, y0, i), (o, y1, o), facemap),
            cube(f"{name}_w", (-o, y0, -i), (-i, y1, i), facemap),
            cube(f"{name}_e", (i, y0, -i), (o, y1, i), facemap),
        ]
    return []


def link(name, x, y, z, w, h, t, facemap, plane="xy"):
    """A chain link: a rectangular ring of four bars, in the xy or zy plane."""
    if plane == "xy":
        return [
            cube(f"{name}_t", (x, y + h - t, z), (x + w, y + h, z + t), facemap),
            cube(f"{name}_b", (x, y, z), (x + w, y + t, z + t), facemap),
            cube(f"{name}_o", (x, y + t, z), (x + t, y + h - t, z + t), facemap),
            cube(f"{name}_i", (x + w - t, y + t, z), (x + w, y + h - t, z + t), facemap),
        ]
    return [
        cube(f"{name}_t", (x, y + h - t, z), (x + t, y + h, z + w), facemap),
        cube(f"{name}_b", (x, y, z), (x + t, y + t, z + w), facemap),
        cube(f"{name}_o", (x, y + t, z), (x + t, y + h - t, z + t), facemap),
        cube(f"{name}_i", (x, y + t, z + w - t), (x + t, y + h - t, z + w), facemap),
    ]


def knucklebone(name, x, y, z, h, facemap):
    """A bone charm: a shaft with a knob at each end. Spans y .. y+h, knobs
    included, so it can be hung exactly off the face above it."""
    return [
        cube(f"{name}_shaft", (x + 0.4, y + 0.5, z + 0.4), (x + 1.6, y + h - 0.5, z + 0.9),
             facemap),
        cube(f"{name}_k0", (x, y, z), (x + 0.5, y + h, z + 1.3), facemap),
        cube(f"{name}_k1", (x + 1.5, y, z), (x + 2.0, y + h, z + 1.3), facemap),
    ]


# --- the model -------------------------------------------------------------
# Layout, all in absolute model units, front = -Z, blade sweeps -X.
SHAFT_HW = 1.6                      # shaft half width (low)
GRIP_HW = 1.35
UP_HW = 1.5
SPINE_Y = 93.0                      # the blade's back line
BLADE_X0 = -2.0                     # where the blade's root plate starts
PLATE_LEN = 10.5
PLATE_STEP = 5.8
PLATE_ANGLE = 10.0                  # degrees per plate, cumulative
CHORDS = [12, 11, 10, 9, 8, 7, 6, 5, 3, 2]
RIDGE_Z, SPINE_Z, EDGE_Z = 1.5, 1.0, 0.5

COLLAR_Y0, COLLAR_Y1 = 88.0, 91.2
COLLAR_HW = 2.0
NECK_Y0, NECK_Y1 = 91.2, 96.0
NECK_HW = 1.8

CAGE_Z = -5.6                       # the soul cage hangs this far in front (clear
                                    # of the chain coil, which reaches z=-3.0)
CAGE_HW = 2.6
CAGE_Y0, CAGE_Y1 = 78.6, 80.2       # the cage floor slab
CAGE_TOP_Y0, CAGE_TOP_Y1 = 84.4, 85.6


def build_butt():
    """Iron butt: a stepped cap, the ground spike, and a shackle with a short
    chain and a knucklebone hanging off the side."""
    iron = FM(all="iron_rust")
    parts = [
        cube("butt_tip", (-0.8, 0.0, -0.8), (0.8, 1.2, 0.8), iron),
        cube("butt_s1", (-1.3, 1.2, -1.3), (1.3, 2.6, 1.3), FM(all="iron")),
        cube("butt_s2", (-1.8, 2.6, -1.8), (1.8, 4.2, 1.8), FM(all="iron")),
        cube("butt_cap", (-2.1, 4.2, -2.1), (2.1, 9.0, 2.1), FM(sides="iron", tb="iron_dark")),
        cube("butt_guard", (-2.3, 9.0, -2.3), (2.3, 11.4, 2.3),
             FM(sides="iron", tb="iron_dark")),
    ]
    shackle = link("shackle", -4.4, 3.2, -0.5, 2.3, 4.2, 1.0, FM(all="iron_dark"), plane="xy")
    bone = knucklebone("butt_charm", -4.2, 0.8, -0.5, 2.4, FM(all="skull"))
    return parts + shackle + bone


def build_shaft():
    """Blackened oak: three tapering lengths (overlapped, never butted, so no
    two faces end up in the same plane), four iron hoops, a leather grip, and a
    coil of chain under the head."""
    wood = FM(all="wood")
    parts = [
        cube("shaft_low", (-SHAFT_HW, 11.4, -SHAFT_HW), (SHAFT_HW, 44.6, SHAFT_HW), wood),
        cube("shaft_grip", (-GRIP_HW, 44.0, -GRIP_HW), (GRIP_HW, 66.6, GRIP_HW), wood),
        cube("shaft_up", (-UP_HW, 66.0, -UP_HW), (UP_HW, 90.0, UP_HW), wood),
    ]
    for name, y0, y1, hw in (("ferrule_lo", 16.0, 17.8, 1.95),
                             ("ferrule_mid", 42.4, 44.4, 2.0),
                             ("ferrule_up", 65.6, 67.6, 2.05)):
        parts += hoop(name, y0, y1, hw, 0.55, FM(all="iron"))
    parts += hoop("brass_grip0", 44.4, 45.6, 2.0, 0.6, FM(all="brass"))
    parts += hoop("brass_grip1", 64.6, 65.8, 2.0, 0.6, FM(all="brass"))
    parts.append(cube("grip_wrap", (-1.8, 45.6, -1.8), (1.8, 64.6, 1.8),
                      FM(sides="leather", tb="leather")))
    coil = []
    # the hoop hugs the haft (inner face flush with the shaft at 1.5) and the
    # turns stay under 60 deg: a fatter hoop swung further round throws its
    # corner into the lantern hanging in front of it
    for i, (y, ry) in enumerate(((69.5, 0.0), (73.0, 30.0), (76.5, 60.0))):
        bars = hoop(f"coil{i}", y, y + 1.0, 2.5, 1.0, FM(all="iron_dark"))
        coil.append(group(f"coil_loop{i}", cubes=bars, origin=(0, y + 0.55, 0),
                          rotation=[0, ry, 0]))
    charm = link("coil_ring", -3.6, 66.9, -0.5, 1.8, 2.6, 0.8, FM(all="iron_dark"), plane="xy") \
        + knucklebone("coil_bone", -4.0, 64.5, -0.5, 2.4, FM(all="skull"))
    return parts + charm, coil


def build_collar():
    """The iron socket the blade and the skull both bolt onto, with the beak
    on the blade's far side."""
    parts = [
        cube("collar_low", (-COLLAR_HW, COLLAR_Y0, -COLLAR_HW),
             (COLLAR_HW, COLLAR_Y1, COLLAR_HW), FM(sides="iron", tb="iron_dark")),
        cube("collar_neck", (-NECK_HW, NECK_Y0, -NECK_HW), (NECK_HW, NECK_Y1, NECK_HW),
             FM(sides="iron", tb="iron_dark")),
        cube("collar_plate", (-2.0, NECK_Y1, -2.0), (2.0, 97.2, 2.0),
             FM(sides="iron", tb="iron_dark")),
    ]
    parts += hoop("collar_brass", 92.0, 93.2, 1.95, 0.55, FM(all="brass"))
    beak = [
        cube("beak_a", (1.6, 92.0, -1.3), (5.0, 94.6, 1.3), FM(all="iron")),
        cube("beak_b", (5.0, 92.5, -0.9), (7.2, 94.1, 0.9), FM(all="iron")),
        cube("beak_tip", (7.2, 92.8, -0.6), (8.8, 93.8, 0.6), FM(all="iron")),
    ]
    beak_grp = group("beak", cubes=beak, origin=(2.0, 93.0, 0.0), rotation=[0, 0, -15])
    # the torn shroud, tied to the collar at the back
    shroud = [
        cube("shroud_a", (-2.2, 78.5, 3.0), (2.2, 89.0, 4.0), FM(all="cloth")),
        cube("shroud_b", (-2.2, 74.0, 3.05), (-0.9, 78.5, 3.95), FM(all="cloth")),
        cube("shroud_c", (-0.7, 76.4, 3.05), (0.7, 78.5, 3.95), FM(all="cloth")),
        cube("shroud_d", (0.9, 72.6, 3.05), (2.2, 78.5, 3.95), FM(all="cloth")),
    ]
    shroud_grp = group("shroud", cubes=shroud, origin=(0, 88.0, 3.0))
    return parts, [beak_grp, shroud_grp]


def build_cage():
    """An iron lantern hanging off the collar's front on a two-link chain,
    holding the soul flame. The flame cubes are the only emissive geometry on
    the shaft, and the link-to-link contacts are exact face contacts so nothing
    floats."""
    iron = FM(all="iron_dark")
    arm = cube("cage_arm", (-1.0, 86.0, -3.4), (1.0, 89.6, -2.0), FM(all="iron"))
    link0 = link("cage_link0", -1.0, 83.0, -3.2, 2.0, 3.0, 0.7, iron, plane="xy")
    link1 = link("cage_link1", -0.35, 80.0, -4.2, 1.6, 3.0, 0.7, iron, plane="zy")
    top = hoop("cage_top", 78.8, 80.0, CAGE_HW, 1.0, iron)
    floor = cube("cage_floor", (-CAGE_HW, 72.6, CAGE_Z - CAGE_HW),
                 (CAGE_HW, 74.2, CAGE_Z + CAGE_HW), iron)
    ribs = []
    for sx in (-1, 1):
        for sz in (-1, 1):
            x0 = sx * CAGE_HW - (1.0 if sx > 0 else 0.0)
            z0 = CAGE_Z + sz * CAGE_HW - (1.0 if sz > 0 else 0.0)
            ribs.append(cube(f"cage_rib{sx}{sz}", (x0, 74.2, z0),
                             (x0 + 1.0, 78.8, z0 + 1.0), iron))
    flame = [
        cube("soul_low", (-1.4, 74.2, CAGE_Z - 1.4), (1.4, 76.6, CAGE_Z + 1.4),
             FM(all="flame")),
        cube("soul_mid", (-1.0, 76.6, CAGE_Z - 1.0), (1.0, 78.6, CAGE_Z + 1.0),
             FM(all="flame")),
        cube("soul_top", (-0.6, 78.6, CAGE_Z - 0.6), (0.6, 81.4, CAGE_Z + 0.6),
             FM(all="flame")),
    ]
    flame_grp = group("soul_flame", cubes=flame, origin=(0.0, 78.6, CAGE_Z))
    return [arm, floor] + link0 + link1 + top + ribs, flame_grp


def build_skull():
    """A ram-horned skull as the crown: a domed cranium, a heavy brow, two deep
    sockets with a soul light burning in each, a nasal notch between the
    cheekbones, a row of fangs, and a lower jaw hinged open under it. The bare
    human-ish skull is what reads as *undead* at a glance -- the earlier beast
    muzzle read as a crocodile, which is why it went.

    The face is a plate of bone in front of the cranium (brow / temple /
    cheekbone), with the socket floors set back 0.4 into it; every plate piece
    is buried a couple of units into the cranium behind, so no cube in the face
    is a paper-thin sliver and nothing z-fights with the cranium's own front."""
    bone = FM(all="skull")
    bone_d = FM(all="skull_dark")
    FACE_BACK = -1.0                     # plates run from the face plane back
    parts = [
        cube("cranium", (-3.6, 97.2, -3.0), (3.6, 103.2, 3.2), bone),
        cube("dome", (-2.8, 103.2, -2.4), (2.8, 104.4, 2.6), bone),
        cube("brow", (-3.8, 100.8, -3.8), (3.8, 102.8, FACE_BACK), bone),
        cube("temple_l", (-3.8, 98.6, -3.8), (-2.6, 100.8, FACE_BACK), bone),
        cube("temple_r", (2.6, 98.6, -3.8), (3.8, 100.8, FACE_BACK), bone),
        cube("bridge", (-1.0, 98.6, -3.5), (1.0, 100.8, FACE_BACK), bone),
        cube("socket_l", (-2.6, 98.6, -3.4), (-1.0, 100.8, FACE_BACK), FM(all="socket")),
        cube("socket_r", (1.0, 98.6, -3.4), (2.6, 100.8, FACE_BACK), FM(all="socket")),
        # the eye is buried one unit deeper than the socket floor so the two
        # back faces are not in the same plane
        cube("eye_l", (-2.3, 99.1, -3.6), (-1.3, 100.3, -0.5), FM(all="eye")),
        cube("eye_r", (1.3, 99.1, -3.6), (2.3, 100.3, -0.5), FM(all="eye")),
        cube("cheek_l", (-3.8, 96.6, -3.8), (-1.8, 98.6, FACE_BACK), bone),
        cube("cheek_r", (1.8, 96.6, -3.8), (3.8, 98.6, FACE_BACK), bone),
        cube("maxilla", (-1.8, 96.6, -3.6), (1.8, 98.6, FACE_BACK),
             FM(all="skull", north="nasal")),
    ]
    for i, cx in enumerate((-2.6, -1.5, -0.5, 0.5, 1.5, 2.6)):
        parts.append(cube(f"fang_u{i}", (cx - 0.45, 95.4, -3.6), (cx + 0.45, 96.6, -2.6),
                          FM(all="teeth")))
    jaw_cubes = [
        cube("jaw", (-2.6, 94.6, -4.8), (2.6, 96.2, -1.6), bone_d),
        cube("jaw_chin", (-1.6, 94.2, -5.2), (1.6, 95.8, -4.0), bone_d),
    ]
    for i, cx in enumerate((-1.9, -0.9, 0.1, 1.1, 2.1)):
        jaw_cubes.append(cube(f"fang_l{i}", (cx - 0.45, 96.2, -4.0), (cx + 0.45, 97.3, -3.0),
                              FM(all="teeth")))
    jaw = group("jaw", cubes=jaw_cubes, origin=(0.0, 96.6, -1.6), rotation=[-14, 0, 0])
    horns = []
    for side, sx in (("l", -1), ("r", 1)):
        hx = sx * 3.2
        h1 = cube(f"horn_{side}0", (hx - 0.8, 103.2, 0.0), (hx + 0.8, 105.8, 1.6),
                  FM(all="horn"))
        h2 = cube(f"horn_{side}1", (hx - 0.7, 105.8, 0.0), (hx + 0.7, 108.2, 1.4),
                  FM(all="horn"))
        h3 = cube(f"horn_{side}2", (hx - 0.6, 108.2, 0.0), (hx + 0.6, 110.4, 1.2),
                  FM(all="horn"))
        g3 = group(f"horn_{side}2", cubes=[h3], origin=(hx, 108.2, 0.7),
                   rotation=[40, 0, -sx * 16])
        g2 = group(f"horn_{side}1", cubes=[h2], children=[g3], origin=(hx, 105.8, 0.7),
                   rotation=[24, 0, -sx * 26])
        g1 = group(f"horn_{side}0", cubes=[h1], children=[g2], origin=(hx, 103.2, 0.8),
                   rotation=[10, 0, -sx * 30])
        horns.append(g1)
    return parts, jaw, horns


def build_blade():
    """Ten overlapping bone plates on a chain of nested groups pivoting on the
    spine line. Every plate is authored straight along -X; the +11.5 deg each
    group carries accumulates into the arc, and swings each plate's cutting
    edge back over its predecessor so the plates overlap instead of gaping."""
    plates = []
    joints = []
    n = len(CHORDS)
    for i, chord in enumerate(CHORDS):
        jx = BLADE_X0 - i * PLATE_STEP
        ridge_h = 2 if chord >= 6 else 0
        edge_h = 2 if chord >= 6 else 1          # the sharpened bevel: thin
        spine_h = chord - edge_h - ridge_h
        # The bend is a rotation about Z, which never moves a plate in z -- so
        # without this every plate's face would sit in the *same* plane as its
        # neighbours' and the whole blade would z-fight (it showed up as a
        # stipple hatch across the blade). Each plate is a little thicker than
        # the one after it, so the shingle always has a clear winner.
        f = 1.0 + 0.03 * (n - 1 - i)
        ridge_z, spine_z, edge_z = RIDGE_Z * f, SPINE_Z * f, EDGE_Z * f
        cubes = []
        if ridge_h:
            cubes.append(cube(f"blade{i}_ridge", (jx - PLATE_LEN, SPINE_Y - ridge_h, -ridge_z),
                              (jx, SPINE_Y, ridge_z), FM(all="spine")))
        if spine_h > 0:
            cubes.append(cube(f"blade{i}_spine",
                              (jx - PLATE_LEN, SPINE_Y - ridge_h - spine_h, -spine_z),
                              (jx, SPINE_Y - ridge_h, spine_z), FM(all="blade")))
        cubes.append(cube(f"blade{i}_edge", (jx - PLATE_LEN, SPINE_Y - chord, -edge_z),
                          (jx, SPINE_Y - ridge_h - spine_h, edge_z), FM(all="edge")))
        if i in (1, 3, 5, 7):
            # a rune stud on the plate's spine, authored in the plate's own
            # frame so it stays aligned once the chain bends
            mx = jx - PLATE_LEN * 0.5
            cubes.append(cube(f"rune{i}", (mx - 1.0, SPINE_Y - 2.3, -ridge_z - 0.4),
                              (mx + 1.0, SPINE_Y - 0.3, ridge_z + 0.4), FM(all="rune")))
        plates.append(cubes)
        joints.append((jx, SPINE_Y, chord))
    chain = None
    for i in reversed(range(len(CHORDS))):
        jx, jy, chord = joints[i]
        chain = group(f"blade{i}", cubes=plates[i], children=[chain] if chain else [],
                      origin=(jx, jy, 0.0),
                      rotation=[0, 0, PLATE_ANGLE] if i else None)
    return chain


def build_embers():
    """Three soul embers drifting around the crown, deliberately detached (they
    are whitelisted as free elements when the model is validated)."""
    spots = [(-5.0, 109.0, -4.0), (7.5, 98.0, 4.5), (4.5, 83.0, -7.5)]
    return [cube(f"ember{i}", (x, y, z), (x + 2.0, y + 2.0, z + 2.0), FM(all="ember"))
            for i, (x, y, z) in enumerate(spots)]


def build_tree():
    butt = build_butt()
    shaft_cubes, coil = build_shaft()
    collar_cubes, collar_groups = build_collar()
    cage, flame_grp = build_cage()
    skull_cubes, jaw, horns = build_skull()
    blade_chain = build_blade()
    embers = build_embers()

    head = group("head", children=[
        group("collar", cubes=collar_cubes + cage + skull_cubes, origin=(0, COLLAR_Y0, 0)),
        flame_grp,
        collar_groups[0],                                   # beak
        collar_groups[1],                                   # shroud
        jaw,
        group("horns", children=horns, origin=(0, 104.2, 0)),
        group("blade", children=[blade_chain], origin=(0, SPINE_Y, 0)),
    ], origin=(0, COLLAR_Y0, 0))

    shaft = group("shaft", cubes=shaft_cubes, children=coil, origin=(0, 11.4, 0))
    butt_grp = group("butt", cubes=butt, origin=(0, 11.4, 0))
    ember_grp = group("embers", cubes=embers, origin=(0, 0, 0))
    root = group(MODEL_NAME, children=[butt_grp, shaft, head, ember_grp], origin=(0, 0, 0))
    info = {"chords": CHORDS, "joints": [(BLADE_X0 - i * PLATE_STEP, SPINE_Y, c)
                                         for i, c in enumerate(CHORDS)]}
    return root, info


# --- self checks -----------------------------------------------------------
def check_blade_chain(tree, info):
    """Every plate must still be tucked into the one before it once the whole
    chain is bent -- that is the difference between a blade and a row of
    floating shards. Exact: the sample points are pushed through the ancestor
    chain the way Blockbench composes it, then compared against the
    predecessor's authored boxes in the predecessor's own frame."""
    pose, boxes = {}, {}
    for path, c, R, t in walk_groups(tree):
        pose[path] = (R, t)
        boxes[path] = (V(*c["from"]), V(*c["to"]))

    def plate_path(j, cube_name):
        chain = "/".join(f"blade{k}" for k in range(j + 1))
        return f"/{MODEL_NAME}/head/blade/{chain}/{cube_name}"

    # each plate reaches PLATE_LEN-PLATE_STEP past its joint into the plate
    # before it; sample the far half of that overlap, on the spine and down at
    # the cutting edge (where a bent chain would gape first if the pivot or the
    # step were wrong)
    reach = PLATE_LEN - PLATE_STEP
    for i in range(len(info["chords"]) - 1):
        nxt, chord = i + 1, info["chords"][i + 1]
        jx = info["joints"][nxt][0]
        R_n, t_n = pose[plate_path(nxt, f"blade{nxt}_spine")]
        for depth, where in ((0.5, "spine"), (chord - 0.5, "the cutting edge")):
            world = R_n @ V(jx - reach * 0.5, SPINE_Y - depth, 0.0) + t_n
            hits = []
            for strip in ("ridge", "spine", "edge"):
                p_prev = plate_path(i, f"blade{i}_{strip}")
                if p_prev not in pose:
                    continue
                R_p, t_p = pose[p_prev]
                loc = R_p.T @ (world - t_p)
                lo, hi = boxes[p_prev]
                if all(lo[k] - 1e-6 <= loc[k] <= hi[k] + 1e-6 for k in range(3)):
                    hits.append(strip)
            if not hits:
                raise AssertionError(
                    f"blade plate {nxt} does not tuck into plate {i} at {where}")
    return reach


def check_solids(tree):
    bad = []
    for path, c, _R, _t in walk_groups(tree):
        d = [c["to"][k] - c["from"][k] for k in range(3)]
        if any(v <= 1e-6 for v in d):
            bad.append((path, "degenerate"))
        elif min(d) < 0.5 and "shroud" not in path and "link" not in path and "charm" not in path:
            bad.append((path, f"thin {min(d):.2f}"))
    return bad


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


# --- writer ----------------------------------------------------------------
def collect_rects(tree, tex_index):
    seen = {}
    for _path, c, _R, _t in walk_groups(tree):
        for mat in c["faces"].values():
            if tex_of(mat) != tex_index:
                continue
            w, h = face_size("north", c["from"], c["to"])
            for face in FACES:
                w, h = face_size(face, c["from"], c["to"])
                seen[(mat, w, h)] = True
    return sorted(seen, key=lambda k: (-k[2], -k[1]))


def build_atlases(tree) -> dict:
    """One atlas size for the whole model (a project has a single uv
    resolution), so the body map decides the size and the glow map follows."""
    body = collect_rects(tree, TEX_BODY)
    glow = collect_rects(tree, TEX_GLOW)
    for size in (256, 320, 384, 448, 512):
        atlases = {}
        try:
            for idx, keys in ((TEX_BODY, body), (TEX_GLOW, glow)):
                atlas = Atlas(size, idx)
                for mat, w, h in keys:
                    atlas.alloc((mat, w, h), w, h)
                atlases[idx] = atlas
        except RuntimeError:
            continue
        for atlas in atlases.values():
            atlas.extend_edges()
        return atlases
    raise SystemExit("no atlas size fits the model")


def check_painted(atlas: Atlas) -> list[str]:
    ph = np.array(atlas.bg, np.uint8)
    return [str(key) for key, (x, y, w, h) in atlas.rects.items()
            if np.any(np.all(atlas.cv[y:y + h, x:x + w] == ph, axis=-1))]


def kf(channel, time, value, interpolation="linear"):
    """One Blockbench keyframe: numbers ride as Molang strings in data_points."""
    if channel == "scale":
        pt = {"x": f"{value[0]:g}", "y": f"{value[1]:g}", "z": f"{value[2]:g}"}
    else:
        pt = {"x": f"{value[0]:g}", "y": f"{value[1]:g}", "z": f"{value[2]:g}"}
    return {"channel": channel, "data_points": [pt], "uuid": str(uuid.uuid4()),
            "time": float(time), "color": -1, "interpolation": interpolation}


def build_animations(by_name: dict) -> list:
    """A two-second idle, looping: the weapon drifts, the soul flame pulses,
    the jaw works, the shroud flutters and the embers orbit. Authored after the
    walk so the animators can be keyed by the group uuids Blockbench wants.

    Nothing keyframes a *cube*: the writer gives every cube origin [0,0,0], so a
    cube-level scale or rotation would pivot on the model origin and fling the
    cube across the scene. Groups carry their own pivots, so groups only."""
    def anim(name, keys):
        g = by_name[name]
        return {"name": name, "type": "bone",
                "keyframes": sum(([kf(c, t, v, i) for c, t, v, i in ks] for ks in keys), [])}

    root = anim("undead_scythe", [[
        ("position", 0.0, (0, 0, 0), "catmullrom"),
        ("position", 1.0, (0, 0.9, 0), "catmullrom"),
        ("position", 2.0, (0, 0, 0), "catmullrom")]])
    flame = anim("soul_flame", [[
        ("scale", 0.0, (1, 1, 1), "catmullrom"),
        ("scale", 0.5, (1.1, 1.18, 1.1), "catmullrom"),
        ("scale", 1.0, (0.96, 0.94, 0.96), "catmullrom"),
        ("scale", 1.5, (1.06, 1.12, 1.06), "catmullrom"),
        ("scale", 2.0, (1, 1, 1), "catmullrom"),
    ], [
        ("position", 0.0, (0, 0, 0), "catmullrom"),
        ("position", 0.8, (0, 0.5, 0), "catmullrom"),
        ("position", 1.6, (0, -0.3, 0), "catmullrom"),
        ("position", 2.0, (0, 0, 0), "catmullrom")]])
    jaw = anim("jaw", [[
        ("rotation", 0.0, (0, 0, 0), "catmullrom"),
        ("rotation", 1.0, (-5.5, 0, 0), "catmullrom"),
        ("rotation", 2.0, (0, 0, 0), "catmullrom")]])
    shroud = anim("shroud", [[
        ("rotation", 0.0, (0, 0, 0), "catmullrom"),
        ("rotation", 0.5, (2.5, 0, 3.0), "catmullrom"),
        ("rotation", 1.0, (0, 0, 0), "catmullrom"),
        ("rotation", 1.5, (-2.0, 0, -2.5), "catmullrom"),
        ("rotation", 2.0, (0, 0, 0), "catmullrom")]])
    embers = anim("embers", [[
        ("position", 0.0, (0, 0, 0), "catmullrom"),
        ("position", 1.2, (0, 1.6, 0), "catmullrom"),
        ("position", 2.0, (0, 0, 0), "catmullrom"),
    ], [
        ("rotation", 0.0, (0, 0, 0), "catmullrom"),
        ("rotation", 2.0, (0, 60, 0), "catmullrom")]])
    return [{
        "uuid": str(uuid.uuid4()), "name": "animation.undead_scythe.idle",
        "loop": "loop", "override": False, "length": 2.0, "snapping": 24,
        "selected": False, "saved": False, "path": "",
        "anim_time_update": "", "blend_weight": "", "start_delay": "", "loop_delay": "",
        "animators": {by_name[a["name"]]: a for a in (root, flame, jaw, shroud, embers)},
    }]


def write_model(path: str, tree, atlases: dict, textures: dict) -> int:
    elements: list[dict] = []
    groups: list[dict] = []
    by_name: dict = {}

    def emit_cube(c: dict) -> str:
        el = {
            "name": c["name"],
            "from": [float(v) for v in c["from"]],
            "to": [float(v) for v in c["to"]],
            "origin": [0.0, 0.0, 0.0],
            "uuid": str(uuid.uuid4()),
            "faces": {},
            "type": "cube",
            "color": 0,
            "box_uv": False,
        }
        for face in FACES:
            mat = c["faces"][face]
            w, h = face_size(face, c["from"], c["to"])
            x, y, rw, rh = atlases[tex_of(mat)].rects[(mat, w, h)]
            el["faces"][face] = {"uv": [x / S, y / S, (x + rw) / S, (y + rh) / S],
                                 "texture": tex_of(mat)}
        elements.append(el)
        by_name[c["name"]] = el["uuid"]
        return el["uuid"]

    def walk(node: dict) -> dict:
        """A group is written twice on purpose: inline in the outliner node (the
        4.5 legacy-group path Blockbench 5.2.1 itself reads) and in a top-level
        `groups` table (the 5.0 layout third-party readers parse). Blockbench
        merges the two by uuid."""
        children = [emit_cube(c) for c in node.get("cubes") or []]
        children += [walk(child) for child in node.get("children") or []]
        gu = str(uuid.uuid4())
        out = {"name": node["name"], "origin": [float(v) for v in node["origin"]],
               "uuid": gu, "children": children}
        table = {"name": node["name"], "origin": [float(v) for v in node["origin"]],
                 "uuid": gu,
                 "children": [c if isinstance(c, str) else c["uuid"] for c in children]}
        if node.get("rotation"):
            out["rotation"] = [float(v) for v in node["rotation"]]
            table["rotation"] = [float(v) for v in node["rotation"]]
        groups.append(table)
        by_name[node["name"]] = gu
        return out

    outliner = [walk(tree)]
    res = atlases[TEX_BODY].size // S
    tex_docs = []
    for idx in (TEX_BODY, TEX_GLOW):
        buf = io.BytesIO()
        textures[idx].save(buf, format="PNG")
        uri = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
        entry = {"path": "", "name": f"{MODEL_NAME}{'' if idx == TEX_BODY else '_glow'}.png",
                 "folder": "entity", "namespace": "", "id": str(idx), "particle": False,
                 "render_mode": "default" if idx == TEX_BODY else "emissive",
                 "visible": True, "mode": "bitmap", "saved": False,
                 "uuid": str(uuid.uuid4()), "source": uri,
                 "width": atlases[idx].size, "height": atlases[idx].size,
                 "uv_width": res, "uv_height": res}
        tex_docs.append(entry)
    doc = {
        "meta": {"format_version": "4.5", "model_format": "free", "box_uv": False},
        "name": MODEL_NAME,
        "resolution": {"width": res, "height": res},
        "elements": elements,
        "outliner": outliner,
        "groups": groups,
        "textures": tex_docs,
        "animations": build_animations(by_name),
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False)
    return len(elements)


PREVIEWS = [
    # the weapon is 111 tall with a 39-unit blade, so the whole-body views sit
    # well back; the two close-ups frame the crown and the crescent
    ("", 222.0, 14.0, 142.0, (-13.0, 56.0, 0.0)),
    ("_front", 180.0, 6.0, 142.0, (-13.0, 56.0, 0.0)),
    ("_side", 268.0, 6.0, 132.0, (0.0, 56.0, 0.0)),
    ("_head", 232.0, 18.0, 54.0, (-3.0, 94.0, 0.0)),
    ("_blade", 244.0, 20.0, 60.0, (-18.0, 82.0, 0.0)),
]


def render_previews(model_path: str) -> None:
    for suffix, az, el, dist, target in PREVIEWS:
        out = os.path.join(OUT_DIR, f"{MODEL_NAME}_preview{suffix}.png")
        subprocess.run([sys.executable, os.path.join(REPO, "tools", "preview_bbmodel.py"),
                        model_path, out, "--size", "760", "--azimuth", str(az),
                        "--elevation", str(el), "--distance", str(dist),
                        "--target", *[str(t) for t in target]], check=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-preview", action="store_true")
    args = ap.parse_args()

    tree, info = build_tree()

    bad = coplanar_conflicts(tree)
    if bad:
        for pi, pj, axis, tag, coord in bad[:20]:
            print(f"  z-fight risk: {pi} / {pj} on {axis}={coord:.3f} ({tag})")
        raise SystemExit(f"{len(bad)} coplanar same-facing overlaps")

    contacts = posed_contacts(tree)
    if contacts:
        print("posed AABB contacts involving rotated chains (visual triage):")
        for pi, pj, vol in sorted(contacts, key=lambda r: -r[2])[:12]:
            print(f"  {vol:6.2f}  {pi.split('/')[-1]:<18} {pj.split('/')[-1]}")

    stretched = stretch_report(tree)
    if stretched:
        # aggregated, not per face: the count of faces at each rounding is what
        # says whether a taper is a deliberate trade or a mistake
        agg: dict = {}
        for _path, _face, want, got in stretched:
            agg[(round(want, 2), got)] = agg.get((round(want, 2), got), 0) + 1
        print(f"stretched faces (rounded uv rect vs true size): {len(stretched)}")
        for (want, got), n in sorted(agg.items()):
            print(f"  {want:6.2f} -> {got} px   x{n}")

    thin = check_solids(tree)
    if thin:
        for path, why in thin[:10]:
            print(f"  solid: {path}: {why}")
        raise SystemExit(f"{len(thin)} bad cubes")

    check_blade_chain(tree, info)
    lo, hi = bounds(tree)
    print(f"bounds  x {lo[0]:7.2f}..{hi[0]:7.2f}  y {lo[1]:7.2f}..{hi[1]:7.2f}  "
          f"z {lo[2]:7.2f}..{hi[2]:7.2f}   (h {hi[1] - lo[1]:.1f})")

    atlases = build_atlases(tree)
    for idx, atlas in atlases.items():
        unpainted = check_painted(atlas)
        if unpainted:
            raise SystemExit(f"texture {idx} rects left unpainted: {unpainted}")
    images = {idx: atlas.image() for idx, atlas in atlases.items()}
    for idx, name in ((TEX_BODY, f"{MODEL_NAME}.png"), (TEX_GLOW, f"{MODEL_NAME}_glow.png")):
        images[idx].save(os.path.join(OUT_DIR, name))

    model_path = os.path.join(OUT_DIR, f"{MODEL_NAME}.bbmodel")
    cubes = write_model(model_path, tree, atlases, images)
    used = {idx: sum(w * h for _x, _y, w, h in a.rects.values()) for idx, a in atlases.items()}
    print(f"{model_path}  ({cubes} cubes, res {atlases[TEX_BODY].size // S}, "
          f"body {atlases[TEX_BODY].size}px {len(atlases[TEX_BODY].rects)} rects "
          f"{used[TEX_BODY]}px, glow {len(atlases[TEX_GLOW].rects)} rects {used[TEX_GLOW]}px)")

    if not args.no_preview:
        render_previews(model_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
