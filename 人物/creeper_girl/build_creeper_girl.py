"""苦力怕娘：以「[无动画共享]映素2.5代-女性标准体型v3.7」为基底的角色换装。

    python 人物/creeper_girl/build_creeper_girl.py

与 enderman_girl 同一套换装机制（同基底、同自检），角色的推导从这里开始：

* 发型——苦力怕是圆脑袋：摘掉两组长散发（SideDownHairC / SideHairA），
  后脑两片大后发收短（丸子头那次量好的坐标，同一基底同一批方块），
  发色按亮度重映射到苦力怕绿色阶（暗绿→亮绿，保留原明暗结构）。摘 DemonHornA。
* 瞳——虹膜/瞳孔（Eyes 组里名为 "Eye" 的元素的 uv 区）重映射到深黑绿。
* 服装——绿色上衣（躯干九块外扩成壳，胸口一整块斜板盖住两片胸板的共面缝），
  上衣背面一整张苦力怕脸印花（题材本体就是那张脸：一大块，不碎）；
  深绿百褶裙（24 片，半径按「身体+外壳」逐高度反推，顶高/摆长/厚度三重交错）。
  短袖（上臂段），小臂露肤色。
* 腿——不另立几何：基底腿方块自己的贴图区按高度重画——膝下绿白横条纹
  （条纹是 v 的函数，绕腿连续），脚背两行深色当鞋。
* 点缀零新增：识别靠配色、印花和条纹。

贴图全部画进基底贴图右侧空白（x >= 276），全模型只留 texture 0。
自检与 enderman_girl 相同（uv 比例 / 贴图引用 / 透明像素 / 裙片净空 /
共面新增 / zfight 新增 / 脚贴地），应全绿。
"""
from __future__ import annotations

import base64
import copy
import hashlib
import io
import json
import math
import os
import sys
import uuid

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.dont_write_bytecode = True
ROOT = HERE
while not os.path.isfile(os.path.join(ROOT, "tools", "bbmodel_kit.py")):
    parent = os.path.dirname(ROOT)
    if parent == ROOT:
        raise SystemExit(f"找不到仓库根（含 tools/bbmodel_kit.py 的目录）：{HERE}")
    ROOT = parent
sys.path.insert(0, os.path.join(ROOT, "tools"))
from bbmodel_kit import V, rot_ZYX, coplanar_conflicts, zfight_world  # noqa: E402

BASE = os.path.join(ROOT, "人工建模参考", "人物",
                    "[无动画共享]映素2.5代-女性标准体型v3.7.bbmodel")
MODEL_NAME = "creeper_girl"

# --- 调色：一种绿，明暗分层；深绿给裙，亮绿给上衣，无橙，无新增发光 ----------
RAMP_HAIR = ((0.00, (26, 56, 30)), (0.40, (52, 110, 56)), (0.75, (78, 148, 76)),
             (1.00, (112, 178, 96)))
RAMP_IRIS = ((0.00, (14, 26, 18)), (0.60, (38, 70, 42)), (1.00, (88, 138, 90)))
TOP = (94, 154, 86)          # 上衣主色
TOP_DARK = (64, 116, 64)     # 领口/袖口/褶谷
TOP_LIGHT = (124, 182, 108)  # 受光
SKIRT = (42, 86, 46)         # 裙主色（比上衣深一档，主色/点缀分得开）
SKIRT_DARK = (30, 64, 36)
FACE_PRINT = (24, 46, 26)    # 背后印花（苦力怕脸）
SOCK_W = (236, 242, 230)     # 条纹袜白
SOCK_G = (96, 156, 88)       # 条纹袜绿
SHOE = (28, 34, 28)
STRIPES_FROM = 8.0           # 膝下（y 8）开始条纹
STRIPES_PERIOD = 2.0         # 一白一绿 2 单位

S = 2
D_SHOULDER = 0.22
D_CHEST = 0.16
D_LOW = 0.03
BUST_D = 0.16
PROUD = 0.05
SKIRT_TOP = 22.95
SKIRT_TOP_ALT = 0.06
WAIST_BAND_TOP = 22.60
SKIRT_HEM = 12.90
SKIRT_HEM_ALT = 0.35
PLEAT_T = 0.16
PLEAT_T_ALT = 0.03
PLEAT_INSET = 0.02
GAP_TOP = 0.18
GAP_BODY = 0.22
MIN_TOP_R = 2.95
N_PLEAT = 24
FLARE = 1.35
COLLAR = dict(half=1.95, depth=2.02, y0=28.55, y1=29.55)   # 圆领，比末影娘矮
SLEEVE_UP = 0.25

