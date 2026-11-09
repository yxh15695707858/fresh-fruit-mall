#!/usr/bin/env python3

import contextlib
import importlib.util
import io
import json
import re
import subprocess
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = SKILL_ROOT / "scripts" / "validate.py"
SCHEMA_PATH = SKILL_ROOT / "references" / "story.schema.json"
REFERENCE_PATH = SKILL_ROOT / "references" / "story-schema-reference.md"
GOLDEN_PATH = SKILL_ROOT / "references" / "examples" / "golden" / "public" / "story" / "story.json"
REGISTRY_PATH = SKILL_ROOT / "references" / "qte-registry.json"

spec = importlib.util.spec_from_file_location("ifg_validate", VALIDATOR_PATH)
validator_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator_module)


def base_story():
    return {
        "meta": {"title": "测试", "version": "1.0.0", "start": "start"},
        "nodes": {
            "start": {"type": "start", "text": "开始", "next": "ending"},
            "ending": {"type": "ending", "text": "结束", "ending_type": "normal"},
        },
    }


def qte_story():
    return {
        "meta": {"title": "QTE", "version": "1.0.0", "start": "start"},
        "nodes": {
            "start": {"type": "start", "text": "开始", "next": "qte"},
            "qte": {
                "type": "interaction", "interaction": "swipe", "text": "滑动",
                "direction": "up", "timeout": 3000,
                "onSuccess": "win", "onFail": "lose",
            },
            "win": {"type": "ending", "text": "赢", "ending_type": "good"},
            "lose": {"type": "ending", "text": "输", "ending_type": "bad"},
        },
    }


def qte_component_story():
    return {
        "meta": {"title": "QTE-C", "version": "1.0.0", "start": "start"},
        "qte": {"lib": "miora-spell", "version": "0.0.1-beta.1"},
        "nodes": {
            "start": {"type": "start", "text": "开始", "next": "qte"},
            "qte": {
                "type": "interaction", "text": "长按蓄力",
                "component": {
                    "name": "hold",
                    "props": {"fillSeconds": 1.5, "title": "别松手，抓住绳索！", "total": 5},
                },
                "rect": {"x": 0.3, "y": 0.5, "w": 0.4, "h": 0.4},
                "appearAt": 2.0, "disappearAt": 7.0,
                "clipDuration": 10000, "timeout": 5000,
                "onSuccess": "win", "onFail": "lose",
            },
            "win": {"type": "ending", "text": "赢", "ending_type": "good"},
            "lose": {"type": "ending", "text": "输", "ending_type": "bad"},
        },
    }


def qte_registry():
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def semantic_errors(data, registry=None):
    validator = validator_module.StoryValidator(data, registry)
    with contextlib.redirect_stdout(io.StringIO()):
        validator.run_all()
    return validator.errors


