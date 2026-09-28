"""白衬衫 + 半身裙：以「[无动画共享]映素2.5代-女性标准体型v3.7」为基底换装。

    python shirt_skirt_girl/build_shirt_skirt_girl.py

读 人工建模参考/人物/[无动画共享]映素2.5代-女性标准体型v3.7.bbmodel，身体几何**原样保留**
（140 个方块、组层级、贴图 0 都不动），只在外面加两层衣服 + 一张衣服自己的贴图。

衬衫 Shirt（挂 UpperBody 下）
    躯干原本的方块各自向外扩 0.22~0.24 单位当外壳，所以衣服是贴着身体的形状长的，
    不是另画的方盒子 —— 肩的斜度、胸型、腰、臀的曲线全部继承。袖子放在 LeftArm /
    RightArm 里（与手臂同一套局部坐标），手臂那 ±13° 外张自动带着袖子转。领子 = 围
    脖的领座（四片）+ 两片压在胸斜面上的领尖；胸前一条门襟（三颗扣）+ 一个胸袋。

半身裙 Skirt（挂 UpBody 下）
    16 片裙片，每片是「先按外倾角在本地倾斜（方块自己的 rx）、再由父组绕中轴 yaw 转到
    位」的嵌套组 —— 和参考模型里发簇的做法一样，这样才既有外倾角又有环向角。片宽按相邻
    片的最大间距 + 0.25 取，互相搭接压住缝。断面用**超椭圆**（指数 5）而不是正圆：身体
    的胯是方的（x 半宽 3.76 / z 半深 2.03），正圆在正后方会鼓成桶。奇数片朝轴心收
    0.13 = 褶谷，配贴图上「暗-亮-暗」的折面明暗。腰头 / 褶线 / 裙摆线全画在贴图上。

衣长/裙长：裙腰 y 23.3（自然腰线），裙摆 y 12.9（大腿中上，膝盖在 9.5）。

贴图：衣服放在新的 texture 1（512×512，只用左上角，其余留白，PNG 压得很小）；基底那
66 张贴图一张没删，想换发色还能用。格式/贴图读写约定与仓库其它模型一致：逐面 uv，v 向
下、从外侧看正立不镜像；正面朝 -Z。

自检（跑完打印）：
  * uv 宽高比 vs 面真实宽高比（> 8% 报警）；
  * 每片裙片沿径向往外看，对身体每个高度层的净空（负值 = 身体戳出裙子）；
  * 全模型共面 z-fighting 与基底的差集（只关心新增的）。
"""
from __future__ import annotations

import base64
import copy
import io
import json
import math
import os
import random
import sys
import uuid

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.dont_write_bytecode = True                      # 别把 __pycache__ 带进仓库
# 模型目录在仓库里的深度不固定（人物/、兵器/……），向上找仓库根
ROOT = HERE
while not os.path.isfile(os.path.join(ROOT, "tools", "bbmodel_kit.py")):
    parent = os.path.dirname(ROOT)
    if parent == ROOT:
        raise SystemExit(f"找不到仓库根（含 tools/bbmodel_kit.py 的目录）：{HERE}")
    ROOT = parent
sys.path.insert(0, os.path.join(ROOT, "tools"))     # 共享的 bbmodel_kit.py
from bbmodel_kit import V, rot_ZYX, walk_groups, coplanar_conflicts  # noqa: E402

BASE = os.path.join(ROOT, "人工建模参考", "人物",
                    "[无动画共享]映素2.5代-女性标准体型v3.7.bbmodel")
MODEL_NAME = "shirt_skirt_girl"
OUT_BBMODEL = os.path.join(HERE, f"{MODEL_NAME}.bbmodel")
OUT_PNG = os.path.join(HERE, f"{MODEL_NAME}.png")

# --- 尺寸（单位 = 1/16 格；正面朝 -Z，与基底相同）---------------------------
D = 0.24              # 衬衫布料离身体的距离（肩、胸、脊柱这些露在外面的）
D_CHEST = 0.16        # 胸箱：往下探进裙腰，得收一点
D_LOW = 0.06          # 腰/腹/臀：整个藏在裙子里的那几块，贴紧一点（裙腰才收得进去）
BUST_D = 0.16         # 胸前两片斜板的外扩
SKIRT_TOP = 22.55     # 裙腰上沿。必须低于胸板最低点（22.63）—— 身体胸宽到 x 3.42，
                      # 裙子腰围只有 2.85，腰头再高就会从裙子侧上方戳出来
SKIRT_HEM = 12.90     # 裙摆高度（大腿中上；膝盖在 y≈9.5）
# 裙腰半径要同时满足：罩住衬衫下摆外壳（x 2.58 / z 2.56），又别撞上垂下来的手臂
# （手掌内侧只有 4.36，小臂在腰高处 3.48）。往下靠外倾角让开胯（最宽 3.758）。
A_TOP, B_TOP = 2.80, 2.73     # 裙腰断面半径（X 半宽 / Z 半深）
A_HEM, B_HEM = 4.30, 3.40     # 裙摆断面半径
SUP_P = 7.0           # 超椭圆指数（2 = 椭圆，越大越接近矩形）—— 身体腰胯都是方的，
                      # 指数小了裙腰的「角」会让腰角戳出来（实测 -0.16）
GAP_TOP = 0.10        # 裙腰离身体表面留多少（布不贴皮，但也不能虚浮）
GAP_BODY = 0.10       # 裙身各处对身体的净空
MIN_TOP_R = 2.55      # 裙腰半径下限，免得在细腰处收得太紧
WAIST_Y0 = 21.9       # 定「腰围」时看的高度带：y 21.9 ~ 裙腰上沿
FLARE = 1.35          # 从腰到摆再往外放多少（A 字的幅度）
N_PLEAT = 24          # 片数越多越像一整圈布，少了就是一排贴上去的矩形
PLEAT_T = 0.16        # 布厚（薄一点才塞得进手掌和胯之间，也不容易看出「一片片」）
PLEAT_INSET = 0.02    # 奇数片收进轴心这么多 = 褶谷
PLEAT_OVERLAP = 0.25  # 相邻片搭接量

PX = 10               # 细节贴图：1 单位 = 10 像素

# 基底带了 66 张贴图（只有第 0 张被方块引用，其余是白毛/黑毛/红毛…配色表）。
# 默认只留用得到的两张：文件 4.0 MB → ~150 KB，可以直接用 Blockbench 网页版打开对照，
# 也不用把 4 MB 塞进 git。想留着配色表就把这个开关打开（参考文件里那份一份不少）。
KEEP_UNUSED_BASE_TEXTURES = False

# 基底贴图里方块 uv 只用到 0..271，右边整条是空的 —— 衣服画在 x >= 276 这一带。
TEX_X0 = 276

