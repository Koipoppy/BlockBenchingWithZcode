"""Build 炼狱链枷 (infernal_flail) as a Blockbench project.

    python 兵器/infernal_flail/build_infernal_flail.py [--no-preview]

A one-and-a-half-hand Nether flail: a blackstone haft banded in netherite and
gold, a hanging chain of five interlocking links, and a spiked magma ball on the
end of it with lava cracks burning through the crust. Built against the same
brief as the rest of 人工建模参考/兵器 (that set has staffs, greatswords, axes,
bows, a hammer and -- after undead_scythe -- a scythe, but no flail), and on the
same scaffolding: tools/bbmodel_build.py.

Where undead_scythe is bone, soul-fire green and a crescent, this one is stone,
magma orange and a ball on a chain: the two read as different weapons from the
same workshop rather than as a colour swap.

  * the chain is five real links, each authored in its own nested group with the
    pivot at the overlap with the link above, so the whole chain and the head
    can swing and still hang together (the animation gate checks detachment);
  * the head is a stepped voxel ball (8 / 11+ / 12 / 11+ / 8 units wide) with
    six tapering spikes, gold hoops at the shoulders and magma cracks standing
    0.4 proud of the crust -- proud, not flush, or they would z-fight the face
    they sit on;
  * a cluster of blaze rods at the crown does the job the scythe's skull does:
    it says what the weapon is before you see the head.

Palette and glow map are the Nether's: blackstone, netherite, gold, blood-dark
leather, magma. The emissive map carries the lava cracks, the crack glow inside
the ball, the blaze-rod tips and two floating motes.
"""
from __future__ import annotations

import argparse
import math
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.dont_write_bytecode = True
REPO = HERE
while not os.path.isfile(os.path.join(REPO, "tools", "bbmodel_kit.py")):
    parent = os.path.dirname(REPO)
    if parent == REPO:
        raise SystemExit(f"repo root not found above {HERE}")
    REPO = parent
sys.path.insert(0, os.path.join(REPO, "tools"))
from bbmodel_kit import (FACES, V, walk_groups,  # noqa: E402
                         coplanar_conflicts, posed_contacts, stretch_report)
from bbmodel_build import (FM, S, TEX_BODY, TEX_GLOW, at, blobs, build_atlases,  # noqa: E402
                           check_painted, cube, edge_lit, group, hoop, kf, link,
                           make_animation, ramp, rect_key, render_previews,
                           rng_for, streaks, tint, write_model)

OUT_DIR = HERE
MODEL_NAME = "infernal_flail"
GLOW_MATERIALS = {"magma", "ember", "blaze"}

# --- palette ---------------------------------------------------------------
BLACK_HI, BLACK, BLACK_MID, BLACK_DK = (96, 86, 82), (72, 64, 62), (52, 46, 46), (32, 28, 28)
NETH_HI, NETH, NETH_DK, NETH_DEEP = (78, 68, 76), (52, 44, 50), (34, 28, 34), (20, 16, 22)
STEEL_HI, STEEL, STEEL_DK = (150, 146, 148), (100, 96, 100), (58, 55, 60)
GOLD_HI, GOLD, GOLD_DK = (250, 214, 118), (208, 160, 58), (140, 100, 30)
LEATH_HI, LEATH, LEATH_DK = (110, 74, 52), (74, 50, 36), (48, 32, 24)
BLOOD, BLOOD_DK = (86, 32, 24), (54, 20, 14)
CHAIN_HI, CHAIN, CHAIN_DK = (152, 144, 146), (104, 98, 102), (58, 54, 58)
CRUST_HI, CRUST, CRUST_DK, CRUST_DEEP = (110, 88, 72), (78, 60, 50), (52, 40, 34), (32, 25, 22)
LAVA_HI, LAVA, LAVA_MID, LAVA_DK = (255, 226, 150), (252, 158, 52), (214, 86, 20), (128, 38, 12)
BONE, BONE_DK = (124, 112, 98), (72, 64, 56)
ASH, ASH_DK = (104, 96, 90), (66, 60, 56)


