"""Shared transform algebra and structural checks for `.bbmodel` builders.

    sys.path.insert(0, os.path.dirname(__file__))
    from bbmodel_kit import (rot_ZYX, euler_ZYX, walk_groups,
                             coplanar_conflicts, posed_contacts, stretch_report)

Everything here encodes facts measured out of Blockbench 5.2.1, not assumptions:

* element/group transform = T(origin) . Rz*Ry*Rx . T(-origin), nested down the
  tree, with children authored in absolute model space (Group.behavior has
  use_absolute_position, so the parent's origin is subtracted on attach);
* Rz*Ry*Rx is the three.js euler order 'ZYX', which is Format.euler_order.

The checks are the "look at it before you render it" gate: z-fighting pairs,
part contacts that only exist once a rotated chain is posed, and faces whose
rounded uv rect stretches the texture. They are cheap, they are exact, and
they caught real bugs on the first model that used them (a mis-mirrored pocket,
a leg cuff pair overlapping at the centreline, a 0.5-unit box rounding to a
zero-pixel rect).
"""
from __future__ import annotations

import math

import numpy as np

FACES = ("north", "east", "south", "west", "up", "down")


def V(*a):
    return np.array(a, float)


def unit(v):
    return v / np.linalg.norm(v)


def Rx(d):
    c, s = math.cos(math.radians(d)), math.sin(math.radians(d))
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def Ry(d):
    c, s = math.cos(math.radians(d)), math.sin(math.radians(d))
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def Rz(d):
    c, s = math.cos(math.radians(d)), math.sin(math.radians(d))
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def rot_ZYX(rx, ry, rz):
    """three.js euler order 'ZYX' (= Format.euler_order) applied to a vector."""
    return Rz(rz) @ Ry(ry) @ Rx(rx)


def euler_ZYX(R):
    """Inverse of rot_ZYX, in degrees. Refuses gimbal lock instead of guessing."""
    sy = -R[2, 0]
    if abs(sy) > 0.9999:
        raise ValueError("gimbal lock: ry is +-90 deg")
    return (math.degrees(math.atan2(R[2, 1], R[2, 2])),
            math.degrees(math.asin(sy)),
            math.degrees(math.atan2(R[1, 0], R[0, 0])))


def walk_groups(node, R=None, t=None, path=""):
    """Yield (path, cube, R, t) with the affine map p_world = R @ p + t that
    Blockbench builds for that cube's ancestor chain. Descending one node:
    R' = R @ R_local and t' = t + R @ (I - R_local) @ o.
    """
    if R is None:
        R, t = np.eye(3), np.zeros(3)
    local = node.get("rotation")
    R_local = rot_ZYX(*local) if local else np.eye(3)
    o = V(*node["origin"])
    R_new = R @ R_local
    t_new = t + R @ ((np.eye(3) - R_local) @ o)
    for c in node.get("cubes") or []:
        yield f"{path}/{node['name']}/{c['name']}", c, R_new, t_new
    for child in node.get("children") or []:
        yield from walk_groups(child, R_new, t_new, f"{path}/{node['name']}")


def coplanar_conflicts(tree, eps=1e-6, min_area=0.02):
    """Z-fight risks: two faces in the same plane, facing the same way, with
    overlapping area. Opposite-facing coincident planes are legal (and used
    deliberately -- a patch flush on a sleeve, a barrel butted into a receiver).

    Two boxes are only worth comparing when they are rotated the SAME way: if
    their total rotations (chain times the element's own) match, the authored
    boxes are what get drawn, and coplanarity and overlap carry over exactly.
    Otherwise their authored boxes are not the drawn geometry, and any pair has
    to go through posed_contacts() instead. So a plate riding a 6-degree limb
    against a plate riding a 14-degree one, or a left knee against a right one
    (mirrored rotations), is skipped -- with element rotations in play the old
    "same chain" shortcut would report pairs that can never fight.
    """
    boxes = []
    for path, c, R, _t in walk_groups(tree):
        el = c.get("rotation")
        total = R @ rot_ZYX(*el) if el else R
        boxes.append({"path": path, "chain": path.rsplit("/", 1)[0],
                      "from": V(*c["from"]), "to": V(*c["to"]),
                      "R": total, "rotated": not np.allclose(total, np.eye(3))})
    trouble = []
    for i in range(len(boxes)):
        a = boxes[i]
        for j in range(i + 1, len(boxes)):
            b = boxes[j]
            if not np.allclose(a["R"], b["R"]):
                continue
            lo, hi = np.maximum(a["from"], b["from"]), np.minimum(a["to"], b["to"])
            ov = hi - lo
            for axis in range(3):
                if min(ov[k] for k in range(3) if k != axis) <= min_area:
                    continue
                for sign, tag in ((+1, "min"), (-1, "max")):
                    ca = a["from"][axis] if sign > 0 else a["to"][axis]
                    cb = b["from"][axis] if sign > 0 else b["to"][axis]
                    if abs(ca - cb) < eps:
                        trouble.append((a["path"], b["path"], "xyz"[axis], tag, ca))
    return trouble