# 丸子头：去掉这两组「长条散发」，其余发片保留（顶盖 + 刘海）。
HAIR_GROUPS = ("HairFemaleH_Matching", "SideDownHairC", "SideHairA")   # 算金发蒙版的范围
HAIR_STRANDS_TO_REMOVE = ("SideDownHairC", "SideHairA")                # 丸子头不需要的长散发
# 后脑那两片大后发：收短收薄，改成贴着后脑勺的盘发（丸子头不该带波波头的后发坨）
HAIR_RESHAPE = ((("from", (-3.0, 30.2, 4.22), (3.0, 36.2, 5.23)),
                 (-3.0, 30.2, 3.60), (3.0, 35.0, 4.60)),
                (("from", (-4.0, 29.2, 3.22), (4.0, 36.2, 4.23)),
                 (-3.8, 29.6, 3.50), (3.8, 34.4, 4.30)))
# 金发色阶：按原发丝的亮度重映射（保留原来的明暗结构，只换色调）
BLONDE_RAMP = ((0.00, (96, 66, 34)), (0.35, (172, 128, 64)),
               (0.70, (216, 176, 100)), (1.00, (248, 228, 168)))


def blonde_of(t):
    t = min(1.0, max(0.0, t))
    for i in range(len(BLONDE_RAMP) - 1):
        a, ca = BLONDE_RAMP[i]
        b, cb = BLONDE_RAMP[i + 1]
        if t <= b:
            k = (t - a) / max(1e-6, b - a)
            return tuple(ca[j] + (cb[j] - ca[j]) * k for j in range(3))
    return BLONDE_RAMP[-1][1]

WHITE = (247, 247, 245)
WHITE_SHADE = (232, 233, 232)
NAVY = (46, 56, 84)
NAVY_DARK = (34, 43, 67)
NAVY_LIGHT = (63, 75, 108)
BUTTON = (226, 226, 224)
SEAM = (206, 208, 210)

FACES = ("north", "east", "south", "west", "up", "down")


def face_size(face, frm, to):
    dx, dy, dz = to[0] - frm[0], to[1] - frm[1], to[2] - frm[2]
    return {"north": (dx, dy), "south": (dx, dy), "east": (dz, dy),
            "west": (dz, dy), "up": (dx, dz), "down": (dx, dz)}[face]


# ===========================================================================
# 贴图：自排货架，按 (material, w, h) 去重
# ===========================================================================
def _weave(cv, r, base, amp, key):
    """平铺布料：极轻的 2px 周期明暗，避免大片死白/死蓝。"""
    x, y, w, h = r
    rng = random.Random(f"{key}{w}x{h}")
    for j in range(h):
        for i in range(w):
            n = rng.uniform(-amp, amp) + (amp * 0.5 if (i + j) % 2 else -amp * 0.5)
            cv[y + j, x + i, :3] = np.clip(np.array(base, float) + n, 0, 255)


def paint_navy_edge(cv, r, key):
    """褶片的侧边/内侧：比正面再深一号。不然亮光下每片侧面都会反成一条白线。"""
    _weave(cv, r, tuple(int(c * 0.72) for c in NAVY), 4.0, "navyedge")


def paint_white(cv, r, key):
    _weave(cv, r, WHITE, 3.0, "white")


def paint_navy(cv, r, key):
    _weave(cv, r, NAVY, 4.5, "navy")


def paint_pleat(cv, r, key):
    """裙片外面：上端腰头（深一号，上沿一道亮线），中间平铺藏青 + 一条褶棱暗线，
    下端裙摆一道浅影。第一版把折面画成「暗-亮-暗」高对比渐变，两个渲染器里都变成
    亮条纹了 —— 褶子交给几何（奇偶片半径差）更干净，贴图只留一点点明暗。"""
    x, y, w, h = r
    band = int(round(1.15 * PX))
    for j in range(h):
        for i in range(w):
            t = i / max(1, w - 1)
            col = np.array(NAVY, float) + (-7 + 15 * t)          # 一点点侧光
            if j < band:
                col = np.array(NAVY_DARK, float) + (26 if j < 2 else 0)
            elif j < band + 2:
                col = np.array(NAVY_DARK, float) + 5             # 腰头下沿的影
            if i < 2:                                            # 褶棱
                col = np.array(col) - 9
            if j >= h - 3:
                col = np.array(col) - (16 if j >= h - 1 else 9)  # 裙摆边
            cv[y + j, x + i, :3] = np.clip(col + random.Random(f"pl{i}{j}").uniform(-2, 2),
                                           0, 255)


def paint_hair(cv, r, key):
    """丸子头用的头发块：金色 + 一点点上下渐变，做出球面的感觉。"""
    x, y, w, h = r
    for j in range(h):
        t = 0.42 + 0.5 * (1.0 - j / max(1, h - 1))
        col = np.array(blonde_of(t), float)
        for i in range(w):
            cv[y + j, x + i, :3] = np.clip(col + random.Random(f"hb{i}{j}").uniform(-6, 6),
                                           0, 255)


def paint_chestfront(cv, r, key):
    """整块前胸：中缝门襟 + 三颗扣子 + 左胸袋（都画在贴图上，不再单独凸板子）。
    u 方向：u1 在 +x 侧，所以「模特左胸」= 贴图右半边（u 大的一侧）。"""
    _weave(cv, r, WHITE, 3.0, "chestfront")
    x, y, w, h = r
    mid = w // 2
    for j in range(h):                          # 门襟：一道压边线 + 一条浅影
        cv[y + j, x + mid] = (*SEAM, 255)
        cv[y + j, x + mid + 1, :3] = np.clip(np.array(WHITE, float) - 8, 0, 255)
    for fy in (0.24, 0.5, 0.76):                # 扣子（在压边线右侧一点，像真的扣位列）
        cy = int(round(h * fy))
        for j in range(cy - 2, cy + 3):
            for i in range(mid - 1, mid + 4):
                d = math.hypot(i - mid - 1.5, j - cy)
                if d > 2.3:
                    continue
                cv[y + j, x + i, :3] = np.array(
                    BUTTON if d > 1.3 else (203, 204, 205), float)
    # 左胸袋（贴图右半边）
    px0, px1 = int(w * 0.72), int(w * 0.93)
    py0, py1 = int(h * 0.44), int(h * 0.86)
    for i in range(px0, px1 + 1):
        cv[y + py0, x + i] = (*SEAM, 255)
        cv[y + py0 + 1, x + i, :3] = np.clip(np.array(WHITE, float) - 9, 0, 255)
        cv[y + py1, x + i] = (*SEAM, 255)
    for j in range(py0, py1 + 1):
        cv[y + j, x + px0] = (*SEAM, 255)
        cv[y + j, x + px1] = (*SEAM, 255)


