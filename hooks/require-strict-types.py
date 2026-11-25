#!/usr/bin/env python3
"""PreToolUse на Write|Edit: каждый PHP-файл начинается с declare(strict_types=1). Включается ключом
`strict_types` в поле `hooks` секции «Код» .claude/workflow.md."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_workflow import enabled, load, skipped

DECLARE = 'declare(strict_types=1)'


def verdict(payload):
    tool_input = payload.get('tool_input') or {}
    path = tool_input.get('file_path') or ''
    if not path.endswith('.php') or path.endswith('.blade.php'):
        return None
    cfg = load(os.path.dirname(path))
    if not enabled(cfg, 'strict_types') or skipped(cfg, path):
        return None
    if payload.get('tool_name') == 'Edit':
        if DECLARE in (tool_input.get('old_string') or '') and DECLARE not in (tool_input.get('new_string') or ''):
            return 'Правка удаляет `declare(strict_types=1);` из PHP-файла проекта. Верни строку в new_string: объявление обязано остаться.'
        return None
    if DECLARE not in (tool_input.get('content') or ''):
        return ('Каждый PHP-файл проекта обязан начинаться с `declare(strict_types=1);`. Добавь её первой строкой после `<?php` '
                'и повтори запись: правило пользователя, без исключений.')
    return None


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return
    reason = verdict(payload)
    if reason:
        print(json.dumps({'hookSpecificOutput': {
            'hookEventName': 'PreToolUse', 'permissionDecision': 'deny', 'permissionDecisionReason': reason,
        }}, ensure_ascii=False))


if __name__ == '__main__':
    main()
