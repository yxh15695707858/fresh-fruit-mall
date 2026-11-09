#!/usr/bin/env python3
"""localize_assets.py 的单元测试。

用本地线程 HTTP server 提供假素材，通过 subprocess 调用脚本，覆盖：
下载/改写/hash 去重、幂等、相对/本地/data: 跳过、严格失败回滚、lenient、
--check 三态、story.json 缺失空跑、nodes 为对象 map、sfx 前缀与 media union。
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "localize_assets.py")


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class LocalizeAssetsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="loc-test-")
        self.media_dir = os.path.join(self.tmp, "media")
        os.makedirs(self.media_dir)
        # 假素材
        self._write("v1.mp4", b"VIDEO-ONE")
        self._write("v2.mp4", b"VIDEO-TWO")
        self._write("p.jpg", b"POSTER-IMG")
        self._write("s.vtt", b"WEBVTT\n")
        self._write("sfx.mp3", b"SFX-AUDIO")
        self._write("shared.mp4", b"SHARED-VIDEO")

        handler = partial(_QuietHandler, directory=self.media_dir)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

        self.story_dir = os.path.join(self.tmp, "proj", "frontend", "public", "story")
        os.makedirs(self.story_dir)
        self.story = os.path.join(self.story_dir, "story.json")
        self.assets_dir = os.path.join(self.tmp, "proj", "frontend", "public", "assets", "story-media")

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, name, data):
        with open(os.path.join(self.media_dir, name), "wb") as f:
            f.write(data)

    def _url(self, name):
        return "http://127.0.0.1:%d/%s?sign=abc&t=1" % (self.port, name)

    def _put_story(self, tree):
        with open(self.story, "w", encoding="utf-8") as f:
            json.dump(tree, f, ensure_ascii=False)

    def _read_story(self):
        with open(self.story, encoding="utf-8") as f:
            return json.load(f)

    def _run(self, *extra):
        return subprocess.run(
            [sys.executable, SCRIPT,
             "--story", self.story,
             "--assets-dir", self.assets_dir,
             "--base", "/assets/story-media", *extra],
            capture_output=True, text=True,
        )

    def _full_story(self):
        return {
            "meta": {"start": "n1"},
            "config": {
                "poster": self._url("p.jpg"),
                "audio": {"bgm": self._url("sfx.mp3")},
                "skin": {"frame": self._url("p.jpg")},
            },
            "items": [{"id": "i1", "image": self._url("p.jpg")}],
            "characters": [{"id": "c1", "image": self._url("p.jpg")}],
            "nodes": {  # 对象 map
                "n1": {
                    "cover": self._url("p.jpg"),
                    "bgm": self._url("sfx.mp3"),
                    "media": {"type": "video", "src": self._url("v1.mp4"),
                              "subtitle": self._url("s.vtt")},
                    "choices": [{"label": "x", "art": self._url("p.jpg"), "next": "n2"}],
                    "fx": ["shake", "sfx:" + self._url("sfx.mp3")],
                },
                "n2": {
                    "media": {"type": "sequence", "items": [
                        {"src": self._url("v2.mp4"), "shotId": "a", "poster": self._url("p.jpg")},
                        {"src": self._url("v2.mp4"), "subtitle": self._url("s.vtt"),
                         "poster": self._url("p.jpg")},
                    ]},
                },
                "eg": {"media": {"type": "video", "src": self._url("shared.mp4")}},
                "eb": {"media": {"type": "video", "src": self._url("shared.mp4")}},
                "keep": {
                    "cover": "/assets/already.png",           # 已本地，跳过
                    "media": {"type": "video", "src": "relative/x.mp4"},  # 相对，跳过
                },
            },
        }

    # ---- 用例 ----

    def test_full_localize_and_rewrite(self):
        self._put_story(self._full_story())
        r = self._run()
        self.assertEqual(r.returncode, 0, r.stderr)
        tree = self._read_story()
        # 所有远程字段改写为 /assets/story-media/
        self.assertTrue(tree["config"]["poster"].startswith("/assets/story-media/"))
        self.assertTrue(tree["config"]["audio"]["bgm"].startswith("/assets/story-media/"))
        self.assertTrue(tree["config"]["skin"]["frame"].startswith("/assets/story-media/"))
        self.assertTrue(tree["items"][0]["image"].startswith("/assets/story-media/"))
        self.assertTrue(tree["characters"][0]["image"].startswith("/assets/story-media/"))
        n1 = tree["nodes"]["n1"]
        self.assertTrue(n1["cover"].startswith("/assets/story-media/"))
        self.assertTrue(n1["bgm"].startswith("/assets/story-media/"))
        self.assertTrue(n1["media"]["src"].startswith("/assets/story-media/"))
        self.assertTrue(n1["media"]["subtitle"].startswith("/assets/story-media/"))
        self.assertTrue(n1["choices"][0]["art"].startswith("/assets/story-media/"))
        # sfx 前缀保留
        self.assertTrue(n1["fx"][1].startswith("sfx:/assets/story-media/"))
        self.assertEqual(n1["fx"][0], "shake")
        # sequence 两段
        seq = tree["nodes"]["n2"]["media"]["items"]
        self.assertTrue(seq[0]["src"].startswith("/assets/story-media/"))
        self.assertTrue(seq[1]["src"].startswith("/assets/story-media/"))
        self.assertEqual(seq[0]["poster"], tree["config"]["poster"])
        self.assertEqual(seq[1]["poster"], tree["config"]["poster"])
        self.assertTrue(seq[1]["subtitle"].startswith("/assets/story-media/"))
        # 内容相同的 URL（eg/eb 共享，n2 两段同 v2）去重到同一文件
        self.assertEqual(tree["nodes"]["eg"]["media"]["src"], tree["nodes"]["eb"]["media"]["src"])
        self.assertEqual(seq[0]["src"], seq[1]["src"])
        # 已本地 / 相对路径不动
        self.assertEqual(tree["nodes"]["keep"]["cover"], "/assets/already.png")
        self.assertEqual(tree["nodes"]["keep"]["media"]["src"], "relative/x.mp4")
        # 无残留 http
        self.assertNotIn("http://", json.dumps(tree))
        # 文件确实落盘
        self.assertTrue(os.path.isdir(self.assets_dir))
        self.assertTrue(len(os.listdir(self.assets_dir)) > 0)

    def test_idempotent_second_run(self):
        self._put_story(self._full_story())
        self.assertEqual(self._run().returncode, 0)
        before = self._read_story()
        r2 = self._run()
        self.assertEqual(r2.returncode, 0)
        self.assertIn("nothing to do", r2.stdout)
        self.assertEqual(before, self._read_story())  # 二次不改动

    def test_check_states(self):
        self._put_story(self._full_story())
        # 本地化前：仍有远程 URL -> rc=3
        self.assertEqual(self._run("--check").returncode, 3)
        self.assertEqual(self._run().returncode, 0)
        # 本地化后：全本地 -> rc=0
        self.assertEqual(self._run("--check").returncode, 0)
        tree = self._read_story()
        # 仅 sequence poster 残留远程 URL / 本地文件缺失 -> rc=3
        for poster in [self._url("p.jpg"), "/assets/story-media/missing-poster.jpg"]:
            with self.subTest(poster=poster):
                tree["nodes"]["n2"]["media"]["items"][0]["poster"] = poster
                self._put_story(tree)
                result = self._run("--check")
                self.assertEqual(result.returncode, 3)
                self.assertIn(poster, result.stderr)

    def test_strict_failure_rolls_back(self):
        tree = self._full_story()
        tree["nodes"]["n2"]["media"]["items"][0]["poster"] = self._url("DOES_NOT_EXIST.jpg")
        self._put_story(tree)
        original = self._read_story()
        r = self._run()
        self.assertEqual(r.returncode, 1)
        self.assertIn("restored", r.stderr)
        self.assertEqual(original, self._read_story())  # 原文件未改动
        # 无残留 .bak/.tmp
        leftovers = [f for f in os.listdir(self.story_dir) if f.endswith((".bak", ".tmp"))]
        self.assertEqual(leftovers, [])

    def test_lenient_keeps_failed_url(self):
        tree = {"meta": {}, "config": {"poster": self._url("p.jpg")},
                "nodes": {"n1": {"media": {"type": "video",
                                           "src": self._url("DOES_NOT_EXIST.mp4")}}}}
        self._put_story(tree)
        r = self._run("--lenient")
        self.assertEqual(r.returncode, 0)
        tree2 = self._read_story()
        self.assertTrue(tree2["config"]["poster"].startswith("/assets/story-media/"))  # 成功的改写
        self.assertIn("DOES_NOT_EXIST", tree2["nodes"]["n1"]["media"]["src"])  # 失败的保留

    def test_missing_story_is_noop(self):
        # 不写 story.json
        r = self._run()
        self.assertEqual(r.returncode, 0)
        self.assertIn("not found", r.stdout)
        r2 = self._run("--check")
        self.assertEqual(r2.returncode, 0)

    def test_max_bytes_limit_fails(self):
        # big.mp4 超过 --max-bytes 上限 -> 严格失败并回滚
        self._write("big.mp4", b"X" * 5000)
        tree = {"meta": {}, "config": {"poster": self._url("p.jpg")},
                "nodes": {"n1": {"media": {"type": "video", "src": self._url("big.mp4")}}}}
        self._put_story(tree)
        original = self._read_story()
        r = self._run("--max-bytes", "1024")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(original, self._read_story())  # 回滚，story.json 未改
        # 上限内则成功
        r2 = self._run("--max-bytes", "1000000")
        self.assertEqual(r2.returncode, 0)
        self.assertTrue(self._read_story()["nodes"]["n1"]["media"]["src"].startswith("/assets/story-media/"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
