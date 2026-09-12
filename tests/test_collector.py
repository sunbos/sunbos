import base64
import copy
import hashlib
import unittest
from urllib.error import HTTPError

from scripts.profile_maintenance.collector import collect


def blob_payload(text):
    raw = text.encode("utf-8") if isinstance(text, str) else text
    sha = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    return {
        "sha": sha,
        "size": len(raw),
        "encoding": "base64",
        "content": base64.encodebytes(raw).decode("ascii"),
    }


class GitHubFixture:
    def __init__(self, text="print('hello')\n", head="a" * 40, pull=None):
        self.calls = []
        self.repo = "sunbos/demo"
        self.head = head
        self.tree_sha = "b" * 40
        self.file_path = "src/example.py"
        self.blob = blob_payload(text)
        self.source = {
            "id": "demo",
            "repo": self.repo,
            "paths": [self.file_path],
        }
        self.routes = {
            f"repos/{self.repo}": {
                "full_name": self.repo,
                "private": False,
                "visibility": "public",
                "default_branch": "main",
                "stargazers_count": 1,
            },
            f"repos/{self.repo}/commits/main": {
                "sha": head,
                "commit": {"tree": {"sha": self.tree_sha}},
            },
            f"repos/{self.repo}/git/trees/{self.tree_sha}?recursive=1": {
                "sha": self.tree_sha,
                "truncated": False,
                "tree": [{"path": self.file_path, "type": "blob", "mode": "100644", "sha": self.blob["sha"]}],
            },
            f"repos/{self.repo}/git/blobs/{self.blob['sha']}": self.blob,
        }
        if pull is None:
            self.source["ref"] = "default"
        else:
            self.source.update({"pull": pull, "expected_author": "sunbos"})
            self.routes[f"repos/{self.repo}/pulls/{pull}"] = {
                "number": pull,
                "state": "open",
                "merged": False,
                "draft": True,
                "user": {"login": "sunbos"},
                "head": {"sha": head, "repo": {"full_name": self.repo}},
            }
            self.routes[f"repos/{self.repo}/commits/{head}"] = self.routes[f"repos/{self.repo}/commits/main"]

    @property
    def config(self):
        return {"sources": [self.source]}

    @property
    def tree(self):
        return self.routes[f"repos/{self.repo}/git/trees/{self.tree_sha}?recursive=1"]

    @property
    def pr(self):
        return self.routes[f"repos/{self.repo}/pulls/{self.source['pull']}"]

    def get(self, path):
        self.calls.append(path)
        value = self.routes[path]
        if isinstance(value, Exception):
            raise value
        return copy.deepcopy(value)


