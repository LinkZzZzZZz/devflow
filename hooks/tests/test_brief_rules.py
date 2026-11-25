import json
import os
import subprocess
import tempfile
import unittest

from tests.helpers import HOOKS, make_repo

ROOT = os.path.dirname(HOOKS)
SCRIPT = os.path.join(ROOT, 'skills', 'task-workflow', 'scripts', 'brief-rules.py')
CLAUDE_MD = """# proj — правила

## 0. Стоп-правила

1. **не угадывай колонку** без схемы;
2. **не трогай деньги** без Money.

## 1. Код

**Сервисы — `final readonly class`.** `[ревьюер]`

**Фильтры — `__('Yes')`.** `[слово]`

**strict_types в каждом файле.** `[хук]`

## 2. Процесс

**Оценка текстом.** `[слово]`
"""
WF = """## Миграции
- migrations_dirs: `database/migrations`
- migration_create: `php artisan make:migration <имя>`

## Ревью
- Деньги — только Money.
- Контроллер без бизнес-логики.

## Не коммитить
- local_wip: `Makefile`
"""


def run(repo, *args):
    result = subprocess.run(['python3', SCRIPT, repo, *args], capture_output=True, text=True, timeout=30)
    return result.returncode, result.stdout, result.stderr


def version():
    with open(os.path.join(ROOT, '.claude-plugin', 'plugin.json')) as handle:
        return json.load(handle)['version']


class BriefRulesTest(unittest.TestCase):
    def test_collects_project_rules_and_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp, WF, {'CLAUDE.md': CLAUDE_MD, 'README.md': 'x\n'})
            code, out, err = run(repo)
            self.assertEqual(code, 0, err)
            for present in ('не угадывай колонку', 'не трогай деньги', 'final readonly class', "__('Yes')",
                            'Оценка текстом', 'Деньги — только Money', 'Контроллер без бизнес-логики',
                            'php artisan make:migration', 'итоговой строки'):
                self.assertIn(present, out)
            self.assertNotIn('strict_types в каждом файле', out)
            self.assertNotIn('local_wip', out)
            self.assertTrue(out.rstrip().endswith('<!-- brief-rules v%s -->' % version()), out[-120:])

    def test_without_project_files_still_prints_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp)
            code, out, err = run(repo)
            self.assertEqual(code, 0, err)
            self.assertIn('итоговой строки', out)
            self.assertIn('нет', out)
            self.assertTrue(out.rstrip().endswith('<!-- brief-rules v%s -->' % version()))

    def test_worktree_reads_main_repo(self):
        from tests.helpers import add_worktree
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp, WF, {'CLAUDE.md': CLAUDE_MD})
            wt = add_worktree(repo, tmp)
            os.remove(os.path.join(wt, 'CLAUDE.md'))
            code, out, err = run(wt)
            self.assertEqual(code, 0, err)
            self.assertIn('final readonly class', out)
            self.assertIn('php artisan make:migration', out)


if __name__ == '__main__':
    unittest.main()
