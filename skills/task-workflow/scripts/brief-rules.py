#!/usr/bin/env python3
"""Собрать блок «Обязательные правила» для брифа implementer из файлов проекта, а не по памяти.

Использование: brief-rules.py <путь в репозитории> [--files <путь>...]

Печатает только то, чего сабагент не получит сам:
  - §0 (стоп-правила) проектного CLAUDE.md целиком и остальные его правила с метками [ревьюер]/[слово]
    ([хук]/[линтер] ловит механика); в worktree CLAUDE.md читается из основного репозитория;
  - секции «Ревью» (карта ссылок на файлы правил и заметки ревью, не сами правила) и «Миграции» из .claude/workflow.md;
  - правило ожидания долгих команд;
  - последней строкой маркер версии — implementer проверяет его, а не заголовок.
Общие правила плагина (rules/general.md) сюда не входят: их сабагент получает хуком SubagentStart.
--files пока не фильтрует: какие файлы правил из карты «Ревью» относятся к задаче, отбирает оркестратор."""
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(ROOT, 'hooks'))
from lib_workflow import load  # noqa: E402

KEEP = re.compile(r'\[(ревьюер|слово)\]')
STOP_SECTION = re.compile(r'^## 0\b')
WAIT_RULE = ('- Долгие команды (тесты, проверки) дожидайся до итоговой строки раннера; запустил в фоне — читай вывод '
             'в цикле до неё. Фоновый процесс умирает вместе с ходом.')


def git(cwd, *args):
    try:
        result = subprocess.run(['git', '-C', cwd, *args], capture_output=True, text=True, timeout=5)
    except Exception:
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def main_repo(cwd):
    common = git(cwd, 'rev-parse', '--path-format=absolute', '--git-common-dir')
    return os.path.dirname(os.path.realpath(common)) if common else os.path.abspath(cwd)


def md_sections(text):
    sections, head, body = [], '', []
    for line in text.splitlines():
        if line.startswith('## '):
            sections.append((head, body))
            head, body = line, []
        else:
            body.append(line)
    sections.append((head, body))
    return sections


def claude_rules(path):
    with open(path, encoding='utf-8') as handle:
        text = handle.read()
    out = []
    for head, body in md_sections(text):
        if not head:
            continue
        if STOP_SECTION.match(head):
            out.append(head)
            out += [line for line in body if line.strip()]
            continue
        kept = [line for line in body if KEEP.search(line)]
        if kept:
            out.append(head)
            out += kept
    return out


def workflow_section(path, title):
    with open(path, encoding='utf-8') as handle:
        text = handle.read()
    for head, body in md_sections(text):
        if head.strip() == '## ' + title:
            return [line for line in body if line.strip()]
    return []


def version():
    try:
        with open(os.path.join(ROOT, '.claude-plugin', 'plugin.json'), encoding='utf-8') as handle:
            return json.load(handle).get('version', '?')
    except (OSError, ValueError):
        return '?'


def main(argv):
    if not argv or argv[0].startswith('-'):
        print(__doc__, file=sys.stderr)
        return 2
    cwd = argv[0]
    repo = main_repo(cwd)
    lines = ['## Обязательные правила', '']

    claude_md = os.path.join(repo, 'CLAUDE.md')
    if os.path.isfile(claude_md):
        lines.append('### Проектный CLAUDE.md (%s)' % claude_md)
        lines += claude_rules(claude_md) or ['нет правил с метками [ревьюер]/[слово] и нет §0']
    else:
        lines.append('### Проектный CLAUDE.md: нет')
    lines.append('')

    cfg = load(cwd)
    for title in ('Ревью', 'Миграции'):
        body = workflow_section(cfg['path'], title) if cfg else []
        lines.append('### %s (.claude/workflow.md)' % ('Ревью: карта правил и заметки' if title == 'Ревью' else title))
        lines += body or ['нет']
        lines.append('')

    lines += ['### Процесс', WAIT_RULE, '', '<!-- brief-rules v%s -->' % version()]
    print('\n'.join(lines))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
