"""Build the M1A2 Abrams main battle tank as a Blockbench project.

    python tools/build_m1a2_abrams.py

Writes ../m1a2_abrams/m1a2_abrams.bbmodel (texture embedded as a data URI) and
../m1a2_abrams/m1a2_abrams.png (the same texture, standalone).

Authored, not downloaded: the Abrams is a real vehicle and no Mojang asset exists
for it, so the geometry is an original Minecraft-style interpretation of the real
thing (public specs: ~9.8 m gun-forward, 3.7 m wide, 2.4 m to the turret roof,
7 road wheels per side, rear drive sprocket, flat-sided wedge turret). Web photo
reference was not reachable from this machine, so fine details (stowage, tools)
are invented in the general style of the vehicle rather than copied from one.

Format facts are the ones measured from Blockbench 5.2.1's own source for the
other models in this collection (see ../bawanghua_flower_pot/README.md):
per-face uv rects upright and unmirrored seen from outside, v from the top;
element/group rotation = Rz * Ry * Rx about `origin`; Generic Model (free)
format, front toward -Z. One uv consequence worth restating: a rect shared by
the east and west side faces is seen left-edge-is-REAR on the east face and
left-edge-is-FRONT on the west face, so every shared side rect is painted
symmetric along its length; art that must be directional (deck grilles, rear
plate) gets its own rect.

Scale: 1 unit = 1/16 block = 1/16 m. The tank spans z -94..65 (gun forward),
x +/-32 at the turret, and tops out at y 61 (antenna tips), so ~10 x 4.3 x 3.8
blocks -- a full-size vehicle at Minecraft scale. Texture is 256x256, one pixel
per unit.
"""
from __future__ import annotations

import base64
import io
import json
import math
import os
import random
import uuid

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(os.path.dirname(HERE), "m1a2_abrams")
os.makedirs(OUT_DIR, exist_ok=True)
MODEL_NAME = "m1a2_abrams"

FACES = ("north", "east", "south", "west", "up", "down")

# --- palette ---------------------------------------------------------------
# CARC desert tan in the family of the Gulf-War-era Abrams; the ramp is warm and
# chalky, tracks and rubber are near-black, stowage is olive drab.
TAN = [(226, 209, 172), (203, 183, 143), (177, 155, 117), (149, 127, 93),
       (119, 99, 71), (91, 75, 53)]
TREAD = [(116, 112, 102), (88, 84, 76), (64, 61, 55), (46, 44, 39)]
RUBBER = [(60, 56, 50), (45, 42, 38)]
METAL = [(122, 119, 111), (92, 89, 82), (66, 63, 58), (47, 45, 41)]
DARK = [(42, 42, 44), (29, 29, 31)]
OLIVE = [(126, 130, 94), (100, 104, 72), (76, 80, 54), (58, 62, 41)]
WHITE = (238, 235, 225)
RED = (142, 54, 45)
PLACEHOLDER = (255, 0, 255, 255)


def shade(ramp, i):
    return ramp[max(0, min(len(ramp) - 1, i))]


def at(cv, r):
    return cv[r[1]:r[1] + r[3], r[0]:r[0] + r[2]]


def paint(cv, r, color):
    at(cv, r)[:] = (*color, 255)


def paint_rows(cv, r, rows):
    for y, color in rows.items():
        at(cv, r)[y, :] = (*color, 255)


def paint_cols(cv, r, cols):
    for x, color in cols.items():
        at(cv, r)[:, x] = (*color, 255)


def speckle(cv, r, color, count, rng, rows=None):
    x0, y0, w, h = r
    span = list(range(h) if rows is None else rows)
    for _ in range(count):
        cv[y0 + rng.choice(span), x0 + rng.randrange(w)] = (*color, 255)


def edge_shadow(cv, r, color):
    sub = at(cv, r)
    sub[0, :] = sub[-1, :] = (*color, 255)
    sub[:, 0] = sub[:, -1] = (*color, 255)


