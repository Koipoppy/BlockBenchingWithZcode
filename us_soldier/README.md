# 荷枪实弹的现代美军士兵

> 本文件夹是「美军士兵」的自包含目录：工程、贴图、预览都在这里。共享脚本在 `../tools/`，通用约定见 [../README.md](../README.md)。

Blockbench 工程：一个原版骨架的现代美军步兵——头 8³、躯干 8×12×4、手臂/腿各 4×12×4，
**双手持枪、M4 系卡宾枪斜挎胸前**（枪口朝左上、仰角 41°）。含头盔（暗色盔罩 + NVG 座）、
拾音降噪耳机 + 喉震麦、防弹背心（三弹匣袋 + 姓名条/军种条/军衔 + 两侧杂物袋）、
腰带（烟雾弹/破片手雷）、突击背包 + 电台 + 越过左肩的鞭状天线、右腿下挂手枪枪套、
护膝、作战靴。整体座标包围盒 19.3 × 33.4 × 14.4（身高 2.09 格）。

| 文件 | 说明 |
|---|---|
| `us_soldier.bbmodel` | Blockbench 工程（128×128 贴图以 base64 内嵌，可直接打开） |
| `us_soldier.png` | 同一张贴图，单独导出 |
| `us_soldier_preview.png` | 默认视角（Blockbench 打开工程时的相机角度） |
| `us_soldier_preview_front.png` / `_left.png` / `_right.png` / `_back.png` | 正/左/右/背四个角度 |
| `us_soldier_preview_detail.png` | 上半身特写（看手怎么握枪、装备层次） |
| `us_soldier_crosscheck_mcp.png` | **第三方渲染器**（headless MCP 的 bb-render / three.js）出的同模型 3/4 视角，用来交叉验证姿态 |
| `../tools/build_us_soldier.py` | 一键生成脚本（调色板、几何、姿态求解、贴图全在里面） |
| `../tools/bbmodel_kit.py` | 本轮新抽出的共享库：格式变换代数 + 三项结构自检 |

## 姿态是算出来的，不是摆出来的

手臂是**两节骨链**（上臂 5 单位、肘到拳心 6 单位），脚本用闭式二骨 IK 把两只手
解到武器上，再把卡宾枪自己的组旋转反解出来。关键数字（脚本每次运行都会重算并断言）：

| 量 | 值 |
|---|---|
| 握把点（右手拳心） | `(2.6, 15.4, -4.8)`，距右肩 9.54 |
| 护木点（左手拳心） | `(-1.51, 19.1, -5.69)`，距左肩 8.48 |
| 右臂 | 上臂 `(8.66, 0, -3.92)°`、前臂 `(37.3, 0, -50.92)°`，肘 `(6.46, 17.57, -0.75)` |
| 左臂 | 上臂 `(18.23, 0, 13.49)°`、前臂 `(41.61, 0, 75.89)°`，肘 `(-5.69, 17.88, -1.56)` |
| 枪口方向 | `(-0.734, 0.660, -0.159)`，仰角 41.3° |
| 枪口世界座标 | `(-7.67, 24.65, -7.03)`（在他左肩外侧、头侧 3.7 单位处，不遮脸） |
| 枪托世界座标 | `(8.03, 10.51, -3.62)`（右胯外侧） |
| 卡宾枪组旋转 | `(-84.69, 54.98, -65.69)°`（抵消手臂链的旋转，使枪身回到设计朝向） |
| 整体包围盒 | `(-10.05, 0, -9.13)` ～ `(10.05, 33.4, 6.2)`，身高 2.09 格 |

握把点的深度（`z`）是**看图定的**：换成 `-4.2` 会压到下巴、`-6.0` 又整把枪浮在胸前，
渲染三张同视角候选图后取中间值 `-4.8`。改这个数会连带重解两只手的角度与枪的组旋转。

`verify_pose()` 会按 Blockbench 真实的复合方式（每层 `T(origin)·Rz·Ry·Rx·T(-origin)`，
子节点用绝对座标、父 origin 在挂接时被减掉）把整条链重算一遍，断言四个量误差 < 1e-6：
两个拳心落在握把/护木点上、枪口落在枪管轴线上、枪身"上"方向等于设计朝向。
实测误差都是 **1e-15 量级**（也就是"这台机器上能算到的极限"，等于说这套公式和
Blockbench 的实现是同一件事）。

> 组旋转是 4.5 格式的合法特性，不是猜的：`js/formats/bbmodel.js` 在读取时对
> **带 `name` 的 outliner 节点**走 "Legacy group support" 分支 `new Group(node, node.uuid)`，
> 而 `origin`/`rotation` 正是 `Group.properties` 里的两项；`js/outliner/outliner.js` 的
> `updateTransform` 对 `use_absolute_position` 的父节点做 `mesh.position -= parent.origin`。
> 换句话说：**组旋转 = `T(origin)·R·T(-origin)`，子元素写绝对座标**——本题的整个姿态都建立在这条上。