def coplanar_visible(tree, eps=1e-6, min_area=0.02, probe=0.3, samples=3):
    """coplanar_conflicts, minus the coincidences nobody can see.

    Two same-facing coincident faces z-fight only where the space just outside
    the shared plane is empty. In a voxel model most coincidences are interior:
    a rib plate butted against the torso, a trim band flush on the plate it
    caps, a plate stack where each layer sits on the one below -- the plane is
    buried and nothing flickers. coplanar_conflicts over-reports those (it has
    no occlusion test), which makes it unusable as a hard gate on a model built
    out of stacked armour; this is the same check with the buried ones removed.

    The test: sample the shared area a fraction of a unit off the plane, along
    the normal the two faces share, and report the pair only if some sample
    point is not inside any third box. Returns (path_a, path_b, axis, tag,
    coord) exactly like coplanar_conflicts, so a caller can swap one for the
    other -- `min_area` and the same-chain/rotation scope are identical.
    """
    boxes = []
    for path, c, R, _t in walk_groups(tree):
        el = c.get("rotation")
        total = R @ rot_ZYX(*el) if el else R
        boxes.append({"path": path, "chain": path.rsplit("/", 1)[0],
                      "from": V(*c["from"]), "to": V(*c["to"]),
                      "R": total, "rotated": not np.allclose(total, np.eye(3))})
    out = []
    for i in range(len(boxes)):
        a = boxes[i]
        for j in range(i + 1, len(boxes)):
            b = boxes[j]
            if not np.allclose(a["R"], b["R"]):
                continue
            lo, hi = np.maximum(a["from"], b["from"]), np.minimum(a["to"], b["to"])
            ov = hi - lo
            for axis in range(3):
                cross = [k for k in range(3) if k != axis]
                if min(ov[k] for k in cross) <= min_area:
                    continue
                for sign, tag in ((+1, "min"), (-1, "max")):
                    ca = a["from"][axis] if sign > 0 else a["to"][axis]
                    cb = b["from"][axis] if sign > 0 else b["to"][axis]
                    if abs(ca - cb) >= eps:
                        continue
                    # the shared faces look outward along -axis on a "min" plane
                    if _face_exposed(boxes, (i, j), axis, -sign, ca, lo, hi, cross,
                                     probe, samples):
                        out.append((a["path"], b["path"], "xyz"[axis], tag, ca))
    return out


def _face_exposed(boxes, skip, axis, normal, coord, lo, hi, cross, probe, samples):
    """Is any part of the shared plane outside both boxes (and outside every
    other box)? A sample grid over the shared area, probed just off the plane."""
    keep = [b for k, b in enumerate(boxes) if k not in skip]
    for u in range(samples):
        for v in range(samples):
            p = np.zeros(3)
            for n, k in enumerate(cross):
                t = (u + 0.5) / samples if n == 0 else (v + 0.5) / samples
                p[k] = lo[k] + t * (hi[k] - lo[k])
            p[axis] = coord + normal * probe
            if not any(np.all(p > b["from"] + 1e-9) and np.all(p < b["to"] - 1e-9)
                       for b in keep):
                return True
    return False


