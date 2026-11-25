import os
import subprocess
import tempfile
import unittest

from tests.helpers import HOOKS, decision, make_repo, run_hook, sh

GATE = os.path.join(HOOKS, 'knowledge-base-check.py')
CHECK = os.path.join(HOOKS, 'pre-push-check.py')

WF = """## Тикет
- key: `CB-\\d+`
## Git
- base: `dev`
## Пути
- tasks_dir: `docs/tasks`
## Проверки
- pre_push: `true`
## База знаний
- architecture_dir: `docs/architecture`
- architecture_ignore: `tests/**`
"""
WF_NO_KB = WF.split('## База знаний')[0]


def run_gate(repo):
    return subprocess.run([GATE], cwd=repo, capture_output=True, text=True)


def write(repo, rel, content):
    path = os.path.join(repo, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write(content)


def commit(repo, rel, content, message='x'):
    write(repo, rel, content)
    sh(repo, 'git', 'add', rel)
    sh(repo, 'git', 'commit', '-q', '-m', message)
    return subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=repo, capture_output=True, text=True).stdout.strip()


def card(paths, sha, extra=''):
    return '---\nmodule: billing\npaths: [%s]\nсверено: %s\n---\n## Назначение и границы\n%s' % (paths, sha, extra)


class KnowledgeBaseTest(unittest.TestCase):
    def repo(self, tmp, workflow=WF):
        repo = make_repo(tmp, workflow, {'README.md': 'x\n'})
        sh(repo, 'git', 'checkout', '-q', '-b', 'CB-7')
        return repo

    def test_field_missing_silent_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.repo(tmp, WF_NO_KB)
            commit(repo, 'src/Billing/Foo.php', '<?php\n')
            result = run_gate(repo)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('не настроена', result.stdout)

    def test_map_verified_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.repo(tmp)
            sha = commit(repo, 'src/Billing/Foo.php', '<?php\n')
            commit(repo, 'docs/architecture/billing.md', card('src/Billing/**', sha))
            write(repo, 'docs/tasks/CB-7/map.md', '# CB-7\n')
            result = run_gate(repo)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('1 карт сверено', result.stdout)

    def test_no_map_fails_with_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.repo(tmp)
            commit(repo, 'src/Billing/Foo.php', '<?php\n')
            write(repo, 'docs/tasks/CB-7/map.md', '# CB-7\n')
            result = run_gate(repo)
            self.assertEqual(result.returncode, 5, result.stdout)
            self.assertIn('нет карты для src/Billing/Foo.php', result.stdout)
            self.assertIn('/map src/Billing area', result.stdout)

    def test_map_unchanged_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp, WF, {'README.md': 'x\n'})
            base = commit(repo, 'docs/architecture/billing.md', card('src/Billing/**', 'HEAD'))
            sh(repo, 'git', 'checkout', '-q', '-b', 'CB-7')
            commit(repo, 'src/Billing/Foo.php', '<?php\n')
            write(repo, 'docs/tasks/CB-7/map.md', '# CB-7\n')
            result = run_gate(repo)
            self.assertEqual(result.returncode, 5, result.stdout)
            self.assertIn('billing.md не сверена с кодом ветки', result.stdout)
            self.assertIn('system-mapper', result.stdout)
            self.assertNotIn(base[:7], result.stdout)

    def test_sverено_points_to_base_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp, WF, {'README.md': 'x\n'})
            base_sha = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=repo, capture_output=True, text=True).stdout.strip()
            sh(repo, 'git', 'checkout', '-q', '-b', 'CB-7')
            commit(repo, 'src/Billing/Foo.php', '<?php\n')
            commit(repo, 'docs/architecture/billing.md', card('src/Billing/**', base_sha))
            write(repo, 'docs/tasks/CB-7/map.md', '# CB-7\n')
            result = run_gate(repo)
            self.assertEqual(result.returncode, 5, result.stdout)
            self.assertIn('не сверена', result.stdout)

    def test_map_md_missing_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.repo(tmp)
            sha = commit(repo, 'src/Billing/Foo.php', '<?php\n')
            commit(repo, 'docs/architecture/billing.md', card('src/Billing/**', sha))
            result = run_gate(repo)
            self.assertEqual(result.returncode, 5, result.stdout)
            self.assertIn('карта области CB-7/map.md отсутствует', result.stdout)
            self.assertIn('Карта области', result.stdout)

    def test_ignore_excludes_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.repo(tmp)
            commit(repo, 'tests/FooTest.php', '<?php\n')
            write(repo, 'docs/tasks/CB-7/map.md', '# CB-7\n')
            result = run_gate(repo)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_no_base_reports_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.repo(tmp, WF.replace('- base: `dev`\n', ''))
            result = run_gate(repo)
            self.assertEqual(result.returncode, 5, result.stdout)
            self.assertIn('задай base', result.stdout)
            self.assertEqual(result.stderr, '')

    def test_garbage_sverено_fails_with_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.repo(tmp)
            commit(repo, 'src/Billing/Foo.php', '<?php\n')
            commit(repo, 'docs/architecture/billing.md', card('src/Billing/**', 'нет'))
            write(repo, 'docs/tasks/CB-7/map.md', '# CB-7\n')
            result = run_gate(repo)
            self.assertEqual(result.returncode, 5, result.stdout + result.stderr)
            self.assertIn('сверено', result.stdout)
            self.assertEqual(result.stderr, '')

    def test_map_without_paths_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.repo(tmp)
            sha = commit(repo, 'src/Billing/Foo.php', '<?php\n')
            commit(repo, 'docs/architecture/billing.md', '---\nmodule: billing\nсверено: %s\n---\n' % sha)
            write(repo, 'docs/tasks/CB-7/map.md', '# CB-7\n')
            result = run_gate(repo)
            self.assertEqual(result.returncode, 5, result.stdout)
            self.assertIn('без paths', result.stdout)

    def test_local_wip_not_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp, WF + '## Не коммитить\n- local_wip: `Makefile`\n', {'README.md': 'x\n', 'Makefile': 'a\n'})
            sh(repo, 'git', 'checkout', '-q', '-b', 'CB-7')
            sha = commit(repo, 'src/Billing/Foo.php', '<?php\n')
            commit(repo, 'docs/architecture/billing.md', card('src/Billing/**', sha))
            write(repo, 'docs/tasks/CB-7/map.md', '# CB-7\n')
            with open(os.path.join(repo, 'Makefile'), 'a') as handle:
                handle.write('local\n')
            result = run_gate(repo)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_uncommitted_map_counts_as_changed(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.repo(tmp)
            sha = commit(repo, 'src/Billing/Foo.php', '<?php\n')
            write(repo, 'docs/architecture/billing.md', card('src/Billing/**', sha))
            sh(repo, 'git', 'add', 'docs/architecture/billing.md')
            write(repo, 'docs/tasks/CB-7/map.md', '# CB-7\n')
            result = run_gate(repo)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_untracked_map_fails_with_git_add(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.repo(tmp)
            sha = commit(repo, 'src/Billing/Foo.php', '<?php\n')
            write(repo, 'docs/architecture/billing.md', card('src/Billing/**', sha))
            write(repo, 'docs/tasks/CB-7/map.md', '# CB-7\n')
            result = run_gate(repo)
            self.assertEqual(result.returncode, 5, result.stdout)
            self.assertIn('не добавлена в git', result.stdout)
            self.assertIn('git add docs/architecture/billing.md', result.stdout)
            self.assertIn('.git/info/exclude', result.stdout)
            self.assertNotIn('не сверена', result.stdout)
            sh(repo, 'git', 'add', 'docs/architecture/billing.md')
            self.assertEqual(run_gate(repo).returncode, 0)

    def exclude(self, repo, pattern):
        with open(os.path.join(repo, '.git', 'info', 'exclude'), 'a', encoding='utf-8') as handle:
            handle.write(pattern + '\n')

    def test_excluded_map_checked_by_content_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.repo(tmp)
            self.exclude(repo, 'docs/architecture/')
            sha = commit(repo, 'src/Billing/Foo.php', '<?php\n')
            write(repo, 'docs/architecture/billing.md', card('src/Billing/**', sha))
            write(repo, 'docs/tasks/CB-7/map.md', '# CB-7\n')
            status = subprocess.run(['git', 'status', '--porcelain', '--', 'docs/architecture'], cwd=repo,
                                    capture_output=True, text=True).stdout
            self.assertEqual(status, '', 'исключённая карта не должна быть видна git')
            result = run_gate(repo)
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn('1 карт сверено', result.stdout)
            commit(repo, 'src/Billing/Bar.php', '<?php\n')
            result = run_gate(repo)
            self.assertEqual(result.returncode, 0, 'правка модуля в самой ветке локальную карту не устаревает: ' + result.stdout)

    def head(self, repo):
        return subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=repo, capture_output=True, text=True).stdout.strip()

    def test_local_map_stale_when_base_changed_module(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp, WF, {'README.md': 'x\n', 'src/Billing/Foo.php': '<?php\n'})
            self.exclude(repo, 'docs/architecture/')
            d1 = self.head(repo)
            write(repo, 'docs/architecture/billing.md', card('src/Billing/**', d1))
            sh(repo, 'git', 'checkout', '-q', '-b', 'CB-7')
            commit(repo, 'src/Billing/Ticket.php', '<?php\n')
            write(repo, 'docs/tasks/CB-7/map.md', '# CB-7\n')
            self.assertEqual(run_gate(repo).returncode, 0)
            sh(repo, 'git', 'checkout', '-q', 'dev')
            d2 = commit(repo, 'src/Billing/Foo.php', '<?php // base change\n')
            sh(repo, 'git', 'checkout', '-q', 'CB-7')
            self.assertEqual(run_gate(repo).returncode, 0, 'до ребейза база ветки прежняя')
            sh(repo, 'git', 'rebase', '-q', 'dev')
            result = run_gate(repo)
            self.assertEqual(result.returncode, 5, result.stdout)
            self.assertIn('отстала от базы dev: после %s в %s изменены src/Billing/Foo.php' % (d1[:7], d2[:7]), result.stdout)
            self.assertIn('system-mapper area', result.stdout)
            write(repo, 'docs/architecture/billing.md', card('src/Billing/**', d2))
            self.assertEqual(run_gate(repo).returncode, 0)

    def test_local_map_newer_than_branch_base_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp, WF, {'README.md': 'x\n', 'src/Billing/Foo.php': '<?php\n'})
            self.exclude(repo, 'docs/architecture/')
            sh(repo, 'git', 'checkout', '-q', '-b', 'CB-7')
            commit(repo, 'src/Billing/Ticket.php', '<?php\n')
            write(repo, 'docs/tasks/CB-7/map.md', '# CB-7\n')
            sh(repo, 'git', 'checkout', '-q', 'dev')
            d2 = commit(repo, 'src/Billing/Foo.php', '<?php // other ticket merged\n')
            write(repo, 'docs/architecture/billing.md', card('src/Billing/**', d2))
            sh(repo, 'git', 'checkout', '-q', 'CB-7')
            result = run_gate(repo)
            self.assertEqual(result.returncode, 0, 'карта новее точки ветвления — свежая: ' + result.stdout)

    def sibling_branch_repo(self, tmp):
        """dev на origin, ветка CB-7 с двумя запушенными коммитами (они же в origin/CB-7-deploy2, отведённой от CB-7)
        и одним незапушенным; локальная карта исключена из git."""
        repo = make_repo(tmp, WF, {'README.md': 'x\n', 'src/Billing/Foo.php': '<?php\n'})
        self.exclude(repo, 'docs/architecture/')
        bare = os.path.join(tmp, 'origin.git')
        sh(tmp, 'git', 'init', '-q', '--bare', bare)
        sh(repo, 'git', 'remote', 'add', 'origin', bare)
        sh(repo, 'git', 'push', '-q', 'origin', 'dev')
        return repo

    def branch_with_sibling(self, repo):
        sh(repo, 'git', 'checkout', '-q', '-b', 'CB-7')
        commit(repo, 'src/Billing/Ticket.php', '<?php\n')
        commit(repo, 'src/Billing/Ticket.php', '<?php // v2\n')
        sh(repo, 'git', 'push', '-q', 'origin', 'CB-7', 'CB-7:CB-7-deploy2')
        commit(repo, 'src/Billing/Ticket.php', '<?php // v3\n')
        write(repo, 'docs/tasks/CB-7/map.md', '# CB-7\n')

    def test_local_map_ignores_ticket_commits_on_sibling_branch(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.sibling_branch_repo(tmp)
            write(repo, 'docs/architecture/billing.md', card('src/Billing/**', self.head(repo)))
            self.branch_with_sibling(repo)
            result = run_gate(repo)
            self.assertEqual(result.returncode, 0, 'коммиты ветки на соседней ветке — не база: ' + result.stdout)
            self.assertIn('1 карт сверено', result.stdout)

    def test_local_map_stale_by_base_with_sibling_branch_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.sibling_branch_repo(tmp)
            d1 = self.head(repo)
            write(repo, 'docs/architecture/billing.md', card('src/Billing/**', d1))
            d2 = commit(repo, 'src/Billing/Foo.php', '<?php // base change\n')
            sh(repo, 'git', 'push', '-q', 'origin', 'dev')
            self.branch_with_sibling(repo)
            result = run_gate(repo)
            self.assertEqual(result.returncode, 5, result.stdout)
            self.assertIn('отстала от базы origin/dev: после %s в %s изменены src/Billing/Foo.php —'
                          % (d1[:7], d2[:7]), result.stdout)
            self.assertNotIn('Ticket.php', result.stdout)

    def test_gitignored_map_without_sverено_fails_with_mapper(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.repo(tmp)
            commit(repo, '.gitignore', 'docs/architecture/\n')
            commit(repo, 'src/Billing/Foo.php', '<?php\n')
            write(repo, 'docs/architecture/billing.md', card('src/Billing/**', ''))
            write(repo, 'docs/tasks/CB-7/map.md', '# CB-7\n')
            result = run_gate(repo)
            self.assertEqual(result.returncode, 5, result.stdout)
            self.assertIn('не сверена', result.stdout)
            self.assertNotIn('не добавлена в git', result.stdout)

    def test_map_dir_symlinked_outside_worktree_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.repo(tmp)
            shared = os.path.join(tmp, 'main-repo-architecture')
            os.makedirs(shared)
            os.makedirs(os.path.join(repo, 'docs'))
            os.symlink(shared, os.path.join(repo, 'docs', 'architecture'))
            sha = commit(repo, 'src/Billing/Foo.php', '<?php\n')
            write(repo, 'docs/architecture/billing.md', card('src/Billing/**', sha))
            write(repo, 'docs/tasks/CB-7/map.md', '# CB-7\n')
            result = run_gate(repo)
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn('1 карт сверено', result.stdout)

    def test_epic_branch_files_not_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp, WF, {'README.md': 'x\n'})
            bare = os.path.join(tmp, 'origin.git')
            sh(tmp, 'git', 'init', '-q', '--bare', bare)
            sh(repo, 'git', 'remote', 'add', 'origin', bare)
            sh(repo, 'git', 'checkout', '-q', '-b', 'epic-x')
            commit(repo, 'src/Epic/Bar.php', '<?php\n')
            sh(repo, 'git', 'push', '-q', 'origin', 'dev', 'epic-x')
            sh(repo, 'git', 'checkout', '-q', '-b', 'CB-7')
            sha = commit(repo, 'src/Billing/Foo.php', '<?php\n')
            commit(repo, 'docs/architecture/billing.md', card('src/Billing/**', sha))
            write(repo, 'docs/tasks/CB-7/map.md', '# CB-7\n')
            result = run_gate(repo)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn('src/Epic/Bar.php', result.stdout)

    def test_squash_after_verification_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.repo(tmp)
            sha = commit(repo, 'src/Billing/Foo.php', '<?php\n')
            commit(repo, 'docs/architecture/billing.md', card('src/Billing/**', sha))
            write(repo, 'docs/tasks/CB-7/map.md', '# CB-7\n')
            self.assertEqual(run_gate(repo).returncode, 0)
            sh(repo, 'git', 'reset', '-q', '--soft', 'dev')
            sh(repo, 'git', 'commit', '-q', '-m', 'feat(CB-7): всё одним коммитом')
            result = run_gate(repo)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_module_changed_after_verification_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.repo(tmp)
            sha = commit(repo, 'src/Billing/Foo.php', '<?php\n')
            commit(repo, 'docs/architecture/billing.md', card('src/Billing/**', sha))
            commit(repo, 'src/Billing/Foo.php', '<?php // v2\n')
            write(repo, 'docs/tasks/CB-7/map.md', '# CB-7\n')
            result = run_gate(repo)
            self.assertEqual(result.returncode, 5, result.stdout)
            self.assertIn('не сверена', result.stdout)
            self.assertIn('src/Billing/Foo.php', result.stdout)

    def test_uncommitted_module_change_after_verification_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.repo(tmp)
            sha = commit(repo, 'src/Billing/Foo.php', '<?php\n')
            commit(repo, 'docs/architecture/billing.md', card('src/Billing/**', sha))
            write(repo, 'docs/tasks/CB-7/map.md', '# CB-7\n')
            write(repo, 'src/Billing/Foo.php', '<?php // dirty\n')
            self.assertEqual(run_gate(repo).returncode, 5)

    def test_missing_verification_commit_fails_with_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.repo(tmp)
            commit(repo, 'src/Billing/Foo.php', '<?php\n')
            commit(repo, 'docs/architecture/billing.md', card('src/Billing/**', 'deadbeefdeadbeefdeadbeefdeadbeefdeadbeef'))
            write(repo, 'docs/tasks/CB-7/map.md', '# CB-7\n')
            result = run_gate(repo)
            self.assertEqual(result.returncode, 5, result.stdout)
            self.assertIn('коммит сверки deadbee', result.stdout)
            self.assertIn('пересвери', result.stdout)

    def test_quoted_list_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.repo(tmp)
            sha = commit(repo, 'src/Billing/Foo.php', '<?php\n')
            commit(repo, 'docs/architecture/billing.md',
                   '---\nmodule: billing\npaths:\n  - "src/Billing/**"\n  - \'config/billing.yaml\'\nсверено: %s\n---\n' % sha)
            write(repo, 'docs/tasks/CB-7/map.md', '# CB-7\n')
            result = run_gate(repo)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_md_without_frontmatter_or_module_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.repo(tmp)
            sha = commit(repo, 'src/Billing/Foo.php', '<?php\n')
            commit(repo, 'docs/architecture/billing.md', card('src/Billing/**', sha))
            commit(repo, 'docs/architecture/README.md', '# Карты\n\nКак читать.\n')
            commit(repo, 'docs/architecture/notes.md', '---\ntitle: заметки\n---\nтекст\n')
            write(repo, 'docs/tasks/CB-7/map.md', '# CB-7\n')
            result = run_gate(repo)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('1 карт сверено', result.stdout)

    def test_bom_card_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.repo(tmp)
            sha = commit(repo, 'src/Billing/Foo.php', '<?php\n')
            commit(repo, 'docs/architecture/billing.md', '\ufeff' + card('src/Billing/**', sha))
            write(repo, 'docs/tasks/CB-7/map.md', '# CB-7\n')
            result = run_gate(repo)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_pre_push_check_runs_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.repo(tmp)
            sha = commit(repo, 'src/Billing/Foo.php', '<?php\n')
            payload = {'tool_name': 'Bash', 'cwd': repo, 'tool_input': {'command': 'git push origin CB-7'}}
            result = subprocess.run([CHECK], cwd=repo, capture_output=True, text=True)
            self.assertEqual(result.returncode, 5, result.stdout)
            self.assertIn('база знаний', result.stdout)
            self.assertIn('дерево не засчитано', result.stdout)
            self.assertEqual(decision(run_hook('guard-git-push.py', payload)), 'deny')
            commit(repo, 'docs/architecture/billing.md', card('src/Billing/**', sha))
            write(repo, 'docs/tasks/CB-7/map.md', '# CB-7\n')
            result = subprocess.run([CHECK], cwd=repo, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(decision(run_hook('guard-git-push.py', payload)), 'ask')


if __name__ == '__main__':
    unittest.main()
