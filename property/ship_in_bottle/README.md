# 瓶中帆船

> 本文件夹是「瓶中帆船」的自包含目录：工程、贴图、预览都在这里。共享脚本在 `../tools/`，总索引见 [../README.md](../README.md)。

Blockbench 工程：一只半透明玻璃瓶，瓶底铺着沙床和海面，里面封着一艘全套帆装的小帆船——
主桅带着瞭望旗**伸进瓶颈**，是经典瓶中船的姿势。

> **注意：本工程现在是 Blockbench 5.0 格式**（`meta.format_version = "5.0"`）——它在 Blockbench 里被打开
> 保存过，组的 origin/rotation 已移到顶层 `groups` 表，文件也不再是生成脚本的输出格式。
> 重跑 `../tools/build_ship_in_bottle.py` 会把它写回 4.5 并**覆盖掉在 GUI 里做的修改**。
> 几何已核对未变：4.5 与 5.0 两个版本用同一渲染器渲染逐像素一致；离线渲染器已支持两种格式。

| 文件 | 说明 |
|---|---|
| `ship_in_bottle.bbmodel` | Blockbench 工程（64×64 贴图以 base64 内嵌，可直接打开） |
| `ship_in_bottle.png` | 同一张贴图，单独导出 |
| `ship_in_bottle_preview.png` / `_front.png` / `_side.png` | 三个角度的离线渲染预览 |
| `../tools/build_ship_in_bottle.py` | 一键生成脚本 |

## 设计

尺寸（1/16 格为单位，`y=0` 是瓶底，船头朝 -Z/北）：瓶足 12×16，总高 31（≈1.94 格）。47 个方块。

- **玻璃瓶**：中空外壳——底板 1 格厚，瓶身四壁 1 格厚（内腔 10×14×14），两级切角溜肩（角上的空缺就是切角），
  4×4 瓶颈、6×6 瓶口沿、4×4 软木塞收顶。玻璃是**真半透明**：浅蓝底色 α≈0.18 + 更实的边框 + 近实心的白色斜向反光，
  透过瓶壁能看清船，同时保留原版玻璃的观感；
- **海**：瓶底一层沙（带贝壳点），上面 1 格深的水面贴着玻璃（边缘一圈泡沫线 + 波纹），
  水面正好齐 keel 底，船是"浮"在水上的；
- **船体**：深色橡木龙骨 + 船首/船尾/船舷板（横板缝线），船首收分出船头尖，金色的舷缘护栏绕一圈；
- **尾楼**：舱房正面有亮着灯的窗和门（金色门把手），坡屋顶出檐 0.5 格，船尾板上两扇亮窗，
  顶上还有一盏发光灯笼；船尾水下挂着舵；
- **帆装**：前桅（顶到 y=17，贴着溜肩下沿）+ 主桅（沿瓶身/溜肩/瓶颈的空腔一路伸到瓶颈里，y=22）；
  前帆 6×4、主帆 6×6（帆脚齐舷缘、红色帆脚缘、帆面有织纹和拼缝），两张帆各压一根 7 格长的帆桁；
  船首斜桅 50° 翘出船头，一面三角帆从斜桅尖绷到前桅；四条侧支索（0.25 格细线）从桅杆斜拉到舷缘；
  主桅顶一面红旗飘进瓶颈。

## 骨骼

```
ship_in_bottle
├─ sea                  沙 + 海面
├─ ship
│  ├─ hull              龙骨 + 船壳 + 甲板 + 舷缘
│  ├─ sterncastle      舱房 + 屋顶 + 灯笼
│  └─ rig              桅/帆桁/帆/三角帆/斜桅/旗/舵/支索
└─ bottle              玻璃壳 + 瓶口 + 软木塞（最后画，罩在内容上面）
```

## 重新生成 / 改动

```bash
python ../tools/build_ship_in_bottle.py
python ../tools/preview_bbmodel.py ship_in_bottle.bbmodel ship_in_bottle_preview.png       --azimuth 225 --elevation 14 --distance 55 --target 0 15 0 --ground 9.5
python ../tools/preview_bbmodel.py ship_in_bottle.bbmodel ship_in_bottle_preview_front.png --azimuth 180 --elevation 10 --distance 55 --target 0 15 0 --ground 9.5
python ../tools/preview_bbmodel.py ship_in_bottle.bbmodel ship_in_bottle_preview_side.png  --azimuth 90  --elevation 10 --distance 55 --target 0 15 0 --ground 9.5
```

- 玻璃浓淡：`GLASS` / `GLASS_FRAME` / `GLASS_STREAK`（rgba，末位是 alpha，255 为不透明）；
- 调色板：`CORK` / `SAND` / `WATER` / `HULL` / `DECK` / `MAST` / `GOLD` / `SAIL` / `HEM`；
- 几何：`build_tree()`，瓶颈空腔是 x -1..1、z -1..1、y 19..27——想让桅杆伸得更高先看这里；
- 旋转件：斜桅 (50°)、三角帆 (-56.3°)、旗 (-8°)、四条支索 (∓30°/∓20°)，都是绕单轴的元素旋转。

## 已知限制

- 半透明玻璃依赖视口的 alpha 渲染（已核实 Blockbench 给贴图用 `transparent:true, alphaTest:.05` 的
  Lambert 材质，default 渲染模式即可）。离线预览器为此改成了**两段式渲染**：先画全部不透明面，
  再按远→近排序画半透明面且不写深度——旧模型渲染结果逐字节不变。
- 只有玻璃有半透明；海水和船体全是实心。从上往下看瓶口能看进瓶里，但瓶身内腔之间是封死的格挡。
- 斜桅尖、三角帆下角离瓶壁只剩 0.05~0.7 格，改船体长度时注意别顶穿玻璃（内腔 z 边界 ±7）。
- 同前：建模源文件。半透明 + 非 22.5° 旋转（斜桅 50°、支索 20°/30°）意味着 Java block model 导不了，
  Bedrock geometry 可以。