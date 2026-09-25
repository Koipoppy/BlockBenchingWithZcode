"""Build the 瓶中帆船 (ship in a bottle) as a Blockbench project.

    python tools/build_ship_in_bottle.py

Writes ../ship_in_bottle/ship_in_bottle.bbmodel (texture embedded as a data URI) and
../ship_in_bottle/ship_in_bottle.png (the same texture, standalone).

A decorative ship-in-a-bottle in the vanilla idiom: a translucent glass bottle
(the way vanilla glass reads -- light blue tint, opaque white diagonal streaks,
a firmer frame) standing on a sand-and-sea floor, with a square-rigged ship
inside: dark-oak hull with a gilded gunwale, lit stern windows, two masts with
yarded sails, a jib running up from the bowsprit, a pennant, a rudder and four
shrouds. Everything except the glass is opaque; the glass tint is what puts the
"inside a bottle" haze over the ship.

Layout (1 unit = 1/16 block, ground y=0, centred on x=z=0, bow to -Z/north):
the bottle footprint is 12x16 with 1-thick hollow walls (cavity 10x14, y 1..15),
two chamfered shoulder rings, a 4x4 neck (y 19..27), a 6x6 lip and a cork --
31 tall in total. The sea is a sand slab plus a water slab whose top face sits
at y=3, exactly where the keel rests. The rig is sized to the cavities: mainmast
tops out flush at y=19 under the neck, the foremast at y=17, and the jib's lower
corner just clears the bow wall -- see the clearance notes next to each cube.

Format conventions are the ones measured out of Blockbench's source (see
build_bawanghua_pot.py): per-face uv rects upright and unmirrored seen from
outside, v from the top; model_format 'free' (the shrouds and yards rotate by
non-22.5 amounts); bow faces -Z (north) so the default camera meets the bow.
"""
from __future__ import annotations

import base64
import io
import json
import math
import os
import random
import uuid

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(os.path.dirname(HERE), "ship_in_bottle")
os.makedirs(OUT_DIR, exist_ok=True)
MODEL_NAME = "ship_in_bottle"

FACES = ("north", "east", "south", "west", "up", "down")

# --- palette ---------------------------------------------------------------
# Glass reads like vanilla's glass block: a light cyan tint at ~22% alpha so the
# ship shows through hazed, a firmer frame, and near-opaque white streaks.
GLASS = (200, 233, 242, 45)
GLASS_FRAME = (228, 247, 250, 100)
GLASS_STREAK = (255, 255, 255, 150)
GLASS_CORNER = (150, 205, 224, 95)
GLASS_SPECK = (135, 195, 218, 110)
GLASS_HIDDEN = (150, 200, 218, 140)   # faces no camera can reach
CORK = [(183, 138, 94), (160, 116, 74), (131, 92, 57)]
SAND = [(219, 207, 163), (203, 189, 143), (178, 162, 118), (160, 143, 100)]
SHELL = (240, 234, 214)
WATER = [(52, 105, 215), (78, 135, 235), (128, 175, 245), (38, 82, 185), (110, 160, 238)]
WOOD_DARK = (66, 43, 21)
SEAM = (52, 33, 16)
HULL = [(99, 64, 34), (85, 54, 28), (108, 71, 38)]
DECK = [(199, 164, 110), (183, 147, 92), (148, 114, 68)]
MAST = [(113, 76, 42), (96, 62, 33)]
GOLD = [(240, 202, 92), (214, 172, 58)]
SAIL = [(240, 238, 230), (222, 219, 209), (208, 205, 195)]
HEM = (176, 52, 50)
HEM_DARK = (148, 40, 40)
PENNANT = [(224, 92, 70), (198, 56, 46)]
SHROUD = (82, 62, 42)
SHROUD_LIT = (120, 95, 64)
WINDOW = (255, 214, 120)
LANTERN = (255, 224, 130)
PLACEHOLDER = (255, 0, 255, 255)


def shade(ramp, i):
    return ramp[max(0, min(len(ramp) - 1, i))]


def at(cv, r):
    return cv[r[1]:r[1] + r[3], r[0]:r[0] + r[2]]


