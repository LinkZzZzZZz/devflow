#!/usr/bin/env python3
"""PreToolUse на Bash: правила проекта, которые раньше держались на дисциплине.

Проверки, каждая независима (первая сработавшая отвечает):
  0. ролевые ограничения по agent_type: implementer, system-mapper и decision-critic не трогают
     историю git, black-box-tester не открывает дифф и историю -> deny
  1. git merge в ветке тикета                                 -> deny  (расхождение чинится rebase)
  2. git pull без --rebase в ветке тикета                     -> deny
  3. запись в GitHub через gh                                -> ask   (видно другим; PR — с заголовком и описанием)
     gh pr create без показанного заголовка и описания         -> deny  (--fill, --web, --editor, нет --title/--body)
     curl или скрипт с токеном к API GitHub на запись          -> deny  (только gh — его ловит этот хук)
  4. git add -A|.|<каталог> в ветке тикета                    -> ask   (файлы тикета — явными путями)
  5. git commit со спекой в индексе                           -> ask   (docs не коммитим без просьбы)
  6. git checkout -- <файл>                                   -> ask   (мутация поверх незакоммиченного уносит работу)
  7. второй параллельный прогон тестов (lock + pgrep)         -> deny  (добивает машину)

Упавшая проверка отвечает ask, а не пропускает команду (см. lib_hook)."""
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_gh import actions as gh_actions
from lib_git_cmd import checked_trees_file, git, invocations, segments
from lib_hook import guarded, respond
from lib_workflow import get, load

TICKET_BRANCH = re.compile(r'^[A-Z][A-Z0-9]*-\d+([-/].*)?$')
DOC_PATH = re.compile(r'(^|/)docs/.*\.(md|json)$')
MERGE_OK = {'--abort', '--continue', '--quit'}
TEST_TARGETS = ('tests-parallel', 'tests-no-cov', 'tests-cov', 'test-cov', 'tests-check')
RUNNING_TESTS = re.compile(r'(phpunit|paratest)')
LOCK_FRESH_SECONDS = 120

IMPLEMENTER = re.compile(r'^(devflow:)?implementer$')
BLACK_BOX = re.compile(r'^(devflow:)?black-box-tester$')
MAPPER = re.compile(r'^(devflow:)?system-mapper$')
CRITIC = re.compile(r'^(devflow:)?decision-critic$')
IMPLEMENTER_DENIED = ('commit', 'add', 'reset', 'rebase', 'stash', 'merge', 'cherry-pick', 'push')
BLACK_BOX_DENIED = ('diff', 'show', 'blame')
PATCH_FLAGS = re.compile(r'^(-p|-u|--patch)$|^-[a-zA-Z]*p[a-zA-Z]*$')

BROAD_ADD = {'-A', '--all', '-u', '--update'}
CURL_BODY_FLAGS = {'-d', '--data', '--data-raw', '--data-binary', '--data-urlencode', '-F', '--form', '--json', '-T', '--upload-file'}
HTTP_MUTATIONS = {'POST', 'PUT', 'PATCH', 'DELETE'}
HTTP_MUTATION_WORD = re.compile(r'\b(POST|PUT|PATCH|DELETE)\b')
GITHUB_TOKEN_MARKERS = ('GITHUB_TOKEN', 'GH_TOKEN', 'Authorization: Bearer', 'Authorization: token')
GITHUB_ASK = 'Запись в GitHub видна другим людям (%s). Подтверди отправку.'
CURL_REASON = ('Запись в API GitHub через curl или скрипт с токеном обходит подтверждение. Пиши через `gh` '
               '(`gh api`, `gh pr …`, `gh issue …`) — хук покажет, что уйдёт, и спросит.')
PR_UNSHOWN_REASON = ('PR создаётся шагом отправки (branch-ops D, ship.md): заголовок и описание сначала показываются '
                     'пользователю, потом `gh pr create --title "…" --body-file <файл> --base <база>`. %s этот шаг обходит.')
PREVIEW = 300


def branch(repo):
    return git(repo, 'rev-parse', '--abbrev-ref', 'HEAD')


