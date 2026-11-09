# story.json 逐字段 API 参考

本文档是 `story.json` 的**唯一字段权威**。数据生产方按此契约产出数据。

`story.schema.json` 负责字段、类型、枚举和节点内约束；`scripts/validate.py` 直接执行该 Schema，并补充节点引用、入口存在性、可达性等 JSON Schema 无法表达的图语义校验。数据必须同时满足两类约束。

## 顶层结构

```jsonc
{
  "meta":       { ... },   // 必填：作品元信息
  "config":     { ... },   // 可选：全局外观/功能配置
  "variables":  { ... },   // 可选：状态变量初值
  "items":      [ ... ],   // 可选：道具库
  "characters": [ ... ],   // 可选：角色库
  "nodes":      { ... }    // 必填：剧情节点字典
}
```

---

## 1. meta（必填）

作品元信息。

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `title` | string | 是 | 作品标题，兼作存档命名空间 key |
| `version` | string | 是 | 数据版本号，建议语义化版本（如 `"1.0.0"`） |
| `start` | string | 是 | 实际入口节点 id，必须存在于 `nodes` 中；可直接指向 scene 或 QTE 节点，无需独立的 `type: start` 节点 |

```jsonc
{
  "meta": {
    "title": "阴门关",
    "version": "1.0.0",
    "start": "start_01"
  }
}
```

---

## 2. config（可选）

故事级全局配置。

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `title` | string | 否 | 标题页主标题 |
| `subtitle` | string | 否 | 标题页副标题 |
| `locale` | string | 否 | 引擎 UI 语言：未指定时使用中文，`zh` 及其地区变体使用中文，其他语言使用英文。仅影响引擎界面文案，不改剧情内容 |
| `poster` | string(URL) | 否 | 标题页封面图 URL |
| `theme` | object | 否 | 主题色/风格配置 |
| `typography` | object | 否 | 排版配置（`textSpeed`：`slow`/`normal`/`fast`/`instant`） |
| `audio` | object | 否 | 全局音频配置 |
| `features` | object | 否 | 功能开关 |
| `skin` | object | 否 | UI 皮肤配置 |
| `motion` | object | 否 | 动效配置 |
| `components` | object | 否 | 按使用位置引用 Miora 组件，传入版本、组件名和展示参数 |

### components

外层 key 表示使用位置，引用内的 `key` 表示 Miora 导出的组件名。每个使用位置都可省略；省略时保留引擎默认组件和参数。

| 使用位置 | `key` | 用途 | 可配置的专属 props |
|------|------|------|------|
| `titleMenu` | `GameMenu` | 标题页菜单容器 | `place`: `left` / `right` / `bottom` |
| `titleMenuButton` | `GameMenuButton` | 标题页菜单按钮 | `variant`: `default` / `cover` / `secondary` |
| `choiceGroup` | `GameChoiceGroup` | 剧情选项容器、通关结局操作组 | 无 |
| `choiceButton` | `GameMenuButton` | bar、overlay、hotspots 剧情选项按钮 | `variant`: `default` / `cover` / `secondary` |
| `loadingProgress` | `GameProgressBar` | 加载进度条 | `variant`: `default` / `loading` |
| `storyTree` | `GameLevelGroup` | 剧情树 | `rows`: 正整数 |
| `storyTreeProgress` | `GameProgressInfo`（默认）或 `GameProgressBar` | 剧情树探索进度 | `GameProgressBar` 支持 `variant`: `default` / `loading` |
| `actionButton` | `GameMenuButton` | 加载重试、视频重试、跳过和通关结局操作（去剧情树 / 结束游戏） | `variant`: `default` / `cover` / `secondary` |
| `endingCard` | `GameEndingCard` | 结局图鉴卡片 | 无 |
| `screen` | `GameScreen` | 剧情树、图鉴页面外框及返回入口 | `blur`: boolean；`blurRadius`: number（px） |
| `text` | `GameText` | 字幕 / 说话人、标题页、通关结局标题 / 说明、图鉴标题 / 统计 / 空态 | `size`: `xs` / `sm` / `md` / `lg` / `xl` 或 number（px）；`tone`: `title` / `body` / `fail` / `weak` |

引用存在时，`key` 和 `version` 必填，`props` 可选。`version` 是精确 SemVer 字符串，支持预发布号，如 `0.0.1-beta.1`。所有组件都支持 `props.className` 字符串、`props.style` 对象和 `props.theme`（`ancient` / `default`）；`style` 使用 React 样式属性名或 CSS 自定义变量，值只能为字符串或数字。除表中展示参数外，不接受其他 props。

