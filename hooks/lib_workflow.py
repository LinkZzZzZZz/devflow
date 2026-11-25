import fnmatch
import os
import re
import subprocess
import sys

FIELD = re.compile(r'^\s*-\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*`([^`]*)`\s*$')


def _git(cwd, *args):
    try:
        result = subprocess.run(['git', '-C', cwd, *args], capture_output=True, text=True, timeout=5)
    except Exception:
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def _existing(path):
    path = os.path.abspath(path)
    while not os.path.isdir(path):
        parent = os.path.dirname(path)
        if parent == path:
            return path
        path = parent
    return path


def parse(text):
    fields = {}
    for line in text.splitlines():
        match = FIELD.match(line)
        if match:
            fields.setdefault(match.group(1).lower(), []).append(match.group(2))
    return fields


def load(cwd):
    cwd = _existing(cwd)
    top = _git(cwd, 'rev-parse', '--show-toplevel')
    common = _git(cwd, 'rev-parse', '--path-format=absolute', '--git-common-dir')
    roots = [top] if top else []
    if common:
        main = os.path.dirname(os.path.realpath(common))
        if main not in roots:
            roots.append(main)
    for root in roots:
        path = os.path.join(root, '.claude', 'workflow.md')
        if os.path.isfile(path):
            with open(path, encoding='utf-8') as handle:
                fields = parse(handle.read())
            return {'path': os.path.realpath(path), 'root': top or root, 'fields': fields}
    return None


def get(cfg, key):
    values = (cfg or {}).get('fields', {}).get(key)
    return values[0] if values else None


def get_list(cfg, key):
    items = []
    for value in (cfg or {}).get('fields', {}).get(key, []):
        items += [part.strip() for part in value.split(',') if part.strip()]
    return items


def warn_missing(cfg, key, hook):
    if cfg and not cfg['fields'].get(key):
        sys.stderr.write('%s: в %s нет поля `%s` — проверка выключена\n' % (hook, cfg['path'], key))


def matches(path, patterns):
    path = path[2:] if path.startswith('./') else path
    for pattern in patterns:
        if pattern.startswith('/'):
            if fnmatch.fnmatchcase(path, pattern[1:]):
                return True
            continue
        if '/' not in pattern:
            if fnmatch.fnmatchcase(os.path.basename(path), pattern):
                return True
            continue
        for variant in {pattern, pattern.replace('**/', ''), pattern.replace('**/', '*/')}:
            if fnmatch.fnmatchcase(path, variant):
                return True
    return False


def enabled(cfg, key):
    return key in {item.strip().lower() for item in get_list(cfg, 'hooks')}


SKIP_DIRS = {'vendor', 'vendor-bin', 'storage', 'node_modules'}


def skipped(cfg, path):
    """Файл лежит в сторонних/служебных каталогах проекта (относительно корня репозитория, не абсолютного пути)."""
    root = os.path.realpath(cfg['root']) if cfg else None
    full = os.path.realpath(path)
    rel = os.path.relpath(full, root) if root and full.startswith(root + os.sep) else None
    parts = rel.split(os.sep) if rel else []
    if any(part in SKIP_DIRS for part in parts[:-1]):
        return True
    return rel is not None and rel.startswith('bootstrap/cache/')
