"""Build 荷枪实弹的现代美军士兵 (a loaded-for-bear modern US soldier) as a
Blockbench project.

    python tools/build_us_soldier.py

Writes ../us_soldier/us_soldier.bbmodel (texture embedded as a data URI) and
../us_soldier/us_soldier.png (the same texture, standalone).

A vanilla-skeleton humanoid (8^3 head, 8x12x4 torso, 4x12x4 arms, 4x12x4 legs,
2 blocks tall) kitted out as a modern US infantryman: camo uniform and helmet
with a cover band + NVG mount, a coyote plate carrier with three rifle-mag
pouches, name/army tapes and a rank patch, a hearing-protection headset with a
boom mic, an assault pack carrying a radio with a whip antenna past the left
shoulder, a belt with a smoke and a frag grenade, a drop-leg pistol holster, a
chest knife-free loadout, kneepads, cargo pockets and coyote combat boots, and
an M4-pattern carbine with a red-dot optic, foregrip, weapon light and a
curved magazine, gripped in both hands and carried diagonally across the chest.

The pose is solved, not eyeballed. Arms are two-bone chains (upper arm 5 units,
elbow to fist 6); given the grip point G and the support-hand point P the script
does closed-form 2-bone IK (elbow placed by a pole vector), converts each
segment's world direction into the rx/rz euler pair that Blockbench applies, and
then derives the rifle group's own rotation R_local = R_total^-1 * R_world so the
carbine lands exactly on the grip axis. verify_pose() rebuilds the whole
transform chain the way Blockbench composes it and asserts the fists and the
muzzle land where intended.

Format facts relied on here were read out of Blockbench 5.2.1's own source
(dist/bundle.js.map -> js/formats/bbmodel.js, js/outliner/outliner.js,
js/outliner/types/group.js), not from memory -- see
skill/references/bbmodel-format.md §12:

  * a 4.5-format outliner node that has a `name` is loaded as a "legacy group"
    and `new Group(node, node.uuid)` merges `origin` + `rotation` off the node;
  * Group.behavior is {movable, rotatable, has_pivot, use_absolute_position},
    so a group's transform is T(origin) . Rz*Ry*Rx . T(-origin) with children
    authored in absolute model space (the parent's origin is subtracted when the
    child is attached), and the rotation order is Format.euler_order = 'ZYX'.

So group rotation is a legitimate 4.5 feature, which is what makes the posed
arms and the slung carbine possible. Per-face uv rects stay upright and
unmirrored seen from outside, v from the top; model_format 'free'; front faces
-Z (north), so the soldier's RIGHT is +X and the rifle is gripped by the right
hand on +X with the muzzle up and to his left.
"""
from __future__ import annotations

import base64
import io
import json
import math
import os
import random
import sys
import uuid
import zlib

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.dont_write_bytecode = True          # keep __pycache__ out of the repo
sys.path.insert(0, HERE)
from bbmodel_kit import (FACES, V, unit, rot_ZYX, euler_ZYX, walk_groups,  # noqa: E402
                         coplanar_conflicts, posed_contacts, face_size,
                         stretch_report)

OUT_DIR = os.path.join(os.path.dirname(HERE), "us_soldier")
os.makedirs(OUT_DIR, exist_ok=True)
MODEL_NAME = "us_soldier"

PLACEHOLDER = (255, 0, 255, 255)

# --- palette ---------------------------------------------------------------
# OCP-ish camouflage: tan base, olive and brown blotches. Gear is coyote brown
# so the nylon reads apart from the uniform at a glance.
CAMO = [(204, 188, 152),   # 0 light tan
        (186, 168, 132),   # 1 base tan
        (150, 140, 100),   # 2 olive blotch
        (120, 96, 70),     # 3 brown blotch
        (92, 74, 56)]      # 4 dark brown
# Helmet cover in the same family but much darker: a light camo helmet on a
# light camo uniform reads as a hat, a dark one reads as a helmet.
HELM = [(122, 118, 96),    # 0 light blotch
        (100, 98, 78),     # 1 base
        (78, 76, 60),      # 2 dark blotch
        (56, 54, 42),      # 3 deep
        (38, 36, 28)]      # 4 rim edge
GEAR = [(158, 132, 96),    # 0 light
        (132, 108, 76),    # 1 base coyote
        (108, 86, 60),     # 2 shade
        (84, 66, 46)]      # 3 dark
WEB = [(96, 78, 54),       # 0 webbing light
       (74, 60, 42),       # 1 base
       (56, 44, 30),       # 2 dark
       (40, 32, 22)]       # 4 near black
SKIN = [(236, 200, 168), (214, 176, 144), (182, 142, 112), (150, 114, 88)]
FACE_PAINT = (92, 88, 62)
HAIR_D = (58, 44, 34)            # buzz cut
GLOVE = [(74, 72, 66), (54, 52, 48), (36, 34, 32)]
BOOT = [(146, 120, 88), (120, 96, 68), (94, 74, 52), (66, 52, 36)]
RUBBER = [(58, 56, 52), (44, 42, 38), (30, 29, 27)]
GUN = [(96, 96, 102), (62, 62, 68), (42, 42, 46), (26, 26, 30)]
POLY = [(58, 58, 62), (44, 44, 48), (30, 30, 34), (18, 18, 22)]
METAL = [(178, 178, 184), (140, 140, 146), (104, 104, 110), (72, 72, 78)]
LENS = (58, 104, 132)
LENS_HI = (156, 210, 232)
OLIVE = [(112, 118, 78), (88, 94, 60), (64, 70, 44)]
FLAG_BLUE = (62, 76, 104)
FLAG_RED = (168, 82, 70)
FLAG_WHITE = (206, 202, 190)
EYE_W = (238, 236, 232)
EYE_D = (54, 44, 38)
MOUTH = (150, 96, 88)


