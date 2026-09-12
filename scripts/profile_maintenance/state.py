"""Durable review state and conservative protection of the bot's PR branch."""

import base64
import binascii
import hashlib
import http.client
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request


MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_FILE_BYTES = 1024 * 1024
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")


class GitHubError(RuntimeError):
    """A safe error with an optional HTTP status, never a raw response body."""

    def __init__(self, message="GitHub operation failed", status=None, *, retryable=False):
        super().__init__(message)
        self.status = status
        self.retryable = retryable


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise GitHubError("GitHub API redirects are not allowed", status=code)


class GitHubClient:
    """Bounded official API access; only a transient GET may be retried once."""

    def __init__(self, token):
        if not isinstance(token, str) or any(ord(char) < 32 for char in token):
            raise GitHubError("Invalid GitHub token configuration")
        self._token = token
        self._opener = urllib.request.build_opener(_NoRedirect())

    def get(self, path):
        try:
            return self._request("GET", path, None)
        except GitHubError as error:
            if not error.retryable:
                raise
        time.sleep(1)
        return self._request("GET", path, None)

    def write(self, method, path, payload):
        if method not in {"POST", "PUT", "PATCH", "DELETE"}:
            raise GitHubError("Unsupported GitHub write method")
        if not self._token:
            raise GitHubError("A GitHub token is required for writes")
        return self._request(method, path, payload)

    def _request(self, method, path, payload):
        if not isinstance(path, str) or not path.startswith("/") or path.startswith("//"):
            raise GitHubError("GitHub API requires a relative path")
        parts = urllib.parse.urlsplit(path)
        decoded_path = urllib.parse.unquote(parts.path)
        if (parts.scheme or parts.netloc or parts.fragment or "\\" in path
                or "\\" in decoded_path or decoded_path.startswith("//")
                or any(segment in {".", ".."} for segment in decoded_path.split("/"))
                or any(ord(char) < 32 or ord(char) == 127 for char in path + decoded_path)):
            raise GitHubError("Invalid GitHub API path")
        url = "https://api.github.com" + path
        headers = {"Accept": "application/vnd.github+json",
                   "X-GitHub-Api-Version": "2026-03-10",
                   "User-Agent": "sunbos-profile-maintenance"}
        if self._token:
            headers["Authorization"] = "Bearer " + self._token
        data = None
        if payload is not None:
            data = _json_bytes(payload)
            headers["Content-Type"] = "application/json"
        try:
            request = urllib.request.Request(url, data=data, headers=headers, method=method)
            with self._opener.open(request, timeout=30) as response:
                if response.geturl() != url:
                    raise GitHubError("Unexpected GitHub API response URL")
                if not 200 <= response.status < 300:
                    raise GitHubError("GitHub API request failed (HTTP " + str(response.status) + ")",
                                      status=response.status,
                                      retryable=response.status == 429 or 500 <= response.status < 600)
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as error:
            raise GitHubError("GitHub API request failed (HTTP " + str(error.code) + ")",
                              status=error.code,
                              retryable=error.code == 429 or 500 <= error.code < 600) from None
        except OSError as error:
            raise GitHubError("GitHub network request failed (" + type(error).__name__ + ")",
                              retryable=True) from None
        except (ValueError, http.client.HTTPException):
            raise GitHubError("GitHub API request or HTTP response was invalid") from None
        if len(raw) > MAX_RESPONSE_BYTES:
            raise GitHubError("GitHub API response exceeds the size limit")
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (ValueError, RecursionError):
            raise GitHubError("GitHub API returned invalid JSON") from None


def _json_bytes(value):
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                          allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, RecursionError):
        raise GitHubError("Invalid JSON data") from None


def _root(config):
    repository = config.get("repository")
    branches = [config.get(name) for name in ("base_branch", "proposal_branch", "state_branch")]
    if not isinstance(repository, str) or not _REPOSITORY.fullmatch(repository):
        raise GitHubError("Invalid repository configuration")
    if any(not isinstance(branch, str) or not branch or branch != branch.strip()
           or any(char in branch for char in "~^:?*[\\") or ".." in branch
           or "@{" in branch or branch.startswith("/") or branch.endswith(("/", ".", ".lock"))
           or "//" in branch or any(ord(char) < 33 or ord(char) == 127 for char in branch)
           for branch in branches):
        raise GitHubError("Invalid maintenance branch configuration")
    if len(set(branches)) != 3:
        raise GitHubError("State, proposal and base branches must be separate")
    return "/repos/" + repository


