"""Build 雷电将军 (Raiden Shogun, Genshin Impact) as a Blockbench project.

    python tools/build_raiden_shogun.py

Writes ../raiden_shogun/raiden_shogun.bbmodel (texture embedded as a data URI) and
../raiden_shogun/raiden_shogun.png (the same texture, standalone).

2026-09-25, fourth rebuild -- the first three were rejected. This one is built to
the *measured proportions of the reference render* the user supplied: see
`_ref/raiden_landmarks.json` and `tools/compare_model.py` (the scoring tool that
drove the iteration). The reference figure is 454 px tall in a 967 px image and
measures:

    chin 0.781, shoulder 0.731, waist 0.558, hip 0.490, hem 0.450,
    boot top 0.150 of its height  ->  a 4.5-head figure, head 22% of height
    head 0.200, chest 0.179, waist 0.154, hip 0.221, thigh 0.158,
    knee 0.115, boot 0.094, foot 0.073 of its height (widths)

At a 52-unit model height those become: head 11.4 tall and 10.4 wide (so the
head cube is 10.4 x 11.4 x 10.4), chin y40.6, shoulders y38, waist y29, hips
y25.5, garment hem y23.4, boot tops y7.8, chest 9.3 wide, waist 8.0, hips 11.5,
thighs 8.2 (both), knees 6.0, boots 4.9.

Two lessons from the rejected versions are baked in:

* **no visible steps in the limbs.**  Each leg segment differs from the next by
  0.2-0.3 units only (4.1 -> 3.8 -> 3.5 -> 3.2 -> 3.0 -> 2.9 -> 2.7 -> 2.45) and
  the boundaries fall on clothes lines (knee, boot cuff), so the silhouette
  curves instead of stacking like a bamboo shoot.  The scoring tool measures
  this directly ("stepiness": mean |second difference| of the width profile).
* **the palette is the reference's**, area-wise: warm cream white (the kimono and
  leggings, r > b so it reads as white and not as lavender), violet sleeves and
  sash, near-black violet hair, gold trim, crimson cords, maroon heeled boots.

The outfit itself follows the reference render and the "Narukami's Law" write-up:
white kimono and leggings with purple pattern motifs and gold trim, dark violet
detached sleeves and back tails, a tasselled violet obi with a gold bow at the
back, thigh-high maroon heeled boots, near-black violet hair with a hime-cut
fringe, face-framing locks, three back layers and a floor-length braid, and the
white-and-gold ornament on her RIGHT (+X).

Format conventions are the ones measured out of Blockbench's source (see
build_bawanghua_pot.py): per-face uv rects upright and unmirrored seen from
outside, v from the top; model_format 'free'; front of the character faces -Z
(north), so her RIGHT side is +X. Left/right group names are anatomical; left
limbs are x-mirrors of the right ones (see `mirror_cubes`).
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
OUT_DIR = os.path.join(os.path.dirname(HERE), "raiden_shogun")
os.makedirs(OUT_DIR, exist_ok=True)
MODEL_NAME = "raiden_shogun"

FACES = ("north", "east", "south", "west", "up", "down")

# --- palette ---------------------------------------------------------------
# Warm cream white: r > b so the scoring tool's classifier reads it as white,
# the way the reference's kimono (205,190,172) does.
WHITE = [
    (252, 248, 236),  # 0 highlight
    (240, 232, 214),  # 1 kimono / legging base (0.8-lit still reads as white)
    (216, 206, 186),  # 2 shade
    (188, 178, 158),  # 3 dark edge
]
HAIR = [
    (74, 60, 108),    # 0 highlight (violet sheen on near-black hair)
    (56, 44, 84),     # 1 base
    (42, 32, 64),     # 2 shade
    (30, 22, 46),     # 3 dark
]
PURP = [
    (162, 122, 210),  # 0 light
    (128, 92, 176),   # 1 sleeve / sash base
    (100, 68, 144),   # 2 shade
    (74, 48, 112),    # 3 dark
]
DARK = [
    (86, 68, 126),    # 0 light
    (66, 50, 98),     # 1 tail base
    (48, 36, 74),     # 2 shade
    (34, 26, 54),     # 3 darkest
]
CRIM = [(200, 68, 84), (168, 46, 66), (136, 34, 54), (106, 26, 44)]
MAROON = [(108, 54, 68), (86, 40, 54), (66, 28, 42), (48, 20, 30)]
SKIN = [
    (248, 214, 186),  # 0 base (warm, reads as skin)
    (232, 190, 162),  # 1 shade
    (208, 166, 140),  # 2 deep shade
]
GOLD = [(248, 212, 128), (226, 182, 92), (190, 146, 64), (154, 114, 48)]
INNER = (246, 232, 214)
PETAL = [(244, 240, 232), (218, 210, 196)]
EYE_HI = (214, 178, 250)
EYE = (146, 88, 220)
EYE_D = (76, 42, 138)
EYE_W = (246, 244, 252)
MOUTH = (196, 112, 118)
BLUSH = (238, 178, 168)
PLACEHOLDER = (255, 0, 255, 255)


def at(cv, r):
    return cv[r[1]:r[1] + r[3], r[0]:r[0] + r[2]]


class Atlas:
    """Shelf packer for the per-face uv rects, plus an edge-extend pass.

    The head rects are placed manually in a 60x11 block at the top left (the
    head is bigger than vanilla's 8x8 there, so its faces get their own 10x11
    rects, 1:1 with the cube), and the packer starts beside them with the row
    height preset so its first wrap lands below the head block.
    """

    def __init__(self, size: int = 128):
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


# --- uv rects ---------------------------------------------------------------
HEAD_RECTS = [
    ("head_up", 0, 0, 10, 10), ("head_down", 10, 0, 10, 10),
    ("head_east", 20, 0, 10, 11), ("head_front", 30, 0, 10, 11),
    ("head_west", 40, 0, 10, 11), ("head_south", 50, 0, 10, 11),
]
PACKED_RECTS = [
    ("bangs_front", 10, 5), ("bangs_side", 1, 5), ("bangs_up", 10, 1), ("bangs_down", 10, 1),
    ("sl_front", 1, 12), ("sl_side", 1, 12), ("sl_end", 1, 1),
    ("nl_front", 1, 4), ("nl_side", 1, 4), ("nl_end", 1, 1),
    ("hbup_back", 11, 6), ("hbup_side", 3, 6), ("hbup_top", 11, 3),
    ("hbmid_back", 12, 6), ("hbmid_side", 3, 6), ("hbmid_top", 12, 3), ("hbmid_bot", 12, 3),
    ("hblo_back", 10, 6), ("hblo_side", 3, 6), ("hblo_top", 10, 3), ("hblo_bot", 10, 3),
    ("flower", 3, 3), ("orn_tassel", 1, 3), ("gold", 1, 1),
    ("braid_seg", 3, 3), ("braid_tie", 2, 2), ("braid_tassel", 2, 3),
    ("neck", 4, 3), ("collar_band", 6, 4), ("collar_flat", 6, 6),
    ("chest_front", 9, 7), ("chest_back", 9, 7), ("chest_side", 5, 7),
    ("chest_up", 9, 5), ("chest_down", 9, 5),
    ("bust_r", 4, 3), ("bust_l", 4, 3), ("cord", 1, 1),
    ("waist_front", 8, 3), ("waist_back", 8, 3), ("waist_side", 5, 3), ("waist_flat", 8, 5),
    ("obi_front", 9, 4), ("obi_back", 9, 4), ("obi_side", 6, 4), ("obi_flat", 9, 6),
    ("obi_cord", 9, 1), ("obi_cord_side", 6, 1),
    ("hip_front", 11, 3), ("hip_back", 11, 3), ("hip_side", 7, 3), ("hip_flat", 11, 7),
    ("hem_front", 12, 3), ("hem_back", 12, 3), ("hem_side", 7, 3), ("hem_flat", 12, 7),
    ("knot_front", 3, 2), ("knot_side", 2, 2), ("knot_up", 3, 2),
    ("loop_front", 4, 2), ("loop_side", 1, 2), ("loop_up", 4, 1), ("loop_down", 4, 1),
    ("tail_1", 2, 6), ("tail_2", 2, 6), ("tail_end", 2, 1),
    ("panel_front", 2, 5), ("panel_side", 1, 5), ("panel_end", 2, 1),
    ("charm", 1, 2),
    ("arm_top_side", 2, 3), ("arm_up_side", 2, 4), ("arm_up_flat", 2, 2),
    ("fore_front", 2, 5), ("fore_side", 2, 5), ("fore_end", 2, 2),
    ("hand", 2, 2),
    ("sleeve", 4, 5), ("sleeve_lo", 4, 5), ("sleeve_up", 4, 4), ("sleeve_down", 4, 4),
    ("sleeve_cuff", 4, 1), ("band", 4, 1), ("band_flat", 4, 4),
    ("thigh_up", 4, 7), ("thigh_up_out", 4, 7), ("thigh_up_flat", 4, 4),
    ("thigh_lo", 4, 4), ("thigh_lo_out", 4, 4), ("thigh_lo_flat", 4, 4),
    ("knee", 4, 3), ("knee_out", 4, 3), ("knee_flat", 4, 4),
    ("shin_a", 4, 2), ("shin_a_out", 4, 2), ("shin_b", 4, 2), ("shin_b_out", 4, 2),
    ("shin_c", 4, 2), ("shin_c_out", 4, 2), ("shin_d", 4, 2), ("shin_d_out", 4, 2),
    ("calf_hi", 4, 3), ("calf_hi_out", 4, 3), ("calf_hi_in", 4, 3), ("calf_hi_up", 4, 4),
    ("calf_lo", 4, 2), ("calf_lo_out", 4, 2), ("calf_lo_in", 4, 2),
    ("boot_trim", 4, 2), ("boot_trim_flat", 4, 4),
    ("boot_hi", 3, 4), ("boot_hi_out", 3, 4), ("boot_hi_in", 3, 4),
    ("boot_lo", 3, 2), ("boot_lo_out", 3, 2), ("boot_lo_in", 3, 2),
    ("foot_front", 3, 2), ("foot_toe_side", 3, 2), ("foot_toe_up", 3, 3), ("foot_sole", 3, 3),
    ("foot_back", 3, 3), ("heel_side", 3, 3), ("heel_up", 3, 3), ("heel_sole", 3, 3),
]


# --- texture painters -------------------------------------------------------
def flat(cv, r, color):
    at(cv, r)[:] = (*color, 255)


def noise(cv, r, rng, color, p):
    a = at(cv, r)
    for py in range(r[3]):
        for px in range(r[2]):
            if rng.random() < p:
                a[py, px] = (*color, 255)


def cloth(cv, r, rng, ramp, base=1, p=0.12, edge=True):
    a = at(cv, r)
    a[:] = (*ramp[base], 255)
    sh = ramp[min(base + 1, len(ramp) - 1)]
    noise(cv, r, rng, sh, p)
    if edge:
        a[r[3] - 1, :] = (*sh, 255)
        a[:, 0] = (*sh, 255)
        a[:, r[2] - 1] = (*sh, 255)


def hairfill(cv, r, rng):
    a = at(cv, r)
    a[:] = (*HAIR[1], 255)
    w, h = r[2], r[3]
    for cx in range(w):
        if rng.random() < 0.5:
            run = rng.randrange(2, h + 1)
            y0 = rng.randrange(0, h - run + 1)
            c = HAIR[2] if rng.random() < 0.72 else HAIR[0]
            a[y0:y0 + run, cx] = (*c, 255)


def paint_face(cv, r):
    """10x11 face: fringe shadow, brows, 3-row violet eyes with whites and a
    lash line, nose, mouth, blush. Rows 0..4 hide under the bangs plate."""
    f = at(cv, r)
    f[:] = (*SKIN[0], 255)
    f[:, 0] = (*SKIN[1], 255)
    f[:, 9] = (*SKIN[1], 255)
    f[10, :] = (*SKIN[1], 255)
    f[0:5, :] = (*HAIR[1], 255)                     # under the bangs plate
    f[2, 2] = (*HAIR[2], 255); f[3, 6] = (*HAIR[2], 255)
    for cx in (2, 3, 6, 7):
        f[5, cx] = (*HAIR[3], 255)                  # brows
    for cx in (1, 2, 3, 6, 7, 8):
        f[6, cx] = (*EYE_D, 255)                    # upper lash
    f[7, 1] = (*EYE_W, 255); f[7, 2] = (*EYE, 255); f[7, 3] = (*EYE_D, 255)
    f[7, 6] = (*EYE_D, 255); f[7, 7] = (*EYE, 255); f[7, 8] = (*EYE_W, 255)
    f[8, 1] = (*EYE_HI, 255); f[8, 2] = (*EYE, 255); f[8, 3] = (*EYE, 255)
    f[8, 6] = (*EYE, 255); f[8, 7] = (*EYE, 255); f[8, 8] = (*EYE_HI, 255)
    f[9, 1] = (*BLUSH, 255); f[9, 8] = (*BLUSH, 255)
    f[9, 4] = (*SKIN[2], 255); f[9, 5] = (*SKIN[2], 255)     # nose shadow
    f[10, 4] = (*MOUTH, 255); f[10, 5] = (*MOUTH, 255)       # mouth


def paint_texture(atlas: Atlas) -> None:
    cv, r = atlas.cv, atlas.rects
    rng = random.Random(20260925)

    # --- head: hair on the sides/back/top, face on the front ---------------
    for name in ("head_east", "head_west", "head_south", "head_up"):
        hairfill(cv, r[name], rng)
    flat(cv, r["head_down"], SKIN[1])
    paint_face(cv, r["head_front"])

    # --- hair volume: bangs plate, a face lock and a neck lock per side -----
    bf = at(cv, r["bangs_front"])
    bf[:] = (*HAIR[1], 255)
    bf[0, :] = (*HAIR[0], 255)
    bf[1, 4] = (*HAIR[2], 255); bf[1, 5] = (*HAIR[2], 255)   # centre part
    for cx in (0, 3, 6, 9):
        bf[4, cx] = (*HAIR[2], 255)
    flat(cv, r["bangs_side"], HAIR[2])
    flat(cv, r["bangs_up"], HAIR[1])
    flat(cv, r["bangs_down"], HAIR[2])
    sl = at(cv, r["sl_front"])
    sl[:] = (*HAIR[1], 255)
    sl[6, 0] = (*HAIR[0], 255)
    sl[9, 0] = (*HAIR[2], 255)
    sl[11, 0] = (*HAIR[3], 255)
    ss = at(cv, r["sl_side"])
    ss[:] = (*HAIR[1], 255)
    ss[11, 0] = (*HAIR[3], 255)
    flat(cv, r["sl_end"], HAIR[2])
    nl = at(cv, r["nl_front"])
    nl[:] = (*HAIR[1], 255)
    nl[3, 0] = (*HAIR[2], 255)
    ns = at(cv, r["nl_side"])
    ns[:] = (*HAIR[1], 255)
    ns[3, 0] = (*HAIR[3], 255)
    flat(cv, r["nl_end"], HAIR[2])

    # --- three hair layers down the back + the gold crescent ---------------
    hairfill(cv, r["hbup_back"], rng)
    bg = at(cv, r["hbup_back"])
    bg[0, 3:8] = (*GOLD[1], 255)
    bg[0, 5] = (*GOLD[0], 255)
    hairfill(cv, r["hbup_side"], rng)
    flat(cv, r["hbup_top"], HAIR[1])
    for name in ("hbmid", "hblo"):
        hairfill(cv, r[f"{name}_back"], rng)
        hairfill(cv, r[f"{name}_side"], rng)
        flat(cv, r[f"{name}_top"], HAIR[1])
        flat(cv, r[f"{name}_bot"], HAIR[2])

    # --- chest: cream kimono, gold collar trim, crimson cord ----------------
    cloth(cv, r["chest_front"], rng, WHITE, base=2, edge=False)
    tf = at(cv, r["chest_front"])
    tf[:, 0] = (*WHITE[3], 255); tf[:, 8] = (*WHITE[3], 255)
    tf[0, 2:7] = (*GOLD[1], 255)
    tf[0, 4] = (*GOLD[0], 255)
    tf[1, 3] = (*GOLD[2], 255); tf[1, 5] = (*GOLD[2], 255)
    tf[1, 4] = (*PURP[2], 255)
    tf[2, 4] = (*CRIM[1], 255)                      # crimson cord at the throat
    tf[5, 1:8] = (*PURP[1], 255)                    # under-bust pattern band
    tf[5, 4] = (*PURP[0], 255)
    tf[6, :] = (*WHITE[3], 255)
    cloth(cv, r["chest_back"], rng, WHITE, base=2, edge=False)
    tb = at(cv, r["chest_back"])
    tb[0, :] = (*GOLD[1], 255)
    tb[3, 2:7] = (*PURP[1], 255)
    tb[3, 4] = (*PURP[0], 255)
    tb[4, 4] = (*GOLD[1], 255)
    cloth(cv, r["chest_side"], rng, WHITE, base=2, edge=False)
    cs = at(cv, r["chest_side"])
    cs[0, :] = (*GOLD[1], 255)
    cs[4, :] = (*PURP[1], 255)
    flat(cv, r["chest_up"], WHITE[2])
    flat(cv, r["chest_down"], DARK[3])

    # --- bust: cream cups with a gold inner trim ---------------------------
    for name, inner_col in (("bust_r", 3), ("bust_l", 0)):
        b = at(cv, r[name])
        b[:] = (*WHITE[1], 255)
        b[0, :] = (*WHITE[0], 255)
        b[2, :] = (*WHITE[2], 255)
        b[:, inner_col] = (*GOLD[2], 255)
        b[0, inner_col] = (*GOLD[1], 255)
    flat(cv, r["cord"], CRIM[1])

    # --- waist + the violet obi with the gold wrap cord --------------------
    for name in ("waist_front", "waist_back"):
        cloth(cv, r[name], rng, WHITE, base=1, edge=False)
        at(cv, r[name])[0, :] = (*WHITE[0], 255)
        at(cv, r[name])[2, :] = (*WHITE[2], 255)
    cloth(cv, r["waist_side"], rng, WHITE, base=1, edge=False)
    flat(cv, r["waist_flat"], WHITE[2])
    for name, clasp in (("obi_front", True), ("obi_back", False), ("obi_side", False)):
        cloth(cv, r[name], rng, PURP, base=1, edge=False)
        o = at(cv, r[name])
        o[0, :] = (*PURP[0], 255)
        o[3, :] = (*PURP[2], 255)
        o[:, 0] = (*PURP[2], 255)
        o[:, r[name][2] - 1] = (*PURP[2], 255)
        if clasp:
            o[0:4, 4] = (*GOLD[0], 255)
            o[1:3, 4] = (*GOLD[1], 255)
            o[1, 1] = (*GOLD[2], 255); o[1, 7] = (*GOLD[2], 255)
    cloth(cv, r["obi_flat"], rng, PURP, base=2, edge=False)
    flat(cv, r["obi_cord"], GOLD[1])
    flat(cv, r["obi_cord_side"], GOLD[2])

    # --- hips + hem: cream garment tiers with a purple pattern band ---------
    for name in ("hip_front", "hip_back", "hip_side"):
        cloth(cv, r[name], rng, WHITE, base=1, edge=False)
        h = at(cv, r[name])
        h[1, ::4] = (*PURP[1], 255)                 # sparse pattern motif
        h[1, 2] = (*PURP[0], 255)
    for name in ("hem_front", "hem_back", "hem_side"):
        cloth(cv, r[name], rng, WHITE, base=1, edge=False)
        h = at(cv, r[name])
        h[0, ::5] = (*PURP[1], 255)
        h[2, :] = (*WHITE[2], 255)
        h[2, r[name][2] // 2] = (*GOLD[2], 255)     # gold accent at the centre
    cloth(cv, r["hip_flat"], rng, WHITE, base=2, edge=False)
    cloth(cv, r["hem_flat"], rng, WHITE, base=2, edge=False)

    # --- obi bow: gold knot, violet loops ----------------------------------
    kn = at(cv, r["knot_front"])
    kn[:] = (*GOLD[1], 255)
    kn[0, 0] = (*GOLD[0], 255); kn[1, 2] = (*GOLD[0], 255)
    flat(cv, r["knot_side"], GOLD[2])
    flat(cv, r["knot_up"], GOLD[0])
    lf = at(cv, r["loop_front"])
    lf[:] = (*PURP[1], 255)
    lf[0, :] = (*PURP[0], 255)
    lf[:, 0] = (*PURP[2], 255); lf[:, 3] = (*PURP[2], 255)
    flat(cv, r["loop_side"], PURP[2])
    flat(cv, r["loop_up"], PURP[0])
    flat(cv, r["loop_down"], PURP[2])

    # --- back ribbon tails: two dark segments each, gold tip ---------------
    for name, tip in (("tail_1", False), ("tail_2", True)):
        t = at(cv, r[name])
        t[:] = (*DARK[1], 255)
        t[0, 0] = (*DARK[0], 255)
        t[3, 0] = (*PURP[1], 255)
        if tip:
            t[5, 0] = (*GOLD[1], 255)
    flat(cv, r["tail_end"], DARK[2])

    # --- front hip panels: cream with a purple motif and a gold tip --------
    pf = at(cv, r["panel_front"])
    pf[:] = (*WHITE[1], 255)
    pf[1, :] = (*PURP[1], 255)
    pf[4, :] = (*GOLD[2], 255)
    flat(cv, r["panel_side"], WHITE[2])
    flat(cv, r["panel_end"], GOLD[2])
    ch = at(cv, r["charm"])
    ch[0, 0] = (*GOLD[1], 255)
    ch[1, 0] = (*GOLD[2], 255)

    # --- neck + high collar: gold rim, cream, crimson lining ---------------
    flat(cv, r["neck"], SKIN[1])
    cb = at(cv, r["collar_band"])
    cb[0, :] = (*GOLD[1], 255)
    cb[1, :] = (*WHITE[2], 255)
    cb[2, :] = (*CRIM[2], 255)
    cb[3, :] = (*WHITE[3], 255)
    cloth(cv, r["collar_flat"], rng, WHITE, base=2, edge=False)

    # --- arms: skin, violet sleeves with motifs and a gold hem -------------
    a = at(cv, r["arm_top_side"])               # kimono-covered shoulder
    a[:] = (*WHITE[1], 255); a[2, :] = (*WHITE[2], 255)
    a[0, :] = (*WHITE[0], 255)
    a = at(cv, r["arm_up_side"])
    a[:] = (*WHITE[1], 255); a[3, :] = (*WHITE[2], 255)
    flat(cv, r["arm_up_flat"], WHITE[0])
    for name in ("fore_front", "fore_side"):
        a = at(cv, r[name])
        a[:] = (*WHITE[1], 255)
        a[0, :] = (*WHITE[0], 255)
        a[4, :] = (*WHITE[2], 255)
    flat(cv, r["fore_end"], WHITE[2])
    flat(cv, r["hand"], SKIN[0])
    sv = at(cv, r["sleeve"])
    sv[:] = (*DARK[0], 255)                     # dark violet, as in the reference
    sv[:, 0] = (*DARK[2], 255); sv[:, 3] = (*DARK[2], 255)
    sv[0, :] = (*DARK[1], 255)
    sv[2, 1] = (*PURP[1], 255); sv[3, 2] = (*PURP[1], 255)   # violet motifs
    sl2 = at(cv, r["sleeve_lo"])
    sl2[:] = (*DARK[0], 255)
    sl2[:, 0] = (*DARK[2], 255); sl2[:, 3] = (*DARK[2], 255)
    sl2[0, 1] = (*PURP[1], 255); sl2[1, 2] = (*PURP[1], 255)
    flat(cv, r["sleeve_up"], DARK[0])
    flat(cv, r["sleeve_down"], DARK[3])
    flat(cv, r["sleeve_cuff"], GOLD[1])
    bd = at(cv, r["band"])
    bd[0, 0] = (*DARK[1], 255); bd[0, 3] = (*DARK[1], 255)
    bd[0, 1] = (*GOLD[1], 255); bd[0, 2] = (*GOLD[1], 255)
    cloth(cv, r["band_flat"], rng, DARK, base=1, edge=False)

    # --- legs: cream leggings with a purple outer motif --------------------
    leggings = [("thigh_up", "thigh_up_out", 7), ("thigh_lo", "thigh_lo_out", 4),
                ("knee", "knee_out", 3), ("shin_a", "shin_a_out", 2),
                ("shin_b", "shin_b_out", 2), ("calf_hi", "calf_hi_out", 3),
                ("calf_lo", "calf_lo_out", 2), ("shin_c", "shin_c_out", 2),
                ("shin_d", "shin_d_out", 2)]
    for name, out, rows in leggings:
        cloth(cv, r[name], rng, WHITE, base=1, edge=False)
        f = at(cv, r[name])
        f[0, :] = (*WHITE[0], 255)
        f[:, 0] = (*WHITE[2], 255)
        f[:, r[name][2] - 1] = (*WHITE[2], 255)
        f[rows - 1, :] = (*WHITE[2], 255)
        if rows >= 4:
            f[2, 1] = (*PURP[1], 255)               # small front motif
        o = at(cv, r[out])
        o[:] = (*WHITE[1], 255)
        o[:, r[out][2] - 1] = (*WHITE[2], 255)
        o[0, 0] = (*PURP[1], 255)                   # purple outer seam motif
        if r[out][3] > 2:
            o[1, 0] = (*PURP[0], 255)
    for name in ("thigh_up_flat", "thigh_lo_flat", "knee_flat", "calf_hi_up"):
        flat(cv, r[name], WHITE[2])
    for name in ("calf_hi_in", "calf_lo_in"):
        flat(cv, r[name], WHITE[2])

    # --- boots: maroon with a gold cuff, darker toward the sole ------------
    flat(cv, r["boot_trim"], GOLD[1])
    flat(cv, r["boot_trim_flat"], GOLD[2])
    for name in ("boot_hi", "boot_hi_out", "boot_hi_in",
                 "boot_lo", "boot_lo_out", "boot_lo_in", "foot_back"):
        b = at(cv, r[name])
        b[:] = (*MAROON[1], 255)
        b[0, :] = (*MAROON[0], 255)
        b[:, 0] = (*MAROON[2], 255)
        b[:, r[name][2] - 1] = (*MAROON[2], 255)
        b[r[name][3] - 1, :] = (*MAROON[3], 255)
    ff = at(cv, r["foot_front"])
    ff[:] = (*MAROON[1], 255)
    ff[0, :] = (*MAROON[0], 255)
    fs = at(cv, r["foot_toe_side"])
    fs[:] = (*MAROON[1], 255)
    fs[0, :] = (*MAROON[0], 255)
    fs[:, 0] = (*MAROON[3], 255)
    flat(cv, r["foot_toe_up"], MAROON[1])
    flat(cv, r["foot_sole"], MAROON[3])
    hs = at(cv, r["heel_side"])
    hs[:] = (*MAROON[2], 255)
    hs[0, :] = (*MAROON[1], 255)
    flat(cv, r["heel_up"], MAROON[1])
    flat(cv, r["heel_sole"], MAROON[3])

    # --- braid ------------------------------------------------------------
    bs = at(cv, r["braid_seg"])
    bs[:] = (*HAIR[1], 255)
    bs[0, 0] = (*HAIR[0], 255)
    bs[1, 1] = (*HAIR[2], 255)
    bt = at(cv, r["braid_tie"])
    bt[:] = (*GOLD[1], 255)
    bt[0, 0] = (*GOLD[0], 255); bt[1, 1] = (*GOLD[2], 255)
    ts = at(cv, r["braid_tassel"])
    ts[0, :] = (*HAIR[1], 255)
    ts[1, :] = (*HAIR[2], 255)
    ts[2, :] = (*HAIR[3], 255)

    # --- ornament: white-and-gold flower + tassel, on her RIGHT ------------
    flw = at(cv, r["flower"])
    flw[:] = (*PETAL[0], 255)
    flw[0, 1] = (*PETAL[1], 255); flw[1, 0] = (*PETAL[1], 255)
    flw[1, 2] = (*GOLD[1], 255); flw[2, 1] = (*GOLD[1], 255)
    flw[2, 2] = (*GOLD[0], 255)
    ot = at(cv, r["orn_tassel"])
    ot[0, 0] = (*GOLD[1], 255); ot[1, 0] = (*GOLD[1], 255); ot[2, 0] = (*GOLD[2], 255)
    flat(cv, r["gold"], GOLD[1])


# --- geometry ---------------------------------------------------------------
# Units of 1/16 block, ground y=0, centred on x=z=0, facing -Z (north).
# Her right side is +X, her left is -X.  52 units tall = 4.5 heads.
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


def mirror_cubes(cubes):
    """x-mirror a limb: negate x, swap the east/west face rects."""
    out = []
    for c in cubes:
        fm = dict(c["faces"])
        fm["east"], fm["west"] = fm["west"], fm["east"]
        out.append(cube(c["name"].replace("_right", "_left"),
                        (-c["to"][0], c["from"][1], c["from"][2]),
                        (-c["from"][0], c["to"][1], c["to"][2]),
                        (-c["origin"][0], c["origin"][1], c["origin"][2]),
                        fm))
    return out


def right_leg_cubes() -> list:
    """One leg, tapering 4.1 -> 2.45 in 0.2..0.3 steps so the silhouette reads
    as a curve, not as stacked boxes. Boundaries sit on clothes lines: the
    knee at y12..15, the gold boot cuff at y7.8..9."""
    o = (2.05, 25.5, 0)
    def legging(name, x0, x1, y0, y1, z0, z1, out=None, inn=None):
        fm = sides(name)
        if out:
            fm["east"] = out
        if inn:
            fm["west"] = inn
        return cube(f"{name}_right", (x0, y0, z0), (x1, y1, z1), o,
                    faces(fm, up=f"{name}_flat" if f"{name}_flat" in RECT_NAMES else name,
                          down=f"{name}_flat" if f"{name}_flat" in RECT_NAMES else name))
    # Outer edges match the reference at the same height fractions (4.10 just
    # below the hem, 3.35 at the knee, 2.50 at the boot, 1.95 at the foot) and
    # step by only 0.15-0.2 per segment, so no single step in the silhouette is
    # coarser than the reference's own taper rate -- that is exactly what the
    # scoring tool's "leg smoothness" measures (biggest step vs taper rate).
    leg = [
        ("thigh_up", 0.00, 4.10, 21.3, 25.5, -2.30, 2.30),
        ("thigh_lo", 0.05, 3.85, 19.0, 21.3, -2.28, 2.28),
        ("knee", 0.10, 3.60, 17.5, 19.0, -2.24, 2.24),
        ("shin_a", 0.15, 3.35, 16.0, 17.5, -2.18, 2.18),
        ("shin_b", 0.20, 3.15, 14.5, 16.0, -2.10, 2.10),
        ("calf_hi", 0.25, 2.95, 13.0, 14.5, -2.00, 2.20),
        ("calf_lo", 0.30, 2.80, 11.5, 13.0, -1.92, 1.92),
        ("shin_c", 0.35, 2.65, 10.0, 11.5, -1.88, 1.88),
        ("shin_d", 0.40, 2.55, 8.6, 10.0, -1.84, 1.84),
    ]
    cubes = [legging(n, x0, x1, y0, y1, z0, z1, out=f"{n}_out") for n, x0, x1, y0, y1, z0, z1 in leg]
    # knee/calf caps use the dedicated "flat" rects
    cubes[2]["faces"]["up"] = "knee_flat"; cubes[2]["faces"]["down"] = "knee_flat"
    cubes[3]["faces"]["up"] = "calf_hi_up"; cubes[3]["faces"]["down"] = "calf_hi_up"
    for c in (cubes[0], cubes[1]):
        c["faces"]["up"] = f"{c['name'].split('_right')[0]}_flat"
        c["faces"]["down"] = f"{c['name'].split('_right')[0]}_flat"
    cubes.append(cube("boot_trim_right", (0.55, 7.4, -1.95), (2.60, 8.0, 1.95), o,
                      faces(sides("boot_trim"), up="boot_trim_flat", down="boot_trim_flat")))
    cubes.append(cube("boot_hi_right", (0.65, 4.2, -1.75), (2.50, 8.0, 1.75), o,
                      faces(sides("boot_hi"), up="boot_hi_in", down="boot_hi_in",
                            east="boot_hi_out", west="boot_hi_in")))
    cubes.append(cube("boot_lo_right", (0.75, 2.4, -1.65), (2.40, 4.2, 1.65), o,
                      faces(sides("boot_lo"), up="boot_lo_in", down="boot_lo_in",
                            east="boot_lo_out", west="boot_lo_in")))
    cubes.append(cube("foot_heel_right", (0.85, 0.0, 0.4), (1.95, 1.5, 2.6), o,
                      faces(sides("heel_side"), up="heel_up", down="heel_sole",
                            north="foot_back", south="foot_back")))
    cubes.append(cube("foot_toe_right", (0.85, 0.0, -3.2), (1.95, 1.5, 0.4), o,
                      faces(sides("foot_toe_side"), up="foot_toe_up", down="foot_sole",
                            north="foot_front", south="foot_back")))
    # one more step at the ankle (1.95 -> 2.15 -> 2.40), so no single width step
    # in the leg is coarser than the reference's own per-band taper
    cubes.append(cube("boot_ankle_right", (0.75, 1.5, -1.5), (2.15, 2.4, 2.0), o,
                      faces(sides("boot_lo"), up="boot_lo_in", down="boot_lo_in",
                            east="boot_lo_out", west="boot_lo_in")))
    return cubes


def right_arm_cubes() -> list:
    """Slim arm (3.0 -> 2.0) with a detached sleeve that hugs then flares."""
    o = (4.65, 38, 0)
    return [
        cube("deltoid_right", (4.4, 35.5, -1.5), (7.4, 38.5, 1.5), o,
             faces(sides("arm_top_side"), up="arm_up_flat", down="arm_up_flat")),
        cube("upper_arm_right", (4.5, 32, -1.4), (7.3, 35.5, 1.4), o,
             faces(sides("arm_up_side"), up="arm_up_flat", down="arm_up_flat")),
        cube("forearm_right", (4.7, 27, -1.2), (7.1, 32, 1.2), o,
             faces(sides("fore_side"), up="fore_end", down="fore_end",
                   north="fore_front", south="fore_front")),
        cube("hand_right", (4.9, 25, -1.0), (6.9, 27, 1.0), o,
             all_faces("hand")),
        cube("sleeve_hi_right", (4.2, 29, -1.7), (7.6, 34, 1.7), o,
             faces(sides("sleeve"), up="sleeve_up", down="sleeve_down")),
        cube("sleeve_lo_right", (4.0, 24.5, -1.9), (7.8, 29, 1.9), o,
             faces(sides("sleeve_lo"), up="sleeve_up", down="sleeve_down")),
        cube("sleeve_cuff_right", (3.95, 24.5, -1.95), (7.85, 25.1, 1.95), o,
             faces(sides("sleeve_cuff"), up="sleeve_cuff", down="sleeve_cuff")),
        cube("sleeve_band_right", (4.3, 33.8, -1.6), (7.5, 34.8, 1.6), o,
             faces(sides("band"), up="band_flat", down="band_flat")),
    ]


RECT_NAMES = {name for name, *_ in PACKED_RECTS}


def build_tree():
    body = {"name": "body", "origin": (0, 25.5, 0), "cubes": [
        # Neck, high collar, cream kimono chest with bust cups, the violet obi
        # with a gold wrap cord and the back bow, the two cream garment tiers
        # over the hips, the hanging charm, the front hip panels and the long
        # dark ribbon tails.
        cube("neck", (-1.8, 39, -1.8), (1.8, 43, 1.8), (0, 25.5, 0), all_faces("neck")),
        cube("collar", (-3.0, 38.5, -3.0), (3.0, 41.4, 3.0), (0, 25.5, 0),
             faces(sides("collar_band"), up="collar_flat", down="collar_flat")),
        cube("chest", (-4.65, 32, -2.6), (4.65, 39, 2.6), (0, 25.5, 0),
             faces(sides("chest_side"), up="chest_up", down="chest_down",
                   north="chest_front", south="chest_back")),
        cube("bust_right", (0.25, 35, -3.7), (4.3, 38, -2.2), (0, 25.5, 0),
             all_faces("bust_r")),
        cube("bust_left", (-4.3, 35, -3.7), (-0.25, 38, -2.2), (0, 25.5, 0),
             all_faces("bust_l")),
        cube("sternum_ornament", (-1.2, 35.2, -3.9), (1.2, 37.4, -2.4), (0, 25.5, 0),
             all_faces("gold")),
        cube("cord_right", (2.2, 38.2, -3.0), (2.9, 39.0, -2.2), (0, 25.5, 0),
             all_faces("cord")),
        cube("cord_left", (-2.9, 38.2, -3.0), (-2.2, 39.0, -2.2), (0, 25.5, 0),
             all_faces("cord")),
        cube("waist", (-4.0, 29, -2.3), (4.0, 32, 2.3), (0, 25.5, 0),
             faces(sides("waist_side"), up="waist_flat", down="waist_flat",
                   north="waist_front", south="waist_back")),
        cube("obi", (-4.3, 28, -2.8), (4.3, 31.5, 3.0), (0, 25.5, 0),
             faces(sides("obi_side"), up="obi_flat", down="obi_flat",
                   north="obi_front", south="obi_back")),
        cube("obi_cord", (-4.4, 29.4, -2.9), (4.4, 30.0, 3.1), (0, 25.5, 0),
             faces(sides("obi_cord_side"), up="obi_cord", down="obi_cord",
                   north="obi_cord", south="obi_cord")),
        cube("hip_tier", (-5.8, 25.2, -3.3), (5.8, 28.6, 3.5), (0, 25.5, 0),
             faces(sides("hip_side"), up="hip_flat", down="hip_flat",
                   north="hip_front", south="hip_back")),
        cube("hem_tier", (-5.7, 24.0, -3.4), (5.7, 25.2, 3.6), (0, 25.5, 0),
             faces(sides("hem_side"), up="hem_flat", down="hem_flat",
                   north="hem_front", south="hem_back")),
        cube("bow_knot", (-1.4, 29.5, 3.1), (1.4, 31.5, 4.3), (0, 25.5, 0),
             faces(sides("knot_side"), up="knot_up", down="knot_up",
                   north="knot_front", south="knot_front")),
        cube("bow_loop_right", (0.9, 29.8, 3.5), (5.0, 32.1, 4.7), (0, 25.5, 0),
             faces(sides("loop_side"), up="loop_up", down="loop_down",
                   north="loop_front", south="loop_front")),
        cube("bow_loop_left", (-5.0, 29.8, 3.5), (-0.9, 32.1, 4.7), (0, 25.5, 0),
             faces(sides("loop_side"), up="loop_up", down="loop_down",
                   north="loop_front", south="loop_front")),
        cube("bow_tail_right_hi", (0.7, 18.5, 3.6), (2.5, 29, 4.6), (0, 25.5, 0),
             faces(sides("tail_1"), up="tail_end", down="tail_end")),
        cube("bow_tail_right_lo", (1.1, 8, 3.6), (2.9, 18.5, 4.6), (0, 25.5, 0),
             faces(sides("tail_2"), up="tail_end", down="tail_end")),
        cube("bow_tail_left_hi", (-2.5, 18.5, 3.6), (-0.7, 29, 4.6), (0, 25.5, 0),
             faces(sides("tail_1"), up="tail_end", down="tail_end")),
        cube("bow_tail_left_lo", (-2.9, 8, 3.6), (-1.1, 18.5, 4.6), (0, 25.5, 0),
             faces(sides("tail_2"), up="tail_end", down="tail_end")),
        cube("charm", (-0.9, 26.5, -4.2), (0.9, 28.5, -3.0), (0, 25.5, 0),
             all_faces("charm")),
        cube("front_panel_right", (1.3, 18, -3.8), (3.3, 23.4, -3.0), (0, 25.5, 0),
             faces(sides("panel_side"), up="panel_end", down="panel_end",
                   north="panel_front", south="panel_front")),
        cube("front_panel_left", (-3.3, 18, -3.8), (-1.3, 23.4, -3.0), (0, 25.5, 0),
             faces(sides("panel_side"), up="panel_end", down="panel_end",
                   north="panel_front", south="panel_front")),
    ], "children": [
        {"name": "head", "origin": (0, 41.7, 0), "cubes": [
            cube("head", (-5.1, 42.8, -5.1), (5.1, 53.1, 5.1), (0, 41.7, 0),
                 faces({}, north="head_front", south="head_south",
                       east="head_east", west="head_west",
                       up="head_up", down="head_down")),
            cube("bangs", (-5.1, 48.1, -6.0), (5.1, 52, -5.0), (0, 40.6, 0),
                 faces(sides("bangs_side"), up="bangs_up", down="bangs_down",
                       north="bangs_front", south="bangs_front")),
            cube("sidelock_face_right", (4.4, 37.1, -5.6), (5.35, 48, -4.6), (0, 40.6, 0),
                 faces(sides("sl_side"), up="sl_end", down="sl_end",
                       north="sl_front", south="sl_front")),
            cube("sidelock_face_left", (-5.35, 37.1, -5.6), (-4.4, 48, -4.6), (0, 40.6, 0),
                 faces(sides("sl_side"), up="sl_end", down="sl_end",
                       north="sl_front", south="sl_front")),
            cube("sidelock_neck_right", (3.6, 34.1, -4.6), (4.7, 36, -3.6), (0, 40.6, 0),
                 faces(sides("nl_side"), up="nl_end", down="nl_end",
                       north="nl_front", south="nl_front")),
            cube("sidelock_neck_left", (-4.7, 34.1, -4.6), (-3.6, 36, -3.6), (0, 40.6, 0),
                 faces(sides("nl_side"), up="nl_end", down="nl_end",
                       north="nl_front", south="nl_front")),
            cube("hair_back_up", (-5.2, 47.1, 5.1), (5.2, 52, 7.6), (0, 40.6, 0),
                 faces(sides("hbup_side"), up="hbup_top", down="hbup_top",
                       north="hbup_back", south="hbup_back")),
            cube("hair_back_mid", (-5.7, 41.1, 4.6), (5.7, 46, 7.1), (0, 40.6, 0),
                 faces(sides("hbmid_side"), up="hbmid_top", down="hbmid_bot",
                       north="hbmid_back", south="hbmid_back")),
            cube("hair_back_lo", (-5.0, 35.1, 4.4), (5.0, 40, 6.6), (0, 40.6, 0),
                 faces(sides("hblo_side"), up="hblo_top", down="hblo_bot",
                       north="hblo_back", south="hblo_back")),
            cube("tiara", (-2.6, 53.1, -3.4), (2.6, 53.4, -1.4), (0, 40.6, 0),
                 all_faces("gold")),
            cube("ornament_flower", (4.4, 46.3, -3.2), (5.5, 47.2, -1.4), (0, 40.6, 0),
                 all_faces("flower")),
            cube("ornament_tassel", (4.9, 43.9, -2.7), (5.6, 45.2, -1.8), (0, 40.6, 0),
                 all_faces("orn_tassel")),
        ], "children": [
            # Signature braid: 12 staggered segments down to the calf, with a
            # gold tie, a hair tassel and a gold tip.
            {"name": "braid", "origin": (0, 44, 5.6), "cubes": [
                cube(f"braid_{i}", (-1.8 if i % 2 else -1.5, 42 - 3.2 * i, 5.6),
                     (1.5 if i % 2 else 1.8, 45.2 - 3.2 * i, 8.8), (0, 44, 5.6),
                     all_faces("braid_seg"))
                for i in range(12)
            ] + [
                cube("braid_tie", (-1.3, 5.7, 6.1), (1.3, 6.2, 8.3), (0, 44, 5.6),
                     faces(sides("braid_tie"), up="gold", down="gold")),
                cube("braid_tassel", (-1.1, 2.7, 6.2), (1.1, 4.6, 8.2), (0, 44, 5.6),
                     all_faces("braid_tassel")),
                cube("braid_tip", (-0.9, 1.5, 6.4), (0.9, 1.6, 8.0), (0, 44, 5.6),
                     all_faces("gold")),
            ]},
        ]},
        {"name": "right_arm", "origin": (4.65, 38, 0), "cubes": right_arm_cubes()},
        {"name": "left_arm", "origin": (-4.65, 38, 0), "cubes": mirror_cubes(right_arm_cubes())},
        {"name": "right_leg", "origin": (2.05, 25.5, 0), "cubes": right_leg_cubes()},
        {"name": "left_leg", "origin": (-2.05, 25.5, 0), "cubes": mirror_cubes(right_leg_cubes())},
    ]}
    return {"name": MODEL_NAME, "origin": (0, 0, 0), "children": [body]}


# --- bbmodel writing -------------------------------------------------------
def write_model(path: str, tree, rects, texture: Image.Image,
                resolution=(128, 128)) -> int:
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
    atlas = Atlas(128)
    for name, x, y, w, h in HEAD_RECTS:
        atlas.place(name, x, y, w, h)
    atlas._x, atlas._y, atlas._row_h = 61, 0, 12
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
