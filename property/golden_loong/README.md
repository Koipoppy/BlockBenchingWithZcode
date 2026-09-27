# 金龙 (golden loong)

> 本文件夹是「金龙」的自包含目录：工程、两张贴图、预览都在这里。共享脚本在 `../tools/`，总索引见 [../README.md](../README.md)。

一条中国龙（loong，不是西方带翼龙）：蛇形长身、鹿角、牛耳、狮鬃、长须、四爪、火焰尾，
身前悬着一颗发光的**宝珠**。**199 个方块、41 个组、两张 1024×1024 贴图**
（`_body` 普通 / `_glow` 自发光），外加一条 3 秒的**腾云游动循环**动画。

本轮沉淀的经验（用 MCP 授权整个工程的流程与四个实测要点、`mirror`/`interpenetration` 两道门"用不上"的
情形、"弯曲的躯体：让曲线决定每节的角度"、以及鳞画成网格 / 鼻孔做成几何 / 腹甲过亮 / 腿太直 /
非平面姿态撞 mirror 门这几个坑）原先回写在 skill 文档里；**那份 skill 已于 2026-09-27 按要求整体删除**。

| 文件 | 说明 |
|---|---|
| `golden_loong.bbmodel` | Blockbench 工程（两张贴图 base64 内嵌，可直接打开） |
| `golden_loong_body.png` | 主贴图（鳞、腹甲、鬃、角、爪、眼、口腔），单独导出 |
| `golden_loong_glow.png` | 自发光贴图（宝珠、火焰尾外刃），单独导出 |
| `*_preview.png` / `_front` / `_side` / `_back` | 四角度离线渲染预览 |
| `*_preview_default_camera.png` | **Blockbench 打开工程时的默认相机**（见"已知限制"：这个机位对 9 格长的模型是贴脸特写） |
| `../tools/build_golden_loong.py` | 一键生成脚本（**通过本机 MCP 服务端授权工程**，见下） |

## 这个工程是怎么做出来的（和本仓库其它模型不同的一点）

其它模型的生成脚本直接把 `.bbmodel` JSON 写出来（4.5 格式）。金龙的脚本**不写文件**，
而是把模型交给本机的 `blockbench-headless` MCP 服务端去建：

```
bbmodel_create        → 空的 free 格式工程（1024×1024）
bbmodel_add_texture   → 内嵌两张画好的 PNG（第二张 render_mode=emissive）
bbmodel_edit          → add_group ×41 + add_cube ×199（每批 ≤400 op）
bbmodel_edit          → add_animation ×1 + set_keyframe ×546
```

脚本用 `../.mcp/call_tool.py` 里的 `Client` 直接跟服务端讲 MCP（stdio + JSON-RPC），
所以 op 的 JSON 全程不经过人眼、也不用复制粘贴。好处是格式由服务端负责：工程落到盘上就是
Blockbench 自己保存的 5.0 布局（组的 origin/rotation 在顶层 `groups` 表）。

## 造型

**配色**：金鳞身体 + 青玉鬃/背鳍/须 + 象牙腹甲/鹿角/爪 + 绯红口腔 + 琥珀发光眼/宝珠。
所有颜色写死在脚本顶部的色阶里（`GOLD`/`JADE`/`IVORY`/`HORN`/`MAW`/`DARK`/`GLOW`），每档 6 级明暗。

**两张贴图各自的底色是故意的**：主贴图未绘制区是品红（`(255,0,255)`，本仓库的约定：
任何 UV 指错都会在渲染里以品红现身），自发光贴图底色是**黑**（品红会发光）。
两张都在 `Atlas.finalize()` 里把每个 rect 的边像素外扩 1 px 到留白里，
所以就算某个面的 UV 落在 rect 边界上也不会采到隔壁。

**"精致"落在三处**：

1. **鳞**：贴图里只画鳞片的**游离边**——一条 U 形暗缝（`Atlas.scales` 的 `v2` 项）。
   画成方格网格会让整条龙看起来像藤编；只画一条弯曲阴影才有"叠压"的鳞感。
   身体 2 px/单位、头部 3 px/单位（脸是给人看的地方，多给纹理密度）。
