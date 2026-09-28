"""Shared scaffolding for the weapon builders: atlas, painting library, cube
vocabulary, writer, animation keys and the preview pass.

    from bbmodel_build import (Atlas, FM, cube, group, hoop, link, knucklebone,
                               build_atlases, write_model, kf, make_animation,
                               render_previews)

`tools/bbmodel_kit.py` is the *math* (transform algebra + structural checks);
this is the *shop floor* the three 兵器/ weapon scripts share -- the same code
that built undead_scythe, factored out so the next weapon does not start by
copying 700 lines of it. Each weapon keeps its own palette, painters, geometry
and self-checks; only what is genuinely the same across them lives here.

House facts encoded below (measured; conventions live in README.md, the
pitfalls that produced them in ISSUE.md):

* per-face uv rects, `box_uv: false` on every cube, front = -Z;
* 1 uv unit = 1 model unit, and the map is painted at S = 2 pixels per unit:
  project `resolution` stays 128 while the texture is 256, and the uv rects
  written out are the pixel rects divided by S (both renderers sample
  `u / resolution.width * image pixels`, so this needs no renderer support);
* noise has to be painted per *unit* (S x S px blocks) -- per-texel speckle at
  2 px/unit turns a blade into static;
* a group is written twice on purpose: inline in the outliner node (the 4.5
  legacy-group path Blockbench itself reads) and in the top-level `groups` table
  (the 5.0 layout third-party renderers parse). Blockbench merges by uuid.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import subprocess
import sys
import uuid

import numpy as np
from PIL import Image

S = 2                                     # texture pixels per model unit / uv unit
PLACEHOLDER = (255, 0, 255, 255)          # magenta canary: unpainted uv shows up
GLOW_BG = (0, 0, 0, 255)                  # the emissive map wants black
TEX_BODY, TEX_GLOW = 0, 1


# --- painting helpers ------------------------------------------------------
def at(cv, r):
    x, y, w, h = r
    return cv[y:y + h, x:x + w]


def rect_key(key):
    """Painters get the (material, w, h) tuple in MODEL units: some read it."""
    return key[1], key[2]


class R:
    """A seeded rng with both the scalar call sites and the array masks the
    painters want, so every rect paints identically on every run.

    The seed is a *digest*, not `hash()`: Python randomises str/tuple hashing
    per process (PYTHONHASHSEED), so seeding on hash() silently repaints the
    whole texture on every run -- the atlas layout stays put but the noise,
    stains and scratches move, which makes "rerun reproduces it" false and any
    before/after comparison useless.
    """

    def __init__(self, key):
        seed = ":".join(str(k) for k in key) if isinstance(key, tuple) else str(key)
        digest = hashlib.sha256(seed.encode("utf-8")).digest()
        self.g = np.random.default_rng(int.from_bytes(digest[:8], "little"))

    def random(self, shape=None):
        return float(self.g.random()) if shape is None else self.g.random(shape)

    def randint(self, a, b):
        return int(self.g.integers(a, b + 1))

    def randrange(self, n):
        return int(self.g.integers(0, n))


def rng_for(key) -> R:
    return R(key)


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
    clusters, not as per-texel dither."""
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


# --- atlas -----------------------------------------------------------------
class Atlas:
    """Shelf packer keyed by (material, w, h) in MODEL units; each rect is
    allocated S pixels per unit and painted on allocate, so a project
    resolution of 128 can carry a 256 px map."""

    def __init__(self, size: int, tex_index: int, painters: dict, bg=None):
        self.size = size                    # pixels
        self.tex = tex_index
        self.bg = bg if bg is not None else (PLACEHOLDER if tex_index == TEX_BODY else GLOW_BG)
        self.painters = painters
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
        self.painters[key[0]](self.cv, r, key)
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


FACES = ("north", "east", "south", "west", "up", "down")