按钮文案、进度值、剧情树节点、结局卡片标题和描述、解锁状态由引擎提供；`label`、`title`、`description`、`value`、`children`、`levels`、`links`、`status`、`disabled`、事件回调及 `ref` 不属于可配置参数。`className` 引用已有样式，不会生成 CSS。样式参数只作用于对应组件，不改变剧情跳转或 QTE 判定。

overlay / hotspots 的区域定位由引擎保留；hotspots 保持透明点击区，文字是否显示由 `hint` 控制。`screen` 的返回文案和行为由引擎提供。Miora 主题按组件 `props.theme` > 最近的组合组件主题 > `config.theme.game` > `ancient` 生效；`config.theme.preset` 不映射到 Miora 主题。

同一故事中 `config.components` 的版本必须一致。若有顶层 `qte.version`，它必须与展示组件版本相同；否则展示组件版本须满足每个 QTE `component.version` 的兼容下限。实际安装沿用 QTE 的 caret 兼容规则，允许使用同兼容段的更高版本。整包对账和安装在生成期执行，播放期不下载或切换包。本协议引用 `miora-spell`，包名不通过 `config.components` 指定。

下面示例仅为标题菜单缩小留白、降低面板背景不透明度；不写这些配置时，保留组件默认外观：

```json
{
  "config": {
    "components": {
      "titleMenu": {
        "key": "GameMenu",
        "version": "0.0.1-beta.1",
        "props": {
          "place": "right",
          "style": {
            "padding": "24px 20px",
            "gap": "12px",
            "--ms-game-menu-panel-bg": "rgba(0, 0, 0, 0.2)"
          }
        }
      },
      "titleMenuButton": {
        "key": "GameMenuButton",
        "version": "0.0.1-beta.1",
        "props": { "variant": "cover" }
      }
    }
  }
}
```

### theme

```jsonc
{
  "theme": {
    "mode": "dark",           // "light" | "dark"
    "accent": "#8b1a1a",      // 强调色 hex
    "game": "ancient",        // Miora 主题："ancient" | "default"，组件 props.theme 可覆盖
    "preset": "horror"        // 成套游戏风格主题，见下表；不填落 minimal 兜底
  }
}
```

`preset` 一行整体换皮：选项按钮 / 道具栏 / 字幕 / HUD / 结局卡的配色与字体默认一起切换。单点覆盖（`skin.choiceStyle` / `skin.accent` / `skin.font` / `choice.skin`）优先级仍高于主题默认。

#### 主题选择指引

| preset | 调性 | 适用题材 |
|--------|------|---------|
| `minimal` | 中性玻璃拟态，无强色（默认兜底） | 现实/生活/通用，或拿不准时 |
| `horror` | 暗金绶带 + 血红点缀，衬线字 | 恐怖、悬疑、灵异、克苏鲁 |
| `scifi` | 霓虹青描边，冷色发光，直角 | 科幻、赛博朋克、末世、太空 |
| `fantasy` | 描金卷轴框，暖色，宝石感道具，衬线字 | 奇幻、RPG、武侠、修仙 |
| `romance` | 干净留白，粉柔色，圆润气泡 | 都市言情、校园、乙女、恋爱 |

### audio

```jsonc
{
  "audio": {
    "bgm": "https://cos.example.com/bgm/main.mp3",  // 全局 BGM URL
    "bgmVolume": 0.7,           // BGM 音量 0~1，默认 0.7
    "sfxVolume": 1.0            // 音效音量 0~1，默认 1.0
  }
}
```

### features

```jsonc
{
  "features": {
    "backlog": true,      // 是否启用历史记录，默认 true
    "gallery": false,     // 是否启用画廊，默认 false
    "inventory": false,   // 是否启用道具背包，默认 false
    "autosave": true,     // 是否启用自动存档，默认 true
    "saveSlots": 10       // 存档栏位数，默认 10
  }
}
```

### skin

```jsonc
{
  "skin": {
    "choiceStyle": "ribbon",  // "plain" | "ribbon" | "plaque"
    "frame": "https://cos.example.com/frame/deco.png", // 全局共享装饰底图 URL（可选）
    "font": "sans",           // "sans" | "serif"
    "accent": "#8b1a1a"       // 强调色，覆盖 theme.accent
  }
}
```

### motion