def paint(cv, r, color):
    at(cv, r)[:] = (*color[:3], color[3] if len(color) > 3 else 255)


def speckle(cv, r, color, count, rng, alpha=255):
    x0, y0, w, h = r
    for _ in range(count):
        cv[y0 + rng.randrange(h), x0 + rng.randrange(w)] = (*color[:3], alpha)


class Atlas:
    """Shelf packer for the per-face uv rects, plus an edge-extend pass.

    extend_edges only bleeds while the neighbour pixel is still the magenta
    placeholder, so a face one texel off shows up as magenta in the preview
    instead of quietly sampling a neighbour's art.
    """

    def __init__(self, size: int = 64):
        self.size = size
        self.cv = np.zeros((size, size, 4), np.uint8)
        self.cv[:] = PLACEHOLDER
        self.rects: dict[str, tuple[int, int, int, int]] = {}
        self._x = 0
        self._y = 0
        self._row_h = 0

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
# Rects are sized to the faces that sample them so no art is ever stretched
# (thin rigging/sail-edge faces round their sub-pixel width up to 1).
RECT_SIZES = [
    # glass bottle
    ("glass_ns", 10, 14), ("glass_ew", 14, 14), ("glass_bottom", 12, 16),
    ("glass_edge_h", 12, 1), ("glass_edge_v", 16, 1),
    ("glass_ledge_a", 10, 1), ("glass_ledge_v", 1, 14),
    ("glass_sh1_ns", 8, 2), ("glass_sh1_ew", 10, 2), ("glass_pillar", 1, 2),
    ("glass_ledge_c", 8, 1), ("glass_ledge_d", 1, 10),
    ("glass_sh2_ns", 6, 2), ("glass_ledge_e", 6, 1), ("glass_ledge_f", 1, 8),
    ("glass_neck_ns", 2, 8), ("glass_neck_ew", 1, 8),
    ("glass_neck_top", 2, 1), ("glass_neck_top_v", 1, 2),
    ("glass_lip_top", 6, 6), ("glass_lip_side", 6, 1),
    ("cork_side", 4, 3), ("cork_top", 4, 4),
    # sea
    ("sand_top", 10, 14), ("sand_side_ns", 10, 1), ("sand_side_ew", 14, 1),
    ("water_top", 10, 14), ("water_side_ns", 10, 1), ("water_side_ew", 14, 1),
    # hull
    ("keel_side_ns", 4, 1), ("keel_side_ew", 10, 1),
    ("hull_plank", 8, 5), ("hull_end", 1, 5), ("hull_end_b", 1, 4),
    ("hull_trim", 1, 2), ("wood_bit", 1, 1),
    ("gunwale_cap", 1, 8), ("deck_edge", 4, 1), ("deck_bit", 2, 1),
    ("bow_face", 4, 4), ("bow_tip", 2, 2), ("stern_face", 4, 5),
    ("bulwark_n", 4, 1), ("quarterdeck_top", 4, 2), ("quarterdeck_s", 4, 1),
    ("deck_planks", 4, 9),
    # sterncastle
    ("cabin_front", 4, 3), ("cabin_back", 4, 3), ("cabin_side", 3, 3),
    ("roof_top", 5, 4), ("roof_edge", 5, 1), ("roof_edge_v", 4, 1),
    ("lantern", 1, 1),
    # rig
    ("mast_side", 1, 9), ("mast_side_main", 1, 14), ("mast_cap", 1, 1),
    ("yard_side", 7, 1), ("spar", 2, 1), ("spar_v", 1, 2),
    ("sail_cloth", 6, 4), ("sail_cloth_main", 6, 6),
    ("sail_edge", 1, 4), ("sail_edge_v", 1, 6), ("sail_hem", 6, 1),
    ("sail_jib", 2, 8),
    ("shroud_line", 1, 4), ("shroud_line_main", 1, 6),
    ("pennant_side", 2, 1), ("pennant_tip", 1, 1),
    ("rudder", 1, 3),
]


