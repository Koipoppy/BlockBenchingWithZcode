"""Build 金龙 (a golden Chinese loong) as a Blockbench project -- authored through
the local blockbench-headless MCP server rather than by writing the .bbmodel by hand.

    python golden_loong/build_golden_loong.py            # build, write, validate, render

Writes ../golden_loong/golden_loong.bbmodel (both textures embedded), the same
two textures as standalone PNGs, and the offline previews.

Why this one goes through the MCP (the earlier models in this repo wrote their
.bbmodel directly): the MCP is the authority on the format, so the project it
writes is 5.0 and already in the layout Blockbench itself saves. Everything the
script does is one MCP call per kind of work:

    bbmodel_create  -> empty free-format project at the target resolution
    bbmodel_edit    -> add_group / add_cube, batched 400 ops at a time
    bbmodel_add_texture -> embeds the two painted PNGs
    bbmodel_edit    -> add_animation / set_keyframe for the fly cycle

The rig is a nested chain, so the pose is solved rather than typed in. Rest pose
is the animal laid out straight along +Z (nose at -Z, per the repo's front-facing
convention); every joint carries a rotation about its own origin and children are
authored in absolute model space, so the accumulated chain reproduces
`p_world = R_chain . p_authored + t`. Given a desired world frame per joint the
script derives the local rotation `R_local = R_parent^-1 . R_world` (bbmodel-format
§12) and then re-walks the whole chain with bbmodel_kit.walk_groups to check where
the geometry actually landed before anything is rendered.

The pose itself comes from a hand-drawn guide curve (waypoints from the nose to
the tail tip); each joint samples the curve's tangent and builds a minimal-roll
frame from it, which is what keeps the dorsal line on the outside of every bend.
"""
from __future__ import annotations

import base64
import io
import json
import math
import os
import sys
import uuid

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.dont_write_bytecode = True
# the model folders sit in category folders now (生物/人物/物品/兵器), so walk up
# to the repo root (the folder holding tools/bbmodel_kit.py) and take the
# workspace -- the folder holding .mcp/ -- as its parent
PROPERTY = HERE
while not os.path.isfile(os.path.join(PROPERTY, "tools", "bbmodel_kit.py")):
    parent = os.path.dirname(PROPERTY)
    if parent == PROPERTY:
        raise SystemExit(f"repo root not found above {HERE}")
    PROPERTY = parent
sys.path.insert(0, os.path.join(PROPERTY, "tools"))   # 共享的 bbmodel_kit.py 在 tools/
sys.path.insert(0, os.path.join(os.path.dirname(PROPERTY), ".mcp"))

from bbmodel_kit import (FACES, V, unit, rot_ZYX, euler_ZYX, walk_groups,  # noqa: E402
                         face_size)
from call_tool import Client  # noqa: E402

OUT_DIR = HERE
os.makedirs(OUT_DIR, exist_ok=True)
MODEL = "golden_loong"
RES = 1024
PX = 2                      # default texels per model unit (the head paints at 3)
BBMODEL = os.path.join(OUT_DIR, MODEL + ".bbmodel")
TEX_MAIN = os.path.join(OUT_DIR, MODEL + "_body.png")
TEX_GLOW = os.path.join(OUT_DIR, MODEL + "_glow.png")

# ---------------------------------------------------------------------------
# 1. palette -- one dark->light ramp per material, never an ad-hoc RGB
# ---------------------------------------------------------------------------

GOLD = [(0x53, 0x32, 0x0A), (0x7C, 0x4E, 0x12), (0xAA, 0x71, 0x1C),
        (0xD2, 0x96, 0x2A), (0xEC, 0xBA, 0x4E), (0xFA, 0xDD, 0x8C)]
JADE = [(0x08, 0x2E, 0x29), (0x0F, 0x4E, 0x45), (0x18, 0x74, 0x64),
        (0x2A, 0xA1, 0x88), (0x5F, 0xCB, 0xAE), (0xA8, 0xEC, 0xD4)]
IVORY = [(0x6E, 0x5F, 0x44), (0xA8, 0x94, 0x6E), (0xD4, 0xC2, 0x98),
         (0xEC, 0xE0, 0xC2), (0xFA, 0xF3, 0xE2), (0xFF, 0xFD, 0xF6)]
HORN = [(0x4E, 0x41, 0x30), (0x7A, 0x69, 0x4E), (0xA6, 0x91, 0x6E),
        (0xCA, 0xB6, 0x92), (0xE4, 0xD6, 0xB8), (0xF6, 0xEE, 0xDC)]
MAW = [(0x33, 0x0A, 0x08), (0x59, 0x13, 0x0E), (0x84, 0x22, 0x18),
       (0xB0, 0x38, 0x26), (0xD1, 0x5C, 0x46), (0xEC, 0x8E, 0x78)]
DARK = [(0x0B, 0x09, 0x07), (0x1A, 0x15, 0x0F), (0x2C, 0x24, 0x18),
        (0x41, 0x36, 0x26), (0x58, 0x4A, 0x35), (0x70, 0x5F, 0x46)]
GLOW = [(0xC0, 0x5E, 0x00), (0xF0, 0x8E, 0x0E), (0xFF, 0xB4, 0x24),
        (0xFF, 0xD8, 0x64), (0xFF, 0xEF, 0xB4), (0xFF, 0xFF, 0xFF)]

MARK = {"gold": 1, "ivory": 2, "jade": 3, "maw": 4, "dark": 5, "glow": 6,
        "horn": 2, "claw": 2, "tooth": 2}


def ramp(rp, t):
    """Sample a ramp at t in 0..1 (clamped), returning an (r,g,b) tuple."""
    t = 0.0 if t < 0 else (1.0 if t > 1 else t)
    f = t * (len(rp) - 1)
    i = min(len(rp) - 2, int(f))
    k = f - i
    return tuple(int(round(rp[i][c] + (rp[i + 1][c] - rp[i][c]) * k)) for c in range(3))


# ---------------------------------------------------------------------------
# 2. texture atlas -- every face gets its own rect, painted 1:1 (or at an
#    explicit finer texel density for the head, which is the part people look at)
# ---------------------------------------------------------------------------

