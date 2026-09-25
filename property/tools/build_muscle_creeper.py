"""Build the 肌肉苦力怕 (muscle creeper) as a Blockbench project.

    python tools/build_muscle_creeper.py

Writes ../muscle_creeper/muscle_creeper.bbmodel (texture embedded as a data URI) and
../muscle_creeper/muscle_creeper.png (the same texture, standalone).

A vanilla creeper rebuilt with a powerlifter's proportions, in vanilla style:
same iconic 8x8 head with the classic face, same mottled four-shade green, but
with a broad chest (14 wide, v-tapered down to the vanilla 8-wide waist), thick
legs, and the one thing a "buff creeper" must have that a vanilla creeper lacks
-- a pair of heavy arms hanging off the shoulders.

Vanilla reference proportions (1 unit = 1/16 block, ground y=0): legs 4x6x4 at
x=+-2/z=+-4, body 8x12x4 at y 6..18, head 8^3 at y 18..26 -- 26 tall total. This
model stands 30 tall (1.875 blocks): shoulders reach +-7, arms to +-13.

The official creeper.png could not be fetched (network blocked), so the palette
is hand-picked to match the vanilla look: four mottled greens + pure black
features, chunky 2px camo blocks like the real texture.

Format conventions are the ones measured out of Blockbench's source (see
build_bawanghua_pot.py): per-face uv rects upright and unmirrored seen from
outside, v from the top; model_format 'free'; front of the mob faces -Z (north)
so the face is the first thing the default camera sees.
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
OUT_DIR = os.path.join(os.path.dirname(HERE), "muscle_creeper")
os.makedirs(OUT_DIR, exist_ok=True)
MODEL_NAME = "muscle_creeper"

FACES = ("north", "east", "south", "west", "up", "down")

# --- palette ---------------------------------------------------------------
# Vanilla-creeper greens: a light shoulder highlight, the mottled base, a shade
# and a deep shadow. Features are pure black, as on the real mob.
GREEN = [
    (162, 214, 106),  # 0 light
    (112, 184, 82),   # 1 base
    (76, 148, 60),    # 2 shade
    (40, 108, 42),    # 3 dark
]
BLACK = (0, 0, 0)
PLACEHOLDER = (255, 0, 255, 255)


def shade(ramp, i):
    return ramp[max(0, min(len(ramp) - 1, i))]


def at(cv, r):
    return cv[r[1]:r[1] + r[3], r[0]:r[0] + r[2]]


def paint(cv, r, color):
    at(cv, r)[:] = (*color, 255)


class Atlas:
    """Shelf packer for the per-face uv rects, plus an edge-extend pass.

    The head rects are placed manually at the vanilla head-box positions (a
    gapless 32x16 region, exactly where the vanilla 64x32 texture puts them),
    so `extend_edges` only bleeds into placeholder pixels -- bleeding into a
    neighbour would corrupt a gapless region's edge column.
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
# Head rects sit at the vanilla head-box coordinates so the face lands where
# everyone expects it on the atlas; everything else is shelf-packed.
HEAD_RECTS = [
    ("head_up", 8, 0, 8, 8), ("head_down", 16, 0, 8, 8),
    ("head_east", 0, 8, 8, 8), ("head_front", 8, 8, 8, 8),
    ("head_west", 16, 8, 8, 8), ("head_south", 24, 8, 8, 8),
]
PACKED_RECTS = [
    ("chest_front", 14, 9), ("chest_back", 14, 9), ("chest_side", 6, 9),
    ("chest_top", 14, 6), ("chest_bottom", 14, 6),
    ("waist_front", 8, 6), ("waist_back", 8, 6), ("waist_side", 4, 6),
    ("waist_top", 8, 4), ("waist_bottom", 8, 4),
    ("arm_front", 6, 9), ("arm_back", 6, 9), ("arm_side", 6, 9),
    ("arm_top", 6, 6), ("arm_bottom", 6, 6),
    ("forearm", 5, 5),
    ("leg_front", 5, 7), ("leg_back", 5, 7), ("leg_side", 5, 7),
    ("leg_top", 5, 5), ("leg_bottom", 5, 5),
]


