"""巨型地狱飞龙（西方 hell dragon）v3 生成脚本 —— 全程经 headless MCP 建模。

v3 重做要点（用户验收意见）：
* 颈/尾：链式关节——每节是沿延伸方向的 pitched 长方体（element rotation 绕
  后端面中心累加角度），呈 S 曲线一节节拍过去，不再横平竖直；
* 翼：指骨从腕部扇形辐射（element ry 旋转），指间膜为真蹼状 mesh 薄板实体
  （三角面片 + 扇形收口后缘），内翼膜连到体侧；
* 腿：四条完整可见（髋/股/胫/足 + 每足 3 爪），挂在躯干两侧下方。

产出 property/hell_dragon/。重跑即可复现。
validate 用 interpenetration_depth=1.35：pitched 链节交界的楔形重叠
（≈(w/2)·sinΔθ ≤ 1.1）是有意连接，已在 README 声明。
"""
from __future__ import annotations

import base64
import io
import json
import math
import os
import random
import subprocess
import time
import zlib

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
PROP = os.path.join(REPO, "property")
OUT_DIR = os.path.join(PROP, "hell_dragon")
MODEL = os.path.join(OUT_DIR, "hell_dragon.bbmodel")
TEX_PNG = os.path.join(OUT_DIR, "hell_dragon.png")
TEX_NAME = "hell_dragon"
RES = 256
S = 1.3

NODE = r"D:/nodejs/node.exe"
MCP_ENTRY = r"D:/Products/blockbench/.mcp/node_modules/blockbench-mcp/bin/blockbench-mcp-headless.mjs"
ROOTS = [REPO.replace("\\", "/"), "D:/Products/blockbench/.mcp/out"]

# ---------------------------------------------------------------- 调色板
HIDE = ["#7d2636", "#5e1b29", "#43101d", "#2d0a14", "#1b060c"]
HIDE_DK = ["#5e1b29", "#43101d", "#2d0a14", "#1b060c", "#100409"]
BELLY = ["#6a463a", "#573830", "#442b26", "#331f1b"]
MEMB = ["#6e2130", "#521726", "#3a0f1a", "#260812"]
HORN = ["#454550", "#33333d", "#232329", "#151519"]
SPIKE = ["#a8906a", "#876c4c", "#654e36", "#43321f"]
EMBER = ["#ffe08a", "#ffb545", "#ff7a26", "#c8501e", "#7a1e06"]
TEETH = ["#d3cbb6", "#b0a78f", "#8d8570"]

MAGENTA = (255, 0, 255, 255)


def hx(s):
    s = s.lstrip("#")
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16), 255)


def ramp(pal, t):
    t = min(1.0, max(0.0, t))
    return hx(pal[min(len(pal) - 1, int(t * len(pal)))])


def _mix(c, k):
    if k >= 0:
        return tuple(min(255, int(v + (255 - v) * k)) for v in c[:3]) + (255,)
    return tuple(int(v * (1 + k)) for v in c[:3]) + (255,)


def scaled(v):
    """设计坐标 → 模型坐标（×S，对齐 0.5 格）。"""
    return round(v * S * 2) / 2


# ---------------------------------------------------------------- 几何定义
# cube 项: (name, group, mat, from, to, roles, inflate, rot, origin)
# rot/origin: element 旋转（度, ZYX）与旋转轴心，None = 不旋转/取方块中心。
# 全部设计坐标，输出时经 scaled() ×1.3 对齐 0.5 格。

CUBES = []


def cube(name, group, mat, f, t, roles=None, inflate=0, rot=None, origin=None):
    CUBES.append((name, group, mat, [float(x) for x in f], [float(x) for x in t],
                  roles or {}, inflate, rot, origin))


def _chain(start, segs, forward="-z", sink=None):
    """链式节段：segs = [(name, L, w, h, pitch)]，pitch 为累计俯仰角。
    forward='-z'（颈，前端抬升）或 '+z'（尾，远端下沉）。
    每节 authored 未旋转，element rx=pitch 绕后端面中心旋转。
    返回 [(name, rear_center, pitch, L, w, h)] 供附属件定位。"""
    out = []
    p = [float(v) for v in start]
    sgn = -1 if forward == "-z" else 1
    for name, L, w, h, pitch in segs:
        z0, z1 = (p[2] - L, p[2]) if sgn < 0 else (p[2], p[2] + L)
        roles = {"down": "plates"} if w >= 5 else {}
        cube(name, sink(name), "hide",
             [p[0] - w / 2, p[1] - h / 2, z0], [p[0] + w / 2, p[1] + h / 2, z1],
             roles, rot=[pitch, 0, 0], origin=list(p))
        out.append((name, list(p), pitch, L, w, h))
        rad = math.radians(pitch)
        p = [p[0], p[1] + L * math.sin(rad) * (1 if sgn < 0 else -1),
             p[2] + L * math.cos(rad) * sgn]
    return out


# ---- 躯干（v4 瘦身：12 宽胸、10 宽髋）
cube("chest", "body", "hide", [-6, 44, -18], [6, 60, 4], {"down": "plates"})
cube("ridge", "body", "hide", [-1.5, 60, -10], [1.5, 63, -2])
cube("belly", "body", "plates", [-3, 38, -10], [3, 45, 0])
cube("hips", "body", "hide", [-5, 44, 4], [5, 58, 18], {"down": "plates"})

