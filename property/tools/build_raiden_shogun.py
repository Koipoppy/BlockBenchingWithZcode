"""Build 雷电将军 (Raiden Shogun, Genshin Impact) as a Blockbench project.

    python tools/build_raiden_shogun.py

Writes ../raiden_shogun/raiden_shogun.bbmodel (texture embedded as a data URI) and
../raiden_shogun/raiden_shogun.png (the same texture, standalone).

A vanilla-Minecraft-style humanoid (Steve/Alex skeleton: 8^3 head, 8x12x4
torso, slim 3x12x4 arms, 4x12x4 legs -- exactly 2 blocks tall) dressed as the
Electro Archon: pale lavender hair with a hime-cut fringe and chest-length
sidelocks, her signature floor-length braid down the back with a gold tie and
tassel, a lavender kimono with a dark crossed collar and gold chest ornament,
a dark obi with gold trim and a back bow, a flared dark hakama skirt with a
front slit, wide light sleeves with dark gold-trimmed hems, dark violet
bodysuit legs with gold anklets, and a magenta hair flower on her left side.

No reference art could be fetched (network blocked on this machine), so the
design is from the character's well-known look: pale purple hair, purple eyes,
deep purple + lavender + gold outfit.

Format conventions are the ones measured out of Blockbench's source (see
build_bawanghua_pot.py): per-face uv rects upright and unmirrored seen from
outside, v from the top; model_format 'free'; front of the character faces -Z
(north), so with front = -Z her RIGHT side is +X (east) and her LEFT is -X --
the flower goes on -X. Left/right group names are anatomical.

Touching cubes follow the "coplanar opposite-facing faces are fine, same-facing
coplanar overlap is a z-fight" rule; every face rect is an integer pixel size so
nothing is stretched.
"""
from __future__ import annotations

import base64
import io
import json
import os
import random
import uuid

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(os.path.dirname(HERE), "raiden_shogun")
os.makedirs(OUT_DIR, exist_ok=True)
MODEL_NAME = "raiden_shogun"

FACES = ("north", "east", "south", "west", "up", "down")

# --- palette ---------------------------------------------------------------
# Pale silver-lavender hair, light skin, a lavender kimono ramp, a deep purple
# ramp for obi/hakama/bodysuit, gold trim, and the feature colors.
HAIR = [
    (226, 220, 242),  # 0 highlight
    (198, 186, 228),  # 1 base
    (164, 148, 204),  # 2 shade
    (128, 112, 172),  # 3 dark
]
SKIN = [
    (250, 226, 206),  # 0 base
    (236, 204, 182),  # 1 shade
    (216, 182, 160),  # 2 deep shade
]
ROBE = [
    (198, 180, 230),  # 0 light lavender kimono
    (168, 150, 206),  # 1 base
    (138, 120, 182),  # 2 shade
    (112, 96, 156),   # 3 dark
]
DARK = [
    (106, 86, 148),   # 0 light deep purple
    (84, 66, 124),    # 1 base (obi, hakama)
    (64, 50, 100),    # 2 shade (bodysuit)
    (46, 36, 78),     # 3 dark (bodysuit shadow, slit)
]
GOLD = [
    (246, 210, 124),  # 0 light
    (224, 180, 90),   # 1 base
    (188, 144, 62),   # 2 shade
    (152, 112, 46),   # 3 dark
]
EYE_HI = (212, 172, 250)
EYE = (152, 92, 220)
EYE_D = (86, 48, 148)
INNER = (240, 235, 250)          # inner collar
SLEEVE_C = (230, 222, 246)       # the whitest lavender, wide sleeves
FLOWER = [(232, 146, 216), (202, 108, 188), (166, 76, 152)]
MOUTH = (216, 136, 144)
PLACEHOLDER = (255, 0, 255, 255)


def at(cv, r):
    return cv[r[1]:r[1] + r[3], r[0]:r[0] + r[2]]