def cube(name, frm, to, facemap):
    """A box. The two corners may be given in either order -- they are sorted,
    so a mirrored part can be authored with one expression while its twin uses
    the negated one (-sx * a, -sx * b) without coming out inside-out."""
    return {"name": name,
            "from": tuple(min(a, b) for a, b in zip(frm, to)),
            "to": tuple(max(a, b) for a, b in zip(frm, to)),
            "faces": facemap}


def group(name, cubes=(), children=(), origin=(0, 0, 0), rotation=None):
    return {"name": name, "origin": origin, "rotation": rotation,
            "cubes": list(cubes), "children": list(children)}


def hoop(name, y0, y1, outer, bar, facemap):
    """Four bars forming a square hoop around the vertical axis."""
    o, i = outer, outer - bar
    return [
        cube(f"{name}_n", (-o, y0, -o), (o, y1, -i), facemap),
        cube(f"{name}_s", (-o, y0, i), (o, y1, o), facemap),
        cube(f"{name}_w", (-o, y0, -i), (-i, y1, i), facemap),
        cube(f"{name}_e", (i, y0, -i), (o, y1, i), facemap),
    ]


def link(name, x, y, z, w, h, t, facemap, plane="xy"):
    """A chain link: a rectangular ring of four bars, in the xy or zy plane.
    Keep w > 2t and h > 2t or the bars themselves end up coplanar."""
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
    """A bone charm: a shaft with a knob at each end. Spans y .. y+h."""
    return [
        cube(f"{name}_shaft", (x + 0.4, y + 0.5, z + 0.4), (x + 1.6, y + h - 0.5, z + 0.9),
             facemap),
        cube(f"{name}_k0", (x, y, z), (x + 0.5, y + h, z + 1.3), facemap),
        cube(f"{name}_k1", (x + 1.5, y, z), (x + 2.0, y + h, z + 1.3), facemap),
    ]


# --- assembling and writing -------------------------------------------------
def collect_rects(tree, tex_index, glow_materials):
    """Every (material, w, h) the tree actually uses, biggest first (a shelf
    packer likes big rects first)."""
    from bbmodel_kit import FACES as F, face_size, walk_groups
    seen = {}
    for _path, c, _R, _t in walk_groups(tree):
        for mat in c["faces"].values():
            if tex_of(mat, glow_materials) != tex_index:
                continue
            for face in F:
                seen[(mat,) + tuple(face_size(face, c["from"], c["to"]))] = True
    return sorted(seen, key=lambda k: (-k[2], -k[1]))


def tex_of(material: str, glow_materials) -> int:
    return TEX_GLOW if material in glow_materials else TEX_BODY


def build_atlases(tree, painters: dict, glow_materials, sizes=(256, 320, 384, 448, 512)):
    """One atlas size for the whole model (a project has a single uv
    resolution), so the body map decides the size and the glow map follows."""
    body = collect_rects(tree, TEX_BODY, glow_materials)
    glow = collect_rects(tree, TEX_GLOW, glow_materials)
    for size in sizes:
        atlases = {}
        try:
            for idx, keys in ((TEX_BODY, body), (TEX_GLOW, glow)):
                atlas = Atlas(size, idx, painters)
                for mat, w, h in keys:
                    atlas.alloc((mat, w, h), w, h)
                atlases[idx] = atlas
        except RuntimeError:
            continue
        for atlas in atlases.values():
            atlas.extend_edges()
        return atlases
    raise SystemExit("no atlas size fits the model")


def check_painted(atlas: Atlas) -> list:
    """Rects the painters left untouched -- the magenta canary."""
    ph = np.array(atlas.bg, np.uint8)
    return [str(key) for key, (x, y, w, h) in atlas.rects.items()
            if np.any(np.all(atlas.cv[y:y + h, x:x + w] == ph, axis=-1))]


