"""A bounded profile review: public evidence in, validated Markdown out."""

import argparse
import hashlib
import html
import json
import os
import re
from urllib.parse import quote
from pathlib import Path
import sys

from .collector import collect
from .reviewer import apply_updates, extract_blocks, protected_text, review
from .state import (
    GitHubClient, GitHubError, assert_base_unchanged, fingerprint, load_proposal,
    load_state, save_state,
)

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / '.github/profile-maintenance.json'


def text_hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def push_expectation(client, config, old_state):
    """Capture the trusted branch head, including deletion after a merged PR."""
    branch = config['proposal_branch']
    try:
        ref = client.get('/repos/' + config['repository'] + '/git/ref/heads/' + quote(branch, safe=''))
    except GitHubError as error:
        if error.status == 404:
            return '0' * 40
        raise
    actual = ref.get('object', {}).get('sha') if isinstance(ref, dict) else None
    if (not isinstance(ref, dict) or ref.get('ref') != 'refs/heads/' + branch or ref.get('object', {}).get('type') != 'commit'
            or not isinstance(actual, str) or not re.fullmatch('[0-9a-f]{40}', actual)
            or actual != (old_state or {}).get('pr_head_sha')):
        raise ValueError('机器人分支已变化，不能确认推送期望。')
    return actual


def prepare(config, readme, client, *, api_key='', dry_run=False, force=False, preview=False):
    """Pure preparation apart from GETs and one optional model call; no writes."""
    if dry_run and preview:
        raise ValueError('dry-run 与 preview 不能同时使用。')
    protected = protected_text(readme, config)
    old_state, file_sha = load_state(client, config)
    # Cache identical reads only during collection, never during concurrency checks.
    responses = {}
    def get(path):
        if path not in responses:
            responses[path] = client.get('/' + path.lstrip('/'))
        return responses[path]
    collected = collect(config, get)
    digest = fingerprint(config, collected['snapshot'], protected)
    common = {
        'fingerprint': digest,
        'source_count': len(config.get('sources', [])),
        'evidence_count': len(collected['evidence']),
    }
    if old_state and old_state.get('fingerprint') == digest and not force:
        return {**common, 'status': 'unchanged', 'publish': False}
    if dry_run:
        return {**common, 'status': 'dry-run', 'publish': False,
                'snapshot': collected['snapshot'],
                'evidence': collected['evidence']}
    # A preview evaluates this checkout, never a pending remote proposal.
    proposal = None if preview else load_proposal(client, config, old_state, readme)
    current = proposal['readme'] if proposal else readme
    if protected_text(current, config) != protected:
        raise ValueError('机器人 PR 的固定内容与主页不一致，请先人工处理。')
    if not api_key:
        raise ValueError('检测到待审查证据，请先在 GitHub Secret 配置 DEEPSEEK_API_KEY。')
    response = review(config, extract_blocks(current, config), collected['evidence'], api_key)
    candidate = apply_updates(current, config, collected['evidence'], response)
    if preview:
        return {
            **common, 'status': 'preview', 'publish': False,
            'candidate': candidate, 'base_readme': readme,
            'response': response, 'evidence': collected['evidence'],
            'snapshot': collected['snapshot'],
        }
    next_state = {
        'schema_version': 1,
        'fingerprint': digest,
        'snapshot': collected['snapshot'],
        'base_readme_sha256': text_hash(readme),
        'pr_head_sha': proposal['head_sha'] if proposal else (old_state or {}).get('pr_head_sha'),
    }
    return {
        **common, 'status': 'reviewed',
        'publish': candidate != current,
        'expected_pr_head': push_expectation(client, config, old_state) if candidate != current else None,
        'candidate': candidate, 'base_readme': readme,
        'old_state': old_state, 'file_sha': file_sha, 'state': next_state,
        'response': response, 'evidence': collected['evidence'],
        'proposal': proposal,
    }


def review_body(result):
    """Describe only the reviewed evidence; no run timestamps or raw model HTML."""
    response = result['response']
    summary = html.escape(response['summary']).replace('@', '＠')
    lines = [
        '根据选定公开项目的变化，更新主页中允许维护的描述。', '', summary, '',
        '核心项目和排序、流程示意、脱敏案例、访问徽章及图表均由程序保护。',
        '这是 AI 草稿；请核对事实、本人贡献归属以及未合并／已合并的区别后再发布。', '',
        '本次建议及依据：', '',
    ]
    evidence = {item['id']: item for item in result['evidence']}
    for update in response['updates']:
        lines.append(f"- `{update['block_id']}`")
        for evidence_id in update['evidence_ids']:
            item = evidence[evidence_id]
            lines.append(f"  - [{evidence_id}]({item['url']})")
    lines.extend(['', '本工作流已执行单元测试和局部内容校验，不代表来源仓库的全部测试已通过。'])
    return '\n'.join(lines) + '\n'


