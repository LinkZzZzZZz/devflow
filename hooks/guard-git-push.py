#!/usr/bin/env python3
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_env import plugin_root
from lib_hook import guarded, respond
from lib_git_cmd import checked_trees_file, git, invocations
from lib_workflow import get, load, warn_missing

TICKET_BRANCH = re.compile(r'^(refs/heads/)?[A-Z][A-Z0-9]*-\d+([-/].*)?$')
VALUE_FLAGS = ('--repo', '--receive-pack', '--exec', '--signed')
OPTION_FLAGS = ('-o', '--push-option')


def parse_push(args):
    flags = []
    positional = []
    options = []
    rest = list(args)
    while rest:
        arg = rest.pop(0)
        if arg in OPTION_FLAGS and rest:
            options.append(rest.pop(0))
        elif arg.startswith('--push-option='):
            options.append(arg.split('=', 1)[1])
        elif arg.startswith('-o') and len(arg) > 2 and not arg.startswith('--'):
            options.append(arg[2:])
        elif arg in VALUE_FLAGS and rest:
            rest.pop(0)
        elif arg.startswith('-'):
            flags.append(arg)
        else:
            positional.append(arg)
    remote = positional[0] if positional else None
    return flags, remote, positional[1:], options


def checked(repo, tree):
    path = checked_trees_file(repo)
    if path is None or not os.path.exists(path):
        return False
    with open(path) as handle:
        return tree in (line.strip() for line in handle)


def decide(repo, args):
    top = git(repo, 'rev-parse', '--show-toplevel') or repo
    cfg = load(top)
    gate = get(cfg, 'pre_push')
    warn_missing(cfg, 'pre_push', 'guard-git-push')
    flags, remote, refspecs, options = parse_push(args)
    current = git(top, 'rev-parse', '--abbrev-ref', 'HEAD') or 'HEAD'
    if not refspecs:
        refspecs = [current]

    deleting = '--delete' in flags or '-d' in flags
    forced = [flag for flag in flags if flag in ('-f', '--force')]
    lines = []
    problems = []
    if options:
        lines.append('push-options: %s' % ', '.join(options))

    for spec in refspecs:
        spec = spec.lstrip('+')
        src, _, dst = spec.partition(':')
        dst = dst or src
        if dst == 'HEAD':
            dst = current
        if deleting or not src:
            lines.append('удаление %s на %s' % (dst, remote or 'origin'))
            continue
        sha = git(top, 'rev-parse', '--short', src + '^{commit}')
        tree = git(top, 'rev-parse', src + '^{tree}')
        label = '%s (%s) → %s/%s' % (src, sha or '?', remote or 'origin', dst)
        upstream = '%s/%s' % (remote or 'origin', dst)
        span = src if git(top, 'rev-parse', '--verify', '--quiet', upstream) is None else '%s..%s' % (upstream, src)
        subjects = (git(top, 'log', '--format=%h %s', '-5', span) or '').splitlines()
        if subjects:
            label += ' [коммиты: %s]' % ' | '.join(subjects)
        if TICKET_BRANCH.match(dst) and gate:
            if tree is not None and checked(top, tree):
                label += ', проверки перед пушем ✓ на этом дереве'
            else:
                problems.append(
                    '%s: проверки перед пушем не засчитаны на коде коммита %s. Запусти '
                    '`%s/hooks/pre-push-check.py` (выполнит `%s`) на финальном состоянии; '
                    'любая правка после прогона обнуляет результат.' % (dst, sha or src, plugin_root(), gate))
        lines.append(label)

    if forced:
        lines.append('ВНИМАНИЕ: %s без --force-with-lease' % ', '.join(forced))
    return lines, problems


def run():
    payload = json.load(sys.stdin)
    if payload.get('tool_name') != 'Bash':
        return
    command = payload.get('tool_input', {}).get('command', '')
    cwd = payload.get('cwd') or os.getcwd()

    pushes = [
        (repo, args) for repo, args in invocations(command, cwd, 'git', 'push')
        if '--dry-run' not in args and '-n' not in args
    ]
    if not pushes:
        return

    lines = []
    problems = []
    for repo, args in pushes:
        repo_lines, repo_problems = decide(repo, args)
        lines += repo_lines
        problems += repo_problems

    if problems:
        decision = 'deny'
        reason = 'Пуш остановлен хуком guard-git-push.\n' + '\n'.join(problems)
    else:
        decision = 'ask'
        reason = 'Пуш: ' + '; '.join(lines) + '. Подтверди.'
    respond(decision, reason)


if __name__ == '__main__':
    guarded('guard-git-push', run)