def kf(channel, time, value, interpolation="linear"):
    """One Blockbench keyframe: numbers ride as Molang strings in data_points."""
    pt = {"x": f"{value[0]:g}", "y": f"{value[1]:g}", "z": f"{value[2]:g}"}
    return {"channel": channel, "data_points": [pt], "uuid": str(uuid.uuid4()),
            "time": float(time), "color": -1, "interpolation": interpolation}


def make_animation(name, length, tracks, by_name, loop="loop", snapping=24):
    """Assemble a clip. `tracks` maps a GROUP name to a list of keyframe lists
    (one per channel): {bone: [[("position", t, (x,y,z), interp), ...], ...]}.

    Only groups: the writer gives every cube origin [0,0,0], so a cube-level
    rotation or scale would pivot on the model origin and fling the cube away.
    """
    animators = {}
    for bone, channels in tracks.items():
        keys = [k for ch in channels for k in ch]
        animators[by_name[bone]] = {"name": bone, "type": "bone", "keyframes": keys}
    return {
        "uuid": str(uuid.uuid4()), "name": name, "loop": loop, "override": False,
        "length": float(length), "snapping": snapping, "selected": False,
        "saved": False, "path": "", "anim_time_update": "", "blend_weight": "",
        "start_delay": "", "loop_delay": "", "animators": animators,
    }


def write_model(path: str, tree, atlases: dict, textures: dict, model_name: str,
                glow_materials, animations=()) -> int:
    """Write the project. `animations` is either a list or a callable taking the
    group-name -> uuid map: animators are keyed by group uuid, and those uuids
    only exist once the tree has been walked, so a callable is the usual form."""
    from bbmodel_kit import FACES as F, face_size, walk_groups  # noqa: F401
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
        for face in F:
            mat = c["faces"][face]
            w, h = face_size(face, c["from"], c["to"])
            x, y, rw, rh = atlases[tex_of(mat, glow_materials)].rects[(mat, w, h)]
            el["faces"][face] = {"uv": [x / S, y / S, (x + rw) / S, (y + rh) / S],
                                 "texture": tex_of(mat, glow_materials)}
        elements.append(el)
        by_name[c["name"]] = el["uuid"]
        return el["uuid"]

    def walk(node: dict) -> dict:
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
    anims = list(animations(by_name)) if callable(animations) else list(animations)
    res = atlases[TEX_BODY].size // S
    tex_docs = []
    for idx in (TEX_BODY, TEX_GLOW):
        if idx not in textures:
            continue
        buf = io.BytesIO()
        textures[idx].save(buf, format="PNG")
        uri = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
        tex_docs.append({
            "path": "", "name": f"{model_name}{'' if idx == TEX_BODY else '_glow'}.png",
            "folder": "entity", "namespace": "", "id": str(idx), "particle": False,
            "render_mode": "default" if idx == TEX_BODY else "emissive",
            "visible": True, "mode": "bitmap", "saved": False,
            "uuid": str(uuid.uuid4()), "source": uri,
            "width": atlases[idx].size, "height": atlases[idx].size,
            "uv_width": res, "uv_height": res})
    doc = {
        "meta": {"format_version": "4.5", "model_format": "free", "box_uv": False},
        "name": model_name,
        "resolution": {"width": res, "height": res},
        "elements": elements,
        "outliner": outliner,
        "groups": groups,
        "textures": tex_docs,
        "animations": anims,
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False)
    return len(elements)


def render_previews(model_path: str, out_dir: str, model_name: str, previews) -> None:
    """previews = [(suffix, azimuth, elevation, distance, (tx, ty, tz)), ...]"""
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for suffix, az, el, dist, target in previews:
        out = os.path.join(out_dir, f"{model_name}_preview{suffix}.png")
        subprocess.run([sys.executable, os.path.join(repo, "tools", "preview_bbmodel.py"),
                        model_path, out, "--size", "760", "--azimuth", str(az),
                        "--elevation", str(el), "--distance", str(dist),
                        "--target", *[str(t) for t in target]], check=True)
