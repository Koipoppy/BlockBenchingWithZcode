"""Build 变异铁傀儡 (mutant_iron_golem) as a Blockbench project.

    python 生物/mutant_iron_golem/build_mutant_iron_golem.py [--no-preview]

An iron golem that has gone wrong -- and been rebuilt in gold: 113 units tall
(7.1 blocks), 91 across the fists, built to the brief of 人工建模参考/生物 -- hulking humanoids (石头人,
变异坚守者) with glowing accents -- and to the rule the user set for this one:

    NO BRICKWORK. Nothing here steps a curve out of the grid. Every curved form
    is a CHAIN:
      * the torso is a barrel of staves -- four bands of plates (12 and 16
        around), each plate placed on the ellipse and turned to face outward,
        so the body's surface is a polygon that reads as a curve. The radius
        swings: a narrow waist between the pelvis and a wide chest is the whole
        read of the body;
      * the skull is a dome of plates pitched over the top, the shoulders are
        domes pitched across;
      * legs, arms, vines and the back growth are `chain()` limbs: each segment
        hinged on the joint above it, its rest angle carried on the ELEMENT, so
        a leg bows instead of stepping and the rig bends at real hinges;
      * each limb SEGMENT is itself a chain of plates -- `local_tube()` lays
        eight (or six) plates around the segment's own axis, each turned to face
        outward, so a limb is a polygon that follows its taper. A segment
        authored as one box shows four flat sides however it is rotated, and a
        chain of those is a staircase of boxes: that is the brickwork this whole
        model exists to avoid.

The creature, top to bottom:
  * a sealed iron head between the shoulders, its face pushed forward of the
    chest -- a dome of six plates, a heavy brow, eyes burning out of the dark,
    the golem's anvil nose grown long, cheek plates turned onto the skull,
    temple shards, and a jaw hanging open on a molten throat;
  * a barrel chest of staved plates with the left front split open: two staves
    are missing, the plate around them torn outward, and what shows through the
    gap is the MOVEMENT -- a big cog meshing with a small one, still lit from
    behind, where the molten heart used to be;
  * cogs at the joints: one bolted to the outside of each shoulder cap, one on
    the side of each knee, one on the golem's own elbow and a heavier one on
    the mutant's mass. A cog is two kinds of piece and nothing else -- a ring of
    big plates, and one tooth rooted in the middle of each plate;
  * and it is dressed as an emperor: a red corona radiata whose rays splay
    wider as they climb, a red skirt of pteruges hanging off the hip band under
    a sash and buckle, and a paludamentum -- nine chains of cloth pinned under
    the shoulder armour, draping down the back and swinging at the hem;
  * shoulders domed over the arms, rust bands, rivets;
  * the creature's RIGHT arm (-x) is the mutation: four segments ballooning
    16 -> 24 wide, hanging lower than its twin and reaching wider, ending in a
    fused wrecking mass whose plating has split and driven shards out. The left
    arm is the ordinary golem arm, so the pair is deliberately asymmetric;
  * an iron bloom growing out of the left shoulder blade: a chain curving up
    and back, splitting into shards at the tip;
  * vines, the golem's signature, overgrown: down the chest, down the back, and
    one spiralling the mutant arm, all thorned;
  * legs a third of the height (38 units of 113) on flat feet, bowed so the
    column reads as a limb rather than a post;
  * and it is dressed as an emperor: a red corona radiata whose rays splay wider
    as they climb, a red skirt of pteruges under a sash and buckle, and a
    paludamentum in three wide panels, its folds painted rather than carved.
    The only light left on the figure is the eyes, and it is arc-cold.

Palette: GOLD LEAF OVER A STEEL MECHANISM, WITH ROMAN DYE OVER THAT. The
shell -- staves, limbs, head -- is gold, darker on the limbs, because that value
break is what keeps an arm beside a chest legible; every band, bolt and cog is
steel, so the worked metal reads apart from the cast shell; the crevices go dark
bronze; the crown, the skirt and the cloak are one red, worked so the folds read
in the painter rather than in the geometry; and the vines keep their green
against all of it. The second texture is the emissive map: the eyes, the
gear train in the split chest, the joint seams that have opened, the bloom's
heart, the throat.

Geometry rules this script holds to (README.md conventions, ISSUE.md pitfalls):
  * every cube's SIZE is a whole number of units, so every face is an exact uv
    rect at S = 2 and there is nothing for stretch_report to report; positions
    are on the 0.5 grid wherever the cube is not rotated (chained and plated
    cubes sit wherever sin/cos puts them -- ISSUE.md 6.3);
  * rest angles live on ELEMENTS, every group sits at zero, so animation keys
    bend the rest pose instead of replacing it (ISSUE.md 6.2);
  * a plate or a segment butts its host or stands proud of it, and neighbours
    in a chain differ in width or depth, so no two same-facing faces end up in
    one plane (ISSUE.md 6.4);
  * 1 uv unit = 1 model unit, painted at 2 px/unit, noise per unit cell;
  * the TEXTURE is painted in MODEL SPACE: an atlas rect is keyed by material,
    face and the cube's position, and every painter samples a field that is a
    function of where it is on the creature. Pieces at different places are
    therefore never identical (the first version of this model put 3966 faces on
    340 rects, an 11.7x repeat with one tile used 160 times -- the "repeated
    material" the user could see at a glance), and pieces that touch sample the
    same field either side of the seam, so the shading and the folds run across
    the whole figure instead of restarting at every plate.

Deliberate overlaps (validate with interpenetration_depth raised if the gate
objects): neighbouring staves in a band overlap ~12% at their edges; the bands
butt in y; limb segments share a wedge at each joint; the head is sunk into the
shoulder band; armour collars are sunk 1 unit into the segment they ride; the
vine presses into the body it climbs; the bloom's base is buried in the chest.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.dont_write_bytecode = True
REPO = HERE
while not os.path.isfile(os.path.join(REPO, "tools", "bbmodel_kit.py")):
    parent = os.path.dirname(REPO)
    if parent == REPO:
        raise SystemExit(f"repo root not found above {HERE}")
    REPO = parent
sys.path.insert(0, os.path.join(REPO, "tools"))
from bbmodel_kit import (coplanar_conflicts, coplanar_visible,  # noqa: E402
                         stretch_report)
from bbmodel_build import (FM, S, TEX_BODY, TEX_GLOW, add_mirrors, at,  # noqa: E402
                           blobs, bounds, box, build_atlases, chain, check_grid,
                           check_painted, check_symmetric, dome, edge_lit, gear,
                           field3, group, kf, lift, local, local_gear, local_tube,
                           make_animation, put, ramp, rect_grid, render_previews,
                           ring, rng_for, side_tree, slab, spike, streaks, tint,
                           write_model)

OUT_DIR = HERE
MODEL_NAME = "mutant_iron_golem"
GLOW_MATERIALS = {"glow"}          # the eyes, and nothing else

# --- palette ---------------------------------------------------------------
# Weathered iron: the golem's own pale green-grey, going black in the pits.
GOLD_HI, GOLD, GOLD_MID, GOLD_DK, GOLD_DEEP = (
    (255, 230, 150), (232, 190, 92), (180, 136, 42), (112, 80, 22), (58, 40, 12))
# The barrel's staves: gold leaf, one polish brighter than the cast limbs.
PLT_HI, PLT, PLT_MID, PLT_DK, PLT_DEEP = (
    (255, 242, 186), (243, 210, 116), (196, 152, 52), (124, 90, 26), (64, 44, 14))
# Steel: the bands and every cog, so the mechanism reads apart from the shell.
STL_HI, STL, STL_MID, STL_DK, STL_DEEP = (
    (186, 192, 196), (134, 141, 146), (92, 98, 103), (58, 63, 67), (30, 33, 36))
SEAM_C = (54, 38, 14)
# The one light left on the figure is the eyes, and it is arc-cold: orange
# against gold just reads as more gold, and the user wanted the orange gone.
GLW_HI, GLW, GLW_MID, GLW_DK = (238, 250, 255), (168, 224, 246), (92, 176, 222), (34, 92, 138)
VIN_HI, VIN, VIN_MID, VIN_DK, VIN_DEEP = (
    (128, 166, 74), (92, 130, 52), (64, 100, 40), (42, 70, 30), (24, 42, 20))
THR_HI, THR, THR_DK = (206, 200, 178), (150, 144, 124), (92, 88, 74)
# Roman dye: the cloak, the skirt and the crown are all this red, worked so the
# folds read in the shading rather than in the geometry.
CLO_HI, CLO, CLO_MID, CLO_DK, CLO_DEEP = (
    (186, 52, 52), (140, 30, 34), (100, 20, 24), (64, 12, 16), (36, 7, 9))


# --- painters --------------------------------------------------------------
# Every painter here samples the model-space field (field3/rect_grid), so the
# pattern is a property of a POINT ON THE CREATURE, not of a tile: the shading
# runs down the whole figure, the folds of the cloak run across its seams, and
# no two plates carry the same pixels. Measured before this change: 3966 faces
# over 340 rects, an 11.7x repeat with one tile used 160 times.
def _mix(c0, c1, t):
    """c0 at t=0, c1 at t=1. `t` may be a scalar or a per-pixel (h, w) array."""
    t = np.asarray(t, float)
    if t.ndim == 0:
        return np.array(c0, float) * (1 - t) + np.array(c1, float) * t
    return (np.array(c0, float) * (1 - t[..., None])
            + np.array(c1, float) * t[..., None])


def _put(a, col):
    """Write a float colour field into the rect. The clip has to happen BEFORE
    the store: numpy casts a value of -4 or 300 into a uint8 array by wrapping
    it, so an unclipped highlight comes back as a purple blotch."""
    a[:, :, :3] = np.clip(np.asarray(col, float), 0, 255).astype(np.uint8)
    a[:, :, 3] = 255


def _edge(a, top, bottom, left=None, right=None):
    def c(v):
        v = np.clip(np.asarray(v, float), 0, 255)
        return tuple(v.astype(int)) if v.ndim else tuple(np.round([v] * 3).astype(int))
    edge_lit(a, top=c(top), bottom=c(bottom), left=left, right=right)


def _metal(cv, r, key, ramp, seed, up=False, blotch=None, blotch_at=0.80,
           streak=False, left=None, right=None):
    """The shared build for every metal on the figure, in four layers.

    1. `tone`, a single gradient in model space -- dark at the feet, bright at
       the crown -- so the shading runs down the whole figure and a plate's
       neighbour continues it instead of restarting;
    2. a per-UNIT speckle, sampled from the same field at unit resolution, so
       it is crisp like the rest of the project's noise but never repeats;
    3. a mid-scale blotch field for rust and tarnish;
    4. a shallow per-FACE ramp, which is the only part that does restart, and is
       what keeps a plate reading as a solid rather than a flat card.
    """
    a = at(cv, r)
    X, Y, Z = rect_grid(key, r)
    tone = np.clip((Y - 6.0) / 104.0, 0.0, 1.0)
    col = _mix(ramp[0], ramp[2] if up else ramp[1], tone)
    cell = field3(np.floor(X), np.floor(Y), np.floor(Z), 1.0, seed=seed)
    blob = field3(X, Y, Z, 4.5, seed=seed + 1)
    col *= (0.88 + 0.24 * cell)[..., None]
    col *= (0.94 + 0.12 * blob)[..., None]
    if streak:
        st = field3(X * 0.3, np.floor(Y), np.floor(Z), 1.0, seed=seed + 2)
        col -= (st < 0.12)[..., None] * 26.0
    if blotch is not None:
        col = np.where((blob > blotch_at)[..., None], _mix(col, blotch, 0.5), col)
    face = (np.arange(r[3]) / max(1, r[3] - 1))[:, None, None]
    col *= (1.18 - 0.34 * face)
    _put(a, col)
    _edge(a, col[0].mean(0) + 20, col[-1].mean(0), left, right)
    return a, col


def paint_gold(cv, r, key, dark=False, up=False):
    """The golem's gold. Limbs pass dark=True and ride the lower ramp."""
    ramp = (GOLD_DEEP, GOLD_MID, GOLD) if dark else (GOLD_DK, GOLD, GOLD_HI)
    _metal(cv, r, key, ramp, seed=1, up=up, blotch=PLT_DK, blotch_at=0.86,
           streak=True)


