#!/usr/bin/env python3
"""Stop-хук: обязательные агенты по режимам (skills/task-workflow/references/cycles.md, раздел «Машинные строки»).

Читает транскрипт сессии (JSONL, записи `assistant`): признаки режимов — Write по шаблону пути (создание файла
оркестратором; Edit не признак — правка spec.md/tasks.md идёт в любом режиме), MCP-вызовы, действия GitHub CLI
(`gh:review`, `gh:reply` — разбор lib_gh.py) и Bash-команды (bash-признак
учитывается только при Write в каталог тикета за сессию — иначе ручной запуск проверок вне тикета блокировал бы ход);
признак с `!` обязан отсутствовать. Транскрипты сабагентов лежат отдельно, их
Write хук не видит — признак всегда действие оркестратора. Агенты — вызовы Agent/Task с `subagent_type`; `агент#regex`
засчитывает только вызов, в `prompt` которого есть regex (режим брифа). Режим опознан, обязательного агента за сессию не было →
{"decision": "block", "reason": "цикл <режим>: не запущен <агент> — <что сделать>"}. Один и тот же блок за сессию —
не чаще одного раза на пару режим/агент и тикет (маркер <git common dir>/claude-cycle-<session>.json), чтобы не зациклить ход.
Неясный режим, нечитаемый транскрипт, чужой формат — молчит (fail-open, одна строка в stderr при ошибке чтения)."""
import json
import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_env import plugin_root
from lib_gh import has as gh_has

CYCLES = os.path.join('skills', 'task-workflow', 'references', 'cycles.md')
LINE = re.compile(r'^-\s*([a-z-]+):\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*$')
AGENT = re.compile(r'([a-z][a-z-]*)(?:#([^\[,]+?))?\s*(?:\[([^\]]*)\])?\s*(?:,|$)')
KEY = r'[A-Z][A-Z0-9]*-\d+'
SIZE = re.compile(r'^\s*размер\s*:\s*(\w+)', re.IGNORECASE | re.MULTILINE)
AGENT_TOOLS = ('Agent', 'Task')


def parse_cycles(text):
    cycles = []
    section = text.split('## Машинные строки', 1)
    body = section[1] if len(section) == 2 else text
    for line in body.splitlines():
        match = LINE.match(line.strip())
        if not match:
            continue
        mode, signs, agents, hint = match.groups()
        parsed_agents = [(name, prompt.strip(), condition.strip()) for name, prompt, condition in AGENT.findall(agents)]
        cycles.append({'mode': mode, 'signs': [s.strip() for s in signs.split(',') if s.strip()],
                       'agents': parsed_agents, 'hint': hint})
    return cycles


def sign_regex(sign):
    """`write:<KEY>/reports/fix-N.md#<regex>` → (regex хвоста пути, regex содержимого или None);
    `mcp:tool!field` → (tool, field); `gh:review|reply|resolve` → имя действия; `bash:<подстрока команды>` → подстрока."""
    kind, _, rest = sign.partition(':')
    if kind == 'write':
        path, _, content = rest.partition('#')
        pattern = re.escape(path).replace(re.escape('<KEY>'), '(' + KEY + ')').replace(re.escape('N'), r'\d+')
        return ('write', (re.compile('(^|/)' + pattern + '$'), re.compile(content, re.IGNORECASE) if content else None))
    if kind == 'mcp':
        tool, _, field = rest.partition('!')
        return ('mcp', (tool, field))
    if kind in ('bash', 'gh'):
        return (kind, rest)
    return (None, None)


def sign_hit(sign, signs):
    """Путь признака (или '' для признаков без пути), если признак есть в транскрипте; None — нет."""
    kind, matcher = sign_regex(sign)
    for name, inp in signs:
        if kind == 'write' and name == 'Write':
            path = inp.get('file_path') or ''
            if matcher[0].search(path.replace(os.sep, '/')) and (matcher[1] is None or matcher[1].search(inp.get('content') or '')):
                return path
        elif kind == 'mcp' and name.startswith('mcp__') and name.split('__')[-1] == matcher[0]:
            if not matcher[1] or matcher[1] not in inp:
                return ''
        elif kind == 'bash' and name == 'Bash' and matcher in (inp.get('command') or ''):
            return ''
        elif kind == 'gh' and name == 'Bash' and gh_has(inp.get('command') or '', matcher):
            return ''
    return None


def read_transcript(path):
    signs, agents = [], []
    with open(path, encoding='utf-8', errors='replace') as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if not isinstance(record, dict) or record.get('type') != 'assistant':
                continue
            message = record.get('message')
            content = message.get('content') if isinstance(message, dict) else None
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict) or block.get('type') != 'tool_use':
                    continue
                name = block.get('name') or ''
                inp = block.get('input') if isinstance(block.get('input'), dict) else {}
                if name in AGENT_TOOLS:
                    kind = (inp.get('subagent_type') or '').split(':')[-1]
                    if kind:
                        agents.append((kind, inp.get('prompt') or ''))
                else:
                    signs.append((name, inp))
    return signs, agents


