"""Collect bounded, commit-pinned evidence from explicitly public GitHub sources."""

import base64
import binascii
import hashlib
import re
from urllib.parse import quote


DEFAULT_FILE_CHARS = 8000
MAX_FILE_CHARS = 12000
MAX_BLOB_BYTES = 1024 * 1024
MAX_SOURCES = 12
MAX_FILES = 40
_REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
_IDENTIFIER = re.compile(r"[A-Za-z0-9_-]+\Z")
_SHA = re.compile(r"[0-9a-f]{40}\Z")


def _sha(value):
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise ValueError("GitHub returned an invalid object SHA")
    return value


def _repo_name(value):
    if not isinstance(value, str) or not _REPO.fullmatch(value):
        raise ValueError("Source must name one GitHub owner/repository")
    if any(part in {".", ".."} for part in value.split("/")):
        raise ValueError("Invalid GitHub repository name")
    return value


def _sources(config):
    sources = config.get("sources")
    if not isinstance(sources, list) or not 1 <= len(sources) <= MAX_SOURCES:
        raise ValueError("Between one and twelve explicit public sources are required")
    seen = set()
    file_count = 0
    for source in sources:
        if not isinstance(source, dict):
            raise ValueError("Invalid source configuration")
        identifier = source.get("id")
        if not isinstance(identifier, str) or not _IDENTIFIER.fullmatch(identifier) or identifier in seen:
            raise ValueError("Source IDs must be valid and unique")
        seen.add(identifier)
        _repo_name(source.get("repo"))
        if ("ref" in source) == ("pull" in source):
            raise ValueError("Each source must select either a ref or a pull request")
        if "pull" in source:
            if type(source["pull"]) is not int or source["pull"] < 1:
                raise ValueError("Invalid pull request number")
            author = source.get("expected_author", "sunbos")
            if not isinstance(author, str) or not author:
                raise ValueError("An expected pull request author is required")
        elif not isinstance(source["ref"], str) or not source["ref"]:
            raise ValueError("A source ref is required")
        paths = source.get("paths")
        if not isinstance(paths, list) or not paths:
            raise ValueError("Each source needs exact file paths")
        file_count += len(paths)
        if file_count > MAX_FILES:
            raise ValueError("At most forty source files may be collected")
        seen_paths = set()
        for path in paths:
            if (not isinstance(path, str) or not path or len(path) > 1024
                    or any(part in {"", ".", ".."} for part in path.split("/"))
                    or any(char in path for char in "\\*?[]")
                    or any(ord(char) < 32 for char in path) or path in seen_paths):
                raise ValueError("Source paths must be unique, exact repository-relative files")
            seen_paths.add(path)
        excerpts = source.get("excerpts", {})
        if not isinstance(excerpts, dict):
            raise ValueError("Source excerpts must map file paths to anchors")
        for path, anchor in excerpts.items():
            if path not in seen_paths or not isinstance(anchor, str) or not anchor or len(anchor) > 1024:
                raise ValueError("Invalid source excerpt anchor")
    return sources


def _public_repo(get_json, repo):
    metadata = get_json(f"repos/{repo}")
    if (not isinstance(metadata, dict) or metadata.get("private") is not False
            or metadata.get("visibility") != "public"
            or str(metadata.get("full_name", "")).casefold() != repo.casefold()):
        raise ValueError("Source repository is not explicitly verified public")
    return metadata


def _pull_facts(pull, source):
    if not isinstance(pull, dict) or pull.get("number") != source["pull"]:
        raise ValueError("Invalid pull request response")
    author = (pull.get("user") or {}).get("login")
    if not isinstance(author, str) or author.casefold() != source.get("expected_author", "sunbos").casefold():
        raise ValueError("Pull request author does not match the expected contributor")
    facts = {"state": pull.get("state"), "merged": pull.get("merged"),
             "draft": pull.get("draft"), "author": author}
    if (facts["state"] not in {"open", "closed"}
            or type(facts["merged"]) is not bool or type(facts["draft"]) is not bool
            or (facts["merged"] and facts["state"] != "closed")):
        raise ValueError("Incomplete or inconsistent pull request facts")
    return facts


def _tree(get_json, repo, tree_sha):
    result = get_json(f"repos/{repo}/git/trees/{tree_sha}?recursive=1")
    if (not isinstance(result, dict) or result.get("sha") != tree_sha
            or result.get("truncated") is not False or not isinstance(result.get("tree"), list)):
        raise ValueError("A complete Git tree is required to prove file presence or deletion")
    entries = {}
    for entry in result["tree"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str) or entry["path"] in entries:
            raise ValueError("Invalid or duplicate Git tree entry")
        entries[entry["path"]] = entry
    return entries


