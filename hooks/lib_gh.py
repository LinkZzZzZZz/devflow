"""Разбор команд GitHub CLI для хуков: что команда делает на GitHub — читает или пишет, и что именно пишет.

Используют guard-bash-rules.py (подтверждение записи, запрет PR без показанного текста) и cycle-check.py
(признаки `gh:review`, `gh:reply` режимов review-pr и resolve-pr-comments).

Источники: `gh api --help` и https://cli.github.com/manual/gh_api — «The default HTTP request method is GET normally
and POST if any parameters were added»; REST-пути ревью — https://docs.github.com/en/rest/pulls/reviews
(`POST /repos/{owner}/{repo}/pulls/{n}/reviews`, `…/reviews/{id}/events`) и https://docs.github.com/en/rest/pulls/comments
(`POST …/pulls/{n}/comments/{comment_id}/replies`)."""
import json
import os
import re

from lib_git_cmd import resolve_dir, segments

API_VALUE_FLAGS = {'-X', '--method', '-F', '--field', '-f', '--raw-field', '-H', '--header', '--hostname', '--input',
                   '-q', '--jq', '-p', '--preview', '-t', '--template', '--cache'}
API_FIELD_FLAGS = {'-F', '--field', '-f', '--raw-field'}
GH_VALUE_FLAGS = {'-R', '--repo'}
PR_CREATE_VALUE_FLAGS = {'-a', '--assignee', '-B', '--base', '-b', '--body', '-F', '--body-file', '-H', '--head',
                         '-l', '--label', '-m', '--milestone', '-p', '--project', '--recover', '-r', '--reviewer',
                         '-T', '--template', '-t', '--title', '-R', '--repo', '--attach'}
PR_CREATE_UNSHOWN = {'-f', '--fill', '--fill-first', '--fill-verbose', '-w', '--web', '-e', '--editor'}
MUTATIONS = {'POST', 'PUT', 'PATCH', 'DELETE'}
PR_WRITES = {'close', 'comment', 'edit', 'lock', 'merge', 'ready', 'reopen', 'revert', 'review', 'unlock',
             'update-branch'}
ISSUE_WRITES = {'create', 'close', 'comment', 'delete', 'develop', 'edit', 'lock', 'pin', 'reopen', 'transfer',
                'unlock', 'unpin'}
OTHER_WRITES = {'create', 'delete', 'edit', 'set', 'run', 'rerun', 'cancel', 'close', 'merge', 'comment', 'upload',
                'transfer', 'archive', 'unarchive', 'rename', 'fork', 'sync', 'clone-template', 'enable', 'disable'}
REVIEW = re.compile(r'^(?:repos/[^/]+/[^/]+/)?pulls/[^/]+/reviews(?:/[^/]+/events)?$')
REPLY = re.compile(r'^(?:repos/[^/]+/[^/]+/)?pulls/[^/]+/comments/[^/]+/replies$')


def _value(rest, index):
    return rest[index + 1] if index + 1 < len(rest) else ''


def _split_flag(token):
    """`--field=a=b` → ('--field', 'a=b'); `-fa=b` → ('-f', 'a=b'); иначе (token, None)."""
    if token.startswith('--') and '=' in token:
        flag, _, value = token.partition('=')
        return flag, value
    if len(token) > 2 and token[0] == '-' and token[1] != '-' and token[:2] in API_VALUE_FLAGS | PR_CREATE_VALUE_FLAGS:
        return token[:2], token[2:]
    return token, None


def _parse(rest, value_flags):
    """Позиционные аргументы и флаги со значениями: ([позиционные], [(флаг, значение)], {булевы флаги})."""
    positional, valued, switches = [], [], set()
    index = 0
    while index < len(rest):
        flag, inline = _split_flag(rest[index])
        if flag in value_flags:
            if inline is None:
                valued.append((flag, _value(rest, index)))
                index += 2
                continue
            valued.append((flag, inline))
        elif flag.startswith('-') and flag != '-':
            switches.add(flag)
        else:
            positional.append(rest[index])
        index += 1
    return positional, valued, switches


def _read(cwd, path):
    if not path or path == '-':
        return None
    try:
        with open(resolve_dir(cwd, path), encoding='utf-8') as handle:
            return handle.read()
    except OSError:
        return None


