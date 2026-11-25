import subprocess
import tempfile
import time
import unittest

from tests.helpers import decision, make_repo, run_hook

WF = '## Проверки\n- serial_only: `npm run test|test:e2e`\n- test_process: `sleep 37\\.5`\n'


def run(repo, command):
    return decision(run_hook('guard-bash-rules.py', {'tool_name': 'Bash', 'cwd': repo,
                                                     'tool_input': {'command': command}}))


class SerialTest(unittest.TestCase):
    def test_second_run_denied_while_first_running(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp, WF)
            proc = subprocess.Popen(['sleep', '37.5'])
            try:
                time.sleep(0.2)
                self.assertEqual(run(repo, 'npm run test:e2e'), 'deny')
                self.assertIsNone(run(repo, 'npm run lint'))
            finally:
                proc.kill()

    def test_no_running_process_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(run(make_repo(tmp, WF), 'npm run test'))


if __name__ == '__main__':
    unittest.main()
