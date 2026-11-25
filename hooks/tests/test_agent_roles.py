import tempfile
import unittest

from tests.helpers import decision, make_repo, run_hook


def bash(repo, command, agent):
    payload = {'tool_name': 'Bash', 'cwd': repo, 'tool_input': {'command': command}}
    if agent:
        payload['agent_type'] = agent
    return run_hook('guard-bash-rules.py', payload)


class ImplementerTest(unittest.TestCase):
    def test_git_mutations_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp)
            for cmd in ('git commit -m x', 'git add a.ts', 'git reset --hard', 'git rebase dev', 'git stash',
                        'cd sub && git commit -am x'):
                out = bash(repo, cmd, 'devflow:implementer')
                self.assertEqual(decision(out), 'deny', cmd)
                self.assertIn('оркестратор', out['hookSpecificOutput']['permissionDecisionReason'])

    def test_reads_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp)
            for cmd in ('git status --short', 'git diff', 'git log -3', 'ls'):
                self.assertIsNone(bash(repo, cmd, 'devflow:implementer'), cmd)

    def test_other_agents_unaffected(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp)
            self.assertIsNone(bash(repo, 'git commit -m x', None))
            self.assertIsNone(bash(repo, 'git commit -m x', 'general-purpose'))


class BlackBoxTest(unittest.TestCase):
    def test_implementation_views_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp)
            for cmd in ('git diff', 'git diff origin/dev...HEAD', 'git show HEAD', 'git blame src.ts',
                        'git log -p', 'git log --patch -3', 'git log -u'):
                out = bash(repo, cmd, 'devflow:black-box-tester')
                self.assertEqual(decision(out), 'deny', cmd)
                self.assertIn('black-box', out['hookSpecificOutput']['permissionDecisionReason'])

    def test_plain_reads_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp)
            for cmd in ('git log --oneline -5', 'git status', 'ls tests', 'grep -rn foo tests'):
                self.assertIsNone(bash(repo, cmd, 'devflow:black-box-tester'), cmd)


class SystemMapperTest(unittest.TestCase):
    def test_git_mutations_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp)
            for cmd in ('git commit -m x', 'git add a.php', 'git push origin CB-1', 'git rebase dev', 'git stash'):
                out = bash(repo, cmd, 'devflow:system-mapper')
                self.assertEqual(decision(out), 'deny', cmd)
                self.assertIn('карт', out['hookSpecificOutput']['permissionDecisionReason'])

    def test_reads_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp)
            for cmd in ('git log --oneline -5', 'git show HEAD:README.md', 'git diff origin/dev...HEAD --stat',
                        'grep -rn Route src', 'git rev-parse HEAD'):
                self.assertIsNone(bash(repo, cmd, 'system-mapper'), cmd)


class DecisionCriticTest(unittest.TestCase):
    def test_git_mutations_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp)
            for cmd in ('git commit -m x', 'git add a.php', 'git reset --hard', 'git cherry-pick abc'):
                out = bash(repo, cmd, 'devflow:decision-critic')
                self.assertEqual(decision(out), 'deny', cmd)
                self.assertIn('critic-N.md', out['hookSpecificOutput']['permissionDecisionReason'])

    def test_reads_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp)
            for cmd in ('git log --oneline -5', 'git diff', 'grep -rn foo src', 'ls'):
                self.assertIsNone(bash(repo, cmd, 'devflow:decision-critic'), cmd)


if __name__ == '__main__':
    unittest.main()