class Atlas:
    """Shelf packer for the per-face uv rects, plus an edge-extend pass.

    The head rects are placed manually at the vanilla head-box positions (a
    gapless 32x16 region), and the packer starts beside them with row height
    preset to 16 so its first wrap lands below the head region.
    """

    def __init__(self, size: int = 64):
        self.size = size
        self.cv = np.zeros((size, size, 4), np.uint8)
        self.cv[:] = PLACEHOLDER
        self.rects: dict[str, tuple[int, int, int, int]] = {}
        self._x = 0
        self._y = 0
        self._row_h = 0

    def place(self, name: str, x: int, y: int, w: int, h: int) -> None:
        self.rects[name] = (x, y, w, h)

    def add(self, name: str, w: int, h: int) -> tuple[int, int, int, int]:
        if self._x + w > self.size:
            self._x = 0
            self._y += self._row_h + 1
            self._row_h = 0
        if self._y + h > self.size:
            raise RuntimeError(f"atlas full placing {name} ({w}x{h})")
        rect = (self._x, self._y, w, h)
        self.rects[name] = rect
        self._x += w + 1
        self._row_h = max(self._row_h, h)
        return rect

    def extend_edges(self) -> None:
        cv = self.cv
        ph = np.array(PLACEHOLDER, np.uint8)
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


# --- texture painters ------------------------------------------------------
HEAD_RECTS = [
    ("head_up", 8, 0, 8, 8), ("head_down", 16, 0, 8, 8),
    ("head_east", 0, 8, 8, 8), ("head_front", 8, 8, 8, 8),
    ("head_west", 16, 8, 8, 8), ("head_south", 24, 8, 8, 8),
]
PACKED_RECTS = [
    ("torso_front", 8, 12), ("torso_back", 8, 12), ("torso_side", 4, 12),
    ("torso_top", 8, 4), ("torso_bottom", 8, 4),
    ("obi_front", 9, 4), ("obi_back", 9, 4), ("obi_side", 6, 4), ("obi_top", 9, 6),
    ("knot_gold", 3, 3), ("knot_side", 1, 3), ("knot_flat", 3, 1),
    ("skirt_front", 10, 6), ("skirt_back", 10, 6), ("skirt_side", 5, 6),
    ("skirt_top", 10, 5),
    ("sleeve", 5, 7), ("sleeve_top", 5, 5), ("sleeve_bottom", 5, 5),
    ("arm_front", 3, 12), ("arm_side", 4, 12), ("arm_top", 3, 4), ("arm_bottom", 3, 4),
    ("leg_side", 4, 12), ("leg_top", 4, 4), ("leg_sole", 4, 4),
    ("sl_front", 2, 15), ("sl_side", 1, 15), ("sl_end", 2, 1),
    ("bangs_front", 8, 3), ("bangs_side", 1, 3), ("bangs_up", 8, 1),
    ("bulge_back", 7, 7), ("bulge_side", 2, 7), ("bulge_top", 7, 2),
    ("slab_back", 7, 6), ("slab_side", 2, 6), ("slab_top", 7, 2),
    ("braid_seg", 3, 3),
    ("tie_band", 2, 1), ("tie_flat", 2, 2), ("tassel", 2, 2),
    ("flower", 1, 1), ("gold", 1, 1),
]


def flat(cv, r, color):
    at(cv, r)[:] = (*color, 255)


def cloth(cv, r, rng, ramp, base=1, noise=0.12, edge=True):
    """Quiet fabric: base fill, sparse shade speckle, hem/side shading."""
    a = at(cv, r)
    a[:] = (*ramp[base], 255)
    sh = ramp[min(base + 1, len(ramp) - 1)]
    for py in range(r[3]):
        for px in range(r[2]):
            if rng.random() < noise:
                a[py, px] = (*sh, 255)
    if edge:
        a[r[3] - 1, :] = (*sh, 255)
        a[:, 0] = (*sh, 255)
        a[:, r[2] - 1] = (*sh, 255)


def hairfill(cv, r, rng):
    """Lavender hair: base fill with vertical light/dark strand runs."""
    a = at(cv, r)
    a[:] = (*HAIR[1], 255)
    w, h = r[2], r[3]
    for cx in range(w):
        if rng.random() < 0.5:
            run = rng.randrange(2, h + 1)
            y0 = rng.randrange(0, h - run + 1)
            c = HAIR[2] if rng.random() < 0.72 else HAIR[0]
            a[y0:y0 + run, cx] = (*c, 255)


