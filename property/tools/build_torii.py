"""Build the 精致鸟居 (shrine torii gate) as a Blockbench project.

    python tools/build_torii.py

Writes ../torii/torii.bbmodel (texture embedded as a data URI) and ../torii/torii.png
(the same texture, standalone).

A myōjin-style torii (明神鳥居), the iconic shrine gate. The signature features are
all here: the two pillars lean inward (柱の内傾, 5 deg), the top lintel (笠木 kasagi)
is a three-piece beam whose end sections tilt up 8 deg to suggest the sorimashi
curve, a secondary beam (島木 shimaki) runs directly under it, the lower tie beam
(貫 nuki) pierces both pillars and pokes out past them, the plaque (額束 gakuzuka)
fills the centre gap, and gilded onion finials (擬宝珠 giboshi) cap the lintel ends.
Dressing: a straw sacred rope (注連縄 shimenawa) sagging under the nuki with two
zigzag paper streamers (紙垂 shide), stone pedestal bases (台石) under the pillars
and a stone approach path running through the gate.

Layout (units of 1/16 block, ground y=0, front faces -Z / north):
  stone path tiles y 0..0.75 across x -4..4; pedestal bases y 0..3 at x +-8..14;
  pillars 3x3 from y 3 to 33, leaning 5 deg inward about their foot pivots
  (11,3,0) / (-11,3,0); shimaki y 32..34 (swallows the tilted pillar tops,
  which reach y ~32.9); kasagi main y 34..37 x -11..11, end sections
  x 10.75..16 rotated +-8 deg about (11,35.5,0) -- their inner ends overlap the
  main beam by 0.25 so no wedge gap opens at the joint, and their outer ends
  reach x ~16.16 at y ~34.8..37.7; giboshi stacks sit on the tilted end
  sections (embedded ~0.5 into them) up to y 41.4; nuki y 25..28 x +-12.5;
  gakuzuka y 28..32; shimenawa rope hangs below the nuki (sag 0.6) with two
  three-segment shide in front of it. Total height ~41.4 (~2.6 blocks),
  kasagi span ~32.3, path footprint 8 x 26.

Pillar tilt sign: rotation about +Z maps +Y toward -X, so the east pillar takes
rz=+5 (top swings toward the centre) and the west rz=-5. Kasagi end sections
rz=+8 on the east rotates the outward-pointing +X end upward.

All rotated elements pivot on their own `origin`; no group carries a rotation,
so the inline-group format of the 4.5 project stays unambiguous. Rotations are
arbitrary degrees, which the 'free' format allows (Java block export would not).

Format conventions are the ones measured out of Blockbench's source (see
build_bawanghua_pot.py / skill/references/bbmodel-format.md): per-face uv rects
upright and unmirrored seen from outside, v from the top; model_format 'free'.
Shared atlas like the cottage: every face samples the rect for its (material,
width, height) pair. Painters are noise/symmetric -- the plaque motif and the
paper shading are deliberately left-right symmetric so north/south/east/west
can share one rect each; the rope's diagonal twist is the one directional
pattern, and its mirror on far sides reads as rope anyway.
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
OUT_DIR = os.path.join(os.path.dirname(HERE), "torii")
os.makedirs(OUT_DIR, exist_ok=True)
MODEL_NAME = "torii"

FACES = ("north", "east", "south", "west", "up", "down")
PLACEHOLDER = (255, 0, 255, 255)

# --- palettes (hand-picked vanilla look; official assets are unreachable) ---
VERM = [(216, 70, 48), (202, 60, 42), (186, 52, 36), (162, 44, 30)]
VERM_END_LIGHT = (232, 96, 66)
VERM_END_RING = (178, 52, 34)
GOLD = [(228, 190, 98), (212, 172, 82), (192, 150, 66), (168, 128, 52)]
GOLD_HI = (244, 216, 138)
STONE = [(136, 134, 130), (124, 122, 118), (112, 110, 106), (98, 96, 92)]
STONE_HI = (152, 150, 146)
STONE_MORTAR = (86, 84, 80)
ROPE = [(198, 164, 102), (182, 148, 90), (164, 132, 78), (146, 116, 68)]
ROPE_DARK = (128, 100, 58)
PAPER = (243, 241, 233)
PAPER_SHADE = (214, 210, 198)
LACQ = [(54, 46, 48), (46, 40, 42), (38, 34, 36)]


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

def paint_verm(cv, r, key):
    """Vermilion lacquer over wood: streaks along the long axis of the face."""
    x, y, w, h = r
    rng = rng_for(key)
    a = at(cv, r)
    if w >= h:  # horizontal member: streaks run along x
        for row in range(h):
            a[row, :] = (*shade(VERM, rng.choice((0, 1, 1, 2))), 255)
        col = 0
        while col < w:
            run = rng.choice((2, 3, 4))
            a[:, col:col + run] = (*shade(VERM, rng.choice((1, 2, 2, 3))), 255)
            col += run
    else:  # vertical post: streaks run along y
        for col in range(w):
            a[:, col] = (*shade(VERM, rng.choice((0, 1, 1, 2))), 255)
        row = 0
        while row < h:
            run = rng.choice((2, 3, 4))
            a[row:row + run, :] = (*shade(VERM, rng.choice((1, 2, 2, 3))), 255)
            row += run
    for _ in range(max(1, (w * h) // 18)):  # weathering flecks back to tone 0
        a[rng.randrange(h), rng.randrange(w)] = (*shade(VERM, 0), 255)


def paint_verm_end(cv, r, key):
    """End grain of a vermilion-painted beam: dark rim, ring, light heart."""
    a = at(cv, r)
    w, h = r[2], r[3]
    a[:] = (*VERM_END_LIGHT, 255)
    if w >= 3 and h >= 3:
        rim = shade(VERM, 2)
        a[0, :] = (*rim, 255)
        a[-1, :] = (*rim, 255)
        a[:, 0] = (*rim, 255)
        a[:, -1] = (*rim, 255)
        a[1:-1, 1:-1] = (*VERM_END_RING, 255)
        a[h // 2 - 1:h // 2 + 1, w // 2 - 1:w // 2 + 1] = (*VERM_END_LIGHT, 255)
    else:
        a[:, w // 2:] = (*VERM_END_RING, 255)


def paint_gold(cv, r, key):
    """Soft gold: gentle tone rows plus bright and dark flecks."""
    x, y, w, h = r
    rng = rng_for(key)
    a = at(cv, r)
    for row in range(h):
        a[row, :] = (*shade(GOLD, rng.choice((0, 1, 1, 2))), 255)
    for _ in range(max(1, (w * h) // 12)):
        px, py = rng.randrange(w), rng.randrange(h)
        a[py, px] = (*(GOLD_HI if rng.random() < 0.4 else shade(GOLD, 3)), 255)


def paint_stone(cv, r, key):
    """Mortar field + small jittered stones, each shaded light top-left."""
    x, y, w, h = r
    rng = rng_for(key)
    a = at(cv, r)
    a[:] = (*STONE_MORTAR, 255)
    ry = 0
    while ry < h:
        rh = min(rng.choice((1, 2, 2)), h - ry)
        rx = 0
        while rx < w:
            rw = min(rng.choice((2, 3, 4)), w - rx)
            if w - (rx + rw) == 1:
                rw += 1
            tone = rng.choice((0, 1, 1, 2, 2, 3))
            a[ry:ry + rh, rx:rx + rw] = (*shade(STONE, tone), 255)
            a[ry, rx] = (*(STONE_HI if tone < 2 else shade(STONE, max(0, tone - 1))), 255)
            a[ry + rh - 1, rx + rw - 1] = (*shade(STONE, min(3, tone + 1)), 255)
            rx += rw + 1
        ry += rh + 1


def paint_rope(cv, r, key):
    """Straw rope: diagonal twist stripes with a dark binding line."""
    x, y, w, h = r
    rng = rng_for(key)
    a = at(cv, r)
    phase = rng.randrange(4)
    for row in range(h):
        for col in range(w):
            t = (col + row + phase) % 4
            a[row, col] = (*(ROPE_DARK if t == 0 else shade(ROPE, t % 3)), 255)


def paint_paper(cv, r, key):
    """White paper streamer: shaded bottom and side folds, faint flecks."""
    x, y, w, h = r
    rng = rng_for(key)
    a = at(cv, r)
    a[:] = (*PAPER, 255)
    a[-1, :] = (*PAPER_SHADE, 255)
    a[:, 0] = (*PAPER_SHADE, 255)
    a[:, -1] = (*PAPER_SHADE, 255)
    for _ in range(max(1, (w * h) // 10)):
        a[rng.randrange(h), rng.randrange(w)] = (*(234, 231, 222), 255)


def paint_plaque(cv, r, key):
    """Gakuzuka face: dark lacquer field with a tiny gold torii glyph.

    The face is tiny (4x4), so any gold frame would dominate; the dark field
    must carry the plaque and the glyph stays edge-to-edge. Left-right
    symmetric so north/south can share the rect.
    """
    a = at(cv, r)
    w, h = r[2], r[3]
    a[:] = (*LACQ[1], 255)
    if w >= 4 and h >= 4:
        a[1, :] = (*shade(GOLD, 0), 255)      # kasagi bar
        a[2, 0] = (*shade(GOLD, 1), 255)      # legs
        a[2, w - 1] = (*shade(GOLD, 1), 255)
        a[2, 1] = (*LACQ[0], 255)             # dark between the legs
        a[2, w - 2] = (*LACQ[0], 255)
        a[1, 0] = (*GOLD_HI, 255)
    else:
        a[h // 2, w // 2] = (*shade(GOLD, 0), 255)


def paint_dark(cv, r, key):
    """Dark lacquer (plaque sides/top/bottom)."""
    x, y, w, h = r
    rng = rng_for(key)
    a = at(cv, r)
    a[:] = (*LACQ[1], 255)
    for _ in range(max(1, (w * h) // 8)):
        a[rng.randrange(h), rng.randrange(w)] = (*LACQ[rng.choice((0, 2))], 255)


PAINTERS = {
    "verm": paint_verm, "verm_end": paint_verm_end, "gold": paint_gold,
    "stone": paint_stone, "rope": paint_rope, "paper": paint_paper,
    "plaque": paint_plaque, "dark": paint_dark,
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
    # sub-unit faces (giboshi tip is 0.5 wide) still need a 1px rect to sample
    return max(1, int(round(s[0]))), max(1, int(round(s[1])))


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


def cube(name, frm, to, facemap, origin=(0, 0, 0), rotation=None):
    return {"name": name, "from": frm, "to": to, "faces": facemap,
            "origin": origin, "rotation": rotation}


def mirror_x(c):
    """Mirror a cube across the x=0 plane (east <-> west).

    Only x flips: a mirror across the x=0 plane maps the pivot (ox, oy, oz) to
    (-ox, oy, oz). Negating y or z too would move the rotation pivot and throw
    the mirrored cube somewhere else entirely.
    """
    faces = dict(c["faces"])
    if "east" in faces or "west" in faces:
        faces["west"], faces["east"] = faces.get("east"), faces.get("west")
        faces = {k: v for k, v in faces.items() if v is not None}
    rot = c.get("rotation")
    return {"name": c["name"].replace("_east", "_west"),
            "from": (-c["to"][0], c["from"][1], c["from"][2]),
            "to": (-c["from"][0], c["to"][1], c["to"][2]),
            "faces": faces,
            "origin": (-c["origin"][0], c["origin"][1], c["origin"][2]),
            "rotation": (-rot[0], rot[1], -rot[2]) if rot else None}


def build_tree():
    tree = {"name": MODEL_NAME, "origin": (0, 0, 0), "children": []}

    def group(name, cubes):
        tree["children"].append(
            {"name": name, "origin": (0, 0, 0), "cubes": cubes, "children": []})

    # --- stone path + pedestal bases (台石) ----------------------------------
    bases = [
        cube("base_east_lower", (8, 0, -3), (14, 2, 3), FM(all="stone")),
        cube("base_east_upper", (8.5, 2, -2.5), (13.5, 3, 2.5), FM(all="stone")),
        cube("path_front_outer", (-4, 0, -13), (4, 0.75, -8), FM(all="stone")),
        cube("path_front_inner", (-4, 0, -8), (4, 0.75, -3), FM(all="stone")),
        cube("path_center", (-4, 0, -3), (4, 0.75, 3), FM(all="stone")),
        cube("path_back_inner", (-4, 0, 3), (4, 0.75, 8), FM(all="stone")),
        cube("path_back_outer", (-4, 0, 8), (4, 0.75, 13), FM(all="stone")),
    ]
    bases.append(mirror_x(bases[0]))
    bases.append(mirror_x(bases[1]))
    group("bases", bases)

    # --- pillars, leaning 5 deg inward about their feet -----------------------
    pillar_east = cube("pillar_east", (9.5, 3, -1.5), (12.5, 33, 1.5),
                       FM(sides="verm", tb="verm_end"),
                       origin=(11, 3, 0), rotation=(0, 0, 5))
    group("pillars", [pillar_east, mirror_x(pillar_east)])

    # --- shimaki + kasagi with upturned ends + giboshi finials ---------------
    lintel = [
        cube("shimaki", (-12, 32, -2.5), (12, 34, 2.5),
             FM(ns="verm", tb="verm", ew="verm_end")),
        cube("kasagi_main", (-11, 34, -3), (11, 37, 3), FM(all="verm")),
        cube("kasagi_east", (10.75, 34, -3), (16, 37, 3),
             FM(ns="verm", tb="verm", east="verm_end", west="verm"),
             origin=(11, 35.5, 0), rotation=(0, 0, 8)),
        # giboshi crowning the tip of the tilted east end section
        # (outer edge 16.1 stays just inside the beam end at 16.16)
        cube("giboshi_east_base", (13.5, 36.8, -1.5), (16.1, 38.8, 1.5), FM(all="gold")),
        cube("giboshi_east_mid", (14.15, 38.8, -1.1), (15.45, 40.3, 1.1), FM(all="gold")),
        cube("giboshi_east_tip", (14.55, 40.3, -0.6), (15.05, 41.4, 0.6), FM(all="gold")),
    ]
    lintel += [mirror_x(c) for c in lintel[2:]]
    group("lintel", lintel)

    # --- nuki, gakuzuka plaque, shimenawa rope + shide streamers -------------
    beam = [
        cube("nuki", (-12.5, 25, -1.5), (12.5, 28, 1.5), FM(all="verm")),
        cube("gakuzuka", (-2, 28, -1), (2, 32, 1),
             FM(ns="plaque", ew="dark", tb="dark")),
        cube("rope_left", (-7.8, 23.5, -2.6), (-2.5, 25.2, -1.3), FM(all="rope")),
        cube("rope_center", (-2.5, 22.9, -2.6), (2.5, 24.6, -1.3), FM(all="rope")),
        cube("rope_right", (2.5, 23.5, -2.6), (7.8, 25.2, -1.3), FM(all="rope")),
    ]
    # two separated zigzag streamers: 2.2-wide folds offset by 1, centres +-2.1
    for side, c in (("left", -2.1), ("right", 2.1)):
        beam.append(cube(f"shide_{side}_1", (c - 1.1, 22.6, -3.4), (c + 1.1, 24.2, -2.5),
                         FM(all="paper")))
        beam.append(cube(f"shide_{side}_2", (c - 0.1, 21.0, -3.4), (c + 2.1, 22.6, -2.5),
                         FM(all="paper")))
        beam.append(cube(f"shide_{side}_3", (c - 1.1, 19.4, -3.4), (c + 1.1, 21.0, -2.5),
                         FM(all="paper")))
    group("beam", beam)

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


def write_model(path: str, tree, atlas: Atlas, texture: Image.Image) -> int:
    elements: list[dict] = []

    def emit_cube(c: dict) -> str:
        el = {
            "name": c["name"],
            "from": [float(v) for v in c["from"]],
            "to": [float(v) for v in c["to"]],
            "origin": [float(v) for v in c.get("origin") or (0, 0, 0)],
            "uuid": str(uuid.uuid4()),
            "faces": {},
            "type": "cube",
            "color": 0,
        }
        if c.get("rotation"):
            el["rotation"] = [float(v) for v in c["rotation"]]
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
        g = {"name": node["name"],
             "origin": [float(v) for v in node["origin"]],
             "uuid": str(uuid.uuid4()),
             "children": children}
        if node.get("rotation"):
            g["rotation"] = [float(v) for v in node["rotation"]]
        return g

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