def at(cv, r):
    return cv[r[1]:r[1] + r[3], r[0]:r[0] + r[2]]


def rng_for(key: str) -> random.Random:
    """Deterministic per-rect rng (str hash is salted, crc32 is not)."""
    return random.Random(zlib.crc32(key.encode("utf-8")))


# --- texture painters ------------------------------------------------------
def flat(cv, r, color):
    at(cv, r)[:] = (*color, 255)


def blobs(a, rng, color, n, hmin=2, hmax=4):
    """Squarish blotches -- at 1 px per unit this reads as a camo pattern."""
    h, w = a.shape[:2]
    for _ in range(n):
        cy, cx = rng.randrange(h), rng.randrange(w)
        bh, bw = rng.randrange(hmin, hmax + 1), rng.randrange(hmin, hmax + 1)
        a[cy:cy + bh, cx:cx + bw] = (*color, 255)


def paint_camo(cv, r, key):
    a = at(cv, r)
    rng = rng_for(key)
    a[:] = (*CAMO[1], 255)
    area = r[2] * r[3]
    blobs(a, rng, CAMO[2], max(1, area // 8))
    blobs(a, rng, CAMO[3], max(1, area // 12))
    if area >= 6:
        blobs(a, rng, CAMO[0], 1, 1, 2)


def paint_helmet(cv, r, key):
    """Dark helmet cover. Kept to two tones plus a rim edge on purpose: a 3-D
    band lip, or a light camo top over a banded edge, reads as a hat brim."""
    a = at(cv, r)
    rng = rng_for(key)
    a[:] = (*HELM[1], 255)
    area = r[2] * r[3]
    blobs(a, rng, HELM[2], max(1, area // 9))
    blobs(a, rng, HELM[0], max(1, area // 14), 1, 3)
    a[-1, :] = (*HELM[4], 255)


def apply_webbing(a, rng, base, strap, step=3):
    """MOLLE-ish: horizontal webbing rows with a stitch line every few columns."""
    h, w = a.shape[:2]
    a[:] = (*base, 255)
    for y in range(1, h, step):
        a[y, :] = (*strap, 255)
    for x in range(0, w, 4):
        for y in range(0, h):
            if a[y, x][0] == base[0] and a[y, x][1] == base[1]:
                a[y, x] = (*strap, 255)


def paint_molle(cv, r, key):
    a = at(cv, r)
    apply_webbing(a, rng_for(key), GEAR[1], GEAR[2])


def paint_pack(cv, r, key):
    a = at(cv, r)
    rng = rng_for(key)
    paint_camo(cv, r, key)
    h, w = a.shape[:2]
    for x in range(0, w, 4):            # pack seams
        a[:, x] = (*CAMO[4], 255)


def paint_flap(cv, r, key):
    a = at(cv, r)
    paint_camo(cv, r, key)
    a[0, :] = (*CAMO[4], 255)
    a[-1, :] = (*CAMO[3], 255)


def paint_pouch(cv, r, key):
    """Mag pouch: body, flap with a buckle, shadowed bottom. Rect sizes vary
    (a pouch's sides are 1 px deep), so every row write is guarded."""
    a = at(cv, r)
    h, w = a.shape[:2]
    a[:] = (*GEAR[1], 255)
    a[0, :] = (*GEAR[3], 255)
    if h >= 2:
        a[1, :] = (*GEAR[0], 255)
    if h >= 3:
        a[2, w // 2] = (*METAL[1], 255)     # buckle
    if h >= 2:
        a[h - 1, :] = (*GEAR[2], 255)


def paint_web(cv, r, key):
    a = at(cv, r)
    h, w = a.shape[:2]
    a[:] = (*WEB[1], 255)
    if h >= 2:
        a[0, :] = (*WEB[0], 255)
        a[-1, :] = (*WEB[2], 255)
    if w >= 3:
        a[:, w // 2] = (*WEB[2], 255)


def paint_glove(cv, r, key):
    a = at(cv, r)
    h, w = a.shape[:2]
    a[:] = (*GLOVE[1], 255)
    a[:, 0] = (*GLOVE[2], 255)
    a[:, w - 1] = (*GLOVE[2], 255)
    if h >= 3:
        a[h - 1, :] = (*GLOVE[0], 255)  # cuff
        for x in range(1, w - 1, 2):
            a[h // 2, x] = (*GLOVE[2], 255)   # knuckle creases


def paint_hair(cv, r, key):
    """Very short buzz cut on the back of the head: what shows below the helmet
    is hair, not bare skin."""
    a = at(cv, r)
    rng = rng_for(key)
    a[:] = (*HAIR_D, 255)
    blobs(a, rng, (72, 56, 44), max(1, r[2] * r[3] // 6), 1, 2)


def paint_skin(cv, r, key):
    a = at(cv, r)
    a[:] = (*SKIN[0], 255)
    a[:, 0] = (*SKIN[1], 255)
    a[:, -1] = (*SKIN[1], 255)
    a[-1, :] = (*SKIN[1], 255)


def paint_face(cv, r, key):
    """8x8 head front. Rows 0-2 sit behind the helmet shell, so the brows start
    at row 3: brows, eyes, nose shadow, mouth, stubbled jaw -- with camo face
    paint down both cheeks."""
    a = at(cv, r)
    a[:] = (*SKIN[0], 255)
    a[:, 0] = (*SKIN[1], 255)
    a[:, 7] = (*SKIN[1], 255)
    for y in (0, 1, 2):
        a[y, :] = (*SKIN[1], 255)       # hidden under the helmet anyway
    a[3, 1] = (*SKIN[3], 255); a[3, 2] = (*SKIN[3], 255)
    a[3, 5] = (*SKIN[3], 255); a[3, 6] = (*SKIN[3], 255)   # brows
    a[4, 1] = (*EYE_W, 255); a[4, 2] = (*EYE_D, 255)
    a[4, 5] = (*EYE_D, 255); a[4, 6] = (*EYE_W, 255)
    a[5, 3] = (*SKIN[2], 255); a[5, 4] = (*SKIN[2], 255)   # nose
    a[6, 3] = (*MOUTH, 255); a[6, 4] = (*SKIN[2], 255)     # mouth
    a[7, :] = (*SKIN[2], 255)           # stubble
    a[7, 0] = (*SKIN[3], 255); a[7, 7] = (*SKIN[3], 255)
    for y, x in ((5, 0), (6, 0), (5, 7), (6, 7), (6, 1), (6, 6)):
        a[y, x] = (*FACE_PAINT, 255)    # camo face paint streaks


def paint_boot(cv, r, key):
    a = at(cv, r)
    h, w = a.shape[:2]
    a[:] = (*BOOT[1], 255)
    a[:, 0] = (*BOOT[2], 255)
    a[:, w - 1] = (*BOOT[2], 255)
    a[-1, :] = (*BOOT[3], 255)


def paint_boot_top(cv, r, key):
    """Laces on the boot's top face."""
    a = at(cv, r)
    h, w = a.shape[:2]
    a[:] = (*BOOT[1], 255)
    for y in range(h):
        for x in range(w):
            if (x + y) % 2 == 0 and 0 < x < w - 1:
                a[y, x] = (*BOOT[3], 255)


def paint_sole(cv, r, key):
    a = at(cv, r)
    h, w = a.shape[:2]
    a[:] = (*RUBBER[1], 255)
    a[0, :] = (*RUBBER[0], 255)
    for x in range(0, w, 2):
        a[-1, x] = (*RUBBER[2], 255)    # tread


def paint_rubber(cv, r, key):
    """Kneepads and elbow pads: matte rubber with a strap line."""
    a = at(cv, r)
    h, w = a.shape[:2]
    a[:] = (*RUBBER[1], 255)
    a[0, :] = (*RUBBER[0], 255)
    if h >= 3:
        a[h // 2, :] = (*RUBBER[2], 255)
    a[:, 0] = (*RUBBER[2], 255)
    a[:, w - 1] = (*RUBBER[2], 255)


def paint_gear(cv, r, key):
    a = at(cv, r)
    a[:] = (*GEAR[1], 255)
    a[0, :] = (*GEAR[0], 255)
    a[-1, :] = (*GEAR[2], 255)


def paint_gun(cv, r, key):
    a = at(cv, r)
    h, w = a.shape[:2]
    a[:] = (*GUN[1], 255)
    a[0, :] = (*GUN[0], 255)
    a[-1, :] = (*GUN[3], 255)


def paint_poly(cv, r, key):
    a = at(cv, r)
    a[:] = (*POLY[1], 255)
    a[0, :] = (*POLY[0], 255)
    a[-1, :] = (*POLY[3], 255)


def paint_rail(cv, r, key):
    """Picatinny-ish: notches across a rail strip."""
    a = at(cv, r)
    h, w = a.shape[:2]
    a[:] = (*POLY[1], 255)
    for x in range(0, w, 2):
        a[:, x] = (*POLY[0], 255)


def paint_optic(cv, r, key):
    a = at(cv, r)
    h, w = a.shape[:2]
    a[:] = (*POLY[1], 255)
    a[0, :] = (*POLY[0], 255)
    for x in range(1, w - 1, 3):
        a[h // 2, x] = (*POLY[2], 255)  # adjustment ribs


def paint_lens(cv, r, key):
    a = at(cv, r)
    h, w = a.shape[:2]
    a[:] = (*LENS, 255)
    a[0, :] = (*LENS_HI, 255)
    if w > 1:
        a[:, 0] = (*LENS_HI, 255)


def paint_metal(cv, r, key):
    a = at(cv, r)
    h, w = a.shape[:2]
    a[:] = (*METAL[1], 255)
    a[0, :] = (*METAL[0], 255)
    if h >= 3:
        a[-1, :] = (*METAL[3], 255)


def paint_flag(cv, r, key):
    """Subdued US flag patch on the right sleeve (drawn into whatever rect the
    sleeve face has, so the fragment is not tied to one block size)."""
    a = at(cv, r)
    paint_camo(cv, r, key)
    h, w = a.shape[:2]
    fw, fh = max(3, int(w * 0.75)), max(2, int(h * 0.34))
    x0, y0 = (w - fw) // 2, (h - fh) // 2
    a[max(0, y0 - 1):y0 + fh + 1, max(0, x0 - 1):x0 + fw + 1] = (*CAMO[4], 255)
    flag = np.zeros((fh, fw, 4), np.uint8)
    for i in range(fh):
        flag[i, :] = (*(FLAG_RED if i % 2 == 0 else FLAG_WHITE), 255)
    flag[:max(1, fh // 2), :max(1, fw // 2)] = (*FLAG_BLUE, 255)
    a[y0:y0 + fh, x0:x0 + fw] = flag


def paint_unit(cv, r, key):
    """Unit patch on the left sleeve: a star on a dark shield."""
    a = at(cv, r)
    paint_camo(cv, r, key)
    h, w = a.shape[:2]
    pw, ph = max(2, int(w * 0.7)), max(3, int(h * 0.5))
    x0, y0 = (w - pw) // 2, (h - ph) // 2
    a[max(0, y0 - 1):y0 + ph + 1, max(0, x0 - 1):x0 + pw + 1] = (*CAMO[4], 255)
    a[y0:y0 + ph, x0:x0 + pw] = (*GEAR[3], 255)
    cy, cx = y0 + ph // 2, x0 + pw // 2
    a[cy, x0:x0 + pw] = (*GEAR[0], 255)
    a[y0:y0 + ph, cx] = (*GEAR[0], 255)


def paint_tape(cv, r, key):
    """Name tape: dark band, light letter blobs."""
    a = at(cv, r)
    h, w = a.shape[:2]
    a[:] = (*WEB[3], 255)
    for x in range(0, w, 2):
        a[h // 2, x] = (*FLAG_WHITE, 255)


def paint_tape2(cv, r, key):
    a = at(cv, r)
    h, w = a.shape[:2]
    a[:] = (*WEB[3], 255)
    for x in range(0, w):
        if x % 3 != 2:
            a[h // 2, x] = (*FLAG_WHITE, 255)
    if w >= 2:
        a[h // 2, 0] = (*WEB[3], 255)
        a[h // 2, w - 1] = (*WEB[3], 255)


def paint_rank(cv, r, key):
    """Rank patch: a chevron."""
    a = at(cv, r)
    h, w = a.shape[:2]
    a[:] = (*GEAR[3], 255)
    for i in range(min(h, w)):
        a[i, min(w - 1, i + 1)] = (*METAL[0], 255)
        a[i, max(0, w - 2 - i)] = (*METAL[0], 255)


def paint_grenade(cv, r, key):
    a = at(cv, r)
    h, w = a.shape[:2]
    a[:] = (*OLIVE[1], 255)
    for y in range(h):
        for x in range(w):
            if (x + y) % 2 == 0:
                a[y, x] = (*OLIVE[2], 255)
    a[0, :] = (*OLIVE[0], 255)


def paint_antenna(cv, r, key):
    a = at(cv, r)
    a[:] = (30, 30, 32, 255)
    a[0, 0] = (58, 58, 60, 255)


def paint_radio(cv, r, key):
    a = at(cv, r)
    h, w = a.shape[:2]
    a[:] = (*OLIVE[1], 255)
    a[h - 2:h, 1:max(2, w - 1)] = (60, 70, 58, 255)     # screen
    a[0, :] = (*OLIVE[2], 255)
    for x in range(0, w, 3):
        a[1, x] = (*METAL[1], 255)                       # knobs


def paint_holster(cv, r, key):
    a = at(cv, r)
    h, w = a.shape[:2]
    a[:] = (*POLY[1], 255)
    a[0, :] = (*POLY[0], 255)
    a[-1, :] = (*POLY[3], 255)
    if w >= 3:
        a[:, w // 2] = (*POLY[2], 255)


def paint_canteen(cv, r, key):
    a = at(cv, r)
    a[:] = (*OLIVE[1], 255)
    a[0, :] = (*OLIVE[0], 255)
    a[-1, :] = (*OLIVE[2], 255)


PAINTERS = {
    "camo": paint_camo, "helmet": paint_helmet, "molle": paint_molle,
    "pouch": paint_pouch, "web": paint_web, "pack": paint_pack,
    "flap": paint_flap, "glove": paint_glove, "skin": paint_skin,
    "face": paint_face, "hair": paint_hair, "boot": paint_boot,
    "boot_top": paint_boot_top,
    "sole": paint_sole, "rubber": paint_rubber, "gear": paint_gear,
    "gun": paint_gun, "poly": paint_poly, "rail": paint_rail,
    "optic": paint_optic, "lens": paint_lens, "metal": paint_metal,
    "flag": paint_flag, "unit": paint_unit, "tape": paint_tape,
    "tape2": paint_tape2, "rank": paint_rank, "grenade": paint_grenade,
    "antenna": paint_antenna, "radio": paint_radio, "holster": paint_holster,
    "canteen": paint_canteen,
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


def bx(sx, x0, x1, y0, y1, z0, z1):
    """Mirror a box across the x=0 plane when sx < 0; returns (from, to)."""
    a, b = sx * x0, sx * x1
    return (min(a, b), y0, z0), (max(a, b), y1, z1)


def aim_down(d):
    """Euler pair (rx, 0, rz) that sends the rest direction (0,-1,0) -- a limb
    hanging from its pivot -- onto unit direction d."""
    d = unit(d)
    return (math.degrees(math.asin(max(-1.0, min(1.0, -d[2])))), 0.0,
            math.degrees(math.atan2(d[0], -d[1])))


def aim_forward(d):
    """Euler triple (rx, ry, 0) sending the rest direction (0,0,-1) -- a barrel
    pointing north -- onto unit direction d, with the minimum roll."""
    d = unit(d)
    return (math.degrees(math.asin(max(-1.0, min(1.0, d[1])))),
            math.degrees(math.atan2(-d[0], -d[2])), 0.0)


def solve_2bone(S, H, a, b, pole):
    """Closed-form 2-bone IK: elbow E with |E-S| = a, |H-E| = b, bulging toward
    the pole vector. Returns (E, unit(E-S), unit(H-E))."""
    u = H - S
    d = float(np.linalg.norm(u))
    if d > a + b - 1e-9:
        raise ValueError(f"target {d:.3f} out of reach ({a}+{b})")
    u = u / d
    cosA = (a * a + d * d - b * b) / (2 * a * d)
    A = math.acos(max(-1.0, min(1.0, cosA)))
    v = pole - float(np.dot(pole, u)) * u
    v = unit(v)
    E = S + a * (math.cos(A) * u + math.sin(A) * v)
    return E, unit(E - S), unit(H - E)


def arm_chain(S, E_rest, F_rest, target, pole, a, b):
    """Solve one arm: returns (upper_rot, fore_rot, E) where the rotations are
    the degrees triplets Blockbench applies, and asserts the fist lands on
    target when the chain is composed the way Blockbench composes it."""
    E, d1, d2 = solve_2bone(S, target, a, b, pole)
    r1 = aim_down(d1)
    d2_local = rot_ZYX(*r1).T @ d2
    r2 = aim_down(d2_local)
    got = rot_ZYX(*r1) @ (rot_ZYX(*r2) @ (F_rest - E_rest) + E_rest - S) + S
    err = float(np.linalg.norm(got - target))
    if err > 1e-6:
        raise AssertionError(f"arm chain misses its target by {err:.6f}")
    return r1, r2, E


# --- the model -------------------------------------------------------------
# Rest skeleton, ground y=0, centred on x=z=0, front = -Z (north). The arms
# hang half a unit clear of the plate carrier's side flaps (x 4.5), so the
# vest and the sleeves are flush instead of interpenetrating.
SHOULDER_R, SHOULDER_L = V(6.8, 22.5, 0), V(-6.8, 22.5, 0)
ELBOW_REST_R, ELBOW_REST_L = V(6.8, 17.5, 0), V(-6.8, 17.5, 0)
FIST_REST_R, FIST_REST_L = V(6.8, 11.5, 0), V(-6.8, 11.5, 0)
A_UPPER, B_FORE = 5.0, 6.0

GRIP = V(2.5, 15.6, -5.3)                 # right fist = pistol grip
# muzzle up and to his left at about 41 deg: the muzzle clears the head and
# ends beside the left shoulder, so neither the face nor the optic is hidden
MUZZLE_DIR = unit(V(-6.0, 5.4, -1.3))
SUPPORT = GRIP + 5.6 * MUZZLE_DIR         # left fist = handguard
POLE_R = V(1.0, -1.2, 0.9)                # right elbow out-back-down
POLE_L = V(-1.0, -1.2, 0.9)               # left elbow out-back-down

# Carbine layout, local frame: origin at the grip, -Z toward the muzzle,
# +Y the top of the receiver. (from, to, material-map)
RIFLE_PARTS = [
    ("recv", (-1, 0.3, -5), (1, 3.2, 3),
     FM(sides="gun", up="rail", down="gun", north="gun", south="gun")),
    ("recv_rail", (-0.7, 3.2, -5), (0.7, 3.7, 2.4), FM(all="rail")),
    ("handguard", (-1, 0.4, -10), (1, 2.6, -5),
     FM(sides="poly", up="rail", down="poly", north="poly", south="poly")),
    ("hg_rail", (-0.7, 2.6, -10), (0.7, 3.0, -5), FM(all="rail")),
    ("foregrip", (-0.6, -1.8, -8), (0.6, 0.4, -6.8), FM(all="poly")),
    ("light", (-1.5, 0.7, -8.6), (-1, 1.8, -6.6),
     FM(all="metal", north="lens")),
    ("barrel", (-0.5, 1.0, -12), (0.5, 2.0, -10), FM(all="gun")),
    ("flash_hider", (-1.0, 0.5, -14), (1.0, 2.5, -12), FM(all="gun")),
    ("front_sight", (-0.5, 2.0, -12.5), (0.5, 4.0, -11.5), FM(all="gun")),
    ("optic", (-0.7, 3.7, -3.4), (0.7, 6.1, -1.6),
     FM(all="optic", north="lens")),
    ("optic_knob", (0.7, 5.0, -2.8), (1.1, 5.6, -2.2), FM(all="optic")),
    ("rear_sight", (-0.5, 3.7, 0.6), (0.5, 4.5, 1.4), FM(all="poly")),
    ("charging_handle", (-0.5, 3.0, 3), (0.5, 3.5, 4.2), FM(all="gun")),
    ("pistol_grip", (-0.6, -2.6, 0.6), (0.6, 0.3, 2.4), FM(all="poly")),
    ("trigger_guard", (-0.5, -1.2, -0.6), (0.5, 0.3, 0.6), FM(all="poly")),
    ("mag_upper", (-0.5, -3.0, -3.2), (0.5, -0.3, -1.2), FM(all="poly")),
    ("mag_lower", (-0.5, -5.6, -3.6), (0.5, -3.0, -1.6), FM(all="poly")),
    ("stock", (-0.9, 0.4, 2.6), (0.9, 2.6, 6.4), FM(all="poly")),
    ("cheek_rest", (-0.7, 2.6, 3.4), (0.7, 3.3, 5.8), FM(all="poly")),
    ("butt_pad", (-1.0, 0.2, 6.4), (1.0, 2.8, 7.4), FM(all="rubber")),
]


def build_tree():
    # pose first: the arms are solved onto the carbine, the carbine's own
    # rotation is then derived from the chain so it lands on the grip axis.
    up_rot_R, fore_rot_R, elbow_R = arm_chain(
        SHOULDER_R, ELBOW_REST_R, FIST_REST_R, GRIP, POLE_R, A_UPPER, B_FORE)
    up_rot_L, fore_rot_L, elbow_L = arm_chain(
        SHOULDER_L, ELBOW_REST_L, FIST_REST_L, SUPPORT, POLE_L, A_UPPER, B_FORE)

    R_total = rot_ZYX(*up_rot_R) @ rot_ZYX(*fore_rot_R)
    R_world = rot_ZYX(*aim_forward(MUZZLE_DIR))
    R_local = R_total.T @ R_world
    rifle_rot = euler_ZYX(R_local)

    def rifle_cube(name, l_from, l_to, facemap):
        """Author the carbine around the fist's rest centre using the local
        offsets as-is: the group carries the rotation that cancels the arm
        chain, so R_total @ R_local == R_world and the offset from the pivot
        passes through unchanged."""
        return cube(name,
                    tuple(FIST_REST_R + V(*l_from)),
                    tuple(FIST_REST_R + V(*l_to)), facemap)

    rifle = group("carbine", [rifle_cube(n, a, b, fm) for n, a, b, fm in RIFLE_PARTS],
                  origin=tuple(FIST_REST_R), rotation=rifle_rot)

    # --- head: helmet, headset, face ---------------------------------------
    head = group("head", origin=(0, 24, 0), cubes=[
        cube("head", (-4, 24, -4), (4, 32, 4),
             FM(sides="skin", up="skin", down="skin", north="face",
                south="hair")),
        # ACH-style helmet: a tight 2-step shell that hugs the head (0.5
        # overhang, no brim), cut high over the ears and running lower at the
        # back -- a 3-step dome or a banded lip reads as a hat instead.
        cube("helmet_shell", (-4.5, 29, -4.5), (4.5, 32.4, 4.5), FM(all="helmet")),
        cube("helmet_back", (-4.5, 26.5, 2.8), (4.5, 29, 4.5), FM(all="helmet")),
        cube("helmet_crown", (-4, 32.4, -4), (4, 33.4, 4), FM(all="helmet")),
        cube("nvg_mount", (-1.2, 30.4, -5.2), (1.2, 31.5, -3.6), FM(all="metal")),
        cube("earcup_r", (4, 26, -1.5), (5, 29, 1.5), FM(all="rubber")),
        cube("earcup_l", (-5, 26, -1.5), (-4, 29, 1.5), FM(all="rubber")),
        cube("mic_arm", (-4.9, 26.5, -4.3), (-4.1, 27.3, -1.4), FM(all="rubber")),
        cube("mic_tip", (-4.1, 26.2, -4.9), (-3.3, 27.0, -4.2), FM(all="poly")),
    ])

    # --- arms: upper arm group + forearm child carrying the fist ------------
    def arm(side, sx, up_rot, fore_rot):
        # the flag patch rides the shooting arm's sleeve, the unit patch the
        # support arm's -- painted, so no extra geometry.
        sleeve = FM(all="camo", east="flag") if sx > 0 else \
            FM(all="camo", west="unit")
        upper = group(f"{side}_arm",
                      origin=tuple(SHOULDER_R if sx > 0 else SHOULDER_L),
                      rotation=up_rot, cubes=[
            cube(f"{side}_upper_arm", *bx(sx, 4.8, 8.8, 17.5, 23.5, -2, 2),
                 sleeve),
            cube(f"{side}_shoulder_cap", *bx(sx, 4.5, 9.5, 22.6, 24.5, -2.5, 2.5),
                 FM(all="molle")),
            cube(f"{side}_elbow_pad", *bx(sx, 4.5, 9.5, 16, 19, -2.5, 2.5),
                 FM(all="rubber")),
        ])
        fore = group(f"{side}_forearm",
                     origin=tuple(ELBOW_REST_R if sx > 0 else ELBOW_REST_L),
                     rotation=fore_rot, cubes=[
            cube(f"{side}_forearm", *bx(sx, 5.3, 8.3, 13, 18, -1.5, 1.5),
                 FM(all="skin")),
            cube(f"{side}_fist", *bx(sx, 4.3, 9.3, 10, 13, -2.5, 2.5),
                 FM(all="glove")),
        ])
        if sx < 0:
            fore["cubes"].append(
                cube("watch", *bx(sx, 4.8, 8.8, 14, 15, -2, 2), FM(all="poly")))
        if sx > 0:
            fore["children"].append(rifle)
        upper["children"].append(fore)
        return upper

    body = group("body", origin=(0, 12, 0), cubes=[
        cube("hips", (-4.5, 11.5, -2.5), (4.5, 15, 2.5), FM(all="camo")),
        cube("torso", (-4, 12, -2), (4, 24, 2), FM(all="camo")),
        # plate carrier: front/back plates, cummerbund, shoulder straps
        cube("plate_front", (-4.5, 15.5, -3.5), (4.5, 22.5, -1.5), FM(all="molle")),
        cube("plate_back", (-4.5, 15.5, 1.5), (4.5, 22.5, 3.5), FM(all="molle")),
        cube("cummerbund_r", (3.6, 15.4, -3), (4.6, 19, 3), FM(all="molle")),
        cube("cummerbund_l", (-4.6, 15.4, -3), (-3.6, 19, 3), FM(all="molle")),
        # side utility pouches on the cummerbund: the rifle covers the chest
        # pouches, these are what still reads from the front
        cube("sidepouch_r", (4.6, 15.5, 2), (5.6, 18.5, 5), FM(all="pouch")),
        cube("sidepouch_l", (-5.6, 15.5, 2), (-4.6, 18.5, 5), FM(all="pouch")),
        cube("strap_r", (2.5, 22, -3.5), (4.5, 24, 3.5), FM(all="molle")),
        cube("strap_l", (-4.5, 22, -3.5), (-2.5, 24, 3.5), FM(all="molle")),
        # three rifle-mag pouches
        cube("magpouch_r", (2, 17.5, -4.6), (4, 20.5, -3.5), FM(all="pouch")),
        cube("magpouch_c", (-1, 17.5, -4.6), (1, 20.5, -3.5), FM(all="pouch")),
        cube("magpouch_l", (-4, 17.5, -4.6), (-2, 20.5, -3.5), FM(all="pouch")),
        # name tape, army tape, rank
        cube("tape_name", (1.5, 21, -4.5), (4.5, 22, -3.5), FM(all="tape")),
        cube("tape_army", (-4.5, 21, -4.5), (-1.5, 22, -3.5), FM(all="tape2")),
        cube("rank", (-1, 20.5, -4.5), (1, 22.5, -3.5), FM(all="rank")),
        # belt, buckle, grenades
        cube("belt", (-4.8, 14.5, -2.8), (4.8, 16.5, 2.8), FM(all="web")),
        cube("belt_buckle", (-1, 15, -3.8), (1, 16, -2.8), FM(all="metal")),
        cube("frag", (5, 11, -2), (6, 14, -1), FM(all="grenade")),
        cube("frag_cap", (5, 14, -2), (6, 15, -1), FM(all="metal")),
        cube("smoke", (-6, 11, -2), (-5, 15, -1), FM(all="grenade")),
        cube("smoke_cap", (-6, 15, -2), (-5, 16, -1), FM(all="metal")),
        # assault pack with the radio and its whip antenna
        cube("pack", (-3, 14, 1.8), (3, 21, 5.6), FM(all="gear")),
        cube("pack_flap", (-3.2, 19.5, 1.6), (3.2, 21.4, 5.8), FM(all="gear")),
        cube("pack_strap_r", (1.4, 14.5, 5.6), (2.2, 19.5, 6), FM(all="web")),
        cube("pack_strap_l", (-2.2, 14.5, 5.6), (-1.4, 19.5, 6), FM(all="web")),
        cube("pack_buckle", (-3, 16.5, 5.8), (3, 17.5, 6.2), FM(all="web")),
        cube("radio", (-4.1, 16, 2.8), (-3, 20, 5.4), FM(all="radio")),
        cube("antenna", (-3.9, 20, 4), (-3.2, 25.5, 4.7), FM(all="antenna")),
        cube("canteen", (2, 12.5, 2.8), (4.8, 15.5, 4.6), FM(all="canteen")),
    ], children=[head, arm("right", 1, up_rot_R, fore_rot_R),
                 arm("left", -1, up_rot_L, fore_rot_L)])

    legs = []
    for name, sx in (("right", 1), ("left", -1)):
        # legs at |x| 0.75..4.75 leave a 1.5-unit gap, which is what lets the
        # bloused cuffs and the soles be proud on both sides without the two
        # legs' coplanar faces landing on each other.
        cubes = [
            cube(f"{name}_leg", *bx(sx, 0.75, 4.75, 4, 12, -2, 2), FM(all="camo")),
            cube(f"{name}_cuff", *bx(sx, 0.25, 5.75, 3, 5, -3, 3),
                 FM(all="camo")),
            cube(f"{name}_boot", *bx(sx, 0.75, 5.25, 1, 4, -3.5, 2.5),
                 FM(sides="boot", up="boot_top", down="boot")),
            cube(f"{name}_sole", *bx(sx, 0.75, 5.75, 0, 1, -4, 3),
                 FM(all="sole")),
            cube(f"{name}_kneepad", *bx(sx, 0.25, 5.25, 5.5, 8.5, -3.5, -1.5),
                 FM(all="rubber")),
        ]
        if sx > 0:      # drop-leg holster on the right thigh
            cubes += [
                cube("holster", *bx(sx, 4.75, 6.75, 5.5, 11, -1.5, 1.5),
                     FM(all="holster")),
                cube("pistol_in_holster", *bx(sx, 5, 6, 11, 13, -1, 1),
                     FM(all="poly")),
                cube("leg_strap_a", *bx(sx, 0.25, 5.25, 8.5, 9.5, -2.6, 2.6),
                     FM(all="web")),
                cube("leg_strap_b", *bx(sx, 0.25, 5.25, 10.5, 11.5, -2.6, 2.6),
                     FM(all="web")),
            ]
        else:           # cargo pocket on the left thigh
            cubes.append(
                cube("cargo_pocket", *bx(sx, 4.75, 5.75, 6.5, 10.5, -1.5, 1.5),
                     FM(all="pouch")))
        legs.append(group(f"{name}_leg_grp", cubes=cubes,
                          origin=(sx * 2.75, 12, 0)))

    tree = {"name": MODEL_NAME, "origin": (0, 0, 0), "cubes": [],
            "children": [body, *legs]}
    return tree, {"G": GRIP, "P": SUPPORT, "muzzle_dir": MUZZLE_DIR,
                  "elbow_r": elbow_R, "elbow_l": elbow_L,
                  "rifle_rot": rifle_rot, "R_world": R_world,
                  "up_rot_R": up_rot_R, "fore_rot_R": fore_rot_R}


# --- self checks -----------------------------------------------------------
def verify_pose(tree, info):
    """Rebuild the transform chain as Blockbench composes it (rotations about
    each node's origin, children in absolute model space) and check the hands
    and the carbine end up where the design says."""
    pose = {}
    for path, c, R, t in walk_groups(tree):
        pose[path] = (R, t, c)
    checks = []
    root = tree["name"]

    def chain_point(path, p):
        R, t, _ = pose[path]
        return R @ p + t

    # fists: the glove cube centre must land on the grip / handguard
    for path, target in ((f"/{root}/body/right_arm/right_forearm/right_fist", info["G"]),
                         (f"/{root}/body/left_arm/left_forearm/left_fist", info["P"])):
        _, _, c = pose[path]
        centre = (V(*c["from"]) + V(*c["to"])) / 2
        err = float(np.linalg.norm(chain_point(path, centre) - target))
        checks.append((f"{path.split('/')[-1]} on target", err))
    # carbine: the flash hider's centre must sit on the grip axis, and the
    # carbine's top must be the most-upright direction around the bore
    path, m_from, m_to = None, None, None
    for p, c, _R, _t in walk_groups(tree):
        if c["name"] == "flash_hider":
            path, m_from, m_to = p, V(*c["from"]), V(*c["to"])
    if path is None:
        raise AssertionError("carbine not found in the tree")
    got = chain_point(path, (m_from + m_to) / 2)
    want = info["G"] + info["R_world"] @ V(0, 1.5, -13.0)
    checks.append(("muzzle on the grip axis", float(np.linalg.norm(got - want))))
    up_now = pose[path][0] @ V(0, 1, 0)
    want_up = info["R_world"] @ V(0, 1, 0)
    checks.append(("carbine roll", float(np.linalg.norm(up_now - want_up))))

    bad = [(n, e) for n, e in checks if e > 1e-6]
    for n, e in checks:
        print(f"  pose: {n:<26} err {e:.2e}")
    if bad:
        raise AssertionError(f"pose checks failed: {bad}")
    return pose


def collect_rects(tree):
    seen = {}
    for path, c, _rot, _origin in walk_groups(tree):
        for face, mat in c["faces"].items():
            w, h = face_size(face, c["from"], c["to"])
            seen[(mat, w, h)] = True
    return sorted(seen, key=lambda k: (-k[2], -k[1]))


def build_atlas(tree) -> Atlas:
    keys = collect_rects(tree)
    for size in (128, 160, 192, 224, 256):
        atlas = Atlas(size)
        try:
            for mat, w, h in keys:
                atlas.alloc((mat, w, h), w, h)
        except RuntimeError:
            continue
        atlas.extend_edges()
        return atlas
    raise SystemExit("no atlas size fits the model")


def check_painted(atlas: Atlas) -> list[str]:
    ph = np.array(PLACEHOLDER, np.uint8)
    return [str(key) for key, (x, y, w, h) in atlas.rects.items()
            if np.any(np.all(atlas.cv[y:y + h, x:x + w] == ph, axis=-1))]


# --- writer ----------------------------------------------------------------
def write_model(path: str, tree, atlas: Atlas, texture: Image.Image) -> int:
    elements: list[dict] = []

    def emit_cube(c: dict) -> str:
        el = {
            "name": c["name"],
            "from": [float(v) for v in c["from"]],
            "to": [float(v) for v in c["to"]],
            "origin": [float(v) for v in c["origin"]] if c.get("origin") else [0.0, 0.0, 0.0],
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
        out = {"name": node["name"],
               "origin": [float(v) for v in node["origin"]],
               "uuid": str(uuid.uuid4()),
               "children": children}
        if node.get("rotation"):
            out["rotation"] = [float(v) for v in node["rotation"]]
        return out

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
            "path": "", "name": f"{MODEL_NAME}.png", "folder": "entity",
            "namespace": "", "id": "0", "particle": False,
            "render_mode": "default", "visible": True, "mode": "bitmap",
            "saved": False, "uuid": str(uuid.uuid4()), "source": uri,
        }],
        "animations": [],
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False)
    return len(elements)


def main() -> int:
    tree, info = build_tree()

    print("pose:")
    verify_pose(tree, info)

    bad = coplanar_conflicts(tree)
    if bad:
        for pi, pj, axis, tag, coord, ov in bad[:20]:
            print(f"  z-fight risk: {pi} / {pj} on {axis}={coord:.3f} ({tag})")
        raise SystemExit(f"{len(bad)} coplanar same-facing overlaps")

    contacts = posed_contacts(tree)
    if contacts:
        print("posed AABB contacts involving rotated chains (visual triage):")
        for pi, pj, vol in sorted(contacts, key=lambda r: -r[2])[:12]:
            print(f"  {vol:6.2f}  {pi.split('/')[-1]:<18} {pj.split('/')[-1]}")

    stretched = stretch_report(tree)
    if stretched:
        print("stretched faces (rounded uv rect vs true size):")
        for path, face, want, got in stretched:
            print(f"  {path}/{face}: {want} -> {got} px")

    atlas = build_atlas(tree)
    unpainted = check_painted(atlas)
    if unpainted:
        raise SystemExit(f"rects left unpainted: {unpainted}")

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