def paint_face(cv, r):
    """8x8 face: gradient purple eyes, tiny mouth. Rows 0..2 hide under the
    3-D bangs plate, so features start at row 3."""
    f = at(cv, r)
    f[:] = (*SKIN[0], 255)
    f[:, 0] = (*SKIN[1], 255)
    f[:, 7] = (*SKIN[1], 255)
    f[7, :] = (*SKIN[1], 255)
    for cx in (1, 2, 5, 6):
        f[3, cx] = (*EYE_D, 255)          # lash line
    f[4, 1] = (*EYE_HI, 255); f[4, 2] = (*EYE, 255)
    f[4, 5] = (*EYE_HI, 255); f[4, 6] = (*EYE, 255)
    f[5, 1] = (*EYE, 255); f[5, 2] = (*EYE_D, 255)
    f[5, 5] = (*EYE, 255); f[5, 6] = (*EYE_D, 255)
    f[6, 3] = (*MOUTH, 255); f[6, 4] = (*MOUTH, 255)


def paint_texture(atlas: Atlas) -> None:
    cv, r = atlas.cv, atlas.rects
    rng = random.Random(20260924)

    # --- head: hair everywhere but the front face ---------------------------
    for name in ("head_east", "head_west", "head_south", "head_up"):
        hairfill(cv, r[name], rng)
    flat(cv, r["head_down"], SKIN[1])
    paint_face(cv, r["head_front"])

    # --- bangs plate: straight hime fringe with strand tips -----------------
    bf = at(cv, r["bangs_front"])
    bf[:] = (*HAIR[1], 255)
    bf[1, 2] = (*HAIR[0], 255); bf[1, 5] = (*HAIR[0], 255)
    for cx in (1, 3, 4, 6):
        bf[2, cx] = (*HAIR[2], 255)
    flat(cv, r["bangs_side"], HAIR[2])
    flat(cv, r["bangs_up"], HAIR[1])

    # --- back-of-head bulge: hair + the gold crescent ornament --------------
    hairfill(cv, r["bulge_back"], rng)
    bg = at(cv, r["bulge_back"])
    bg[1, 2:5] = (*GOLD[1], 255)
    bg[0, 3] = (*GOLD[0], 255)
    hairfill(cv, r["bulge_side"], rng)
    flat(cv, r["bulge_top"], HAIR[1])

    # --- loose hair draping down the back -----------------------------------
    hairfill(cv, r["slab_back"], rng)
    hairfill(cv, r["slab_side"], rng)
    flat(cv, r["slab_top"], HAIR[1])

    # --- sidelocks: pale with a shaded inner column and dark tips -----------
    sl = at(cv, r["sl_front"])
    sl[:] = (*HAIR[1], 255)
    sl[:, 1] = (*HAIR[2], 255)
    sl[5, 0] = (*HAIR[0], 255)
    sl[13:15, :] = (*HAIR[3], 255)
    ss = at(cv, r["sl_side"])
    ss[:] = (*HAIR[1], 255)
    ss[12:15, 0] = (*HAIR[2], 255)
    flat(cv, r["sl_end"], HAIR[2])

    # --- torso: crossed collar, gold chest ornament, blossom on the back ----
    cloth(cv, r["torso_front"], rng, ROBE, base=1)
    tf = at(cv, r["torso_front"])
    tf[0, 2:6] = (*DARK[1], 255)                     # collar band
    tf[1, 2] = (*DARK[1], 255)
    tf[1, 3:5] = (*INNER, 255)                       # inner collar sliver
    tf[1, 5] = (*DARK[1], 255)
    tf[2, 3:5] = (*DARK[1], 255)                     # the V closes
    tf[3, 3] = (*GOLD[0], 255); tf[3, 4] = (*GOLD[1], 255)
    tf[4, 3] = (*GOLD[2], 255); tf[4, 4] = (*GOLD[1], 255)   # chest knot

    cloth(cv, r["torso_back"], rng, ROBE, base=1)
    tb = at(cv, r["torso_back"])
    tb[0, :] = (*ROBE[0], 255)

    cloth(cv, r["torso_side"], rng, ROBE, base=1)
    ts = at(cv, r["torso_side"])
    ts[0, :] = (*ROBE[0], 255)
    ts[1:4, 0:3] = (*FLOWER[1], 255)                 # plum blossom on the side
    ts[1, 1] = (*FLOWER[0], 255); ts[3, 1] = (*FLOWER[0], 255)
    ts[2, 0] = (*FLOWER[0], 255); ts[2, 2] = (*FLOWER[0], 255)
    ts[2, 1] = (*GOLD[1], 255)
    cloth(cv, r["torso_top"], rng, ROBE, base=1, edge=False)
    flat(cv, r["torso_bottom"], DARK[2])

    # --- obi: dark sash, gold rope rows, clasp on the front left ------------
    for name, clasp in (("obi_front", True), ("obi_back", False)):
        cloth(cv, r[name], rng, DARK, base=1, edge=False)
        o = at(cv, r[name])
        o[0, :] = (*GOLD[1], 255)
        o[3, :] = (*GOLD[2], 255)
        o[:, 0] = (*DARK[2], 255)
        o[:, r[name][2] - 1] = (*DARK[2], 255)
        if clasp:
            o[1:3, 1:3] = (*GOLD[1], 255)
            o[1, 1] = (*GOLD[0], 255)
            o[1:3, 3:6] = (*DARK[0], 255)
            o[1, 4] = (*GOLD[0], 255)
    cloth(cv, r["obi_side"], rng, DARK, base=1, edge=False)
    os_ = at(cv, r["obi_side"])
    os_[0, :] = (*GOLD[1], 255)
    os_[3, :] = (*GOLD[2], 255)
    flat(cv, r["obi_top"], DARK[2])          # shared by the bottom face

    # --- obi bow knot at the back -------------------------------------------
    kg = at(cv, r["knot_gold"])
    kg[:] = (*GOLD[1], 255)
    kg[0, 0] = (*GOLD[2], 255); kg[0, 2] = (*GOLD[2], 255)
    kg[2, 0] = (*GOLD[2], 255); kg[2, 2] = (*GOLD[2], 255)
    kg[1, 1] = (*GOLD[0], 255)
    flat(cv, r["knot_side"], DARK[1])
    flat(cv, r["knot_flat"], GOLD[2])

    # --- hakama skirt: dark flare, front slit, gold hem ----------------------
    cloth(cv, r["skirt_front"], rng, DARK, base=1, edge=False)
    sf = at(cv, r["skirt_front"])
    sf[0:5, 4:6] = (*DARK[3], 255)                   # the front slit
    sf[4, :] = (*DARK[2], 255)
    sf[5, :] = (*GOLD[2], 255)                       # hem
    sf[:, 0] = (*DARK[2], 255); sf[:, 9] = (*DARK[2], 255)
    cloth(cv, r["skirt_back"], rng, DARK, base=1, edge=False)
    sb = at(cv, r["skirt_back"])
    sb[5, :] = (*GOLD[2], 255)
    cloth(cv, r["skirt_side"], rng, DARK, base=2, edge=False)
    at(cv, r["skirt_side"])[5, :] = (*GOLD[2], 255)
    flat(cv, r["skirt_top"], DARK[2])        # shared by the bottom face

    # --- wide sleeves: whitest lavender, gold line, dark cuff ----------------
    sv = at(cv, r["sleeve"])
    sv[:] = (*SLEEVE_C, 255)
    for py in range(4):
        for px in range(5):
            if rng.random() < 0.12:
                sv[py, px] = (*ROBE[1], 255)
    sv[:, 0] = (*ROBE[1], 255); sv[:, 4] = (*ROBE[1], 255)
    sv[4, :] = (*GOLD[1], 255)
    sv[5, :] = (*DARK[1], 255)
    sv[6, :] = (*DARK[2], 255)
    flat(cv, r["sleeve_top"], SLEEVE_C)
    flat(cv, r["sleeve_bottom"], DARK[2])

    # --- arms: kimono shoulder, dark under-sleeve, bare hands ----------------
    for name in ("arm_front", "arm_side"):
        a = at(cv, r[name])
        a[0, :] = (*ROBE[0], 255)
        a[1:3, :] = (*ROBE[1], 255)
        a[3:10, :] = (*DARK[1], 255)
        for py in range(3, 10):
            for px in range(r[name][2]):
                if rng.random() < 0.12:
                    a[py, px] = (*DARK[2], 255)
        a[10:12, :] = (*SKIN[0], 255)
        a[11, :] = (*SKIN[1], 255)
    flat(cv, r["arm_top"], ROBE[1])
    flat(cv, r["arm_bottom"], SKIN[1])

    # --- legs: dark bodysuit, gold anklet, dark sole -------------------------
    cloth(cv, r["leg_side"], rng, DARK, base=2, noise=0.15, edge=False)
    ls = at(cv, r["leg_side"])
    ls[9, :] = (*GOLD[2], 255)
    ls[11, :] = (*DARK[3], 255)
    flat(cv, r["leg_top"], DARK[2])
    flat(cv, r["leg_sole"], DARK[3])

    # --- braid: one soft light/dark diagonal hint per tile; the staggered
    # segments provide the plait silhouette -----------------------------------
    bs = at(cv, r["braid_seg"])
    bs[:] = (*HAIR[1], 255)
    bs[0, 0] = (*HAIR[0], 255)
    bs[1, 1] = (*HAIR[2], 255)
    flat(cv, r["tie_band"], GOLD[1])
    flat(cv, r["tie_flat"], GOLD[0])
    ta = at(cv, r["tassel"])
    ta[0, 0] = (*DARK[1], 255); ta[0, 1] = (*DARK[1], 255)
    ta[1, 0] = (*DARK[2], 255); ta[1, 1] = (*DARK[3], 255)

    # --- ornaments ------------------------------------------------------------
    flat(cv, r["flower"], FLOWER[0])
    flat(cv, r["gold"], GOLD[1])


