import os
import tempfile
import unittest

from tests.helpers import decision, make_repo, run_hook, sh

WF = '## Проверки\n- pre_push: `true`\n'


def bash(repo, command, hook='guard-bash-rules.py', **extra):
    payload = {'tool_name': 'Bash', 'cwd': repo, 'tool_input': {'command': command}}
    payload.update(extra)
    return run_hook(hook, payload)


def ticket_repo(tmp, files=None):
    repo = make_repo(tmp, WF, files)
    sh(repo, 'git', 'checkout', '-q', '-b', 'CB-7')
    return repo


def reason(out):
    return out['hookSpecificOutput']['permissionDecisionReason']


def write_file(repo, name, content):
    path = os.path.join(repo, name)
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write(content)
    return path


class PushOptionTest(unittest.TestCase):
    def test_push_option_shown_in_ask(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp)
            out = bash(repo, 'git push -o ci.skip origin dev', 'guard-git-push.py')
            self.assertEqual(decision(out), 'ask')
            self.assertIn('ci.skip', reason(out))


class GhPrCreateTest(unittest.TestCase):
    def test_pr_without_shown_title_or_body_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp)
            for cmd in ('gh pr create --fill', 'gh pr create -f', 'gh pr create --fill-verbose --base dev',
                        'gh pr create --web', 'gh pr create -e', 'gh pr create --title x',
                        'gh pr create --body-file pr.md', 'gh pr create'):
                out = bash(repo, cmd)
                self.assertEqual(decision(out), 'deny', cmd)
                self.assertIn('шагом отправки', reason(out), cmd)

    def test_pr_with_title_and_body_file_asks_with_details(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp)
            write_file(repo, 'pr.md', '## Что сделано\n- правка\n\nЗадача: T-12\n')
            out = bash(repo, 'gh pr create --title "fix(T-12): перенос урока" --body-file pr.md --base dev '
                             '--head T-12 --reviewer friend')
            self.assertEqual(decision(out), 'ask')
            for part in ('fix(T-12): перенос урока', 'T-12 → dev', 'friend', 'описание 4 строк', 'Задача: T-12'):
                self.assertIn(part, reason(out))

    def test_pr_short_flags_and_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp)
            out = bash(repo, 'gh pr create -t "x" -b "тело" -B dev -r a -r b -d')
            self.assertEqual(decision(out), 'ask')
            self.assertIn('a, b', reason(out))
            self.assertIn('черновик', reason(out))
            self.assertIsNone(bash(repo, 'gh pr create --fill --dry-run'))


class GhWritesTest(unittest.TestCase):
    def test_writes_ask(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp)
            for cmd in ('gh pr comment 5 --body x', 'gh pr review 5 --approve', 'gh pr merge 5 --squash',
                        'gh pr edit 5 --body-file b.md', 'gh pr close 5', 'gh -R o/r pr ready 5',
                        'gh issue create --title x --body y', 'gh issue comment 3 -b x', 'gh issue close 3',
                        'gh api -X POST repos/o/r/issues', 'gh api repos/{owner}/{repo}/issues -f title=x',
                        'gh api --method=PATCH repos/o/r/pulls/5', 'gh api repos/o/r/labels -F name=x',
                        'gh api repos/o/r/issues --input body.json', 'gh release create v1', 'gh label delete x'):
                self.assertEqual(decision(bash(repo, cmd)), 'ask', cmd)

    def test_reads_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp)
            for cmd in ('gh pr view 5 --json title,body', 'gh pr diff 5', 'gh pr list --head T-12',
                        'gh pr checks 5', 'gh issue view 3', 'gh api repos/o/r/pulls/5/comments --paginate',
                        'gh api -X GET repos/o/r/pulls/5/reviews', 'gh auth status', 'gh repo view',
                        "gh api graphql -f query='query { viewer { login } }'",
                        'curl https://api.github.com/repos/o/r'):
                self.assertIsNone(bash(repo, cmd), cmd)

    def test_review_publication_shows_count_and_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp)
            write_file(repo, 'review.json', '{"event": "COMMENT", "body": "", "comments": ['
                                            '{"path": "app/A.php", "line": 3, "body": "x"},'
                                            '{"path": "app/B.php", "line": 9, "body": "y"}]}')
            out = bash(repo, 'gh api repos/{owner}/{repo}/pulls/5/reviews --input review.json')
            self.assertEqual(decision(out), 'ask')
            for part in ('Публикация ревью PR', 'комментариев 2', 'app/A.php, app/B.php', 'COMMENT'):
                self.assertIn(part, reason(out))

    def test_reply_and_resolve_ask(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp)
            out = bash(repo, 'gh api repos/o/r/pulls/5/comments/77/replies -f body="поправил"')
            self.assertIn('Ответ в тред ревью', reason(out))
            out = bash(repo, "gh api graphql -f query='mutation { resolveReviewThread(input: {threadId: \"X\"}) { thread { id } } }'")
            self.assertEqual(decision(out), 'ask')
            self.assertIn('Резолв треда', reason(out))

    def test_graphql_query_from_unreadable_file_asks(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp)
            self.assertEqual(decision(bash(repo, 'gh api graphql -F query=@missing.graphql')), 'ask')


