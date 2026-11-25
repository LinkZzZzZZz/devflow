#!/usr/bin/env python3
"""PostToolUse на Bash: `make lint rector` гейт пуша больше не засчитывает — напомнить про pre-push-check.
Заодно снимает lock прогона тестов (claude-tests.lock), который поставил guard-bash-rules на PreToolUse."""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_env import plugin_root
from lib_workflow import get, load
from lib_git_cmd import checked_trees_file, resolve_dir, segments

REQUIRED_TARGETS = {'lint', 'rector'}


def make_runs(command, cwd):
    current = cwd
    found = []
    for tokens in segments(command):
        if tokens[0] == 'cd' and len(tokens) >= 2:
            current = resolve_dir(current, tokens[1])
            continue
        if os.path.basename(tokens[0]) != 'make':
            continue
        workdir = current
        targets = set()
        rest = tokens[1:]
        while rest:
            token = rest.pop(0)
            if token in ('-C', '--directory') and rest:
                workdir = resolve_dir(workdir, rest.pop(0))
            elif token.startswith('--directory='):
                workdir = resolve_dir(workdir, token.split('=', 1)[1])
            elif token in ('-f', '--file', '-j', '--jobs') and rest:
                rest.pop(0)
            elif token.startswith('-') or re.match(r'^[A-Za-z_][A-Za-z0-9_]*=', token):
                continue
            else:
                targets.add(token)
        if REQUIRED_TARGETS <= targets:
            found.append(workdir)
    return found


def release_test_lock(cwd, tool_use_id):
    trees = checked_trees_file(cwd)
    if trees is None or not tool_use_id:
        return
    path = os.path.join(os.path.dirname(trees), 'claude-tests.lock')
    try:
        with open(path) as handle:
            owner = json.load(handle).get('tool_use_id')
    except (OSError, ValueError):
        return
    if owner == tool_use_id:
        try:
            os.remove(path)
        except OSError:
            pass


def main():
    payload = json.load(sys.stdin)
    if payload.get('tool_name') != 'Bash':
        return
    command = payload.get('tool_input', {}).get('command', '')
    cwd = payload.get('cwd') or os.getcwd()
    release_test_lock(cwd, payload.get('tool_use_id'))
    notes = []
    for repo in make_runs(command, cwd):
        gate = get(load(repo), 'pre_push')
        if gate:
            notes.append('make lint rector гейт пуша не засчитывает — перед пушем запусти '
                         '%s/hooks/pre-push-check.py (выполнит `%s`).' % (plugin_root(), gate))
    if notes:
        print(json.dumps({'hookSpecificOutput': {'hookEventName': 'PostToolUse',
                                                 'additionalContext': '\n'.join(notes)}}, ensure_ascii=False))


if __name__ == '__main__':
    main()