# --- geometry --------------------------------------------------------------
# Units of 1/16 block, ground y=0, centred on x=z=0, facing -Z (north).
# With front = -Z her right side is +X, her left is -X.
def all_faces(rect):
    return {f: rect for f in FACES}


def sides(rect):
    return {f: rect for f in ("north", "south", "east", "west")}


def faces(base, **overrides):
    merged = dict(base)
    merged.update(overrides)
    return merged


def cube(name, frm, to, origin, facemap):
    return {"name": name, "from": frm, "to": to, "origin": origin, "faces": facemap}


def build_tree():
    body = {"name": "body", "origin": (0, 12, 0), "cubes": [
        # Kimono torso, obi sash with back bow, flared hakama skirt.
        cube("torso", (-4, 12, -2), (4, 24, 2), (0, 12, 0),
             faces(sides("torso_side"), up="torso_top", down="torso_bottom",
                   north="torso_front", south="torso_back")),
        cube("obi", (-4.5, 15, -3), (4.5, 19, 3), (0, 12, 0),
             faces(sides("obi_side"), up="obi_top", down="obi_top",
                   north="obi_front", south="obi_back")),
        cube("obi_bow", (-1.5, 14, 3), (1.5, 17, 4), (0, 12, 0),
             faces(sides("knot_side"), up="knot_flat", down="knot_flat",
                   north="knot_gold", south="knot_gold")),
        cube("skirt", (-5, 8, -2.5), (5, 14, 2.5), (0, 12, 0),
             faces(sides("skirt_side"), up="skirt_top", down="skirt_top",
                   north="skirt_front", south="skirt_back")),
    ], "children": [
        {"name": "head", "origin": (0, 24, 0), "cubes": [
            cube("head", (-4, 24, -4), (4, 32, 4), (0, 24, 0),
                 faces({}, north="head_front", south="head_south",
                       east="head_east", west="head_west",
                       up="head_up", down="head_down")),
            # Hime fringe as a plate proud of the face, sidelocks to the chest.
            cube("bangs", (-4, 29, -4.6), (4, 32, -3.6), (0, 24, 0),
                 faces(sides("bangs_side"), up="bangs_up", down="bangs_up",
                       north="bangs_front", south="bangs_front")),
            cube("sidelock_left", (-4.5, 15, -4.5), (-2.5, 30, -3.5), (0, 24, 0),
                 faces(sides("sl_side"), up="sl_end", down="sl_end",
                       north="sl_front", south="sl_front")),
            cube("sidelock_right", (2.5, 15, -4.5), (4.5, 30, -3.5), (0, 24, 0),
                 faces(sides("sl_side"), up="sl_end", down="sl_end",
                       north="sl_front", south="sl_front")),
            # Hair mass at the back of the head + loose hair down the back.
            cube("hair_back", (-3.5, 24, 4), (3.5, 31, 6), (0, 24, 0),
                 faces(sides("bulge_side"), up="bulge_top", down="bulge_top",
                       north="bulge_back", south="bulge_back")),
            cube("back_hair", (-3.5, 19, 2), (3.5, 25, 4), (0, 24, 0),
                 faces(sides("slab_side"), up="slab_top", down="slab_top",
                       north="slab_back", south="slab_back")),
            # Ornaments: flower + gold pin on her left, small pin on her right.
            cube("hair_flower", (-5.0, 30, -2.2), (-4.0, 31, -1.2), (0, 24, 0),
                 faces(all_faces("flower"))),
            cube("hairpin_left", (-5.0, 29, -2.2), (-4.0, 30, -1.2), (0, 24, 0),
                 faces(all_faces("gold"))),
            cube("hairpin_right", (4.0, 29.5, -2.2), (5.0, 30.5, -1.2), (0, 24, 0),
                 faces(all_faces("gold"))),
        ], "children": [
            # The signature floor-length braid, hung from the back of the head
            # and hugging the back (segments alternate a small x sway).
            {"name": "braid", "origin": (0, 24, 5.5), "cubes": [
                cube("braid_1", (-1.5, 21, 4), (1.5, 24, 7), (0, 24, 5.5),
                     faces(all_faces("braid_seg"))),
                cube("braid_2", (-1.25, 18, 4), (1.75, 21, 7), (0, 24, 5.5),
                     faces(all_faces("braid_seg"))),
                cube("braid_3", (-1.75, 15, 4), (1.25, 18, 7), (0, 24, 5.5),
                     faces(all_faces("braid_seg"))),
                cube("braid_4", (-1.25, 12, 4), (1.75, 15, 7), (0, 24, 5.5),
                     faces(all_faces("braid_seg"))),
                cube("braid_5", (-1.75, 9, 4), (1.25, 12, 7), (0, 24, 5.5),
                     faces(all_faces("braid_seg"))),
                cube("braid_6", (-1.25, 6, 4), (1.75, 9, 7), (0, 24, 5.5),
                     faces(all_faces("braid_seg"))),
                cube("braid_7", (-1.5, 3, 4), (1.5, 6, 7), (0, 24, 5.5),
                     faces(all_faces("braid_seg"))),
                cube("braid_tie", (-1, 2, 4.5), (1, 3, 6.5), (0, 24, 5.5),
                     faces(sides("tie_band"), up="tie_flat", down="tie_flat")),
                cube("braid_tassel", (-1, 0, 4.5), (1, 2, 6.5), (0, 24, 5.5),
                     faces(all_faces("tassel"))),
            ]},
        ]},
        {"name": "right_arm", "origin": (5, 22, 0), "cubes": [
            cube("right_arm_cube", (4, 12, -2), (7, 24, 2), (5, 22, 0),
                 faces(sides("arm_side"), up="arm_top", down="arm_bottom",
                       north="arm_front", south="arm_front")),
            cube("sleeve_right", (3, 14, -2.5), (8, 21, 2.5), (5, 22, 0),
                 faces(all_faces("sleeve"), up="sleeve_top", down="sleeve_bottom")),
        ]},
        {"name": "left_arm", "origin": (-5, 22, 0), "cubes": [
            cube("left_arm_cube", (-7, 12, -2), (-4, 24, 2), (-5, 22, 0),
                 faces(sides("arm_side"), up="arm_top", down="arm_bottom",
                       north="arm_front", south="arm_front")),
            cube("sleeve_left", (-8, 14, -2.5), (-3, 21, 2.5), (-5, 22, 0),
                 faces(all_faces("sleeve"), up="sleeve_top", down="sleeve_bottom")),
        ]},
    ]}

    leg_facemap = faces(sides("leg_side"), up="leg_top", down="leg_sole",
                        north="leg_side", south="leg_side")
    legs = []
    for name, cx in (("right_leg", 1.9), ("left_leg", -1.9)):
        x0 = -4 if cx < 0 else 0
        legs.append({"name": name, "origin": (cx, 12, 0), "cubes": [
            cube(f"{name}_cube", (x0, 0, -2), (x0 + 4, 12, 2), (cx, 12, 0),
                 leg_facemap),
        ]})

    return {"name": MODEL_NAME, "origin": (0, 0, 0), "children": [body, *legs]}


