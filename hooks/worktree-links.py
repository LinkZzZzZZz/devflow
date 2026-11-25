#!/usr/bin/env python3
import json
import os
import shutil
import subprocess
import sys
import time

GRACE_SECONDS = 120


def git(cwd, *args):
    result = subprocess.run(
        ['git', '-C', cwd, *args],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def locally_modified(path, since):
    if os.path.isfile(path) or os.path.islink(path):
        return [path] if os.path.getmtime(path) > since else []
    changed = []
    for root, _dirs, files in os.walk(path):
        for name in files:
            full = os.path.join(root, name)
            if os.path.getmtime(full) > since:
                changed.append(full)
    return changed


class Linker:
    def __init__(self, worktree, main_repo):
        self.worktree = worktree
        self.main_repo = main_repo
        self.created_at = os.path.getmtime(os.path.join(worktree, '.git')) + GRACE_SECONDS
        self.backup_root = os.path.join(worktree, '.claude', '.link-backup', time.strftime('%Y%m%d-%H%M%S'))
        self.linked = []
        self.swept = []
        self.blocked = []
        self.claude_md_was_missing = False

    def rel(self, path):
        return os.path.relpath(path, self.worktree)

    def replace_with_link(self, source, target):
        if os.path.islink(target):
            if os.path.realpath(target) != os.path.realpath(source):
                self.blocked.append('%s — симлинк ведёт не в основной репозиторий: %s' % (self.rel(target), os.readlink(target)))
            return
        if os.path.lexists(target):
            changed = locally_modified(target, self.created_at)
            if changed:
                sample = ', '.join(self.rel(p) for p in changed[:5])
                self.blocked.append('%s — копия с правками после создания worktree (%s)' % (self.rel(target), sample))
                return
            backup = os.path.join(self.backup_root, self.rel(target))
            os.makedirs(os.path.dirname(backup), exist_ok=True)
            shutil.move(target, backup)
        elif self.rel(target) == 'CLAUDE.md':
            self.claude_md_was_missing = True
        os.makedirs(os.path.dirname(target), exist_ok=True)
        os.symlink(source, target)
        self.linked.append(self.rel(target))

    def link_per_entry(self, rel, source, target, tracked):
        # `git checkout --` перезаписывает рабочие файлы версией из индекса и уносит незакоммиченные правки.
        # Восстанавливать отслеживаемое безопасно один раз — когда каталог только создаётся
        # (его не было или на его месте стоял симлинк целиком). Хук работает и на Stop, то есть
        # на каждом ходе, поэтому существующий каталог не трогаем.
        fresh = os.path.islink(target) or not os.path.exists(target)
        if os.path.islink(target):
            os.remove(target)
        os.makedirs(target, exist_ok=True)
        if fresh:
            git(self.worktree, 'checkout', '--', rel)
        tracked_entries = {path[len(rel) + 1:].split('/')[0] for path in tracked}

        for entry in sorted(os.listdir(target)):
            path = os.path.join(target, entry)
            if entry in tracked_entries or os.path.islink(path) or os.path.lexists(os.path.join(source, entry)):
                continue
            shutil.move(path, os.path.join(source, entry))
            os.symlink(os.path.join(source, entry), path)
            self.swept.append(self.rel(path))

        for entry in sorted(os.listdir(source)):
            if entry in tracked_entries:
                continue
            self.replace_with_link(os.path.join(source, entry), os.path.join(target, entry))

    def run(self, paths):
        for rel in paths:
            source = os.path.join(self.main_repo, rel)
            target = os.path.join(self.worktree, rel)
            if not os.path.exists(source):
                continue
            tracked = (git(self.worktree, 'ls-files', '--', rel) or '').splitlines()
            if tracked and os.path.isdir(source):
                self.link_per_entry(rel, source, target, tracked)
            else:
                self.replace_with_link(source, target)


def main():
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        payload = {}
    cwd = payload.get('cwd') or os.getcwd()
    session_start = (payload.get('hook_event_name') or 'SessionStart') == 'SessionStart'

    worktree = git(cwd, 'rev-parse', '--path-format=absolute', '--show-toplevel')
    common = git(cwd, 'rev-parse', '--path-format=absolute', '--git-common-dir')
    if worktree is None or common is None:
        return
    main_repo = os.path.dirname(common)
    if os.path.realpath(worktree) == os.path.realpath(main_repo):
        return

    config = os.path.join(main_repo, '.claude', 'worktree-links')
    if not os.path.isfile(config):
        return
    with open(config) as handle:
        paths = [line.strip() for line in handle if line.strip() and not line.startswith('#')]

    linker = Linker(worktree, main_repo)
    linker.run(paths)

    notes = []
    if linker.linked:
        notes.append('Worktree: подключены симлинки на основной репозиторий: %s.' % ', '.join(linker.linked))
    if linker.swept:
        notes.append('Worktree: новые каталоги перенесены в основной репозиторий и заменены симлинками: %s.' % ', '.join(linker.swept))
    if linker.blocked:
        notes.append(
            'Worktree: НЕ заменены симлинками, иначе потеряются правки. Перенеси правки в %s вручную — '
            'при следующем старте сессии хук заменит копию симлинком:\n- %s' % (main_repo, '\n- '.join(linker.blocked))
        )
    if session_start:
        if os.path.isfile(os.path.join(worktree, 'composer.json')) and not os.path.exists(os.path.join(worktree, 'vendor')):
            notes.append('Worktree: нет vendor — перед тестами и make check выполни composer install в самом worktree (vendor не симлинкать).')
        if linker.claude_md_was_missing:
            with open(os.path.join(main_repo, 'CLAUDE.md')) as handle:
                notes.append(
                    'CLAUDE.md не было в worktree на старте сессии, поэтому правила проекта не загрузились. '
                    'Они обязательны — вот содержимое %s:\n\n%s' % (os.path.join(main_repo, 'CLAUDE.md'), handle.read())
                )

    if not notes:
        return

    summary = []
    if linker.linked:
        summary.append('симлинки: %d' % len(linker.linked))
    if linker.swept:
        summary.append('перенесено в основной репозиторий: %d' % len(linker.swept))
    if linker.blocked:
        summary.append('не заменено: %d' % len(linker.blocked))
    output = {}
    if summary:
        output['systemMessage'] = 'worktree-links: ' + ', '.join(summary)
    if session_start:
        output['hookSpecificOutput'] = {
            'hookEventName': 'SessionStart',
            'additionalContext': '\n\n'.join(notes),
        }
    if output:
        print(json.dumps(output, ensure_ascii=False))


if __name__ == '__main__':
    main()