class Atlas:
    def __init__(self, size, bg=(255, 0, 255)):
        self.size = size
        # magenta by default: anything a uv samples outside a painted rect
        # screams instead of blending in, and the render gate scans for it.
        # The emissive map wants black instead -- magenta would GLOW.
        self.arr = np.zeros((size, size, 3), np.uint8)
        self.arr[:, :] = bg
        self.alpha = np.zeros((size, size), np.uint8)
        self.rects = {}
        self._x = self._y = self._rowh = 0
        self.pad = 1

    def finalize(self):
        """Bleed each rect one pixel into the padding around it, so no sampling
        at a rect edge can pick up the gap (the atlas is 1:1 with the faces, but
        a rounding on a fractional face size can still land on the boundary)."""
        n = 0
        for x, y, w, h in self.rects.values():
            block = self.arr[y:y + h, x:x + w]
            if y > 0:
                self.arr[y - 1, x:x + w] = block[0, :]
            if y + h < self.size:
                self.arr[y + h, x:x + w] = block[-1, :]
            if x > 0:
                self.arr[y:y + h, x - 1] = block[:, 0]
            if x + w < self.size:
                self.arr[y:y + h, x + w] = block[:, -1]
            for dy, yy in ((-1, y - 1), (1, y + h)):
                for dx, xx in ((-1, x - 1), (1, x + w)):
                    if 0 <= yy < self.size and 0 <= xx < self.size:
                        self.arr[yy, xx] = self.arr[y if dy < 0 else y + h - 1,
                                                    x if dx < 0 else x + w - 1]
            n += 1
        return n

    def alloc(self, name, w, h):
        w, h = int(w), int(h)
        if self._x + w + self.pad > self.size:
            self._y += self._rowh + self.pad
            self._x, self._rowh = 0, 0
        if self._y + h + self.pad > self.size:
            raise RuntimeError(f"atlas full at {name} ({w}x{h})")
        self.rects[name] = (self._x, self._y, w, h)
        self._x += w + self.pad
        self._rowh = max(self._rowh, h)
        return self.rects[name]

    def rect(self, name):
        x, y, w, h = self.rects[name]
        return [x, y, x + w, y + h]

    def put(self, name, rgb, a=None):
        x, y, w, h = self.rects[name]
        self.arr[y:y + h, x:x + w] = np.array(rgb, np.uint8)
        if a is not None:
            self.alpha[y:y + h, x:x + w] = a

    # ---- painting primitives (all vectorised over the rect) ---------------

    def _flow(self, rect, dir_):
        """(a, b) grids for a rect: b runs 'downstream' (the direction the pattern
        points), a runs across it. Matches how Blockbench maps a uv rect onto a
        face seen from outside: +u is left-to-right on screen, +v downward, and
        for a box along Z the four sides mirror each other, hence per-face dirs."""
        x, y, w, h = self.rects[rect] if isinstance(rect, str) else rect
        px = np.arange(w)[None, :].repeat(h, 0)
        py = np.arange(h)[:, None].repeat(w, 1)
        if dir_ == "right":
            return py, px
        if dir_ == "left":
            return py, (w - 1 - px)
        if dir_ == "down":
            return px, py
        return px, (h - 1 - py)          # "up"

    def scales(self, name, rp, dir_, seed=0, row=6, sw=8, grad=0.0, lo=0.34,
               hi=0.80):
        """Overlapping scales. What makes it read as scales rather than as a
        woven grid is that only the FREE EDGE is drawn: the dark seam follows a
        U across each scale (v2), so the cells interlock in a brick pattern with
        one curved shadow instead of a box outline. At 2 px/unit the default is
        a 3x4 unit scale."""
        a, b = self._flow(name, dir_)
        x, y, w, h = self.rects[name]
        row_i = b // row
        ai = a + (row_i % 2) * (sw // 2)
        u = (ai % sw) / float(sw)
        v = (b % row) / float(row)
        v2 = v + 0.30 * (2.0 * np.abs(u - 0.5)) ** 2
        seam = np.clip((v2 - 0.70) / 0.30, 0, 1)
        body = 0.66 + 0.30 * np.sin(math.pi * np.clip(v2 / 0.86, 0, 1))
        jit = (np.sin(ai * 12.9898 + row_i * 78.233) * 43758.5453) % 1.0
        jit = (jit - 0.5) * 0.11
        t = body * (1.0 - 0.52 * seam) + jit + grad * (v - 0.5)
        rp_arr = np.array(rp, np.float32)
        f = np.clip(lo + (hi - lo) * np.clip(t, 0, 1), 0, 1) * (len(rp) - 1)
        i0 = np.clip(f.astype(int), 0, len(rp) - 2)
        k = (f - i0)[..., None]
        col = rp_arr[i0] * (1 - k) + rp_arr[i0 + 1] * k
        self.arr[y:y + h, x:x + w] = col.astype(np.uint8)

    def bands(self, name, rp, dir_, pitch=5, seam=0.22, grad=0.0, lo=0.0, hi=1.0):
        """Transverse plates (belly scutes) stacked along the flow."""
        a, b = self._flow(name, dir_)
        x, y, w, h = self.rects[name]
        v = (b % pitch) / float(pitch)
        plate = np.clip(v / (1.0 - seam), 0, 1) ** 0.7
        plate = np.where(v > 1.0 - seam, 1.0 - (v - (1.0 - seam)) / seam, plate)
        crown = 0.72 + 0.28 * np.sin(math.pi * np.clip(a / max(1, a.max()), 0, 1))
        t = plate * crown + grad * (1.0 - 2 * np.abs(a / max(1, a.max()) - 0.5))
        rp_arr = np.array(rp, np.float32)
        f = np.clip(lo + (hi - lo) * np.clip(t, 0, 1), 0, 1) * (len(rp) - 1)
        i0 = np.clip(f.astype(int), 0, len(rp) - 2)
        k = (f - i0)[..., None]
        self.arr[y:y + h, x:x + w] = (rp_arr[i0] * (1 - k) + rp_arr[i0 + 1] * k).astype(np.uint8)

    def strands(self, name, rp, dir_, seed=0, pitch=3, wob=0.9, grad=0.0):
        """Hair: strands running downstream, wavy across, dark between them."""
        a, b = self._flow(name, dir_)
        x, y, w, h = self.rects[name]
        a2 = a.astype(np.float32) + wob * pitch * np.sin(b / (pitch * 3.5) + seed)
        s = (a2 % pitch) / float(pitch)
        core = 1.0 - 2.0 * np.abs(s - 0.5)
        shade = np.clip(core * 1.5 - 0.12, 0, 1)
        along = 0.72 + 0.28 * np.sin(b / (pitch * 2.2) + seed * 1.7)
        rng = (np.sin((a2 // pitch) * 41.7 + seed) * 17231.0) % 1.0
        t = shade * along * (0.80 + 0.34 * rng) + grad * 0.35
        rp_arr = np.array(rp, np.float32)
        f = np.clip(t, 0, 1) * (len(rp) - 1)
        i0 = np.clip(f.astype(int), 0, len(rp) - 2)
        k = (f - i0)[..., None]
        self.arr[y:y + h, x:x + w] = (rp_arr[i0] * (1 - k) + rp_arr[i0 + 1] * k).astype(np.uint8)

    def smooth(self, name, rp, dir_=None, grad=0.0, base=0.62):
        """A clean gradient along the flow (claws, horns, teeth)."""
        if dir_ is None:
            a, b = self._flow(name, "down")
        else:
            a, b = self._flow(name, dir_)
        x, y, w, h = self.rects[name]
        span = max(1, b.max())
        t = base + grad * (b / float(span) - 0.5) + 0.10 * np.sin(a * 1.9)
        rp_arr = np.array(rp, np.float32)
        f = np.clip(t, 0, 1) * (len(rp) - 1)
        i0 = np.clip(f.astype(int), 0, len(rp) - 2)
        k = (f - i0)[..., None]
        self.arr[y:y + h, x:x + w] = (rp_arr[i0] * (1 - k) + rp_arr[i0 + 1] * k).astype(np.uint8)

    def rings(self, name, rp, dir_="down", pitch=4):
        """Horn: growth rings across the length, brighter toward the tip."""
        a, b = self._flow(name, dir_)
        x, y, w, h = self.rects[name]
        v = (b % pitch) / float(pitch)
        ring = 0.55 + 0.45 * np.cos(2 * math.pi * v)
        span = max(1, b.max())
        t = 0.30 + 0.45 * (b / float(span)) + 0.22 * ring
        rp_arr = np.array(rp, np.float32)
        f = np.clip(t, 0, 1) * (len(rp) - 1)
        i0 = np.clip(f.astype(int), 0, len(rp) - 2)
        k = (f - i0)[..., None]
        self.arr[y:y + h, x:x + w] = (rp_arr[i0] * (1 - k) + rp_arr[i0 + 1] * k).astype(np.uint8)

    def radial(self, name, rp, lo=0.30, hi=1.0, power=1.1, rim=0.0):
        """A soft ball gradient from the rect's centre, for the pearl: without it
        an emissive cube renders as a flat yellow crate. `rim` darkens the outer
        ring, which is what makes it read as a sphere rather than a sticker."""
        x, y, w, h = self.rects[name]
        u = (np.arange(w)[None, :] + 0.5) / w * 2 - 1
        v = (np.arange(h)[:, None] + 0.5) / h * 2 - 1
        r = np.clip(np.sqrt(u * u + v * v) / 1.414, 0, 1)
        t = hi - (hi - lo) * (r ** power) - rim * np.clip((r - 0.72) / 0.28, 0, 1)
        rp_arr = np.array(rp, np.float32)
        f = np.clip(t, 0, 1) * (len(rp) - 1)
        i0 = np.clip(f.astype(int), 0, len(rp) - 2)
        k = (f - i0)[..., None]
        self.arr[y:y + h, x:x + w] = (rp_arr[i0] * (1 - k) + rp_arr[i0 + 1] * k).astype(np.uint8)

    def eye(self, name, mirror=False):
        """A loong eye: a slanted amber lens around a dark slit pupil, framed by
        a dark rim, with the specular highlight in the UPPER half. It is painted
        deliberately asymmetric -- a flipped uv would drop the highlight into the
        lower lid and the eye would read as dead, which is what makes it a uv
        canary as well as a face."""
        x, y, w, h = self.rects[name]
        slant = math.radians(16.0)
        for j in range(h):
            for i in range(w):
                ii = (w - 1 - i) if mirror else i
                u = (ii + 0.5) / w * 2 - 1
                v = (j + 0.5) / h * 2 - 1
                cs, sn = math.cos(slant), math.sin(slant)
                ur = u * cs - v * sn
                vr = u * sn + v * cs
                r = math.hypot(ur / 1.02, vr / 0.74)
                if r > 0.995:
                    c = ramp(GOLD, 0.34 + 0.16 * (1.0 - min(1.0, abs(v))))
                elif r > 0.90:
                    c = ramp(DARK, 0.06)
                else:
                    k = r / 0.90
                    slit = abs(ur + 0.06) < 0.13 + 0.09 * max(0.0, vr)
                    if slit and k < 0.92:
                        c = ramp(DARK, 0.02 + 0.10 * k)
                    elif k > 0.84:
                        c = ramp(MAW, 0.10 + 0.20 * (1 - k))
                    else:
                        c = ramp(GLOW, 0.34 + 0.50 * (1 - k) + 0.10 * max(0.0, -vr))
                    if math.hypot((u + 0.30) / 0.30, (v + 0.34) / 0.24) < 1.0:
                        c = ramp(GLOW, 1.0)
                    elif math.hypot((u - 0.34) / 0.17, (v - 0.30) / 0.15) < 1.0:
                        c = ramp(GLOW, 0.78)
                self.arr[y + j, x + i] = c
                self.alpha[y + j, x + i] = 255

    def save(self):
        img = Image.fromarray(self.arr, "RGB").convert("RGBA")
        img.putalpha(Image.fromarray(self.alpha, "L"))
        return img


def build_main_atlas():
    A = Atlas(RES)
    A.alpha[:, :] = 255
    return A


# ---------------------------------------------------------------------------
# 3. model description -- rest space is the animal laid out straight along +Z
#    (nose toward -Z), dorsal side +Y, right +X. The pose is applied later.
# ---------------------------------------------------------------------------

class Cube:
    __slots__ = ("g", "name", "frm", "to", "origin", "rot", "uv", "mark", "tex",
                 "faces")

    def __init__(self, g, name, frm, to, uv, mark, origin=None, rot=None, tex=0,
                 faces=None):
        self.g, self.name = g, name
        # every axis ascending: mirroring a right-hand part negates x, which
        # leaves from > to, and Blockbench wants a non-negative span
        self.frm = [float(min(frm[i], to[i])) for i in range(3)]
        self.to = [float(max(frm[i], to[i])) for i in range(3)]
        self.origin = [float(v) for v in (origin if origin is not None else
                                          ((frm[0] + to[0]) / 2,
                                           (frm[1] + to[1]) / 2,
                                           (frm[2] + to[2]) / 2))]
        self.rot = list(rot) if rot else [0.0, 0.0, 0.0]
        self.uv = uv                      # {face: [u1,v1,u2,v2]}
        self.mark = mark
        self.tex = tex
        self.faces = faces                # optional per-face overrides

    def dims(self):
        return (abs(self.to[0] - self.frm[0]), abs(self.to[1] - self.frm[1]),
                abs(self.to[2] - self.frm[2]))


class Group:
    def __init__(self, name, parent=None, origin=(0, 0, 0), rot=None):
        self.name, self.parent = name, parent
        self.origin = [float(v) for v in origin]
        self.rot = list(rot) if rot else [0.0, 0.0, 0.0]
        self.cubes = []
        self.children = []


class Model:
    def __init__(self):
        self.groups = {}
        self.order = []
        self.cubes = []

    def group(self, name, parent=None, origin=(0, 0, 0), rot=None):
        g = Group(name, parent, origin, rot)
        self.groups[name] = g
        self.order.append(name)
        if parent:
            self.groups[parent].children.append(g)
        return g

    def cube(self, gname, name, frm, to, uv, mark, origin=None, rot=None, tex=0,
             faces=None):
        c = Cube(gname, name, frm, to, uv, mark, origin, rot, tex, faces)
        self.cubes.append(c)
        self.groups[gname].cubes.append(c)
        return c

    def bar(self, gname, name, a, b, thick, width, uv, mark, tex=0, rot=None,
            faces=None):
        """A plate/tine running from point a to point b: authored unrotated along
        -Z hanging off `a` (which is also the pivot), then rotated by the
        minimal-roll euler that puts -Z on (b-a) -- bbmodel-format §12/§3."""
        a = np.array(a, float)
        b = np.array(b, float)
        d = b - a
        L = float(np.linalg.norm(d))
        d = d / L
        rx = math.degrees(math.asin(max(-1.0, min(1.0, d[1]))))
        ry = math.degrees(math.atan2(-d[0], -d[2]))
        frm = [a[0] - thick / 2, a[1] - width / 2, a[2] - L]
        to = [a[0] + thick / 2, a[1] + width / 2, a[2]]
        if rot is not None:
            rx, ry = rot[0], rot[1]
        return self.cube(gname, name, frm, to, uv, mark, origin=[float(v) for v in a],
                         rot=[rx, ry, 0.0], tex=tex, faces=faces)


def mirror_cube_within(model, src, dst_group, suffix):
    """Mirror a cube across x=0: swap the x extent and negate ry/rz (M.R.M leaves
    rx alone and flips the other two -- verified in the format notes)."""
    frm = [-src.to[0], src.frm[1], src.frm[2]]
    to = [-src.frm[0], src.to[1], src.to[2]]
    origin = [-src.origin[0], src.origin[1], src.origin[2]]
    rot = [src.rot[0], -src.rot[1], -src.rot[2]]
    faces = None
    if src.faces:
        faces = {}
        for k, v in src.faces.items():
            faces[MIRROR_FACE[k]] = dict(v)
    return model.cube(dst_group, src.name + suffix, frm, to, src.skin, src.mark,
                      origin=origin, rot=rot, tex=src.tex, faces=faces)


MIRROR_FACE = {"north": "north", "south": "south", "east": "west", "west": "east",
               "up": "up", "down": "down"}

# ---- spine stations -------------------------------------------------------
# (group, parent, joint z, box z0, box z1, half-width, half-height, y offset)
BODY_STATIONS = [
    ("body",    "loong",   16.0,   2.0,  32.0, 7.6, 7.2, 0.4),
    ("spine_1", "body",    32.0,  26.0,  38.0, 7.2, 6.8, 0.3),
    ("spine_2", "spine_1", 44.0,  38.0,  50.0, 6.7, 6.3, 0.3),
    ("spine_3", "spine_2", 56.0,  50.0,  62.0, 6.2, 5.8, 0.2),
    ("spine_4", "spine_3", 68.0,  62.0,  74.0, 5.6, 5.3, 0.2),
    ("spine_5", "spine_4", 80.0,  74.0,  86.0, 5.0, 4.7, 0.1),
    ("tail_1",  "spine_5", 92.0,  86.0,  98.0, 4.3, 4.0, 0.0),
    ("tail_2",  "tail_1", 104.0,  98.0, 110.0, 3.6, 3.4, 0.0),
    ("tail_3",  "tail_2", 115.0, 110.0, 120.0, 3.0, 2.8, 0.0),
    ("tail_4",  "tail_3", 126.0, 120.0, 131.0, 2.4, 2.3, 0.0),
    ("tail_5",  "tail_4", 136.0, 131.0, 141.0, 1.9, 1.8, 0.0),
    ("tail_6",  "tail_5", 146.0, 141.0, 150.0, 1.5, 1.4, 0.0),
    ("tail_fin", "tail_6", 152.0, 149.0, 156.0, 1.2, 1.1, 0.0),
]
NECK_STATIONS = [
    ("neck_1", "body",    6.0,  -4.0,   8.0, 6.4, 6.3, 0.3),
    ("neck_2", "neck_1", -4.0, -14.0,  -3.0, 5.9, 5.8, 0.3),
    ("neck_3", "neck_2", -14.0, -24.0, -13.0, 5.4, 5.3, 0.2),
    ("head",   "neck_3", -24.0, -49.0, -22.0, 6.0, 6.2, 1.0),
]
# arc length from the nose tip (z = -49) to each joint, for sampling the guide
S_NOSE = -49.0


def station_s(z):
    return z - S_NOSE


# ---------------------------------------------------------------------------
# 4. skins -- a cube's six faces, each its own rect, painted with the pattern
#    pointing tailward. Which way is "tailward" in a rect is fixed by how
#    Blockbench maps a uv rect onto a face (bbmodel-format §1/§2): +u is screen
#    right and +v screen down seen from outside, so for a box along Z the
#    north and east faces run +Z toward -u while south and west run +Z toward
#    +u, and the up/down faces split on v.
# ---------------------------------------------------------------------------

TAILWARD = {"north": "left", "south": "right", "east": "left", "west": "right",
            "up": "down", "down": "up"}


class SkinFactory:
    def __init__(self, atlas):
        self.A = atlas
        self.cache = {}

    def panel(self, name, w, h, kind):
        """A one-off rect a cube can point a single face at, for details that
        must NOT be geometry: nostril holes modelled as protruding cubes read as
        a second pair of eyes the moment the model is seen from above."""
        if name in self.A.rects:
            return self.A.rect(name)
        self.A.alloc(name, w, h)
        if kind == "nose":
            self.A.scales(name, GOLD, "down", seed=7, row=max(3, int(3 * PX)),
                          sw=max(4, int(4 * PX)), grad=-0.10)
            x, y, rw, rh = self.A.rects[name]
            for j in range(rh):
                for i in range(rw):
                    u = (i + 0.5) / rw
                    v = (j + 0.5) / rh
                    # low on the muzzle and small: two dark dots level with the
                    # brow read as a second pair of eyes
                    d = min(math.hypot((u - 0.30) / 0.11, (v - 0.74) / 0.13),
                            math.hypot((u - 0.70) / 0.11, (v - 0.74) / 0.13))
                    if d < 1.0:
                        self.A.arr[y + j, x + i] = ramp(DARK, 0.10 + 0.34 * d)
        else:
            raise KeyError(kind)
        return self.A.rect(name)

    def get(self, mat, dims, px=None):
        """Resolve a material + box size into {face: [u1,v1,u2,v2]}."""
        px = PX if px is None else px
        key = (mat, round(dims[0], 2), round(dims[1], 2), round(dims[2], 2), px)
        if key in self.cache:
            return self.cache[key]
        dx, dy, dz = dims
        uvs = {}
        for face in ("north", "south", "east", "west", "up", "down"):
            fw, fh = face_size(face, (0, 0, 0), (dx, dy, dz))
            w = max(1, int(round(fw * px)))
            h = max(1, int(round(fh * px)))
            nm = f"s{len(self.cache)}_{face}"
            self.A.alloc(nm, w, h)
            self._paint(mat, nm, face, px, w, h, len(self.cache))
            uvs[face] = self.A.rect(nm)
        self.cache[key] = uvs
        return uvs

    def _paint(self, mat, nm, face, px, w, h, seed):
        A = self.A
        d = TAILWARD[face]
        if mat == "eye":
            if face in ("east", "west"):
                A.eye(nm, mirror=(face == "west"))
            else:
                A.scales(nm, GOLD, d, seed=seed, row=max(3, int(1.5 * px)),
                         sw=max(4, int(2 * px)), grad=-0.35, lo=0.16, hi=0.60)
        elif mat == "gold":
            A.scales(nm, GOLD, d, seed=seed, row=max(3, int(3 * px)),
                     sw=max(4, int(4 * px)),
                     grad=0.30 if face in ("east", "west") else 0.0)
        elif mat == "goldflat":
            A.scales(nm, GOLD, d, seed=seed, row=max(3, int(2 * px)),
                     sw=max(4, int(3 * px)), grad=0.10)
        elif mat == "belly":
            A.bands(nm, IVORY, d, pitch=max(3, int(2.5 * px)), grad=0.18,
                    lo=0.18, hi=0.62)
        elif mat == "throat":
            A.bands(nm, IVORY, d, pitch=max(3, int(2.0 * px)), grad=0.14,
                    lo=0.10, hi=0.50)
        elif mat == "jade":
            A.strands(nm, JADE, d, seed=seed, pitch=max(2, int(1.5 * px)), grad=0.25)
        elif mat == "fin":
            A.strands(nm, JADE, d, seed=seed * 1.7, pitch=max(2, int(1.2 * px)),
                      wob=2.0, grad=0.30)
        elif mat == "horn":
            A.rings(nm, HORN, d, pitch=max(2, int(2 * px)))
        elif mat == "claw":
            A.smooth(nm, IVORY, d, grad=0.55, base=0.42)
        elif mat == "tooth":
            A.smooth(nm, IVORY, d, grad=0.22, base=0.86)
        elif mat == "maw":
            A.smooth(nm, MAW, d, grad=-0.30 if face in ("up", "down") else 0.12,
                     base=0.30)
        elif mat == "tongue":
            A.smooth(nm, MAW, d, grad=0.30, base=0.62)
        elif mat == "dark":
            A.smooth(nm, DARK, d, grad=0.25, base=0.30)
        elif mat == "nostril":
            A.smooth(nm, DARK, d, grad=0.20, base=0.42)
        elif mat == "darkgold":
            A.scales(nm, GOLD, d, seed=seed, row=max(3, int(2 * px)),
                     sw=max(4, int(3 * px)), grad=-0.55, lo=0.10, hi=0.52)
        elif mat == "glow":
            A.smooth(nm, GLOW, d, grad=0.34, base=0.42)
        elif mat == "glowhot":
            A.radial(nm, GLOW, lo=0.06, hi=1.0, power=0.80, rim=0.22)
        else:
            raise KeyError(mat)


# ---------------------------------------------------------------------------
# 5. geometry
# ---------------------------------------------------------------------------

BELLY = (-1.7, 1.2)          # a belly plate: below the core, poking out this far
DORSAL = [                   # (station z centre, half length, height) -- rhythm
    (20.0, 5.0, 9.0), (30.5, 4.8, 10.2), (41.0, 4.6, 9.6), (52.0, 4.4, 8.8),
    (63.0, 4.2, 7.8), (74.0, 3.8, 6.8), (85.0, 3.4, 6.0), (96.0, 3.0, 5.2),
    (107.0, 2.6, 4.4), (118.0, 2.2, 3.8), (129.0, 1.9, 3.2), (140.0, 1.6, 2.6),
    (149.0, 1.3, 2.2),
]


def build_body(M, S):
    for name, parent, jz, z0, z1, hw, hh, yo in BODY_STATIONS + NECK_STATIONS:
        M.group(name, parent, (0, 0, jz))
        if name == "head":
            continue
        M.cube(name, name + "_core", (-hw, yo - hh, z0), (hw, yo + hh, z1),
               S.get("gold", (2 * hw, 2 * hh, z1 - z0)), 1)
        # belly scutes: narrow enough that gold still frames them, and a muted
        # cream rather than white, or the whole animal reads as white-bellied
        if hh >= 2.6:
            bw = hw - (2.2 if hh > 5.0 else (1.7 if hh > 4.0 else 1.0))
            mat = "belly" if name in ("body", "spine_1", "spine_2", "spine_3",
                                      "spine_4") else "throat"
            skin = S.get(mat, (2 * bw, BELLY[1] - BELLY[0], z1 - z0 - 2.0))
            M.cube(name, name + "_belly", (-bw, yo - hh + BELLY[0], z0 + 1.0),
                   (bw, yo - hh + BELLY[1], z1 - 1.0), skin, 2)
    # the dorsal crest rides on whichever station owns each z
    for cz, bz, ht in DORSAL:
        st = next(s for s in BODY_STATIONS if s[3] <= cz <= s[4])
        _n, _p, _j, _z0, _z1, hw, hh, yo = st
        top = yo + hh
        tag = f"{st[0]}_fin{int(round(cz))}"
        skin = S.get("fin", (bz * 2, ht * 0.6, 1.4))
        M.cube(st[0], tag + "_base", (-0.7, top - 1.6, cz - bz),
               (0.7, top + ht * 0.50, cz + bz), skin, 3)
        M.bar(st[0], tag + "_tip", (0.0, top + ht * 0.44, cz - bz * 0.20),
              (0.0, top + ht, cz + bz * 0.50), 1.3, bz * 1.05, skin, 3)


def build_head(M, S):
    """Head local design, rest space: the joint is at z=-24 and the skull runs
    forward to the nose at z=-49, so the whole animal is authored straight.
    Built in steps -- crown over skull over snout over muzzle -- because a loong
    head that is one box reads as a box no matter what is painted on it."""
    g = "head"
    PK = 3                      # texels per unit: the face is what people look at

    # ---- the skull: crown / skull / brow, each step narrower ---------------
    M.cube(g, "h_skull", (-5.8, 0.4, -35.5), (5.8, 7.0, -22.0),
           S.get("gold", (11.6, 6.6, 13.5), PK), 1)
    M.cube(g, "h_crown", (-4.6, 6.6, -33.6), (4.6, 9.2, -23.2),
           S.get("gold", (9.2, 2.6, 10.4), PK), 1)
    M.cube(g, "h_brow", (-6.6, 4.4, -37.2), (6.6, 7.6, -33.2),
           S.get("gold", (13.2, 3.2, 4.0), PK), 1)
    # ---- the snout: two tapering steps then the muzzle --------------------
    M.cube(g, "h_snout", (-4.6, 1.2, -43.2), (4.6, 6.6, -34.6),
           S.get("gold", (9.2, 5.4, 8.6), PK), 1)
    M.cube(g, "h_snout_low", (-5.0, -1.8, -43.6), (5.0, 1.4, -34.6),
           S.get("gold", (10.0, 3.2, 9.0), PK), 1)
    M.cube(g, "h_muzzle", (-3.8, 1.8, -46.8), (3.8, 6.2, -42.8),
           S.get("gold", (7.6, 4.4, 4.0), PK), 1)
    M.cube(g, "h_nose", (-3.0, 2.4, -47.8), (3.0, 6.6, -46.4),
           S.get("gold", (6.0, 4.2, 1.4), PK), 1,
           faces={"north": {"uv": S.panel("nose_panel", int(6.0 * PK), int(4.2 * PK),
                                          "nose")}})
    M.cube(g, "h_lip", (-5.6, -2.6, -45.6), (5.6, 1.8, -38.2),
           S.get("gold", (11.2, 4.4, 7.4), PK), 1)
    # the maw: a thin dark roof proud of the lip's underside plus a 1.2 unit
    # gap to the tongue, so the mouth reads as a line that opens, not as a cave
    M.cube(g, "h_palate", (-4.4, -3.4, -45.6), (4.4, -2.2, -33.6),
           S.get("maw", (8.8, 1.2, 12.0), PK), 4)
    for sgn, sfx in ((1, "_R"), (-1, "_L")):
        # raised lip corners and the cheek mass that carries the jaw hinge
        M.cube(g, "h_lipcurl" + sfx, (sgn * 4.6, -2.4, -41.6), (sgn * 6.4, 2.8, -38.2),
               S.get("gold", (1.8, 5.2, 3.4), PK), 1)
        M.cube(g, "h_cheek" + sfx, (sgn * 4.6, -3.8, -36.0), (sgn * 7.0, 2.6, -23.0),
               S.get("gold", (2.4, 6.4, 13.0), PK), 1)
        # upper fangs hang well below the lip line; they are the read of "dragon"
        M.cube(g, "h_fang" + sfx, (sgn * 2.8, -6.4, -44.8), (sgn * 4.2, -2.2, -42.0),
               S.get("tooth", (1.4, 4.2, 2.8), PK), 2)
        # eye: a dark orbit band, a bulging eyeball proud of it, brow above
        M.cube(g, "h_orbit" + sfx, (sgn * 4.4, 0.6, -38.6), (sgn * 6.6, 6.4, -31.4),
               S.get("darkgold", (2.2, 5.8, 7.2), PK), 1)
        M.cube(g, "h_eye" + sfx, (sgn * 5.6, 1.4, -38.2), (sgn * 7.5, 6.0, -32.2),
               S.get("eye", (1.9, 4.6, 6.0), PK), 6)
        M.cube(g, "h_browridge" + sfx, (sgn * 4.4, 6.0, -38.8), (sgn * 6.9, 8.8, -33.0),
               S.get("gold", (2.5, 2.8, 5.8), PK), 1)
        # ear: a swept plate behind the antler
        M.bar(g, "h_ear" + sfx, (sgn * 6.0, 1.8, -24.4), (sgn * 8.8, 4.6, -17.4),
              0.8, 3.2, S.get("fin", (3.8, 0.8, 7.6), PK), 3)
        # cheek frill sweeping back and down off the jaw hinge
        M.bar(g, "h_frill" + sfx, (sgn * 6.2, -2.4, -30.6), (sgn * 8.6, -4.6, -19.4),
              0.8, 4.4, S.get("fin", (4.8, 0.8, 11.6), PK), 3)

    # ---- lower jaw: its own group so the maw can open ----------------------
    M.group("jaw", "head", (0, -2.6, -33.5), [0.0, 0.0, 0.0])
    M.cube("jaw", "j_body", (-4.4, -6.4, -45.0), (4.4, -4.4, -33.6),
           S.get("gold", (8.8, 2.0, 11.4), PK), 1)
    M.cube("jaw", "j_chin", (-3.6, -7.6, -44.4), (3.6, -5.6, -36.6),
           S.get("gold", (7.2, 2.0, 7.8), PK), 1)
    M.cube("jaw", "j_tongue", (-3.0, -4.5, -44.0), (3.0, -3.3, -34.6),
           S.get("tongue", (6.0, 1.2, 9.4), PK), 4)
    for sgn, sfx in ((1, "_R"), (-1, "_L")):
        M.cube("jaw", "j_side" + sfx, (sgn * 3.6, -5.6, -43.0), (sgn * 5.0, -3.2, -35.0),
               S.get("gold", (1.4, 2.4, 8.0), PK), 1)
        M.cube("jaw", "j_fang" + sfx, (sgn * 1.3, -5.0, -45.2), (sgn * 2.6, -2.6, -42.6),
               S.get("tooth", (1.3, 2.4, 2.6), PK), 2)

    # ---- antlers: the signature. Beam of three bars plus two tines ---------
    for sgn, sfx in ((1, "_R"), (-1, "_L")):
        M.group("antler" + sfx, "head", (sgn * 4.0, 8.4, -27.4))
        a0 = (sgn * 3.6, 7.6, -27.6)
        a1 = (sgn * 5.8, 12.6, -26.6)
        a2 = (sgn * 7.2, 17.2, -21.6)
        a3 = (sgn * 6.4, 21.0, -14.6)
        M.bar("antler" + sfx, "an_base" + sfx, a0, a1, 3.0, 3.0,
              S.get("horn", (3.0, 3.0, 5.4)), 2)
        M.bar("antler" + sfx, "an_mid" + sfx, a1, a2, 2.3, 2.3,
              S.get("horn", (2.3, 2.3, 6.4)), 2)
        M.bar("antler" + sfx, "an_tip" + sfx, a2, a3, 1.6, 1.6,
              S.get("horn", (1.6, 1.6, 6.8)), 2)
        M.bar("antler" + sfx, "an_tine1" + sfx, a1, (sgn * 8.6, 16.0, -31.6),
              1.5, 1.5, S.get("horn", (1.5, 1.5, 6.4)), 2)
        M.bar("antler" + sfx, "an_tine2" + sfx, a2, (sgn * 5.0, 21.8, -22.6),
              1.2, 1.2, S.get("horn", (1.2, 1.2, 5.4)), 2)

    # ---- whiskers: two chained pairs, thin and long, trailing back ---------
    for sgn, sfx in ((1, "_R"), (-1, "_L")):
        w0 = (sgn * 4.8, 1.0, -44.2)
        w1 = (sgn * 6.8, 1.8, -34.0)
        w2 = (sgn * 7.8, 4.4, -22.4)
        w3 = (sgn * 7.0, 7.4, -11.0)
        w4 = (sgn * 5.2, 9.4, 0.4)
        M.group("whisker" + sfx, "head", w0)
        M.bar("whisker" + sfx, "wh_1" + sfx, w0, w1, 1.0, 1.0,
              S.get("jade", (1.0, 1.0, 10.6)), 3)
        M.bar("whisker" + sfx, "wh_2" + sfx, w1, w2, 0.9, 0.9,
              S.get("jade", (0.9, 0.9, 12.2)), 3)
        M.group("whisker2" + sfx, "whisker" + sfx, w2)
        M.bar("whisker2" + sfx, "wh_3" + sfx, w2, w3, 0.8, 0.8,
              S.get("jade", (0.8, 0.8, 12.0)), 3)
        M.bar("whisker2" + sfx, "wh_4" + sfx, w3, w4, 0.7, 0.7,
              S.get("jade", (0.7, 0.7, 11.6)), 3)

    # ---- mane: a crest that hugs the neck, in two layered rows -------------
    M.group("mane", "head", (0, 8.0, -25.0))
    MANE = ((-4.8, 7.0, -25.6, -6.2, 4.2), (-2.8, 8.6, -26.2, -3.6, 5.0),
            (-0.6, 9.2, -26.4, -0.8, 5.4), (1.6, 8.8, -26.2, 2.4, 5.0),
            (3.6, 7.4, -25.6, 5.2, 4.4), (5.2, 6.0, -24.6, 7.0, 3.8))
    for i, (x0, y0, z0, x1, wid) in enumerate(MANE):
        ln = 10.0 + (i % 3) * 2.0
        p0 = (x0, y0, z0)
        p1 = (x0 + (x1 - x0) * 0.5, y0 - 1.4, z0 + ln * 0.55)
        p2 = (x1, y0 - 3.0, z0 + ln)
        M.bar("mane", f"mane_{i}a", p0, p1, 0.8, wid,
              S.get("jade", (0.8, wid, ln * 0.6)), PK)
        M.bar("mane", f"mane_{i}b", p1, p2, 0.7, wid * 0.78,
              S.get("jade", (0.7, wid * 0.78, ln * 0.6)), PK)
    M.group("neck_frill", "neck_2", (0, -6.0, -6.0))
    for i, sx in enumerate((-4.6, -1.8, 1.8, 4.6)):
        ln = 9.0 + (i % 2) * 2.2
        p0 = (sx, -6.4, -8.0)
        p1 = (sx * 1.4, -8.2, 1.0)
        p2 = (sx * 1.8, -8.4, 1.0 + ln)
        M.bar("neck_frill", f"nrill_{i}a", p0, p1, 0.8, 2.6,
              S.get("jade", (0.8, 2.6, 9.4)), PK)
        M.bar("neck_frill", f"nrill_{i}b", p1, p2, 0.7, 2.2,
              S.get("jade", (0.7, 2.2, 9.6)), PK)
    # beard under the chin, hung off the jaw so it moves with the maw
    M.group("beard", "jaw", (0, -8.0, -40.0))
    for i, sx in enumerate((-2.2, 0.0, 2.2)):
        ln = 7.5 + (2.0 if i == 1 else 0.0)
        p0 = (sx, -8.2, -40.8)
        p1 = (sx * 1.3, -10.6, -34.0)
        p2 = (sx * 1.6, -11.0, -34.0 + ln)
        M.bar("beard", f"beard_{i}a", p0, p1, 0.8, 2.2,
              S.get("jade", (0.8, 2.2, 6.6)), PK)
        M.bar("beard", f"beard_{i}b", p1, p2, 0.7, 1.8,
              S.get("jade", (0.7, 1.8, 7.4)), PK)


# legs: rest space hangs them straight down; the pose aims each bone. Both legs
# are given a real Z-bend (elbow back then forearm forward, knee back then shank
# forward) because a straight limb reads as a table leg, not an animal.
FRONT_LEG = {           # name -> (pivot, world bone direction, front hint)
    "upper": ((7.2, -3.0, 16.0), (0.26, -0.74, 0.62), (0.10, -0.40, -0.91)),
    "fore":  ((7.2, -18.0, 16.0), (0.13, -0.77, -0.63), (0.06, -0.40, -0.92)),
    "paw":   ((7.2, -30.0, 16.0), (0.03, -0.63, -0.78), (0.00, -0.30, -0.95)),
}
HIND_LEG = {
    "thigh": ((5.2, -2.6, 68.0), (0.30, -0.60, 0.74), (0.00, 0.20, -0.98)),
    "shank": ((5.2, -17.0, 68.0), (0.15, -0.88, -0.45), (0.00, 0.05, -1.00)),
    "foot":  ((5.2, -29.0, 68.0), (0.04, -0.68, -0.73), (0.00, -0.25, -0.97)),
}


def build_legs(M, S):
    for is_right in (True, False):
        sfx = "_R" if is_right else "_L"
        sgn = 1 if is_right else -1
        # ---- front ----
        M.group("fleg_a" + sfx, "body",
                (sgn * FRONT_LEG["upper"][0][0], *FRONT_LEG["upper"][0][1:]))
        M.cube("fleg_a" + sfx, "fl_shoulder" + sfx, (sgn * 4.2, -9.6, 11.4),
               (sgn * 10.8, 0.8, 20.6), S.get("gold", (6.6, 10.4, 9.2)), 1)
        M.cube("fleg_a" + sfx, "fl_upper" + sfx, (sgn * 5.0, -18.4, 12.8),
               (sgn * 9.8, -6.0, 19.2), S.get("gold", (4.8, 12.4, 6.4)), 1)
        M.group("fleg_b" + sfx, "fleg_a" + sfx,
                (sgn * FRONT_LEG["fore"][0][0], *FRONT_LEG["fore"][0][1:]))
        M.cube("fleg_b" + sfx, "fl_knee" + sfx, (sgn * 5.2, -20.8, 12.6),
               (sgn * 9.6, -15.4, 18.6), S.get("gold", (4.4, 5.4, 6.0)), 1)
        M.cube("fleg_b" + sfx, "fl_fore" + sfx, (sgn * 5.6, -30.4, 13.8),
               (sgn * 9.4, -18.8, 18.2), S.get("gold", (3.8, 11.6, 4.4)), 1)
        M.group("fleg_c" + sfx, "fleg_b" + sfx,
                (sgn * FRONT_LEG["paw"][0][0], *FRONT_LEG["paw"][0][1:]))
        M.cube("fleg_c" + sfx, "fl_paw" + sfx, (sgn * 4.8, -34.4, 11.2),
               (sgn * 9.6, -28.8, 19.2), S.get("gold", (4.8, 5.6, 8.0)), 1)
        M.cube("fleg_c" + sfx, "fl_sole" + sfx, (sgn * 5.0, -34.8, 12.4),
               (sgn * 9.4, -32.4, 18.6), S.get("darkgold", (4.4, 2.4, 6.2)), 1)
        claws(M, S, "fleg_c" + sfx, sgn, base=(sgn * 7.2, -32.8, 11.4),
              n=4, spread=1.85, scale=1.08)
        M.bar("fleg_b" + sfx, "fl_elbowfin" + sfx, (sgn * 6.0, -19.4, 18.6),
              (sgn * 6.0, -13.0, 25.4), 0.8, 4.0,
              S.get("fin", (4.0, 0.8, 7.6)), 3)
        # ---- hind ----
        M.group("hleg_a" + sfx, "spine_4",
                (sgn * HIND_LEG["thigh"][0][0], *HIND_LEG["thigh"][0][1:]))
        M.cube("hleg_a" + sfx, "hl_haunch" + sfx, (sgn * 3.0, -10.6, 61.0),
               (sgn * 9.8, 1.0, 74.4), S.get("gold", (6.8, 11.6, 13.4)), 1)
        M.cube("hleg_a" + sfx, "hl_thigh" + sfx, (sgn * 3.6, -17.8, 63.0),
               (sgn * 9.0, -7.0, 72.6), S.get("gold", (5.4, 10.8, 9.6)), 1)
        M.group("hleg_b" + sfx, "hleg_a" + sfx,
                (sgn * HIND_LEG["shank"][0][0], *HIND_LEG["shank"][0][1:]))
        M.cube("hleg_b" + sfx, "hl_knee" + sfx, (sgn * 3.6, -20.4, 63.2),
               (sgn * 8.6, -14.8, 71.8), S.get("gold", (5.0, 5.6, 8.6)), 1)
        M.cube("hleg_b" + sfx, "hl_shank" + sfx, (sgn * 4.2, -29.4, 64.4),
               (sgn * 8.0, -18.6, 70.8), S.get("gold", (3.8, 10.8, 6.4)), 1)
        M.group("hleg_c" + sfx, "hleg_b" + sfx,
                (sgn * HIND_LEG["foot"][0][0], *HIND_LEG["foot"][0][1:]))
        M.cube("hleg_c" + sfx, "hl_foot" + sfx, (sgn * 3.8, -33.4, 61.6),
               (sgn * 8.2, -28.2, 70.2), S.get("gold", (4.4, 5.2, 8.6)), 1)
        M.cube("hleg_c" + sfx, "hl_sole" + sfx, (sgn * 4.0, -33.8, 62.6),
               (sgn * 8.0, -31.2, 69.4), S.get("darkgold", (4.0, 2.6, 6.8)), 1)
        claws(M, S, "hleg_c" + sfx, sgn, base=(sgn * 6.0, -31.8, 61.7),
              n=3, spread=1.7, scale=1.0)
        M.bar("hleg_b" + sfx, "hl_hipfin" + sfx, (sgn * 5.4, -19.0, 71.4),
              (sgn * 5.4, -13.0, 78.4), 0.8, 3.8, S.get("fin", (3.8, 0.8, 7.8)), 3)


def claws(M, S, g, sgn, base, n, spread, scale):
    """Curved claws off the front of a paw: a base bar then a tip bar turned
    further down, so each claw reads as a hook rather than a spike."""
    cx, cy, cz = base
    for i in range(n):
        off = (i - (n - 1) / 2.0) * spread
        a = (cx + off * sgn, cy - 0.6 * scale, cz)
        b = (cx + off * 1.12 * sgn, cy - 2.4 * scale, cz - 3.6 * scale)
        c = (cx + off * 1.2 * sgn, cy - 3.4 * scale, cz - 6.6 * scale)
        M.bar(g, f"{g}_claw{i}a", a, b, 1.5 * scale, 1.5 * scale,
              S.get("claw", (1.5, 1.5, 4.2)), 2)
        M.bar(g, f"{g}_claw{i}b", b, c, 1.1 * scale, 1.1 * scale,
              S.get("claw", (1.1, 1.1, 3.4)), 2)


def build_tail_fin(M, S, SG):
    """A flame fan at the tail tip -- the loong's 火焰尾. The two outer blades
    are emissive so the tip reads as fire rather than as more mane."""
    g = "tail_fin"
    for i, (ang, thick, ln) in enumerate(((62, 0.9, 11.0), (30, 1.0, 14.5),
                                          (-4, 1.0, 15.5), (-38, 0.9, 12.5))):
        r = math.radians(ang)
        a = (0.0, 0.0, 150.0)
        b = (0.0, math.sin(r) * ln, 150.0 + math.cos(r) * ln)
        glow = i in (0, 3)
        M.bar(g, f"tfin_{i}", a, b, thick, 6.8 - abs(ang) * 0.035,
              SG.get("glow", (6.4, 1.0, ln)) if glow else S.get("fin", (6.4, 1.0, ln)),
              6 if glow else 3, tex=1 if glow else 0)
    for i, sx in enumerate((-2.2, 0.0, 2.2)):
        a = (sx, 0.0, 147.0)
        b = (sx * 1.6, -1.4, 166.0 + (2.5 if i == 1 else 0.0))
        M.bar(g, f"tstrand_{i}", a, b, 0.8, 1.9, S.get("jade", (0.8, 1.9, 19.2)), 3)


def build_pearl(M, SG, at):
    """The flaming pearl the loong chases: one bright core with a comet tail of
    three petals trailing behind it (a symmetric four-petal star reads as a UI
    icon, not as a pearl). Emissive, in its own root-level group so it holds
    still while the body swims through the pose."""
    M.group("pearl", "loong", at)
    M.cube("pearl", "p_core", (-3.8, -3.8, -3.8), (3.8, 3.8, 3.8),
           SG.get("glowhot", (7.6, 7.6, 7.6)), 6, tex=1)
    # a comet trail of petals, and two flame licks that clear the core's silhouette
    for i, (dx, dy, dz, ln) in enumerate(((0.0, 0.30, 1.0, 13.0), (0.0, -0.55, 1.0, 9.0),
                                          (0.0, 0.85, 0.9, 7.5))):
        M.bar("pearl", f"p_tail{i}", (dx * 3.0, dy * 3.0, dz * 3.0),
              (dx * 3.0 + 0.6 * (1 - i), dy * 3.0 + 0.60 * ln, dz * 3.0 + 0.78 * ln),
              2.2, 2.2, SG.get("glow", (2.2, 2.2, ln * 0.5)), 6, tex=1)
    for i, (ax, ay) in enumerate(((-1.0, 0.35), (1.0, 0.35))):
        M.bar("pearl", f"p_lick{i}", (ax * 3.4, ay * 3.4, -1.0),
              (ax * 7.6, ay * 8.2, -6.2), 2.4, 2.4,
              SG.get("glow", (2.4, 2.4, 6.4)), 6, tex=1)


# ---------------------------------------------------------------------------
# 6. pose -- one guide curve from the nose to the tail tip. Each joint samples
#    the tangent there and builds a minimal-roll frame; the local rotation then
#    falls out of the parent chain as R_local = R_parent^-1 . R_world.
# ---------------------------------------------------------------------------

SONE = np.array([0.0, 1.0, 0.0])
SZ = np.array([0.0, 0.0, 1.0])
SDOWN = np.array([0.0, -1.0, 0.0])

GUIDE = [                       # (x, y, z), nose first: a soaring S
    (0.0, 74.0, -76.0),
    (0.0, 72.0, -58.0),
    (-2.0, 64.0, -42.0),
    (-5.0, 50.0, -30.0),
    (-9.0, 34.0, -20.0),
    (-13.0, 21.0, -6.0),
    (-15.0, 17.0, 14.0),
    (-13.0, 24.0, 34.0),
    (-7.0, 38.0, 50.0),
    (3.0, 52.0, 60.0),
    (14.0, 62.0, 62.0),
    (23.0, 68.0, 56.0),
    (28.0, 72.0, 44.0),
]


def frame_from(p, a, s, b):
    """Rotation taking rest axis p to world a and rest axis s to world b
    (b orthogonalised against a). Both bases are right-handed, so det = +1."""
    a = unit(np.array(a, float))
    b = np.array(b, float)
    b = b - b.dot(a) * a
    if np.linalg.norm(b) < 1e-6:
        b = np.array([0.0, 1.0, 0.0]) - a[1] * a
    b = unit(b)
    P = np.column_stack([p, s, np.cross(p, s)])
    W = np.column_stack([a, b, np.cross(a, b)])
    return W @ P.T


def catmull_rom(pts, per=40):
    p = [np.array(pts[0], float)] + [np.array(q, float) for q in pts] + \
        [np.array(pts[-1], float)]
    out = []
    for i in range(len(pts) - 1):
        p0, p1, p2, p3 = p[i], p[i + 1], p[i + 2], p[i + 3]
        for k in range(per):
            t = k / per
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t
                              + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                              + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    out.append(np.array(pts[-1], float))
    poly = np.array(out)
    seg = np.linalg.norm(np.diff(poly, axis=0), axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    return poly, cum


def curve_at(table, s):
    poly, cum = table
    s = max(0.0, min(cum[-1] - 1e-6, s))
    i = int(np.searchsorted(cum, s) - 1)
    i = max(0, min(len(poly) - 2, i))
    span = max(1e-9, cum[i + 1] - cum[i])
    k = (s - cum[i]) / span
    pos = poly[i] * (1 - k) + poly[i + 1] * k
    tan = unit(poly[i + 1] - poly[i])
    return pos, tan


def solve_pose(M):
    """Fill in every group rotation; return {group: [rx, ry, rz]} in degrees."""
    table = catmull_rom(GUIDE)
    L = table[1][-1]
    S_TOTAL = 156.0 - S_NOSE
    rot = {}

    def world_for(gname):
        g = M.groups[gname]
        z = g.origin[2]
        s = (z - S_NOSE) / S_TOTAL * L
        _, tan = curve_at(table, s)
        return frame_from(SZ, tan, SONE, SONE)

    order = [s[0] for s in BODY_STATIONS] + [s[0] for s in NECK_STATIONS]
    world = {}
    for gname in order + ["loong"]:
        world[gname] = (np.eye(3) if gname == "loong"
                        else world_for(gname))
    # the head carries a deliberate nose-up tilt off the neck's tangent
    world["head"] = world["head"] @ rot_ZYX(-9.0, 0.0, 0.0)
    for gname in order:
        g = M.groups[gname]
        par = world[g.parent]
        rot[gname] = [round(v, 6) for v in euler_ZYX(par.T @ world[gname])]
    # the jaw hangs off the head: a pure local nod, so the maw can be keyed open
    rot["jaw"] = [-13.0, 0.0, 0.0]
    # legs: aim each bone in world space, then convert into its parent's frame
    for sfx in ("_R", "_L"):
        for tag, spec, hip, bones in (("fleg", FRONT_LEG, "body", ("upper", "fore", "paw")),
                                      ("hleg", HIND_LEG, "spine_4", ("thigh", "shank", "foot"))):
            parent_world = world[hip]
            for bi, bone in enumerate(bones):
                bdir = np.array(spec[bone][1], float)
                hint = np.array(spec[bone][2], float)
                if sfx == "_L":
                    bdir = bdir * np.array([-1.0, 1.0, 1.0])
                    hint = hint * np.array([-1.0, 1.0, 1.0])
                Rw = frame_from(SDOWN, bdir, np.array([0.0, 0.0, -1.0]), hint)
                gname = f"{tag}_{'abc'[bi]}{sfx}"
                rot[gname] = [round(v, 6) for v in euler_ZYX(parent_world.T @ Rw)]
                world[gname] = Rw
                parent_world = Rw
    return rot


def as_tree(M, rot):
    def node(gname):
        g = M.groups[gname]
        return {"name": g.name, "origin": g.origin, "rotation": rot.get(gname, g.rot),
                "cubes": [{"name": c.name, "from": c.frm, "to": c.to}
                          for c in g.cubes],
                "children": [node(c.name) for c in g.children]}
    return node("loong")


def posed_boxes(tree):
    out = []
    for path, c, R, t in walk_groups(tree):
        f, to = c["from"], c["to"]
        cs = np.array([R @ V(x, y, z) + t
                       for x in (f[0], to[0]) for y in (f[1], to[1])
                       for z in (f[2], to[2])])
        out.append((path, cs.min(axis=0), cs.max(axis=0)))
    return out


VIEWS = [("side (dragon's left, tail right)", (2, +1, 1, +1)),
         ("front (nose on)", (0, -1, 1, +1)),
         ("top", (0, +1, 2, -1))]


def silhouette(boxes, path, W=1320, H=460):
    """Cheap orthographic check of the pose before spending a real render: three
    views of the posed boxes, same scale, so the silhouette can be judged."""
    img = Image.new("RGB", (W, H), (24, 22, 28))
    px = img.load()
    proj = []
    for label, (ha, hs, va, vs) in VIEWS:
        rows = []
        for _p, bmin, bmax in boxes:
            x0, x1 = hs * bmin[ha], hs * bmax[ha]
            y0, y1 = vs * bmin[va], vs * bmax[va]
            rows.append((min(x0, x1), max(x0, x1), min(y0, y1), max(y0, y1)))
        proj.append((label, rows))
    allr = [r for _l, rows in proj for r in rows]
    xlo = min(r[0] for r in allr)
    xhi = max(r[1] for r in allr)
    ylo = min(r[2] for r in allr)
    yhi = max(r[3] for r in allr)
    pad = 16
    scale = min((W / 3.0 - 2 * pad) / max(1e-6, xhi - xlo),
                (H - 2 * pad - 14) / max(1e-6, yhi - ylo))
    for vi, (label, rows) in enumerate(proj):
        ox = vi * W / 3.0 + pad
        oy = H - pad - 14
        for (x0, x1, y0, y1) in rows:
            sx0 = int(ox + (x0 - xlo) * scale)
            sx1 = int(ox + (x1 - xlo) * scale)
            sy1 = int(oy - (y0 - ylo) * scale)
            sy0 = int(oy - (y1 - ylo) * scale)
            shade = 96 + int(74 * min(1.0, (y1 - y0) / 14.0))
            for yy in range(max(0, sy0), min(H, sy1 + 1)):
                for xx in range(max(0, sx0), min(W, sx1 + 1)):
                    px[xx, yy] = (shade, shade - 16, shade - 30)
    img.save(path)
    return path


def place(M, tree):
    """Drop the posed model onto y=0 and centre it, by translating every cube and
    every pivot by the same vector -- rotations about origins are unaffected."""
    boxes = posed_boxes(tree)
    lo = np.min([b[1] for b in boxes], axis=0)
    hi = np.max([b[2] for b in boxes], axis=0)
    shift = np.array([-(lo[0] + hi[0]) / 2.0, -lo[1], -(lo[2] + hi[2]) / 2.0])
    for g in M.groups.values():
        g.origin = [g.origin[i] + shift[i] for i in range(3)]
    for c in M.cubes:
        c.frm = [c.frm[i] + shift[i] for i in range(3)]
        c.to = [c.to[i] + shift[i] for i in range(3)]
        c.origin = [c.origin[i] + shift[i] for i in range(3)]
    return shift, lo + shift, hi + shift


# ---------------------------------------------------------------------------
# 7. emit through the MCP
# ---------------------------------------------------------------------------

def cube_faces(c):
    out = {}
    for f in FACES:
        out[f] = {"uv": list(c.uv[f]), "texture": c.tex}
    for f, ov in (c.faces or {}).items():
        out[f].update(ov)
    return out


def fix(v):
    return [round(float(x), 4) for x in v]


def mirror_report(M, tol=1e-6):
    """The MCP's mirror gate compares WORLD boxes, and this pose deliberately
    drifts in X so the animal is not symmetric about x=0 on screen. The invariant
    that actually has to hold is the authored one: every _L cube is its _R twin
    mirrored across x=0 (negated x extent, rx kept, ry/rz negated). Checked here
    exactly, in rest space, where it is a real gate."""
    bad = []
    pairs = 0
    for c in M.cubes:
        if not c.name.endswith("_L"):
            continue
        twin = next((o for o in M.cubes if o.name == c.name[:-2] + "_R"), None)
        if twin is None:
            bad.append(f"{c.name}: no _R twin")
            continue
        pairs += 1
        want_frm = [-twin.to[0], twin.frm[1], twin.frm[2]]
        want_to = [-twin.frm[0], twin.to[1], twin.to[2]]
        # compare the rotations as matrices: the euler triple is not unique
        # (ry=180 and ry=-180 are the same rotation), the matrix is
        want_R = rot_ZYX(twin.rot[0], -twin.rot[1], -twin.rot[2])
        got_R = rot_ZYX(*c.rot)
        if (max(abs(a - b) for a, b in zip(c.frm, want_frm)) > tol
                or max(abs(a - b) for a, b in zip(c.to, want_to)) > tol
                or np.max(np.abs(want_R - got_R)) > 1e-9):
            bad.append(c.name)
    return f"{pairs} left/right pairs, all exact mirrors" if not bad else \
        f"MISMATCH {bad}"


def send(client, name, args):
    r = client.call(name, args)
    if r.get("isError"):
        txt = " ".join(b.get("text", "") for b in (r.get("content") or []))
        raise SystemExit(f"{name} failed: {txt[:1200]}")
    return r


def send_ops(client, path, ops, batch=400, log=print):
    for i in range(0, len(ops), batch):
        send(client, "bbmodel_edit", {"file": path, "operations": ops[i:i + batch]})
        log(f"    ops {i}..{min(len(ops), i + batch)}")


# ---------------------------------------------------------------------------
# 8. the fly cycle: a wave travelling nose -> tail, everything behind it lagging
# ---------------------------------------------------------------------------

S_TOTAL = 156.0 - S_NOSE
CHAIN = ["head", "neck_3", "neck_2", "neck_1", "body"] + \
        [s[0] for s in BODY_STATIONS[1:]]


def joint_s(gname):
    for name, _p, jz, *_r in BODY_STATIONS + NECK_STATIONS:
        if name == gname:
            return jz - S_NOSE
    return 0.0


def fly_ops(rot, T=3.0, N=13, anim="animation.golden_loong.fly"):
    ops = [{"op": "add_animation", "name": anim, "length": T, "loop": "loop",
            "snapping": 24}]

    def key(bone, chan, t, val):
        ops.append({"op": "set_keyframe", "animation": anim, "bone": bone,
                    "channel": chan, "time": round(t, 4), "value": fix(val),
                    "interpolation": "catmullrom"})

    def times():
        return [T * k / (N - 1) for k in range(N)]

    for g in CHAIN:
        frac = min(1.0, joint_s(g) / S_TOTAL)
        ph = 2 * math.pi * 1.55 * frac          # 1.55 waves along the body
        amp = 1.1 + 7.6 * frac                  # the wave grows toward the tail
        e = rot.get(g, [0.0, 0.0, 0.0])
        for t in times():
            w = 2 * math.pi * t / T
            key(g, "rotation", t, [e[0] + amp * 0.85 * math.sin(w - ph),
                                   e[1] + amp * 0.50 * math.sin(w - ph + math.pi / 2),
                                   e[2]])
    for sfx, lag in (("_R", 0.0), ("_L", 0.35)):
        for tag, base_ph in (("fleg", 0.25), ("hleg", 0.75)):
            for bi, bl in enumerate("abc"):
                g = f"{tag}_{bl}{sfx}"
                e = rot.get(g, [0.0, 0.0, 0.0])
                for t in times():
                    w = 2 * math.pi * t / T
                    key(g, "rotation", t,
                        [e[0] + (6.5 - 1.4 * bi) * math.sin(w + 2 * math.pi * base_ph + lag),
                         e[1], e[2]])
    # trailing parts lag the head, which is what makes the motion read as one animal
    for g, amp, delay, chan in (("mane", 4.5, 0.60, "rotation"),
                                ("neck_frill", 4.0, 0.75, "rotation"),
                                ("beard", 5.0, 0.55, "rotation"),
                                ("whisker_R", 6.5, 0.95, "rotation"),
                                ("whisker_L", 6.5, 0.95, "rotation"),
                                ("whisker2_R", 5.5, 1.30, "rotation"),
                                ("whisker2_L", 5.5, 1.30, "rotation"),
                                ("antler_R", 2.0, 0.40, "rotation"),
                                ("antler_L", 2.0, 0.40, "rotation")):
        for t in times():
            w = 2 * math.pi * t / T
            key(g, "rotation", t, [amp * math.sin(w - delay),
                                   amp * 0.6 * math.sin(w - delay + 1.1), 0.0])
    jaw_e = rot.get("jaw", [-13.0, 0.0, 0.0])
    for t in times():
        w = 2 * math.pi * t / T
        key("jaw", "rotation", t, [jaw_e[0] + 3.4 * math.sin(2 * w - 0.5), 0.0, 0.0])
    for t in times():
        w = 2 * math.pi * t / T
        key("loong", "position", t, [0.0, 1.8 * math.sin(w), 0.0])
        key("pearl", "position", t, [0.0, 2.6 * math.sin(w + 1.0), 0.0])
        s = 1.0 + 0.06 * math.sin(w * 2.0 + 0.4)
        key("pearl", "scale", t, [s, s, s])
    return ops


# ---------------------------------------------------------------------------
# 9. main
# ---------------------------------------------------------------------------

def main():
    A = build_main_atlas()
    AG = Atlas(RES, bg=(0, 0, 0))
    AG.alpha[:, :] = 255
    S, SG = SkinFactory(A), SkinFactory(AG)

    M = Model()
    M.group("loong", None, (0, 0, 0))
    build_body(M, S)
    build_head(M, S)
    build_legs(M, S)
    build_tail_fin(M, S, SG)

    rot = solve_pose(M)
    tree = as_tree(M, rot)
    boxes = posed_boxes(tree)
    box = [b for b in boxes if b[0].endswith("/h_skull")]
    skull = box[0]
    hc = (skull[1] + skull[2]) / 2.0
    print(f"[pose] head centre pre-shift {np.round(hc, 1)}")
    # the pearl hangs in the gap under the muzzle, above the reaching paws
    build_pearl(M, SG, (hc[0] + 1.5, hc[1] - 25.0, hc[2] - 10.0))

    tree = as_tree(M, rot)
    boxes = posed_boxes(tree)
    silhouette(boxes, os.path.join(PROPERTY, "_cmp", "loong_silhouette.png"))

    # the authored mirror relation has to be checked before place(), which
    # translates everything by a vector that is not itself symmetric in x
    mir = mirror_report(M)
    shift, blo, bhi = place(M, tree)
    tree = as_tree(M, rot)
    boxes = posed_boxes(tree)
    lo = np.min([b[1] for b in boxes], axis=0)
    hi = np.max([b[2] for b in boxes], axis=0)

    # ---- structural gates this side of the wire ---------------------------
    thin = [c.name for c in M.cubes if min(c.dims()) < 0.35]
    bad = [c.name for c in M.cubes if any(c.to[i] <= c.frm[i] for i in range(3))]
    names = [c.name for c in M.cubes]
    dups = sorted({n for n in names if names.count(n) > 1})
    print(f"[geom] cubes={len(M.cubes)} groups={len(M.groups)} "
          f"size={np.round(hi - lo, 1).tolist()} min_y={round(lo[1], 3)}")
    print(f"[geom] thin(<0.35)={thin or 'none'} inverted={bad or 'none'} "
          f"dup_names={dups or 'none'}")
    print(f"[mirror] {mir}")
    print(f"[uv] atlas rects={len(A.rects)} used_area="
          f"{sum(w * h for _x, _y, w, h in A.rects.values())} of {RES * RES}")

    A.finalize()
    AG.finalize()
    A.save().save(TEX_MAIN)
    AG.save().save(TEX_GLOW)
    print(f"[tex] wrote {TEX_MAIN} and {TEX_GLOW}")

    # ---- author it through the local MCP ---------------------------------
    client = Client(timeout=900)
    try:
        send(client, "bbmodel_create", {"file": BBMODEL, "format": "free",
                                        "name": MODEL, "overwrite": True,
                                        "resolution": {"width": RES, "height": RES}})
        send(client, "bbmodel_add_texture", {"file": BBMODEL, "image": TEX_MAIN,
                                             "name": MODEL + "_body.png"})
        send(client, "bbmodel_add_texture", {"file": BBMODEL, "image": TEX_GLOW,
                                             "name": MODEL + "_glow.png",
                                             "render_mode": "emissive"})
        gops = []
        for gname in M.order:
            g = M.groups[gname]
            op = {"op": "add_group", "name": g.name, "origin": fix(g.origin),
                  "rotation": fix(rot.get(gname, g.rot))}
            if g.parent:
                op["parent"] = g.parent
            gops.append(op)
        send_ops(client, BBMODEL, gops)
        cops = [{"op": "add_cube", "name": c.name, "from": fix(c.frm),
                 "to": fix(c.to), "origin": fix(c.origin), "rotation": fix(c.rot),
                 "parent": c.g, "box_uv": False, "faces": cube_faces(c)}
                for c in M.cubes]
        send_ops(client, BBMODEL, cops)
        aops = fly_ops(rot)
        send_ops(client, BBMODEL, aops)
        print(f"[mcp] authored groups={len(gops)} cubes={len(cops)} anim_ops={len(aops)}")
    finally:
        client.close()
    print(f"[done] {BBMODEL}")


if __name__ == "__main__":
    main()
