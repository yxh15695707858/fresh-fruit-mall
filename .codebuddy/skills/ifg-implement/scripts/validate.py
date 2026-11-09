#!/usr/bin/env python3
"""
IFG (Interactive Film Game) story.json 数据合规校验器。

用法:
    # 校验项目中的 story.json（<project_root>/frontend/public/story/story.json）
    python3 validate.py <project_root> [--stage <stage>] [--watch]

    # 直接校验任意路径的 story.json（用于落盘前校验，如 /tmp 下载的文件）
    python3 validate.py --file <path/to/story.json> [--stage <stage>]

校验流程:
    所有阶段都会先执行 references/story.schema.json 结构校验。

校验阶段:
    tree    - 图结构校验（入口/孤儿/可达性）
    media   - media 素材 URL 语义校验
    logic   - 状态逻辑（变量/道具声明与引用自洽）
    full    - 全部阶段

退出码:
    0 = PASS，非 0 = FAIL（打印失败清单）
"""

import json
import math
import re
import sys
from pathlib import Path
from urllib.parse import urlparse


# ── 工具函数 ────────────────────────────────────────────

def err(msg, node_id=None, field=None):
    """输出错误"""
    loc = f"[{node_id}" + (f".{field}" if field else "") + "] " if node_id else ""
    print(f"  FAIL  {loc}{msg}")
    return False


def warn(msg, node_id=None, field=None):
    """输出警告"""
    loc = f"[{node_id}" + (f".{field}" if field else "") + "] " if node_id else ""
    print(f"  WARN  {loc}{msg}")


def is_valid_url(url):
    """检查是否为合法 http(s) URL"""
    if not url or not isinstance(url, str) or re.search(r"[\t\r\n]", url):
        return False
    try:
        result = urlparse(url)
        return result.scheme in ("http", "https") and bool(result.netloc) and not re.search(r"\s", result.netloc)
    except Exception:
        return False


