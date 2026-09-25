"""Export the muscle creeper to a Bedrock geometry file (.geo.json).

    python tools/export_bedrock.py

Writes ../muscle_creeper.geo.json (bones + cubes + per-face uv), ready to drop
into a Bedrock resource pack as models/entity/muscle_creeper.geo.json with the
texture at textures/entity/muscle_creeper.png.

The conversion rules are Blockbench's own (resources/app.asar -> sourcemap ->
js/formats/bedrock/bedrock.js, functions compileCube/compileGroup), so this
file matches what File > Export > Bedrock Entity would write:

* x axis mirrors: bedrock_origin.x = -(bb_from.x + size.x), bone pivot.x = -x
* north/south/east/west faces: uv = [u1, v1], uv_size = [w, h]
* up/down faces are written flipped (the codec's own convention):
  uv = [u2, v2], uv_size = [-w, -h]
* format_version 1.12.0
"""
from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(os.path.dirname(HERE), "muscle_creeper")
os.makedirs(OUT_DIR, exist_ok=True)
MODEL = os.path.join(OUT_DIR, "muscle_creeper.bbmodel")
OUT = os.path.join(OUT_DIR, "muscle_creeper.geo.json")


def dezero(value):
    """json would write x-mirrored zeros as -0.0; normalise them."""
    return 0.0 if value == 0 else value


def convert_cube(el: dict) -> dict:
    fx, fy, fz = el["from"]
    tx, ty, tz = el["to"]
    size = [tx - fx, ty - fy, tz - fz]
    cube = {"origin": [dezero(-(fx + size[0])), dezero(fy), dezero(fz)], "size": size}
    uv = {}
    for face, data in (el.get("faces") or {}).items():
        u1, v1, u2, v2 = data["uv"]
        w, h = u2 - u1, v2 - v1
        if face in ("up", "down"):
            uv[face] = {"uv": [u2, v2], "uv_size": [-w, -h]}
        else:
            uv[face] = {"uv": [u1, v1], "uv_size": [w, h]}
    cube["uv"] = uv
    return cube


def walk(node: dict, parent: str | None, bones: list, used: set, elements: dict,
         emit_self: bool = True) -> None:
    if node.get("type") == "cube" or not isinstance(node, dict):
        return
    cubes = [convert_cube(elements[c]) for c in node.get("children", [])
             if not isinstance(c, dict) and elements[c].get("type") == "cube"]
    kids = [c for c in node.get("children", []) if isinstance(c, dict)]
    if (cubes or kids) and emit_self:
        bone = {"name": node["name"]}
        if parent and parent in used:
            bone["parent"] = parent
        bone["pivot"] = [dezero(-node["origin"][0]), dezero(node["origin"][1]),
                         dezero(node["origin"][2])]
        if cubes:
            bone["cubes"] = cubes
        bones.append(bone)
        used.add(node["name"])
        parent = node["name"]
    for kid in kids:
        walk(kid, parent, bones, used, elements)


def main() -> int:
    doc = json.load(open(MODEL, encoding="utf-8"))
    elements = {el["uuid"]: el for el in doc["elements"]}

    bones: list = []
    used: set = set()
    for node in doc["outliner"]:
        # the free-format project wraps everything in one container group; that
        # group is not a real bone, so don't emit it (Blockbench's bedrock format
        # takes its top-level groups to be the bones)
        walk(node, None, bones, used, elements, emit_self=False)

    geo = {
        "format_version": "1.12.0",
        "minecraft:geometry": [{
            "description": {
                "identifier": "geometry.muscle_creeper",
                "texture_width": 64,
                "texture_height": 64,
                "visible_bounds_width": 2,
                "visible_bounds_height": 2,
                "visible_bounds_offset": [0, 1, 0],
            },
            "bones": bones,
        }],
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(geo, fh, indent=2)

    n_cubes = sum(len(b.get("cubes", [])) for b in bones)
    print(f"{OUT}  ({len(bones)} bones, {n_cubes} cubes)")

    # --- self check -----------------------------------------------------------
    # For a cube centred on x the mirror leaves origin.x unchanged (as with the
    # vanilla bedrock creeper's own head cube at [-4, 18, -4]); off-centre cubes
    # and pivots do flip sign.
    assert n_cubes == 11 and len(bones) == 8, (len(bones), n_cubes)
    chest = next(c for b in bones if b["name"] == "body" for c in b["cubes"]
                 if c["size"] == [14, 9, 6])
    assert chest["origin"] == [-7, 13, -3], chest["origin"]
    head_bone = next(b for b in bones if b["name"] == "head")
    assert head_bone["parent"] == "body"
    head_cube = head_bone["cubes"][0]
    assert head_cube["origin"] == [-4, 22, -4] and head_cube["size"] == [8, 8, 8]
    assert head_cube["uv"]["north"] == {"uv": [8, 8], "uv_size": [8, 8]}
    assert head_cube["uv"]["up"]["uv_size"][0] < 0 and head_cube["uv"]["up"]["uv"][0] > 8
    arms = {b["name"]: b["pivot"][0] for b in bones if "arm" in b["name"]}
    assert arms == {"right_arm": 10.0, "left_arm": -10.0}, arms
    legs = {b["name"]: b["pivot"] for b in bones if "leg" in b["name"]}
    assert legs["right_front_leg"][0] == 3.5 and legs["left_hind_leg"][2] == 4.5
    print("self check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