def posed_contacts(tree, min_vol=0.05):
    """Coarse 'these two boxes may intersect once posed' report using posed
    axis-aligned bounds, for pairs where at least one side is in a rotated
    chain. Over-reports on purpose (a rotated box's AABB is fat): it is a
    triage list to eyeball, not a gate."""
    boxes = []
    for path, c, R, t in walk_groups(tree):
        f, to = V(*c["from"]), V(*c["to"])
        corners = np.array([R @ V(x, y, z) + t
                            for x in (f[0], to[0]) for y in (f[1], to[1])
                            for z in (f[2], to[2])])
        boxes.append((path, corners.min(axis=0), corners.max(axis=0),
                      not np.allclose(R, np.eye(3))))
    out = []
    for i in range(len(boxes)):
        pi, lo_i, hi_i, rot_i = boxes[i]
        for j in range(i + 1, len(boxes)):
            pj, lo_j, hi_j, rot_j = boxes[j]
            if not (rot_i or rot_j):
                continue
            ov = np.minimum(hi_i, hi_j) - np.maximum(lo_i, lo_j)
            if np.all(ov > 0) and float(np.prod(ov)) > min_vol:
                out.append((pi, pj, float(np.prod(ov))))
    return out


def face_size(face, frm, to):
    """uv rect size in pixels: 1 px per unit, never degenerate (round(0.5) is 0
    in Python, and a zero-size rect indexes out of bounds in numpy)."""
    dx, dy, dz = (to[0] - frm[0], to[1] - frm[1], to[2] - frm[2])
    s = {"north": (dx, dy), "south": (dx, dy), "east": (dz, dy),
         "west": (dz, dy), "up": (dx, dz), "down": (dx, dz)}[face]
    return max(1, int(round(s[0]))), max(1, int(round(s[1])))


def stretch_report(tree, tol=0.08):
    """Faces whose rounded uv rect differs from the true face size by more than
    tol. Any of these is a deliberate trade (a half-unit taper) or a mistake."""
    out = []
    for path, c, _R, _t in walk_groups(tree):
        for face in FACES:
            dx, dy, dz = (V(*c["to"]) - V(*c["from"]))
            w = {"north": dx, "south": dx, "east": dz, "west": dz,
                 "up": dx, "down": dx}[face]
            h = {"north": dy, "south": dy, "east": dy, "west": dy,
                 "up": dz, "down": dz}[face]
            for got, want in ((face_size(face, c["from"], c["to"])[0], w),
                              (face_size(face, c["from"], c["to"])[1], h)):
                if want > 1e-6 and abs(got - want) / want > tol:
                    out.append((path, face, round(want, 2), got))
    return out

# local corner signs per face, and the six face normals: used to get a cube's
# faces into world space, which coplanar_conflicts cannot do -- it compares
# AUTHORED boxes and therefore only dares compare cubes that share a rotation.
_CORNER = [(-1, -1, -1), (1, -1, -1), (-1, 1, -1), (1, 1, -1),
           (-1, -1, 1), (1, -1, 1), (-1, 1, 1), (1, 1, 1)]
_FACE_IX = {"north": (0, 1, 3, 2), "south": (4, 5, 7, 6), "west": (0, 2, 6, 4),
            "east": (1, 3, 7, 5), "up": (2, 3, 7, 6), "down": (0, 1, 5, 4)}
_FACE_N = {"north": (0, 0, -1), "south": (0, 0, 1), "west": (-1, 0, 0),
           "east": (1, 0, 0), "up": (0, 1, 0), "down": (0, -1, 0)}


def _world_boxes(tree):
    """Every cube as (path, M, origin, t, from, to, faces) with its faces in
    world space: each (tag, normal, quad)."""
    out = []
    for path, c, R, t in walk_groups(tree):
        el = c.get("rotation")
        M = R @ rot_ZYX(*el) if el else R
        o = np.array(c.get("origin") or (0.0, 0.0, 0.0), float)
        lo, hi = np.array(c["from"], float), np.array(c["to"], float)
        cor = {}
        for k, sg in enumerate(_CORNER):
            q = np.array([hi[i] if sg[i] > 0 else lo[i] for i in range(3)])
            cor[k] = M @ (q - o) + o + t
        faces = [(tag, M @ np.array(_FACE_N[tag], float),
                  np.array([cor[k] for k in ix])) for tag, ix in _FACE_IX.items()]
        out.append({"path": path, "M": M, "o": o, "t": t, "from": lo, "to": hi,
                    "faces": faces})
    return out


