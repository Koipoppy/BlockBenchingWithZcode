"""Build 半人马骑士 (centaur_knight) as a Blockbench project.

    python 生物/centaur_knight/build_centaur_knight.py [--no-preview]

A centaur knight and his long trident. 118 units to the helm, 130 to the
trident's point, 40 across the horse's ribs.

Every form here is derived from the THING:

  * the HORSE'S BODY is an anatomical profile, not a pipe. `BODY` lists the
    thirteen cross-sections a horse actually has: the brisket tapering out of
    nothing, the shoulder, the girth (deepest, right behind the elbow), the
    ribs, the loin (where the back dips), the flank, the haunch, the croup. Each
    section's plates span to the midpoints of its neighbours, so the surface is
    continuous end to end, and the two ends TAPER TO A CLOSE -- a run of rings
    with flat caps is a coffin, which is exactly what the first version's body
    read as. The chest and the rump are closed by the peytral and the crupper,
    which are barding and cap in one piece.
  * the LEGS are cones at the animal's joint heights. Horse proportions: the
    elbow sits at the belly line, the knee (carpus) at 0.36 of the withers, the
    fetlock at 0.15, and between them the cannon is a slim bone. That
    thick / thin / thick sequence is what makes a leg read as a leg. Each
    segment is a `taper_tube`: plates standing at the radius the cone has at the
    segment's middle and pitched onto its slope, so one segment meets the next
    at the joint's radius. One cylinder per segment is "two barrels stacked",
    which is what the first version's legs read as.
  * the TRIDENT is tubes end to end: a haft tapering from ferrule to socket,
    and a head of three prongs that are each a four-plate DIAMOND -- n=4 on a
    squashed radius gives two bevels a side, so a prong has a ridge and an edge
    instead of being a square bar, and a taper to r=0.4 ends it in a point. The
    two side prongs leave the socket, curve out, then crank back toward the
    centre blade, which runs longest. Nothing stacked, nothing stuck on: no
    boxes stepping a taper down, no rings wrapped round a shaft.
  * the KNIGHT is a harness of named pieces: a cuirass whose rings climb waist
    -> chest -> shoulder, a gorget over a mail collar, a helm with a domed skull
    and a visored face, a pauldron of three lames each covering a different band
    of the shoulder, and a fauld of lames over the join with the horse -- that
    join is why the fauld is there.
  * MATERIAL: he is steel, the horse under him is hide, and that contrast is
    what lets either read. The plates are painted as polished metal -- smooth
    model-space gradients, a hard highlight along the top edge of every plate,
    a terminator under it, almost no grain. The first version carried the
    golem's per-unit speckle at +-12%; at 2 px/unit that is a fabric weave, and
    the user read the armour as wool. One cold light, in the visor slit.

Geometry rules this script holds to (README.md conventions, ISSUE.md pitfalls):
  * every cube's SIZE is a whole number of units, so every face is an exact uv
    rect at S = 2; positions are on the 0.5 grid wherever the cube is not
    rotated (ring and cone plates sit wherever sin/cos puts them);
  * rest angles live on ELEMENTS, every group sits at zero, so a clip bends the
    rest pose instead of replacing it (ISSUE.md 6.2);
  * a band's plates are staggered along its axis, and a raised band rides a
    quarter off the band it is strapped over: two same-facing coincident planes
    are the per-pixel shimmer (ISSUE.md 13.3). Both coplanar gates run every
    build -- coplanar_visible for same-rotation pairs, zfight_world for rings
    and cones whose plates each carry their own heading;
  * the atlas is keyed by material, face and the cube's position in the model,
    and the painters sample a field that is a function of where it is on the
    creature: pieces at different places are never identical, and pieces that
    touch continue each other across the seam.

Deliberate overlaps (validate with interpenetration_depth 1.35, and
asymmetric for the two arms -- the right one holds the haft, so it does not
mirror the left): neighbouring plates overlap ~12% at their edges; consecutive
body sections overlap 2 units; every chain segment's core box sits inside its
own cone; the tops of all four legs and both shoulders are sunk into the body
they hang from; the tail's root is buried in the croup; the trident's haft
passes through the fist.
"""
from __future__ import annotations

import argparse
import math
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
from bbmodel_kit import (coplanar_visible, stretch_report,  # noqa: E402
                         zfight_world)
from bbmodel_build import (FM, S, TEX_BODY, TEX_GLOW, add_mirrors, at,  # noqa: E402
                           bounds, box, build_atlases, chain, check_grid,
                           check_painted, check_symmetric, dome, field3, group,
                           half, lift, local, put, rect_grid, render_previews,
                           ring, side_tree, slab, taper_tube, write_model)

OUT_DIR = HERE
MODEL_NAME = "centaur_knight"
GLOW_MATERIALS = {"glow"}          # the visor slit, and nothing else

# --- palette ---------------------------------------------------------------
# Polished steel for the harness: near-white highlights, a mid grey body, dark
# shadows. Polished metal is CONTRAST, not texture.
STL_HI, STL, STL_DK, STL_DEEP = (
    (252, 254, 255), (196, 206, 218), (104, 114, 128), (54, 61, 72))
# The horse: near-black hide with a warm cast, satin rather than matte.
HID_HI, HID, HID_DK, HID_DEEP = (
    (104, 84, 74), (64, 52, 47), (38, 30, 28), (18, 14, 13))