def paint_plate(cv, r, key, dark=False, up=False):
    """A stave of the barrel: the same gold, one polish brighter, with rivets."""
    ramp = (PLT_DEEP, PLT_MID, PLT) if dark else (PLT_DK, PLT, PLT_HI)
    a, col = _metal(cv, r, key, ramp, seed=11, up=up, blotch=PLT_DEEP,
                    blotch_at=0.88, left=PLT_DK, right=PLT_DK)
    h, w = a.shape[:2]
    if w >= 4 * S and 5 * S <= h <= 18 * S:
        for x in (S, w - 3 * S):
            cy = h // 2 - S // 2
            a[cy:cy + S, x:x + 2 * S, :3] = np.array(PLT_HI, np.uint8)


def paint_steel(cv, r, key, dark=False):
    """The mechanism: cool grey, flat shading, horizontal scratches."""
    ramp = (STL_DEEP, STL_MID, STL_HI) if dark else (STL_DK, STL, STL_HI)
    a = at(cv, r)
    X, Y, Z = rect_grid(key, r)
    tone = np.clip((Y - 6.0) / 104.0, 0.0, 1.0)
    col = _mix(ramp[0], ramp[1], tone)
    cell = field3(np.floor(X), np.floor(Y), np.floor(Z), 1.0, seed=21)
    scrub = field3(np.floor(X * 0.5), Y, Z, 5.0, seed=22)
    col *= (0.90 + 0.20 * cell)[..., None]
    col += (scrub - 0.5)[..., None] * 22.0
    face = (np.arange(r[3]) / max(1, r[3] - 1))[:, None, None]
    col *= (1.14 - 0.28 * face)
    _put(a, col)
    _edge(a, col[0].mean(0) + 22, col[-1].mean(0))


def paint_cloth(cv, r, key, dark=False, up=False):
    """Wool in the dye. The folds are a function of position in the model, not
    of the piece -- a slow wave in x plus a field-driven wander -- so a fold
    runs down the cloak and crosses the panel seams without restarting, which is
    the whole reason three wide panels read as one sheet."""
    a = at(cv, r)
    X, Y, Z = rect_grid(key, r)
    wander = field3(X, np.zeros_like(Y), Z, 26.0, seed=31)
    fold = 0.74 + 0.26 * (0.5 + 0.5 * np.sin(X * 1.15 + wander * 3.4))
    tone = np.clip((Y - 12.0) / 96.0, 0.0, 1.0)
    col = _mix(CLO_DEEP, CLO_HI if (up or not dark) else CLO, tone) * fold[..., None]
    fleck = field3(np.floor(X), np.floor(Y), np.floor(Z), 1.0, seed=32)
    col *= (0.90 + 0.20 * fleck)[..., None]
    col -= (1.0 - tone)[..., None] * 14.0                    # the hem soaks dark
    _put(a, col)
    _edge(a, col[0].mean(0) + 16, col[-1].mean(0))


