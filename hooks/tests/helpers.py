import json
import os
import subprocess

HOOKS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def sh(cwd, *args):
    subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True)


def make_repo(tmp, workflow=None, files=None):
    repo = os.path.join(tmp, 'repo')
    os.makedirs(repo)
    sh(repo, 'git', 'init', '-q', '-b', 'dev')
    sh(repo, 'git', 'config', 'user.email', 't@t')
    sh(repo, 'git', 'config', 'user.name', 't')
    for rel, content in (files or {'README.md': 'x\n'}).items():
        path = os.path.join(repo, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as handle:
            handle.write(content)
    sh(repo, 'git', 'add', '-A')
    sh(repo, 'git', 'commit', '-q', '-m', 'init')
    if workflow is not None:
        os.makedirs(os.path.join(repo, '.claude'), exist_ok=True)
        with open(os.path.join(repo, '.claude', 'workflow.md'), 'w') as handle:
            handle.write(workflow)
        with open(os.path.join(repo, '.git', 'info', 'exclude'), 'a') as handle:
            handle.write('.claude/\n')
    return repo


def add_worktree(repo, tmp, branch='CB-1'):
    path = os.path.join(tmp, 'wt')
    sh(repo, 'git', 'worktree', 'add', '-q', '-b', branch, path)
    return path


def run_hook(name, payload):
    result = subprocess.run([os.path.join(HOOKS, name)], input=json.dumps(payload),
                            capture_output=True, text=True, timeout=60)
    out = result.stdout.strip()
    return json.loads(out) if out else None


def decision(output):
    return None if output is None else output['hookSpecificOutput'].get('permissionDecision')