def _ref_path(root, branch):
    return root + "/git/ref/heads/" + urllib.parse.quote(branch, safe="")


def _contents_path(root, name, ref):
    return root + "/contents/" + name + "?" + urllib.parse.urlencode({"ref": ref})


def _optional_get(client, path):
    try:
        response = client.get(path)
        if response is None:
            raise GitHubError("Unexpected empty GitHub API response")
        return response
    except GitHubError as error:
        if error.status == 404:
            return None
        raise


def _branch_sha(response, branch):
    if (not isinstance(response, dict) or response.get("ref") != "refs/heads/" + branch
            or not isinstance(response.get("object"), dict)
            or response["object"].get("type") != "commit"
            or not isinstance(response["object"].get("sha"), str)
            or not _SHA.fullmatch(response["object"]["sha"])):
        raise GitHubError("Invalid branch reference response")
    return response["object"]["sha"]


def _file(response):
    if (not isinstance(response, dict) or response.get("type") != "file"
            or response.get("encoding") != "base64"
            or not isinstance(response.get("content"), str)
            or not isinstance(response.get("sha"), str) or not _SHA.fullmatch(response["sha"])):
        raise GitHubError("Expected a complete GitHub file response")
    try:
        raw = base64.b64decode("".join(response["content"].split()), validate=True)
    except (ValueError, binascii.Error):
        raise GitHubError("Invalid GitHub file encoding") from None
    if len(raw) > MAX_FILE_BYTES or response.get("size") != len(raw):
        raise GitHubError("GitHub file is truncated or exceeds the size limit")
    return raw, response["sha"]


def _open_proposals(client, config, root):
    owner = config["repository"].split("/")[0]
    query = urllib.parse.urlencode({"state": "open", "head": owner + ":" + config["proposal_branch"],
                                    "per_page": 100})
    pulls = client.get(root + "/pulls?" + query)
    if not isinstance(pulls, list) or len(pulls) > 1:
        raise GitHubError("Expected at most one maintenance pull request")
    return pulls


def _validate_state(state):
    fields = {"schema_version", "fingerprint", "snapshot", "base_readme_sha256", "pr_head_sha"}
    if (not isinstance(state, dict) or set(state) != fields
            or type(state["schema_version"]) is not int or state["schema_version"] != 1
            or not isinstance(state["snapshot"], dict)
            or any(not isinstance(state[key], str) or not _SHA256.fullmatch(state[key])
                   for key in ("fingerprint", "base_readme_sha256"))
            or (state["pr_head_sha"] is not None and
                (not isinstance(state["pr_head_sha"], str) or not _SHA.fullmatch(state["pr_head_sha"])))):
        raise GitHubError("Invalid or unsupported maintenance state schema")


def _load_state_json(raw):
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate state key")
            result[key] = value
        return result

    def reject_constant(_):
        raise ValueError("Non-finite state value")

    try:
        state = json.loads(raw, object_pairs_hook=unique_object, parse_constant=reject_constant)
    except (ValueError, RecursionError):
        raise GitHubError("Invalid maintenance state JSON") from None
    _validate_state(state)
    return state


def load_state(client, config):
    """A missing ledger is safe only when no existing bot work can be overwritten."""
    root = _root(config)
    response = _optional_get(client, _contents_path(root, "state.json", config["state_branch"]))
    if response is None:
        if _open_proposals(client, config, root):
            raise GitHubError("Existing maintenance PR has no trusted state")
        if _optional_get(client, _ref_path(root, config["proposal_branch"])) is not None:
            raise GitHubError("Existing maintenance branch has no trusted state")
        return None, None
    raw, file_sha = _file(response)
    return _load_state_json(raw), file_sha