TORSO_UUIDS = (
    ("83be27fb-9e1d-2c86-d65b-c8f7a6f6a7b5", D_SHOULDER, "Top_Shoulder_L"),
    ("237cc73b-122a-4f04-bb98-3fe3b931c9d5", D_SHOULDER, "Top_Shoulder_R"),
    ("d28fe618-b6f4-fef7-6fd8-d070ed0240cc", D_CHEST, "Top_Chest"),
    ("1413ec5c-4324-93eb-6cf1-958c8d653d84", D_SHOULDER + 0.015, "Top_Spine"),
    ("5739873c-9f1c-e9a2-2a2a-3b636d27977a", BUST_D, "Top_Bust_L"),
    ("0ebf689c-e0b5-6abf-5740-db7a4a02054b", BUST_D + 0.02, "Top_Bust_R"),  # 错缝防共面
    ("6af77825-44f2-2d7d-bf10-b3e7fdf2e071", D_LOW, "Top_Waist"),
    ("fd9d301e-c1d9-e45f-baf2-8ca1794d5b56", D_LOW, "Top_Belly"),
    ("399e3521-472f-caaf-6834-93233d967903", D_LOW, "Top_Butt"),
)
ARM_UUIDS = {"L": "e84da2f9-6c5f-5950-2a48-c8ff88d923ef",
             "R": "0ccd4641-feb8-0af7-6768-fdde6ca87af4"}
HAIR_GROUPS = ("HairFemaleH_Matching", "SideDownHairC", "SideHairA")

DROP_GROUPS = ("DemonHornA",)   # 只摘角；侧发链摘了会露头皮（试过，否决）
LEG_CUBES = {"DaTui": 9.0, "XiaoTui": 0.85, "Jio": -0.09}   # 名字 -> 方块最低 y
FACES = ("north", "east", "south", "west", "up", "down")


def sha_seed(key) -> np.random.RandomState:
    h = hashlib.sha256(str(key).encode("utf-8")).hexdigest()[:8]
    return np.random.RandomState(int(h, 16))


def ramp_lookup(stops, t):
    t = min(1.0, max(0.0, float(t)))
    for i in range(len(stops) - 1):
        t0, c0 = stops[i]
        t1, c1 = stops[i + 1]
        if t <= t1:
            k = (t - t0) / max(1e-6, t1 - t0)
            return tuple(c0[j] + (c1[j] - c0[j]) * k for j in range(3))
    return stops[-1][1]


# ===========================================================================
# 贴图
# ===========================================================================
class Atlas:
    def __init__(self, base_img, x0):
        self.size = base_img.size[0]
        self.cv = np.array(base_img, np.uint8).copy()
        self.x0 = x0
        self.rects = {}
        self.mask = np.zeros((self.size, self.size), bool)
        self._x, self._y, self._row_h = x0, 0, 0

    def rect(self, key, w, h, min_size=4):
        w = max(min_size, int(round(w)))
        h = max(min_size, int(round(h)))
        if key in self.rects:
            return self.rects[key]
        if self._x + w > self.size:
            self._x, self._y, self._row_h = self.x0, self._y + self._row_h + 1, 0
        if self._y + h > self.size:
            raise RuntimeError(f"atlas 装不下 {key}")
        r = (self._x, self._y, w, h)
        self.rects[key] = r
        self._x += w + 1
        self._row_h = max(self._row_h, h)
        mat0 = key[0] if isinstance(key[0], str) else key[0][0]
        PAINTERS[mat0](self.cv, r, key)
        self.cv[r[1]:r[1] + h, r[0]:r[0] + w, 3] = 255
        e0x, e0y = max(self.x0, r[0] - 1), max(0, r[1] - 1)
        e1x, e1y = min(self.size, r[0] + w + 1), min(self.size, r[1] + h + 1)
        ys = np.clip(np.arange(e0y, e1y) - r[1], 0, h - 1)
        xs = np.clip(np.arange(e0x, e1x) - r[0], 0, w - 1)
        ring = self.cv[r[1] + ys][:, r[0] + xs].copy()
        self.cv[e0y:e1y, e0x:e1x] = ring
        self.cv[e0y:e1y, e0x:e1x, 3] = 255
        self.mask[e0y:e1y, e0x:e1x] = True
        return r

    def extend_edges(self, rounds=16):
        cv, mask = self.cv, self.mask
        for _ in range(rounds):
            for (x, y, w, h) in self.rects.values():
                sub = cv[y:y + h, x:x + w]
                if x - 1 >= self.x0:
                    free = ~mask[y:y + h, x - 1]
                    cv[y:y + h, x - 1][free] = sub[:, 0][free]
                    mask[y:y + h, x - 1][free] = True
                if x + w < self.size:
                    free = ~mask[y:y + h, x + w]
                    cv[y:y + h, x + w][free] = sub[:, -1][free]
                    mask[y:y + h, x + w][free] = True
                if y > 0:
                    free = ~mask[y - 1, x:x + w]
                    cv[y - 1, x:x + w][free] = sub[0, :][free]
                    mask[y - 1, x:x + w][free] = True
                if y + h < self.size:
                    free = ~mask[y + h, x:x + w]
                    cv[y + h, x:x + w][free] = sub[-1, :][free]
                    mask[y + h, x:x + w][free] = True

    def image(self):
        return Image.fromarray(self.cv, "RGBA")


