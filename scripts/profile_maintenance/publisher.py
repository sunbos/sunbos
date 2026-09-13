"""Publish an already reviewed README as one non-forced child of a frozen base.

Git object creation never changes a branch. The final ref update can only fast
forward to the verified single-parent commit, so a concurrent main commit cannot
be overwritten. State persistence follows publication and is not transactional
with it; a failed checkpoint must never roll back the published README.
"""

import hashlib
from urllib.parse import quote

from .reviewer import apply_updates
from .state import (
    GitHubError, _SHA, _branch_sha, _contents_path, _file, _ref_path, _root,
    _validate_state, load_proposal, save_state,
)


_DEFERRED = {'status': 'deferred', 'commit_sha': None}
_BOT = {'name': 'github-actions[bot]', 'email': '41898282+github-actions[bot]@users.noreply.github.com'}


def _sha(value):
    if not isinstance(value, str) or not _SHA.fullmatch(value) or value == '0' * 40:
        raise ValueError('Invalid direct publication object SHA')
    return value


def _text_hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _blob_hash(text):
    raw = text.encode('utf-8')
    return hashlib.sha1(b'blob ' + str(len(raw)).encode('ascii') + b'\0' + raw).hexdigest()


def _validate_result(config, result, expected_base_sha):
    if not isinstance(config, dict) or config.get('publication_mode') != 'direct':
        raise ValueError('Direct profile publication is not enabled')
    _sha(expected_base_sha)
    if (not isinstance(result, dict) or result.get('status') != 'reviewed'
            or result.get('proposal') is not None
            or not isinstance(result.get('base_readme'), str)
            or not isinstance(result.get('candidate'), str)):
        raise ValueError('Only a completed review without a pending proposal can publish directly')
    state = result.get('state')
    _validate_state(state)
    old_state = result.get('old_state')
    if old_state is not None:
        _validate_state(old_state)
    if result.get('file_sha') is not None:
        _sha(result['file_sha'])
    if (state['fingerprint'] != result.get('fingerprint')
            or state['base_readme_sha256'] != _text_hash(result['base_readme'])
            or state['pr_head_sha'] != (old_state or {}).get('pr_head_sha')):
        raise ValueError('Direct publication state does not match the reviewed inputs')
    verified = apply_updates(result['base_readme'], config, result.get('evidence'), result.get('response'))
    if verified != result['candidate']:
        raise ValueError('Direct publication candidate does not match the validated review')


def _no_proposal(client, config, result):
    if load_proposal(client, config, result.get('old_state'), result['base_readme']) is not None:
        raise ValueError('Pending profile proposals cannot be published directly')


def _main_head(client, root, branch):
    return _branch_sha(client.get(_ref_path(root, branch)), branch)


def _base_tree(client, root, base_sha, readme_sha):
    commit = client.get(root + '/git/commits/' + base_sha)
    if (not isinstance(commit, dict) or commit.get('sha') != base_sha
            or not isinstance(commit.get('tree'), dict)):
        raise ValueError('Invalid frozen base commit')
    tree_sha = _sha(commit['tree'].get('sha'))
    tree = client.get(root + '/git/trees/' + tree_sha)
    if (not isinstance(tree, dict) or tree.get('sha') != tree_sha
            or tree.get('truncated') is not False or not isinstance(tree.get('tree'), list)
            or any(not isinstance(item, dict) for item in tree['tree'])):
        raise ValueError('Expected a complete frozen base tree')
    entries = [item for item in tree['tree'] if item.get('path') == 'README.md']
    if (len(entries) != 1 or entries[0].get('type') != 'blob'
            or entries[0].get('mode') not in ('100644', '100755')
            or entries[0].get('sha') != readme_sha):
        raise ValueError('Frozen README must be a matching regular Git blob')
    return tree_sha, entries[0]['mode']


def _verify_commit(commit, base_sha, tree_sha, expected_sha=None):
    if (not isinstance(commit, dict) or not isinstance(commit.get('tree'), dict)
            or commit['tree'].get('sha') != tree_sha
            or not isinstance(commit.get('parents'), list) or len(commit['parents']) != 1
            or not isinstance(commit['parents'][0], dict) or commit['parents'][0].get('sha') != base_sha):
        raise ValueError('Publication commit must have exactly the frozen base as its parent')
    commit_sha = _sha(commit.get('sha'))
    if commit_sha == base_sha or (expected_sha is not None and commit_sha != expected_sha):
        raise ValueError('Publication commit identity changed')
    return commit_sha