```jsonc
{
  "motion": {
    "transition": "fade",           // 节点转场，见节点 transition 枚举
    "choiceReveal": "stagger-fade", // 选项入场，"stagger-fade"|"slide-up"|"scale-in"|"typewriter"|"glow-pulse"
    "textStyle": "banner",          // 文本呈现，"banner"|"bubble"|"centered"
    "intensity": "normal",          // 动效强度，"subtle"|"normal"|"cinematic"
    "reducedMotion": "auto"         // 无障碍减弱动效，"auto"|"on"|"off"
  }
}
```

---

## 3. variables（可选）

状态变量初值。key 为变量名，value 为初值（仅支持 `boolean` / `number` / `string`）。

```jsonc
{
  "variables": {
    "has_key": false,
    "trust_level": 0,
    "chosen_path": ""
  }
}
```

---

## 4. items（可选）

道具库。每个道具一个对象。

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | string | 是 | 道具唯一标识 |
| `name` | string | 是 | 道具显示名称 |
| `image` | string(URL) | 否 | 道具图 URL（道具栏展示用） |

```jsonc
{
  "items": [
    { "id": "old_key", "name": "生锈的钥匙", "image": "https://cos.example.com/items/key.png" }
  ]
}
```

---

## 5. characters（可选）

角色库。

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | string | 是 | 角色唯一标识 |
| `name` | string | 是 | 角色显示名称 |
| `image` | string(URL) | 否 | 角色参考图 URL |

```jsonc
{
  "characters": [
    { "id": "hero", "name": "小明", "image": "https://cos.example.com/avatars/hero.png" }
  ]
}
```

---

## 6. nodes（必填）

剧情节点字典。key 为节点 id，value 为节点对象。

### 节点通用字段

| 字段 | 类型 | 必填 | 适用节点 | 说明 |
|------|------|------|----------|------|
| `type` | enum | 是 | 全部 | 节点类型：`start` / `scene` / `choice` / `ending` / `interaction`；QTE 节点亦可直接用玩法名 `click` / `combo` / `hold` / `direction`（等价于 `interaction`，见「QTE 组件引用」） |
| `text` | string | 是 | 全部 | 本幕文案（剧本真源），多段用 `\n` 分隔 |
| `title` | string | 否 | 全部 | 剧情树和结局展示标题；缺省使用正文首行 |
| `cover` | string(URL) | 否 | 全部 | 剧情树和结局卡封面图片；缺省时剧情树使用 `media.items[0].poster`（仅 sequence） |
| `media` | object | 否 | 全部 | 多媒体配置 |
| `bgm` | string(URL) | 否 | 全部 | 节点级背景音 URL：从本节点起沿玩家实际走过的路径延续，进入下一个配了 `bgm` 的节点时交叉淡化换曲（同一首不重头）；路径上都没配时才用全局 BGM |
| `bgmLoop` | boolean | 否 | 全部 | 本节点 `bgm` 是否循环播放，缺省 `true`；`false` 时播完一遍即静音，直到进入下一个配了 `bgm` 的节点。仅在同节点配了 `bgm` 时有意义 |
| `effects` | object[] | 否 | 全部 | 进入节点时应用的状态变更（见 effects 对象） |
| `next` | string | 条件 | start/scene/interaction | 线性后继节点 id |
| `choices` | object[] | 条件 | scene/choice | 分支选项（>=2） |
| `clipDuration` | number | 否 | scene/choice/interaction | 原始 JSON 中的片段时长（毫秒），播放器加载后转换为秒 |
| `choiceAt` | number | 否 | scene/choice | 原始 JSON 中的选项浮现时机（毫秒），播放器加载后转换为秒 |
| `choiceDuration` | number | 否 | scene/choice/interaction | 原始 JSON 中的选项显示持续时间（毫秒） |
| `fail` | string | 否 | 无 component 的 interaction/QTE | 内置交互窗口截止时的跳转节点，目标必须存在；组件 QTE 不使用此出口 |
| `transition` | enum | 否 | 全部 | 进入转场：`fade`/`fade-black`/`fade-white`/`slide-up`/`slide-down`/`slide-left`/`slide-right`/`zoom`/`blur`/`dissolve`/`glitch`/`ripple`/`none` |
| `textStyle` | enum | 否 | 全部 | 文本呈现：`banner`/`bubble`/`centered` |
| `typewriter` | boolean | 否 | 全部 | 是否逐字打字机（默认 false，字幕整句直显） |
| `speaker` | string | 否 | 全部 | 当前说话人（引用 `characters[].id`） |
| `fx` | string[] | 否 | 全部 | 节点触发的瞬时视听/振动反馈列表；仅影响表现，不修改剧情状态。详见下文 |
| `ending_type` | enum | 条件 | ending | 结局类型：`good`/`bad`/`hidden`/`normal` |
| `interaction` | enum | 条件 | interaction | 交互类型：见下文 |

