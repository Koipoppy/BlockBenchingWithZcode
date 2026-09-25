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

**`from`/`to` 是"未旋转姿态"下模型空间的绝对坐标，`origin` 是同一空间里的轴心点**；
两者不在一处时（比如坐标写在中部、轴心写在几十格外），旋转会把方块甩到完全无关的位置。
摆斜板的正确流程（M1A2 首上装甲验证）：

1. 目标是"铰链 H → 端点 T"的一块板：先把板**未旋转**地挂在 H 上
   （竖直悬挂，板长 = |H−T|，厚度居中于铰链平面），`origin` 设在 H；
2. 旋转角由端点反解：Rx(θ) 作用下悬挂板的下端走 `(Δy, Δz) = (−L·cosθ, −L·sinθ)`，
   要落到 T 就解 `θ = atan2(−Δz, −Δy)`（首上板 Δy=−20、Δz=−11.5 → θ=30°）；
   绕竖轴的颊板同理：沿 +z 从枢轴摆出，`ry = atan2(Δx, Δz)`；
3. 手算一个端点的落点核对（必须落在设计坐标上），再渲染侧视/正视确认。

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

## 11. 工程格式版本：4.5（脚本写的）与 5.0（Blockbench 保存写的）

实测对象：`property/ship_in_bottle/ship_in_bottle.bbmodel`——在 Blockbench 里打开并保存过一次。

| | 4.5（本仓库生成脚本写出的） | 5.0（Blockbench 自己保存写出的） |
|---|---|---|
| `meta.format_version` | `"4.5"` | `"5.0"` |
| 组的 name/origin/rotation | 内联在 outliner 节点里 | 移到顶层 `groups` 数组 |
| outliner 节点 | `{name, origin, rotation, uuid, children}` | `{uuid, isOpen, children}`（纯引用） |
| 元素额外字段 | 无 | `scope` / `autouv` / `export` / `locked` / `allow_mirror_modeling` / `render_order` … |
| 数字写法 | `1.0` / `0.0` | 能取整就写整数（`0` 而非 `0.0`） |
| 额外顶层键 | 无 | `groups` / `model_identifier` / `timeline_setups` / `visible_box` / `unhandled_root_fields` / `variable_placeholder*` / `multi_file_ruleset` |

要点：

- **解析器两边都要读**：outliner 节点里没有 `origin`/`rotation` 时，按 `uuid` 去顶层 `groups` 表取。
  组的 `origin` 只是 pivot（**不**平移子元素），所以真正会丢的是**组的旋转**——没有旋转组时
  看不出问题，一旦有（比如给某个组做了摆动）就会静默按 0 渲染。`tools/preview_bbmodel.py`
  现已两边都支持（`collect_quads` 里的 `groups` 查表）。
- **元素几何不受影响**：同一模型 4.5 → 5.0 重新保存后，用同一渲染器渲染输出逐像素一致
  （实测平均差 0.000），即保存只改格式、不改几何与 UV。
- **重新生成会覆盖 GUI 修改**：生成脚本写 4.5；对已被 Blockbench 保存成 5.0 的文件重跑生成脚本，
  文件会退回 4.5 且**丢掉在 GUI 里做的修改**。想保留 GUI 修改就别重跑脚本。
- 元素的 `scope` 是 5.x 新增字段，观测到的工程里全为 0（模型空间）；非 0 的语义未验证——
  解析时遇到非 0 应当显式报错，不要当作 0 静默处理。

## 12. 组旋转（4.5 格式就支持）与组的变换代数

实测对象：`us_soldier.bbmodel`（2026-09-25 的持枪士兵，本仓库第一个用组旋转的工程）。
读的是 `js/formats/bbmodel.js`、`js/outliner/outliner.js`、`js/outliner/types/group.js`：

| 源文件 | 代码 | 结论 |
|---|---|---|
| `formats/bbmodel.js` | `if (model.groups) { model.groups.forEach(t => new Group(t, t.uuid).init()) }`，之后才是 `if (model.outliner) Outliner.loadJSON(model.outliner)` | 顶层 `groups` 表**不是 5.0 专属**，4.5 文件里写了也会被读；两条路径都会跑 |
| 同上 | `loadJSON` 遍历 outliner：`if (item.name != undefined) { obj instanceof Group ? obj.extend(item) : obj = new Group(item, item.uuid); obj.init() }`（源码注释就写着 `// Legacy group support`） | **4.5 的 outliner 节点只要带 `name` 就按组解析**，`new Group(node, node.uuid)` 会把 `origin`/`rotation` 从节点上读走 |
| `outliner/types/group.js` | `new Property(Group, 'vector', 'origin', …); new Property(Group, 'vector', 'rotation');`，`extend()` 里 `for (key in Group.properties) Group.properties[key].merge(this, object)` | `origin`/`rotation` 是 Property 系统里的组属性；`extend` 里没单写这两项，是因为走了 Property 循环 |
| `outliner/outliner.js` | `updateTransform`：`mesh.position.set(element.origin…)`；`if (Format.bone_rig) { parent.mesh.add(mesh); if (parent.getTypeBehavior('use_absolute_position')) mesh.position -= parent.origin }` | 组 origin 是**枢轴**：子节点写绝对模型座标，挂接时父 origin 被减掉，等价于逐层 `T(o)·R·T(-o)` |
| `outliner/types/group.js` | `static behavior = {parent, movable, rotatable, has_pivot, use_absolute_position: true, …}` | 组确实具备 movable/rotatable/use_absolute_position，上一条对组成立 |
| 同上 | 预览控制器 `setup`：`bone.rotation.order = Format.euler_order` | 组的旋转序同样是 `'ZYX'` = `Rz·Ry·Rx`，与元素一致 |

写生成脚本时可直接用的推论：

- 组旋转**不需要为了用它而升到 5.0**：4.5 的 outliner 节点写
  `{"name": …, "origin": [...], "rotation": [rx,ry,rz], "children": [...]}` 即可（本仓库 `build_us_soldier.py` 就是这么写的，validator 与预览器都认）；
- 复合式：`p_world = R_chain · p_authored + t`；沿树下推一层是
  `R' = R @ R_local`、`t' = t + R @ (I - R_local) @ o`。
  `R'` 是**父在左**（three.js 的 `parent_world · local`），写成 `R_local @ R` 会在两层以上时转反；
- 由方向反解角度（求解姿态时反复用到，都是精确解不是近似）：
  - 作用在 `(0,-1,0)`（自然下垂的肢体）上、只给 `rx`+`rz`：`rx = asin(-d_z)`，`rz = atan2(d_x, -d_y)`；
  - 作用在 `(0,0,-1)`（指向北的枪管/炮管）上、只给 `rx`+`ry`：`rx = asin(d_y)`，`ry = atan2(-d_x, -d_z)`（这组恰好是"绕轴的最小滚转"）；
  - `rot_ZYX` 的反解：`ry = asin(-R[2,0])`、`rz = atan2(R[1,0], R[0,0])`、`rx = atan2(R[2,1], R[2,2])`；`|R[2,0]| → 1` 是万向锁，必须显式报错；
- **挂在旋转链下的物件**（本例：枪挂在右前臂组下）：让它在世界里落在 `G + R_world·L`
  （`L` 是相对枢轴的局部偏移），正确写法是节点旋转取 `R_local = R_chain⁻¹·R_world`、
  子方块座标写 `pivot + L`（L 原样，不要再乘一次 R_local）。错写成 `pivot + R_local·L`
  会让物件整体转错一个 R_local——见 pitfalls.md 第 15 条。
