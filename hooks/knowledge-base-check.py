#!/usr/bin/env python3
"""Гейт базы знаний перед пушем: каждый файл ветки покрыт картой модуля (`paths:` во фронтматтере
<architecture_dir>/<модуль>.md), каждая затронутая карта изменена в ветке и сверена по содержимому — коммит `сверено:`
существует и среди файлов `git diff <сверено> HEAD` плюс незакоммиченных нет ни одного под `paths` карты (родство с HEAD
не требуется: сквош и ребейз переживаются, правка модуля после сверки — нет); на ветке тикета есть <tasks_dir>/<KEY>/map.md. Карта — файл <architecture_dir>/*.md (плоско, без подкаталогов)
с полем `module:` во фронтматтере; прочие .md (README, заметки) пропускаются. База знаний бывает в git (карта
коммитится с кодом — тогда она обязана быть изменена в ветке) или локальной: каталог исключён через .gitignore /
.git/info/exclude либо лежит за симлинком на основной репозиторий (worktree-links). Локальная карта одна на все
worktree и описывает базовую ветку, поэтому сверяется с базой, не с веткой: база — merge-base HEAD с origin/<base>
(иначе с локальным <base>) конфига, без base — точка ветвления; устарела, если `сверено` не потомок базы и
`git diff <сверено> <база>` трогает файлы под `paths`; собственные правки ветки карту не устаревают (их
несёт feature-map тикета). Карта не в git и не исключена — ошибка с действием.
Файлы ветки — как в branch-files.py: собственные коммиты HEAD, которых нет ни на одной удалённой ветке, кроме
origin/<текущая> (эпик-ветка и база исключаются сами); без remote — от `base` конфига. Вызывается из pre-push-check.py
до запуска pre_push; запускается и руками.

Без поля architecture_dir в .claude/workflow.md молчит (одна строка, код 0). Любое УПАЛО — код 5; текст называет действие."""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_env import plugin_root
from lib_git_cmd import git
from lib_workflow import get, get_list, load, matches

EXIT_FAILED = 5
TICKET_KEY = re.compile(r'^[A-Z][A-Z0-9]*-\d+')
SHA = re.compile(r'^[0-9a-f]{7,40}$')