def paint_top(cv, r, key):
    x, y, w, h = r
    rng = sha_seed(("top", key[1], key[2]))
    n = (rng.uniform(-3.5, 3.5, (h, w, 1))
         + (np.indices((h, w)).sum(0) % 2)[..., None] * 1.8 - 0.9)
    col = np.array(TOP, float)[None, None, :] + n
    cv[y:y + h, x:x + w, :3] = np.clip(col, 0, 255).astype(np.uint8)


def paint_top_dark(cv, r, key):
    x, y, w, h = r
    rng = sha_seed(("topd", key[1], key[2]))
    n = rng.uniform(-3.0, 3.0, (h, w, 1))
    col = np.array(TOP_DARK, float)[None, None, :] + n
    cv[y:y + h, x:x + w, :3] = np.clip(col, 0, 255).astype(np.uint8)


def paint_creeper_face(cv, r, key):
    """胸口整板的正面：平铺绿 + 一整张苦力怕脸印花（题材本体，一大块不碎）。"""
    x, y, w, h = r
    paint_top(cv, r, key)
    px = np.array(FACE_PRINT, np.uint8)
    def block(a0, b0, a1, b1):
        x0, y0 = int(x + a0 * w), int(y + b0 * h)
        x1, y1 = int(x + a1 * w), int(y + b1 * h)
        cv[y0:y1, x0:x1, :3] = px
    block(0.10, 0.18, 0.32, 0.50)      # 左眼
    block(0.68, 0.18, 0.90, 0.50)      # 右眼
    block(0.42, 0.42, 0.58, 0.92)      # 嘴中柱
    block(0.28, 0.55, 0.44, 0.78)      # 嘴左撇
    block(0.56, 0.55, 0.72, 0.78)      # 嘴右撇


def paint_pleat(cv, r, key):
    x, y, w, h = r
    shade = PLEAT_SHADE.get(key[1], 0.0)
    base = np.array(SKIRT, float) + shade * 255.0 * 0.16
    band = max(2, int(round(1.1 * S)))
    for j in range(h):
        for i in range(w):
            col = base + (-5 + 9 * (i / max(1, w - 1)))
            if j < band:
                col = np.array(SKIRT_DARK, float) + (20 if j < 2 else 0)
            elif j < band + 2:
                col = np.array(SKIRT_DARK, float) + 5
            if i < 2:
                col = col - 9
            if j >= h - 3:
                col = col - (15 if j >= h - 1 else 8)
            cv[y + j, x + i, :3] = np.clip(col + sha_seed(("pp", key, i, j)).uniform(-2, 2),
                                           0, 255)


PAINTERS = {"top": paint_top, "topdark": paint_top_dark,
            "creeperface": paint_creeper_face, "pleat": paint_pleat}
PLEAT_SHADE = {}
DETAIL_SCALES = {}      # (方块名, 面) -> 放大倍数：uv 检查用


# ===========================================================================
# 几何与骨架（与 enderman_girl 同一套闸门与换装机制）
# ===========================================================================
def box(name, frm, to, origin=None, rotation=None, color=0):
    lo = [round(min(a, b), 4) for a, b in zip(frm, to)]
    hi = [round(max(a, b), 4) for a, b in zip(frm, to)]
    c = {"name": name, "from": lo, "to": hi, "color": color,
         "origin": [round(v, 4) for v in (origin if origin is not None
                                          else [(a + b) / 2 for a, b in zip(lo, hi)])]}
    if rotation and any(abs(a) > 1e-9 for a in rotation):
        c["rotation"] = [round(v, 4) for v in rotation]
    return c


def shell(el, delta, name):
    c = {"name": name,
         "from": [round(v - delta, 4) for v in el["from"]],
         "to": [round(v + delta, 4) for v in el["to"]],
         "origin": [round(v, 4) for v in el.get("origin", [0, 0, 0])],
         "color": 1}
    if el.get("rotation"):
        c["rotation"] = [round(v, 4) for v in el["rotation"]]
    return c


def face_size(face, frm, to):
    dx, dy, dz = to[0] - frm[0], to[1] - frm[1], to[2] - frm[2]
    return {"north": (dx, dy), "south": (dx, dy), "east": (dz, dy),
            "west": (dz, dy), "up": (dx, dz), "down": (dx, dz)}[face]


def group_elements(outliner, names):
    hits = {}

    def grab(node, ids):
        for c in node.get("children", []):
            if isinstance(c, str):
                ids.append(c)
            elif isinstance(c, dict):
                grab(c, ids)

    def walk(nodes):
        for ch in nodes:
            if isinstance(ch, dict):
                if ch.get("name") in names:
                    ids = []
                    grab(ch, ids)
                    hits.setdefault(ch["name"], []).extend(ids)
                walk(ch.get("children", []))
    walk(outliner)
    return hits