def in_ticket_branch(repo):
    name = branch(repo)
    return name if name and TICKET_BRANCH.match(name) else None


def check_agent_role(command, cwd, agent_type):
    if IMPLEMENTER.match(agent_type or ''):
        for sub in IMPLEMENTER_DENIED:
            if invocations(command, cwd, 'git', sub):
                return ('deny', f'`git {sub}` — не твой шаг: коммит делает оркестратор, между твоим отчётом и '
                                'ревью. Закончи работу отчётом (статус, файлы, как проверено) и не трогай историю git.')
    if MAPPER.match(agent_type or ''):
        for sub in IMPLEMENTER_DENIED:
            if invocations(command, cwd, 'git', sub):
                return ('deny', f'`git {sub}` — не твой шаг: ты строишь карты, код и историю git не меняешь. Пиши карты '
                                'Write/Edit в architecture_dir и каталог тикета, коммитит их оркестратор; закончи отчётом.')
    if CRITIC.match(agent_type or ''):
        for sub in IMPLEMENTER_DENIED:
            if invocations(command, cwd, 'git', sub):
                return ('deny', f'`git {sub}` — не твой шаг: критик только читает код и спеку. Твой выход — отчёт '
                                'reports/critic-N.md и вердикт CONTINUE/REVISE/BLOCK; правки делает оркестратор.')
    if BLACK_BOX.match(agent_type or ''):
        for sub in BLACK_BOX_DENIED:
            if invocations(command, cwd, 'git', sub):
                return ('deny', f'`git {sub}` раскрывает реализацию, а ты black-box: проверяешь заказанное в spec.md, '
                                'а не построенное. Тесты ищи по имени и grep, стек поднимай из конфига.')
        for _repo, args in invocations(command, cwd, 'git', 'log'):
            if any(PATCH_FLAGS.match(a) for a in args):
                return ('deny', '`git log` с патчем раскрывает реализацию, а ты black-box: проверяешь заказанное в '
                                'spec.md, а не построенное. `git log --oneline` без -p можно.')
    return None


def check_merge(command, cwd):
    for repo, args in invocations(command, cwd, 'git', 'merge'):
        if any(a in MERGE_OK for a in args):
            continue
        name = in_ticket_branch(repo)
        if name:
            return ('deny', f'В ветке тикета {name} расхождение с базовой чинится rebase, '
                            'а не merge-коммитом. Переписывай историю и делай force-push '
                            '(--force-with-lease). Операция D скилла branch-ops это умеет.')
    return None


def check_pull(command, cwd):
    for repo, args in invocations(command, cwd, 'git', 'pull'):
        name = in_ticket_branch(repo)
        if not name:
            continue
        if '--ff-only' in args:
            continue
        if any(a in ('--rebase', '-r') or (a.startswith('--rebase=') and a != '--rebase=false') for a in args):
            continue
        explicit_merge = '--no-rebase' in args or '--rebase=false' in args
        if not explicit_merge and (git(repo, 'config', '--get', 'pull.rebase') or '') in ('true', 'merges', 'interactive'):
            continue
        return ('deny', f'В ветке тикета {name} `git pull` без --rebase сделает merge-коммит. '
                        'Расхождение с базовой чинится rebase: `git pull --rebase` (или `git fetch` + `git rebase`). '
                        'Операция D скилла branch-ops это умеет.')
    return None


def preview(text):
    text = (text or '').strip()
    return text if len(text) <= PREVIEW else text[:PREVIEW] + '…'