def paint_vine(cv, r, key, dark=False):
    a = at(cv, r)
    X, Y, Z = rect_grid(key, r)
    tone = np.clip((Y - 6.0) / 104.0, 0.0, 1.0)
    col = _mix(VIN_DEEP, VIN_HI if not dark else VIN, tone)
    cell = field3(np.floor(X), np.floor(Y), np.floor(Z), 1.0, seed=41)
    vein = field3(np.floor(X * 2), np.floor(Y), np.floor(Z * 2), 2.0, seed=42)
    col *= (0.84 + 0.32 * cell)[..., None]
    col -= (vein < 0.22)[..., None] * 30.0
    face = (np.arange(r[3]) / max(1, r[3] - 1))[:, None, None]
    col *= (1.14 - 0.28 * face)
    _put(a, col)
    _edge(a, col[0].mean(0) + 18, col[-1].mean(0))


def paint_rust(cv, r, key, dark=False):
    """Tarnish patches; the bands themselves are painted as steel now."""
    a = at(cv, r)
    X, Y, Z = rect_grid(key, r)
    col = _mix(PLT_DEEP, PLT, np.clip((Y - 6.0) / 104.0, 0.0, 1.0))
    col *= (0.86 + 0.28 * field3(np.floor(X), np.floor(Y), np.floor(Z), 1.0,
                                seed=51))[..., None]
    _put(a, col)
    _edge(a, col[0].mean(0) + 18, col[-1].mean(0))


def paint_seam(cv, r, key):
    """The groove between two staves, and the inside of the body."""
    a = at(cv, r)
    rng = rng_for(key)
    a[:, :, :3] = np.array(SEAM_C, np.uint8)
    a[:, :, 3] = 255
    tint(a, rng, GOLD_DEEP, 0.16)
    tint(a, rng, STL_DEEP, 0.07)


def paint_glow(cv, r, key):
    """Emissive, and the only one left: the eyes. Arc-cold, and it falls off
    toward the rim of the plate so a two-unit slit still reads as a light."""
    a = at(cv, r)
    h, w = a.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    d = np.clip(np.sqrt(((yy - (h - 1) / 2) / max(1.0, h * 0.60)) ** 2 +
                        ((xx - (w - 1) / 2) / max(1.0, w * 0.60)) ** 2), 0, 1)
    a[:, :, :3] = np.clip(_mix(GLW_HI, GLW_DK, d), 0, 255).astype(np.uint8)
    a[:, :, 3] = 255


def paint_thorn(cv, r, key):
    a = at(cv, r)
    X, Y, Z = rect_grid(key, r)
    col = _mix(THR_DK, THR_HI, np.clip((Y - 6.0) / 104.0, 0.0, 1.0))
    col *= (0.88 + 0.20 * field3(X, Y, Z, 2.0, seed=61))[..., None]
    _put(a, col)
    _edge(a, col[0].mean(0) + 22, col[-1].mean(0))


PAINTERS = {
    "gold": lambda cv, r, k: paint_gold(cv, r, k),
    "gold_up": lambda cv, r, k: paint_gold(cv, r, k, up=True),
    "gold_dk": lambda cv, r, k: paint_gold(cv, r, k, dark=True),
    "plate": lambda cv, r, k: paint_plate(cv, r, k),
    "plate_hi": lambda cv, r, k: paint_plate(cv, r, k, up=True),
    "plate_dk": lambda cv, r, k: paint_plate(cv, r, k, dark=True),
    "steel": paint_steel,
    "steel_dk": lambda cv, r, k: paint_steel(cv, r, k, dark=True),
    "seam": paint_seam,
    "glow": lambda cv, r, k: paint_glow(cv, r, k),
    "glow_hot": lambda cv, r, k: paint_glow(cv, r, k, hot=True),
    "vine": lambda cv, r, k: paint_vine(cv, r, k),
    "vine_dk": lambda cv, r, k: paint_vine(cv, r, k, dark=True),
    "thorn": paint_thorn,
    "cloth": lambda cv, r, k: paint_cloth(cv, r, k),
    "cloth_hi": lambda cv, r, k: paint_cloth(cv, r, k, up=True),
    "cloth_dk": lambda cv, r, k: paint_cloth(cv, r, k, dark=True),
}

# Face maps. Which face is the "outside" depends on what the cube is:
#   * a stave of the barrel is turned by a yaw, and its local +z (`south`) is
#     the surface you see -- the other three sides are the grooves between
#     staves, so they are seam (PLATE);
#   * a dome plate is pitched, and its local +y (`up`) is the outside (DOME);
#   * armour wrapped around a limb (a knee cap, an arm collar) sticks out on
#     every side at once, so all four are metal (BAND) -- painting a collar's
#     sides as groove is what made the first version's arms read as black slabs.
PLATE = FM(all="plate", north="seam", east="seam", west="seam",
           up="plate_hi", down="plate_dk")
PLATE_DK = FM(all="plate_dk", north="seam", east="seam", west="seam",
              up="plate", down="seam")
DOME = FM(all="plate", north="seam", east="seam", south="seam", down="seam")
BAND = FM(all="plate", up="plate_hi", down="plate_dk")
BAND_DK = FM(all="plate_dk", up="plate", down="seam")
GOLDF = FM(all="gold", up="gold_up", down="gold_dk")
GOLDF_DK = FM(all="gold_dk", up="gold", down="seam")
STEELB = FM(all="steel", up="steel", down="steel_dk")
GLOWF = FM(all="glow")
COREF = FM(all="glow_hot")
VINEF = FM(all="vine", up="vine", down="vine_dk")
THORNF = FM(all="thorn")
CLOTHF = FM(all="cloth", up="cloth_hi", down="cloth_dk")
CLOTHB = FM(all="cloth_dk", up="cloth", down="cloth_dk")

# --- the body plan, in one place -------------------------------------------
# Bands are (name, centre y, half-width a, half-depth b, staves, height, thick):
# a band's plates straddle the ellipse, so the outer surface is a + thick/2.
# Four of them, and the radius has to SWING: a narrow waist between the pelvis
# and a wide chest is the whole read of the body. Bands of near-equal radius
# read as a wedding cake (v1) and one straight-sided trapezoid reads as a slab
# with grooves (v2); it is the hourglass that says "chest over pelvis".
BANDS = [
    ("hipband", 27.0, 13.5, 10.5, 12, 10.0, 4.0),      # y 22..32
    ("waistband", 37.0, 11.0, 9.0, 12, 8.0, 4.0),      # y 33..41
    ("chestband", 47.5, 17.0, 12.5, 16, 13.0, 5.0),    # y 41..54
    ("shldrband", 58.0, 18.5, 13.0, 16, 8.0, 5.0),     # y 54..62
]
# The chest staves missing on the front-left: the mutation split the chest open,
# and the core burns through the hole.
RUPTURE = ("chestband", 1, 2)
# The shoulder joint, in x and y. The arm hangs outboard of the barrel's shell
# so the limb keeps its own silhouette -- a joint at the shell's surface buries
# the whole arm in the torso (v1) and the limbs merge with the chest (v2).
SHOULDER = (22.0, 54.0)


