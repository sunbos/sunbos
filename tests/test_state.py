"""HTTP-fixture tests: no test makes a real GitHub request or write."""

import base64
import hashlib
import io
import json
import unittest
import urllib.error
import urllib.parse
import urllib.request
from unittest.mock import patch

try:
    from scripts.profile_maintenance import state as subject
except ImportError:
    subject = None


CONFIG = {
    "repository": "sunbos/sunbos",
    "base_branch": "main",
    "proposal_branch": "automation/profile-maintenance",
    "state_branch": "automation/profile-maintenance-state",
}
ROOT = "/repos/sunbos/sunbos"
BOT_SHA = "a" * 40
MAIN_SHA = "b" * 40
FILE_SHA = "c" * 40
README = "# sunbos\n已批准的介绍。\n"


def ref_path(branch):
    return ROOT + "/git/ref/heads/" + urllib.parse.quote(branch, safe="")


def contents_path(name, ref):
    return ROOT + "/contents/" + name + "?" + urllib.parse.urlencode({"ref": ref})


def pulls_path():
    return ROOT + "/pulls?" + urllib.parse.urlencode(
        {"state": "open", "head": "sunbos:" + CONFIG["proposal_branch"], "per_page": 100}
    )


def file_response(text, sha=FILE_SHA):
    raw = text.encode("utf-8")
    return {"type": "file", "encoding": "base64", "content": base64.encodebytes(raw).decode(),
            "sha": sha, "size": len(raw)}


def branch_response(branch, sha):
    return {"ref": "refs/heads/" + branch, "object": {"type": "commit", "sha": sha}}


def pull_response(sha=BOT_SHA):
    return {"number": 7, "state": "open", "head": {
        "sha": sha, "ref": CONFIG["proposal_branch"], "repo": {"full_name": CONFIG["repository"]}},
        "base": {"ref": "main", "repo": {"full_name": CONFIG["repository"]}}}


def saved_state():
    return {"schema_version": 1, "snapshot": {"sources": {}},
            "fingerprint": "d" * 64, "pr_head_sha": BOT_SHA,
            "base_readme_sha256": hashlib.sha256(README.encode()).hexdigest()}


class Response(io.BytesIO):
    def __init__(self, value, url, status=200, raw=False):
        super().__init__(value if raw else json.dumps(value).encode())
        self.url, self.status = url, status

    def geturl(self):
        return self.url


class HTTPFixture:
    def __init__(self, responses):
        self.responses = responses
        self.requests = []

    def open(self, request, timeout):
        self.requests.append(request)
        parts = urllib.parse.urlsplit(request.full_url)
        path = parts.path + (("?" + parts.query) if parts.query else "")
        key = (request.method, path)
        if key not in self.responses:
            raise AssertionError("Unexpected fixture request: " + str(key))
        value = self.responses[key]
        if isinstance(value, int):
            raise urllib.error.HTTPError(request.full_url, value, "SECRET_RESPONSE",
                                         {}, io.BytesIO(b"SECRET_RESPONSE"))
        if isinstance(value, Exception):
            raise value
        if isinstance(value, Response):
            return value
        return Response(value, request.full_url)


class StateTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(subject, "state.py has not been implemented")
        self.sleep_patch = patch("time.sleep")
        self.sleep = self.sleep_patch.start()
        self.addCleanup(self.sleep_patch.stop)

    def client(self, responses):
        fixture = HTTPFixture(responses)
        with patch("urllib.request.build_opener", return_value=fixture):
            client = subject.GitHubClient("TEST_SECRET_TOKEN")
        return client, fixture

    def absent_state(self):
        return {("GET", contents_path("state.json", CONFIG["state_branch"])): 404,
                ("GET", pulls_path()): [],
                ("GET", ref_path(CONFIG["proposal_branch"])): 404}

    def test_only_404_without_existing_proposal_is_missing_state(self):
        client, _ = self.client(self.absent_state())
        self.assertEqual(subject.load_state(client, CONFIG), (None, None))

    def test_failure_is_not_treated_as_empty_state(self):
        for failure in (403, 500, urllib.error.URLError("SECRET_RESPONSE")):
            with self.subTest(failure=type(failure).__name__):
                client, _ = self.client({("GET", contents_path("state.json", CONFIG["state_branch"])): failure})
                with self.assertRaises(subject.GitHubError) as caught:
                    subject.load_state(client, CONFIG)
                self.assertNotIn("SECRET", str(caught.exception))
                self.assertEqual(caught.exception.status, failure if isinstance(failure, int) else None)

    def test_missing_state_cannot_adopt_existing_branch_or_pr(self):
        for is_pr in (False, True):
            fixtures = self.absent_state()
            if is_pr:
                fixtures[("GET", pulls_path())] = [pull_response()]
            else:
                fixtures[("GET", ref_path(CONFIG["proposal_branch"]))] = branch_response(CONFIG["proposal_branch"], BOT_SHA)
            client, _ = self.client(fixtures)
            with self.assertRaises(subject.GitHubError):
                subject.load_state(client, CONFIG)

    def test_load_state_returns_validated_json_and_file_sha(self):
        expected = saved_state()
        client, _ = self.client({("GET", contents_path("state.json", CONFIG["state_branch"])):
                                file_response(json.dumps(expected))})
        self.assertEqual(subject.load_state(client, CONFIG), (expected, FILE_SHA))

    def invalid_states(self):
        valid = saved_state()
        return [
            {}, {"fingerprint": valid["fingerprint"]},
            {**valid, "schema_version": 2}, {**valid, "schema_version": True},
            {**valid, "fingerprint": "not-a-digest"},
            {**valid, "base_readme_sha256": "a" * 63},
            {**valid, "snapshot": []}, {**valid, "pr_head_sha": "main"},
            {**valid, "pr_head_sha": False}, {**valid, "unexpected": "field"},
            {key: value for key, value in valid.items() if key != "pr_head_sha"},
        ]

    def test_load_rejects_incomplete_or_wrong_version_state(self):
        for value in self.invalid_states():
            with self.subTest(value=value):
                client, _ = self.client({
                    ("GET", contents_path("state.json", CONFIG["state_branch"])):
                    file_response(json.dumps(value)),
                })
                with self.assertRaises(subject.GitHubError):
                    subject.load_state(client, CONFIG)

    def test_save_rejects_invalid_schema_before_any_request(self):
        for value in self.invalid_states():
            with self.subTest(value=value):
                client, fixture = self.client({
                    ("GET", ref_path(CONFIG["state_branch"])):
                    branch_response(CONFIG["state_branch"], BOT_SHA),
                    ("PUT", ROOT + "/contents/state.json"): {"content": {"sha": FILE_SHA}},
                })
                with self.assertRaises(subject.GitHubError):
                    subject.save_state(client, CONFIG, value, FILE_SHA)
                self.assertEqual(fixture.requests, [])

    def test_load_rejects_duplicate_json_keys_and_nonfinite_snapshot(self):
        valid = json.dumps(saved_state())
        values = [valid[:-1] + ', "schema_version": 1}',
                  json.dumps({**saved_state(), "snapshot": {"value": float("nan")}})]
        for raw in values:
            client, _ = self.client({
                ("GET", contents_path("state.json", CONFIG["state_branch"])): file_response(raw),
            })
            with self.assertRaises(subject.GitHubError):
                subject.load_state(client, CONFIG)

    def test_corrupt_state_is_not_missing(self):
        for content in ("[]", "null", "not-json"):
            client, _ = self.client({("GET", contents_path("state.json", CONFIG["state_branch"])): file_response(content)})
            with self.assertRaises(subject.GitHubError):
                subject.load_state(client, CONFIG)

    def test_null_http_response_is_not_404(self):
        fixtures = self.absent_state()
        fixtures[("GET", contents_path("state.json", CONFIG["state_branch"]))] = None
        client, _ = self.client(fixtures)
        with self.assertRaises(subject.GitHubError):
            subject.load_state(client, CONFIG)

    def test_save_state_uses_file_sha_and_separate_branch(self):
        new_state = saved_state()
        client, fixture = self.client({
            ("GET", ref_path(CONFIG["state_branch"])): branch_response(CONFIG["state_branch"], BOT_SHA),
            ("PUT", ROOT + "/contents/state.json"): {"content": {"sha": "d" * 40}},
        })
        subject.save_state(client, CONFIG, new_state, FILE_SHA)
        body = json.loads(fixture.requests[-1].data)
        self.assertEqual(body["sha"], FILE_SHA)
        self.assertEqual(body["branch"], CONFIG["state_branch"])
        self.assertEqual(json.loads(base64.b64decode(body["content"])), new_state)
        self.assertNotIn("force", body)

    def test_first_save_creates_state_ref_from_base_then_creates_file(self):
        client, fixture = self.client({
            ("GET", ref_path(CONFIG["state_branch"])): 404,
            ("GET", ref_path(CONFIG["base_branch"])): branch_response(CONFIG["base_branch"], MAIN_SHA),
            ("POST", ROOT + "/git/refs"): branch_response(CONFIG["state_branch"], MAIN_SHA),
            ("PUT", ROOT + "/contents/state.json"): {"content": {"sha": FILE_SHA}},
        })
        subject.save_state(client, CONFIG, {**saved_state(), "pr_head_sha": None}, None)
        self.assertEqual(json.loads(fixture.requests[-2].data),
                         {"ref": "refs/heads/" + CONFIG["state_branch"], "sha": MAIN_SHA})
        self.assertNotIn("sha", json.loads(fixture.requests[-1].data))

    def test_cas_conflict_is_not_retried_or_force_written(self):
        client, fixture = self.client({
            ("GET", ref_path(CONFIG["state_branch"])): branch_response(CONFIG["state_branch"], BOT_SHA),
            ("PUT", ROOT + "/contents/state.json"): 409,
        })
        with self.assertRaises(subject.GitHubError) as caught:
            subject.save_state(client, CONFIG, saved_state(), FILE_SHA)
        self.assertEqual(caught.exception.status, 409)
        self.assertEqual(len([r for r in fixture.requests if r.method == "PUT"]), 1)

    def test_save_requires_a_confirmed_written_file(self):
        for response in (None, {}, {"content": {"sha": "not-a-sha"}}):
            client, _ = self.client({
                ("GET", ref_path(CONFIG["state_branch"])): branch_response(CONFIG["state_branch"], BOT_SHA),
                ("PUT", ROOT + "/contents/state.json"): response,
            })
            with self.assertRaises(subject.GitHubError):
                subject.save_state(client, CONFIG, saved_state(), FILE_SHA)

    def test_first_save_requires_confirmed_ref_creation(self):
        client, fixture = self.client({
            ("GET", ref_path(CONFIG["state_branch"])): 404,
            ("GET", ref_path(CONFIG["base_branch"])): branch_response(CONFIG["base_branch"], MAIN_SHA),
            ("POST", ROOT + "/git/refs"): {},
            ("PUT", ROOT + "/contents/state.json"): {"content": {"sha": FILE_SHA}},
        })
        with self.assertRaises(subject.GitHubError):
            subject.save_state(client, CONFIG, saved_state(), None)
        self.assertFalse(any(request.method == "PUT" for request in fixture.requests))

    def test_state_branch_must_be_isolated(self):
        for branch in ("main", CONFIG["proposal_branch"]):
            config = {**CONFIG, "state_branch": branch}
            client, fixture = self.client({})
            with self.assertRaises(subject.GitHubError):
                subject.save_state(client, config, {}, None)
            self.assertEqual(fixture.requests, [])

    def proposal_fixtures(self, head=BOT_SHA):
        return {("GET", pulls_path()): [pull_response(head)],
                ("GET", ref_path(CONFIG["proposal_branch"])): branch_response(CONFIG["proposal_branch"], head),
                ("GET", contents_path("README.md", head)): file_response("# Proposed\n")}

    def test_proposal_readme_is_read_at_verified_commit(self):
        client, _ = self.client(self.proposal_fixtures())
        self.assertEqual(subject.load_proposal(client, CONFIG, saved_state(), README),
                         {"number": 7, "head_sha": BOT_SHA, "readme": "# Proposed\n"})

    def test_manual_pr_commit_is_rejected(self):
        client, fixture = self.client(self.proposal_fixtures("f" * 40))
        with self.assertRaises(subject.GitHubError):
            subject.load_proposal(client, CONFIG, saved_state(), README)
        self.assertFalse(any("/contents/" in request.full_url for request in fixture.requests))

    def test_base_readme_change_rejects_pending_proposal(self):
        client, _ = self.client(self.proposal_fixtures())
        with self.assertRaises(subject.GitHubError):
            subject.load_proposal(client, CONFIG, saved_state(), README + "manual change\n")

    def test_closed_pr_branch_with_manual_commit_is_rejected(self):
        client, _ = self.client({("GET", pulls_path()): [],
                                ("GET", ref_path(CONFIG["proposal_branch"])):
                                branch_response(CONFIG["proposal_branch"], "f" * 40)})
        with self.assertRaises(subject.GitHubError):
            subject.load_proposal(client, CONFIG, saved_state(), README)

    def test_closed_pr_unchanged_branch_returns_none(self):
        client, _ = self.client({("GET", pulls_path()): [],
                                ("GET", ref_path(CONFIG["proposal_branch"])):
                                branch_response(CONFIG["proposal_branch"], BOT_SHA)})
        self.assertIsNone(subject.load_proposal(client, CONFIG, saved_state(), README))

    def test_absent_proposal_returns_none(self):
        client, _ = self.client({("GET", pulls_path()): [],
                                ("GET", ref_path(CONFIG["proposal_branch"])): 404})
        self.assertIsNone(subject.load_proposal(client, CONFIG, None, README))

    def test_branch_changes_between_pr_lookup_and_ref_lookup_are_rejected(self):
        fixtures = self.proposal_fixtures()
        fixtures[("GET", ref_path(CONFIG["proposal_branch"]))] = branch_response(CONFIG["proposal_branch"], "e" * 40)
        client, _ = self.client(fixtures)
        with self.assertRaises(subject.GitHubError):
            subject.load_proposal(client, CONFIG, saved_state(), README)

    def test_readme_bytes_not_branch_head_control_base_guard(self):
        client, fixture = self.client({("GET", contents_path("README.md", "main")): file_response(README)})
        subject.assert_base_unchanged(client, CONFIG, README)
        self.assertEqual(len(fixture.requests), 1)

    def test_base_guard_detects_even_line_ending_change(self):
        client, _ = self.client({("GET", contents_path("README.md", "main")): file_response(README.replace("\n", "\r\n"))})
        with self.assertRaises(subject.GitHubError):
            subject.assert_base_unchanged(client, CONFIG, README)

    def test_fingerprint_is_order_independent_but_sensitive_to_evidence_and_policy(self):
        a = subject.fingerprint(CONFIG, {"b": 2, "a": 1}, "protected")
        b = subject.fingerprint(dict(reversed(list(CONFIG.items()))), {"a": 1, "b": 2}, "protected")
        self.assertEqual(a, b)
        self.assertEqual(len(a), 64)
        self.assertNotEqual(a, subject.fingerprint(CONFIG, {"a": 1, "b": 3}, "protected"))
        self.assertNotEqual(a, subject.fingerprint({**CONFIG, "model": "different"}, {"a": 1, "b": 2}, "protected"))
        self.assertNotEqual(a, subject.fingerprint(CONFIG, {"a": 1, "b": 2}, "changed"))

    def test_client_only_accepts_official_relative_paths(self):
        client, fixture = self.client({})
        for path in ("https://api.github.com/user", "https://evil.test", "//evil.test/path",
                     "/\\evil.test", "/repos/x/y#fragment", "/repos/x/../y", "/repos/%2e%2e/user"):
            with self.subTest(path=path), self.assertRaises(subject.GitHubError):
                client.get(path)
        self.assertEqual(fixture.requests, [])

    def test_client_headers_and_method_are_bounded(self):
        client, fixture = self.client({("GET", "/user"): {"login": "sunbos"}})
        self.assertEqual(client.get("/user"), {"login": "sunbos"})
        self.assertEqual(fixture.requests[0].full_url, "https://api.github.com/user")
        self.assertEqual(fixture.requests[0].get_header("Authorization"), "Bearer TEST_SECRET_TOKEN")
        with self.assertRaises(subject.GitHubError):
            client.write("TRACE", "/user", {})

    def test_get_retries_one_transient_failure_then_returns_data(self):
        errors = [urllib.error.URLError("SECRET_RESPONSE"), TimeoutError("SECRET_RESPONSE"),
                  urllib.error.HTTPError("https://api.github.com/user", 429, "SECRET_RESPONSE", {}, None),
                  urllib.error.HTTPError("https://api.github.com/user", 503, "SECRET_RESPONSE", {}, None)]
        for failure in errors:
            with self.subTest(failure=type(failure).__name__):
                self.sleep.reset_mock()
                client, fixture = self.client({})
                response = Response({"login": "sunbos"}, "https://api.github.com/user")
                with patch.object(fixture, "open", side_effect=[failure, response]) as opened:
                    self.assertEqual(client.get("/user"), {"login": "sunbos"})
                    self.assertEqual(opened.call_count, 2)
                    self.sleep.assert_called_once_with(1)

    def test_get_never_makes_more_than_two_attempts(self):
        client, fixture = self.client({})
        with patch.object(fixture, "open", side_effect=TimeoutError("SECRET_RESPONSE")) as opened:
            with self.assertRaises(subject.GitHubError) as caught:
                client.get("/user")
            self.assertEqual(opened.call_count, 2)
            self.sleep.assert_called_once_with(1)
            self.assertIn("TimeoutError", str(caught.exception))
            self.assertNotIn("SECRET", str(caught.exception))

    def test_get_does_not_retry_nontransient_http_or_invalid_json(self):
        for failure in (400, 403, 404, Response(b"SECRET_RESPONSE", "https://api.github.com/user", raw=True)):
            with self.subTest(failure=type(failure).__name__):
                self.sleep.reset_mock()
                client, fixture = self.client({("GET", "/user"): failure})
                with self.assertRaises(subject.GitHubError) as caught:
                    client.get("/user")
                self.assertEqual(len(fixture.requests), 1)
                self.sleep.assert_not_called()
                expected = "HTTP " + str(failure) if isinstance(failure, int) else "JSON"
                self.assertIn(expected, str(caught.exception))
                self.assertNotIn("SECRET", str(caught.exception))

    def test_writes_never_retry_transient_failures(self):
        for method in ("PUT", "POST"):
            for failure in (503, TimeoutError("SECRET_RESPONSE")):
                with self.subTest(method=method, failure=type(failure).__name__):
                    self.sleep.reset_mock()
                    client, fixture = self.client({(method, "/user"): failure})
                    with self.assertRaises(subject.GitHubError):
                        client.write(method, "/user", {})
                    self.assertEqual(len(fixture.requests), 1)
                    self.sleep.assert_not_called()

    def test_client_rejects_redirects_without_forwarding_credentials(self):
        with patch("urllib.request.build_opener", wraps=urllib.request.build_opener) as build:
            subject.GitHubClient("TEST_SECRET_TOKEN")
        handler = next(arg for arg in build.call_args.args if isinstance(arg, urllib.request.HTTPRedirectHandler))
        request = urllib.request.Request("https://api.github.com/user", headers={"Authorization": "Bearer TEST_SECRET_TOKEN"})
        with self.assertRaises(subject.GitHubError) as caught:
            handler.redirect_request(request, None, 302, "SECRET_RESPONSE", {}, "https://evil.test")
        self.assertNotIn("SECRET", str(caught.exception))

    def test_client_rejects_invalid_json_and_oversized_responses(self):
        for raw in (b"SECRET_RESPONSE", b" " * (subject.MAX_RESPONSE_BYTES + 1)):
            client, _ = self.client({("GET", "/user"): Response(raw, "https://api.github.com/user", raw=True)})
            with self.assertRaises(subject.GitHubError) as caught:
                client.get("/user")
            self.assertNotIn("SECRET", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
