"""Protocol validation and a real Git reproduction of the publication race."""

import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest

try:
    from scripts.profile_maintenance import pre_push
except ImportError:
    pre_push = None


ROOT = Path(__file__).resolve().parents[1]
BRANCH = "automation/profile-maintenance"
REF = "refs/heads/" + BRANCH
OLD = "a" * 40
NEW = "b" * 40
ZERO = "0" * 40


def update(old=OLD, new=NEW, ref=REF):
    return f"{REF} {new} {ref} {old}\n"


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(pre_push, "pre_push.py is not implemented")

    def test_accepts_exact_update_and_first_creation(self):
        self.assertIsNone(pre_push.validate_updates(update(), BRANCH, OLD))
        self.assertIsNone(pre_push.validate_updates([update(old=ZERO)], BRANCH, ZERO))

    def test_rejects_remote_head_changed_after_review(self):
        with self.assertRaises(ValueError):
            pre_push.validate_updates(update(old="c" * 40), BRANCH, OLD)

    def test_rejects_other_refs_even_with_matching_expected_sha(self):
        for ref in ["refs/heads/main", "refs/tags/test", "refs/heads/" + BRANCH + "-other"]:
            with self.subTest(ref=ref), self.assertRaises(ValueError):
                pre_push.validate_updates(update(ref=ref), BRANCH, OLD)

    def test_rejects_empty_multiple_and_malformed_updates(self):
        for lines in ["", "\n", [], update() + update(), update() + "\n",
                      update().replace(NEW, "bad"), update().replace(OLD, "bad"),
                      update().replace(NEW, ZERO), update() + "extra", "x y z\n",
                      update().replace(REF, "(delete)", 1), [None], "x" * 5000]:
            with self.subTest(lines=str(lines)[:80]), self.assertRaises(ValueError):
                pre_push.validate_updates(lines, BRANCH, OLD)

    def test_rejects_invalid_configuration(self):
        for branch, expected in [("", OLD), (BRANCH, ""), (BRANCH, "f" * 39),
                                 (BRANCH, "F" * 40), ("main\n", OLD),
                                 ("a/../main", OLD), ("/main", OLD), ("x.lock", OLD),
                                 ("a//b", OLD), ("-main", OLD), (None, OLD)]:
            with self.subTest(branch=branch, expected=expected), self.assertRaises(ValueError):
                pre_push.validate_updates(update(), branch, expected)

    def test_cli_requires_env_and_does_not_print_untrusted_data(self):
        environment = dict(os.environ, PYTHONPATH=str(ROOT))
        environment.pop("PROFILE_PROPOSAL_BRANCH", None)
        environment.pop("PROFILE_EXPECTED_PR_SHA", None)
        result = subprocess.run([sys.executable, "-m", "scripts.profile_maintenance.pre_push"],
                                input="sensitive-sentinel\n", text=True, capture_output=True,
                                cwd=ROOT, env=environment, timeout=10)
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("sensitive-sentinel", result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stderr)


class RealGitTests(unittest.TestCase):
    def test_create_update_and_raced_human_commit_with_refreshed_tracking_ref(self):
        self.assertIsNotNone(pre_push, "pre_push.py is not implemented")
        with tempfile.TemporaryDirectory(prefix="profile-hook-test-") as temporary:
            root = Path(temporary)
            remote, local, human, hooks = (root/name for name in ("remote.git", "action", "human", "hooks"))
            for path in (remote, local, hooks, root/"templates"):
                path.mkdir()
            environment = dict(os.environ, PYTHONPATH=str(ROOT), GIT_CONFIG_NOSYSTEM="1",
                               GIT_CONFIG_GLOBAL=os.devnull, GIT_TEMPLATE_DIR=str(root/"templates"),
                               GIT_AUTHOR_NAME="Fixture", GIT_AUTHOR_EMAIL="fixture@example.invalid",
                               GIT_COMMITTER_NAME="Fixture", GIT_COMMITTER_EMAIL="fixture@example.invalid",
                               PROFILE_PROPOSAL_BRANCH=BRANCH, PROFILE_EXPECTED_PR_SHA=ZERO)

            def git(path, *args, check=True):
                return subprocess.run(["git", "-c", "commit.gpgsign=false", "-C", str(path), *args],
                                      env=environment, text=True, capture_output=True, check=check, timeout=20)

            def commit(text):
                (local/"README.md").write_text(text + "\n", encoding="utf-8")
                git(local, "add", "README.md")
                git(local, "commit", "-m", "fixture")
                return git(local, "rev-parse", "HEAD").stdout.strip()

            def remote_head():
                return git(local, "ls-remote", "origin", REF).stdout.split()[0]

            git(remote, "init", "--bare")
            git(local, "init", "-b", "main")
            commit("base")
            git(local, "remote", "add", "origin", str(remote))
            git(local, "push", "origin", "main")
            (hooks/"pre-push").write_text(
                "#!/bin/sh\nexec " + shlex.quote(sys.executable) + " -m scripts.profile_maintenance.pre_push\n",
                encoding="utf-8")
            (hooks/"pre-push").chmod(0o700)
            git(local, "config", "core.hooksPath", str(hooks))

            # Initial creation is permitted only when the server advertises zero.
            git(local, "checkout", "-b", BRANCH)
            initial = commit("first proposal")
            git(local, "push", "--force-with-lease", "origin", f"{BRANCH}:{REF}")
            self.assertEqual(remote_head(), initial)

            # A normal update preserves the same explicitly verified expectation.
            environment["PROFILE_EXPECTED_PR_SHA"] = initial
            normal = commit("second proposal")
            git(local, "push", "--force-with-lease", "origin", f"{BRANCH}:{REF}")
            self.assertEqual(remote_head(), normal)

            # Review/guard saw normal. A human then pushes before the Action fetch.
            environment["PROFILE_EXPECTED_PR_SHA"] = normal
            git(root, "clone", "-b", BRANCH, str(remote), str(human))
            (human/"README.md").write_text("human changes must survive\n", encoding="utf-8")
            git(human, "commit", "-am", "human review")
            manual = git(human, "rev-parse", "HEAD").stdout.strip()
            git(human, "push", "origin", BRANCH)

            # Match create-pull-request: fetch the NEW remote head, recreate the
            # candidate, then force-with-lease. The lease alone would accept it.
            git(local, "fetch", "--force", "origin", f"{BRANCH}:refs/remotes/origin/{BRANCH}")
            self.assertEqual(git(local, "rev-parse", f"origin/{BRANCH}").stdout.strip(), manual)
            commit("AI replacement must be rejected")
            rejected = git(local, "push", "--force-with-lease", "origin", f"{BRANCH}:{REF}", check=False)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn("Profile publication refused", rejected.stderr)
            self.assertEqual(remote_head(), manual)
            self.assertEqual(git(remote, "show", f"{REF}:README.md").stdout, "human changes must survive\n")


if __name__ == "__main__":
    unittest.main()
