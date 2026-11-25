import os
import re
import shlex
import subprocess

SEPARATORS = re.compile(r'&&|\|\||;|\||\n')


def git(cwd, *args, env=None):
    result = subprocess.run(
        ['git', '-C', cwd, *args],
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def segments(command):
    for part in SEPARATORS.split(command):
        try:
            tokens = shlex.split(part)
        except ValueError:
            tokens = part.split()
        while tokens and re.match(r'^[A-Za-z_][A-Za-z0-9_]*=', tokens[0]):
            tokens = tokens[1:]
        if tokens:
            yield tokens


def resolve_dir(base, path):
    path = os.path.expanduser(path)
    return os.path.normpath(path if os.path.isabs(path) else os.path.join(base, path))


def invocations(command, cwd, program, subcommand):
    current = cwd
    found = []
    for tokens in segments(command):
        if tokens[0] == 'cd' and len(tokens) >= 2:
            current = resolve_dir(current, tokens[1])
            continue
        if os.path.basename(tokens[0]) != program:
            continue
        workdir = current
        rest = tokens[1:]
        while rest and rest[0].startswith('-') and rest[0] != '--':
            flag = rest.pop(0)
            if flag in ('-C', '-c', '--git-dir', '--work-tree', '-f', '--file', '--directory') and rest:
                value = rest.pop(0)
                if flag in ('-C', '--directory'):
                    workdir = resolve_dir(workdir, value)
            elif flag.startswith('--directory='):
                workdir = resolve_dir(workdir, flag.split('=', 1)[1])
        if rest and subcommand == rest[0]:
            found.append((workdir, rest[1:]))
    return found


def worktree_tree(repo):
    git_dir = git(repo, 'rev-parse', '--path-format=absolute', '--git-dir')
    if git_dir is None:
        return None
    index = os.path.join(git_dir, 'claude-check-index')
    env = dict(os.environ, GIT_INDEX_FILE=index)
    try:
        if git(repo, 'read-tree', 'HEAD', env=env) is None:
            return None
        if git(repo, 'add', '-A', env=env) is None:
            return None
        return git(repo, 'write-tree', env=env)
    finally:
        if os.path.exists(index):
            os.remove(index)


def checked_trees_file(repo):
    common_dir = git(repo, 'rev-parse', '--path-format=absolute', '--git-common-dir')
    if common_dir is None:
        return None
    return os.path.join(common_dir, 'claude-make-check-trees')


def record_checked_tree(repo, tree, keep=100):
    path = checked_trees_file(repo)
    if path is None or tree is None:
        return
    lines = []
    if os.path.exists(path):
        with open(path) as handle:
            lines = [line.strip() for line in handle if line.strip()]
    lines = [line for line in lines if line != tree] + [tree]
    with open(path, 'w') as handle:
        handle.write('\n'.join(lines[-keep:]) + '\n')
