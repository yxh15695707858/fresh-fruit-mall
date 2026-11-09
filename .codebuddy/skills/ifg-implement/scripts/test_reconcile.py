#!/usr/bin/env python3

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


RECONCILE_PATH = Path(__file__).resolve().parent / "reconcile_qte.py"
spec = importlib.util.spec_from_file_location("ifg_reconcile", RECONCILE_PATH)
rc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rc)

LIB = rc.LIB  # miora-spell


def catalog(components=None):
    return {
        "schemaVersion": 2, "lib": LIB, "libVersion": "0.1.0-beta.0",
        "components": components if components is not None else {
            "click": {"entry": "click", "propsSchema": {"type": "object"}, "capabilities": {"canFail": True}},
            "hold": {"entry": "hold", "propsSchema": {"type": "object"}, "capabilities": {"canFail": True}},
        },
    }


def story_with(component, qte_version="0.1.0-beta.0"):
    story = {
        "meta": {"title": "t", "version": "1.0.0", "start": "s"},
        "nodes": {
            "s": {"type": "start", "text": "a", "next": "q"},
            "q": {"type": "interaction", "text": "长按", "component": component,
                  "onSuccess": "w", "onFail": "l"},
            "w": {"type": "ending", "text": "w", "ending_type": "good"},
            "l": {"type": "ending", "text": "l", "ending_type": "bad"},
        },
    }
    if qte_version is not None:
        story["qte"] = {"lib": LIB, "version": qte_version}
    return story


def make_frontend(tmp, installed_version, story):
    """搭最小 frontend：node_modules/<lib>/package.json 写已装版本，public/story 放 story.json。"""
    fe = Path(tmp)
    pkg_dir = fe / "node_modules" / LIB
    pkg_dir.mkdir(parents=True)
    if installed_version is not None:
        (pkg_dir / "package.json").write_text(
            json.dumps({"name": LIB, "version": installed_version}), encoding="utf-8")
    (fe / "public" / "story").mkdir(parents=True)
    story_path = fe / "public" / "story" / "story.json"
    story_path.write_text(json.dumps(story, ensure_ascii=False), encoding="utf-8")
    return str(fe), str(story_path)


def with_ui(story=None, version="0.1.0-beta.1"):
    story = story if story is not None else {"nodes": {}}
    story["config"] = {"theme": {"game": "default"}, "components": {
        "titleMenu": {"key": "GameMenu", "version": version, "props": {"place": "right"}},
        "titleMenuButton": {"key": "GameMenuButton", "version": version, "props": {"variant": "cover"}},
        "choiceGroup": {"key": "GameChoiceGroup", "version": version},
        "choiceButton": {"key": "GameMenuButton", "version": version},
        "loadingProgress": {"key": "GameProgressBar", "version": version, "props": {"variant": "loading"}},
        "storyTree": {"key": "GameLevelGroup", "version": version},
        "storyTreeProgress": {"key": "GameProgressInfo", "version": version},
        "actionButton": {"key": "GameMenuButton", "version": version, "props": {"variant": "secondary"}},
        "endingCard": {"key": "GameEndingCard", "version": version, "props": {"style": {"width": "100%"}}},
        "screen": {"key": "GameScreen", "version": version, "props": {"blur": True}},
        "text": {"key": "GameText", "version": version, "props": {"size": "lg", "theme": "ancient"}},
    }}
    return story


