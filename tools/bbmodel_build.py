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
import re
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


def cube(name, frm, to, facemap, rot=None, origin=None, inflate=0.0):
    """A box. The two corners may be given in either order -- they are sorted,
    so a mirrored part can be authored with one expression while its twin uses
    the negated one (-sx * a, -sx * b) without coming out inside-out.

    `rot` / `origin` put a rotation on the ELEMENT (`rot` in degrees, ZYX order,
    about `origin`, default the box centre). Element rotation is what lets a
    limb be a chain of segments that each hinge on the joint above them; a
    group would work too, but a group's rotation is what animations key, so a
    rest angle there gets overwritten by the first keyframe."""
    if rot:
        if origin is None:
            origin = [(a + b) / 2 for a, b in zip(frm, to)]
        rot = [float(v) for v in rot]
    return {"name": name,
            "from": tuple(min(a, b) for a, b in zip(frm, to)),
            "to": tuple(max(a, b) for a, b in zip(frm, to)),
            "faces": facemap,
            "rotation": rot,
            "origin": [float(v) for v in origin] if rot else None,
            "inflate": float(inflate)}


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


# --- chain and surface vocabulary ------------------------------------------
# Promoted out of 生物/hell_juggernaut, where the chain approach was first worked
# out (ISSUE.md 6): a limb is a chain of segments that each hinge on the joint
# above them, and a curved surface is a chain of plates laid along it -- the
# shape carries in the orientation of each piece, not in the step between
# stacked cubes.
DIRS = {"-y": (0, -1, 0), "+y": (0, 1, 0), "+z": (0, 0, 1), "-z": (0, 0, -1)}


def half(v):
    """Snap to the 0.5 grid: chain joints land wherever sin/cos puts them, and
    the boxes authored from them have to stay on the grid with whole sizes."""
    return round(v * 2) / 2


def box(name, mat, f, t, rot=None, origin=None, inflate=0.0, **faces):
    """One box. `mat` may be a facemap (FM(...)) or a material name. `rot` is an
    element rotation (degrees, ZYX) about `origin` (default: the box's own
    centre) -- what a chain segment uses to hinge on the joint above it, and
    what a plate uses to lie along a curved surface."""
    return cube(name, f, t, mat if isinstance(mat, dict) else FM(all=mat, **faces),
                rot=rot, origin=origin, inflate=inflate)


def axle_offset(i, step=0.25):
    """A five-step quarter-unit walk along a gear's axle: -0.5 .. +0.5.

    A cog's face plane sits at offset + thick/2, so the walk and the thickness
    step have to move in ONE dimension between them. Stepping the thickness
    alone leaves plates two apart (which overlap, because a tooth is wider than
    its slot) in the same plane; a five-step walk separates every pair that can
    touch, and skews the wheel by a unit across its whole circumference, which
    is under a pixel a plate.
    """
    return step * (i % 5) - 2 * step


def stagger(i, base, alt=1):
    """Alternate one dimension of a piece by `alt` units around a run of them.

    This is what stops a band of plates z-fighting. The plates of a ring all
    share a height, so their top (and bottom) faces land in ONE plane, and they
    overlap each other by design -- coincident, same-facing and overlapping: the
    renderer picks a winner per pixel and it changes with the camera. Stepping
    the height one unit around the ring breaks every one of those pairs, and at
    a 2 px/unit texture it reads as hand-forged rather than as an error.
    (ISSUE.md 3 hit this first with a scythe blade, at 0.03 units a plate.)
    """
    return base if i % 2 == 0 else max(1, base - alt)