2. **头**：颅骨 → 冠 → 眉脊 → 吻 → 鼻，逐级收窄分五层，不是一个大盒子；
   眼球凸出于眼窝、上方压一道厚眉脊；上颚两颗獠牙垂到唇线以下；**鼻孔画在鼻端面板上**
   （做成凸出的小方块的话，一从上方看就变成第二对眼睛）。
3. **龙角**：主枝 3 段 + 2 根分叉，全部由 `Model.bar()` 生成——
   从两点坐标反解"最小滚转"欧拉角（§12 公式），所以每根角都是精确对准端点的斜板。

## 姿态是解出来的，不是手填的

静态姿态来自一条手画的**导向曲线**（`GUIDE`，从鼻尖到尾尖 13 个控制点，Catmull-Rom 采样）。
每个骨骼在自己的弧长位置取切线，用 `frame_from(rest轴, 世界轴, …)` 造一个"最小滚转"坐标系，
再按树的父子关系反解局部旋转：

```
R_local = R_parent⁻¹ · R_world        （bbmodel-format.md §12）
```

这样做的直接好处：**颈链和脊链可以共用同一套切线约定**——颈链的静止朝向是 -Z、脊链是 +Z，
同一个"尾向切线"坐标系喂进去，自动一个朝前一个朝后。姿态定完还会用
`bbmodel_kit.walk_groups` 把整棵树重走一遍（`posed_boxes`），确认落点、包围盒、接地，
以及 L/R 零件在**静止空间**里逐轴精确镜像（33 对，见 `mirror_report`）。

## 骨骼（可直接做动画）

```
loong (0,0,0)                     根；动画里做整体上下浮动
├─ body (0,0,16)                  胸腔 + 两肩 + 腹甲（躯干 pivot 在胸中）
│  ├─ neck_1 → neck_2 → neck_3     三节渐粗的颈
│  │  └─ head                      颅/冠/眉/吻/鼻/眼/耳/颊鳍 + 鹿角×2 + 须×2(各两节) + 鬃 + 颊鬃
│  │     ├─ jaw                    下颌（含舌、下獠牙）；动画里开合
│  │     │  └─ beard               颌下龙髯
│  │     ├─ antler_L / antler_R    角
│  │     └─ whisker_L/R → whisker2_L/R
│  ├─ fleg_a_R → fleg_b_R → fleg_c_R    肩/上臂 → 肘/前臂 → 掌（含 4 爪 + 肘鳍）
│  ├─ fleg_a_L → …（左侧镜像）
│  └─ spine_1 → spine_2 → spine_3 → spine_4 → spine_5
│     ├─ hleg_a_R → hleg_b_R → hleg_c_R  胯/股 → 膝/胫 → 跗（含 3 爪 + 胯鳍）
│     ├─ hleg_a_L → …（左侧镜像）
│     └─ tail_1 → … → tail_6 → tail_fin  六节渐细的尾 + 火焰尾扇（外刃自发光）
└─ pearl (…)                       宝珠：7.6 方核心 + 3 片拖尾 + 2 道火舌，全自发光
```

正面朝 -Z（北），所以龙的右侧在 +X（组名 `_R`，`_L` 由右侧镜像生成）。
尾部六节链、颈部三节链都是可动画的，沿链做相位差就是游动。

## 动画

`animation.golden_loong.fly`——3 秒循环，`catmullrom` 插值，**41 根骨骼共 546 帧**
（宝珠另有一条缩放通道，`loong` 根一条位移通道）：

- 躯体 17 节链：沿体长 1.55 个波长的行波，**振幅从头部 1.1° 递增到尾尖 8.7°**
  （末端摆得更大才像游动而不是整体平移），俯仰 + 偏航相差 90° 相位，走的是螺旋波；
- 四肢：三节各按相位差摆动（左右再错 0.35 弧度），前肢相位 0.25、后肢 0.75；
- 拖尾件（鬃、颊鬃、髯、须、角）按 0.4→1.3 的延迟跟随头部——**同一条动物**的感觉就靠这个；
- 下颌每循环开合两次；`loong` 根做 1.8 单位的上下浮动，宝珠浮动 2.6 并做 6% 呼吸缩放。