**组的两份表都写了**：outliner 节点内联 `name/origin/rotation/children`（4.5 legacy 路径），
**同时**写一份顶层 `groups` 表（5.0 布局）。两边 uuid 一致，Blockbench 加载时按 uuid 合并、不会重复。
这么做是因为实测发现：**只写内联那份时，Blockbench 本体与它的 validator 都正确，
但第三方渲染器（bb-render）会渲染成复位姿态**——它只认顶层 `groups` 表。
交叉验证就是靠这条抓到的（`us_soldier_crosscheck_mcp.png` 是补上 `groups` 表之后、
第三方渲染器给出的姿态正确的结果）。

## 骨骼（可直接做动画）

```
us_soldier
├─ body (0,12,0)                       躯干 + 护甲 + 腰带 + 背包 + 天线 + 手雷
│  ├─ head (0,24,0)                    头 + 头盔 + 耳机 + 麦克风
│  ├─ right_arm (6.5,22.5,0)           上臂 + 肩甲（外侧面画美国国旗）+ 护肘
│  │  └─ right_forearm (6.5,17.5,0)    前臂 + 手套拳
│  │     └─ carbine (6.5,11.5,0)       整枪（跟随右手，见下）
│  └─ left_arm (-6.5,22.5,0)           上臂 + 肩甲（外侧面画部队臂章）
│     └─ left_forearm (-6.5,17.5,0)    前臂 + 手表 + 手套拳
├─ right_leg_grp (2.75,12,0)           腿 + 裤脚束口 + 靴 + 护膝 + 枪套 + 绑带
└─ left_leg_grp (-2.75,12,0)           腿 + 裤脚束口 + 靴 + 护膝 + 大腿口袋
```

正面朝 -Z（北），所以他的右手在 +X、左手在 -X（组名按解剖学命名）。

**卡宾枪挂在 `right_forearm` 下**：动右臂，枪跟着走（这是把枪放在手下的意义）。
代价是左手不会自动跟——做动画时要么让左臂跟着右臂反向补，要么把 `left_forearm`
的旋转 K 成与右手一致的轨迹。脚本里那两个前臂角度（`-65.86°` / `93.81°`）就是这条约束的解。

## 重新生成 / 改动

```bash
python ../tools/build_us_soldier.py         # 打印姿态自检 → 结构自检 → 写出 .bbmodel 与 .png
python ../tools/preview_bbmodel.py us_soldier.bbmodel us_soldier_preview.png        --azimuth 225 --elevation 19.47 --distance 60 --target 0 12 0 --ground 8
python ../tools/preview_bbmodel.py us_soldier.bbmodel us_soldier_preview_front.png  --azimuth 180 --elevation 6     --distance 62 --target 0 15 0 --ground 8
python ../tools/preview_bbmodel.py us_soldier.bbmodel us_soldier_preview_left.png   --azimuth 270 --elevation 8     --distance 62 --target 0 15 0 --ground 8
python ../tools/preview_bbmodel.py us_soldier.bbmodel us_soldier_preview_right.png  --azimuth 90  --elevation 8     --distance 62 --target 0 15 0 --ground 8
python ../tools/preview_bbmodel.py us_soldier.bbmodel us_soldier_preview_back.png   --azimuth 0   --elevation 12    --distance 62 --target 0 15 0 --ground 8
python ../tools/preview_bbmodel.py us_soldier.bbmodel us_soldier_preview_detail.png --azimuth 240 --elevation 12    --distance 34 --target 0 19 0 --ground 6
```

- 调色板：脚本顶部的 `CAMO`（OCP 迷彩）/ `HELM`（暗色盔罩）/ `GEAR`（狼棕色装具）/
  `WEB`（织带）/ `SKIN` / `GLOVE` / `BOOT` / `RUBBER` / `GUN` / `POLY`(聚合物件) / `METAL` / `OLIVE`(手雷、电台)；
- 贴图：每个材质一个画笔函数（`paint_*`），矩形按 **(材质, 宽, 高)** 去重后由货架打包器装进 128×128；
- 几何：`build_tree()`；姿态参数在文件顶部的 `GRIP` / `MUZZLE_DIR` / `POLE_*`——
  想改持枪姿势，改这几个向量即可，手的落点与组旋转都会重算；
- 想换武器：改 `RIFLE_PARTS`（局部座标：原点在握把、-Z 指向枪口、+Y 是机匣上方）。

## 设计说明（重要）

**没能联网核对参考图**（fandom/萌娘/百度全部不可达，同前几轮），造型按现代美军步兵装备的
公开常识设计：OCP 系迷彩 + 狼棕色装具 + 暗色盔罩。具体到件的取舍：

- **盔**：ACH 形状——贴头的两段式盔体（比头宽 0.5，没有帽檐）、后颈加长片、
  前额 NVG 底座、盔罩下缘暗边。**深色盔罩是刻意的**：浅迷彩盔体压在同一件浅迷彩制服上时，
  渲染出来读作"帽子"而不是"头盔"（见下面的踩坑记录）。
