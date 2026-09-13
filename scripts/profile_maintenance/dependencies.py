"""Merge only proven, checked Dependabot action patch/minor updates."""

import hashlib
import json
import os
from pathlib import Path
import re
from urllib.parse import quote, urlencode

from .state import GitHubClient, GitHubError, _file


MAX_PRS = 20
MAX_FILES = 8
MAX_ACTION_UPDATES = 32
MAX_FILE_BYTES = 128 * 1024
MAX_ITEMS = 100
MAX_TREE_ITEMS = 2000
MAX_TAG_DEPTH = 3
CHECK_WORKFLOW = '.github/workflows/profile-maintenance-check.yml'
CHECK_NAME = 'Profile Maintenance Checks'
CONFIG_PATH = Path(__file__).resolve().parents[2] / '.github/profile-maintenance.json'
_SHA = re.compile(r'[0-9a-f]{40}\Z')
_WORKFLOW = re.compile(r'\.github/workflows/[A-Za-z0-9_-][A-Za-z0-9_.-]*\.yml\Z')
_VERSION = rb'(?:0|[1-9][0-9]{0,8})\.(?:0|[1-9][0-9]{0,8})\.(?:0|[1-9][0-9]{0,8})'
_USES = re.compile(rb'(?P<prefix> *(?:- +)?uses: +)'
                   rb'(?P<action>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*)@'
                   rb'(?P<sha>[0-9a-fA-F]{40})(?P<separator> +# +)v'
                   rb'(?P<version>' + _VERSION + rb')(?P<ending> *(?:\r?\n)?)\Z')


class _Unsafe(ValueError):
    """A fixed, non-sensitive reason to leave a PR untouched."""


def _require(condition, reason):
    if not condition:
        raise _Unsafe(reason)


def _sha(value):
    _require(isinstance(value, str) and _SHA.fullmatch(value), '提交标识无效。')
    return value


def _integer(value):
    return type(value) is int and value > 0


def _root(config):
    repository, branch = config.get('repository'), config.get('base_branch')
    _require(isinstance(repository, str) and re.fullmatch(
        r'[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*', repository), '仓库配置无效。')
    _require(isinstance(branch, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]{0,199}', branch)
             and '..' not in branch and '//' not in branch and not branch.endswith(('/', '.', '.lock')),
             '基础分支配置无效。')
    return '/repos/' + repository


def _listed(response, key, limit=MAX_ITEMS):
    _require(isinstance(response, dict), 'GitHub 列表响应无效。')
    items = response.get(key)
    _require(isinstance(items, list) and type(response.get('total_count')) is int
             and response['total_count'] == len(items) and len(items) <= limit
             and all(isinstance(item, dict) for item in items), '列表不完整或超过审查上限。')
    return items


def _base(client, root, branch):
    ref = client.get(root + '/git/ref/heads/' + quote(branch, safe=''))
    _require(isinstance(ref, dict) and ref.get('ref') == 'refs/heads/' + branch
             and isinstance(ref.get('object'), dict) and ref['object'].get('type') == 'commit',
             '基础分支响应无效。')
    return _sha(ref['object'].get('sha'))


def _pull(client, root, config, number):
    pr = client.get(root + '/pulls/' + str(number))
    _require(isinstance(pr, dict) and pr.get('number') == number, 'PR 响应无效。')
    _require(pr.get('state') == 'open' and pr.get('draft') is False and pr.get('merged') is False,
             'PR 不是可审查的开放非草稿。')
    user = pr.get('user', {})
    _require(isinstance(user, dict) and user.get('login') == 'dependabot[bot]' and user.get('type') == 'Bot',
             '只维护官方 Dependabot 创建的 PR。')
    for side in ('head', 'base'):
        value = pr.get(side)
        _require(isinstance(value, dict) and isinstance(value.get('repo'), dict)
                 and value['repo'].get('full_name') == config['repository'], 'PR 必须来自同一仓库。')
        _sha(value.get('sha'))
    _require(pr['base'].get('ref') == config['base_branch'], 'PR 的基础分支不匹配。')
    _require(isinstance(pr['head'].get('ref'), str) and pr['head']['ref'], 'PR head 分支无效。')
    _require(type(pr.get('changed_files')) is int and 1 <= pr['changed_files'] <= MAX_FILES,
             '修改文件数量超出保守维护范围。')
    _require(pr['base']['sha'] == _base(client, root, config['base_branch']), '基础分支已变化。')
    return pr