# Iron: the haft's ferrule and the mail collar under the gorget.
IRN_HI, IRN, IRN_DK, IRN_DEEP = (132, 132, 130), (88, 88, 87), (52, 52, 53), (26, 26, 27)
# Horn for the hooves.
HRN_HI, HRN, HRN_DK = (112, 104, 96), (76, 70, 64), (40, 36, 33)
# Leather: the haft's grip.
LTH_HI, LTH, LTH_DK = (128, 94, 62), (84, 58, 36), (46, 30, 19)
# Gilt, on one edge only: the band round the helm.
GLD_HI, GLD, GLD_DK = (255, 238, 178), (228, 190, 96), (124, 92, 28)
# The one light on the figure, and it is cold.
GLW_HI, GLW, GLW_DK = (240, 250, 255), (166, 222, 244), (28, 84, 130)
SEAM_C = (52, 56, 64)


# --- painters --------------------------------------------------------------
def _mix(c0, c1, t):
    t = np.asarray(t, float)
    if t.ndim == 0:
        return np.array(c0, float) * (1 - t) + np.array(c1, float) * t
    return (np.array(c0, float) * (1 - t[..., None])
            + np.array(c1, float) * t[..., None])


def _put(a, col):
    a[:, :, :3] = np.clip(np.asarray(col, float), 0, 255).astype(np.uint8)
    a[:, :, 3] = 255


def _plate(cv, r, key, ramp, up=False, grain=0.025, span=118.0, scratch=0,
           sheen=0.0):
    """A polished plate, in three layers and no more.

    1. a smooth gradient in model space, so the value runs down the whole figure
       and two plates either side of a seam continue each other;
    2. a hard vertical profile inside the rect -- one unit of highlight along
       the top edge, a terminator at the bottom: that is what a flat-shaded
       renderer needs in order to read a surface as gloss;
    3. a whisper of grain, and a few long scratches.

    The first version carried the golem's per-unit speckle at +-12% plus a
    blotch field. At 2 px/unit that is a fabric weave, and the user read the
    plates as wool: polished metal is the opposite of a noisy material.
    `sheen` adds a broad specular band a third of the way down a face, for
    materials that are smooth but not mirror -- hide and horn.
    """
    a = at(cv, r)
    X, Y, Z = rect_grid(key, r)
    h = max(2, r[3])
    tone = np.clip((Y - 4.0) / span, 0.0, 1.0)
    col = _mix(ramp[0], ramp[2] if up else ramp[1], tone)
    v = (np.arange(h) / (h - 1.0))[:, None, None]
    prof = 1.06 - 0.20 * v
    if sheen:
        prof = prof + sheen * np.exp(-((v - 0.32) ** 2) / 0.02)
    col = col * prof
    col = col * (1.0 - grain + 2 * grain * field3(np.floor(X), np.floor(Y),
                                                  np.floor(Z), 1.0,
                                                  seed=7))[..., None]
    for k in range(scratch):
        zz = field3(X * 0.25, np.floor(Y) * 4.0, np.floor(Z), 1.0, seed=11 + k)
        col = col - (zz < 0.05)[..., None] * (0.10 * float(np.mean(col)))
    col[0:S] = np.clip(col[0:S] * 1.24 + 18.0, 0, 255)   # the top edge: sky
    col[h - S:h] = col[h - S:h] * 0.78                  # the bottom: shadow
    _put(a, col)


def paint_steel(cv, r, key, up=False):
    _plate(cv, r, key, (STL_DEEP, STL, STL_HI) if up else (STL_DK, STL, STL_HI),
           up=up, grain=0.018, scratch=1)


def paint_hide(cv, r, key, up=False):
    _plate(cv, r, key, (HID_DEEP, HID, HID_HI) if up else (HID_DEEP, HID, HID),
           up=up, grain=0.03, sheen=0.12, scratch=2)


def paint_iron(cv, r, key, up=False):
    _plate(cv, r, key, (IRN_DEEP, IRN_DK, IRN_HI) if up else (IRN_DEEP, IRN, IRN),
           up=up, grain=0.03, scratch=2)


def paint_horn(cv, r, key, up=False):
    _plate(cv, r, key, (HRN_DK, HRN, HRN_HI) if up else (HRN_DK, HRN, HRN),
           up=up, grain=0.03, sheen=0.10)


def paint_leather(cv, r, key, up=False):
    _plate(cv, r, key, (LTH_DK, LTH, LTH_HI) if up else (LTH_DK, LTH, LTH),
           up=up, grain=0.05, scratch=2)


def paint_gold(cv, r, key, up=False):
    _plate(cv, r, key, (GLD_DK, GLD, GLD_HI) if up else (GLD_DK, GLD, GLD),
           up=up, grain=0.02)


def paint_seam(cv, r, key):
    """Inside a body, and the groove between two plates."""
    a = at(cv, r)
    a[:, :, :3] = np.array(SEAM_C, np.uint8)
    a[:, :, 3] = 255


def paint_glow(cv, r, key):
    """The visor slit: cold, falling off toward the rim so a three-unit slot
    still reads as a light rather than a sticker."""
    a = at(cv, r)
    h, w = a.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    d = np.clip(np.sqrt(((yy - (h - 1) / 2) / max(1.0, h * 0.62)) ** 2 +
                        ((xx - (w - 1) / 2) / max(1.0, w * 0.62)) ** 2), 0, 1)
    a[:, :, :3] = np.clip(_mix(GLW_HI, GLW_DK, d), 0, 255).astype(np.uint8)
    a[:, :, 3] = 255