class PureFnTest(unittest.TestCase):
    def test_component_names_collects_used(self):
        story = {"nodes": {
            "a": {"type": "interaction", "component": {"name": "click"}},
            "b": {"type": "interaction", "component": {"name": "hold"}},
            "c": {"type": "scene"},
        }}
        self.assertEqual(rc.component_names(story), {"click", "hold"})

    def test_component_names_from_upstream_keys(self):
        # 上游终态：node.type=click/combo/hold/direction + component.key=Game*Control → 归一化逻辑短名
        story = {"nodes": {
            "a": {"type": "click", "component": {"key": "GameClickControl"}},
            "b": {"type": "direction", "component": {"key": "GameSlideControl"}},
            "c": {"type": "hold", "component": {"key": "GameHoldControl"}},
            "d": {"type": "combo", "component": {"key": "GameComboControl"}},
        }}
        self.assertEqual(rc.component_names(story), {"click", "slide", "hold", "combo"})

    def test_caret_prerelease_ordering(self):
        self.assertTrue(rc._caret_satisfies("0.1.0-beta.1", "0.1.0-beta.0"))
        self.assertFalse(rc._caret_satisfies("0.1.0-beta.0", "0.1.0-beta.1"))
        self.assertTrue(rc._caret_satisfies("0.1.0", "0.1.0-beta.9"))  # 正式版 > 任何 prerelease

    def test_pinned_version_from_qte_block(self):
        story = story_with({"name": "hold"}, qte_version="0.1.0-beta.0")
        self.assertEqual(rc.pinned_version(story), "0.1.0-beta.0")

    def test_pinned_version_falls_back_to_component_version(self):
        story = story_with({"name": "hold", "version": "0.2.0"}, qte_version=None)
        self.assertEqual(rc.pinned_version(story), "0.2.0")

    def test_unsatisfied_lib_missing_degrades_all(self):
        self.assertEqual(
            rc.unsatisfied({"click", "hold"}, catalog(), installed=None, pinned="0.1.0-beta.0"),
            {"click", "hold"})

    def test_unsatisfied_stale_lib_degrades_all(self):
        # 已装 0.0.9 不满足 0.1.0 → 整库不可用 → 全降级
        self.assertEqual(
            rc.unsatisfied({"click"}, catalog(), installed="0.0.9", pinned="0.1.0"),
            {"click"})

    def test_unsatisfied_unknown_name_only(self):
        # 整库满足，但 story 用了目录里没有的组件名
        self.assertEqual(
            rc.unsatisfied({"click", "ghost"}, catalog(), installed="0.1.0-beta.0", pinned="0.1.0-beta.0"),
            {"ghost"})

    def test_unsatisfied_all_ok_empty(self):
        self.assertEqual(
            rc.unsatisfied({"click", "hold"}, catalog(), installed="0.1.0-beta.0", pinned="0.1.0-beta.0"),
            set())

    def test_codegen_lists_adapters(self):
        ts = rc.codegen_registry(catalog(), available=True)
        self.assertIn('"click": () => import("./adapters/click")', ts)
        self.assertIn('"hold": () => import("./adapters/hold")', ts)

    def test_codegen_empty_when_unavailable(self):
        ts = rc.codegen_registry(catalog(), available=False)
        self.assertNotIn("import(", ts)
        self.assertIn("QTE_REGISTRY", ts)


