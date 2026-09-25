# 雷电将军

> 本文件夹是「雷电将军」的自包含目录：工程、贴图、预览都在这里。共享脚本在 `../tools/`，总索引见 [../README.md](../README.md)。

Blockbench 工程：《原神》雷电将军的人形模型，按原版 MC 的玩家骨架做——头 8³、躯干 8×12×4、
细臂 3×12×4（Alex 式）、腿 4×12×4，总高正好 2 格，无任何非方块几何，观感是"游戏里能生成的皮肤实体"。

| 文件 | 说明 |
|---|---|
| `raiden_shogun.bbmodel` | Blockbench 工程（64×64 贴图以 base64 内嵌，可直接打开） |
| `raiden_shogun.png` | 同一张贴图，单独导出 |
| `raiden_shogun_preview.png` / `_front.png` / `_side.png` / `_back.png` | 四个角度的离线渲染预览 |
| `../tools/build_raiden_shogun.py` | 一键生成脚本 |

## 设计说明（重要）

没能联网核对原画（网络封锁同前），造型按角色的公开形象常识设计：淡紫银长发 + 姬发式平刘海 +
胸长鬓发，脑后头发盘成一条**及踝长麻花辫**（金环 + 紫流苏收尾），紫瞳渐变大眼；
淡紫和服配深紫交领 + 白色内领 + 金色胸饰，腰带（obi）金绳镶边、前有金扣、后带金色蝴蝶结；
浅色宽袖（袖口金线 + 深紫袖缘），下身深紫袴裙（前开衩、金缘）配深紫紧身裤袜 + 金脚环；
左鬓戴品红发花 + 金发笄，右鬓一枚小金饰。如果没有想要的细节，改
`build_raiden_shogun.py` 的调色板和 `build_tree()` 即可重新生成。

## 骨骼（可直接做动画）

```
raiden_shogun
├─ body (0,12,0)              躯干 + 腰带 + 蝴蝶结 + 袴裙（pivot 在胯，可坐/弯腰）
│  ├─ head (0,24,0)           头 + 刘海/鬓发/脑后发 + 发饰
│  │  └─ braid (0,24,5.5)     7 节麻花辫 + 金环 + 流苏（垂到地面）
│  ├─ right_arm (5,22,0)      手臂 + 宽袖（袖随臂动）
│  └─ left_arm (-5,22,0)
├─ right_leg (1.9,12,0)
└─ left_leg (-1.9,12,0)
```

正面朝 -Z（北），所以她的右手在 +X、左手在 -X（组名按解剖学命名）。辫子挂在 head 下，
甩头时辫子会跟着摆。

## 重新生成 / 改动

```bash
python ../tools/build_raiden_shogun.py
python ../tools/preview_bbmodel.py raiden_shogun.bbmodel raiden_shogun_preview.png       --azimuth 225 --elevation 22 --distance 74 --target 0 16 0 --ground 8
python ../tools/preview_bbmodel.py raiden_shogun.bbmodel raiden_shogun_preview_front.png --azimuth 180 --elevation 6  --distance 72 --target 0 16 0 --ground 8
python ../tools/preview_bbmodel.py raiden_shogun.bbmodel raiden_shogun_preview_side.png  --azimuth 90  --elevation 8  --distance 72 --target 0 16 0 --ground 8
python ../tools/preview_bbmodel.py raiden_shogun.bbmodel raiden_shogun_preview_back.png  --azimuth 0   --elevation 12 --distance 74 --target 0 16 0 --ground 8
```

- 调色板：脚本顶部的 `HAIR` / `SKIN` / `ROBE` / `DARK` / `GOLD` / `EYE*` / `FLOWER`；
- 贴图：`paint_texture()`（脸在 `paint_face()`，8×8：3 行被刘海盖住，眼睛从第 3 行开始）；
- 几何：`build_tree()`；所有面 UV 矩形都是整数像素、逐面独立指定。

## 已知限制

- 同前：建模源文件，进游戏需在 Blockbench 里导出（全部方块零旋转，Java/Bedrock 都能导）。
- 长辫子垂到 y=0（贴地），做走路动画时辫子会穿地，需要给 braid 组 K 一点摆动或缩短 `braid_7` 以下的段落。
- 头像是 8×8 像素的原版分辨率，"精致"靠配色和层次（渐变眼、金饰、袖口）实现，不是高清脸。