PAINTERS = {
    "steel": paint_steel,
    "steel_hi": lambda cv, r, k: paint_steel(cv, r, k, up=True),
    "hide": paint_hide,
    "hide_hi": lambda cv, r, k: paint_hide(cv, r, k, up=True),
    "iron": paint_iron,
    "iron_hi": lambda cv, r, k: paint_iron(cv, r, k, up=True),
    "horn": paint_horn,
    "horn_hi": lambda cv, r, k: paint_horn(cv, r, k, up=True),
    "leather": paint_leather,
    "leather_hi": lambda cv, r, k: paint_leather(cv, r, k, up=True),
    "gold": paint_gold,
    "gold_hi": lambda cv, r, k: paint_gold(cv, r, k, up=True),
    "seam": paint_seam,
    "glow": paint_glow,
}

# Which face is "outside" depends on the piece:
#   * a plate of a RING (cuirass, helm, visor, gorget) is yawed, so its local +z
#     `south` is the surface you see;
#   * a stave of the BODY is rolled about z, so its local +x points outward and
#     east and west must be painted the same (which also keeps the mirrored half
#     correct);
#   * a dome plate is pitched and its local +y `up` is the outside;
#   * a CONE plate is turned about the limb's axis and `south` is the outside;
#   * a standalone plate carries metal on every side -- painting its flanks as
#     groove is what turned the first version's face into black bars.
STEEL_PLATE = FM(all="steel", north="seam", east="seam", west="seam",
                 up="steel_hi", down="steel")
STEEL_DOME = FM(all="steel", north="seam", east="seam", south="seam",
                down="seam")
STEELF = FM(all="steel", up="steel_hi", down="steel")
BODY_STAVE = FM(all="hide", up="seam", down="seam", north="hide", south="hide")
HIDE_F = FM(all="hide", up="hide_hi", down="hide")
IRONF = FM(all="iron", up="iron_hi", down="iron")
HORNF = FM(all="horn", up="horn_hi", down="horn")
LTHF = FM(all="leather", up="leather_hi", down="leather")
GILT = FM(all="gold", up="gold_hi", down="gold")
SEAMF = FM(all="seam")
GLOWF = FM(all="glow")


# --- vocabulary ------------------------------------------------------------
def barrel(prefix, z0, z1, cy, a, b, n, thick, mat, cx=0.0, alt=0, tilt=0.0):
    """The LEFT half of a band of staves around the BODY axis (z), plus the two
    plates that sit on x = 0 (the belly and the back) as centre parts.

    Plate k stands on the cross-section's ellipse and is rolled about z to face
    outward, so its local +x is the surface you see. Neighbours overlap ~12% at
    their edges, which is what closes the body. Three disciplines keep the
    plates' own planes apart, because a plate's end face is a plane the renderer
    has to pick a winner on (ISSUE.md 13.3):

    * the plate's tangential width steps a unit around the ring (odd k is one
      narrower), which is the house's `stagger`;
    * the plates walk half a unit along the body axis in a three-step cycle;
    * the SIDE plates take a quarter-unit shove along the ring's own tangent in
      a second three-step cycle, and the centre plates instead take their
      one-unit width step from the section index -- a plate on x = 0 has to
      straddle it, so it cannot be shoved sideways, and two sections whose belly
      plates come out the same width would otherwise share a plane.
    """
    steps = n // 2
    pts = []
    for k in range(steps + 1):
        t = math.radians(-90.0 + 180.0 * k / steps)
        s_, c_ = math.sin(t), math.cos(t)
        pts.append((cx + a * c_, cy + b * s_,
                    math.degrees(math.atan2(a * s_, b * c_))))
    L = int(round(z1 - z0))
    zc = (z0 + z1) / 2.0
    out = []
    for k, (px, py, phi) in enumerate(pts):
        chord = 0.0
        for j in (k - 1, k + 1):
            if 0 <= j < len(pts):
                chord = max(chord, math.dist((px, py), pts[j][:2]))
        centre = abs(px - cx) < 1e-6
        arc = max(1, math.ceil(chord * 1.12) - (k % 2) -
                  (alt % 2 if centre else 0))
        dz = 0.5 * ((k % 3) - 1)
        sh = 0.0 if centre else 0.25 * ((k + alt) % 3 - 1)
        name = f"{prefix}{k:02d}" + ("" if centre else "_l")
        # `tilt` pitches the plate onto the profile's slope, so its two ends
        # land on the radii of the sections in front of and behind it and the
        # body is one curved shell instead of a stack of cylinders
        out.append(slab(name, (px - sh * math.sin(phi), py + sh * math.cos(phi),
                               zc + dz), (thick, arc, L),
                        (0.0, tilt, phi), mat))
    return out


def body_rings(prefix, profile, n, thick, mat):
    """The horse's trunk: a ring of staves per cross-section in `profile`, each
    ring's plates spanning from the midpoint of the previous section to the
    midpoint of the next, plus a unit of overlap at either end.

    That span is what makes the body continuous -- a ring only as deep as its
    own section would leave the animal a stack of hoops with the interior
    showing between them. The rings butt at the section midpoints, and because
    every ring carries its own radii the surface reads as the animal's profile.
    """
    out = []
    zs = [p[0] for p in profile]
    for i, (z, cy, a, b) in enumerate(profile):
        z0 = z - 1.0 if i == 0 else (zs[i - 1] + z) / 2.0 - 1.0
        z1 = z + 1.0 if i == len(profile) - 1 else (z + zs[i + 1]) / 2.0 + 1.0
        # the local slope of the profile, which is what each plate is pitched
        # onto: without it every section is its own cylinder and the animal
        # reads as a stack of hoops
        lo = profile[max(0, i - 1)]
        hi = profile[min(len(profile) - 1, i + 1)]
        da = (hi[2] - lo[2]) / max(1e-6, hi[0] - lo[0])
        db = (hi[3] - lo[3]) / max(1e-6, hi[0] - lo[0])
        tilt = -math.degrees(math.atan(0.5 * (da + db)))
        # the end sections are small: fewer, wider plates around them, or the
        # ring's neighbours lap over each other at the centre line
        out += barrel(f"{prefix}{i}", z0, z1, cy, a, b,
                      n if a > 8 else 6, thick, mat, alt=i, tilt=tilt)
    return out


