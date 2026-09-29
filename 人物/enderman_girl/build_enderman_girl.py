"""末影娘：以「[无动画共享]映素2.5代-女性标准体型v3.7」为基底的角色换装。

    python 人物/enderman_girl/build_enderman_girl.py

身体几何原样保留（曲线、组层级、贴图 0 不动），只动三样：

* 重上色——头发三组按亮度重映射到「虚空紫黑」色阶（保留原明暗结构），
  虹膜/瞳孔（眼眶贴图区里冷色像素）重映射到品红色阶。摘掉 DemonHornA（末影人无角）。
* 连衣裙——躯干九块向外扩 0.04~0.22 当外壳（肩斜/胸型/腰臀曲线全部继承），
  胸口用一整块横跨左右的斜板盖住两片胸板的缝（基底两片胸板前表面本来共面）。
  高领四片（上下沿错 0.04 防共面）。长袖分上臂/前臂两段挂进各自的手臂组，
  前臂段比上臂段外扩多 0.03，两段在肘部的侧面就不共面。
* 裙——24 片裙片，每片「本地外倾（元素 rx）+ 父组绕中轴 yaw」的嵌套组，
  半径按身体+外壳的逐高度支撑值反推（裙子裹着身体长出来，不硬套超椭圆）。
  相邻裙片：长度/厚度/顶高三个维度交错，顶面永不共面。

点缀只有一处：腰带正中一颗品红宝石（呼应眼睛）。左手一枚 8 板棱珠当末影珍珠
（每板绕自身轴交替俯仰，相邻板法线必不同——没有共面对），贴在掌心、不悬浮、不发光。

贴图全部画进基底贴图没人用的右侧空白（x >= TEX_X0），全模型只留 texture 0。
裙片每片一块自己的矩形（键带片号），明暗按片的角度连续变化——绕一圈明暗接得上，
也没有「同一块像素盖 24 片」的重复感。

自检（跑完打印，应全绿）：
  [1] 细节面 uv 宽高比 vs 真实宽高比（>8% 报警）
  [1b] 全模型只引用 texture 0
  [1c] 新面采样区里没有透明像素
  [2] 裙片对「身体+外壳」逐高度净空 >= 0.10；裙面对前臂/袖子净空
  [3] coplanar_conflicts 新增 = 0
  [4] zfight_world 新增 = 0（世界坐标 + 遮挡判定，圈板只能靠它抓）
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
MODEL_NAME = "enderman_girl"

# --- 调色（一种紫，靠明暗分层；品红只给眼睛和腰带上那一颗宝石）--------------
RAMP_HAIR = ((0.00, (14, 9, 24)), (0.35, (32, 20, 54)),
             (0.70, (54, 34, 86)), (1.00, (92, 54, 128)))
RAMP_IRIS = ((0.00, (66, 14, 88)), (0.55, (172, 44, 204)), (1.00, (255, 138, 255)))
VOID = (23, 17, 36)          # 连衣裙主色
VOID_DARK = (14, 10, 24)     # 褶谷/裙摆影
VOID_LIGHT = (40, 31, 62)    # 受光面
GEM = (198, 60, 220)
GEM_LIGHT = (246, 150, 255)
PEARL_A = (16, 74, 78)       # 末影珍珠：深青
PEARL_B = (52, 168, 156)     # 亮面
PEARL_C = (190, 255, 244)    # 高光点

S = 2                        # 衣服贴图密度：1 单位 = 2 像素
D_SHOULDER = 0.22            # 肩/脊柱这些露在外面的壳
D_CHEST = 0.16               # 胸壳（往下探进裙腰，收一点）
D_LOW = 0.04                 # 腰/腹/臀壳（整个藏在裙子里）
BUST_D = 0.16                # 胸板外扩
PROUD = 0.05                 # 胸口整板比胸壳再凸多少
SKIRT_TOP = 22.95            # 裙腰（盖住上衣下摆 22.84，不露基底内衣；低于胸壳最低点）
SKIRT_TOP_ALT = 0.06         # 裙片顶高交错幅度（防顶面共面，也 别高过上衣下摆）
WAIST_BAND_TOP = 22.60       # 裙腰半径的测量带顶（自然腰；胸壳不算，不然裙腰包住手臂）
SKIRT_HEM = 12.90            # 裙摆（大腿中上；膝盖在 9.5）
SKIRT_HEM_ALT = 0.35         # 裙摆长度交错（防底面共面）
PLEAT_T = 0.16               # 布厚
PLEAT_T_ALT = 0.03           # 厚度交错
PLEAT_INSET = 0.02           # 奇数片收进轴心 = 褶谷
GAP_TOP = 0.18               # 裙腰对「身体+外壳」的空隙
GAP_BODY = 0.22              # 裙身对「身体+外壳」的空隙
MIN_TOP_R = 2.95             # 裙腰半径下限（要罩住腰壳 2.54 再留空隙）
N_PLEAT = 24
FLARE = 1.35

COLLAR = dict(half=1.95, depth=2.02, y0=28.60, y1=30.15)
SLEEVE_UP = 0.25             # 上臂袖外扩
SLEEVE_FORE = 0.28           # 前臂袖外扩（多 0.03，肘部侧面不共面）
TORSO_UUIDS = (              # 基底躯干九块（外扩成连衣裙的外壳）
    ("83be27fb-9e1d-2c86-d65b-c8f7a6f6a7b5", D_SHOULDER, "Dress_Shoulder_L"),
    ("237cc73b-122a-4f04-bb98-3fe3b931c9d5", D_SHOULDER, "Dress_Shoulder_R"),
    ("d28fe618-b6f4-fef7-6fd8-d070ed0240cc", D_CHEST, "Dress_Chest"),
    ("1413ec5c-4324-93eb-6cf1-958c8d653d84", D_SHOULDER + 0.015, "Dress_Spine"),
    ("5739873c-9f1c-e9a2-2a2a-3b636d27977a", BUST_D, "Dress_Bust_L"),
    # R 侧多 0.02：基底两片胸板的前表面本来共面（zfight_world 实测会报），
    # 壳原样外扩会把这个共面对放大。0.02 的错缝肉眼不可见，平面就分开了。
    ("0ebf689c-e0b5-6abf-5740-db7a4a02054b", BUST_D + 0.02, "Dress_Bust_R"),
    ("6af77825-44f2-2d7d-bf10-b3e7fdf2e071", D_LOW, "Dress_Waist"),
    ("fd9d301e-c1d9-e45f-baf2-8ca1794d5b56", D_LOW, "Dress_Belly"),
    ("399e3521-472f-caaf-6834-93233d967903", D_LOW, "Dress_Butt"),
)
ARM_UUIDS = {"L": "e84da2f9-6c5f-5950-2a48-c8ff88d923ef",
             "R": "0ccd4641-feb8-0af7-6768-fdde6ca87af4"}
HAIR_GROUPS = ("HairFemaleH_Matching", "SideDownHairC", "SideHairA")
IRIS_GROUPS = ("Eyes",)      # 眼眶贴图区（在区里按冷色挑虹膜/瞳孔像素）
DROP_GROUPS = ("DemonHornA",)
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
# 贴图：自排货架（画进基底贴图的空白区），每块矩形 allocation 时立刻画好
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
        # 四周一圈 clamp 外框（含角）：uv 含右端点采样 + mip 都会碰到这一圈
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


def paint_void(cv, r, key):
    """连衣裙平铺：极轻的单位格明暗 + 顶部略亮（有布的感觉，不死黑）。"""
    x, y, w, h = r
    rng = sha_seed(("void",) + key[1:] if isinstance(key, tuple) else key)
    n = (rng.uniform(-3.5, 3.5, (h, w, 1))
         + (np.indices((h, w)).sum(0) % 2)[..., None] * 1.8 - 0.9)
    col = np.array(VOID, float)[None, None, :] + n
    cv[y:y + h, x:x + w, :3] = np.clip(col, 0, 255).astype(np.uint8)


def paint_void_edge(cv, r, key):
    """褶片侧面/内面：比正面深一号（不然亮光下侧面反成白线）。"""
    x, y, w, h = r
    rng = sha_seed(("edge",) + key[1:] if isinstance(key, tuple) else key)
    n = rng.uniform(-3.0, 3.0, (h, w, 1))
    col = np.array(tuple(int(c * 0.70) for c in VOID), float)[None, None, :] + n
    cv[y:y + h, x:x + w, :3] = np.clip(col, 0, 255).astype(np.uint8)


def paint_pleat(cv, r, key):
    """单片裙片：明暗由片的角度决定（key[1] 是片名 → 查亮度偏移表），
    腰头一道深带 + 上沿亮线，褶棱一条暗线，裙摆两行渐深。
    正面那片（Pleat_13，yaw 180°）腰头正中画一颗品红宝石——全身唯一的点缀。"""
    x, y, w, h = r
    shade = PLEAT_SHADE.get(key[1], 0.0)
    base = np.array(VOID, float) + shade * 255.0 * 0.16
    band = max(2, int(round(1.1 * S)))
    for j in range(h):
        for i in range(w):
            col = base + (-5 + 9 * (i / max(1, w - 1)))     # 一点点侧光
            if j < band:
                col = np.array(VOID_DARK, float) + (20 if j < 2 else 0)
            elif j < band + 2:
                col = np.array(VOID_DARK, float) + 5
            if i < 2:
                col = col - 9                                # 褶棱
            if j >= h - 3:
                col = col - (15 if j >= h - 1 else 8)        # 裙摆影
            cv[y + j, x + i, :3] = np.clip(col + sha_seed(("pp", key, i, j)).uniform(-2, 2),
                                           0, 255)
    if key[1] == "Pleat_13":   # yaw 180 → 板落在 -z，即正面（正文朝 -Z，README 约定）
        cx, cy = w // 2, 1
        for j in range(3):
            for i in range(3):
                col = GEM_LIGHT if (i, j) == (1, 1) else GEM
                cv[y + cy + j, x + cx - 1 + i, :3] = np.array(col, np.uint8)


def paint_pearl(cv, r, key):
    """珠面：中心亮青、边缘沉暗、一角高光——径向感。"""
    x, y, w, h = r
    cx, cy = (w - 1) / 2, (h - 1) / 2
    rad = max(cx, cy)
    for j in range(h):
        for i in range(w):
            t = math.hypot(i - cx, j - cy) / max(1e-6, rad)
            col = tuple(PEARL_B[k] + (PEARL_A[k] - PEARL_B[k]) * min(1.0, t * 1.15)
                        for k in range(3))
            if i <= 1 and j <= 1:
                col = PEARL_C
            cv[y + j, x + i, :3] = np.clip(np.array(col, float)
                                           + sha_seed(("pearl", key, i, j)).uniform(-4, 4),
                                           0, 255)


PAINTERS = {"void": paint_void, "voidedge": paint_void_edge,
            "pleat": paint_pleat, "pearl": paint_pearl}
PLEAT_SHADE = {}


# ===========================================================================
# 几何
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
    """按组名收集（含后代）所有方块 uuid。"""
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
    """大纲（uuid 引用）转成闸门要的 {cubes, children} 树。"""
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
    """只留 keep_uuids 的方块、但保留完整组链（origin/rotation 原样）——
    zfight_world 要在新件真实的组变换下跑。"""
    def walk(node):
        cubes = [c for c in node.get("cubes", []) if c.get("uuid") in keep_uuids]
        children = [walk(ch) for ch in node.get("children", [])]
        children = [ch for ch in children if ch["cubes"] or ch["children"]]
        return {"name": node.get("name", "?"), "origin": node.get("origin", [0, 0, 0]),
                "rotation": node.get("rotation"), "cubes": cubes, "children": children}
    return walk(tree)


def body_slices(tree, n=10, skip_uuids=()):
    """全身（含元素自身旋转）切薄片，分 body / arm 两桶：手臂垂在裙子外面，
    裙片半径只按身体算（手臂按角度扇区单独判，shirt_skirt_girl 同规则）。"""
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


def walk_all(node, R=None, t=None):
    """组链 × 元素自身旋转，yield (path, cube, R, t)。walk_groups 不算元素旋转，这里补上。"""
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
    """逐片定半径：腰上贴着「身体+外壳」+ 空隙；往下按各高度的最大需求反推外倾角，
    和 A 字幅度取大者。手臂不进来——袖子垂在裙子外面，扇区检查单独判。
    支撑带只量到自然腰（WAIST_BAND_TOP）：胸壳在更高的地方，裙腰不该被它撑大
    （撑大了会包住手臂——袖子在裙外的前提就是腰围小于臂线）。"""
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
        # 宽度带 0.25 搭接（盖住缝），厚度/长度/顶高交错（防共面）
        q["width"] = width + 0.25
        q["top"] = SKIRT_TOP - (SKIRT_TOP_ALT if q["k"] % 2 else 0.0)
        q["hem"] = SKIRT_HEM - (SKIRT_HEM_ALT if q["k"] % 2 else 0.0)
        q["t"] = PLEAT_T - (PLEAT_T_ALT if q["k"] % 2 else 0.0)
        q["length"] = (q["top"] - q["hem"]) / math.cos(math.radians(q["phi"]))
        q["name"] = f"Pleat_{q['k'] + 1:02d}"
        PLEAT_SHADE[q["name"]] = 0.5 + 0.5 * math.sin(math.radians(q["yaw"]) * 2 + 0.8)
    return out


# ===========================================================================
# 主流程
# ===========================================================================
def main():
    with io.open(BASE, encoding="utf-8") as fh:
        doc = json.load(fh)
    els_by_uuid = {e["uuid"]: e for e in doc["elements"]}

    base_outliner = copy.deepcopy(doc["outliner"])
    base_elements = list(doc["elements"])
    base_tree = to_tree(base_outliner, base_elements)
    base_coplanar = set(map(str, coplanar_conflicts(base_tree)))
    print(f"基底：{len(base_elements)} 方块；共面冲突 {len(base_coplanar)}（基底自带，不新增即可）")

    # ---- 1. 贴图底子 + 重上色 --------------------------------------------
    base_tex = Image.open(io.BytesIO(base64.b64decode(
        doc["textures"][0]["source"].split(",", 1)[1]))).convert("RGBA")
    max_u = max(int(f["uv"][2]) for e in base_elements for f in e["faces"].values() if "uv" in f)
    max_v = max(int(f["uv"][3]) for e in base_elements for f in e["faces"].values() if "uv" in f)
    tex_x0 = min(276, (max_u // 8 + 1) * 8 + 4)
    print(f"基底 uv 用到 u<={max_u} v<={max_v}；衣服画在 x>={tex_x0}")
    atlas = Atlas(base_tex, tex_x0)

    hair_ids = group_elements(doc["outliner"], HAIR_GROUPS)
    hair_uuids = {u for ids in hair_ids.values() for u in ids}
    remap_region(atlas, (els_by_uuid[u]["faces"] for u in hair_uuids),
                 RAMP_HAIR, label="头发")

    # 虹膜/瞳孔 = Eyes 组里名为 "Eye" 的元素的 uv 矩形（那里只有虹膜的红，
    # 没有皮肤和眼白），按亮度整块重映射到品红色阶
    eye_ids = group_elements(doc["outliner"], ("Eyes",))["Eyes"]
    iris_uuids = [u for u in eye_ids if els_by_uuid[u]["name"] == "Eye"]
    remap_region(atlas, (els_by_uuid[u]["faces"] for u in iris_uuids),
                 RAMP_IRIS, label="虹膜/瞳孔")

    # ---- 2. 摘角 ----------------------------------------------------------
    removed = drop_groups(doc["outliner"], DROP_GROUPS)
    doc["elements"] = [e for e in doc["elements"] if e["uuid"] not in removed]
    print(f"摘掉 DemonHornA：{len(removed)} 块")

    # ---- 3. 新方块 --------------------------------------------------------
    new_elements = []
    detail_faces = []          # (名, 面, uv宽, uv高, 面宽, 面高) —— uv 比例自检用
    attach = {}                # 组名 -> [uuid]
    skirt_groups = []

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
            w, h = face_size(face, c["from"], c["to"])
            key = (mat, c["name"], face)
            r = atlas.rect(key, w * S, h * S)
            x, y, rw, rh = r
            el["faces"][face] = {"uv": [x, y, x + rw, y + rh], "texture": 0}
            detail_faces.append((c["name"], face, rw, rh, round(w, 3), round(h, 3)))
        new_elements.append(el)
        return el

    # 3a. 连衣裙外壳：躯干九块外扩（必须挂回大纲，否则渲染器不画、outliner 闸点名）
    for u, delta, name in TORSO_UUIDS:
        s = emit(shell(els_by_uuid[u], delta, name), {"all": "void"})
        attach.setdefault("UpperBody", []).append(s["uuid"])

    # 3b. 胸口整板：两片胸板的前表面本来共面（法线 (0,.80,-.60)），铺一整块盖住
    bust_L = els_by_uuid["5739873c-9f1c-e9a2-2a2a-3b636d27977a"]
    RX = bust_L["rotation"][0]
    Rb = rot_ZYX(*bust_L["rotation"])
    f, t = V(*bust_L["from"]), V(*bust_L["to"])
    mid = (V(f[0], f[1], f[2]) + V(t[0], t[1], f[2])) / 2
    c_mid = Rb @ (mid - V(*bust_L["origin"])) + V(*bust_L["origin"])
    n_bust = Rb @ V(0, 0, -1)
    CW = 3.60
    O = V(0.0, c_mid[1], c_mid[2]) + n_bust * (BUST_D + PROUD)
    p_f = emit(box("Dress_Chest_Front",
                   (O[0] - CW, O[1] - 1.72, O[2] - 0.05), (O[0] + CW, O[1] + 1.72, O[2] + 0.28),
                   origin=O, rotation=(RX, 0, 0), color=1),
               {"all": "void"})
    O2 = V(0.0, c_mid[1], c_mid[2]) + Rb @ V(0, -1, 0) * (BUST_D + PROUD)
    p_u = emit(box("Dress_Chest_Under",
                   (O2[0] - CW, O2[1] - 1.70, O2[2] - 0.28), (O2[0] + CW, O2[1] + 1.70, O2[2] + 0.05),
                   origin=O2, rotation=(RX - 90.0, 0, 0), color=1),
               {"all": "void"})
    attach.setdefault("UpperBody", []).extend([p_f["uuid"], p_u["uuid"]])

    # 3c. 高领四片（上下沿错 0.04，转角处不共面）
    NB, NZ = COLLAR["half"], COLLAR["depth"]
    y0, y1 = COLLAR["y0"], COLLAR["y1"]
    emit(box("Collar_F", (-NB, y0, -NZ - 0.10), (NB, y1, -1.60)), {"all": "void"})
    emit(box("Collar_B", (-NB, y0 + 0.04, 1.60), (NB, y1 + 0.04, NZ + 0.10)), {"all": "void"})
    emit(box("Collar_L", (-NB - 0.10, y0 + 0.02, -NZ), (-1.60, y1 + 0.02, NZ)), {"all": "void"})
    emit(box("Collar_R", (1.60, y0 + 0.06, -NZ), (NB + 0.10, y1 + 0.06, NZ)), {"all": "void"})
    for nm in ("Collar_F", "Collar_B", "Collar_L", "Collar_R"):
        attach.setdefault("UpperBody", []).append(
            next(e["uuid"] for e in new_elements if e["name"] == nm))

    # 3d. 长袖：上臂段 + 前臂段 + 袖口（挂进各自手臂组，跟着 ±13° 走）
    for side, gname in (("L", "LeftArm"), ("R", "RightArm")):
        ua = els_by_uuid[ARM_UUIDS[side]]
        x0, x1 = sorted((ua["from"][0] - SLEEVE_UP, ua["to"][0] + SLEEVE_UP))
        z0, z1 = ua["from"][2] - SLEEVE_UP, ua["to"][2] + SLEEVE_UP
        s_up = emit(box(f"SleeveUp_{side}", (x0, 22.60, z0), (x1, 28.45, z1)), {"all": "void"})
        s_fo = emit(box(f"SleeveFore_{side}",
                        (ua["from"][0] - SLEEVE_FORE, 18.50, ua["from"][2] - SLEEVE_FORE),
                        (ua["to"][0] + SLEEVE_FORE, 22.70, ua["to"][2] + SLEEVE_FORE)),
                    {"all": "void"})
        s_cf = emit(box(f"Cuff_{side}",
                        (ua["from"][0] - SLEEVE_FORE - 0.06, 18.40, ua["from"][2] - SLEEVE_FORE - 0.06),
                        (ua["to"][0] + SLEEVE_FORE + 0.06, 19.40, ua["to"][2] + SLEEVE_FORE + 0.06)),
                    {"all": "voidedge"})
        attach.setdefault(gname, []).append(s_up["uuid"])
        attach.setdefault(f"{'Left' if side == 'L' else 'Right'}ForeArm", []).extend(
            [s_fo["uuid"], s_cf["uuid"]])

    # 3e. 腰部点缀：不另立 3D 腰带（方箍会切进旋转的腹/臀壳角）——
    #     品红直接画在正面裙片（Pleat_13，yaw 180°）的腰头贴图上，见 paint_pleat

    # 3f. 裙：先把已发出的新件挂回大纲（to_tree 只认大纲引用到的方块，
    #     不挂的话裙片量的是裸身体、验证量的却是带壳身体），再算净空。
    #     两片胸壳不进测量：53° 倾斜的下摆角旋转后探到 y 22.5、半径 5.7——
    #     那是悬垂在裙筒外的体型（和基底裸胸板一样），不是要裙腰去罩的东西。
    for gname, uuids in attach.items():
        if not insert_children(doc["outliner"], gname, uuids):
            raise RuntimeError(f"找不到组 {gname}")
    attach.clear()
    bust_skip = {e["uuid"] for e in new_elements
                 if e["name"] in ("Dress_Bust_L", "Dress_Bust_R")}
    tree_now = to_tree(doc["outliner"], doc["elements"] + new_elements)
    slices_body, _slices_arms = body_slices(tree_now, skip_uuids=bust_skip)
    pleats = pleat_plan(slices_body)
    for p in pleats:
        name = f"Pleat_{p['k'] + 1:02d}"
        el = emit(box(name,
                      (-p["width"] / 2, p["top"] - p["length"], p["r_top"]),
                      (p["width"] / 2, p["top"], p["r_top"] + p["t"]),
                      origin=(0, p["top"], p["r_top"]), rotation=(-p["phi"], 0, 0), color=5),
                  {"south": ("pleat", name), "north": "voidedge",
                   "east": "voidedge", "west": "voidedge", "up": "void", "down": "void"})
        skirt_groups.append(
            {"name": name, "uuid": str(uuid.uuid4()), "origin": [0, p["top"], 0],
             "rotation": [0, round(p["yaw"], 4), 0], "color": 5, "bedrock_binding": "",
             "mirror_uv": False, "isOpen": False, "locked": False, "visibility": True,
             "autouv": 0, "children": [el["uuid"]]})

    # 3g. 末影珍珠：单颗斜持的宝珠（掌心大小，微倾 40°）。试过 8 板棱珠——
    #     板薄缝大，读出来是一把青色尖爪而不是珠子；一颗整珠才诚实。
    #     与手掌方块相交 = 有接触，不是悬浮件，也不发光。
    emit(box("Pearl", (-4.70, 16.20, -1.00), (-2.50, 18.40, 1.20),
             origin=(-3.60, 17.30, 0.10), rotation=(14, 40, 0), color=3),
         {"all": "pearl"})
    attach.setdefault("LeftHand", []).append(new_elements[-1]["uuid"])

    # ---- 4. 挂回大纲（珍珠等裙片规划之后才发出的件）------------------------
    for gname, uuids in attach.items():
        if not insert_children(doc["outliner"], gname, uuids):
            raise RuntimeError(f"找不到组 {gname}")
    if not insert_children(doc["outliner"], "UpBody", skirt_groups):
        raise RuntimeError("找不到 UpBody")

    doc["elements"] = doc["elements"] + new_elements
    doc["name"] = "末影娘"

    # ---- 5. 顶层 groups 表（5.0 互操作，ISSUE.md 第 2 节）------------------
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
    img = atlas.image()
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
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

    verify(doc, new_elements, base_coplanar, base_tree, pleats, detail_faces, atlas)
    return 0


def find_group(outliner, name):
    for ch in outliner:
        if isinstance(ch, dict):
            if ch.get("name") == name:
                return ch
            r = find_group(ch.get("children", []), name)
            if r:
                return r
    return None


def remap_region(atlas, face_iter, stops, label):
    """把一批面的 uv 覆盖区按亮度重映射到色阶（该区应只含目标材质的像素）。"""
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
        print(f"{label}: 没挑到像素（检查选区）")
        return
    lut = np.array([ramp_lookup(stops, v) for v in np.linspace(0, 1, 256)])
    idx = np.clip((lum * 255).astype(int), 0, 255)
    out = lut[idx]
    atlas.cv[sel, :3] = out[sel].astype(np.uint8)
    atlas.mask |= mask
    print(f"{label}: 重上色 {int(sel.sum())} 像素")


# --- 自检 -------------------------------------------------------------------
def verify(doc, new_elements, base_coplanar, base_tree, pleats, detail_faces, atlas):
    new_uuids = {e["uuid"] for e in new_elements}
    tree = to_tree(doc["outliner"], doc["elements"])

    # [1] uv 宽高比（只抓真错：rect 尺寸应等于 max(4, round(面尺寸×S))；
    #     平铺布料的 4px 下限造成的比例变化不算）
    bad = []
    for el in new_elements:
        for face, data in el["faces"].items():
            x0, y0, x1, y1 = data["uv"]
            w_px, h_px = x1 - x0, y1 - y0
            fw, fh = face_size(face, el["from"], el["to"])
            ew, eh = max(4, round(fw * S)), max(4, round(fh * S))
            if abs(w_px - ew) > 0.51 * S or abs(h_px - eh) > 0.51 * S:
                bad.append((el["name"], face, w_px, h_px, ew, eh))
    print(f"[1] uv rect 与「面尺寸×{S}px（4px 下限）」不符：{len(bad)} {bad[:5]}")

    # [1b] 贴图引用
    tex_ids = {f_.get("texture") for el in doc["elements"] for f_ in el["faces"].values()}
    print(f"[1b] 引用的贴图编号 {sorted(tex_ids)}（应只有 0）；贴图张数 {len(doc['textures'])}")

    # [1c] 新面采样区透明像素
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

    # [2] 裙片净空：对「身体+外壳」量到 SWEET_BAND（22.70）为止——再往上胸壳
    #     下摆本来就悬在裙沿外（体型悬垂，径向度量会误报），交给渲染图看。
    #     两片胸壳同理：它们的下摆角整个悬在裙筒半径之外（y 22.65 处 5.3 > 3.7），
    #     从外头悬垂过去、不穿过裙壁，不进径向净空。
    skip = {e["uuid"] for e in doc["elements"]
            if e["name"].startswith("Pleat_") or e["name"] in ("Dress_Bust_L", "Dress_Bust_R")}
    slices_body, slices_arms = body_slices(tree, skip_uuids=skip)
    worst_body, worst_arm = 9e9, 9e9
    culprit = culprit_arm = None
    for p in pleats:
        yaw = math.radians(p["yaw"])
        d = np.array([math.sin(yaw), 0.0, math.cos(yaw)])
        slope = math.tan(math.radians(p["phi"]))
        y = p["hem"]
        while y <= min(p["top"], 22.70):
            r_in = p["r_top"] + (p["top"] - y) * slope
            s_val = support(slices_body, d, y)
            if r_in - s_val < worst_body:
                worst_body = r_in - s_val
                culprit = (p["name"], round(p["yaw"], 1), round(y, 2),
                           round(r_in, 2), round(s_val, 2))
            for corners in slices_arms:
                if corners[:, 1].min() - 1e-6 > y or corners[:, 1].max() + 1e-6 < y:
                    continue
                for cx, _, cz in corners:
                    ang = math.degrees(math.atan2(cx, cz))
                    if abs((ang - p["yaw"] + 180) % 360 - 180) > 20.0:
                        continue
                    c = math.hypot(cx, cz) - (r_in + p["t"])
                    if c < worst_arm:
                        worst_arm = c
                        culprit_arm = (p["name"], round(math.hypot(cx, cz), 2),
                                       round(y, 2), round(r_in + p["t"], 2))
            y += 0.25
    print(f"[2] 裙片对「身体+外壳」净空最小 {worst_body:.2f}（>=0.10）；"
          f"裙面对袖子扇区 {worst_arm:.2f}（小负 = 袖子贴布，大负 = 切进裙子）")
    if worst_arm < -1.0 and culprit_arm:
        print(f"     手臂侧最深处：{culprit_arm}（片名, 臂半径, y, 裙面半径）")
    if worst_body < 0.10 and culprit:
        pn, pyaw, py, rin, sv = culprit
        d = np.array([math.sin(math.radians(pyaw)), 0.0, math.cos(math.radians(pyaw))])
        for path, cube, R, t in walk_all(tree):
            if cube.get("uuid") in skip:
                continue
            frm, to = V(*cube["from"]), V(*cube["to"])
            for i in range(10):
                y0 = frm[1] + (to[1] - frm[1]) * i / 10
                y1 = frm[1] + (to[1] - frm[1]) * (i + 1) / 10
                corners = np.array([R @ V(x, yy, z) + t
                                    for x in (frm[0], to[0]) for yy in (y0, y1)
                                    for z in (frm[2], to[2])])
                lo, hi = corners[:, 1].min() - 1e-6, corners[:, 1].max() + 1e-6
                if lo > py or hi < py:
                    continue
                if abs(float((corners @ d).max()) - sv) < 0.05:
                    print(f"     肇事方块：{path} @ y={py}（r_in={rin}, 支撑={sv}）")
                    break
            else:
                continue
            break

    # [3] coplanar 新增
    new_cop = sorted(set(map(str, coplanar_conflicts(tree))) - base_coplanar)
    print(f"[3] coplanar_conflicts 新增：{len(new_cop)}")
    for x in new_cop[:8]:
        print("     ", x)

    # [4] zfight 新增（世界坐标；只跑含新件的剪枝树 + 基底对照）
    new_tree = pruned_tree(tree, new_uuids)
    zf_new = zfight_world(new_tree)
    print(f"[4] zfight_world（新件子树）：{len(zf_new)}")
    for x in zf_new[:8]:
        print("     ", x[0], "|", x[1], "|", x[2], x[3])

    lo = min(min(c["from"][1], c["to"][1]) for c in doc["elements"])
    print(f"[5] 最低点 y={lo:.2f}（脚应贴地）")


if __name__ == "__main__":
    raise SystemExit(main())