实测循环首尾严格重合（t=0 与 t=3.0 的采样包围盒逐位相同），整圈最低点只在 y 4.0↔12.2
之间浮动（不触地、不弹跳）。`bbmodel_validate_animations` 四道门全过。

## 重新生成 / 改动

```bash
cd ../            # property/
python tools/build_golden_loong.py          # 重新授权工程（会覆盖 .bbmodel）
python tools/preview_bbmodel.py golden_loong/golden_loong.bbmodel golden_loong/golden_loong_preview.png      --azimuth 225 --elevation 20 --distance 250 --target 0 48 0 --ground 6 --size 900
python tools/preview_bbmodel.py golden_loong/golden_loong.bbmodel golden_loong/golden_loong_preview_front.png --azimuth 180 --elevation 8  --distance 240 --target 0 50 0 --ground 6 --size 900
python tools/preview_bbmodel.py golden_loong/golden_loong.bbmodel golden_loong/golden_loong_preview_side.png  --azimuth 90  --elevation 5  --distance 240 --target 0 50 0 --ground 6 --size 900
python tools/preview_bbmodel.py golden_loong/golden_loong.bbmodel golden_loong/golden_loong_preview_back.png  --azimuth 10  --elevation 16 --distance 240 --target 0 50 0 --ground 6 --size 900
python tools/preview_bbmodel.py golden_loong/golden_loong.bbmodel golden_loong/golden_loong_preview_default_camera.png --azimuth 225 --elevation 19.47 --distance 60 --target 0 12 0 --size 760 --bg 40
```

脚本里改哪儿：

| 想改 | 改哪里 |
|---|---|
| 姿态（起伏、尾圈、抬头角） | `GUIDE`（13 个控制点）与 `solve_pose` 里头部的 -9° 附加俯仰 |
| 肢体朝向 | `FRONT_LEG` / `HIND_LEG`（每个骨的世界朝向 + 正面参考向量） |
| 身体粗细/分段 | `BODY_STATIONS` / `NECK_STATIONS` |
| 背鳍节奏 | `DORSAL`（位置、半长、高度） |
| 颜色 | 顶部色阶；`MARK` 是给校验用的物料色号 |
| 鳞的大小 | `_paint` 里 `gold` 的 `row`/`sw`（像素），以及 `PX`（默认 2 px/单位） |
| 动画 | `fly_ops`（波长、相位、振幅、时长、帧数） |

## 已知限制

- **Blockbench 的默认相机不框这个模型**：`DefaultCameraPresets[0]` 是固定的
  `position (-40,32,-40)` → `target (0,12,0)`，为 2~3 格的模型调的；金龙 9.4 格长、6.3 格高，
  打开工程第一眼是腹甲的贴脸特写（就是 `*_preview_default_camera.png` 那张，
  顺便可以当鳞片的放大样张看）。按一下"适合视图"或滚轮拉远即可。
- **贴图 1024×1024 ×2**，比本仓库其它模型（64~256）大一档：鳞和眼睛需要这个密度。
  进资源包前若要压体积，把 `RES` 降到 512 即可，代价是鳞变糊。
- **33 对 L/R 零件在静止空间里是精确镜像，但姿态本身在 X 上有横向游走**（躯干 S 形），
  所以整个模型**不**关于 x=0 平面对称。MCP 的 `mirror` 门比较的是**世界坐标**盒子，
  在这个模型上会把 47 个零件全部报出来（它的自检也标了 `discriminates: false`）。
  真正该守的不变量——左右件在**未姿态空间**互为镜像——由脚本自带的 `mirror_report` 检查。
- 尾巴的六节链是固定弯曲；做盘绕/缠绕动作需要给 `tail_*` 组另 K 一套旋转。
- 静态姿态已经把 `body`/`spine_*` 的旋转烘进去了，所以**动画的每一帧都从姿态值出发**
  （`fly_ops` 里 `e = rot[g]` 是基准），不要把组的旋转"清零"当默认姿态用。
- 面数 199+ 方块；若要进原版实体，需在 Blockbench 里导出并自行压面。
