#!/usr/bin/env python3
"""female_base —— 女性素体模板：从人工建模参考/人物/huohuo.bbmodel 剥出的裸体。

剥掉什么、为什么，都是实测出来的（不是照组名猜）：

1. 整件删除（整棵子树都是衣物/鞋/帽）
   octagon        兜帽 + 头部金饰（帽子）
   group42        白大衣（含下摆 group43/group27、背带）
   group5/4/26    领口、胸前红结、圆形挂符
   group128/124   两只鞋（含鞋带细节）
   group126/19    小腿护腿（白布 + 青绿滚边 + 踝饰）
   group127/97    脚踝袜口
   group30        头侧的帽翼

2. 只留皮肤 —— 这些子树是「皮肤芯 + 布料壳」两层结构，把壳剥掉
   Arm、RightLeg/LeftLeg、group6（胯）、group9
   判据用立方体六面的贴图采样色（暖浅色 = 皮肤），布料偏冷/灰/青绿都过不了。

3. 身体重新上肤（不含头发/脸）
   源模型的贴图是「每面取图集上一格色卡」的采样式；躯干和胯这几处正好落在
   图集上一排近黑像素，渲染出来是胯上一条黑带，另有大片灰白斑。素体要干净，
   统一改指一张纯肤色贴图。头发/脸保持原样（那是角色的辨识部分）。
   头芯有一块伸到下巴以下、在胸口露出灰白，也按脖子一起上肤。

4. 头发改黑：改图集，不换贴图
   头发原来靠透明像素出镂空（刘海之间的缝、发梢的尖），换成不透明纯色会把
   镂空填死、整颗头变成一坨黑板，所以是把头发 UV 覆盖到的图集像素里「偏青的」
   压暗成黑，透明度和原来的明暗差都留着。头芯那 4 块也在内：它在头顶露出的是
   头发、在脸位露出的是皮肤，同一张脸上半青下半肉——只压青的那半，脸留住了。

（内衣内裤一度按「胸/胯实测范围外扩做壳」的方式补过，2026-09-30 作者要求去掉，
 已从脚本里撤掉——素体保持全裸。）

产物：female_base.bbmodel + female_base.png（肤色贴图）+ *_preview*.png

注意：脚本读 人工建模参考/人物/huohuo.bbmodel（第三方素材，.gitignore 挡住、不随仓库发布），
那个文件不在，本脚本就重跑不了——但产物 female_base.bbmodel 是自带贴图的完整工程，不依赖它。
重跑：python 人物/female_base/build_female_base.py
"""
import base64
import io
import json
import sys
import uuid
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
REPO = HERE
while not (REPO / 'tools' / 'bbmodel_kit.py').is_file():
    if REPO == REPO.parent:
        raise SystemExit('find the repo root (the folder holding tools/bbmodel_kit.py)')
    REPO = REPO.parent
sys.path.insert(0, str(REPO / 'tools'))
from bbmodel_kit import rot_ZYX, walk_groups  # noqa: E402

SRC = REPO / '人工建模参考' / '人物' / 'huohuo.bbmodel'
OUT = HERE / 'female_base.bbmodel'

# 皮肤色取自模型自己的脸/大腿采样值（(252,217,211)~(254,229,224) 一档）
SKIN = (252, 222, 216)

REMOVE_GROUPS = [
    'octagon',    # 兜帽 + 头部金饰
    'group42',    # 白大衣
    'group5',     # 领口 + 红结 + 圆挂符
    'group4',     # 肩领
    'group26',    # 领口小件
    'group128',   # 右鞋
    'group124',   # 左鞋
    'group126',   # 右小腿护腿
    'group19',    # 左小腿护腿
    'group127',   # 右脚踝袜口
    'group97',    # 左脚踝袜口
    'group30',    # 头侧帽翼
    'Tail',       # 尾巴（含 group130/Body_Tail2..6）
]

SKIN_ONLY = ['Arm', 'RightLeg', 'LeftLeg', 'group6', 'group9']

# 重新上肤的范围（按顶层容器名算；头/尾巴不在这里）
RETEINT_ROOT = ['DownBody', 'group6', 'group9', 'group36', 'Arm']


def decode_textures(doc):
    out = {}
    for i, t in enumerate(doc['textures']):
        s = t.get('source') or ''
        if s.startswith('data:image'):
            out[i] = np.array(Image.open(io.BytesIO(base64.b64decode(s.split(',', 1)[1]))).convert('RGBA'))
    return out