def drop_groups(outliner, names, removed=None):
    if removed is None:
        removed = set()

    def grab(node):
        for c in node.get("children", []):
            if isinstance(c, str):
                removed.add(c)
            elif isinstance(c, dict):
                grab(c)

    i = 0
    while i < len(outliner):
        ch = outliner[i]
        if isinstance(ch, dict) and ch.get("name") in names:
            grab(ch)
            outliner.pop(i)
            continue
        if isinstance(ch, dict):
            drop_groups(ch.get("children", []), names, removed)
        i += 1
    return removed


def insert_children(outliner, group_name, nodes):
    for ch in outliner:
        if isinstance(ch, dict):
            if ch.get("name") == group_name:
                ch.setdefault("children", [])
                ch["children"].extend(nodes)
                return True
            if insert_children(ch.get("children", []), group_name, nodes):
                return True
    return False


def to_tree(outliner, elements):
    els = {e["uuid"]: e for e in elements}

    def conv(nodes):
        cubes, children = [], []
        for ch in nodes:
            if isinstance(ch, str):
                if ch in els:
                    cubes.append(els[ch])
            elif ch.get("uuid") in els:
                cubes.append(els[ch["uuid"]])
            else:
                sc, cc = conv(ch.get("children", []))
                children.append({"name": ch.get("name", "?"),
                                 "origin": ch.get("origin", [0, 0, 0]),
                                 "rotation": ch.get("rotation"),
                                 "cubes": sc, "children": cc})
        return cubes, children
    cubes, children = conv(outliner)
    return {"name": "Root", "origin": [0, 0, 0], "rotation": [0, 0, 0],
            "cubes": cubes, "children": children}


def pruned_tree(tree, keep_uuids):
    def walk(node):
        cubes = [c for c in node.get("cubes", []) if c.get("uuid") in keep_uuids]
        children = [walk(ch) for ch in node.get("children", [])]
        children = [ch for ch in children if ch["cubes"] or ch["children"]]
        return {"name": node.get("name", "?"), "origin": node.get("origin", [0, 0, 0]),
                "rotation": node.get("rotation"), "cubes": cubes, "children": children}
    return walk(tree)


def walk_all(node, R=None, t=None):
    if R is None:
        R, t = np.eye(3), np.zeros(3)
    local = node.get("rotation")
    R_l = rot_ZYX(*local) if local else np.eye(3)
    o = V(*node["origin"])
    R_n, t_n = R @ R_l, t + R @ ((np.eye(3) - R_l) @ o)
    for c in node.get("cubes", []):
        cl = c.get("rotation")
        Rc = R_n @ rot_ZYX(*cl) if cl else R_n
        oc = V(*c.get("origin", (0, 0, 0)))
        tc = t_n + R_n @ ((np.eye(3) - rot_ZYX(*cl) if cl else np.eye(3)) @ oc)
        yield f"{node.get('name','?')}/{c['name']}", c, Rc, tc
    for ch in node.get("children", []):
        yield from walk_all(ch, R_n, t_n)


def body_slices(tree, n=10, skip_uuids=()):
    body, arms = [], []

    def rec(node, R, t, in_arms):
        local = node.get("rotation")
        R_l = rot_ZYX(*local) if local else np.eye(3)
        o = V(*node["origin"])
        R_n, t_n = R @ R_l, t + R @ ((np.eye(3) - R_l) @ o)
        here = in_arms or node.get("name") in ("Arms", "LeftArm", "RightArm",
                                               "LeftForeArm", "RightForeArm",
                                               "LeftHand", "RightHand")
        for c in node.get("cubes", []):
            if c.get("uuid") in skip_uuids:
                continue
            cl = c.get("rotation")
            Rcl = rot_ZYX(*cl) if cl else np.eye(3)
            oc = V(*c.get("origin", (0, 0, 0)))
            Rc, tc = R_n @ Rcl, t_n + R_n @ ((np.eye(3) - Rcl) @ oc)
            frm, to = V(*c["from"]), V(*c["to"])
            bucket = arms if here else body
            for i in range(n):
                y0 = frm[1] + (to[1] - frm[1]) * i / n
                y1 = frm[1] + (to[1] - frm[1]) * (i + 1) / n
                bucket.append(np.array([Rc @ V(x, y, z) + tc
                                        for x in (frm[0], to[0]) for y in (y0, y1)
                                        for z in (frm[2], to[2])]))
        for ch in node.get("children", []):
            rec(ch, R_n, t_n, here)

    rec(tree, np.eye(3), np.zeros(3), False)
    return body, arms


def support(slices, d, y, y_hi=None):
    best = -9e9
    for corners in slices:
        lo, hi = corners[:, 1].min() - 1e-6, corners[:, 1].max() + 1e-6
        if y_hi is None:
            if lo > y or hi < y:
                continue
        elif lo > y_hi or hi < y:
            continue
        best = max(best, float((corners @ d).max()))
    return best


