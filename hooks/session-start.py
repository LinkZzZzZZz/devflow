#!/usr/bin/env python3
"""SessionStart и SubagentStart: подать общие правила плагина (rules/general.md) и корень плагина в контекст.
На SessionStart дополнительно экспортирует DEVFLOW_ROOT в CLAUDE_ENV_FILE — для Bash-команд сессии.
Сабагент получает только секции с маркером `<!-- subagent -->` в заголовке: у него нет пользователя, тикета
и трекера, а каждый нерелевантный абзац стоит токенов на каждом его ходе."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_env import plugin_root
from lib_workflow import get_list, load

LIMIT = 9500
SUBAGENT_MARK = '<!-- subagent -->'
SUBAGENT_NOTE = ('Ты сабагент: там, где правило велит остановиться и спросить, остановись и верни вопрос '
                 'оркестратору отдельным пунктом отчёта.\n\n')


def sections(text):
    """Разбить тело правил на (заголовок, текст) по `## `; преамбула до первого заголовка — с пустым заголовком."""
    parts = []
    head, body = '', []
    for line in text.splitlines(keepends=True):
        if line.startswith('## '):
            parts.append((head, ''.join(body)))
            head, body = line, []
        else:
            body.append(line)
    parts.append((head, ''.join(body)))
    return parts


def for_event(rules, event):
    subagent = event == 'SubagentStart'
    out = []
    for head, body in sections(rules):
        if subagent and head and SUBAGENT_MARK not in head:
            continue
        out.append(head.replace(' ' + SUBAGENT_MARK, '').replace(SUBAGENT_MARK, '') + body)
    text = ''.join(out)
    return SUBAGENT_NOTE + text if subagent else text


def version(root):
    try:
        with open(os.path.join(root, '.claude-plugin', 'plugin.json'), encoding='utf-8') as handle:
            return json.load(handle).get('version', '?')
    except (OSError, ValueError):
        return '?'


def body(root):
    try:
        with open(os.path.join(root, 'rules', 'general.md'), encoding='utf-8') as handle:
            return handle.read()
    except OSError:
        return ''


NOTE = '⚠ rules/general.md длиннее %d символов — текст обрезан по границе секции, сократи файл.\n\n' % LIMIT


def trim(text):
    if len(text) <= LIMIT:
        return text
    sys.stderr.write('session-start: rules/general.md длиннее %d символов, текст обрезан по границе секции\n' % LIMIT)
    first, rest = text.split('\n', 1)
    budget = LIMIT - len(first) - 1 - len(NOTE)
    cut = rest.rfind('\n## ', 0, budget)
    cut = cut if cut > 0 else budget
    return first + '\n' + NOTE + rest[:cut].rstrip() + '\n'


def stack_hooks(cwd):
    keys = get_list(load(cwd), 'hooks') if cwd else []
    return ', '.join(keys) if keys else 'нет'


def export_root(root):
    env_file = os.environ.get('CLAUDE_ENV_FILE')
    if not env_file:
        return
    try:
        with open(env_file, 'a', encoding='utf-8') as handle:
            handle.write('export DEVFLOW_ROOT=%s\n' % json.dumps(root, ensure_ascii=False))
    except OSError as error:
        sys.stderr.write('session-start: не записать CLAUDE_ENV_FILE: %s\n' % error)


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}
    event = payload.get('hook_event_name') or 'SessionStart'
    root = plugin_root()
    if event == 'SessionStart':
        export_root(root)
    text = body(root)
    if not text:
        sys.stderr.write('session-start: нет rules/general.md в %s\n' % root)
        return
    head = ('# Общие правила devflow (плагин, версия %s)\n\n'
            'Корень плагина devflow: %s — в Bash доступен как $DEVFLOW_ROOT '
            '(скрипты: $DEVFLOW_ROOT/hooks/…, $DEVFLOW_ROOT/skills/…). '
            'Стековые хуки проекта: %s.\n\n' % (version(root), root, stack_hooks(payload.get('cwd') or os.getcwd())))
    rules = text.split('\n', 1)[1] if text.startswith('# ') else text
    rules = for_event(rules.lstrip(), event)
    print(json.dumps({'hookSpecificOutput': {'hookEventName': event,
                                             'additionalContext': trim(head + rules)}}, ensure_ascii=False))


if __name__ == '__main__':
    main()
