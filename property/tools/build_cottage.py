"""Build the 精致小屋 (cozy cottage) as a Blockbench project.

    python tools/build_cottage.py

Writes ../cottage/cottage.bbmodel (texture embedded as a data URI) and ../cottage/cottage.png
(the same texture, standalone).

A vanilla-style cottage display model, built entirely from axis-aligned cubes
so it also exports cleanly to a Java block model. The look is the classic
survival-house recipe: cobblestone foundation with a lip, oak plank walls with
bark-log corner posts and a log ring beam, recessed door and windows, a 45
degree stepped dark-shingle roof with overhang and gables, a brick chimney,
plus the cottage dressing: wall lantern, flower boxes, a small attic window,
stone steps and stepping stones.

Layout (units of 1/16 block, ground y=0, front faces -Z / north):
  foundation 24x3x18 at x +-12 / z +-9, walls 22x10x16 (y 3..13), log ring
  y 13..15, roof rows from y 15 up to the ridge cap at y 29. Total height 29
  (~1.8 blocks), footprint with eaves 26 x 18.

Format conventions are the ones measured out of Blockbench's source (see
build_bawanghua_pot.py): per-face uv rects upright and unmirrored seen from
outside, v from the top; model_format 'free'. Unlike the other models here the
texture is a shared atlas: every face samples the rect for its (material,
width, height) pair, so one cobble rect serves every face of that size. All
painters are noise/symmetric, so sharing never shows, and the atlas self-check
convention (unpainted corners stay magenta) still holds.
"""
from __future__ import annotations

import base64
import io
import json
import os
import random
import uuid
import zlib

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(os.path.dirname(HERE), "cottage")
os.makedirs(OUT_DIR, exist_ok=True)
MODEL_NAME = "cottage"

FACES = ("north", "east", "south", "west", "up", "down")
PLACEHOLDER = (255, 0, 255, 255)

# --- palettes (hand-picked vanilla look; official assets are unreachable) ---
PLANK = [(178, 146, 92), (164, 132, 80), (150, 118, 70), (136, 106, 62)]
PLANK_SEAM = (106, 82, 46)
DARK = [(88, 62, 38), (76, 52, 30), (64, 44, 24), (52, 36, 18)]
BARK = [(110, 88, 54), (98, 76, 46), (84, 64, 38), (70, 52, 30)]
END_LIGHT = (188, 152, 96)
END_RING = (150, 118, 70)
COBBLE = [(136, 136, 136), (122, 122, 122), (108, 108, 108), (94, 94, 94)]
COBBLE_HI = (152, 152, 152)
MORTAR = (78, 78, 78)
BRICK = [(152, 88, 68), (140, 78, 60), (128, 68, 52)]
BRICK_MORTAR = (186, 178, 170)
SHINGLE = [(92, 62, 36), (80, 52, 30), (66, 42, 24), (52, 32, 18)]
GLASS_FRAME = (56, 40, 24)
GLASS = (186, 214, 226)
GLASS_LIT = (214, 234, 240)
GLASS_STREAK = (234, 246, 250)
DOOR_OAK = (164, 132, 80)
DOOR_FRAME = (46, 32, 18)
LANTERN_FRAME = (30, 26, 22)
LANTERN_GLOW = (255, 206, 96)
LANTERN_HOT = (255, 236, 170)
POPPY = (210, 66, 52)
DANDELION = (238, 196, 58)
CAP_HOLE = (24, 18, 14)


def shade(ramp, i):
    return ramp[max(0, min(len(ramp) - 1, i))]


def at(cv, r):
    return cv[r[1]:r[1] + r[3], r[0]:r[0] + r[2]]


def paint(cv, r, color):
    at(cv, r)[:] = (*color, 255)


def rng_for(key):
    return random.Random(zlib.crc32(f"{MODEL_NAME}:{key}".encode()))


# --- texture painters -------------------------------------------------------
# Every painter fills its whole rect; a shared rect is painted exactly once.