def face_color(f, imgs):
    """该面 UV 落在图集上的平均色（无 UV / 全透明返回 None）。"""
    uv = f.get('uv') if f else None
    t = f.get('texture') if f else None
    if uv is None or t not in imgs:
        return None
    a = imgs[t]
    H, W = a.shape[:2]
    x1, x2 = sorted((uv[0], uv[2]))
    y1, y2 = sorted((uv[1], uv[3]))
    X1, Y1 = int(x1), int(y1)
    X2, Y2 = max(X1 + 1, int(round(x2))), max(Y1 + 1, int(round(y2)))
    sub = a[max(0, Y1):min(H, Y2), max(0, X1):min(W, X2)]
    if sub.size == 0:
        return None
    m = sub[:, :, 3] > 0
    if not m.any():
        return None
    return tuple(int(v) for v in sub[:, :, :3][m].mean(axis=0))


def is_skin(c):
    """暖浅色 = 皮肤。白布偏冷/灰、青绿、深蓝都过不了。"""
    if c is None:
        return False
    r, g, b = c
    return r >= 232 and (r - g) >= 12 and (g - b) >= 0


def mean_color(e, imgs):
    cs = [c for c in (face_color(f, imgs) for f in e.get('faces', {}).values()) if c]
    if not cs:
        return None
    return tuple(sum(c[i] for c in cs) / len(cs) for i in range(3))


def is_teal(e, imgs):
    """六面平均明显偏青 = 头发（源模型的头发是青绿，绿比红高 47 以上）。

    阈值不能只写 g > r：头芯那块灰片是 (194,209,207)，只差 15，那样会把它当成头发。
    """
    c = mean_color(e, imgs)
    return c is not None and (c[1] - c[0]) >= 25 and c[1] > c[2]


def add_flat_texture(doc, name, rgb):
    """追加一张纯色贴图，返回它的下标。字段照抄源工程的贴图条目。"""
    img = Image.new('RGBA', (64, 64), tuple(rgb) + (255,))
    buf = io.BytesIO()
    img.save(buf, 'PNG')
    idx = len(doc['textures'])
    entry = dict(doc['textures'][0])
    entry.update({'name': name, 'id': str(idx), 'uuid': str(uuid.uuid4()),
                  'folder': '', 'namespace': '', 'width': 64, 'height': 64,
                  'uv_width': 64, 'uv_height': 64,
                  'source': 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()})
    doc['textures'].append(entry)
    return idx


def to_tree(doc):
    """outliner -> bbmodel_kit.walk_groups 要的 {name, origin, rotation, cubes, children}。"""
    els = {e['uuid']: e for e in doc['elements']}
    grps = {g['uuid']: g for g in doc['groups']}

    def conv(node):
        if isinstance(node, str):
            return None
        g = grps.get(node['uuid'], {})
        kids = [conv(c) for c in node.get('children', [])]
        return {'name': g.get('name', '?'),
                'origin': g.get('origin', [0, 0, 0]),
                'rotation': g.get('rotation', [0, 0, 0]),
                'cubes': [els[c] for c in node.get('children', []) if isinstance(c, str)],
                'children': [k for k in kids if k]}

    return [t for t in (conv(n) for n in doc['outliner']) if t]


def world_box(doc):
    """{cube_uuid: (min_xyz, max_xyz)} 世界坐标包围盒 —— 组的 origin/rotation 要一起算。"""
    out = {}
    for root in to_tree(doc):
        for _path, cube, R, t in walk_groups(root):
            f = np.array(cube['from'], float)
            to = np.array(cube['to'], float)
            o = np.array(cube.get('origin') or (0.0, 0.0, 0.0), float)
            el = cube.get('rotation')
            M = R @ rot_ZYX(*el) if el else R
            cor = np.array([[x, y, z] for x in (f[0], to[0]) for y in (f[1], to[1]) for z in (f[2], to[2])])
            w = (M @ (cor - o).T).T + o + t
            out[cube['uuid']] = (w.min(axis=0), w.max(axis=0))
    return out