def slab(name, centre, size, rot, mat, **faces):
    """A plate: an axis-aligned box of `size` centred on `centre` -- its real
    position in the rest pose, so the project still reads in Blockbench -- then
    turned by `rot` about its own centre. This is how a curved surface is laid:
    every plate is authored where it belongs and angled to face outward, so N
    plates make an N-gon that reads as a curve.

    There is deliberately no pivot argument: authoring a box at its true centre
    AND rotating it about some far pivot applies the transform twice (ISSUE.md
    6.5). A plate that has to swing around a body axis belongs in a chain
    segment, where `local()` gives it the segment's own frame.
    """
    w, h, d = size
    f = (centre[0] - w / 2, centre[1] - h / 2, centre[2] - d / 2)
    t = (centre[0] + w / 2, centre[1] + h / 2, centre[2] + d / 2)
    rot = [float(v) for v in rot]
    return box(name, mat, f, t, rot=rot if any(rot) else None, **faces)


def ring(prefix, cy, a, b, n, h, thick, mat, cx=0.0, cz=0.0, **faces):
    """The LEFT half of a ring of plates standing around the vertical axis: plate
    i sits on the ellipse (a wide, b deep) at yaw psi and faces outward, its
    local +z (the `south` face) pointing away from the body.

    Authoring the half and letting add_mirrors() make the right is what keeps
    the mirror gate exact; the two plates on x = 0 (front and back) are centre
    parts and are returned unmarked. Even n only (it must close on the mirror
    plane). Each plate is as wide as the longer of the two chords it has to
    bridge, plus a little, so neighbours overlap into a barrel instead of
    opening wedges where the ellipse is flat.
    """
    import math
    steps = n // 2
    pts = []
    for i in range(steps + 1):
        psi = 180.0 * i / steps
        s, c = math.sin(math.radians(psi)), math.cos(math.radians(psi))
        pts.append((cx + a * s, cz - b * c,
                    math.degrees(math.atan2(b * s, -a * c))))
    out = []
    for i, (px, pz, yaw) in enumerate(pts):
        chord = 0.0
        for j in (i - 1, i + 1):
            if 0 <= j < len(pts):
                chord = max(chord, math.dist((px, pz), pts[j][:2]))
        arc = max(1, math.ceil(chord * 1.12))
        name = f"{prefix}{i:02d}" + ("_l" if px - cx > 1e-6 else "")
        out.append(slab(name, (px, cy, pz),
                        (stagger(i, arc), stagger(i, h), thick),
                        (0.0, yaw, 0.0), mat, **faces))
    return out


def dome(prefix, centre, r, n, a0, a1, w, thick, mat, **faces):
    """An arc of plates over the top of a head or a shoulder -- the same idea as
    ring() turned through 90 degrees: plate i sits on the circle of radius `r`
    about `centre` at pitch phi (0 = straight up, + = forward, - = back) and
    faces radially outward, so its local +y (the `up` face) is the outside.
    Plates are `w` wide; a dome on x = 0 (a skull) is a centre part, one offset
    to a shoulder carries an `_l` for add_mirrors() to complete.
    """
    import math
    pts = []
    for i in range(n):
        phi = a0 + (a1 - a0) * i / max(1, n - 1)
        pts.append((centre[1] + r * math.cos(math.radians(phi)),
                    centre[2] - r * math.sin(math.radians(phi)), phi))
    out = []
    for i, (cy, cz, phi) in enumerate(pts):
        chord = 0.0
        for j in (i - 1, i + 1):
            if 0 <= j < len(pts):
                chord = max(chord, math.dist((cy, cz), pts[j][:2]))
        arc = max(1, math.ceil(chord * 1.12))
        name = f"{prefix}{i:02d}" + ("_l" if centre[0] > 1e-6 else "")
        out.append(slab(name, (centre[0], cy, cz),
                        (stagger(i, w), thick, stagger(i, arc)),
                        (-phi, 0.0, 0.0), mat, **faces))
    return out


