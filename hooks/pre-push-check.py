#!/usr/bin/env python3
"""Прогон pre_push из .claude/workflow.md и засчёт дерева для гейта пуша.

Вывод проверок уходит в <git-dir>/claude-pre-push.log, в stdout только итог: модели для решения «пушить или
чинить» нужны код выхода и места падений, а не тысячи строк линтера, которые потом едут в контексте до компакции.
`--verbose` стримит всё как есть (ручной запуск)."""
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_env import plugin_root
from lib_git_cmd import git, record_checked_tree
from lib_workflow import get, get_list, load, matches

TAIL_LINES = 40
ERROR_LINE = re.compile(r'error|fail|✗|exception|fatal', re.IGNORECASE)
MAX_ERROR_LINES = 40
KNOWLEDGE_BASE_FAILED = 5


def run_logged(command, repo, env, log_path):
    with open(log_path, 'w', encoding='utf-8') as log:
        log.write('$ %s\n' % command)
        log.flush()
        code = subprocess.run(command, shell=True, cwd=repo, env=env, stdout=log, stderr=subprocess.STDOUT).returncode
    with open(log_path, encoding='utf-8', errors='replace') as log:
        lines = log.read().splitlines()[1:]
    return code, lines


def failure_digest(lines, log_path):
    tail = lines[-TAIL_LINES:]
    errors = [line for line in lines[:-TAIL_LINES] if ERROR_LINE.search(line)][:MAX_ERROR_LINES]
    out = []
    if errors:
        out.append('--- строки с ошибками выше хвоста (%d) ---' % len(errors))
        out += errors
    out.append('--- последние %d строк ---' % len(tail))
    out += tail
    out.append('полный вывод: %s' % log_path)
    return '\n'.join(out)


def candidate_tree(repo, wip):
    """Дерево будущего коммита: HEAD + изменения отслеживаемых файлов, без local_wip и неотслеживаемых."""
    git_dir = git(repo, 'rev-parse', '--path-format=absolute', '--git-dir')
    if git_dir is None:
        return None, []
    changed = (git(repo, 'diff', '--name-only', 'HEAD') or '').splitlines()
    skipped = [path for path in changed if matches(path, wip)]
    keep = [path for path in changed if path not in skipped]
    index = os.path.join(git_dir, 'claude-pre-push-index-%d' % os.getpid())
    env = dict(os.environ, GIT_INDEX_FILE=index)
    try:
        if git(repo, 'read-tree', 'HEAD', env=env) is None:
            return None, skipped
        if keep and git(repo, 'add', '-u', '--', *keep, env=env) is None:
            return None, skipped
        return git(repo, 'write-tree', env=env), skipped
    finally:
        if os.path.exists(index):
            os.remove(index)


def main():
    verbose = '--verbose' in sys.argv[1:]
    cfg = load(os.getcwd())
    command = get(cfg, 'pre_push')
    if not command:
        print('pre-push-check: в .claude/workflow.md нет поля pre_push — добавь в секцию «Проверки» строку '
              '`- pre_push: `<команда проверок>`` (эквивалент CI, без автофикса) и запусти снова', file=sys.stderr)
        return 2
    repo = cfg['root']
    wip = get_list(cfg, 'local_wip')
    before, skipped = candidate_tree(repo, wip)
    if before is None:
        print('pre-push-check: не удалось собрать дерево коммита (нет HEAD?) — сделай первый коммит и запусти снова', file=sys.stderr)
        return 4
    gate = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'knowledge-base-check.py')],
                          cwd=repo, capture_output=True, text=True)
    print((gate.stdout + gate.stderr).rstrip(), flush=True)
    if gate.returncode != 0:
        print('pre-push-check: УПАЛО (база знаний) — дерево не засчитано')
        return KNOWLEDGE_BASE_FAILED
    print('$ ' + command, flush=True)
    env = dict(os.environ, DEVFLOW_ROOT=plugin_root(), CLAUDE_PLUGIN_ROOT=plugin_root())
    if verbose:
        code, lines, log_path = subprocess.run(command, shell=True, cwd=repo, env=env).returncode, [], None
    else:
        log_path = os.path.join(git(repo, 'rev-parse', '--path-format=absolute', '--git-dir'), 'claude-pre-push.log')
        code, lines = run_logged(command, repo, env, log_path)
    after, _ = candidate_tree(repo, wip)
    if code != 0:
        if log_path:
            print(failure_digest(lines, log_path))
        print('pre-push-check: УПАЛО (код %d) — дерево не засчитано: почини найденное выше и запусти снова' % code)
        return code
    if before != after:
        print('pre-push-check: проверки изменили файлы — закоммить правки и запусти снова')
        return 3
    record_checked_tree(repo, after)
    print('pre-push-check: OK, засчитано дерево %s' % after[:10])
    if skipped:
        print('pre-push-check: локальные правки не входят в засчитанное дерево: %s' % ', '.join(skipped))
    if after != git(repo, 'rev-parse', 'HEAD^{tree}'):
        print('pre-push-check: есть незакоммиченные изменения файлов тикета — гейт пропустит пуш после коммита ровно этого содержимого')
    return 0


if __name__ == '__main__':
    sys.exit(main())