### fx（节点瞬时反馈）

`fx` 用于加强当前剧情节点的表现力，不参与变量、道具或分支计算。普通节点在进入时触发；`interaction` 节点在用户完成交互时触发。多个反馈可组合，视觉反馈约 700ms 后自动结束。

| 值 | 实际效果 |
|------|------|
| `shake-light` | 画面轻微横向震动 |
| `shake-heavy` | 画面较强的横纵震动 |
| `flash` | 屏幕快速白闪 |
| `vignette` | 屏幕边缘短暂变暗 |
| `zoom-punch` | 画面快速放大后恢复 |
| `slowmo` | 画面短暂增强饱和度；当前不会改变视频播放速度 |
| `sparkle` | 屏幕出现短暂金色闪光粒子 |
| `haptic-light` | 设备轻振约 20ms；浏览器不支持振动时忽略 |
| `haptic-medium` | 设备中等振动约 60ms；浏览器不支持振动时忽略 |
| `sfx:<音频URL>` | 立即播放一次 HTTP(S) 音频，例如 `sfx:https://cdn.example.com/hit.mp3` |

```jsonc
{
  "fx": ["shake-heavy", "flash", "sfx:https://cdn.example.com/hit.mp3"]
}
```

`fx` 与 `effects` 不同：`fx` 只产生瞬时表现反馈；`effects` 会修改变量或道具等剧情状态。

### media 对象

媒体类型为 `"video"`（单视频）或 `"sequence"`（多段序列），二者互斥。

**type = "video"**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | `"video"` | 是 | 固定值 |
| `src` | string(URL) | 是 | 视频 URL |
| `subtitle` | string(URL) | 否 | 字幕文件 URL（`.vtt`/`.srt`/`.ass`） |

**type = "sequence"**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | `"sequence"` | 是 | 固定值 |
| `items` | array | 是 | 按播放顺序排列的片段列表，至少 1 项 |

每个 `items` 元素：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `src` | string(URL) | 是 | 该片段的视频 URL |
| `shotId` | string | 否 | 片段标识 |
| `subtitle` | string(URL) | 否 | 字幕文件 URL |
| `poster` | string(URL) | 否 | 镜头首帧图片；节点未指定 `cover` 时，剧情树使用第一项的 `poster`。资源本地化时随视频一起下载并改写为本地路径 |

所有素材使用 http(s) URL 直接引用，不使用占位 ID、不使用本地文件路径、不使用 id-to-url 映射。

### choices 对象

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `label` | string | 是 | 选项显示文字 |
| `next` | string | 是 | 选中后跳转的节点 id |
| `condition` | object | 否 | 选项可见条件（结构化对象，见 condition 对象） |
| `effects` | object[] | 否 | 选择后立即应用的状态变更（见 effects 对象） |
| `skin` | enum | 否 | overlay 选项皮肤：`plain`/`ribbon`/`plaque` |
| `art` | string(URL) | 否 | overlay 选项专属装饰底图 URL |
| `hint` | boolean | 否 | hotspots 布局是否显示可见提示 |
| `anchor` | object | 否 | overlay 布局锚点 `{x,y}`（相对媒体框 0~1） |
| `region` | object | 否 | hotspots 布局热区 `{x,y,w,h}`（相对媒体框 0~1） |

### effects 对象

状态变更采用 **`op` 结构**：`set`/`inc`/`dec` 作用于变量，`add`/`remove` 作用于道具。

| op | 附带字段 | 说明 |
|------|------|------|
| `set` | `var`, `value` | 将变量设为指定值 |
| `inc` | `var`, `value?` | 变量自增（`value` 缺省为 1） |
| `dec` | `var`, `value?` | 变量自减（`value` 缺省为 1） |
| `add` | `item` | 添加道具到背包 |
| `remove` | `item` | 从背包移除道具 |

```jsonc
{
  "effects": [
    { "op": "set", "var": "has_key", "value": true },
    { "op": "inc", "var": "trust", "value": 1 },
    { "op": "add", "item": "old_key" }
  ]
}
```