def front_arc(prefix, cy, h, a, b, n, keep, thick, mat, cz=0.0):
    """The FRONT of a ring only: `keep` plates either side of the centre line --
    a visor, a throat, any armour that wraps the front of a tube and stops.
    Authoring the left half and letting add_mirrors() close it keeps the mirror
    gate exact, exactly as ring() does."""
    steps = n // 2
    pts = []
    for i in range(steps + 1):
        psi = 180.0 * i / steps
        s, c = math.sin(math.radians(psi)), math.cos(math.radians(psi))
        pts.append((a * s, cz - b * c, math.degrees(math.atan2(b * s, -a * c))))
    out = []
    for i, (px, pz, yaw) in enumerate(pts):
        if i > keep:
            continue
        chord = 0.0
        for j in (i - 1, i + 1):
            if 0 <= j < len(pts):
                chord = max(chord, math.dist((px, pz), pts[j][:2]))
        arc = max(1, math.ceil(chord * 1.12))
        name = f"{prefix}{i:02d}" + ("_l" if px > 1e-6 else "")
        out.append(slab(name, (px, cy, pz),
                        (max(1, arc - (i % 2)), max(1, int(h) - (i % 2)), thick),
                        (0.0, yaw, 0.0), mat))
    return out


def lames(prefix, cy, a, b, n, h, thick, flare, mat, cz=0.0):
    """A fauld: a ring of hanging plates, each turned to face outward and flared
    at the hem, cut NARROWER than its chord so the gaps between the lames are
    real -- a closed ring of plates reads as one carved cone, and a fauld is a
    run of separate lames."""
    steps = n // 2
    out = []
    for i in range(steps + 1):
        psi = 180.0 * i / steps
        s, c = math.sin(math.radians(psi)), math.cos(math.radians(psi))
        px, pz = a * s, cz - b * c
        yaw = math.degrees(math.atan2(b * s, -a * c))
        arc = max(2, math.floor(2 * a * math.sin(math.pi / n) * 0.72))
        name = f"{prefix}{i:02d}" + ("_l" if px > 1e-6 else "")
        out.append(slab(name, (px, cy, pz), (arc, h, thick), (-flare, yaw, 0.0),
                        mat))
    return out


def cone_box(r, squash, thick):
    """The core box that seals a cone at its NARROW end: a box sized for the
    segment's smallest radius can never poke out of the cone, and the plates of
    the segment above overlap the joint, so the gap left inside is never seen."""
    return (max(2, int(round(2 * r - thick)) + 1),
            max(2, int(round(2 * r * squash - thick)) + 1))


def limb(parent, name, joint, spec, dirv="-y", side="", half=False,
         phase0=0.0):
    """A limb as a chain of CONES.

    spec = [(tag, L, r0, r1, rot, n, squash, mat)]: the radii are the cone's at
    the joint and at the far end, so the limb is one continuous taper instead of
    a run of equal-bore tubes. Every segment still gets its own group hinged on
    the joint above it, so a clip bends the limb at real joints.
    """
    segs = chain(parent, name, joint, dirv,
                 [(t, L, *cone_box(min(r0, r1), sq, 3), rot, mat)
                  for t, L, r0, r1, rot, n, sq, mat in spec])
    for i, (seg, (tag, L, r0, r1, rot, n, sq, mat)) in enumerate(zip(segs, spec)):
        put(seg, *taper_tube(seg, r0, r1, 3, mat, f"{name}_{tag}{side}", n=n,
                             phase=phase0 + ((6.0 if n == 4 else 180.0 / n)
                                             if i % 2 else
                                             (0.0 if n != 8 else 22.5)),
                             squash=sq, dirv=dirv, half=half))
    return segs


# --- the horse -------------------------------------------------------------
# Thirteen cross-sections, front to back: (z, centre y, half-width, half-height).
# The brisket tapers out of nothing, the girth behind the elbow is the deepest
# point, the loin is where the back dips, the croup stands high and wide before
# the rump closes. This table IS the horse's body.
BODY = [
    (-30.0, 57.0, 3.0, 3.0),
    (-27.0, 56.5, 8.0, 6.5),
    (-23.0, 56.5, 12.5, 9.5),
    (-18.0, 57.0, 15.0, 11.5),
    (-12.0, 56.5, 16.5, 12.5),
    (-5.0, 56.0, 17.0, 12.5),
    (2.0, 55.0, 16.5, 12.0),
    (9.0, 56.0, 16.0, 11.5),
    (15.0, 56.0, 15.5, 10.5),
    (20.0, 57.0, 15.0, 11.0),
    (25.0, 58.5, 12.0, 9.0),
    (28.0, 58.5, 8.0, 7.0),
    (30.0, 58.0, 4.0, 4.0),
]
BODY_N = 10                        # staves to the ring: big plates, low count
FRONT_LEG = (10.5, 48.0, -13.0)    # the top of the forearm, inside the body
REAR_LEG = (11.5, 48.0, 16.0)
# a quarter off the half grid: the pauldron's plates are pitched slabs, so
# their side faces can sit off the 0.5 grid the arm's boxes live on
SHOULDER = (18.25, 92.0, -11.0)    # the knight's shoulder joint
HUMAN_LIFT = 4.0                   # the human half rides up on the horse's back


