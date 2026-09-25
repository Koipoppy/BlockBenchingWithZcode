"""Build the 霸王花 (Bawanghua) flower-pot model as a Blockbench project.

    python tools/build_bawanghua_pot.py

Writes ../bawanghua_flower_pot/bawanghua_flower_pot.bbmodel (texture embedded as a data URI) and
../bawanghua_flower_pot/bawanghua_flower_pot.png (the same texture, standalone, for a resource pack).

Everything here is authored rather than downloaded, because no Mojang asset exists for
it: the flower pot is a *block* (Minecraft compiles block geometry into the engine and
publishes none of it), and 霸王花 is not Minecraft content at all.

Three format facts are measured from Blockbench 5.2.1's own source (resources/app.asar
-> dist/bundle.js.map) rather than guessed, because each one silently mirrors or
scrambles the art when it is wrong:

* js/util/three_custom.js (setShape) + js/outliner/types/cube.js (updateUV): a face's uv
  rect appears upright and *unmirrored* when that face is seen from outside. uv rects are
  in texture pixels with v measured from the top.
* Element and group rotations build the matrix Rz * Ry * Rx and pivot on `origin`
  (three.js euler order 'ZYX', the ModelFormat default). That is why every petal is a
  group spun about Y with the blade tilted about its *local* Z: a single element rotation
  cannot express "radially outward and tilted up" at once.
* ModelFormat('free') allows bones, arbitrary rotation and a centered grid, and its
  default camera sits at (-40, 32, -40) looking at (0, 12, 0) -- so the flower's mouth
  faces -Z (north) to be visible the moment the project is opened.
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
OUT_DIR = os.path.join(os.path.dirname(HERE), "bawanghua_flower_pot")
os.makedirs(OUT_DIR, exist_ok=True)
MODEL_NAME = "bawanghua_flower_pot"

FACES = ("north", "east", "south", "west", "up", "down")

# --- palette ---------------------------------------------------------------
# Terracotta clay in the family of vanilla's own flower_pot texture; the greens and
# crimson are pushed a little more saturated than vanilla, the way PvZ's plants are.
CLAY = [(190, 136, 102), (156, 105, 75), (122, 78, 53), (92, 55, 35)]
SOIL = [(112, 80, 55), (88, 61, 41), (66, 45, 30), (48, 32, 21)]
GREEN = [(128, 178, 78), (98, 145, 58), (70, 108, 41), (48, 76, 29)]
RED = [(246, 122, 138), (212, 76, 98), (170, 48, 72), (122, 30, 54), (84, 18, 40)]
MOUTH = [(58, 14, 26), (92, 26, 42)]
TOOTH = [(246, 243, 229), (216, 209, 190), (168, 162, 146)]
TONGUE = [(232, 122, 142), (192, 78, 102)]
POLLEN = (248, 214, 118)
PLACEHOLDER = (255, 0, 255, 255)


def shade(ramp, i):
    return ramp[max(0, min(len(ramp) - 1, i))]


def at(cv, r):
    return cv[r[1]:r[1] + r[3], r[0]:r[0] + r[2]]


def paint(cv, r, color):
    at(cv, r)[:] = (*color, 255)


def paint_rows(cv, r, rows):
    """rows: {row index from the top: color}"""
    for y, color in rows.items():
        at(cv, r)[y, :] = (*color, 255)


def paint_cols(cv, r, cols):
    for x, color in cols.items():
        at(cv, r)[:, x] = (*color, 255)


def speckle(cv, r, color, count, rng, rows=None):
    x0, y0, w, h = r
    span = list(range(h) if rows is None else rows)
    for _ in range(count):
        cv[y0 + rng.choice(span), x0 + rng.randrange(w)] = (*color, 255)


def edge_shadow(cv, r, color):
    """1px inner border -- the cheap outline that makes pixel art read at 16px."""
    sub = at(cv, r)
    sub[0, :] = sub[-1, :] = (*color, 255)
    sub[:, 0] = sub[:, -1] = (*color, 255)


class Atlas:
    """Shelf packer for the per-face uv rects, plus an edge-extend pass.

    The extend pass matters: rects are sampled with nearest-neighbour, so a face one
    texel off would otherwise pull in whatever was painted next door -- and the magenta
    placeholder underneath is unmistakable in the preview when a uv is wrong.
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
        for (x, y, w, h) in self.rects.values():
            sub = cv[y:y + h, x:x + w].copy()
            if x > 0:
                cv[y:y + h, x - 1] = sub[:, 0]
            if x + w < self.size:
                cv[y:y + h, x + w] = sub[:, -1]
            if y > 0:
                cv[y - 1, x:x + w] = sub[0, :]
            if y + h < self.size:
                cv[y + h, x:x + w] = sub[-1, :]

    def image(self) -> Image.Image:
        return Image.fromarray(self.cv, "RGBA")