def weld_seams(cv, r, gap, color, vertical=True):
    """Thin darker weld lines across a plate, the Abrams has welds, not rivets."""
    sub = at(cv, r)
    if vertical:
        for x in range(gap // 2, r[2], gap):
            sub[:, x] = (*color, 255)
    else:
        for y in range(gap // 2, r[3], gap):
            sub[y, :] = (*color, 255)


class Atlas:
    """Shelf packer for the per-face uv rects, plus an edge-extend pass."""

    def __init__(self, size: int = 256):
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


# --- texture painters ------------------------------------------------------
# Rect sizes equal the real pixel size of the faces that sample them.
RECT_SIZES = [
    ("deck_top", 44, 115), ("hull_side", 115, 16), ("lower_side", 123, 9),
    ("belly", 44, 123), ("glacis", 44, 23), ("glacis_edge", 44, 2),
    ("glacis_edge2", 23, 2), ("lower_front", 44, 9), ("lower_front_edge", 44, 2),
    ("plate_edge2", 9, 2), ("nose_side", 5, 24), ("rear_plate", 44, 25),
    ("skirt", 102, 10), ("skirt_end", 3, 10), ("skirt_tip", 8, 10),
    ("fender", 118, 2),
    ("track_bottom", 102, 8), ("track_top", 95, 8), ("track_side", 102, 3),
    ("track_end", 8, 3), ("track_slope_f", 8, 12), ("track_slope_r", 8, 14),
    ("wheel_face", 10, 10), ("wheel_edge", 3, 10),
    ("sprocket", 11, 11), ("ring_edge", 3, 11),
    ("idler", 9, 9), ("idler_edge", 3, 9),
    ("turret_side", 70, 11), ("turret_front_dark", 64, 11),
    ("cheek", 39, 11), ("cheek_top", 3, 39),
    ("cheek_end", 3, 11),
    ("roof_front", 60, 22), ("roof_main", 64, 70),
    ("mantlet", 24, 8), ("mantlet_side", 20, 8), ("mantlet_top", 24, 20),
    ("tube", 30, 3), ("muzzle", 3, 3), ("sleeve", 11, 4), ("mrs", 2, 4),
    ("cupola_side", 10, 3), ("hatch_top", 8, 8),
    ("citv", 9, 4), ("citv_top", 9, 9), ("citv_lens", 9, 4),
    ("gps_front", 7, 6), ("gps_side", 10, 6), ("gps_top", 7, 10),
    ("d_hatch", 8, 8), ("periscope", 2, 2), ("periscope_case", 2, 2),
    ("grille", 12, 18), ("grille_case", 18, 3), ("deckbox", 16, 2),
    ("light_lens", 4, 3), ("light_case", 3, 3), ("hook", 4, 3), ("flap", 8, 5),
    ("bustle_rear", 40, 8), ("bustle_side", 16, 8), ("bustle_top", 40, 16),
    ("rack_floor", 41, 16), ("rail_side", 18, 2), ("rail_back", 42, 2),
    ("jerry", 5, 5), ("crate", 7, 4), ("stow", 12, 4),
    ("smoke_face", 4, 4), ("smoke_case", 8, 4),
    ("antenna", 1, 22), ("sensor", 2, 2),
    ("mg50_side", 6, 2), ("mg50_end", 2, 2), ("mg50_barrel", 10, 1),
    ("mg50_tip", 2, 2),
    ("mg240_body", 2, 2), ("mg240_barrel", 8, 1),
    ("filler", 44, 24),
]


def tan_panel(cv, r, rng, base=1, weld_gap=0, wear=True):
    """Base plate: tan ramp + speckle + optional weld seams + edge shading."""
    paint(cv, r, shade(TAN, base))
    if wear:
        speckle(cv, r, shade(TAN, base + 1), max(4, (r[2] * r[3]) // 220), rng)
        speckle(cv, r, shade(TAN, base - 1), max(3, (r[2] * r[3]) // 300), rng)
    if weld_gap:
        weld_seams(cv, r, weld_gap, shade(TAN, base + 2))
    edge_shadow(cv, r, shade(TAN, base + 2))


def paint_texture(atlas: Atlas) -> None:
    cv, r = atlas.cv, atlas.rects
    rng = random.Random(20260925)

    # --- hull plates -------------------------------------------------------
    tan_panel(cv, r["hull_side"], rng, base=1, weld_gap=24)
    tan_panel(cv, r["lower_side"], rng, base=2, weld_gap=30)
    tan_panel(cv, r["nose_side"], rng, base=2)
    tan_panel(cv, r["glacis"], rng, base=1, weld_gap=14)
    paint_rows(cv, r["glacis"], {r["glacis"][3] - 3: shade(TAN, 3),
                                 r["glacis"][3] - 2: shade(TAN, 4)})
    # tow cable loop painted across the glacis
    g = at(cv, r["glacis"])
    g[6, 4:40] = (*shade(TAN, 4), 255)
    g[7, 4:40] = (*shade(TAN, 5), 255)
    tan_panel(cv, r["glacis_edge"], rng, base=2, wear=False)
    tan_panel(cv, r["glacis_edge2"], rng, base=2, wear=False)
    tan_panel(cv, r["lower_front"], rng, base=2, weld_gap=11)
    tan_panel(cv, r["lower_front_edge"], rng, base=3, wear=False)
    tan_panel(cv, r["plate_edge2"], rng, base=3, wear=False)
    tan_panel(cv, r["filler"], rng, base=3, wear=False)

    # deck: front strip clean, rear engine deck with grilles and hatches.
    # rect v runs front (z -52) at the top to rear (z +63) at the bottom.
    tan_panel(cv, r["deck_top"], rng, base=1, weld_gap=0)
    d = at(cv, r["deck_top"])
    d[26:28, :] = (*shade(TAN, 2), 255)          # weld seam across the deck
    for gx in (4, 28):                            # engine deck grille panels
        panel = d[78:96, gx:gx + 12]
        panel[:] = (*shade(TREAD, 2), 255)
        for i in range(0, 18, 2):
            panel[i, :] = (*shade(TREAD, 3), 255)
        panel[:, 0] = panel[:, -1] = (*shade(TREAD, 1), 255)
    for hx, hz in ((10, 34), (26, 40)):           # round-ish access hatches
        d[hz:hz + 8, hx:hx + 8] = (*shade(TAN, 2), 255)
        edge_shadow(d[hz:hz + 8, hx:hx + 8], (0, 0, 8, 8), shade(TAN, 3))
    speckle(cv, r["deck_top"], shade(TAN, 3), 60, rng, rows=range(70, 115))

    # rear plate: louvered grilles, taillights, tow pintle
    tan_panel(cv, r["rear_plate"], rng, base=1, weld_gap=12)
    rp = at(cv, r["rear_plate"])
    for gx in (4, 24):
        rp[6:16, gx:gx + 16] = (*shade(TREAD, 2), 255)
        for i in range(0, 10, 2):
            rp[6 + i, gx:gx + 16] = (*shade(TREAD, 3), 255)
    rp[20:23, 8:11] = (*RED, 255)
    rp[20:23, 33:36] = (*RED, 255)
    rp[18:21, 20:24] = (*shade(METAL, 2), 255)   # tow pintle

    tan_panel(cv, r["belly"], rng, base=4, wear=False)

    # --- skirts, fenders, flaps -------------------------------------------
    tan_panel(cv, r["skirt"], rng, base=1, weld_gap=0)
    s = at(cv, r["skirt"])
    for x in range(0, 102, 17):                   # skirt segment joints
        s[:, x] = (*shade(TAN, 3), 255)
    paint_rows(cv, r["skirt"], {8: shade(TAN, 3), 9: shade(TAN, 4)})
    speckle(cv, r["skirt"], shade(TAN, 3), 40, rng, rows=range(6, 10))
    tan_panel(cv, r["skirt_end"], rng, base=2, wear=False)
    tan_panel(cv, r["skirt_tip"], rng, base=1, weld_gap=0)
    tan_panel(cv, r["fender"], rng, base=2, wear=False)

    # --- running gear -------------------------------------------------------
    def link_pattern(rect, pitch=3, guide=True):
        sub = at(cv, rect)
        sub[:] = (*shade(TREAD, 1), 255)
        for x in range(0, rect[2], pitch):
            sub[:, x] = (*shade(TREAD, 3), 255)
        if guide:
            mid = rect[3] // 2
            sub[mid - 1:mid + 1, :] = (*shade(TREAD, 2), 255)

    link_pattern(r["track_bottom"])
    link_pattern(r["track_top"])
    link_pattern(r["track_side"], pitch=4, guide=False)
    link_pattern(r["track_end"], pitch=2, guide=False)
    link_pattern(r["track_slope_f"], pitch=2, guide=False)
    link_pattern(r["track_slope_r"], pitch=2, guide=False)

    def disc(rect, face_ramp, hub=True):
        """Road-wheel / sprocket face: thin rubber ring, tan face, hub."""
        sub = at(cv, rect)
        sub[:] = (*shade(face_ramp, 2), 255)
        edge_shadow(cv, rect, shade(RUBBER, 1))
        cx, cy = rect[2] / 2 - 0.5, rect[3] / 2 - 0.5
        rad = min(rect[2], rect[3]) / 2 - 1.0
        for yy in range(rect[3]):
            for xx in range(rect[2]):
                dist = math.hypot(xx - cx, yy - cy)
                if dist < rad - 1.0:
                    sub[yy, xx] = (*shade(TAN, 1), 255)
                if hub and dist < rad * 0.42:
                    sub[yy, xx] = (*shade(METAL, 2), 255)
                if hub and dist < rad * 0.18:
                    sub[yy, xx] = (*shade(METAL, 3), 255)
        if hub:  # bolt circle
            for ang in range(0, 360, 60):
                bx = int(round(cx + math.cos(math.radians(ang)) * rad * 0.68))
                by = int(round(cy + math.sin(math.radians(ang)) * rad * 0.68))
                if 0 <= by < rect[3] and 0 <= bx < rect[2]:
                    sub[by, bx] = (*shade(METAL, 2), 255)

    disc(r["wheel_face"], RUBBER)
    paint(cv, r["wheel_edge"], shade(RUBBER, 0))
    disc(r["sprocket"], METAL, hub=False)
    paint(cv, r["ring_edge"], shade(TREAD, 1))
    disc(r["idler"], METAL, hub=True)
    paint(cv, r["idler_edge"], shade(TREAD, 1))

    # --- turret -------------------------------------------------------------
    tan_panel(cv, r["turret_side"], rng, base=1, weld_gap=22)
    paint(cv, r["turret_front_dark"], shade(TAN, 4))
    speckle(cv, r["turret_front_dark"], shade(TAN, 5), 20, rng)
    tan_panel(cv, r["cheek"], rng, base=1, weld_gap=13)
    tan_panel(cv, r["cheek_top"], rng, base=2, wear=False)
    tan_panel(cv, r["cheek_end"], rng, base=2, wear=False)
    tan_panel(cv, r["roof_front"], rng, base=1, weld_gap=20)
    tan_panel(cv, r["roof_main"], rng, base=1, weld_gap=0)
    rm = at(cv, r["roof_main"])
    rm[33:35, :] = (*shade(TAN, 2), 255)          # ring weld seam
    speckle(cv, r["roof_main"], shade(TAN, 2), 50, rng)
    tan_panel(cv, r["mantlet"], rng, base=2, weld_gap=0)
    tan_panel(cv, r["mantlet_side"], rng, base=2, wear=False)
    tan_panel(cv, r["mantlet_top"], rng, base=2, wear=False)

    # 120mm tube: thermal sleeve sections painted as darker bands
    paint(cv, r["tube"], shade(METAL, 1))
    paint_rows(cv, r["tube"], {0: shade(METAL, 0), 2: shade(METAL, 2)})
    paint(cv, r["muzzle"], shade(METAL, 3))
    paint(cv, r["sleeve"], shade(METAL, 2))
    paint_rows(cv, r["sleeve"], {0: shade(METAL, 1), 3: shade(METAL, 3)})
    paint(cv, r["mrs"], shade(METAL, 3))

    tan_panel(cv, r["bustle_rear"], rng, base=1, weld_gap=10)
    tan_panel(cv, r["bustle_side"], rng, base=1, wear=False)
    tan_panel(cv, r["bustle_top"], rng, base=2, wear=False)
    tan_panel(cv, r["rack_floor"], rng, base=2, wear=False)
    tan_panel(cv, r["rail_side"], rng, base=3, wear=False)
    tan_panel(cv, r["rail_back"], rng, base=3, wear=False)

    # cupola ring with vision blocks; hatches with a hint of a hinge
    paint(cv, r["cupola_side"], shade(TAN, 1))
    cs = at(cv, r["cupola_side"])
    for x in (1, 4, 7):
        cs[1, x:x + 2] = (*DARK[0], 255)
    edge_shadow(cv, r["cupola_side"], shade(TAN, 3))
    tan_panel(cv, r["hatch_top"], rng, base=2, wear=False)
    edge_shadow(cv, r["hatch_top"], shade(TAN, 4))

    paint(cv, r["citv"], shade(TAN, 2))
    paint(cv, r["citv_top"], shade(TAN, 1))
    edge_shadow(cv, r["citv_top"], shade(TAN, 3))
    paint(cv, r["citv_lens"], shade(DARK, 1))
    at(cv, r["citv_lens"])[1:3, 2:7] = (*shade(DARK, 0), 255)

    tan_panel(cv, r["gps_front"], rng, base=2, wear=False)
    gf = at(cv, r["gps_front"])
    gf[1:5, 2:5] = (*shade(DARK, 0), 255)         # the sight "door"
    gf[2:4, 3] = (*shade(DARK, 1), 255)
    tan_panel(cv, r["gps_side"], rng, base=1, wear=False)
    tan_panel(cv, r["gps_top"], rng, base=2, wear=False)

    tan_panel(cv, r["d_hatch"], rng, base=2, wear=False)
    edge_shadow(cv, r["d_hatch"], shade(TAN, 4))
    paint(cv, r["periscope"], shade(DARK, 0))
    paint(cv, r["periscope_case"], shade(TAN, 2))

    # engine deck raised intake boxes with slat tops
    paint(cv, r["grille"], shade(TREAD, 2))
    gr = at(cv, r["grille"])
    for i in range(0, 18, 2):
        gr[i, :] = (*shade(TREAD, 3), 255)
    gr[:, 0] = gr[:, -1] = (*shade(TAN, 3), 255)
    tan_panel(cv, r["grille_case"], rng, base=2, wear=False)
    tan_panel(cv, r["deckbox"], rng, base=2, wear=False)

    paint(cv, r["light_lens"], shade(DARK, 1))
    at(cv, r["light_lens"])[1, 1:3] = (*WHITE, 255)
    tan_panel(cv, r["light_case"], rng, base=2, wear=False)
    tan_panel(cv, r["hook"], rng, base=3, wear=False)
    paint(cv, r["flap"], shade(TAN, 3))
    paint_rows(cv, r["flap"], {0: shade(TAN, 2), 4: shade(TAN, 4)})

    # --- stowage ------------------------------------------------------------
    paint(cv, r["jerry"], shade(OLIVE, 1))
    j = at(cv, r["jerry"])
    j[1:4, 1:4] = (*shade(OLIVE, 2), 255)
    j[2, 2] = (*shade(OLIVE, 3), 255)
    j[0, :] = j[-1, :] = (*shade(OLIVE, 0), 255)
    tan_panel(cv, r["crate"], rng, base=2, wear=False)
    c = at(cv, r["crate"])
    c[:, 3] = (*shade(OLIVE, 3), 255)
    paint(cv, r["stow"], shade(OLIVE, 1))
    st = at(cv, r["stow"])
    st[:, 2] = st[:, 9] = (*shade(OLIVE, 2), 255)
    st[0, :] = st[-1, :] = (*shade(OLIVE, 0), 255)

    paint(cv, r["smoke_case"], shade(TAN, 2))
    edge_shadow(cv, r["smoke_case"], shade(TAN, 3))
    sf = at(cv, r["smoke_face"])
    sf[:] = (*shade(METAL, 2), 255)
    for ty, tx in ((0, 0), (0, 2), (2, 0), (2, 2)):   # 2x3 tube bank
        sf[ty:ty + 2, tx] = (*shade(DARK, 0), 255)

    paint(cv, r["antenna"], shade(DARK, 1))
    tan_panel(cv, r["sensor"], rng, base=2, wear=False)

    # --- machine guns -------------------------------------------------------
    paint(cv, r["mg50_side"], shade(METAL, 1))
    paint(cv, r["mg50_end"], shade(METAL, 2))
    paint(cv, r["mg50_barrel"], shade(METAL, 2))
    paint(cv, r["mg50_tip"], shade(METAL, 3))
    paint(cv, r["mg240_body"], shade(METAL, 1))
    paint(cv, r["mg240_barrel"], shade(METAL, 2))


# --- geometry ---------------------------------------------------------------
def all_faces(rect):
    return {f: rect for f in FACES}


def sides(rect):
    return {f: rect for f in ("north", "south", "east", "west")}


def faces(base, **overrides):
    merged = dict(base)
    merged.update(overrides)
    return merged


def cube(name, frm, to, origin, facemap, rotation=None):
    return {"name": name, "from": frm, "to": to, "origin": origin,
            "faces": facemap, "rotation": rotation}


WHEEL_Z = (-42, -30, -18, -6, 6, 18, 30)


def xbox(s, frm, to):
    """Mirror a box across x=0 for the left side, keeping from <= to on x."""
    if s == 1:
        return frm, to
    return (-to[0], frm[1], frm[2]), (-frm[0], to[1], to[2])


def build_running_gear(side: str) -> list[dict]:
    """Tracks + wheels for one side. side: 'left' (west, x<0) or 'right'."""
    s = -1 if side == "left" else 1

    def mx(v):
        return s * v

    gear = []

    # track loop: bottom band, top band, and two rotated slopes wrapping the
    # idler (front) and sprocket (rear). The middle span is left open so the
    # road wheels show through the side, like the real belt.
    frm, to = xbox(s, (22, 0, -50), (30, 3, 52))
    gear.append(cube(f"track_bottom_{side}", frm, to,
                     (0, 0, 0),
                     faces(all_faces("track_side"), up="track_end",
                          down="track_bottom")))
    frm, to = xbox(s, (22, 11, -46), (30, 14, 49))
    gear.append(cube(f"track_top_{side}", frm, to,
                     (0, 0, 0),
                     faces(all_faces("track_side"), up="track_top",
                          down="track_end")))
    frm, to = xbox(s, (22, 7, -59), (30, 10, -43))
    gear.append(cube(f"track_slope_front_{side}", frm, to,
                     (mx(26), 8.5, -51),
                     faces(all_faces("track_slope_f")), rotation=(-60, 0, 0)))
    frm, to = xbox(s, (22, 6.5, 47), (30, 9.5, 64))
    gear.append(cube(f"track_slope_rear_{side}", frm, to,
                     (mx(26), 8, 55.5),
                     faces(all_faces("track_slope_r")), rotation=(60, 0, 0)))

    for i, cz in enumerate(WHEEL_Z):
        frm, to = xbox(s, (23.5, 3, cz - 5), (26.5, 13, cz + 5))
        gear.append(cube(f"roadwheel_{side}_{i}", frm, to, (mx(25), 8, cz),
                         faces(sides("wheel_edge"),
                               east="wheel_face", west="wheel_face")))
    frm, to = xbox(s, (23.5, 4, 50), (26.5, 16, 61))
    gear.append(cube(f"sprocket_{side}", frm, to,
                     (mx(25), 10, 55.5),
                     faces(sides("ring_edge"),
                           east="sprocket", west="sprocket",
                           up="ring_edge", down="ring_edge")))
    frm, to = xbox(s, (23.5, 4.5, -55.5), (26.5, 13.5, -46.5))
    gear.append(cube(f"idler_{side}", frm, to,
                     (mx(25), 9, -51),
                     faces(sides("idler_edge"),
                           east="idler", west="idler")))
    return gear


def build_skirt(side: str) -> list[dict]:
    s = -1 if side == "left" else 1
    mx = lambda v: s * v
    # skirt segments plus a tip piece tilted up over the idler, and a fender
    # lip running the full length above them
    skirt = xbox(s, (27.5, 8, -50), (30, 16, 52))
    tip = xbox(s, (27.5, 8, -58), (30, 16, -50))
    fender = xbox(s, (25, 16.5, -56), (30.5, 18.5, 62))
    flap = xbox(s, (22, 2.5, 61.5), (30, 7.5, 63.5))
    return [
        cube(f"skirt_{side}", *skirt, (0, 0, 0),
             faces(sides("skirt_end"), east="skirt", west="skirt",
                   up="skirt_end")),
        cube(f"skirt_tip_{side}", *tip,
             (mx(28.75), 11, -50),
             faces(sides("skirt_end"), east="skirt_tip", west="skirt_tip",
                   up="skirt_end"), rotation=(35, 0, 0)),
        cube(f"fender_{side}", *fender, (0, 0, 0),
             faces(sides("fender"), up="fender")),
        cube(f"mudflap_{side}", *flap, (0, 0, 0), faces(all_faces("flap"))),
    ]


def build_hull() -> dict:
    cubes = [
        # lower hull between the tracks, upper hull sides, deck cap, rear plate
        cube("hull_lower", (-22, 5, -60), (22, 14, 63), (0, 0, 0),
             faces(sides("lower_side"), up="belly", down="belly")),
        cube("hull_upper", (-22, 14, -52), (22, 30, 63), (0, 0, 0),
             faces(sides("hull_side"), up="hull_side")),
        cube("hull_deck", (-22, 30, -52), (22, 31, 63), (0, 0, 0),
             faces(sides("hull_side"), up="deck_top", down="belly")),
        cube("hull_rear", (-22, 5, 63), (22, 30, 65), (0, 0, 0),
             faces(sides("rear_plate"), up="rear_plate", down="belly")),
        # nose: a dark filler closes the wedge, then the two sloped plates --
        # upper glacis (rx -60, pivot on the deck edge) and the lower front
        # plate (rx +42.8, pivot on the nose tip) meeting at the crest.
        cube("nose_filler", (-22, 5, -56), (22, 29, -51), (0, 0, 0),
             faces(sides("nose_side"), up="nose_side", down="nose_side",
                   north="filler")),
        cube("glacis", (-22, 6.9, -53), (22, 30, -51), (0, 30, -52),
             faces(all_faces("glacis_edge"),
                   north="glacis", south="glacis",
                   east="glacis_edge2", west="glacis_edge2"),
             rotation=(30, 0, 0)),
        cube("lower_front_plate", (-22, 1.9, -64.5), (22, 10.5, -62.5),
             (0, 10, -63.5),
             faces(all_faces("lower_front_edge"),
                   north="lower_front", south="lower_front",
                   east="plate_edge2", west="plate_edge2"),
             rotation=(-52.4, 0, 0)),
        # driver station: hatch on the deck lip + three hooded periscopes
        cube("driver_hatch", (-4, 31, -50), (4, 32, -42), (0, 0, 0),
             faces(sides("d_hatch"), up="d_hatch")),
        cube("periscope_l", (-5.5, 31, -51.5), (-3.9, 32.2, -49.5), (0, 0, 0),
             faces(all_faces("periscope_case"), north="periscope")),
        cube("periscope_m", (-0.8, 31, -51.5), (0.8, 32.2, -49.5), (0, 0, 0),
             faces(all_faces("periscope_case"), north="periscope")),
        cube("periscope_r", (3.9, 31, -51.5), (5.5, 32.2, -49.5), (0, 0, 0),
             faces(all_faces("periscope_case"), north="periscope")),
        # engine deck intake boxes and a small stowage box
        cube("intake_l", (-18, 31, 34), (-6, 34, 52), (0, 0, 0),
             faces(sides("grille_case"), up="grille")),
        cube("intake_r", (6, 31, 34), (18, 34, 52), (0, 0, 0),
             faces(sides("grille_case"), up="grille")),
        cube("deck_box", (-8, 31, 55), (8, 33, 60), (0, 0, 0),
             faces(sides("deckbox"), up="deckbox")),
        # headlights in the fender corners, tow hooks under the nose
        cube("headlight_l", (-29, 15, -58), (-25, 18, -55), (0, 0, 0),
             faces(sides("light_case"), north="light_lens",
                   up="light_case")),
        cube("headlight_r", (25, 15, -58), (29, 18, -55), (0, 0, 0),
             faces(sides("light_case"), north="light_lens",
                   up="light_case")),
        cube("tow_hook_l", (-15, 6, -65), (-11, 8.5, -63.5), (0, 0, 0),
             faces(all_faces("hook"))),
        cube("tow_hook_r", (11, 6, -65), (15, 8.5, -63.5), (0, 0, 0),
             faces(all_faces("hook"))),
    ]
    children = [{"name": "hull_plates", "origin": (0, 0, 0), "cubes": cubes},
                {"name": "skirt_left", "origin": (0, 0, 0),
                 "cubes": build_skirt("left")},
                {"name": "skirt_right", "origin": (0, 0, 0),
                 "cubes": build_skirt("right")},
                {"name": "track_left", "origin": (0, 0, 0),
                 "cubes": build_running_gear("left")},
                {"name": "track_right", "origin": (0, 0, 0),
                 "cubes": build_running_gear("right")}]
    return {"name": "hull", "origin": (0, 0, 0), "children": children}


def build_turret() -> dict:
    # plan of the wedge front: apex (0, -70) to corners (+/-32, -48); each
    # cheek is a wall swung out from the apex about Y, the pair meeting at the
    # centre ridge with a thin roof slab closing the V on top.
    cheek_len = math.hypot(32, 22)          # 38.8
    cheek_ang = math.degrees(math.atan2(32, 22))  # 55.4
    cubes = [
        cube("turret_core", (-32, 30, -48), (32, 41, 22), (0, 0, 0),
             faces(sides("turret_side"), north="turret_front_dark",
                   up="roof_main")),
        cube("cheek_left", (-3, 30, -70), (0, 41, -70 + cheek_len),
             (0, 35.5, -70),
             faces(all_faces("cheek_end"),
                   west="cheek", east="cheek",
                   up="cheek_top", down="cheek_top"),
             rotation=(0, -cheek_ang, 0)),
        cube("cheek_right", (0, 30, -70), (3, 41, -70 + cheek_len),
             (0, 35.5, -70),
             faces(all_faces("cheek_end"),
                   west="cheek", east="cheek",
                   up="cheek_top", down="cheek_top"),
             rotation=(0, cheek_ang, 0)),
        cube("roof_step_0", (-3, 40.55, -70), (3, 40.95, -67.9), (0, 0, 0),
             faces(all_faces("roof_front"))),
        cube("roof_step_1", (-8, 40.55, -67.9), (8, 40.95, -64.5), (0, 0, 0),
             faces(all_faces("roof_front"))),
        cube("roof_step_2", (-15, 40.55, -64.5), (15, 40.95, -59.7), (0, 0, 0),
             faces(all_faces("roof_front"))),
        cube("roof_step_3", (-23, 40.55, -59.7), (23, 40.95, -54.2), (0, 0, 0),
             faces(all_faces("roof_front"))),
        cube("roof_step_4", (-32, 40.55, -54.2), (32, 40.95, -48), (0, 0, 0),
             faces(all_faces("roof_front"))),
        # mantlet wedge sits recessed in the V; the gun group rides behind it
        cube("mantlet", (-12, 30, -66), (12, 38, -46), (0, 0, 0),
             faces(sides("mantlet_side"), north="mantlet", up="mantlet_top")),
        # roof furniture: gunner's sight (pokes past the roof edge), CITV drum,
        # commander cupola + hatch, loader hatch
        cube("gunner_sight", (-11, 38, -50), (-4, 45, -40), (0, 0, 0),
             faces(sides("gps_side"), north="gps_front", up="gps_top")),
        cube("citv", (6, 41, -26), (15, 45, -17), (0, 0, 0),
             faces(sides("citv"), north="citv_lens", up="citv_top")),
        cube("cupola", (-14, 41, 4), (-4, 44, 14), (0, 0, 0),
             faces(sides("cupola_side"), up="hatch_top")),
        cube("cupola_hatch", (-13, 44, 5), (-5, 45, 13), (0, 0, 0),
             faces(sides("hatch_top"), up="hatch_top")),
        cube("loader_hatch", (8, 41, 0), (16, 42, 8), (0, 0, 0),
             faces(sides("hatch_top"), up="hatch_top")),
        # commander's .50 M2 on the cupola ring
        cube("mg50_receiver", (-11, 45, 4), (-9, 47, 10), (0, 0, 0),
             faces(sides("mg50_side"), up="mg50_side", down="mg50_end",
                   north="mg50_end", south="mg50_end")),
        cube("mg50_barrel", (-10.4, 45.4, -6), (-9.6, 46.2, 4), (0, 0, 0),
             faces(sides("mg50_barrel"), up="mg50_barrel", down="mg50_barrel",
                   north="mg50_end", south="mg50_end")),
        cube("mg50_muzzle", (-10.7, 45.1, -7), (-9.3, 46.5, -6), (0, 0, 0),
             faces(all_faces("mg50_tip"), north="mg50_end")),
        # loader's M240 on the hatch
        cube("mg240_body", (10, 42, -2), (12, 43.5, 1), (0, 0, 0),
             faces(sides("mg240_body"), up="mg240_body")),
        cube("mg240_barrel", (10.7, 42.5, -10), (11.3, 43.1, -2), (0, 0, 0),
             faces(sides("mg240_barrel"), up="mg240_barrel")),
        # smoke grenade launchers, angled out over the cheeks
        cube("smoke_l", (-31.5, 32.5, -55), (-27.5, 36.5, -47),
             (-29.5, 34.5, -51),
             faces(sides("smoke_case"), north="smoke_face",
                   up="smoke_case", down="smoke_case"),
             rotation=(0, -25, 0)),
        cube("smoke_r", (27.5, 32.5, -55), (31.5, 36.5, -47),
             (29.5, 34.5, -51),
             faces(sides("smoke_case"), north="smoke_face",
                   up="smoke_case", down="smoke_case"),
             rotation=(0, 25, 0)),
        # side stowage racks
        cube("stow_l1", (-34.5, 32, -22), (-31.5, 36, -10), (0, 0, 0),
             faces(sides("stow"), east="stow", west="stow",
                   up="stow")),
        cube("stow_l2", (-34.5, 32, -6), (-31.5, 36, 6), (0, 0, 0),
             faces(sides("stow"), east="stow", west="stow",
                   up="stow")),
        cube("stow_r1", (31.5, 32, -22), (34.5, 36, -10), (0, 0, 0),
             faces(sides("stow"), east="stow", west="stow",
                   up="stow")),
        cube("stow_r2", (31.5, 32, -6), (34.5, 36, 6), (0, 0, 0),
             faces(sides("stow"), east="stow", west="stow",
                   up="stow")),
        # bustle with rack rails, jerry can, crate, crosswind sensor
        cube("bustle", (-20, 30, 22), (20, 38, 38), (0, 0, 0),
             faces(sides("bustle_side"), south="bustle_rear",
                   up="bustle_top")),
        cube("rack_floor", (-20.5, 38, 22), (20.5, 39, 38), (0, 0, 0),
             faces(sides("rail_back"), up="rack_floor")),
        cube("rail_l", (-21, 39, 21.5), (-20.4, 41, 39), (0, 0, 0),
             faces(sides("rail_side"), up="rail_side")),
        cube("rail_r", (20.4, 39, 21.5), (21, 41, 39), (0, 0, 0),
             faces(sides("rail_side"), up="rail_side")),
        cube("rail_back", (-21, 39, 38.4), (21, 41, 39), (0, 0, 0),
             faces(sides("rail_back"), up="rail_back")),
        cube("jerry_can", (-17, 39, 29), (-13, 44, 34), (0, 0, 0),
             faces(all_faces("jerry"))),
        cube("crate", (4, 39, 27), (11, 43, 36), (0, 0, 0),
             faces(all_faces("crate"))),
        cube("wind_sensor", (-1, 38, 23.5), (1, 39.2, 25.5), (0, 0, 0),
             faces(all_faces("sensor"))),
        # whip antennas at the bustle corners
        cube("antenna_l", (-19.5, 39, 19), (-18.9, 61, 19.6), (0, 0, 0),
             faces(all_faces("antenna"))),
        cube("antenna_r", (18.9, 39, 23), (19.5, 61, 23.6), (0, 0, 0),
             faces(all_faces("antenna"))),
    ]
    gun = {"name": "gun", "origin": (0, 35, -60), "cubes": [
        cube("gun_tube", (-1.5, 33.5, -94), (1.5, 36.5, -64), (0, 0, 0),
             faces(sides("tube"), up="tube", down="tube", north="muzzle")),
        cube("thermal_sleeve", (-1.9, 33.1, -82), (1.9, 36.9, -71), (0, 0, 0),
             faces(all_faces("sleeve"))),
        cube("mrs_collar", (-1.9, 33.1, -91.5), (1.9, 36.9, -89.5), (0, 0, 0),
             faces(all_faces("mrs"))),
    ]}
    return {"name": "turret", "origin": (0, 31, -12), "cubes": cubes,
            "children": [gun]}


def build_tree():
    return {"name": MODEL_NAME, "origin": (0, 0, 0),
            "children": [build_hull(), build_turret()]}


# --- bbmodel writing -------------------------------------------------------
def write_model(path: str, tree, rects, texture: Image.Image,
                resolution=(256, 256)) -> int:
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
            # faces left unspecified are interior faces; they get the dark
            # filler rect so a geometry mistake shows as a dark slit, not art
            x, y, w, h = rects[c["faces"].get(face, "filler")]
            el["faces"][face] = {"uv": [x, y, x + w, y + h], "texture": 0}
        if c.get("rotation"):
            el["rotation"] = [float(v) for v in c["rotation"]]
        elements.append(el)
        return el["uuid"]

    def walk(node: dict) -> dict:
        children = [emit_cube(c) for c in node.get("cubes") or []]
        children += [walk(child) for child in node.get("children") or []]
        group = {"name": node["name"],
                 "origin": [float(v) for v in node["origin"]],
                 "uuid": str(uuid.uuid4()),
                 "children": children}
        if node.get("rotation"):
            group["rotation"] = [float(v) for v in node["rotation"]]
        return group

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


def unsampled_rects(atlas: Atlas, tree) -> list[str]:
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
    atlas = Atlas(256)
    for name, w, h in sorted(RECT_SIZES, key=lambda item: -item[2]):
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