class SchemaContractTest(unittest.TestCase):
    def assert_schema_valid(self, data):
        errors = validator_module.validate_schema_contract(data)
        self.assertEqual([], errors)

    def assert_schema_invalid(self, data):
        errors = validator_module.validate_schema_contract(data)
        self.assertTrue(errors)

    def test_golden_story_passes_schema_and_semantic_validation(self):
        data = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
        self.assert_schema_valid(data)
        self.assertEqual(0, semantic_errors(data))

    def test_reference_complete_example_passes_validation(self):
        content = REFERENCE_PATH.read_text(encoding="utf-8")
        match = re.search(r"## 完整示例.*?```jsonc\n(.*?)\n```", content, re.S)
        self.assertIsNotNone(match)
        data = json.loads(match.group(1))
        self.assert_schema_valid(data)
        self.assertEqual(0, semantic_errors(data))

    def test_schema_valid_fx_array_passes_semantic_validation(self):
        data = base_story()
        data["nodes"]["start"]["media"] = {
            "type": "video",
            "src": "https://example.com/opening.mp4",
        }
        data["nodes"]["start"]["fx"] = ["flash"]
        self.assert_schema_valid(data)
        self.assertEqual(0, semantic_errors(data))

    def test_locale_accepts_language_tags_and_rejects_non_strings(self):
        for locale in ["en-US", "ja", "zh-TW"]:
            with self.subTest(locale=locale):
                data = base_story()
                data["config"] = {"locale": locale}
                self.assert_schema_valid(data)
        data = base_story()
        data["config"] = {"locale": 123}
        self.assert_schema_invalid(data)

    def test_schema_rejects_non_http_media_url(self):
        data = base_story()
        data["nodes"]["start"]["media"] = {
            "type": "video",
            "src": "mailto:test@example.com",
        }
        self.assert_schema_invalid(data)

    def test_schema_rejects_structural_violations(self):
        cases = []

        missing_title = base_story()
        del missing_title["meta"]["title"]
        cases.append(missing_title)

        one_choice = base_story()
        one_choice["nodes"]["start"]["next"] = "scene"
        one_choice["nodes"]["scene"] = {
            "type": "scene",
            "text": "选择",
            "choices": [{"label": "继续", "next": "ending"}],
        }
        cases.append(one_choice)

        invalid_transition = base_story()
        invalid_transition["nodes"]["start"]["transition"] = "spin"
        cases.append(invalid_transition)

        for data in cases:
            with self.subTest(data=data):
                self.assert_schema_invalid(data)

    def test_clip_duration_has_no_upper_limit(self):
        data = base_story()
        data["nodes"]["start"]["clipDuration"] = 3600
        self.assert_schema_valid(data)
        self.assertEqual(0, semantic_errors(data))

    def test_schema_encodes_node_type_constraints(self):
        cases = []

        start_without_next = base_story()
        del start_without_next["nodes"]["start"]["next"]
        cases.append(start_without_next)

        choice_without_choices = base_story()
        choice_without_choices["nodes"]["start"]["next"] = "choice"
        choice_without_choices["nodes"]["choice"] = {
            "type": "choice",
            "text": "选择",
        }
        cases.append(choice_without_choices)

        ending_with_next = base_story()
        ending_with_next["nodes"]["ending"]["next"] = "start"
        cases.append(ending_with_next)

        scene_with_next_and_choices = base_story()
        scene_with_next_and_choices["nodes"]["start"]["next"] = "scene"
        scene_with_next_and_choices["nodes"]["scene"] = {
            "type": "scene",
            "text": "冲突",
            "next": "ending",
            "choices": [
                {"label": "A", "next": "ending"},
                {"label": "B", "next": "ending"},
            ],
        }
        cases.append(scene_with_next_and_choices)

        for data in cases:
            with self.subTest(data=data):
                self.assert_schema_invalid(data)

    def test_cross_node_rules_remain_semantic_validation(self):
        data = base_story()
        data["nodes"]["start"]["next"] = "missing"
        self.assert_schema_valid(data)
        self.assertGreater(semantic_errors(data), 0)

    def test_scene_entry_without_start_node_passes(self):
        data = base_story()
        data["meta"]["start"] = "scene"
        data["nodes"]["scene"] = data["nodes"].pop("start")
        data["nodes"]["scene"]["type"] = "scene"
        self.assert_schema_valid(data)
        self.assertEqual(0, semantic_errors(data))

    def test_entry_rejects_missing_meta_start(self):
        data = base_story()
        data["nodes"]["start"]["type"] = "scene"
        del data["meta"]["start"]
        self.assert_schema_invalid(data)
        self.assertGreater(semantic_errors(data), 0)

    def test_entry_rejects_dangling_meta_start(self):
        data = base_story()
        data["nodes"]["start"]["type"] = "scene"
        data["meta"]["start"] = "missing"
        self.assert_schema_valid(data)
        self.assertGreater(semantic_errors(data), 0)

    def test_entry_allows_multiple_start_nodes(self):
        data = base_story()
        data["nodes"]["start"]["next"] = "second_start"
        data["nodes"]["second_start"] = {
            "type": "start", "text": "再次开始", "next": "ending",
        }
        self.assert_schema_valid(data)
        self.assertEqual(0, semantic_errors(data))

    def test_qte_valid_success_fail_branch_passes(self):
        data = qte_story()
        self.assert_schema_valid(data)
        self.assertEqual(0, semantic_errors(data))

    def test_qte_rejects_same_success_and_fail_branch(self):
        data = qte_story()
        data["nodes"]["qte"]["onFail"] = "win"
        self.assertGreater(semantic_errors(data), 0)

    def test_qte_rejects_dangling_branch_reference(self):
        data = qte_story()
        data["nodes"]["qte"]["onFail"] = "does_not_exist"
        self.assertGreater(semantic_errors(data), 0)

    def test_qte_rejects_missing_exit(self):
        data = qte_story()
        del data["nodes"]["qte"]["onSuccess"]
        del data["nodes"]["qte"]["onFail"]
        self.assertGreater(semantic_errors(data), 0)

    def test_qte_rejects_unpaired_branch(self):
        data = qte_story()
        del data["nodes"]["qte"]["onFail"]
        data["nodes"]["qte"]["next"] = "win"
        self.assertGreater(semantic_errors(data), 0)

    def test_qte_rejects_window_ge_duration(self):
        data = qte_story()
        data["nodes"]["qte"]["interaction"] = "hold-release"
        data["nodes"]["qte"]["duration"] = 1000
        data["nodes"]["qte"]["window"] = 2000
        self.assertGreater(semantic_errors(data), 0)

    def test_qte_rejects_timeout_out_of_range(self):
        data = qte_story()
        data["nodes"]["qte"]["timeout"] = 60000
        self.assertGreater(semantic_errors(data), 0)

    def test_qte_rejects_target_out_of_bounds(self):
        data = qte_story()
        data["nodes"]["qte"]["interaction"] = "drag"
        data["nodes"]["qte"]["target"] = {"x": 1.8, "y": 0.5}
        self.assertGreater(semantic_errors(data), 0)

    # ── sequence 媒体类型 ──

    def test_sequence_media_valid_passes_schema_and_semantic(self):
        data = base_story()
        data["nodes"]["start"]["media"] = {
            "type": "sequence",
            "items": [
                {"src": "https://cdn.example.com/shot1.mp4", "poster": "https://cdn.example.com/shot1.jpg"},
                {"src": "https://cdn.example.com/shot2.mp4", "subtitle": "https://cdn.example.com/shot2.vtt"},
            ],
        }
        self.assert_schema_valid(data)
        self.assertEqual(0, semantic_errors(data))

    def test_sequence_media_invalid_item_url_fails(self):
        data = base_story()
        data["nodes"]["start"]["media"] = {
            "type": "sequence",
            "items": [
                {"src": "https://cdn.example.com/shot1.mp4"},
                {"src": "not-a-url"},
            ],
        }
        self.assertGreater(semantic_errors(data), 0)

    def test_sequence_media_invalid_item_subtitle_url_fails(self):
        data = base_story()
        data["nodes"]["start"]["media"] = {
            "type": "sequence",
            "items": [
                {"src": "https://cdn.example.com/shot1.mp4", "subtitle": "ftp://bad/sub.vtt"},
            ],
        }
        self.assertGreater(semantic_errors(data), 0)

    def test_sequence_media_empty_items_fails_schema(self):
        data = base_story()
        data["nodes"]["start"]["media"] = {
            "type": "sequence",
            "items": [],
        }
        self.assert_schema_invalid(data)

    def test_video_and_sequence_coexist_across_nodes(self):
        data = base_story()
        data["nodes"]["start"]["next"] = "scene"
        data["nodes"]["scene"] = {"type": "scene", "text": "场景", "next": "ending"}
        data["nodes"]["start"]["media"] = {
            "type": "video",
            "src": "https://cdn.example.com/opening.mp4",
        }
        data["nodes"]["scene"]["media"] = {
            "type": "sequence",
            "items": [{"src": "https://cdn.example.com/s1.mp4"}],
        }
        self.assert_schema_valid(data)
        self.assertEqual(0, semantic_errors(data))

    # ── QTE 组件引用（方案 A）──

    def test_qte_component_valid_passes(self):
        data = qte_component_story()
        self.assert_schema_valid(data)
        self.assertEqual(0, semantic_errors(data, qte_registry()))

    def test_qte_component_missing_carrier_fails(self):
        # 既无 interaction 也无 component
        data = qte_component_story()
        del data["nodes"]["qte"]["component"]
        self.assertGreater(semantic_errors(data, qte_registry()), 0)

    def test_qte_component_unknown_name_fails(self):
        data = qte_component_story()
        data["nodes"]["qte"]["component"]["name"] = "nope"
        self.assertGreater(semantic_errors(data, qte_registry()), 0)

    def test_qte_component_floor_too_high_fails(self):
        data = qte_component_story()
        data["qte"]["version"] = "2.0.0"  # 快照 libVersion=0.0.1-beta.1
        self.assertGreater(semantic_errors(data, qte_registry()), 0)

    def test_qte_component_major_mismatch_fails(self):
        # 已装 major 高于 story 要求 → caret 不兼容（旧 >= 逻辑会误放行）
        data = qte_component_story()
        data["qte"]["version"] = "1.0.0"
        reg = {
            "schemaVersion": 2, "lib": "miora-spell", "libVersion": "2.0.0",
            "components": {"hold": {"entry": "hold", "propsSchema": {"type": "object"},
                                    "capabilities": {"canFail": True}}},
        }
        self.assertGreater(semantic_errors(data, reg), 0)

    def test_qte_component_same_major_newer_passes(self):
        # story 要 0.0.1-beta.1、快照同为 0.0.1-beta.1 → caret 兼容,通过
        data = qte_component_story()
        self.assertEqual(0, semantic_errors(data, qte_registry()))

    def test_qte_component_bad_props_fails(self):
        data = qte_component_story()
        data["nodes"]["qte"]["component"]["props"]["fillSeconds"] = 999  # 超 propsSchema max 30
        self.assertGreater(semantic_errors(data, qte_registry()), 0)

    def test_combo_accepts_original_decay_range(self):
        for decay in (0, 5, 50, 500):
            with self.subTest(decay=decay):
                data = self.upstream_story("combo", "GameComboControl", props={
                    "comboTarget": 20, "decayPerSecond": decay,
                })
                self.assert_schema_valid(data)
                self.assertEqual(0, semantic_errors(data, qte_registry()))

    def test_combo_rejects_decay_outside_original_range(self):
        for decay in (-1, 501):
            with self.subTest(decay=decay):
                data = self.upstream_story("combo", "GameComboControl", props={
                    "comboTarget": 20, "decayPerSecond": decay,
                })
                self.assertGreater(semantic_errors(data, qte_registry()), 0)

    def test_qte_component_rect_out_of_bounds_fails(self):
        data = qte_component_story()
        data["nodes"]["qte"]["rect"] = {"x": 0.8, "y": 0.2, "w": 0.5, "h": 0.2}  # x+w=1.3>1
        self.assertGreater(semantic_errors(data, qte_registry()), 0)

    def test_qte_component_appear_after_disappear_fails(self):
        data = qte_component_story()
        data["nodes"]["qte"]["appearAt"] = 8.0
        data["nodes"]["qte"]["disappearAt"] = 7.0
        self.assertGreater(semantic_errors(data, qte_registry()), 0)

    def test_qte_component_degraded_short_circuits(self):
        # degraded=true 的节点跳过 floor/props（即便 name 不存在也不报 error）
        data = qte_component_story()
        data["nodes"]["qte"]["component"]["name"] = "nope"
        data["nodes"]["qte"]["component"]["degraded"] = True
        self.assertEqual(0, semantic_errors(data, qte_registry()))

    def test_qte_component_without_registry_warns_not_errors(self):
        # 无 CCR 快照时降级为 WARN 跳过，不阻塞
        data = qte_component_story()
        self.assertEqual(0, semantic_errors(data, None))

    # ── 上游终态协议（node.type=click/…、component.key=Game*Control、库原生 props）──

    def upstream_story(self, node_type, key, version="0.0.1-beta.1", props=None):
        data = qte_component_story()
        data.pop("qte", None)  # 上游无顶层 qte 块，版本在 component.version
        q = data["nodes"]["qte"]
        q["type"] = node_type
        q["component"] = {"key": key, "version": version, "props": props or {}}
        return data

    def test_qte_upstream_key_and_type_passes(self):
        data = self.upstream_story("click", "GameClickControl",
                                   props={"label": "点击", "title": "t", "remaining": 5, "total": 5, "showProgress": True})
        self.assert_schema_valid(data)
        self.assertEqual(0, semantic_errors(data, qte_registry()))

    def test_qte_upstream_click_entry_without_start_node_passes(self):
        data = {
            "meta": {"title": "QTE", "version": "1.0.0", "start": "4.4"},
            "nodes": {
                "4.4": {
                    "type": "click", "text": "点击",
                    "component": {
                        "key": "GameClickControl", "version": "0.0.1-beta.1",
                        "props": {"remaining": 5, "total": 5},
                    },
                    "timeout": 5000, "onSuccess": "4.5", "onFail": "4.10",
                },
                "4.5": {"type": "scene", "text": "成功", "next": "4.6"},
                "4.10": {"type": "scene", "text": "失败", "next": "4.6"},
                "4.6": {"type": "ending", "text": "结束", "ending_type": "normal"},
            },
        }
        self.assert_schema_valid(data)
        self.assertEqual(0, semantic_errors(data, qte_registry()))

    def test_qte_upstream_direction_maps_to_slide(self):
        data = self.upstream_story("direction", "GameSlideControl",
                                   props={"knobLabel": "向右滑动", "angle": 0, "total": 5})
        self.assert_schema_valid(data)
        self.assertEqual(0, semantic_errors(data, qte_registry()))

    def test_qte_upstream_unknown_key_fails(self):
        data = self.upstream_story("click", "GameNopeControl")
        self.assertGreater(semantic_errors(data, qte_registry()), 0)

    def test_qte_prerelease_floor_too_high_fails(self):
        # 快照 libVersion=0.0.1-beta.1，组件要求 beta.1 → prerelease 排序 beta.0 < beta.1 → 不满足
        data = self.upstream_story("hold", "GameHoldControl", version="0.0.1-beta.2")
        self.assertGreater(semantic_errors(data, qte_registry()), 0)