# ---- 颈（4 节链式，22/35/47/60° S 形上扬，截面 8→5 渐细）
_neck = _chain((0, 53, -17), [
    ("neck_1", 14, 8, 8, 22),
    ("neck_2", 13, 7, 7, 35),
    ("neck_3", 12, 6, 6, 47),
    ("neck_4", 11, 5, 5, 60),
    ("neck_5", 8, 5, 5, 55),
], forward="-z", sink=lambda n: n)


def _neck_spike(seg_idx, t_frac, h=3):
    _, p, pitch, L, w, sh = _neck[seg_idx]
    rad = math.radians(pitch)
    t = L * t_frac
    cx = p[0]
    cy = p[1] + t * math.sin(rad) + (sh / 2) * math.cos(rad)
    cz = p[2] - t * math.cos(rad)
    cube(f"nspike_{seg_idx+1}", f"neck_{seg_idx+1}", "spike",
         [cx - 1, cy - 0.5, cz - 1], [cx + 1, cy + h, cz + 1],
         rot=[pitch, 0, 0], origin=[cx, cy, cz])


_neck_spike(1, 0.55)
_neck_spike(2, 0.5)
_neck_spike(3, 0.35, h=2.5)

# ---- 头（架在颈链顶端；头基座与颈 4 同角楔接）
_p4 = _neck[3][1]
cube("head_base", "head", "hide",
     [_p4[0] - 2.5, _p4[1] - 3, _p4[2] - 6], [_p4[0] + 2.5, _p4[1] + 3, _p4[2]],
     rot=[60, 0, 0], origin=list(_p4))
cube("skull", "head", "hide", [-4, 80, -70], [4, 94, -56], {"down": "plates"})
cube("snout", "head", "hide", [-2, 82, -77], [2, 88, -67],
     {"down": "mouth", "north": "snoutfront"})
cube("crest", "head", "spike", [-2, 94, -69], [2, 96, -65])
cube("brow_l", "head", "horn", [-5, 89, -70], [-3, 91, -65])
cube("eye_l", "head", "glow", [-5, 86, -69], [-4, 88, -66])
cube("jaw", "jaw", "hide", [-2, 76, -75], [2, 80, -59],
     {"up": "mouth", "north": "jawfront"})
cube("throat", "head", "glow", [-1, 80, -76], [1, 82, -69], {"north": "mouth"})
cube("fang_ul", "head", "teeth", [-2, 80, -77], [-1, 82, -75.5])
cube("fang_ur", "head", "teeth", [1, 80, -77], [2, 82, -75.5])
cube("fang_ll", "jaw", "teeth", [-2, 80, -75], [-1, 82, -73.5])
cube("fang_lr", "jaw", "teeth", [1, 80, -75], [2, 82, -73.5])

# ---- 角（链式 5 节渐细：仰角 80°→8° 的后掠弧，截面 2.2→1.2）
def _horn_chain():
    p = [-2.2, 93.5, -62]
    dims = [(2.2, 2.2), (2, 2), (1.8, 1.8), (1.5, 1.5), (1.2, 1.2)]
    for i, e in enumerate((80, 62, 44, 26, 8)):
        L = 3.2
        w, h = dims[i]
        P = 90 + e
        cube(f"horn_{i+1}_l", "horns", "horn",
             [p[0] - w / 2, p[1] - h / 2, p[2] - L], [p[0] + w / 2, p[1] + h / 2, p[2]],
             rot=[P, 0, 0], origin=list(p))
        rad = math.radians(P)
        p = [p[0], p[1] + L * math.sin(rad), p[2] - L * math.cos(rad)]
_horn_chain()

# ---- 尾（6 节链式下垂 8→36°，截面 7→2 渐细 + 三叉尾矛）
_tail = _chain((0, 50, 18.5), [
    ("tail_1", 13, 7, 8, 8),
    ("tail_2", 12, 6, 7, 16),
    ("tail_3", 11, 5, 6, 24),
    ("tail_4", 10, 4, 5, 30),
    ("tail_5", 9, 3, 4, 34),
    ("tail_6", 8, 2, 3, 36),
], forward="+z", sink=lambda n: n)


def _tail_spike(seg_idx, t_frac, h=3):
    _, p, pitch, L, w, sh = _tail[seg_idx]
    rad = math.radians(pitch)
    t = L * t_frac
    cx = p[0]
    cy = p[1] - t * math.sin(rad) + (sh / 2) * math.cos(rad)
    cz = p[2] + t * math.cos(rad)
    cube(f"tspike_{seg_idx+1}", f"tail_{seg_idx+1}", "spike",
         [cx - 1, cy - 0.5, cz - 1], [cx + 1, cy + h, cz + 1],
         rot=[pitch, 0, 0], origin=[cx, cy, cz])


_tail_spike(1, 0.5)
_tail_spike(2, 0.5)
_tail_spike(3, 0.5)
_tail_spike(4, 0.5)

# 尾矛：末节末端沿 -36° 的三叉
_p6 = _tail[5][1]
_rad = math.radians(36)
_cx, _cy, _cz = 0, _p6[1] - 8 * math.sin(_rad), _p6[2] + 8 * math.cos(_rad)
cube("spade", "tail_6", "spike", [_cx - 1.5, _cy - 2, _cz], [_cx + 1.5, _cy + 2, _cz + 4],
     rot=[36, 0, 0], origin=[_cx, _cy, _cz])
cube("spade_up", "tail_6", "spike", [_cx - 0.5, _cy + 2, _cz - 1], [_cx + 0.5, _cy + 8, _cz + 3],
     rot=[36, 0, 0], origin=[_cx, _cy + 2, _cz])
