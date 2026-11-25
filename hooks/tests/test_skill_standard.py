import os
import subprocess
import tempfile
import unittest

from tests.helpers import HOOKS

ROOT = os.path.dirname(HOOKS)
LINT = os.path.join(ROOT, 'tools', 'skill-lint.py')

VALID = """---
name: demo
description: Делает одно действие по команде «сделай demo». Не для ревью и не для тикетов.
---

# Demo — одна строка

## Зачем

Кейс провала.

## Когда / когда нет

## 0. Конфиг проекта

## 1. Протокол

## 2. Режимы

| Запрос | Режим | Справочник |
|---|---|---|
| «а» | a | `references/a.md` |

## 3. Цикл

## 4. Отчёт

```
Demo: OK
```

## Остановка

## Самопроверка

- [ ] пункт
"""


def make_skill(tmp, name, text, references=('a.md',)):
    path = os.path.join(tmp, 'skills', name)
    os.makedirs(os.path.join(path, 'references'), exist_ok=True)
    with open(os.path.join(path, 'SKILL.md'), 'w', encoding='utf-8') as handle:
        handle.write(text)
    for ref in references:
        with open(os.path.join(path, 'references', ref), 'w', encoding='utf-8') as handle:
            handle.write('# ref\n')
    return os.path.join(tmp, 'skills')


def lint(path):
    result = subprocess.run(['python3', LINT, path], capture_output=True, text=True, timeout=60)
    return result.returncode, result.stdout + result.stderr


class SkillLintTest(unittest.TestCase):
    def test_valid_skill_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out = lint(make_skill(tmp, 'demo', VALID))
            self.assertEqual(code, 0, out)

    def test_missing_section_named(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out = lint(make_skill(tmp, 'demo', VALID.replace('## Остановка\n', '')))
            self.assertEqual(code, 1)
            self.assertIn('demo', out)
            self.assertIn('## Остановка', out)

    def test_oversize_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = VALID + 'x' * (6145 - len(VALID.encode('utf-8')))
            code, out = lint(make_skill(tmp, 'demo', text))
            self.assertEqual(code, 1)
            self.assertIn('6144', out)

    def test_description_without_cyrillic_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = VALID.replace('description: Делает одно действие по команде «сделай demo». Не для ревью и не для тикетов.',
                                 'description: Use when the user asks for demo. Not for review.')
            code, out = lint(make_skill(tmp, 'demo', text))
            self.assertEqual(code, 1)
            self.assertIn('description', out)

    def test_description_without_not_for_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = VALID.replace(' Не для ревью и не для тикетов.', '')
            code, out = lint(make_skill(tmp, 'demo', text))
            self.assertEqual(code, 1)
            self.assertIn('не для', out)

    def test_overview_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out = lint(make_skill(tmp, 'demo', VALID.replace('## Зачем', '## Overview\n\n## Зачем')))
            self.assertEqual(code, 1)
            self.assertIn('Overview', out)

    def test_missing_reference_file_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out = lint(make_skill(tmp, 'demo', VALID, references=()))
            self.assertEqual(code, 1)
            self.assertIn('references/a.md', out)

    def test_mode_row_without_reference_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = VALID.replace("| «а» | a | `references/a.md` |", "| «а» | a | `references/a.md` |\n| «б» | b | в чате |")
            code, out = lint(make_skill(tmp, 'demo', text))
            self.assertEqual(code, 1)
            self.assertIn('b', out)
            self.assertIn('references/', out)

    def test_stage_table_without_reference_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = VALID.replace('## 2. Режимы', '## 2. Этапы').replace("| «а» | a | `references/a.md` |", "| «а» | a | команда |")
            code, out = lint(make_skill(tmp, 'demo', text))
            self.assertEqual(code, 0, out)

    def test_section_outside_template_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out = lint(make_skill(tmp, 'demo', VALID + '\n## Пока НЕ умеет\n\nx\n'))
            self.assertEqual(code, 1)
            self.assertIn('Пока НЕ умеет', out)

    def test_single_skill_path_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            skills = make_skill(tmp, 'demo', VALID)
            code, out = lint(os.path.join(skills, 'demo'))
            self.assertEqual(code, 0, out)


class RealSkillsTest(unittest.TestCase):
    def test_real_skills_pass(self):
        code, out = lint(os.path.join(ROOT, 'skills'))
        self.assertEqual(code, 0, out)
        self.assertIn('OK', out)


if __name__ == '__main__':
    unittest.main()