def paint_glass(cv, r):
    """Vanilla-glass look: tinted body, firmer frame, white diagonal glints."""
    w, h = r[2], r[3]
    paint(cv, r, GLASS)
    if w < 3 or h < 2:                       # tiny strips: tint plus firmer ends
        return
    sub = at(cv, r)
    sub[0, :] = (*GLASS_FRAME[:3], GLASS_FRAME[3])
    sub[:, 0] = (*GLASS_FRAME[:3], GLASS_FRAME[3])
    if h > 1:
        sub[-1, :] = (*GLASS_FRAME[:3], GLASS_FRAME[3])
    if w > 1:
        sub[:, -1] = (*GLASS_FRAME[:3], GLASS_FRAME[3])
    for corner in ((0, 0), (0, w - 1), (h - 1, 0), (h - 1, w - 1)):
        sub[corner] = (*GLASS_CORNER[:3], GLASS_CORNER[3])
    run = max(3, min(w, h) - 2)              # glint runs most of the diagonal
    for i in range(run):
        y, x = 1 + i, 1 + i
        if y < h - 1 and x < w - 1:
            sub[y, x] = (*GLASS_STREAK[:3], GLASS_STREAK[3])


def paint_water_top(cv, r, rng):
    w, h = r[2], r[3]
    paint(cv, r, WATER[0])
    sub = at(cv, r)
    sub[0, :] = (*WATER[4], 255)             # foam ring where sea meets glass
    sub[-1, :] = (*WATER[4], 255)
    sub[:, 0] = (*WATER[4], 255)
    sub[:, -1] = (*WATER[4], 255)
    for row in (2, 5, 8, 11):                # staggered wave crests
        if row >= h - 1:
            break
        x = 1 + (row * 3) % max(1, w - 4)
        for dx in range(3):
            if 1 <= x + dx < w - 1:
                sub[row, x + dx] = (*WATER[1], 255)
                if dx == 1:
                    sub[row + 1, x + dx] = (*WATER[2], 255)
    for _ in range(4):
        speckle(cv, r, WATER[2], 1, rng)