def pleat_plan(slices_body):
    drop = SKIRT_TOP - SKIRT_HEM
    out = []
    for k in range(N_PLEAT):
        th = 2.0 * math.pi * k / N_PLEAT
        d = np.array([math.sin(th), 0.0, math.cos(th)])
        r_top = max(support(slices_body, d, 21.9, WAIST_BAND_TOP) + GAP_TOP
                    + (PLEAT_INSET if k % 2 else 0.0), MIN_TOP_R)
        need = 0.0
        y = SKIRT_HEM
        while y <= WAIST_BAND_TOP:
            need = max(need, (support(slices_body, d, y) + GAP_BODY - r_top)
                       / max(0.35, SKIRT_TOP - y))
            y += 0.5
        r_hem = r_top + max(FLARE, need * drop)
        phi = math.degrees(math.atan2(r_hem - r_top, drop))
        out.append({"k": k, "yaw": math.degrees(th), "phi": phi,
                    "r_top": r_top, "r_hem": r_hem,
                    "length": drop / math.cos(math.radians(phi))})
    width = 0.0
    for k in range(N_PLEAT):
        o = out[(k + 1) % N_PLEAT]
        dth = math.radians(abs(((o["yaw"] - out[k]["yaw"] + 180) % 360) - 180))
        width = max(width,
                    2 * max(out[k]["r_top"], o["r_top"]) * math.sin(dth / 2),
                    2 * max(out[k]["r_hem"], o["r_hem"]) * math.sin(dth / 2))
    for q in out:
        q["width"] = width + 0.25
        q["top"] = SKIRT_TOP - (SKIRT_TOP_ALT if q["k"] % 2 else 0.0)
        q["hem"] = SKIRT_HEM - (SKIRT_HEM_ALT if q["k"] % 2 else 0.0)
        q["t"] = PLEAT_T - (PLEAT_T_ALT if q["k"] % 2 else 0.0)
        q["length"] = (q["top"] - q["hem"]) / math.cos(math.radians(q["phi"]))
        q["name"] = f"Pleat_{q['k'] + 1:02d}"
        PLEAT_SHADE[q["name"]] = 0.5 + 0.5 * math.sin(math.radians(q["yaw"]) * 2 + 0.8)
    return out


def remap_region(atlas, face_iter, stops, label):
    mask = np.zeros((atlas.size, atlas.size), bool)
    for faces in face_iter:
        for data in (faces or {}).values():
            if "uv" not in data:
                continue
            x0, y0, x1, y1 = (int(v) for v in data["uv"])
            mask[max(0, y0):y1 + 1, max(0, x0):x1 + 1] = True
    op = mask & (atlas.cv[:, :, 3] > 8)
    r, g, b = atlas.cv[:, :, 0].astype(int), atlas.cv[:, :, 1].astype(int), atlas.cv[:, :, 2].astype(int)
    lum = (r * 0.299 + g * 0.587 + b * 0.114) / 255.0
    sel = op & (lum < 0.98)
    if not sel.any():
        print(f"{label}: 没挑到像素")
        return
    lut = np.array([ramp_lookup(stops, v) for v in np.linspace(0, 1, 256)])
    out = lut[np.clip((lum * 255).astype(int), 0, 255)]
    atlas.cv[sel, :3] = out[sel].astype(np.uint8)
    atlas.mask |= mask
    print(f"{label}: 重上色 {int(sel.sum())} 像素")


def repaint_legs(atlas, els_by_uuid, leg_uuids):
    """基底腿方块的贴图区按世界高度重画：膝下绿白条纹，脚背深色当鞋。
    条纹/鞋都是「高度 v 的函数」，绕腿一圈连续，不是盖章。"""
    r_ch, g_ch, b_ch = atlas.cv[:, :, 0].astype(int), atlas.cv[:, :, 1].astype(int), atlas.cv[:, :, 2].astype(int)
    lum = (r_ch * 0.299 + g_ch * 0.587 + b_ch * 0.114) / 255.0
    n_px = 0
    for u in leg_uuids:
        e = els_by_uuid[u]
        y_lo = min(v[1] for v in (e["from"], e["to"]))
        y_hi = max(v[1] for v in (e["from"], e["to"]))
        h = y_hi - y_lo
        for face, data in e["faces"].items():
            if face not in ("north", "south", "east", "west") or "uv" not in data:
                continue
            x0, y0, x1, y1 = (int(v) for v in data["uv"])
            for row in range(y0, y1 + 1):
                v_frac = 1.0 - (row - y0) / max(1, y1 - y0)     # v 向下 = 高度向下
                wy = y_lo + v_frac * h
                if wy < 1.9:
                    col = SHOE
                elif wy < STRIPES_FROM:
                    col = None                                  # 膝上留肤色
                else:
                    col = SOCK_W if int(math.floor((wy - STRIPES_FROM) / STRIPES_PERIOD)) % 2 else SOCK_G
                if col is None:
                    continue
                for xx in range(x0, x1 + 1):
                    px = atlas.cv[row, xx]
                    if px[3] < 8:
                        continue
                    atlas.cv[row, xx, :3] = np.clip(
                        np.array(col, float) + sha_seed(("leg", u, face, row, xx)).uniform(-4, 4),
                        0, 255)
                    n_px += 1
    print(f"腿：条纹/鞋 重画 {n_px} 像素")