def paint_placket(cv, r, key):
    """门襟：一道压边线 + 三颗扣。"""
    _weave(cv, r, WHITE, 3.0, "placket")
    x, y, w, h = r
    seam = int(round(w * 0.62))
    for j in range(h):
        cv[y + j, x + seam] = (*SEAM, 255)
    for fy in (0.26, 0.52, 0.78):
        cy = int(round(h * fy))
        for j in range(cy - 2, cy + 3):
            for i in range(seam - 2, seam + 2):
                if math.hypot(i - seam + 0.5, j - cy) > 2.2:
                    continue
                cv[y + j, x + i, :3] = np.array(
                    BUTTON if math.hypot(i - seam + 0.5, j - cy) > 1.2 else (205, 206, 206),
                    float)


def paint_pocket(cv, r, key):
    """胸袋：袋口压边 + 缝线。"""
    _weave(cv, r, WHITE, 3.0, "pocket")
    x, y, w, h = r
    flap = max(3, int(round(h * 0.30)))
    for i in range(w):
        cv[y + flap, x + i] = (*SEAM, 255)
        cv[y + h - 1, x + i] = (*SEAM, 255)
    for j in range(flap, h):
        cv[y + j, x] = (*SEAM, 255)
        cv[y + j, x + w - 1] = (*SEAM, 255)


def paint_collar(cv, r, key):
    """领尖：外沿压线 + 下沿一点点厚度阴影。"""
    _weave(cv, r, WHITE, 3.0, "collar")
    x, y, w, h = r
    for j in range(h):
        cv[y + j, x + w - 1] = (*SEAM, 255)
        if w > 2:
            cv[y + j, x + w - 2] = (*WHITE_SHADE, 255)
    for i in range(w):
        cv[y + h - 1, x + i] = (*WHITE_SHADE, 255)


def paint_cuff(cv, r, key):
    """袖口：上沿折线 + 下沿厚度。"""
    _weave(cv, r, WHITE, 3.0, "cuff")
    x, y, w, h = r
    for i in range(w):
        cv[y, x + i] = (*SEAM, 255)
        if h > 2:
            cv[y + 1, x + i, :3] = np.clip(np.array(WHITE, float) - 10, 0, 255)
        cv[y + h - 1, x + i, :3] = np.clip(np.array(WHITE, float) - 6, 0, 255)


PAINTERS = {"white": paint_white, "navy": paint_navy, "navyedge": paint_navy_edge,
            "chestfront": paint_chestfront, "hair": paint_hair, "pleat": paint_pleat,
            "placket": paint_placket, "pocket": paint_pocket,
            "collar": paint_collar, "cuff": paint_cuff}


class Atlas:
    """货架装箱，按 (材质, 宽px, 高px) 去重；分配时立刻画好。"""

    def __init__(self, base=None, x0=0, size=512):
        """base: 基底贴图（RGBA 数组），衣服直接画在它的空白区里；
        x0: 从哪一列开始摆衣服的 rect —— 基底的 uv 只用到 271，右边整条都是空的。"""
        self.size = size
        self.cv = (np.array(base, np.uint8).copy() if base is not None
                   else np.full((size, size, 4), 255, np.uint8))
        self.x0 = x0
        self.rects: dict[tuple, tuple[int, int, int, int]] = {}
        self.mask = np.zeros((size, size), bool)      # 自己画过的像素（判空白用）
        self._x = x0
        self._y = self._row_h = 0

    MIN_PLAIN = 4          # 平铺面料的最小 rect：1px 宽的 rect 在 mipmap 下会被旁边
                           # 的留白染成白色（three.js 那边就是这么把褶片侧边照成白线的）

    def rect(self, mat, w, h, min_size=1):
        w = max(min_size, int(math.floor(w + 0.5)))
        h = max(min_size, int(math.floor(h + 0.5)))
        key = (mat, w, h)
        if key in self.rects:
            return self.rects[key]
        if self._x + w > self.size:
            self._x, self._y, self._row_h = self.x0, self._y + self._row_h + 1, 0
        if self._y + h > self.size:
            raise RuntimeError(f"atlas 装不下 {key}")
        r = (self._x, self._y, w, h)
        self.rects[key] = r
        x, y, _w, _h = r
        self.mask[y:y + _h, x:x + _w] = True
        self._x += w + 1
        self._row_h = max(self._row_h, h)
        PAINTERS[mat](self.cv, r, f"{mat}:{w}x{h}")
        # 基底贴图的空白区 alpha=0（透明），而画笔只写 RGB —— 不补这一下衣服会整片透明
        self.cv[y:y + _h, x:x + _w, 3] = 255
        # 再补一圈 1px 的「clamp 到边缘」的外框（含四个角，8 邻域）：
        #   * 预览渲染器把 uv 矩形按 [u1,u2] 含右端点采样，会多采一列/一行；
        #   * 双线性/mipmap 也会混到旁边。
        # 只要这一圈里有一个透明像素，整张面就会被判成半透明（不写深度）→
        # 身体从裙子里透出来。原来 4 邻域的膨胀漏掉了右下角那一个像素，就是那次 bug。
        e0x, e0y = max(self.x0, x - 1), max(0, y - 1)
        e1x, e1y = min(self.size, x + _w + 1), min(self.size, y + _h + 1)
        ys = np.clip(np.arange(e0y, e1y) - y, 0, _h - 1)
        xs = np.clip(np.arange(e0x, e1x) - x, 0, _w - 1)
        ring = self.cv[y + ys][:, x + xs].copy()
        self.cv[e0y:e1y, e0x:e1x] = ring
        self.cv[e0y:e1y, e0x:e1x, 3] = 255
        self.mask[e0y:e1y, e0x:e1x] = True
        return r

    def rect_units(self, mat, w, h):
        """面片按 1 单位 = 1 像素取 rect。"""
        return self.rect(mat, w, h)

    def rect_px(self, mat, w_px, h_px):
        """细节面：显式像素 rect。"""
        return self.rect(mat, w_px, h_px)

    def extend_edges(self, rounds=16):
        """每个 rect 的边像素一圈圈往外扩（只写还是留白的像素），把四周填成同色。
        只扩一圈不够：裙片侧面那种 4x10 px 的小 rect 在高 mip 级别下还是会被四周的
        白底混进来，渲染出来就是面板边上一条虚线（实测）。"""
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