def describe(action):
    kind = action['kind']
    if kind == 'pr_create':
        body = action.get('body')
        lines = len(body.splitlines()) if body is not None else '?'
        return ('Создание PR «%s»: %s → %s, ревьюеры %s%s, описание %s строк. PR увидят ревьюер и команда.'
                % (action.get('title') or '?', action.get('head') or 'текущая ветка', action.get('base') or 'база по умолчанию',
                   ', '.join(action.get('reviewers') or []) or 'нет', ', черновик' if action.get('draft') else '', lines))
    if action.get('review'):
        count = action.get('comments')
        where = ', '.join(action.get('paths') or [])
        return 'Публикация ревью PR (%s): комментариев %s%s, событие %s' % (
            action['endpoint'], '?' if count is None else count, ' — ' + where if where else '', action.get('event') or 'не задано')
    if action.get('reply'):
        return 'Ответ в тред ревью (%s)' % action['endpoint']
    if action.get('resolve'):
        return 'Резолв треда ревью (GraphQL resolveReviewThread)'
    if kind == 'api':
        return '%s %s' % (action['method'], action['endpoint'] or '?')
    return 'gh %s %s' % (kind, action.get('verb') or '')


def check_github(command, cwd):
    if ('api.github.com' in command and any(marker in command for marker in GITHUB_TOKEN_MARKERS)
            and HTTP_MUTATION_WORD.search(command)):
        return ('deny', CURL_REASON)
    for tokens in segments(command):
        if os.path.basename(tokens[0]) != 'curl' or not any('api.github.com' in t for t in tokens[1:]):
            continue
        rest = tokens[1:]
        method, body = None, False
        for index, token in enumerate(rest):
            if token in ('-X', '--request') and index + 1 < len(rest):
                method = rest[index + 1].upper()
            elif token.startswith('--request='):
                method = token.split('=', 1)[1].upper()
            elif token in CURL_BODY_FLAGS or token.startswith('--data'):
                body = True
        if method in HTTP_MUTATIONS or (body and method is None):
            return ('deny', CURL_REASON)
    writes = []
    for action in gh_actions(command, cwd):
        if action['kind'] == 'pr_create':
            if action['dry_run']:
                continue
            if action['unshown']:
                return ('deny', PR_UNSHOWN_REASON % ('`gh pr create %s`' % ' '.join(action['unshown'])))
            if not action['title'] or not action['body_given']:
                return ('deny', PR_UNSHOWN_REASON % '`gh pr create` без `--title` и `--body`/`--body-file`')
        if action['write']:
            writes.append(action)
    if not writes:
        return None
    text = '; '.join(describe(action) for action in writes)
    body = next((a.get('body') for a in writes if a['kind'] == 'pr_create' and a.get('body')), None)
    if body:
        text += '\nОписание:\n' + preview(body)
    return ('ask', GITHUB_ASK % text)


def check_add(command, cwd):
    for repo, args in invocations(command, cwd, 'git', 'add'):
        name = in_ticket_branch(repo)
        if not name:
            continue
        paths = args[args.index('--') + 1:] if '--' in args else [a for a in args if not a.startswith('-')]
        broad = any(a in BROAD_ADD for a in args) or not paths and any(a.startswith('-') for a in args)
        broad = broad or any(p == '.' or os.path.isdir(os.path.join(repo, p)) for p in paths)
        if not broad:
            continue
        pathspec = ['--', *paths] if paths else []
        changed = (git(repo, 'status', '--porcelain', '--untracked-files=all', *pathspec) or '').splitlines()
        files = [line.split(None, 1)[1] for line in changed if len(line.split(None, 1)) == 2]
        if not files:
            continue
        shown = ', '.join(files[:8]) + ('…' if len(files) > 8 else '')
        return ('ask', f'`git add` в ветке тикета {name} целиком захватит: {shown}. Файлы тикета добавляются '
                       'явными путями, чтобы в коммит не попало лишнее. Если список и есть правка тикета — подтверди.')
    return None


def check_commit(command, cwd):
    for repo, args in invocations(command, cwd, 'git', 'commit'):
        staged = git(repo, 'diff', '--cached', '--name-only')
        if not staged:
            continue
        docs = [p for p in staged.splitlines() if DOC_PATH.search(p)]
        if docs:
            shown = ', '.join(docs[:4]) + ('…' if len(docs) > 4 else '')
            return ('ask', f'В индексе файлы docs: {shown}. Spec/design-документы не коммитим '
                           'без явной просьбы пользователя — они рабочая память тикета. '
                           'Если это осознанно, подтверди.')
    return None


