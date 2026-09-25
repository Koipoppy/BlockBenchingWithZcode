"""Build the 佛塔 (Buddhist pagoda) model as a Blockbench project.

    python tools/build_pagoda.py

Writes ../pagoda/pagoda.bbmodel (texture embedded as a data URI) and ../pagoda/pagoda.png
(the same texture, standalone, for a resource pack).

Three tiers of plaster-and-timber body under stepped dark-tile eaves, on a stone
platform, topped by a gilded 塔刹 (sūtra spire) with 相轮 rings and a 宝珠 finial.
Everything is authored here rather than downloaded: no Mojang asset exists for a
decorative pagoda, and the palette is kept inside what vanilla ships -- stone gray,
washed-plaster walls, dark walnut timber, a slate-blue glazed tile roof, and gold.

Format facts are the ones measured for the flower pot (see build_bawanghua_pot.py):
a face's uv rect reads upright and unmirrored from outside with v from the top, and
Free format allows a centred grid, so the pagoda stands on y=0 centred on x=z=0 with
the door facing -Z (north) -- Blockbench's default camera sits at (-40, 32, -40), so
the entrance is the first thing visible when the project opens.

One convention of its own: uv rects are sampled in "crop" mode -- a face of size
w*h takes the rect's top-left w*h pixels -- so every face on the model samples at
1:1 texel density no matter which tier it belongs to. Each rect is therefore painted
seamless from its origin, which is also why the stacked roof slabs line up: a
smaller top crops the same tile grid the slab below shows.
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
OUT_DIR = os.path.join(os.path.dirname(HERE), "pagoda")
os.makedirs(OUT_DIR, exist_ok=True)
MODEL_NAME = "pagoda"

FACES = ("north", "east", "south", "west", "up", "down")
PLACEHOLDER = (255, 0, 255, 255)


def at(cv, r):
    return cv[r[1]:r[1] + r[3], r[0]:r[0] + r[2]]


def paint(cv, r, color):
    at(cv, r)[:] = (*color, 255)


def speckle(cv, r, color, count, rng):
    x0, y0, w, h = r
    for _ in range(count):
        cv[y0 + rng.randrange(h), x0 + rng.randrange(w)] = (*color, 255)


def edge_shadow(cv, r, color):
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


# --- texture rects -----------------------------------------------------------
# Each rect is painted seamless from its origin because faces crop from the top-left
# corner at 1:1 density; the largest face that samples a rect sets its size.
RECT_SIZES = [
    ("stone", 20, 20), ("roof_top", 19, 19), ("roof_edge", 19, 1),
    ("wall_t1", 14, 8), ("wall_t2", 10, 5), ("wall_t3", 7, 4),
    ("pillar_side", 1, 8), ("wood_end", 1, 1),
    ("door", 4, 5), ("window_t1", 3, 3), ("window_t2", 3, 2),
    ("gold_pole", 2, 8), ("gold_ball", 4, 4), ("gold_seat", 3, 1), ("gold_cap", 2, 1),
    ("ring_side", 5, 1), ("ring_face", 5, 5),
]


def paint_texture(atlas: Atlas) -> None:
    cv, r = atlas.cv, atlas.rects
    rng = random.Random(20260924)

    # --- stone: vanilla-style mid-gray speckle for the platform and plinth ----
    stone = [(98, 98, 98), (112, 112, 112), (120, 120, 120), (127, 127, 127),
             (134, 134, 134), (140, 140, 140)]
    weights = [1, 3, 4, 6, 4, 2]
    pool = [c for c, n in zip(stone, weights) for _ in range(n)]
    s = r["stone"]
    for y in range(s[3]):
        for x in range(s[2]):
            cv[s[1] + y, s[0] + x] = (*rng.choice(pool), 255)

    # --- roofs: glazed dark tiles, 3x2 running bond with dark joints ----------
    tiles = [(50, 54, 64), (57, 61, 71), (44, 48, 58), (63, 67, 77)]
    tile_hi = (72, 77, 88)
    joint = (28, 30, 36)
    tile_rng = random.Random(777001)
    tile_colors: dict[tuple[int, int], tuple[int, int, int]] = {}

    def tile_color(tx: int, row: int):
        key = (tx, row)
        if key not in tile_colors:
            tile_colors[key] = (tile_hi if tile_rng.random() < 0.10
                                else tiles[tile_rng.randrange(len(tiles))])
        return tile_colors[key]

    rt = r["roof_top"]
    for y in range(rt[3]):
        row = y // 2
        off = (row % 2) * 2
        for x in range(rt[2]):
            if y % 2 == 1:
                c = joint
            elif (x + off) % 3 == 0:
                c = joint
            else:
                c = tile_color((x + off) // 3, row)
            cv[rt[1] + y, rt[0] + x] = (*c, 255)

    re = r["roof_edge"]                     # eave fascia: darker board under the tiles
    paint(cv, re, (36, 39, 46))
    speckle(cv, re, (28, 30, 36), 6, rng)
    speckle(cv, re, (46, 50, 58), 6, rng)

    # --- walls: washed plaster, a dirt line at the base -----------------------
    def paint_wall(rect):
        paint(cv, rect, (198, 190, 168))
        speckle(cv, rect, (178, 170, 148), max(2, rect[2] * rect[3] // 14), rng)
        speckle(cv, rect, (212, 205, 184), max(2, rect[2] * rect[3] // 18), rng)
        for _ in range(max(1, rect[2] // 6)):     # faint vertical weather streaks
            x = rng.randrange(rect[2])
            h = rng.randint(2, max(2, rect[3] - 2))
            for y in range(h):
                cv[rect[1] + y, rect[0] + x] = (*(172, 164, 142), 255)
        paint(cv, (rect[0], rect[1] + rect[3] - 1, rect[2], 1), (156, 148, 128))

    paint_wall(r["wall_t1"])
    paint_wall(r["wall_t2"])
    paint_wall(r["wall_t3"])

    # --- timber: dark walnut, grain running down the pillar -------------------
    ps = r["pillar_side"]
    grain = [(95, 71, 43), (82, 60, 36), (72, 52, 30), (86, 63, 38), (76, 56, 33)]
    for y in range(ps[3]):
        cv[ps[1] + y, ps[0]] = (*grain[(y * 7 + 3) % len(grain)], 255)
    paint(cv, r["wood_end"], (92, 68, 41))

    # --- door: red-lacquered planks in a dark frame, brass knocker ------------
    d = r["door"]
    paint(cv, d, (124, 54, 42))
    paint(cv, (d[0] + 2, d[1] + 1, 1, d[3] - 2), (100, 42, 32))   # plank seam
    edge_shadow(cv, d, (78, 32, 24))
    paint(cv, (d[0] + 1, d[1] + 2, 1, 1), (218, 174, 86))

    # --- windows: black lattice ------------------------------------------------
    w1 = r["window_t1"]
    paint(cv, w1, (32, 34, 38))
    paint(cv, (w1[0], w1[1] + 1, w1[2], 1), (88, 92, 100))        # cross muntin
    paint(cv, (w1[0] + 1, w1[1], 1, w1[3]), (88, 92, 100))
    w2 = r["window_t2"]
    paint(cv, w2, (32, 34, 38))
    paint(cv, (w2[0], w2[1] + 1, w2[2], 1), (64, 68, 76))         # slit bar

    # --- gilded spire ----------------------------------------------------------
    gp = r["gold_pole"]
    paint(cv, (gp[0], gp[1], 1, gp[3]), (238, 192, 88))
    paint(cv, (gp[0] + 1, gp[1], 1, gp[3]), (206, 152, 56))
    speckle(cv, (gp[0], gp[1], 1, gp[3]), (248, 220, 128), 4, rng)
    speckle(cv, (gp[0] + 1, gp[1], 1, gp[3]), (182, 134, 44), 4, rng)

    gb = r["gold_ball"]                     # the 宝珠: lit top-left, shaded low-right
    paint(cv, gb, (222, 172, 62))
    for hx, hy in ((0, 0), (1, 0), (0, 1)):
        cv[gb[1] + hy, gb[0] + hx] = (*(250, 228, 144), 255)
    for hx, hy in ((2, 3), (3, 2), (3, 3)):
        cv[gb[1] + hy, gb[0] + hx] = (*(178, 130, 42), 255)
    cv[gb[1] + 1, gb[0] + 2] = (*(238, 192, 88), 255)

    paint(cv, r["gold_seat"], (238, 192, 88))
    paint(cv, (r["gold_seat"][0] + 1, r["gold_seat"][1], 1, 1), (222, 172, 62))
    paint(cv, (r["gold_seat"][0] + 2, r["gold_seat"][1], 1, 1), (196, 146, 52))
    paint(cv, r["gold_cap"], (244, 204, 100))
    paint(cv, (r["gold_cap"][0] + 1, r["gold_cap"][1], 1, 1), (204, 152, 56))

    rs = r["ring_side"]                     # the 相轮 rings read as stacked beads
    for x, c in enumerate([(196, 146, 52), (228, 180, 76), (196, 146, 52),
                           (228, 180, 76), (178, 130, 42)]):
        cv[rs[1], rs[0] + x] = (*c, 255)
    rf = r["ring_face"]
    paint(cv, rf, (190, 140, 48))
    speckle(cv, rf, (206, 156, 60), 6, rng)
    speckle(cv, rf, (172, 122, 40), 6, rng)
    edge_shadow(cv, rf, (148, 102, 32))


# --- geometry -----------------------------------------------------------------
# Blockbench pixels: 1 unit = 1/16 block. The pagoda stands on y=0, centred on
# x=z=0, 40 units tall and 20 across: a slim three-storey tower rather than a squat
# shrine. Bodies step in 14 -> 10 -> 7; each roof flares past its body and steps
# back in over 2-3 slabs, which is how blocky models say "upturned eave".
def face_dims(face, frm, to):
    """Face size in model units: (u width, v height) for the crop sampler."""
    if face in ("north", "south"):
        return to[0] - frm[0], to[1] - frm[1]
    if face in ("east", "west"):
        return to[2] - frm[2], to[1] - frm[1]
    return to[0] - frm[0], to[2] - frm[2]           # up / down


def cube(name, frm, to, facemap):
    origin = ((frm[0] + to[0]) / 2, frm[1], (frm[2] + to[2]) / 2)
    return {"name": name, "from": frm, "to": to, "origin": origin, "faces": facemap}


def group(name, origin, children):
    return {"name": name, "origin": origin, "children": children}


def body(name, s, y0, y1, wall_rect, windows=("n", "e", "s", "w")):
    """One storey: a plaster box, four proud corner posts, and lattice panels.

    Tier 1 passes windows without "n" -- its north face carries the door, and a
    window panel there would be a second solid cube occupying the door's volume.
    """
    parts = [
        cube(f"{name}_body", (-s, y0, -s), (s, y1, s),
             {"north": wall_rect, "south": wall_rect, "east": wall_rect,
              "west": wall_rect, "up": "stone", "down": "stone"}),
    ]
    for sx, sz in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
        x0, x1 = sorted((sx * s - 0.5 * sx, sx * s + 0.5 * sx))
        z0, z1 = sorted((sz * s - 0.5 * sz, sz * s + 0.5 * sz))
        parts.append(cube(f"{name}_pillar_{'n' if sz < 0 else 's'}{'w' if sx < 0 else 'e'}",
                          (x0, y0, z0), (x1, y1, z1),
                          {"north": "pillar_side", "south": "pillar_side",
                           "east": "pillar_side", "west": "pillar_side",
                           "up": "wood_end", "down": "wood_end"}))
    h = 3 if wall_rect == "wall_t1" else 2
    wy0 = y0 + (y1 - y0 - h) // 2 + 1
    wy1 = wy0 + h
    rect = "window_t1" if h == 3 else "window_t2"
    if "n" in windows:
        parts.append(cube(f"{name}_window_n", (-1.5, wy0, -s - 0.5), (1.5, wy1, -s),
                          {f: rect for f in FACES}))
    if "s" in windows:
        parts.append(cube(f"{name}_window_s", (-1.5, wy0, s), (1.5, wy1, s + 0.5),
                          {f: rect for f in FACES}))
    if "e" in windows:
        parts.append(cube(f"{name}_window_e", (s, wy0, -1.5), (s + 0.5, wy1, 1.5),
                          {f: rect for f in FACES}))
    if "w" in windows:
        parts.append(cube(f"{name}_window_w", (-s - 0.5, wy0, -1.5), (-s, wy1, 1.5),
                          {f: rect for f in FACES}))
    return parts


def roof(name, y0, spans):
    """Stepped eave: one slab per span, all 1 unit thick, tiles above, fascia below."""
    parts = []
    for i, half in enumerate(spans):
        parts.append(cube(f"{name}_{i}", (-half, y0 + i, -half), (half, y0 + i + 1, half),
                          {"north": "roof_edge", "south": "roof_edge",
                           "east": "roof_edge", "west": "roof_edge",
                           "up": "roof_top", "down": "roof_top"}))
    return parts


def build_tree():
    base = group("base", (0, 0, 0), [
        cube("platform", (-10, 0, -10), (10, 1, 10), {f: "stone" for f in FACES}),
        cube("plinth", (-9, 1, -9), (9, 2, 9), {f: "stone" for f in FACES}),
    ])

    tier1 = group("tier1", (0, 2, 0), body("t1", 7, 2, 10, "wall_t1",
                                           windows=("s", "e", "w")) + [
        cube("t1_door", (-2, 2, -7.5), (2, 7, -7), {f: "door" for f in FACES}),
    ])
    roof1 = group("roof1", (0, 10, 0), roof("t1_roof", 10, (9.5, 8.5, 7)))

    tier2 = group("tier2", (0, 13, 0), body("t2", 5, 13, 18, "wall_t2"))
    roof2 = group("roof2", (0, 18, 0), roof("t2_roof", 18, (7, 6)))

    tier3 = group("tier3", (0, 20, 0), body("t3", 3.5, 20, 24, "wall_t3"))
    roof3 = group("roof3", (0, 24, 0), roof("t3_roof", 24, (5.5, 4.5)))

    spire = group("spire", (0, 26, 0), [
        cube("spire_base", (-2, 26, -2), (2, 27, 2), {f: "stone" for f in FACES}),
        cube("spire_seat", (-1.5, 27, -1.5), (1.5, 28, 1.5),
             {"north": "gold_seat", "south": "gold_seat", "east": "gold_seat",
              "west": "gold_seat", "up": "gold_ball", "down": "gold_ball"}),
        cube("spire_pole", (-1, 28, -1), (1, 36, 1),
             {"north": "gold_pole", "south": "gold_pole", "east": "gold_pole",
              "west": "gold_pole", "up": "gold_ball", "down": "gold_seat"}),
        cube("spire_ring_0", (-2.5, 29, -2.5), (2.5, 30, 2.5),
             {"north": "ring_side", "south": "ring_side", "east": "ring_side",
              "west": "ring_side", "up": "ring_face", "down": "ring_face"}),
        cube("spire_ring_1", (-2.5, 31, -2.5), (2.5, 32, 2.5),
             {"north": "ring_side", "south": "ring_side", "east": "ring_side",
              "west": "ring_side", "up": "ring_face", "down": "ring_face"}),
        cube("spire_ring_2", (-2.5, 33, -2.5), (2.5, 34, 2.5),
             {"north": "ring_side", "south": "ring_side", "east": "ring_side",
              "west": "ring_side", "up": "ring_face", "down": "ring_face"}),
        cube("spire_ball", (-2, 35, -2), (2, 39, 2), {f: "gold_ball" for f in FACES}),
        cube("spire_cap", (-1, 39, -1), (1, 40, 1),
             {"north": "gold_cap", "south": "gold_cap", "east": "gold_cap",
              "west": "gold_cap", "up": "gold_ball", "down": "gold_ball"}),
    ])

    return group(MODEL_NAME, (0, 0, 0), [base, tier1, roof1, tier2, roof2,
                                         tier3, roof3, spire])


# --- bbmodel writing ----------------------------------------------------------
def write_model(path: str, tree, rects, texture: Image.Image,
                resolution=(64, 64)) -> int:
    elements: list[dict] = []

    def emit_cube(c: dict) -> str:
        frm, to = c["from"], c["to"]
        el = {
            "name": c["name"],
            "from": [float(v) for v in frm],
            "to": [float(v) for v in to],
            "origin": [float(v) for v in c["origin"]],
            "uuid": str(uuid.uuid4()),
            "faces": {},
            "type": "cube",
            "color": 0,
        }
        for face in FACES:
            rx, ry, rw, rh = rects[c["faces"][face]]
            fw, fh = face_dims(face, frm, to)
            uv_w = min(fw, rw)
            uv_h = min(fh, rh)
            el["faces"][face] = {"uv": [rx, ry, rx + uv_w, ry + uv_h], "texture": 0}
        elements.append(el)
        return el["uuid"]

    def walk(node: dict) -> dict:
        if "faces" in node:                      # a cube leaf from build_tree
            return emit_cube(node)
        children = [walk(child) for child in node.get("children") or []]
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
            "path": "", "name": f"{MODEL_NAME}.png", "folder": "block", "namespace": "",
            "id": "0", "particle": False, "render_mode": "default", "visible": True,
            "mode": "bitmap", "saved": False, "uuid": str(uuid.uuid4()), "source": uri,
        }],
        "animations": [],
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False)
    return len(elements)


def unsampled_or_unpainted(atlas: Atlas, tree) -> None:
    """Both directions: a face sampling an unpainted rect shows magenta, and a rect
    no face samples means a typo in a facemap that silently shipped unpainted."""
    used: set[str] = set()

    def collect(node):
        if "faces" in node:                      # a cube leaf
            used.update(node["faces"].values())
            return
        for child in node.get("children") or []:
            collect(child)

    collect(tree)

    def is_painted(name):
        x, y, w, h = atlas.rects[name]
        patch = atlas.cv[y:y + h, x:x + w]
        return not np.any(np.all(patch == np.array(PLACEHOLDER, np.uint8), axis=-1))

    bad = [n for n in used if not is_painted(n)]
    if bad:
        raise SystemExit(f"faces sample unpainted rects: {bad}")
    unused = sorted(set(atlas.rects) - used)
    if unused:
        raise SystemExit(f"rects painted but never sampled: {unused}")


def main() -> int:
    atlas = Atlas(64)
    for name, w, h in sorted(RECT_SIZES, key=lambda item: -item[2]):
        atlas.add(name, w, h)
    paint_texture(atlas)
    atlas.extend_edges()

    tree = build_tree()
    unsampled_or_unpainted(atlas, tree)

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