class ReconcileFlowTest(unittest.TestCase):
    def test_already_ok_no_update_no_degrade(self):
        story = story_with({"name": "hold", "props": {}})
        with tempfile.TemporaryDirectory() as tmp:
            fe, sp = make_frontend(tmp, "0.1.0-beta.0", story)
            calls = []
            report = rc.reconcile(fe, sp, catalog=catalog(),
                                  updater=lambda *a: calls.append(a) or True)
            self.assertTrue(report["alreadyOk"])
            self.assertFalse(report["updated"])
            self.assertEqual(report["degraded"], [])
            self.assertEqual(calls, [])  # 未触发更新
            self.assertTrue((Path(fe) / "public/story/qte-registry.json").exists())
            gen = (Path(fe) / "src/engine/qte/registry.generated.ts").read_text()
            self.assertIn('import("./adapters/hold")', gen)

    def test_stale_then_update_success(self):
        story = story_with({"name": "hold", "props": {}}, qte_version="0.1.0-beta.0")
        with tempfile.TemporaryDirectory() as tmp:
            fe, sp = make_frontend(tmp, "0.0.9", story)  # 旧版

            def fake_update(frontend_dir, target, timeout, retries):
                p = Path(frontend_dir) / "node_modules" / LIB / "package.json"
                p.write_text(json.dumps({"name": LIB, "version": target}), encoding="utf-8")
                return True

            report = rc.reconcile(fe, sp, catalog=catalog(), updater=fake_update)
            self.assertEqual(report.get("target"), "0.1.0-beta.0")
            self.assertTrue(report["updated"])
            self.assertEqual(report["degraded"], [])
            saved = json.loads(Path(sp).read_text(encoding="utf-8"))
            self.assertNotIn("degraded", saved["nodes"]["q"]["component"])

    def test_stale_then_update_fail_degrades_and_completes(self):
        story = story_with({"name": "hold", "props": {}}, qte_version="0.2.0")
        with tempfile.TemporaryDirectory() as tmp:
            fe, sp = make_frontend(tmp, "0.1.0-beta.0", story)
            report = rc.reconcile(fe, sp, catalog=catalog(), updater=lambda *a: False)
            self.assertFalse(report["updated"])
            self.assertEqual(report["degraded"], ["hold"])
            saved = json.loads(Path(sp).read_text(encoding="utf-8"))
            self.assertTrue(saved["nodes"]["q"]["component"]["degraded"])
            self.assertTrue((Path(fe) / "public/story/qte-registry.json").exists())

    def test_unknown_component_degrades_that_node(self):
        story = story_with({"name": "ghost", "props": {}})
        with tempfile.TemporaryDirectory() as tmp:
            fe, sp = make_frontend(tmp, "0.1.0-beta.0", story)
            report = rc.reconcile(fe, sp, catalog=catalog(), updater=lambda *a: True)
            self.assertIn("ghost", report["degraded"])
            saved = json.loads(Path(sp).read_text(encoding="utf-8"))
            self.assertTrue(saved["nodes"]["q"]["component"]["degraded"])

    def test_unknown_component_strict_fails(self):
        story = story_with({"name": "ghost", "props": {}})
        with tempfile.TemporaryDirectory() as tmp:
            fe, sp = make_frontend(tmp, "0.1.0-beta.0", story)
            report = rc.reconcile(fe, sp, catalog=catalog(), updater=lambda *a: True, strict=True)
            self.assertTrue(report.get("strictFail"))
            self.assertIn("ghost", report["degraded"])

    def test_lib_missing_skips_snapshot(self):
        story = story_with({"name": "hold", "props": {}})
        with tempfile.TemporaryDirectory() as tmp:
            fe, sp = make_frontend(tmp, None, story)  # 未装且更新失败
            report = rc.reconcile(fe, sp, catalog=catalog(), updater=lambda *a: False)
            self.assertIn("hold", report["degraded"])
            self.assertNotIn("snapshot", report)  # 无已装版本 → 不写快照

    def test_snapshot_uses_installed_version(self):
        story = story_with({"name": "click", "props": {}})
        with tempfile.TemporaryDirectory() as tmp:
            fe, sp = make_frontend(tmp, "0.1.0-beta.0", story)
            rc.reconcile(fe, sp, catalog=catalog(), updater=lambda *a: True)
            snap = json.loads((Path(fe) / "public/story/qte-registry.json").read_text(encoding="utf-8"))
            self.assertEqual(snap["libVersion"], "0.1.0-beta.0")
            self.assertEqual(snap["lib"], LIB)
            self.assertIn("click", snap["components"])

    def test_declared_version_fallback_when_node_modules_absent(self):
        # 生成期早于 npm install：node_modules 未装，但 package.json 声明了满足版本
        # → 不降级、不触发 npm i、快照用声明版本（构建时会装成它）
        story = story_with({"name": "hold", "props": {}}, qte_version="0.1.0-beta.1")
        with tempfile.TemporaryDirectory() as tmp:
            fe, sp = make_frontend(tmp, None, story)  # 不写 node_modules/<lib>/package.json
            (Path(fe) / "package.json").write_text(
                json.dumps({"dependencies": {LIB: "^0.1.0-beta.1"}}), encoding="utf-8")
            calls = []
            report = rc.reconcile(fe, sp, catalog=catalog(),
                                  updater=lambda *a: calls.append(a) or True)
            self.assertEqual(calls, [])              # 未触发 npm i
            self.assertEqual(report["degraded"], [])  # 未降级
            self.assertEqual(report["declared"], "0.1.0-beta.1")
            snap = json.loads((Path(fe) / "public/story/qte-registry.json").read_text(encoding="utf-8"))
            self.assertEqual(snap["libVersion"], "0.1.0-beta.1")

    def test_prerelease_bump_triggers_update(self):
        # 已装 beta.0，上游 story 组件要求 beta.1（component.version，无顶层 qte）→ prerelease-aware → 需整库更新
        story = story_with({"key": "GameHoldControl", "version": "0.1.0-beta.1", "props": {}}, qte_version=None)
        story["nodes"]["q"]["type"] = "hold"
        with tempfile.TemporaryDirectory() as tmp:
            fe, sp = make_frontend(tmp, "0.1.0-beta.0", story)
            calls = []

            def upd(fd, target, timeout, retries):
                calls.append(target)
                p = Path(fd) / "node_modules" / LIB / "package.json"
                p.write_text(json.dumps({"name": LIB, "version": target}), encoding="utf-8")
                return True

            report = rc.reconcile(fe, sp, catalog=catalog(), updater=upd)
            self.assertEqual(report.get("target"), "0.1.0-beta.1")
            self.assertTrue(report["updated"])
            self.assertEqual(calls, ["0.1.0-beta.1"])
            self.assertEqual(report["degraded"], [])