# ===========================================================================
# 几何
# ===========================================================================
def shell(el, delta, name, color=0):
    """基底方块向外扩 delta 变成衣服外壳（旋转/轴心原样继承）。"""
    c = {"name": name,
         "from": [round(v - delta, 4) for v in el["from"]],
         "to": [round(v + delta, 4) for v in el["to"]],
         "origin": [round(v, 4) for v in el.get("origin", [0, 0, 0])],
         "color": color}
    if el.get("rotation"):
        c["rotation"] = [round(v, 4) for v in el["rotation"]]
    return c


def box(name, frm, to, origin=None, rotation=None, color=0):
    lo = [round(min(a, b), 4) for a, b in zip(frm, to)]
    hi = [round(max(a, b), 4) for a, b in zip(frm, to)]
    c = {"name": name, "from": lo, "to": hi, "color": color,
         "origin": [round(v, 4) for v in (origin if origin is not None else
                                          [(a + b) / 2 for a, b in zip(lo, hi)])]}
    if rotation and any(abs(a) > 1e-9 for a in rotation):
        c["rotation"] = [round(v, 4) for v in rotation]
    return c


def superellipse(a, b, theta, p=SUP_P):
    s, c = math.sin(theta), math.cos(theta)
    fx = math.copysign(abs(s) ** (2.0 / p), s) if abs(s) > 1e-12 else 0.0
    fz = math.copysign(abs(c) ** (2.0 / p), c) if abs(c) > 1e-12 else 0.0
    return a * fx, b * fz


def group_elements(outliner, names):
    """按组名收集（含后代）所有方块 uuid。"""
    hits = {}

    def walk(nodes):
        for ch in nodes:
            if not isinstance(ch, dict):
                continue
            nm = ch.get("name", "")
            if nm in names:
                ids = []

                def grab(node):
                    for c in node.get("children", []):
                        if isinstance(c, str):
                            ids.append(c)
                        elif isinstance(c, dict):
                            grab(c)
                grab(ch)
                hits.setdefault(nm, []).extend(ids)
            walk(ch.get("children", []))
    walk(outliner)
    return hits


def drop_groups(outliner, names, removed=None):
    """从大纲里删掉这些组（连同里面的方块引用），返回删掉的 uuid 集合。
    注意递归要把 same set 传下去 —— 第一版递归丢掉了返回值，组被摘掉了、
    uuid 却没收上来，于是 31 个发条留在了 elements 里没进大纲（校验器会报）。"""
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


def body_slices(tree, n=10):
    """把身体（含方块自身旋转）切成薄片，供「按身体轮廓给裙子定半径」和净空自检用。"""
    out = []
    def walk(node, R, t, in_arms):
        local = node.get("rotation")
        R_l = rot_ZYX(*local) if local else np.eye(3)
        o = V(*node["origin"])
        R_n, t_n = R @ R_l, t + R @ ((np.eye(3) - R_l) @ o)
        for c in node.get("cubes") or []:
            cl = c.get("rotation")
            cl = rot_ZYX(*cl) if cl else np.eye(3)
            oc = V(*c.get("origin", (0, 0, 0)))
            Rc, tc = R_n @ cl, t_n + R_n @ ((np.eye(3) - cl) @ oc)
            frm, to = V(*c["from"]), V(*c["to"])
            bucket = out
            for i in range(n):
                y0 = frm[1] + (to[1] - frm[1]) * i / n
                y1 = frm[1] + (to[1] - frm[1]) * (i + 1) / n
                bucket.append(("arm" if in_arms else "body",
                               np.array([Rc @ V(x, y, z) + tc
                                         for x in (frm[0], to[0]) for y in (y0, y1)
                                         for z in (frm[2], to[2])])))
        for ch in node.get("children") or []:
            walk(ch, R_n, t_n, in_arms or node.get("name") == "Arms")
    walk(tree, np.eye(3), np.zeros(3), False)
    return out


def support(slices, kind, d, y, y_hi=None):
    """该高度层（或 y..y_hi 这一带）里身体/手臂沿 d 的最大支撑值。"""
    best = -9e9
    for k, corners in slices:
        if k != kind:
            continue
        lo = corners[:, 1].min() - 1e-6
        hi = corners[:, 1].max() + 1e-6
        if (y_hi is None and lo > y) or (y_hi is None and hi < y):
            continue
        if y_hi is not None and (lo > y_hi or hi < y):
            continue
        best = max(best, float((corners @ d).max()))
    return best


def pleat_plan(slices):
    """按身体轮廓逐片定半径。
    * 腰那一带：贴着身体 + GAP_TOP 的空隙（布不贴皮，也不虚浮）；
    * 往下：先算这一片方向上下半身最宽处在哪、需要多大半径，反推外倾角；
      再和 FLARE（保证 A 字幅度）取大者。
    这样裙子是「裹着身体长出来的」，而不是拿一个超椭圆硬套 —— 身体腰胯都是方的，
    硬套要么腰角戳出来（实测 -0.16），要么裙腰虚浮。"""
    drop = SKIRT_TOP - SKIRT_HEM
    out = []
    for k in range(N_PLEAT):
        th = 2.0 * math.pi * k / N_PLEAT
        d = np.array([math.sin(th), 0.0, math.cos(th)])
        r_top = max(support(slices, "body", d, WAIST_Y0, SKIRT_TOP) + GAP_TOP
                    + (PLEAT_INSET if k % 2 else 0.0), MIN_TOP_R)
        # 这一片往下要走到多远：身体在下半身各高度的最大需求
        need = 0.0
        y = SKIRT_HEM
        while y <= WAIST_Y0:
            need = max(need, (support(slices, "body", d, y) + GAP_BODY - r_top)
                       / max(0.35, SKIRT_TOP - y))
            y += 0.5
        r_hem = r_top + max(FLARE, need * drop)
        phi = math.degrees(math.atan2(r_hem - r_top, drop))
        out.append({"name": f"Pleat_{k + 1:02d}", "yaw": math.degrees(th), "phi": phi,
                    "r_top": r_top, "r_hem": r_hem,
                    "length": drop / math.cos(math.radians(phi))})
    width = 0.0
    for k in range(N_PLEAT):
        other = (k + 1) % N_PLEAT
        dth = abs(((out[other]["yaw"] - out[k]["yaw"] + 180) % 360) - 180)
        width = max(width,
                    2 * max(out[k]["r_top"], out[other]["r_top"]) * math.sin(math.radians(dth) / 2),
                    2 * max(out[k]["r_hem"], out[other]["r_hem"]) * math.sin(math.radians(dth) / 2))
    for q in out:
        q["width"] = width + PLEAT_OVERLAP
    return out