def build_body():
    """The horse: the profile as rings of hide, one core box per section, and
    the two pieces of barding -- the peytral over the chest and the crupper over
    the rump -- which close the tapered ends as well."""
    cubes = []
    for i, (z, cy, a, b) in enumerate(BODY):
        k = (0.58, 0.60, 0.62, 0.64)[i % 4]
        dy = (3 * i + 1) % 5 - 2        # neighbours' cores sit units apart
        dz = 3 - i % 2                  # ... and their spans differ too
        # the box is capped by the ring's own bore (a - 2): a core as wide as a
        # section's belly plate puts its flanks in that plate's planes
        hx = min(half(a - 2.0), half(k * a))
        cubes.append(box(f"core{int(z):+03d}", SEAMF,
                         (-hx, int(round(cy - k * b)) - dy, z - dz),
                         (hx, int(round(cy + k * b)) - dy, z + dz)))
    cubes += body_rings("body", BODY, BODY_N, 4.0, BODY_STAVE)
    cubes += barrel("peytral", -32.0, -28.5, 56.5, 11.0, 9.0, 10, 4.0, STEELF,
                    alt=1)
    cubes += barrel("crupper", 27.5, 31.0, 58.0, 12.0, 9.0, 10, 4.0, STEELF,
                    alt=1)
    cubes += [box("chest_boss", STEELF, (-3.0, 54.5, -34.5), (3.0, 60.5, -31.5)),
              box("rump_boss", STEELF, (-3.5, 54.5, 30.5), (3.5, 60.5, 33.5))]
    return group("body", origin=(0, 55, 0), cubes=cubes)


# The horse's legs. The joint heights are the animal's (elbow at the belly line,
# knee at 0.36 of the withers, fetlock at 0.15) and every segment is a cone.
# (tag, length, r at the joint, r at the far end, (rx, rz), plates, squash, mat)
FRONT_LEG_SPEC = [
    ("fore", 11, 6.0, 4.4, (0, 0, 3), 6, 1.00, HORNF),
    ("fore2", 11, 4.4, 3.0, (0, 0, -1), 6, 1.00, HORNF),
    ("knee", 5, 3.3, 2.8, (0, 0, 0), 6, 1.10, HORNF),
    ("cannon", 10, 2.2, 1.8, (0, 0, 0), 6, 1.15, HORNF),
    ("fetlock", 3, 2.5, 2.2, (0, 0, 0), 6, 1.05, HORNF),
    ("pastern", 4, 2.0, 2.4, (7, 0, 0), 6, 1.10, HORNF),
    ("hoof", 3, 2.6, 3.8, (0, 0, 0), 6, 1.45, HORNF),
]
REAR_LEG_SPEC = [
    ("gaskin", 10, 6.8, 5.0, (-8, 0, 3), 6, 1.00, HORNF),
    ("gaskin2", 11, 5.0, 3.2, (-3, 0, 0), 6, 1.00, HORNF),
    ("hock", 6, 3.5, 3.0, (12, 0, -2), 6, 1.20, HORNF),
    ("cannon", 10, 2.2, 1.8, (-6, 0, 0), 6, 1.15, HORNF),
    ("fetlock", 3, 2.5, 2.2, (-2, 0, 0), 6, 1.05, HORNF),
    ("pastern", 4, 2.0, 2.4, (5, 0, 0), 6, 1.10, HORNF),
    ("hoof", 3, 2.6, 3.8, (0, 0, 0), 6, 1.45, HORNF),
]


def build_leg(prefix, joint, spec):
    """A leg: seven cones from the top of the forearm down to the hoof."""
    host = group(f"{prefix}_l", origin=joint, cubes=[])
    segs = limb(host, f"{prefix}_l", joint, spec, side="_l")
    hoof = segs[-1]
    # the sole is placed from the hoof's own joint, so it lands on y = 0 exactly
    # however the chain's rounding came out
    put(hoof, local(hoof, 0, 1.5 - hoof["joint"][1], 0, (10, 3, 14), HORNF,
                    f"{prefix}_sole_l"))
    return host


def build_tail():
    """The tail: four cones falling off the croup, past the hocks, ending in
    hair. It hangs from the top of the rump and sweeps back as it drops -- the
    one line no other part of the animal has."""
    host = group("tail", origin=(0, 66, 22), cubes=[])
    # half a facet round: a cone in a centre group must not put a plate on
    # x = 0, or that plate cannot be shoved off its neighbour's plane
    segs = limb(host, "tail", (0, 66, 22), half=True, phase0=6.0, spec=[
        ("t0", 10, 4.5, 3.6, (-22, 0, 0), 6, 1.0, IRONF),
        ("t1", 9, 3.6, 2.8, (-40, 0, 0), 6, 1.0, IRONF),
        ("t2", 8, 2.8, 2.0, (-58, 0, 0), 6, 1.0, IRONF),
        ("t3", 7, 2.0, 1.2, (-72, 0, 0), 6, 1.0, IRONF),
    ])
    tip = segs[-1]
    put(tip,
        local(tip, 0.0, -9.0, 0.0, (5, 16, 6), IRONF, "hair0"),
        local(tip, 2.5, -7.5, 0.0, (4, 12, 5), IRONF, "hair1_l"),
        local(tip, 0.0, -8.0, 2.5, (6, 12, 5), IRONF, "hair2"),
        )
    return host