### condition 对象

选项可见条件为**结构化对象**（引擎安全求值，不接受字符串表达式）。叶子为比较 / 拥有道具 / 到访节点，可用 `and`/`or`/`not` 递归组合。

| 形态 | 结构 | 说明 |
|------|------|------|
| 比较 | `{ "op": ">=", "var": "trust", "value": 1 }` | `op` ∈ `>=` `>` `<=` `<` `==` `!=` |
| 拥有道具 | `{ "op": "has", "item": "old_key" }` | 背包含指定道具 |
| 到访节点 | `{ "op": "visited", "node": "scene_03" }` | 曾进入指定节点 |
| 与 | `{ "and": [ <cond>, <cond> ] }` | 全部成立 |
| 或 | `{ "or": [ <cond>, <cond> ] }` | 任一成立 |
| 非 | `{ "not": <cond> }` | 取反 |

```jsonc
{
  "condition": {
    "and": [
      { "op": "has", "item": "old_key" },
      { "op": ">=", "var": "trust", "value": 1 }
    ]
  }
}
```

### interaction 枚举值

| 值 | 说明 |
|------|------|
| `tap` | 点击/轻触 |
| `longpress` | 长按 |
| `hold-release` | 蓄力后释放 |
| `swipe` | 滑动 |
| `drag` | 拖拽 |
| `rotate` | 旋转 |
| `rapidtap` | 快速连点 |
| `rhythm` | 节奏点击 |
| `trace` | 描线 |
| `hotspots` | 多点热区 |

### interaction 配置字段（QTE）

| 字段 | 类型 | 适用交互 | 说明 |
|------|------|----------|------|
| `prompt` | string | 全部 | 操作提示文案 |
| `timeout` | number(ms) | 全部 | 判定限时；超时按 `onFail` 处理。**须在 [1000, 10000] 区间** |
| `onSuccess` | string | 全部 | 判定成功跳转的节点 id |
| `onFail` | string | 全部 | 判定失败/超时跳转的节点 id |
| `duration` | number(ms) | longpress/hold-release | 蓄力时长 |
| `window` | number(ms) | hold-release/rhythm | 命中窗口；**须 < `duration`** |
| `direction` | enum | swipe/drag | `up`/`down`/`left`/`right`/`any` |
| `target` | Point | drag | 目标点（相对媒体框 **0~1**） |
| `angle` | number(度) | rotate | 目标角度 |
| `tolerance` | number | rotate/drag/trace | 角度容差 / 命中半径 |
| `count` | number | rapidtap | 需要连点次数 |
| `decay` | number | rapidtap | 每帧衰减 |
| `beats` | number[] | rhythm | 节拍时间点(ms) |
| `points` | Point[] | trace | 途经点（相对媒体框 **0~1**） |

### 成/败分支（QTE）

- interaction 节点的出口二选一：**要么给 `next`（无成败之分，判定成功即推进），要么给成对的 `onSuccess` + `onFail`**（成/败走不同剧情）。
- `onSuccess` 与 `onFail` 必须成对出现，且**不得指向同一节点**（否则成败无区别，QTE 失去意义）。
- 成功奖励的状态变更（`effects`）应写在 **`onSuccess` 目标节点**上（节点 `effects` 在进入时应用），而非 interaction 节点本身。
- 判定成功/失败的跳转复用剧情图的 goto 语义，`onSuccess`/`onFail` 目标节点必须存在且被纳入可达性检查。

### QTE 组件引用（远端统一组件库 `miora-spell`）

QTE 节点（`type` 为 `interaction` 或玩法名 `click`/`combo`/`hold`/`direction`）的交互载体二选一：**内置 `interaction` 枚举，或 `component` 组件引用**。组件引用远端统一库 `miora-spell`（整库按版本安装/更新，节点按组件名引用）。