def chain(parent, name, joint, dirv, segs):
    """A limb or a tail as a chain of hinged segments.

    segs = [(tag, L, w, h, rot, mat)]: `rot` is that segment's ABSOLUTE
    rotation in degrees (ZYX) about the joint it hangs from, so a chain of
    growing angles bends like a limb instead of stacking bricks. Each segment
    is authored as an axis-aligned box reaching L from its joint along `dirv`
    ('-y' down, '+z' back, '+y' up) and then rotated about that joint. Every
    segment gets its own group, parented to the one above, with its origin on
    the shared joint -- that group chain is what the animation bends.

    Angles live on the ELEMENTS and the groups stay at zero, deliberately: a
    keyframe on a group replaces its rotation outright, so a rest angle parked
    there would be wiped out by the first keyframe of any clip.

    Returns one record per segment: {tag, group, joint, rot, R}, with the last
    group also as `chain.last`.
    """
    from bbmodel_kit import V, rot_ZYX
    axis = np.array(DIRS[dirv], float)
    p = V(*joint)
    out, prev = [], parent
    for tag, L, w, h, rot, mat in segs:
        R = rot_ZYX(*rot) if rot else np.eye(3)
        if dirv in ("-y", "+y"):
            f = (p[0] - w / 2, min(p[1], p[1] + axis[1] * L), p[2] - h / 2)
            t = (p[0] + w / 2, max(p[1], p[1] + axis[1] * L), p[2] + h / 2)
        else:
            f = (p[0] - w / 2, p[1] - h / 2, min(p[2], p[2] + axis[2] * L))
            t = (p[0] + w / 2, p[1] + h / 2, max(p[2], p[2] + axis[2] * L))
        g = group(f"{name}_{tag}", origin=tuple(p), cubes=[
            box(f"{name}_{tag}_seg", mat, f, t, rot=list(rot), origin=tuple(p))])
        prev["children"].append(g)
        out.append({"tag": tag, "group": g, "joint": tuple(p), "L": L,
                    "rot": tuple(rot), "R": R})
        prev = g
        nxt = p + R @ (axis * L)
        p = V(half(nxt[0]), half(nxt[1]), half(nxt[2]))
    chain.last = prev
    return out


def put(seg, *cubes):
    """Add boxes to a chain segment's own group, so they animate with it."""
    seg["group"]["cubes"].extend(cubes)
    return seg


def local(seg, x, y, z, size, mat=None, name=None, **faces):
    """A box in a chain segment's OWN frame.

    (x, y, z) is the centre measured from the segment's joint in the segment's
    own un-rotated axes: y down the limb for a '-y' chain, z along the tail for
    a '+z' chain. The box is authored there and the segment's element rotation
    carries it into place, exactly as chain() authors the segment boxes -- so
    armour rides the limb instead of hanging in the world's axes. Do NOT apply
    the inverse rotation here: authoring un-rotated and letting the element
    rotation carry the box is the whole trick (applying R^T as well lands the
    plate on the far side of the joint -- ISSUE.md 6.5).
    """
    from bbmodel_kit import V
    j = V(*seg["joint"])
    c = j + V(x, y, z)
    w, h, d = size
    return box(name, mat,
               (c[0] - w / 2, c[1] - h / 2, c[2] - d / 2),
               (c[0] + w / 2, c[1] + h / 2, c[2] + d / 2),
               rot=list(seg["rot"]), origin=tuple(seg["joint"]), **faces)


def spike(name, mat, f, t, axis, step, steps, shrink=0.5, drift=(0, 0), tip=None,
          **faces):
    """A tapering spike: `steps` boxes strung along `axis`, each pulling both
    cross axes in by `shrink` per side and drifting its centre by `drift`.

    ISSUE.md 4.1: a spike that only tapers in one cross axis ends in a slab,
    so both cross axes shrink every step. `tip` is the material of the last
    step (horns and tusks go pale at the point)."""
    ai = "xyz".index(axis[1])
    sign = 1 if axis[0] == "+" else -1
    cross = [i for i in range(3) if i != ai]
    f, t = [float(v) for v in f], [float(v) for v in t]
    stem, side = (name[:-2], name[-2:]) if name.endswith("_l") else (name, "")
    out = []
    for i in range(steps):
        m = mat if (tip is None or i < steps - 1) else tip
        out.append(box(f"{stem}{i}{side}", m, tuple(f), tuple(t), **faces))
        na, nb = list(f), list(t)
        for k, c in enumerate(cross):
            na[c] += shrink + drift[k]
            nb[c] -= shrink - drift[k]
        if sign > 0:
            na[ai] = t[ai] - 0.5
            nb[ai] = na[ai] + step
        else:
            nb[ai] = f[ai] + 0.5
            na[ai] = nb[ai] - step
        for c in cross:
            if nb[c] - na[c] < 1:
                return out
        f, t = na, nb
    return out