class GithubTokenScriptTest(unittest.TestCase):
    def test_curl_and_scripts_with_token_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp)
            script = ("python3 - <<'EOF'\nimport urllib.request\n"
                      "req = urllib.request.Request('https://api.github.com/repos/o/r/pulls/2', "
                      "method='PATCH', headers={'Authorization': 'Bearer ' + GITHUB_TOKEN})\nEOF")
            for cmd in (script,
                        'curl -X POST -H "Authorization: Bearer $GH_TOKEN" https://api.github.com/repos/o/r/issues',
                        'curl -d \'{"body":"x"}\' https://api.github.com/repos/o/r/issues/1/comments'):
                out = bash(repo, cmd)
                self.assertEqual(decision(out), 'deny', cmd)
                self.assertIn('через `gh`', reason(out))

    def test_script_read_with_token_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp)
            cmd = ("python3 -c \"import urllib.request; urllib.request.urlopen(urllib.request.Request("
                   "'https://api.github.com/repos/o/r', headers={'Authorization': 'Bearer ' + GITHUB_TOKEN}))\"")
            self.assertIsNone(bash(repo, cmd))


class PullTest(unittest.TestCase):
    def test_pull_without_rebase_in_ticket_branch_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = ticket_repo(tmp)
            for cmd in ('git pull', 'git pull origin dev', 'git pull --no-rebase', 'git pull --rebase=false'):
                out = bash(repo, cmd)
                self.assertEqual(decision(out), 'deny', cmd)
                self.assertIn('--rebase', out['hookSpecificOutput']['permissionDecisionReason'])

    def test_pull_with_rebase_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = ticket_repo(tmp)
            for cmd in ('git pull --rebase', 'git pull -r origin dev', 'git pull --ff-only'):
                self.assertIsNone(bash(repo, cmd), cmd)

    def test_pull_with_rebase_config_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = ticket_repo(tmp)
            sh(repo, 'git', 'config', 'pull.rebase', 'true')
            self.assertIsNone(bash(repo, 'git pull'))

    def test_pull_outside_ticket_branch_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(bash(make_repo(tmp), 'git pull'))


class BroadAddTest(unittest.TestCase):
    def test_broad_add_in_ticket_branch_asks_with_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = ticket_repo(tmp, {'src/a.ts': 'a\n', 'src/b.ts': 'b\n'})
            with open(os.path.join(repo, 'src', 'a.ts'), 'a') as handle:
                handle.write('x\n')
            for cmd in ('git add -A', 'git add .', 'git add src', 'git add --all'):
                out = bash(repo, cmd)
                self.assertEqual(decision(out), 'ask', cmd)
                self.assertIn('src/a.ts', out['hookSpecificOutput']['permissionDecisionReason'])

    def test_explicit_add_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = ticket_repo(tmp, {'src/a.ts': 'a\n'})
            self.assertIsNone(bash(repo, 'git add src/a.ts'))

    def test_broad_add_outside_ticket_branch_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(bash(make_repo(tmp), 'git add -A'))


class TestLockTest(unittest.TestCase):
    WF = '## Проверки\n- serial_only: `npm run test`\n- test_process: `definitely-not-running-xyz`\n'

    def test_second_start_denied_until_first_finishes(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp, self.WF)
            self.assertIsNone(bash(repo, 'npm run test', tool_use_id='t1'))
            out = bash(repo, 'npm run test', tool_use_id='t2')
            self.assertEqual(decision(out), 'deny')
            done = {'tool_name': 'Bash', 'cwd': repo, 'tool_use_id': 't1',
                    'tool_input': {'command': 'npm run test'}, 'tool_response': {'stdout': '', 'stderr': ''}}
            run_hook('record-make-check.py', done)
            self.assertIsNone(bash(repo, 'npm run test', tool_use_id='t3'))

    def test_stale_lock_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp, self.WF)
            lock = os.path.join(repo, '.git', 'claude-tests.lock')
            with open(lock, 'w') as handle:
                handle.write('{"tool_use_id": "old"}')
            os.utime(lock, (1, 1))
            self.assertIsNone(bash(repo, 'npm run test', tool_use_id='t1'))


if __name__ == '__main__':
    unittest.main()