def _tree(client, root, commit):
    obj = client.get(root + '/git/commits/' + commit)
    _require(isinstance(obj, dict) and obj.get('sha') == commit and isinstance(obj.get('tree'), dict),
             '提交对象无效。')
    tree_sha = _sha(obj['tree'].get('sha'))
    tree = client.get(root + '/git/trees/' + tree_sha + '?recursive=1')
    _require(isinstance(tree, dict) and tree.get('sha') == tree_sha and tree.get('truncated') is False
             and isinstance(tree.get('tree'), list) and len(tree['tree']) <= MAX_TREE_ITEMS,
             '文件树不完整或过大。')
    result = {}
    for item in tree['tree']:
        _require(isinstance(item, dict) and isinstance(item.get('path'), str)
                 and item['path'] not in result, '文件树条目无效。')
        result[item['path']] = item
    return result


def _source(client, root, path, commit, tree):
    entry = tree.get(path, {})
    _require(entry.get('type') == 'blob' and entry.get('mode') == '100644', '只维护既有普通工作流文件。')
    response = client.get(root + '/contents/' + path + '?' + urlencode({'ref': commit}))
    _require(isinstance(response, dict) and response.get('path') == path, '源码路径不匹配。')
    try:
        raw, blob = _file(response)
    except GitHubError as error:
        raise _Unsafe('源码不完整或编码无效。') from error
    _require(len(raw) <= MAX_FILE_BYTES and blob == entry.get('sha')
             and blob == hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest(),
             '源码大小或 blob 校验失败。')
    return raw, blob


def _action_step(lines, index):
    """Recognize only the repository's simple block-style job/step layout.

    This is deliberately not a permissive YAML parser: flow maps, unusual
    indentation and multiline scalar lookalikes remain manual/skipped updates.
    """
    line = lines[index].rstrip(b'\r\n')
    previous = lines[:index]
    if line.startswith(b'        uses: '):
        step = next((x.rstrip(b'\r\n') for x in reversed(previous)
                     if x.strip() and not x.lstrip().startswith(b'#') and len(x)-len(x.lstrip(b' ')) <= 6), b'')
        if not step.startswith(b'      - name: '):
            return False
        name = step[len(b'      - name: '):].strip()
        if not name or name[:1] in (b'|', b'>'):
            return False
        if name[:1] in (b'"', b"'") and (len(name) < 2 or name[-1:] != name[:1]):
            return False
    elif not line.startswith(b'      - uses: '):
        return False
    def parent(max_indent):
        return next((x.strip() for x in reversed(previous) if x.strip()
                     and not x.lstrip().startswith(b'#') and len(x)-len(x.lstrip(b' ')) <= max_indent), b'')
    return (parent(4) == b'steps:' and re.fullmatch(rb'[A-Za-z_][A-Za-z0-9_-]*:', parent(2))
            and parent(0) == b'jobs:')


def _updates(before, after):
    old, new = before.splitlines(keepends=True), after.splitlines(keepends=True)
    _require(len(old) == len(new), '含有 action 引用以外的改动。')
    changes = []
    for i, (left, right) in enumerate(zip(old, new)):
        if left == right:
            continue
        a, b = _USES.fullmatch(left), _USES.fullmatch(right)
        _require(a is not None and b is not None and _action_step(old, i),
                 '无法证明改动仅为真实 action 引用。')
        _require(all(a[key] == b[key] for key in ('prefix', 'action', 'separator', 'ending')),
                 'action 名称、路径或其他字节已改变。')
        action = a['action'].decode('ascii')
        _require(all(p not in {'.', '..'} for p in action.split('/')), 'action 路径无效。')
        old_version, new_version = (tuple(int(p) for p in item['version'].split(b'.')) for item in (a, b))
        _require(old_version[0] == new_version[0] and new_version > old_version
                 and a['sha'].lower() != b['sha'].lower(), '只接受版本升高的同 major 更新。')
        changes.append(('/'.join(action.split('/')[:2]), 'v' + b['version'].decode('ascii'),
                        b['sha'].decode('ascii').lower()))
    _require(changes, '没有符合维护范围的 action 更新。')
    return changes


