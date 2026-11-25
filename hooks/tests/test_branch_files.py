import os
import subprocess
import tempfile
import unittest

from tests.helpers import HOOKS, make_repo, sh

SCRIPT = os.path.join(HOOKS, 'branch-files.py')


def files(repo, *args):
    result = subprocess.run([SCRIPT, *args], cwd=repo, capture_output=True, text=True)
    return result.stdout.split()


def commit(repo, name, content='x\n'):
    path = os.path.join(repo, name)
    os.makedirs(os.path.dirname(path) or repo, exist_ok=True)
    with open(path, 'w') as handle:
        handle.write(content)
    sh(repo, 'git', 'add', name)
    sh(repo, 'git', 'commit', '-qm', name)


class BranchFilesTest(unittest.TestCase):
    def test_own_commits_only_excluding_epic_branch(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp)
            sh(repo, 'git', 'update-ref', 'refs/remotes/origin/dev', 'HEAD')
            sh(repo, 'git', 'checkout', '-qb', 'release-x')
            commit(repo, 'epic.php')
            sh(repo, 'git', 'update-ref', 'refs/remotes/origin/release-x', 'HEAD')
            sh(repo, 'git', 'checkout', '-qb', 'YR-1')
            commit(repo, 'src/a.php')
            commit(repo, 'src/b.ts')
            self.assertEqual(files(repo), ['src/a.php', 'src/b.ts'])
            self.assertEqual(files(repo, '--ext', 'php'), ['src/a.php'])

    def test_branch_at_remote_tip_gives_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp)
            sh(repo, 'git', 'update-ref', 'refs/remotes/origin/dev', 'HEAD')
            sh(repo, 'git', 'checkout', '-qb', 'YR-2')
            self.assertEqual(files(repo), [])

    def test_pushed_branch_still_counts_own_commits(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp)
            sh(repo, 'git', 'update-ref', 'refs/remotes/origin/dev', 'HEAD')
            sh(repo, 'git', 'checkout', '-qb', 'YR-3')
            commit(repo, 'src/a.php')
            sh(repo, 'git', 'update-ref', 'refs/remotes/origin/YR-3', 'HEAD')
            commit(repo, 'src/c.php')
            self.assertEqual(files(repo, '--ext', 'php'), ['src/a.php', 'src/c.php'])


if __name__ == '__main__':
    unittest.main()