# --- texture painters ------------------------------------------------------
# Every rect is sized to the faces that sample it, so no art is ever stretched.
RECT_SIZES = [
    ("pot_side", 6, 6), ("pot_rim_top", 8, 8), ("pot_rim_side", 8, 2),
    ("pot_bottom", 8, 8), ("stem_side", 2, 8), ("stem_cap", 2, 2),
    ("leaf_face", 7, 3), ("leaf_edge", 7, 1), ("leaf_end", 3, 1),
    ("leaf_z_up", 3, 7), ("leaf_z_dn", 3, 7),
    ("petal_face", 6, 5), ("petal_edge", 6, 1),
    ("sepal_face", 5, 4), ("sepal_edge", 5, 1),
    ("thorn", 1, 1), ("calyx_side", 5, 2), ("calyx_top", 5, 5),
    ("jaw_side", 10, 2), ("mouth_floor", 10, 8), ("jaw_bottom", 10, 8),
    ("head_front", 8, 3), ("skull_side", 10, 4), ("head_top", 8, 6),
    ("mouth_roof", 10, 8), ("cheek_side", 2, 4), ("throat", 6, 4),
    ("tooth_up", 2, 2), ("tooth_dn", 2, 2), ("tongue", 6, 2), ("spike", 2, 3),
]