def _tag(client, repository, tag, expected):
    root = '/repos/' + repository
    ref = client.get(root + '/git/ref/tags/' + quote(tag, safe=''))
    _require(isinstance(ref, dict) and ref.get('ref') == 'refs/tags/' + tag, '精确版本 tag 无法核实。')
    obj, seen = ref.get('object'), set()
    for _ in range(MAX_TAG_DEPTH + 1):
        _require(isinstance(obj, dict), 'tag 对象无效。')
        target = _sha(obj.get('sha'))
        if obj.get('type') == 'commit':
            _require(target == expected, '新 SHA 与 action 仓库精确 tag 不匹配。')
            return
        _require(obj.get('type') == 'tag' and target not in seen and len(seen) < MAX_TAG_DEPTH,
                 'annotated tag 超出解引用上限或形成循环。')
        seen.add(target)
        annotated = client.get(root + '/git/tags/' + target)
        _require(isinstance(annotated, dict) and annotated.get('sha') == target, 'annotated tag 对象不匹配。')
        obj = annotated.get('object')
    raise _Unsafe('tag 超出解引用上限。')


def _completed(item, head):
    return (item.get('head_sha') == head and item.get('status') == 'completed'
            and item.get('conclusion') in {'success', 'neutral', 'skipped'})


def _checks(client, root, config, pr):
    head = pr['head']['sha']
    workflow = client.get(root + '/actions/workflows/profile-maintenance-check.yml')
    _require(isinstance(workflow, dict) and _integer(workflow.get('id')) and workflow.get('path') == CHECK_WORKFLOW
             and workflow.get('name') == CHECK_NAME and workflow.get('state') == 'active',
             '维护检查工作流不可确认。')
    query = urlencode({'event': 'pull_request', 'head_sha': head, 'per_page': MAX_ITEMS})
    runs = _listed(client.get(root + '/actions/runs?' + query), 'workflow_runs')
    matching = []
    for item in runs:
        _require(_completed(item, head), '当前提交有未通过或未完成的工作流。')
        if item.get('workflow_id') == workflow['id']:
            _require(item.get('event') == 'pull_request' and item.get('path') == CHECK_WORKFLOW
                     and item.get('name') == CHECK_NAME and item.get('head_branch') == pr['head']['ref']
                     and item.get('repository', {}).get('full_name') == config['repository']
                     and item.get('head_repository', {}).get('full_name') == config['repository']
                     and item.get('conclusion') == 'success' and _integer(item.get('check_suite_id')),
                     '维护检查并非当前 PR 提交的成功运行。')
            matching.append(item)
    _require(matching, '尚无当前 PR 提交的成功维护检查。')
    checks = _listed(client.get(root + '/commits/' + head + '/check-runs?per_page=100&filter=latest'), 'check_runs')
    suites = _listed(client.get(root + '/commits/' + head + '/check-suites?per_page=100'), 'check_suites')
    _require(checks and suites and all(_completed(c, head) for c in checks + suites),
             '存在失败、待处理或无法确认的检查。')
    suite_ids = {r['check_suite_id'] for r in matching}
    _require(suite_ids <= {s.get('id') for s in suites}, '维护检查 suite 不完整。')
    _require(any(c.get('name') == 'validate' and c.get('conclusion') == 'success'
                 and c.get('check_suite', {}).get('id') in suite_ids
                 and c.get('app', {}).get('id') == 15368 and c['app'].get('slug') == 'github-actions'
                 for c in checks), '缺少对应 GitHub Actions suite 的成功 validate 检查。')
    status = client.get(root + '/commits/' + head + '/status?per_page=100')
    statuses = _listed(status, 'statuses')
    # GitHub returns state=pending even when there are zero legacy statuses.
    _require(status.get('sha') == head and all(s.get('state') == 'success' for s in statuses)
             and status.get('state') in ({'success'} if statuses else {'pending', 'success'}),
             '存在未通过的传统提交状态。')


