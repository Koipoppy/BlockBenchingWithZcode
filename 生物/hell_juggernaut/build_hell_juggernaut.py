"""Build 地狱魔将 (hell_juggernaut) as a Blockbench project.

    python 生物/hell_juggernaut/build_hell_juggernaut.py [--no-preview]

A greater devil: 104 units tall (6.5 blocks), 48 across the pauldrons, and built
to the same brief as 人工建模参考/生物 -- that set is hulking humanoids (石头人,
变异坚守者) with glowing accents, so this one is a hulking humanoid with the
Nether's palette: a furnace burning behind a barred ribcage, molten seams at
every joint, horns and tusks, layered pauldrons over chains and trophies.

The creature, top to bottom:
  * crown horns (two pairs, stepped 4 -> 1 units, curving up and back), cheek
    horns, a heavy brow with two eyes glowing out of dark sockets, a wide muzzle
    with a bone nose-plate and four fangs, and a bull's lower tusks rising past
    the muzzle on the jaw -- the jaw is its own group, so it opens;
  * a barrel chest 24 wide carrying the furnace: a barred core, a two-part
    breastplate, a stepped rib stack down each flank with a molten seam in each
    joint, and a spine ridge of four spikes with a glowing spine line under them;
  * pauldrons in three stacked plates with a trim rim under each, three spikes
    on top of the stack, and a chain hanging off the outer edge with a bone
    charm at the end;
  * arms that step outward as they descend (no rest rotations -- the whole model
    is axis-aligned, which keeps the coplanar and mirror gates exact), banded
    with an armor ring and a molten seam, ending in a 10-wide fist whose four
    fingers curl under with claws;
  * cloven-hoofed legs with a rimmed hoof, a greave plate and outward spikes,
    a knee cap with a three-step spike;
  * a belt with a glowing buckle gem, hip plates, a hanging chain and a skull
    trophy per side, a front and back tabard of cloth, and a four-segment tail
    ending in a barbed spade.

Palette: demon hide (dark crimson), blackened steel armor with bronze trim,
bone, iron chains, blood-dark leather and cloth, and the Nether's magma. The
second texture is the emissive map: the furnace core, the molten seams, the
eyes, the buckle gem and the tail's glow.

Geometry rules this script holds to (README.md conventions, ISSUE.md pitfalls):
  * every coordinate is on the 0.5 grid and every cube's size is a whole number
    of units -- at S = 2 px/unit that makes every face an exact uv rect, so
    there is nothing for stretch_report to report;
  * no element or group rotations in the rest pose: the model is axis-aligned,
    so coplanar_conflicts and MCP's mirror gate both see the real thing;
  * 1 uv unit = 1 model unit, the map is painted at 2 px/unit (project
    resolution 256, texture 512), noise painted per unit cell not per texel;
  * parts that sit proud of a host start 0.5 inside it (contact) and end on a
    plane no other face shares (no z-fighting).

Deliberate overlaps (validate with interpenetration_depth raised if the gate
objects): armor bands and plates sunk into the limbs they wrap, the pauldron
plates into each other, the chain's first link into the belt it hangs from, the
tusks into the jaw, the spine spikes into the ridge, and the barbed spade into
the tail tip.
"""
from __future__ import annotations

import argparse
import os
import re
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
from bbmodel_kit import (V, rot_ZYX, walk_groups,  # noqa: E402
                         coplanar_conflicts, coplanar_visible, stretch_report)
from bbmodel_build import (DIRS, FM, S, TEX_BODY, TEX_GLOW, add_mirrors, at,  # noqa: E402
                           blobs, bounds, box, build_atlases, chain, check_grid,
                           check_painted, check_symmetric, cube, edge_lit, group,
                           half, hoop, kf, link, local, make_animation, mirror_tree, put, ramp,
                           render_previews, rng_for, side_tree, spike, streaks,
                           tint, write_model)

OUT_DIR = HERE
MODEL_NAME = "hell_juggernaut"
GLOW_MATERIALS = {"magma", "ember", "core"}

# --- palette ---------------------------------------------------------------
HIDE_HI, HIDE_C, HIDE_MID, HIDE_DK, HIDE_DEEP = (
    (152, 50, 54), (114, 33, 37), (74, 20, 25), (44, 12, 16), (26, 7, 10))
ARM_HI, ARM, ARM_MID, ARM_DK, ARM_DEEP = (
    (76, 71, 78), (50, 46, 52), (33, 30, 36), (21, 19, 24), (11, 10, 13))
TRIM_HI, TRIM, TRIM_DK, TRIM_DEEP = (172, 134, 70), (122, 90, 38), (74, 52, 20), (42, 28, 12)
HORN_HI, HORN, HORN_DK, HORN_DEEP = (104, 92, 82), (70, 60, 54), (44, 36, 33), (26, 21, 19)
TIP_HI, TIP, TIP_DK = (196, 186, 160), (146, 136, 114), (96, 88, 72)
BONE_HI, BONE_C, BONE_DK, BONE_DEEP = (178, 166, 140), (138, 128, 104), (98, 90, 72), (58, 52, 42)
CHAIN_HI, CHAIN_C, CHAIN_DK = (154, 146, 150), (102, 96, 100), (58, 54, 58)
LEATH_HI, LEATH, LEATH_DK = (112, 76, 52), (78, 52, 36), (46, 30, 21)
CLOTH_HI, CLOTH_C, CLOTH_MID, CLOTH_DK = (140, 40, 42), (100, 26, 30), (68, 17, 21), (42, 10, 13)
LAVA_HI, LAVA, LAVA_MID, LAVA_DK, LAVA_DEEP = (
    (255, 236, 176), (252, 172, 62), (218, 96, 22), (124, 36, 10), (54, 14, 4))


