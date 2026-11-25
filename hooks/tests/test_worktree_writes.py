import os
import tempfile
import unittest

from tests.helpers import add_worktree, decision, make_repo, run_hook

WF = '## Проверки\n- pre_push: `true`\n'


def setup(tmp):
    repo = make_repo(tmp, WF, {'CLAUDE.md': '# rules\n', 'README.md': 'x\n'})
    wt = add_worktree(repo, tmp)
    os.makedirs(os.path.join(wt, '.claude'))
    os.symlink(os.path.join(repo, '.claude', 'workflow.md'), os.path.join(wt, '.claude', 'workflow.md'))
    return repo, wt


def run(cwd, command):
    return decision(run_hook('guard-worktree-writes.py', {'tool_name': 'Bash', 'cwd': cwd,
                                                          'tool_input': {'command': command}}))


class WorktreeWritesTest(unittest.TestCase):
    def test_write_to_shared_config_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, wt = setup(tmp)
            for cmd in ('echo x > .claude/workflow.md', "sed -i '' s/a/b/ .claude/workflow.md",
                        'echo x > %s/.claude/workflow.md' % repo, 'cp a.md %s/CLAUDE.md' % repo):
                self.assertEqual(run(wt, cmd), 'deny', cmd)

    def test_cd_inside_command_moves_the_base(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, wt = setup(tmp)
            for cmd in ('mkdir -p lab && cd lab && mkdir .claude && echo x > .claude/workflow.md && echo y > CLAUDE.md',
                        'cd lab && printf "a" > CLAUDE.md'):
                self.assertIsNone(run(wt, cmd), cmd)
            self.assertEqual(run(wt, 'cd .claude && echo x > workflow.md'), 'deny')

    def test_reads_and_own_files_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, wt = setup(tmp)
            for cmd in ('cat .claude/workflow.md', 'grep -r x . 2>/dev/null', 'echo x > README.md', 'echo x > CLAUDE.md'):
                self.assertIsNone(run(wt, cmd), cmd)

    def test_main_repo_session_not_gated(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, wt = setup(tmp)
            self.assertIsNone(run(repo, 'echo x > .claude/workflow.md'))

    def test_broken_stdin_asks(self):
        import json, subprocess
        from tests.helpers import HOOKS
        result = subprocess.run([os.path.join(HOOKS, 'guard-worktree-writes.py')], input='{nope', capture_output=True, text=True)
        self.assertEqual(decision(json.loads(result.stdout)), 'ask')


if __name__ == '__main__':
    unittest.main()
