import copy
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from scripts.profile_maintenance import run


CONFIG = {
    'repository': 'sunbos/sunbos', 'base_branch': 'main',
    'proposal_branch': 'automation/profile-maintenance',
    'state_branch': 'automation/profile-maintenance-state',
    'model': 'deepseek-flash',
    'blocks': {'demo': {'source_ids': ['source'], 'max_chars': 1000}},
}
README = '固定核心\n<!-- profile-ai:demo:start -->\n公开实践已有验证。\n<!-- profile-ai:demo:end -->\n固定案例\n'
COLLECTED = {'snapshot': {'source': {'file': 'abc'}}, 'evidence': []}


class PrepareTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock()
        self.collect = patch.object(run, 'collect', return_value=copy.deepcopy(COLLECTED)).start()
        self.load = patch.object(run, 'load_state', return_value=(None, None)).start()
        self.proposal = patch.object(run, 'load_proposal', return_value=None).start()
        self.model = patch.object(run, 'review', return_value={'summary': '没有新增能力证据', 'updates': []}).start()
        self.addCleanup(patch.stopall)

    def test_same_snapshot_never_calls_model_or_writes(self):
        first = run.prepare(CONFIG, README, self.client, api_key='test')
        self.load.return_value = (first['state'], 'saved-file-sha')
        self.model.reset_mock()
        result = run.prepare(CONFIG, README, self.client, api_key='')
        self.assertEqual(result['status'], 'unchanged')
        self.model.assert_not_called()
        self.client.write.assert_not_called()

    def test_no_update_still_produces_checkpoint_without_readme_change(self):
        result = run.prepare(CONFIG, README, self.client, api_key='test')
        self.assertEqual(result['status'], 'reviewed')
        self.assertFalse(result['publish'])
        self.assertEqual(result['candidate'], README)
        self.assertEqual(result['state']['snapshot'], COLLECTED['snapshot'])
        self.assertIn('fingerprint', result['state'])
        self.client.write.assert_not_called()

    def test_dry_run_collects_without_key_model_or_remote_write(self):
        result = run.prepare(CONFIG, README, self.client, dry_run=True)
        self.assertEqual(result['status'], 'dry-run')
        self.assertNotIn('state', result)
        self.model.assert_not_called()
        self.client.write.assert_not_called()

    def test_model_failure_produces_no_checkpoint_and_never_writes(self):
        self.model.side_effect = RuntimeError('provider failed')
        with self.assertRaises(RuntimeError):
            run.prepare(CONFIG, README, self.client, api_key='test')
        self.client.write.assert_not_called()

    def test_changed_input_requires_key_and_does_not_mark_reviewed(self):
        with self.assertRaisesRegex(ValueError, 'DEEPSEEK_API_KEY'):
            run.prepare(CONFIG, README, self.client)
        self.model.assert_not_called()

    def test_pending_proposal_is_context_and_preserved_on_no_update(self):
        pending = README.replace('公开实践已有验证。', '公开实践已有离线验证。')
        self.proposal.return_value = {'number': 9, 'head_sha': 'abc', 'readme': pending}
        result = run.prepare(CONFIG, README, self.client, api_key='test')
        self.assertEqual(self.model.call_args.args[1]['demo'].strip(), '公开实践已有离线验证。')
        self.assertEqual(result['candidate'], pending)
        self.assertFalse(result['publish'])
        self.assertEqual(result['state']['pr_head_sha'], 'abc')

    def test_pending_proposal_cannot_change_protected_case(self):
        self.proposal.return_value = {'number': 9, 'head_sha': 'abc', 'readme': README.replace('固定案例', '篡改案例')}
        with self.assertRaises(ValueError):
            run.prepare(CONFIG, README, self.client, api_key='test')
        self.model.assert_not_called()

    def test_force_reviews_unchanged_evidence(self):
        first = run.prepare(CONFIG, README, self.client, api_key='test')
        self.load.return_value = (first['state'], 'saved-file-sha')
        self.model.reset_mock()
        result = run.prepare(CONFIG, README, self.client, api_key='test', force=True)
        self.assertEqual(result['status'], 'reviewed')
        self.model.assert_called_once()

    @patch.object(run, 'push_expectation')
    @patch.object(run, 'assert_base_unchanged')
    def test_preview_uses_checkout_blocks_and_preserves_protection_without_writes(self, base_check, push_check):
        self.proposal.return_value = {'number': 9, 'head_sha': 'abc', 'readme': '远端候选不应读取'}
        self.collect.return_value['evidence'] = [{
            'id': 'source:file', 'source_id': 'source',
            'url': 'https://github.com/sunbos/demo/blob/abc/file.py', 'text': '公开新增验证证据',
        }]
        self.model.return_value = {'summary': '补充已验证的公开细节', 'updates': [{
            'block_id': 'demo', 'markdown': '公开实践已有验证，并补充了离线故障测试。',
            'evidence_ids': ['source:file'],
        }]}
        result = run.prepare(CONFIG, README, self.client, api_key='test', preview=True)
        self.assertEqual(result['status'], 'preview')
        self.assertFalse(result['publish'])
        self.assertNotEqual(result['candidate'], README)
        self.assertEqual(run.protected_text(result['candidate'], CONFIG), run.protected_text(README, CONFIG))
        self.assertEqual(self.model.call_args.args[1]['demo'].strip(), '公开实践已有验证。')
        self.model.assert_called_once()
        self.proposal.assert_not_called()
        base_check.assert_not_called()
        push_check.assert_not_called()
        self.client.write.assert_not_called()
        for field in ['state', 'old_state', 'file_sha', 'expected_pr_head', 'proposal']:
            self.assertNotIn(field, result)

    def test_preview_unchanged_skips_model_without_key(self):
        first = run.prepare(CONFIG, README, self.client, api_key='test')
        self.load.return_value = (first['state'], 'file-sha')
        self.model.reset_mock()
        self.proposal.reset_mock()
        result = run.prepare(CONFIG, README, self.client, preview=True)
        self.assertEqual(result['status'], 'unchanged')
        self.assertFalse(result['publish'])
        self.model.assert_not_called()
        self.proposal.assert_not_called()

    def test_preview_force_runs_one_model_call_even_for_same_fingerprint(self):
        first = run.prepare(CONFIG, README, self.client, api_key='test')
        self.load.return_value = (first['state'], 'file-sha')
        self.model.reset_mock()
        result = run.prepare(CONFIG, README, self.client, api_key='test', preview=True, force=True)
        self.assertEqual(result['status'], 'preview')
        self.assertFalse(result['publish'])
        self.assertEqual(result['candidate'], README)
        self.model.assert_called_once()

    @patch.object(run, 'save_state')
    @patch.object(run, 'assert_base_unchanged')
    def test_preview_cannot_be_checkpointed(self, base_check, save):
        result = run.prepare(CONFIG, README, self.client, api_key='test', preview=True)
        with self.assertRaises(ValueError):
            run.checkpoint(self.client, CONFIG, result, 'a' * 40)
        base_check.assert_not_called()
        save.assert_not_called()

    def test_preview_and_dry_run_are_mutually_exclusive_before_any_work(self):
        with self.assertRaises(ValueError):
            run.prepare(CONFIG, README, self.client, dry_run=True, preview=True)
        self.load.assert_not_called()
        self.collect.assert_not_called()
        self.model.assert_not_called()

    @patch.object(run, 'ensure_fresh')
    @patch.object(run, 'assert_base_unchanged')
    def test_preview_cli_writes_artifacts_without_publication_or_guards(self, base_check, freshness):
        with tempfile.TemporaryDirectory(prefix='profile-preview-test-') as temporary:
            root = Path(temporary)
            config_file, output = root / 'config.json', root / 'output'
            config_file.write_text(json.dumps(CONFIG), encoding='utf-8')
            (root / 'README.md').write_text(README, encoding='utf-8')
            environment = {'DEEPSEEK_API_KEY': 'test', 'GITHUB_OUTPUT': str(root / 'outputs'),
                           'GITHUB_ENV': str(root / 'environment')}
            with patch.object(run, 'ROOT', root), patch.object(run, 'CONFIG_PATH', config_file), \
                    patch.object(run, 'GitHubClient', return_value=self.client), patch.dict(os.environ, environment, clear=True), \
                    contextlib.redirect_stdout(io.StringIO()):
                run.main(['prepare', '--output-dir', str(output), '--preview'])
                result = json.loads((output / 'result.json').read_text())
                self.assertEqual(result['status'], 'preview')
                self.assertFalse(result['publish'])
                self.assertNotIn('state', result)
                self.assertEqual((output / 'candidate.md').read_text(), README)
                self.assertIn('没有新增能力证据', (output / 'pr-body.md').read_text())
                self.assertEqual((root / 'outputs').read_text(), 'status=preview\npublish=false\n')
                self.assertFalse((root / 'environment').exists())
                with self.assertRaises(ValueError):
                    run.main(['guard', '--output-dir', str(output)])
                with self.assertRaises(ValueError):
                    run.main(['checkpoint', '--output-dir', str(output)])
            self.model.assert_called_once()
            self.proposal.assert_not_called()
            self.client.write.assert_not_called()
            base_check.assert_not_called()
            freshness.assert_not_called()

    def test_preview_failure_saves_diagnostics_without_candidate_or_state(self):
        def rejected_review(*args, diagnostics=None):
            if diagnostics is not None:
                diagnostics.update(stage='validation', validation_error='Update exceeds block length limits')
            raise ValueError('invalid review')
        self.model.side_effect = rejected_review
        with tempfile.TemporaryDirectory(prefix='profile-preview-failure-') as temporary:
            root = Path(temporary)
            config_file, output = root / 'config.json', root / 'output'
            config_file.write_text(json.dumps(CONFIG), encoding='utf-8')
            (root / 'README.md').write_text(README, encoding='utf-8')
            with patch.object(run, 'ROOT', root), patch.object(run, 'CONFIG_PATH', config_file), \
                    patch.object(run, 'GitHubClient', return_value=self.client), \
                    patch.dict(os.environ, {'DEEPSEEK_API_KEY': 'test'}, clear=True):
                with self.assertRaises(ValueError):
                    run.main(['prepare', '--output-dir', str(output), '--preview'])
            self.assertTrue((output / 'review-diagnostics.json').exists())
            diagnostic = json.loads((output / 'review-diagnostics.json').read_text())
            self.assertEqual(diagnostic['stage'], 'validation')
            self.assertFalse((output / 'candidate.md').exists())
            self.assertFalse((output / 'result.json').exists())
        self.client.write.assert_not_called()

    def test_preview_cli_rejects_dry_run_combination_before_reading_files(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as caught:
            run.main(['prepare', '--preview', '--dry-run', '--output-dir', '/unused'])
        self.assertEqual(caught.exception.code, 2)
        self.assertNotIn('unrecognized arguments', stderr.getvalue())
        self.collect.assert_not_called()
        self.model.assert_not_called()

    def test_closed_proposal_retains_trusted_branch_head(self):
        self.load.return_value = ({'pr_head_sha': 'a' * 40, 'fingerprint': 'old'}, 'b' * 40)
        result = run.prepare(CONFIG, README, self.client, api_key='test')
        self.assertEqual(result['state']['pr_head_sha'], 'a' * 40)

    @patch.object(run, 'save_state')
    @patch.object(run, 'assert_base_unchanged')
    def test_checkpoint_saves_no_update_decision(self, base_check, save):
        result = run.prepare(CONFIG, README, self.client, api_key='test')
        run.checkpoint(self.client, CONFIG, result, '')
        save.assert_called_once_with(self.client, CONFIG, result['state'], None)

    @patch.object(run, 'save_state')
    @patch.object(run, 'assert_base_unchanged')
    def test_checkpoint_rejects_publish_without_confirmed_remote_pr(self, base_check, save):
        result = run.prepare(CONFIG, README, self.client, api_key='test')
        result.update(publish=True, candidate=README.replace('已有验证', '已有离线验证'))
        with self.assertRaises(ValueError):
            run.checkpoint(self.client, CONFIG, result, 'a' * 40)
        save.assert_not_called()

    @patch.object(run, 'save_state')
    @patch.object(run, 'assert_base_unchanged')
    def test_checkpoint_rejects_remote_candidate_mismatch(self, base_check, save):
        result = run.prepare(CONFIG, README, self.client, api_key='test')
        result['publish'] = True
        self.proposal.return_value = {'head_sha': 'a' * 40, 'readme': 'other'}
        with self.assertRaises(ValueError):
            run.checkpoint(self.client, CONFIG, result, 'a' * 40)
        save.assert_not_called()

    @patch.object(run, 'save_state')
    @patch.object(run, 'assert_base_unchanged')
    def test_checkpoint_waits_for_verified_published_readme(self, base_check, save):
        result = run.prepare(CONFIG, README, self.client, api_key='test')
        result['publish'] = True
        self.proposal.return_value = {'head_sha': 'a' * 40, 'readme': result['candidate']}
        run.checkpoint(self.client, CONFIG, result, 'a' * 40)
        self.assertEqual(save.call_args.args[2]['pr_head_sha'], 'a' * 40)

    @patch.object(run, 'assert_base_unchanged')
    def test_guard_rejects_pr_change_after_review(self, base_check):
        result = run.prepare(CONFIG, README, self.client, api_key='test')
        self.proposal.return_value = {'head_sha': 'a' * 40, 'readme': README}
        with self.assertRaises(ValueError):
            run.ensure_fresh(self.client, CONFIG, result)


class PushExpectationTests(unittest.TestCase):
    def test_deleted_previous_branch_requires_new_branch_creation(self):
        client = Mock()
        client.get.side_effect = run.GitHubError('missing', status=404)
        self.assertEqual(run.push_expectation(client, CONFIG, {'pr_head_sha': 'a' * 40}), '0' * 40)

    def test_existing_branch_must_match_recorded_head(self):
        client = Mock()
        client.get.return_value = {'ref': 'refs/heads/automation/profile-maintenance', 'object': {'type': 'commit', 'sha': 'a' * 40}}
        self.assertEqual(run.push_expectation(client, CONFIG, {'pr_head_sha': 'a' * 40}), 'a' * 40)
        with self.assertRaises(ValueError):
            run.push_expectation(client, CONFIG, {'pr_head_sha': 'b' * 40})

    def test_api_failure_does_not_allow_branch_creation(self):
        client = Mock()
        client.get.side_effect = run.GitHubError('failure', status=500)
        with self.assertRaises(run.GitHubError):
            run.push_expectation(client, CONFIG, None)


if __name__ == '__main__':
    unittest.main()
