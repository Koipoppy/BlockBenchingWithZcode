"""Shared transform algebra and structural checks for `.bbmodel` builders.

    sys.path.insert(0, os.path.dirname(__file__))
    from bbmodel_kit import (rot_ZYX, euler_ZYX, walk_groups,
                             coplanar_conflicts, posed_contacts, stretch_report)

Everything here encodes facts measured out of Blockbench 5.2.1 (see
skill/references/bbmodel-format.md), not assumptions:

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

    Pairs inside one chain are compared in the authored frame, because a shared
    rigid transform preserves coplanarity and overlap exactly; so are pairs of
    cubes whose chains are both unrotated. Pairs where either side is posed by a
    rotated chain are left to posed_contacts(), since their authored boxes are
    not what gets drawn.
    """
    boxes = []
    for path, c, R, _t in walk_groups(tree):
        boxes.append({"path": path, "chain": path.rsplit("/", 1)[0],
                      "from": V(*c["from"]), "to": V(*c["to"]),
                      "rotated": not np.allclose(R, np.eye(3))})
    trouble = []
    for i in range(len(boxes)):
        a = boxes[i]
        for j in range(i + 1, len(boxes)):
            b = boxes[j]
            if (a["rotated"] or b["rotated"]) and a["chain"] != b["chain"]:
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