class SemanticRegressionTest(unittest.TestCase):
    def validate(self, data):
        self.assertEqual([], validator_module.validate_schema_contract(data))
        validator = validator_module.StoryValidator(data, qte_registry())
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            validator.run_all()
        return validator, output.getvalue()

    def test_bgm_without_media_and_global_bgm_are_checked(self):
        data = base_story()
        data["nodes"]["start"]["bgm"] = "https://bad host/node.mp3"
        data["config"] = {"audio": {"bgm": "https://bad host/global.mp3"}}
        validator, output = self.validate(data)
        self.assertEqual(2, validator.errors)
        self.assertEqual([
            "  FAIL  config.audio.bgm 不是合法 http(s) URL: https://bad host/global.mp3",
            "  FAIL  [start.bgm] bgm 不是合法 http(s) URL: https://bad host/node.mp3",
        ], output.splitlines())

    def test_bgm_loop_accepts_booleans_and_rejects_other_types(self):
        data = base_story()
        data["nodes"]["start"]["bgm"] = "https://host/theme.mp3"
        for loop in (True, False):
            with self.subTest(loop=loop):
                data["nodes"]["start"]["bgmLoop"] = loop
                validator, _ = self.validate(data)
                self.assertEqual(0, validator.errors)
        data["nodes"]["start"]["bgmLoop"] = "false"
        self.assertNotEqual([], validator_module.validate_schema_contract(data))

    def test_url_rejects_authority_whitespace_and_control_characters(self):
        for url in (
            "https://bad host/video.mp4", "https://bad\u3000host/video.mp4",
            "https://bad\thost/video.mp4", "https://bad\nhost/video.mp4",
            "https://host/video\r.mp4",
        ):
            with self.subTest(url=url):
                self.assertFalse(validator_module.is_valid_url(url))
        self.assertTrue(validator_module.is_valid_url("https://host/video.mp4?time=8"))

    def test_numeric_node_ids_have_stable_semantic_order(self):
        data = base_story()
        data["nodes"]["2"] = {"type": "scene", "text": "二", "next": "ending", "bgm": "https://bad host/2.mp3"}
        data["nodes"]["10"] = {"type": "scene", "text": "十", "next": "ending", "bgm": "https://bad host/10.mp3"}
        first, first_output = self.validate(data)
        data["nodes"] = dict(reversed(list(data["nodes"].items())))
        second, second_output = self.validate(data)
        self.assertEqual(2, first.errors)
        self.assertEqual(first.errors, second.errors)
        self.assertEqual(first_output, second_output)
        self.assertLess(first_output.index("[10.bgm]"), first_output.index("[2.bgm]"))

    def test_schema_node_errors_have_stable_numeric_id_order(self):
        data = base_story()
        data["nodes"]["2"] = {"type": "scene", "next": "ending"}
        data["nodes"]["10"] = {"type": "scene", "next": "ending"}
        first = validator_module.validate_schema_contract(data)
        data["nodes"] = dict(reversed(list(data["nodes"].items())))
        self.assertEqual(first, validator_module.validate_schema_contract(data))
        self.assertEqual(["$.nodes.10.text: 缺少必填字段", "$.nodes.2.text: 缺少必填字段"], first)

    def test_legacy_fail_rejects_dangling_reference_with_or_without_component(self):
        for data in (qte_story(), qte_component_story()):
            with self.subTest(component=data["nodes"]["qte"].get("component")):
                data["nodes"]["qte"]["fail"] = "missing"
                validator, output = self.validate(data)
                self.assertEqual(1, validator.errors)
                self.assertIn("[qte.fail] fail 指向不存在的节点: missing", output)

    def test_legacy_fail_makes_failure_ending_reachable(self):
        data = qte_story()
        node = data["nodes"]["qte"]
        node["next"] = node.pop("onSuccess")
        node["fail"] = node.pop("onFail")
        validator, output = self.validate(data)
        self.assertEqual(0, validator.errors)
        self.assertEqual("", output)

    def test_declared_empty_fail_rejects_missing_target(self):
        for data in (qte_story(), qte_component_story()):
            with self.subTest(component=data["nodes"]["qte"].get("component")):
                data["nodes"]["qte"]["fail"] = ""
                validator, output = self.validate(data)
                self.assertEqual(1, validator.errors)
                self.assertIn("[qte.fail] fail 指向不存在的节点: ", output)

    def test_qte_overridden_next_does_not_hide_closed_cycle(self):
        for data in (qte_story(), qte_component_story()):
            with self.subTest(component=data["nodes"]["qte"].get("component")):
                data["nodes"]["qte"].update(next="win", onSuccess="qte")
                data["nodes"]["lose"] = {"type": "scene", "text": "重试", "next": "qte"}
                validator, output = self.validate(data)
                self.assertEqual(2, validator.errors)
                self.assertIn("结局节点不可达: win", output)
                self.assertIn("以下节点无法到达任何结局: lose, qte, start", output)

    def test_qte_retry_cycle_with_real_success_exit_is_allowed(self):
        for data in (qte_story(), qte_component_story()):
            with self.subTest(component=data["nodes"]["qte"].get("component")):
                data["nodes"]["lose"] = {"type": "scene", "text": "重试", "next": "qte"}
                validator, output = self.validate(data)
                self.assertEqual(0, validator.errors)
                self.assertEqual("", output)

    def test_qte_empty_success_target_falls_back_to_next(self):
        data = qte_story()
        data["nodes"]["qte"].update(next="win", onSuccess="")
        validator, output = self.validate(data)
        self.assertEqual(0, validator.errors)
        self.assertEqual("", output)

    def test_component_fail_does_not_make_ignored_ending_reachable(self):
        data = qte_component_story()
        node = data["nodes"]["qte"]
        node["next"] = node.pop("onSuccess")
        node["fail"] = node.pop("onFail")
        validator, output = self.validate(data)
        self.assertEqual(1, validator.errors)
        self.assertIn("结局节点不可达: lose", output)

    def test_reachable_dead_end_is_reported_even_when_another_branch_finishes(self):
        data = qte_story()
        data["nodes"]["lose"] = {"type": "scene", "text": "停住"}
        validator, output = self.validate(data)
        self.assertEqual(1, validator.errors)
        self.assertIn("以下节点无法到达任何结局: lose", output)

    def test_closed_cycle_is_reported_even_when_another_branch_finishes(self):
        data = qte_story()
        data["nodes"]["lose"] = {"type": "scene", "text": "循环", "next": "retry"}
        data["nodes"]["retry"] = {"type": "scene", "text": "再来", "next": "lose"}
        validator, output = self.validate(data)
        self.assertEqual(1, validator.errors)
        self.assertIn("以下节点无法到达任何结局: lose, retry", output)

    def test_cycle_with_an_exit_is_allowed(self):
        data = base_story()
        data["nodes"]["start"]["next"] = "choice"
        data["nodes"]["choice"] = {
            "type": "choice", "text": "重试？",
            "choices": [{"label": "重试", "next": "choice"}, {"label": "结束", "next": "ending"}],
        }
        validator, output = self.validate(data)
        self.assertEqual(0, validator.errors)
        self.assertEqual("", output)

    def test_story_without_any_ending_is_rejected(self):
        data = base_story()
        data["nodes"]["ending"] = {"type": "scene", "text": "循环", "next": "start"}
        validator, output = self.validate(data)
        self.assertEqual(1, validator.errors)
        self.assertIn("以下节点无法到达任何结局: ending, start", output)

    def test_dangling_edges_suppress_cascading_cannot_finish_error(self):
        for edge in ("next", "fail", "onFail", "choice"):
            with self.subTest(edge=edge):
                data = qte_story()
                if edge == "choice":
                    data["nodes"]["qte"] = {
                        "type": "choice", "text": "分支",
                        "choices": [{"label": "坏引用", "next": "missing"}, {"label": "继续", "next": "lose"}],
                    }
                else:
                    data["nodes"]["qte"][edge] = "missing"
                data["nodes"]["lose"] = {"type": "scene", "text": "停住"}
                validator, output = self.validate(data)
                self.assertGreater(validator.errors, 0)
                self.assertIn("指向不存在的节点: missing", output)
                self.assertNotIn("以下节点无法到达任何结局", output)

    def test_disappear_time_uses_seconds_against_clip_milliseconds(self):
        for disappear_at, expected_errors in ((8, 0), (8.1, 1)):
            with self.subTest(disappear_at=disappear_at):
                data = qte_component_story()
                data["nodes"]["qte"]["clipDuration"] = 8000
                data["nodes"]["qte"]["disappearAt"] = disappear_at
                validator, output = self.validate(data)
                self.assertEqual(expected_errors, validator.errors)
                if expected_errors:
                    self.assertIn("disappearAt(8.1s) 不应 > clipDuration(8000ms)", output)

    def test_component_eight_seconds_cut_to_one_warns_without_blocking(self):
        for timeout, appear_at, disappear_at in ((8000, 7, 8), (1000, 0, 8)):
            with self.subTest(timeout=timeout):
                data = qte_component_story()
                node = data["nodes"]["qte"]
                node.update(timeout=timeout, appearAt=appear_at, disappearAt=disappear_at)
                node["component"]["props"]["total"] = 8
                validator, output = self.validate(data)
                self.assertEqual(0, validator.errors)
                self.assertEqual(1, validator.warnings)
                self.assertIn("配置时长(8000ms) 超过实际 QTE 时间(1000ms)", output)

    def test_display_total_alone_does_not_impose_deadline_or_warning(self):
        data = qte_component_story()
        node = data["nodes"]["qte"]
        for key in ("timeout", "appearAt", "disappearAt"):
            node.pop(key)
        node["component"]["props"]["total"] = 8
        validator, output = self.validate(data)
        self.assertEqual(0, validator.errors)
        self.assertEqual(0, validator.warnings)
        self.assertEqual("", output)

    def test_limited_false_suppresses_truncation_warning(self):
        # limited:false 关闭限时 → 不再对配置时长超实际限时告警（与 SDK 侧一致，守住对拍不变量）
        data = qte_component_story()
        node = data["nodes"]["qte"]
        node.update(timeout=8000, appearAt=7, disappearAt=8)
        node["component"]["props"]["total"] = 8
        node["limited"] = False
        validator, output = self.validate(data)
        self.assertEqual(0, validator.errors)
        self.assertEqual(0, validator.warnings)

    def test_scale_limited_without_component_warns(self):
        # scale/limited 落在无 component 的旧内置 interaction 上，运行时会被忽略 → WARN 提醒作者
        data = qte_component_story()
        node = data["nodes"]["qte"]
        del node["component"]
        node["interaction"] = "tap"
        node["scale"] = 120
        node["limited"] = False
        _, output = self.validate(data)
        self.assertIn("scale/limited 仅对带 component 的 QTE 节点生效", output)

    def test_scale_invalid_is_lenient_warn_not_error(self):
        # 越界/非数的 scale 不 FAIL（schema 不再约束范围），仅 WARN，运行时回落 100
        for scale in (49, 201, "120"):
            with self.subTest(scale=scale):
                data = qte_component_story()
                data["nodes"]["qte"]["scale"] = scale
                validator, output = self.validate(data)
                self.assertEqual(0, validator.errors)
                self.assertIn("运行时将忽略并回落 100", output)