def paint_planks(cv, r, key):
    """Oak boards: 3px boards, dark seam under each, tint jitter + grain."""
    x, y, w, h = r
    rng = rng_for(key)
    a = at(cv, r)
    for row in range(h):
        board = row // 3
        if row % 3 == 2:
            a[row, :] = (*PLANK_SEAM, 255)
        else:
            a[row, :] = (*shade(PLANK, 1 if rng.random() < 0.8 else 2), 255)
    for _ in range(max(1, (w * h) // 12)):
        px, py = rng.randrange(w), rng.randrange(h)
        if py % 3 != 2:
            a[py, px] = (*PLANK_SEAM, 255)


def paint_dark(cv, r, key):
    """Dark oak boards (door jamb, lantern arm, flower boxes), 2px boards."""
    x, y, w, h = r
    rng = rng_for(key)
    a = at(cv, r)
    for row in range(h):
        board = row // 2
        if row % 2 == 1 and board > 0:
            a[row, :] = (*shade(DARK, 3), 255)
        else:
            a[row, :] = (*shade(DARK, board % 2), 255)
    for _ in range(max(1, (w * h) // 10)):
        px, py = rng.randrange(w), rng.randrange(h)
        if py % 2 == 0:
            a[py, px] = (*shade(DARK, 3), 255)


def paint_bark(cv, r, key):
    """Log bark; grain runs along the long axis of the face."""
    x, y, w, h = r
    rng = rng_for(key)
    a = at(cv, r)
    if w >= h:  # horizontal log: streaks run along x
        for row in range(h):
            a[row, :] = (*shade(BARK, rng.choice((1, 1, 2, 2, 3))), 255)
        col = 0
        while col < w:
            run = rng.choice((2, 3, 4))
            tone = rng.choice((0, 1, 1, 2, 3))
            a[:, col:col + run] = (*shade(BARK, tone), 255)
            col += run
    else:  # vertical post: streaks run along y
        for col in range(w):
            a[:, col] = (*shade(BARK, rng.choice((1, 1, 2, 2, 3))), 255)
        row = 0
        while row < h:
            run = rng.choice((2, 3, 4))
            tone = rng.choice((0, 1, 1, 2, 3))
            a[row:row + run, :] = (*shade(BARK, tone), 255)
            row += run


def paint_log_end(cv, r, key):
    """Log end grain: bark rim + light heart with a ring."""
    a = at(cv, r)
    w, h = r[2], r[3]
    a[:] = (*END_LIGHT, 255)
    if w >= 3 and h >= 3:
        a[0, :] = (*shade(BARK, 2), 255)
        a[-1, :] = (*shade(BARK, 2), 255)
        a[:, 0] = (*shade(BARK, 2), 255)
        a[:, -1] = (*shade(BARK, 2), 255)
        a[1:-1, 1:-1] = (*END_RING, 255)
        a[h // 2 - 1:h // 2 + 1, w // 2 - 1:w // 2 + 1] = (*END_LIGHT, 255)
    elif w == 2 and h == 2:
        a[0, 0] = (*END_RING, 255)
        a[1, 1] = (*END_RING, 255)
    else:
        a[:, w // 2:] = (*END_RING, 255)


def paint_cobble(cv, r, key):
    """Mortar field + jittered stones, each shaded light top-left."""
    x, y, w, h = r
    rng = rng_for(key)
    a = at(cv, r)
    a[:] = (*MORTAR, 255)
    ry = 0
    while ry < h:
        rh = min(rng.choice((2, 3)), h - ry)
        rx = 0
        while rx < w:
            rw = min(rng.choice((3, 4, 5)), w - rx)
            if w - (rx + rw) == 1:
                rw += 1
            tone = rng.choice((0, 1, 1, 2, 2, 3))
            a[ry:ry + rh, rx:rx + rw] = (*shade(COBBLE, tone), 255)
            a[ry, rx] = (*(COBBLE_HI if tone < 2 else shade(COBBLE, max(0, tone - 1))), 255)
            a[ry + rh - 1, rx + rw - 1] = (*shade(COBBLE, min(3, tone + 1)), 255)
            rx += rw + 1
        ry += rh + 1


def paint_brick(cv, r, key):
    """Running-bond bricks: 2px bricks, 1px light mortar, rows offset."""
    x, y, w, h = r
    rng = rng_for(key)
    a = at(cv, r)
    a[:] = (*BRICK_MORTAR, 255)
    row = 0
    band = 0
    while row < h:
        if row + 3 <= h:
            off = 2 if band % 2 else 0
            cx = -off
            while cx < w:
                bw = min(3, w - cx)
                if bw > 0 and cx + bw > 0:
                    lo, hi = max(0, cx), min(w, cx + bw)
                    a[row:row + 2, lo:hi] = (*shade(BRICK, rng.choice((0, 0, 1, 2))), 255)
                cx += 4
            row += 3
        else:
            a[row:h, :] = (*shade(BRICK, 1), 255)
            row = h
        band += 1


def paint_shingle(cv, r, key):
    """Dark shingles: 2px courses, light butt edge, staggered vertical seams."""
    x, y, w, h = r
    rng = rng_for(key)
    a = at(cv, r)
    course = 0
    for row in range(0, h, 2):
        tone = rng.choice((1, 1, 2, 2, 3))
        a[row:row + 1, :] = (*shade(SHINGLE, max(0, tone - 1)), 255)
        if row + 1 < h:
            a[row + 1, :] = (*shade(SHINGLE, tone), 255)
        off = course % 2
        for sx in range(off, w, 3):
            if row + 1 < h:
                a[row + 1, sx] = (*shade(SHINGLE, 3), 255)
        course += 1


def paint_glass(cv, r, key):
    """Wood-framed window: pale glass, lit top edge, one diagonal streak."""
    x, y, w, h = r
    rng = rng_for(key)
    a = at(cv, r)
    a[:] = (*GLASS, 255)
    a[0, :] = (*GLASS_FRAME, 255)
    a[-1, :] = (*GLASS_FRAME, 255)
    a[:, 0] = (*GLASS_FRAME, 255)
    a[:, -1] = (*GLASS_FRAME, 255)
    if w >= 4 and h >= 4:
        a[1, 1:-1] = (*GLASS_LIT, 255)
        for i in range(1, w - 1):
            for j in range(1, h - 1):
                if (i - j) % 4 == 0:
                    a[j, i] = (*GLASS_STREAK, 255)


def paint_door(cv, r, key):
    """Front door, 6x10: dark frame, vertical oak boards, transom window."""
    a = at(cv, r)
    a[:] = (*DOOR_FRAME, 255)
    a[1:9, 1:5] = (*DOOR_OAK, 255)
    for col in range(1, 5):
        tone = (col // 1) % 2
        a[1:9, col] = (*(DOOR_OAK if tone == 0 else (154, 122, 72)), 255)
    a[1, 1:5] = (*GLASS_LIT, 255)      # transom panes
    a[3, 1:5] = (*GLASS_LIT, 255)
    a[2, 1:5] = (*DOOR_FRAME, 255)     # transom bar
    a[1:4, 0] = (*DOOR_FRAME, 255)
    a[4, 4] = (20, 16, 12, 255)        # handle
    a[5, 4] = (48, 40, 32, 255)
    a[7:9, 1:5] = (*(140, 110, 64), 255)  # plinth board
    a[8, 1:5] = (*(120, 92, 52), 255)


def paint_lantern(cv, r, key):
    """Glowing panes with a black cap and base."""
    a = at(cv, r)
    w, h = r[2], r[3]
    a[:] = (*LANTERN_GLOW, 255)
    a[0, :] = (*LANTERN_FRAME, 255)
    a[-1, :] = (*LANTERN_FRAME, 255)
    if h >= 3 and w >= 2:
        a[1 + (h - 2) // 2, w // 2] = (*LANTERN_HOT, 255)


def paint_lantern_black(cv, r, key):
    paint(cv, r, LANTERN_FRAME)


def paint_flower_red(cv, r, key):
    paint(cv, r, POPPY)


def paint_flower_yellow(cv, r, key):
    paint(cv, r, DANDELION)


def paint_cap_top(cv, r, key):
    """Chimney cap top: bricks with a dark flue hole and a smoke shadow."""
    paint_brick(cv, r, key)
    a = at(cv, r)
    w, h = r[2], r[3]
    cx, cy = w // 2, h // 2
    a[cy - 2:cy + 2, cx - 2:cx + 2] = (40, 30, 24, 255)
    a[cy - 1:cy + 1, cx - 1:cx + 1] = (*CAP_HOLE, 255)


PAINTERS = {
    "planks": paint_planks, "dark": paint_dark, "bark": paint_bark,
    "log_end": paint_log_end, "cobble": paint_cobble, "brick": paint_brick,
    "shingle": paint_shingle, "glass": paint_glass, "door": paint_door,
    "lantern": paint_lantern, "lantern_black": paint_lantern_black,
    "flower_red": paint_flower_red, "flower_yellow": paint_flower_yellow,
    "cap_top": paint_cap_top,
}


class Atlas:
    """Shelf packer keyed by (material, w, h); each rect painted on allocate."""

    def __init__(self, size: int):
        self.size = size
        self.cv = np.zeros((size, size, 4), np.uint8)
        self.cv[:] = PLACEHOLDER
        self.rects: dict[tuple, tuple[int, int, int, int]] = {}
        self._x = self._y = self._row_h = 0

    def alloc(self, key, w, h) -> tuple[int, int, int, int]:
        if self._x + w > self.size:
            self._x = 0
            self._y += self._row_h + 1
            self._row_h = 0
        if self._y + h > self.size:
            raise RuntimeError(f"atlas full placing {key} ({w}x{h})")
        r = (self._x, self._y, w, h)
        self.rects[key] = r
        self._x += w + 1
        self._row_h = max(self._row_h, h)
        PAINTERS[key[0]](self.cv, r, f"{key[0]}:{key[1]}x{key[2]}")
        return r

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


# --- geometry ---------------------------------------------------------------
# Units of 1/16 block, ground y=0, centred on x=z=0, facing -Z (north).

def face_size(face, frm, to):
    dx, dy, dz = (to[0] - frm[0], to[1] - frm[1], to[2] - frm[2])
    s = {"north": (dx, dy), "south": (dx, dy), "east": (dz, dy),
         "west": (dz, dy), "up": (dx, dz), "down": (dx, dz)}[face]
    return int(round(s[0])), int(round(s[1]))


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


def build_tree():
    tree = {"name": MODEL_NAME, "origin": (0, 0, 0), "children": []}

    def group(name, cubes, origin=(0, 0, 0)):
        tree["children"].append(
            {"name": name, "origin": origin, "cubes": cubes, "children": []})

    # --- foundation, steps, stepping stones ---------------------------------
    group("foundation", [
        cube("foundation", (-12, 0, -9), (12, 3, 9), FM(all="cobble")),
        cube("step_lower", (-4, 0, -10), (4, 1, -9), FM(all="cobble")),
        cube("step_upper", (-3, 1, -10), (3, 3, -9), FM(all="cobble")),
        cube("stepping_stone_a", (-3, 0, -12), (2, 1, -10), FM(all="cobble")),
        cube("stepping_stone_b", (3, 0, -13), (6, 1, -11), FM(all="cobble")),
    ])

    # --- walls: planks between bark posts, recessed door and windows --------
    walls = []
    # front wall pieces (z -8..-6) around door x -3..3 and windows x +-4..8
    for name, x0, x1 in (("strip_w", -9, -8), ("strip_wl", -4, -3),
                         ("strip_wr", 3, 4), ("strip_e", 8, 9)):
        walls.append(cube(f"front_{name}", (x0, 3, -8), (x1, 13, -6), FM(all="planks")))
    for tag, x0, x1 in (("wl", -8, -4), ("wr", 4, 8)):
        walls.append(cube(f"front_{tag}_sill", (x0, 3, -8), (x1, 7, -6), FM(all="planks")))
        walls.append(cube(f"front_{tag}_head", (x0, 12, -8), (x1, 13, -6), FM(all="planks")))
        walls.append(cube(f"window_front_{tag}", (x0, 7, -7), (x1, 12, -6), FM(all="glass")))
    # side walls (x +-9..11) with a window at z -2..2
    for tag, x0, x1 in (("east", 9, 11), ("west", -11, -9)):
        walls.append(cube(f"side_{tag}_sill", (x0, 3, -2), (x1, 7, 2), FM(all="planks")))
        walls.append(cube(f"side_{tag}_head", (x0, 12, -2), (x1, 13, 2), FM(all="planks")))
        walls.append(cube(f"side_{tag}_strip_s", (x0, 3, -6), (x1, 13, -2), FM(all="planks")))
        walls.append(cube(f"side_{tag}_strip_n", (x0, 3, 2), (x1, 13, 6), FM(all="planks")))
        gx0, gx1 = (9, 10) if tag == "east" else (-10, -9)
        walls.append(cube(f"window_side_{tag}", (gx0, 7, -2), (gx1, 12, 2), FM(all="glass")))
    # back wall (z 6..8) with a window at x -2..2
    walls.append(cube("back_sill", (-2, 3, 6), (2, 7, 8), FM(all="planks")))
    walls.append(cube("back_head", (-2, 12, 6), (2, 13, 8), FM(all="planks")))
    walls.append(cube("back_strip_w", (-9, 3, 6), (-2, 13, 8), FM(all="planks")))
    walls.append(cube("back_strip_e", (2, 3, 6), (9, 13, 8), FM(all="planks")))
    walls.append(cube("window_back", (-2, 7, 6), (2, 12, 7), FM(all="glass")))
    # corner posts
    for tag, x0, x1, z0, z1 in (("nw", -11, -9, -8, -6), ("ne", 9, 11, -8, -6),
                                ("sw", -11, -9, 6, 8), ("se", 9, 11, 6, 8)):
        walls.append(cube(f"post_{tag}", (x0, 3, z0), (x1, 13, z1),
                          FM(all="bark", up="log_end", down="log_end")))
    # log ring beam, y 13..15 (front/back run the full width, sides fill in)
    walls.append(cube("ring_front", (-11, 13, -8), (11, 15, -6),
                      FM(all="bark", east="log_end", west="log_end")))
    walls.append(cube("ring_back", (-11, 13, 6), (11, 15, 8),
                      FM(all="bark", east="log_end", west="log_end")))
    walls.append(cube("ring_east", (9, 13, -6), (11, 15, 6),
                      FM(all="bark", north="log_end", south="log_end")))
    walls.append(cube("ring_west", (-11, 13, -6), (-9, 15, 6),
                      FM(all="bark", north="log_end", south="log_end")))
    group("walls", walls)

    # --- roof: stepped shingle rows, gables, ridge, chimney ------------------
    roof = []
    # gable steps: j=0 widest, tracking the roof underside above the wall plane
    for side, z0, z1 in (("front", -8, -6), ("back", 6, 8)):
        for j in range(6):
            x = 11 - 2 * j
            roof.append(cube(f"gable_{side}_{j}", (-x, 15 + 2 * j, z0),
                             (x, 17 + 2 * j, z1), FM(all="planks")))
    # small attic window mounted proud of the front gable face
    roof.append(cube("window_attic", (-2, 19.5, -9), (2, 22.5, -8), FM(all="glass")))
    # roof rows: k=0 is the eave overhang, each row steps 2 in and 2 up
    for k in range(6):
        x0, x1 = 11 - 2 * k, 13 - 2 * k
        y0, y1 = 15 + 2 * k, 17 + 2 * k
        roof.append(cube(f"roof_east_{k}", (x0, y0, -9), (x1, y1, 9), FM(all="shingle")))
        roof.append(cube(f"roof_west_{k}", (-x1, y0, -9), (-x0, y1, 9), FM(all="shingle")))
    roof.append(cube("ridge", (-1, 27, -9), (1, 29, 9), FM(all="shingle")))
    # brick chimney punching through the east slope, with a capped top
    roof.append(cube("chimney_shaft", (4, 1, -2), (8, 26, 2), FM(all="brick")))
    roof.append(cube("chimney_cap", (3, 26, -3), (9, 27, 3),
                     FM(all="brick", up="cap_top")))
    group("roof", roof)

    # --- door on a hinge pivot so it can be swung open in an animation -------
    group("door", [cube("door", (-3, 3, -7), (3, 13, -6),
                       FM(sides="dark", north="door", up="dark", down="dark"))],
          origin=(-3, 8, -6.5))

    # --- dressing: lantern, flower boxes with flowers ------------------------
    details = [
        cube("lantern_arm", (3, 12, -9), (4, 13, -7), FM(all="dark")),
        cube("lantern_body", (3, 9, -9), (4, 12, -7),
             FM(ns="lantern", ew="lantern", up="lantern_black", down="lantern_black")),
        cube("flowerbox_front", (4, 6, -9), (8, 7, -8), FM(all="dark")),
        cube("flowerbox_front_west", (-8, 6, -9), (-4, 7, -8), FM(all="dark")),
        cube("flowerbox_back", (-2, 6, 8), (2, 7, 9), FM(all="dark")),
    ]
    for i, (x0, x1) in enumerate(((4, 5), (5.5, 6.5), (7, 8))):
        details.append(cube(f"flower_front_{i}", (x0, 7, -9), (x1, 8, -8),
                            FM(all="flower_red" if i % 2 == 0 else "flower_yellow")))
    for i, (x0, x1) in enumerate(((-8, -7), (-6.5, -5.5), (-5, -4))):
        details.append(cube(f"flower_frontw_{i}", (x0, 7, -9), (x1, 8, -8),
                            FM(all="flower_red" if i % 2 == 0 else "flower_yellow")))
    for i, (x0, x1) in enumerate(((-2, -1), (-0.5, 0.5), (1, 2))):
        details.append(cube(f"flower_back_{i}", (x0, 7, 8), (x1, 8, 9),
                            FM(all="flower_red" if i % 2 == 0 else "flower_yellow")))
    group("details", details)

    return tree


# --- bbmodel writing -------------------------------------------------------
def collect_rects(tree):
    """Every (material, w, h) pair any face samples, tallest first for packing."""
    seen = {}

    def walk(node):
        for c in node.get("cubes") or []:
            for face, mat in c["faces"].items():
                w, h = face_size(face, c["from"], c["to"])
                seen[(mat, w, h)] = True
        for child in node.get("children") or []:
            walk(child)

    walk(tree)
    return sorted(seen, key=lambda k: (-k[2], -k[1]))


def build_atlas(tree) -> Atlas:
    keys = collect_rects(tree)
    for size in (160, 192, 224, 256):
        atlas = Atlas(size)
        try:
            for mat, w, h in keys:
                atlas.alloc((mat, w, h), w, h)
        except RuntimeError:
            continue
        atlas.extend_edges()
        return atlas
    raise SystemExit("no atlas size fits the model")


def write_model(path: str, tree, atlas: Atlas, texture: Image.Image) -> int:
    elements: list[dict] = []

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
        }
        for face in FACES:
            mat = c["faces"][face]
            w, h = face_size(face, c["from"], c["to"])
            x, y, rw, rh = atlas.rects[(mat, w, h)]
            el["faces"][face] = {"uv": [x, y, x + rw, y + rh], "texture": 0}
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
        "resolution": {"width": atlas.size, "height": atlas.size},
        "elements": elements,
        "outliner": outliner,
        "textures": [{
            "path": "", "name": f"{MODEL_NAME}.png", "folder": "block", "namespace": "",
            "id": "0", "particle": False, "render_mode": "default", "visible": True,
            "mode": "bitmap", "saved": False, "uuid": str(uuid.uuid4()), "source": uri,
        }],
        "animations": [],
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False)
    return len(elements)


def main() -> int:
    tree = build_tree()
    atlas = build_atlas(tree)
    img = atlas.image()

    png_path = os.path.join(OUT_DIR, f"{MODEL_NAME}.png")
    img.save(png_path)

    model_path = os.path.join(OUT_DIR, f"{MODEL_NAME}.bbmodel")
    cubes = write_model(model_path, tree, atlas, img)
    print(f"{model_path}  ({cubes} cubes, atlas {atlas.size}x{atlas.size}, "
          f"{len(atlas.rects)} rects)")
    print(f"{png_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