cube("spade_dn", "tail_6", "spike", [_cx - 0.5, _cy - 6, _cz - 1], [_cx + 0.5, _cy - 2, _cz + 3],
     rot=[36, 0, 0], origin=[_cx, _cy - 2, _cz])
cube("spade_bl", "tail_6", "spike", [_cx - 4.5, _cy - 1, _cz + 0.5], [_cx - 1.5, _cy + 1, _cz + 2.5],
     rot=[36, 0, 0], origin=[_cx - 1.5, _cy, _cz + 0.5])
cube("spade_br", "tail_6", "spike", [_cx + 1.5, _cy - 1, _cz + 0.5], [_cx + 4.5, _cy + 1, _cz + 2.5],
     rot=[36, 0, 0], origin=[_cx + 1.5, _cy, _cz + 0.5])

# ---- 腿（链式收拢：股-胫-足-3爪，飞行姿向后收折；左右由镜像生成）
def _leg_chain(tag, start, segs, claws=3):
    p = [float(v) for v in start]
    for i, (name, L, w, h, e) in enumerate(segs):
        rad = math.radians(e)
        cube(f"{name}_{tag}", f"leg_{tag}", "hide",
             [p[0] - w / 2, p[1] - h / 2, p[2]], [p[0] + w / 2, p[1] + h / 2, p[2] + L],
             rot=[e, 0, 0], origin=list(p))
        p = [p[0], p[1] - L * math.sin(rad), p[2] + L * math.cos(rad)]
    for j in range(claws):
        off = (j - (claws - 1) / 2) * 1.1
        cx, cy, cz = p[0] + off, p[1], p[2]
        cube(f"claw{j+1}_{tag}", f"leg_{tag}", "horn",
             [cx - 0.5, cy - 1, cz], [cx + 0.5, cy + 1, cz + 2.5],
             rot=[15, 0, 0], origin=[cx, cy, cz])


_leg_chain("b_l", (-4.5, 47, 9), [
    ("thigh", 11, 4.5, 5, 35),
    ("shin", 9, 3, 3.5, 65),
    ("foot", 6, 2.5, 2.5, 15),
])
_leg_chain("f_l", (-4, 47, -10), [
    ("thigh", 9, 3.5, 4, 40),
    ("shin", 7.5, 2.5, 3, 70),
    ("foot", 5, 2, 2, 18),
])

# ---- 左翼（+x）：臂/前臂沿体侧；指骨扇形辐射；蹼膜旋转板条
# 翼臂链式（参考尾巴）：肩→肘→腕两节，后节前端埋入前节 1.2，关节处连续
_ARM_S = (4.5, -10.2)  # 肩部（埋入胸侧 1.5）
_ARM_E = (28.19, -9.37)  # 肘
cube("humerus_l", "wing_l", "hide",
     [_ARM_S[0], 55.75, _ARM_S[1] - 1.25], [_ARM_S[0] + 26, 58.25, _ARM_S[1] + 1.25],
     rot=[0, -2, 0], origin=[_ARM_S[0], 57, _ARM_S[1]])
_Q = (_ARM_E[0] - 1.1, _ARM_E[1] - 0.49)  # 前臂后端回埋 1.1（加粗 2.5、加长 23）
cube("forearm_l", "wing_fore_l", "hide",
     [_Q[0], 55.75, _Q[1] - 1.25], [_Q[0] + 23, 58.25, _Q[1] + 1.25],
     rot=[0, -24, 0], origin=[_Q[0], 57, _Q[1]])

_WX, _WY, _WZ = 50.39, 57, -0.43  # 腕（前臂末端）
_FINGERS = [(3, 30), (22, 26), (42, 21), (62, 17)]
for _i, (_ang, _L) in enumerate(_FINGERS, 1):
    cube(f"finger{_i}_l", "wing_hand_l", "hide",
         [_WX - 1.5, _WY - 0.75, _WZ - 0.75], [_WX + _L, _WY + 0.75, _WZ + 0.75],
         {}, 0, rot=[0, -_ang, 0], origin=[_WX, _WY, _WZ])
cube("thumb_l", "wing_hand_l", "horn", [_WX, _WY + 0.75, _WZ - 3], [_WX + 4, _WY + 2.75, _WZ + 1])


# ---- 蹼膜面片（零厚度平面栅格）：多边形 → 1.5 格 cell 阵列
# 轮廓严格跟随指骨（放射边界）与指尖间凹弧后缘（贝塞尔内收），杜绝"砖块矩形"。
# UV 世界锁定到一张大矩形：血脉纹理跨面片连续。镜像由 _mirror_name 处理。
# 内翼第二扇（肘部辐条+面片）：从肘部向后（尾侧）辐射 3 根细辐条，
# 辐条之间铺楔形零厚度膜面片——与外翼指扇同款工艺
_EX, _EZ = 28.19, -9.37  # 肘
_ESPOKES = [(40, 22), (55, 25), (70, 27), (85, 27), (100, 25)]
for _i, (_ang, _L) in enumerate(_ESPOKES, 1):
    cube(f"espoke{_i}_l", "wing_fore_l", "hide",
         [_EX, _WY - 0.75, _EZ - 0.75], [_EX + _L, _WY + 0.75, _EZ + 0.75],
         rot=[0, -_ang, 0], origin=[_EX, _WY, _EZ])

