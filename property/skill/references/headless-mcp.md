# 无头 MCP：第三方校验 / 渲染 / 导出 / 编辑

`blockbench-mcp-headless` 1.9.1 —— 独立进程直接读写 `.bbmodel`，**不需要 Blockbench 运行**。
它是我们"没亲眼看过的渲染等于没渲染"这条规则的第三方对照：校验与导出走 Blockbench 自己的
编解码器，渲染是另一套实现，所以两个渲染器的结论互相独立。

## 来源与安装

- 仓库：`jasonjgardner/blockbench-mcp-plugin`（2026-09 时 449★，GPL-3.0，更新活跃）。
  **不在 Blockbench 官方插件库**里——作者注明官方库不允许 AI 功能，所以只能旁路分发。
- 同一仓库两套用法，我们只用后者：
  - **桌面插件**：作者 GitHub Pages 分发的 `mcp.js`，装进 Blockbench 后在应用内起 HTTP MCP server
    （默认 `http://localhost:3000/bb-mcp`），能力是驱动 GUI；**本仓库未安装**。
  - **headless**（本文）：stdio server，直接对文件生效，可多进程并行。
- 安装（2026-09-25，装在工作区 `.mcp/`）：

  ```bash
  npm install https://github.com/jasonjgardner/blockbench-mcp-plugin/archive/refs/heads/main.tar.gz
  ```

  两个坑：`npm i github:用户/仓库` 会被解析成 **SSH** 地址 → 本机没有 GitHub SSH key，
  直接 `Permission denied (publickey)`，必须用 HTTPS tarball；
  **包名与仓库名不同**——仓库 `blockbench-mcp-plugin`，包是 `blockbench-mcp`，
  入口 `node_modules/blockbench-mcp/bin/blockbench-mcp-headless.mjs`。

## 接入 ZCode

`C:\Users\chenyuchong\MyApp\blockbench\.zcode\config.json`：

```json
{"mcp": {"servers": {"blockbench-headless": {
  "type": "stdio",
  "command": "C:\\Users\\chenyuchong\\MyApp\\Nodejs\\node.exe",
  "args": ["C:/Users/chenyuchong/MyApp/blockbench/.mcp/node_modules/blockbench-mcp/bin/blockbench-mcp-headless.mjs",
           "--root", "C:/Users/chenyuchong/MyApp/blockbench/property",
           "--root", "C:/Users/chenyuchong/MyApp/blockbench/skill",
           "--root", "C:/Users/chenyuchong/MyApp/blockbench/.mcp/out"],
  "timeoutMs": 60000}}}}
```

配置要点（来自 ZCode 的 MCP 诊断文档，踩错会静默消失）：

- schema **严格**：任何未知键都会让这个 server 被丢弃；`command` 必须是**字符串**
  （写成数组会报 `command.trim is not a function`），参数放 `args`；
- 配置文件里**不展开** `${...}`，一律写绝对路径（Windows 上用 `node.exe` 的绝对路径）；
- 同名 server **用户级覆盖工作区级**；
- **只在会话启动时加载**——改完要重开会话才会出现原生 `mcp__blockbench-headless__*` 工具。

不进 MCP 客户端也能用（本目录自带极简 stdio 客户端）：

```bash
cd C:/Users/chenyuchong/MyApp/blockbench/.mcp
python call_tool.py --list
python call_tool.py bbmodel_validate '{"file": "cottage/cottage.bbmodel"}'
```

## 工具（23 个）

| 类别 | 工具 |
|---|---|
| 读 | `bbmodel_info` / `bbmodel_outline` / `bbmodel_find_elements` / `bbmodel_get_node` / `bbmodel_list_textures` / `bbmodel_list_animations` / `bbmodel_sample_pose`（按时间求值动画，报骨骼位置与包围盒） |
| 写 | `bbmodel_create` / `bbmodel_edit` / `bbmodel_add_texture` |
| 校验 | `bbmodel_validate` / `bbmodel_validate_animations` |
| 导出 | `bbmodel_export_bedrock_geometry` / `bbmodel_export_java_block` / `bbmodel_import_java_block` / `bbmodel_export_modded_entity` / `bbmodel_convert_legacy` |
| 渲染 | `bbmodel_render` / `bbmodel_contact_sheet`（three.js WebGPU） |
| 其他 | `bbmodel_web_url`（网页版打开链接，URL 过长时落一个 launcher HTML）/ `blockbench_launch` |

`bbmodel_edit` 的 21 种操作：`add_group` `add_cube` `update_node` `remove_node` `add_texture`
`add_material` `update_material` `update_texture` `assign_texture` `add_animation` `remove_animation`
`set_keyframe` `remove_keyframe` `set_model_properties` `add_locator` `set_particle_keyframe`
`remove_particle_keyframe` `add_mesh` `add_mesh_primitive` `edit_mesh` `map_mesh_uv`。
一次调用是一个**原子批次**，且做 revision 校验（读时拿到的 `revision` 传回
`expected_revision`，别人改过就拒写）——多个 agent 并行改同一文件不会互相覆盖。

## 校验结果怎么读：warning 不是错

`summary.errors` 才是错。warning 只有两类：

- **有意为之**，需要在交付说明里说清楚的那种——跨组穿插（茎穿过花萼、花瓣从花头下伸出、
  人形四肢互相重叠）与 floating（刻意独立的件：坦克诱导轮、帆船支索、门前步石）；
- **真该修**——`mirror` 门报"左右件不镜像"，通常意味着尺寸或 x 位置抄错了
  （本仓库实测：`us_soldier` 7 处、`torii` 1 处、`m1a2_abrams` 1 处，后者可能是有意的）。

