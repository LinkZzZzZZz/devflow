#!/usr/bin/env python3
"""PreToolUse на меняющие данные инструменты MCP YouTrack: задачи, черновики, комментарии, теги, связи,
статьи, вложения, учёт работы — по подтверждению с тем, что уйдёт. Чтение хук не трогает (матчер в hooks.json).
Имена параметров инструментов сервер не документирует, поэтому вход показывается целиком, длинные значения — обрезаются."""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_hook import guarded, respond

TOOL = re.compile(r'^mcp__(?:plugin_devflow_)?youtrack__(?P<name>[a-z_]+)$')
WRITES = {
    'create_issue': 'Новая задача',
    'create_draft_issue': 'Черновик задачи (виден только тебе)',
    'update_draft_issue': 'Правка черновика задачи',
    'publish_draft_issue': 'Публикация черновика задачи',
    'update_issue': 'Правка задачи (поля, описание, статус)',
    'change_issue_assignee': 'Смена исполнителя',
    'add_issue_comment': 'Комментарий в задачу',
    'manage_issue_tags': 'Теги задачи',
    'link_issues': 'Связь задач',
    'create_article': 'Новая статья базы знаний',
    'update_article': 'Правка статьи базы знаний',
    'add_attachment': 'Вложение',
    'log_work': 'Запись учёта работы',
    'update_work_item': 'Правка записи учёта работы',
}
VALUE = 300
TOTAL = 1500


def shown(value):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    text = text.strip()
    return text if len(text) <= VALUE else text[:VALUE] + '…'


def details(args):
    lines = ['- %s: %s' % (key, shown(value)) for key, value in sorted(args.items())
             if key not in ('content',) and value not in (None, '', [], {})]
    if args.get('content'):
        lines.append('- content: <%d символов base64>' % len(str(args['content'])))
    text = '\n'.join(lines) or '- (без параметров)'
    return text if len(text) <= TOTAL else text[:TOTAL] + '\n…'


def run():
    payload = json.load(sys.stdin)
    match = TOOL.match(payload.get('tool_name') or '')
    if not match:
        respond('ask', 'confirm-youtrack-write: инструмент не распознан, подтверди осознанно.')
        return
    name = match.group('name')
    what = WRITES.get(name, 'Действие')
    args = payload.get('tool_input') or {}
    respond('ask', '%s в YouTrack (%s) от твоего имени, увидят другие участники проекта.\n%s\nПодтверди.'
            % (what, name, details(args)))


if __name__ == '__main__':
    guarded('confirm-youtrack-write', run)