def frontmatter(text):
    """Поля фронтматтера карты: paths → список шаблонов (инлайн `[a, b]` или строки `- a`), остальное → строка."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != '---':
        return {}
    fields = {}
    key = None
    for line in lines[1:]:
        if line.strip() == '---':
            break
        if line.startswith((' ', '\t', '-')) and key == 'paths':
            item = line.strip().lstrip('-').strip().strip('\'"')
            if item:
                fields['paths'].append(item)
            continue
        name, sep, value = line.partition(':')
        if not sep:
            continue
        key = name.strip().lower()
        value = value.split('#', 1)[0].strip()
        if key == 'paths':
            inner = value.strip('[]')
            fields['paths'] = [part.strip().strip('\'"') for part in inner.split(',') if part.strip()] if inner else []
        else:
            fields[key] = value.strip('\'"')
    return fields


def load_maps(repo, arch_dir):
    maps = []
    root = os.path.join(repo, arch_dir)
    if not os.path.isdir(root):
        return maps
    for name in sorted(os.listdir(root)):
        if not name.endswith('.md'):
            continue
        rel = os.path.join(arch_dir, name)
        with open(os.path.join(root, name), encoding='utf-8-sig', errors='replace') as handle:
            fields = frontmatter(handle.read())
        if not fields.get('module'):
            continue  # README и заметки без фронтматтера `module:` — не карты
        maps.append({'path': rel, 'name': name, 'module': fields['module'],
                     'paths': fields.get('paths'), 'sverено': fields.get('сверено')})
    return maps


def branch_base(repo, cfg):
    """Коммит, от которого отведена ветка: родитель первого собственного коммита (как branch-files.py — коммиты
    HEAD, которых нет на удалённых ветках, кроме origin/<текущая>) → origin/<base> → локальный <base>."""
    branch = git(repo, 'rev-parse', '--abbrev-ref', 'HEAD')
    exclude = ['--exclude=origin/%s' % branch] if branch and branch != 'HEAD' else []
    own = git(repo, 'rev-list', '--reverse', 'HEAD', '--not', *exclude, '--remotes=origin')
    if own:
        parent = git(repo, 'rev-parse', '--verify', '--quiet', own.split()[0] + '^')
        if parent:
            return parent
    return config_base(repo, cfg)[1]


def config_base(repo, cfg):
    """Базовая ветка конфига и merge-base с ней HEAD: (origin/<base> или локальный <base>, sha); (None, None) без base."""
    base = get(cfg, 'base')
    if base:
        for ref in ('origin/%s' % base, base):
            if git(repo, 'rev-parse', '--verify', '--quiet', ref + '^{commit}') is not None:
                return ref, git(repo, 'merge-base', 'HEAD', ref)
    return None, None


def branch_files(repo, base, cfg, arch_dir):
    committed = (git(repo, 'diff', '--name-only', '--diff-filter=ACMR', base, 'HEAD') or '').splitlines()
    dirty = (git(repo, 'diff', '--name-only', '--diff-filter=ACMR', 'HEAD') or '').splitlines()
    skip_dirs = [arch_dir, get(cfg, 'tasks_dir') or 'docs/tasks', get(cfg, 'epics_dir') or 'docs/epics']
    skip_dirs = [d.strip('/') + '/' for d in skip_dirs]
    ignore = get_list(cfg, 'architecture_ignore') + get_list(cfg, 'local_wip')
    out = []
    for path in dict.fromkeys(committed + dirty):
        if not path or any(path.startswith(d) for d in skip_dirs) or matches(path, ignore):
            continue
        out.append(path)
    return out


def changed_in_branch(repo, base, path):
    committed = git(repo, 'diff', '--name-only', base, 'HEAD', '--', path)
    return bool(committed or git(repo, 'diff', '--name-only', 'HEAD', '--', path))


def local_map(repo, rel):
    """Карта вне git: путь игнорируется (.gitignore, .git/info/exclude) или ведёт за симлинком из дерева репозитория."""
    if git(repo, 'check-ignore', '-q', '--', rel) is not None:
        return True
    real = os.path.realpath(os.path.join(repo, rel))
    return not real.startswith(os.path.realpath(repo) + os.sep)


def base_changed_since(repo, sha, base, paths):
    """Файлы под `paths`, изменённые в базе после сверки локальной карты. Карта новее базы (`сверено` —
    потомок базы) считается свежей: она описывает более поздний master, чем видит ветка."""
    if git(repo, 'merge-base', '--is-ancestor', base, sha) is not None:
        return []
    committed = (git(repo, 'diff', '--name-only', sha, base) or '').splitlines()
    return [path for path in committed if path and matches(path, paths)]


def changed_since(repo, sha, paths):
    """Файлы под `paths` карты, изменённые с коммита сверки: `git diff <sha> HEAD` плюс незакоммиченные."""
    committed = (git(repo, 'diff', '--name-only', sha, 'HEAD') or '').splitlines()
    dirty = (git(repo, 'diff', '--name-only', 'HEAD') or '').splitlines()
    return [path for path in dict.fromkeys(committed + dirty) if path and matches(path, paths)]


def ticket_key(repo, cfg):
    branch = git(repo, 'rev-parse', '--abbrev-ref', 'HEAD') or ''
    pattern = get(cfg, 'key')
    match = None
    if pattern:
        try:
            match = re.match(pattern, branch)
        except re.error:
            match = None
    match = match or TICKET_KEY.match(branch)
    return match.group(0) if match else None


def map_md_exists(repo, cfg, key):
    tasks_dir = get(cfg, 'tasks_dir') or 'docs/tasks'
    epics_dir = get(cfg, 'epics_dir') or 'docs/epics'
    if os.path.isfile(os.path.join(repo, tasks_dir, key, 'map.md')):
        return True
    root = os.path.join(repo, epics_dir)
    if os.path.isdir(root):
        for epic in os.listdir(root):
            if os.path.isfile(os.path.join(root, epic, 'tickets', key, 'map.md')):
                return True
    return False


def check(cfg, repo):
    arch_dir = (get(cfg, 'architecture_dir') or '').strip('/')
    if not arch_dir:
        return True, ['база знаний: не настроена (нет architecture_dir в .claude/workflow.md)']
    base = branch_base(repo, cfg)
    if not base:
        return False, ['база знаний: УПАЛО — база ветки не определена: задай base в секции «Git» .claude/workflow.md '
                       '(или сделай fetch origin), иначе не отличить файлы ветки от базы']
    base_ref, base_point = config_base(repo, cfg)
    if not base_point:
        base_ref, base_point = None, base
    failed = []
    maps = load_maps(repo, arch_dir)
    for card in maps:
        if card['paths'] is None:
            failed.append('карта %s без paths — добавь во фронтматтер строку paths: [<glob>, …] с файлами модуля' % card['path'])
    files = branch_files(repo, base, cfg, arch_dir)
    touched = {}
    for path in files:
        owners = [card for card in maps if card['paths'] and matches(path, card['paths'])]
        if not owners:
            module = os.path.dirname(path) or path
            failed.append('нет карты для %s — создай %s/<модуль>.md с paths или добавь путь в существующую '
                          '(/map %s area)' % (path, arch_dir, module))
        for card in owners:
            touched[card['path']] = card
    for card in touched.values():
        tracked = git(repo, 'ls-files', '--error-unmatch', '--', card['path']) is not None
        local = not tracked and local_map(repo, card['path'])
        if not tracked and not local:
            failed.append('карта %s не добавлена в git — `git add %s`; для локальной базы знаний исключи %s/ '
                          'в .git/info/exclude (гейт и сквош видят только отслеживаемые или исключённые файлы)'
                          % (card['name'], card['path'], arch_dir))
            continue
        sha = card['sverено'] or ''
        if not SHA.match(sha) or (tracked and not changed_in_branch(repo, base, card['path'])):
            failed.append('карта %s не сверена с кодом ветки — запусти system-mapper (area или feature) и обнови '
                          'строку сверено (sha коммита, на котором сверял)' % card['name'])
            continue
        if git(repo, 'rev-parse', '--verify', '--quiet', sha + '^{commit}') is None:
            failed.append('коммит сверки %s карты %s не найден (чистый клон или gc) — пересвери карту маппером '
                          '(system-mapper area или feature) и обнови строку сверено' % (sha[:7], card['name']))
            continue
        if local:
            stale = base_changed_since(repo, sha, base_point, card['paths'])
            if stale:
                failed.append('карта %s отстала от базы%s: после %s в %s изменены %s — запусти system-mapper area '
                              'и обнови строку сверено' % (card['name'], ' ' + base_ref if base_ref else '', sha[:7],
                                                           base_point[:7], ', '.join(stale[:5])))
            continue
        stale = changed_since(repo, sha, card['paths'])
        if stale:
            failed.append('карта %s не сверена с кодом ветки: после %s изменены %s — запусти system-mapper '
                          '(area или feature) и обнови строку сверено' % (card['name'], sha[:7], ', '.join(stale[:5])))
    key = ticket_key(repo, cfg)
    if key and not map_md_exists(repo, cfg, key):
        failed.append('карта области %s/map.md отсутствует — шаг «Карта области» start.md пропущен: '
                      'запусти system-mapper area' % key)
    if failed:
        return False, ['база знаний: УПАЛО — %s' % line for line in failed]
    return True, ['база знаний: %d карт сверено на %s (файлов ветки: %d)'
                  % (len(touched), (git(repo, 'rev-parse', '--short', 'HEAD') or '?'), len(files))]


def main():
    cfg = load(os.getcwd())
    if not cfg:
        print('база знаний: не настроена (нет .claude/workflow.md)')
        return 0
    repo = cfg['root']
    ok, lines = check(cfg, repo)
    print('\n'.join(lines))
    return 0 if ok else EXIT_FAILED


if __name__ == '__main__':
    sys.exit(main())