# --- bbmodel writing -------------------------------------------------------
def write_model(path: str, tree, rects, texture: Image.Image,
                resolution=(64, 64)) -> int:
    elements: list[dict] = []

    def emit_cube(c: dict) -> str:
        el = {
            "name": c["name"],
            "from": [float(v) for v in c["from"]],
            "to": [float(v) for v in c["to"]],
            "origin": [float(v) for v in c["origin"]],
            "uuid": str(uuid.uuid4()),
            "faces": {},
            "type": "cube",
            "color": 0,
        }
        for face in FACES:
            x, y, w, h = rects[c["faces"][face]]
            el["faces"][face] = {"uv": [x, y, x + w, y + h], "texture": 0}
        elements.append(el)
        return el["uuid"]

    def walk(node: dict) -> dict:
        children = [emit_cube(c) for c in node.get("cubes") or []]
        children += [walk(child) for child in node.get("children") or []]
        return {"name": node["name"],
                "origin": [float(v) for v in node["origin"]],
                "uuid": str(uuid.uuid4()),
                "children": children}

    outliner = [walk(tree)]

    buf = io.BytesIO()
    texture.save(buf, format="PNG")
    uri = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    doc = {
        "meta": {"format_version": "4.5", "model_format": "free", "box_uv": False},
        "name": MODEL_NAME,
        "resolution": {"width": resolution[0], "height": resolution[1]},
        "elements": elements,
        "outliner": outliner,
        "textures": [{
            "path": "", "name": f"{MODEL_NAME}.png", "folder": "entity", "namespace": "",
            "id": "0", "particle": False, "render_mode": "default", "visible": True,
            "mode": "bitmap", "saved": False, "uuid": str(uuid.uuid4()), "source": uri,
        }],
        "animations": [],
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False)
    return len(elements)


