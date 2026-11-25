import json
import os
import subprocess
import tempfile
import unittest

from tests.helpers import HOOKS, decision, make_repo, run_hook

POLICY_HOOKS = ('guard-git-push.py', 'guard-bash-rules.py', 'guard-local-wip.py',
                'confirm-youtrack-write.py', 'design-critique-gate.py')


def raw(name, stdin):
    result = subprocess.run([os.path.join(HOOKS, name)], input=stdin, capture_output=True, text=True, timeout=60)
    return result.returncode, (json.loads(result.stdout) if result.stdout.strip() else None)


class FailClosedTest(unittest.TestCase):
    def test_broken_stdin_asks_instead_of_passing(self):
        for name in POLICY_HOOKS:
            code, out = raw(name, '{not json')
            self.assertEqual(code, 0, name)
            self.assertEqual(decision(out), 'ask', name)
            self.assertIn(name.split('.')[0], out['hookSpecificOutput']['permissionDecisionReason'])

    def test_exception_inside_check_asks(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp, '## Проверки\n- serial_only: `(unbalanced`\n- test_process: `x`\n')
            out = run_hook('guard-bash-rules.py', {'tool_name': 'Bash', 'cwd': repo,
                                                   'tool_input': {'command': 'npm test'}})
            self.assertEqual(decision(out), 'ask')


if __name__ == '__main__':
    unittest.main()