def mottle(cv, r, rng, weights=(1, 5, 3, 1)):
    """Chunky camo: 2px blocks of green + 1px speckle, the vanilla creeper way."""
    x0, y0, w, h = r
    for by in range(0, h, 2):
        for bx in range(0, w, 2):
            bw, bh = min(2, w - bx), min(2, h - by)
            idx = rng.choices((0, 1, 2, 3), weights)[0]
            cv[y0 + by:y0 + by + bh, x0 + bx:x0 + bx + bw] = (*GREEN[idx], 255)
    for _ in range(max(1, (w * h) // 8)):
        px, py = rng.randrange(w), rng.randrange(h)
        cv[y0 + py, x0 + px] = (*GREEN[rng.choice((0, 2, 3))], 255)


def paint_face(cv, r):
    """The iconic creeper face, pure black on camo: 2x2 eyes, dropping mouth."""
    f = at(cv, r)
    f[1:3, 1:3] = (*BLACK, 255)
    f[1:3, 5:7] = (*BLACK, 255)
    f[3, 3:5] = (*BLACK, 255)
    f[4:6, 2:6] = (*BLACK, 255)
    f[6, 2] = (*BLACK, 255)
    f[6, 5] = (*BLACK, 255)


def paint_texture(atlas: Atlas) -> None:
    cv, r = atlas.cv, atlas.rects
    rng = random.Random(20260924)

    # --- head: camo everywhere, features on the north rect -------------------
    for name in ("head_up", "head_down", "head_east", "head_west", "head_south"):
        mottle(cv, r[name], rng)
    mottle(cv, r["head_front"], rng)
    paint_face(cv, r["head_front"])

    # --- chest: pecs with a centre crease, under-pec shadow, ab grid ---------
    # The front face is 14x9; rows 0-4 are the pec shelf, rows 5-8 the abs.
    cf = at(cv, r["chest_front"])
    mottle(cv, r["chest_front"], rng)
    cf[0, :] = (*GREEN[0], 255)            # light across the collar
    cf[1:5, 6:8] = (*GREEN[3], 255)        # pec crease, dark and hard
    cf[4, 1:6] = (*GREEN[2], 255)          # under-pec shadow
    cf[4, 8:13] = (*GREEN[2], 255)
    cf[:, 0] = (*GREEN[2], 255)            # side shading rounds the torso
    cf[:, 13] = (*GREEN[2], 255)
    cf[5:9, 6:8] = (*GREEN[2], 255)        # linea alba, softer than the crease
    cf[6, 1:6] = (*GREEN[2], 255)          # ab crease row
    cf[6, 8:13] = (*GREEN[2], 255)
    cf[8, :] = (*GREEN[3], 255)

    cb = at(cv, r["chest_back"])
    mottle(cv, r["chest_back"], rng)
    cb[:, 6:8] = (*GREEN[2], 255)          # spine groove
    cb[1:4, 2:5] = (*GREEN[0], 255)        # scapula highlights
    cb[1:4, 9:12] = (*GREEN[0], 255)
    cb[8, :] = (*GREEN[3], 255)

    ct = at(cv, r["chest_top"])
    mottle(cv, r["chest_top"], rng)
    ct[1:5, 2:12] = (*GREEN[0], 255)       # traps catching the light
    ct[0, :] = (*GREEN[3], 255)
    ct[5, :] = (*GREEN[2], 255)

    mottle(cv, r["chest_side"], rng)
    at(cv, r["chest_side"])[8, :] = (*GREEN[3], 255)
    mottle(cv, r["chest_bottom"], rng, weights=(0, 1, 3, 5))

    # --- waist: the vanilla-width trunk, abs carved into it ------------------
    wf = at(cv, r["waist_front"])
    mottle(cv, r["waist_front"], rng)
    wf[:, 3:5] = (*GREEN[2], 255)          # centre line continues the crease
    wf[2, :] = (*GREEN[2], 255)            # one ab crease
    wf[:, 0] = (*GREEN[3], 255)
    wf[:, 7] = (*GREEN[3], 255)
    wf[5, :] = (*GREEN[3], 255)

    mottle(cv, r["waist_back"], rng)
    at(cv, r["waist_back"])[5, :] = (*GREEN[3], 255)
    mottle(cv, r["waist_side"], rng)
    at(cv, r["waist_side"])[5, :] = (*GREEN[3], 255)
    mottle(cv, r["waist_top"], rng)
    mottle(cv, r["waist_bottom"], rng, weights=(0, 0, 2, 5))

    # --- arms: deltoid light, bicep bulge, a hard crease under it ------------
    for name in ("arm_front", "arm_back", "arm_side"):
        a = at(cv, r[name])
        mottle(cv, r[name], rng)
        a[0, :] = (*GREEN[0], 255)         # deltoid top
        a[2:5, 1:5] = (*GREEN[0], 255)     # bicep bulge
        a[2, 1:5] = (*GREEN[1], 255)       # soften the bulge's top edge
        a[5, :] = (*GREEN[3], 255)         # the crease that says "muscle"
        a[8, :] = (*GREEN[2], 255)
    at_ = at(cv, r["arm_top"])
    mottle(cv, r["arm_top"], rng)
    at_[1:5, 1:5] = (*GREEN[0], 255)       # shoulder cap
    mottle(cv, r["arm_bottom"], rng, weights=(0, 1, 3, 5))
    fa = at(cv, r["forearm"])
    mottle(cv, r["forearm"], rng)
    fa[0, :] = (*GREEN[2], 255)            # shadow under the bicep
    fa[4, :] = (*GREEN[3], 255)            # knuckle line

    # --- legs: plain camo, dark footfall edge --------------------------------
    for name in ("leg_front", "leg_back", "leg_side", "leg_top"):
        mottle(cv, r[name], rng)
        at(cv, r[name])[r[name][3] - 1, :] = (*GREEN[2], 255)
    mottle(cv, r["leg_bottom"], rng, weights=(0, 0, 2, 5))


# --- geometry --------------------------------------------------------------
# Units of 1/16 block, ground y=0, centred on x=z=0, facing -Z (north).
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
    body = {"name": "body", "origin": (0, 13, 0), "cubes": [
        # Broad chest over the vanilla-width waist: the v-taper is the whole gag.
        cube("chest", (-7, 13, -3), (7, 22, 3), (0, 13, 0),
             faces(sides("chest_side"), up="chest_top", down="chest_bottom",
                   north="chest_front", south="chest_back")),
        cube("waist", (-4, 7, -2), (4, 13, 2), (0, 13, 0),
             faces(sides("waist_side"), up="waist_top", down="waist_bottom",
                   north="waist_front", south="waist_back")),
    ], "children": [
        {"name": "head", "origin": (0, 22, 0), "cubes": [
            cube("head", (-4, 22, -4), (4, 30, 4), (0, 22, 0),
                 faces({}, north="head_front", south="head_south", east="head_east",
                       west="head_west", up="head_up", down="head_down")),
        ]},
        {"name": "right_arm", "origin": (-10, 21, 0), "cubes": [
            cube("right_upper_arm", (-13, 13, -3), (-7, 22, 3), (-10, 21, 0),
                 faces(sides("arm_side"), up="arm_top", down="arm_bottom",
                       north="arm_front", south="arm_back")),
            cube("right_forearm", (-12.5, 8, -2.5), (-7.5, 13, 2.5), (-10, 13, 0),
                 faces(all_faces("forearm"))),
        ]},
        {"name": "left_arm", "origin": (10, 21, 0), "cubes": [
            cube("left_upper_arm", (7, 13, -3), (13, 22, 3), (10, 21, 0),
                 faces(sides("arm_side"), up="arm_top", down="arm_bottom",
                       north="arm_front", south="arm_back")),
            cube("left_forearm", (7.5, 8, -2.5), (12.5, 13, 2.5), (10, 13, 0),
                 faces(all_faces("forearm"))),
        ]},
    ]}

    leg_facemap = faces(sides("leg_side"), up="leg_top", down="leg_bottom",
                        north="leg_front", south="leg_back")
    legs = []
    for name, cx, cz in (("right_front_leg", -3.5, -4.5), ("left_front_leg", 3.5, -4.5),
                         ("right_hind_leg", -3.5, 4.5), ("left_hind_leg", 3.5, 4.5)):
        legs.append({"name": name, "origin": (cx, 7, cz), "cubes": [
            cube(name, (cx - 2.5, 0, cz - 2.5), (cx + 2.5, 7, cz + 2.5),
                 (cx, 7, cz), leg_facemap),
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
