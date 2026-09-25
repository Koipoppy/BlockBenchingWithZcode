# M1A2 艾布拉姆斯主战坦克

> 本文件夹是「M1A2 艾布拉姆斯」的自包含目录：工程、贴图、预览都在这里。
> 共享脚本在 `../tools/`，总索引见 [../README.md](../README.md)。

Blockbench 工程：美国 M1A2 主战坦克的 Minecraft 风格模型，沙漠涂装。

| 文件 | 说明 |
|---|---|
| `m1a2_abrams.bbmodel` | Blockbench 工程（256×256 贴图以 base64 内嵌，可直接打开） |
| `m1a2_abrams.png` | 同一张贴图，单独导出，方便改图或放进资源包 |
| `m1a2_abrams_preview.png` | 预览图，左前 3/4 视角 |
| `m1a2_abrams_preview_side.png` / `_front.png` / `_back.png` | 侧 / 正 / 后视角预览 |
| `../tools/build_m1a2_abrams.py` | 生成贴图 + 几何 + 写出 `.bbmodel` 的脚本 |

## 打开

用 Blockbench 打开 `m1a2_abrams.bbmodel` 即可。工程格式是 **Generic Model (free)**
（要骨骼组、任意角度旋转——首上装甲 30°、炮塔颊板 55.4°，`java_block` 会拒绝这类角度）。

模型尺寸：1 单位 = 1/16 格。全长 159 单位（含前伸的炮管，约 10 格），
车体宽 44、炮塔宽 64，高 41（炮塔顶）~61（天线），基本按实车 9.83 m × 3.66 m × 2.44 m
的比例换算。共 90 个方块。

## 分组（方便做动画）

- `hull`：车体板件、进气格栅、大灯、拖钩、驾驶员舱门与潜望镜
  - `skirt_left` / `skirt_right`：侧裙板 + 挡泥板 + 后挡泥板
  - `track_left` / `track_right`：履带环 + 7 个负重轮 + 主动轮（车尾）+ 导向轮
    （负重轮、主动轮、导向轮的 origin 都在各自轮心，原地旋转即可做履带滚动）
- `turret`（origin 在炮塔环中心，绕 Y 旋转即回转）
  - `gun`（origin 在耳轴，绕 X 俯仰）：120mm 炮管 + 热护套 + MRS 校炮圈
  - 炮长主瞄（车顶左前）、CITV 热像仪（右前）、车长指挥塔与 M2 重机枪、
    装填手舱门与 M240、烟幕弹发射器、侧储物箱、尾舱 + 弹架栏杆 + 油桶/木箱、
    横风传感器、两根天线

## 设计说明

外部照片在建模时拿不到（WebSearch 能检索到文字史实——单炮塔布局、7 轮、后置主动轮、
尺寸；wikipedia/fandom 直连全部超时），所以造型是按这些硬指标加 M1 系列通用观感
自行设计的"像素版"，细节（储物箱、油桶、木箱摆放）是风格化创作：

- **车体**：大倾角首上装甲（30°）+ 下首板在鼻尖汇合，平台甲板后部是动力舱
  （两块进气格栅 + 检查口），尾部格栅化排气 + 红色尾灯；
- **炮塔**：正面是两块互成 55.4° 的颊板在前尖汇成脊线，楔形 V 区里凹装炮盾，
  炮塔比车体宽、两侧外伸遮住侧裙板上方——这是 Abrams 侧影的关键；
  炮塔顶前部用 5 级阶梯板填平楔形，避免方块穿帮；
- **行走**：每侧 7 个负重轮、环形履带只在上下和前后包覆处有带体，中段敞开
  露出轮子（和真车侧影一致），主动轮在车尾、带齿圈贴图；
- **涂装**：CARC 沙漠黄，焊缝线代替铆钉（Abrams 是焊接车体），履带和轮缘是
  近黑的橡胶色，储物/弹架用橄榄绿点缀。

## 重新生成 / 改动

```bash
python ../tools/build_m1a2_abrams.py        # 重新生成 bbmodel + png
python ../tools/preview_bbmodel.py m1a2_abrams.bbmodel m1a2_abrams_preview.png \
    --azimuth 225 --elevation 20 --distance 235 --target 0 22 -8 --ground 95
python ../tools/preview_bbmodel.py m1a2_abrams.bbmodel m1a2_abrams_preview_side.png \
    --azimuth 90 --elevation 8 --distance 200 --target 0 22 -8 --ground 95
```

要改的东西都在 `build_m1a2_abrams.py` 里：

- 调色板：文件顶部的 `TAN` / `TREAD` / `RUBBER` / `METAL` / `OLIVE`（明→暗色阶）。
  想要丛林绿版本，把 `TAN` 换成一套绿色色阶重新生成即可；
- 贴图：`paint_texture()` 里每个 rect 的画法（`RECT_SIZES` 是各面 UV 矩形尺寸，
  尺寸=对应面的实际像素大小，不会被拉伸）；
- 几何：`build_hull()` / `build_running_gear()` / `build_skirt()` / `build_turret()`
  里的方块坐标（1/16 格，y=0 是地面，整体以 x=z=0 为中心）；
- 炮塔颊板角度：`build_turret()` 里的 `cheek_ang`，楔形深度改颊板长度即可。

生成脚本自带自检：UV 矩形按货架算法打包进 256×256，没画到的区域是品红色，
预览里看到品红就是某个面的 UV 指错了地方；`extend_edges()` 把每个矩形边缘外扩 1px
防止采样串色。

## 已知限制

- 这是**建模源文件**，不是能直接丢进资源包的模型：进 Java 版要在 Blockbench 里另行
  导出，且 Java 方块模型只接受 22.5° 整数倍的旋转（首上 30°、颊板 55.4° 都会被警告）；
  导出 Bedrock geometry 不受此限制。
- 贴图 256×256 整车共用一张，没有发光/透明通道；履带是"视觉环"（中段无带体），
  近距离贴着看会穿帮。
- 炮塔楔形 V 区在阶梯板和炮盾之间留了一条凹槽，是刻意的阴影缝；真车那个位置
  是炮盾楔块直接顶到颊板。