class CollectorTests(unittest.TestCase):
    def test_unselected_changes_and_counters_do_not_change_snapshot(self):
        first = GitHubFixture()
        second = GitHubFixture(head="c" * 40)
        second.routes[f"repos/{second.repo}"]["stargazers_count"] = 999
        second.tree["tree"].append({"path": "unselected.md", "type": "blob", "sha": "d" * 40})
        self.assertEqual(collect(first.config, first.get)["snapshot"], collect(second.config, second.get)["snapshot"])

    def test_selected_file_change_changes_snapshot(self):
        first, second = GitHubFixture(), GitHubFixture("print('changed')\n")
        self.assertNotEqual(collect(first.config, first.get)["snapshot"], collect(second.config, second.get)["snapshot"])

    def test_evidence_has_pinned_commit_path_and_line_numbers(self):
        fixture = GitHubFixture()
        result = collect(fixture.config, fixture.get)
        evidence = result["evidence"][0]
        self.assertEqual(set(evidence), {"id", "source_id", "url", "text"})
        self.assertEqual(evidence["source_id"], "demo")
        self.assertEqual(evidence["url"], f"https://github.com/sunbos/demo/blob/{fixture.head}/src/example.py")
        self.assertIn("src/example.py", evidence["text"])
        self.assertIn("L1: print('hello')", evidence["text"])
        self.assertNotIn(fixture.head, str(result["snapshot"]))

    def test_named_branch_is_resolved_with_encoded_ref(self):
        fixture = GitHubFixture()
        fixture.source["ref"] = "feat/contract"
        fixture.routes[f"repos/{fixture.repo}/commits/feat%2Fcontract"] = fixture.routes.pop(f"repos/{fixture.repo}/commits/main")
        collect(fixture.config, fixture.get)
        self.assertIn(f"repos/{fixture.repo}/commits/feat%2Fcontract", fixture.calls)

    def test_private_source_is_rejected_before_content_reads(self):
        fixture = GitHubFixture()
        fixture.routes[f"repos/{fixture.repo}"].update(private=True, visibility="private")
        with self.assertRaises(ValueError):
            collect(fixture.config, fixture.get)
        self.assertEqual(fixture.calls, [f"repos/{fixture.repo}"])

    def test_missing_visibility_is_not_assumed_public(self):
        fixture = GitHubFixture()
        fixture.routes[f"repos/{fixture.repo}"].pop("visibility")
        with self.assertRaises(ValueError):
            collect(fixture.config, fixture.get)
        self.assertEqual(fixture.calls, [f"repos/{fixture.repo}"])

    def test_private_pr_head_repository_is_rejected_before_content_reads(self):
        fixture = GitHubFixture(pull=10)
        fixture.pr["head"]["repo"]["full_name"] = "sunbos/private-head"
        fixture.routes["repos/sunbos/private-head"] = {
            "full_name": "sunbos/private-head", "private": True, "visibility": "private"
        }
        with self.assertRaises(ValueError):
            collect(fixture.config, fixture.get)
        self.assertFalse(any("/commits/" in path or "/git/" in path for path in fixture.calls))

    def test_public_pr_fork_is_verified_and_used_for_pinned_code(self):
        fixture = GitHubFixture(pull=10)
        fork = "sunbos/public-fork"
        fixture.pr["head"]["repo"]["full_name"] = fork
        fixture.routes[f"repos/{fork}"] = {
            "full_name": fork, "private": False, "visibility": "public"
        }
        for suffix in [f"commits/{fixture.head}", f"git/trees/{fixture.tree_sha}?recursive=1", f"git/blobs/{fixture.blob['sha']}"]:
            fixture.routes[f"repos/{fork}/{suffix}"] = fixture.routes.pop(f"repos/{fixture.repo}/{suffix}")
        result = collect(fixture.config, fixture.get)
        file_item = next(item for item in result["evidence"] if ":file:" in item["id"])
        self.assertEqual(file_item["url"], f"https://github.com/{fork}/blob/{fixture.head}/{fixture.file_path}")
        self.assertLess(fixture.calls.index(f"repos/{fork}"), fixture.calls.index(f"repos/{fork}/commits/{fixture.head}"))

    def test_unavailable_pr_head_repository_fails_closed(self):
        fixture = GitHubFixture(pull=10)
        fixture.pr["head"]["repo"] = None
        with self.assertRaises(ValueError):
            collect(fixture.config, fixture.get)

    def test_pr_author_must_match_expected_contributor(self):
        fixture = GitHubFixture(pull=10)
        fixture.pr["user"]["login"] = "someone-else"
        with self.assertRaises(ValueError):
            collect(fixture.config, fixture.get)
        self.assertFalse(any("/commits/" in path or "/git/" in path for path in fixture.calls))

    def test_pr_open_closed_and_merged_are_distinct(self):
        snapshots = []
        for state, merged in [("open", False), ("closed", False), ("closed", True)]:
            fixture = GitHubFixture(pull=10)
            fixture.pr.update(state=state, merged=merged)
            result = collect(fixture.config, fixture.get)
            facts = result["snapshot"]["sources"]["demo"]["pull"]
            self.assertEqual(facts, {"state": state, "merged": merged, "draft": True, "author": "sunbos"})
            self.assertTrue(any(item["url"] == "https://github.com/sunbos/demo/pull/10" for item in result["evidence"]))
            snapshots.append(result["snapshot"])
        self.assertNotEqual(snapshots[0], snapshots[1])
        self.assertNotEqual(snapshots[1], snapshots[2])

    def test_pr_draft_change_is_tracked(self):
        fixture = GitHubFixture(pull=10)
        before = collect(fixture.config, fixture.get)["snapshot"]
        fixture.pr["draft"] = False
        self.assertNotEqual(before, collect(fixture.config, fixture.get)["snapshot"])

    def test_absence_in_complete_tree_is_explicit_deletion(self):
        fixture = GitHubFixture()
        fixture.tree["tree"] = []
        result = collect(fixture.config, fixture.get)
        self.assertIsNone(result["snapshot"]["sources"]["demo"]["files"]["src/example.py"])
        self.assertIn("不存在", result["evidence"][0]["text"])
        self.assertFalse(any("/git/blobs/" in path for path in fixture.calls))

    def test_truncated_tree_never_proves_deletion(self):
        fixture = GitHubFixture()
        fixture.tree.update(truncated=True, tree=[])
        with self.assertRaises(ValueError):
            collect(fixture.config, fixture.get)

    def test_api_failures_are_not_deletions(self):
        for status in (404, 403, 500):
            with self.subTest(status=status):
                fixture = GitHubFixture()
                route = f"repos/{fixture.repo}/git/trees/{fixture.tree_sha}?recursive=1"
                fixture.routes[route] = HTTPError("https://api.github.com/", status, "failure", {}, None)
                with self.assertRaises(HTTPError):
                    collect(fixture.config, fixture.get)

    def test_missing_blob_after_tree_match_is_failure(self):
        fixture = GitHubFixture()
        fixture.routes[f"repos/{fixture.repo}/git/blobs/{fixture.blob['sha']}"] = HTTPError("https://api.github.com/", 404, "failure", {}, None)
        with self.assertRaises(HTTPError):
            collect(fixture.config, fixture.get)

    def test_network_failure_is_not_deletion(self):
        fixture = GitHubFixture()
        fixture.routes[f"repos/{fixture.repo}"] = TimeoutError("unavailable")
        with self.assertRaises(TimeoutError):
            collect(fixture.config, fixture.get)

    def test_invalid_or_incomplete_blob_is_rejected(self):
        for change in ({"content": "not-base64!"}, {"content": ""}, {"size": 999}, {"encoding": "none"}):
            with self.subTest(change=change):
                fixture = GitHubFixture()
                fixture.blob.update(change)
                with self.assertRaises(ValueError):
                    collect(fixture.config, fixture.get)

    def test_non_utf8_blob_is_not_silently_replaced(self):
        fixture = GitHubFixture(b"\xff\xfe")
        with self.assertRaises(ValueError):
            collect(fixture.config, fixture.get)

    def test_long_file_evidence_is_bounded_and_marks_truncation(self):
        fixture = GitHubFixture("x" * 20000)
        result = collect(fixture.config, fixture.get)
        text = result["evidence"][0]["text"]
        self.assertLessEqual(len(text), 12000)
        self.assertIn("已截断", text)
        self.assertEqual(result["snapshot"]["sources"]["demo"]["files"][fixture.file_path], fixture.blob["sha"])

    def test_excerpt_starts_at_anchor_with_original_line_numbers(self):
        fixture = GitHubFixture("# intro\n\ndef irrelevant():\n    pass\n\ndef selected():\n    return 42\n")
        fixture.source["excerpts"] = {fixture.file_path: "def selected("}
        evidence = collect(fixture.config, fixture.get)["evidence"][0]
        self.assertIn("L6: def selected():", evidence["text"])
        self.assertIn("L7:     return 42", evidence["text"])
        self.assertNotIn("L3: def irrelevant", evidence["text"])
        self.assertIn("已截断", evidence["text"])

    def test_line_numbers_use_source_newlines_not_unicode_separators(self):
        fixture = GitHubFixture('text = "one\u2028two"\n\ndef selected():\n    pass\n')
        fixture.source["excerpts"] = {fixture.file_path: "def selected("}
        text = collect(fixture.config, fixture.get)["evidence"][0]["text"]
        self.assertIn("L3: def selected():", text)
        self.assertIn("L4:     pass", text)

    def test_crlf_line_numbers_remain_correct(self):
        fixture = GitHubFixture("# intro\r\ndef selected():\r\n    pass\r\n")
        fixture.source["excerpts"] = {fixture.file_path: "def selected("}
        text = collect(fixture.config, fixture.get)["evidence"][0]["text"]
        self.assertIn("L2: def selected():", text)

    def test_missing_excerpt_anchor_explicitly_falls_back_to_file_start(self):
        fixture = GitHubFixture()
        fixture.source["excerpts"] = {fixture.file_path: "def missing("}
        text = collect(fixture.config, fixture.get)["evidence"][0]["text"]
        self.assertIn("锚点未找到", text)
        self.assertIn("不能据此判断能力消失", text)
        self.assertIn("L1: print('hello')", text)

    def test_default_excerpt_budget_is_eight_thousand_characters(self):
        fixture = GitHubFixture("x" * 20000)
        text = collect(fixture.config, fixture.get)["evidence"][0]["text"]
        self.assertLessEqual(len(text), 8000)

    def test_symlink_is_not_treated_as_source_text(self):
        fixture = GitHubFixture()
        fixture.tree["tree"][0]["mode"] = "120000"
        with self.assertRaises(ValueError):
            collect(fixture.config, fixture.get)

    def test_duplicate_ids_and_non_exact_paths_are_rejected(self):
        fixture = GitHubFixture()
        bad_configs = [
            {"sources": [fixture.source, fixture.source]},
            {"sources": [{**fixture.source, "paths": ["../secrets"]}]},
            {"sources": [{**fixture.source, "paths": ["src/*.py"]}]},
            {"sources": [{**fixture.source, "repo": "https://example.test/repo"}]},
        ]
        for config in bad_configs:
            with self.subTest(config=config):
                with self.assertRaises(ValueError):
                    collect(config, fixture.get)

    def test_source_count_is_bounded_before_network_calls(self):
        fixture = GitHubFixture()
        config = {"sources": [{**fixture.source, "id": f"source{index}"} for index in range(13)]}
        with self.assertRaises(ValueError):
            collect(config, fixture.get)
        self.assertEqual(fixture.calls, [])

    def test_total_selected_file_count_is_bounded_before_network_calls(self):
        fixture = GitHubFixture()
        config = {"sources": [{**fixture.source, "paths": [f"file{index}.py" for index in range(41)]}]}
        with self.assertRaises(ValueError):
            collect(config, fixture.get)
        self.assertEqual(fixture.calls, [])


if __name__ == "__main__":
    unittest.main()
