import os
import tempfile
import unittest

from tests.helpers import add_worktree, make_repo, run_hook, sh

FILES = {'docs/tasks/README.md': 'readme\n', 'src.ts': 'a\n'}


def setup(tmp):
    repo = make_repo(tmp, None, FILES)
    os.makedirs(os.path.join(repo, '.claude'))
    with open(os.path.join(repo, '.claude', 'worktree-links'), 'w') as handle:
        handle.write('docs/tasks\n')
    with open(os.path.join(repo, '.git', 'info', 'exclude'), 'a') as handle:
        handle.write('.claude/\ndocs/tasks/CB-1/\n')
    os.makedirs(os.path.join(repo, 'docs', 'tasks', 'CB-1'))
    with open(os.path.join(repo, 'docs', 'tasks', 'CB-1', 'notes.md'), 'w') as handle:
        handle.write('notes\n')
    wt = add_worktree(repo, tmp)
    run_hook('worktree-links.py', {'hook_event_name': 'SessionStart', 'cwd': wt})
    return repo, wt


class WorktreeLinksTest(unittest.TestCase):
    def test_ticket_dir_linked_on_session_start(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, wt = setup(tmp)
            self.assertTrue(os.path.islink(os.path.join(wt, 'docs', 'tasks', 'CB-1')))
            with open(os.path.join(wt, 'docs', 'tasks', 'CB-1', 'notes.md')) as handle:
                self.assertEqual(handle.read(), 'notes\n')

    def test_stop_keeps_unstaged_edit_of_tracked_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, wt = setup(tmp)
            readme = os.path.join(wt, 'docs', 'tasks', 'README.md')
            with open(readme, 'a') as handle:
                handle.write('edited\n')
            run_hook('worktree-links.py', {'hook_event_name': 'Stop', 'cwd': wt})
            with open(readme) as handle:
                self.assertEqual(handle.read(), 'readme\nedited\n')

    def test_whole_dir_symlink_replaced_and_tracked_restored(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp, None, FILES)
            os.makedirs(os.path.join(repo, '.claude'))
            with open(os.path.join(repo, '.claude', 'worktree-links'), 'w') as handle:
                handle.write('docs/tasks\n')
            with open(os.path.join(repo, '.git', 'info', 'exclude'), 'a') as handle:
                handle.write('.claude/\n')
            wt = add_worktree(repo, tmp)
            target = os.path.join(wt, 'docs', 'tasks')
            sh(wt, 'rm', '-r', target)
            os.symlink(os.path.join(repo, 'docs', 'tasks'), target)
            run_hook('worktree-links.py', {'hook_event_name': 'SessionStart', 'cwd': wt})
            self.assertFalse(os.path.islink(target))
            self.assertTrue(os.path.isfile(os.path.join(target, 'README.md')))


if __name__ == '__main__':
    unittest.main()