# --- the creature ----------------------------------------------------------
def build_leg():
    """A leg as a chain of tubes: the thigh bows out, the shin brings the column
    back under the hips, the foot plants. Knee ring, rust band and sole ride the
    segment they belong to, so the knee is a real hinge."""
    host = group("leg_l", origin=(10.5, 38, 0), cubes=[])
    thigh, shin, foot = chain(host, "leg_l", (10.5, 38, 0), "-y", [
        ("thigh", 19, 11, 13, (0, 0, 10), GOLDF_DK),
        ("shin", 15, 9, 11, (0, 0, -12), GOLDF_DK),
        ("foot", 5, 18, 21, (0, 0, 0), GOLDF_DK),
    ])
    put(thigh,
        *local_tube(thigh, 7, 8, 4, GOLDF_DK, "thigh_l", n=8, phase=22.5),
        *local_tube(thigh, 8, 9, 3, STEELB, "thigh_rust_l", n=8, phase=22.5,
                    length=4, mid=-7),
        *local_tube(thigh, 8, 9, 4, BAND, "knee_l", n=8, phase=22.5,
                    length=4, mid=-17),
        *local_gear(thigh, 7, 10, 6, STEELB, "kneeg_l", mid=-17, out=10,
                   tooth=3, inner=2),
    )
    put(shin,
        *local_tube(shin, 6, 7, 4, GOLDF_DK, "shin_l", n=6),
        *local_tube(shin, 7, 8, 3, STEELB, "ankle_l", n=8, phase=22.5,
                    length=4, mid=-12),
        local(shin, 0, -3, -9.5, (4, 3, 3), BAND_DK, "shin_torn_l"),
    )
    put(foot,
        local(foot, 0, -1, -11, (8, 3, 5), BAND, "toe_i_l"),
        local(foot, -6, -1, -10, (5, 4, 5), BAND, "toe_o_l"),
        local(foot, 0, -1, 11, (11, 3, 5), BAND, "heel_l"),
        local(foot, 0, -2, 0, (19, 3, 22), STEELB, "sole_l"),
    )
    return host


def build_hips():
    """The pelvis band, a crotch plate closing it underneath, a rust scab where
    the plating has come away, and a bolt on each hip."""
    cubes = ring(*BANDS[0], PLATE)
    cubes += [
        slab("crotch", (0, 21.5, -1), (17, 3, 15), (0, 0, 0), BAND),
        slab("hip_scab_l", (10, 30, -8), (7, 5, 3), (0, -24, 6), STEELB),
        slab("hip_bolt_l", (14.5, 26, 0), (3, 4, 5), (0, 90, 0), BAND),
        slab("hip_back_l", (8, 29, 9), (8, 6, 3), (0, 30, -4), BAND_DK),
    ] + build_skirt()
    return group("hips", origin=(0, 25, 0), cubes=cubes)


def build_rupture():
    """Where the chest gave way: two staves torn out of line at the hole's
    edges, and the core showing through the gap as narrow splits rather than a
    lit doorway -- a wide flat glow panel reads as a hatch (v2 did). Its own
    group, `_l`-marked, because it is on one side only: a centre group's cubes
    all have to straddle x = 0."""
    return group("rupture_l", origin=(0, 47.5, 0), cubes=[
        slab("chest_torn0_l", (15.5, 52, -11), (9, 7, 4), (22, 24, 16), BAND_DK),
        slab("chest_torn1_l", (15, 43, -11), (9, 7, 4), (-20, 24, 14), BAND_DK),
        slab("chest_rim_l", (11, 53.5, -10), (11, 3, 6), (0, 42, 0), BAND_DK),
    ] + gear("chgear_big", (11.5, 46, -11), 6.5, 12, 5, STEELB, axis="z",
             tooth=3, inner=2, hub=5) + gear("chgear_small", (12.5, 40, -13), 4, 10, 4,
                                    STEELB, axis="z", tooth=3, inner=1, phase=15)
      + [
    ])


def build_torso():
    """Waist, chest and shoulder bands, the spine running down the back, a rust
    scab, and the shelf the head stands on. The torn-out chest staves are
    build_rupture()'s business."""
    cubes = []
    for name, cy, a, b, n, h, t in BANDS[1:]:
        staves = ring(name, cy, a, b, n, h, t, PLATE)
        if name == RUPTURE[0]:
            torn = set(RUPTURE[1:])
            staves = [s for i, s in enumerate(staves) if i not in torn]
        cubes += staves
    cubes += [
        slab("spine_up", (0, 57, 14), (12, 11, 4), (0, 0, 0), BAND_DK),
        slab("spine_lo", (0, 44, 10), (10, 12, 4), (0, 0, 0), BAND_DK),
        slab("back_scab_l", (11, 45, 10), (8, 7, 3), (0, 34, 5), STEELB),
        # 88 degrees, not 90: a bolt yawed exactly like the stave it sits on shares
        # that stave's face planes (the coplanar gate compares cubes with the
        # same total rotation), and two degrees is under a pixel
        slab("waist_bolt_l", (12, 37, 0), (3, 3, 5), (0, 88, 0), BAND),
        # the shoulder shelf: the top of the barrel, so the head has a floor
        slab("shelf", (0, 62.5, 1), (28, 3, 18), (0, 0, 0), BAND),
        slab("shelf_lip_l", (15.5, 64.5, 1), (5, 2, 17), (0, 0, 0), STEELB),
    ]
    return group("spine", origin=(0, 32, 0), cubes=cubes)


def build_head():
    """The skull: a box between the shoulders wearing a dome of six plates, with
    the face pushed FORWARD of the chest -- the anvil nose and the brow have to
    stand proud of the barrel's front plane or the head reads as a box
    half-buried in the shoulders (v2). Plus eyes burning out of the dark, cheeks
    turned onto the skull, temple shards, and a jaw hanging open."""
    jaw = group("jaw", origin=(0, 60, -6), cubes=[
        box("jaw", BAND_DK, (-8, 53, -21), (8, 59, -13),
            rot=(-22, 0, 0), origin=(0, 60, -6)),
        box("jaw_chin", BAND_DK, (-6, 50, -20), (6, 54, -14),
            rot=(-22, 0, 0), origin=(0, 60, -6)),
        box("jaw_tooth_l", THORNF, (2, 57, -20), (5, 61, -17),
            rot=(-22, 0, 0), origin=(0, 60, -6)),
    ])
    cubes = [
        box("skull", GOLDF, (-8, 62, -12), (8, 80, 4)),
        box("crown", GOLDF, (-6, 80, -11), (6, 87, 3)),
        box("nose", BAND, (-4, 63, -20), (4, 75, -12)),
        # brow, eyes, cheeks and temples: plates turned onto the skull, so the
        # face is a set of surfaces rather than a row of boxes
        slab("brow", (0, 78, -14), (18, 6, 6), (-14, 0, 0), BAND),
        slab("socket_l", (4.5, 74, -12.5), (6, 5, 3), (0, -12, 0), FM(all="seam")),
        slab("eye_l", (4.5, 74, -14.5), (4, 3, 2), (0, -12, 0), GLOWF),
        slab("nose_lip", (0, 61.5, -17), (11, 3, 4), (12, 0, 0), BAND),
        slab("nose_step", (0, 76.5, -13), (7, 4, 4), (8, 0, 0), BAND_DK),
        slab("cheek_l", (9, 72, -6), (4, 11, 13), (0, -14, -8), BAND_DK),
        slab("temple_l", (7, 82, -1), (5, 6, 9), (0, 20, 6), BAND_DK),
    ] + dome("skullcap", (0, 80, -4), 10.0, 6, -74, 74, 17, 6, DOME) \
      + build_crown() \
      + spike("temple_shard_l", THORNF, (6, 78, -5), (10, 82, -1), "+z", 2, 3) \
      + spike("cheek_shard_l", THORNF, (8, 70, -4), (11, 72, 0), "+z", 2, 2)
    return group("head", origin=(0, 62, -3), cubes=cubes, children=[jaw])