def _in_box(b, p, eps=1e-6):
    q = b["M"].T @ (p - b["o"] - b["t"]) + b["o"]
    return bool(np.all(q > b["from"]+eps) and np.all(q < b["to"]-eps))


def _poly_uv(quad, n):
    a = np.array([1.0, 0, 0]) if abs(n[0]) < 0.9 else np.array([0, 1.0, 0])
    u = np.cross(n, a); u /= np.linalg.norm(u)
    v = np.cross(n, u)
    return np.array([[q @ u, q @ v] for q in quad])


def _inside_2d(poly, p):
    s = 0
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        cr = (b[0]-a[0])*(p[1]-a[1]) - (b[1]-a[1])*(p[0]-a[0])
        if abs(cr) < 1e-12:
            continue
        s += 1 if cr > 0 else -1
    return abs(s) == len(poly)


def zfight_world(tree, eps=1e-4, probe=0.3, samples=3, min_area=0.02):
    """Coincident same-facing faces IN WORLD SPACE, exposed ones only.

    coplanar_conflicts only compares cubes that share a total rotation, because
    it works on authored boxes (ISSUE.md 7). That leaves the biggest real
    offender untested: a RING of plates, where every plate has its own yaw, all
    of them share a height, and neighbours overlap by design -- so their top
    faces are one plane, stacked and overlapping, and the renderer picks a
    winner per pixel. Rendering a `ring()` band shows it as a shimmering rim.

    This walks the transformed faces instead: parallel normals, equal plane
    offset, overlapping area, and -- like coplanar_visible -- reported only when
    the shared area is not buried inside some third cube.

    Returns (path_a, path_b, tag_a, tag_b, normal, coord).
    """
    boxes = _world_boxes(tree)
    out = []
    for i in range(len(boxes)):
        a = boxes[i]
        for j in range(i + 1, len(boxes)):
            b = boxes[j]
            for ta, na, qa in a["faces"]:
                for tb, nb, qb in b["faces"]:
                    if float(na @ nb) < 0.9999:
                        continue
                    ca, cb = float(na @ qa[0]), float(nb @ qb[0])
                    if abs(ca - cb) > eps:
                        continue
                    p1, p2 = _poly_uv(qa, na), _poly_uv(qb, na)
                    lo = np.maximum(p1.min(0), p2.min(0))
                    hi = np.minimum(p1.max(0), p2.max(0))
                    if np.any(hi - lo <= min_area):
                        continue
                    seen = False
                    for u in range(samples):
                        for v in range(samples):
                            f = (np.array([u, v]) + 0.5) / samples
                            sp = lo + (hi - lo) * f
                            if not (_inside_2d(p1, sp) and _inside_2d(p2, sp)):
                                continue
                            for sgn in (probe, -probe):
                                wp = (qa[0] + (sp[0] - p1[0][0]) * 0
                                      + np.zeros(3))
                                # rebuild the world point from the 2D sample
                                aa = np.array([1.0, 0, 0]) if abs(na[0]) < 0.9 else np.array([0, 1.0, 0])
                                uu = np.cross(na, aa); uu /= np.linalg.norm(uu)
                                vv = np.cross(na, uu)
                                origin = qa[0] - np.array([qa[0] @ uu, qa[0] @ vv, 0])[0]*uu - np.array([qa[0] @ uu, qa[0] @ vv, 0])[1]*vv
                                wp = origin + sp[0] * uu + sp[1] * vv + na * sgn
                                if not any(_in_box(boxes[k], wp)
                                           for k in range(len(boxes))
                                           if k != i and k != j):
                                    seen = True
                    if seen:
                        out.append((a["path"], b["path"], ta, tb, tuple(na), ca))
    return out
