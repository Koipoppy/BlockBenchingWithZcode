# BlockBenchingWithZcode — Blockbench 模型集

模型就是根目录下的各个文件夹：**一个模型一个文件夹，文件夹名 = 模型名**。每个模型文件夹里放：工程（`.bbmodel`）、贴图、预览图、以及它自己的生成脚本 `build_<模型名>.py`（重跑即可复现）。
这里不再逐个登记模型（省得每加一个都要回来改一遍），要看清单直接看目录。

共享工具：

| 文件 | 说明 |
|---|---|
| `tools/preview_bbmodel.py` | 自建离线渲染器（零依赖、可脚本化），`--ground` 可调接触阴影半径；任何 `.bbmodel` 都能渲 |
| `tools/bbmodel_kit.py` | 格式变换代数（`rot_ZYX`/`euler_ZYX`/`walk_groups`）+ 三项结构自检（共面 z-fighting、姿态后接触、贴图拉伸）；`golden_loong` 与 `us_soldier` 的生成脚本会 import 它 |
| `<模型名>/build_<模型名>.py` | 每个模型自己的一键生成脚本（贴图 + 几何 + 写出 `.bbmodel`），就放在该模型文件夹里 |
| `<模型名>/export_bedrock.py` | 手写 Bedrock 几何导出（`compileCube`/`compileGroup` 规则实测自 Blockbench 源码），在 `muscle_creeper/` 里 |
| 工作区 `.mcp/`（本目录之外） | **无头 MCP**：第三方校验 / 渲染 / 导出 / 编辑 `.bbmodel`，不需要 Blockbench 运行；`call_tool.py` 的 `Client` 可 import，用来让生成脚本**通过 MCP 授权**整个工程（金龙的做法） |

> **2026-09-24 修复**：`tools/preview_bbmodel.py` 的逐面 UV 采样条件原本写反了，导致预览图里
> 每个面都被渲染成 180° 旋转（`v` 轴上下颠倒 + 左右镜像）。`bbmodel` 工程本身从来没受过影响
> （Blockbench 里的朝向一直是 README 约定的"从外侧看正立不镜像"），只有离线预览 PNG 受影响。
> 噪点贴图看不出来，方向性贴图（苦力怕的鬼脸）看得出来。所有模型的预览图已用修好的渲染器重出。

格式约定（所有模型通用，实测自 Blockbench 5.2.1 源码）：
**Generic Model (free)** 格式、逐面 UV（`v` 从上往下、从外侧看正立不镜像）、朝向 -Z（北）为正面。

工程格式版本：生成脚本写 `format_version 4.5`；**用 Blockbench 打开并保存过的工程会变成 5.0**
（组的 origin/rotation 移到顶层 `groups` 表，outliner 只剩 uuid 引用），解析脚本两边都要能读。实测 4.5→5.0 保存只改格式、不改几何（渲染逐像素一致），
但在 GUI 里的修改会被重跑生成脚本覆盖。

> **2026-09-27 补充几条实测**（`shirt_skirt_girl` 换装时踩到的，加方块到别人的工程上尤其要注意）：
>
> 1. **往工程里加方块时，每个方块自己的 `box_uv` 要为 `false`**，否则 Blockbench / three-blockbench
>    会**忽略逐面 `uv`**，改按 `uv_offset` 重算盒式 UV（`three-blockbench/dist/geometry/cube.js:43`：
>    `element.box_uv === true ? boxUV(...) : face.uv`）。我们的 `uv_offset` 是 `[0,0]`，于是一整片衣服
>    都采到贴图左上角那片白 —— 而离线渲染器 `tools/preview_bbmodel.py` 只读逐面 uv，**看不出来**。
>    基底那些 `box_uv: true` 的方块没事，是因为它们的 `uv_offset` 和逐面 uv 本来就一致。
> 2. **只在 outliner 节点上内联 `origin`/`rotation`（4.10/4.5 布局）、不写顶层 `groups` 表，会被
>    只认 5.0 的读取器当成"没有组变换"**：手臂不张、裙子的 16 片全部塌回 rest 位置
>    （three-blockbench 只读 `document.groups`）。所以给别人的工程加东西时，最后照样补一份顶层
>    `groups` 表；Blockbench 按 uuid 合并，不会重复。
> 3. **bedrock 实体格式是单贴图（`single_texture`）：给现有工程加的第二张贴图在 GUI 里会被忽略。**
>    面上的 `"texture": 1` 在 Blockbench 里会回落成 0，于是新加的部件去采基底那张图 —— 用户看到的是
>    "裙子变成粉色麻点、身体从裙子里透出来"。**实测：**
>    * Blockbench 5.2.1：裙片贴图错位（用户截图）；
>    * 无头 MCP 的 three-blockbench：正常 —— 它按逐面贴图索引取图，**所以这类 bug 只有 GUI 看得见**；
>    * 结论：加装到别人工程上时，衣服**画进基底贴图没人用的区域**（基底 uv 只到 271，x≥276 整条是空的），
>      全模型只留 texture 0；`shirt_skirt_girl` 的生成脚本就是这么做的，并带两条闸：
>      「所有面只引用 texture 0」和「衣服面采样区里不能有透明像素」。
> 4. 顺带一条渲染器行为：`tools/preview_bbmodel.py` 把 uv 矩形按 `[u1..u2]` **含右端点**采样，
>    所以自画贴图时 rect 四周最好补一圈 clamp 到边缘的外框；只要那圈里有一个透明像素，整张面就会被
>    判成半透明（不写深度）→ 身体会从衣服里透出来。`shirt_skirt_girl` 第一版就是右下角那一个像素。

## 目录结构

**本仓库根目录就是模型工作目录**（2026-09-27 把原来那层 `property/` 拍平到了根）：
一个模型一个文件夹，文件夹名 = 模型名。

```
<仓库根>
├─ README.md            本文件：格式约定 + 共享脚本说明
├─ tools/               共享脚本：离线渲染器 preview_bbmodel.py、格式代数 bbmodel_kit.py，
│                       以及临时输出 out/
└─ <模型名>/
   ├─ <模型名>.bbmodel  Blockbench 工程（贴图 base64 内嵌，双击即看）
   ├─ <模型名>.png      同一张贴图单独导出
   ├─ *_preview*.png    离线渲染的预览图
   └─ build_<模型名>.py 该模型的一键生成脚本（重跑即可复现）
```

每个模型的生成脚本输出目录就是它自己的文件夹，重跑不会散落到别处。
