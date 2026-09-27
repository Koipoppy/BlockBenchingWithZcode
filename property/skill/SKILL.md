---
name: blockbench-model-authoring
description: >-
  用代码从零编写 Minecraft 风格的 Blockbench 模型（.bbmodel）：手绘像素贴图、按 MC 面光照做离线渲染预览、
  结构校验、修渲染 bug。用于"做一个 MC 风格的模型 / 道具 / 盆栽 / 雕像 / 方块"、".bbmodel"、"Blockbench 模型"
  这类任务；也用于模型已经做出来但不对劲时——贴图镜像或错位、部分面凭空消失、白色画成灰色、部件互相穿插、
  模型读起来像箱子而不是生物。
---

# 用代码编写 Blockbench 模型

> **本副本是随模型维护的工作版**（property 分支的 `property/skill/`）：做新模型时学到的东西——
> 新的格式事实、新的坑与修复、更省事的做法——请回写进本目录（规则进 SKILL.md，细节进 `references/`）。
> 仓库根目录那份是对应的发布版。细则见 [README.md](README.md)。

## 产出什么

1. `*.bbmodel` —— 能直接在 Blockbench 打开的工程（贴图 base64 内嵌，双击即看）
2. `*.png` —— 同一张贴图单独导出，方便改图或进资源包
3. `preview*.png` —— 离线渲染的预览，其中一张必须用 Blockbench 打开工程时的默认相机角度
4. 生成脚本 —— 调色板、几何、贴图全是代码里的数据，改完重跑即可复现

`example/` 是一次完整产出（霸王花盆栽），`scripts/` 能从零重新生成它。

## 四条决定成败的规则

**1. 格式事实从 Blockbench 自己的源码里读，不要凭记忆或博客写。**

三个最贵的坑，全部实测自本机 5.2.1 的安装包：

- **显式 UV 没有 north/south 翻转**。uv 矩形在"从外侧看这个面"时正立且不镜像
  （`js/util/three_custom.js` 的 `setShape` + `js/outliner/types/cube.js` 的 `updateUV`，
  顶点序和 uv 角的对照表见 [references/bbmodel-format.md](references/bbmodel-format.md)）。
  网上教程和 Blender 导入器里常见的"box net 南北面翻 u"是**另一套约定**，照抄不会报错，
  只会把沿长度方向的渐变（花瓣根暗尖亮、叶片中脉）在南北面上画反。
- **旋转矩阵是 Rz·Ry·Rx（three.js euler `'ZYX'`），绕 `origin`**。这意味着单个元素的旋转
  表达不了"绕轴排布 + 自身倾斜"的复合——每片花瓣要两层：**组**绕 Y 转到角度 θ（pivot 在花头中心），
  **元素**只带绕自己局部 Z 的倾角（pivot 在花瓣根部）。两者复合恰好是"径向朝外并翘起"。
- **模型格式**：`free`（Generic Model）支持骨骼组、任意角度旋转、居中网格，是代码生成模型最稳的默认；
  `java_block` 要求旋转是 22.5° 的整数倍，16° 的花瓣会被警告或丢弃。`euler_order` 默认 `'ZYX'`，
  `forward_direction` 默认 `'-z'`，两者 free 都不覆盖。

bundle 本体是 vite 压缩过的，直接 grep 没用；要读 `resources/app.asar` 里 `dist/bundle.js.map`
的 `sourcesContent`（asar 头部偏移和提取方法见 references/bbmodel-format.md）。

**2. 以像素为单位思考（1 单位 = 1/16 格）。**

小于 1 单位的特征是亚像素：0.4 格的嘴缝渲染出来是噪点，0.45 格的牙缝糊成一条白带。
要么把开口做到 ≥1 格，要么故意让上下牙咬合、用齿列之间 1 格宽的暗缝表达"嘴"。
面的尺寸尽量取整，让 UV 矩形和面 1:1，贴图永不被拉伸。像素画要**沿中线对称**——
一个件的 up 面和 down 面经常从相反方向看同一个矩形，对称就两种情况都对。

