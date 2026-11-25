#!/usr/bin/env python3
"""PreToolUse на Write и Agent/Task: план и реализация architectural-тикета — только после проверок дизайна.

Тикет с `<KEY>/design.md`:
- Write `<KEY>/plan.md` без `reports/design-critique.md` (отчёт spec-critic в режиме design) — deny;
- вызов implementer, в брифе которого есть путь каталога тикета, — deny, если нет `reports/design-critique.md`,
  нет `reports/fact-check.md` (отчёт fact-checker) или в fact-check.md есть строка НЕ ПОДТВЕРЖДЕНО / ТОЛКОВАНИЕ
  с номером решения, а в этом решении `design.md` нет нужной строки: «кто решает» = пользователь —
  `Решение пользователя (дата): «цитата»`, цитата которой найдена в сообщениях пользователя (транскрипты
  всех сессий репозитория, включая его worktree, за 60 дней); источник / образец / умолчание —
  `Исправлено по проверке (дата): …`. Таблица вердиктов без колонок «решение» и «кто решает» — старый формат, deny.
Каталог тикета без design.md (small/bounded) и пути, которых нет на диске, гейт не трогают.
Сбой самого хука — ask (lib_hook.guarded): политика, которая падает, равна отсутствию политики."""
import glob
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_hook import guarded, respond

KEY = r'[A-Z][A-Z0-9]*-\d+'
TICKET_DIR = re.compile(r'([^\s`\'"()<>\[\]]*?(?<![A-Za-z0-9_-])' + KEY + r')(?=[/\s`\'"()\[\],.:;]|$)')
AGENT_TOOLS = ('Agent', 'Task')
CRITIQUE = os.path.join('reports', 'design-critique.md')
FACT_CHECK = os.path.join('reports', 'fact-check.md')
REFUTED = re.compile(r'НЕ\s+ПОДТВЕРЖДЕНО|ТОЛКОВАНИЕ')
USER_DECISION = re.compile(r'Решение пользователя\s*\(\d{4}-\d{2}-\d{2}\)\s*:\s*«([^»]+)»')
FIXED = re.compile(r'Исправлено по проверке\s*\(\d{4}-\d{2}-\d{2}\)\s*:\s*\S')
DECIDERS = ('источник', 'образец', 'умолчание', 'пользователь')
DECISION_ITEM = re.compile(r'^(?:[-*]\s+)?(?:\*\*)?[РрPp]?(\d+)\.\s')
MIN_QUOTE = 8
TRANSCRIPT_AGE = 60 * 86400


def read(path):
    try:
        with open(path, encoding='utf-8', errors='replace') as handle:
            return handle.read()
    except OSError:
        return None


def architectural(ticket_dir):
    return os.path.isfile(os.path.join(ticket_dir, 'design.md'))


def has(ticket_dir, rel):
    return os.path.isfile(os.path.join(ticket_dir, rel))


def critique_reason(ticket_dir, action):
    return ('%s: design.md есть, а %s нет — %s до критики дизайна запрещено. '
            'Запусти devflow:spec-critic, первая строка брифа «режим: design» (бриф: spec.md, design.md, '
            '<KEY>/map.md, пути карт модулей, отчёт reports/design-critique.md); находки — в design.md, затем план '
            '(task-workflow/references/start.md п. 5).' % (os.path.basename(ticket_dir), CRITIQUE, action))


