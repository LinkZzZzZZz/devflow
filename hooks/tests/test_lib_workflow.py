import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib_workflow import get, get_list, load, matches
from tests.helpers import add_worktree, make_repo

WF = """# workflow
## Тикет
- key: `CB-\\d+`
## Проверки
- pre_push: `npx prettier --check "src/**/*.ts" && npm run lint`
## Не коммитить
- local_wip: `Makefile, src/**/environment.ts`
- local_wip: `docker-compose.yml`
- база: `dev`
"""


class LoadTest(unittest.TestCase):
    def test_no_config_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(load(make_repo(tmp)))

    def test_fields_parsed(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = load(make_repo(tmp, WF))
            self.assertEqual(get(cfg, 'key'), 'CB-\\d+')
            self.assertEqual(get(cfg, 'pre_push'), 'npx prettier --check "src/**/*.ts" && npm run lint')
            self.assertEqual(get_list(cfg, 'local_wip'), ['Makefile', 'src/**/environment.ts', 'docker-compose.yml'])
            self.assertIsNone(get(cfg, 'база'))
            self.assertIsNone(get(cfg, 'base'))

    def test_worktree_finds_main_repo_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp, WF)
            wt = add_worktree(repo, tmp)
            cfg = load(wt)
            self.assertEqual(cfg['path'], os.path.join(os.path.realpath(repo), '.claude', 'workflow.md'))
            self.assertEqual(os.path.realpath(cfg['root']), os.path.realpath(wt))

    def test_missing_cwd_uses_existing_parent(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp, WF)
            self.assertIsNotNone(load(os.path.join(repo, 'common', 'migrations', 'new')))


class MatchesTest(unittest.TestCase):
    def test_globs(self):
        pats = ['Makefile', 'src/**/environment.ts', 'docker-compose.yml']
        self.assertTrue(matches('Makefile', pats))
        self.assertTrue(matches('src/environment.ts', pats))
        self.assertTrue(matches('src/config/env/environment.ts', pats))
        self.assertTrue(matches('./docker-compose.yml', pats))
        self.assertFalse(matches('src/test/docker-compose.yml', ['/docker-compose.yml']))
        self.assertFalse(matches('src/main.ts', pats))


class KeyCaseTest(unittest.TestCase):
    def test_keys_are_case_insensitive(self):
        import lib_workflow
        fields = lib_workflow.parse('## Код\n- Hooks: `Strict_Types`\n- PRE_PUSH: `make check`\n')
        self.assertEqual(fields['hooks'], ['Strict_Types'])
        self.assertEqual(fields['pre_push'], ['make check'])


if __name__ == '__main__':
    unittest.main()