**组件标识（`key` / `name` 二选一，至少其一）：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `component.key` | string | 库控件类名：`GameClickControl` / `GameComboControl` / `GameHoldControl` / `GameSlideControl`（**上游终态推荐写法**） |
| `component.name` | string | 逻辑短名：`click` / `combo` / `hold` / `slide`（等价旧写法，与 `key` 二选一） |
| `component.version` | string | 组件/整库版本；`story.qte.version` 缺省时以此为准，由生成期对账据此安装/更新。**支持预发布号排序**（`0.1.0-beta.0` < `0.1.0-beta.1`） |
| `component.props` | object | 玩法参数，直接透传库控件（如 `comboTarget`/`decayPerSecond`/`angle`/`knobLabel`/`total`/`label`/`title` 等）；深校验由 CCR `propsSchema` 承担 |
| `component.degraded` | boolean | 作者不填；仅生成期对账在无法满足时写入 → 运行时直接 `FallbackQte` |
| `rect` | Region(0~1) | 组件在媒体内容框内的子矩形，缺省铺满；须 `x+w<=1`、`y+h<=1` |
| `appearAt` | number(秒) | 组件浮现时机，缺省沿用 `choiceAt`/片段末尾 |
| `disappearAt` | number(秒) | 组件消失时机，窗口内未完成按 `onFail`；须 `appearAt < disappearAt`、`disappearAt * 1000 <= clipDuration` |
| `scale` | number(建议 50~200) | 组件视觉缩放百分比，缺省 100（不缩放）；以 `rect` 框中心为原点，点击热区同步缩放、可溢出 `rect` 框不裁剪。**仅对带 `component` 的节点生效**。**非法值（非数/越界）不报错，运行时回落 100，校验器仅给 `QTE_SCALE_IGNORED` 告警** |
| `limited` | boolean | `false`=关闭判定限时：不展示倒计时、也不超时判负（忽略 `timeout` 与 `appearAt/disappearAt` 窗口；`appearAt` 仍控制浮现时机；**`videoSpeed` 随之整段生效**，见该字段）；缺省/`true` 沿用现有限时。**仅对带 `component` 的节点生效**；关倒计时须同时不写 `component.props.total` |
| `videoSpeed` | `0.5` \| `1` \| `1.5` \| `2` | **QTE 区间内**的视频播放速率，缺省 `1`（正常速度）。生效范围是 `appearAt`~`disappearAt` 这段**媒体时间**，区间外（含区间之前、`disappearAt` 之后）一律原速——不是整个节点变速。`appearAt`/`disappearAt`/`clipDuration` 按**原始媒体时间**填写，不要预先折算；`timeout` 是玩家反应时间（墙钟），不随速率变化。**仅对带 `component`、且有自己 `media` 的节点生效**；非档位值运行时回落 `1`，校验器仅给 `QTE_SPEED_IGNORED` 告警（不报错），无自有 `media` 时给 `QTE_SPEED_NO_MEDIA` 告警，**没有可用区间时（缺 `appearAt`/`disappearAt` 其一，或 `limited:false`）退化成整段变速——整个节点按该速率播放，并给 `QTE_SPEED_WHOLE_NODE` 告警** |
| `resultTransitionMode` | `"immediate"` \| `"afterVideoEnd"` | QTE 得出成功/失败结果后的跳转时机，**缺省 `immediate`（立即跳转）**。`afterVideoEnd`=记录结果，待当前视频（序列则是最后一段）播放结束后再跳转；要延迟必须**显式写出**。**仅对带 `component` 的节点生效**；节点无自有 `media` 或**实际循环播放**（节点 `loop:true`，或节点未写 `loop` 而 `config.features.loopByDefault` 为 `true`）时等不到视频结束信号，运行时回落 `immediate` 并给 `QTE_TRANSITION_DEFER_IGNORED` 告警 |

**整库版本（可选，二选一定版方式）：** 顶层 `story.qte = { "lib": "miora-spell", "version": "0.0.1-beta.1" }` 声明整库版本（推荐，整库统一）——版本须为 registry 上真实发布的版本；缺省时省略顶层 `qte`、由各 `component.version` 定版（上游终态写法），或直接不 pin 以继承模板 `package.json` 的声明版本。

若同时配置 `config.components`，展示组件的统一版本也参与整包对账；与顶层 `qte.version` 必须相同，没有顶层声明时须满足 QTE 节点的版本兼容下限，详见 `config.components`。

- 节点 `type` = `click`/`combo`/`hold`/`direction` 时，即便不写 `component.key/name` 也可由 `type` 推断组件（`direction` → 滑动）。
- 组件名/`key` 归一化：`GameClickControl`↔`click`、`GameComboControl`↔`combo`、`GameHoldControl`↔`hold`、`GameSlideControl`↔`slide`/`direction`。
- props 的合法性由 CCR 快照 `qte-registry.json` 里该组件的 `propsSchema` 决定（校验器通用执行，新增玩法零改校验器）。
- 组件缺失/版本不满足/`degraded` → 运行时落固定兜底 `FallbackQte`（点击继续→`onSuccess`），**绝不判 `onFail`**。
- 详见 `docs/qte-remote-component-tech-spec.md`。