_S1 = (_EX + 22 * math.cos(math.radians(40)), _EZ + 22 * math.sin(math.radians(40)))
_S2 = (_EX + 25 * math.cos(math.radians(55)), _EZ + 25 * math.sin(math.radians(55)))
_S3 = (_EX + 27 * math.cos(math.radians(70)), _EZ + 27 * math.sin(math.radians(70)))
_S4 = (_EX + 27 * math.cos(math.radians(85)), _EZ + 27 * math.sin(math.radians(85)))
_S5 = (_EX + 25 * math.cos(math.radians(100)), _EZ + 25 * math.sin(math.radians(100)))
_IN_PANELS = [
    ("wing_fore_l", (28.19, -9.37), (45.5, -1.6), _S1, 0.25),
    ("wing_fore_l", (28.19, -9.37), _S1, _S2, 0.3),
    ("wing_fore_l", (28.19, -9.37), _S2, _S3, 0.3),
    ("wing_fore_l", (28.19, -9.37), _S3, _S4, 0.3),
    ("wing_fore_l", (28.19, -9.37), _S4, _S5, 0.3),
]

# 外翼指扇（已认可形态，保持不动）
_WEDGE_SPECS = (
    ((50.39, -0.43), (80.36, 1.14), (74.5, 9.34)),
    ((50.39, -0.43), (74.5, 9.34), (66.0, 13.65)),
    ((50.39, -0.43), (66.0, 13.65), (58.4, 14.6)),
)


def _pip(pt, poly):
    x, z = pt
    inside = False
    n = len(poly)
    for i in range(n):
        x0, z0 = poly[i]
        x1, z1 = poly[(i + 1) % n]
        if (z0 > z) != (z1 > z):
            xi = x0 + (z - z0) * (x1 - x0) / (z1 - z0)
            if x < xi:
                inside = not inside
    return inside


_MEM_CELLS = []
_cid = 0


def _raster(poly, group, anchor, step=1.5):
    global _cid
    xs = [q[0] for q in poly]
    zs = [q[1] for q in poly]
    gx = math.floor((min(xs) - anchor[0]) / step) * step + anchor[0]
    gz = math.floor((min(zs) - anchor[1]) / step) * step + anchor[1]
    cells = []
    x = gx
    while x < max(xs):
        z = gz
        while z < max(zs):
            c = (x + step / 2, z + step / 2)
            if _pip(c, poly):
                cells.append((x, z))
            z += step
        x += step
    cellset = set(cells)
    seen = set()
    best = []
    for c in cells:
        if c in seen:
            continue
        comp = []
        stack = [c]
        seen.add(c)
        while stack:
            cur = stack.pop()
            comp.append(cur)
            cx, cz = cur
            for dx, dz in ((step, 0), (-step, 0), (0, step), (0, -step)):
                nb = (cx + dx, cz + dz)
                if nb in cellset and nb not in seen:
                    seen.add(nb)
                    stack.append(nb)
        if len(comp) > len(best):
            best = comp
    for (x, z) in best:
        _cid += 1
        _MEM_CELLS.append((f"memc_{_cid}_l", group, x, z, x + step, z + step))


def _notch(p_a, p_b, t):
    """指间凹弧点：两端点中点向毂浅拉 t（t 过大自交成蝴蝶结）。"""
    mx, mz = (p_a[0] + p_b[0]) / 2, (p_a[1] + p_b[1]) / 2
    return (mx + (_EX - mx) * t, _EZ + (mz - _EZ) * t)


for (_pg, _a, _b, _c, _t) in _IN_PANELS:
    _raster([_a, _b, _notch(_b, _c, _t), _c], _pg, (_EX, _EZ))
for _poly in _WEDGE_SPECS:
    _raster(_poly, "wing_hand_l", (50.39, -0.43))
# 肘/腕两个辐条汇聚毂掏空（骨丛遮挡该处，防面片共面闪烁）
for _hx, _hz in ((_EX, _EZ), (50.39, -0.43)):
    _MEM_CELLS = [c for c in _MEM_CELLS
                  if (c[2] + 0.75 - _hx) ** 2 + (c[3] + 0.75 - _hz) ** 2 >= 2.25]

# 世界锁定 UV 用 bbox（缩放后）
_allx = [scaled(v) for c in _MEM_CELLS for v in (c[2], c[4])]
_allz = [scaled(v) for c in _MEM_CELLS for v in (c[3], c[5])]
MEM_BBOX = (min(_allx), min(_allz), max(_allx), max(_allz))
MEM_EXTRA = {("memwing", "l"): (math.ceil(MEM_BBOX[2] - MEM_BBOX[0]) + 2,
                                math.ceil(MEM_BBOX[3] - MEM_BBOX[1]) + 2)}

# 背棘/髋棘
cube("rspike_1", "body", "spike", [-1, 63, -8], [1, 66, -6])
cube("rspike_2", "body", "spike", [-1, 63, -4], [1, 66, -2])
cube("hspike", "body", "spike", [-1, 58, 8], [1, 61, 10])

# ---------------------------------------------------------------- 组（链式关节 = 动画铰链，父先于子）
GROUPS = [
    ("root", None, (0, 0, 0)),
    ("body", "root", (0, 52, -7)),
    ("wing_l", "body", (4.5, 57, -10.2)),
    ("wing_fore_l", "wing_l", (28.19, 57, -9.37)),
    ("wing_hand_l", "wing_fore_l", (46, 57, -2)),
    ("leg_f_l", "body", (-4, 47, -10)),
    ("leg_b_l", "body", (-4.5, 47, 9)),
]
GROUPS += [(name, parent, tuple(p)) for (name, p, pitch, L, w, h), parent in
           zip(_neck, ("body", "neck_1", "neck_2", "neck_3", "neck_4"))]
GROUPS += [("head", "neck_4", tuple(_p4)), ("jaw", "head", (0, 80, -60)),
           ("horns", "head", (0, 94, -58))]
