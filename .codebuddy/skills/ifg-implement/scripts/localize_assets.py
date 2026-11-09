#!/usr/bin/env python3
"""Localize remote signed media URLs in an IFG story.json into sandbox-local files.

上游通过 story.json 下发的图片/视频/字幕/音频地址带签名和有效期，直接发布后
分享出去会因签名过期而无法访问。本脚本把这些远程 URL 下载到沙箱本地的 assets 目录，
并把 story.json 里的 URL 改写为站点根相对路径（如 /assets/story-media/<hash>.mp4），
使发布产物不再依赖会过期的签名 URL。

调用方式：由上游服务在沙箱内通过 e2b 执行本脚本；执行时机由上游调用方决定，
但保证在发布之前完成。本脚本不由 api-server 发布链路、也不由 ifg-implement skill 触发。
--check 供上游在发布前做快速校验（仍有外部 URL 或本地文件缺失即非零退出）。

守门语义（默认 strict）：
- story.json 不存在 -> 直接成功退出（非 IFG 项目安全空跑）。
- 任一资源下载失败 -> 还原 story.json 原文件并以非零码退出（不产出半本地化的坏站）。
- 幂等：已是 /assets 相对路径 / 非 http 的值一律跳过，重复执行几乎零开销。

用法：
  # 完整本地化
  python3 localize_assets.py --story frontend/public/story/story.json \
      --assets-dir frontend/public/assets/story-media --base /assets/story-media [--lenient]
  # 快速校验：仍有外部 URL 或本地文件缺失 -> 退出码 3
  python3 localize_assets.py --story ... --assets-dir ... --base ... --check
"""
import argparse
import hashlib
import json
import mimetypes
import os
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

DOWNLOAD_TIMEOUT = 60  # 单个资源下载超时（秒）
USER_AGENT = "genie-ifg-localizer/1.0"
CHUNK = 1 << 16
EXIT_CHECK_FAILED = 3  # --check：仍有外部 URL 或本地文件缺失
DEFAULT_MAX_BYTES = 1 << 30  # 单文件下载上限（1 GiB），防恶意/超大引用撑爆沙箱磁盘

# Content-Type -> 扩展名兜底（URL 无可用后缀时使用）
CT_EXT = {
    "video/mp4": ".mp4", "video/webm": ".webm", "video/quicktime": ".mov",
    "video/x-m4v": ".m4v", "video/mpeg": ".mpeg",
    "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp",
    "image/gif": ".gif", "image/svg+xml": ".svg", "image/avif": ".avif",
    "audio/mpeg": ".mp3", "audio/mp3": ".mp3", "audio/wav": ".wav",
    "audio/ogg": ".ogg", "audio/aac": ".aac", "audio/x-m4a": ".m4a",
    "text/vtt": ".vtt", "application/x-subrip": ".srt",
}


def is_remote(value):
    return isinstance(value, str) and (value.startswith("http://") or value.startswith("https://"))


def pick_ext(url, content_type):
    """优先取 URL 路径后缀，其次按 Content-Type 映射，最后兜底 .bin。"""
    path = urlparse(url).path
    _, ext = os.path.splitext(path)
    if ext and 1 < len(ext) <= 6 and ext[1:].isalnum():
        return ext.lower()
    if content_type:
        ct = content_type.split(";")[0].strip().lower()
        if ct in CT_EXT:
            return CT_EXT[ct]
        guessed = mimetypes.guess_extension(ct)
        if guessed:
            return guessed
    return ".bin"