# --- painters --------------------------------------------------------------
def paint_blackstone(cv, r, key):
    """Nether blackstone: near-black, warm, gravelly."""
    a = at(cv, r)
    rng = rng_for(key)
    ramp(a, [(0.0, BLACK_HI), (0.22, BLACK), (0.72, BLACK_MID), (1.0, BLACK_DK)])
    blobs(a, rng, BLACK_DK, 3, 1, 2)
    blobs(a, rng, BLACK_HI, 2, 1, 1)
    tint(a, rng, BLACK_MID, 0.10)
    streaks(a, rng, BLACK_DK, max(1, a.shape[1] // (3 * S)), vertical=True, lo=3)
    edge_lit(a, top=BLACK_HI, bottom=(20, 17, 17))


def paint_netherite(cv, r, key):
    """Netherite: black with a violet sheen along the light."""
    a = at(cv, r)
    rng = rng_for(key)
    ramp(a, [(0.0, NETH_HI), (0.20, NETH), (0.70, NETH_DK), (1.0, NETH_DEEP)])
    streaks(a, rng, NETH_HI, max(1, a.shape[1] // (3 * S)), vertical=False, lo=2, wide=1)
    tint(a, rng, NETH_DK, 0.10)
    edge_lit(a, top=NETH_HI, bottom=(16, 13, 16))


def paint_gold(cv, r, key):
    a = at(cv, r)
    rng = rng_for(key)
    ramp(a, [(0.0, GOLD_HI), (0.28, GOLD), (0.80, GOLD_DK), (1.0, (92, 64, 20))])
    streaks(a, rng, GOLD_HI, max(1, a.shape[1] // (2 * S)), vertical=False, lo=1, wide=1)
    tint(a, rng, GOLD_DK, 0.10)
    edge_lit(a, top=(255, 236, 176), bottom=(74, 50, 16))


def paint_leather_nether(cv, r, key):
    """Blood-dark grip leather with a turn of gold wire."""
    a = at(cv, r)
    rng = rng_for(key)
    ramp(a, [(0.0, LEATH_HI), (0.28, LEATH), (1.0, LEATH_DK)])
    h = a.shape[0]
    for y in range(S, h, 5 * S):
        a[y:y + S, :, :3] = np.array(LEATH_DK, np.uint8)
        a[y + S:y + 2 * S, :, :3] = np.array(LEATH_HI, np.uint8)
    for y in range(0, h, 11 * S):                      # the gold wire
        a[y:y + 1, :, :3] = np.array(GOLD_DK, np.uint8)
        a[min(h - 1, y + 1):y + 2, :, :3] = np.array(GOLD, np.uint8)
    blobs(a, rng, BLOOD_DK, 2, 1, 2)
    blobs(a, rng, BLOOD, 2, 1, 1)
    edge_lit(a, bottom=LEATH_DK)


def paint_spike(cv, r, key):
    """Forged steel: the spikes have to read against a near-black crust."""
    a = at(cv, r)
    rng = rng_for(key)
    ramp(a, [(0.0, STEEL_HI), (0.24, STEEL), (0.72, STEEL_DK), (1.0, (34, 32, 36))])
    streaks(a, rng, STEEL_HI, max(1, a.shape[1] // (2 * S)), vertical=False, lo=1, wide=1)
    tint(a, rng, STEEL_DK, 0.10)
    edge_lit(a, top=(182, 178, 180), bottom=(28, 26, 30))


def paint_chain(cv, r, key):
    a = at(cv, r)
    rng = rng_for(key)
    a[:, :, :3] = np.array(CHAIN, np.uint8)
    a[:, :, 3] = 255
    tint(a, rng, CHAIN_HI, 0.16)
    tint(a, rng, CHAIN_DK, 0.14)
    tint(a, rng, BLOOD_DK, 0.05)
    a[0:1, :, :3] = np.array(CHAIN_HI, np.uint8)
    a[-1:, :, :3] = np.array((26, 24, 26), np.uint8)


def paint_crust(cv, r, key):
    """The magma ball's crust: cooled rock with heat still under it."""
    a = at(cv, r)
    rng = rng_for(key)
    ramp(a, [(0.0, CRUST_HI), (0.25, CRUST), (0.75, CRUST_DK), (1.0, CRUST_DEEP)])
    blobs(a, rng, CRUST_DEEP, 4, 1, 2)
    blobs(a, rng, CRUST_HI, 3, 1, 1)
    streaks(a, rng, LAVA_DK, max(1, a.shape[1] // (4 * S)), vertical=True, lo=2, wide=1)
    tint(a, rng, CRUST_DK, 0.10)
    edge_lit(a, top=CRUST_HI, bottom=(10, 8, 8))


def paint_bone_dark(cv, r, key):
    """Wither-bone: the charm at the butt, grey and cracked."""
    a = at(cv, r)
    rng = rng_for(key)
    ramp(a, [(0.0, BONE), (0.45, BONE_DK), (1.0, (40, 36, 32))])
    streaks(a, rng, (40, 36, 32), max(1, a.shape[1] // (2 * S)), vertical=True, lo=2, hi=4)
    tint(a, rng, BONE, 0.08)
    edge_lit(a, top=BONE, bottom=(34, 30, 26))


def paint_ash(cv, r, key):
    a = at(cv, r)
    rng = rng_for(key)
    ramp(a, [(0.0, ASH), (0.5, ASH_DK), (1.0, (40, 36, 34))])
    tint(a, rng, ASH, 0.14)
    tint(a, rng, (34, 30, 28), 0.10)
    edge_lit(a, top=ASH)


def paint_magma(cv, r, key):
    """Emissive: the crack itself -- white-hot at the core, soot at the rim."""
    a = at(cv, r)
    h, w = a.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    d = np.sqrt(((yy - (h - 1) / 2) / max(1.0, h * 0.62)) ** 2 +
                ((xx - (w - 1) / 2) / max(1.0, w * 0.62)) ** 2)
    d = np.clip(d, 0, 1)
    col = (np.array(LAVA_HI, float) * (1 - d[..., None]) +
           np.array(LAVA_MID, float) * d[..., None])
    a[:, :, :3] = np.clip(col, 0, 255).astype(np.uint8)
    a[:, :, 3] = 255
    rng = rng_for(key)
    a[0:S, :, :3] = np.array(LAVA_DK, np.uint8)
    a[-S:, :, :3] = np.array(LAVA_DK, np.uint8)
    tint(a, rng, LAVA, 0.12)


def paint_ember(cv, r, key):
    a = at(cv, r)
    h, w = a.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    d = np.clip(np.sqrt(((yy - (h - 1) / 2) / max(1.0, h * 0.62)) ** 2 +
                        ((xx - (w - 1) / 2) / max(1.0, w * 0.62)) ** 2), 0, 1)
    col = (np.array(LAVA_HI, float) * (1 - d[..., None]) +
           np.array((96, 26, 8), float) * d[..., None])
    a[:, :, :3] = np.clip(col, 0, 255).astype(np.uint8)
    a[:, :, 3] = 255


def paint_blaze(cv, r, key):
    """Emissive: a blaze rod -- dark at both cut ends, molten down the middle,
    with a hotter core stripe so the side faces read too (they only ever see
    the width-wise outer columns)."""
    a = at(cv, r)
    h, w = a.shape[:2]
    ramp(a, [(0.0, (44, 16, 6)), (0.22, LAVA_DK), (0.42, LAVA), (0.55, (255, 208, 120)),
             (0.68, LAVA), (0.88, LAVA_DK), (1.0, (44, 16, 6))])
    core = max(0, (w - S) // 2)
    a[:, core:core + S, :3] = np.array((255, 244, 200), np.uint8)
    a[:, :, 3] = 255


PAINTERS = {
    "blackstone": paint_blackstone, "netherite": paint_netherite, "gold": paint_gold,
    "leather_nether": paint_leather_nether, "chain": paint_chain, "crust": paint_crust,
    "bone_dark": paint_bone_dark, "ash": paint_ash, "magma": paint_magma,
    "spike": paint_spike,
    "ember": paint_ember, "blaze": paint_blaze,
}

# --- the weapon ------------------------------------------------------------
# Haft: y 0 (butt) .. 90 (chain ring). The chain runs the last stretch in line
# with the haft and the ball hangs off the end of it, the way a flail carries.
HAFT_HW = 1.75
RING_Y0, RING_Y1 = 87.6, 90.4                 # the eye the chain hooks through
LINK_Y = (88.0, 89.4, 90.8, 92.2, 93.6)       # five links, overlapped 0.6
BALL_Y = 96.0                                 # the ball's underside
SPIKE = 3


def build_head():
    """The head: a cut gem -- one tall octagonal block with a chamfered top and
    bottom -- with five pyramidal spikes and lava cracks down its faces.

    Two earlier attempts are worth not repeating: a 12-unit sphere out of
    axis-aligned boxes is stacked discs whose wide rims read as a pagoda roof,
    and a spike whose steps only taper in one axis has a big flat top face, so
    it reads as a slab. The spikes here taper in BOTH cross axes, every step."""
    crust = FM(all="crust")
    steel = FM(all="spike")
    neth = FM(all="netherite")
    gold = FM(all="gold")
    parts = [
        cube("ball_socket", (-2.0, 94.6, -2.0), (2.0, 96.0, 2.0), neth),
        cube("ball_low", (-3.6, 95.0, -3.0), (3.6, 98.5, 3.0), crust),
        cube("ball_low_z", (-3.0, 95.05, -3.6), (3.0, 98.45, 3.6), crust),
        cube("ball_mid", (-5.5, 98.0, -4.4), (5.5, 105.5, 4.4), crust),
        cube("ball_mid_z", (-4.4, 98.05, -5.5), (4.4, 105.45, 5.5), crust),
        cube("ball_top", (-3.6, 105.0, -3.0), (3.6, 108.5, 3.0), crust),
        cube("ball_top_z", (-3.0, 105.05, -3.6), (3.0, 108.45, 3.6), crust),
    ]
    parts += hoop("ball_collar", 96.0, 97.0, 3.4, 0.8, gold)
    # spikes: each step pulls in on both cross axes, so no step leaves a flat
    # top worth seeing
    for sx, tag in ((1, "xp"), (-1, "xn")):
        parts += [
            cube(f"spike_{tag}0", (sx * 4.2, 98.4, -2.2), (sx * 6.0, 104.4, 2.2), steel),
            cube(f"spike_{tag}1", (sx * 6.0, 99.4, -1.5), (sx * 7.6, 103.4, 1.5), steel),
            cube(f"spike_{tag}2", (sx * 7.6, 100.2, -1.0), (sx * 9.0, 102.6, 1.0), steel),
            cube(f"spike_{tag}3", (sx * 9.0, 100.8, -0.6), (sx * 10.2, 102.0, 0.6), steel),
            cube(f"spike_{tag}4", (sx * 10.2, 101.1, -0.35), (sx * 11.0, 101.7, 0.35), gold),
        ]
    for sz, tag in ((1, "zp"), (-1, "zn")):
        parts += [
            cube(f"spike_{tag}0", (-2.2, 98.4, sz * 4.2), (2.2, 104.4, sz * 6.0), steel),
            cube(f"spike_{tag}1", (-1.5, 99.4, sz * 6.0), (1.5, 103.4, sz * 7.6), steel),
            cube(f"spike_{tag}2", (-1.0, 100.2, sz * 7.6), (1.0, 102.6, sz * 9.0), steel),
            cube(f"spike_{tag}3", (-0.6, 100.8, sz * 9.0), (0.6, 102.0, sz * 10.2), steel),
            cube(f"spike_{tag}4", (-0.35, 101.1, sz * 10.2), (0.35, 101.7, sz * 11.0), gold),
        ]
    parts += [
        cube("spike_up0", (-1.8, 106.0, -1.8), (1.8, 109.2, 1.8), steel),
        cube("spike_up1", (-1.3, 109.2, -1.3), (1.3, 111.2, 1.3), steel),
        cube("spike_up2", (-0.9, 111.2, -0.9), (0.9, 112.8, 0.9), steel),
        cube("spike_up3", (-0.5, 112.8, -0.5), (0.5, 113.8, 0.5), gold),
    ]
    # lava cracks down the gem's four faces, set to the side of the spikes
    for sx, sz in ((1, -1), (-1, 1)):
        parts.append(cube(f"crack_x{sx}", (sx * 4.9, 98.8, sz * 1.7),
                          (sx * 5.9, 105.0, sz * 4.5), FM(all="magma")))
    for sz, sx in ((1, -1), (-1, 1)):
        parts.append(cube(f"crack_z{sz}", (sx * 1.7, 98.8, sz * 4.9),
                          (sx * 4.5, 105.0, sz * 5.9), FM(all="magma")))
    return parts


def build_haft():
    """Blackstone, netherite, gold: the butt, the grip, the crown and the eye
    the chain hangs from."""
    black = FM(all="blackstone")
    neth = FM(all="netherite")
    gold = FM(all="gold")
    parts = [
        cube("butt_tip", (-1.4, 0.0, -1.4), (1.4, 1.8, 1.4), gold),
        cube("butt_cap", (-2.0, 1.8, -2.0), (2.0, 5.4, 2.0), black),
        cube("butt_collar", (-2.35, 5.4, -2.35), (2.35, 7.6, 2.35), neth),
        cube("shaft_low", (-HAFT_HW, 7.6, -HAFT_HW), (HAFT_HW, 30.0, HAFT_HW), black),
    ]
    parts += hoop("hoop_mid", 30.0, 32.2, 1.95, 0.5, neth)
    parts += [
        cube("shaft_mid", (-1.65, 32.2, -1.65), (1.65, 50.0, 1.65), black),
        cube("grip_core", (-1.5, 49.4, -1.5), (1.5, 70.0, 1.5), black),
    ]
    parts += hoop("gold_ring0", 50.0, 51.4, 1.85, 0.55, gold)
    parts.append(cube("grip_wrap", (-1.85, 51.4, -1.85), (1.85, 68.0, 1.85),
                      FM(sides="leather_nether", tb="leather_nether")))
    parts += hoop("gold_ring1", 68.0, 69.4, 1.85, 0.55, gold)
    parts += [
        cube("shaft_up", (-1.6, 69.4, -1.6), (1.6, 84.0, 1.6), black),
        cube("crown", (-2.0, 84.0, -2.0), (2.0, 87.6, 2.0), neth),
    ]
    # the eye: a link standing in the XY plane, its hole vertical
    parts += link("chain_eye", -1.8, 87.0, -0.45, 3.6, 3.6, 0.8,
                  FM(all="netherite"), plane="xy")
    return parts


def build_charms():
    """A blaze-rod cluster at the crown and a bone charm at the butt -- the two
    places the eye lands when the head is out of frame."""
    rods = []
    for i, (rz, rx) in enumerate(((-62, 0), (62, 0), (0, -62), (0, 62))):
        g = group(f"blaze{i}", cubes=[
            cube(f"blaze{i}_a", (-0.9, 83.4, -0.9), (0.9, 88.0, 0.9), FM(all="blaze")),
            cube(f"blaze{i}_b", (-0.6, 88.0, -0.6), (0.6, 90.6, 0.6), FM(all="blaze")),
        ], origin=(0.0, 85.4, 0.0), rotation=[rx, 0, rz])
        rods.append(g)
    # a trophy bone tied to the haft on a chain hoop -- Nether weapons wear
    # what they killed
    bone = hoop("charm_hoop", 13.0, 14.2, 1.95, 0.5, FM(all="chain"))
    bone += [
        cube("charm_bone", (-3.6, 9.0, -0.9), (-1.6, 14.0, 0.9), FM(all="bone_dark")),
        cube("charm_wrap", (-3.7, 12.0, -1.0), (-1.5, 13.0, 1.0), FM(all="chain")),
    ]
    return rods, bone


def build_chain():
    """Five links, each in its own group pivoting on the overlap above it, so
    the chain (and the head under it) can swing and still hang together."""
    links = []
    # (y, plane, w, h, t); the link is centred on its own axis, and each one is
    # walked a twentieth of a unit off the previous so consecutive links never
    # share a face plane (their bars interlock, which is the point)
    # three fat links: at this scale a slim chain reads as a rod, so the links
    # are 2.6 wide and overlap each other by 1.4 -- the interlock is the read
    specs = [(87.6, "zy", 3.2, 4.0, 1.6), (90.4, "xy", 3.2, 4.0, 1.6),
             (93.2, "zy", 3.2, 4.0, 1.6)]
    for i, (y, plane, w, h, t) in enumerate(specs):
        # every link is walked a twentieth of a unit off the last on each axis
        # (and a touch taller): consecutive links interlock by ~1.2 units, so
        # without the walk their bars land in each other's planes and z-fight
        off = 0.05 * (i + 1)
        yy = y + 0.03 * i
        hh = h + 0.05 * i
        if plane == "zy":
            cubes = link(f"chainlink{i}", -t / 2 + off, yy, -w / 2 + off, w, hh, t,
                         FM(all="chain"), plane="zy")
        else:
            cubes = link(f"chainlink{i}", -w / 2 + off, yy, -t / 2 + off, w, hh, t,
                         FM(all="chain"), plane="xy")
        links.append((cubes, y + 0.6))
    chain = None
    for i in reversed(range(len(links))):
        cubes, pivot_y = links[i]
        chain = group(f"chain{i}", cubes=cubes, children=[chain] if chain else [],
                      origin=(0.0, pivot_y, 0.0))
    return chain


def build_embers():
    """Two motes off the ball, deliberately detached (whitelisted as free)."""
    spots = [(-9.5, 106.5, -3.5), (8.0, 94.6, 5.0)]
    return [cube(f"ember{i}", (x, y, z), (x + 2.0, y + 2.0, z + 2.0), FM(all="ember"))
            for i, (x, y, z) in enumerate(spots)]


def build_tree():
    rods, bone = build_charms()
    embers = build_embers()
    head = group("head", cubes=build_head(), origin=(0.0, 96.2, 0.0))
    chain = build_chain()
    # hang the ball off the last link (walk to the innermost one, so the chain
    # can change length without editing this line)
    last = chain
    while last["children"]:
        last = last["children"][0]
    last["children"].append(head)
    root = group(MODEL_NAME, children=[
        group("haft", cubes=build_haft(), origin=(0.0, 0.0, 0.0)),
        group("crown_rods", children=rods, origin=(0.0, 87.6, 0.0)),
        group("charm", cubes=bone, origin=(0.0, 0.0, 0.0)),
        group("chain", children=[chain], origin=(0.0, 88.4, 0.0)),
        group("embers", cubes=embers, origin=(0.0, 0.0, 0.0)),
    ], origin=(0.0, 0.0, 0.0))
    return root


# --- self checks -----------------------------------------------------------
def check_solids(tree):
    bad = []
    for path, c, _R, _t in walk_groups(tree):
        d = [c["to"][k] - c["from"][k] for k in range(3)]
        if any(v <= 1e-6 for v in d):
            bad.append((path, "degenerate"))
        elif min(d) < 0.5 and not any(k in path for k in ("chain", "charm", "crack")):
            bad.append((path, f"thin {min(d):.2f}"))
    return bad


def bounds(tree):
    lo = np.array([1e9] * 3)
    hi = np.array([-1e9] * 3)
    for _path, c, R, t in walk_groups(tree):
        for x in (c["from"][0], c["to"][0]):
            for y in (c["from"][1], c["to"][1]):
                for z in (c["from"][2], c["to"][2]):
                    p = R @ V(x, y, z) + t
                    lo, hi = np.minimum(lo, p), np.maximum(hi, p)
    return lo, hi


PREVIEWS = [
    ("", 222.0, 14.0, 150.0, (0.0, 58.0, 0.0)),
    ("_front", 180.0, 6.0, 150.0, (0.0, 58.0, 0.0)),
    ("_side", 268.0, 6.0, 150.0, (0.0, 58.0, 0.0)),
    ("_head", 230.0, 16.0, 58.0, (0.0, 100.0, 0.0)),
    ("_chain", 240.0, 18.0, 52.0, (0.0, 82.0, 0.0)),
]


# --- animation -------------------------------------------------------------
def build_animations(by_name: dict) -> list:
    """A two-second idle: the flail hangs and swings a little, the chain links
    lag behind each other, the magma breathes and the rods flicker."""
    swing = [
        kf("rotation", 0.0, (0, 0, 0), "catmullrom"),
        kf("rotation", 0.7, (0, 0, 6.0), "catmullrom"),
        kf("rotation", 1.4, (0, 0, -5.0), "catmullrom"),
        kf("rotation", 2.0, (0, 0, 0), "catmullrom"),
    ]
    return [make_animation("animation.infernal_flail.idle", 2.0, {
        "infernal_flail": [[
            kf("position", 0.0, (0, 0, 0), "catmullrom"),
            kf("position", 1.0, (0, 0.7, 0), "catmullrom"),
            kf("position", 2.0, (0, 0, 0), "catmullrom")]],
        "chain0": [swing],
        "chain1": [[kf("rotation", t, (0, 0, v * 0.8), "catmullrom")
                    for t, v in ((0.0, 0), (0.7, 6.0), (1.4, -5.0), (2.0, 0))]],
        "chain2": [[kf("rotation", t, (0, 0, v * 0.7), "catmullrom")
                    for t, v in ((0.0, 0), (0.5, 4.0), (1.2, -5.5), (2.0, 0))]],
        "head": [[
            kf("rotation", 0.0, (0, 0, 0), "catmullrom"),
            kf("rotation", 0.6, (0, 8.0, -4.0), "catmullrom"),
            kf("rotation", 1.5, (0, -10.0, 5.0), "catmullrom"),
            kf("rotation", 2.0, (0, 0, 0), "catmullrom")]],
        "crown_rods": [[
            kf("rotation", 0.0, (0, 0, 0), "catmullrom"),
            kf("rotation", 1.0, (2.5, 0, 0), "catmullrom"),
            kf("rotation", 2.0, (0, 0, 0), "catmullrom")]],
        "embers": [[
            kf("position", 0.0, (0, 0, 0), "catmullrom"),
            kf("position", 1.1, (0, 1.4, 0), "catmullrom"),
            kf("position", 2.0, (0, 0, 0), "catmullrom")]],
        "charm": [[
            kf("rotation", 0.0, (0, 0, 0), "catmullrom"),
            kf("rotation", 0.8, (0, 0, 4.0), "catmullrom"),
            kf("rotation", 1.6, (0, 0, -3.0), "catmullrom"),
            kf("rotation", 2.0, (0, 0, 0), "catmullrom")]],
    }, by_name)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-preview", action="store_true")
    args = ap.parse_args()

    tree = build_tree()

    bad = coplanar_conflicts(tree)
    if bad:
        for pi, pj, axis, tag, coord in bad[:20]:
            print(f"  z-fight risk: {pi} / {pj} on {axis}={coord:.3f} ({tag})")
        raise SystemExit(f"{len(bad)} coplanar same-facing overlaps")

    stretched = stretch_report(tree)
    if stretched:
        agg: dict = {}
        for _path, _face, want, got in stretched:
            agg[(round(want, 2), got)] = agg.get((round(want, 2), got), 0) + 1
        print(f"stretched faces: {len(stretched)}")
        for (want, got), n in sorted(agg.items()):
            print(f"  {want:6.2f} -> {got} px   x{n}")

    thin = check_solids(tree)
    if thin:
        for path, why in thin[:10]:
            print(f"  solid: {path}: {why}")
        raise SystemExit(f"{len(thin)} bad cubes")

    lo, hi = bounds(tree)
    print(f"bounds  x {lo[0]:7.2f}..{hi[0]:7.2f}  y {lo[1]:7.2f}..{hi[1]:7.2f}  "
          f"z {lo[2]:7.2f}..{hi[2]:7.2f}   (h {hi[1] - lo[1]:.1f})")

    atlases = build_atlases(tree, PAINTERS, GLOW_MATERIALS)
    for idx, atlas in atlases.items():
        unpainted = check_painted(atlas)
        if unpainted:
            raise SystemExit(f"texture {idx} rects left unpainted: {unpainted}")
    images = {idx: atlas.image() for idx, atlas in atlases.items()}
    for idx, name in ((TEX_BODY, f"{MODEL_NAME}.png"), (TEX_GLOW, f"{MODEL_NAME}_glow.png")):
        images[idx].save(os.path.join(OUT_DIR, name))

    model_path = os.path.join(OUT_DIR, f"{MODEL_NAME}.bbmodel")
    cubes = write_model(model_path, tree, atlases, images, MODEL_NAME, GLOW_MATERIALS,
                        animations=build_animations)
    used = {idx: sum(w * h for _x, _y, w, h in a.rects.values()) for idx, a in atlases.items()}
    print(f"{model_path}  ({cubes} cubes, res {atlases[TEX_BODY].size // S}, "
          f"body {atlases[TEX_BODY].size}px {len(atlases[TEX_BODY].rects)} rects "
          f"{used[TEX_BODY]}px, glow {len(atlases[TEX_GLOW].rects)} rects {used[TEX_GLOW]}px)")

    if not args.no_preview:
        render_previews(model_path, OUT_DIR, MODEL_NAME, PREVIEWS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
