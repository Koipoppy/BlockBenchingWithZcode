# 肌肉苦力怕

> 本文件夹是「肌肉苦力怕」的自包含目录：工程、贴图、预览都在这里。共享脚本在 `../tools/`，总索引见 [../README.md](../README.md)。

Blockbench 工程：原版苦力怕的"健身房形态"。原版的辨识度全在 8×8 的脸和迷彩绿上，所以这两样原样保留，
把"肌肉"做在骨架比例和贴图阴影里，不加任何非原版元素。

| 文件 | 说明 |
|---|---|
| `muscle_creeper.bbmodel` | Blockbench 工程（64×64 贴图以 base64 内嵌，可直接打开）——**模型本体是这个文件** |
| `muscle_creeper.geo.json` | Bedrock 几何导出（8 骨骼 + 11 方块 + 逐面 UV），可直接放进 Bedrock 资源包 |
| `muscle_creeper.png` | 贴图（单独导出；Bedrock 包里放 `textures/entity/muscle_creeper.png`） |
| `muscle_creeper_blockbench.png` | 在 Blockbench 里实际打开本工程的截屏（真机验证，不是离线渲染） |
| `muscle_creeper_preview.png` / `_front.png` / `_side.png` | 三个角度的离线渲染预览 |
| `../tools/build_muscle_creeper.py` | 一键生成脚本 |
| `../tools/export_bedrock.py` | 从 bbmodel 导出 Bedrock geometry（换算规则核实自 Blockbench 源码） |

## 打开与使用

- **看模型 / 改模型**：双击 `muscle_creeper.bbmodel`（或 Blockbench 里 File → Open Model）。
  `*.png` 只是贴图和预览渲染，双击它们只会打开贴图查看器，看不到 3D 模型。
- **进 Bedrock 存档 / 资源包**：把 `muscle_creeper.geo.json` 放进资源包的 `models/entity/`，
  `muscle_creeper.png` 放进 `textures/entity/`，实体定义里 `geometry` 引用 `geometry.muscle_creeper` 即可。
- **进 Java 版**：资源包本体换不了原版实体模型，需要 OptiFine 的 CEM 或 mod 加载；Blockbench 里
  File → Convert Project 可以转到对应格式再导出。

## 设计（对照原版）

原版苦力怕（1/16 格为单位）：腿 4×6×4（中心 x=±2, z=±4）、躯干 8×12×4、头 8³，总高 26。
本模型总高 30（≈1.875 格），改动全部围绕"壮"：

- **头**：原版 8³ 不动，经典鬼脸（2×2 眼 + 下垂嘴），UV 也放在原版 64×32 贴图头部那 32×16 的坐标上，
  以后想换成官方贴图直接对得上；
- **躯干 V 字**：胸 14×9×6（宽肩，肩线与手臂顶齐平）→ 腰 8×6×4（正是原版躯干的宽度），
  前面用贴图画了胸肌中缝、下缘阴影和腹肌格；
- **手臂**：原版苦力怕没有手臂——这是"肌肉强化"的核心。上臂 6×9×6 + 前臂 5×5×5，垂到 y=8，
  贴图画了三角肌高光、肱二头肌鼓块和硬折痕；
- **腿**：5×7×5（原版加粗加高），位置仍是四角布局；
- **贴图**：64×64，4 阶原版观感的迷彩绿（2px 块状噪点）+ 纯黑五官。

## 骨骼（可直接做动画）

```
muscle_creeper
├─ body (0,13,0)        胸 + 腰
│  ├─ head (0,22,0)     头
│  ├─ right_arm (-10,21,0)  上臂 + 前臂
│  └─ left_arm  (10,21,0)
├─ right_front_leg (-3.5,7,-4.5)
├─ left_front_leg  (3.5,7,-4.5)
├─ right_hind_leg  (-3.5,7,4.5)
└─ left_hind_leg   (3.5,7,4.5)
```

腿的 pivot 在髋部，手臂的 pivot 在肩部，走路/挥手/膨胀(swell)动画都能直接 K。

## 重新生成 / 改动

```bash
python ../tools/build_muscle_creeper.py       # 重新生成 bbmodel + png
python ../tools/export_bedrock.py             # 重新导出 Bedrock geometry
python ../tools/preview_bbmodel.py muscle_creeper.bbmodel muscle_creeper_preview.png --azimuth 225 --elevation 22 --distance 68 --target 0 15 0 --ground 8
python ../tools/preview_bbmodel.py muscle_creeper.bbmodel muscle_creeper_preview_front.png --azimuth 180 --elevation 12 --distance 66 --target 0 15 0 --ground 8
python ../tools/preview_bbmodel.py muscle_creeper.bbmodel muscle_creeper_preview_side.png  --azimuth 90  --elevation 10 --distance 66 --target 0 15 0 --ground 8
```

- 调色板：`GREEN`（明→暗 4 阶绿）；鬼脸像素在 `paint_face()`；
- 肌肉阴影：`paint_texture()` 里 chest/arm 各 rect 的画法；
- 比例：`build_tree()` 里各方块坐标（`y=0` 是脚底，正面朝 -Z）；
- `--ground` 是预览器接触阴影的半径（本次给 `preview_bbmodel.py` 新增的参数，默认 4.6，盆栽不受影响）。

## 已知限制

- 官方 `creeper.png` 拿不到（网络封锁，两个镜像都失败），绿色是按原版观感手调的；
  头部 UV 坐标特意对齐官方贴图，想换真贴图直接导入重指 UV 即可。
- 头部 6 个面的 rect 在图集里是**无缝**的（原版头盒布局），所以 `extend_edges()` 只往品红空隙里渗边，
  不会污染相邻矩形。
- 同盆栽：这是建模源文件，进游戏需在 Blockbench 里导出（本模型没有非 22.5° 旋转，Java/Bedrock 都能导）。
- 贴图未用到的角落保持品红（图集自检约定）。