def paint_texture(atlas: Atlas) -> None:
    cv, r = atlas.cv, atlas.rects
    rng = random.Random(20260924)

    # --- pot ---------------------------------------------------------------
    paint(cv, r["pot_side"], shade(CLAY, 1))
    paint_rows(cv, r["pot_side"], {0: shade(CLAY, 0), 5: shade(CLAY, 2)})
    paint_cols(cv, r["pot_side"], {0: shade(CLAY, 2), 5: shade(CLAY, 2)})
    speckle(cv, r["pot_side"], shade(CLAY, 2), 3, rng, rows=range(1, 5))
    speckle(cv, r["pot_side"], shade(CLAY, 0), 2, rng, rows=range(1, 5))

    # Rim top: clay ring around a 6x6 soil square, with a dark hole where the stem
    # enters, so the plant reads as planted rather than glued on.
    rim_top = r["pot_rim_top"]
    paint(cv, rim_top, shade(CLAY, 1))
    paint_rows(cv, rim_top, {0: shade(CLAY, 0), 7: shade(CLAY, 2)})
    paint_cols(cv, rim_top, {0: shade(CLAY, 0), 7: shade(CLAY, 2)})
    soil = (rim_top[0] + 1, rim_top[1] + 1, 6, 6)
    paint(cv, soil, shade(SOIL, 1))
    edge_shadow(cv, soil, shade(SOIL, 2))
    speckle(cv, rim_top, shade(SOIL, 0), 5, rng, rows=range(2, 6))
    paint(cv, (rim_top[0] + 3, rim_top[1] + 3, 2, 2), shade(SOIL, 3))

    paint_rows(cv, r["pot_rim_side"], {0: shade(CLAY, 0), 1: shade(CLAY, 2)})
    paint(cv, r["pot_bottom"], shade(CLAY, 3))
    speckle(cv, r["pot_bottom"], shade(CLAY, 2), 8, rng)

    # --- stem, leaves, calyx, thorns --------------------------------------
    paint_cols(cv, r["stem_side"], {0: shade(GREEN, 1), 1: shade(GREEN, 2)})
    speckle(cv, r["stem_side"], shade(GREEN, 2), 5, rng)
    speckle(cv, r["stem_side"], shade(GREEN, 0), 3, rng)
    paint(cv, r["stem_cap"], shade(GREEN, 2))

    # Leaf blade: dark edges and base, light tip, 1px midrib down the middle. Painted
    # symmetric about its centre line because the up and down faces of a leaf see the
    # rect's vertical axis in opposite directions.
    lf = at(cv, r["leaf_face"])
    for x in range(7):
        for y in range(3):
            c = shade(GREEN, 1) if y == 1 else shade(GREEN, 2)
            if x == 0:
                c = shade(GREEN, 2)
            if x >= 5:
                c = shade(GREEN, 0)
            lf[y, x] = (*c, 255)
    paint(cv, r["leaf_edge"], shade(GREEN, 2))
    paint(cv, r["leaf_end"], shade(GREEN, 2))
    for key, tip_at_top in (("leaf_z_up", True), ("leaf_z_dn", False)):
        sub = at(cv, r[key])
        for y in range(7):
            tip = (y < 2) if tip_at_top else (y >= 5)
            base = (y >= 5) if tip_at_top else (y < 2)
            for x in range(3):
                c = shade(GREEN, 1) if x == 1 else shade(GREEN, 2)
                if tip:
                    c = shade(GREEN, 0)
                if base:
                    c = shade(GREEN, 2)
                sub[y, x] = (*c, 255)

    paint(cv, r["thorn"], shade(GREEN, 3))
    paint_rows(cv, r["calyx_side"], {0: shade(GREEN, 1), 1: shade(GREEN, 2)})
    paint(cv, r["calyx_top"], shade(GREEN, 2))
    edge_shadow(cv, r["calyx_top"], shade(GREEN, 3))
    paint(cv, (r["calyx_top"][0] + 2, r["calyx_top"][1] + 2, 1, 1), shade(GREEN, 1))

    # --- petals: dark at the base, lit at the tip, vein down the middle -----
    # Petal blade: dark root, lit tip, 1px vein -- painted along the rect's *length*
    # axis, because a petal's blade is its top and bottom face, never a side.
    pf = at(cv, r["petal_face"])
    ramp = [4, 3, 3, 2, 1, 0]
    for x in range(6):
        for y in range(5):
            idx = ramp[x] + (1 if y in (0, 4) else 0)     # blade edges in shadow
            pf[y, x] = (*shade(RED, idx), 255)
    for x in (4, 5):
        pf[2, x] = (*shade(RED, 0), 255)                  # lit vein toward the tip
    pe = at(cv, r["petal_edge"])
    for x in range(6):
        pe[0, x] = (*shade(RED, [4, 3, 3, 2, 1, 1][x]), 255)

    sf = at(cv, r["sepal_face"])
    sramp = [3, 3, 2, 1, 0]
    for x in range(5):
        for y in range(4):
            sf[y, x] = (*shade(GREEN, sramp[x] + (1 if y in (0, 3) else 0)), 255)
    se = at(cv, r["sepal_edge"])
    for x in range(5):
        se[0, x] = (*shade(GREEN, min(3, sramp[x] + 1)), 255)

    # --- the maw -----------------------------------------------------------
    paint_rows(cv, r["jaw_side"], {0: shade(RED, 2), 1: shade(RED, 4)})
    paint_rows(cv, r["cheek_side"], {0: shade(RED, 3), 1: shade(RED, 3),
                                     2: shade(RED, 4), 3: shade(RED, 4)})
    paint(cv, r["jaw_bottom"], shade(RED, 4))
    speckle(cv, r["jaw_bottom"], shade(RED, 3), 10, rng)
    paint(cv, r["mouth_floor"], shade(MOUTH, 0))
    edge_shadow(cv, r["mouth_floor"], shade(MOUTH, 1))
    speckle(cv, r["mouth_floor"], shade(MOUTH, 1), 9, rng)
    paint(cv, r["mouth_roof"], shade(MOUTH, 0))
    speckle(cv, r["mouth_roof"], shade(MOUTH, 1), 11, rng)

    th = at(cv, r["throat"])
    for y in range(4):
        th[y, :] = (*shade(MOUTH, 1 if y < 2 else 0), 255)

    # Teeth: the gum line sits at the top on the upper row and at the bottom on the
    # lower one, which is why they need two rects rather than one flipped at runtime.
    paint_rows(cv, r["tooth_up"], {0: shade(TOOTH, 2), 1: shade(TOOTH, 0)})
    paint_rows(cv, r["tooth_dn"], {0: shade(TOOTH, 0), 1: shade(TOOTH, 2)})
    paint(cv, r["tongue"], shade(TONGUE, 0))
    paint_rows(cv, r["tongue"], {0: shade(TONGUE, 1)})   # shadow under the front teeth

    paint(cv, r["skull_side"], shade(RED, 2))
    paint_rows(cv, r["skull_side"], {0: shade(RED, 1), 3: shade(RED, 3)})
    speckle(cv, r["skull_side"], shade(RED, 3), 7, rng, rows=range(1, 3))
    speckle(cv, r["skull_side"], shade(RED, 1), 5, rng, rows=range(1, 3))

    # The face: two eyes set above the mouth, the one thing that makes a PvZ plant read
    # as a character rather than a shrub.
    hf = at(cv, r["head_front"])
    hf[:] = (*shade(RED, 2), 255)
    hf[0, :] = (*shade(RED, 1), 255)
    hf[2, :] = (*shade(RED, 3), 255)
    for eye_x in (1, 5):
        hf[1:3, eye_x:eye_x + 2] = (*shade(TOOTH, 0), 255)
        hf[2, eye_x + 1] = (*shade(MOUTH, 0), 255)        # pupil, toward the middle

    paint(cv, r["head_top"], shade(RED, 1))
    edge_shadow(cv, r["head_top"], shade(RED, 2))
    paint(cv, (r["head_top"][0] + 3, r["head_top"][1] + 2, 4, 4), shade(RED, 0))
    for px, py in ((4, 3), (5, 5), (6, 3)):
        cv[r["head_top"][1] + py, r["head_top"][0] + px] = (*POLLEN, 255)

    paint(cv, r["spike"], shade(GREEN, 2))
    paint_rows(cv, r["spike"], {0: shade(GREEN, 1), 2: shade(GREEN, 3)})