# --- mirroring and self checks ---------------------------------------------
# A left-side name carries an `_l` marker as a whole component: `*_l`, or `_l_`
# / `_l0` where the helpers (link, spike, ring, dome) append a part or step
# suffix after it. A plain substring search would be wrong -- tail_1,
# pelvis_plate_f and the like all contain an "l", so the marker is matched as a
# component.
SIDE_MARK = re.compile(r"(?:^|_)l(?=_|$|\d)")
RIGHT_MARK = re.compile(r"(?:^|_)r(?=_|$|\d)")


def is_left(name: str) -> bool:
    return bool(SIDE_MARK.search(name))


def is_side(name: str) -> bool:
    """True for a left or right part -- a centre part carries either marker."""
    return bool(SIDE_MARK.search(name) or RIGHT_MARK.search(name))


def mirror_name(name: str) -> str:
    return re.sub(r"(?<=_)l(?=_|$|\d)", "r", name)


def mirror_cube(c):
    """The x-mirror image of a cube: name, extents, and both yaw and roll --
    exact, because a mirrored rotation about X keeps rx and flips ry / rz."""
    f, t = c["from"], c["to"]
    out = dict(c)
    out["name"] = mirror_name(c["name"])
    out["from"] = (-t[0], f[1], f[2])
    out["to"] = (-f[0], t[1], t[2])
    if c.get("rotation"):
        rx, ry, rz = c["rotation"]
        out["rotation"] = [rx, -ry, -rz]
    if c.get("origin"):
        out["origin"] = [-c["origin"][0], c["origin"][1], c["origin"][2]]
    return out


def mirror_tree(node):
    """The mirror image of a subtree of groups: `*_l` becomes `*_r`, x is
    negated, and the group chain keeps its shape."""
    cubes = [mirror_cube(c) for c in node.get("cubes") or []]
    children = [mirror_tree(ch) for ch in node.get("children") or []]
    origin = node["origin"]
    rot = node.get("rotation")
    return {"name": mirror_name(node["name"]), "origin": (-origin[0], origin[1], origin[2]),
            "rotation": (rot[0], -rot[1], -rot[2]) if rot else None,
            "cubes": cubes, "children": children}


def side_tree(side: str, tree: dict) -> dict:
    return tree if side == "_l" else mirror_tree(tree)


def lift(node: dict, dy: float) -> dict:
    """Shift a whole subtree up by dy: every cube, every group origin.

    Group origins are pivots, so they have to move with the geometry or the
    animation swings the limb around a point that is no longer the joint. A
    build that needs the legs longer at the last minute can lift the body with
    this instead of re-deriving a hundred literal y values.
    """
    for c in node.get("cubes") or []:
        c["from"] = (c["from"][0], c["from"][1] + dy, c["from"][2])
        c["to"] = (c["to"][0], c["to"][1] + dy, c["to"][2])
        if c.get("origin"):
            c["origin"] = [c["origin"][0], c["origin"][1] + dy, c["origin"][2]]
    o = node["origin"]
    node["origin"] = (o[0], o[1] + dy, o[2])
    for ch in node.get("children") or []:
        lift(ch, dy)
    return node