**3. 轮廓靠阶梯方块堆出来。**

一个大长方体读作箱子/建筑，不读作生物。MC 模型的"圆润"来自一步 1 格的收分：
上层方块四边各收 1 格叠在下层上面。环绕件（花瓣、领圈、萼片）的起始半径必须 ≥
被环绕体的半宽，否则内段穿进体积里，渲染成一团碎纸——把环下移到被环绕体的下方，
藏在下面的部分本来就该藏住。

**4. 没亲眼看过的渲染等于没渲染。**

Blockbench 应用本身没有无头 CLI（不能脚本开工程截图），所以验证分两层：**自建三道门**
（零依赖、永远可用）加 **第三方对照**（[headless MCP](references/headless-mcp.md)——用 Blockbench
自己的编解码器和另一套渲染器复核，是我们没有 GUI 时能拿到的最接近"真值"的东西）：

| 门 | 工具 | 通过标准 |
|---|---|---|
| 结构 | `validate_bbmodel.py`（minecraft-animation skill 自带，路径见下） | 全部不变量通过 |
| 结构（第三方） | headless MCP `bbmodel_validate` | errors = 0；warning 每一条都能解释（有意的跨组穿插、刻意独立的件要说得出来） |
| UV | 生成脚本内置（每个面采到的矩形必须已绘制）+ 一张**方向性贴图**自检方向 | 0 个未绘制矩形被采样；脸/字母测试贴图正立、不镜像 |
| 结构（几何关系） | `tools/bbmodel_kit.py` 的 `coplanar_conflicts` / `posed_contacts` / `stretch_report` | 共面**同向**面 = 0（反向共面是合法的，故意在用）；接触清单逐条能解释；拉伸项都是刻意收分 |
| 视觉 | `scripts/preview_bbmodel.py` | 默认视角 + 正面两张都逐张看过；画面里品红像素 = 0 |
| 视觉（第三方） | headless MCP `bbmodel_render` / `bbmodel_contact_sheet` | 与自建渲染器**同视角**对比：几何与朝向必须一致（灯光/背景可以不同） |

> **第三方门的用法有一条硬规矩**：一致才算过；**不一致时要以能证伪的那个为准并追查到底**。
> 第三轮就是这么抓到「4.5 内联组旋转第三方渲染器不认」的（pitfalls #22）——自建渲染器与
> Blockbench 校验器两边都说对，只有第三方渲染器给出**不同**结果。另注意第三方的
> `interpenetration` 是 **AABB 口径**（旋转件会大量误报），它只当清单、不当门（pitfalls #23）。

品红是故意的：贴图未绘制区域涂 `(255,0,255)`，任何一个 UV 指错都会在渲染里以品红出现，
一眼可辨。构建期的 UV 门和渲染期的品红扫描是**两条独立的检查**，别用一条替代另一条。

## 流水线

1. **调色板**：每个材质一条明→暗色阶（4-5 档），写死在代码顶部；不要现调 RGB
2. **贴图**：货架打包器把各面矩形装进 64×64 → 每个 rect 一个小画笔函数 →
   `extend_edges()` 把边缘像素外扩 1px，防止相邻矩形串色
3. **几何**：树状组结构，每个方块 `(name, from, to, origin, faces→rect, rotation)`
4. **写 bbmodel**：`meta / resolution / elements / outliner / textures`（最小骨架见 references）。
   也可以**让无头 MCP 来写**（`bbmodel_create` + `bbmodel_edit` 批量授权，金龙的做法，
   见 [references/headless-mcp.md](references/headless-mcp.md)）
5. **校验 → 渲染 → 逐张看**

## 弯曲的躯体：让曲线决定每节的角度

蛇、龙、尾巴、触手这类**长而弯**的身体，不要手算每节的世界坐标，也不要一段段试角度——
把静止姿态**沿一根轴拉直**（金龙是沿 +Z，鼻尖在 -Z），然后：