# --- geometry --------------------------------------------------------------
# Blockbench pixels: 1 unit = 1/16 block. The pot stands on y=0, centred on x=z=0, and
# the plant tops out at y=29 -- not quite two blocks, the way a big potted plant sits in
# a build. The mouth opens toward -Z (north), and a pair of cheeks closes the gap between
# jaw and skull so the head reads as one chunky block with a maw cut into it rather than
# as two halves floating apart.
PETAL_R0 = 2.0


def all_faces(rect):
    return {f: rect for f in FACES}


def sides(rect):
    return {f: rect for f in ("north", "south", "east", "west")}


def faces(base, **overrides):
    """Face -> rect map: start from a base (all_faces/sides), override named faces."""
    merged = dict(base)
    merged.update(overrides)
    return merged


def cube(name, frm, to, origin, facemap, rotation=None):
    return {"name": name, "from": frm, "to": to, "origin": origin,
            "faces": facemap, "rotation": rotation}


def petal_whorl(prefix: str, y: float, r0: float, length: float, width: float,
                tilt: float, count: int, offset: float):
    """One whorl of petals: a group per petal so each blade tilts in its own frame.

    The group carries the Y spin, the element carries only the local Z tilt -- the
    composition Blockbench's Rz*Ry*Rx order supports. A single element rotation cannot
    spin a blade around the stem *and* tilt it up.
    """
    whorl = []
    for i in range(count):
        angle = offset + i * (360.0 / count)
        blade = cube(
            f"{prefix}_blade_{i:02d}",
            (r0, y, -width / 2), (r0 + length, y + 1, width / 2), (r0, y, 0),
            faces(all_faces(f"{prefix}_edge"), up=f"{prefix}_face", down=f"{prefix}_face"),
            rotation=(0, 0, tilt),
        )
        whorl.append({"name": f"{prefix}_{i:02d}", "origin": (0, y, 0),
                      "rotation": (0, angle, 0), "cubes": [blade]})
    return whorl


