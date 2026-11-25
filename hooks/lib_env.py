"""Общий .env плагина: креды трекера и локальные настройки. Путь — ~/.claude/devflow/.env
или переменная окружения DEVFLOW_ENV."""
import os
import re

DEFAULT_ENV = '~/.claude/devflow/.env'
DEFAULT_SRC = '~/dev/devflow'
LINE = re.compile(r'^\s*([A-Z][A-Z0-9_]*)\s*=\s*(.*?)\s*$')


def env_path():
    return os.path.expanduser(os.environ.get('DEVFLOW_ENV') or DEFAULT_ENV)


def load_env(path=None):
    path = path or env_path()
    env = {}
    try:
        with open(path, encoding='utf-8') as handle:
            for line in handle:
                if line.lstrip().startswith('#'):
                    continue
                match = LINE.match(line)
                if match:
                    value = match.group(2)
                    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                        value = value[1:-1]
                    env[match.group(1)] = value
    except OSError:
        return {}
    return env


def plugin_src():
    return os.path.expanduser(load_env().get('DEVFLOW_SRC') or DEFAULT_SRC)


def plugin_root():
    root = os.environ.get('CLAUDE_PLUGIN_ROOT')
    if root:
        return root
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


if __name__ == '__main__':
    import sys
    what = sys.argv[1] if len(sys.argv) > 1 else ''
    if what == 'src':
        print(plugin_src())
    elif what == 'env-path':
        print(env_path())
    else:
        sys.stderr.write('lib_env.py src | env-path\n')
        sys.exit(2)
