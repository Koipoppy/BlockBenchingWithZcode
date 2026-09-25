# 雷电将军

> 本文件夹是「雷电将军」的自包含目录：工程、贴图、预览都在这里。共享脚本在 `../tools/`，总索引见 [../README.md](../README.md)。

Blockbench 工程：《原神》雷电将军的**女性体型人形模型**。2026-09-25 按用户给的 MC 风格参考渲染图重做：
不再是"方块人套衣服"，而是用参考图那套建模语法雕出来的身材——**56 单位高（3.5 格）= 7 头身，
腿长到 y31（占身高 55%）**，共 **84 个方块**，128×128 贴图。

| 文件 | 说明 |
|---|---|
| `raiden_shogun.bbmodel` | Blockbench 工程（128×128 贴图以 base64 内嵌，可直接打开） |
| `raiden_shogun.png` | 同一张贴图，单独导出 |
| `raiden_shogun_preview.png` / `_front.png` / `_side.png` / `_back.png` | 四个角度的离线渲染预览 |
| `../tools/build_raiden_shogun.py` | 一键生成脚本 |

## 建模语法（参考图里学到的三件事）

1. **分段渐细**：没有一段肢体是单个方块。腿 = 大腿 3.8 → 3.4 → 小腿 3.1 → 2.8 → 靴筒 2.9，
   手臂 = 三角肌 2.4 → 上臂 2.2 → 前臂 1.7 → 手 1.4，逐级收细才有曲线而不是圆柱堆叠。
2. **薄板做布**：所有布料都是 1 单位厚的板——刘海板、每侧两片鬓发、脑后三层发片、
   腰部两层衣摆、胯前两片垂片、腰后左右各三节的长飘带、袖子的两段喇叭壳。
3. **小方块做五金**：胸口金饰、锁骨两颗绯红绳结、腰带金绳缠绕、袖口金环、靴口金边、发笄。

## 造型（按搜索到的原设定 + 参考图）

近黑紫罗兰长发 + 姬发式刘海 + 胸长鬓发，脑后一条**及小腿长麻花辫**（金环 + 紫流苏 + 金尖）；
白色和服上衣（高领、金色交领、绯红绳饰、胸下紫色纹样带）+ 白色紧身裤（外侧紫色纹样）；
深紫宽袖（金袖口、深紫束带）与腰后深紫长飘带；紫色腰带配金绳与金扣，背后金色蝴蝶结；
暗酒红高跟靴（金靴口、分体鞋跟）；**发饰在她自己的右侧（+X）**——白花 + 金流苏 + 金月牙。

## 骨骼（可直接做动画）

```
raiden_shogun
└─ body (0,31,0)              躯干 + 胸 + 腰带 + 蝴蝶结 + 飘带 + 衣摆 + 垂片（pivot 在胯）
   ├─ head (0,48,0)           头 + 刘海/鬓发/三层脑后发 + 右侧发饰
   │  └─ braid (0,52,5)       12 节麻花辫 + 金环 + 流苏 + 金尖（垂到小腿）
   ├─ right_arm (3.7,46,0)    三角肌/上臂/前臂/手 + 两段喇叭袖
   ├─ left_arm (-3.7,46,0)
   ├─ right_leg (2.2,31,0)    大腿/小腿两段 + 靴筒 + 鞋跟/鞋头
   └─ left_leg (-2.2,31,0)
```

正面朝 -Z（北），所以她的右手在 +X、左手在 -X（组名按解剖学命名，左侧肢体由右侧镜像生成）。
辫子挂在 head 下，甩头时辫子会跟着摆。

## 重新生成 / 改动

```bash
python ../tools/build_raiden_shogun.py
python ../tools/preview_bbmodel.py raiden_shogun.bbmodel raiden_shogun_preview.png       --azimuth 225 --elevation 16 --distance 104 --target 0 28 0 --ground 8
python ../tools/preview_bbmodel.py raiden_shogun.bbmodel raiden_shogun_preview_front.png --azimuth 180 --elevation 8  --distance 104 --target 0 28 0 --ground 8
python ../tools/preview_bbmodel.py raiden_shogun.bbmodel raiden_shogun_preview_side.png  --azimuth 90  --elevation 5  --distance 104 --target 0 28 0 --ground 8
python ../tools/preview_bbmodel.py raiden_shogun.bbmodel raiden_shogun_preview_back.png  --azimuth 0   --elevation 14 --distance 104 --target 0 28 0 --ground 8
```

- 调色板：脚本顶部的 `HAIR` / `SKIN` / `WHITE` / `PURP` / `DARK` / `CRIM` / `MAROON` / `GOLD` / `EYE*` / `PETAL`；
- 贴图：`paint_texture()`（脸在 `paint_face()`，8×8：3 行被刘海盖住，眼睛在第 4~5 行，嘴角第 6 行）；
- 几何：`build_tree()`（右侧肢体 + `mirror_cubes()` 镜像；飘带在 `build_tree()` 末尾追加）；
- 所有面 UV 矩形都是整数像素、逐面独立指定，`unsampled_rects()` 会拦住漏画的矩形。

## 已知限制

- 建模源文件，进游戏需在 Blockbench 里导出（全部方块零旋转，Java/Bedrock 都能导）。
- 身高 3.5 格、贴图 128×128，比原版玩家（2 格 / 64×64）大一档；要压成原版尺寸需整体缩放并重排 UV。
- 麻花辫垂到 y=6（小腿中段），走路动画时建议给 braid 组 K 摆动。
- 脸仍是 8×8 像素的原版分辨率，"精致"靠造型层次和配色（渐变紫眼、金饰、绯红绳、纹样）实现。