def add_mirrors(node: dict) -> dict:
    """Mirror every left-side cube that sits inside a centre group.

    Authoring the left half and mirroring the limbs is not enough: the flank
    ribs, the eyes and the ring plates of a barrel live inside hips / spine /
    head, and those groups are built once. The mirrored copy goes into the same
    group, which is also what the headless mirror gate pairs on (it looks for
    the same cube name under the same group)."""
    lefts = [mirror_cube(c) for c in node.get("cubes") or [] if is_left(c["name"])]
    for child in node.get("children") or []:
        add_mirrors(child)
    if lefts:
        node["cubes"] = list(node.get("cubes") or []) + lefts
    return node


def check_grid(tree):
    """Whole-unit sizes on every cube, and 0.5-grid positions on every cube
    that is not rotated.

    The size rule is what makes each face an exact uv rect at S = 2 (the atlas
    rect is face_size(round(w), round(h)), so a half-unit size rounds and
    stretches); it has to hold for chain segments and their armour too. The
    position rule only matters for axis-aligned work -- a box authored inside a
    rotated frame (a plate riding a limb at 14 degrees) sits wherever the
    rotation puts it, and there is no grid to be on there."""
    from bbmodel_kit import walk_groups
    bad = []
    for path, c, _R, _t in walk_groups(tree):
        rotated = bool(c.get("rotation"))
        if not rotated:
            for v in list(c["from"]) + list(c["to"]):
                if abs(v * 2 - round(v * 2)) > 1e-6:
                    bad.append((path, "off-grid", v))
        for k in range(3):
            d = c["to"][k] - c["from"][k]
            if d <= 1e-6:
                bad.append((path, "degenerate", k))
            elif abs(d - round(d)) > 1e-6:
                bad.append((path, f"half-unit size {d}", k))
    return bad


def check_symmetric(tree):
    """Centre parts (no _l/_r marker) must straddle x = 0."""
    from bbmodel_kit import walk_groups
    bad = []
    for path, c, _R, _t in walk_groups(tree):
        name = path.rsplit("/", 1)[1]
        if is_side(name):
            continue
        if abs(c["from"][0] + c["to"][0]) > 1e-6:
            bad.append((path, c["from"][0], c["to"][0]))
    return bad


def bounds(tree):
    from bbmodel_kit import V, walk_groups
    lo, hi = np.array([1e9] * 3), np.array([-1e9] * 3)
    for _path, c, R, t in walk_groups(tree):
        for x in (c["from"][0], c["to"][0]):
            for y in (c["from"][1], c["to"][1]):
                for z in (c["from"][2], c["to"][2]):
                    p = R @ V(x, y, z) + t
                    lo, hi = np.minimum(lo, p), np.maximum(hi, p)
    return lo, hi


def local_tube(seg, a, b, thick, mat, name, n=6, phase=0.0, length=None, mid=None):
    """A chain segment's SURFACE: n plates lying around the segment's own axis,
    each turned to face outward, running most of its length.

    This is the difference between a limb and a stack of bricks. A segment
    authored as one box shows four flat sides however it is rotated, so a chain
    of them reads as a staircase of boxes; a chain of TUBES shows a polygon
    whose every facet follows the taper, exactly as the torso's staves do.

    (a, b) is the radius the plates straddle -- the limb comes out a + thick/2
    wide and b + thick/2 deep -- and the segment's own box sits inside at
    a - thick/2, sealing the tube's ends. `length` / `mid` override the span, so
    a short fat tube at a chosen point along the segment is a band or a joint
    ring. Eight plates put a facet every 45 degrees, which looks right but sits
    exactly on the gimbal lock of a ZYX euler: those calls pass phase=22.5 to
    turn the polygon half a facet.
    """
    import math
    from bbmodel_kit import V, euler_ZYX, rot_ZYX
    R, j, L = seg["R"], V(*seg["joint"]), seg["L"]
    band = length is not None
    if length is None:
        length = L + 1                     # +1: neighbours overlap at the joint
    # three quarter-families, so a band's rim can never land on the segment
    # tube's rim or on the core box's own end (which sits on an integer)
    mid = (-L / 2.0 if mid is None else mid) + (0.125 if band else 0.25)
    stem, side = (name[:-2], name[-2:]) if name[-2:] in ("_l", "_r") else (name, "")
    pts = []
    for i in range(n):
        psi = math.radians(phase + 360.0 * i / n)
        pts.append((a * math.sin(psi), -b * math.cos(psi),
                    math.degrees(math.atan2(b * math.sin(psi), -a * math.cos(psi)))))
    out = []
    for i, (px, pz, yaw) in enumerate(pts):
        chord = max(math.dist((px, pz), pts[(i + k) % n][:2]) for k in (-1, 1))
        arc = max(1, math.ceil(chord * 1.12))
        c = j + R @ V(px, mid, pz)
        try:
            eul = euler_ZYX(R @ rot_ZYX(0.0, yaw, 0.0))
        except ValueError:                 # ry = +-90: nudge off the lock
            eul = euler_ZYX(R @ rot_ZYX(0.0, yaw + 0.05, 0.0))
        out.append(slab(f"{stem}{i}{side}", (c[0], c[1], c[2]),
                        (stagger(i, arc), stagger(i, length), thick), eul,
                        mat))
    return out