def build_tree():
    pot = {"name": "pot", "origin": (0, 0, 0), "cubes": [
        cube("pot_base", (-3, 0, -3), (3, 6, 3), (0, 0, 0),
             faces(sides("pot_side"), up="pot_side", down="pot_bottom")),
        cube("pot_rim", (-4, 6, -4), (4, 8, 4), (0, 6, 0),
             faces(sides("pot_rim_side"), up="pot_rim_top", down="pot_bottom")),
    ]}

    stem = {"name": "stem", "origin": (0, 8, 0), "cubes": [
        cube("stem", (-1, 8, -1), (1, 16, 1), (0, 8, 0),
             faces(sides("stem_side"), up="stem_cap", down="stem_cap")),
        cube("thorn_west", (-2, 11.8, -0.5), (-1, 12.8, 0.5), (-1, 11.8, 0),
             faces(all_faces("thorn")), rotation=(0, 0, -35)),
        cube("thorn_east", (1, 12.2, -0.5), (2, 13.2, 0.5), (1, 12.2, 0),
             faces(all_faces("thorn")), rotation=(0, 0, 35)),
    ]}

    leaves = {"name": "leaves", "origin": (0, 8, 0), "cubes": [
        cube("leaf_east", (1, 9, -1.5), (8, 10, 1.5), (1, 9, 0),
             faces(sides("leaf_edge"), up="leaf_face", down="leaf_face",
                   east="leaf_end", west="leaf_end"), rotation=(0, 0, 18)),
        cube("leaf_west", (-8, 9, -1.5), (-1, 10, 1.5), (-1, 9, 0),
             faces(sides("leaf_edge"), up="leaf_face", down="leaf_face",
                   east="leaf_end", west="leaf_end"), rotation=(0, 0, -18)),
        # The north/south leaves are Z-aligned, so their up and down faces see the rect's
        # vertical axis in opposite directions and need their own two rects.
        cube("leaf_north", (-1.5, 11, -8), (1.5, 12, -1), (0, 11, -1),
             faces(sides("leaf_end"), east="leaf_edge", west="leaf_edge",
                   up="leaf_z_up", down="leaf_z_dn"), rotation=(18, 0, 0)),
        cube("leaf_south", (-1.5, 11, 1), (1.5, 12, 8), (0, 11, 1),
             faces(sides("leaf_end"), east="leaf_edge", west="leaf_edge",
                   up="leaf_z_dn", down="leaf_z_up"), rotation=(-18, 0, 0)),
    ]}

    calyx = {"name": "calyx", "origin": (0, 12, 0), "cubes": [
        cube("calyx", (-2.5, 12, -2.5), (2.5, 14, 2.5), (0, 12, 0),
             faces(sides("calyx_side"), up="calyx_top", down="calyx_top")),
    ]}

    jaw = {"name": "jaw", "origin": (0, 16, 0), "cubes": [
        cube("jaw", (-5, 16, -4), (5, 18, 4), (0, 16, 0),
             faces(sides("jaw_side"), up="mouth_floor", down="jaw_bottom")),
        cube("cheek_west", (-5, 18, -4), (-3, 22, 4), (0, 18, 0),
             faces(all_faces("cheek_side"), east="skull_side", west="skull_side")),
        cube("cheek_east", (3, 18, -4), (5, 22, 4), (0, 18, 0),
             faces(all_faces("cheek_side"), east="skull_side", west="skull_side")),
        cube("tooth_lower_west", (-3, 18, -4), (-1, 19.5, -3), (0, 18, 0),
             faces(all_faces("tooth_up"), north="tooth_dn", south="tooth_dn")),
        cube("tooth_lower_east", (1, 18, -4), (3, 19.5, -3), (0, 18, 0),
             faces(all_faces("tooth_up"), north="tooth_dn", south="tooth_dn")),
        cube("tongue_base", (-2, 18, 0), (2, 19.2, 2), (0, 18, 0),
             faces(all_faces("tongue"))),
        cube("tongue_tip", (-1.5, 18, -2), (1.5, 19, 0), (0, 18, 0),
             faces(all_faces("tongue"))),
    ]}

    # The skull tapers: a 10x8 lower block with an 8x6 block stepped in on top of it.
    # A straight box of that size reads as a crate; MC models get their roundness from
    # exactly this kind of one-pixel step.
    skull = {"name": "skull", "origin": (0, 22, 0), "cubes": [
        cube("skull_lower", (-5, 22, -4), (5, 24, 4), (0, 22, 0),
             faces(sides("skull_side"), up="skull_side", down="mouth_roof")),
        cube("skull_upper", (-4, 24, -3), (4, 27, 3), (0, 24, 0),
             faces(sides("skull_side"), up="head_top", down="skull_side",
                   north="head_front")),
        cube("tooth_upper_west", (-2.5, 20.5, -4), (-0.5, 22, -3), (0, 22, 0),
             faces(all_faces("tooth_dn"), north="tooth_up", south="tooth_up")),
        cube("tooth_upper_east", (0.5, 20.5, -4), (2.5, 22, -3), (0, 22, 0),
             faces(all_faces("tooth_dn"), north="tooth_up", south="tooth_up")),
    ]}

    maw = {"name": "maw", "origin": (0, 18, 0), "cubes": [
        cube("throat", (-3, 18, 0), (3, 22, 4), (0, 18, 0), faces(all_faces("throat"))),
    ]}

    crown = {"name": "crown", "origin": (0, 27, 0), "cubes": [
        cube("spike_centre", (-1, 27, -1), (1, 30, 1), (0, 27, 0),
             faces(all_faces("spike"))),
        cube("spike_west", (-4, 26, -1), (-1, 28, 1), (-1, 27, 0),
             faces(all_faces("spike")), rotation=(0, 0, -35)),
        cube("spike_east", (1, 26, -1), (4, 28, 1), (1, 27, 0),
             faces(all_faces("spike")), rotation=(0, 0, 35)),
        cube("spike_north", (-1, 26, -4), (1, 28, -1), (0, 27, -1),
             faces(all_faces("spike")), rotation=(35, 0, 0)),
        cube("spike_south", (-1, 26, 1), (1, 28, 4), (0, 27, 1),
             faces(all_faces("spike")), rotation=(-35, 0, 0)),
    ]}

    head = {"name": "head", "origin": (0, 16, 0), "children": [
        # A collar under the head rather than around it: the head is 10 wide, so petal
        # roots reaching inward of r=5 stay hidden behind its silhouette instead of
        # punching through it. Green sepals sit under the petals, as on the real flower.
        {"name": "petals", "origin": (0, 14, 0),
         "children": petal_whorl("petal", 14, 2.5, 6, 5, 16, 8, 0)},
        {"name": "sepals", "origin": (0, 13, 0),
         "children": petal_whorl("sepal", 13, 2.5, 4.5, 4, 8, 8, 22.5)},
        maw, jaw, skull, crown,
    ]}

    plant = {"name": "plant", "origin": (0, 8, 0),
             "children": [stem, leaves, calyx, head]}
    return {"name": MODEL_NAME, "origin": (0, 0, 0), "children": [pot, plant]}


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
        group = {"name": node["name"],
                 "origin": [float(v) for v in node["origin"]],
                 "uuid": str(uuid.uuid4()),
                 "children": children}
        if node.get("rotation"):
            group["rotation"] = [float(v) for v in node["rotation"]]
        return group

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
    """Every rect a face samples must be painted, not left as placeholder magenta.

    Cheap and total: a wrong uv name, or a rect that was registered but never painted,
    shows up here instead of as a magenta patch on the model.
    """
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
    for name, w, h in sorted(RECT_SIZES, key=lambda item: -item[2]):
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
