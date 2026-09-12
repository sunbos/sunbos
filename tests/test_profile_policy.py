"""Keep the profile owner's agreed editorial boundaries reviewable in CI."""
import json
from pathlib import Path
import unittest

from scripts.profile_maintenance.reviewer import extract_blocks, protected_text

ROOT = Path(__file__).resolve().parents[1]


class ProfilePolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = json.loads((ROOT / '.github/profile-maintenance.json').read_text())
        cls.readme = (ROOT / 'README.md').read_bytes().decode('utf-8')
        cls.blocks = extract_blocks(cls.readme, cls.config)
        cls.fixed = protected_text(cls.readme, cls.config)

    def test_anonymized_cases_are_entirely_outside_model_input(self):
        start = self.readme.index('### 设备稳定性测试 Agent')
        end = self.readme.index('## 开源协作')
        cases = self.readme[start:end]
        self.assertIn(cases, self.fixed)
        for block in self.blocks.values():
            self.assertNotIn('非开源案例', block)

    def test_header_flows_and_charts_remain_fixed(self):
        for line in self.readme.splitlines():
            if (line.startswith('#') or line.startswith('> **') or
                    'page_id=sunbos.sunbos' in line or '<picture>' in line or
                    '<img ' in line or '<source ' in line):
                self.assertIn(line, self.fixed)
        self.assertLess(self.readme.index('page_id=sunbos.sunbos'), self.readme.index('## 项目与实践'))

    def test_curated_stars_keep_their_identities_and_only_one_cell_is_editable(self):
        for repository in ('sqlalchemy/sqlalchemy', 'FactoryBoy/factory_boy',
                           'langchain-ai/langchain', 'NousResearch/hermes-agent',
                           'PrefectHQ/fastmcp', 'microsoft/markitdown'):
            self.assertIn('https://github.com/' + repository, self.fixed)
        self.assertEqual(self.config['blocks']['sqlalchemy']['kind'], 'table-cell')
        self.assertNotIn('\n', self.blocks['sqlalchemy'])
        self.assertNotIn('|', self.blocks['sqlalchemy'])

    def test_sources_and_preservation_limits_match_editorial_policy(self):
        sources = {source['id'] for source in self.config['sources']}
        for spec in self.config['blocks'].values():
            self.assertGreaterEqual(spec['min_ratio'], 0.9)
            self.assertTrue(set(spec['source_ids']) <= sources)
        for source in self.config['sources']:
            if 'pull' in source:
                self.assertEqual(source['expected_author'], 'sunbos')


if __name__ == '__main__':
    unittest.main()
