"""Direct publication checks against a stateful, offline GitHub API fixture."""

import base64
import copy
import hashlib
import json
import unittest
from urllib.parse import quote, urlencode

from scripts.profile_maintenance.reviewer import apply_updates
from scripts.profile_maintenance.state import GitHubError

try:
    from scripts.profile_maintenance import publisher
except ImportError:
    publisher = None


ROOT = '/repos/sunbos/sunbos'
BASE = 'b' * 40
BASE_TREE = 'c' * 40
STATE_HEAD = 'd' * 40
NEW_TREE = 'e' * 40
FILE_SHA = 'f' * 40
NEW_COMMIT = 'a' * 40
OTHER = '9' * 40
LEGACY_HEAD = '8' * 40
CONFIG = {
    'repository': 'sunbos/sunbos', 'base_branch': 'main',
    'proposal_branch': 'automation/profile-maintenance',
    'state_branch': 'automation/profile-maintenance-state', 'publication_mode': 'direct',
    'blocks': {'sdk': {'source_ids': ['sdk'], 'max_chars': 500, 'min_ratio': 0.9,
                       'protected_phrases': ['补充同步与异步接口']}}
}
OLD = '为 SDK 补充同步与异步接口，并增加失败路径的测试；目前仍在审阅中。'
NEW = '为 SDK 补充同步与异步接口，并增加失败路径的测试；目前已经合并完成。'
README = '# 固定标题\r\n已批准的脱敏案例。\r\n<!-- profile-ai:sdk:start -->\r\n' + OLD + '\r\n<!-- profile-ai:sdk:end -->\r\n'
EVIDENCE = [{'id': 'sdk:pull', 'source_id': 'sdk', 'url': 'https://github.com/sunbos/sdk/pull/1',
             'text': 'state=closed; merged=true'}]


def blob_sha(text):
    raw = text.encode('utf-8')
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()


def contents(text):
    raw = text.encode('utf-8')
    return {'type': 'file', 'encoding': 'base64', 'content': base64.b64encode(raw).decode(),
            'sha': blob_sha(text), 'size': len(raw)}


def ref(branch, sha):
    return {'ref': 'refs/heads/' + branch, 'object': {'type': 'commit', 'sha': sha}}


def ref_path(branch):
    return ROOT + '/git/ref/heads/' + quote(branch, safe='')


def result(changed=True):
    response = {'summary': '根据公开证据更新合并状态。', 'updates': []}
    if changed:
        response['updates'] = [{'block_id': 'sdk', 'markdown': NEW, 'evidence_ids': ['sdk:pull']}]
    state = {'schema_version': 1, 'fingerprint': '1' * 64, 'snapshot': {'sources': {'sdk': {'merged': True}}},
             'base_readme_sha256': hashlib.sha256(README.encode()).hexdigest(), 'pr_head_sha': None}
    old = {**state, 'fingerprint': '0' * 64}
    return {'status': 'reviewed', 'publish': changed, 'proposal': None, 'old_state': old,
            'file_sha': FILE_SHA, 'state': state, 'fingerprint': state['fingerprint'],
            'base_readme': README, 'candidate': apply_updates(README, CONFIG, EVIDENCE, response),
            'response': response, 'evidence': EVIDENCE}