def _audit(client, config, root, number, expected=None):
    pr = _pull(client, root, config, number)
    if expected is not None:
        _require((pr['base']['sha'], pr['head']['sha']) == expected[:2],
                 '审查期间 PR 或基础提交已变化。')
    files = client.get(root + '/pulls/' + str(number) + '/files?per_page=9')
    _require(isinstance(files, list) and len(files) == pr['changed_files'], 'PR 文件列表不完整。')
    paths = []
    for item in files:
        _require(isinstance(item, dict) and item.get('status') == 'modified'
                 and isinstance(item.get('filename'), str) and _WORKFLOW.fullmatch(item['filename'])
                 and not item.get('previous_filename') and item['filename'] not in paths,
                 'PR 包含范围外、新增、删除或重命名文件。')
        paths.append(item['filename'])
    base, head = pr['base']['sha'], pr['head']['sha']
    base_tree, head_tree = _tree(client, root, base), _tree(client, root, head)
    proof, tags, update_count = [], set(), 0
    for item in files:
        path = item['filename']
        before, old_blob = _source(client, root, path, base, base_tree)
        after, new_blob = _source(client, root, path, head, head_tree)
        _require(item.get('sha') == new_blob, 'PR 文件列表与固定 head 内容不一致。')
        updates = _updates(before, after)
        update_count += len(updates)
        _require(update_count <= MAX_ACTION_UPDATES, 'action 更新数量超过审查上限。')
        tags.update(updates)
        proof.append((path, old_blob, new_blob))
    for repository, tag, commit in sorted(tags):
        _tag(client, repository, tag, commit)
    _checks(client, root, config, pr)
    return base, head, tuple(sorted(proof))


def run(client, config):
    """No checkout, PR code execution, comment, write retry or auto-merge enablement."""
    results, number = [], None
    try:
        root = _root(config)
        query = urlencode({'state': 'open', 'base': config['base_branch'], 'per_page': MAX_PRS})
        pulls = client.get(root + '/pulls?' + query)
        _require(isinstance(pulls, list) and len(pulls) <= MAX_PRS, '开放 PR 列表响应无效。')
        seen = set()
        for item in pulls:
            _require(isinstance(item, dict) and _integer(item.get('number')) and item['number'] not in seen,
                     '开放 PR 标识无效。')
            number = item['number']
            seen.add(number)
            try:
                frozen = _audit(client, config, root, number)
                _require(_audit(client, config, root, number, frozen) == frozen, '审查期间 PR 或基础内容已变化。')
                _require(_base(client, root, config['base_branch']) == frozen[0], '合并前基础分支已变化。')
            except _Unsafe as error:
                results.append({'number': number, 'status': 'skipped', 'reason': str(error)})
                continue
            except GitHubError as error:
                if error.status != 404:
                    raise
                results.append({'number': number, 'status': 'skipped', 'reason': '所需公开文件、版本或检查不存在，保留 PR。'})
                continue
            response = client.write('PUT', root + '/pulls/' + str(number) + '/merge',
                                    {'sha': frozen[1], 'merge_method': 'squash'})
            if not isinstance(response, dict) or response.get('merged') is not True:
                results.append({'number': number, 'status': 'stopped', 'reason': '合并结果未确认，未重试写操作。'})
                break
            results.append({'number': number, 'status': 'merged', 'head_sha': frozen[1]})
    except (GitHubError, _Unsafe, KeyError, TypeError, AttributeError, ValueError):
        results.append({'number': number, 'status': 'stopped', 'reason': 'GitHub 请求或响应无法确认，已安全停止且未重试写操作。'})
    return results


def main():
    try:
        config = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
        token = os.environ.get('GH_TOKEN', '')
        if not token:
            raise ValueError('missing token')
        results = run(GitHubClient(token), config)
    except (OSError, ValueError, GitHubError):
        results = [{'number': None, 'status': 'stopped', 'reason': '依赖维护配置不可用，未执行写操作。'}]
    print(json.dumps(results, ensure_ascii=False))
    return 1 if any(item['status'] == 'stopped' for item in results) else 0


if __name__ == '__main__':
    raise SystemExit(main())
