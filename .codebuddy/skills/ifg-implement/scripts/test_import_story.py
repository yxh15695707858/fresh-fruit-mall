#!/usr/bin/env python3

import contextlib
import http.client
import importlib.util
import io
import json
import subprocess
import tempfile
import unittest
import urllib.error
from pathlib import Path


IMPORT_PATH = Path(__file__).resolve().parent / "import_story.py"
spec = importlib.util.spec_from_file_location("ifg_import", IMPORT_PATH)
importer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(importer)

SOURCE = b'{"meta":{"title":"new"},"nodes":{}}\n'
URL = "https://example.com/story.json?token=private-source-token"


class ImportStoryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.frontend = Path(self.tmp.name) / "frontend"
        self.story_dir = self.frontend / "public" / "story"
        self.story_dir.mkdir(parents=True)
        self.target = self.story_dir / "story.json"
        self.status = self.story_dir / "import-status.json"
        self.private = Path(self.tmp.name) / ".genie" / "ifg-import"
        self.calls = []

    def download(self, url, destination):
        self.assertEqual(url, URL)
        destination.write_bytes(SOURCE)

    def runner(self, *, fail_stage=None, stdout="", stderr=""):
        def run(command, **kwargs):
            stage = "reconcile" if command[1].endswith("reconcile_qte.py") else "validate"
            self.calls.append(stage)
            flag = "--story" if stage == "reconcile" else "--file"
            candidate = Path(command[command.index(flag) + 1])
            self.assertTrue(candidate.is_relative_to(self.private.resolve()))
            self.assertEqual(candidate.read_bytes(), SOURCE)
            self.assertTrue(kwargs["capture_output"])
            return subprocess.CompletedProcess(command, int(stage == fail_stage),
                                               stdout if stage == fail_stage else "", stderr)
        return run

    def run_import(self, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return importer.import_story(self.frontend, URL, downloader=kwargs.pop("downloader", self.download), **kwargs)

    def read_status(self):
        return json.loads(self.status.read_text())

    def test_first_validation_failure_publishes_error_without_public_story(self):
        output = "正在校验: /workspace/frontend/public/story/story.json\n  FAIL  [schema] $.config.components.text.props.tone: 值不在允许范围\n结果: FAIL（1 个 Schema 错误）\n"
        result = self.run_import(runner=self.runner(fail_stage="validate", stdout=output))
        self.assertEqual(result, 1)
        self.assertFalse(self.target.exists())
        self.assertEqual(self.calls, ["reconcile", "validate"])
        self.assertEqual(self.read_status(), {
            "status": "error", "stage": "validate",
            "message": "FAIL  [schema] $.config.components.text.props.tone: 值不在允许范围",
        })
        self.assertEqual((self.private / "failed-story.json").read_bytes(), SOURCE)
        self.assertEqual(sorted(p.name for p in self.story_dir.iterdir()), ["import-status.json"])

    def test_update_failure_keeps_existing_story(self):
        original = b'{"meta":{"title":"old"},"nodes":{}}\n'
        self.target.write_bytes(original)
        self.assertEqual(self.run_import(runner=self.runner(fail_stage="validate", stdout="  FAIL  [n1.component.props] props.count: 不能小于 1\n")), 1)
        self.assertEqual(self.target.read_bytes(), original)
        self.assertEqual(self.read_status()["stage"], "validate")

    def test_candidate_uses_reconciled_registry_and_only_publishes_after_validation(self):
        original = b'{"meta":{"title":"old"},"nodes":{}}\n'
        self.target.write_bytes(original)
        story = {"meta": {"title": "candidate", "version": "1.0.0", "start": "start"},
                 "qte": {"lib": "miora-spell", "version": "0.0.1-beta.1"}, "nodes": {
            "start": {"type": "start", "text": "开始", "next": "q"},
            "q": {"type": "interaction", "text": "点击", "component": {
                "key": "GameClickControl", "props": {"total": 2}},
                "onSuccess": "ending", "onFail": "failed"},
            "ending": {"type": "ending", "text": "结束", "ending_type": "normal"},
            "failed": {"type": "ending", "text": "失败", "ending_type": "bad"},
        }}
        catalog = json.loads((IMPORT_PATH.parent.parent / "references/qte-registry.json").read_text())
        catalog["components"]["click"]["propsSchema"]["properties"]["total"]["maximum"] = 1

        def download(_url, destination):
            destination.write_text(json.dumps(story))

        def run(command, **kwargs):
            self.assertEqual(self.target.read_bytes(), original)
            if command[1].endswith("reconcile_qte.py"):
                candidate = Path(command[command.index("--story") + 1])
                reconciled = json.loads(candidate.read_text())
                reconciled["meta"]["title"] = "reconciled"
                candidate.write_text(json.dumps(reconciled))
                (self.story_dir / "qte-registry.json").write_text(json.dumps(catalog))
                return subprocess.CompletedProcess(command, 0, "", "")
            return subprocess.run(command, **kwargs)

        self.assertEqual(self.run_import(downloader=download, runner=run), 1)
        self.assertEqual(self.target.read_bytes(), original)
        self.assertIn("total", self.read_status()["message"])
        self.assertEqual(json.loads((self.private / "failed-story.json").read_text()), story)
        catalog["components"]["click"]["propsSchema"]["properties"]["total"]["maximum"] = 10
        result = self.run_import(downloader=download, runner=run)
        self.assertEqual(result, 0, self.read_status() if result else "")
        self.assertEqual(json.loads(self.target.read_text())["meta"]["title"], "reconciled")
        self.assertFalse(self.status.exists())

    def test_reconcile_failure_skips_validation(self):
        output = json.dumps({"failed": True, "error": {
            "code": "COMPONENT_VERSION_CONFLICT", "message": "config.components 版本与 qte.version 不一致",
        }})
        self.assertEqual(self.run_import(runner=self.runner(fail_stage="reconcile", stdout=output)), 1)
        self.assertEqual(self.calls, ["reconcile"])
        self.assertEqual(self.read_status()["stage"], "reconcile")
        self.assertIn("COMPONENT_VERSION_CONFLICT", self.read_status()["message"])
        self.assertFalse(self.target.exists())

    def test_success_keeps_story_and_clears_previous_error(self):
        self.status.write_text('{"status":"error","stage":"validate","message":"old error"}')
        self.assertEqual(self.run_import(runner=self.runner()), 0)
        self.assertEqual(self.target.read_bytes(), SOURCE)
        self.assertFalse(self.status.exists())
        self.assertEqual(self.calls, ["reconcile", "validate"])

    def test_download_failure_keeps_old_story_and_hides_signed_url(self):
        original = b'{"meta":{"title":"old"},"nodes":{}}\n'
        self.target.write_bytes(original)
        def download(url, destination):
            raise urllib.error.HTTPError(url, 403, "private-source-token", {}, None)
        self.assertEqual(self.run_import(downloader=download, runner=self.runner()), 1)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.target.read_bytes(), original)
        self.assertEqual(self.read_status(), {
            "status": "error", "stage": "download", "message": "下载剧情文件失败：HTTP 403。",
        })

    def test_invalid_download_protocol_produces_error_without_story(self):
        def download(_url, destination):
            importer.download_story("file:///private/story.json", destination)
        self.assertEqual(self.run_import(downloader=download, runner=self.runner()), 1)
        self.assertEqual(self.read_status()["stage"], "download")
        self.assertFalse(self.target.exists())
        self.assertEqual(self.calls, [])

    def test_interrupted_download_keeps_partial_data_outside_public(self):
        def download(_url, destination):
            destination.write_bytes(b'{"meta":')
            raise http.client.IncompleteRead(b'{"meta":', 200)
        self.assertEqual(self.run_import(downloader=download, runner=self.runner()), 1)
        self.assertFalse(self.target.exists())
        self.assertEqual(self.read_status()["stage"], "download")
        self.assertEqual((self.private / "failed-story.json").read_bytes(), b'{"meta":')
        self.assertEqual(self.calls, [])

    def test_public_error_redacts_urls_secrets_and_commands(self):
        output = (
            "  FAIL  [n1.media.src] URL 无效: https://example.com/video.mp4?Signature=secret-signature\n"
            "  FAIL  [n2] token=secret-token Authorization: Bearer private-bearer-token\n"
            "  FAIL  [n3] curl -H 'X-Api-Key: private-api-key' https://example.com\n"
            "  FAIL  [schema] $.nodes.end.type: 值 'Bearer sk_test_private_value' 不在允许范围\n"
            "  FAIL  [schema] $.nodes.end.type: 值 'node -e console.log(1)' 不在允许范围\n"
        )
        self.run_import(runner=self.runner(fail_stage="validate", stdout=output))
        public = self.status.read_text()
        for secret in ("https://", "secret-signature", "secret-token", "private-bearer-token", "curl -H", "private-api-key", "sk_test_private_value", "node -e"):
            self.assertNotIn(secret, public)
        self.assertIn("[n1.media.src]", public)
        self.assertIn(output, (self.private / "failure.log").read_text())

    def test_json_parse_error_excludes_traceback_commands(self):
        error = 'Traceback (most recent call last):\n  subprocess.run(["curl", "https://example.com?token=private-source-token"])\njson.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)\n'
        self.run_import(runner=self.runner(fail_stage="reconcile", stderr=error))
        self.assertEqual(self.read_status()["message"], "json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)")
        self.assertNotIn("curl", self.status.read_text())

    def test_real_scripts_report_schema_field_and_allow_next_valid_import(self):
        story = {"meta": {"title": "测试", "start": "start"}, "nodes": {
            "start": {"type": "start", "text": "开始", "next": "ending"},
            "ending": {"type": "ending", "text": "结束", "ending_type": "normal"},
        }}
        def download(_url, destination):
            destination.write_text(json.dumps(story, ensure_ascii=False))
        self.assertEqual(self.run_import(downloader=download), 1)
        self.assertFalse(self.target.exists())
        self.assertEqual(self.read_status()["stage"], "validate")
        self.assertIn("$.meta.version: 缺少必填字段", self.read_status()["message"])
        story["meta"]["version"] = "1.0.0"
        self.assertEqual(self.run_import(downloader=download), 0)
        self.assertFalse(self.status.exists())
        self.assertEqual(json.loads(self.target.read_text()), story)


if __name__ == "__main__":
    unittest.main()