class UiReconcileFlowTest(unittest.TestCase):
    def test_ui_without_qte_requires_real_install_despite_declared_version(self):
        story = with_ui()
        with tempfile.TemporaryDirectory() as tmp:
            fe, sp = make_frontend(tmp, None, story)
            (Path(fe) / "package.json").write_text(json.dumps({
                "dependencies": {LIB: "0.1.0-beta.1"},
            }), encoding="utf-8")
            calls = []

            def updater(frontend_dir, target, timeout, retries):
                calls.append((target, timeout, retries))
                (Path(frontend_dir) / "node_modules" / LIB / "package.json").write_text(
                    json.dumps({"name": LIB, "version": target}), encoding="utf-8")
                return True

            report = rc.reconcile(fe, sp, catalog=catalog(), updater=updater, timeout=5, retries=1)
            self.assertEqual(calls, [("0.1.0-beta.1", 5, 1)])
            self.assertEqual(report["installed"], "0.1.0-beta.1")
            self.assertEqual(report["pinned"], "0.1.0-beta.1")
            self.assertEqual(report["names"], [])
            self.assertEqual(report["uiComponents"], sorted(story["config"]["components"]))
            self.assertEqual(len(report["uiComponents"]), 11)
            self.assertTrue(report["updated"])
            self.assertNotIn("failed", report)

    def test_compatible_installed_ui_version_skips_update(self):
        with tempfile.TemporaryDirectory() as tmp:
            fe, sp = make_frontend(tmp, "0.1.0-beta.2", with_ui())
            calls = []
            report = rc.reconcile(fe, sp, catalog=catalog(), updater=lambda *a: calls.append(a))
            self.assertEqual(calls, [])
            self.assertTrue(report["alreadyOk"])
            self.assertFalse(report["updated"])
            self.assertNotIn("failed", report)

    def test_failed_or_unverified_ui_install_preserves_story_and_registries(self):
        story = with_ui(story_with({"key": "GameHoldControl", "version": "0.1.0-beta.1"},
                                  qte_version="0.1.0-beta.1"))
        for updater_result in (False, True):
            with self.subTest(updater_result=updater_result), tempfile.TemporaryDirectory() as tmp:
                fe, sp = make_frontend(tmp, "0.1.0-beta.0", story)
                snapshot = Path(fe) / "public/story/qte-registry.json"
                snapshot.write_text(json.dumps(catalog()), encoding="utf-8")
                registry = Path(fe) / "src/engine/qte/registry.generated.ts"
                registry.parent.mkdir(parents=True)
                registry.write_text(rc.codegen_registry(catalog()), encoding="utf-8")
                before = {p: p.read_bytes() for p in (Path(sp), snapshot, registry)}
                calls = []
                report = rc.reconcile(fe, sp, catalog=catalog(),
                                      updater=lambda *a: calls.append(a) or updater_result)
                self.assertEqual(len(calls), 1)
                self.assertTrue(report["failed"])
                self.assertEqual(report["error"]["code"], "COMPONENT_INSTALL_FAILED")
                self.assertEqual(report["degraded"], [])
                self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_ui_version_conflict_rejected_before_update(self):
        for slot in ("endingCard", "storyTreeProgress", "screen", "text"):
            with self.subTest(slot=slot), tempfile.TemporaryDirectory() as tmp:
                story = with_ui()
                story["config"]["components"][slot]["version"] = "0.2.0"
                fe, sp = make_frontend(tmp, None, story)
                calls = []
                report = rc.reconcile(fe, sp, catalog=catalog(), updater=lambda *a: calls.append(a))
                self.assertEqual(calls, [])
                self.assertTrue(report["failed"])
                self.assertEqual(report["error"]["code"], "COMPONENT_VERSION_CONFLICT")
                self.assertEqual(report["error"]["versions"][slot], "0.2.0")
                self.assertNotIn("registry", report)

    def test_ui_progress_bar_reference_keeps_version_reconciliation(self):
        story = with_ui()
        story["config"]["components"]["storyTreeProgress"]["key"] = "GameProgressBar"
        with tempfile.TemporaryDirectory() as tmp:
            fe, sp = make_frontend(tmp, "0.1.0-beta.1", story)
            before = Path(sp).read_bytes()
            report = rc.reconcile(fe, sp, catalog=catalog())
            self.assertTrue(report["alreadyOk"])
            self.assertIn("storyTreeProgress", report["uiComponents"])
            self.assertEqual(Path(sp).read_bytes(), before)

    def test_top_level_version_conflict_rejected_and_cli_exits_nonzero(self):
        story = with_ui(story_with({"name": "hold"}, qte_version="0.2.0"))
        with tempfile.TemporaryDirectory() as tmp:
            fe, sp = make_frontend(tmp, None, story)
            calls = []
            report = rc.reconcile(fe, sp, catalog=catalog(), updater=lambda *a: calls.append(a))
            self.assertEqual(calls, [])
            self.assertEqual(report["error"]["code"], "COMPONENT_VERSION_CONFLICT")
            result = subprocess.run([sys.executable, str(RECONCILE_PATH), fe],
                                    capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads(result.stdout)["error"]["code"], "COMPONENT_VERSION_CONFLICT")

    def test_ui_version_must_satisfy_qte_floor_without_top_level_version(self):
        for qte_version in ("0.1.0-beta.2", "0.2.0"):
            with self.subTest(qte_version=qte_version), tempfile.TemporaryDirectory() as tmp:
                story = with_ui(story_with({"key": "GameHoldControl", "version": qte_version},
                                          qte_version=None))
                fe, sp = make_frontend(tmp, None, story)
                calls = []
                report = rc.reconcile(fe, sp, catalog=catalog(), updater=lambda *a: calls.append(a))
                self.assertEqual(calls, [])
                self.assertTrue(report["failed"])
                self.assertEqual(report["error"]["code"], "COMPONENT_QTE_VERSION_CONFLICT")

    def test_ui_version_accepts_compatible_qte_floor(self):
        story = with_ui(story_with({"key": "GameHoldControl", "version": "0.1.0-beta.0"},
                                  qte_version=None))
        with tempfile.TemporaryDirectory() as tmp:
            fe, sp = make_frontend(tmp, "0.1.0-beta.1", story)
            report = rc.reconcile(fe, sp, catalog=catalog())
            self.assertTrue(report["alreadyOk"])
            self.assertEqual(report["pinned"], "0.1.0-beta.1")
            self.assertEqual(report["degraded"], [])
            self.assertNotIn("failed", report)