1. 手画一条**导向曲线**（鼻尖到尾尖 10~13 个控制点，Catmull-Rom 采样 + 弧长表）；
2. 每根骨骼在自己的弧长位置取切线 `t`，造坐标系
   `frame_from(rest轴, 世界轴, 次rest轴, 次世界轴)`（两个基底都右手系，`det=+1`）；
3. 按树的父子关系反解局部旋转：`R_local = R_parent⁻¹ · R_world`（§12）；
4. 用 `walk_groups` 把整棵树重走一遍，核对落点/包围盒/接地/左右镜像。

三个白拿的好处：

- **一条链的两个方向共用一套约定**。颈链的静止朝向是 -Z、脊链是 +Z，喂同一个"尾向切线"
  坐标系进去，自动一个朝前一个朝后——不用为反向链另写一套公式。
- **动画就是给这些角度加相位**。行波写成 `e + A·sin(ωt − k·s)`，`A` 随弧长递增、
  `k` 逐节延迟，一套参数同时给出静止姿态和游动动画（金龙的 `fly_ops` 就 40 行）。
- **末端要摆得比近端大**。振幅均匀 = 整条平移；`A` 从头部 1.1° 递增到尾尖 8.7° 才像游动。

斜构件（龙角、獠牙、爪、鳍条）用 `bar(A, B, 厚, 宽)`：把盒子**未旋转**地挂在 A（= 轴心）、
沿 -Z 伸出 `|B−A|`，旋转角由 §12 的最小滚转公式反解（`rx = asin(d_y)`、`ry = atan2(−d_x, −d_z)`），
于是一块料就精确对准两个端点，不需要试。

## 这次踩过的坑（症状 → 根因 → 修复）

