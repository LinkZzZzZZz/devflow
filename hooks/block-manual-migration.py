#!/usr/bin/env python3
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_workflow import get, get_list, load

def real(path):
    head, tail = os.path.abspath(path), []
    while not os.path.exists(head):
        head, part = os.path.split(head)
        tail.insert(0, part)
    return os.path.join(os.path.realpath(head), *tail)


def verdict(path):
    if not path or os.path.exists(path):
        return None
    cfg = load(os.path.dirname(path))
    dirs = get_list(cfg, 'migrations_dirs')
    if dirs:
        rel = os.path.relpath(real(path), os.path.realpath(cfg['root']))
        if any(rel.startswith(d.strip('/') + '/') for d in dirs):
            create = get(cfg, 'migration_create') or 'CLI проекта'
            return ('Новые файлы миграций создаются только командой `%s` — ручная временная метка ломает '
                    'порядок применения. Создай файл командой, потом правь его тело.' % create)
        return None
    return None


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return
    reason = verdict((payload.get('tool_input') or {}).get('file_path'))
    if reason:
        print(json.dumps({'hookSpecificOutput': {
            'hookEventName': 'PreToolUse', 'permissionDecision': 'deny', 'permissionDecisionReason': reason,
        }}, ensure_ascii=False))


if __name__ == '__main__':
    main()