def _blob_text(get_json, repo, sha):
    result = get_json(f"repos/{repo}/git/blobs/{sha}")
    if (not isinstance(result, dict) or result.get("sha") != sha
            or result.get("encoding") != "base64" or not isinstance(result.get("content"), str)
            or type(result.get("size")) is not int or not 0 <= result["size"] <= MAX_BLOB_BYTES):
        raise ValueError("Source blob is unsupported, oversized or incomplete")
    try:
        raw = base64.b64decode("".join(result["content"].split()), validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("Source blob has invalid base64 encoding") from exc
    digest = hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()
    if len(raw) != result["size"] or digest != sha:
        raise ValueError("Source blob size or content does not match its Git object")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Source file is not valid UTF-8 text") from exc


def _excerpt(path, content, anchor, context, limit):
    # GitHub source line numbers follow LF, including CRLF files. Unicode
    # separators inside a string literal must not create extra source lines.
    lines = content.split("\n") if content else []
    if lines and lines[-1] == "":
        lines.pop()
    lines = [line.removesuffix("\r") for line in lines]
    start = 0
    note = ""
    if anchor:
        position = content.find(anchor)
        if position < 0:
            note = "锚点未找到，改从文件开头节选；不能据此判断能力消失。\n"
        else:
            start = content[:position].count("\n")
    header = f"文件：{path}\n{context}\n{note}"
    body = "\n".join(f"L{index + 1}: {line}" for index, line in enumerate(lines[start:], start))
    if not lines:
        body = "（文件为空）"
    suffix = "\n[已截断：只展示上述源码节选，未展示部分不能视为不存在。]"
    truncated = start > 0 or len(header) + len(body) > limit
    if truncated:
        body = body[:max(0, limit - len(header) - len(suffix))]
        return header + body + suffix
    return header + body


def collect(config, get_json):
    """Return stable file/PR facts and bounded evidence; API errors fail closed.

    Missing selected paths are represented by ``None`` only after a complete
    commit-pinned tree proves their absence. A 404, including a missing blob
    after a tree match, is an API failure and is deliberately not intercepted.
    """
    sources = _sources(config)
    limit = config.get("evidence_file_chars", DEFAULT_FILE_CHARS)
    if type(limit) is not int or not 2000 <= limit <= MAX_FILE_CHARS:
        raise ValueError("Evidence file character limit must be between 2000 and 12000")
    snapshot = {"sources": {}}
    evidence = []
    for source in sources:
        source_id, repo = source["id"], source["repo"]
        metadata = _public_repo(get_json, repo)
        facts = None
        code_repo = repo
        if "pull" in source:
            pull = get_json(f"repos/{repo}/pulls/{source['pull']}")
            facts = _pull_facts(pull, source)
            head = pull.get("head") or {}
            code_repo = _repo_name((head.get("repo") or {}).get("full_name"))
            _public_repo(get_json, code_repo)
            ref = _sha(head.get("sha"))
            context = (f"PR #{source['pull']}：state={facts['state']}; merged={facts['merged']}; "
                       f"draft={facts['draft']}; author={facts['author']}。PR 作者身份不等于逐行贡献归属。")
        else:
            ref = metadata.get("default_branch") if source["ref"] == "default" else source["ref"]
            if not isinstance(ref, str) or not ref:
                raise ValueError("Source default branch is unavailable")
            context = f"公开仓库：{repo}；配置引用：{source['ref']}。源码存在不等于已发布或全部由本人实现。"
        commit = get_json(f"repos/{code_repo}/commits/{quote(ref, safe='')}")
        if not isinstance(commit, dict):
            raise ValueError("Invalid source commit response")
        commit_sha = _sha(commit.get("sha"))
        if facts is not None and commit_sha != ref:
            raise ValueError("Resolved commit does not match the pull request head")
        tree_sha = _sha((commit.get("commit") or {}).get("tree", {}).get("sha"))
        entries = _tree(get_json, code_repo, tree_sha)
        source_snapshot = {"files": {}}
        if facts is not None:
            source_snapshot["pull"] = facts
            evidence.append({
                "id": f"{source_id}:pull", "source_id": source_id,
                "url": f"https://github.com/{repo}/pull/{source['pull']}",
                "text": f"{context}\n本轮读取的 head commit：{commit_sha}。",
            })
        for path in sorted(source["paths"]):
            entry = entries.get(path)
            if entry is None:
                source_snapshot["files"][path] = None
                evidence.append({
                    "id": f"{source_id}:file:{path}", "source_id": source_id,
                    "url": f"https://github.com/{code_repo}/tree/{commit_sha}",
                    "text": f"文件：{path}\n{context}\n该路径在此提交的完整 Git tree 中不存在；不据此推断功能是否迁移或消失。",
                })
                continue
            if entry.get("type") != "blob" or entry.get("mode") not in {"100644", "100755"}:
                raise ValueError("Selected path is not a regular source file")
            blob_sha = _sha(entry.get("sha"))
            content = _blob_text(get_json, code_repo, blob_sha)
            source_snapshot["files"][path] = blob_sha
            evidence.append({
                "id": f"{source_id}:file:{path}", "source_id": source_id,
                "url": f"https://github.com/{code_repo}/blob/{commit_sha}/{quote(path, safe='/')}",
                "text": _excerpt(path, content, source.get("excerpts", {}).get(path), context, limit),
            })
        snapshot["sources"][source_id] = source_snapshot
    return {"snapshot": snapshot, "evidence": evidence}