# ===========================================================================
# 主流程
# ===========================================================================
def main():
    with io.open(BASE, encoding="utf-8") as fh:
        doc = json.load(fh)
    els_by_uuid = {e["uuid"]: e for e in doc["elements"]}

    base_elements = list(doc["elements"])
    base_tree = to_tree(copy.deepcopy(doc["outliner"]), base_elements)
    base_coplanar = set(map(str, coplanar_conflicts(base_tree)))
    print(f"基底：{len(base_elements)} 方块；共面冲突 {len(base_coplanar)}（基底自带）")

    base_tex = Image.open(io.BytesIO(base64.b64decode(
        doc["textures"][0]["source"].split(",", 1)[1]))).convert("RGBA")
    max_u = max(int(f["uv"][2]) for e in base_elements for f in e["faces"].values() if "uv" in f)
    atlas = Atlas(base_tex, min(276, (max_u // 8 + 1) * 8 + 4))

    # ---- 1. 重上色 --------------------------------------------------------
    hair_ids = group_elements(doc["outliner"], HAIR_GROUPS)
    hair_uuids = {u for ids in hair_ids.values() for u in ids}
    remap_region(atlas, (els_by_uuid[u]["faces"] for u in hair_uuids), RAMP_HAIR, label="头发")
    eye_ids = group_elements(doc["outliner"], ("Eyes",))["Eyes"]
    iris_uuids = [u for u in eye_ids if els_by_uuid[u]["name"] == "Eye"]
    remap_region(atlas, (els_by_uuid[u]["faces"] for u in iris_uuids), RAMP_IRIS, label="虹膜")

    # ---- 2. 摘角、摘长散发、后发收短 --------------------------------------
    removed = drop_groups(doc["outliner"], DROP_GROUPS)
    doc["elements"] = [e for e in doc["elements"] if e["uuid"] not in removed]
    hair_uuids -= removed
    print(f"摘掉 {len(removed)} 块（角+长散发）")

    # ---- 3. 腿：条纹袜 + 鞋（贴图重画，零新几何）---------------------------
    leg_uuids = [u for u, e in els_by_uuid.items()
                 if e["name"] in LEG_CUBES and u not in removed]
    repaint_legs(atlas, els_by_uuid, leg_uuids)

    # ---- 4. 新方块 --------------------------------------------------------
    new_elements = []
    attach = {}

    def emit(c, faces):
        el = {"name": c["name"], "box_uv": False, "rescale": False, "locked": False,
              "render_order": "default", "allow_mirror_modeling": True,
              "from": [round(v, 4) for v in c["from"]],
              "to": [round(v, 4) for v in c["to"]],
              "autouv": 0, "color": c.get("color", 0),
              "origin": [round(v, 4) for v in c["origin"]],
              "uv_offset": [0, 0], "faces": {}, "type": "cube",
              "uuid": str(uuid.uuid4())}
        if c.get("rotation"):
            el["rotation"] = [round(v, 4) for v in c["rotation"]]
        for face in FACES:
            mat = faces.get(face, faces.get("all"))
            scale = 1
            if isinstance(mat, tuple):      # (材质, 放大)：细节面用高分辨率 rect
                mat, scale = mat
            w, h = face_size(face, c["from"], c["to"])
            key = (mat, c["name"], face)
            if scale != 1:
                DETAIL_SCALES[(c["name"], face)] = scale
            x, y, rw, rh = atlas.rect(key, w * S * scale, h * S * scale)
            el["faces"][face] = {"uv": [x, y, x + rw, y + rh], "texture": 0}
        new_elements.append(el)
        return el

    # 4a. 上衣外壳
    for u, delta, name in TORSO_UUIDS:
        s = emit(shell(els_by_uuid[u], delta, name), {"all": "top"})
        attach.setdefault("UpperBody", []).append(s["uuid"])

    # 4b. 胸口整板（两片胸板前表面共面，铺一整块盖住）
    bust_L = els_by_uuid["5739873c-9f1c-e9a2-2a2a-3b636d27977a"]
    RX = bust_L["rotation"][0]
    Rb = rot_ZYX(*bust_L["rotation"])
    f, t = V(*bust_L["from"]), V(*bust_L["to"])
    c_mid = Rb @ ((V(f[0], f[1], f[2]) + V(t[0], t[1], f[2])) / 2 - V(*bust_L["origin"])) + V(*bust_L["origin"])
    n_bust = Rb @ V(0, 0, -1)
    CW = 3.60
    O = V(0.0, c_mid[1], c_mid[2]) + n_bust * (BUST_D + PROUD)
    p_f = emit(box("Top_Chest_Front",
                   (O[0] - CW, O[1] - 1.72, O[2] - 0.05), (O[0] + CW, O[1] + 1.72, O[2] + 0.28),
                   origin=O, rotation=(RX, 0, 0), color=1),
               {"north": ("creeperface", 3), "all": "top"})
    O2 = V(0.0, c_mid[1], c_mid[2]) + Rb @ V(0, -1, 0) * (BUST_D + PROUD)
    p_u = emit(box("Top_Chest_Under",
                   (O2[0] - CW, O2[1] - 1.70, O2[2] - 0.28), (O2[0] + CW, O2[1] + 1.70, O2[2] + 0.05),
                   origin=O2, rotation=(RX - 90.0, 0, 0), color=1), {"all": "top"})
    attach.setdefault("UpperBody", []).extend([p_f["uuid"], p_u["uuid"]])

    # 4c. 苦力怕脸印花：已在 4b 里画在胸口整板的正面（north 材质 creeperface）。
    #     注意不能印在腹/臀壳的背面——那一段整个藏在裙腰里，印了也看不见。

    # 4d. 圆领四片（上下沿错 0.04）
    NB, NZ = COLLAR["half"], COLLAR["depth"]
    y0, y1 = COLLAR["y0"], COLLAR["y1"]
    for nm, frm, to in (
            ("Collar_F", (-NB, y0, -NZ - 0.10), (NB, y1, -1.60)),
            ("Collar_B", (-NB, y0 + 0.04, 1.60), (NB, y1 + 0.04, NZ + 0.10)),
            ("Collar_L", (-NB - 0.10, y0 + 0.02, -NZ), (-1.60, y1 + 0.02, NZ)),
            ("Collar_R", (1.60, y0 + 0.06, -NZ), (NB + 0.10, y1 + 0.06, NZ))):
        s = emit(box(nm, frm, to), {"all": "topdark"})
        attach.setdefault("UpperBody", []).append(s["uuid"])

    # 4e. 短袖（上臂段，挂进手臂组跟 ±13°）
    for side, gname in (("L", "LeftArm"), ("R", "RightArm")):
        ua = els_by_uuid[ARM_UUIDS[side]]
        x0, x1 = sorted((ua["from"][0] - SLEEVE_UP, ua["to"][0] + SLEEVE_UP))
        z0, z1 = ua["from"][2] - SLEEVE_UP, ua["to"][2] + SLEEVE_UP
        s = emit(box(f"Sleeve_{side}", (x0, 24.60, z0), (x1, 28.45, z1)),
                 {"all": "top", "down": "topdark"})
        attach.setdefault(gname, []).append(s["uuid"])

    # 4f. 裙（先挂壳再量净空）
    for gname, uuids in attach.items():
        if not insert_children(doc["outliner"], gname, uuids):
            raise RuntimeError(f"找不到组 {gname}")
    attach.clear()
    bust_skip = {e["uuid"] for e in new_elements
                 if e["name"] in ("Top_Bust_L", "Top_Bust_R")}
    tree_now = to_tree(doc["outliner"], doc["elements"] + new_elements)
    slices_body, _arms = body_slices(tree_now, skip_uuids=bust_skip)
    pleats = pleat_plan(slices_body)
    skirt_groups = []
    for p in pleats:
        name = f"Pleat_{p['k'] + 1:02d}"
        el = emit(box(name,
                      (-p["width"] / 2, p["top"] - p["length"], p["r_top"]),
                      (p["width"] / 2, p["top"], p["r_top"] + p["t"]),
                      origin=(0, p["top"], p["r_top"]), rotation=(-p["phi"], 0, 0), color=5),
                  {"south": ("pleat", name), "north": "topdark",
                   "east": "topdark", "west": "topdark", "up": "top", "down": "top"})
        skirt_groups.append(
            {"name": name, "uuid": str(uuid.uuid4()), "origin": [0, p["top"], 0],
             "rotation": [0, round(p["yaw"], 4), 0], "color": 5, "bedrock_binding": "",
             "mirror_uv": False, "isOpen": False, "locked": False, "visibility": True,
             "autouv": 0, "children": [el["uuid"]]})

    # ---- 5. 挂裙组 + 顶层 groups 表 ---------------------------------------
    if not insert_children(doc["outliner"], "UpBody", skirt_groups):
        raise RuntimeError("找不到 UpBody")
    doc["elements"] = doc["elements"] + new_elements
    doc["name"] = "苦力怕娘"
    groups_table = []

    def collect(nodes):
        for ch in nodes:
            if isinstance(ch, dict) and ch.get("uuid"):
                groups_table.append({k: ch[k] for k in
                                     ("name", "uuid", "origin", "rotation", "color",
                                      "bedrock_binding", "mirror_uv", "autouv") if k in ch})
                collect(ch.get("children", []))
    collect(doc["outliner"])
    doc["groups"] = groups_table

    # ---- 6. 落盘 ----------------------------------------------------------
    atlas.extend_edges()
    buf = io.BytesIO()
    atlas.image().save(buf, "PNG", optimize=True)
    png = buf.getvalue()
    merged = doc["textures"][0]
    merged["source"] = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
    merged["name"] = f"{MODEL_NAME}.png"
    merged["id"] = "0"
    merged["uv_width"] = doc["resolution"]["width"]
    merged["uv_height"] = doc["resolution"]["height"]
    doc["textures"] = [merged]
    with open(os.path.join(HERE, f"{MODEL_NAME}.png"), "wb") as fh:
        fh.write(png)
    with open(os.path.join(HERE, f"{MODEL_NAME}.bbmodel"), "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False)
    print(f"写出 {MODEL_NAME}.bbmodel：新增 {len(new_elements)} 方块 / "
          f"{len(skirt_groups)} 裙片组；衣服矩形 {len(atlas.rects)}")

    verify(doc, new_elements, base_coplanar, pleats, atlas)
    return 0


# --- 自检（与 enderman_girl 同一套）-----------------------------------------
def verify(doc, new_elements, base_coplanar, pleats, atlas):
    new_uuids = {e["uuid"] for e in new_elements}
    tree = to_tree(doc["outliner"], doc["elements"])

    bad = []
    for el in new_elements:
        for face, data in el["faces"].items():
            scale = DETAIL_SCALES.get((el["name"], face), 1)
            w_px, h_px = data["uv"][2] - data["uv"][0], data["uv"][3] - data["uv"][1]
            fw, fh = face_size(face, el["from"], el["to"])
            ew, eh = max(4, round(fw * S * scale)), max(4, round(fh * S * scale))
            if abs(w_px - ew) > 0.51 * S or abs(h_px - eh) > 0.51 * S:
                bad.append((el["name"], face))
    print(f"[1] uv rect 与「面尺寸×{S}px×细节倍率」不符：{len(bad)} {bad[:5]}")

    tex_ids = {f_.get("texture") for el in doc["elements"] for f_ in el["faces"].values()}
    print(f"[1b] 引用的贴图编号 {sorted(tex_ids)}（应只有 0）；贴图张数 {len(doc['textures'])}")

    holes = []
    for el in new_elements:
        for face, data in el["faces"].items():
            x0, y0, x1, y1 = (int(v) for v in data["uv"])
            x0, y0 = max(0, x0), max(0, y0)
            x1, y1 = min(atlas.size, x1 + 1), min(atlas.size, y1 + 1)
            if x1 <= x0 or y1 <= y0:
                continue
            n = int((atlas.cv[y0:y1, x0:x1, 3] < 254).sum())
            if n:
                holes.append((el["name"], face, n))
    print(f"[1c] 新面采样区透明像素：{len(holes)} {holes[:5]}")

    skip = {e["uuid"] for e in doc["elements"]
            if e["name"].startswith("Pleat_") or e["name"] in ("Top_Bust_L", "Top_Bust_R")}
    slices_body, slices_arms = body_slices(tree, skip_uuids=skip)
    worst_body, worst_arm = 9e9, 9e9
    for p in pleats:
        yaw = math.radians(p["yaw"])
        d = np.array([math.sin(yaw), 0.0, math.cos(yaw)])
        slope = math.tan(math.radians(p["phi"]))
        y = p["hem"]
        while y <= min(p["top"], 22.70):
            r_in = p["r_top"] + (p["top"] - y) * slope
            worst_body = min(worst_body, r_in - support(slices_body, d, y))
            for corners in slices_arms:
                if corners[:, 1].min() - 1e-6 > y or corners[:, 1].max() + 1e-6 < y:
                    continue
                for cx, _, cz in corners:
                    ang = math.degrees(math.atan2(cx, cz))
                    if abs((ang - p["yaw"] + 180) % 360 - 180) > 20.0:
                        continue
                    worst_arm = min(worst_arm, math.hypot(cx, cz) - (r_in + p["t"]))
            y += 0.25
    print(f"[2] 裙片对「身体+外壳」净空最小 {worst_body:.2f}（>=0.10）；"
          f"裙面对袖子扇区 {worst_arm:.2f}（小负 = 袖子贴布）")

    new_cop = sorted(set(map(str, coplanar_conflicts(tree))) - base_coplanar)
    print(f"[3] coplanar_conflicts 新增：{len(new_cop)}")
    for x in new_cop[:6]:
        print("     ", x)

    zf = zfight_world(pruned_tree(tree, new_uuids))
    print(f"[4] zfight_world（新件子树）：{len(zf)}")
    for x in zf[:6]:
        print("     ", x[0], "|", x[1], "|", x[2], x[3])

    lo = min(min(c["from"][1], c["to"][1]) for c in doc["elements"])
    print(f"[5] 最低点 y={lo:.2f}（脚应贴地）")


if __name__ == "__main__":
    raise SystemExit(main())
