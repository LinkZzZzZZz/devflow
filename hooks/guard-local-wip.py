#!/usr/bin/env python3
"""PreToolUse на Bash: не даёт закоммитить локальные правки пользователя (local_wip из .claude/workflow.md)."""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_git_cmd import git, invocations
from lib_hook import guarded, respond
from lib_workflow import get_list, load, matches

BROAD_ADD = {'-A', '--all', '-u', '--update'}
COMMIT_ALL = {'-a', '--all'}
COMMIT_VALUE = {'-m', '-F', '-C', '-c', '--author', '--date', '--fixup', '--squash', '--message', '--file'}


def porcelain_paths(repo, *pathspec, tracked_only=False):
    args = ['git', '-C', repo, 'status', '--porcelain=v1', '-z',
            '--untracked-files=%s' % ('no' if tracked_only else 'all')]
    if pathspec:
        args += ['--', *pathspec]
    try:
        out = subprocess.run(args, capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return []
    paths = []
    entries = out.split('\0')
    index = 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if len(entry) < 4:
            continue
        paths.append(entry[3:])
        if entry[0] in 'RC':
            index += 1
    return paths


def hits(paths, patterns):
    return sorted({p for p in paths if matches(p, patterns)})


def check_add(repo, args, patterns):
    explicit = [a for a in args if not a.startswith('-')]
    if '--' in args:
        explicit = args[args.index('--') + 1:]
    if any(a in BROAD_ADD for a in args) or not explicit:
        return hits(porcelain_paths(repo, tracked_only='-u' in args or '--update' in args), patterns)
    return hits(porcelain_paths(repo, *explicit), patterns)


def commit_paths(args):
    if '--' in args:
        return args[args.index('--') + 1:]
    paths = []
    rest = list(args)
    while rest:
        arg = rest.pop(0)
        if arg in COMMIT_VALUE:
            if rest:
                rest.pop(0)
        elif not arg.startswith('-'):
            paths.append(arg)
    return paths


def check_commit(repo, args, patterns):
    staged = (git(repo, 'diff', '--cached', '--name-only') or '').splitlines()
    found = hits(staged, patterns)
    short = [a for a in args if a.startswith('-') and not a.startswith('--')]
    if any(a in COMMIT_ALL for a in args) or any('a' in a[1:] for a in short if a not in COMMIT_VALUE):
        found += hits(porcelain_paths(repo, tracked_only=True), patterns)
    paths = commit_paths(args)
    if paths:
        found += hits(porcelain_paths(repo, *paths), patterns)
    return sorted(set(found))


def run():
    payload = json.load(sys.stdin)
    command = (payload.get('tool_input') or {}).get('command') or ''
    cwd = payload.get('cwd') or os.getcwd()
    found = []
    for subcommand, check in (('add', check_add), ('commit', check_commit)):
        for repo, args in invocations(command, cwd, 'git', subcommand):
            patterns = get_list(load(repo), 'local_wip')
            if patterns:
                found += check(repo, args, patterns)
    if not found:
        return
    respond('deny', 'Это локальные правки пользователя, их не коммитим: %s. Добавляй файлы тикета явными путями '
                    '(`git add <путь>`), без -A/./каталогов, где лежат эти файлы. Список — секция «Не коммитить» '
                    'в .claude/workflow.md.' % ', '.join(sorted(set(found))))


if __name__ == '__main__':
    guarded('guard-local-wip', run)
