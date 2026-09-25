# BlockBenchingWithZcode

> **这是随模型一起维护的 skill 工作版**（property 分支里的 `property/skill/`）。
> 之后建模过程里的一切新经验——格式事实、坑与修复、更省事的做法——都回写到这里；
> 仓库根目录的那份是对应的发布版，只同步已经验证成熟的结论。细则见文末
> [「版本关系与维护约定」](#版本关系与维护约定)。

用 ZCode 从零编写 Minecraft 风格 Blockbench 模型的 skill 与实战记录。

- **[skill/SKILL.md](skill/SKILL.md)** —— skill 正文：四条核心规则、流水线、踩坑速查表、验证门
- `skill/references/bbmodel-format.md` —— 从 Blockbench 5.2.1 源码实测的格式表
  （顶点序 / uv 角配对 / 旋转序 / 默认相机 / 格式 id / asar 提取方法）
- `skill/references/pitfalls.md` —— 每个坑的完整 post-mortem（症状 → 定位 → 根因 → 修复）
- `skill/scripts/` —— 可复现的生成与离线预览脚本
- `skill/example/` —— 一次完整产出：霸王花盆栽（`.bbmodel` + 贴图 + 两张预览）

## 快速开始

```bash
cd skill
python scripts/build_bawanghua_pot.py      # 重新生成 example/ 里的模型和贴图
python scripts/preview_bbmodel.py example/bawanghua_flower_pot.bbmodel preview.png \
       --azimuth 225 --elevation 19.47 --distance 60 --target 0 12 0
```

用 Blockbench 打开 `skill/example/bawanghua_flower_pot.bbmodel` 即可查看/编辑模型。

## 这套 skill 解决的核心问题

1. **格式事实以 Blockbench 源码为准**：显式 UV 是"从外看正立不镜像"（不是 box-net 的南北翻 u），
   旋转是 `Rz·Ry·Rx` 绕 origin，`free` 格式才允许骨骼组 + 任意角度——搞错任何一条，贴图静默镜像或错位
2. **以像素为单位思考**：小于 1/16 格的特征是亚像素
3. **轮廓靠阶梯方块**：大长方体读作箱子，1 格收分读作生物
4. **没看过的渲染等于没渲染**：Blockbench 没有无头 CLI，用结构校验 + 品红占位门 + 自写光栅器三道门闭环

版本基于 Blockbench 5.2.1（Windows 安装版）。换版本时，skill 里的实证方法
（uvprobe 探针 + source map 提取）可以重新核对一遍。

> **待同步到发布版**（main）：发布版的 `scripts/preview_bbmodel.py` 还是**修复前**的版本——
> 逐面 UV 角的三元写反，会把每个面的贴图渲染成 180° 旋转；工作版这里已经是修好的版本。
> 下次同步时记得带上这个修复。


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