def check_checkout(command, cwd):
    for repo, args in invocations(command, cwd, 'git', 'checkout'):
        if '--' not in args:
            continue
        paths = args[args.index('--') + 1:]
        if not paths:
            continue
        dirty = git(repo, 'status', '--porcelain', '--', *paths)
        if not dirty:
            continue
        return ('ask', f'`git checkout --` откатит к индексу: {", ".join(paths[:4])}. '
                       'Если работа до мутации не закоммичена, она уйдёт вместе с мутацией. '
                       'Убедись, что коммит есть, и подтверди.')
    return None


def pgrep(pattern):
    try:
        out = subprocess.run(['pgrep', '-fl', pattern], capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return []
    return [line for line in out.splitlines() if 'pgrep' not in line]


def lock_path(repo):
    path = checked_trees_file(repo)
    return None if path is None else os.path.join(os.path.dirname(path), 'claude-tests.lock')


def acquire_test_lock(repo, tool_use_id):
    """Атомарный lock на прогон: pgrep видит процесс только после старта, а два агента стартуют одновременно.
    Снимает lock record-make-check.py (PostToolUse) по tool_use_id; осиротевший lock стареет за LOCK_FRESH_SECONDS."""
    path = lock_path(repo)
    if path is None:
        return None
    for _attempt in (1, 2):
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            age = time.time() - os.path.getmtime(path)
            if age < LOCK_FRESH_SECONDS:
                return 'прогон стартовал %d с назад (lock %s)' % (age, path)
            try:
                os.remove(path)
            except OSError:
                pass
            continue
        with os.fdopen(fd, 'w') as handle:
            json.dump({'tool_use_id': tool_use_id, 'started': time.time()}, handle)
        return None
    return 'lock %s не освобождается' % path


def check_tests(command, cwd, tool_use_id=None):
    cfg = load(cwd)
    pattern, process = get(cfg, 'serial_only'), get(cfg, 'test_process')
    if pattern and process:
        if not re.search(pattern, command):
            return None
        running = pgrep(process)
        reason = 'Тесты уже идут в другом процессе (%s). Прогоны в этом проекте только последовательные — дождись текущего.'
    else:
        wanted = any(os.path.basename(tokens[0]) == 'make' and any(t in TEST_TARGETS for t in tokens[1:])
                     for tokens in segments(command))
        if not wanted:
            return None
        running = [l for l in pgrep('phpunit|paratest') if RUNNING_TESTS.search(l)]
        reason = ('Прогон тестов уже идёт в другом процессе (%s). Параллельные полные прогоны добивают машину — '
                  'дождись текущего. Полный набор гоняем ровно один раз и не в нескольких агентах разом.')
    busy = running[0][:120] if running else acquire_test_lock(cwd, tool_use_id)
    return ('deny', reason % busy) if busy else None


def run():
    payload = json.load(sys.stdin)
    command = (payload.get('tool_input') or {}).get('command') or ''
    if not command:
        return
    cwd = payload.get('cwd') or os.getcwd()
    agent_type = payload.get('agent_type') or ''
    tool_use_id = payload.get('tool_use_id')

    checks = (
        ('agent_role', lambda: check_agent_role(command, cwd, agent_type)),
        ('merge', lambda: check_merge(command, cwd)),
        ('pull', lambda: check_pull(command, cwd)),
        ('github', lambda: check_github(command, cwd)),
        ('add', lambda: check_add(command, cwd)),
        ('commit', lambda: check_commit(command, cwd)),
        ('checkout', lambda: check_checkout(command, cwd)),
        ('tests', lambda: check_tests(command, cwd, tool_use_id)),
    )
    for name, check in checks:
        try:
            verdict = check()
        except Exception as error:
            verdict = ('ask', 'guard-bash-rules: проверка %s упала (%s: %s). Команда не проверена — подтверди '
                              'осознанно или почини хук.' % (name, type(error).__name__, error))
        if verdict:
            respond(*verdict)
            return


if __name__ == '__main__':
    guarded('guard-bash-rules', run)