def build_shoulder():
    """A dome of plates pitched across the shoulder joint, sitting on the
    barrel's top band: the golem's shoulder, not a pauldron."""
    return group("shoulder_l", origin=(SHOULDER[0], SHOULDER[1], 0), cubes=
                 dome("cap", (SHOULDER[0], 55.0, 0), 9.0, 5, -36, 100, 15, 5,
                      DOME)
                 + gear("shgear", (SHOULDER[0] + 6, 60, 0), 6.5, 10, 6, STEELB,
                        axis="x", tooth=4, inner=2)
                 + [slab("cap_rust_l", (23, 61, 5), (6, 4, 6), (-14, 0, 20),
                         STEELB)])


def build_arm_l():
    """The golem's own arm on the left: three segments hanging with a mild
    splay, banded at the elbow and wrist, ending in the flat splayed hand it
    plants on the ground. Deliberately the plain one -- the mutation is on the
    other side."""
    host = group("arm_l", origin=(SHOULDER[0], SHOULDER[1], 0), cubes=[])
    upper, fore, hand = chain(host, "arm_l", (SHOULDER[0], SHOULDER[1], 0), "-y", [
        ("upper", 18, 11, 13, (0, 0, 10), GOLDF_DK),
        ("fore", 16, 9, 11, (0, 0, 10), GOLDF_DK),
        ("hand", 8, 15, 16, (0, 0, 6), GOLDF_DK),
    ])
    put(upper,
        *local_tube(upper, 8, 9, 4, GOLDF_DK, "upper_l", n=8, phase=22.5),
        *local_tube(upper, 9, 10, 3, STEELB, "upper_band_l", n=8, phase=22.5,
                    length=4, mid=-11),
        *local_tube(upper, 9.5, 10.5, 4, BAND, "elbow_l", n=8, phase=22.5,
                    length=5, mid=-16),
        *local_gear(upper, 6.5, 10, 6, STEELB, "elbowg_l", mid=-16, out=10,
                   tooth=3, inner=2),
    )
    put(fore,
        *local_tube(fore, 7, 8, 4, GOLDF_DK, "fore_l", n=6),
        *local_tube(fore, 8, 9, 3, STEELB, "wrist_band_l", n=8, phase=22.5,
                    length=4, mid=-12),
    )
    put(hand,
        local(hand, 0, -2, 0, (17, 5, 18), BAND, "hand_plate_l"),
        local(hand, 5, -7, -9, (3, 6, 5), GOLDF_DK, "finger0_l"),
        local(hand, 0, -7, -9, (3, 6, 5), GOLDF_DK, "finger1_l"),
        local(hand, -5, -7, -9, (3, 6, 5), GOLDF_DK, "finger2_l"),
        local(hand, -7.5, -5, -3, (3, 5, 6), GOLDF_DK, "thumb_l"),
    )
    return host


def local_spike(seg, x, y, z, size, mat, name, steps=3, grow=0.35, drop=0.55,
                tip=None):
    """A shard riding a chain segment: `steps` boxes marching out along the
    segment's own axes, shrinking as they go, the last one pale. local() takes
    one box at a time; a shard needs a run of them that stays in the frame."""
    w, h, d = size
    out = []
    for i in range(steps):
        k = 1.0 - 0.25 * i
        out.append(local(seg, x * (1 + grow * i), y - drop * h * i, z * (1 + grow * i),
                         (max(1, round(w * k)), max(1, round(h * k)),
                          max(1, round(d * k))),
                         mat if (tip is None or i < steps - 1) else tip, f"{name}{i}"))
    return out


def build_arm_r():
    """The mutation: the creature's right arm (-x) has kept growing -- four
    segments ballooning 16 -> 24 wide, hanging lower than its twin and reaching
    wider, ending in a fused wrecking mass whose plating has split and driven
    shards out. Asymmetric on purpose; the MCP mirror gate is told so."""
    host = group("arm_r", origin=(-SHOULDER[0], SHOULDER[1], 0), cubes=[])
    upper, mass, fore, fist = chain(host, "arm_r",
                                    (-SHOULDER[0], SHOULDER[1], 0), "-y", [
        ("upper", 14, 10, 12, (0, 0, -12), GOLDF_DK),
        ("mass", 12, 9, 11, (0, 0, -20), GOLDF_DK),
        ("fore", 11, 16, 19, (0, 0, -24), GOLDF_DK),
        ("fist", 8, 18, 21, (0, 0, -16), GOLDF_DK),
    ])
    put(upper,
        *local_tube(upper, 8, 9, 4, GOLDF_DK, "m_upper_r", n=8, phase=22.5),
        *local_tube(upper, 9, 10, 3, STEELB, "m_band_r", n=8, phase=22.5,
                    length=4, mid=-9),
    )
    put(mass,
        *local_tube(mass, 7.5, 8.5, 4, GOLDF_DK, "m_mass_r", n=8, phase=22.5),
        *local_tube(mass, 8.5, 9.5, 3, STEELB, "m_band2_r", n=8, phase=22.5,
                    length=5, mid=-9),
        *local_gear(mass, 8, 10, 6, STEELB, "m_gearg_r", mid=-6, out=-11,
                   tooth=4, inner=2),
    )
    put(fore,
        *local_tube(fore, 10, 11.5, 4, GOLDF_DK, "m_fore_r", n=8, phase=22.5),
        *local_tube(fore, 11.5, 13, 3, STEELB, "m_band3_r", n=8, phase=22.5,
                    length=5, mid=-8),
        *local_tube(fore, 12, 13.5, 4, BAND, "m_knuckle_r", n=8, phase=22.5,
                    length=6, mid=-11),
    )
    # the wrecking mass: plating split open on the front, shards driven out
    put(fist,
        *local_tube(fist, 11, 12.5, 4, GOLDF_DK, "m_fist_r", n=8, phase=22.5),
        *local_tube(fist, 12, 13.5, 3, STEELB, "m_sole_r", n=8, phase=22.5,
                    length=4, mid=-6.5),
        local(fist, 10, -4, -11, (5, 6, 5), BAND_DK, "m_torn_r0"),
        local(fist, -10, -4, -11, (5, 6, 5), BAND_DK, "m_torn_r1"),
        *local_spike(fist, 10, -5.5, 8, (4, 4, 4), BAND_DK, "m_shard0_r", steps=2,
                     grow=0.2, drop=0.5),
        *local_spike(fist, -10, -5.5, 8, (4, 4, 4), BAND_DK, "m_shard1_r", steps=2,
                     grow=0.2, drop=0.5, tip=BAND_DK),
        *local_spike(fist, 0, -4.5, -12, (4, 4, 4), BAND_DK, "m_shard2_r", steps=2,
                     grow=0.2, drop=0.5),
    )
    return host


def build_vine_front():
    """A vine down the chest: a chain whose segments each add a little pitch and
    yaw, so it snakes down the barrel and presses into the body it climbs
    instead of hanging beside it like a rope."""
    host = group("vine_f_l", origin=(14, 62, -9), cubes=[])
    segs = chain(host, "vine_f_l", (14, 62, -9), "-y", [
        ("s0", 8, 3, 3, (14, 0, 6), VINEF),
        ("s1", 8, 3, 3, (9, 0, 10), VINEF),
        ("s2", 8, 3, 3, (4, 0, 5), VINEF),
        ("s3", 8, 3, 3, (0, 0, -3), VINEF),
        ("s4", 8, 3, 3, (3, 0, -9), VINEF),
        ("s5", 7, 3, 3, (7, 0, -8), VINEF),
    ])
    for i, s in enumerate(segs):
        put(s, local(s, 0, -4, 0, (2, 5, 2), VINEF, f"vf{i}_stem_l"))
        if i % 2 == 0:
            put(s, local(s, 2.5, -3, -1.5, (4, 1, 3), VINEF, f"vf{i}_leaf_l"))
        if i % 3 == 1:
            put(s, local(s, -2.5, -5, 1, (3, 2, 2), THORNF, f"vf{i}_thorn_l"))
    return host


