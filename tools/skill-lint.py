#!/usr/bin/env python3
"""Линт стандарта скиллов (docs/skill-standard.md). Использование: skill-lint.py <каталог skills | каталог скилла>…

Проверяет каждый SKILL.md: фронтматтер с `name` и русским `description`, содержащим «не для»; обязательные разделы
шаблона; размер ≤ 6144 байт (остальное — в references/); каждый упомянутый `references/<имя>.md` существует;
нет `## Overview`. По строке на нарушение: `skill-lint: <skill>: <что не так — что сделать>`; код 1 при любой."""
import os
import re
import sys

MAX_BYTES = 6144
REQUIRED = (
    ('## Зачем', 'кейс провала, который скилл ловит'),
    ('## Когда', '«Когда / когда нет»: триггеры и границы'),
    ('## 0. Конфиг', 'поля workflow.md, которые читает скилл (или «не читает»)'),
    ('## 1. Протокол', 'сквозные правила с метками [хук]/[слово]'),
    ('## 2. ', '«2. Этапы» или «2. Режимы»: таблица → references/<режим>.md'),
    ('## 3. Цикл', 'обязательные агенты или «агентов нет»'),
    ('## 4. Отчёт', 'формат итоговой строки с примером'),
    ('## Остановка', 'признак шума или формальности'),
    ('## Самопроверка', 'чек-лист перед выдачей'),
)
CYRILLIC = re.compile('[а-яА-ЯёЁ]')
REFERENCE = re.compile(r'`references/([^`\s]+\.md)`')
TEMPLATE_HEADINGS = ('## Зачем', '## Когда', '## 0. Конфиг', '## 1. Протокол', '## 2. Этапы', '## 2. Режимы', '## 3. Цикл',
                     '## 4. Отчёт', '## Остановка', '## Самопроверка')


def frontmatter(text):
    lines = text.splitlines()
    if not lines or lines[0].strip() != '---':
        return None
    fields = {}
    for line in lines[1:]:
        if line.strip() == '---':
            return fields
        key, sep, value = line.partition(':')
        if sep:
            fields[key.strip()] = value.strip()
    return None


def lint_skill(path):
    name = os.path.basename(path.rstrip('/'))
    skill_md = os.path.join(path, 'SKILL.md')
    problems = []
    if not os.path.isfile(skill_md):
        return ['%s: нет SKILL.md — создай по шаблону docs/skill-standard.md' % name]
    with open(skill_md, 'rb') as handle:
        raw = handle.read()
    text = raw.decode('utf-8', errors='replace')
    if len(raw) > MAX_BYTES:
        problems.append('%s: SKILL.md %d байт, лимит %d — вынеси этапы и подробности в references/' % (name, len(raw), MAX_BYTES))
    fields = frontmatter(text)
    if fields is None:
        problems.append('%s: нет фронтматтера --- name/description --- — добавь его первыми строками' % name)
    else:
        if not fields.get('name'):
            problems.append('%s: во фронтматтере нет name — добавь `name: %s`' % (name, name))
        description = fields.get('description', '')
        if not CYRILLIC.search(description):
            problems.append('%s: description не по-русски — перепиши: триггеры в кавычках и «не для …»' % name)
        if 'не для' not in description.lower():
            problems.append('%s: в description нет «не для …» — назови, для чего скилл не применяется' % name)
    for heading, meaning in REQUIRED:
        if not re.search('^' + re.escape(heading), text, re.MULTILINE):
            problems.append('%s: нет раздела `%s` — добавь (%s)' % (name, heading.rstrip(), meaning))
    if re.search(r'^## Overview', text, re.MULTILINE):
        problems.append('%s: раздел `## Overview` — замени на «Зачем» и «Когда / когда нет»' % name)
    for heading in re.findall(r'^## .*$', text, re.MULTILINE):
        if not heading.startswith(TEMPLATE_HEADINGS):
            problems.append('%s: раздел `%s` вне шаблона — перенеси содержимое в раздел шаблона или в references/' % (name, heading.strip()))
    modes = re.search(r'^## 2\. Режимы[^\n]*\n(.*?)(?=^## |\Z)', text, re.MULTILINE | re.DOTALL)
    if modes:
        for row in re.findall(r'^\|.*\|$', modes.group(1), re.MULTILINE):
            cells = [c.strip() for c in row.strip('|').split('|')]
            if len(cells) < 2 or set(cells[0]) <= set('-: ') or cells == [c for c in cells if c.lower() in ('запрос', 'сообщение', 'режим', 'операция', 'справочник', 'этап')]:
                continue
            if not REFERENCE.search(row):
                problems.append('%s: режим `%s` без файла `references/<режим>.md` в строке таблицы — добавь ссылку' % (name, cells[1]))
    for ref in sorted(set(REFERENCE.findall(text))):
        if not os.path.isfile(os.path.join(path, 'references', ref)):
            problems.append('%s: ссылка на отсутствующий `references/%s` — создай файл или поправь ссылку' % (name, ref))
    return problems


def skill_dirs(arg):
    if os.path.isfile(os.path.join(arg, 'SKILL.md')):
        return [arg]
    if not os.path.isdir(arg):
        return []
    return sorted(os.path.join(arg, d) for d in os.listdir(arg) if os.path.isdir(os.path.join(arg, d)))


def main(args):
    targets = []
    for arg in args or ['skills']:
        targets += skill_dirs(arg)
    if not targets:
        print('skill-lint: скиллы не найдены в %s' % ', '.join(args or ['skills']), file=sys.stderr)
        return 1
    problems = []
    for target in targets:
        problems += lint_skill(target)
    for line in problems:
        print('skill-lint: ' + line)
    if not problems:
        print('skill-lint: OK (%d скиллов)' % len(targets))
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
