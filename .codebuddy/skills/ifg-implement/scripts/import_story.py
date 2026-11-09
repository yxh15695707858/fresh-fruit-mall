#!/usr/bin/env python3
"""下载、对账并校验 IFG story，向预览页提供脱敏的导入失败信息。"""

import argparse
import http.client
import json
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit


SCRIPT_DIR = Path(__file__).resolve().parent


class HttpRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urlsplit(newurl).scheme not in ("http", "https"):
            raise urllib.error.URLError("unsupported redirect protocol")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download_story(url, destination):
    if urlsplit(url).scheme not in ("http", "https"):
        raise ValueError("story URL must use HTTP(S)")
    opener = urllib.request.build_opener(HttpRedirectHandler())
    with opener.open(url, timeout=30) as response, destination.open("wb") as target:
        shutil.copyfileobj(response, target)


def public_message(message):
    message = re.sub(r"https?://[^\s\"'<>]+", "[URL 已隐藏]", message, flags=re.I)
    message = re.sub(r"\bBearer\s+[A-Za-z0-9._~+/-]+=*", "Bearer [已隐藏]", message, flags=re.I)
    message = re.sub(
        r"([\w.-]*(?:token|secret|password|passwd|authorization|api[_-]?key|signature|credential)[\w.-]*[\"']?\s*[:=]\s*)(?:[\"'][^\"']*[\"']|(?:Bearer\s+)?[^\s,;}]+)",
        r"\1[已隐藏]", message, flags=re.I,
    )
    message = re.sub(r"(?:\$\(|`|\b(?:curl|wget|npm|pnpm|npx|node|python3?|bash|sh)\s+).*", "[命令已隐藏]", message)
    return message


def stage_message(stage, result):
    if stage == "reconcile":
        try:
            error = json.loads(result.stdout).get("error", {})
            if error.get("message"):
                return public_message(f"{error.get('code', '组件依赖对账失败')}: {error['message']}")
        except (ValueError, AttributeError):
            pass
    failures = [line.strip() for line in result.stdout.splitlines() if line.lstrip().startswith("FAIL")]
    if failures:
        return public_message("\n".join(failures))
    for line in result.stderr.splitlines():
        if line.startswith("json.decoder.JSONDecodeError:"):
            return public_message(line)
    return "组件依赖对账失败，详细输出已保留供排查。" if stage == "reconcile" else "剧情数据校验未完成，详细输出已保留供排查。"


def write_status(path, stage, message):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({"status": "error", "stage": stage, "message": message},
                                    ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def import_story(frontend_dir, url, *, downloader=download_story, runner=subprocess.run):
    frontend = Path(frontend_dir).resolve()
    story_dir = frontend / "public" / "story"
    story_dir.mkdir(parents=True, exist_ok=True)
    target = story_dir / "story.json"
    status = story_dir / "import-status.json"
    private_dir = frontend.parent / ".genie" / "ifg-import"
    private_dir.mkdir(parents=True, exist_ok=True)
    stage = "download"
    raw_output = ""
    message = ""
    with tempfile.TemporaryDirectory(prefix="attempt-", dir=private_dir) as tmp:
        downloaded = Path(tmp) / "downloaded-story.json"
        candidate = Path(tmp) / "story.json"
        try:
            downloader(url, downloaded)
        except urllib.error.HTTPError as error:
            message = f"下载剧情文件失败：HTTP {error.code}。"
        except (urllib.error.URLError, http.client.HTTPException, TimeoutError, OSError, ValueError):
            message = "下载剧情文件失败：请检查 HTTP(S) 地址或网络后重试。"

        if not message:
            stage = "reconcile"
            try:
                shutil.copyfile(downloaded, candidate)
                for stage, command in (
                    ("reconcile", [sys.executable, str(SCRIPT_DIR / "reconcile_qte.py"), str(frontend), "--story", str(candidate)]),
                    ("validate", [sys.executable, str(SCRIPT_DIR / "validate.py"), "--file", str(candidate), "--stage", "full"]),
                ):
                    registry = story_dir / "qte-registry.json"
                    if stage == "validate" and registry.exists():
                        shutil.copyfile(registry, candidate.parent / registry.name)
                    result = runner(command, cwd=frontend.parent, capture_output=True, text=True, check=False)
                    raw_output = result.stdout + result.stderr
                    if result.returncode:
                        message = stage_message(stage, result)
                        break
                    if raw_output:
                        print(public_message(raw_output), end="" if raw_output.endswith("\n") else "\n")
                if not message:
                    temporary = target.with_suffix(".tmp")
                    shutil.copyfile(candidate, temporary)
                    status.unlink(missing_ok=True)
                    temporary.replace(target)
            except OSError as error:
                raw_output = str(error)
                message = "组件依赖对账未能执行。" if stage == "reconcile" else "剧情数据校验或写入未能完成。"

        if message:
            failed_story = private_dir / "failed-story.json"
            if downloaded.exists():
                shutil.copyfile(downloaded, failed_story)
            else:
                failed_story.unlink(missing_ok=True)
            (private_dir / "failure.log").write_text(f"stage: {stage}\n{raw_output or message}\n", encoding="utf-8")
            write_status(status, stage, message)
            print(message, file=sys.stderr)
            return 1

    print("剧情导入成功。")
    return 0


def main():
    parser = argparse.ArgumentParser(description="IFG 剧情导入、依赖对账与完整校验")
    parser.add_argument("frontend_dir", help="前端目录")
    parser.add_argument("--url", required=True, help="story.json HTTP(S) URL")
    args = parser.parse_args()
    return import_story(args.frontend_dir, args.url)


if __name__ == "__main__":
    sys.exit(main())