class PnpmUpdaterTest(unittest.TestCase):
    def setUp(self):
        self._orig_run = rc.subprocess.run
        self.calls = []

    def tearDown(self):
        rc.subprocess.run = self._orig_run

    def _frontend(self, tmp):
        fe = Path(tmp)
        (fe / "package.json").write_text('{"dependencies":{}}', encoding="utf-8")
        (fe / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
        return fe

    def test_uses_pnpm_add_exact_noninteractive(self):
        def fake_run(cmd, **kw):
            self.calls.append((cmd, kw))
            return subprocess.CompletedProcess(cmd, 0, "", "")

        rc.subprocess.run = fake_run
        with tempfile.TemporaryDirectory() as tmp:
            fe = self._frontend(tmp)
            self.assertEqual(rc.default_pnpm_updater(str(fe), "0.0.1-beta.2", 120, 0), (True, ""))
            cmd, kw = self.calls[0]
            self.assertEqual(cmd[:3], ["pnpm", "add", f"{LIB}@0.0.1-beta.2"])
            self.assertIn("--save-exact", cmd)
            self.assertEqual(kw["env"]["CI"], "true")
            self.assertEqual(kw["cwd"], str(fe))
            self.assertEqual(kw["timeout"], 120)
            self.assertEqual(sorted(p.name for p in fe.iterdir()), ["package.json", "pnpm-lock.yaml"])

    def test_failure_rolls_back_manifest_and_lock_without_retry(self):
        def fake_run(cmd, **kw):
            self.calls.append(cmd)
            fe = Path(kw["cwd"])
            (fe / "package.json").write_text("broken", encoding="utf-8")
            (fe / "pnpm-lock.yaml").write_text("broken", encoding="utf-8")
            raise subprocess.CalledProcessError(1, cmd, output="", stderr="ERR_PNPM_FETCH_404 not found")

        rc.subprocess.run = fake_run
        with tempfile.TemporaryDirectory() as tmp:
            fe = self._frontend(tmp)
            before = {p.name: p.read_bytes() for p in fe.iterdir()}
            ok, detail = rc.default_pnpm_updater(str(fe), "9.9.9", 120, 0)
            self.assertFalse(ok)
            self.assertIn("ERR_PNPM_FETCH_404", detail)
            self.assertEqual(len(self.calls), 1)
            self.assertEqual({p.name: p.read_bytes() for p in fe.iterdir()}, before)

    def test_timeout_reports_detail(self):
        def fake_run(cmd, **kw):
            raise subprocess.TimeoutExpired(cmd, kw["timeout"], stderr=b"resolving...")

        rc.subprocess.run = fake_run
        with tempfile.TemporaryDirectory() as tmp:
            ok, detail = rc.default_pnpm_updater(str(self._frontend(tmp)), "0.0.1", 5, 0)
            self.assertFalse(ok)
            self.assertIn("超时", detail)
            self.assertIn("resolving...", detail)

    def test_reconcile_surfaces_update_error(self):
        story = with_ui()
        with tempfile.TemporaryDirectory() as tmp:
            fe, sp = make_frontend(tmp, None, story)
            report = rc.reconcile(fe, sp, catalog=catalog(),
                                  updater=lambda *a: (False, "pnpm add 退出码 1"))
            self.assertEqual(report["error"]["code"], "COMPONENT_INSTALL_FAILED")
            self.assertEqual(report["updateError"], "pnpm add 退出码 1")


if __name__ == "__main__":
    unittest.main()
