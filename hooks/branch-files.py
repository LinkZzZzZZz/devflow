#!/usr/bin/env python3
"""Файлы, изменённые собственными коммитами текущей ветки: коммиты HEAD, которых нет ни на одной
удалённой ветке, кроме origin/<текущая>. Эпик-ветка и база тем самым исключаются сами.
Использование: branch-files.py [--ext php] [--remote origin]  → пути через перевод строки."""
import argparse
import os
import subprocess
import sys


def git(*args):
    result = subprocess.run(['git', *args], capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ext', action='append', default=[], help='расширение без точки, можно несколько')
    parser.add_argument('--remote', default='origin')
    args = parser.parse_args()
    branch = git('rev-parse', '--abbrev-ref', 'HEAD')
    exclude = ['--exclude=%s/%s' % (args.remote, branch)] if branch and branch != 'HEAD' else []
    own = git('rev-list', '--reverse', 'HEAD', '--not', *exclude, '--remotes=%s' % args.remote)
    if not own:
        return 0
    first = own.split()[0]
    base = git('rev-parse', '--verify', '--quiet', first + '^')
    if base is None:
        print('branch-files: у первого коммита нет родителя', file=sys.stderr)
        return 1
    changed = git('diff', '--name-only', '--diff-filter=ACMR', base, 'HEAD') or ''
    exts = {'.' + ext.lstrip('.') for ext in args.ext}
    for path in changed.splitlines():
        if path and (not exts or os.path.splitext(path)[1] in exts):
            print(path)
    return 0


if __name__ == '__main__':
    sys.exit(main())
