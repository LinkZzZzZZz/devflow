import os
import subprocess
import tempfile
import unittest

from tests.helpers import HOOKS, decision, make_repo, run_hook, sh

CHECK = os.path.join(HOOKS, 'pre-push-check.py')


def wf(cmd):
    return '## Проверки\n- pre_push: `%s`\n' % cmd


def push_payload(repo):
    return {'tool_name': 'Bash', 'cwd': repo, 'tool_input': {'command': 'git push origin CB-7'}}


def run_check(repo, *args):
    return subprocess.run([CHECK, *args], cwd=repo, capture_output=True, text=True).returncode


def run_check_out(repo, *args):
    return subprocess.run([CHECK, *args], cwd=repo, capture_output=True, text=True)


NOISY_FAIL = "for i in $(seq 1 60); do echo noise-$i; done; echo 'Error: boom'; exit 1"


class PushGateTest(unittest.TestCase):
    def repo(self, tmp, cmd):
        repo = make_repo(tmp, wf(cmd))
        sh(repo, 'git', 'checkout', '-q', '-b', 'CB-7')
        return repo

    def test_push_denied_without_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = run_hook('guard-git-push.py', push_payload(self.repo(tmp, 'true')))
            self.assertEqual(decision(out), 'deny')
            self.assertIn('pre-push-check', out['hookSpecificOutput']['permissionDecisionReason'])
            self.assertIn(CHECK, out['hookSpecificOutput']['permissionDecisionReason'])

    def test_push_asks_after_green_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.repo(tmp, 'true')
            self.assertEqual(run_check(repo), 0)
            self.assertEqual(decision(run_hook('guard-git-push.py', push_payload(repo))), 'ask')

    def test_failed_check_not_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.repo(tmp, 'false')
            self.assertNotEqual(run_check(repo), 0)
            self.assertEqual(decision(run_hook('guard-git-push.py', push_payload(repo))), 'deny')

    def test_check_that_modifies_files_not_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.repo(tmp, 'echo y >> README.md')
            self.assertEqual(run_check(repo), 3)
            sh(repo, 'git', 'checkout', '--', 'README.md')
            self.assertEqual(decision(run_hook('guard-git-push.py', push_payload(repo))), 'deny')

    def test_missing_field_exit_2_and_push_only_asks(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp, '## Проверки\n- prepush: `true`\n')
            sh(repo, 'git', 'checkout', '-q', '-b', 'CB-7')
            result = run_check_out(repo)
            self.assertEqual(result.returncode, 2)
            self.assertIn('добавь', result.stderr)
            self.assertEqual(decision(run_hook('guard-git-push.py', push_payload(repo))), 'ask')

    def test_no_config_only_asks(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp)
            sh(repo, 'git', 'checkout', '-q', '-b', 'CB-7')
            self.assertEqual(decision(run_hook('guard-git-push.py', push_payload(repo))), 'ask')

    def test_no_config_with_makefile_only_asks(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp, None, {'Makefile': 'lint:\n\ttrue\nrector:\n\ttrue\n'})
            sh(repo, 'git', 'checkout', '-q', '-b', 'CB-9')
            payload = {'tool_name': 'Bash', 'cwd': repo, 'tool_input': {'command': 'git push origin CB-9'}}
            self.assertEqual(decision(run_hook('guard-git-push.py', payload)), 'ask')

    def test_non_ticket_branch_not_gated(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp, wf('true'))
            payload = {'tool_name': 'Bash', 'cwd': repo, 'tool_input': {'command': 'git push origin dev'}}
            self.assertEqual(decision(run_hook('guard-git-push.py', payload)), 'ask')


class QuietOutputTest(unittest.TestCase):
    def repo(self, tmp, cmd):
        repo = make_repo(tmp, wf(cmd))
        sh(repo, 'git', 'checkout', '-q', '-b', 'CB-7')
        return repo

    def log(self, repo):
        with open(os.path.join(repo, '.git', 'claude-pre-push.log')) as handle:
            return handle.read()

    def test_success_prints_summary_not_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.repo(tmp, "printf 'NOISE_%s\\n' OUT; printf 'NOISE_%s\\n' ERR >&2; true")
            result = run_check_out(repo)
            self.assertEqual(result.returncode, 0)
            self.assertIn('OK, засчитано', result.stdout)
            self.assertNotIn('NOISE_OUT', result.stdout + result.stderr)
            self.assertIn('NOISE_OUT', self.log(repo))
            self.assertIn('NOISE_ERR', self.log(repo))

    def test_failure_prints_tail_errors_and_log_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.repo(tmp, NOISY_FAIL)
            result = run_check_out(repo)
            self.assertEqual(result.returncode, 1)
            self.assertIn('Error: boom', result.stdout)
            self.assertIn('почини', result.stdout)
            self.assertIn('claude-pre-push.log', result.stdout)
            self.assertNotIn('noise-3\n', result.stdout)
            self.assertIn('noise-3\n', self.log(repo))

    def test_verbose_streams_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.repo(tmp, "printf 'NOISE_%s\\n' OUT; true")
            result = run_check_out(repo, '--verbose')
            self.assertEqual(result.returncode, 0)
            self.assertIn('NOISE_OUT', result.stdout)


class PushGateEnvTest(unittest.TestCase):
    def test_pre_push_sees_plugin_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp, wf('echo "$DEVFLOW_ROOT" > root.txt'))
            sh(repo, 'git', 'checkout', '-q', '-b', 'CB-7')
            self.assertEqual(run_check(repo), 0)
            with open(os.path.join(repo, 'root.txt')) as handle:
                self.assertEqual(handle.read().strip(), os.path.dirname(HOOKS))


class PushGateLocalWipTest(unittest.TestCase):
    def repo(self, tmp):
        repo = make_repo(tmp, wf('true') + '- local_wip: `/Makefile`\n', {'Makefile': 'a\n', 'src.ts': 'a\n'})
        sh(repo, 'git', 'checkout', '-q', '-b', 'CB-7')
        return repo

    def test_dirty_local_wip_does_not_break_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.repo(tmp)
            with open(os.path.join(repo, 'Makefile'), 'a') as handle:
                handle.write('local\n')
            self.assertEqual(run_check(repo), 0)
            self.assertEqual(decision(run_hook('guard-git-push.py', push_payload(repo))), 'ask')

    def test_untracked_file_does_not_break_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.repo(tmp)
            with open(os.path.join(repo, 'notes.md'), 'w') as handle:
                handle.write('x\n')
            self.assertEqual(run_check(repo), 0)
            self.assertEqual(decision(run_hook('guard-git-push.py', push_payload(repo))), 'ask')

    def test_uncommitted_ticket_change_still_gated_until_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.repo(tmp)
            with open(os.path.join(repo, 'src.ts'), 'a') as handle:
                handle.write('b\n')
            self.assertEqual(run_check(repo), 0)
            self.assertEqual(decision(run_hook('guard-git-push.py', push_payload(repo))), 'deny')
            sh(repo, 'git', 'commit', '-qam', 'x')
            self.assertEqual(decision(run_hook('guard-git-push.py', push_payload(repo))), 'ask')


if __name__ == '__main__':
    unittest.main()