def walk_media(tree, visit):
    """遍历 story.json 的全部媒体 URL 槽位，对每个字符串值调用 visit(value)。

    visit 返回字符串则替换该槽位，返回 None 则保持原值。collect / rewrite / check
    共用这一份遍历，确保字段集合单一来源。sfx: 前缀与 media(video/sequence) union
    这两个不规则点在此统一处理。
    """
    def apply(value):
        if not isinstance(value, str):
            return value
        new = visit(value)
        return new if isinstance(new, str) else value

    cfg = tree.get("config")
    if isinstance(cfg, dict):
        if isinstance(cfg.get("poster"), str):
            cfg["poster"] = apply(cfg["poster"])
        audio = cfg.get("audio")
        if isinstance(audio, dict) and isinstance(audio.get("bgm"), str):
            audio["bgm"] = apply(audio["bgm"])
        skin = cfg.get("skin")
        if isinstance(skin, dict) and isinstance(skin.get("frame"), str):
            skin["frame"] = apply(skin["frame"])

    for item in tree.get("items") or []:
        if isinstance(item, dict) and isinstance(item.get("image"), str):
            item["image"] = apply(item["image"])

    for char in tree.get("characters") or []:
        if isinstance(char, dict) and isinstance(char.get("image"), str):
            char["image"] = apply(char["image"])

    # nodes 是 Record<string, StoryNode>（对象 map），也兼容数组形态
    nodes = tree.get("nodes")
    if isinstance(nodes, dict):
        node_iter = nodes.values()
    elif isinstance(nodes, list):
        node_iter = nodes
    else:
        node_iter = []
    for node in node_iter:
        if not isinstance(node, dict):
            continue
        if isinstance(node.get("cover"), str):
            node["cover"] = apply(node["cover"])
        if isinstance(node.get("bgm"), str):
            node["bgm"] = apply(node["bgm"])

        media = node.get("media")
        if isinstance(media, dict):
            mtype = media.get("type")
            if mtype == "video":
                if isinstance(media.get("src"), str):
                    media["src"] = apply(media["src"])
                if isinstance(media.get("subtitle"), str):
                    media["subtitle"] = apply(media["subtitle"])
            elif mtype == "sequence":
                for seg in media.get("items") or []:
                    if isinstance(seg, dict):
                        if isinstance(seg.get("src"), str):
                            seg["src"] = apply(seg["src"])
                        if isinstance(seg.get("poster"), str):
                            seg["poster"] = apply(seg["poster"])
                        if isinstance(seg.get("subtitle"), str):
                            seg["subtitle"] = apply(seg["subtitle"])

        for choice in node.get("choices") or []:
            if isinstance(choice, dict) and isinstance(choice.get("art"), str):
                choice["art"] = apply(choice["art"])

        # fx: 字符串数组，音效 URL 内嵌在 "sfx:" 前缀之后
        fx = node.get("fx")
        if isinstance(fx, list):
            for i, entry in enumerate(fx):
                if isinstance(entry, str) and entry.startswith("sfx:"):
                    new = visit(entry[4:])
                    if isinstance(new, str):
                        fx[i] = "sfx:" + new


def collect_remote(tree):
    seen = set()

    def visit(value):
        if is_remote(value):
            seen.add(value)
        return None

    walk_media(tree, visit)
    return sorted(seen)


def download(url, staging_dir, max_bytes):
    """流式下载到暂存文件，边下边算 sha256；超过 max_bytes 即中止。返回 (临时路径, 摘要, 扩展名)。"""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    digest = hashlib.sha256()
    written = 0
    fd, tmp_path = tempfile.mkstemp(dir=staging_dir)
    try:
        with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT) as resp, os.fdopen(fd, "wb") as out:
            content_type = resp.headers.get("Content-Type", "")
            while True:
                chunk = resp.read(CHUNK)
                if not chunk:
                    break
                written += len(chunk)
                if max_bytes and written > max_bytes:
                    raise ValueError("exceeds max size %d bytes" % max_bytes)
                digest.update(chunk)
                out.write(chunk)
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise
    return tmp_path, digest.hexdigest(), pick_ext(url, content_type)