def _verify_compare(value, base_sha, commit_sha, blob_sha):
    if (not isinstance(value, dict) or value.get('status') != 'ahead'
            or any(type(value.get(key)) is not int or value[key] != expected
                   for key, expected in (('ahead_by', 1), ('behind_by', 0), ('total_commits', 1)))
            or any(not isinstance(value.get(key), dict) or value[key].get('sha') != base_sha
                   for key in ('base_commit', 'merge_base_commit'))
            or not isinstance(value.get('commits'), list) or len(value['commits']) != 1
            or not isinstance(value['commits'][0], dict) or value['commits'][0].get('sha') != commit_sha
            or not isinstance(value.get('files'), list) or len(value['files']) != 1):
        raise ValueError('Publication must contain exactly one README-only child commit')
    file = value['files'][0]
    if (not isinstance(file, dict) or file.get('filename') != 'README.md'
            or file.get('status') != 'modified' or file.get('sha') != blob_sha
            or 'previous_filename' in file):
        raise ValueError('Publication comparison contains an unexpected file change')


def _checkpoint(client, config, result):
    state = dict(result['state'])
    state['base_readme_sha256'] = _text_hash(result['candidate'])
    save_state(client, config, state, result.get('file_sha'))


def publish(client, config, result, expected_base_sha):
    """Publish a verified candidate, checkpoint a no-op, or safely defer a race.

No write is retried. If the final ref response is lost, only a fresh GET proving
main equals the preconstructed commit permits a checkpoint. Deferred outcomes
always have a null commit_sha; unreferenced Git objects may have been created.
"""
    _validate_result(config, result, expected_base_sha)
    root = _root(config)
    branch = config['base_branch']
    _no_proposal(client, config, result)
    if _main_head(client, root, branch) != expected_base_sha:
        return dict(_DEFERRED)
    raw, readme_sha = _file(client.get(_contents_path(root, 'README.md', expected_base_sha)))
    if raw != result['base_readme'].encode('utf-8') or readme_sha != _blob_hash(result['base_readme']):
        raise ValueError('Frozen base README differs from the reviewed bytes')
    if result['candidate'] == result['base_readme']:
        _no_proposal(client, config, result)
        if _main_head(client, root, branch) != expected_base_sha:
            return dict(_DEFERRED)
        _checkpoint(client, config, result)
        return {'status': 'checkpointed', 'commit_sha': expected_base_sha}

    base_tree, mode = _base_tree(client, root, expected_base_sha, readme_sha)
    candidate_blob = _blob_hash(result['candidate'])
    # Fail visibly without retrying object writes. An uncertain response can
    # leave an unreferenced object, but cannot change main or justify success.
    blob = client.write('POST', root + '/git/blobs', {'content': result['candidate'], 'encoding': 'utf-8'})
    if not isinstance(blob, dict) or blob.get('sha') != candidate_blob:
        raise ValueError('Created README blob does not match the candidate bytes')
    tree = client.write('POST', root + '/git/trees', {'base_tree': base_tree, 'tree': [
        {'path': 'README.md', 'mode': mode, 'type': 'blob', 'sha': candidate_blob}]})
    if not isinstance(tree, dict) or tree.get('truncated') is not False:
        raise ValueError('Invalid publication tree response')
    tree_sha = _sha(tree.get('sha'))
    commit = client.write('POST', root + '/git/commits', {
        'message': 'docs: refresh evidence-backed profile descriptions',
        'tree': tree_sha, 'parents': [expected_base_sha], 'author': dict(_BOT), 'committer': dict(_BOT)})
    commit_sha = _verify_commit(commit, expected_base_sha, tree_sha)
    _verify_commit(client.get(root + '/git/commits/' + commit_sha), expected_base_sha, tree_sha, commit_sha)
    _verify_compare(client.get(root + '/compare/' + expected_base_sha + '...' + commit_sha),
                    expected_base_sha, commit_sha, candidate_blob)
    _no_proposal(client, config, result)
    if _main_head(client, root, branch) != expected_base_sha:
        return dict(_DEFERRED)
    write_error = None
    try:
        client.write('PATCH', root + '/git/refs/heads/' + quote(branch, safe=''),
                     {'sha': commit_sha, 'force': False})
    except (GitHubError, OSError) as error:
        write_error = error  # The response may be lost after success. Read once.
    current_sha = _main_head(client, root, branch)
    if current_sha != commit_sha:
        if current_sha != expected_base_sha:
            return dict(_DEFERRED)
        if write_error is not None:
            raise write_error
        raise ValueError('Publication ref did not advance to the verified commit')
    _checkpoint(client, config, result)
    return {'status': 'published', 'commit_sha': commit_sha}
