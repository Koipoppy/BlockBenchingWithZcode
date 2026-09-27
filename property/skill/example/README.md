# 霸王花盆栽（Minecraft 风格花盆模型）

Blockbench 工程：一个陶土花盆，种着《植物大战僵尸》风格的霸王花。

| 文件 | 说明 |
|---|---|
| `bawanghua_flower_pot.bbmodel` | Blockbench 工程（64×64 贴图以 base64 内嵌，可直接打开） |
| `bawanghua_flower_pot.png` | 同一张贴图，单独导出，方便改图或放进资源包 |
| `preview.png` | 预览图，相机位置 = Blockbench 打开工程时的默认视角 |
| `preview_front.png` | 预览图，正面 3/4 视角 |
| `../scripts/build_bawanghua_pot.py` | 生成贴图 + 几何 + 写出 `.bbmodel` 的脚本 |
| `../scripts/preview_bbmodel.py` | 自建离线渲染器（零依赖、可脚本化）；第三方对照用无头 MCP，见 [`../references/headless-mcp.md`](../references/headless-mcp.md) |

## 打开

用 Blockbench 打开 `bawanghua_flower_pot.bbmodel` 即可。工程格式是 **Generic Model (free)**，
因为它支持骨骼组、任意角度旋转和居中网格；旋转角度不是 22.5° 的整数倍（花瓣有 16°/8° 的倾角），
`java_block` 会拒绝这类模型。

模型尺寸：宽约 1 格（花瓣展开 17/16 格），高 30/16 ≈ 1.9 格，花盆是原版花盆的比例（底部 6×6×6，口沿 8×8×2）。
43 个方块，分 4 层组：`pot` / `plant`（`stem`、`leaves`、`calyx`、`head`（`petals`、`sepals`、`maw`、`jaw`、`skull`、`crown`））。
花瓣和萼片是**每片一个组**，每一组绕 Y 轴旋转到自己的角度，所以：

- 可以单独抓住某一片花瓣旋转／做动画（比如开花、咬合）；
- 想改花瓣数量，只改 `petal_whorl(...)` 的 `count`／`offset` 参数就行。

## 设计说明（重要）

当时取不到霸王花在游戏里的原始造型图（fandom／萌娘百科／百科直连 404 / 403 / 超时；
后来发现 WebSearch 的文本摘要可用，但图仍然拿不到），
所以这个模型是按 PvZ 植物的通用美术语言自己设计的，名称取"霸王"之意：

- **花头**：粗壮的深红方块头，正面是一张有眼白+瞳孔的脸，下面是一张带獠牙的大嘴（白色牙齿交错咬合、粉色舌头、暗红口腔）；
- **花瓣**：8 片厚花瓣围着花头下方排成一圈，底下再垫 8 片绿色萼片；
- **茎叶**：2×2 绿茎，带两根小刺，四片叶子（两张低、两张高，交错生长）；
- **花盆**：原版花盆结构——底部 6×6×6 陶土、口沿 8×8×2，顶面画的是"陶土圈 + 泥土 + 中间插着茎的土洞"；
- **顶部**：5 根绿色尖刺组成的冠。

如果你手上有霸王花的参考图，想让我按原图改（花瓣颜色/数量、嘴巴形状、是否要眼睛等），
改 `build_bawanghua_pot.py` 里的调色板和 `build_tree()` 就行，脚本会重新生成模型和贴图。

## 关于格式的几个坑（已从 Blockbench 源码核实）

这些约定如果搞错，贴图会静默镜像或错位，所以是**实测**出来的，不是猜的
（源码在 `resources/app.asar` → `dist/bundle.js.map`；完整对照表与工程格式版本见
[`../references/bbmodel-format.md`](../references/bbmodel-format.md)）：

1. **UV 方向**（`js/util/three_custom.js` 的 `setShape` + `js/outliner/types/cube.js` 的 `updateUV`）：
   从外侧看一个面时，UV 矩形是**正立且不镜像**的；`uv = [u1, v1, u2, v2]` 单位是贴图像素，
   `v` 从**上**往下。这里没有 north/south 翻转那种约定。
2. **旋转顺序**（three.js euler order `ZYX`，即矩阵 `Rz·Ry·Rx`，绕 `origin` 旋转）：
   所以每片花瓣必须是"**组绕 Y 转 + 方块自身绕局部 Z 倾**"的组合，
   单靠一个元素的旋转没法同时表达"绕茎排布"和"向上翘"。
3. **默认相机**在 `(-40, 32, -40)`，看向 `(0, 12, 0)` —— 也就是从 `-X/-Z` 角看过来，
   所以花的嘴朝 **-Z（北）**，打开工程第一眼就能看到脸。

## 重新生成 / 改动

```bash
python ../scripts/build_bawanghua_pot.py        # 重新生成 bbmodel + png
python ../scripts/preview_bbmodel.py bawanghua_flower_pot.bbmodel preview.png --azimuth 225 --elevation 19.47 --distance 60 --target 0 12 0
```

要改的东西都在 `build_bawanghua_pot.py` 里：

- 调色板：文件顶部的 `CLAY` / `SOIL` / `GREEN` / `RED` / `MOUTH` / `TOOTH` / `TONGUE`（每个都是明→暗的色阶）；
- 贴图：`paint_texture()` 里每个 rect 的画法，`RECT_SIZES` 是各个面的 UV 矩形尺寸（尺寸=对应面的实际像素大小，不会被拉伸）；
- 几何：`build_tree()` 里所有方块的坐标（单位是 1/16 格，`y=0` 是盆底，整体以 `x=z=0` 为中心）；
- 花瓣环：`petal_whorl(前缀, y, 起始半径, 长度, 宽度, 倾角, 片数, 相位偏移)`。

生成脚本自带一个廉价的自检：UV 矩形按货架算法打包进 64×64，没画到的区域是**品红色**，
所以在预览里看到品红就说明某个面的 UV 指错了地方。`extend_edges()` 会把每个矩形的边缘像素外扩 1px，防止采样到隔壁。

## 已知限制

- 这是**建模源文件**，不是能直接丢进资源包的方块模型：要进游戏得在 Blockbench 里另行导出
  （Bedrock geometry／Java block model 都可以，但 Java 方块模型要求旋转是 22.5° 的整数倍，花瓣的 16° 会被警告/丢弃）。
- 贴图 64×64，整模型共用一张，没有做发光／透明通道。
- 预览图是用 `../scripts/preview_bbmodel.py` 离线渲染的（z-buffer + MC 的面光照系数：顶 1.0、南北 0.8、东西 0.6、底 0.5），
  和 Blockbench 视口的观感接近但并不完全相同；要第三方复核就用无头 MCP 的 `bbmodel_render`。