- **脸**：8×8 里 3 行被盔遮住，所以眉眼从第 3 行开始：眉、眼（白+瞳）、鼻影、嘴、
  下颌胡青，两颊各两道迷彩油。耳罩与喉震麦贴在头侧。
- **背心**：前后两块板 + 腰封 + 两条过肩带；胸前三个弹匣袋、姓名条（`tape`）、
  军种条（`tape2`）、中胸军衔臂章（`rank`）。**弹匣袋会被枪挡住**——这是真实的遮挡关系，
  所以又在大腿方向补了两个腰封杂物袋（`sidepouch_*`）保证正面读得到装具。
- **国旗与部队臂章是画上去的，不是加几何**：右臂袖子外侧面用 `flag` 材质（3×2 px 星条），
  左臂用 `unit` 材质（深底 + 四角星）。这样零额外方块、零额外厚度。
- **背包**：狼棕色突击包 + 电台 + 越过左肩的鞭状天线——这一根细天线是"现代士兵"读感的关键件。
- **靴**：鞋底比靴身宽 0.5 并带一圈浅色中底；裤脚在靴口外鼓一圈（束口）。

## 已知限制

- 同前：建模源文件，进游戏需在 Blockbench 里导出。**手臂与枪是带旋转的组**，
  `java_block` 导出会因非 22.5° 倍数告警（`free` 格式无此限制，本工程就是 `free`）；
  25.75° 之类的角度只有 `free` 能表达。要导出给 Java 实体用，需要把姿态烘成零旋转重建。
- 卡宾枪全长约 20 单位（1.25 格）：比真实的 M4（0.85 格）长，是 MC 惯用的"主角放大"，
  为的是 1 px = 1 单位的贴图上还能看清红点镜、弹匣、护木导轨。
- 贴图是 1 像素 = 1 单位（16 px/格，原版密度）："精致"来自层次与配色，
  不是高分辨率。红点镜镜片、国旗、文字条都是 1-3 px 级别的东西。
- 手臂的前臂比上臂细 1 格（`5.3..8.3` vs `4.8..8.8`）：这是为了让肘关节处两段盒子
  不出现共面同向面（会 z-fighting），属于刻意收分，不是笔误。
- 持枪时**右前臂会压进胸甲一点点**（第三方 AABB 口径报 2.0 单位，实际是前臂内侧贴住背心，
  渲染图上看不出穿模）：这是"抱枪贴胸"姿态的代价。把握把点前移可以消除它，
  但枪会浮在胸前失去贴胸的读感（试过 `z=-6.0`），最终选了 `-4.8`。

## 本轮（2026-09-25）新增到工具箱的东西

1. `tools/bbmodel_kit.py`：把 **格式变换代数**（`rot_ZYX` / `euler_ZYX` / `walk_groups`
   的仿射链）与 **三项结构自检**（共面同向面 = z-fighting 风险、姿态后 AABB 接触、
   贴图拉伸报告）抽成共享库。生成脚本 `import` 它。
2. 三项自检在本次建模中各自抓到过真 bug：
   - 共面检查抓到**左大腿口袋镜像写反**（`bx(-1, -4.75, -4.25, ...)` 把负座标又乘了一次
     -1，口袋跑到右腿上和枪套重叠）——纯靠看渲染图很难发现；
   - 共面检查抓到**两条裤腿的束口/鞋底在中线互相压面**（各 0.5 单位）；
   - `face_size` 的 0 像素保护：宽 0.5 的盒子在 Python 里 `round(0.5) == 0`，
     会生成 0 像素的 uv 矩形（numpy 索引越界）。
3. 姿态求解三件套（二骨 IK + 方向→欧拉角 + 组旋转反解）都在 `build_us_soldier.py` 里，
   是通用做法，下一轮做持械角色可以直接抄。
4. **跨读器兼容**：组数据写两份（内联 + 顶层 `groups`），并在 `write_model()` 的注释里
   写明了为什么——这是本轮唯一的"只在第三方工具下暴露"的格式问题。

## 三道门的最终结果

| 门 | 结果 |
|---|---|
| `validate_bbmodel.py`（结构不变量） | `OK`（1/1 valid） |
| headless MCP `bbmodel_validate` | **errors 0 / passed true**；warning 94 条全部可解释：87 条是 AABB 口径的 interpenetration（护肘包前臂、手包机匣这类**有意嵌套**），7 条是 mirror（姿势与装备本来就左右不对称：持枪、右腿枪套、左腿口袋、左手表） |
| 自建渲染器 | 默认视角 + 正/左/右/背 + 特写，6 张逐张看过；画面里无品红像素 |
| 第三方渲染器（bb-render） | 3/4 视角与自建渲染器逐部件一致（见 `us_soldier_crosscheck_mcp.png`） |
| 姿态断言 | 两拳心、枪口位置、枪身滚转，四项误差均 ≤ 4e-15 |
