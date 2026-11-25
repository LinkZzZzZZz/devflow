import os
import tempfile
import unittest

from tests.helpers import HOOKS, make_repo, run_hook, sh

MAKEFILE = 'lint:\n\ttrue\nrector:\n\ttrue\n'


def checked_file(repo):
    return os.path.join(repo, '.git', 'claude-make-check-trees')


def payload(repo):
    return {'tool_name': 'Bash', 'cwd': repo, 'tool_input': {'command': 'make lint rector'},
            'tool_response': {'stdout': 'ok', 'stderr': ''}}


def branch_repo(tmp, workflow):
    repo = make_repo(tmp, workflow, {'Makefile': MAKEFILE})
    sh(repo, 'git', 'update-ref', 'refs/remotes/origin/dev', 'HEAD')
    sh(repo, 'git', 'checkout', '-q', '-b', 'CB-7')
    with open(os.path.join(repo, 'a.txt'), 'w') as handle:
        handle.write('a\n')
    sh(repo, 'git', 'add', 'a.txt')
    sh(repo, 'git', 'commit', '-qm', 'x')
    return repo


class RecordMakeCheckTest(unittest.TestCase):
    def test_not_recorded_without_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = branch_repo(tmp, None)
            out = run_hook('record-make-check.py', payload(repo))
            self.assertFalse(os.path.exists(checked_file(repo)))
            self.assertIsNone(out)

    def test_not_recorded_when_pre_push_configured(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = branch_repo(tmp, '## Проверки\n- pre_push: `make check`\n')
            out = run_hook('record-make-check.py', payload(repo))
            self.assertFalse(os.path.exists(checked_file(repo)))
            self.assertIn('pre-push-check', out['hookSpecificOutput']['additionalContext'])
            self.assertIn(os.path.dirname(HOOKS) + '/hooks/pre-push-check.py', out['hookSpecificOutput']['additionalContext'])


if __name__ == '__main__':
    unittest.main()