# --- the knight ------------------------------------------------------------
# The cuirass climbs: waist, chest, shoulders. A breastplate is widest at the
# chest and pinches at the waist, and that pinch is the whole silhouette.
# The cuirass climbs the way a breastplate does: pinched at the waist, widest
# at the chest, easing back in at the shoulders. Five sections, so the radius
# steps under a unit at a time, and each ring is pitched onto that slope.
CUIRASS = [      # (centre y, half-width, half-depth, band height, plates, cz)
    (68.0, 12.5, 9.0, 8, 12, -7.0),
    (74.0, 14.5, 10.5, 6, 14, -9.0),
    (80.0, 16.5, 12.0, 6, 12, -10.0),
    (86.0, 17.0, 12.5, 6, 14, -11.5),
    (91.0, 16.0, 12.0, 6, 12, -12.0),
]
HELM = [         # the skull, domed: (centre y, half-width, half-depth, height)
    (98.0, 8.5, 8.0, 7.0),
    (103.0, 8.8, 8.2, 6.0),
    (107.0, 7.0, 6.5, 5.0),
    (110.5, 4.5, 4.2, 4.0),
]
HELM_CZ = -12.0


def build_torso():
    """Cuirass, keel, belt, fauld: the knight's own body."""
    cubes = [box("torso_core", SEAMF, (-7, 68, -14), (7, 92, -5))]
    ys = [c[0] for c in CUIRASS]
    for i, (cy, a, b, h, n, cz) in enumerate(CUIRASS):
        lo, hi = CUIRASS[max(0, i - 1)], CUIRASS[min(len(CUIRASS) - 1, i + 1)]
        da = (hi[1] - lo[1]) / max(1e-6, hi[0] - lo[0])
        db = (hi[2] - lo[2]) / max(1e-6, hi[0] - lo[0])
        tilt = math.degrees(math.atan(0.5 * (da + db)))
        cubes += ring(f"cuirass{i}", cy, a, b, n, h, 5.0, STEEL_PLATE, cz=cz,
                      tilt=tilt, alt=i)
    cubes += [
        # the keel: every breastplate has one, and it is what stops the chest
        # reading as a barrel with a belt on
        slab("keel", (0, 84, CUIRASS[2][5] - 14.0), (5, 15, 4), (-6, 0, 0),
             STEELF),
    ]
    cubes += lames("fauld", 70.0, 15.0, 11.5, 10, 14.0, 3.0, 20.0, STEEL_PLATE,
                   cz=CUIRASS[0][5])
    cubes += ring("belt", 76.25, 16.0, 12.5, 12, 5.0, 3.0, LTHF, alt=1,
                  cz=CUIRASS[0][5])
    return group("torso", origin=(0, 76, CUIRASS[0][5]), cubes=cubes)


def build_head():
    """Gorget over a mail collar, the helm, and the only light on the figure:
    the visor's slit."""
    cz = HELM_CZ
    cubes = ring("gorget", 92.0, 15.5, 12.5, 12, 6.0, 3.0, STEEL_PLATE, cz=cz)
    cubes += ring("mail", 95.0, 11.0, 9.5, 12, 6.0, 3.0, IRONF, cz=cz)
    for i, (cy, a, b, h) in enumerate(HELM):
        # the plate counts differ ring to ring: two rings sharing a count put
        # their plates' tangential end faces in the same planes
        lo, hi = HELM[max(0, i - 1)], HELM[min(len(HELM) - 1, i + 1)]
        da = (hi[1] - lo[1]) / max(1e-6, hi[0] - lo[0])
        db = (hi[2] - lo[2]) / max(1e-6, hi[0] - lo[0])
        tilt = math.degrees(math.atan(0.5 * (da + db)))
        cubes += ring(f"helm{i}", cy, a, b, (12, 14, 12, 10)[i], h, 4.0,
                      STEEL_PLATE, cz=cz, tilt=tilt, alt=i)
    cubes += [slab("helmcap", (0, 112.5, cz), (9, 2, 8), (0, 0, 0), STEELF)]
    # the visor: a band of plates over the helm's face, split by the slit the
    # light comes out of. Authored as the FRONT of two rings, so its plates
    # follow the helm's curve instead of lying across it as planks
    cubes += front_arc("brow", 106.0, 5, 10.4, 9.8, 14, 2, 5.0, STEELF, cz=cz)
    cubes += front_arc("cheek", 98.0, 5, 10.4, 9.8, 14, 2, 5.0, STEELF, cz=cz)
    cubes += front_arc("eyeslit", 102.0, 4, 9.4, 8.8, 10, 2, 3.0, GLOWF, cz=cz)
    return group("head", origin=(0, 96, cz), cubes=cubes)