GROUPS += [(name, parent, tuple(p)) for (name, p, pitch, L, w, h), parent in
           zip(_tail, ("body", "tail_1", "tail_2", "tail_3", "tail_4", "tail_5"))]

def _mirror_name(n):
    """_fl/_bl 后缀（腿）与 _l 后缀（其余左件）都能镜像。"""
    if n.endswith("_fl"):
        return n[:-3] + "_fr"
    if n.endswith("_bl"):
        return n[:-3] + "_br"
    if n.endswith("_l"):
        return n[:-2] + "_r"
    return n


def mirror_cube(c):
    (name, group, mat, f, t, roles, inflate, rot, origin) = c
    mf = [-t[0], f[1], f[2]]
    mt = [-f[0], t[1], t[2]]
    mrot = list(rot) if rot else None
    if mrot:
        mrot[1] = -mrot[1]  # ry 翻转
    morigin = list(origin) if origin else None
    if morigin:
        morigin[0] = -morigin[0]
    return (_mirror_name(name), _mirror_name(group), mat, mf, mt, roles, inflate, mrot, morigin)


RIGHT_CUBES = [mirror_cube(c) for c in CUBES if c[0].endswith("_l") or c[0].endswith("_fl") or c[0].endswith("_bl")]
MIRROR_GROUPS = [(_mirror_name(n), _mirror_name(p) if p else p, (-o[0], o[1], o[2]))
                 for n, p, o in GROUPS if _mirror_name(n) != n]

ALL_GROUPS = GROUPS + MIRROR_GROUPS
ALL_CUBES = CUBES + RIGHT_CUBES


def scaled(v):
    return round(v * S * 2) / 2


# ---------------------------------------------------------------- UV 装箱
FACES = ("north", "east", "south", "west", "up", "down")


def face_dims(f, t, face):
    dx, dy, dz = t[0] - f[0], t[1] - f[1], t[2] - f[2]
    return {"north": (dx, dy), "south": (dx, dy), "east": (dz, dy),
            "west": (dz, dy), "up": (dx, dz), "down": (dx, dz)}[face]


def build_rects(extra=None):
    rects = {}
    unique = [c for c in ALL_CUBES if not c[0].endswith("_r")]
    items = []
    for name, _, _, f, t, _, _, _, _ in unique:
        for face in FACES:
            w = max(1, round(face_dims(f, t, face)[0]))
            h = max(1, round(face_dims(f, t, face)[1]))
            items.append((w, h, (name, face)))
    for key, (w, h) in (extra or {}).items():
        items.append((w, h, key))
    items.sort(key=lambda it: (-it[1], -it[0]))
    x = y = 0
    row_h = 0
    gutter = 2
    for w, h, key in items:
        if x + w + gutter > RES:
            y += row_h + gutter
            x = 0
            row_h = 0
        if y + h > RES:
            raise RuntimeError(f"UV atlas 溢出：{key}")
        rects[key] = (x, y, x + w, y + h)
        x += w + gutter
        row_h = max(row_h, h)
    for name, _, _, _, _, _, _, _, _ in ALL_CUBES:
        if name.endswith("_r"):
            for face in FACES:
                rects[(name, face)] = rects[(name[:-2] + "_l", face)]
    return rects


RECTS = None


# ---------------------------------------------------------------- 像素画笔
def px(d, x, y, c):
    if 0 <= x < RES and 0 <= y < RES:
        d.point((x, y), fill=c)


