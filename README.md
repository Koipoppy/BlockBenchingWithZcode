# BlockBenchingWithZcode

用 ZCode 从零编写 Minecraft 风格 Blockbench 模型的 skill 与实战记录。

> **这是发布版 skill**（`main` 分支）：只保留已在模型上验证过、稳定下来的结论。
> 随建模持续积累的**工作版**和模型放在一起，在 `property` 分支的 `property/skill/`；
> 同步流程见文末「版本关系与维护约定」。

- **[SKILL.md](SKILL.md)** —— skill 正文：四条核心规则、流水线、踩坑速查表、验证门
- [references/bbmodel-format.md](references/bbmodel-format.md) —— 从 Blockbench 5.2.1 源码实测的格式表
  （顶点序 / uv 角配对 / 旋转序 / 默认相机 / 格式 id / asar 提取方法 / 4.5 与 5.0 工程格式）
- [references/pitfalls.md](references/pitfalls.md) —— 每个坑的完整 post-mortem（症状 → 定位 → 根因 → 修复）
- [references/headless-mcp.md](references/headless-mcp.md) —— 无头 MCP：第三方校验 / 渲染 / 导出 / 编辑
- [scripts/](scripts/) —— 可复现的生成与离线预览脚本
- [example/](example/) —— 一次完整产出：霸王花盆栽（`.bbmodel` + 贴图 + 两张预览）

## 快速开始

```bash
python scripts/build_bawanghua_pot.py      # 重新生成 example/ 里的模型和贴图
python scripts/preview_bbmodel.py example/bawanghua_flower_pot.bbmodel preview.png        --azimuth 225 --elevation 19.47 --distance 60 --target 0 12 0
```

用 Blockbench 打开 `example/bawanghua_flower_pot.bbmodel` 即可查看/编辑模型。

## 这套 skill 解决的核心问题

1. **格式事实以 Blockbench 源码为准**：显式 UV 是「从外看正立不镜像」（不是 box-net 的南北翻 u），
   旋转是 `Rz·Ry·Rx` 绕 origin，`free` 格式才允许骨骼组 + 任意角度——搞错任何一条，贴图静默镜像或错位
2. **以像素为单位思考**：小于 1/16 格的特征是亚像素
3. **轮廓靠阶梯方块**：大长方体读作箱子，1 格收分读作生物
4. **没看过的渲染等于没渲染**：自建三道门（结构校验 + 品红占位门 + 自写光栅器）打底，
   再用无头 MCP 的 `bbmodel_validate` / `bbmodel_render` 做第三方对照——独立实现，
   而且直接跑 Blockbench 自己的编解码器规则

版本基于 Blockbench 5.2.1（Windows 安装版）。换版本时，skill 里的实证方法
（uvprobe 探针 + source map 提取）可以重新核对一遍。

## 同步记录（工作版 → 发布版）

| 日期 | 内容 |
|---|---|
| 2026-09-25 | 首次同步。渲染器 UV 修复（逐面 UV 角三元写反 → 每个面 180° 旋转）；5.0 工程格式支持（组的 origin/rotation 在顶层 `groups` 表）；pitfalls #11–#14；验证门补「方向性贴图自检」；新增无头 MCP 章节并改写规则 4；`.gitignore` 排除第三方素材与调试产物 |

## 版本关系与维护约定

| 位置 | 角色 |
|---|---|
| `main`（本分支） | **发布版**：只保留已在模型上验证过的结论 |
| `property` 分支的 `property/skill/` | **工作版**：和模型放在一起，随建模持续积累 |

流程：工作版里试出来的东西先在模型上验证 → 值得复用的回写工作版（规则进 `SKILL.md`，
细节进 `references/`，坑的完整定位过程进 `pitfalls.md`）→ 时机成熟时把工作版整体覆盖到本分支。