# ===========================================================================
# 主流程
# ===========================================================================
def main():
    with io.open(BASE, encoding="utf-8") as fh:
        doc = json.load(fh)
    base_outliner = copy.deepcopy(doc["outliner"])
    base_elements = list(doc["elements"])
    by_uuid = {e["uuid"]: e for e in base_elements}
    base_tree = to_tree(base_outliner, base_elements)
    base_conflicts = set(map(str, coplanar_conflicts(base_tree)))

    # Bedrock 实体格式在 Blockbench 里是 single_texture（只认一张贴图）：
    # 新加一张 texture 1 的话，所有衣服面在 GUI 里会被回落成 texture 0 —— 裙子会采到
    # 基底贴图的粉色区（用户截图实测）。所以衣服直接画进基底贴图的空白区，
    # 全模型只留 texture 0 这一张。
    base_tex = Image.open(io.BytesIO(base64.b64decode(
        doc["textures"][0]["source"].split(",", 1)[1]))).convert("RGBA")
    atlas = Atlas(np.asarray(base_tex), x0=TEX_X0)
    new_elements = []
    detail_faces = []        # (方块名, 面, uv宽, uv高, 面宽, 面高) —— 供自检
    arm_extras = {}          # 组名 -> [uuid]（袖子塞进手臂组）
    skirt_groups = []        # 裙片：每个一片，自带 yaw

    def emit(c, faces):
        # box_uv 必须是 False：True 的话 Blockbench / three-blockbench 会**忽略逐面 uv**，
        # 改用 uv_offset 重算盒式 UV（offset 是 [0,0] → 全部采到贴图左上角那片白）。
        # 衣服各面来自贴图不同区域（褶面/门襟/领尖…），盒式 UV 表达不了，只能逐面。
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
            if mat is None:
                el["faces"][face] = {"uv": [0, 0, 1, 1], "texture": 0}
                continue
            w, h = face_size(face, c["from"], c["to"])
            if isinstance(mat, tuple):        # (材质, 放大倍数)：细节面按同样比例取 rect，
                mat, scale = mat              # 宽高比天然对得上
                r = atlas.rect(mat, w * scale, h * scale)
            else:
                r = atlas.rect(mat, w, h, min_size=atlas.MIN_PLAIN)
            x, y, rw, rh = r
            el["faces"][face] = {"uv": [x, y, x + rw, y + rh], "texture": 0}
            if isinstance(faces.get(face, faces.get("all")), tuple):
                detail_faces.append((c["name"], face, rw, rh, w, h))
        new_elements.append(el)
        return el

    # ---- 1. 衬衫躯干：躯干各块外扩当外壳 ---------------------------------
    for uuid_, delta, name in [
            ("83be27fb-9e1d-2c86-d65b-c8f7a6f6a7b5", D, "Shirt_Shoulder_L"),
            ("237cc73b-122a-4f04-bb98-3fe3b931c9d5", D, "Shirt_Shoulder_R"),
            ("d28fe618-b6f4-fef7-6fd8-d070ed0240cc", D_CHEST, "Shirt_Chest"),
            ("1413ec5c-4324-93eb-6cf1-958c8d653d84", D + 0.015, "Shirt_Spine"),
            ("5739873c-9f1c-e9a2-2a2a-3b636d27977a", BUST_D, "Shirt_Bust_L"),
            ("0ebf689c-e0b5-6abf-5740-db7a4a02054b", BUST_D, "Shirt_Bust_R"),
            ("6af77825-44f2-2d7d-bf10-b3e7fdf2e071", D_LOW, "Shirt_Waist"),
            ("fd9d301e-c1d9-e45f-baf2-8ca1794d5b56", D_LOW, "Shirt_Belly"),
            ("399e3521-472f-caaf-6834-93233d967903", D_LOW, "Shirt_Butt")]:
        emit(shell(by_uuid[uuid_], delta, name), {"all": "white"})

    bust_L = by_uuid["5739873c-9f1c-e9a2-2a2a-3b636d27977a"]
    bust_R = by_uuid["0ebf689c-e0b5-6abf-5740-db7a4a02054b"]
    RX = bust_L["rotation"][0]
    R_bust = rot_ZYX(*bust_L["rotation"])
    O_bust = V(*bust_L["origin"])
    n_bust = R_bust @ V(0, 0, -1)                     # 胸斜面外法线 (0, .80, -.60)
    c_local = (V(*bust_L["from"]) + V(bust_L["to"][0], bust_L["to"][1], bust_L["from"][2])) / 2
    chest_face = R_bust @ (c_local - O_bust) + O_bust  # 未外扩时胸斜面中点（世界）

    # ---- 2. 胸口：一整块前面板，把两片胸斜板盖成一整片 ---------------------
    # 基底那两片 ±53° 的胸板各自是一块平板，中间有缝、外沿有棱 —— 穿上衬衫还这样就是
    # 「胸分成两块」。实测两片的**前表面其实共面**（法线都是 (0,.80,-.60)，偏移也一样，
    # ±4°/∓3° 的扭转在法线上正好抵消），所以只要在那一张平面上铺一块横跨左右的整板，
    # 再把胸下那面也铺一整块，胸口就是连续的一整片。门襟和胸袋改成画在贴图上（不再
    # 单独凸一块板子）。
    def plane_panel(name, rot, face, half_len, half_w, proud, color=0):
        """在胸板某个面张成的平面上铺一块整板。
        rot: 整板自己的旋转（决定面朝哪）；face: 取胸板的哪一面 ('north' 前斜 / 'down' 胸下)；
        half_len: 沿斜面方向的半长；half_w: 半宽；proud: 比外扩后的胸面再凸多少。"""
        Rb = rot_ZYX(*bust_L["rotation"])
        n = Rb @ V(0, 0, -1) if face == "north" else Rb @ V(0, -1, 0)
        f, t = V(*bust_L["from"]), V(*bust_L["to"])
        mid = (V(f[0], f[1], f[2]) + V(t[0], t[1], f[2])) / 2 if face == "north"             else (V(f[0], f[1], t[2]) + V(t[0], t[1], t[2])) / 2
        c = Rb @ (mid - V(*bust_L["origin"])) + V(*bust_L["origin"])
        O = V(0.0, c[1], c[2]) + n * (BUST_D + proud)   # 法线无 x 分量：x 取 0 即正中
        return box(name,
                   (O[0] - half_w, O[1] - half_len, O[2] - 0.05),
                   (O[0] + half_w, O[1] + half_len, O[2] + 0.28),
                   origin=O, rotation=rot, color=color)

    CW = 3.60                       # 整板半宽（盖住外扩后的胸板 ±3.58）
    RX_UNDER = RX - 90.0            # 胸下那面的倾角
    emit(plane_panel("Shirt_Chest_Front", (RX, 0, 0), "north", 1.72, CW, 0.05, color=1),
         {"north": ("chestfront", PX), "all": "white"})
    emit(plane_panel("Shirt_Chest_Under", (RX_UNDER, 0, 0), "down", 1.70, CW, 0.05, color=1),
         {"all": "white"})

    # ---- 3. 领座（围脖四片）+ 两片领尖 -----------------------------------
    # 四片的上下沿故意错开 0.04，不然转角处会出现共面面片（z-fighting）
    NB, NZ = 1.95, 1.95
    emit(box("Collar_Band_F", (-NB, 28.70, -NZ - 0.10), (NB, 29.50, -1.55)), {"all": "white"})
    emit(box("Collar_Band_B", (-NB, 28.74, 1.55), (NB, 29.54, NZ + 0.10)), {"all": "white"})
    emit(box("Collar_Band_L", (-NB - 0.10, 28.72, -NZ), (-1.55, 29.52, NZ)), {"all": "white"})
    emit(box("Collar_Band_R", (1.55, 28.76, -NZ), (NB + 0.10, 29.56, NZ)), {"all": "white"})

    # 领尖：贴着领座、从胸口**立起来**往两边垂（rx 比胸斜面小得多 = 不顺着胸滑），
    # 这是真衬衫领子的样子，正面/侧面都看得出是领子。
    for sgn, name in ((-1, "Collar_Flap_L"), (1, "Collar_Flap_R")):
        x_in, x_out = sgn * 0.45, sgn * 2.45
        o = (x_in, 28.55, -2.30)
        emit(box(name, (x_in, 26.85, -2.32), (x_out, 28.55, -2.10),
                 origin=o, rotation=(22, 0, -18 if sgn > 0 else 18), color=3),
             {"north": ("collar", PX), "all": "white"})

    # ---- 5. 短袖 + 袖口（塞进手臂组，跟着 ±13° 转）------------------------
    for gname, ua_uuid, sname, cname in (
            ("LeftArm", "e84da2f9-6c5f-5950-2a48-c8ff88d923ef", "Sleeve_L", "Cuff_L"),
            ("RightArm", "0ccd4641-feb8-0af7-6768-fdde6ca87af4", "Sleeve_R", "Cuff_R")):
        ua = by_uuid[ua_uuid]
        x0, x1 = sorted((ua["from"][0] - 0.25, ua["to"][0] + 0.25))
        z0, z1 = ua["from"][2] - 0.25, ua["to"][2] + 0.25
        s = emit(box(sname, (x0, 25.05, z0), (x1, 28.36, z1)), {"all": "white"})
        c = emit(box(cname, (x0 - 0.10, 24.95, z0 - 0.10), (x1 + 0.10, 25.85, z1 + 0.10)),
                 {"north": ("cuff", PX), "south": ("cuff", PX),
                  "east": ("cuff", PX), "west": ("cuff", PX),
                  "up": "white", "down": "white"})
        arm_extras.setdefault(gname, []).extend([s["uuid"], c["uuid"]])

    # ---- 6. 半身裙 --------------------------------------------------------
    slices = body_slices(to_tree(doc["outliner"], base_elements))
    pleats = pleat_plan(slices)
    for p in pleats:
        el = emit(box(p["name"],
                      (-p["width"] / 2, SKIRT_TOP - p["length"], p["r_top"]),
                      (p["width"] / 2, SKIRT_TOP, p["r_top"] + PLEAT_T),
                      origin=(0, SKIRT_TOP, p["r_top"]), rotation=(-p["phi"], 0, 0),
                      color=5),
                  {"south": ("pleat", PX), "north": "navyedge",
                   "east": "navyedge", "west": "navyedge", "up": "navy", "down": "navy"})
        skirt_groups.append(
            {"name": p["name"], "uuid": str(uuid.uuid4()), "origin": [0, SKIRT_TOP, 0],
             "rotation": [0, round(p["yaw"], 4), 0], "color": 5, "bedrock_binding": "",
             "mirror_uv": False, "isOpen": False, "locked": False, "visibility": True,
             "autouv": 0, "children": [el["uuid"]]})

    # ---- 6b. 头发：金发 + 丸子头 -----------------------------------------
    # 先把「长散发」两组摘掉（丸子头不留披发），再按剩下的发丝贴图区域整体换成金色
    # （按原亮度重映射，明暗结构保留），最后在后脑上方加一颗丸子。
    hair_maps = group_elements(doc["outliner"], HAIR_GROUPS)
    hair_uuid_set = {u for ids in hair_maps.values() for u in ids}
    removed_hair = drop_groups(doc["outliner"], HAIR_STRANDS_TO_REMOVE)
    keep_hair = hair_uuid_set - removed_hair
    for (_, frm, to), nf, nt in HAIR_RESHAPE:                      # 后发收形
        for e in base_elements:
            if (tuple(round(v, 2) for v in e["from"]) == tuple(round(v, 2) for v in frm)
                    and tuple(round(v, 2) for v in e["to"]) == tuple(round(v, 2) for v in to)):
                e["from"], e["to"] = [float(v) for v in nf], [float(v) for v in nt]
                break
    base_elements = [e for e in base_elements if e["uuid"] not in removed_hair]
    print(f"头发：保留 {len(keep_hair)} 块，摘掉 {len(removed_hair)} 块披发")

    # 金发：把发丝面覆盖到的贴图像素按亮度重映射到金色
    hair_mask = np.zeros((atlas.size, atlas.size), bool)
    by_uuid_all = {e["uuid"]: e for e in base_elements}
    for u in keep_hair:
        for data in (by_uuid_all[u].get("faces") or {}).values():
            if "uv" not in data:
                continue
            x0, y0, x1, y1 = (int(v) for v in data["uv"])
            hair_mask[max(0, y0):y1 + 1, max(0, x0):x1 + 1] = True
    sel = hair_mask & (atlas.cv[:, :, 3] > 8)
    lum = (atlas.cv[:, :, 0] * 0.299 + atlas.cv[:, :, 1] * 0.587
           + atlas.cv[:, :, 2] * 0.114) / 255.0
    if sel.any():
        lo, hi = np.percentile(lum[sel], [4, 96])
        t = 0.35 + 0.65 * np.clip((lum - lo) / max(1e-3, hi - lo), 0, 1)
        ramp = np.array([blonde_of(v) for v in (0.0, 0.25, 0.5, 0.75, 1.0)])
        idx = np.clip(t * (len(ramp) - 1), 0, len(ramp) - 1)
        i0 = np.floor(idx).astype(int)
        i1 = np.minimum(i0 + 1, len(ramp) - 1)
        k = (idx - i0)[..., None]
        col = ramp[i0] * (1 - k) + ramp[i1] * k
        atlas.cv[sel, :3] = np.clip(col[sel], 0, 255).astype(np.uint8)
        atlas.mask |= hair_mask            # 别让外扩再动这些像素
    print(f"金发：重上色 {int(sel.sum())} 像素")

    # 丸子：后脑上方一坨圆角块
    bun = [("Bun_Core", (-2.06, 36.5, 0.9), (2.06, 40.5, 5.0)),
           ("Bun_Top", (-1.4, 40.1, 1.8), (1.4, 41.3, 4.1)),
           ("Bun_Bottom", (-1.4, 35.2, 1.8), (1.4, 36.7, 4.1)),
           ("Bun_Left", (-3.0, 37.1, 1.8), (-1.9, 39.9, 4.1)),
           ("Bun_Right", (1.9, 37.1, 1.8), (3.0, 39.9, 4.1)),
           ("Bun_Back", (-1.4, 37.3, 4.7), (1.4, 39.7, 5.9)),
           ("Bun_Front", (-1.4, 37.3, 0.0), (1.4, 39.7, 1.0)),
           ("Bun_TL", (-2.3, 39.1, 1.7), (-1.0, 40.7, 4.2)),      # 四个上角，别成方块塔
           ("Bun_TR", (1.0, 39.1, 1.7), (2.3, 40.7, 4.2)),
           ("Bun_TB", (-1.3, 40.2, 3.55), (1.3, 41.0, 4.95)),
           ("HairTopFill", (-2.6, 36.4, -4.05), (2.6, 38.2, -2.5)),
           # 刘海是几根发条、中间有缝，皮肤会透出来（基底头发是粉色看不出来，
           # 染成金色后就是额头上一条粉带）—— 加一块衬板垫在发条后面
           ("HairFringeBack", (-2.72, 33.2, -4.12), (2.72, 37.4, -3.62))]
    bun_uuids = [emit(box(n, f, t, color=3), {"all": "hair"})["uuid"] for n, f, t in bun]
    doc["outliner"] and insert_children(doc["outliner"], "Head", bun_uuids)

    # ---- 7. 挂回大纲 ------------------------------------------------------
    shirt_uuid = str(uuid.uuid4())
    shirt_children = [e["uuid"] for e in new_elements if e["name"].startswith("Shirt_")]
    shirt_children += [e["uuid"] for e in new_elements if e["name"].startswith("Collar_")]
    shirt_node = {"name": "Shirt", "uuid": shirt_uuid, "origin": [0, 22.2, 0],
                  "rotation": [0, 0, 0], "color": 0, "bedrock_binding": "",
                  "mirror_uv": False, "isOpen": True, "locked": False,
                  "visibility": True, "autouv": 0, "children": shirt_children}
    if not insert_children(doc["outliner"], "UpperBody", [shirt_node]):
        raise RuntimeError("找不到 UpperBody")
    if not insert_children(doc["outliner"], "UpBody", skirt_groups):
        raise RuntimeError("找不到 UpBody")
    for gname, uuids in arm_extras.items():
        if not insert_children(doc["outliner"], gname, uuids):
            raise RuntimeError(f"找不到 {gname}")

    doc["elements"] = base_elements + new_elements
    doc["name"] = "白衬衫半身裙女生"

    # ---- 8. 组的变换写两份（ISSUE.md 第 2 节记过这个坑）--------------------
    # 基底的 4.10 布局只把 origin/rotation 内联在大纲节点上。只认 5.0 的读取器
    # （bb-render / three-blockbench）拿不到组旋转 —— 手臂不张、16 片裙片全部
    # 落在 rest 位置、裙子直接看不见（实测）。所以按 Blockbench 存 5.0 的做法
    # 再写一份顶层 groups 表；Blockbench 自己按 uuid 合并，不会重复。
    groups_table: list[dict] = []

    def collect(nodes):
        for ch in nodes:
            if isinstance(ch, dict) and ch.get("uuid"):
                groups_table.append({k: ch[k] for k in
                                     ("name", "uuid", "origin", "rotation", "color",
                                      "bedrock_binding", "mirror_uv", "autouv")
                                     if k in ch})
                collect(ch.get("children", []))

    collect(doc["outliner"])
    doc["groups"] = groups_table
    print(f"顶层 groups 表：{len(groups_table)} 个组")

    # ---- 9. 贴图与落盘 ----------------------------------------------------
    atlas.extend_edges()                    # 边缘外扩，见 Atlas.extend_edges
    img = atlas.image()
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    png = buf.getvalue()
    # 插到 index 1：基底 66 张贴图全部顺延（它们本来没人引用），
    # 这样新方块统一写 "texture": 1 就指到衣服贴图（追加到末尾会指错）。
    # 贴图 0 换成「基底 + 衣服」合成后的那张，其余全部丢掉（single_texture）
    merged = doc["textures"][0]
    merged["source"] = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
    merged["name"] = f"{MODEL_NAME}.png"
    merged["id"] = "0"
    if not KEEP_UNUSED_BASE_TEXTURES:
        doc["textures"] = [merged]
    else:
        doc["textures"] = [merged] + doc["textures"][1:]
    with open(OUT_PNG, "wb") as fh:
        fh.write(png)
    with open(OUT_BBMODEL, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False)

    print(f"{OUT_BBMODEL}\n新增 {len(new_elements)} 个方块 / {len(skirt_groups)+3} 个组；"
          f"衣服贴图 {len(png)//1024} KB，{len(atlas.rects)} 个 rect")
    verify(doc, new_elements, base_conflicts, base_tree, pleats, detail_faces, atlas)
    return 0


