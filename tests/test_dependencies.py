"""Conservative dependency publication against an offline GitHub fixture."""

import base64
import copy
import hashlib
import unittest
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from scripts.profile_maintenance.state import GitHubError

try:
    from scripts.profile_maintenance import dependencies
except ImportError:
    dependencies = None


ROOT = '/repos/sunbos/sunbos'
CONFIG = {'repository': 'sunbos/sunbos', 'base_branch': 'main'}
BASE, HEAD, OLD, NEW, OTHER = (c * 40 for c in 'abcde')
WORKFLOW = '.github/workflows/profile-maintenance-check.yml'
FILE = '.github/workflows/snake.yml'
TEXT = ('name: Example\n'
        'on: push\n'
        'jobs:\n'
        '  check:\n'
        '    runs-on: ubuntu-latest\n'
        '    steps:\n'
        '      - uses: actions/checkout@' + OLD + ' # v4.2.1\n'
        '      - run: echo checked\n')
UPDATED = TEXT.replace(OLD, NEW).replace('v4.2.1', 'v4.2.2')


def sha(raw):
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()


def content(raw, path):
    return {'type': 'file', 'path': path, 'encoding': 'base64', 'size': len(raw),
            'sha': sha(raw), 'content': base64.b64encode(raw).decode()}


class GitHubFixture:
    def __init__(self):
        self.pr = {'number': 1, 'state': 'open', 'draft': False, 'merged': False,
                   'user': {'login': 'dependabot[bot]', 'type': 'Bot'}, 'changed_files': 1,
                   'head': {'sha': HEAD, 'ref': 'dependabot/github_actions/group-1',
                            'repo': {'full_name': 'sunbos/sunbos'}},
                   'base': {'sha': BASE, 'ref': 'main', 'repo': {'full_name': 'sunbos/sunbos'}}}
        self.prs = [self.pr]
        self.base = BASE
        self.files = {FILE: [TEXT.encode(), UPDATED.encode()]}
        self.status = 'modified'
        self.mode = '100644'
        self.tag_sha = NEW
        self.annotated = 0
        self.requests = []
        self.before_read = None
        self.overrides = {}
        self.merge_error = False
        self.run_data = {'id': 12, 'workflow_id': 7, 'check_suite_id': 13,
                         'name': 'Profile Maintenance Checks', 'path': WORKFLOW,
                         'event': 'pull_request', 'head_sha': HEAD,
                         'head_branch': self.pr['head']['ref'], 'status': 'completed',
                         'conclusion': 'success', 'pull_requests': [],
                         'repository': {'full_name': 'sunbos/sunbos'},
                         'head_repository': {'full_name': 'sunbos/sunbos'}}
        self.checks = [{'id': 21, 'name': 'validate', 'head_sha': HEAD, 'status': 'completed',
                        'conclusion': 'success', 'check_suite': {'id': 13},
                        'app': {'id': 15368, 'slug': 'github-actions'}},
                       {'id': 22, 'name': 'deepseek-preview', 'head_sha': HEAD,
                        'status': 'completed', 'conclusion': 'skipped',
                        'check_suite': {'id': 13}, 'app': {'id': 15368, 'slug': 'github-actions'}}]
        self.suites = [{'id': 13, 'head_sha': HEAD, 'status': 'completed', 'conclusion': 'success'}]
        self.statuses = {'sha': HEAD, 'state': 'pending', 'total_count': 0, 'statuses': []}

    def get(self, path):
        self.requests.append(('GET', path, None))
        if self.before_read:
            self.before_read(path)
        if path in self.overrides:
            value = self.overrides[path]
            if isinstance(value, Exception):
                raise value
            return copy.deepcopy(value)
        parsed = urlsplit(path)
        route, query = parsed.path, parse_qs(parsed.query)
        if route == ROOT + '/pulls':
            return copy.deepcopy(self.prs)
        if route == ROOT + '/pulls/1':
            return copy.deepcopy(self.pr)
        if route == ROOT + '/pulls/1/files':
            return [{'filename': f, 'status': self.status, 'sha': sha(data[1])}
                    for f, data in self.files.items()]
        if route == ROOT + '/git/ref/heads/main':
            return {'ref': 'refs/heads/main', 'object': {'type': 'commit', 'sha': self.base}}
        if route.startswith(ROOT + '/contents/'):
            name = route.split('/contents/', 1)[1]
            ref = query['ref'][0]
            if name not in self.files:
                raise GitHubError(status=404)
            return content(self.files[name][0 if ref == BASE else 1], name)
        if route.startswith(ROOT + '/git/commits/'):
            commit = route.rsplit('/', 1)[1]
            return {'sha': commit, 'tree': {'sha': ('1' if commit == BASE else '2') * 40}}
        if route.startswith(ROOT + '/git/trees/'):
            tree = route.rsplit('/', 1)[1]
            side = 0 if tree == '1' * 40 else 1
            return {'sha': tree, 'truncated': False, 'tree': [
                {'path': f, 'type': 'blob', 'mode': self.mode, 'sha': sha(raw[side])}
                for f, raw in self.files.items()]}
        if route == '/repos/actions/checkout/git/ref/tags/v4.2.2':
            obj = {'type': 'tag', 'sha': '9' * 40} if self.annotated else {'type': 'commit', 'sha': self.tag_sha}
            return {'ref': 'refs/tags/v4.2.2', 'object': obj}
        if route.startswith('/repos/actions/checkout/git/tags/'):
            obj = {'type': 'tag', 'sha': '9' * 40} if self.annotated > 1 else {'type': 'commit', 'sha': self.tag_sha}
            return {'sha': '9' * 40, 'object': obj}
        if route == ROOT + '/actions/workflows/profile-maintenance-check.yml':
            return {'id': 7, 'name': 'Profile Maintenance Checks', 'path': WORKFLOW, 'state': 'active'}
        if route == ROOT + '/actions/runs':
            assert query['head_sha'] == [HEAD]
            assert query['event'] == ['pull_request']
            return {'total_count': 1, 'workflow_runs': [copy.deepcopy(self.run_data)]}
        if route == ROOT + '/commits/' + HEAD + '/check-runs':
            return {'total_count': len(self.checks), 'check_runs': copy.deepcopy(self.checks)}
        if route == ROOT + '/commits/' + HEAD + '/check-suites':
            return {'total_count': len(self.suites), 'check_suites': copy.deepcopy(self.suites)}
        if route == ROOT + '/commits/' + HEAD + '/status':
            return copy.deepcopy(self.statuses)
        raise AssertionError('Unexpected GET: ' + path)

    def write(self, method, path, payload):
        self.requests.append((method, path, copy.deepcopy(payload)))
        assert (method, path, payload) == ('PUT', ROOT + '/pulls/1/merge', {'sha': HEAD, 'merge_method': 'squash'})
        if self.merge_error:
            raise GitHubError('lost response', retryable=True)
        return {'merged': True, 'sha': OTHER}

    def writes(self):
        return [r for r in self.requests if r[0] != 'GET']


class DependencyTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(dependencies, 'dependencies.py has not been implemented')
        self.client = GitHubFixture()

    def run_module(self):
        return dependencies.run(self.client, CONFIG)

    def assert_skipped(self):
        result = self.run_module()
        self.assertEqual(result[0]['status'], 'skipped', result)
        self.assertTrue(result[0]['reason'])
        self.assertEqual(self.client.writes(), [])

    def test_verified_patch_merges_once_after_second_complete_review(self):
        result = self.run_module()
        self.assertEqual(result[0]['status'], 'merged')
        self.assertEqual(len(self.client.writes()), 1)
        for endpoint in ['/pulls/1', '/pulls/1/files', '/contents/' + FILE,
                         '/actions/runs', '/commits/' + HEAD + '/check-runs']:
            self.assertGreaterEqual(sum(endpoint in r[1] for r in self.client.requests if r[0] == 'GET'), 2)

    def test_annotated_tag_is_dereferenced(self):
        self.client.annotated = 1
        self.assertEqual(self.run_module()[0]['status'], 'merged')

    def test_crlf_and_named_action_step_keep_original_bytes(self):
        self.client.files[FILE] = [x.replace(b'      - uses:', b'      - name: Checkout\n        uses:').replace(b'\n', b'\r\n') for x in self.client.files[FILE]]
        self.assertEqual(self.run_module()[0]['status'], 'merged')

    def test_non_dependabot_fork_draft_closed_and_wrong_base_skip(self):
        for path, value in [('user.login', 'someone'), ('user.type', 'User'), ('draft', True),
                            ('state', 'closed'), ('head.repo.full_name', 'someone/sunbos'),
                            ('base.repo.full_name', 'someone/sunbos'), ('base.ref', 'dev')]:
            with self.subTest(path=path):
                self.client = GitHubFixture()
                obj = self.client.pr
                parts = path.split('.')
                for part in parts[:-1]: obj = obj[part]
                obj[parts[-1]] = value
                self.assert_skipped()

    def test_major_equal_rollback_prerelease_and_action_replacement_skip(self):
        for old, new in [('v4.2.2', 'v5.0.0'), ('v4.2.2', 'v4.2.0'), ('v4.2.2', 'v4.2.1'),
                         ('v4.2.2', 'v4.3.0-beta.1'), ('actions/checkout', 'evil/checkout')]:
            with self.subTest(new=new):
                self.client = GitHubFixture()
                self.client.files[FILE][1] = UPDATED.replace(old, new).encode()
                self.assert_skipped()

    def test_other_bytes_new_files_renames_and_non_workflows_skip(self):
        for mutation in ['run', 'comment', 'whitespace', 'addition', 'removed', 'renamed', 'path', 'mode']:
            with self.subTest(mutation=mutation):
                self.client = GitHubFixture()
                if mutation == 'run': self.client.files[FILE][1] += b'      - run: curl attacker\n'
                elif mutation == 'comment': self.client.files[FILE][1] = UPDATED.replace('name: Example', 'name: Changed').encode()
                elif mutation == 'whitespace': self.client.files[FILE][1] = UPDATED.replace(' # v', '  # v').encode()
                elif mutation in {'addition', 'removed', 'renamed'}: self.client.status = {'addition':'added'}.get(mutation, mutation)
                elif mutation == 'path': self.client.files['README.md'] = self.client.files.pop(FILE)
                else: self.client.mode = '120000'
                self.assert_skipped()

    def test_uses_looking_line_inside_shell_or_multiline_name_is_not_action(self):
        for prefix in ['      - run: |\n', '      - name: |\n', '      - name: "unfinished\n']:
            with self.subTest(prefix=prefix):
                self.client = GitHubFixture()
                self.client.files[FILE] = [x.replace(b'      - uses:', prefix.encode()+b'        uses:') for x in self.client.files[FILE]]
                self.assert_skipped()

    def test_tag_mismatch_or_cycle_does_not_merge(self):
        self.client.tag_sha = OTHER
        self.assert_skipped()
        self.client = GitHubFixture()
        self.client.annotated = 2
        self.assert_skipped()

    def test_same_major_minor_and_preserved_action_subpath_are_supported(self):
        self.client.files[FILE] = [TEXT.replace('v4.2.1', 'v4.1.9').encode(), UPDATED.encode()]
        self.client.files[FILE] = [x.replace(b'checkout@', b'checkout/nested@') for x in self.client.files[FILE]]
        self.assertEqual(self.run_module()[0]['status'], 'merged')

    def test_eight_workflow_group_merges_but_nine_is_skipped(self):
        self.client.files = {f'.github/workflows/example-{i}.yml': [TEXT.encode(), UPDATED.encode()]
                             for i in range(8)}
        self.client.pr['changed_files'] = 8
        self.assertEqual(self.run_module()[0]['status'], 'merged')
        self.client = GitHubFixture()
        self.client.pr['changed_files'] = 9
        self.assert_skipped()

    def test_excessive_action_updates_are_bounded_and_shared_tags_rechecked(self):
        old_line = b'      - uses: actions/checkout@'+OLD.encode()+b' # v4.2.1\n'
        new_line = b'      - uses: actions/checkout@'+NEW.encode()+b' # v4.2.2\n'
        self.client.files[FILE] = [TEXT.encode().replace(old_line,old_line*65),
                                  UPDATED.encode().replace(new_line,new_line*65)]
        self.assert_skipped()
        self.client = GitHubFixture()
        self.client.files[WORKFLOW] = self.client.files[FILE][:]
        self.client.pr['changed_files'] = 2
        self.assertEqual(self.run_module()[0]['status'], 'merged')
        tag_reads = [r for r in self.client.requests if '/git/ref/tags/' in r[1]]
        self.assertEqual(len(tag_reads), 2, 'one tag read per independent audit')

    def test_claimed_blob_sha_and_status_summary_must_agree_with_content(self):
        path = ROOT+'/contents/'+FILE+'?ref='+HEAD
        self.client.overrides[path] = {**content(UPDATED.encode(),FILE), 'sha': OTHER}
        self.assert_skipped()
        self.client = GitHubFixture()
        self.client.statuses.update(state='failure',total_count=1,statuses=[{'state':'success','context':'build'}])
        self.assert_skipped()

    def test_missing_tag_skips_pr_without_treating_it_as_a_network_failure(self):
        self.client.overrides['/repos/actions/checkout/git/ref/tags/v4.2.2'] = GitHubError(status=404)
        self.assert_skipped()

    def test_pending_failed_wrong_head_wrong_suite_or_forged_validation_skip(self):
        for kind in ['pending', 'failure', 'head', 'suite', 'app', 'run_head', 'run_event', 'run_path', 'run_branch', 'run_repo', 'run_failed', 'suite_pending', 'legacy_pending']:
            with self.subTest(kind=kind):
                self.client = GitHubFixture()
                if kind == 'pending': self.client.checks[0]['status'] = 'queued'
                elif kind == 'failure': self.client.checks[0]['conclusion'] = 'failure'
                elif kind == 'head': self.client.checks[0]['head_sha'] = OTHER
                elif kind == 'suite': self.client.checks[0]['check_suite']['id'] = 99
                elif kind == 'app': self.client.checks[0]['app']['id'] = 99
                elif kind.startswith('run_'):
                    key = {'run_head':'head_sha','run_event':'event','run_path':'path','run_branch':'head_branch','run_repo':'repository','run_failed':'conclusion'}[kind]
                    self.client.run_data[key] = {'full_name':'other/repo'} if kind == 'run_repo' else 'wrong'
                elif kind == 'suite_pending': self.client.suites[0]['status'] = 'queued'
                else: self.client.statuses.update(total_count=1,statuses=[{'state':'pending','context':'other'}])
                self.assert_skipped()

    def test_truncation_missing_workflow_and_large_input_skip(self):
        for kind in ['files', 'checks', 'runs', 'tree', 'size']:
            with self.subTest(kind=kind):
                self.client = GitHubFixture()
                if kind == 'files': self.client.pr['changed_files'] = 2
                elif kind == 'checks': self.client.checks *= 60
                elif kind == 'runs': self.client.run_data['workflow_id'] = 99
                elif kind == 'tree': self.client.overrides[ROOT+'/git/trees/'+('1'*40)+'?recursive=1'] = {'sha':'1'*40,'truncated':True,'tree':[]}
                else: self.client.files[FILE] = [x+b'#'+b'x'*150000 for x in self.client.files[FILE]]
                self.assert_skipped()

    def test_pr_base_content_tag_and_ci_changes_during_review_stop_merge(self):
        for kind in ['head', 'base', 'content', 'tag', 'ci']:
            with self.subTest(kind=kind):
                self.client = GitHubFixture()
                count = 0
                def mutate(path):
                    nonlocal count
                    if path == ROOT+'/pulls/1':
                        count += 1
                        if count == 2:
                            if kind == 'head': self.client.pr['head']['sha'] = OTHER
                            elif kind == 'base': self.client.base = OTHER
                            elif kind == 'content': self.client.files[FILE][1] += b'# changed\n'
                            elif kind == 'tag': self.client.tag_sha = OTHER
                            else: self.client.checks[0]['status'] = 'in_progress'
                self.client.before_read = mutate
                self.assert_skipped()

    def test_base_moving_after_second_ci_review_prevents_merge(self):
        count = 0
        def mutate(path):
            nonlocal count
            if path == ROOT+'/git/ref/heads/main':
                count += 1
                if count == 3: self.client.base = OTHER
        self.client.before_read = mutate
        self.assert_skipped()

    def test_failed_or_truncated_additional_checks_block_successful_validate(self):
        for kind in ['extra_failed','truncated','no_validate']:
            with self.subTest(kind=kind):
                self.client = GitHubFixture()
                if kind == 'extra_failed':
                    self.client.checks.append({**self.client.checks[0],'id':25,'name':'lint','conclusion':'failure'})
                elif kind == 'truncated':
                    self.client.overrides[ROOT+'/commits/'+HEAD+'/check-runs?per_page=100&filter=latest'] = {'total_count':3,'check_runs':self.client.checks}
                else:
                    self.client.checks[0]['conclusion'] = 'skipped'
                self.assert_skipped()

    def test_network_failure_stops_scan_and_write_is_never_retried(self):
        self.client.overrides[ROOT+'/pulls/1'] = GitHubError('secret raw content', retryable=True)
        result = self.run_module()
        self.assertEqual(result[0]['status'], 'stopped')
        self.assertNotIn('secret', str(result))
        self.assertEqual(self.client.writes(), [])
        self.client = GitHubFixture()
        self.client.merge_error = True
        result = self.run_module()
        self.assertEqual(result[0]['status'], 'stopped')
        self.assertEqual(len(self.client.writes()), 1)

    def test_bounded_pr_scan_and_invalid_configuration_never_write(self):
        self.client.prs = []
        self.assertEqual(self.run_module(), [])
        query = parse_qs(urlsplit(self.client.requests[0][1]).query)
        self.assertLessEqual(int(query['per_page'][0]), 30)
        self.assertEqual(query['state'], ['open'])
        self.assertEqual(query['base'], ['main'])
        for value in ['../bad', 'owner/repo/other', 'https://github.com/owner/repo']:
            result = dependencies.run(self.client, {**CONFIG,'repository':value})
            self.assertEqual(result[0]['status'], 'stopped')
        self.assertEqual(self.client.writes(), [])

    def test_cli_uses_checked_in_configuration_and_existing_client(self):
        with patch.object(dependencies, 'GitHubClient') as constructor, patch.object(dependencies, 'run', return_value=[] ) as run:
            with patch.dict('os.environ', {'GH_TOKEN':'example-token'}, clear=True):
                self.assertEqual(dependencies.main(), 0)
        constructor.assert_called_once_with('example-token')
        self.assertEqual(run.call_args.args[1]['repository'], 'sunbos/sunbos')


if __name__ == '__main__':
    unittest.main()
