#!/usr/bin/env python3
"""PreToolUse на Bash: не даёт из worktree писать в общий .claude основного репозитория.

Изоляция worktree в Claude Code закрывает Edit и Write, но не Bash: правка
через `python3 - <<PY`, `sed -i`, `tee` или `>` проходила незамеченной.

Важное свойство: смотрим не «есть ли где-то в строке признак записи», а какие
именно пути стоят в позиции цели записи. Иначе `2>/dev/null` в обычном `grep`
делает ложный отказ. Относительные цели резолвятся от каталога на момент сегмента:
`cd lab && echo x > CLAUDE.md` пишет в lab/CLAUDE.md, а не в CLAUDE.md worktree.
"""
import json
import os
import re
import shlex
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_git_cmd import resolve_dir
from lib_hook import guarded, respond

REDIRECT = re.compile(r'(?<![0-9])>>?\s*([^\s;|&<>]+)|[0-9]>>?\s*([^\s;|&<>]+)')
PY_OPEN = re.compile(r"""open\(\s*['"]([^'"]+)['"]\s*,\s*['"][wax]""")
JS_WRITE = re.compile(r"""writeFileSync\(\s*['"]([^'"]+)['"]""")
DEST_LAST = {'cp', 'mv', 'install', 'rsync'}
ALL_ARGS = {'rm', 'touch', 'mkdir', 'truncate', 'chmod', 'chown', 'unlink', 'tee', 'ln'}
SEPARATORS = re.compile(r'&&|\|\||;|\||\n')


def main_repo_of(cwd):
    """Если cwd — worktree, вернуть корень основного репозитория, иначе None."""
    def rp(*a):
        r = subprocess.run(['git', '-C', cwd, 'rev-parse', '--path-format=absolute', *a],
                           capture_output=True, text=True, timeout=5)
        return None if r.returncode else r.stdout.strip()
    try:
        common, own = rp('--git-common-dir'), rp('--git-dir')
    except Exception:
        return None
    if not common or not own or os.path.realpath(common) == os.path.realpath(own):
        return None
    return os.path.dirname(os.path.realpath(common))


def write_targets(command, cwd):
    """Пары (каталог на момент сегмента, путь в позиции цели записи)."""
    out = []
    current = cwd
    for part in SEPARATORS.split(command):
        for m in REDIRECT.finditer(part):
            out.append((current, m.group(1) or m.group(2)))
        out += [(current, t) for t in PY_OPEN.findall(part)]
        out += [(current, t) for t in JS_WRITE.findall(part)]
        try:
            tokens = shlex.split(part)
        except ValueError:
            tokens = part.split()
        if not tokens:
            continue
        prog = os.path.basename(tokens[0])
        args = [t for t in tokens[1:] if not t.startswith('-')]
        if prog == 'cd' and args:
            current = resolve_dir(current, args[0])
        elif prog == 'sed' and any(t.startswith('-i') or t == '-i' for t in tokens[1:]):
            out += [(current, t) for t in (args[1:] if len(args) > 1 else args)]
        elif prog in DEST_LAST and args:
            out.append((current, args[-1]))
        elif prog in ALL_ARGS:
            out += [(current, t) for t in args]
    return [(base, t) for base, t in out if t and t != '/dev/null' and not t.startswith('$')]


def run():
    payload = json.load(sys.stdin)
    command = (payload.get('tool_input') or {}).get('command') or ''
    if not command:
        return
    cwd = payload.get('cwd') or os.getcwd()
    raw_targets = write_targets(command, cwd)
    if not raw_targets:
        return
    main_repo = main_repo_of(cwd)
    if not main_repo:
        return
    roots = (os.path.realpath(os.path.join(main_repo, '.claude')),
             os.path.realpath(os.path.join(main_repo, 'CLAUDE.md')))

    # Сам worktree лежит внутри <main>/.claude/worktrees/, поэтому любой его файл
    # формально попадает под защищённый корень. Своё рабочее дерево исключаем:
    # ссылки на общий конфиг ведут туда симлинками и после realpath всё равно ловятся.
    top = subprocess.run(['git', '-C', cwd, 'rev-parse', '--show-toplevel'],
                         capture_output=True, text=True, timeout=5)
    own_tree = os.path.realpath(top.stdout.strip()) if top.returncode == 0 else None

    hits = []
    for base, raw in raw_targets:
        path = os.path.expanduser(raw.strip('\'"'))
        if not os.path.isabs(path):
            path = os.path.join(base, path)
        real = os.path.realpath(path)
        if own_tree and (real == own_tree or real.startswith(own_tree + os.sep)):
            continue
        if any(real == r or real.startswith(r + os.sep) for r in roots):
            hits.append(raw)
    if not hits:
        return

    respond('deny', 'Из worktree нельзя писать в общий конфиг основного репозитория: '
                    + ', '.join(sorted(set(hits))[:4])
                    + '. Изоляция worktree закрывает Edit и Write, но не Bash — этот хук '
                      'закрывает ту же дыру. Правь из сессии основного репозитория. '
                      'Чтение этих файлов разрешено.')


if __name__ == '__main__':
    guarded('guard-worktree-writes', run)