def build_shoulder():
    """A pauldron of three lames, each covering a DIFFERENT band of the shoulder
    -- they stack down the arm like plates, rather than nesting shells over the
    same area (nesting is the "叠" the user has thrown out twice)."""
    host = group("shoulder_l", origin=SHOULDER, cubes=[])
    for name, cy, r, w, a0, a1 in (("pcap0", 92.0, 9.0, 13, -46, 88),
                                   ("pcap1", 86.0, 9.6, 11, -34, 96),
                                   ("pcap2", 79.5, 10.2, 15, -24, 104)):
        # the lame widths differ so that no two of them put their side faces in
        # one plane: the lames overlap down the shoulder by design
        host["cubes"] += dome(name, (SHOULDER[0], cy, SHOULDER[2]), r, 4,
                              a0, a1, w, 4, STEEL_DOME)
    return host


def build_arm(prefix, sign, angles):
    """An arm: upper, elbow, forearm, hand -- four cones and the gauntlet's
    plate. `angles` are the upper arm's, the forearm's and the hand's rest
    rotations; the right hand is authored flat so the haft can be driven
    straight through it."""
    joint = (sign * SHOULDER[0], SHOULDER[1], SHOULDER[2])
    host = group(f"arm{prefix}", origin=joint, cubes=[])
    up, fore, hand = angles
    spec = [
        ("upper", 15, 4.6, 3.4, up, 6, 1.0, STEELF),
        ("elbow", 4, 3.6, 3.2, ((up[0] + fore[0]) / 2.0, 0, 0), 6, 1.1, STEELF),
        ("fore", 13, 3.2, 2.4, fore, 6, 1.0, STEELF),
        ("hand", 7, 2.9, 3.3, hand, 6, 1.1, STEELF),
    ]
    segs = limb(host, f"arm{prefix}", joint, spec, side=prefix)
    put(segs[-1], local(segs[-1], 0, -4, sign * -4.0, (7, 6, 4), STEELF,
                        f"arm{prefix}_fingers"))
    return host, segs[-1]


def build_trident(grip):
    """The trident, authored around the fist the arm actually ended up at.

    Every piece is a tube of plates. The haft is a six-plate column that tapers
    from the ferrule at the butt up to the socket; the head is a socket cone,
    a centre blade and two side prongs. Each blade segment is a FOUR-plate
    diamond -- n=4 on a squashed radius gives two bevels a side, so a prong has
    a ridge and an edge instead of being a square bar -- and the taper down to
    r=0.4 ends it in a point. The side prongs leave the socket, curve out, then
    crank back toward the centre blade, which runs longest: that is a trident's
    head, and it is drawn by the headings of its plates, not by stacked boxes.
    """
    gx, gz = grip[0], grip[2]
    # the cones start a little above the model's floor and an iron ferrule
    # takes the ground: a cone's lowest plate hangs a quarter unit below its
    # own joint, so a haft that started at the floor would stand in it
    y0 = -HUMAN_LIFT + 1.5
    host = group("trident", origin=(gx, grip[1], gz), cubes=[
        box("tri_ferrule", IRONF, (gx - 2, -HUMAN_LIFT, gz - 2),
            (gx + 2, -HUMAN_LIFT + 3, gz + 2))])
    haft = group("tri_haft", origin=(gx, y0, gz), cubes=[])
    hsegs = chain(haft, "tri_haft", (gx, y0, gz), "+y", [
        ("butt", 6, 3, 3, (0, 0, 0), IRONF),
        ("lo", 39, 3, 3, (0, 0, 0), STEELF),
        ("grip", 21, 4, 4, (0, 0, 0), LTHF),
        ("hi", 31, 3, 3, (0, 0, 0), STEELF),
        ("socket", 8, 4, 5, (0, 0, 0), STEELF),
    ])
    for i, (seg, (r0, r1), mat) in enumerate(zip(hsegs, ((1.7, 1.6), (1.4, 1.3),
                                                         (1.7, 1.7), (1.3, 1.2),
                                                         (2.4, 3.1)),
                                                 (IRONF, STEELF, LTHF, STEELF,
                                                  STEELF))):
        # each cone turns its plate seams half a facet off the one below
        put(seg, *taper_tube(seg, r0, r1, 2, mat, f"tri_{seg['tag']}", n=6,
                             phase=30.0 if i % 2 else 0.0, dirv="+y"))
    host["children"].append(haft)
    top = y0 + 6 + 39 + 22 + 31 + 8
    blade = group("tri_blade", origin=(gx, top - 4.0, gz), cubes=[])
    bsegs = chain(blade, "tri_blade", (gx, top - 4.0, gz), "+y", [
        ("b0", 8, 2, 2, (0, 0, 0), STEELF),
        ("b1", 8, 2, 2, (0, 0, 0), STEELF),
        ("b2", 7, 2, 2, (0, 0, 0), STEELF),
    ])
    for i, (seg, (r0, r1)) in enumerate(zip(bsegs, ((2.8, 2.0), (2.0, 1.2),
                                                   (1.2, 0.4)))):
        put(seg, *taper_tube(seg, r0, r1, 2, STEELF, f"tri_{seg['tag']}", n=4,
                             phase=(0.0, 8.0, 16.0)[i], squash=0.42,
                             dirv="+y"))
    host["children"].append(blade)
    for s, nm in ((1, "triprong0"), (-1, "triprong1")):
        # half a unit forward of the blade: chain() rounds every joint to the
        # 0.5 grid, so a quarter offset would be rounded away and the two
        # cones' core boxes would share their front and back planes
        dzp = 0.5 if s > 0 else 1.0     # the twins differ by half a unit
        prong = group(nm, origin=(gx + s * 3.2, top - 5.0, gz + dzp), cubes=[])
        psegs = chain(prong, nm, (gx + s * 3.2, top - 5.0, gz + dzp), "+y", [
            ("a", 9, 2, 2, (0, 0, s * 13), STEELF),
            ("b", 8, 2, 2, (0, 0, s * 4), STEELF),
            ("c", 7, 2, 2, (0, 0, s * -5), STEELF),
        ])
        for i, (seg, (r0, r1)) in enumerate(zip(psegs, ((2.4, 1.7), (1.7, 1.0),
                                                       (1.0, 0.4)))):
            put(seg, *taper_tube(seg, r0, r1, 2, STEELF, f"{nm}_{seg['tag']}",
                                 n=4, phase=(4.0, 12.0, 20.0)[i], squash=0.44,
                                 dirv="+y"))
        host["children"].append(prong)
    return host


