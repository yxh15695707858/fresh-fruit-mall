#!/usr/bin/env python3
"""
Miora 组件库依赖对账（生成期，在 validate.py 与 vite build 之前运行）。

模型（整库整体安装/更新，见 docs/qte-remote-component-tech-spec.md §4）：
  组件库 miora-spell 是**一个整包**，story.json 用 `qte.version` 传入整库版本，
  节点按 `component.key`（兼容 `name`）引用组件。组件目录（合法组件名 + 适配器 entry + propsSchema）
  由**宿主自维护**（references/qte-registry.json，因 miora-spell 为源码分发、无 manifest.json）。
  非 QTE 引用位于 config.components，各使用位置的 version 必须一致，并与顶层 qte.version 一致；
  无顶层版本时，非 QTE 版本须满足各 QTE 引用的兼容下限。非 QTE 依赖必须真实安装，失败即阻断。

流程：
  1. 解析 story.json：收集 QTE 和 config.components 引用，检查整库版本约束
  2. 读沙箱已装 node_modules/<lib>/package.json 的 version
  3. 已装缺失 / 不满足整库版本 → 有界更新（pnpm add <lib>@<version>，超时 + package.json/pnpm-lock.yaml 回滚）
  4. 非 QTE 依赖仍不满足 → 阻断；仅 QTE 依赖不满足或组件未登记 → 对应节点降级（degraded=true）
  5. 刷新本地 CCR 快照 public/story/qte-registry.json（libVersion=已装版本 + 目录 components）
  6. codegen src/engine/qte/registry.generated.ts（name → 宿主适配器 ./adapters/<entry> 静态 import）
  7. 输出报告；非 QTE 失败始终退出非 0，QTE 降级只在 --strict 时退出非 0

用法:
    python3 reconcile_qte.py <frontend_dir> [--story <path>] [--strict] [--timeout 60] [--retries 0] [--lib <pkg>]
默认 story = <frontend_dir>/public/story/story.json

对账绝不发生在播放期；播放期零 npm。
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

LIB = "miora-spell"
CATALOG_PATH = Path(__file__).resolve().parent.parent / "references" / "qte-registry.json"


# ── semver（与 validate.py 同口径，prerelease-aware：0.1.0-beta.0 < 0.1.0-beta.1）──

def _parse_semver(v):
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
    return _parse_semver(v)[0]


def _cmp_pre(a, b):
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
            c = -1 if xn else 1
        else:
            c = (x > y) - (x < y)
        if c:
            return c
    return (len(a) > len(b)) - (len(a) < len(b))


def _semver_cmp(a, b):
    an, ap = _parse_semver(a)
    bn, bp = _parse_semver(b)
    if an != bn:
        return (an > bn) - (an < bn)
    return _cmp_pre(ap, bp)


def _caret_satisfies(installed, floor):
    """caret 兼容：同兼容段（首个非零段一致）且 installed >= floor（含 prerelease 排序）。"""
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
_QTE_NODE_TYPES = {"interaction", "click", "combo", "hold", "direction"}


def _canon_qte_name(comp, node_type=None):
    cand = None
    if isinstance(comp, dict):
        cand = comp.get("key") or comp.get("name")
    if cand:
        return _QTE_ALIAS.get(cand, cand)  # 已知控件→逻辑短名；未知具名→原样返回（交 catalog 判未登记）
    return _QTE_ALIAS.get(node_type)       # 无 key/name → 靠节点 type；未知 type → None


# ── 纯函数（便于离线单测）──

def component_names(story):
    """扫 QTE 节点 → 用到的逻辑短名集合（上游 component.key / 旧 name / 节点 type 归一化）。"""
    names = set()
    for node in (story.get("nodes") or {}).values():
        if node.get("type") not in _QTE_NODE_TYPES:
            continue
        comp = node.get("component")
        if not isinstance(comp, dict):
            continue
        canon = _canon_qte_name(comp, node.get("type"))
        if canon:
            names.add(canon)
    return names


def pinned_version(story):
    """整库版本：story.qte.version 权威；缺省回退各 QTE 组件 component.version 的最大值（prerelease-aware）；都无则 None。"""
    qte = story.get("qte")
    if isinstance(qte, dict) and qte.get("version"):
        return qte["version"]
    floors = []
    for node in (story.get("nodes") or {}).values():
        if node.get("type") not in _QTE_NODE_TYPES:
            continue
        comp = node.get("component")
        if isinstance(comp, dict) and isinstance(comp.get("version"), str):
            floors.append(comp["version"])
    if not floors:
        return None
    best = floors[0]
    for f in floors[1:]:
        if _semver_cmp(f, best) > 0:
            best = f
    return best


def unsatisfied(names, catalog, installed, pinned):
    """无法满足的组件名集合。整库拉不到 → 全部；否则仅「目录里没有的组件名」。"""
    lib_ok = installed is not None and (not pinned or _caret_satisfies(installed, pinned))
    if not lib_ok:
        return set(names)
    comps = (catalog or {}).get("components") or {}
    return {n for n in names if n not in comps}


def apply_degradations(story, names):
    """给无法满足的节点 component 标 degraded=true（按归一化逻辑短名匹配）。返回标记数。"""
    n = 0
    for node in (story.get("nodes") or {}).values():
        comp = node.get("component")
        if not isinstance(comp, dict):
            continue
        if _canon_qte_name(comp, node.get("type")) in names:
            comp["degraded"] = True
            n += 1
    return n


def codegen_registry(catalog, available=True):
    """依宿主组件目录生成 registry.generated.ts：name → 宿主适配器 ./adapters/<entry>（静态 import，vite 才能切 chunk）。
    available=False（整库不可用）→ 空注册表，运行时全走 FallbackQte。"""
    comps = (catalog or {}).get("components") or {}
    lines = [
        'import type { QteModule } from "./contract";',
        "",
        "// AUTO-GENERATED by scripts/reconcile_qte.py —— 请勿手改。",
        "// name → 宿主适配器（把 QteContext 映射到 miora-spell 的 Game*Control）。",
        "export const QTE_REGISTRY: Record<string, () => Promise<QteModule>> = {",
    ]
    if available:
        for name in sorted(comps):
            entry = comps[name].get("entry", name)
            lines.append(f'  {json.dumps(name)}: () => import("./adapters/{entry}"),')
    lines.append("};")
    lines.append("")
    return "\n".join(lines)


def read_installed_version(frontend_dir):
    """已装整库版本：node_modules/<lib>/package.json 的 version。未装 → None。"""
    p = Path(frontend_dir) / "node_modules" / LIB / "package.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("version")
    except Exception:
        return None


def read_declared_version(frontend_dir):
    """package.json 里声明的整库版本（去掉 ^ ~ 等范围前缀）。node_modules 尚未安装时用它兜底，
    避免"生成期早于 npm install"把全部 QTE 误降级（构建时会按声明装成它）。"""
    p = Path(frontend_dir) / "package.json"
    if not p.exists():
        return None
    try:
        pkg = json.loads(p.read_text(encoding="utf-8"))
        for field in ("dependencies", "devDependencies", "optionalDependencies"):
            spec = (pkg.get(field) or {}).get(LIB)
            if spec:
                return str(spec).lstrip("^~>=< ").strip() or None
    except Exception:
        return None
    return None


def load_catalog():
    try:
        return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


# ── 有界更新（真实 pnpm；单测用注入的 fake updater 替换）──

_ROLLBACK_FILES = ("package.json", "pnpm-lock.yaml")


def _tail(text, lines=20):
    if isinstance(text, bytes):
        text = text.decode("utf-8", "replace")
    return "\n".join((text or "").strip().splitlines()[-lines:])


def default_pnpm_updater(frontend_dir, target, timeout, retries):
    """备份 package.json/pnpm-lock.yaml → pnpm add <lib>@target → 失败回滚。返回 (是否成功, 失败详情)。"""
    fe = Path(frontend_dir)
    backups = {}
    for name in _ROLLBACK_FILES:
        src = fe / name
        if src.exists():
            bak = fe / f"{name}.reconcile-bak"
            shutil.copy2(src, bak)
            backups[src] = bak
    env = {**os.environ, "CI": "true"}
    detail = ""
    try:
        for i in range(retries + 1):
            try:
                subprocess.run(
                    ["pnpm", "add", f"{LIB}@{target}", "--save-exact", "--prefer-offline"],
                    cwd=str(fe), timeout=timeout, env=env, stdin=subprocess.DEVNULL,
                    capture_output=True, text=True, check=True,
                )
                return True, ""
            except subprocess.TimeoutExpired as e:
                detail = f"pnpm add 超时（{timeout}s）\n{_tail(e.stderr)}".strip()
            except subprocess.CalledProcessError as e:
                detail = f"pnpm add 退出码 {e.returncode}\n{_tail(e.stderr or e.stdout)}".strip()
            except FileNotFoundError:
                detail = "未找到 pnpm 可执行文件"
                break
            if i < retries:
                time.sleep(0.3 * (3 ** i))
        for src, bak in backups.items():
            shutil.copy2(bak, src)
        return False, detail
    finally:
        for bak in backups.values():
            bak.unlink(missing_ok=True)


# ── 主流程 ──

def reconcile(frontend_dir, story_path, *, updater=default_pnpm_updater, catalog=None,
              strict=False, timeout=60, retries=0):
    fe = Path(frontend_dir)
    story = json.loads(Path(story_path).read_text(encoding="utf-8"))
    names = component_names(story)
    pinned = pinned_version(story)
    ui_components = (story.get("config") or {}).get("components") or {}
    catalog = catalog if catalog is not None else load_catalog()
    installed = read_installed_version(frontend_dir)
    declared = read_declared_version(frontend_dir)
    effective = installed if ui_components else installed or declared

    report = {"names": sorted(names), "pinned": pinned, "installed": installed,
              "declared": declared, "updated": False, "alreadyOk": False, "degraded": []}

    if ui_components:
        report["uiComponents"] = sorted(ui_components)
        versions = {ref.get("version") for ref in ui_components.values()}
        if len(versions) != 1 or not next(iter(versions)):
            report["failed"] = True
            report["error"] = {
                "code": "COMPONENT_VERSION_CONFLICT",
                "message": "config.components 各使用位置必须指定相同的组件库版本",
                "versions": {slot: ref.get("version") for slot, ref in ui_components.items()},
            }
            return report
        ui_version = next(iter(versions))
        top_version = (story.get("qte") or {}).get("version")
        if top_version and top_version != ui_version:
            report["failed"] = True
            report["error"] = {
                "code": "COMPONENT_VERSION_CONFLICT",
                "message": f"config.components 版本 {ui_version} 与 qte.version {top_version} 不一致",
            }
            return report
        if not top_version:
            for node_id, node in (story.get("nodes") or {}).items():
                if node.get("type") not in _QTE_NODE_TYPES:
                    continue
                floor = (node.get("component") or {}).get("version")
                if floor and not _caret_satisfies(ui_version, floor):
                    report["failed"] = True
                    report["error"] = {
                        "code": "COMPONENT_QTE_VERSION_CONFLICT",
                        "message": f"config.components 版本 {ui_version} 不满足 QTE 节点 {node_id} 的兼容下限 {floor}",
                    }
                    return report
        pinned = ui_version
        report["pinned"] = pinned

    need_update = bool(names or ui_components) and bool(pinned) and (
        effective is None or not _caret_satisfies(effective, pinned))
    if need_update:
        report["target"] = pinned
        result = updater(frontend_dir, pinned, timeout, retries)
        ok, detail = result if isinstance(result, tuple) else (bool(result), "")
        report["updated"] = ok
        if detail:
            report["updateError"] = detail
        if ok:
            installed = read_installed_version(frontend_dir)
            effective = installed if ui_components else installed or declared
            report["installed"] = installed

    lib_ok = effective is not None and (not pinned or _caret_satisfies(effective, pinned))
    if ui_components and not lib_ok:
        report["failed"] = True
        report["error"] = {
            "code": "COMPONENT_INSTALL_FAILED",
            "message": f"{LIB}@{pinned} 未成功安装，非 QTE 组件不能降级或替换为本地实现",
        }
        return report
    if (names or ui_components) and not need_update and lib_ok:
        report["alreadyOk"] = True

    bad = unsatisfied(names, catalog, effective, pinned) if names else set()
    if bad:
        report["degraded"] = sorted(bad)
        if strict:
            report["strictFail"] = True
            return report
        apply_degradations(story, bad)
        Path(story_path).write_text(json.dumps(story, ensure_ascii=False, indent=2), encoding="utf-8")

    # 刷新快照 + codegen（有生效版本才写；否则注册表为空 → 全兜底）
    if effective is not None and catalog is not None:
        snap = fe / "public" / "story" / "qte-registry.json"
        snap.parent.mkdir(parents=True, exist_ok=True)
        snapshot = {
            "schemaVersion": catalog.get("schemaVersion", 2),
            "lib": LIB,
            "libVersion": effective,
            "components": catalog.get("components", {}),
        }
        snap.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")

        gen = fe / "src" / "engine" / "qte" / "registry.generated.ts"
        gen.parent.mkdir(parents=True, exist_ok=True)
        gen.write_text(codegen_registry(catalog, available=lib_ok), encoding="utf-8")
        report["snapshot"] = str(snap)
        report["registry"] = str(gen)

    return report


def main():
    global LIB
    parser = argparse.ArgumentParser(description="Miora 组件库依赖对账（生成期，整库整体安装/更新）")
    parser.add_argument("frontend_dir", help="前端目录（含 node_modules / public / src）")
    parser.add_argument("--story", help="story.json 路径，默认 <frontend_dir>/public/story/story.json")
    parser.add_argument("--strict", action="store_true", help="QTE 无法满足时退出非 0（默认降级；非 QTE 安装失败始终阻断）")
    parser.add_argument("--timeout", type=int, default=60, help="单次 pnpm 更新超时(s)")
    parser.add_argument("--retries", type=int, default=0, help="更新重试次数")
    parser.add_argument("--lib", default=LIB, help=f"组件库包名（默认 {LIB}）")
    args = parser.parse_args()

    LIB = args.lib

    story_path = args.story or str(Path(args.frontend_dir) / "public" / "story" / "story.json")
    if not Path(story_path).exists():
        print(f"FAIL  story.json 未找到: {story_path}")
        sys.exit(1)

    report = reconcile(args.frontend_dir, story_path, strict=args.strict,
                       timeout=args.timeout, retries=args.retries)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    sys.exit(2 if report.get("strictFail") or report.get("failed") else 0)


if __name__ == "__main__":
    main()
