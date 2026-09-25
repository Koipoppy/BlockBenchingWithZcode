# bbmodel 格式实测表（Blockbench 5.2.1）

所有条目都从本机安装包读出，不是猜的：`resources/app.asar` → `dist/bundle.js.map`
的 `sourcesContent[]`（下标与 `sources[]` 一一对应，存的是未压缩源码和原始路径）。
读源码时盯这几个文件：

| 源文件 | 里面有什么 |
|---|---|
| `js/util/three_custom.js` | `BufferGeometry.setShape`（方块 24 个顶点的排布）、Euler 扩展 |
| `js/outliner/types/cube.js` | `updateUV`（显式 uv 与 box-uv 两套）、`mapAutoUV`、面序 `Canvas.face_order` |
| `js/preview/preview.ts` | `DefaultCameraPresets`、fov、相机逻辑 |
| `js/formats/generic.ts` | `ModelFormat('free', {...})` 的能力开关 |
| `js/io/format.ts` | 各 ModelFormat 属性的默认值（euler_order、forward_direction、block_size） |
| `js/outliner/types/group.js` | 骨骼组的旋转序同样取 `Format.euler_order` |

## 1. 顶点序（setShape，按面写出 4 个顶点）

记号：`(x0/x1, y0/y1, z0/z1)` 是方块的 from/to。面的写入顺序（= 顶点缓冲里的分组顺序，
也与 `Canvas.face_order` 一致）：**east, west, up, down, south, north**，每面 4 顶点：

```
east  (x=x1): (x1,y1,z1) (x1,y1,z0) (x1,y0,z1) (x1,y0,z0)
west  (x=x0): (x0,y1,z0) (x0,y1,z1) (x0,y0,z0) (x0,y0,z1)
up    (y=y1): (x0,y1,z0) (x1,y1,z0) (x0,y1,z1) (x1,y1,z1)
down  (y=y0): (x0,y0,z1) (x1,y0,z1) (x0,y0,z0) (x1,y0,z0)
south (z=z1): (x0,y1,z1) (x1,y1,z1) (x0,y0,z1) (x1,y0,z1)
north (z=z0): (x1,y1,z0) (x0,y1,z0) (x1,y0,z0) (x0,y0,z0)
```

索引缓冲每面两个三角形：`(0, 2, 1)` 和 `(2, 3, 1)`。

## 2. uv 角与顶点的配对（updateUV）

`uv = [u1, v1, u2, v2]`，单位是贴图像素，**v 从贴图顶部起算**。每面 4 个顶点依次拿到：

```
v0 ← (u1, v1)   矩形左上
v1 ← (u2, v1)   矩形右上
v2 ← (u1, v2)   矩形左下
v3 ← (u2, v2)   矩形右下
```

合并 1 和 2 的结论：**从外侧看任何一个面，贴图都是正立且不镜像的**。
推论：

- 一个件的 up 面和 down 面若"长边方向相同"（如沿 X 放的叶片），可以共用一个矩形；
- 若从相反方向看同一矩形（如沿 Z 放的叶片的上下两面），要么给两个矩形，要么把画成沿中线对称；
- north/south、east/west 互为镜像方向——只有**左右对称**的画法可以一个矩形通吃 4 个侧面。

box-uv（`element.box_uv = true`）时 updateUV 自动铺的 net（`size = [sx, sy, sz]`）：

```
east:  from [0, sz]       size [sz, sy]
west:  from [sz+sx, sz]   size [sz, sy]
up:    from [sz+sx, sz]   size [-sx, -sz]
down:  from [sz+sx*2, 0]  size [-sx, sz]
south: from [sz*2+sx, sz] size [sx, sy]
north: from [sz, sz]      size [sx, sy]
```

up/down 是**负尺寸**——net 里方向翻转，这正是"box net"和显式 uv 手感不同的来源。

## 3. 旋转

`mesh.rotation.order = Format.euler_order`，默认 `'ZYX'`（`js/io/format.ts`：
`new Property(ModelFormat, 'enum', 'euler_order', {default: 'ZYX'})`，free 格式不覆盖）。
three.js 的 'ZYX' 矩阵 = **Rz·Ry·Rx**，作用在向量上即先 X 后 Y 后 Z；pivot 是
`element.origin` / `group.origin`（变换 = `T(o) · R · T(-o)`）。组嵌套时子节点继承父链。

写模型时最有用的一条推论：**"绕竖轴排布 + 自身翘起"必须两层**——
组带 `[0, θ, 0]`（pivot 在轴心），元素只带 `[0, 0, 倾角]`（pivot 在根部）。
一个元素旋转写 `[0, θ, 倾角]` 会在 θ≠0 时把翘起变成侧滚。

## 4. 格式与默认值