def paint_scales(d, r, pal, seed, light_top=True):
    x0, y0, x1, y1 = r
    w, h = x1 - x0, y1 - y0
    rng = random.Random(seed)
    for yy in range(h):
        vt = yy / max(1, h - 1)
        base_t = vt if light_top else 1 - vt
        row_phase = (yy // 3) * 2
        seam = (yy % 3 == 2)
        for xx in range(w):
            t = base_t + rng.uniform(-0.04, 0.04)
            if seam:
                t += 0.18
            elif (xx + row_phase) % 4 == 0:
                t += 0.30
            elif (xx + row_phase) % 4 == 1 and yy % 3 == 0:
                t -= 0.12
            px(d, x0 + xx, y0 + yy, ramp(pal, min(1, max(0, t))))


def paint_plates(d, r, seed):
    x0, y0, x1, y1 = r
    w, h = x1 - x0, y1 - y0
    rng = random.Random(seed)
    for yy in range(h):
        band, row = divmod(yy, 5)
        for xx in range(w):
            t = 0.38 + 0.08 * ((xx // 10 + band) % 2) + rng.uniform(-0.05, 0.05)
            if row == 0:
                t += 0.10
            elif row == 4:
                t -= 0.16
            elif (xx + band * 3) % 5 == 2:
                t -= 0.08
            px(d, x0 + xx, y0 + yy, ramp(BELLY, min(1, max(0, t))))


def paint_membrane(d, r, seed):
    x0, y0, x1, y1 = r
    w, h = x1 - x0, y1 - y0
    rng = random.Random(seed)
    for yy in range(h):
        for xx in range(w):
            c = hx(MEMB[1]) if (xx // 2 + yy // 2) % 3 else hx(MEMB[2])
            if rng.random() < 0.16:
                c = hx(MEMB[0])
            if rng.random() < 0.06:
                c = hx(MEMB[3])
            px(d, x0 + xx, y0 + yy, c)
    if w >= 5 and h >= 3:
        for _ in range(2):
            xx, yy = 0, rng.randrange(max(1, h - 1))
            while xx < w and 0 <= yy < h:
                px(d, x0 + xx, y0 + yy, hx(EMBER[3] if rng.random() < 0.6 else EMBER[2]))
                px(d, x0 + min(xx + 1, w - 1), y0 + yy, hx(EMBER[3]))
                xx += rng.randint(2, 3)
                if rng.random() < 0.55:
                    yy += rng.choice((-1, 1))
    elif rng.random() < 0.5:
        px(d, x0 + rng.randrange(w), y0 + rng.randrange(h), hx(EMBER[3]))


def paint_horn(d, r, seed):
    x0, y0, x1, y1 = r
    w, h = x1 - x0, y1 - y0
    rng = random.Random(seed)
    for yy in range(h):
        vt = yy / max(1, h - 1)
        band = yy % 3
        t = 0.15 + vt * 0.45 + (0.0 if band == 1 else 0.12)
        c = ramp(HORN, min(1, t + rng.uniform(-0.03, 0.03)))
        for xx in range(w):
            px(d, x0 + xx, y0 + yy, c)


def paint_claw(d, r, seed):
    x0, y0, x1, y1 = r
    for yy in range(y1 - y0):
        c = ramp(HORN, yy / max(1, y1 - y0 - 1) * 0.7)
        for xx in range(x1 - x0):
            px(d, x0 + xx, y0 + yy, c)


def paint_spike(d, r, seed, ember_tip=True):
    x0, y0, x1, y1 = r
    w, h = x1 - x0, y1 - y0
    rng = random.Random(seed)
    for yy in range(h):
        c = ramp(SPIKE, yy / max(1, h - 1) + rng.uniform(-0.03, 0.03))
        for xx in range(w):
            cc = _mix(c, 0.10) if xx == w // 2 else c
            px(d, x0 + xx, y0 + yy, cc)
    if ember_tip and h >= 2:
        for xx in range(w):
            px(d, x0 + xx, y0, hx(EMBER[3]))


def paint_glow(d, r, seed):
    x0, y0, x1, y1 = r
    w, h = x1 - x0, y1 - y0
    cx, cy = (w - 1) / 2, (h - 1) / 2
    for yy in range(h):
        for xx in range(w):
            dist = ((xx - cx) ** 2 + (yy - cy) ** 2) ** 0.5 / max(1.0, (w + h) / 4)
            px(d, x0 + xx, y0 + yy, ramp(EMBER, min(1, dist * 0.85)))


def paint_mouth(d, r, seed):
    x0, y0, x1, y1 = r
    w, h = x1 - x0, y1 - y0
    cx, cy = (w - 1) / 2, (h - 1) / 2
    for yy in range(h):
        for xx in range(w):
            dist = ((xx - cx) ** 2 + (yy - cy) ** 2) ** 0.5 / max(1.0, max(w, h) / 2)
            px(d, x0 + xx, y0 + yy, ramp(EMBER, 0.5 + dist * 0.5) if dist < 0.65 else hx(MEMB[3]))


def paint_teeth(d, r, seed):
    x0, y0, x1, y1 = r
    w, h = x1 - x0, y1 - y0
    for yy in range(h):
        for xx in range(w):
            c = hx(TEETH[0]) if yy == 0 else hx(TEETH[1]) if yy < h - 1 else hx(TEETH[2])
            if xx == w // 2 and w >= 2:
                c = hx(TEETH[2])
            px(d, x0 + xx, y0 + yy, c)


def paint_snoutfront(d, r, seed):
    x0, y0, x1, y1 = r
    paint_scales(d, r, HIDE, seed)
    w, h = x1 - x0, y1 - y0
    if w >= 2 and h >= 4:
        py = y0 + h - 2
        px(d, x0, py, hx(EMBER[2]))
        px(d, x0 + w - 1, py, hx(EMBER[2]))


def paint_jawfront(d, r, seed):
    x0, y0, x1, y1 = r
    paint_scales(d, r, HIDE, seed)
    for xx in range(x1 - x0):
        if xx % 2 == 0:
            px(d, x0 + xx, y0, hx(TEETH[0]))


PAINTERS = {
    "hide": lambda d, r, s: paint_scales(d, r, HIDE, s),
    "plates": lambda d, r, s: paint_plates(d, r, s),
    "membrane": lambda d, r, s: paint_membrane(d, r, s),
    "horn": lambda d, r, s: paint_horn(d, r, s),
    "claw": lambda d, r, s: paint_claw(d, r, s),
    "spike": lambda d, r, s: paint_spike(d, r, s),
    "glow": lambda d, r, s: paint_glow(d, r, s),
    "mouth": lambda d, r, s: paint_mouth(d, r, s),
    "teeth": lambda d, r, s: paint_teeth(d, r, s),
    "snoutfront": lambda d, r, s: paint_snoutfront(d, r, s),
    "jawfront": lambda d, r, s: paint_jawfront(d, r, s),
}


def _ao_ring(img, d, r, k=0.22):
    x0, y0, x1, y1 = r
    for xx in range(x0, x1):
        for y in (y0, y1 - 1):
            if 0 <= xx < RES and 0 <= y < RES:
                d.point((xx, y), fill=_mix(img.getpixel((xx, y)), -k))
    for yy in range(y0, y1):
        for x in (x0, x1 - 1):
            if 0 <= x < RES and 0 <= yy < RES:
                d.point((x, yy), fill=_mix(img.getpixel((x, yy)), -k))


def paint_atlas(rects, extra=None):
    img = Image.new("RGBA", (RES, RES), MAGENTA)
    d = ImageDraw.Draw(img)
    for (name, face), r in rects.items():
        if name == "memwing":
            continue  # 蹼膜大矩形在后面单独画（世界锁定 UV 的面片共享它）
        cube = next(c for c in ALL_CUBES if c[0] == name)
        _, _, mat, _, _, roles, _, _, _ = cube
        role = roles.get(face, mat)
        if mat == "horn" and role == "horn" and "claw" in name:
            role = "claw"
        seed = zlib.crc32(f"{name}/{face}".encode()) & 0xFFFF
        if role == "hide" and face == "down":
            paint_scales(d, r, HIDE_DK, seed)
        else:
            PAINTERS[role](d, r, seed)
        if role not in ("glow", "mouth"):
            _ao_ring(img, d, r)
    for key, r in (extra or {}).items():
        paint_membrane(d, r, zlib.crc32(f"{key[1]}".encode()) & 0xFFFF)
        _ao_ring(img, d, r, 0.15)
    for (x0, y0, x1, y1) in list(rects.values()) + list((extra or {}).values()):
        if x0 - 1 >= 0:
            d.line([(x0 - 1, y0), (x0 - 1, y1 - 1)], fill=img.getpixel((x0, y0)))
        if x1 < RES:
            d.line([(x1, y0), (x1, y1 - 1)], fill=img.getpixel((x1 - 1, y0)))
        if y0 - 1 >= 0:
            d.line([(x0, y0 - 1), (x1 - 1, y0 - 1)], fill=img.getpixel((x0, y0)))
        if y1 < RES:
            d.line([(x0, y1), (x1 - 1, y1)], fill=img.getpixel((x0, y1 - 1)))
    return img


# ---------------------------------------------------------------- MCP 客户端
class MCP:
    def __init__(self):
        self.proc = subprocess.Popen(
            [NODE, MCP_ENTRY, "--root", ROOTS[0], "--root", ROOTS[1]],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8")
        self.next_id = 1

    def call(self, tool, args, timeout=300):
        rid = self.next_id
        self.next_id += 1
        req = {"jsonrpc": "2.0", "id": rid, "method": "tools/call",
               "params": {"name": tool, "arguments": args}}
        self.proc.stdin.write(json.dumps(req) + "\n")
        self.proc.stdin.flush()
        t0 = time.time()
        while time.time() - t0 < timeout:
            line = self.proc.stdout.readline()
            if not line:
                raise RuntimeError(f"MCP 流中断（{tool}）")
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if msg.get("id") == rid:
                if msg.get("error"):
                    raise RuntimeError(f"{tool} 错误: {msg['error']}")
                result = msg["result"]
                if result.get("isError"):
                    text = "\n".join(c.get("text", "") for c in result.get("content", []))
                    raise RuntimeError(f"{tool} 失败: {text}")
                return result
        raise TimeoutError(f"{tool} 超时 {timeout}s")

    def text(self, result):
        return "\n".join(c.get("text", "") for c in result.get("content", []) if c.get("type") == "text")

    def close(self):
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=10)
        except Exception:
            self.proc.kill()


# ---------------------------------------------------------------- 蹼膜 mesh 构建
# ---------------------------------------------------------------- 动画
def anim_ops():
    ops = []
    kf = lambda a, b, c, t, v: ops.append({"op": "set_keyframe", "animation": a, "bone": b,
                                           "channel": c, "time": t, "value": v})
    ops.append({"op": "add_animation", "name": "animation.hell_dragon.idle_hover",
                "length": 3.0, "loop": "loop", "snapping": 24})
    A = "animation.hell_dragon.idle_hover"
    for t, y in [(0, 0), (1.5, 1.2), (3.0, 0)]:
        kf(A, "root", "position", t, [0, y, 0])
    for t, rz in [(0, 12), (0.75, -7), (1.5, -14), (2.25, 2), (3.0, 12)]:
        kf(A, "wing_l", "rotation", t, [0, 0, rz])
        kf(A, "wing_r", "rotation", t, [0, 0, -rz])
    for t, rz in [(0, 7), (0.75, -4), (1.5, -9), (2.25, 0), (3.0, 7)]:
        kf(A, "wing_fore_l", "rotation", t, [0, 0, rz])
        kf(A, "wing_fore_r", "rotation", t, [0, 0, -rz])
    for t, ry in [(0, 5), (1.5, -5), (3.0, 5)]:
        for i in range(1, 7):
            k = 1 + 0.25 * (i - 1)
            kf(A, f"tail_{i}", "rotation", t, [0, ry * k, 0])
    for t, rx in [(0, 2), (1.5, -3), (3.0, 2)]:
        for i in range(1, 6):
            kf(A, f"neck_{i}", "rotation", t, [rx * (1 if i % 2 else -1) * 0.7, 0, 0])
    ops.append({"op": "add_animation", "name": "animation.hell_dragon.wing_flap",
                "length": 1.4, "loop": "loop", "snapping": 24})
    B = "animation.hell_dragon.wing_flap"
    for t, rz, fe, hd in [(0, -30, 12, 9), (0.35, 15, -7, -6), (0.7, 28, -11, -9),
                          (1.05, 8, -2, -2), (1.4, -30, 12, 9)]:
        kf(B, "wing_l", "rotation", t, [0, 0, rz])
        kf(B, "wing_r", "rotation", t, [0, 0, -rz])
        kf(B, "wing_fore_l", "rotation", t, [0, 0, fe])
        kf(B, "wing_fore_r", "rotation", t, [0, 0, -fe])
        kf(B, "wing_hand_l", "rotation", t, [0, 0, hd])
        kf(B, "wing_hand_r", "rotation", t, [0, 0, -hd])
    ops.append({"op": "add_animation", "name": "animation.hell_dragon.roar",
                "length": 2.4, "loop": "once", "snapping": 24})
    C = "animation.hell_dragon.roar"
    for t, rx in [(0, 0), (0.5, -38), (1.4, -32), (2.4, 0)]:
        kf(C, "jaw", "rotation", t, [rx, 0, 0])
    for t, r1, r2, r3, r4 in [(0, 0, 0, 0, 0), (0.6, 10, 8, 6, 4), (1.5, 8, 6, 5, 3), (2.4, 0, 0, 0, 0)]:
        for i, rv in enumerate((r1, r2, r3, r4), 1):
            kf(C, f"neck_{i}", "rotation", t, [rv, 0, 0])
    for t, rz in [(0, 12), (0.6, -40), (1.5, -36), (2.4, 12)]:
        kf(C, "wing_l", "rotation", t, [0, 0, rz])
        kf(C, "wing_r", "rotation", t, [0, 0, -rz])
    return ops


# ---------------------------------------------------------------- 主流程
def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    global RECTS
    RECTS = build_rects(MEM_EXTRA)
    img = paint_atlas(RECTS, {k: RECTS[k] for k in MEM_EXTRA})
    img.save(TEX_PNG)
    n_cubes = len(ALL_CUBES)
    span = (max(c[4][0] for c in ALL_CUBES) - min(c[3][0] for c in ALL_CUBES)) * S
    length = (max(c[4][2] for c in ALL_CUBES) - min(c[3][2] for c in ALL_CUBES)) * S
    print(f"[tex] {TEX_PNG}  {RES}x{RES}, {len(RECTS)} 个 UV 矩形")
    print(f"[geo] {n_cubes} 方块, 翼展 {span:.0f}, 体长 {length:.0f} 单位")

    buf = io.BytesIO()
    img.save(buf, "PNG")

    mcp = MCP()
    try:
        r = mcp.call("bbmodel_create",
                     {"file": MODEL, "format": "free", "name": "hell_dragon",
                      "box_uv": False, "resolution": {"width": RES, "height": RES},
                      "overwrite": True})
        print("[create] ok")
        r = mcp.call("bbmodel_add_texture",
                     {"file": MODEL, "image": TEX_PNG.replace("\\", "/"), "name": TEX_NAME})
        print("[texture] ok")

        ops = []
        for n, p, o in ALL_GROUPS:
            g = {"op": "add_group", "name": n, "origin": [scaled(v) for v in o]}
            if p:
                g["parent"] = p
            ops.append(g)
        mem_uv = {}
        rx0, ry0, rx1, ry1 = RECTS[("memwing", "l")]
        for (nm, grp, x0d, z0d, x1d, z1d) in _MEM_CELLS:
            for side in ("_l", "_r"):
                for face in FACES:
                    u0 = rx0 + (scaled(x0d) - MEM_BBOX[0])
                    v0 = ry0 + (scaled(z0d) - MEM_BBOX[1])
                    u1 = rx0 + (scaled(x1d) - MEM_BBOX[0])
                    v1 = ry0 + (scaled(z1d) - MEM_BBOX[1])
                    mem_uv[(nm.replace("_l", side), face)] = (u0, v0, u1, v1)
        for name, group, mat, f, t, roles, inflate, rot, origin in ALL_CUBES:
            fs, ts = [scaled(v) for v in f], [scaled(v) for v in t]
            faces = {}
            for face in FACES:
                x0, y0, x1, y1 = mem_uv.get((name, face), RECTS[(name, face)])
                faces[face] = {"uv": [round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2)],
                               "texture": TEX_NAME}
            op = {"op": "add_cube", "name": name, "parent": group, "from": fs, "to": ts,
                  "faces": faces}
            op["origin"] = [scaled(v) for v in origin] if origin else [
                (fs[0] + ts[0]) / 2, (fs[1] + ts[1]) / 2, (fs[2] + ts[2]) / 2]
            if rot:
                op["rotation"] = list(rot)
            if inflate:
                op["inflate"] = inflate
            ops.append(op)
        # 蹼膜面片（零厚度平面，含镜像）
        for (nm, grp, x0d, z0d, x1d, z1d) in _MEM_CELLS:
            for side in ("_l", "_r"):
                sgn = 1 if side == "_l" else -1
                nm2 = nm if side == "_l" else nm.replace("_l", "_r")
                grp2 = grp if side == "_l" else grp.replace("_l", "_r")
                xa, xb = sorted((scaled(x0d) * sgn, scaled(x1d) * sgn))
                faces2 = {}
                for face in FACES:
                    u0, v0, u1, v1 = mem_uv[(nm2, face)]
                    faces2[face] = {"uv": [round(u0, 2), round(v0, 2), round(u1, 2), round(v1, 2)],
                                    "texture": TEX_NAME}
                ops.append({"op": "add_cube", "name": nm2, "parent": grp2,
                            "from": [xa, scaled(57), scaled(z0d)], "to": [xb, scaled(57), scaled(z1d)],
                            "faces": faces2})
        ops.append({"op": "set_model_properties", "name": "hell_dragon",
                    "model_identifier": "hell_dragon",
                    "resolution": {"width": RES, "height": RES}})
        ops += anim_ops()
        for i in range(0, len(ops), 400):
            r = mcp.call("bbmodel_edit", {"file": MODEL, "operations": ops[i:i + 400]})
            print(f"[edit {i // 400}] 已应用 {len(ops[i:i + 400])} 个操作")
    finally:
        mcp.close()


if __name__ == "__main__":
    main()