def paint_texture(atlas: Atlas) -> None:
    cv, r = atlas.cv, atlas.rects
    rng = random.Random(20260925)

    # --- glass ---------------------------------------------------------------
    for name in [n for n, _, _ in RECT_SIZES if n.startswith(("glass", "cork"))]:
        if name == "glass_bottom":
            paint(cv, r[name], GLASS_HIDDEN)   # never visible, keep it quiet
        elif name.startswith("glass"):
            paint_glass(cv, r[name])
    cs = at(cv, r["cork_side"])
    for y in range(r["cork_side"][3]):
        cs[y, :] = (*CORK[y % 2], 255)
    speckle(cv, r["cork_side"], CORK[2], 4, rng)
    ct = at(cv, r["cork_top"])
    ct[:] = (*CORK[1], 255)
    ct[0, :] = ct[-1, :] = (*CORK[2], 255)
    ct[:, 0] = ct[:, -1] = (*CORK[2], 255)
    speckle(cv, r["cork_top"], CORK[0], 3, rng)

    # --- sea -----------------------------------------------------------------
    paint(cv, r["sand_top"], SAND[0])
    speckle(cv, r["sand_top"], SAND[1], 16, rng)
    speckle(cv, r["sand_top"], SAND[2], 10, rng)
    speckle(cv, r["sand_top"], SAND[3], 5, rng)
    speckle(cv, r["sand_top"], SHELL, 2, rng)
    for name in ("sand_side_ns", "sand_side_ew"):
        paint(cv, r[name], SAND[2])
        speckle(cv, r[name], SAND[3], 3, rng)
    paint_water_top(cv, r["water_top"], rng)
    for name in ("water_side_ns", "water_side_ew"):
        paint(cv, r[name], WATER[3])

    # --- hull: dark oak strakes with seams, gilded gunwale -------------------
    for name in ("keel_side_ns", "keel_side_ew"):
        paint(cv, r[name], WOOD_DARK)
        speckle(cv, r[name], SEAM, 2, rng)
    hp = at(cv, r["hull_plank"])
    for y in range(5):
        hp[y, :] = (*(SEAM if y % 2 else HULL[1] if y == 2 else HULL[0]), 255)
    hp[0, :] = (*HULL[2], 255)
    speckle(cv, r["hull_plank"], SEAM, 3, rng)
    for name in ("hull_end", "hull_end_b", "hull_trim"):
        paint(cv, r[name], WOOD_DARK)
    paint(cv, r["gunwale_cap"], GOLD[0])
    gcap = at(cv, r["gunwale_cap"])
    gcap[0, 0] = gcap[0, -1] = (*GOLD[1], 255)
    paint(cv, r["bow_face"], HULL[0])
    bf = at(cv, r["bow_face"])
    bf[:, 1] = bf[:, 3] = (*HULL[1], 255)
    bf[3, :] = (*SEAM, 255)
    paint(cv, r["bow_tip"], WOOD_DARK)
    at(cv, r["bow_tip"])[0, 1] = (*HULL[1], 255)
    sf = at(cv, r["stern_face"])
    sf[:] = (*HULL[1], 255)
    sf[0, :] = (*GOLD[0], 255)               # transom trim
    sf[1, 0] = sf[1, 3] = (*HULL[0], 255)
    sf[2, 1] = sf[2, 2] = (*WINDOW, 255)     # lit stern windows
    sf[4, :] = (*SEAM, 255)                  # waterline
    paint(cv, r["bulwark_n"], HULL[2])
    paint(cv, r["quarterdeck_top"], DECK[0])
    at(cv, r["quarterdeck_top"])[1, :] = (*DECK[1], 255)
    paint(cv, r["quarterdeck_s"], DECK[1])
    dp = at(cv, r["deck_planks"])
    dp[:] = (*DECK[0], 255)
    dp[:, 1] = dp[:, 3] = (*DECK[1], 255)    # plank seams run fore-aft
    speckle(cv, r["deck_planks"], DECK[2], 6, rng)
    paint(cv, r["deck_edge"], DECK[1])
    paint(cv, r["deck_bit"], DECK[1])

    # --- sterncastle: plank walls, gold cornice, lit windows, lantern --------
    cf = at(cv, r["cabin_front"])
    cf[:] = (*HULL[1], 255)
    cf[0, :] = (*GOLD[0], 255)
    cf[1, 0] = cf[1, 1] = (*WINDOW, 255)     # lit window band
    cf[1:3, 2:4] = (*WOOD_DARK, 255)         # door
    cf[2, 3] = (*GOLD[0], 255)               # door handle
    cb = at(cv, r["cabin_back"])
    cb[:] = (*HULL[1], 255)
    cb[0, :] = (*GOLD[0], 255)
    cb[1, 1] = cb[1, 2] = (*WINDOW, 255)
    csd = at(cv, r["cabin_side"])
    csd[:] = (*HULL[1], 255)
    csd[0, :] = (*GOLD[0], 255)
    csd[1, 1] = (*WINDOW, 255)               # porthole
    rt = at(cv, r["roof_top"])
    rt[:] = (*DECK[0], 255)
    rt[1, :] = rt[3, :] = (*DECK[1], 255)
    speckle(cv, r["roof_top"], DECK[2], 3, rng)
    paint(cv, r["roof_edge"], DECK[1])
    paint(cv, r["roof_edge_v"], DECK[2])
    paint(cv, r["lantern"], LANTERN)

    # --- rig -----------------------------------------------------------------
    for name in ("mast_side", "mast_side_main"):
        paint(cv, r[name], MAST[0])
        speckle(cv, r[name], MAST[1], 3, rng)
    paint(cv, r["mast_cap"], GOLD[0])
    paint(cv, r["yard_side"], MAST[0])
    at(cv, r["yard_side"])[0, 0] = at(cv, r["yard_side"])[0, -1] = (*MAST[1], 255)
    paint(cv, r["spar"], MAST[0])
    at(cv, r["spar"])[0, -1] = (*MAST[1], 255)
    paint(cv, r["spar_v"], MAST[0])
    paint(cv, r["wood_bit"], MAST[1])

    sc = at(cv, r["sail_cloth"])
    sc[:] = (*SAIL[0], 255)
    speckle(cv, r["sail_cloth"], SAIL[1], 8, rng)
    speckle(cv, r["sail_cloth"], SAIL[2], 3, rng)
    sc[3, :] = (*HEM, 255)                   # red foot on the fore sail
    scm = at(cv, r["sail_cloth_main"])
    scm[:] = (*SAIL[0], 255)
    speckle(cv, r["sail_cloth_main"], SAIL[1], 12, rng)
    speckle(cv, r["sail_cloth_main"], SAIL[2], 5, rng)
    scm[:, 2] = (*SAIL[1], 255)              # stitched panel columns
    scm[:, 4] = (*SAIL[1], 255)
    scm[2, :] = (*SAIL[2], 255)              # one seam across the middle
    scm[5, :] = (*HEM, 255)
    for name in ("sail_edge", "sail_edge_v"):
        paint(cv, r[name], SAIL[1])
    paint(cv, r["sail_hem"], HEM)
    at(cv, r["sail_hem"])[0, 0] = at(cv, r["sail_hem"])[0, -1] = (*HEM_DARK, 255)
    sj = at(cv, r["sail_jib"])
    sj[:] = (*SAIL[0], 255)
    speckle(cv, r["sail_jib"], SAIL[1], 7, rng)
    sj[:, 0] = (*SAIL[1], 255)
    sj[7, :] = (*HEM, 255)
    for name in ("shroud_line", "shroud_line_main"):
        paint(cv, r[name], SHROUD)
        at(cv, r[name])[1, 0] = (*SHROUD_LIT, 255)
    paint(cv, r["pennant_side"], PENNANT[1])
    at(cv, r["pennant_side"])[0, 0] = (*PENNANT[0], 255)
    paint(cv, r["pennant_tip"], PENNANT[1])
    rd = at(cv, r["rudder"])
    rd[:] = (*WOOD_DARK, 255)
    rd[1, 0] = (*HULL[1], 255)


