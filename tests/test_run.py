import copy
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