---

## 节点类型约束

完整剧情的每个入口可达节点都必须存在一条通往 `ending` 的路线。允许有出口的回环；没有结局出口的闭环、作为隐式结局的普通场景会被拒绝。此检查只判断连线，不证明选项条件在运行时一定可满足。

语义校验按节点 ID 字典序输出问题。QTE 的成功和失败路线分别使用非空 `onSuccess/onFail`，缺省或空字符串时回退 `next`，被成败分支覆盖的 `next` 不作为图出口。无组件 QTE 的 `fail` 也参与图检查；组件 QTE 的 `fail` 不作为实际出口。

组件 QTE 的实际限时取正数 `timeout` 和 `(disappearAt - appearAt) * 1000` 的较小值。若配置的 `timeout` 或展示参数 `component.props.total` 超过实际限时，校验返回 `QTE_DURATION_TRUNCATED` 警告并给出实际毫秒数。`props.total` 单独存在时仅影响展示，不产生超时判负；校验不会改写这些参数。`limited:false` 时关闭限时：忽略 `timeout` 与 `appearAt/disappearAt` 窗口，运行时不注册超时判负、不展示倒计时，故不产生 `QTE_DURATION_TRUNCATED` 告警（此时应同时不写 `props.total`）。`scale` 只做视觉缩放、不参与任何判定。

**变速的生效范围**：`videoSpeed` 只在 `appearAt`~`disappearAt` 这段媒体时间内改变播放速率（左闭右开：`disappearAt` 这一刻已回到原速，与该时刻的判负口径一致），区间之前与之后都是原速。例如 8s 的视频把 QTE 定在 3~4s、`videoSpeed:2`，播放顺序是：0~3s 原速 → 3~4s 两倍速（墙钟 0.5s）→ 4~8s 原速，总墙钟 7.5s。循环播放的节点每一轮都会重新进入区间。**要只在 QTE 区间内变速，`videoSpeed` 必须与 `appearAt`、`disappearAt` 一起写，且不要写 `limited:false`** —— 这两种写法下没有可用区间，运行时退化成**整段变速**（整个节点从第一帧按该速率播到结尾），并给 `QTE_SPEED_WHOLE_NODE` 告警：

- 缺 `appearAt` 或 `disappearAt`：没有区间终点，无从限定范围；
- `limited:false`：判负截止被整个关掉，组件也不在 `disappearAt` 消失，QTE 区间本就没有终点——即使两端都写了，`disappearAt` 在运行时也不生效，一律整段变速。

整段变速会成倍改变节点时长：20s 的视频配 `videoSpeed:0.5` 要播 40s 墙钟，配 `2` 则 10s 播完。配 `resultTransitionMode:"afterVideoEnd"` 时这段等待玩家躲不开，慢放要特别留意。

**速率与限时的时间基**：`appearAt`/`disappearAt`/`clipDuration` 是**媒体时间**（视频自己的时间轴），`timeout` 与运行时倒计时是**墙钟**。`videoSpeed` 只拉伸两者之间的换算关系：区间对应的墙钟长度是 `(disappearAt - appearAt) * 1000 / videoSpeed`，而 `timeout` 原样不变。所以 0.5 倍速会把媒体窗口对应的实际反应时间拉长一倍、2 倍速则折半，`QTE_DURATION_TRUNCATED` 的实际限时按折算后的值计算。作者按原速填写时间字段即可，不要自己乘除。

`disappearAt * 1000 <= clipDuration` 这条检查是**纯媒体时间比较**，始终不随速率折算——变速不会让一个超出片段长度的消失时机变得合法。折算只在**变速按区间生效**时发生：节点要**有自己的 `media`**（无自有 `media` 的节点画面是上一节点的定格继承帧，没有视频可变速）、速率要是非 `1` 的档位值、区间两端齐备且 `limited` 未关；任一条不满足都按 `1` 倍速算，避免"写了速率却只是限时被改短"。退化成整段变速时也按 `1` 算——那种写法下本就没有区间可折算，且 `limited:false` 时根本没有判定限时。

**变速的两个已知副作用**（按预期行为对待，不是缺陷）：变速只作用于节点视频自身的音轨，浏览器默认保持音高（台词变快/变慢但不变调）；节点与全局 BGM 走独立音轨、**不随速率变化**，所以 0.5/2 倍速段落会和 BGM 在节奏上分离，变速段落建议避开强节奏 BGM。