def detect(cycles, signs):
    """Режимы, признаки которых есть в транскрипте: [(cycle, путь признака или None)].
    Хоть один положительный признак найден и ни одного отрицательного (`!`) нет."""
    found = []
    for cycle in cycles:
        positive = [s for s in cycle['signs'] if not s.startswith('!')]
        negative = [s[1:] for s in cycle['signs'] if s.startswith('!')]
        if any(sign_hit(s, signs) is not None for s in negative):
            continue
        for sign in positive:
            hit = sign_hit(sign, signs)
            if hit is None:
                continue
            path = hit or ticket_path(signs)
            if sign.startswith('bash:') and not path:
                continue
            found.append((cycle, path))
            break
    return found


def ticket_path(signs):
    """Для признаков без пути (bash, mcp): первый Write сессии внутри каталога <KEY>/ — оттуда размер и ключ."""
    for name, inp in signs:
        path = (inp.get('file_path') or '') if name == 'Write' else ''
        if re.search('/' + KEY + '/', path.replace(os.sep, '/')):
            return path
    return None


def size_of(sign_path):
    """Строка «Размер:» из spec.md рядом с признаком (каталог тикета — ближайший родитель с именем <KEY>)."""
    if not sign_path:
        return None
    current = os.path.dirname(sign_path)
    for _ in range(4):
        if re.fullmatch(KEY, os.path.basename(current)):
            break
        current = os.path.dirname(current)
    else:
        return None
    try:
        with open(os.path.join(current, 'spec.md'), encoding='utf-8', errors='replace') as handle:
            match = SIZE.search(handle.read())
    except OSError:
        return None
    return match.group(1).lower() if match else None


def required(agent_condition, size):
    if not agent_condition:
        return True
    if agent_condition.startswith('не '):
        return size != agent_condition[3:].strip()
    sizes = [s.strip() for s in agent_condition.split(',')]
    return size in sizes


def ticket_of(sign_path):
    match = re.search('/(' + KEY + ')/', (sign_path or '').replace(os.sep, '/') + '/')
    return match.group(1) if match else '-'


def called(agent, prompt_regex, agents):
    """Агент вызван за сессию; с `#regex` — вызов, в prompt которого regex найден."""
    pattern = re.compile(prompt_regex, re.IGNORECASE) if prompt_regex else None
    return any(kind == agent and (pattern is None or pattern.search(prompt)) for kind, prompt in agents)


def missing(cycles_found, agents):
    """[(mode, agent, hint, ticket)] — обязательный агент не вызван."""
    out = []
    for cycle, sign_path in cycles_found:
        size = size_of(sign_path)
        for agent, prompt_regex, condition in cycle['agents']:
            if required(condition, size) and not called(agent, prompt_regex, agents):
                label = '%s (%s)' % (agent, prompt_regex) if prompt_regex else agent
                out.append((cycle['mode'], label, cycle['hint'], ticket_of(sign_path)))
    return out


def marker_path(cwd, session_id):
    try:
        result = subprocess.run(['git', '-C', cwd, 'rev-parse', '--path-format=absolute', '--git-common-dir'],
                                capture_output=True, text=True, timeout=5)
        base = result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        base = None
    base = base or tempfile.gettempdir()
    return os.path.join(base, 'claude-cycle-%s.json' % re.sub(r'[^A-Za-z0-9_-]', '_', session_id or 'nosession'))


def load_marker(path):
    try:
        with open(path, encoding='utf-8') as handle:
            data = json.load(handle)
        return set(data) if isinstance(data, list) else set()
    except (OSError, ValueError):
        return set()


def save_marker(path, blocked):
    try:
        with open(path, 'w', encoding='utf-8') as handle:
            json.dump(sorted(blocked), handle, ensure_ascii=False)
    except OSError:
        pass


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return
    transcript = payload.get('transcript_path') or ''
    cwd = payload.get('cwd') or os.getcwd()
    try:
        with open(os.path.join(plugin_root(), CYCLES), encoding='utf-8') as handle:
            cycles = parse_cycles(handle.read())
    except OSError as error:
        sys.stderr.write('cycle-check: нет таблицы циклов (%s) — проверка выключена\n' % error)
        return
    try:
        signs, agents = read_transcript(transcript)
    except OSError as error:
        sys.stderr.write('cycle-check: транскрипт не прочитан (%s) — проверка выключена\n' % error)
        return
    gaps = missing(detect(cycles, signs), agents)
    if not gaps:
        return
    marker = marker_path(cwd, payload.get('session_id') or '')
    blocked = load_marker(marker)
    fresh = [gap for gap in gaps if '%s/%s/%s' % (gap[0], gap[1], gap[3]) not in blocked]
    if not fresh:
        return
    save_marker(marker, blocked | {'%s/%s/%s' % (mode, agent, ticket) for mode, agent, _, ticket in fresh})
    reason = '\n'.join('цикл %s: не запущен %s — %s' % (mode, agent, hint) for mode, agent, hint, _ in fresh)
    print(json.dumps({'decision': 'block', 'reason': reason}, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        sys.stderr.write('cycle-check: хук упал (%s: %s) — проверка выключена\n' % (type(error).__name__, error))
