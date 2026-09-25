# property — Minecraft 风格 Blockbench 模型集

| 模型 | 工程 | 一句话 |
|---|---|---|
| [霸王花盆栽](bawanghua_flower_pot/README.md) | `bawanghua_flower_pot/` | 原版花盆里种一棵 PvZ 风格霸王花 |
| [肌肉苦力怕](muscle_creeper/README.md) | `muscle_creeper/` | 原版风格的重肌苦力怕：宽肩、粗臂、经典鬼脸 |
| [精致小屋](cottage/README.md) | `cottage/` | 原版风格小屋：石基板墙、原木柱、阶梯屋顶、烟囱灯笼花箱 |
| [三层宝塔](pagoda/README.md) | `pagoda/` | 石台上的三层白墙黑瓦佛塔，金色塔刹 |
| [雷电将军](raiden_shogun/README.md) | `raiden_shogun/` | 原版人形骨架的雷电将军：麻花辫、和服、袴裙 |
| [瓶中帆船](ship_in_bottle/README.md) | `ship_in_bottle/` | 半透明玻璃瓶里一艘全套帆装的小帆船 |

共享工具：

| 文件 | 说明 |
|---|---|
| `tools/preview_bbmodel.py` | 离线渲染任意 `.bbmodel`（Blockbench 没有可用的无头 CLI），`--ground` 可调接触阴影半径 |
| `tools/build_*.py` | 各模型的一键生成脚本（贴图 + 几何 + 写出 `.bbmodel`） |

> **2026-09-24 修复**：`preview_bbmodel.py` 的逐面 UV 采样条件原本写反了，导致预览图里
> 每个面都被渲染成 180° 旋转（`v` 轴上下颠倒 + 左右镜像）。`bbmodel` 工程本身从来没受过影响
> （Blockbench 里的朝向一直是 README 约定的"从外侧看正立不镜像"），只有离线预览 PNG 受影响。
> 噪点贴图看不出来，方向性贴图（苦力怕的鬼脸）看得出来。所有模型的预览图已用修好的渲染器重出。

格式约定（所有模型通用，实测自 Blockbench 5.2.1 源码，详见[霸王花盆栽的文档](bawanghua_flower_pot/README.md)）：
**Generic Model (free)** 格式、逐面 UV（`v` 从上往下、从外侧看正立不镜像）、朝向 -Z（北）为正面。

## 目录结构

一个模型一个文件夹，文件夹名 = 模型名：

```
property/
├─ README.md            本文件：总索引
├─ skill/               skill 工作版（随建模一起积累更新，见下）
├─ tools/               共享脚本：各模型的一键生成 + 离线渲染器 + Bedrock 导出
└─ <模型名>/
   ├─ <模型名>.bbmodel  Blockbench 工程（贴图 base64 内嵌，双击即看）
   ├─ <模型名>.png      同一张贴图单独导出
   ├─ *_preview*.png    离线渲染的预览图
   └─ README.md         该模型的设计说明与重新生成方法
```

生成脚本（`tools/build_*.py`）的输出目录已指向各自模型文件夹，在 property 里重新生成不会散落到根目录。

## skill（工作版，随建模持续积累）

`skill/` 是这份分支随模型一起维护的 **skill 工作版**：格式实测表、踩坑记录、生成与渲染脚本都在里面。

- 每次建模——新做模型、发现新的格式事实、踩到新的坑、改进渲染器——都应当把经验**回写到这里**：
  规则进 `skill/SKILL.md`，细节表进 `skill/references/bbmodel-format.md`，
  坑的完整定位过程进 `skill/references/pitfalls.md`；
- 同时在对应模型的 `README.md` 里记一句"这次新增/改了什么"；
- 仓库根目录的那份 skill（与 main 分支一致）是**发布版**，只沉淀已验证成熟的结论：
  工作版里试出来的东西先在模型上验证，再决定何时往发布版同步。

维护细则写在 `skill/README.md` 的「版本关系与维护约定」里。