def build_vine_back():
    """The same on the back, hanging off the spine plates."""
    host = group("vine_b_l", origin=(-11, 58, 13), cubes=[])
    segs = chain(host, "vine_b_l", (-11, 58, 13), "-y", [
        ("s0", 8, 3, 3, (-8, 0, -8), VINEF),
        ("s1", 8, 3, 3, (-4, 0, -6), VINEF),
        ("s2", 8, 3, 3, (0, 0, 2), VINEF),
        ("s3", 8, 3, 3, (2, 0, 8), VINEF),
        ("s4", 7, 3, 3, (0, 0, 12), VINEF),
    ])
    for i, s in enumerate(segs):
        put(s, local(s, 0, -4, 0, (2, 5, 2), VINEF, f"vb{i}_stem_l"))
        if i % 2 == 1:
            put(s, local(s, -2.5, -3, 1.5, (4, 1, 3), VINEF, f"vb{i}_leaf_l"))
        if i % 3 == 2:
            put(s, local(s, 2.5, -5, -1, (3, 2, 2), THORNF, f"vb{i}_thorn_l"))
    return host


def build_vine_arm():
    """The one that has taken the mutant arm. A vine wraps by walking AROUND the
    limb, so its segments' direction has to swing in a cone about the arm's
    axis: pitch and roll (rx / rz) step a fifth of a turn each segment, which
    spirals the chain down and around the swelling iron. (Roll alone -- the y
    rotation -- would just twist each segment in place; the direction of a '-y'
    chain is invariant under it.)"""
    import math
    base_rz = -22.0                       # the direction the arm itself hangs
    spec = []
    for i in range(5):
        ph = math.radians(72.0 * i)
        spec.append((f"s{i}", 7, 3, 3,
                     (round(26 * math.cos(ph), 1), 0.0,
                      round(base_rz + 26 * math.sin(ph), 1)), VINEF))
    host = group("vine_a_r", origin=(-30, 34, -11), cubes=[])
    segs = chain(host, "vine_a_r", (-30, 34, -11), "-y", spec)
    for i, s in enumerate(segs):
        put(s, local(s, 0, -3.5, 0, (2, 4, 2), VINEF, f"va{i}_stem_r"))
        if i % 2 == 0:
            put(s, local(s, 2.5, -3, 0, (4, 1, 4), VINEF, f"va{i}_leaf_r"))
        put(s, local(s, 0, -5.5, -2.5, (3, 2, 2), THORNF, f"va{i}_thorn_r"))
    return host


def build_bloom():
    """The growth on the left shoulder blade: a chain curving up and back, its
    segments shrinking, splitting into shards where the iron has given way. The
    shape is the point -- a horn of iron, not a stack of blocks."""
    host = group("bloom_l", origin=(13, 58, 10), cubes=[])
    segs = chain(host, "bloom_l", (13, 58, 10), "+y", [
        ("b0", 5, 10, 10, (16, 0, 10), GOLDF),
        ("b1", 5, 8, 8, (30, 0, 14), GOLDF),
        ("b2", 4, 6, 6, (42, 0, 17), BAND_DK),
        ("b3", 3, 4, 4, (52, 0, 19), BAND_DK),
    ])
    put(segs[0], local(segs[0], 0, 3, -4, (8, 5, 3), STEELB, "bloom_rust_l"))
    tip = segs[-1]
    put(tip,
        local(tip, 0, 4, 0, (5, 3, 5), BAND_DK, "bloom_core_l"),
        local(tip, 3, 3, 0, (3, 4, 3), THORNF, "bloom_shard0_l"),
        local(tip, -3, 3, 0, (3, 4, 3), THORNF, "bloom_shard1_l"),
        local(tip, 0, 3, 3, (3, 4, 3), THORNF, "bloom_shard2_l"),
        local(tip, 0, 5, 0, (2, 3, 2), THORNF, "bloom_shard3_l"),
    )
    segs[0]["group"]["cubes"] += spike("bloom_spur_l", THORNF, (10, 64, 12),
                                       (13, 69, 15), "+y", 2, 3)
    return host



# --- the Roman kit ---------------------------------------------------------
def crown_rays(prefix, centre, r, y0, n, segs):
    """A radiant crown: `n` rays standing round a band, each one a short chain
    that leans further outward as it rises, so a ray CURVES instead of stepping.
    Authoring the left half and letting add_mirrors() close the circle keeps the
    mirror gate exact, exactly as ring() does.
    """
    import math
    from bbmodel_kit import V, rot_ZYX
    steps = n // 2
    out = []
    for i in range(steps + 1):
        psi = 180.0 * i / max(1, steps)
        s_, c_ = math.sin(math.radians(psi)), math.cos(math.radians(psi))
        p = V(centre[0] + r * s_, y0, centre[2] - r * c_)
        for k, seg in enumerate(segs):
            L, w, d, pitch = seg[:4]
            mat = seg[4] if len(seg) > 4 else CLOTHF
            R = rot_ZYX(pitch, psi, 0.0)
            mid = p + R @ V(0.0, L / 2.0, 0.0)
            name = f"{prefix}{i}{k}" + ("_l" if 0 < i < steps else "")
            out.append(slab(name, (mid[0], mid[1], mid[2]), (w, L, d),
                            (pitch, psi, 0.0), mat))
            p = p + R @ V(0.0, L, 0.0)
    return out


def skirt_strips(prefix, cy, a, b, n, h, thick, flare, mat):
    """Pteruges: the strips of a Roman soldier's skirt. Each strip is a plate
    turned to face outward, flared at the hem, and cut NARROWER than its chord
    so the gaps are real -- a closed ring of plates reads as one carved cone,
    and a skirt is a run of separate strips."""
    import math
    steps = n // 2
    out = []
    for i in range(steps + 1):
        psi = 180.0 * i / steps
        s_, c_ = math.sin(math.radians(psi)), math.cos(math.radians(psi))
        px, pz = a * s_, -b * c_
        yaw = math.degrees(math.atan2(b * s_, -a * c_))
        arc = max(2, math.floor(2 * a * math.sin(math.pi / n) * 0.80))
        name = f"{prefix}{i:02d}" + ("_l" if px > 1e-6 else "")
        out.append(slab(name, (px, cy, pz), (arc, h, thick),
                        (-flare, yaw, 0.0), mat))
    return out


def build_crown():
    """The crown: a red band round the head and eight red rays rising out of it
    and splaying wider as they climb, the front and back rays authored as centre
    parts and the rest mirrored. This is the corona radiata -- the radiate crown
    Roman emperors are drawn in -- and it is the model's one bit of pure
    silhouette, so the rays are long and few: a dozen short thick ones read as a
    red cap, which is exactly what the first try looked like."""
    return (ring("crownband", 84.0, 9.0, 9.0, 12, 5.0, 3.0, CLOTHB, cz=-4.0)
            + ring("crownlip", 87.0, 9.5, 9.5, 10, 2.0, 3.0, CLOTHF, cz=-4.0)
            + crown_rays("crownray", (0.0, 0.0, -4.0), 9.0, 86.5, 8,
                         [(8, 3, 3, -14), (7, 2, 2, -38, CLOTHB)]))