def gear(name, centre, r, n, thick, mat, axis="z", tooth=3, inner=2, hub=0,
         phase=0.0):
    """A cog as ONE ring of plates whose radial length alternates: a long plate
    is a tooth, its neighbour is the gap between two teeth.

    Two earlier versions were wrong in the same way -- they put the teeth ON
    something. The first laid a thin ring of rim tiles down and dropped a ring
    of tooth blocks outside it; the second rooted a tooth in each rim plate, but
    a tooth rooted in a plate still leaves TWO plates over the same radial span,
    one proud of the other. Stacking either way. Here every radial span is
    covered by exactly one plate, the teeth ARE the ring, and n counts plates --
    pass an even n so half of them are teeth.

    `r` is the root radius (a tooth reaches r + tooth), `inner` how far the
    plates reach in, `thick` the wheel's thickness. Neighbouring plates differ in
    thickness by one unit: adjacent plates overlap a little, and the coplanar
    gate only compares cubes that share a total rotation, so a yawed ring needs
    its own discipline (ISSUE.md 12).

    `axis` is the axle: 'z' lays the gear in the XY plane (it faces front and
    back), 'x' in the YZ plane (it faces the sides). `hub` is the boss's side
    length; 0 leaves the middle open, which is how a cog on a shaft looks.
    """
    import math
    cx, cy, cz = centre
    side = "_l" if cx > 1e-6 else ("_r" if cx < -1e-6 else "")
    out = []
    for i in range(n):
        phi = math.radians(phase + 360.0 * i / n)
        deg = math.degrees(phi)
        r_out = r + (tooth if i % 2 else 0)
        rad = round((inner + r_out) / 2.0 * 2) / 2.0
        depth = max(2, math.ceil(r_out - inner))
        chord = 2 * r_out * math.sin(math.pi / n)
        want = max(2, math.floor(chord * 0.99))
        t, off = stagger(i, thick), axle_offset(i)
        if axis == "z":
            u, rot = (math.cos(phi), math.sin(phi), 0.0), (0.0, 0.0, deg)
            size = (depth, want, t)
            pos = (cx + u[0] * rad, cy + u[1] * rad, cz + u[2] * rad + off)
        else:
            u, rot = (0.0, math.cos(phi), math.sin(phi)), (deg, 0.0, 0.0)
            size = (t, depth, want)
            pos = (cx + u[0] * rad + off, cy + u[1] * rad, cz + u[2] * rad)
        out.append(slab(f"{name}{i}{side}", pos, size, rot, mat))
    if hub:
        h = float(max(2, int(hub)))
        size = (h, h, thick + 2) if axis == "z" else (thick + 2, h, h)
        out.append(box(f"{name}hub{side}", mat,
                       (cx - size[0] / 2, cy - size[1] / 2, cz - size[2] / 2),
                       (cx + size[0] / 2, cy + size[1] / 2, cz + size[2] / 2)))
    return out