class CLIExitCodeTest(unittest.TestCase):
    """断言 CLI 退出码：合法输入 0，非法输入 1。"""

    def _run_cli(self, data, stage="full"):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()
            result = subprocess.run(
                ["python3", str(VALIDATOR_PATH), "--file", f.name, "--stage", stage],
                capture_output=True, text=True,
            )
            Path(f.name).unlink(missing_ok=True)
        return result.returncode

    def test_cli_video_valid_exits_0(self):
        data = base_story()
        data["nodes"]["start"]["media"] = {
            "type": "video", "src": "https://cdn.example.com/v.mp4",
        }
        self.assertEqual(0, self._run_cli(data))

    def test_cli_sequence_valid_exits_0(self):
        data = base_story()
        data["nodes"]["start"]["media"] = {
            "type": "sequence",
            "items": [{"src": "https://cdn.example.com/s1.mp4"}],
        }
        self.assertEqual(0, self._run_cli(data))

    def test_cli_sequence_invalid_url_exits_1(self):
        data = base_story()
        data["nodes"]["start"]["media"] = {
            "type": "sequence",
            "items": [{"src": "not-a-url"}],
        }
        self.assertEqual(1, self._run_cli(data))

    def test_cli_video_invalid_url_exits_1(self):
        data = base_story()
        data["nodes"]["start"]["media"] = {
            "type": "video", "src": "ftp://bad/video.mp4",
        }
        self.assertEqual(1, self._run_cli(data))


if __name__ == "__main__":
    unittest.main()