def build_skirt():
    """The skirt over the pelvis, with a red sash belt and a steel buckle over
    it. It hangs off the hip band and covers the top of the thighs."""
    import math
    out = skirt_strips("skirt", 16.0, 15.0, 12.0, 14, 14.0, 3.0, 14.0, CLOTHF)
    out += ring("sash", 23.0, 15.0, 12.0, 14, 5.0, 3.0, CLOTHB)
    out += [slab("buckle", (0, 23, -13.5), (7, 6, 4), (0, 0, 0), BAND),
            slab("buckle_gem", (0, 23, -15), (4, 4, 3), (0, 0, 0), BAND_DK)]
    return out


def build_cloak():
    """The paludamentum: the general's cloak, pinned under the shoulder armour
    and hanging down the back.

    Nine narrow strips were too dense and too repetitive -- the seams were doing
    work the cloth should do. Three panels of sixteen units with a single bend
    each read as one sheet; the fold shading is painted, and the panels take
    different thicknesses so the corners they share are never in one plane. The
    arms hang clear: the panels stay behind the shoulder line (psi 135..225).
    """
    import math
    host = group("cloak", origin=(0, 63, 16), cubes=[])
    for i, psi in enumerate((135.0, 180.0, 225.0)):
        s_, c_ = math.sin(math.radians(psi)), math.cos(math.radians(psi))
        j = (19.0 * s_, 63.0, -16.0 * c_)
        side = "_l" if j[0] > 1e-6 else ("_r" if j[0] < -1e-6 else "")
        # the panel at 225 is the mirror of the one at 135, so it is cloak0_r:
        # the mirror gate pairs by the swapped name (ISSUE.md 12)
        idx = i if i <= 1 else 0
        segs = [(f"s{k}", L, w, t, (-f, psi - 180.0, 0.0), CLOTHF)
                for k, (L, w, t, f) in enumerate(((24, 16, 3, 5.0),
                                                  (22, 17, 4, 13.0)))]
        chain(host, f"cloak{idx}{side}", j, "-y", segs)
    return host


# --- assembly --------------------------------------------------------------
BODY_LIFT = 13.0        # the legs got longer; the body rides up with them


def assemble() -> dict:
    hips = lift(add_mirrors(build_hips()), BODY_LIFT)
    torso = add_mirrors(build_torso())
    head = add_mirrors(build_head())
    torso["children"] += [head]
    # The mutation: the mutant arm, the growth on the left shoulder blade, the
    # vine that has taken the arm and the chest split are authored ONCE and
    # never mirrored. So is the golem's own left arm -- it has no twin to be
    # mirrored into, because the right shoulder grew the other thing.
    for build in (build_arm_l, build_arm_r, build_bloom, build_vine_arm,
                  build_rupture):
        torso["children"] += [build()]
    torso["children"] += [build_cloak()]
    for build in (build_shoulder, build_vine_front, build_vine_back):
        half = side_tree("_l", build())
        torso["children"] += [half, side_tree("_r", half)]
    hips["children"] += [lift(torso, BODY_LIFT)]
    for build in (build_leg,):
        half = side_tree("_l", build())
        hips["children"] += [half, side_tree("_r", half)]
    return group(MODEL_NAME, children=[hips], origin=(0, 0, 0))


# Clip poses: the offline renderer bakes a clip at a time into the transforms
# (tools/preview_bbmodel.py --clip/--time), which is the only way to look at a
# joint chain actually bent.
POSES = [("_idle", "animation.mutant_iron_golem.idle", 1.6)]


def pose_previews(model_path: str) -> None:
    tool = os.path.join(REPO, "tools", "preview_bbmodel.py")
    for suffix, clip, t in POSES:
        out = os.path.join(OUT_DIR, f"{MODEL_NAME}_preview{suffix}.png")
        subprocess.run([sys.executable, tool, model_path, out, "--size", "760",
                        "--azimuth", "205", "--elevation", "8", "--distance", "158",
                        "--target", "0", "50", "0", "--clip", clip, "--time", str(t)],
                       check=True)


PREVIEWS = [
    ("", 205.0, 10.0, 196.0, (0.0, 50.0, 0.0)),
    ("_front", 180.0, 6.0, 196.0, (0.0, 50.0, 0.0)),
    ("_side", 270.0, 8.0, 196.0, (0.0, 50.0, 0.0)),
    ("_back", 0.0, 10.0, 196.0, (0.0, 50.0, 0.0)),
    ("_head", 202.0, 8.0, 84.0, (0.0, 80.0, -6.0)),
    ("_chest", 208.0, 6.0, 64.0, (6.0, 46.0, -8.0)),
    ("_armr", 232.0, 8.0, 110.0, (-28.0, 30.0, 0.0)),
    ("_leg", 220.0, 6.0, 74.0, (11.0, 16.0, 0.0)),
]