def json_parse(filepath):
    """解析 JSON 文件，返回 (data, error)"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        return json.loads(content), None
    except json.JSONDecodeError as e:
        return None, f"JSON 语法错误 (行 {e.lineno}, 列 {e.colno}): {e.msg}"
    except FileNotFoundError:
        return None, f"文件不存在: {filepath}"
    except Exception as e:
        return None, str(e)


SCHEMA_PATH = Path(__file__).resolve().parent.parent / "references" / "story.schema.json"
_SCHEMA_KEYWORDS = {
    "$schema", "$id", "$ref", "$comment", "title", "description",
    "type", "required", "properties", "additionalProperties", "definitions",
    "items", "minItems", "minProperties", "enum", "const", "pattern",
    "minimum", "maximum", "format", "oneOf", "allOf", "not", "if", "then", "else",
}


def _find_unsupported_keywords(schema, path="$"):
    """确保 bundled schema 只使用本校验器支持的 Draft-07 关键字。"""
    if not isinstance(schema, dict):
        return []

    errors = [f"{path}: 不支持的 Schema 关键字 {key}" for key in schema if key not in _SCHEMA_KEYWORDS]

    for container in ("properties", "definitions"):
        for name, child in schema.get(container, {}).items():
            errors.extend(_find_unsupported_keywords(child, f"{path}.{container}.{name}"))

    for key in ("items", "additionalProperties", "not", "if", "then", "else"):
        child = schema.get(key)
        if isinstance(child, dict):
            errors.extend(_find_unsupported_keywords(child, f"{path}.{key}"))

    for key in ("oneOf", "allOf"):
        for index, child in enumerate(schema.get(key, [])):
            errors.extend(_find_unsupported_keywords(child, f"{path}.{key}[{index}]"))

    return errors


def _resolve_ref(root_schema, ref):
    if not ref.startswith("#/"):
        raise ValueError(f"仅支持本地 Schema 引用: {ref}")

    target = root_schema
    for part in ref[2:].split("/"):
        key = part.replace("~1", "/").replace("~0", "~")
        target = target[key]
    return target


def _matches_type(value, expected):
    matchers = {
        "object": lambda v: isinstance(v, dict),
        "array": lambda v: isinstance(v, list),
        "string": lambda v: isinstance(v, str),
        "boolean": lambda v: isinstance(v, bool),
        "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
        "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
        "null": lambda v: v is None,
    }
    return matchers[expected](value)


def _schema_errors(value, schema, root_schema, path="$"):
    """校验当前 story schema 使用到的 Draft-07 关键字子集。"""
    if "$ref" in schema:
        return _schema_errors(value, _resolve_ref(root_schema, schema["$ref"]), root_schema, path)

    errors = []
    expected_type = schema.get("type")
    if expected_type is not None:
        allowed_types = expected_type if isinstance(expected_type, list) else [expected_type]
        if not any(_matches_type(value, item) for item in allowed_types):
            return [f"{path}: 类型应为 {'/'.join(allowed_types)}"]

    for child in schema.get("allOf", []):
        errors.extend(_schema_errors(value, child, root_schema, path))

    if "oneOf" in schema:
        matches = sum(
            not _schema_errors(value, child, root_schema, path)
            for child in schema["oneOf"]
        )
        if matches != 1:
            errors.append(f"{path}: 必须且只能匹配一个 oneOf 分支，实际匹配 {matches} 个")

    if "not" in schema and not _schema_errors(value, schema["not"], root_schema, path):
        errors.append(f"{path}: 命中了禁止的字段组合")

    if "if" in schema:
        condition_matches = not _schema_errors(value, schema["if"], root_schema, path)
        branch = schema.get("then") if condition_matches else schema.get("else")
        if branch:
            errors.extend(_schema_errors(value, branch, root_schema, path))

    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: 值 {value!r} 不在允许范围 {schema['enum']}")
    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: 值必须为 {schema['const']!r}")

    if isinstance(value, dict):
        required = schema.get("required", [])
        for key in required:
            if key not in value:
                errors.append(f"{path}.{key}: 缺少必填字段")

        properties = schema.get("properties", {})
        for key, child in properties.items():
            if key in value:
                errors.extend(_schema_errors(value[key], child, root_schema, f"{path}.{key}"))

        additional = schema.get("additionalProperties")
        if additional is not None:
            for key in sorted(value.keys() - properties.keys()):
                if additional is False:
                    errors.append(f"{path}.{key}: 不允许的字段")
                elif isinstance(additional, dict):
                    errors.extend(_schema_errors(value[key], additional, root_schema, f"{path}.{key}"))

        if len(value) < schema.get("minProperties", 0):
            errors.append(f"{path}: 字段数量不能少于 {schema['minProperties']}")

    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errors.append(f"{path}: 数组元素不能少于 {schema['minItems']} 个")
        if isinstance(schema.get("items"), dict):
            for index, item in enumerate(value):
                errors.extend(_schema_errors(item, schema["items"], root_schema, f"{path}[{index}]"))

    if isinstance(value, str):
        pattern = schema.get("pattern")
        if pattern and re.search(pattern, value) is None:
            errors.append(f"{path}: 字符串不匹配格式 {pattern}")
        if schema.get("format") == "uri" and not urlparse(value).scheme:
            errors.append(f"{path}: 不是合法 URI")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: 不能小于 {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: 不能大于 {schema['maximum']}")

    return errors


def validate_schema_contract(data):
    """以 bundled story.schema.json 为唯一结构契约执行校验。"""
    try:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"无法读取 Schema: {exc}"]

    unsupported = _find_unsupported_keywords(schema)
    if unsupported:
        return unsupported
    return _schema_errors(data, schema, schema)


# ── QTE 组件契约清单（CCR）──────────────────────────────

def _load_qte_registry(story_path):
    """定位 qte-registry.json：优先 story.json 同目录（对账刷新的快照），否则回退 bundled references 副本。"""
    candidates = [
        Path(story_path).parent / "qte-registry.json",
        Path(__file__).resolve().parent.parent / "references" / "qte-registry.json",
    ]
    for p in candidates:
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                return None
    return None


def _parse_semver(v):
    """解析为 (数字三元组, prerelease 标识符列表)。忽略 +build。"""
    s = str(v).split("+")[0]
    core, _, pre = s.partition("-")
    parts = core.split(".")
    nums = []
    for i in range(3):
        try:
            nums.append(int(parts[i]))
        except (IndexError, ValueError):
            nums.append(0)
    return tuple(nums), (pre.split(".") if pre else [])


def _semver_tuple(v):
    """仅取前三段数字（兼容段判定用）。"""
    return _parse_semver(v)[0]


def _cmp_pre(a, b):
    """比较两组 prerelease 标识符（semver 规则）：无 prerelease > 有 prerelease。"""
    if not a and not b:
        return 0
    if not a:
        return 1
    if not b:
        return -1
    for x, y in zip(a, b):
        xn, yn = x.isdigit(), y.isdigit()
        if xn and yn:
            c = (int(x) > int(y)) - (int(x) < int(y))
        elif xn != yn:
            c = -1 if xn else 1  # 数字标识符 < 字母标识符
        else:
            c = (x > y) - (x < y)
        if c:
            return c
    return (len(a) > len(b)) - (len(a) < len(b))


def _semver_cmp(a, b):
    """整版本比较（含 prerelease）：-1/0/1。"""
    an, ap = _parse_semver(a)
    bn, bp = _parse_semver(b)
    if an != bn:
        return (an > bn) - (an < bn)
    return _cmp_pre(ap, bp)


def _semver_ge(a, b):
    return _semver_cmp(a, b) >= 0


def _caret_satisfies(installed, floor):
    """caret 兼容：同兼容段（首个非零数字段一致）且 installed >= floor（含 prerelease 排序，
    故 0.1.0-beta.0 < 0.1.0-beta.1）。防止 major 破坏性升级悄悄满足旧 floor。"""
    if _semver_cmp(installed, floor) < 0:
        return False
    iv, fv = _semver_tuple(installed), _semver_tuple(floor)
    if fv[0] > 0:
        return iv[0] == fv[0]
    if fv[1] > 0:
        return iv[0] == 0 and iv[1] == fv[1]
    return iv[0] == 0 and iv[1] == 0 and iv[2] == fv[2]


# ── QTE 引用归一化（上游终态 key/type ↔ 逻辑短名）──

_QTE_ALIAS = {
    "GameClickControl": "click", "GameComboControl": "combo",
    "GameHoldControl": "hold", "GameSlideControl": "slide",
    "click": "click", "combo": "combo", "hold": "hold", "slide": "slide",
    "direction": "slide", "swipe": "slide",
}
# 会被当作 QTE 交互节点处理的 node.type
_QTE_NODE_TYPES = {"interaction", "click", "combo", "hold", "direction"}


def _canon_qte_name(comp, node_type=None):
    """component.key(库控件类名) / component.name(逻辑短名) / node.type → 逻辑短名；
    未知具名原样返回（交 catalog 判未登记）；无 key/name 时靠节点 type，未知 type → None。"""
    cand = None
    if isinstance(comp, dict):
        cand = comp.get("key") or comp.get("name")
    if cand:
        return _QTE_ALIAS.get(cand, cand)
    return _QTE_ALIAS.get(node_type)


# ── 校验器 ──────────────────────────────────────────────

class StoryValidator:
    """story.json 数据合规校验器"""

    def __init__(self, data, registry=None):
        self.data = data
        self.nodes = dict(sorted(data.get("nodes", {}).items()))
        self.variables = data.get("variables", {})
        self.items = {item.get("id"): item for item in data.get("items", [])}
        self.characters = {c.get("id"): c for c in data.get("characters", [])}
        self.errors = 0
        self.warnings = 0
        # CCR 快照：None 表示无快照（组件 floor/props 校验降级为 WARN 跳过）
        self.qte_components = registry.get("components") if isinstance(registry, dict) else None
        self.qte_lib_version = registry.get("libVersion") if isinstance(registry, dict) else None
        # story 级整库引用：qte.version 为整库版本权威（新模型），component.version 已废弃仅兼容旧数据
        qte_block = data.get("qte") if isinstance(data.get("qte"), dict) else {}
        self.qte_pin = qte_block.get("version")
        self.qte_lib = qte_block.get("lib")

    def validate_component_versions(self):
        components = self.data.get("config", {}).get("components", {})
        slots = sorted(components)
        if not slots:
            return True

        version = self.qte_pin if self.qte_pin is not None else components[slots[0]]["version"]
        conflict = False
        for slot in slots:
            actual = components[slot]["version"]
            if actual != version:
                conflict = True
                self.errors += 1
                err(f"$.config.components.{slot}.version: 展示组件版本必须统一为 {version}，实际 {actual}")
        if conflict or self.qte_pin is not None:
            return not conflict

        for nid, node in self.nodes.items():
            if node.get("type") not in _QTE_NODE_TYPES:
                continue
            floor = node.get("component", {}).get("version")
            if isinstance(floor, str) and floor and not _caret_satisfies(version, floor):
                self.errors += 1
                err(f"$.nodes.{nid}.component.version: 展示组件版本 {version} 不满足 QTE 兼容下限 {floor}")
        return self.errors == 0

    def validate_tree(self):
        """阶段：图结构校验"""
        nodes = self.nodes

        # 1. 必须有 nodes
        if not nodes:
            self.errors += 1
            err("nodes 为空或缺失")
            return

        # 2. 验证 meta.start
        meta_start = self.data.get("meta", {}).get("start")
        if meta_start:
            if meta_start not in nodes:
                self.errors += 1
                err(f"meta.start 指向不存在的节点: {meta_start}")
        else:
            self.errors += 1
            err("meta.start 缺失")

        has_dangling = False
        adjacency = {}
        # 3. 遍历节点验证基本字段
        for nid, node in nodes.items():
            node_type = node.get("type", "unknown")

            # 所有节点必须包含 text
            if "text" not in node:
                self.errors += 1
                err("缺少 text 字段", nid)

            # type 检查
            valid_types = {"start", "scene", "choice", "ending", "interaction",
                           "click", "combo", "hold", "direction"}
            if node_type not in valid_types:
                self.errors += 1
                err(f"无效节点类型: {node_type}", nid)

            # start 必须有 next，不能有 choices
            if node_type == "start":
                if "next" not in node:
                    self.errors += 1
                    err("start 节点缺少 next", nid)
                if "choices" in node:
                    self.errors += 1
                    err("start 节点不应包含 choices", nid)

            # ending 必须有 ending_type，不能有 next/choices
            if node_type == "ending":
                if "ending_type" not in node:
                    self.errors += 1
                    err("ending 节点缺少 ending_type", nid)
                else:
                    valid_ending = {"good", "bad", "hidden", "normal"}
                    if node["ending_type"] not in valid_ending:
                        self.errors += 1
                        err(f"无效 ending_type: {node['ending_type']}", nid, "ending_type")
                if "next" in node:
                    self.errors += 1
                    err("ending 节点不应包含 next", nid)
                if "choices" in node:
                    self.errors += 1
                    err("ending 节点不应包含 choices", nid)

            # choice 必须有 choices (>=2)
            if node_type == "choice":
                if "choices" not in node or len(node["choices"]) < 2:
                    self.errors += 1
                    err("choice 节点必须包含至少 2 个选项", nid)

            # interaction 节点：交互类型/组件 + 出口 + 成/败分支 + 合理性
            # （含上游终态玩法节点 click/combo/hold/direction，均按 QTE 交互处理）
            if node_type in _QTE_NODE_TYPES:
                # 交互载体：内置 interaction 枚举 或 QTE 组件引用（二选一）
                if "interaction" not in node and not isinstance(node.get("component"), dict):
                    self.errors += 1
                    err("interaction 节点缺少交互载体：需要 interaction 字段或 component 组件引用", nid)
                has_success = "onSuccess" in node
                has_fail = "onFail" in node
                # 出口：需要 next，或成对的 onSuccess + onFail
                if not node.get("next") and not (has_success and has_fail):
                    self.errors += 1
                    err("interaction 节点缺少出口：需要 next，或成对的 onSuccess + onFail", nid)
                # onSuccess / onFail 必须成对出现
                if has_success != has_fail:
                    self.errors += 1
                    err("onSuccess 与 onFail 必须成对出现（QTE 成/败分支）", nid)
                # 成功与失败不能指向同一节点，否则 QTE 判定无意义
                if has_success and has_fail and node.get("onSuccess") == node.get("onFail"):
                    self.errors += 1
                    err(f"onSuccess 与 onFail 指向同一节点({node.get('onSuccess')})，QTE 成/败无区别", nid)
                # onSuccess / onFail 引用存在性
                for key in ("onSuccess", "onFail"):
                    ref = node.get(key)
                    if ref and ref not in nodes:
                        has_dangling = True
                        self.errors += 1
                        err(f"{key} 指向不存在的节点: {ref}", nid, key)
                # 合理性：命中窗口应小于蓄力时长
                dur, win = node.get("duration"), node.get("window")
                if isinstance(dur, (int, float)) and isinstance(win, (int, float)) and win >= dur:
                    self.errors += 1
                    err(f"判定窗口 window({win}) 不应 >= 蓄力时长 duration({dur})", nid)
                # 合理性：判定限时应在 [1000, 10000] ms
                to = node.get("timeout")
                if isinstance(to, (int, float)) and not isinstance(to, bool) and not (1000 <= to <= 10000):
                    self.errors += 1
                    err(f"timeout({to}ms) 超出合理区间 [1000, 10000]", nid)
                # 合理性：drag 目标点 / trace 途经点坐标应在 0~1
                pts = []
                if isinstance(node.get("target"), dict):
                    pts.append(("target", node["target"]))
                for i, p in enumerate(node.get("points", []) or []):
                    if isinstance(p, dict):
                        pts.append((f"points[{i}]", p))
                for label, p in pts:
                    for axis in ("x", "y"):
                        v = p.get(axis)
                        if isinstance(v, (int, float)) and not isinstance(v, bool) and not (0 <= v <= 1):
                            self.errors += 1
                            err(f"{label}.{axis}({v}) 应在 0~1（相对媒体框）", nid)
                # QTE 组件引用 + rect + 时机 + CCR props 校验
                self._check_qte(nid, node)

            # 相邻同 setting 警告
            # （简化校验，仅输出提醒）
            if node.get("setting"):
                pass  # 全量校验需要上下文分析，此处略

            # 检查 choices
            choices = node.get("choices", [])
            if choices:
                for i, choice in enumerate(choices):
                    if "label" not in choice:
                        self.errors += 1
                        err(f"第 {i+1} 个选项缺少 label", nid)
                    if "next" not in choice:
                        self.errors += 1
                        err(f"第 {i+1} 个选项缺少 next", nid)
                    elif choice["next"] not in nodes:
                        has_dangling = True
                        self.errors += 1
                        err(f"第 {i+1} 个选项的 next 指向不存在的节点: {choice['next']}", nid)

            # 检查 next
            nxt = node.get("next")
            if nxt and nxt not in nodes:
                has_dangling = True
                self.errors += 1
                err(f"next 指向不存在的节点: {nxt}", nid)

            fail = node.get("fail")
            if "fail" in node and fail not in nodes:
                has_dangling = True
                self.errors += 1
                err(f"fail 指向不存在的节点: {fail}", nid, "fail")

            refs = [nxt]
            if node_type in _QTE_NODE_TYPES:
                refs = [node.get(key) or nxt for key in ("onSuccess", "onFail")]
            refs.extend(choice.get("next") for choice in node.get("choices", []))
            if node_type in _QTE_NODE_TYPES and not isinstance(node.get("component"), dict):
                refs.append(fail)
            adjacency[nid] = [ref for ref in refs if ref]

        # 4. 可达性检查（简单 BFS）
        if meta_start and meta_start in nodes:
            reachable = set()
            queue = [meta_start]
            while queue:
                nid = queue.pop(0)
                if nid in reachable:
                    continue
                reachable.add(nid)
                queue.extend(adjacency.get(nid, []))

            unreachable = set(nodes.keys()) - reachable
            if unreachable:
                self.warnings += 1
                warn(f"以下节点从入口不可达: {', '.join(sorted(unreachable)[:10])}")

            # ending 可达性
            endings = [nid for nid, n in nodes.items() if n.get("type") == "ending"]
            unreachable_endings = [e for e in endings if e not in reachable]
            if unreachable_endings:
                self.errors += 1
                err(f"结局节点不可达: {', '.join(unreachable_endings)}")

            if not has_dangling:
                predecessors = {nid: [] for nid in nodes}
                for nid, refs in adjacency.items():
                    for ref in refs:
                        if ref in predecessors:
                            predecessors[ref].append(nid)
                can_reach_ending = set()
                queue = list(endings)
                while queue:
                    nid = queue.pop()
                    if nid in can_reach_ending:
                        continue
                    can_reach_ending.add(nid)
                    queue.extend(predecessors[nid])
                trapped = reachable - can_reach_ending
                if trapped:
                    self.errors += 1
                    err(f"以下节点无法到达任何结局: {', '.join(sorted(trapped)[:10])}")

        return self.errors == 0

    def _check_qte(self, nid, node):
        """QTE 组件节点校验：时机窗口、rect、CCR floor/props/capabilities（degraded 短路）。"""
        num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)

        # 时机窗口（对 interaction/component 通用）
        a, d = node.get("appearAt"), node.get("disappearAt")
        if num(a) and num(d) and not (a < d):
            self.errors += 1
            err(f"appearAt({a}) 必须 < disappearAt({d})", nid)
        cd = node.get("clipDuration")
        if num(d) and num(cd) and d * 1000 > cd:
            self.errors += 1
            err(f"disappearAt({d}s) 不应 > clipDuration({cd}ms)", nid)

        comp = node.get("component")
        if not isinstance(comp, dict):
            # scale/limited/videoSpeed/resultTransitionMode 仅对带 component 的 QTE 生效；
            # 无 component（旧内置 interaction）时运行时直接忽略 → 提醒作者
            ignored = [k for k in ("scale", "limited", "videoSpeed", "resultTransitionMode") if node.get(k) is not None]
            if ignored:
                self.warnings += 1
                warn(f"{'/'.join(ignored)} 仅对带 component 的 QTE 节点生效；该节点无 component，运行时将忽略", nid)
            return

        # afterVideoEnd 要等本节点视频播放结束：无自有 media（定格继承上一节点画面）或实际循环播放
        # （循环视频不派发 ended）都等不到该信号，运行时回落 immediate。
        # 循环与运行时同源：node.loop 缺省时继承 config.features.loopByDefault。
        loop_by_default = self.data.get("config", {}).get("features", {}).get("loopByDefault") is True
        looping = loop_by_default if node.get("loop") is None else node.get("loop") is True
        if node.get("resultTransitionMode") == "afterVideoEnd" and (node.get("media") is None or looping):
            if node.get("media") is None:
                reason = "该节点没有自己的 media，不会有视频播放结束事件"
            elif node.get("loop") is True:
                reason = "该节点 loop:true，循环视频不会播放结束"
            else:
                reason = "该节点经 config.features.loopByDefault 继承循环播放，循环视频不会播放结束"
            self.warnings += 1
            warn(f"resultTransitionMode:afterVideoEnd 无法生效：{reason}，运行时将回落 immediate", nid, "resultTransitionMode")

        # videoSpeed 宽容处理：非档位值不 FAIL，运行时回落 1。三条互斥，不重复告警：
        #  - 非档位值 → 忽略，回落 1；
        #  - 无自有 media → 没有视频可变速，回落 1（否则兜底时钟与窗口折算会静默改写 QTE 限时）；
        #  - 没有可用的 appearAt~disappearAt 区间 → 不回落 1，而是整段变速（整个节点按该速率播放）。
        #    两种触发：缺端点，或 limited:false 把判负截止整个关掉、disappearAt 不再生效 ——
        #    此时 QTE 区间没有终点，拿它当变速边界没有依据。
        raw_speed = node.get("videoSpeed")
        valid_speed = num(raw_speed) and raw_speed in (0.5, 1, 1.5, 2)
        speed_effective = valid_speed and raw_speed != 1 and node.get("media") is not None
        pair_present = num(a) and num(d)
        inverted = pair_present and not a < d
        has_window = pair_present and not inverted and node.get("limited") is not False
        if raw_speed is not None and not valid_speed:
            # 非数值用 JSON 字面量呈现，避免字符串 "2" 打印成 2 后与合法档位混淆。
            # separators 必须给紧凑形式：json.dumps 默认在 , 和 : 后加空格，而 TS 侧的
            # JSON.stringify 不加，容器取值（[2,3] / {"x":2}）会让两侧文案逐字对不上。
            shown = str(raw_speed) if num(raw_speed) else json.dumps(raw_speed, ensure_ascii=False, separators=(",", ":"))
            self.warnings += 1
            warn(f"videoSpeed({shown}) 非 0.5/1/1.5/2 档位，运行时将忽略并回落 1（正常速度）", nid, "videoSpeed")
        elif valid_speed and raw_speed != 1 and node.get("media") is None:
            self.warnings += 1
            warn(f"videoSpeed({raw_speed}) 无法生效：该节点没有自己的 media，没有视频可变速，运行时将回落 1（正常速度）", nid, "videoSpeed")
        elif speed_effective and not has_window and not inverted:
            # 倒置已由 QTE_APPEAR_GE_DISAPPEAR 报错（必须先改对），这里不叠第二条噪声
            missing = "/".join(k for k, v in (("appearAt", a), ("disappearAt", d)) if not num(v))
            # 两个原因可以同时成立（真实内容里就有「缺 disappearAt 且 limited:false」）：
            # 只报一个会让作者补完字段后发现还是整段变速，必须两条都点出来才是可操作的
            unlimited = "limited:false 已关闭判定限时，disappearAt 不再生效、QTE 区间没有终点" if node.get("limited") is False else ""
            if missing and unlimited:
                reason = f"该节点缺 {missing}，且 {unlimited}"
            elif unlimited:
                reason = f"该节点 {unlimited}"
            else:
                reason = f"该节点缺 {missing}"
            self.warnings += 1
            warn(f"videoSpeed({raw_speed}) 将整段生效：变速优先只在 appearAt~disappearAt（媒体时间）区间内，{reason}，运行时整个节点按 {raw_speed} 倍速播放", nid, "videoSpeed")

        # appearAt/disappearAt 是媒体时间，区间内变速后对应的墙钟长度要除以速率。
        # 除数与上面的生效判定同源：区间不成立时按 1 走（整段变速下根本没有区间可折算），否则会
        # 出现「限时按 2 倍算、画面却是原速」这种只在某些写法下才暴露的漂移。
        speed = raw_speed if speed_effective and has_window else 1
        window_ms = (d - a) * 1000 / speed if num(a) and num(d) else None
        timeout = node.get("timeout")
        total = comp.get("props", {}).get("total")
        positive = lambda value: num(value) and math.isfinite(value) and value > 0
        limits = [value for value in (timeout, window_ms) if positive(value)]
        configured = [value for value in (timeout, total * 1000 if num(total) else None) if positive(value)]
        if node.get("limited") is not False and limits and configured:
            effective_ms = math.floor(min(limits) + 0.5)
            configured_ms = math.floor(max(configured) + 0.5)
            if configured_ms > effective_ms:
                self.warnings += 1
                warn(f"配置时长({configured_ms}ms) 超过实际 QTE 时间({effective_ms}ms)，请检查 timeout、appearAt/disappearAt 与 component.props.total", nid)

        # rect 边界（0~1，且 x+w<=1 / y+h<=1）
        rect = node.get("rect")
        if isinstance(rect, dict):
            for axis in ("x", "y", "w", "h"):
                v = rect.get(axis)
                if num(v) and not (0 <= v <= 1):
                    self.errors += 1
                    err(f"rect.{axis}({v}) 应在 0~1", nid, "rect")
            x, y, w, h = (rect.get(k) for k in ("x", "y", "w", "h"))
            if num(x) and num(w) and x + w > 1:
                self.errors += 1
                err(f"rect 越界：x+w({x + w}) > 1", nid, "rect")
            if num(y) and num(h) and y + h > 1:
                self.errors += 1
                err(f"rect 越界：y+h({y + h}) > 1", nid, "rect")

        # scale 宽容处理：非法值（非有限数 / 超出 50~200）不 FAIL，运行时一律回落 100；仅 WARN 提示作者
        scale = node.get("scale")
        if scale is not None and not (num(scale) and math.isfinite(scale) and 50 <= scale <= 200):
            self.warnings += 1
            warn(f"scale({scale}) 非 50~200 的有限数，运行时将忽略并回落 100（不缩放）", nid, "scale")

        # degraded 短路：对账主动降级为 FallbackQte 的节点，跳过 floor/props，仅 WARN
        if comp.get("degraded") is True:
            self.warnings += 1
            warn("QTE 已降级为 FallbackQte（对账未满足），跳过 floor/props 校验", nid)
            return

        name = _canon_qte_name(comp, node.get("type"))
        # 无 CCR 快照 → 无法做 floor/props 校验，降级 WARN 跳过（不阻塞离线 dev）
        if self.qte_components is None:
            self.warnings += 1
            warn("无 CCR 快照（qte-registry.json），跳过组件 floor/props 校验", nid)
            return

        if name is None:
            self.errors += 1
            err(f"无法识别的 QTE 组件引用：key={comp.get('key')!r} name={comp.get('name')!r} type={node.get('type')!r}", nid, "component")
            return

        entry = self.qte_components.get(name)
        if entry is None:
            self.errors += 1
            err(f"组件 '{name}' 未在 CCR 快照登记", nid, "component")
            return

        # floor：整库版本须满足 story.qte.version（新模型）；缺省回退旧的 component.version
        ver = self.qte_pin or comp.get("version")
        if isinstance(ver, str) and self.qte_lib_version and not _caret_satisfies(self.qte_lib_version, ver):
            self.errors += 1
            err(f"组件库需要 ~{ver}（同 major 且≥），当前快照 {self.qte_lib_version}", nid, "qte.version")

        # props 深校验（复用 schema 引擎，propsSchema 随组件走）
        pschema = entry.get("propsSchema")
        if isinstance(pschema, dict):
            bad_kw = _find_unsupported_keywords(pschema)
            if bad_kw:
                self.warnings += 1
                warn(f"组件 '{name}' propsSchema 含不支持关键字，跳过 props 校验: {bad_kw[:3]}", nid)
            else:
                for e in _schema_errors(comp.get("props", {}), pschema, pschema, path=f"props"):
                    self.errors += 1
                    err(e, nid, "component.props")

        # capabilities：不会失败的玩法却给了独立 onFail → 失败分支永不可达
        caps = entry.get("capabilities", {})
        if caps.get("canFail") is False and node.get("onFail") and node.get("onFail") != node.get("onSuccess"):
            self.warnings += 1
            warn(f"组件 '{name}' 不会失败(canFail=false)，onFail 分支永不可达", nid)

    def validate_media(self):
        """阶段：media URL 语义校验（结构由 Schema oneOf definitions/Media 保证）"""
        bgm = self.data.get("config", {}).get("audio", {}).get("bgm")
        if bgm and not is_valid_url(bgm):
            self.errors += 1
            err(f"config.audio.bgm 不是合法 http(s) URL: {bgm}")

        for nid, node in self.nodes.items():
            bgm = node.get("bgm")
            if bgm and not is_valid_url(bgm):
                self.errors += 1
                err(f"bgm 不是合法 http(s) URL: {bgm}", nid, "bgm")

            media = node.get("media")
            if media is None:
                continue

            mtype = media.get("type")
            if mtype == "video":
                src = media.get("src")
                if not src:
                    self.errors += 1
                    err("media.src 缺失", nid, "media.src")
                elif not is_valid_url(src):
                    self.errors += 1
                    err(f"media.src 不是合法 http(s) URL: {src}", nid, "media.src")

                subtitle = media.get("subtitle")
                if subtitle and not is_valid_url(subtitle):
                    self.errors += 1
                    err(f"media.subtitle 不是合法 http(s) URL: {subtitle}", nid, "media.subtitle")

            elif mtype == "sequence":
                for i, item in enumerate(media.get("items", [])):
                    src = item.get("src") if isinstance(item, dict) else None
                    if not src or not is_valid_url(src):
                        self.errors += 1
                        err(f"media.items[{i}].src 不是合法 http(s) URL", nid, f"media.items[{i}].src")
                    subtitle = item.get("subtitle") if isinstance(item, dict) else None
                    if subtitle and not is_valid_url(subtitle):
                        self.errors += 1
                        err(f"media.items[{i}].subtitle 不是合法 http(s) URL", nid, f"media.items[{i}].subtitle")

            else:
                self.errors += 1
                err(f"media.type 不支持: {mtype}", nid, "media.type")

        return self.errors == 0

    def _check_effect(self, effect, nid, path):
        """校验单个 effect（op 结构：set/inc/dec + var，add/remove + item）"""
        op = effect.get("op")
        if op in ("set", "inc", "dec"):
            var = effect.get("var")
            if var is not None and var not in self.variables:
                self.warnings += 1
                warn(f"effect 引用未声明的变量: {var}", nid, f"{path}.var")
        elif op in ("add", "remove"):
            item = effect.get("item")
            if item is not None and item not in self.items:
                self.warnings += 1
                warn(f"effect 引用未定义的道具: {item}", nid, f"{path}.item")
        else:
            self.warnings += 1
            warn(f"effect 使用未知 op: {op}（应为 set/inc/dec/add/remove）", nid, f"{path}.op")

    def _check_condition(self, cond, nid, path):
        """校验结构化 condition（递归 and/or/not；叶子为 op 比较 / has / visited）"""
        if not isinstance(cond, dict):
            self.warnings += 1
            warn(f"condition 必须为结构化对象（如 {{\"op\":\">=\",\"var\":\"x\",\"value\":1}}），当前为 {type(cond).__name__}", nid, path)
            return
        if "and" in cond:
            for j, c in enumerate(cond["and"]):
                self._check_condition(c, nid, f"{path}.and[{j}]")
            return
        if "or" in cond:
            for j, c in enumerate(cond["or"]):
                self._check_condition(c, nid, f"{path}.or[{j}]")
            return
        if "not" in cond:
            self._check_condition(cond["not"], nid, f"{path}.not")
            return
        op = cond.get("op")
        if op == "has":
            if cond.get("item") not in self.items:
                self.warnings += 1
                warn(f"condition(has) 引用未定义道具: {cond.get('item')}", nid, path)
        elif op == "visited":
            if cond.get("node") not in self.nodes:
                self.warnings += 1
                warn(f"condition(visited) 引用不存在节点: {cond.get('node')}", nid, path)
        elif op in (">", ">=", "<", "<=", "==", "!="):
            if cond.get("var") not in self.variables:
                self.warnings += 1
                warn(f"condition 引用未声明变量: {cond.get('var')}", nid, path)
        else:
            self.warnings += 1
            warn(f"condition 使用未知 op: {op}", nid, path)

    def validate_logic(self):
        """阶段：状态逻辑校验（effect/condition 结构与变量/道具/角色引用自洽）"""
        for nid, node in self.nodes.items():
            # 节点级 effects
            for i, effect in enumerate(node.get("effects", [])):
                self._check_effect(effect, nid, f"effects[{i}]")

            # choices 的 effects / condition
            for ci, choice in enumerate(node.get("choices", [])):
                for i, effect in enumerate(choice.get("effects", [])):
                    self._check_effect(effect, nid, f"choices[{ci}].effects[{i}]")
                condition = choice.get("condition")
                if condition is not None:
                    self._check_condition(condition, nid, f"choices[{ci}].condition")

            # 检查 speaker 引用
            speaker = node.get("speaker")
            if speaker and speaker not in self.characters:
                self.warnings += 1
                warn(f"speaker 引用未定义角色: {speaker}", nid, "speaker")

        return self.errors == 0

    def run_all(self):
        """运行全部阶段"""
        results = []
        results.append(("components", self.validate_component_versions()))
        results.append(("tree", self.validate_tree()))
        results.append(("media", self.validate_media()))
        results.append(("logic", self.validate_logic()))
        return all(r[1] for r in results)


# ── 主入口 ──────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="IFG story.json 校验器")
    parser.add_argument("project_root", nargs="?",
                        help="项目根目录（校验 <root>/frontend/public/story/story.json）")
    parser.add_argument("--file", help="直接校验指定的 story.json 文件路径（用于落盘前校验，如 /tmp 下载的文件）")
    parser.add_argument("--stage", choices=["tree", "media", "logic", "full"], default="full",
                        help="校验阶段（默认 full）")
    parser.add_argument("--watch", action="store_true", help="监听模式（暂未实现）")

    args = parser.parse_args()

    if args.file:
        story_path = Path(args.file)
    elif args.project_root:
        story_path = Path(args.project_root) / "frontend" / "public" / "story" / "story.json"
    else:
        parser.error("必须提供 project_root 或 --file 之一")

    if not story_path.exists():
        print(f"FAIL  story.json 未找到: {story_path}")
        sys.exit(1)

    print(f"正在校验: {story_path}")
    print()

    data, parse_error = json_parse(story_path)
    if parse_error:
        print(f"FAIL  {parse_error}")
        sys.exit(1)

    schema_errors = validate_schema_contract(data)
    if schema_errors:
        for message in schema_errors:
            print(f"  FAIL  [schema] {message}")
        print()
        print(f"结果: FAIL（{len(schema_errors)} 个 Schema 错误）")
        sys.exit(1)

    validator = StoryValidator(data, _load_qte_registry(story_path))
    if args.stage != "full":
        validator.validate_component_versions()

    if args.stage == "tree":
        passed = validator.validate_tree()
    elif args.stage == "media":
        passed = validator.validate_media()
    elif args.stage == "logic":
        passed = validator.validate_logic()
    else:
        passed = validator.run_all()

    print()
    if validator.errors > 0:
        print(f"结果: FAIL（{validator.errors} 个错误，{validator.warnings} 个警告）")
        sys.exit(1)
    elif validator.warnings > 0:
        print(f"结果: PASS（{validator.warnings} 个警告）")
        sys.exit(0)
    else:
        print("结果: PASS（无错误，无警告）")
        sys.exit(0)


if __name__ == "__main__":
    main()