# --- geometry --------------------------------------------------------------
# Units of 1/16 block, ground y=0, centred on x=z=0, bow to -Z. The bottle is a
# hollow shell: contents live in the cavity x -5..5, z -7..7, y 1..15, with the
# two shoulder rings (y 15..19) carved out around the masts.
def all_faces(rect):
    return {f: rect for f in FACES}


def sides(rect):
    return {f: rect for f in ("north", "south", "east", "west")}


def faces(base, **overrides):
    merged = dict(base)
    merged.update(overrides)
    return merged


def cube(name, frm, to, origin, facemap, rotation=None):
    return {"name": name, "from": frm, "to": to, "origin": origin,
            "faces": facemap, "rotation": rotation}


def build_tree():
    sea = {"name": "sea", "origin": (0, 0, 0), "cubes": [
        cube("sand", (-5, 1, -7), (5, 2, 7), (0, 0, 0),
             faces(sides("sand_side_ns"), east="sand_side_ew", west="sand_side_ew",
                   up="sand_top", down="sand_top")),
        cube("water", (-5, 2, -7), (5, 3, 7), (0, 0, 0),
             faces(sides("water_side_ns"), east="water_side_ew", west="water_side_ew",
                   up="water_top", down="water_side_ns")),
    ]}

    hull = {"name": "hull", "origin": (0, 4, 0), "cubes": [
        # keel rests on the water top (y=3); both faces are opposite normals, no fight
        cube("keel", (-2, 3, -5), (2, 4, 5), (0, 3, 0),
             faces(sides("keel_side_ns"), east="keel_side_ew", west="keel_side_ew",
                   up="keel_side_ew", down="keel_side_ns")),
        cube("bow", (-2, 4, -6), (2, 8, -5), (0, 4, 0),
             faces(sides("hull_end_b"), north="bow_face", up="deck_edge", down="deck_edge")),
        cube("bow_tip", (-1, 4, -6.5), (1, 6, -5.5), (0, 4, 0),
             faces(sides("hull_trim"), north="bow_tip", up="deck_bit", down="deck_bit")),
        cube("side_w", (-3, 4, -4), (-2, 9, 4), (0, 4, 0),
             faces(sides("hull_end"), east="hull_plank", west="hull_plank",
                   up="gunwale_cap", down="hull_end")),
        cube("side_e", (2, 4, -4), (3, 9, 4), (0, 4, 0),
             faces(sides("hull_end"), east="hull_plank", west="hull_plank",
                   up="gunwale_cap", down="hull_end")),
        cube("stern", (-2, 4, 4), (2, 9, 5), (0, 4, 0),
             faces(sides("hull_end"), north="stern_face", south="stern_face",
                   up="deck_edge", down="deck_edge")),
        cube("deck", (-2, 7, -5), (2, 8, 4), (0, 7, 0),
             faces(all_faces("deck_planks"))),
        cube("bulwark_bow", (-2, 8, -6), (2, 9, -5), (0, 8, 0),
             faces(sides("wood_bit"), north="bulwark_n", up="deck_edge", down="deck_edge")),
        cube("quarterdeck", (-2, 8, 2), (2, 9, 4), (0, 8, 0),
             faces(all_faces("quarterdeck_s"), up="quarterdeck_top", down="quarterdeck_top")),
    ]}

    sterncastle = {"name": "sterncastle", "origin": (0, 9, 0), "cubes": [
        cube("cabin", (-2, 9, 2), (2, 12, 5), (0, 9, 0),
             faces(sides("cabin_side"), north="cabin_front", south="cabin_back",
                   up="roof_top", down="roof_top")),
        # roof overhangs the cabin by half a unit all around
        cube("cabin_roof", (-2.5, 12, 1.5), (2.5, 13, 5.5), (0, 12, 0),
             faces(sides("roof_edge_v"), north="roof_edge", south="roof_edge",
                   up="roof_top", down="roof_top")),
        cube("lantern", (1.25, 13, 4.25), (2, 13.75, 5), (0, 13, 0),
             faces(all_faces("lantern"))),
    ]}

    rig = {"name": "rig", "origin": (0, 8, 0), "cubes": [
        # foremast tops out flush at y=17 under shoulder ring 1; the mainmast
        # rides the body/shoulder/neck cavities (all aligned on z 0..1) and its
        # top with the pennant slides INTO the neck, the classic bottle-ship pose.
        cube("foremast", (-0.5, 8, -2), (0.5, 17, -1), (0, 8, 0),
             faces(all_faces("mast_side"), up="mast_cap")),
        cube("mainmast", (-0.5, 8, 0), (0.5, 22, 1), (0, 8, 0),
             faces(all_faces("mast_side_main"), up="mast_cap")),
        cube("fore_yard", (-3.5, 13, -2), (3.5, 14, -1), (0, 13, 0),
             faces(sides("yard_side"), up="yard_side", down="yard_side",
                   east="wood_bit", west="wood_bit")),
        cube("main_yard", (-3.5, 15, 0), (3.5, 16, 1), (0, 15, 0),
             faces(sides("yard_side"), up="yard_side", down="yard_side",
                   east="wood_bit", west="wood_bit")),
        # sails hang with their feet at the gunwale line (y=9) so nothing floats;
        # red hem only on the underside -- an up-facing hem reads as a floating
        # red stripe from the elevated cameras
        cube("fore_sail", (-3, 9, -2.5), (3, 13, -2), (0, 9, 0),
             faces(sides("sail_cloth"), east="sail_edge", west="sail_edge",
                   up="sail_edge", down="sail_hem")),
        cube("main_sail", (-3, 9, -0.5), (3, 15, 0), (0, 9, 0),
             faces(sides("sail_cloth_main"), east="sail_edge_v", west="sail_edge_v",
                   up="sail_edge", down="sail_hem")),
        # jib: a thin plane from the bowsprit tip up to the foremast; rotated so
        # its wide faces turn outboard. Corners stay inside the cavity (z > -7).
        cube("jib", (-0.125, 11.85, -7.885), (0.125, 13.85, -0.315), (0, 12.85, -4.1),
             faces(sides("sail_edge"), east="sail_jib", west="sail_jib",
                   up="sail_edge", down="sail_edge"),
             rotation=(-56.3, 0, 0)),
        # bowsprit: emerges through the bow top, tip at (0, 9.5, -6.3)
        cube("bowsprit", (-0.5, 7.5, -7), (0.5, 8.5, -5), (0, 8, -5),
             faces(sides("wood_bit"), east="spar", west="spar",
                   up="spar_v", down="spar_v"),
             rotation=(50, 0, 0)),
        cube("pennant", (-0.25, 21.5, -0.5), (0.25, 22.5, 1), (0, 22, -0.5),
             faces(sides("pennant_tip"), east="pennant_side", west="pennant_side",
                   up="pennant_side", down="pennant_side"),
             rotation=(-8, 0, 0)),
        cube("rudder", (-0.5, 3, 5), (0.5, 6, 5.75), (0, 3, 0),
             faces(sides("rudder"), up="wood_bit", down="keel_side_ns")),
        # shrouds: thin lines from each mast down to the gilded gunwale; they
        # stop just under their yards so nothing intersects
        cube("shroud_fore_e", (0.55, 8.6, -1.875), (0.8, 12.5, -1.625),
             (0.55, 12.5, -1.75), faces(all_faces("shroud_line"), up="wood_bit", down="wood_bit"),
             rotation=(0, 0, 30)),
        cube("shroud_fore_w", (-0.8, 8.6, -1.875), (-0.55, 12.5, -1.625),
             (-0.55, 12.5, -1.75), faces(all_faces("shroud_line"), up="wood_bit", down="wood_bit"),
             rotation=(0, 0, -30)),
        cube("shroud_main_e", (0.55, 8.6, 0.55), (0.8, 14.5, 0.8),
             (0.55, 14.5, 0.675), faces(all_faces("shroud_line_main"), up="wood_bit", down="wood_bit"),
             rotation=(0, 0, 20)),
        cube("shroud_main_w", (-0.8, 8.6, 0.55), (-0.55, 14.5, 0.8),
             (-0.55, 14.5, 0.675), faces(all_faces("shroud_line_main"), up="wood_bit", down="wood_bit"),
             rotation=(0, 0, -20)),
    ]}

    ship = {"name": "ship", "origin": (0, 0, 0), "children": [hull, sterncastle, rig]}

    # Glass shell, painted last so translucent quads sort over the contents.
    bottle = {"name": "bottle", "origin": (0, 0, 0), "cubes": [
        cube("bottle_bottom", (-6, 0, -8), (6, 1, 8), (0, 0, 0),
             faces(sides("glass_edge_h"), east="glass_edge_v", west="glass_edge_v",
                   up="glass_bottom", down="glass_bottom")),
        cube("wall_n", (-5, 1, -8), (5, 15, -7), (0, 1, 0),
             faces(sides("glass_ns"), east="glass_ledge_v", west="glass_ledge_v",
                   up="glass_ledge_a", down="glass_ledge_a")),
        cube("wall_s", (-5, 1, 7), (5, 15, 8), (0, 1, 0),
             faces(sides("glass_ns"), east="glass_ledge_v", west="glass_ledge_v",
                   up="glass_ledge_a", down="glass_ledge_a")),
        cube("wall_w", (-6, 1, -7), (-5, 15, 7), (0, 1, 0),
             faces(sides("glass_ew"), north="glass_ledge_v", south="glass_ledge_v",
                   up="glass_ledge_v", down="glass_ledge_v")),
        cube("wall_e", (5, 1, -7), (6, 15, 7), (0, 1, 0),
             faces(sides("glass_ew"), north="glass_ledge_v", south="glass_ledge_v",
                   up="glass_ledge_v", down="glass_ledge_v")),
        # two chamfered shoulder rings; the corner gaps are the chamfer
        cube("shoulder1_n", (-4, 15, -6), (4, 17, -5), (0, 15, 0),
             faces(sides("glass_sh1_ns"), east="glass_pillar", west="glass_pillar",
                   up="glass_ledge_c", down="glass_ledge_c")),
        cube("shoulder1_s", (-4, 15, 5), (4, 17, 6), (0, 15, 0),
             faces(sides("glass_sh1_ns"), east="glass_pillar", west="glass_pillar",
                   up="glass_ledge_c", down="glass_ledge_c")),
        cube("shoulder1_w", (-5, 15, -5), (-4, 17, 5), (0, 15, 0),
             faces(sides("glass_sh1_ew"), north="glass_pillar", south="glass_pillar",
                   up="glass_ledge_d", down="glass_ledge_d")),
        cube("shoulder1_e", (4, 15, -5), (5, 17, 5), (0, 15, 0),
             faces(sides("glass_sh1_ew"), north="glass_pillar", south="glass_pillar",
                   up="glass_ledge_d", down="glass_ledge_d")),
        cube("shoulder2_n", (-3, 17, -5), (3, 19, -4), (0, 17, 0),
             faces(sides("glass_sh2_ns"), east="glass_pillar", west="glass_pillar",
                   up="glass_ledge_e", down="glass_ledge_e")),
        cube("shoulder2_s", (-3, 17, 4), (3, 19, 5), (0, 17, 0),
             faces(sides("glass_sh2_ns"), east="glass_pillar", west="glass_pillar",
                   up="glass_ledge_e", down="glass_ledge_e")),
        cube("shoulder2_w", (-4, 17, -4), (-3, 19, 4), (0, 17, 0),
             faces(sides("glass_sh1_ns"), north="glass_pillar", south="glass_pillar",
                   up="glass_ledge_f", down="glass_ledge_f")),
        cube("shoulder2_e", (3, 17, -4), (4, 19, 4), (0, 17, 0),
             faces(sides("glass_sh1_ns"), north="glass_pillar", south="glass_pillar",
                   up="glass_ledge_f", down="glass_ledge_f")),
        cube("neck_n", (-1, 19, -2), (1, 27, -1), (0, 19, 0),
             faces(sides("glass_neck_ns"), east="glass_neck_ew", west="glass_neck_ew",
                   up="glass_neck_top", down="glass_neck_top")),
        cube("neck_s", (-1, 19, 1), (1, 27, 2), (0, 19, 0),
             faces(sides("glass_neck_ns"), east="glass_neck_ew", west="glass_neck_ew",
                   up="glass_neck_top", down="glass_neck_top")),
        cube("neck_w", (-2, 19, -1), (-1, 27, 1), (0, 19, 0),
             faces(sides("glass_neck_ns"), north="glass_neck_ew", south="glass_neck_ew",
                   up="glass_neck_top_v", down="glass_neck_top_v")),
        cube("neck_e", (1, 19, -1), (2, 27, 1), (0, 19, 0),
             faces(sides("glass_neck_ns"), north="glass_neck_ew", south="glass_neck_ew",
                   up="glass_neck_top_v", down="glass_neck_top_v")),
        cube("lip", (-3, 27, -3), (3, 28, 3), (0, 27, 0),
             faces(all_faces("glass_lip_side"), up="glass_lip_top", down="glass_lip_top")),
        cube("cork", (-2, 28, -2), (2, 31, 2), (0, 28, 0),
             faces(all_faces("cork_side"), up="cork_top", down="cork_top")),
    ]}

    return {"name": MODEL_NAME, "origin": (0, 0, 0), "children": [sea, ship, bottle]}


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
        if c.get("rotation"):
            el["rotation"] = [float(v) for v in c["rotation"]]
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


def unsampled_rects(atlas: Atlas, tree) -> tuple[list[str], list[str]]:
    """Every sampled rect must be painted, and flag rects nothing samples."""
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
    unused = sorted(set(atlas.rects) - used)
    return bad, unused


def main() -> int:
    atlas = Atlas(64)
    for name, w, h in sorted(RECT_SIZES, key=lambda item: (-item[2], -item[1])):
        atlas.add(name, w, h)
    paint_texture(atlas)
    atlas.extend_edges()

    tree = build_tree()
    unpainted, unused = unsampled_rects(atlas, tree)
    if unpainted:
        raise SystemExit(f"faces sample unpainted rects: {unpainted}")
    if unused:
        print("warning: rects nothing samples:", ", ".join(unused))

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