# --- animation -------------------------------------------------------------
def build_animations(by_name: dict) -> list:
    """One idle: the golem is heavy, so it is slow -- it settles on its feet, the
    mass of the mutant arm drags the whole torso over, the head swings, and the
    vines lag behind everything.

    Every key is a DELTA: a chain's rest angle lives on the element and the
    chain groups sit at zero, so keying a group bends the limb further instead
    of straightening it (ISSUE.md 6.2).

    Sign convention (measured against tools/preview_bbmodel.py): for a limb
    hanging along -y, +rx swings the far end forward (-z) and +rz swings it
    toward +x; for the bloom, which runs along +y, +rx leans it back (+z).
    """
    def sway(amp, period=6.0, lag=0.0, sgn=1.0):
        return [kf("rotation", t, (0, round(sgn * float(amp * np.sin(
            2 * np.pi * (t / period) - lag)), 2), 0), "catmullrom")
            for t in (0.0, 1.5, 3.0, 4.5, 6.0)]

    tracks = {
        "mutant_iron_golem": [[kf("position", t, (0, y, 0), "catmullrom")
                               for t, y in ((0.0, 0.0), (1.5, 1.0), (3.0, 0.2),
                                            (4.5, 0.8), (6.0, 0.0))]],
        "hips": [[kf("rotation", t, (0, 0, rz), "catmullrom")
                  for t, rz in ((0.0, 0.0), (1.5, -1.5), (3.0, 0.5), (6.0, 0.0))]],
        "spine": [[kf("rotation", t, (rx, ry, rz), "catmullrom") for t, rx, ry, rz in
                   ((0.0, 0, 0, 0), (1.5, 1.5, -2.0, -2.0), (2.6, 0.5, 1.5, -0.5),
                    (4.2, 0.8, -1.0, -1.5), (6.0, 0, 0, 0))]],
        "head": [[kf("rotation", t, (rx, ry, 0), "catmullrom") for t, rx, ry in
                  ((0.0, 0, 0), (1.2, 3.0, 7.0), (2.4, -2.0, -6.0), (3.6, 1.5, 4.0),
                   (6.0, 0, 0))]],
        "jaw": [[kf("rotation", t, (rx, 0, 0), "catmullrom")
                 for t, rx in ((0.0, 0.0), (1.5, -5.0), (2.5, -1.0), (6.0, 0.0))]],
        "shoulder_l": [[kf("rotation", t, (0, 0, rz), "catmullrom")
                        for t, rz in ((0.0, 0.0), (1.5, -2.0), (3.0, 1.0), (6.0, 0.0))]],
        "shoulder_r": [[kf("rotation", t, (0, 0, -rz), "catmullrom")
                        for t, rz in ((0.0, 0.0), (1.5, -2.0), (3.0, 1.0), (6.0, 0.0))]],
        "arm_l_upper": [[kf("rotation", t, (rx, 0, rz), "catmullrom") for t, rx, rz in
                         ((0.0, 0, 0), (1.6, -2.0, -3.0), (3.2, 1.0, 1.5), (6.0, 0, 0))]],
        "arm_l_fore": [[kf("rotation", t, (rx, 0, 0), "catmullrom")
                        for t, rx in ((0.0, 0.0), (1.8, -4.0), (3.4, 1.0), (6.0, 0.0))]],
        # the mutant arm swings slower and further: it is the heavy side
        "arm_r_upper": [[kf("rotation", t, (rx, 0, rz), "catmullrom") for t, rx, rz in
                         ((0.0, 0, 0), (1.8, -3.0, 3.0), (3.4, 1.5, -1.5), (6.0, 0, 0))]],
        "arm_r_mass": [[kf("rotation", t, (rx, 0, rz), "catmullrom") for t, rx, rz in
                        ((0.0, 0, 0), (2.0, -2.0, 2.0), (3.6, 1.0, -1.0), (6.0, 0, 0))]],
        "arm_r_fore": [[kf("rotation", t, (rx, 0, 0), "catmullrom")
                        for t, rx in ((0.0, 0.0), (2.2, -3.0), (3.8, 1.5), (6.0, 0.0))]],
        "leg_l_thigh": [[kf("rotation", t, (0, 0, rz), "catmullrom")
                         for t, rz in ((0.0, 0.0), (3.0, 1.0), (6.0, 0.0))]],
        "leg_r_thigh": [[kf("rotation", t, (0, 0, -rz), "catmullrom")
                         for t, rz in ((0.0, 0.0), (3.0, 1.0), (6.0, 0.0))]],
        "bloom_l_b0": [[kf("rotation", t, (rx, ry, 0), "catmullrom") for t, rx, ry in
                        ((0.0, 0, 0), (1.6, -2.5, 2.0), (3.2, 1.0, -1.0), (6.0, 0, 0))]],
        "bloom_l_b1": [[kf("rotation", t, (rx, ry, 0), "catmullrom") for t, rx, ry in
                        ((0.0, 0, 0), (1.9, -3.5, 3.0), (3.5, 1.5, -1.5), (6.0, 0, 0))]],
        "bloom_l_b2": [[kf("rotation", t, (rx, ry, 0), "catmullrom") for t, rx, ry in
                        ((0.0, 0, 0), (2.2, -4.0, 4.0), (3.8, 2.0, -2.0), (6.0, 0, 0))]],
        "bloom_l_b3": [[kf("rotation", t, (rx, ry, 0), "catmullrom") for t, rx, ry in
                        ((0.0, 0, 0), (2.5, -5.0, 5.0), (4.1, 2.5, -2.5), (6.0, 0, 0))]],
    }
    # the cloak swings like cloth: the hem leads, the middle follows, and the
    # strips further back lag a little more than the ones at the shoulders
    cloak = {}
    for i, panel in enumerate(("cloak0_l", "cloak1", "cloak0_r")):
        for k, amp in ((0, 2.5), (1, 5.0)):
            lag = 0.3 * (i + 2 * k)
            cloak[f"{panel}_s{k}"] = [[kf("rotation", t, (round(
                amp * 0.4 * np.sin(2 * np.pi * (t / 6.0) - lag), 2), round(
                amp * np.sin(2 * np.pi * (t / 6.0) - lag), 2), 0), "catmullrom")
                for t in (0.0, 1.5, 3.0, 4.5, 6.0)]]
    tracks.update(cloak)
    # the vines lag behind everything, each segment a little more than the one
    # above it
    tracks.update({
        f"{pre}_{side}_s{i}": [sway(4.0 + 1.0 * i, lag=0.3 * i, sgn=sgn)]
        for pre, n in (("vine_f", 6), ("vine_b", 5))
        for side, sgn in (("l", 1.0), ("r", -1.0))
        for i in range(n)})
    return [make_animation("animation.mutant_iron_golem.idle", 6.0, tracks, by_name)]


# --- self checks -----------------------------------------------------------
def check_ground(tree, tol=0.2):
    """Nothing may hang below y = 0: the feet rest on it exactly, and a fist or
    a vine that reaches past it is standing in the floor."""
    lo, _hi = bounds(tree)
    return [] if lo[1] > -tol else [("ground", float(lo[1]))]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-preview", action="store_true")
    args = ap.parse_args()

    tree = assemble()

    bad = check_grid(tree)
    if bad:
        for path, why, v in bad[:20]:
            print(f"  grid: {path}: {why} ({v})")
        raise SystemExit(f"{len(bad)} cubes off the whole-unit grid")

    asym = check_symmetric(tree)
    if asym:
        for path, a, b in asym[:10]:
            print(f"  asymmetric centre part: {path} x {a}..{b}")
        raise SystemExit(f"{len(asym)} centre parts not straddling x = 0")

    fights = coplanar_visible(tree)
    if fights:
        for pi, pj, axis, tag, coord in fights[:20]:
            print(f"  z-fight risk: {pi} / {pj} on {axis}={coord:.2f} ({tag})")
        raise SystemExit(f"{len(fights)} visible coplanar overlaps "
                         f"({len(coplanar_conflicts(tree))} raw)")

    stretched = stretch_report(tree)
    if stretched:
        agg = {}
        for _path, _face, want, got in stretched:
            agg[(round(want, 2), got)] = agg.get((round(want, 2), got), 0) + 1
        print(f"stretched faces: {len(stretched)}")
        for (want, got), n in sorted(agg.items()):
            print(f"  {want:6.2f} -> {got} px   x{n}")

    below = check_ground(tree)
    if below:
        raise SystemExit(f"geometry below the ground plane: {below}")

    lo, hi = bounds(tree)
    print(f"bounds  x {lo[0]:7.1f}..{hi[0]:7.1f}  y {lo[1]:7.1f}..{hi[1]:7.1f}  "
          f"z {lo[2]:7.1f}..{hi[2]:7.1f}   (h {hi[1] - lo[1]:.1f}, "
          f"w {hi[0] - lo[0]:.1f}, d {hi[2] - lo[2]:.1f})")

    atlases = build_atlases(tree, PAINTERS, GLOW_MATERIALS,
                            sizes=(384, 448, 512, 640, 768, 1024))
    for idx, atlas in atlases.items():
        unpainted = check_painted(atlas)
        if unpainted:
            raise SystemExit(f"texture {idx} rects left unpainted: {unpainted[:8]}")
    images = {idx: atlas.image() for idx, atlas in atlases.items()}
    for idx, name in ((TEX_BODY, f"{MODEL_NAME}.png"),
                      (TEX_GLOW, f"{MODEL_NAME}_glow.png")):
        images[idx].save(os.path.join(OUT_DIR, name))

    model_path = os.path.join(OUT_DIR, f"{MODEL_NAME}.bbmodel")
    n = write_model(model_path, tree, atlases, images, MODEL_NAME, GLOW_MATERIALS,
                    animations=build_animations)
    used = {idx: sum(w * h for _x, _y, w, h in a.rects.values())
            for idx, a in atlases.items()}
    print(f"{model_path}  ({n} cubes, res {atlases[TEX_BODY].size // S}, "
          f"body {atlases[TEX_BODY].size}px {len(atlases[TEX_BODY].rects)} rects "
          f"{used[TEX_BODY]}px, glow {len(atlases[TEX_GLOW].rects)} rects "
          f"{used[TEX_GLOW]}px)")

    if not args.no_preview:
        render_previews(model_path, OUT_DIR, MODEL_NAME, PREVIEWS)
        pose_previews(model_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