def ensure_fresh(client, config, result):
    """Recheck the base and bot branch before publication or state persistence."""
    assert_base_unchanged(client, config, result['base_readme'])
    proposal = load_proposal(client, config, result['old_state'], result['base_readme'])
    expected = result['proposal']
    if (proposal or {}).get('head_sha') != (expected or {}).get('head_sha'):
        raise ValueError('审查期间机器人 PR 已变化，停止发布旧建议。')


def checkpoint(client, config, result, pr_head_sha):
    if result.get('status') != 'reviewed':
        raise ValueError('只有成功完成审查的结果可以更新状态。')
    assert_base_unchanged(client, config, result['base_readme'])
    next_state = dict(result['state'])
    if result['publish']:
        if not pr_head_sha:
            raise ValueError('PR 发布缺少确认的 head SHA，不记录完成状态。')
        next_state['pr_head_sha'] = pr_head_sha
        # Verify publication against the actual API state, not only Action output.
        published = load_proposal(client, config, next_state, result['base_readme'])
        if published and published['readme'] != result['candidate']:
            raise ValueError('远端候选内容与验证结果不一致，停止记录状态。')
        if result['candidate'] != result['base_readme'] and not published:
            raise ValueError('未找到发布后的开放 PR，停止记录状态。')
    else:
        ensure_fresh(client, config, result)
    save_state(client, config, next_state, result['file_sha'])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'guard', 'checkpoint', 'validate'])
    parser.add_argument('--output-dir', type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--dry-run', action='store_true')
    mode.add_argument('--preview', action='store_true',
                      help='使用模型生成当前分支预览，不发布或记录完成状态')
    parser.add_argument('--force', action='store_true')
    parser.add_argument('--pr-head-sha', default='')
    args = parser.parse_args(argv)
    config = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
    controller = hashlib.sha256()
    for source in sorted(Path(__file__).parent.glob('*.py')):
        controller.update(source.name.encode('utf-8') + b'\0' + source.read_bytes())
    config['controller_sha256'] = controller.hexdigest()
    if os.getenv('DEEPSEEK_MODEL'):
        config['model'] = os.environ['DEEPSEEK_MODEL']
    if args.command == 'validate':
        blocks = extract_blocks((ROOT / 'README.md').read_bytes().decode('utf-8'), config)
        print(f'已校验 {len(blocks)} 个受管区域。')
        return
    if args.output_dir is None:
        parser.error('--output-dir is required')
    client = GitHubClient(os.getenv('GH_TOKEN', ''))
    output = args.output_dir.resolve()
    if args.command == 'prepare':
        readme = (ROOT / 'README.md').read_bytes().decode('utf-8')
        # Read-only modes may intentionally inspect a proposed README before merge.
        if not args.dry_run and not args.preview:
            assert_base_unchanged(client, config, readme)
        result = prepare(config, readme, client, api_key=os.getenv('DEEPSEEK_API_KEY', ''),
                         dry_run=args.dry_run, force=args.force, preview=args.preview)
        result['config_fingerprint'] = text_hash(json.dumps(config, sort_keys=True))
        output.mkdir(parents=True, exist_ok=True)
        (output / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        if result['status'] in {'reviewed', 'preview'}:
            if result['status'] == 'reviewed':
                ensure_fresh(client, config, result)
            (output / 'candidate.md').write_text(result['candidate'], encoding='utf-8')
            (output / 'pr-body.md').write_text(review_body(result), encoding='utf-8')
        if result['publish'] and os.getenv('GITHUB_ENV'):
            with open(os.environ['GITHUB_ENV'], 'a', encoding='utf-8') as handle:
                handle.write(f"PROFILE_EXPECTED_PR_SHA={result['expected_pr_head']}\n")
        github_output = os.getenv('GITHUB_OUTPUT')
        if github_output:
            with open(github_output, 'a', encoding='utf-8') as handle:
                handle.write(f"status={result['status']}\npublish={str(result['publish']).lower()}\n")
        message = {
            'unchanged': '证据未变化，已跳过模型和写入。',
            'dry-run': '公开证据采集完成；dry-run 未调用模型或写入远端。',
            'preview': '模型预览与局部校验完成；仅生成候选文件，未发布或保存完成状态。',
            'reviewed': '证据审查与局部校验完成，等待发布或记录无需修改的结果。',
        }[result['status']]
        print(message)
        if os.getenv('GITHUB_STEP_SUMMARY'):
            with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as handle:
                handle.write(message + '\n')
    else:
        result = json.loads((output / 'result.json').read_text(encoding='utf-8'))
        if result['config_fingerprint'] != text_hash(json.dumps(config, sort_keys=True)):
            raise ValueError('审查配置已变化，请重新运行。')
        if args.command == 'guard':
            if result.get('status') != 'reviewed':
                raise ValueError('预览或未完成审查的结果不能进入发布流程。')
            ensure_fresh(client, config, result)
        else:
            checkpoint(client, config, result, args.pr_head_sha)
            print('成功审查的证据已保存到状态分支。')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError, OSError, KeyError, TypeError) as error:
        # Exception text from local validation is safe; never dump HTTP responses.
        print(f'主页维护停止：{error}', file=sys.stderr)
        raise SystemExit(1)