def local_gear(seg, r, n, thick, mat, name, mid=None, out=0.0, tooth=3, inner=2,
               phase=0.0):
    """A cog riding a chain segment, its axle across the limb -- a knee, an
    elbow, a shoulder hinge. The same one-ring construction as gear(), but every
    plate is carried by the segment's own rotation, so the cog turns with the
    joint.

    `out` slides the whole gear sideways along the limb's own x, which is where
    a cog on a hinge actually lives: sitting ON the side of the knee, its rim
    clear of the limb, instead of buried inside it.
    """
    import math
    from bbmodel_kit import V, euler_ZYX, rot_ZYX
    R, j, L = seg["R"], V(*seg["joint"]), seg["L"]
    if mid is None:
        mid = -L / 2.0
    stem, side = (name[:-2], name[-2:]) if name[-2:] in ("_l", "_r") else (name, "")
    cubes = []
    for i in range(n):
        phi = math.radians(phase + 360.0 * i / n)
        r_out = r + (tooth if i % 2 else 0)
        rad = round((inner + r_out) / 2.0 * 2) / 2.0
        depth = max(2, math.ceil(r_out - inner))
        chord = 2 * r_out * math.sin(math.pi / n)
        want = max(2, math.floor(chord * 0.99))
        c = j + R @ V(out + axle_offset(i), mid + rad * math.cos(phi),
                      rad * math.sin(phi))
        try:
            eul = euler_ZYX(R @ rot_ZYX(phi, 0.0, 0.0))
        except ValueError:
            eul = euler_ZYX(R @ rot_ZYX(phi + 0.0009, 0.0, 0.0))
        cubes.append(slab(f"{stem}{i}{side}", (c[0], c[1], c[2]),
                          (stagger(i, thick), depth, want), eul, mat))
    return cubes


# --- assembling and writing -------------------------------------------------
def collect_rects(tree, tex_index, glow_materials):
    """Every (material, w, h) the tree actually uses, biggest first (a shelf
    packer likes big rects first)."""
    from bbmodel_kit import FACES as F, V, face_size, walk_groups
    seen = {}
    for _path, c, R, t in walk_groups(tree):
        centre = R @ ((V(*c["from"]) + V(*c["to"])) / 2.0) + t
        for face in F:
            mat = c["faces"][face]
            if tex_of(mat, glow_materials) != tex_index:
                continue
            w, h = face_size(face, c["from"], c["to"])
            seen[face_key(mat, face, w, h, centre)] = True
    return sorted(seen, key=lambda k: (-k[3], -k[2]))


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
                for key in keys:                      # (mat, face, w, h, cx, cy, cz)
                    atlas.alloc(key, key[2], key[3])
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

    def emit_cube(c: dict, centre) -> str:
        el = {
            "name": c["name"],
            "from": [float(v) for v in c["from"]],
            "to": [float(v) for v in c["to"]],
            "origin": [float(v) for v in (c.get("origin") or (0.0, 0.0, 0.0))],
            "uuid": str(uuid.uuid4()),
            "faces": {},
            "type": "cube",
            "color": 0,
            "box_uv": False,
        }
        if c.get("rotation"):
            el["rotation"] = [float(v) for v in c["rotation"]]
        if c.get("inflate"):
            el["inflate"] = float(c["inflate"])
        for face in F:
            mat = c["faces"][face]
            w, h = face_size(face, c["from"], c["to"])
            x, y, rw, rh = atlases[tex_of(mat, glow_materials)].rects[
                face_key(mat, face, w, h, centre)]
            el["faces"][face] = {"uv": [x / S, y / S, (x + rw) / S, (y + rh) / S],
                                 "texture": tex_of(mat, glow_materials)}
        elements.append(el)
        by_name[c["name"]] = el["uuid"]
        return el["uuid"]

    def walk(node: dict, R=None, t=None) -> dict:
        from bbmodel_kit import V, rot_ZYX
        R = np.eye(3) if R is None else R
        t = np.zeros(3) if t is None else t
        o = np.array(node["origin"], float)
        R_local = rot_ZYX(*node["rotation"]) if node.get("rotation") else np.eye(3)
        Rn = R @ R_local
        tn = t + R @ ((np.eye(3) - R_local) @ o)      # same map as walk_groups
        children = [emit_cube(c, Rn @ ((V(*c["from"]) + V(*c["to"])) / 2.0) + tn)
                    for c in node.get("cubes") or []]
        children += [walk(child, Rn, tn) for child in node.get("children") or []]
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