def main():
    if not SRC.is_file():
        raise SystemExit(f'找不到源模型：{SRC}')
    d = json.load(open(SRC, encoding='utf-8'))
    els = {e['uuid']: e for e in d['elements']}
    grps = {g['uuid']: g for g in d['groups']}
    imgs = decode_textures(d)
    n0, g0 = len(d['elements']), len(d['groups'])

    def walk(node):
        if isinstance(node, str):
            return [node]
        out = []
        for c in node.get('children', []):
            out += walk(c)
        return out

    # ---- 1) 整件删除 ----
    drop = set()

    def mark(node):
        if isinstance(node, str):
            return
        if grps.get(node['uuid'], {}).get('name') in REMOVE_GROUPS:
            drop.update(walk(node))
            return
        for c in node.get('children', []):
            mark(c)
    for n in d['outliner']:
        mark(n)
    n_removed = len(drop)

    # ---- 2) 混合组里只留皮肤 ----
    zones = []

    def mark_zone(node):
        if isinstance(node, str):
            return
        if grps.get(node['uuid'], {}).get('name') in SKIN_ONLY:
            zones.append(set(walk(node)))
            return
        for c in node.get('children', []):
            mark_zone(c)
    for n in d['outliner']:
        mark_zone(n)

    peeled = 0
    for zone in zones:
        for u in zone:
            if u in drop:
                continue
            cs = [c for c in (face_color(f, imgs) for f in els[u].get('faces', {}).values()) if c]
            if cs and sum(1 for c in cs if is_skin(c)) * 2 < len(cs):
                drop.add(u)
                peeled += 1

    # ---- 3) 身体重新上肤：新加一张纯肤色贴图 ----
    tex_id = add_flat_texture(d, 'skin.png', SKIN)
    SKIN_FACE = {'uv': [0, 0, 1, 1], 'texture': tex_id}

    retex = set()

    def mark_retex(node):
        if isinstance(node, str):
            return
        if grps.get(node['uuid'], {}).get('name') in RETEINT_ROOT:
            retex.update(walk(node))
            return
        for c in node.get('children', []):
            mark_retex(c)
    for n in d['outliner']:
        mark_retex(n)
    retex -= drop
    for u in retex:
        for fn in els[u].get('faces', {}):
            els[u]['faces'][fn] = dict(SKIN_FACE)

    # 3b) 头芯伸到下巴以下的那一块（在胸口露灰白）也按脖子一起上肤。
    #     判据：头部子树里、世界高度低于 31、且本身不偏青（偏青的是头发，要保留）。
    wy = world_box(d)
    head_zone = set()

    def mark_head(node, inside):
        if isinstance(node, str):
            if inside:
                head_zone.add(node)
            return
        nm = grps.get(node['uuid'], {}).get('name')
        for c in node.get('children', []):
            mark_head(c, inside or nm == 'AllHead')
    for n in d['outliner']:
        mark_head(n, False)

    head_core = set()

    def mark_core(node):
        if isinstance(node, str):
            return
        if grps.get(node['uuid'], {}).get('name') == 'Head_Root':
            head_core.update(c for c in node.get('children', []) if isinstance(c, str))
            return
        for c in node.get('children', []):
            mark_core(c)
    for n in d['outliner']:
        mark_core(n)

    fixed_head = 0
    for u in head_zone - retex - drop:
        if wy[u][0][1] >= 31.0:
            continue
        if is_teal(els[u], imgs):        # 偏青 = 头发，留给 3c 改黑
            continue
        if u in head_core:               # 头芯按脸/发分开处理，不整块刷肤
            continue
        for fn in els[u].get('faces', {}):
            els[u]['faces'][fn] = dict(SKIN_FACE)
        fixed_head += 1

    # 保护名单：这几处的青绿不是头发，不能被压黑
    #   Face / Mouth  —— 瞳孔、眼睑
    #   Head_Root 的直接方块 —— 头芯（脸那层皮肤），在脸位是最前的一块
    #   （只护头芯自己：子树 AtBtCt_Root 里是头顶两侧的发绺，那些要刷黑）
    protect = set()

    def mark_prot(node, inside):
        if isinstance(node, str):
            if inside:
                protect.add(node)
            return
        nm = grps.get(node['uuid'], {}).get('name')
        if nm == 'Head_Root':
            for c in node.get('children', []):
                if isinstance(c, str):
                    protect.add(c)
                else:
                    mark_prot(c, inside)
            return
        for c in node.get('children', []):
            mark_prot(c, inside or nm in ('Face', 'Mouth'))
    for n in d['outliner']:
        mark_prot(n, False)

    # ---- 3c) 头发改黑：直接改图集，不换贴图 ----
    #     源模型的头发是青绿色，但一撮发散在青绿里、而且是靠透明像素出镂空
    #     （刘海之间的缝、发梢的尖）。给立方体换一张不透明纯黑会把镂空填死，
    #     整颗头变成一坨黑板 —— 栽过一次。所以改成：把「头发那几个立方体 UV 覆盖到
    #     的图集像素」里偏青的挑出来，压暗成黑（保留透明度和原来的明暗差）。
    #     头芯那 4 块也要算进来：它在头顶露出来的部分是头发、在脸位露出来的是皮肤，
    #     同一张脸上半青下半肉 —— 只把偏青的像素压黑，脸那半自己就留住了。
    hair_cubes = [u for u in head_zone - drop
                  if u not in protect and is_teal(els[u], imgs)]
    atlas_sets = []                                  # (texture_index, mask)
    for ti in {f.get('texture') for u in hair_cubes + sorted(head_core)
               for f in els[u].get('faces', {}).values()}:
        if ti not in imgs:
            continue
        m = np.zeros(imgs[ti].shape[:2], bool)
        for u in hair_cubes + sorted(head_core):
            for f in els[u].get('faces', {}).values():
                if f.get('texture') != ti or not f.get('uv'):
                    continue
                x1, x2 = sorted((f['uv'][0], f['uv'][2]))
                y1, y2 = sorted((f['uv'][1], f['uv'][3]))
                X1, Y1 = int(x1), int(y1)
                X2, Y2 = max(X1 + 1, int(round(x2))), max(Y1 + 1, int(round(y2)))
                m[max(0, Y1):min(m.shape[0], Y2), max(0, X1):min(m.shape[1], X2)] = True
        atlas_sets.append((ti, m))

    # 这些像素不能同时被别的件用着（脸/嘴的瞳孔、身体、内衣）；实测为 0，防呆
    other = np.zeros(imgs[0].shape[:2], bool)
    for e in d['elements']:
        if e['uuid'] in hair_cubes or e['uuid'] in head_core:
            continue
        for f in e.get('faces', {}).values():
            if f.get('texture') != 0 or not f.get('uv'):
                continue
            x1, x2 = sorted((f['uv'][0], f['uv'][2]))
            y1, y2 = sorted((f['uv'][1], f['uv'][3]))
            X1, Y1 = int(x1), int(y1)
            X2, Y2 = max(X1 + 1, int(round(x2))), max(Y1 + 1, int(round(y2)))
            other[max(0, Y1):min(other.shape[0], Y2), max(0, X1):min(other.shape[1], X2)] = True

    n_hair_px = 0
    for ti, mask in atlas_sets:
        a = imgs[ti].astype(np.int32)
        op = a[:, :, 3] > 0
        teal = op & ((a[:, :, 1] - a[:, :, 0]) >= 25) & (a[:, :, 1] > a[:, :, 2]) & mask
        if ti == 0:
            teal &= ~other
        if not teal.any():
            continue
        g = a[:, :, 1][teal]
        v = np.clip((g - 100) * 0.5 + 24, 16, 78).astype(np.int32)   # 明暗差留着
        a[:, :, 0][teal] = (v * 0.92).astype(np.int32)
        a[:, :, 1][teal] = (v * 0.92).astype(np.int32)
        a[:, :, 2][teal] = v
        imgs[ti] = a.astype(np.uint8)
        n_hair_px += int(teal.sum())

    # 改完的图集要写回工程（贴图是内嵌的 base64）
    for ti in {i for i, _m in atlas_sets}:
        buf2 = io.BytesIO()
        Image.fromarray(imgs[ti]).save(buf2, 'PNG')
        d['textures'][ti]['source'] = 'data:image/png;base64,' + base64.b64encode(buf2.getvalue()).decode()

    # ---- 3e) 加胸 ----
    #     做法照人工建模参考里的「[无动画共享]映素2.5代-女性标准体型v3.7」：
    #     每个胸就是一块倾斜的方板（rot X≈52°，Y/Z 各偏几度，左右镜像），
    #     形由板自己的朝向承载，不是靠几层方块叠出台阶。
    #     位置按我们躯干的实际数据摆：胸前表面 z≈-1.88，可见胸段 y≈26.5..31.5。
    BR = dict(w=3.05, h=2.75, d=2.35,        # 板的尺寸
              rx=50.0, ry=2.5, rz=2.0,       # 俯仰 / 外张 / 侧倾
              cx=1.58, cy=28.40, cz=-2.20)   # 单侧中心
    tmpl_e2 = dict(d['elements'][0])
    gu = str(uuid.uuid4())
    g = dict(next(gr for gr in d['groups'] if gr['name'] == 'Hair'))
    g.update({'name': 'Breast', 'uuid': gu, 'origin': [0, 30.8, -1.1], 'rotation': [0, 0, 0],
              'children': [], 'isOpen': True, 'visibility': True})
    d['groups'].append(g)
    bre_node = {'uuid': gu, 'isOpen': True, 'children': []}
    for sign in (-1, 1):
        c = (sign * BR['cx'], BR['cy'], BR['cz'])
        half = (BR['w'] / 2, BR['h'] / 2, BR['d'] / 2)
        e = dict(tmpl_e2)
        e.update({'name': 'Breast', 'uuid': str(uuid.uuid4()),
                  'from': [round(c[i] - half[i], 3) for i in range(3)],
                  'to': [round(c[i] + half[i], 3) for i in range(3)],
                  'origin': [round(v, 3) for v in c],
                  'rotation': [BR['rx'], -sign * BR['ry'], sign * BR['rz']],
                  'faces': {k: {'uv': [0, 0, 1, 1], 'texture': tex_id}
                            for k in ('north', 'east', 'south', 'west', 'up', 'down')}})
        d['elements'].append(e)
        bre_node['children'].append(e['uuid'])

    def attach_breast(node):
        if isinstance(node, str):
            return False
        if grps.get(node['uuid'], {}).get('name') == 'UpperBody':
            node['children'].append(bre_node)
            return True
        return any(attach_breast(c) for c in node.get('children', []))
    for n in d['outliner']:
        if attach_breast(n):
            break

    # ---- 4) 重写 outliner / elements / groups ----
    def prune(node):
        if isinstance(node, str):
            return None if node in drop else node
        kids = [k for k in (prune(c) for c in node.get('children', [])) if k is not None]
        return {**node, 'children': kids} if kids else None

    new_out = [r for r in (prune(n) for n in d['outliner']) if r is not None]
    live = set()

    def collect(n):
        if isinstance(n, str):
            return
        live.add(n['uuid'])
        for c in n.get('children', []):
            collect(c)
    for n in new_out:
        collect(n)

    out_els = [e for e in d['elements'] if e['uuid'] not in drop]

    # 清掉没人用的贴图（源工程那张 32x32 只喂过已删的件），面里的下标要跟着重映射
    used = sorted({f['texture'] for e in out_els for f in e.get('faces', {}).values()
                   if f.get('texture') is not None})
    if len(used) != len(d['textures']):
        remap = {old_i: new_i for new_i, old_i in enumerate(used)}
        d['textures'] = [d['textures'][i] for i in used]
        for e in out_els:
            for f in e.get('faces', {}).values():
                if f.get('texture') is not None:
                    f['texture'] = remap[f['texture']]

    out = dict(d)
    out['name'] = 'female_base'
    out['outliner'] = new_out
    out['elements'] = out_els
    out['groups'] = [g for g in d['groups'] if g['uuid'] in live]
    json.dump(out, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False)
    Image.fromarray(imgs[0]).save(HERE / 'female_base.png')

    ys = [(min(e['from'][1], e['to'][1]), max(e['from'][1], e['to'][1])) for e in out['elements']]
    print(f'-> {OUT}')
    print(f'   方块 {n0} -> {len(out["elements"])}（整件删除 {n_removed}，剥掉布料壳 {peeled}）')
    print(f'   组   {g0} -> {len(out["groups"])}')
    print(f'   重新上肤 {len(retex)} 块 + 头芯 {fixed_head} 块，肤色 {SKIN}')
    print(f'   加胸 2 块（倾斜方板，rot {BR["rx"]}/{BR["ry"]}/{BR["rz"]}）')
    print(f'   头发改黑：{len(hair_cubes)} 块 + 头芯 {len(head_core)} 块，'
          f'压暗图集像素 {n_hair_px} 个')
    print(f'   高度 {min(a for a, _ in ys):.2f}..{max(b for _, b in ys):.2f}')


if __name__ == '__main__':
    main()