```
ModelFormat id: 'free' | 'java_block' | 'modded_entity' | 'skin' | 'image'
free:  meshes, billboards, armature_rig, splines, rotate_cubes, bone_rig,
       centered_grid, optional_box_uv, per_texture_uv_size, uv_rotation,
       animation_mode, locators, bounding_boxes, pbr   ← 代码生成模型的首选
java_block: 旋转限 22.5° 整数倍、单轴，16° 花瓣会被警告/丢弃
euler_order 默认 'ZYX'；forward_direction 默认 '-z'；block_size 默认 16
```

## 5. 默认相机（preview.ts 的 DefaultCameraPresets[0]）

```
forward_direction '-z'（默认）→ position [-40, 32, -40]，target [0, block_size*0.75, 0]
即 fov 45°、距离 60、从 -X/-Z 角俯视 19.47°
```

推论：**模型要给观众看的面朝 -Z（北）**，打开工程第一眼就能看到。
离线渲染复现该视角：`--azimuth 225 --elevation 19.47 --distance 60 --target 0 12 0`。

## 6. MC 方块面光照（渲染器该用的明暗）

```
up 1.0 | north/south 0.8 | east/west 0.6 | down 0.5
```

倾斜面按法线分量**平方**加权混合：`shade = Σ w_i·light_i / Σ w_i`，`w_i = max(0, n_i)²`。
正交面精确落在游戏数值上，45° 斜面得 0.8 之类的合理中间值。
不要用"头灯"（随相机方向的光）：像素画的明暗全在贴图里，头灯会把白牙压成灰。

## 7. bbmodel 最小骨架

```json
{
  "meta": {"format_version": "4.5", "model_format": "free", "box_uv": false},
  "name": "模型名",
  "resolution": {"width": 64, "height": 64},
  "elements": [
    {"name": "cube名", "from": [x,y,z], "to": [x,y,z], "origin": [x,y,z],
     "uuid": "<uuid4>", "type": "cube", "color": 0,
     "faces": {"north": {"uv": [u1,v1,u2,v2], "texture": 0},
               "east": {...}, "south": {...}, "west": {...},
               "up": {...}, "down": {...}},
     "rotation": [rx,ry,rz]}
  ],
  "outliner": [
    {"name": "组名", "origin": [x,y,z], "uuid": "<uuid4>",
     "children": ["<element uuid>", {"name": "子组", "origin": [...], "uuid": "...", "children": [...]}]}
  ],
  "textures": [{"path": "", "name": "tex.png", "folder": "entity", "namespace": "",
                "id": "0", "particle": false, "render_mode": "default", "visible": true,
                "mode": "bitmap", "saved": false, "uuid": "<uuid4>",
                "source": "data:image/png;base64,..."}],
  "animations": []
}
```

要点：**嵌套组内联为对象，元素用 uuid 字符串引用**——把组写成"平铺 + uuid 互相指"会被
Blockbench 读成多个不相关的根加悬空引用。未旋转的方块也写上 `origin`（它是以后旋转的 pivot）。

## 8. 结构校验的不变量（validator 检查的全部内容）

自带的校验脚本（minecraft-animation skill 的 `tools/validate_bbmodel.py`）检查：

1. 顶层键齐全：`meta / resolution / elements / outliner / textures`
2. `meta.format_version` 存在
3. `resolution` 非退化；**内嵌贴图解码后的尺寸必须与 resolution 一致**
4. 每个 cube 的 `from/to` 三轴跨度非负；必须有面；每个面有 4 数 uv（且非空、在贴图范围内）、texture 索引在 0..n-1
5. outliner 里引用的 uuid 都存在；**元素不能是孤儿**（每个元素都要被 outliner 引用）
6. uuid 不重复
7. animation 的 animator 名必须是 outliner 里真实存在的 bone 名

## 9. 从 app.asar 提取源码

asar 头部（小端 u32）：

```
@0  = 4                  （固定）
@4  = headerSize
@8  = headerSize - 4
@12 = jsonLen            ← 目录 JSON 的长度
@16 = JSON（目录树，含每个文件的 offset/size）
文件数据区从 8 + headerSize 开始，按目录里的 offset/size 取
```

要的不是 bundle 本体（已压缩），而是 `dist/bundle.js.map`：`json.load` 后
`sources[]` 是原始路径、`sourcesContent[]` 是未压缩源码，按路径下标取即可。
注意坑：Git Bash 的 `/tmp` 对原生 Windows Python 不成立，临时文件用 `os.environ['TEMP']`。

## 10. 实证校验手段：uvprobe

以上任何一条都可以（也应该）用探针实证：造一个立方体，六个面各涂一种纯色 +
白色箭头指向矩形 -v 方向 + 角落放一个黑点，渲染六个方向，读图即可一次确定全部六面的
方向映射。改 Blockbench 版本或换导出路径时重跑一次，两分钟。