| # | 症状 | 根因 | 修复 |
|---|---|---|---|
| 1 | 花盆下半凭空消失，只剩一个楔形 | 预览器背面剔除把**相机系**面心和**世界系** eye 相减，该剔的没剔、不该剔的剔了 | 剔除测试必须全在世界系：`dot(normal, eye - verts.mean())`。z-buffer 让绘制顺序无所谓，但剔除测试仍要求两侧同一坐标系 |
| 2 | 白牙、眼白渲染成灰色 | 头灯式光照把所有朝向相机的面压到同一亮度，像素画的对比度全在贴图里，被光照抹平 | 改用 MC 方块面光照表（顶 1.0 / 南北 0.8 / 东西 0.6 / 底 0.5），按法线分量**平方**混合，倾斜面（花瓣）自然过渡，正交面精确落在游戏数值上 |
| 3 | 花瓣成一团碎纸 | 花瓣环起始半径 2 < 花头半宽 5，内段穿进头部体积 | 领圈整体下移到花头下方，半径从轮廓外开始；再垫一层绿萼片补层次 |
| 4 | 花头读作箱子 | 一个 10×8×10 长方体 + 方形嘴洞 | skull 拆成 10×8 下块 + 8×6 上块做阶梯收分，脸画在收分后的上块 |
| 5 | 牙缝、嘴缝看不见 | 0.4-0.45 格是亚像素 | 上下牙间隙 ≥1 格；齿列间留 1 格暗缝露出喉咙 |
| 6 | 方向性渐变在部分面反了 | 照搬了 Blender 导入器的南北翻 u 表 | bbmodel 显式 UV 是 WYSIWYG；up/down 面从相反方向看同一矩形的件（Z 向叶片）干脆给两个矩形 |
| 7 | outliner 读成多个根、元素悬空 | group 之间用 uuid 字符串互相引用，写平了引用就断 | 嵌套 group **内联为对象**，元素用 uuid 字符串引用；validator 的"孤儿元素"检查抓的就是这个 |
| 8 | grep app.asar 全是压缩乱码 | bundle 被压缩 | 读 `dist/bundle.js.map` 的 `sourcesContent`（未压缩源码 + 原始路径） |
| 9 | `/tmp/x.png` 写入报 FileNotFoundError | Git Bash 的 `/tmp` 映射对原生 Windows Python 不成立 | 用 `os.environ['TEMP']` 或显式 `C:/` 路径 |
| 11 | 预览里每个面的贴图上下颠倒+左右镜像，噪点贴图却看不出来 | 逐面 UV 角的三元写反：`u1 if cx else u2` 与 `u2 if cx else u1` 是两个相反方向 | 顶点 v0 必须拿矩形左上角 `(u1,v1)`；**用方向性贴图自检**（皮肤布局的脸、字母、箭头），别用噪点贴图验证 UV 方向 |
| 12 | Blockbench 打开保存过的工程，组的旋转"失效" | 5.0 格式把组的 origin/rotation 搬到顶层 `groups` 表，outliner 只剩 uuid 引用 | 解析器两边都读：节点里没有就按 uuid 查组表；仓库里已有一个 5.0 工程（瓶中帆船） |
| 13 | 镜像的件一边贴合一边悬空（"同款造型，就它飘着"） | 镜像函数把**轴心整个取负**：`-v for v in origin` 会把 (11, 35.5) 镜成 (−11, −35.5)，跨 x=0 镜像只该翻 x | 轴心只翻 x：`(-ox, oy, oz)`；再断言对称不变量（每对左右件的世界 AABB：x 之和为 0、y/z 相等）。详见 pitfalls #13 |
| 14 | 旋转的斜板整车乱飞（首上板翘上天空、颊板立到车尾），左侧镜像件被 validator 抓负 extent | 元素的 from/to 是**未旋转姿态**的绝对坐标，和 origin 必须同一处——把"目标区域"当坐标、把几十格外的铰链当轴心，旋转就甩飞；镜像盒子 x 取负后 from>to | 先把板**未旋转**地挂在铰链上（板长=弦长），origin 在铰链，角度由端点落点反解（`θ = atan2(−Δz, −Δy)`）；镜像用 `xbox()` 交换 from/to 两端。详见 bbmodel-format.md §3 与 pitfalls #14 |
| 15 | 姿态校验：旋转全对（err 1e-16）但手离目标 0.47/1.35 单位 | 组链的**平移**推错：多层复合时每层贡献 `(I-R_i)·o_i`，且被更深层的父旋转搬运；`R'` 必须是**父在左** | 沿树下推 `R' = R @ R_local`、`t' = t + R @ (I-R_local) @ o`；`walk_groups` 返回 `(R,t)` 并断言 `R·p+t`。见 pitfalls #15 |
| 16 | 挂在手下的武器差 20 单位（≈枪长）且绕握把转错 | 局部偏移**多乘了一次**组旋转：组旋转本身已作用一次，`p_authored = pivot + L` 才是原样 | 节点旋转取 `R_local = R_chain⁻¹·R_world`、子方块座标写 `pivot + L`。见 pitfalls #16、bbmodel-format.md §12 |
| 17 | 无可见症状，检查器报 42 处共面同向面 | 两个面共面、同向、投影面积重叠 = z-fighting（贴图/几何数据全合法，validator 不查） | 只报**同向**（反向背靠背合法、故意在用）；本轮据它抓到镜像写反的口袋与中线互压的裤脚。见 pitfalls #17 |
| 18 | 复位坐标系里一片穿模，渲染图却正常 | 带旋转的件在复位姿态下不是渲染姿态 | 检查分两档：同链/双静止件严格判共面；涉旋转件改判**姿态后 AABB 接触**当清单。见 pitfalls #18 |
| 19 | 小矩形画笔抛 `IndexError: size 1` | 0.5 单位的件 `int(round(0.5)) == 0`（Python 银行家舍入）⇒ 0 像素 uv 矩形 | `face_size` 一律 `max(1, round())`；<1 单位的件本身就不该存在。见 pitfalls #19 |
| 20 | 头盔怎么做都像宽檐帽/渔夫帽（削宽、去阶梯、去 3D 盔带、压到眉线都没用） | **明度**问题：浅色盔罩压在浅色迷彩制服上读成同一坨 | 盔罩整体压暗（暗橄榄），只留一圈淡下缘 + 后颈加长片；MC 官方盔也是靠材质色区分头盔的。见 pitfalls #20 |
| 22 | 自建渲染器姿态正确，第三方渲染器渲染成**复位姿态**；同一份文件第三方校验器却报告旋转后的包围盒 | **4.5 内联组旋转只有 Blockbench 本体读**；bb-render 只认 5.0 顶层 `groups` 表 | 组的两份表都写（内联 + 顶层 `groups`，uuid 相同，Blockbench 按 uuid 合并）。见 pitfalls #22 与 bbmodel-format.md §12 |
| 23 | 第三方报 87 条穿插、最深 4.69 单位 | 该门口径是 **AABB**（旋转件包围盒很胖），且**有意的嵌套**（护肘包前臂、手包机匣）也会报 | 清单逐条解释：嵌套/握持可解释，并列件互吃 >1 格不可解释；真实可见性以渲染图为准。见 pitfalls #23 |
| 10 | 想查参考图，直连页面不可达 | WebSearch 摘要可用（M1A2 一次检索就拿到了炮塔布局/轮数/产量等史实），但 WebFetch 直连 wikipedia/fandom/百科全部超时，**拿不到图** | 文字资料用 WebSearch 摘要；美术细节仍按名称 + 题材惯例设计并**显式声明是假设**，或让用户贴参考图 |
| 15 | `npm i github:用户/仓库` 报 `git@github.com: Permission denied (publickey)` | npm 把 `github:` 规格解析成 **SSH** 地址（`git@github.com:...`），本机没有 GitHub SSH key | 改用 HTTPS tarball：`npm i https://github.com/用户/仓库/archive/refs/heads/main.tar.gz`。另外**包名可能与仓库名不同**（仓库 `blockbench-mcp-plugin` → 包 `blockbench-mcp`），别按仓库名找 `node_modules/` 下的目录 |
| 16 | 无头工具改完的模型在 Blockbench 里"看不到变化"；或写入被拒 | 应用**不重载**磁盘上变化的文件；写入会被打 `ai_used`/`ai_agents` 标记；路径必须落在某个 `--root` 内 | 改完在 GUI 里重新打开，别两边同时改同一文件；`--no-ai-disclosure` 关标记；把产物目录也加成 `--root`（否则只能写进模型目录） |
| 17 | 手写的 Bedrock 导出比 Blockbench 少一层骨架 | 导出器没有为模型本身发一根 **root 骨骼** | 与 headless MCP 的 `bbmodel_export_bedrock_geometry` 对照：11/11 方块的几何+UV 完全一致，对方多一根以模型名命名的 root bone（9 vs 8）；补上即可，详见 [references/headless-mcp.md](references/headless-mcp.md) |
| 24 | 龙身贴图读成"藤编 / 竹节"，不是鳞 | 鳞片画成了完整方格网格（行缝 + 侧缝都画满） | 只画**游离边**：一条 U 形暗缝（`v2 = v + 0.30·(2|u−0.5|)²` 后再取 `(v2−0.70)/0.30`），砖排错位、明度压到色阶中段。坑 6 的方向性自检仍然要跑 |
| 25 | 鼻孔从上方看变成第二对"眼睛"，越改越小也没用 | 把鼻孔做成了**凸出的小方块**——任何凸出件从上方看都会露出顶面 | **细节不该是几何**：鼻孔画在鼻端的 `panel()` rect 上，只让那一面指过去（`faces={"north": …}`），并压到吻部下方 1/4 处 |
| 26 | 整条龙读成"白肚皮"，不是金鳞 | 象牙腹甲又宽又亮（几乎用到色阶最亮档），而且宽度没给金边留位置 | 腹甲只用色阶中段（`lo/hi` 夹住）、两侧留出金边；颈/胸另走更暗的一档（`throat`） |
| 27 | 四条腿像桌腿，不像兽腿 | 每节骨的世界朝向都太接近竖直，没有折角；且滚转没定，"最小滚转"公式把爪子转歪 | 每条腿给真实折角（肘朝后 + 前臂朝前 = Z 形，后腿膝/跗同法），并用**正面参考向量**定滚转（`frame_from(rest下, 骨向, rest前, 前参考)`） |
| 28 | 姿态是 S 形的生物模型被 `mirror` 门全量报违规 | 该门比的是**世界坐标**盒子，非平面姿态本就不关于 x=0 对称（它的 `self_test` 自己会标 `discriminates: false`） | 别关灯也别逐个加 `asymmetric`：自己在**未姿态空间**查镜像关系（比较旋转**矩阵**而不是欧拉三元组），详见 [references/headless-mcp.md](references/headless-mcp.md) |