def unsampled_rects(atlas: Atlas, tree) -> list[str]:
    """Every rect a face samples must be painted, not left as placeholder magenta."""
    used = set()

    def walk(node):
        for c in node.get("cubes") or []:
            used.update(c["faces"].values())
        for child in node.get("children") or []:
            walk(child)

    walk(tree)
    bad = []
    for name in used:
        x, y, w, h = atlas.rects[name]
        patch = atlas.cv[y:y + h, x:x + w]
        if np.any(np.all(patch == np.array(PLACEHOLDER, np.uint8), axis=-1)):
            bad.append(name)
    return bad


def main() -> int:
    atlas = Atlas(64)
    for name, x, y, w, h in HEAD_RECTS:
        atlas.place(name, x, y, w, h)
    atlas._x, atlas._y, atlas._row_h = 32, 0, 16   # packer starts beside the head
    for name, w, h in sorted(PACKED_RECTS, key=lambda item: -item[2]):
        atlas.add(name, w, h)
    paint_texture(atlas)
    atlas.extend_edges()

    tree = build_tree()
    unpainted = unsampled_rects(atlas, tree)
    if unpainted:
        raise SystemExit(f"faces sample unpainted rects: {unpainted}")

    img = atlas.image()
    png_path = os.path.join(OUT_DIR, f"{MODEL_NAME}.png")
    img.save(png_path)

    model_path = os.path.join(OUT_DIR, f"{MODEL_NAME}.bbmodel")
    cubes = write_model(model_path, tree, atlas.rects, img)
    print(f"{model_path}  ({cubes} cubes)")
    print(f"{png_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
