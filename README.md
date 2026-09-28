# BlockBenchingWithZcode — Blockbench 模型集

模型按分类放进四层文件夹，**一个模型一个文件夹，文件夹名 = 模型名**：
`兵器/`、`人物/`、`物品/`、`生物/`。每个模型文件夹里放：工程（`.bbmodel`）、贴图、预览图、
以及它自己的生成脚本 `build_<模型名>.py`（重跑即可复现）。
这里不再逐个登记模型（省得每加一个都要回来改一遍），要看清单直接看目录。
第三方素材（别人做的模型包，只做参考、不随分支发布）统一放在 `人工建模参考/`，分类同上一行。

共享工具：

| 文件 | 说明 |
|---|---|
| `tools/preview_bbmodel.py` | 自建离线渲染器（零依赖、可脚本化），`--ground` 可调接触阴影半径；任何 `.bbmodel` 都能渲 |
| `tools/bbmodel_kit.py` | 格式变换代数（`rot_ZYX`/`euler_ZYX`/`walk_groups`）+ 三项结构自检（共面 z-fighting、姿态后接触、贴图拉伸）；`golden_loong` 与 `us_soldier` 的生成脚本会 import 它 |
| `tools/bbmodel_build.py` | 武器脚本的共享脚手架：图集打包 + 画笔库 + 方块词汇 + 写出器（双层 outliner/groups 表）+ 动画键 + 预览渲染；`兵器/` 里的三个武器脚本都 import 它 |
| `<分类>/<模型名>/build_<模型名>.py` | 每个模型自己的一键生成脚本（贴图 + 几何 + 写出 `.bbmodel`），就放在该模型文件夹里；脚本自己向上找 `tools/`，不依赖所在深度 |
| `<分类>/<模型名>/export_bedrock.py` | 手写 Bedrock 几何导出（`compileCube`/`compileGroup` 规则实测自 Blockbench 源码），在 `生物/muscle_creeper/` 里 |
| 工作区 `.mcp/`（本目录之外） | **无头 MCP**：第三方校验 / 渲染 / 导出 / 编辑 `.bbmodel`，不需要 Blockbench 运行；`call_tool.py` 的 `Client` 可 import，用来让生成脚本**通过 MCP 授权**整个工程（金龙的做法） |

> **踩过的坑都在 [ISSUE.md](ISSUE.md)**：box_uv / 顶层 groups 表 / single_texture 三条互操作坑、链式旋转组的
> 共面 z-fighting、贴图密度与分辨率解耦、画笔随机种子、轴对齐方块拼球、浮空造型的登记与空档…… 开工前扫一遍；
> 新踩到的坑也往里加，本文件只留约定与结构。

格式约定（所有模型通用，实测自 Blockbench 5.2.1 源码）：
**Generic Model (free)** 格式、逐面 UV（`v` 从上往下、从外侧看正立不镜像）、朝向 -Z（北）为正面。

工程格式版本：生成脚本写 `format_version 4.5`；**用 Blockbench 打开并保存过的工程会变成 5.0**
（组的 origin/rotation 移到顶层 `groups` 表，outliner 只剩 uuid 引用），解析脚本两边都要能读。实测 4.5→5.0 保存只改格式、不改几何（渲染逐像素一致），
但在 GUI 里的修改会被重跑生成脚本覆盖。

## 目录结构

**本仓库根目录就是模型工作目录**（2026-09-27 把原来那层 `property/` 拍平到了根；
同日又按分类分了文件夹）：模型按 `兵器/`、`人物/`、`物品/`、`生物/` 四类分开放，
一个模型一个文件夹，文件夹名 = 模型名。

```
<仓库根>
├─ README.md            本文件：格式约定 + 共享脚本说明
├─ ISSUE.md             踩坑记录（实测结论，跨模型复用）
├─ tools/               共享脚本：离线渲染器 preview_bbmodel.py、格式代数 bbmodel_kit.py、
│                       武器脚手架 bbmodel_build.py，以及临时输出 out/
├─ 人工建模参考/        第三方模型包（只做设计参考，.gitignore 挡住、不发布）
├─ 兵器/ 人物/ 物品/ 生物/
│  └─ <模型名>/
│     ├─ <模型名>.bbmodel  Blockbench 工程（贴图 base64 内嵌，双击即看）
│     ├─ <模型名>.png      同一张贴图单独导出（有自发光贴图的还有 *_glow.png）
│     ├─ *_preview*.png    离线渲染的预览图（`*_crosscheck_mcp.png` 是另一个渲染器的对照）
│     └─ build_<模型名>.py 该模型的一键生成脚本（重跑即可复现）
```

每个模型的生成脚本输出目录就是它自己的文件夹，重跑不会散落到别处。
脚本不假定自己在第几层：从自己所在目录**向上找**含 `tools/bbmodel_kit.py` 的那层当仓库根，
所以模型文件夹再挪位置也不用改脚本。