class GitHubFixture:
    """Model immutable objects, ref movement and state CAS; never use a network."""

    def __init__(self):
        self.main = BASE
        self.proposal_head = None
        self.proposals = []
        self.state_head = STATE_HEAD
        self.readme = README
        self.created_text = None
        self.requests = []
        self.overrides = {}
        self.before_read = None
        self.before_write = None
        self.lose_patch_response = False
        self.saved = None
        self.base_mode = '100644'

    def _override(self, method, path):
        value = self.overrides[(method, path)]
        if isinstance(value, Exception):
            raise value
        return copy.deepcopy(value)

    def get(self, path):
        self.requests.append(('GET', path, None))
        if self.before_read:
            self.before_read(path)
        if ('GET', path) in self.overrides:
            return self._override('GET', path)
        if path == ref_path('main'):
            return ref('main', self.main)
        if path == ref_path(CONFIG['proposal_branch']):
            if self.proposal_head is None:
                raise GitHubError('missing', status=404)
            return ref(CONFIG['proposal_branch'], self.proposal_head)
        if path == ref_path(CONFIG['state_branch']):
            if self.state_head is None:
                raise GitHubError('missing', status=404)
            return ref(CONFIG['state_branch'], self.state_head)
        if path.startswith(ROOT + '/pulls?'):
            return copy.deepcopy(self.proposals)
        if path == ROOT + '/contents/README.md?' + urlencode({'ref': BASE}):
            return contents(self.readme)
        if path == ROOT + '/git/commits/' + BASE:
            return {'sha': BASE, 'tree': {'sha': BASE_TREE}, 'parents': [{'sha': OTHER}]}
        if path == ROOT + '/git/trees/' + BASE_TREE:
            return {'sha': BASE_TREE, 'truncated': False, 'tree': [
                {'path': 'README.md', 'mode': self.base_mode, 'type': 'blob', 'sha': blob_sha(README)},
                {'path': '.github', 'mode': '040000', 'type': 'tree', 'sha': OTHER}]}
        if path == ROOT + '/git/commits/' + NEW_COMMIT:
            return self.commit()
        if path == ROOT + '/compare/' + BASE + '...' + NEW_COMMIT:
            return self.comparison()
        raise AssertionError('Unexpected GET: ' + path)

    def commit(self):
        return {'sha': NEW_COMMIT, 'tree': {'sha': NEW_TREE}, 'parents': [{'sha': BASE}]}

    def comparison(self):
        return {'status': 'ahead', 'ahead_by': 1, 'behind_by': 0, 'total_commits': 1,
                'base_commit': {'sha': BASE}, 'merge_base_commit': {'sha': BASE},
                'commits': [{'sha': NEW_COMMIT}],
                'files': [{'filename': 'README.md', 'status': 'modified', 'sha': blob_sha(self.created_text)}]}

    def write(self, method, path, payload):
        self.requests.append((method, path, copy.deepcopy(payload)))
        if self.before_write:
            self.before_write(method, path, payload)
        if (method, path) in self.overrides:
            return self._override(method, path)
        if method == 'POST' and path == ROOT + '/git/blobs':
            assert payload['encoding'] == 'utf-8'
            self.created_text = payload['content']
            return {'sha': blob_sha(self.created_text)}
        if method == 'POST' and path == ROOT + '/git/trees':
            assert payload == {'base_tree': BASE_TREE, 'tree': [
                {'path': 'README.md', 'mode': self.base_mode, 'type': 'blob', 'sha': blob_sha(self.created_text)}]}
            return {'sha': NEW_TREE, 'truncated': False}
        if method == 'POST' and path == ROOT + '/git/commits':
            assert payload['tree'] == NEW_TREE and payload['parents'] == [BASE]
            return self.commit()
        if method == 'PATCH' and path == ROOT + '/git/refs/heads/main':
            assert payload == {'sha': NEW_COMMIT, 'force': False}
            if self.main != BASE:
                raise GitHubError('not a fast forward', status=422)
            self.main = NEW_COMMIT
            if self.lose_patch_response:
                raise GitHubError('response lost', retryable=True)
            return ref('main', self.main)
        if method == 'POST' and path == ROOT + '/git/refs':
            assert payload == {'ref': 'refs/heads/' + CONFIG['state_branch'], 'sha': self.main}
            self.state_head = self.main
            return ref(CONFIG['state_branch'], self.state_head)
        if method == 'PUT' and path == ROOT + '/contents/state.json':
            assert payload['branch'] == CONFIG['state_branch']
            self.saved = json.loads(base64.b64decode(payload['content']))
            return {'content': {'sha': '7' * 40}}
        raise AssertionError('Unexpected write: ' + method + ' ' + path)

    def writes(self):
        return [entry for entry in self.requests if entry[0] != 'GET']

    def main_writes(self):
        return [entry for entry in self.writes() if entry[0] == 'PATCH']


class PublisherTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(publisher, 'publisher.py has not been implemented')
        self.client = GitHubFixture()

    def publish(self, prepared=None, config=None, expected_base=BASE):
        return publisher.publish(self.client, config or CONFIG, prepared or result(), expected_base)

    def test_changed_readme_publishes_one_child_then_checkpoints_exact_candidate(self):
        prepared = result()
        original_state = copy.deepcopy(prepared['state'])
        self.assertEqual(self.publish(prepared), {'status': 'published', 'commit_sha': NEW_COMMIT})
        self.assertEqual(self.client.main, NEW_COMMIT)
        self.assertEqual(self.client.created_text, prepared['candidate'])
        self.assertEqual(len(self.client.main_writes()), 1)
        self.assertEqual(self.client.saved['base_readme_sha256'], hashlib.sha256(prepared['candidate'].encode()).hexdigest())
        self.assertEqual(self.client.saved['snapshot'], original_state['snapshot'])
        self.assertEqual(prepared['state'], original_state)
        writes = self.client.writes()
        self.assertEqual([item[0] for item in writes], ['POST', 'POST', 'POST', 'PATCH', 'PUT'])
        self.assertEqual(writes[-1][2]['sha'], FILE_SHA)

    def test_no_update_only_checkpoints_and_preserves_main(self):
        prepared = result(False)
        self.assertEqual(self.publish(prepared), {'status': 'checkpointed', 'commit_sha': BASE})
        self.assertEqual(self.client.main, BASE)
        self.assertEqual(len(self.client.writes()), 1)
        self.assertEqual(self.client.writes()[0][:2], ('PUT', ROOT + '/contents/state.json'))
        self.assertEqual(self.client.saved, prepared['state'])

    def test_first_checkpoint_creates_only_the_state_branch(self):
        prepared = result(False)
        prepared.update(old_state=None, file_sha=None)
        self.client.state_head = None
        self.assertEqual(self.publish(prepared)['status'], 'checkpointed')
        self.assertEqual([p for _, p, _ in self.client.writes()], [ROOT + '/git/refs', ROOT + '/contents/state.json'])
        self.assertNotIn('sha', self.client.writes()[-1][2])

    def test_invalid_mode_status_proposal_and_sha_fail_before_network(self):
        cases = [(dict(CONFIG, publication_mode='pr'), result(), BASE),
                 (CONFIG, dict(result(), status='preview'), BASE),
                 (CONFIG, dict(result(), proposal={}), BASE)]
        cases += [(CONFIG, result(), bad) for bad in (None, '', '0' * 40, 'A' * 40, 'main')]
        for config, prepared, base in cases:
            self.client = GitHubFixture()
            with self.subTest(base=base, status=prepared['status']), self.assertRaises(ValueError):
                self.publish(prepared, config, base)
            self.assertEqual(self.client.requests, [])

    def test_candidate_cannot_bypass_response_or_protected_content(self):
        for candidate in (result()['candidate'] + '\n新增内容', result()['candidate'].replace('已批准的脱敏案例', '改写案例')):
            prepared = result(); prepared['candidate'] = candidate
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                self.publish(prepared)
            self.assertEqual(self.client.writes(), [])

    def test_invalid_evidence_or_removed_protected_phrase_never_publishes(self):
        for changed in ('foreign-evidence', 'removed-phrase'):
            prepared = result()
            if changed == 'foreign-evidence': prepared['response']['updates'][0]['evidence_ids'] = ['missing']
            else: prepared['response']['updates'][0]['markdown'] = NEW.replace('补充同步与异步接口', '补充接口能力并维护调用')
            with self.subTest(changed=changed), self.assertRaises(ValueError): self.publish(prepared)
            self.assertEqual(self.client.writes(), [])

    def test_invalid_state_is_rejected_before_main_publication(self):
        for field, value in (('state', {}), ('file_sha', 'invalid')):
            prepared = result(); prepared[field] = value
            with self.subTest(field=field), self.assertRaises((ValueError, GitHubError)):
                self.publish(prepared)
            self.assertEqual(self.client.writes(), [])

    def test_unknown_or_pending_legacy_proposal_is_never_adopted(self):
        for pending in (False, True):
            self.client = GitHubFixture(); self.client.proposal_head = LEGACY_HEAD
            prepared = result()
            if pending:
                prepared['old_state']['pr_head_sha'] = prepared['state']['pr_head_sha'] = LEGACY_HEAD
                self.client.proposals = [{'number': 7, 'state': 'open',
                    'head': {'sha': LEGACY_HEAD, 'ref': CONFIG['proposal_branch'], 'repo': {'full_name': CONFIG['repository']}},
                    'base': {'ref': 'main', 'repo': {'full_name': CONFIG['repository']}}}]
                self.client.overrides[('GET', ROOT + '/contents/README.md?' + urlencode({'ref': LEGACY_HEAD}))] = contents(README)
            with self.subTest(pending=pending), self.assertRaises((ValueError, GitHubError)):
                self.publish(prepared)
            self.assertEqual(self.client.writes(), [])

    def test_closed_legacy_branch_keeps_its_trusted_head_in_state(self):
        prepared = result(); self.client.proposal_head = LEGACY_HEAD
        prepared['old_state']['pr_head_sha'] = prepared['state']['pr_head_sha'] = LEGACY_HEAD
        self.assertEqual(self.publish(prepared)['status'], 'published')
        self.assertEqual(self.client.saved['pr_head_sha'], LEGACY_HEAD)

    def test_changed_base_defers_before_creating_objects(self):
        self.client.main = OTHER
        self.assertEqual(self.publish(), {'status': 'deferred', 'commit_sha': None})
        self.assertEqual(self.client.writes(), [])

    def test_pinned_base_readme_must_match_reviewed_bytes(self):
        self.client.readme = README.replace('\r\n', '\n')
        with self.assertRaises(ValueError): self.publish()
        self.assertEqual(self.client.writes(), [])

    def test_frozen_tree_must_be_complete_and_readme_a_matching_regular_blob(self):
        variants = [{'truncated': True}, {'sha': OTHER}, {'tree': []},
                    {'tree': [{'path': 'README.md', 'mode': '120000', 'type': 'blob', 'sha': blob_sha(README)}]},
                    {'tree': [{'path': 'README.md', 'mode': '100644', 'type': 'blob', 'sha': OTHER}]}]
        for replacement in variants:
            self.client = GitHubFixture()
            tree_path = ROOT + '/git/trees/' + BASE_TREE
            self.client.overrides[('GET', tree_path)] = {**self.client.get(tree_path), **replacement}
            with self.subTest(replacement=replacement), self.assertRaises(ValueError): self.publish()
            self.assertEqual(self.client.writes(), [])

    def test_existing_readme_executable_mode_is_preserved(self):
        self.client.base_mode = '100755'
        self.assertEqual(self.publish()['status'], 'published')
        tree_write = next(payload for method, path, payload in self.client.writes() if path == ROOT + '/git/trees')
        self.assertEqual(tree_write['tree'][0]['mode'], '100755')

    def test_mismatched_state_inputs_fail_before_network(self):
        for field, value in (('fingerprint', '2' * 64), ('base_readme_sha256', '2' * 64), ('pr_head_sha', LEGACY_HEAD)):
            self.client = GitHubFixture(); prepared = result(); prepared['state'][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): self.publish(prepared)
            self.assertEqual(self.client.requests, [])

    def test_no_update_rechecks_main_before_saving_state(self):
        count = 0
        def move(path):
            nonlocal count
            if path == ref_path('main'):
                count += 1
                if count == 2: self.client.main = OTHER
        self.client.before_read = move
        self.assertEqual(self.publish(result(False))['status'], 'deferred')
        self.assertEqual(self.client.writes(), [])

    def test_base_moving_during_object_creation_defers_without_main_or_state_write(self):
        def move(method, path, payload):
            if path == ROOT + '/git/commits': self.client.main = OTHER
        self.client.before_write = move
        self.assertEqual(self.publish()['status'], 'deferred')
        self.assertEqual(self.client.main, OTHER)
        self.assertEqual(self.client.main_writes(), [])
        self.assertIsNone(self.client.saved)

    def test_unknown_proposal_appearing_during_object_creation_blocks_publication(self):
        def move(method, path, payload):
            if path == ROOT + '/git/commits': self.client.proposal_head = OTHER
        self.client.before_write = move
        with self.assertRaises((ValueError, GitHubError)): self.publish()
        self.assertEqual(self.client.main, BASE)
        self.assertEqual(self.client.main_writes(), [])
        self.assertIsNone(self.client.saved)

    def test_last_moment_main_race_is_rejected_without_force_or_checkpoint(self):
        def move(method, path, payload):
            if method == 'PATCH': self.client.main = OTHER
        self.client.before_write = move
        self.assertEqual(self.publish()['status'], 'deferred')
        self.assertEqual(self.client.main, OTHER)
        self.assertEqual(len(self.client.main_writes()), 1)
        self.assertIsNone(self.client.saved)

    def test_lost_successful_ref_response_is_confirmed_without_retrying_write(self):
        self.client.lose_patch_response = True
        self.assertEqual(self.publish()['status'], 'published')
        self.assertEqual(len(self.client.main_writes()), 1)
        self.assertIsNotNone(self.client.saved)

    def test_unknown_publication_outcome_without_read_confirmation_is_not_checkpointed(self):
        def fail_confirmation(path):
            if path == ref_path('main') and self.client.main == NEW_COMMIT:
                raise GitHubError('confirmation unavailable', status=503)
        self.client.before_read = fail_confirmation
        self.client.lose_patch_response = True
        with self.assertRaises(GitHubError): self.publish()
        self.assertEqual(self.client.main, NEW_COMMIT)
        self.assertEqual(len(self.client.main_writes()), 1)
        self.assertIsNone(self.client.saved)

    def test_failed_ref_write_is_not_retried_or_recorded(self):
        for error in (GitHubError('unavailable', status=503), GitHubError('protected', status=403), OSError('network')):
            self.client = GitHubFixture()
            self.client.overrides[('PATCH', ROOT + '/git/refs/heads/main')] = error
            with self.subTest(error=type(error).__name__):
                with self.assertRaises(type(error)) as caught: self.publish()
                self.assertIs(caught.exception, error)
            self.assertEqual(len(self.client.main_writes()), 1)
            self.assertEqual(self.client.main, BASE)
            self.assertIsNone(self.client.saved)

    def test_apparently_successful_ref_write_that_did_not_advance_main_fails(self):
        self.client.overrides[('PATCH', ROOT + '/git/refs/heads/main')] = ref('main', NEW_COMMIT)
        with self.assertRaises(ValueError): self.publish()
        self.assertEqual(len(self.client.main_writes()), 1)
        self.assertEqual(self.client.main, BASE)
        self.assertIsNone(self.client.saved)

    def test_unknown_object_write_does_not_retry_or_advance_refs(self):
        for path in ('/git/blobs', '/git/trees', '/git/commits'):
            self.client = GitHubFixture()
            error = GitHubError('response lost', retryable=True)
            self.client.overrides[('POST', ROOT + path)] = error
            with self.subTest(path=path):
                with self.assertRaises(GitHubError) as caught: self.publish()
                self.assertIs(caught.exception, error)
            self.assertEqual(sum(p == ROOT + path for _, p, _ in self.client.writes()), 1)
            self.assertEqual(self.client.main_writes(), [])
            self.assertIsNone(self.client.saved)

    def test_invalid_blob_tree_or_commit_response_cannot_advance_main(self):
        cases = [('/git/blobs', {'sha': OTHER}), ('/git/trees', {'sha': 'invalid'}),
                 ('/git/commits', {'sha': NEW_COMMIT, 'tree': {'sha': NEW_TREE}, 'parents': [{'sha': OTHER}]}),
                 ('/git/commits', {'sha': NEW_COMMIT, 'tree': {'sha': OTHER}, 'parents': [{'sha': BASE}]}),
                 ('/git/commits', {'sha': NEW_COMMIT, 'tree': {'sha': NEW_TREE}, 'parents': [{'sha': BASE}, {'sha': OTHER}]})]
        for path, response in cases:
            self.client = GitHubFixture(); self.client.overrides[('POST', ROOT + path)] = response
            with self.subTest(path=path, response=response), self.assertRaises((ValueError, GitHubError)):
                self.publish()
            self.assertEqual(self.client.main_writes(), [])
            self.assertIsNone(self.client.saved)

    def test_compare_must_confirm_exactly_one_modified_readme_and_one_child_commit(self):
        variants = [{'status': 'diverged'}, {'ahead_by': 2}, {'behind_by': 1}, {'total_commits': 2},
                    {'base_commit': {'sha': OTHER}}, {'merge_base_commit': {'sha': OTHER}},
                    {'commits': [{'sha': OTHER}]}, {'files': []},
                    {'files': [{'filename': 'README.md', 'status': 'renamed', 'sha': 'x'}]},
                    {'files': [{'filename': 'other.py', 'status': 'modified', 'sha': 'x'}]},
                    {'files': [{'filename': 'README.md', 'status': 'modified', 'sha': OTHER}]},
                    {'files': [{'filename': 'README.md', 'status': 'modified', 'sha': blob_sha(result()['candidate'])},
                               {'filename': 'extra.py', 'status': 'modified', 'sha': OTHER}]}]
        for replacement in variants:
            self.client = GitHubFixture()
            self.client.created_text = result()['candidate']
            bad = {**self.client.comparison(), **replacement}
            self.client.overrides[('GET', ROOT + '/compare/' + BASE + '...' + NEW_COMMIT)] = bad
            with self.subTest(replacement=replacement), self.assertRaises((ValueError, GitHubError)):
                self.publish()
            self.assertEqual(self.client.main_writes(), [])
            self.assertIsNone(self.client.saved)

    def test_created_commit_is_rechecked_from_the_immutable_object_endpoint(self):
        for replacement in ({'sha': OTHER}, {'parents': [{'sha': OTHER}]}, {'tree': {'sha': OTHER}}):
            self.client = GitHubFixture()
            self.client.overrides[('GET', ROOT + '/git/commits/' + NEW_COMMIT)] = {**self.client.commit(), **replacement}
            with self.subTest(replacement=replacement), self.assertRaises(ValueError): self.publish()
            self.assertEqual(self.client.main_writes(), [])
            self.assertIsNone(self.client.saved)

    def test_state_failure_does_not_undo_main_or_report_success(self):
        self.client.overrides[('PUT', ROOT + '/contents/state.json')] = GitHubError('state conflict', status=409)
        with self.assertRaises(GitHubError): self.publish()
        self.assertEqual(self.client.main, NEW_COMMIT)
        self.assertEqual(len(self.client.main_writes()), 1)
        self.assertIsNone(self.client.saved)

    def test_read_failure_is_never_treated_as_no_pending_proposal_or_safe_base(self):
        self.client.overrides[('GET', ref_path(CONFIG['proposal_branch']))] = GitHubError('unavailable', status=503)
        with self.assertRaises(GitHubError): self.publish()
        self.assertEqual(self.client.writes(), [])


if __name__ == '__main__':
    unittest.main()
