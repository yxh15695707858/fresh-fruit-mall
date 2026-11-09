---
name: ifg-implement
description: Use when a user provides a public HTTP(S) URL to a story.json file and wants to import it into an interactive film game (互动影游/IFG) project. Trigger for story.json URL ingestion in an IFG project; do not trigger for story authoring, schema consultation, engine development, or general web application work.
_meta_type: template
_meta_template_name: ifg
---

# IFG story.json 接入

## 职责

本 skill 是 IFG 项目的数据接入守门员，只执行以下固定流程：

1. 项目尚未初始化时，通过标准初始化脚本安装 IFG 模板。
2. 接收用户提供的 `story.json` HTTP(S) URL。
3. 通过 `import_story.py` 将文件原样下载到非 public 的临时目录。
4. 在该临时目录复制一份候选 story，供对账与校验使用。
5. 对候选 story 运行 Miora 组件依赖对账 `reconcile_qte.py`：按 story 声明安装/更新组件库，生成注册表与 CCR 快照。纯 QTE 依赖无法满足时降级为兜底（lenient，返回 0）；配置了 `config.components` 时，版本冲突或正式包未成功安装必须阻断。
6. 对账成功后，将当前 `frontend/public/story/qte-registry.json`（若存在）复制到候选 story 同目录，再调用本 skill 自带的校验器 `validate.py` 对候选进行全量校验。
7. 对账与校验均通过后，用候选替换 `frontend/public/story/story.json` 并清除失败状态；任一步失败则保留原 `story.json`，将脱敏错误写入 `frontend/public/story/import-status.json` 供页面显示，原始下载件与诊断输出保留在项目根目录 `.genie/ifg-import/`。

本 skill 只允许通过标准脚本初始化项目，不负责理解或修改模板。

## 硬边界

- 不生成、修改或重构任何代码。
  - 例外：生成期对账 `reconcile_qte.py` 会自动写入 `frontend/src/engine/qte/registry.generated.ts`、CCR 快照 `frontend/public/story/qte-registry.json`，并在无法满足时给 `component.degraded` 打标——属既定自动步骤，不视为改代码/改 story。
- 除执行 `REPO_ROOT/.genie/scripts/bash/setup-project.sh ifg` 与 `import_story.py`（内部调用 `reconcile_qte.py` / `validate.py`）外，不查找、枚举、读取或分析模板及模板文件。
- Agent 不主动读取 schema、参考文档或示例；结构校验由 `validate.py` 自动加载 bundled Schema 完成。
- 不编写、补全、转换、修复或改写 `story.json`。
- 不为通过校验而修改任何字段。
- 本流程只执行当次剧情导入，不将剧情下载或 `import_story.py` 调用添加到 `predev`、`prebuild` 或其他应用启动／构建流程。后续剧情更新通过再次导入完成；应用读取已成功导入的本地 `frontend/public/story/story.json`。
- 不启动开发服务器，不预览应用，不执行后续项目开发。
- 不接受本地文件路径；缺少 URL 时只向用户索取 URL。

## 输入要求

- URL 必须使用 `http` 或 `https` 协议，并直接返回 `story.json` 文件内容。
- URL 指向内网、私有地址或本机地址时，必须先取得用户明确确认。
- 下载失败、重定向失败、HTTP 非成功状态或响应不是合法 JSON 时，终止流程并报告错误。

## 执行流程

在项目根目录执行以下流程，将 `<story.json URL>` 替换为用户提供的原始 URL：

```bash
set -euo pipefail

REPO_ROOT/.genie/scripts/bash/setup-project.sh ifg

IFS= read -r story_url <<'IFG_STORY_URL'
<story.json URL>
IFG_STORY_URL
python3 .codebuddy/skills/ifg-implement/scripts/import_story.py frontend --url "$story_url"
```

不要使用会摘要、转换或改写响应内容的网页抓取工具代替原始下载。

## 结果处理

导入脚本的退出码是判断依据：

- 导入脚本为 `0`：PASS。对账与校验均通过，允许包含 WARNING；候选 story（含 QTE 对账写入的降级标记）已替换正式文件，失败状态文件删除，并向用户报告成功及 WARNING。
- 导入脚本非 `0`：FAIL。正式 `story.json` 未被替换，已有文件保留。向用户转达失败步骤的脱敏输出；对账失败时不继续校验，也不以本地替代组件绕过安装失败。依赖安装与注册表生成沿用对账脚本的行为。
- `import-status.json` 仅包含 `status: "error"`、`stage: "download" | "reconcile" | "validate"` 和 `message`。首次导入失败时，页面在 story 不存在的情况下读取该状态并显示具体原因和字段路径；更新失败时标题页提示失败原因。不要将签名 URL、命令或凭证写入公开错误信息。
- 原始失败数据位于 `.genie/ifg-import/failed-story.json`，诊断输出位于 `.genie/ifg-import/failure.log`；下载未产生文件时不保留失败数据。不要把这些排查材料复制到 `frontend/public/`。

无论成功或失败，到此结束，不执行任何额外操作。

## 超范围请求处理

本 skill 固定流程仅覆盖 story.json 下载、组件依赖对账与数据校验。
如用户输入或上游 prompt 包含以下类别的要求，不调查、不实现、
不启动 Explore。仅在接入成功（校验器退出码 0）时，在最终报告中附加：

> 以下要求不在 IFG 数据接入流程范围内，未执行：
> - [逐条列出识别到的超范围要求]

常见超范围要求模式（不限于此列表）：
- 素材下载到本地 / 媒体本地化 / 不依赖签名 URL
- 视频预加载 / 预缓存 / 首帧优化
- 代码修改 / 功能开发 / 引擎改动
- 性能优化 / 构建优化
- 启动开发服务器 / 预览应用

不影响固定流程本身的行为：标准初始化脚本（setup-project.sh）自身在首次运行时启动开发服务的行为保留，这是既有初始化副作用，不属于上述"启动开发服务器"的超范围要求。