def refuted_rows(text):
    """([(номера решений, утверждение, кто решает)], старый формат) — строки таблиц fact-check.md с вердиктом
    НЕ ПОДТВЕРЖДЕНО или ТОЛКОВАНИЕ; старый формат — таблица вердиктов без колонок «решение» и «кто решает»."""
    rows, header, legacy = [], None, False
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith('|'):
            header = None
            continue
        cells = [cell.strip() for cell in line.strip('|').split('|')]
        if all(re.fullmatch(r':?-{2,}:?', cell or '--') for cell in cells):
            continue
        lowered = [cell.lower() for cell in cells]
        if header is None and any('вердикт' in cell for cell in lowered):
            decision = next((i for i, c in enumerate(lowered) if 'решени' in c), None)
            decider = next((i for i, c in enumerate(lowered) if 'кто' in c and 'реша' in c), None)
            if decision is None or decider is None:
                legacy = True
                continue
            claim = next((i for i, c in enumerate(lowered) if 'утвержд' in c), 0)
            header = (decision, next(i for i, c in enumerate(lowered) if 'вердикт' in c), claim, decider)
            continue
        if header is None or max(header) >= len(cells):
            continue
        if REFUTED.search(cells[header[1]]):
            numbers = sorted(set(int(n) for n in re.findall(r'\d+', cells[header[0]])))
            if numbers:
                who = next((d for d in DECIDERS if d[:6] in lowered[header[3]]), None)
                rows.append((numbers, cells[header[2]], who))
    return rows, legacy


def decisions(design):
    """{номер: текст решения} из раздела «Принятые решения» design.md: пункты «N.» или «РN.» с начала строки."""
    section = re.split(r'^##\s+Принятые решения\s*$', design, maxsplit=1, flags=re.MULTILINE)
    if len(section) < 2:
        return {}
    body = re.split(r'^##\s', section[1], maxsplit=1, flags=re.MULTILINE)[0]
    out, current = {}, None
    for line in body.splitlines():
        match = DECISION_ITEM.match(line)
        if match:
            current = int(match.group(1))
            out[current] = line + '\n'
        elif current is not None:
            out[current] += line + '\n'
    return out


def norm(text):
    return re.sub(r'\s+', ' ', (text or '').lower().replace('ё', 'е')).strip()


def user_texts(path):
    out = []
    try:
        handle = open(path, encoding='utf-8', errors='replace')
    except OSError:
        return out
    with handle:
        for line in handle:
            if '"user"' not in line:
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if not isinstance(record, dict) or record.get('type') != 'user' or record.get('isMeta'):
                continue
            message = record.get('message')
            content = message.get('content') if isinstance(message, dict) else None
            if isinstance(content, str):
                out.append(norm(content))
            elif isinstance(content, list):
                out.extend(norm(block.get('text')) for block in content
                           if isinstance(block, dict) and block.get('type') == 'text')
    return out