# --- assembly --------------------------------------------------------------
def assemble() -> dict:
    body = add_mirrors(build_body())
    torso = add_mirrors(build_torso())
    torso["children"] += [add_mirrors(build_head())]
    half = side_tree("_l", build_shoulder())
    torso["children"] += [half, side_tree("_r", half)]
    arm_l, _ = build_arm("_l", 1, ((12, 0, 14), (6, 0, 8), (2, 0, 4)))
    torso["children"] += [arm_l]
    arm_r, hand_r = build_arm("_r", -1, ((34, 0, -20), (14, 0, -4), (0, 0, 0)))
    grip = (hand_r["joint"][0], hand_r["joint"][1] - hand_r["L"] / 2.0,
            hand_r["joint"][2])
    hand_r["group"]["children"].append(build_trident(grip))
    torso["children"] += [arm_r]
    body["children"] += [lift(torso, HUMAN_LIFT)]
    body["children"] += [add_mirrors(build_tail())]
    for prefix, joint, spec in (("legf", FRONT_LEG, FRONT_LEG_SPEC),
                                ("legb", REAR_LEG, REAR_LEG_SPEC)):
        half = side_tree("_l", build_leg(prefix, joint, spec))
        body["children"] += [half, side_tree("_r", half)]
    return group(MODEL_NAME, children=[body], origin=(0, 0, 0))


PREVIEWS = [
    ("", 205.0, 10.0, 250.0, (0.0, 58.0, 0.0)),
    ("_front", 180.0, 6.0, 250.0, (0.0, 58.0, 0.0)),
    ("_side", 270.0, 6.0, 250.0, (0.0, 58.0, 0.0)),
    ("_back", 0.0, 10.0, 250.0, (0.0, 58.0, 0.0)),
    ("_torso", 202.0, 8.0, 110.0, (0.0, 88.0, -8.0)),
    ("_head", 196.0, 6.0, 62.0, (0.0, 104.0, -12.0)),
    ("_trident", 236.0, 10.0, 130.0, (-23.0, 118.0, -14.0)),
    ("_legs", 214.0, 8.0, 120.0, (0.0, 26.0, 2.0)),
]


# --- self checks -----------------------------------------------------------
def check_ground(tree, tol=0.25):
    """Nothing may hang below y = 0 -- the hooves stand on it, and the trident's
    ferrule is planted on it."""
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

    asym = check_symmetric(tree, skip=("/trident/",))
    if asym:
        for path, a, b in asym[:10]:
            print(f"  asymmetric centre part: {path} x {a}..{b}")
        raise SystemExit(f"{len(asym)} centre parts not straddling x = 0")

    fights = coplanar_visible(tree)
    if fights:
        for pi, pj, axis, tag, coord in fights[:20]:
            print(f"  z-fight risk: {pi} / {pj} on {axis}={coord:.2f} ({tag})")
        raise SystemExit(f"{len(fights)} visible coplanar overlaps")

    world = zfight_world(tree)
    if world:
        for pi, pj, ta, tb, nrm, coord in world[:20]:
            print(f"  world z-fight: {pi.split('/')[-1]}:{ta} / "
                  f"{pj.split('/')[-1]}:{tb}  "
                  f"n={tuple(round(float(v), 2) for v in nrm)} d={coord:.2f}")
        raise SystemExit(f"{len(world)} coincident same-facing world faces")

    stretched = stretch_report(tree)
    if stretched:
        agg: dict = {}
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
                            sizes=(512, 640, 768, 1024, 1280, 1536))
    for idx, atlas in atlases.items():
        unpainted = check_painted(atlas)
        if unpainted:
            raise SystemExit(f"texture {idx} rects left unpainted: {unpainted[:8]}")
    images = {idx: atlas.image() for idx, atlas in atlases.items()}
    for idx, name in ((TEX_BODY, f"{MODEL_NAME}.png"),
                      (TEX_GLOW, f"{MODEL_NAME}_glow.png")):
        if idx in images:
            images[idx].save(os.path.join(OUT_DIR, name))

    model_path = os.path.join(OUT_DIR, f"{MODEL_NAME}.bbmodel")
    n = write_model(model_path, tree, atlases, images, MODEL_NAME,
                    GLOW_MATERIALS, animations=[])
    used = {idx: sum(w * h for _x, _y, w, h in a.rects.values())
            for idx, a in atlases.items()}
    print(f"{model_path}  ({n} cubes, res {atlases[TEX_BODY].size // S}, "
          f"body {atlases[TEX_BODY].size}px {len(atlases[TEX_BODY].rects)} rects "
          f"{used[TEX_BODY]}px, glow {len(atlases[TEX_GLOW].rects)} rects "
          f"{used[TEX_GLOW]}px)")

    if not args.no_preview:
        render_previews(model_path, OUT_DIR, MODEL_NAME, PREVIEWS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