让有意为之的警告静下来：`free_elements`（声明这些件就是独立件）、`interpenetration_depth`
（允许的穿插量）、`mirror_x`（对称轴）。`self_test` 会证明每个门仍能检出它负责的缺陷。

### 两个门有"用不上"的情形，别被它们带偏

- **`mirror` 比的是世界坐标盒子**（`golden_loong` 实测）：姿态一旦不是平面姿态——
  比如躯干在 X 上走 S 形——左右件在世界空间里就**本来就不**关于 x=0 对称，
  这个门会把几十个零件全部报出来，而且 `self_test` 会自己标 `"discriminates": false`
  （注入一个偏移缺陷后违规数一模一样，说明它在这个模型上没有分辨力）。
  这时该守的不变量是**未姿态空间**里的镜像关系，自己在生成脚本里查：把每个 `_L` 与 `_R` 配对，
  比较 `from/to` 逐轴（x 取负并交换两端），旋转**比较矩阵而不是欧拉三元组**
  （`ry=180` 与 `ry=-180` 是同一个旋转，拿三元组比会误报——`golden_loong` 的两把鳍就是这么被抓出来的假阳性）。
- **`interpenetration` 用 `material_key` 豁免同料重叠**：蛇形身体那种"相邻体节故意重叠
  1~2 单位、免得弯曲时开缝"的作法，靠 `material_key: "color"` + 给同料方块同一个
  marker 色号静音；不同料（鬃扎进颅骨、须穿进吻部）仍然会被报出来，这才有用。
  实测 `add_cube` 不传 `color` 时服务端会随机挑一个——**必须显式传**，否则同料判定失效。

## 用 MCP 授出一个完整工程（`golden_loong` 的做法，2026-09-25）

以前所有模型都是脚本直接拼 `.bbmodel` JSON（4.5 格式）。金龙改成**让服务端来写**：

```python
sys.path.insert(0, "../.mcp")
from call_tool import Client                 # 极简 stdio 客户端，可直接 import
c = Client(timeout=900)
c.call("bbmodel_create", {"file": path, "format": "free", "overwrite": True,
                          "resolution": {"width": 1024, "height": 1024}})
c.call("bbmodel_add_texture", {"file": path, "image": "…_body.png"})
c.call("bbmodel_add_texture", {"file": path, "image": "…_glow.png",
                               "render_mode": "emissive"})     # 发光贴图 = 第二张纹理
c.call("bbmodel_edit", {"file": path, "operations": groups + cubes})   # 一次原子批次
c.call("bbmodel_edit", {"file": path, "operations": anim_ops})
```

实测要点：

- **`bbmodel_edit` 一次最多 500 个 op**（工具 schema 的 `maxItems`）。41 组 + 199 方块 = 240 op
  一次过；1×`add_animation` + 546×`set_keyframe` 要拆两批（脚本里 `send_ops` 按 400 分批）。
- **纹理索引 = 加入顺序**：面的 `texture` 字段是纯索引，所以**先加纹理再加方块**，
  免得中间态引用不存在的索引。
- **`set_keyframe` 的旋转值原样存储**（探针实测：传 `[30,0,0]`，文件里就是 `"x":"30"`），
  没有 4.10 导出那种 x/y 取负；组 `rotation` 与关键帧 `rotation` **同一套约定**，
  所以动画帧可以直接写成"基准姿态 + 波动"，不用换算。
- **落盘就是 5.0**：组属性写进顶层 `groups` 表、outliner 只剩 uuid 引用（见 bbmodel-format.md §11），
  数字能取整就写整数。`preview_bbmodel.py` 两边都能读，不用改。
- 服务端做 **revision 校验**：读到的 `revision` 可用 `expected_revision` 回传，别人改过就拒写；
  生成脚本反复跑没问题（每次 `bbmodel_create … overwrite: true` 重开）。
- 产物带 `ai_used` 标记；`.bbmodel` 体积 ≈ 两张 PNG 的 base64（金龙 1024²×2 ≈ 640 KB）。

## 与自建工具的对照结论（2026-09-25）

- **渲染**：宝塔同视角对比——**几何与朝向完全一致**，只有灯光/背景不同（它是深色背景 + 软光照）。
  结论：自建光栅器的几何与 UV 方向没问题；两个渲染器不一致时，先怀疑自建的那个。
- **Bedrock 导出**：肌肉苦力怕 11 个方块的 `origin/size/uv/rotation` 集合**完全一致**；
  唯一差别是它多导出一根以模型名命名的 **root 骨骼**（9 vs 我们的 8）——手写导出器应补上。
- **info 的格式提示**：对 4.5 工程会附
  "Converted from format 4.5 to 5.0 in memory; the file is written as 5.0 on the next save."，
  与 [bbmodel-format.md §11](bbmodel-format.md) 的格式版本事实一致。

## 限制（照实记）

- 写入的模型会被打 `ai_used` / `ai_agents` 标记（`--no-ai-disclosure` 可关）。
- 路径必须落在某个 `--root` 内（含符号链接解析），否则拒写；产物目录想独立就再加一个 `--root`。
- Blockbench **不重载**磁盘上变化的文件：无头改完要在 GUI 里重新打开，别两边同时改同一文件。
- 渲染首次会往 `%LOCALAPPDATA%\blockbench-mcp-headless` 装约 127MB 引擎（本机 Node v22.20 也能跑，
  它自带 Bun；机器上另有 Node v24 备用）。
- 粒子不能无头渲染；动画检查只采样数值关键帧（Bezier 按直线采样、Molang 跳过）；
  mesh 只在 `free` 格式可编辑。