详细的定位过程（包括怎么一步步锁定坑 1 那个 bug 的）在
[references/pitfalls.md](references/pitfalls.md)。

## 修复渲染 bug 的套路

模型"看起来不对"时，按这个顺序排查，每步都能排除一类原因：

1. **结构**：跑 validator。缺面/穿模/悬空引用先在这里现形
2. **单独渲染可疑件**：把疑似部件单独画一张。单独画是对的 → 是遮挡/剔除问题；单独画也是碎的 → 是几何或 UV 问题
3. **数像素**：对缺失区域取一个像素，遍历所有三角形算重心坐标，看谁覆盖它、谁的 depth 最小——覆盖它的四边形列表会直接说出真相（坑 1 就是这么定位的：覆盖该像素的只有一个四边形，就是那个"消失"的面本身）
4. **看贴图**：把 atlas 放大 8 倍逐 rect 检查，确认画的是你以为是的东西
5. **对照 Blockbench 源码**：涉及 UV / 顶点序 / 旋转 / 相机的一切，以 `app.asar` 的 source map 为准，不以记忆为准
6. **对照第三方实现**：`bbmodel_validate`（结构、对称、悬空）+ `bbmodel_render`（同视角比几何与朝向）。
   两个渲染器不一致时，先怀疑自建的那个——它没经过 Blockbench 编解码器的校验；
   对方是独立实现且直接跑 Blockbench 的导出规则，是"我看到的"和"Blockbench 会渲染成什么"之间最近的一环