def repo_root(cwd):
    try:
        result = subprocess.run(['git', '-C', cwd, 'rev-parse', '--path-format=absolute', '--git-common-dir'],
                                capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    common = result.stdout.strip() if 0 == result.returncode else ''
    return os.path.dirname(common.rstrip('/')) if common else None


def transcripts(transcript_path, cwd):
    """Транскрипт сессии, затем транскрипты всех сессий репозитория и его worktree (каталоги проектов Claude Code
    с именем пути репозитория, где не буквы и не цифры заменены на «-»), свежие первыми."""
    if not transcript_path:
        return []
    folders = {os.path.dirname(transcript_path)}
    root = repo_root(cwd)
    if root:
        prefixes = {re.sub(r'[^A-Za-z0-9]', '-', path) for path in (root, os.path.realpath(root))}
        projects = os.path.dirname(os.path.dirname(transcript_path))
        folders.update(d for d in glob.glob(os.path.join(projects, '*')) if os.path.isdir(d) and any(
            os.path.basename(d) == prefix or os.path.basename(d).startswith(prefix + '-') for prefix in prefixes))
    fresh = time.time() - TRANSCRIPT_AGE
    others = [p for folder in folders for p in glob.glob(os.path.join(folder, '*.jsonl')) if p != transcript_path]
    others = [p for p in others if os.path.getmtime(p) >= fresh]
    return [transcript_path] + sorted(others, key=os.path.getmtime, reverse=True)


def quoted_by_user(quotes, transcript_path, cwd):
    wanted = [norm(q) for q in quotes if norm(q)]
    if not wanted:
        return False
    for path in transcripts(transcript_path, cwd):
        for message in user_texts(path):
            for quote in wanted:
                if quote == message or (len(quote) >= MIN_QUOTE and quote in message):
                    return True
    return False


def fact_check_reason(ticket_dir, transcript_path, cwd):
    name = os.path.basename(ticket_dir)
    report = read(os.path.join(ticket_dir, FACT_CHECK))
    if report is None:
        return ('%s: нет %s — implementer до проверки фактов не зовётся. Запусти devflow:fact-checker '
                '(бриф: spec.md, design.md, отчёт reports/fact-check.md) и закрой опровержения по колонке «кто решает» '
                '(task-workflow/references/start.md п. 5).' % (name, FACT_CHECK))
    rows, legacy = refuted_rows(report)
    if legacy:
        return ('%s: в %s таблица вердиктов без колонок «решение» и «кто решает» (старый формат) — гейт не видит, '
                'на какие решения опираются опровержения и кто их закрывает. Перезапусти devflow:fact-checker '
                '(бриф: spec.md, design.md, отчёт reports/fact-check.md).' % (name, FACT_CHECK))
    items = decisions(read(os.path.join(ticket_dir, 'design.md')) or '')
    for numbers, claim, who in rows:
        for number in numbers:
            text = items.get(number, '')
            head = '%s: решение %d design.md опирается на опровергнутое или толкование (%s: «%s»)' % (
                name, number, FACT_CHECK, claim[:120])
            if who is None:
                return head + ', а в колонке «кто решает» нет источник / образец / умолчание / пользователь — перезапусти devflow:fact-checker.'
            if 'пользователь' != who:
                if FIXED.search(text):
                    continue
                return (head + ', кто решает — %s: исправь решение по ответу из пруфа сам (вопрос пользователю не нужен), '
                        'поправь сценарии и «Контракт API» и допиши в решение %d строку «Исправлено по проверке '
                        '(ГГГГ-ММ-ДД): <что стало>».' % (who, number))
            quotes = USER_DECISION.findall(text)
            if quotes and quoted_by_user(quotes, transcript_path, cwd):
                continue
            problem = ('строки «Решение пользователя (ГГГГ-ММ-ДД): «цитата»» нет' if not quotes
                       else 'цитаты из строки «Решение пользователя» нет в сообщениях пользователя')
            return (head + ', кто решает — пользователь, а %s. Вынеси пользователю: опровержение, цитата первоисточника, '
                    'варианты с рекомендуемым первым; его ответ — строкой «Решение пользователя (дата): «его слова»» в '
                    'решении %d. «Не меняю, фиксирую» — нарушение rules/general.md §1.' % (problem, number))
    return None


def ticket_dirs(text, cwd):
    seen = []
    for match in TICKET_DIR.finditer(text or ''):
        path = match.group(1)
        path = os.path.normpath(path if os.path.isabs(path) else os.path.join(cwd, path))
        if path not in seen:
            seen.append(path)
    return seen


def check():
    payload = json.load(sys.stdin)
    tool = payload.get('tool_name') or ''
    inp = payload.get('tool_input') or {}
    cwd = payload.get('cwd') or os.getcwd()
    if tool == 'Write':
        path = inp.get('file_path') or ''
        if os.path.basename(path) != 'plan.md':
            return
        ticket_dir = os.path.dirname(path if os.path.isabs(path) else os.path.join(cwd, path))
        if re.fullmatch(KEY, os.path.basename(ticket_dir)) and architectural(ticket_dir) and not has(ticket_dir, CRITIQUE):
            respond('deny', critique_reason(ticket_dir, 'писать plan.md'))
        return
    if tool in AGENT_TOOLS and (inp.get('subagent_type') or '').split(':')[-1] == 'implementer':
        for ticket_dir in ticket_dirs(inp.get('prompt') or '', cwd):
            if not architectural(ticket_dir):
                continue
            if not has(ticket_dir, CRITIQUE):
                respond('deny', critique_reason(ticket_dir, 'звать implementer'))
                return
            reason = fact_check_reason(ticket_dir, payload.get('transcript_path') or '', cwd)
            if reason:
                respond('deny', reason)
                return


if __name__ == '__main__':
    guarded('design-critique-gate', check)