# --- painting in MODEL space -------------------------------------------------
# The atlas used to key a rect by (material, width, height) alone, so every cube
# with the same material and the same face size got the same handful of pixels:
# measured on a 660-cube creature, 3966 faces shared 340 rects -- an 11.7x
# repeat, with 160 faces on one tile. The key now carries the FACE and the
# cube's model-space centre (quantised), and the painters sample a field that is
# a function of position in the model. Two consequences, and they are the two
# things the eye was missing: pieces at different places are never identical
# (no repetition) and pieces that touch sample the same field either side of the
# seam (continuity).
UV_CELL = 2.0                    # model units; the quantisation of the key


def _hash3(i, j, k, seed):
    n = (i * 73856093) ^ (j * 19349663) ^ (k * 83492791) ^ (seed * 2654435761)
    n &= 0xFFFFFFFF
    n = ((n ^ (n >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((n ^ (n >> 16)) & 0xFFFFFF) / float(0xFFFFFF)


def field3(x, y, z, scale=8.0, seed=0):
    """Value noise as a function of MODEL coordinates, vectorised.

    The same model point always gets the same value, whichever plate happens to
    cover it -- which is what lets two neighbouring plates continue each other
    across the seam instead of restarting their pattern.
    """
    x, y, z = np.asarray(x, float) / scale, np.asarray(y, float) / scale,         np.asarray(z, float) / scale
    i, j, k = np.floor(x).astype(np.int64), np.floor(y).astype(np.int64),         np.floor(z).astype(np.int64)
    fx, fy, fz = x - i, y - j, z - k
    sx, sy, sz = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy), fz * fz * (3 - 2 * fz)
    out = np.zeros(np.broadcast(x, y, z).shape, float)
    for di in (0, 1):
        for dj in (0, 1):
            for dk in (0, 1):
                h = _hash3(i + di, j + dj, k + dk, seed)
                w = ((sx if di else 1 - sx) * (sy if dj else 1 - sy)
                     * (sz if dk else 1 - sz))
                out = out + w * h
    return out


def rect_grid(key, r):
    """The model-space coordinates of every pixel of a rect, from its key.

    key = (material, face, w, h, cx2, cy2, cz2) with the centre on the 0.5 grid
    (doubled to stay integral). Returns (X, Y, Z) arrays shaped like the rect,
    the third coordinate held at the face's plane, so a painter can just write
    field3(X, Y, Z, ...) and get a pattern that runs across the model.
    """
    _mat, face, w, h, cx2, cy2, cz2 = key
    x, y, z = cx2 / 2.0, cy2 / 2.0, cz2 / 2.0
    px, py = r[2], r[3]
    u = np.linspace(x - w / 2.0 + 0.5 / S, x + w / 2.0 - 0.5 / S, px)
    v = np.linspace(y + h / 2.0 - 0.5 / S, y - h / 2.0 + 0.5 / S, py)
    U, V = np.meshgrid(u, v)
    full = np.full_like(U, 0.0)
    if face in ("north", "south"):
        return U, V, full + z
    if face in ("east", "west"):
        return full + z, V, U
    return U, full + y, V


def face_key(mat, face, w, h, centre, cell=None):
    """The atlas key for one face of one cube."""
    c = UV_CELL if cell is None else cell
    q = [int(round(v / c) * round(c * 2)) for v in centre]
    return (mat, face, int(w), int(h), q[0], q[1], q[2])