# --- 大纲操作 ---------------------------------------------------------------
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
    """bbmodel 的大纲（元素用 uuid 引用）转成 kit 要的 {cubes, children} 树。"""
    els = {e["uuid"]: e for e in elements}

    def conv(nodes):
        cubes, children = [], []
        for ch in nodes:
            if isinstance(ch, str):
                if ch in els:
                    cubes.append(els[ch])
            elif ch.get("uuid") in els:                 # 5.0 里元素也可能是节点
                cubes.append(els[ch["uuid"]])
            else:
                sub_cubes, sub_children = conv(ch.get("children", []))
                children.append({"name": ch.get("name", "?"),
                                 "origin": ch.get("origin", [0, 0, 0]),
                                 "rotation": ch.get("rotation"),
                                 "cubes": sub_cubes, "children": sub_children})
        return cubes, children
    cubes, children = conv(outliner)
    return {"name": "Root", "origin": [0, 0, 0], "rotation": [0, 0, 0],
            "cubes": cubes, "children": children}


# --- 自检 -------------------------------------------------------------------
def verify(doc, new_elements, base_conflicts, base_tree, pleats, detail_faces, atlas):
    """打印四项自检：uv 宽高比 / 贴图引用 / 裙片净空 / 新增共面冲突。"""
    # 1) 细节面（手画 rect 的那些）uv 宽高比 vs 面真实宽高比；平铺面料不看这个
    degen = [(n, f) for (n, f, uw, uh, dw, dh) in detail_faces if dw < 1e-6 or dh < 1e-6]
    bad = [(n, f, round(uw / uh, 3), round(dw / dh, 3))
           for (n, f, uw, uh, dw, dh) in detail_faces
           if uh > 0 and dw > 1e-6 and dh > 1e-6
           and abs((uw / uh) / (dw / dh) - 1) > 0.08]
    print(f"[1] 细节面 uv 宽高比偏差 >8%：{len(bad)} {bad[:5]}"
          + (f"；退化面 {degen}" if degen else ""))

    # 1b) Bedrock 实体格式是 single_texture：任何一面引用了 texture != 0，
    #     Blockbench 里都会回落成 0（贴图会串）。这条闸就是为那次 bug 加的。
    tex_ids = {f.get("texture") for el in doc["elements"] for f in el["faces"].values()}
    tex_n = len(doc["textures"])
    stray = [el["name"] for el in doc["elements"]
             if any(f.get("texture") != 0 for f in el["faces"].values())]
    print(f"[1b] 全模型引用的贴图编号 {sorted(tex_ids)}（应只有 0）；贴图张数 {tex_n}"
          f"{'；越界方块 ' + str(stray[:5]) if stray else ''}")

    # 1c) 衣服每个面「被采样到的那块贴图」必须完全不透明。
    #     采样按 uv 矩形的 [u1..u2]（含右端）算 —— 预览渲染器就是这么采的；
    #     只要那块里有一个透明像素，整面会被判成半透明（不写深度），身体就会从衣服里
    #     透出来。这条闸对应 rect() 里那圈 clamp 外框。
    cv = atlas.cv
    holes = []
    for el in new_elements:
        for face, data in el["faces"].items():
            x0, y0, x1, y1 = (int(v) for v in data["uv"])
            x0, y0 = max(0, x0), max(0, y0)
            x1, y1 = min(atlas.size, x1 + 1), min(atlas.size, y1 + 1)
            if x1 <= x0 or y1 <= y0:
                continue
            alpha = cv[y0:y1, x0:x1, 3]
            n = int((alpha < 254).sum())
            if n:
                holes.append((el["name"], face, (x0, y0, x1, y1), n))
    print(f"[1c] 衣服面采样区里的透明像素：{len(holes)} 个面有问题 {holes[:5]}")

    # 2) 裙片净空。身体（躯干+腿）必须整块在裙子里面；小臂是垂在裙子外面的，判据换成
    #    「裙面 ≤ 小臂内侧」，这样最多是小臂内侧埋进一点布厚，不会被裙子切开。
    #    注意 walk_groups() 只算组链、不算方块自己的 rotation/origin，这里得自己补上
    #    （基底里髋、腹、臀、胸都是带自身旋转的方块，漏掉就会算出假的穿模）。
    NS = 12
    body, arms = [], []

    def walk(node, R, t, in_arms):
        local = node.get("rotation")
        R_l = rot_ZYX(*local) if local else np.eye(3)
        o = V(*node["origin"])
        R_n, t_n = R @ R_l, t + R @ ((np.eye(3) - R_l) @ o)
        for c in node.get("cubes") or []:
            cl = c.get("rotation")
            cl = rot_ZYX(*cl) if cl else np.eye(3)
            oc = V(*c.get("origin", (0, 0, 0)))
            Rc, tc = R_n @ cl, t_n + R_n @ ((np.eye(3) - cl) @ oc)
            frm, to = V(*c["from"]), V(*c["to"])
            bucket = arms if in_arms else body
            for i in range(NS):
                y0, y1 = frm[1] + (to[1] - frm[1]) * i / NS, frm[1] + (to[1] - frm[1]) * (i + 1) / NS
                bucket.append(np.array([Rc @ V(x, y, z) + tc
                                        for x in (frm[0], to[0]) for y in (y0, y1)
                                        for z in (frm[2], to[2])]))
        for ch in node.get("children") or []:
            walk(ch, R_n, t_n, in_arms or node.get("name") == "Arms")

    walk(base_tree, np.eye(3), np.zeros(3), False)

    def support(slices, d, y):
        best = -9e9
        for corners in slices:
            if corners[:, 1].min() - 1e-6 > y or corners[:, 1].max() + 1e-6 < y:
                continue
            best = max(best, float((corners @ d).max()))
        return best

    def nearest(slices, d, y):
        best = 9e9
        for corners in slices:
            if corners[:, 1].min() - 1e-6 > y or corners[:, 1].max() + 1e-6 < y:
                continue
            best = min(best, float((corners @ d).min()))
        return best

    worst_body, worst_arm = [], []
    for p in pleats:
        yaw = math.radians(p["yaw"])
        d = np.array([math.sin(yaw), 0.0, math.cos(yaw)])
        slope = math.tan(math.radians(p["phi"]))
        lb, la = 9e9, 9e9
        y = SKIRT_HEM
        while y <= SKIRT_TOP:
            r_in = p["r_top"] + (SKIRT_TOP - y) * slope
            lb = min(lb, r_in - support(body, d, y))
            # 手臂：只看落在这片角度扇区里的角点（不然会把对面那条手臂算进来），
            # 埋进布厚多少 = r_out - 角点到轴的距离
            for corners in arms:
                if corners[:, 1].min() - 1e-6 > y or corners[:, 1].max() + 1e-6 < y:
                    continue
                for cx, _, cz in corners:
                    ang = math.degrees(math.atan2(cx, cz))
                    if abs((ang - p["yaw"] + 180) % 360 - 180) > 20.0:
                        continue
                    la = min(la, math.hypot(cx, cz) - (r_in + PLEAT_T))
            y += 0.25
        worst_body.append((p["name"], round(lb, 3)))
        worst_arm.append((p["name"], round(la, 3)))
    mb = min(w[1] for w in worst_body)
    ma = min(w[1] for w in worst_arm)
    tight = [w for w in worst_body if w[1] < 0.1]
    print(f"[2] 裙片对身体净空最小 {mb:.2f}（<0.10 的 {len(tight)} {tight[:4]}）；"
          f"裙面对小臂 {ma:.2f}（负 = 小臂内侧埋进裙布）")

    # 3) 共面 z-fighting：只报新增的
    tree = to_tree(doc["outliner"], doc["elements"])
    new_conf = sorted(set(map(str, coplanar_conflicts(tree))) - base_conflicts)
    print(f"[3] 新增共面冲突：{len(new_conf)}")
    for x in new_conf[:8]:
        print("     ", x)


if __name__ == "__main__":
    raise SystemExit(main())