def _api(rest, cwd):
    positional, valued, _ = _parse(rest, API_VALUE_FLAGS)
    endpoint = positional[0].lstrip('/') if positional else ''
    method = next((value.upper() for flag, value in valued if flag in ('-X', '--method')), None)
    fields = [value for flag, value in valued if flag in API_FIELD_FLAGS]
    input_path = next((value for flag, value in valued if flag == '--input'), None)
    if method is None:
        method = 'POST' if fields or input_path is not None else 'GET'
    action = {'kind': 'api', 'method': method, 'endpoint': endpoint, 'write': False}
    if endpoint == 'graphql':
        texts = []
        for value in fields:
            key, _, val = value.partition('=')
            if key == 'query':
                texts.append(_read(cwd, val[1:]) if val.startswith('@') else val)
        if input_path is not None:
            texts.append(_read(cwd, input_path))
        unknown = any(text is None for text in texts)
        mutation = any(re.search(r'\bmutation\b', text) for text in texts if text)
        action['write'] = mutation or unknown
        action['graphql_mutation'] = mutation
        action['resolve'] = any('resolveReviewThread' in text for text in texts if text)
        return action
    if method not in MUTATIONS:
        return action
    action['write'] = True
    if method == 'POST' and REVIEW.match(endpoint):
        action['review'] = True
        body = _read(cwd, input_path) if input_path is not None else None
        try:
            data = json.loads(body) if body else {}
        except ValueError:
            data = {}
        comments = data.get('comments') if isinstance(data, dict) else None
        action['comments'] = len(comments) if isinstance(comments, list) else None
        action['paths'] = sorted({c.get('path') for c in comments if isinstance(c, dict) and c.get('path')}) \
            if isinstance(comments, list) else []
        event = data.get('event') if isinstance(data, dict) else None
        event = event or next((v.partition('=')[2] for v in fields if v.startswith('event=')), None)
        action['event'] = event
    elif method == 'POST' and REPLY.match(endpoint):
        action['reply'] = True
    return action


def _pr_create(rest, cwd):
    _, valued, switches = _parse(rest, PR_CREATE_VALUE_FLAGS)
    values = {}
    for flag, value in valued:
        values.setdefault(flag, []).append(value)
    first = lambda *flags: next((values[f][0] for f in flags if f in values), None)
    body = first('-b', '--body')
    body_file = first('-F', '--body-file')
    if body is None and body_file is not None:
        body = _read(cwd, body_file)
    return {
        'kind': 'pr_create', 'write': True,
        'dry_run': '--dry-run' in switches,
        'title': first('-t', '--title'),
        'body': body,
        'body_given': first('-b', '--body') is not None or body_file is not None,
        'base': first('-B', '--base'),
        'head': first('-H', '--head'),
        'reviewers': [v for f in ('-r', '--reviewer') for v in values.get(f, [])],
        'draft': '-d' in switches or '--draft' in switches,
        'unshown': sorted(switches & PR_CREATE_UNSHOWN),
    }


def actions(command, cwd):
    """Действия gh в команде: список словарей с `kind` и `write`; чтение тоже попадает (write=False)."""
    found = []
    for tokens in segments(command):
        if os.path.basename(tokens[0]) != 'gh' or len(tokens) < 2:
            continue
        rest = tokens[1:]
        while rest and rest[0] in GH_VALUE_FLAGS:
            rest = rest[2:]
        if not rest:
            continue
        group, args = rest[0], rest[1:]
        if group == 'api':
            found.append(_api(args, cwd))
            continue
        verb = next((a for a in args if not a.startswith('-')), '')
        if group == 'pr' and verb == 'create':
            found.append(_pr_create(args[args.index('create') + 1:], cwd))
        elif group == 'pr':
            found.append({'kind': 'pr', 'verb': verb, 'write': verb in PR_WRITES})
        elif group == 'issue':
            found.append({'kind': 'issue', 'verb': verb, 'write': verb in ISSUE_WRITES})
        else:
            found.append({'kind': group, 'verb': verb, 'write': verb in OTHER_WRITES})
    return found


def has(command, sign):
    """Признак для cycle-check: `review` — публикация ревью PR, `reply` — ответ в тред ревью, `resolve` — резолв треда."""
    for action in actions(command, os.getcwd()):
        if action.get(sign):
            return True
        if sign == 'review' and action.get('kind') == 'pr' and action.get('verb') == 'review':
            return True
    return False
