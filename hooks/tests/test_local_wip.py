import os
import tempfile
import unittest

from tests.helpers import decision, make_repo, run_hook, sh

WF = '## Не коммитить\n- local_wip: `Makefile, src/**/environment.ts, /docker-compose.yml`\n'
FILES = {'Makefile': 'a\n', 'src/config/environment.ts': 'a\n', 'src/main.ts': 'a\n',
         'docker-compose.yml': 'a\n', 'src/test/docker-compose.yml': 'a\n'}


def touch(repo, rel):
    with open(os.path.join(repo, rel), 'a') as handle:
        handle.write('changed\n')


def run(repo, command):
    return decision(run_hook('guard-local-wip.py',
                             {'tool_name': 'Bash', 'cwd': repo, 'tool_input': {'command': command}}))


class LocalWipTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = make_repo(self.tmp.name, WF, FILES)

    def tearDown(self):
        self.tmp.cleanup()

    def test_explicit_wip_path_denied(self):
        touch(self.repo, 'Makefile')
        self.assertEqual(run(self.repo, 'git add Makefile src/main.ts'), 'deny')

    def test_add_all_with_dirty_wip_denied(self):
        touch(self.repo, 'src/config/environment.ts')
        touch(self.repo, 'src/main.ts')
        for cmd in ('git add -A', 'git add .', 'git add src', 'git add -u', 'git commit -am "x"'):
            self.assertEqual(run(self.repo, cmd), 'deny', cmd)

    def test_add_all_with_clean_wip_passes(self):
        touch(self.repo, 'src/main.ts')
        self.assertIsNone(run(self.repo, 'git add -A && git commit -m "x"'))

    def test_root_anchored_pattern(self):
        touch(self.repo, 'src/test/docker-compose.yml')
        self.assertIsNone(run(self.repo, 'git add src/test/docker-compose.yml'))
        touch(self.repo, 'docker-compose.yml')
        self.assertEqual(run(self.repo, 'git add docker-compose.yml'), 'deny')

    def test_commit_with_staged_wip_denied(self):
        touch(self.repo, 'Makefile')
        sh(self.repo, 'git', 'add', 'Makefile')
        self.assertEqual(run(self.repo, 'git commit -m "x"'), 'deny')

    def test_commit_with_positional_wip_path_denied(self):
        touch(self.repo, 'Makefile')
        self.assertEqual(run(self.repo, 'git commit -m x Makefile'), 'deny')
        self.assertEqual(run(self.repo, 'git commit -m "fix: a" -- Makefile'), 'deny')

    def test_commit_message_values_are_not_paths(self):
        touch(self.repo, 'Makefile')
        touch(self.repo, 'src/main.ts')
        self.assertIsNone(run(self.repo, 'git commit -m Makefile src/main.ts'))
        self.assertIsNone(run(self.repo, 'git commit --author "a <b@c>" -m "x" src/main.ts'))

    def test_no_config_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp, None, FILES)
            touch(repo, 'Makefile')
            self.assertIsNone(run(repo, 'git add -A'))


if __name__ == '__main__':
    unittest.main()