def save_state(client, config, state, file_sha):
    """Create/update state.json with Contents API CAS; conflicts are never retried."""
    root = _root(config)
    _validate_state(state)
    if file_sha is not None and (not isinstance(file_sha, str) or not _SHA.fullmatch(file_sha)):
        raise GitHubError("Invalid maintenance file SHA")
    raw = _json_bytes(state) + b"\n"
    if len(raw) > MAX_FILE_BYTES:
        raise GitHubError("Maintenance state exceeds the size limit")
    branch = config["state_branch"]
    ref = _optional_get(client, _ref_path(root, branch))
    if ref is None:
        if file_sha is not None:
            raise GitHubError("Previously saved state branch is missing")
        base = client.get(_ref_path(root, config["base_branch"]))
        base_sha = _branch_sha(base, config["base_branch"])
        created = client.write("POST", root + "/git/refs", {"ref": "refs/heads/" + branch, "sha": base_sha})
        if _branch_sha(created, branch) != base_sha:
            raise GitHubError("Created state branch does not match the requested base")
    else:
        _branch_sha(ref, branch)
    payload = {"message": "chore: record profile maintenance review",
               "content": base64.b64encode(raw).decode("ascii"), "branch": branch}
    if file_sha is not None:
        payload["sha"] = file_sha
    result = client.write("PUT", root + "/contents/state.json", payload)
    if (not isinstance(result, dict) or not isinstance(result.get("content"), dict)
            or not isinstance(result["content"].get("sha"), str)
            or not _SHA.fullmatch(result["content"]["sha"])):
        raise GitHubError("State write did not return a confirmed file SHA")
    return result


def _readme_bytes(readme):
    if isinstance(readme, bytes):
        return readme
    if isinstance(readme, str):
        return readme.encode("utf-8")
    raise GitHubError("README must be text or bytes")


def load_proposal(client, config, state, base_readme):
    """Only resume a PR whose current branch head matches the saved bot head."""
    root = _root(config)
    pulls = _open_proposals(client, config, root)
    branch = _optional_get(client, _ref_path(root, config["proposal_branch"]))
    branch_sha = _branch_sha(branch, config["proposal_branch"]) if branch is not None else None
    expected = state.get("pr_head_sha") if isinstance(state, dict) else None
    if branch_sha is not None and branch_sha != expected:
        raise GitHubError("Maintenance branch changed outside the saved review")
    if not pulls:
        return None
    pr = pulls[0]
    if not isinstance(pr, dict):
        raise GitHubError("Invalid maintenance PR response")
    head, base = pr.get("head"), pr.get("base")
    if (not isinstance(head, dict) or not isinstance(base, dict)
            or not isinstance(head.get("repo"), dict) or not isinstance(base.get("repo"), dict)
            or head["repo"].get("full_name") != config["repository"]
            or base["repo"].get("full_name") != config["repository"]
            or head.get("ref") != config["proposal_branch"] or base.get("ref") != config["base_branch"]
            or pr.get("state") != "open" or type(pr.get("number")) is not int or pr["number"] < 1
            or not expected or head.get("sha") != expected or branch_sha != expected):
        raise GitHubError("Maintenance PR does not match the saved branch state")
    if hashlib.sha256(_readme_bytes(base_readme)).hexdigest() != state.get("base_readme_sha256"):
        raise GitHubError("Base README changed while a maintenance PR was pending")
    raw, _ = _file(client.get(_contents_path(root, "README.md", expected)))
    try:
        readme = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise GitHubError("Maintenance README is not UTF-8") from None
    return {"number": pr["number"], "head_sha": expected, "readme": readme}


def assert_base_unchanged(client, config, base_readme):
    """Compare README bytes, allowing unrelated asset commits on the base branch."""
    root = _root(config)
    raw, _ = _file(client.get(_contents_path(root, "README.md", config["base_branch"])))
    if raw != _readme_bytes(base_readme):
        raise GitHubError("Base README changed during maintenance")


def fingerprint(config, snapshot, protected):
    """Hash semantic inputs only; no timestamp or run identifier is added."""
    return hashlib.sha256(_json_bytes({"version": 1, "config": config,
                                      "snapshot": snapshot, "protected": protected})).hexdigest()
