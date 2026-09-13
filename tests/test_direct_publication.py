"""Direct publication must keep paid review and trusted-result boundaries intact."""
import contextlib
import copy
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
    'publication_mode': 'direct',
    'blocks': {'demo': {'source_ids': ['source'], 'max_chars': 1000}},
}
README = '固定简介\n<!-- profile-ai:demo:start -->\n公开实践已有验证。\n<!-- profile-ai:demo:end -->\n固定案例\n'
EVIDENCE = [{'id': 'source:file', 'source_id': 'source',
             'url': 'https://github.com/sunbos/demo/blob/' + 'a' * 40 + '/file.py',
             'text': 'A public offline test.'}]
RESPONSE = {'summary': '补充已有离线验证的描述', 'updates': [
    {'block_id': 'demo', 'markdown': '公开实践已有离线验证。', 'evidence_ids': ['source:file']}]}


class DirectPublicationTests(unittest.TestCase):
    def test_changed_candidate_does_not_require_a_bot_branch_push(self):
        client = Mock()
        with patch.object(run, 'load_state', return_value=(None, None)), \
                patch.object(run, 'load_proposal', return_value=None), \
                patch.object(run, 'collect', return_value={'snapshot': {}, 'evidence': EVIDENCE}), \
                patch.object(run, 'review', return_value=RESPONSE), \
                patch.object(run, 'push_expectation') as expected:
            result = run.prepare(CONFIG, README, client, api_key='fixture-key')
        self.assertTrue(result['publish'])
        self.assertIn('已有离线验证', result['candidate'])
        expected.assert_not_called()
        self.assertIsNone(result['expected_pr_head'])
        client.write.assert_not_called()

    def test_direct_mode_preview_does_not_claim_it_will_publish(self):
        result = {'status': 'preview', 'response': {'summary': '保持已有事实', 'updates': []}, 'evidence': []}
        body = run.review_body(result, 'direct')
        self.assertIn('仅供预览，不发布或写状态', body)
        self.assertNotIn('校验后自动发布', body)

    def test_pending_legacy_proposal_stops_before_paid_review(self):
        client = Mock()
        with patch.object(run, 'load_state', return_value=(None, None)), \
                patch.object(run, 'load_proposal', return_value={'readme': README}), \
                patch.object(run, 'collect', return_value={'snapshot': {}, 'evidence': EVIDENCE}), \
                patch.object(run, 'review') as model:
            with self.assertRaisesRegex(ValueError, '旧维护 PR'):
                run.prepare(CONFIG, README, client, api_key='fixture-key')
        model.assert_not_called()
        client.write.assert_not_called()

    def test_cli_routes_verified_result_to_exact_checkout_publication(self):
        self._exercise_cli(change_config=False)

    def test_cli_rejects_a_result_after_policy_changes(self):
        self._exercise_cli(change_config=True)

    def _exercise_cli(self, *, change_config):
        with tempfile.TemporaryDirectory(prefix='profile-direct-test-') as temporary:
            root = Path(temporary)
            config_path, output = root / 'config.json', root / 'result'
            config_path.write_text(json.dumps(CONFIG))
            (root / 'README.md').write_text(README)
            result = {'status': 'reviewed', 'publish': True, 'candidate': README,
                      'base_readme': README, 'response': {'summary': '保持已有事实', 'updates': []},
                      'evidence': [], 'expected_pr_head': None}
            client, publisher = Mock(), Mock(return_value={'status': 'published', 'commit_sha': 'c' * 40})
            with patch.object(run, 'ROOT', root), patch.object(run, 'CONFIG_PATH', config_path), \
                    patch.object(run, 'GitHubClient', return_value=client), \
                    patch.object(run, 'prepare', return_value=copy.deepcopy(result)), \
                    patch.object(run, 'ensure_fresh'), patch.object(run, 'assert_base_unchanged'), \
                    patch.object(run, 'publish_candidate', publisher, create=True), \
                    patch.dict(os.environ, {'GITHUB_ENV': str(root / 'environment')}, clear=True), \
                    contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                run.main(['prepare', '--output-dir', str(output)])
                self.assertFalse((root / 'environment').exists())
                if change_config:
                    config_path.write_text(json.dumps({**CONFIG, 'policy_version': 'changed'}))
                    with self.assertRaisesRegex(ValueError, '审查配置已变化'):
                        run.main(['publish', '--output-dir', str(output), '--base-sha', 'b' * 40])
                    publisher.assert_not_called()
                else:
                    run.main(['publish', '--output-dir', str(output), '--base-sha', 'b' * 40])
                    publisher.assert_called_once()
                    args = publisher.call_args.args
                    self.assertIs(args[0], client)
                    self.assertEqual(args[1]['publication_mode'], 'direct')
                    self.assertEqual(args[2]['candidate'], README)
                    self.assertEqual(args[3], 'b' * 40)
