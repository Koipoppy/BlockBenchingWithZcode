"""Render a .bbmodel to a PNG, offline, with the same conventions Blockbench uses.

    python tools/preview_bbmodel.py ../bawanghua_flower_pot.bbmodel ../preview.png
    python tools/preview_bbmodel.py model.bbmodel out.png --azimuth 40 --elevation 25

Why this exists: the model is judged by looking at it, and the thing that judges it must
not be the code that built it. Blockbench has no headless CLI (its plugins folder is not
scanned at startup, so a project cannot be opened and screenshotted without a human in
the GUI), so this is a small software rasteriser instead: z-buffered triangles, flat
per-face shading, nearest-neighbour texture sampling, 2x supersampling, and two-pass
alpha (all opaque quads first, then translucent ones far to near without depth writes,
so translucent glass sits over the model instead of cutting it out).

Conventions are the ones measured out of Blockbench's source, so the preview predicts
what the GUI shows:
  * face vertex order and uv corner order from js/util/three_custom.js + cube.js -- a
    face's uv rect appears upright and unmirrored seen from outside, v from the top
  * element/group transform = T(origin) . Rz*Ry*Rx . T(-origin), composed down the tree
  * default camera (-40, 32, -40) looking at (0, 12, 0), 45 deg fov, as on project open
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import math
import os
import re
import sys

import numpy as np
from PIL import Image, ImageFilter

# Minecraft's block face shading (up 1.0, north/south 0.8, east/west 0.6, down 0.5).
# Blending these by the squared normal axis keeps tilted faces (petals, thorns) sensible
# while leaving axis-aligned ones exactly at the value the game uses -- which is what
# makes an unlit white tooth still read as white here.
FACE_LIGHT = {"y+": 1.0, "y-": 0.5, "z+": 0.8, "z-": 0.8, "x+": 0.6, "x-": 0.6}


def face_shade(normal):
    nx, ny, nz = normal
    weights = {"x+": max(0.0, nx) ** 2, "x-": max(0.0, -nx) ** 2,
               "y+": max(0.0, ny) ** 2, "y-": max(0.0, -ny) ** 2,
               "z+": max(0.0, nz) ** 2, "z-": max(0.0, -nz) ** 2}
    total = sum(weights.values())
    if total <= 1e-9:
        return 1.0
    return sum(FACE_LIGHT[k] * v for k, v in weights.items()) / total

# Per face, as (x0/x1, y0/y1, z0/z1) corner keys, in setShape order.
FACE_VERTICES = {
    "east":  ((1, 1, 1), (1, 1, 0), (1, 0, 1), (1, 0, 0)),
    "west":  ((0, 1, 0), (0, 1, 1), (0, 0, 0), (0, 0, 1)),
    "up":    ((0, 1, 0), (1, 1, 0), (0, 1, 1), (1, 1, 1)),
    "down":  ((0, 0, 1), (1, 0, 1), (0, 0, 0), (1, 0, 0)),
    "south": ((0, 1, 1), (1, 1, 1), (0, 0, 1), (1, 0, 1)),
    "north": ((1, 1, 0), (0, 1, 0), (1, 0, 0), (0, 0, 0)),
}
FACE_NORMALS = {
    "east": (1, 0, 0), "west": (-1, 0, 0), "up": (0, 1, 0),
    "down": (0, -1, 0), "south": (0, 0, 1), "north": (0, 0, -1),
}
# Faces in the geometry's index/attribute order; each face's four vertices carry the uv
# rect corners (u1,v1), (u2,v1), (u1,v2), (u2,v2) in texture pixels, v measured downward.
FACE_ORDER = ("east", "west", "up", "down", "south", "north")
RECT_CORNERS = ((0, 0), (1, 0), (0, 1), (1, 1))
# Quad split matching Blockbench's index buffer: (0,2,1) and (2,3,1).
TRIANGLES = ((0, 2, 1), (2, 3, 1))


def rotation_matrix(degrees) -> np.ndarray:
    """Rz * Ry * Rx -- three.js euler order 'ZYX', which is what Blockbench uses."""
    rx, ry, rz = (math.radians(a) for a in degrees)
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    mx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    my = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    mz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return mz @ my @ mx


def node_matrix(origin, rotation) -> np.ndarray:
    m = np.eye(4)
    if rotation and any(abs(a) > 1e-9 for a in rotation):
        m[:3, :3] = rotation_matrix(rotation)
    o = np.array(origin, dtype=float)
    m[:3, 3] = o - m[:3, :3] @ o
    return m


def decode_textures(doc) -> list[np.ndarray]:
    out = []
    for tex in doc.get("textures") or []:
        src = tex.get("source") or ""
        m = re.match(r"data:image/\w+;base64,(.*)$", src, re.S)
        if not m:
            raise SystemExit(f"texture '{tex.get('name')}' has no embedded png")
        img = Image.open(io.BytesIO(base64.b64decode(m.group(1)))).convert("RGBA")
        out.append(np.asarray(img, dtype=np.float32) / 255.0)
    return out


def collect_quads(doc):
    """Walk the outliner, compose transforms, emit world-space textured quads."""
    elements = {el["uuid"]: el for el in doc.get("elements") or []}
    resolution = doc.get("resolution") or {"width": 64, "height": 64}
    tex_w = float(resolution.get("width", 64))
    tex_h = float(resolution.get("height", 64))
    quads = []

    def emit(element, world):
        inflate = float(element.get("inflate") or 0.0)
        low = np.array(element["from"], dtype=float) - inflate
        high = np.array(element["to"], dtype=float) + inflate
        local = node_matrix(element.get("origin") or (0, 0, 0), element.get("rotation"))
        m = world @ local
        rot = m[:3, :3]
        corner = {
            (0, 0, 0): (low[0], low[1], low[2]), (1, 0, 0): (high[0], low[1], low[2]),
            (0, 1, 0): (low[0], high[1], low[2]), (1, 1, 0): (high[0], high[1], low[2]),
            (0, 0, 1): (low[0], low[1], high[2]), (1, 0, 1): (high[0], low[1], high[2]),
            (0, 1, 1): (low[0], high[1], high[2]), (1, 1, 1): (high[0], high[1], high[2]),
        }

        def to_world(p):
            return rot @ np.array(p, dtype=float) + m[:3, 3]

        for face in FACE_ORDER:
            data = (element.get("faces") or {}).get(face)
            if not data or "uv" not in data:
                continue
            u1, v1, u2, v2 = data["uv"]
            verts = np.array([to_world(corner[k]) for k in FACE_VERTICES[face]])
            uvs = np.array([
                ((u2 if cx else u1) / tex_w, (v2 if cy else v1) / tex_h)
                for cx, cy in RECT_CORNERS
            ])
            normal = rot @ np.array(FACE_NORMALS[face], dtype=float)
            norm = np.linalg.norm(normal)
            quads.append({"verts": verts, "uvs": uvs,
                          "normal": normal / (norm or 1.0),
                          "texture": int(data.get("texture") or 0)})

    def walk(node, parent):
        world = parent @ node_matrix(node.get("origin") or (0, 0, 0), node.get("rotation"))
        for child in node.get("children") or []:
            if isinstance(child, dict):
                if child.get("uuid") in elements:
                    emit(elements[child["uuid"]], world)
                else:
                    walk(child, world)
            elif child in elements:
                emit(elements[child], world)

    for node in doc.get("outliner") or []:
        walk(node, np.eye(4))
    return quads


def view_matrix(eye, target, up=(0.0, 1.0, 0.0)) -> np.ndarray:
    eye = np.array(eye, dtype=float)
    forward = np.array(target, dtype=float) - eye
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, np.array(up, dtype=float))
    right /= np.linalg.norm(right)
    true_up = np.cross(right, forward)
    m = np.eye(4)
    m[0, :3], m[1, :3], m[2, :3] = right, true_up, -forward
    m[:3, 3] = -m[:3, :3] @ eye
    return m


def fill_polygon(mask, points) -> None:
    """Rasterise a convex screen-space polygon into a float mask (no depth)."""
    for tri in ((0, 1, 2), (0, 2, 3)):
        _raster(mask, None, points[list(tri)], None, None, 1.0)


def _raster(color, depth, points, uvs, texture, shade, write_depth=True):
    """One triangle: barycentric fill with perspective-correct uv and a z-buffer."""
    height, width = color.shape[:2]
    x0, y0 = points[0][:2]
    x1, y1 = points[1][:2]
    x2, y2 = points[2][:2]
    min_x = max(0, int(math.floor(min(x0, x1, x2))))
    max_x = min(width - 1, int(math.ceil(max(x0, x1, x2))))
    min_y = max(0, int(math.floor(min(y0, y1, y2))))
    max_y = min(height - 1, int(math.ceil(max(y0, y1, y2))))
    if max_x < min_x or max_y < min_y:
        return
    ys, xs = np.mgrid[min_y:max_y + 1, min_x:max_x + 1]
    px = xs + 0.5
    py = ys + 0.5
    denom = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
    if abs(denom) < 1e-12:
        return
    w0 = ((y1 - y2) * (px - x2) + (x2 - x1) * (py - y2)) / denom
    w1 = ((y2 - y0) * (px - x2) + (x0 - x2) * (py - y2)) / denom
    w2 = 1.0 - w0 - w1
    inside = (w0 >= -1e-7) & (w1 >= -1e-7) & (w2 >= -1e-7)
    if not inside.any():
        return
    view = color[min_y:max_y + 1, min_x:max_x + 1]

    if depth is None:                       # shadow mask pass
        view[inside] = 1.0
        return

    zview = depth[min_y:max_y + 1, min_x:max_x + 1]
    inv_w = w0 * points[0][2] + w1 * points[1][2] + w2 * points[2][2]
    inside &= inv_w > zview
    if not inside.any():
        return
    tex_h, tex_w = texture.shape[:2]
    u = w0 * uvs[0][0] * points[0][2] + w1 * uvs[1][0] * points[1][2] + w2 * uvs[2][0] * points[2][2]
    v = w0 * uvs[0][1] * points[0][2] + w1 * uvs[1][1] * points[1][2] + w2 * uvs[2][1] * points[2][2]
    safe = np.where(inv_w == 0, 1.0, inv_w)
    tx = np.clip((u / safe * tex_w).astype(np.int32), 0, tex_w - 1)
    ty = np.clip((v / safe * tex_h).astype(np.int32), 0, tex_h - 1)
    texel = texture[ty, tx, :3]
    alpha = texture[ty, tx, 3:4]
    lit = texel * shade
    view[inside] = (lit * alpha + view * (1 - alpha))[inside]
    if write_depth:
        zview[inside] = inv_w[inside]


def render(doc, textures, size=720, eye=(-40.0, 32.0, -40.0), target=(0.0, 12.0, 0.0),
           fov=45.0, ssaa=2, ground=-0.02, ground_half=4.6) -> Image.Image:
    quads = collect_quads(doc)
    w = h = size * ssaa
    eye = np.array(eye, dtype=float)
    view = view_matrix(eye, target)
    focal = 0.5 * h / math.tan(math.radians(fov) / 2.0)

    # background: a soft vertical gradient so the silhouette reads
    top = np.array([236, 239, 243], np.float32) / 255.0
    bottom = np.array([203, 210, 219], np.float32) / 255.0
    ramp = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None, None]
    color = (top * (1 - ramp) + bottom * ramp) * np.ones((h, w, 1), np.float32)

    def project(points):
        view_pts = (view[:3, :3] @ points.T).T + view[:3, 3]
        depth = -view_pts[:, 2]
        depth = np.where(depth < 1e-6, 1e-6, depth)
        inv = 1.0 / depth
        screen = np.stack([w / 2.0 + focal * view_pts[:, 0] * inv,
                           h / 2.0 - focal * view_pts[:, 1] * inv,
                           inv], axis=1)
        return screen, view_pts

    # contact shadow: the model's footprint on the ground plane, blurred
    if ground is not None:
        gh = ground_half
        corners = np.array([[-gh, 0.0, -gh], [gh, 0.0, -gh],
                            [gh, 0.0, gh], [-gh, 0.0, gh]])
        screen, _ = project(corners)
        mask = np.zeros((h, w), np.float32)
        fill_polygon(mask, screen)
        soft = np.asarray(Image.fromarray((mask * 255).astype(np.uint8))
                          .filter(ImageFilter.GaussianBlur(w / 42.0)), np.float32) / 255.0
        color *= 1.0 - 0.34 * soft[:, :, None]

    depth = np.zeros((h, w), np.float32)

    # Two passes, the way a real renderer handles transparency: everything
    # opaque first (z-buffered, order-independent), then translucent quads far
    # to near with no depth write, so glass tints whatever is behind it instead
    # of erasing it. A quad is translucent when its sampled rect carries any
    # partial alpha.
    opaque, translucent = [], []
    for quad in quads:
        tex = textures[min(quad["texture"], len(textures) - 1)]
        th, tw = tex.shape[:2]
        x0 = max(0, min(int(uv[0] * tw) for uv in quad["uvs"]))
        x1 = min(tw, max(int(uv[0] * tw) + 1 for uv in quad["uvs"]))
        y0 = max(0, min(int(uv[1] * th) for uv in quad["uvs"]))
        y1 = min(th, max(int(uv[1] * th) + 1 for uv in quad["uvs"]))
        alpha = tex[y0:y1, x0:x1, 3]
        if alpha.size and alpha.min() >= 0.98:
            opaque.append(quad)
        else:
            translucent.append(quad)

    def cam_depth(quad):
        forward = np.array(target, dtype=float) - eye
        forward /= np.linalg.norm(forward)
        return float(np.dot(quad["verts"].mean(axis=0) - eye, forward))

    translucent.sort(key=cam_depth)

    for pass_quads, write_depth in ((opaque, True), (translucent, False)):
        for quad in pass_quads:
            screen, _ = project(quad["verts"])
            # backface cull: with a z-buffer and many coincident interior faces, drawing the
            # back side of a cube would fight the front side for the same pixels. This must
            # be tested in world space -- project() returns camera-space points, and
            # comparing those against the world-space eye silently culls visible faces.
            if np.dot(quad["normal"], eye - quad["verts"].mean(axis=0)) <= 0:
                continue
            shade = face_shade(quad["normal"])
            tex = textures[min(quad["texture"], len(textures) - 1)]
            for tri in TRIANGLES:
                pts = [screen[i] for i in tri]
                uvs = [quad["uvs"][i] for i in tri]
                _raster(color, depth, pts, uvs, tex, shade, write_depth)

    img = Image.fromarray((np.clip(color, 0, 1) * 255).astype(np.uint8), "RGB")
    if ssaa > 1:
        img = img.resize((size, size), Image.BOX)
    return img


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("model")
    ap.add_argument("out")
    ap.add_argument("--size", type=int, default=720)
    ap.add_argument("--azimuth", type=float, default=225.0,
                    help="degrees around Y; 225 is Blockbench's default corner (-X,-Z)")
    ap.add_argument("--elevation", type=float, default=26.0)
    ap.add_argument("--distance", type=float, default=58.0)
    ap.add_argument("--target", type=float, nargs=3, default=(0.0, 12.0, 0.0))
    ap.add_argument("--fov", type=float, default=45.0)
    ap.add_argument("--ground", type=float, default=4.6,
                    help="half-size of the contact-shadow footprint on the ground")
    args = ap.parse_args()

    with open(args.model, encoding="utf-8") as fh:
        doc = json.load(fh)
    textures = decode_textures(doc)

    az, el = math.radians(args.azimuth), math.radians(args.elevation)
    target = np.array(args.target, dtype=float)
    eye = target + args.distance * np.array([math.cos(el) * math.sin(az),
                                             math.sin(el),
                                             math.cos(el) * math.cos(az)])
    img = render(doc, textures, size=args.size, eye=eye, target=target, fov=args.fov,
                 ground_half=args.ground)
    img.save(args.out)
    print(f"{args.out}  {img.width}x{img.height}  eye={np.round(eye, 1).tolist()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())