## 环境

- Blockbench 5.2.1 安装在 `C:\Users\chenyuchong\MyApp\blockbench`（`Blockbench.exe` + `resources/app.asar`）
- 系统带 Python 3.13 + Pillow + numpy（贴图和渲染全靠它）
- 共享自检库 `tools/bbmodel_kit.py`（格式变换代数 + 共面/接触/拉伸三项检查）：新模型应当 `import`
  它而不是各自复制一份；从第三个模型起，这一套能省掉一整轮试错
- 结构校验脚本：`C:\Users\chenyuchong\.agents\skills\minecraft-animation\scripts\tools\validate_bbmodel.py`。
  如果它不在了，references/bbmodel-format.md 列出了它检查的全部不变量，可以照着重写
- 渲染器 `scripts/preview_bbmodel.py` 是通用工具，任何 `.bbmodel` 都能渲染：
  `python scripts/preview_bbmodel.py 模型.bbmodel 输出.png --azimuth 225 --elevation 19.47 --distance 60 --target 0 12 0`
- **无头 MCP（第三方校验 / 渲染 / 导出 / 编辑）**：装在 `C:\Users\chenyuchong\MyApp\blockbench\.mcp`，
  由工作区配置 `blockbench/.zcode/config.json` 的 `mcp.servers.blockbench-headless` 接入 ZCode
  （会话启动时加载，所以原生工具下一次会话才出现）。当下就能用：
  `cd blockbench/.mcp && python call_tool.py bbmodel_validate '{"file": "cottage/cottage.bbmodel"}'`。
  工具清单、安装坑、与自建工具的对照结论见 [references/headless-mcp.md](references/headless-mcp.md)
