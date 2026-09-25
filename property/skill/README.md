# BlockBenchingWithZcode

> **这是随模型一起维护的 skill 工作版**（property 分支里的 `property/skill/`）。
> 之后建模过程里的一切新经验——格式事实、坑与修复、更省事的做法——都回写到这里；
> 仓库根目录的那份是对应的发布版，只同步已经验证成熟的结论。细则见文末
> [「版本关系与维护约定」](#版本关系与维护约定)。

用 ZCode 从零编写 Minecraft 风格 Blockbench 模型的 skill 与实战记录。

- **[SKILL.md](SKILL.md)** —— skill 正文：四条核心规则、流水线、踩坑速查表、验证门
- [references/bbmodel-format.md](references/bbmodel-format.md) —— 从 Blockbench 5.2.1 源码实测的格式表
  （顶点序 / uv 角配对 / 旋转序 / 默认相机 / 格式 id / asar 提取方法 / 4.5 与 5.0 工程格式）
- [references/pitfalls.md](references/pitfalls.md) —— 每个坑的完整 post-mortem（症状 → 定位 → 根因 → 修复）
- [references/headless-mcp.md](references/headless-mcp.md) —— 无头 MCP：第三方校验 / 渲染 / 导出 / 编辑
  （安装坑、接入 ZCode、23 个工具、校验门怎么读、与自建工具的对照结论）
- [scripts/](scripts/) —— 可复现的生成与离线预览脚本
- [example/](example/) —— 一次完整产出：霸王花盆栽（`.bbmodel` + 贴图 + 两张预览）

## 快速开始

```bash
python scripts/build_bawanghua_pot.py      # 重新生成 example/ 里的模型和贴图
python scripts/preview_bbmodel.py example/bawanghua_flower_pot.bbmodel preview.png \
       --azimuth 225 --elevation 19.47 --distance 60 --target 0 12 0
```

用 Blockbench 打开 `example/bawanghua_flower_pot.bbmodel` 即可查看/编辑模型。

## 这套 skill 解决的核心问题

1. **格式事实以 Blockbench 源码为准**：显式 UV 是"从外看正立不镜像"（不是 box-net 的南北翻 u），
   旋转是 `Rz·Ry·Rx` 绕 origin，`free` 格式才允许骨骼组 + 任意角度——搞错任何一条，贴图静默镜像或错位
2. **以像素为单位思考**：小于 1/16 格的特征是亚像素
3. **轮廓靠阶梯方块**：大长方体读作箱子，1 格收分读作生物
4. **没看过的渲染等于没渲染**：自建三道门（结构校验 + 品红占位门 + 自写光栅器）打底，
   再用无头 MCP 的 `bbmodel_validate` / `bbmodel_render` 做第三方对照——独立实现，
   而且直接跑 Blockbench 自己的编解码器规则

版本基于 Blockbench 5.2.1（Windows 安装版）。换版本时，skill 里的实证方法
（uvprobe 探针 + source map 提取）可以重新核对一遍。

## 工作版积累记录（相对发布版 main 新增的部分）

| 日期 | 内容 |
|---|---|
| 2026-09-25 | 渲染器 UV 修复同步：逐面 UV 角三元写反，每个面的贴图被渲染成 180° 旋转（噪点贴图看不出、方向性贴图一眼看穿） |
| 2026-09-25 | 支持 5.0 工程格式：Blockbench 保存后组的 origin/rotation 搬到顶层 `groups` 表，outliner 只剩 uuid 引用 |
| 2026-09-25 | pitfalls #11（UV 三元写反的定论过程）、#12（5.0 格式导致组旋转"失效"）；验证门补"方向性贴图自检" |
| 2026-09-25 | 其它会话的积累：pitfalls #13（镜像函数把轴心整个取负）、#14（旋转件 from/to 与 origin 不在同一坐标系）、速查表第 10 条改为"WebSearch 摘要可用但取不到图" |
| 2026-09-25 | 无头 MCP 接入与对照结论（[references/headless-mcp.md](references/headless-mcp.md)）：第三方校验 / 渲染 / 导出三层对照，镜像门与 floating 门的读法，导出缺 root 骨骼的差异 |

> **已同步到发布版**（main，2026-09-25，commit `ea09422`）：上表这一批已整体覆盖过去，
> 发布版的 `scripts/preview_bbmodel.py` 也已是修复后的版本。之后的积累继续按下面 1–5 步走，
> 攒到值得发布时再覆盖一次。


## 版本关系与维护约定

| 位置 | 角色 |
|---|---|
| 仓库根目录（main 分支） | **发布版** skill：SKILL.md / references / scripts / example |
| `property/skill/`（property 分支） | **工作版**：和模型放在一起，随建模持续积累 |

维护流程：

1. 做新模型时按 SKILL.md 的流水线走，中途每个新发现（格式事实、几何/渲染 bug 及其修复、
   更省事的做法）先记进该模型的 `README.md`；
2. 收尾时把值得复用的部分**回写**到本目录——规则进 `SKILL.md`，
   细节表进 `references/bbmodel-format.md`，坑的完整定位过程进 `references/pitfalls.md`；
3. 本目录的 `scripts/` 可以按需改进，但改完要保证 `example/` 仍能一键重新生成；
4. 与发布版的同步时机由你决定：发布版只保留已在模型上验证过的结论。
5. 同步到 property 分支时**只复制该发布的内容**：各模型文件夹、`tools/`、`skill/`、`README.md`；
   排除 `参考/`（第三方素材）、`_ref/`（角色参考图）、`_cmp/`（对照调试产物）、`out/`（临时输出）。
   仓库根 `.gitignore` 已列出这些，但整目录 `cp -r` 仍会把它们带进 git 工作区，
   而切回 main 后它们就成了未跟踪文件——下一次 `git add -A` 会把第三方素材一起公开出去。