def cmd_check(args):
    """快速校验：仍存在外部 http(s) URL、或已本地化的文件在磁盘上缺失 -> 非零退出。不下载。"""
    if not os.path.exists(args.story):
        print("story.json not found, nothing to check: %s" % args.story)
        return 0

    with open(args.story, encoding="utf-8") as f:
        tree = json.load(f)

    base = args.base.rstrip("/")
    remote = []
    missing = []

    def visit(value):
        if is_remote(value):
            remote.append(value)
        elif value.startswith(base + "/"):
            fname = value[len(base) + 1:]
            if not os.path.exists(os.path.join(args.assets_dir, fname)):
                missing.append(value)
        return None

    walk_media(tree, visit)

    if remote or missing:
        print("check failed: %d remote url(s) remaining, %d local file(s) missing"
              % (len(remote), len(missing)), file=sys.stderr)
        for u in (remote + missing)[:20]:
            print("  - %s" % u, file=sys.stderr)
        return EXIT_CHECK_FAILED

    print("check ok: all media localized")
    return 0


def cmd_localize(args):
    if not os.path.exists(args.story):
        print("story.json not found, skip: %s" % args.story)
        return 0

    with open(args.story, encoding="utf-8") as f:
        tree = json.load(f)  # 解析失败直接抛异常、非零退出，不动原文件

    remote = collect_remote(tree)
    if not remote:
        print("no remote media urls, nothing to do")
        return 0

    os.makedirs(args.assets_dir, exist_ok=True)
    staging = tempfile.mkdtemp(prefix="ifg-localize-")
    backup = args.story + ".localize.bak"
    shutil.copy2(args.story, backup)

    base = args.base.rstrip("/")
    mapping = {}
    failures = {}
    deduped = 0

    try:
        with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as pool:
            futures = {pool.submit(download, url, staging, args.max_bytes): url for url in remote}
            for fut in as_completed(futures):
                url = futures[fut]
                try:
                    tmp_path, digest, ext = fut.result()
                except Exception as exc:  # noqa: BLE001
                    failures[url] = "%s: %s" % (type(exc).__name__, exc)
                    continue
                dest_name = digest + ext
                dest_path = os.path.join(args.assets_dir, dest_name)
                if os.path.exists(dest_path):
                    os.remove(tmp_path)
                    deduped += 1
                else:
                    shutil.move(tmp_path, dest_path)
                mapping[url] = base + "/" + dest_name

        if failures and not args.lenient:
            raise RuntimeError("download failed for %d url(s): %s"
                               % (len(failures), json.dumps(failures, ensure_ascii=False)))

        walk_media(tree, lambda url: mapping.get(url))

        tmp_story = args.story + ".localize.tmp"
        with open(tmp_story, "w", encoding="utf-8") as f:
            json.dump(tree, f, ensure_ascii=False, indent=2)
        os.replace(tmp_story, args.story)
        os.remove(backup)

        summary = {"total": len(remote), "downloaded": len(mapping),
                   "deduped": deduped, "failed": len(failures)}
        print(json.dumps(summary, ensure_ascii=False))
        if failures:  # 仅 lenient 会走到这里
            print("WARN kept %d unresolved url(s): %s"
                  % (len(failures), json.dumps(failures, ensure_ascii=False)), file=sys.stderr)
        return 0

    except Exception as exc:  # noqa: BLE001
        shutil.copy2(backup, args.story)
        os.remove(backup)
        print("localize failed, story.json restored unchanged: %s" % exc, file=sys.stderr)
        return 1
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description="Localize remote media URLs in an IFG story.json")
    parser.add_argument("--story", default="/workspace/frontend/public/story/story.json")
    parser.add_argument("--assets-dir", default="/workspace/frontend/public/assets/story-media")
    parser.add_argument("--base", default="../assets/story-media")
    parser.add_argument("--concurrency", type=int, default=6)
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES,
                        help="单文件下载上限（字节），默认 1 GiB；0 表示不限")
    parser.add_argument("--lenient", action="store_true",
                        help="下载失败时保留原 URL 并告警退出 0（默认严格失败）")
    parser.add_argument("--check", action="store_true",
                        help="只校验不下载：仍有外部 URL 或本地文件缺失时退出码 3")
    args = parser.parse_args()

    if args.check:
        return cmd_check(args)
    return cmd_localize(args)


if __name__ == "__main__":
    sys.exit(main())