# --- painters --------------------------------------------------------------
def paint_hide(cv, r, key, dark=False):
    """Demon hide: dark crimson, plated in unit-cell scales, darker on the
    shadow side (this painter serves both `hide` and `hide_dk`)."""
    a = at(cv, r)
    rng = rng_for(key)
    ramp(a, [(0.0, HIDE_MID if dark else HIDE_HI), (0.26, HIDE_MID if dark else HIDE_C),
             (0.72, HIDE_DK), (1.0, HIDE_DEEP)])
    tint(a, rng, HIDE_DEEP, 0.16)                     # scale shadow
    tint(a, rng, HIDE_HI if not dark else HIDE_C, 0.10)  # scale highlight
    streaks(a, rng, HIDE_DEEP, max(1, a.shape[0] // (4 * S)), vertical=False, lo=2, wide=1)
    blobs(a, rng, HIDE_MID, 2, 1, 2)
    edge_lit(a, top=HIDE_HI if not dark else HIDE_C, bottom=HIDE_DEEP)


def paint_armor(cv, r, key, dark=False, up=False):
    """Blackened steel plate: warm-dark, scratched, riveted at the corners."""
    a = at(cv, r)
    rng = rng_for(key)
    h, w = a.shape[:2]
    top = ARM_HI if up else (ARM if not dark else ARM_MID)
    ramp(a, [(0.0, top), (0.30, ARM if not dark else ARM_MID),
             (0.74, ARM_DK), (1.0, ARM_DEEP)])
    streaks(a, rng, ARM_MID if not dark else ARM_DK, max(1, w // (3 * S)),
            vertical=False, lo=2, wide=1)
    streaks(a, rng, ARM_DEEP, max(1, h // (4 * S)), vertical=True, lo=2, wide=1)
    tint(a, rng, ARM_HI if up else ARM_MID, 0.08)
    edge_lit(a, top=ARM_HI if (up or not dark) else ARM, bottom=ARM_DEEP)
    if w >= 8 * S and h >= 8 * S:                      # corner rivets on big plates
        for x in (S, w - 3 * S):
            for y in (S, h - 3 * S):
                a[y:y + 2 * S, x:x + 2 * S, :3] = np.array(ARM_DEEP, np.uint8)
                a[y + (S // 2) + (0 if y < h // 2 else -S // 2):
                  y + (S // 2) + (0 if y < h // 2 else -S // 2) + S,
                  x + (S // 2):x + (S // 2) + S, :3] = np.array(ARM_HI, np.uint8)


def paint_trim(cv, r, key):
    """Bronze trim: the rims and studs that break up the black."""
    a = at(cv, r)
    rng = rng_for(key)
    ramp(a, [(0.0, TRIM_HI), (0.26, TRIM), (0.78, TRIM_DK), (1.0, TRIM_DEEP)])
    streaks(a, rng, TRIM_DK, max(1, a.shape[1] // (3 * S)), vertical=True, lo=2, wide=1)
    tint(a, rng, TRIM_HI, 0.12)
    edge_lit(a, top=TRIM_HI, bottom=TRIM_DEEP)


def paint_horn(cv, r, key, rings=True):
    """Horn: dark keratin with growth rings; hooves use it too."""
    a = at(cv, r)
    rng = rng_for(key)
    ramp(a, [(0.0, HORN_HI), (0.24, HORN), (0.70, HORN_DK), (1.0, HORN_DEEP)])
    h = a.shape[0]
    if rings:
        for y in range(S, h, 4 * S):
            a[y:y + S, :, :3] = np.array(HORN_DK, np.uint8)
            if y + 2 * S < h:
                a[y + S:y + 2 * S, :, :3] = np.array(HORN_HI, np.uint8)
    streaks(a, rng, HORN_DEEP, max(1, h // (4 * S)), vertical=True, lo=2, wide=1)
    edge_lit(a, top=HORN_HI, bottom=HORN_DEEP)


def paint_tip(cv, r, key):
    """Pale horn tip -- the last step of every horn, tusk and claw."""
    a = at(cv, r)
    rng = rng_for(key)
    ramp(a, [(0.0, TIP_HI), (0.42, TIP), (1.0, TIP_DK)])
    tint(a, rng, TIP_DK, 0.12)
    edge_lit(a, top=(242, 236, 220), bottom=TIP_DK)


def paint_claw(cv, r, key):
    a = at(cv, r)
    rng = rng_for(key)
    ramp(a, [(0.0, HORN), (0.35, HORN_DK), (0.80, HORN_DEEP), (1.0, TIP_DK)])
    streaks(a, rng, HORN_DEEP, max(1, a.shape[0] // (3 * S)), vertical=True, lo=2, wide=1)
    edge_lit(a, bottom=TIP_HI)


def paint_bone(cv, r, key):
    """Trophies and the muzzle plate: old bone, cracked."""
    a = at(cv, r)
    rng = rng_for(key)
    ramp(a, [(0.0, BONE_HI), (0.34, BONE_C), (0.80, BONE_DK), (1.0, BONE_DEEP)])
    streaks(a, rng, BONE_DEEP, max(1, a.shape[1] // (3 * S)), vertical=True, lo=2, wide=1)
    blobs(a, rng, BONE_DK, 2, 1, 1)
    tint(a, rng, BONE_HI, 0.08)
    edge_lit(a, top=BONE_HI, bottom=BONE_DEEP)


def paint_chain(cv, r, key):
    a = at(cv, r)
    rng = rng_for(key)
    a[:, :, :3] = np.array(CHAIN_C, np.uint8)
    a[:, :, 3] = 255
    tint(a, rng, CHAIN_HI, 0.18)
    tint(a, rng, CHAIN_DK, 0.16)
    tint(a, rng, HIDE_DEEP, 0.05)
    a[0:1, :, :3] = np.array(CHAIN_HI, np.uint8)
    a[-1:, :, :3] = np.array((24, 22, 24), np.uint8)


def paint_leather(cv, r, key):
    a = at(cv, r)
    rng = rng_for(key)
    h = a.shape[0]
    ramp(a, [(0.0, LEATH_HI), (0.30, LEATH), (1.0, LEATH_DK)])
    for y in range(S, h, 5 * S):                       # grain + stitching
        a[y:y + S, :, :3] = np.array(LEATH_DK, np.uint8)
        a[y + S:y + 2 * S, :, :3] = np.array(LEATH_HI, np.uint8)
    for x in range(0, a.shape[1], 3 * S):
        a[:, x:x + 1, :3] = np.array(LEATH_DK, np.uint8)
    edge_lit(a, bottom=LEATH_DK)


def paint_cloth(cv, r, key):
    """The tabard: crimson cloth with a bronze hem."""
    a = at(cv, r)
    rng = rng_for(key)
    h, w = a.shape[:2]
    ramp(a, [(0.0, CLOTH_HI), (0.30, CLOTH_C), (0.76, CLOTH_MID), (1.0, CLOTH_DK)])
    streaks(a, rng, CLOTH_DK, max(1, w // (3 * S)), vertical=True, lo=3, wide=1)
    tint(a, rng, CLOTH_HI, 0.10)
    a[h - 2 * S:h - S, :, :3] = np.array(TRIM, np.uint8)   # the hem
    a[h - S:h, :, :3] = np.array(TRIM_DK, np.uint8)
    edge_lit(a, top=CLOTH_HI)


def paint_muzzle(cv, r, key):
    """The muzzle's front face: hide with two dark nostrils."""
    a = at(cv, r)
    paint_hide(cv, r, key)
    h, w = a.shape[:2]
    if w >= 6 * S and h >= 3 * S:
        for x in (w // 2 - 2 * S, w // 2 + S):
            a[h - 2 * S:h - S, x:x + S, :3] = np.array(HIDE_DEEP, np.uint8)
            a[h - 2 * S:h - S, x:x + S, :3] = np.array((16, 5, 8), np.uint8)


def paint_magma(cv, r, key):
    """Emissive: a molten seam -- white-hot down the middle, soot at the rim."""
    a = at(cv, r)
    h, w = a.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    d = np.sqrt(((yy - (h - 1) / 2) / max(1.0, h * 0.60)) ** 2 +
                ((xx - (w - 1) / 2) / max(1.0, w * 0.60)) ** 2)
    d = np.clip(d, 0, 1)
    col = (np.array(LAVA_HI, float) * (1 - d[..., None]) +
           np.array(LAVA_DK, float) * d[..., None])
    a[:, :, :3] = np.clip(col, 0, 255).astype(np.uint8)
    a[:, :, 3] = 255
    tint(a, rng_for(key), LAVA, 0.14)


def paint_ember(cv, r, key):
    """Emissive: an eye or a gem -- hottest at the centre, deep red at the rim."""
    a = at(cv, r)
    h, w = a.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    d = np.clip(np.sqrt(((yy - (h - 1) / 2) / max(1.0, h * 0.72)) ** 2 +
                        ((xx - (w - 1) / 2) / max(1.0, w * 0.72)) ** 2), 0, 1)
    col = (np.array((255, 214, 128), float) * (1 - d[..., None]) +
           np.array((108, 16, 4), float) * d[..., None])
    a[:, :, :3] = np.clip(col, 0, 255).astype(np.uint8)
    a[:, :, 3] = 255


def paint_core(cv, r, key):
    """Emissive: the furnace behind the ribs -- a hot heart in a dark frame."""
    a = at(cv, r)
    h, w = a.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    d = np.clip(np.sqrt(((yy - (h - 1) / 2) / max(1.0, h * 0.58)) ** 2 +
                        ((xx - (w - 1) / 2) / max(1.0, w * 0.58)) ** 2), 0, 1)
    col = (np.array((255, 252, 232), float) * (1 - d[..., None]) +
           np.array(LAVA_MID, float) * d[..., None])
    a[:, :, :3] = np.clip(col, 0, 255).astype(np.uint8)
    a[:, :, 3] = 255
    a[0:S, :, :3] = np.array(LAVA_DEEP, np.uint8)
    a[-S:, :, :3] = np.array(LAVA_DEEP, np.uint8)


PAINTERS = {
    "hide": lambda cv, r, k: paint_hide(cv, r, k, dark=False),
    "hide_dk": lambda cv, r, k: paint_hide(cv, r, k, dark=True),
    "armor": lambda cv, r, k: paint_armor(cv, r, k),
    "armor_up": lambda cv, r, k: paint_armor(cv, r, k, up=True),
    "armor_dk": lambda cv, r, k: paint_armor(cv, r, k, dark=True),
    "trim": paint_trim, "horn": paint_horn, "tip": paint_tip, "claw": paint_claw,
    "bone": paint_bone, "chain": paint_chain, "leather": paint_leather,
    "cloth": paint_cloth, "muzzle": paint_muzzle,
    "magma": paint_magma, "ember": paint_ember, "core": paint_core,
}

# face-map shorthands: lit top, shadowed underside
HIDE = FM(all="hide", down="hide_dk")
ARMOR = FM(all="armor", up="armor_up", down="armor_dk")
BONE = FM(all="bone")
CLOTH = FM(all="cloth")
CHAIN = FM(all="chain")


# --- the creature ----------------------------------------------------------
# Author the left half (+x); add_mirrors() copies every left-side cube inside a
# centre group, and mirror_tree() makes the right limb. Limbs, tail and joints
# are CHAINS: a segment hinges on the joint above it, so a leg splays and a
# tail droops as one curved thing instead of a brick stack.

# --- the creature ----------------------------------------------------------
# Author the left half (+x); mirror_tree() makes the right. The tail and the
# spine/head centres are symmetric about x = 0 and are authored once.
#
# Placement discipline, so that no two touching boxes share a face plane:
# a part either BUTTS its host (contact along one plane, no volume overlap, so
# no coincident same-facing faces at all) or stands proud of it. Within a
# cluster -- the torso stack, the pauldron stack, the forearm, the fist -- the
# min AND max of every box differ from its neighbours on the axes where they
# overlap. That is what keeps the coplanar gate quiet (ISSUE.md 6).

def build_leg():
    """A leg as a chain: the thigh splays out, the shin brings it back under
    the body, the foot plants. Plates ride the segment they belong to and the
    hoof is built off the chain's own ankle joint."""
    host = group("leg_l", origin=(6, 41, 0), cubes=[])
    thigh, shin, foot = chain(host, "leg_l", (6, 41, 0), "-y", [
        ("thigh", 18, 10, 12, (0, 0, 6), HIDE),
        ("shin", 15, 7, 7, (0, 0, -2), HIDE),
        ("foot", 6, 9, 10, (0, 0, 0), HIDE),
    ])
    kx, ky, kz = shin["joint"]                     # the knee
    ax, ay, az = foot["joint"]                     # the ankle
    put(thigh,
        local(thigh, 0, -17, 0, (9, 7, 8), ARMOR, "knee_l"),
        local(thigh, 0, -15, 0, (11, 4, 10), "trim", "knee_trim_l"),
        local(thigh, 0, -18, -4.5, (6, 3, 2), "magma", "knee_glow_l"),
        local(thigh, 6, -10, 0, (2, 12, 9), ARMOR, "thigh_guard_l"),
        local(thigh, 5, -14.5, 0, (3, 4, 11), "trim", "thigh_guard_rim_l"),
        local(thigh, 0, -6, 0, (12, 3, 14), "leather", "thigh_strap_l"),
        local(thigh, 7, -12, 0, (1, 4, 3), "trim", "thigh_stud_l"),
        local(thigh, -2, -4.5, -5, (4, 4, 3), "claw", "knee_spike0_l"),
        local(thigh, -1, -3, -6, (3, 3, 3), "claw", "knee_spike1_l"),
        local(thigh, -1, -2, -7.5, (2, 2, 2), "tip", "knee_spike2_l"),
    )
    put(shin,
        local(shin, 4.5, -9, 0, (2, 11, 9), ARMOR, "shin_greave_l"),
        local(shin, 3.5, -13, 0, (5, 4, 11), "trim", "shin_trim_l"),
        local(shin, 3.5, -8, 0, (4, 4, 4), "claw", "shin_spike0_l"),
        local(shin, 5.5, -8, 0, (3, 3, 3), "claw", "shin_spike1_l"),
        local(shin, 8, -8, 0, (2, 2, 2), "tip", "shin_spike2_l"),
    )
    put(foot,
        local(foot, 0, -1.5, 0, (7, 3, 7), HIDE, "ankle_l"),
        local(foot, 0, -5.5, 0, (8, 5, 11), "horn", "hoof_l"),
        local(foot, -3, -5.5, -4.5, (4, 3, 5), "horn", "hoof_toe_i_l"),
        local(foot, 3, -5.5, -4.5, (4, 3, 5), "horn", "hoof_toe_o_l"),
        local(foot, 0, -5.5, 4.5, (6, 3, 3), "horn", "hoof_heel_l"),
        local(foot, 0, -2.5, 0, (11, 3, 13), ARMOR, "hoof_rim_l"),
    )
    return host


def build_hips():
    """Pelvis, belt with a glowing buckle, front and back tabard, hip plates, a
    hanging chain, and a skull trophy on each side."""
    chain = (link("hipchain0_l", 4.5, 41, -10, 3, 5, 1, CHAIN, plane="xy")
             + link("hipchain1_l", 5.5, 36.5, -11, 3, 5, 1, CHAIN, plane="zy")
             + link("hipchain2_l", 4.5, 32, -10, 3, 5, 1, CHAIN, plane="xy"))
    return group("hips", origin=(0, 40, 0), cubes=[
        box("hips_low", HIDE, (-7, 32, -4), (7, 38, 3)),
        box("hips", HIDE, (-8, 38, -6), (8, 47, 6)),
        box("pelvis_plate_f", ARMOR, (-5, 31, -9), (5, 38, -4)),
        box("pelvis_trim_f", "trim", (-5, 29, -9), (5, 31, -5)),
        box("pelvis_cloth_f", CLOTH, (-4, 21, -7), (4, 29, -2)),
        box("pelvis_plate_b", ARMOR, (-5, 30, 5), (5, 40, 8)),
        box("pelvis_cloth_b", CLOTH, (-4, 19, 5), (4, 30, 7)),
        box("belt", "leather", (-9, 44, -8), (9, 50, 4)),
        box("belt_buckle", ARMOR, (-3, 42, -9), (3, 49, -8)),
        box("buckle_gem", "ember", (-2, 44, -10), (2, 47, -9)),
        box("belt_stud0_l", "trim", (4, 45, -9), (6, 48, -8)),
        box("belt_stud1_l", "trim", (7, 45, -9), (9, 48, -8)),
        box("belt_stud2_l", "trim", (3.5, 45, 5), (5.5, 48, 7)),
        box("belt_stud3_l", "trim", (6.5, 45, 5), (8.5, 48, 7)),
        box("hip_side_l", ARMOR, (8.5, 35, -7), (12.5, 44, 6)),
        box("hip_side_rim_l", "trim", (7, 32, -11), (13, 36, 2)),
    ] + chain + [
        box("trophy_skull_l", BONE, (5, 27, -10), (9, 32, -7)),
        box("trophy_brow_l", BONE, (4, 31, -12), (10, 34, -6)),
        box("trophy_jaw_l", BONE, (5.5, 24, -9), (8.5, 27, -6)),
        box("trophy_socket0_l", "hide_dk", (5.5, 28, -11), (6.5, 30, -10)),
        box("trophy_socket1_l", "hide_dk", (7.5, 28, -11), (8.5, 30, -10)),
    ])


def build_torso():
    """Waist, barrel chest (deeper as it rises), breastplate with the barred
    furnace, a stepped rib stack down each flank with a molten seam in each
    joint, and a spine ridge up the back with four spikes."""
    return group("spine", origin=(0, 46, 0), cubes=[
        box("waist", HIDE, (-7, 47, -5), (7, 54, 5)),
        box("waist_glow", "magma", (-5, 48, -6), (5, 53, -5)),
        box("torso_mid", HIDE, (-9, 54, -6), (9, 62, 5)),
        box("torso_up", HIDE, (-11, 62, -7), (11, 71, 3)),
        box("torso_top", HIDE, (-9, 71, -6), (9, 78, 6)),
        box("lat_l", HIDE, (11, 62, -4), (13, 71, 3)),
        box("chest_plate_c", ARMOR, (-5, 59, -9), (5, 73, -7)),
        box("plate_trim_c", "trim", (-6, 56, -9), (6, 59, -7)),
        box("plate_trim_top", "trim", (-6, 73, -9), (6, 76, -7)),
        box("core_frame_b", ARMOR, (-5, 60, -10), (5, 62, -9)),
        box("core_frame_t", ARMOR, (-5, 70, -10), (5, 72, -9)),
        box("core_frame_l", ARMOR, (4, 62, -10), (5, 70, -9)),
        box("core", "core", (-4, 62, -10), (4, 70, -9)),
        box("core_bar0_l", ARMOR, (1, 62, -11), (3, 69, -10)),
        box("core_bar_c", ARMOR, (-4, 65, -12), (4, 67, -11)),
        box("rib_l0", ARMOR, (9, 53, -5), (13, 58, 4)),
        box("rib_l1", ARMOR, (9, 58, -5), (13, 62, 6)),
        box("rib_l2", ARMOR, (10, 62, -6), (14, 66, 6)),
        box("rib_l3", ARMOR, (10, 66, -6), (14, 70, 5)),
        box("rib_seam_l0", "magma", (13, 56, -2), (15, 59, 2)),
        box("rib_seam_l1", "magma", (14, 61, -2), (16, 63, 1)),
        box("rib_seam_l2", "magma", (14, 65, -2), (16, 68, 1)),
        box("ridge_a", HIDE, (-2, 53, 6), (2, 61, 9)),
        box("ridge_b", HIDE, (-2, 61, 5), (2, 70, 8)),
        box("ridge_c", HIDE, (-2, 70, 5), (2, 77, 7)),
        box("ridge_seam0", "magma", (-1, 60, 8), (1, 62, 10)),
        box("ridge_seam1", "magma", (-1, 69, 7), (1, 71, 9)),
        box("neck", HIDE, (-5, 77, -5), (5, 85, 4)),
        box("collar", ARMOR, (-7, 76, -7), (7, 80, 5)),
        box("collar_trim", ARMOR, (-8, 79, -6), (8, 82, 6)),
        box("throat_glow", "magma", (-2, 78, -8), (2, 84, -7)),
    ] + spike("sspike0", "horn", (-1.5, 54, 9), (1.5, 59, 12), "+z", 3, 3, tip="tip",
              drift=(0.0, 1.0))
      + spike("sspike1", "horn", (-1.5, 62, 8), (1.5, 67, 12), "+z", 3, 4, tip="tip",
              drift=(0.0, 1.0))
      + spike("sspike2", "horn", (-1.5, 68, 8), (1.5, 72, 11), "+z", 3, 3, tip="tip",
              drift=(0.0, 1.0))
      + spike("sspike3", "horn", (-1.5, 73, 7), (1.5, 77, 11), "+z", 3, 3, tip="tip",
              drift=(0.0, 1.0))
      + spike("blade_spike_l", "horn", (5, 64, 4), (9, 68, 8), "+z", 3, 2, tip="tip",
              drift=(0.0, 1.5))
      + spike("blade_spike2_l", "horn", (7, 57, 3), (11, 61, 7), "+z", 3, 2, tip="tip",
              drift=(0.0, 1.5)))


def build_head():
    """Skull, crown horns, cheek horns, brow, glowing eyes out of dark sockets,
    a muzzle with a bone nose plate, four fangs, and a jaw group carrying the
    bull tusks. The crown horns are stepped by hand so their curve back is
    exact (the generic spike helper cannot drift and taper at the same time
    without leaving two segments sharing a plane); they start on the skull's
    top-front so they read from the front, and the brow is hide, not a bronze
    band -- a bright band across it turned the head into a hat (v2 did)."""
    crown_a = [
        box("crown_a_l0", "horn", (2, 92, -7), (5, 95, -2)),
        box("crown_a_l1", "horn", (2.5, 93, -6), (5.5, 97, 0)),
        box("crown_a_l2", "tip", (3, 96, -5), (5, 100, 1)),
    ]
    crown_b = [
        box("crown_b_l0", "horn", (5, 90, -6), (8, 93, -2)),
        box("crown_b_l1", "horn", (5.5, 92, -5), (8.5, 96, -1)),
        box("crown_b_l2", "tip", (6, 95, -4), (8, 99, 0)),
    ]
    jaw = group("jaw", origin=(0, 82, -9), cubes=[
        box("jaw", HIDE, (-5, 77, -17), (5, 83, -9)),
        box("jaw_chin", HIDE, (-4, 74, -16), (4, 78, -10)),
        box("jaw_teeth", "bone", (-2, 82, -16), (2, 85, -13)),
    ] + [
        box("tusk_l0", "bone", (5.5, 80, -16), (8.5, 85, -13)),
        box("tusk_l1", "bone", (6, 84, -18), (8, 88, -15)),
        box("tusk_l2", "tip", (6.5, 87, -19), (7.5, 90, -16)),
    ])
    return group("head", origin=(0, 84, -2), cubes=[
        box("skull", HIDE, (-6, 84, -9), (6, 94, 3)),
        box("skull_top", ARMOR, (-4.5, 94, -8), (4.5, 96, 2)),
        box("brow", HIDE, (-7, 89, -12), (7, 93, -9)),
        box("socket_l", "hide_dk", (1, 84, -13), (5, 90, -9)),
        box("eye_l", "ember", (2.5, 85, -14), (5.5, 89, -11)),
        box("cheek_l", HIDE, (6, 82, -9), (9, 90, 0)),
        box("cheek_plate_l", ARMOR, (6, 84, -13), (8, 90, -9)),
        box("snout", HIDE, (-2.5, 83, -17), (2.5, 91, -9)),
        box("snout_top", HIDE, (-2, 91, -16), (2, 94, -9)),
        box("snout_plate", "bone", (-3, 84, -18), (3, 90, -16), north="muzzle"),
        box("fang_ul_l", "bone", (1.5, 78, -19), (4.5, 84, -15)),
    ] + crown_a + crown_b + spike("cheek_horn_l", "horn", (7, 85, -2), (10, 89, 2),
                                  "+z", 3, 3, tip="tip")
      + spike("mane_l", "horn", (4, 88, 2), (8, 93, 5), "+z", 3, 3, tip="tip")
      + spike("mane2_l", "horn", (1.5, 85, 1), (4.5, 89, 4), "+z", 2, 3, tip="tip"),
        children=[jaw])


def build_pauldron():
    """A shoulder mass in three tiers, each with a lip at its bottom edge: the
    lip is the same steel, one unit proud, so the tiers read as steps in the
    shading -- a bright rim band turns the stack into a totem pole (v1 did).
    Two horns rise off the cap and one juts outward past the edge."""
    return group("pauldron_l", origin=(12, 72, -0.5), cubes=[
        box("pd0_l", ARMOR, (7, 68, -8), (17, 75, 4)),
        box("pd0_lip_l", ARMOR, (6, 66, -9), (18, 68, 2)),
        box("pd1_l", ARMOR, (8, 60, -8), (19, 67, 4)),
        box("pd1_lip_l", ARMOR, (7, 58, -10), (20, 61, 3)),
        box("pd2_l", ARMOR, (9, 54, -8), (21, 60, 1)),
        box("pd2_lip_l", ARMOR, (8, 52, -11), (22, 55, 3)),
        box("pd_stud_l", "trim", (14, 63, -9), (18, 66, -8)),
    ] + spike("pds_a_l", "horn", (11, 74, -4), (15, 77, 1), "+y", 3, 3, tip="tip")
      + spike("pds_c_l", "horn", (17, 66, -3), (20, 69, 1), "+x", 2, 3, tip="tip",
              drift=(1.0, 0.0)))


def build_arm():
    """An arm as a chain: the upper arm swings out from the shoulder, the
    forearm follows it, the fist closes at the end. That swing is what keeps
    the fist clear of the thigh -- a chain buys the splay a staircase cannot."""
    host = group("arm_l", origin=(12, 66, 0), cubes=[])
    upper, fore, hand = chain(host, "arm_l", (12, 66, 0), "-y", [
        ("upper", 16, 9, 11, (0, 0, 14), HIDE),
        ("fore", 14, 8, 9, (0, 0, 14), HIDE),
        ("hand", 9, 10, 11, (0, 0, 14), HIDE),
    ])
    fx, fy, fz = hand["joint"]                     # the fist
    put(upper,
        local(upper, 0, -3, 0, (11, 9, 15), HIDE, "deltoid_l"),
        local(upper, 0, -10, 0, (8, 13, 12), HIDE, "bicep_l"),
        local(upper, 0, -13.5, 0, (10, 4, 14), ARMOR, "arm_band_l"),
        local(upper, 0, -16.5, 0, (7, 3, 13), "magma", "arm_glow_l"),
    )
    put(fore,
        local(fore, 0, -3, 0, (9, 7, 10), HIDE, "elbow_l"),
        local(fore, 0, -9, 0, (10, 6, 13), ARMOR, "bracer_l"),
        local(fore, 0, -12, 0, (11, 3, 14), "trim", "bracer_trim_l"),
        local(fore, 0, -6, 0, (7, 3, 11), "magma", "bracer_glow_l"),
        local(fore, 0, -2, 6.5, (5, 4, 3), "horn", "elbow_spike0_l"),
        local(fore, 0, -1, 8.5, (4, 3, 3), "horn", "elbow_spike1_l"),
        local(fore, 0, 0, 10.5, (3, 2, 2), "tip", "elbow_spike2_l"),
        local(fore, 5, -10, 0, (4, 4, 5), "claw", "bracer_spike0_l"),
        local(fore, 6.5, -10, 0, (3, 3, 3), "claw", "bracer_spike1_l"),
        local(fore, 8, -10, 0, (2, 2, 2), "tip", "bracer_spike2_l"),
    )
    put(hand,
        local(hand, 0, -2, 0, (11, 7, 17), ARMOR, "fist_plate_l"),
        local(hand, 0, -5, 0, (13, 9, 12), HIDE, "palm_l"),
        local(hand, 0, -1, 0, (14, 3, 12), "leather", "palm_wrap_l"),
    )
    # the four fingers curl: each joint BUTTS the one above it (the segments
    # share an x span, so an overlap would put their side faces in one plane)
    for i in range(4):
        x = -5 + 2.5 * i
        put(hand,
            local(hand, x, -7, -6.5, (2, 4, 3), HIDE, f"knuckle{i}_l"),
            local(hand, x, -11, -5, (2, 4, 3), HIDE, f"finger{i}_a_l"),
            local(hand, x, -14.5, -4.5, (2, 3, 3), HIDE, f"finger{i}_b_l"),
            local(hand, x, -17.5, -4, (2, 3, 3), "claw", f"claw{i}_l"),
            local(hand, x, -20, -4, (1, 2, 2), "tip", f"claw{i}_tip_l"),
        )
    put(hand,
        local(hand, -6.5, -8, -2.5, (4, 4, 6), HIDE, "thumb_l"),
        local(hand, -7.5, -10.5, -2.5, (3, 4, 5), "tip", "thumb_claw_l"),
    )
    return host


def build_tail():
    """The tail as a chain of six segments drooping from the hips: each one
    pitched further than the last, so it leaves the pelvis, curves down and
    ends near the ground behind the creature."""
    host = group("tail_1", origin=(0, 44, 4), cubes=[])
    segs = chain(host, "tail", (0, 44, 4), "+z", [
        ("t1", 8, 8, 9, (16, 0, 0), HIDE),
        ("t2", 8, 7, 8, (34, 0, 0), HIDE),
        ("t3", 7, 6, 7, (52, 0, 0), HIDE),
        ("t4", 7, 5, 6, (68, 0, 0), HIDE),
        ("t5", 6, 4, 5, (80, 0, 0), HIDE),
        ("t6", 6, 3, 4, (88, 0, 0), HIDE),
    ])
    put(segs[0], local(segs[0], 0, -4.5, 3, (3, 4, 6), "horn", "tail_ridge"))
    for i in (1, 2, 3):
        put(segs[i],
            local(segs[i], 0, -4.5, 4, (3, 4, 3), "horn", f"tail_spike{i}"),
            local(segs[i], 0, 4.5, 5, (2, 2, 4), "magma", f"tail_glow{i}"),
        )
    tip = segs[-1]
    put(tip,
        local(tip, 0, 0, 3, (4, 5, 5), "horn", "barb_tip"),
        local(tip, 0, 0, 8, (3, 3, 4), "tip", "barb_tip2"),
        local(tip, 0, 4, 5, (5, 5, 4), "horn", "barb_back"),
        local(tip, 0, 7, 5, (3, 3, 3), "tip", "barb_back2"),
        local(tip, 0, -4, 3, (6, 5, 4), "horn", "barb_front"),
        local(tip, 0, -7, 5, (3, 3, 3), "tip", "barb_front2"),
        local(tip, 3.5, 0, 6, (6, 7, 5), "horn", "barb_sd_l"),
        local(tip, 6, 0, 4.5, (3, 3, 3), "tip", "barb_sd_l2"),
    )
    return host



# Clip poses: the offline renderer bakes a clip at a time into the transforms
# (tools/preview_bbmodel.py --clip/--time), which is the only way to look at a
# joint chain actually bent.
POSES = [("_roar", "animation.hell_juggernaut.roar", 0.6),
         ("_slam", "animation.hell_juggernaut.slam", 1.2),
         ("_idle", "animation.hell_juggernaut.idle", 1.4)]


def pose_previews(model_path: str) -> None:
    tool = os.path.join(REPO, "tools", "preview_bbmodel.py")
    for suffix, clip, t in POSES:
        out = os.path.join(OUT_DIR, f"{MODEL_NAME}_preview{suffix}.png")
        subprocess.run([sys.executable, tool, model_path, out, "--size", "760",
                        "--azimuth", "200", "--elevation", "8", "--distance", "210",
                        "--target", "0", "52", "0", "--clip", clip, "--time", str(t)],
                       check=True)


PREVIEWS = [
    ("", 205.0, 10.0, 200.0, (0.0, 52.0, 0.0)),
    ("_front", 180.0, 6.0, 200.0, (0.0, 52.0, 0.0)),
    ("_side", 270.0, 8.0, 200.0, (0.0, 52.0, 0.0)),
    ("_back", 0.0, 12.0, 200.0, (0.0, 55.0, 0.0)),
    ("_head", 205.0, 14.0, 72.0, (0.0, 88.0, -6.0)),
    ("_face", 190.0, 4.0, 46.0, (0.0, 87.0, -8.0)),
    ("_core", 190.0, 6.0, 78.0, (0.0, 64.0, -6.0)),
    ("_tail", 30.0, 18.0, 150.0, (0.0, 34.0, 20.0)),
]


# --- animation -------------------------------------------------------------
def build_animations(by_name: dict) -> list:
    """Three clips: the idle (breathing, the shoulders rolling, the tail's
    lagging sway, the head scanning), the roar (jaw wide, head up, arms flung
    back), and a two-fisted slam (rear back, hurl down, the ground shake).

    Every key is a DELTA: a chain's rest angle lives on the element and the
    chain groups sit at zero, so keying a group bends the limb further instead
    of straightening it -- which is what happened to the neck of an earlier
    model whose rest pitches were parked on the groups.

    Sign convention (measured against tools/preview_bbmodel.py, the renderer
    that agrees with Blockbench on rotations): for a limb hanging along -y,
    +rx swings the far end forward (-z) and +rz swings it toward +x; for the
    tail, which runs along +z, +rx drops the tip and -rx lifts it.
    """
    def sway(bone, amp, period=4.0, lag=0.0):
        """A slow ry sway with a per-segment lag, as the flail's chain does."""
        return [kf("rotation", t, (0, round(float(amp * np.sin(
            2 * np.pi * (t / period) - lag)), 2), 0), "catmullrom")
            for t in (0.0, 1.0, 2.0, 3.0, 4.0)]

    idle = make_animation("animation.hell_juggernaut.idle", 4.0, {
        "hell_juggernaut": [[kf("position", t, (0, y, 0), "catmullrom")
                             for t, y in ((0.0, 0.0), (1.4, 1.2), (2.2, 0.4),
                                          (3.2, 0.8), (4.0, 0.0))]],
        "spine": [[kf("rotation", t, (rx, 0, 0), "catmullrom")
                   for t, rx in ((0.0, 0.0), (1.4, 2.5), (2.4, 1.0), (4.0, 0.0))]],
        "head": [[kf("rotation", t, (rx, ry, 0), "catmullrom") for t, rx, ry in
                  ((0.0, 0, 0), (1.0, 2.0, 6.0), (2.0, -1.5, -5.0), (3.0, 1.0, 3.0),
                   (4.0, 0, 0))]],
        "jaw": [[kf("rotation", t, (rx, 0, 0), "catmullrom")
                 for t, rx in ((0.0, 0.0), (1.4, -5.0), (2.2, -1.0), (4.0, 0.0))]],
        "pauldron_l": [[kf("rotation", t, (0, 0, rz), "catmullrom")
                        for t, rz in ((0.0, 0.0), (1.4, -3.0), (2.6, 1.0), (4.0, 0.0))]],
        "pauldron_r": [[kf("rotation", t, (0, 0, -rz), "catmullrom")
                        for t, rz in ((0.0, 0.0), (1.4, -3.0), (2.6, 1.0), (4.0, 0.0))]],
        "arm_l_upper": [[kf("rotation", t, (rx, 0, rz), "catmullrom") for t, rx, rz in
                         ((0.0, 0, 0), (1.5, -2.0, 2.0), (2.6, 1.0, -1.0), (4.0, 0, 0))]],
        "arm_r_upper": [[kf("rotation", t, (rx, 0, -rz), "catmullrom") for t, rx, rz in
                         ((0.0, 0, 0), (1.5, -2.0, 2.0), (2.6, 1.0, -1.0), (4.0, 0, 0))]],
        "arm_l_fore": [[kf("rotation", t, (rx, 0, 0), "catmullrom")
                        for t, rx in ((0.0, 0.0), (1.8, -3.0), (4.0, 0.0))]],
        "arm_r_fore": [[kf("rotation", t, (rx, 0, 0), "catmullrom")
                        for t, rx in ((0.0, 0.0), (1.8, -3.0), (4.0, 0.0))]],
        "leg_l_thigh": [[kf("rotation", t, (0, 0, rz), "catmullrom")
                         for t, rz in ((0.0, 0.0), (2.0, 1.5), (4.0, 0.0))]],
        "leg_r_thigh": [[kf("rotation", t, (0, 0, -rz), "catmullrom")
                         for t, rz in ((0.0, 0.0), (2.0, 1.5), (4.0, 0.0))]],
        "tail_t1": [sway("tail_t1", 5.0, 4.0, 0.0)],
        "tail_t2": [sway("tail_t2", 6.0, 4.0, 0.35)],
        "tail_t3": [sway("tail_t3", 7.0, 4.0, 0.70)],
        "tail_t4": [sway("tail_t4", 8.0, 4.0, 1.05)],
        "tail_t5": [sway("tail_t5", 9.0, 4.0, 1.40)],
        "tail_t6": [sway("tail_t6", 10.0, 4.0, 1.75)],
    }, by_name)

    roar = make_animation("animation.hell_juggernaut.roar", 2.8, {
        "jaw": [[kf("rotation", t, (rx, 0, 0), "catmullrom")
                 for t, rx in ((0.0, 0.0), (0.5, -46.0), (1.6, -42.0), (2.8, 0.0))]],
        "head": [[kf("rotation", t, (rx, 0, 0), "catmullrom")
                  for t, rx in ((0.0, 0.0), (0.5, 18.0), (1.6, 15.0), (2.8, 0.0))]],
        "spine": [[kf("rotation", t, (rx, 0, 0), "catmullrom")
                   for t, rx in ((0.0, 0.0), (0.5, 7.0), (1.6, 5.0), (2.8, 0.0))]],
        "hell_juggernaut": [[kf("position", t, (0, y, 0), "catmullrom")
                             for t, y in ((0.0, 0.0), (0.5, 1.5), (1.6, 1.0), (2.8, 0.0))]],
        "pauldron_l": [[kf("rotation", t, (0, 0, rz), "catmullrom")
                        for t, rz in ((0.0, 0.0), (0.6, -10.0), (1.8, -8.0), (2.8, 0.0))]],
        "pauldron_r": [[kf("rotation", t, (0, 0, -rz), "catmullrom")
                        for t, rz in ((0.0, 0.0), (0.6, -10.0), (1.8, -8.0), (2.8, 0.0))]],
        "arm_l_upper": [[kf("rotation", t, (rx, 0, rz), "catmullrom") for t, rx, rz in
                         ((0.0, 0, 0), (0.6, -16.0, 16.0), (1.8, -14.0, 14.0),
                          (2.8, 0, 0))]],
        "arm_r_upper": [[kf("rotation", t, (rx, 0, -rz), "catmullrom") for t, rx, rz in
                         ((0.0, 0, 0), (0.6, -16.0, 16.0), (1.8, -14.0, 14.0),
                          (2.8, 0, 0))]],
        "arm_l_fore": [[kf("rotation", t, (rx, 0, 0), "catmullrom")
                        for t, rx in ((0.0, 0.0), (0.6, 22.0), (1.8, 18.0), (2.8, 0.0))]],
        "arm_r_fore": [[kf("rotation", t, (rx, 0, 0), "catmullrom")
                        for t, rx in ((0.0, 0.0), (0.6, 22.0), (1.8, 18.0), (2.8, 0.0))]],
        "tail_t1": [[kf("rotation", t, (rx, 0, 0), "catmullrom")
                     for t, rx in ((0.0, 0.0), (0.6, -16.0), (1.8, -2.0), (2.8, 0.0))]],
        "tail_t2": [[kf("rotation", t, (rx, 0, 0), "catmullrom")
                     for t, rx in ((0.0, 0.0), (0.8, -12.0), (2.0, -2.0), (2.8, 0.0))]],
        "tail_t3": [[kf("rotation", t, (rx, 0, 0), "catmullrom")
                     for t, rx in ((0.0, 0.0), (1.0, -8.0), (2.2, -2.0), (2.8, 0.0))]],
    }, by_name)

    slam = make_animation("animation.hell_juggernaut.slam", 2.2, {
        # the impact settle cannot drop the root below zero: the hooves rest
        # exactly on y = 0, so a negative root drives them into the ground
        "hell_juggernaut": [[kf("position", t, (0, y, 0), "catmullrom")
                             for t, y in ((0.0, 0.0), (0.8, 3.0), (1.2, 0.5),
                                          (1.5, 1.5), (2.2, 0.0))]],
        "spine": [[kf("rotation", t, (rx, 0, 0), "catmullrom")
                   for t, rx in ((0.0, 0.0), (0.8, 12.0), (1.2, -16.0), (1.6, -10.0),
                                 (2.2, 0.0))]],
        "head": [[kf("rotation", t, (rx, 0, 0), "catmullrom")
                  for t, rx in ((0.0, 0.0), (0.8, 10.0), (1.2, -14.0), (2.2, 0.0))]],
        "jaw": [[kf("rotation", t, (rx, 0, 0), "catmullrom")
                 for t, rx in ((0.0, 0.0), (0.8, -20.0), (1.2, -30.0), (2.2, 0.0))]],
        "arm_l_upper": [[kf("rotation", t, (rx, 0, rz), "catmullrom") for t, rx, rz in
                         ((0.0, 0, 0), (0.8, -40.0, 10.0), (1.2, 26.0, -4.0),
                          (2.2, 0, 0))]],
        "arm_r_upper": [[kf("rotation", t, (rx, 0, -rz), "catmullrom") for t, rx, rz in
                         ((0.0, 0, 0), (0.8, -40.0, 10.0), (1.2, 26.0, -4.0),
                          (2.2, 0, 0))]],
        "arm_l_fore": [[kf("rotation", t, (rx, 0, 0), "catmullrom")
                        for t, rx in ((0.0, 0.0), (0.8, -30.0), (1.2, 18.0), (2.2, 0.0))]],
        "arm_r_fore": [[kf("rotation", t, (rx, 0, 0), "catmullrom")
                        for t, rx in ((0.0, 0.0), (0.8, -30.0), (1.2, 18.0), (2.2, 0.0))]],
        "pauldron_l": [[kf("rotation", t, (0, 0, rz), "catmullrom")
                        for t, rz in ((0.0, 0.0), (0.8, -6.0), (1.2, 6.0), (2.2, 0.0))]],
        "pauldron_r": [[kf("rotation", t, (0, 0, -rz), "catmullrom")
                        for t, rz in ((0.0, 0.0), (0.8, -6.0), (1.2, 6.0), (2.2, 0.0))]],
        "leg_l_thigh": [[kf("rotation", t, (rx, 0, 0), "catmullrom")
                         for t, rx in ((0.0, 0.0), (0.8, -6.0), (1.2, 8.0), (2.2, 0.0))]],
        "leg_r_thigh": [[kf("rotation", t, (rx, 0, 0), "catmullrom")
                         for t, rx in ((0.0, 0.0), (0.8, -6.0), (1.2, 8.0), (2.2, 0.0))]],
        "leg_l_shin": [[kf("rotation", t, (rx, 0, 0), "catmullrom")
                        for t, rx in ((0.0, 0.0), (0.8, 8.0), (1.2, -10.0), (2.2, 0.0))]],
        "leg_r_shin": [[kf("rotation", t, (rx, 0, 0), "catmullrom")
                        for t, rx in ((0.0, 0.0), (0.8, 8.0), (1.2, -10.0), (2.2, 0.0))]],
        "tail_t1": [[kf("rotation", t, (rx, 0, 0), "catmullrom")
                     for t, rx in ((0.0, 0.0), (0.8, -20.0), (1.2, -3.0), (2.2, 0.0))]],
        "tail_t2": [[kf("rotation", t, (rx, 0, 0), "catmullrom")
                     for t, rx in ((0.0, 0.0), (1.0, -15.0), (1.4, -3.0), (2.2, 0.0))]],
        "tail_t3": [[kf("rotation", t, (rx, 0, 0), "catmullrom")
                     for t, rx in ((0.0, 0.0), (1.2, -10.0), (1.6, -3.0), (2.2, 0.0))]],
    }, by_name)
    return [idle, roar, slam]


# --- assembly --------------------------------------------------------------
def assemble() -> dict:
    hips = add_mirrors(build_hips())
    torso = add_mirrors(build_torso())
    head = add_mirrors(build_head())
    torso["children"] += [head]
    for build in (build_pauldron, build_arm):
        half = side_tree("_l", build())
        torso["children"] += [half, mirror_tree(half)]
    hips["children"] += [torso, add_mirrors(build_tail())]
    for build in (build_leg,):
        half = side_tree("_l", build())
        hips["children"] += [half, mirror_tree(half)]
    return group(MODEL_NAME, children=[hips], origin=(0, 0, 0))


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

    lo, hi = bounds(tree)
    print(f"bounds  x {lo[0]:7.1f}..{hi[0]:7.1f}  y {lo[1]:7.1f}..{hi[1]:7.1f}  "
          f"z {lo[2]:7.1f}..{hi[2]:7.1f}   (h {hi[1] - lo[1]:.1f}, "
          f"w {hi[0] - lo[0]:.1f}, d {hi[2] - lo[2]:.1f})")

    atlases = build_atlases(tree, PAINTERS, GLOW_MATERIALS,
                            sizes=(256, 320, 384, 448, 512, 640, 768))
    for idx, atlas in atlases.items():
        unpainted = check_painted(atlas)
        if unpainted:
            raise SystemExit(f"texture {idx} rects left unpainted: {unpainted[:8]}")
    images = {idx: atlas.image() for idx, atlas in atlases.items()}
    for idx, name in ((TEX_BODY, f"{MODEL_NAME}.png"), (TEX_GLOW, f"{MODEL_NAME}_glow.png")):
        images[idx].save(os.path.join(OUT_DIR, name))

    model_path = os.path.join(OUT_DIR, f"{MODEL_NAME}.bbmodel")
    n = write_model(model_path, tree, atlases, images, MODEL_NAME, GLOW_MATERIALS,
                    animations=build_animations)
    used = {idx: sum(w * h for _x, _y, w, h in a.rects.values()) for idx, a in atlases.items()}
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