### start（入口节点）
- 数量不限，可省略；实际入口由 `meta.start` 指定
- 必须包含 `next`（线性后继）
- 不得包含 `choices`

### scene（叙事场景）
- 可包含 `choices`（>=2，有 choices 时用户选择分支）
- 可包含 `next`（无 choices 时线性推进）
- `choices` 和 `next` 互斥：有 choices 则无 next，有 next 则无 choices
- 入口可达的场景必须有通往结局的出口；剧情结束处使用 `ending`

### choice（分支选择）
- 必须包含 `choices`（>=2）
- 不得包含 `next`

### ending（结局节点）
- 必须包含 `ending_type`
- 不得包含 `next` 或 `choices`
- 图结构中所有 ending 必须可达

### interaction（交互节点，含 `click`/`combo`/`hold`/`direction`）
- `type` 为 `interaction` 或 QTE 玩法名 `click`/`combo`/`hold`/`direction`，均按 QTE 交互节点处理
- 必须包含交互载体：`interaction` 枚举字段，**或** `component` 组件引用（二选一，见上方「QTE 组件引用」）
- 出口二选一：`next`（线性后继），或成对的 `onSuccess` + `onFail`（QTE 成/败分支）
- `onSuccess`/`onFail` 成对出现、不得同指一节点、目标须存在且可达
- 合理性：`timeout` ∈ [1000,10000]ms；`window` < `duration`；`target`/`points` 坐标 ∈ 0~1

---

## 完整示例

```jsonc
{
  "meta": {
    "title": "阴门关",
    "version": "1.0.0",
    "start": "start_01"
  },
  "config": {
    "theme": { "mode": "dark", "accent": "#8b1a1a", "preset": "horror" },
    "audio": { "bgm": "https://cos.example.com/bgm/main.mp3", "bgmVolume": 0.7 }
  },
  "variables": {
    "has_key": false,
    "trust": 0
  },
  "items": [
    { "id": "old_key", "name": "生锈的钥匙", "image": "https://cos.example.com/items/key.png" }
  ],
  "characters": [
    { "id": "hero", "name": "小明", "image": "https://cos.example.com/avatars/hero.png" }
  ],
  "nodes": {
    "start_01": {
      "type": "start",
      "text": "夜色如墨，你站在一座古老的城门前。",
      "media": {
        "type": "video",
        "src": "https://cos.example.com/video/opening.mp4",
        "subtitle": "https://cos.example.com/subtitles/opening.vtt"
      },
      "speaker": "hero",
      "next": "scene_01"
    },
    "scene_01": {
      "type": "scene",
      "text": "城门缓缓打开，你看到一条幽深的小径。",
      "media": { "type": "video", "src": "https://cos.example.com/video/path.mp4" },
      "clipDuration": 30000,
      "choices": [
        {
          "label": "走进城门",
          "next": "ending_01",
          "effects": [{ "op": "set", "var": "has_key", "value": true }]
        },
        {
          "label": "转身离开",
          "next": "ending_01"
        }
      ]
    },
    "ending_01": {
      "type": "ending",
      "ending_type": "bad",
      "text": "你选择了离开，故事就此结束。"
    }
  }
}
```

---

## 播放模型

```
start → scene → scene(含choice) → interaction → scene(含choice) → ending
```

- 引擎从 `meta.start` 指定的入口节点开始播放
- `scene`/`interaction` 节点播完后，有 `next` 则自动前进，有 `choices` 则等待用户选择
- `choice` 节点显示选项列表，用户选择后跳转
- `ending` 节点播放后显示结局画面

---

## 字幕规范

- 字幕文件上传 COS，URL 写进 `media.subtitle`
- 支持格式：`.vtt` / `.srt` / `.ass`（按扩展名推断）
- 说话人标识：WebVTT 使用 `<v 角色名>` voice tag
- 无 `subtitle` 字段则该段无字幕（安全兜底，不报错）

---

## 素材托管规范

- 所有素材（视频/图片/音频/字幕/封面/按钮底图）上传到 COS
- 使用 http(s) URL 直接引用，无占位符 ID、无本地落盘、无 id→url 映射
- 引擎运行时直接按 URL 加载；URL 未就绪/失败时占位兜底
- 需保证 COS 允许引擎域名跨域（CORS）
