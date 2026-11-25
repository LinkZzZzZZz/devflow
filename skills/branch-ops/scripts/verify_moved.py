#!/usr/bin/env python3
"""Сверяет коммиты до и после переноса (rebase / cherry-pick).

Пары ищутся по (дата автора, автор, тема) — rebase и cherry-pick их сохраняют.
Для каждой пары сравнивается git patch-id; несовпавшие показываются через range-diff.

  verify_moved.py <old-base> <old-tip> <new-base> <new-tip>
      старый диапазон old-base..old-tip против нового new-base..new-tip;
      дополнительно: совпадает ли diff(old-tip, new-tip) с diff(old-base, new-base),
      то есть поменялась ли ветка ровно на то, что пришло из базы.

  verify_moved.py --commits <sha>... -- <new-base> <new-tip>
      исходные коммиты списком (cherry-pick) против new-base..new-tip.
"""
from __future__ import annotations

import subprocess
import sys


def git(*args: str, stdin: str | None = None) -> str:
    return subprocess.run(
        ["git", *args], input=stdin, capture_output=True, text=True, check=True
    ).stdout


def commits(rev_args: list[str]) -> list[str]:
    out = git("rev-list", "--reverse", "--no-merges", *rev_args)
    return out.split()


def key(sha: str) -> tuple[str, str, str]:
    ad, an, s = git("show", "-s", "--format=%ad%x00%an%x00%s", "--date=raw", sha).rstrip("\n").split("\x00")
    return ad, an, s


def patch_id(sha: str) -> str:
    out = git("patch-id", "--stable", stdin=git("show", "-U0", "--format=", sha))
    return out.split()[0] if out else "EMPTY"


def diff_patch_id(a: str, b: str) -> str:
    out = git("patch-id", "--stable", stdin=git("diff", "-U0", a, b))
    return out.split()[0] if out else "EMPTY"


def short(sha: str) -> str:
    return git("rev-parse", "--short", sha).strip()


def main(argv: list[str]) -> int:
    whole_check = None
    if argv and argv[0] == "--commits":
        sep = argv.index("--")
        old = [git("rev-parse", c).strip() for c in argv[1:sep]]
        new_base, new_tip = argv[sep + 1 : sep + 3]
    elif len(argv) == 4:
        old_base, old_tip, new_base, new_tip = argv
        old = commits([f"{old_base}..{old_tip}"])
        whole_check = (old_base, old_tip, new_base, new_tip)
    else:
        print(__doc__)
        return 2

    new = commits([f"{new_base}..{new_tip}"])
    new_by_key = {key(c): c for c in new}
    matched_new = set()

    same, changed, dropped = [], [], []
    for o in old:
        n = new_by_key.get(key(o))
        if n is None:
            dropped.append(o)
            continue
        matched_new.add(n)
        (same if patch_id(o) == patch_id(n) else changed).append((o, n))
    extra = [c for c in new if c not in matched_new]

    merges = git("rev-list", "--merges", f"{new_base}..{new_tip}").split()

    print(f"Старых коммитов: {len(old)}, новых: {len(new)}")
    print(f"  патч совпал:   {len(same)}")
    print(f"  патч изменился: {len(changed)}")
    for o, n in changed:
        subj = key(o)[2]
        print(f"    {short(o)} -> {short(n)}  {subj}")
    print(f"  выпали (уже есть в базе или стали пустыми): {len(dropped)}")
    for o in dropped:
        print(f"    {short(o)}  {key(o)[2]}")
    print(f"  новые, без пары в старом диапазоне: {len(extra)}")
    for n in extra:
        print(f"    {short(n)}  {key(n)[2]}")
    print(f"  merge-коммитов в новом диапазоне: {len(merges)}")

    if whole_check:
        ob, ot, nb, nt = whole_check
        equal = diff_patch_id(ot, nt) == diff_patch_id(ob, nb)
        print(
            "Итоговое дерево: изменилось ровно на приход из базы"
            if equal
            else "Итоговое дерево: отличается от «старое + приход из базы» — ожидаемо только при конфликтах, смотри changed"
        )

    for o, n in changed:
        print(f"\n=== range-diff {short(o)} -> {short(n)} ===")
        print(git("range-diff", "--no-color", f"{o}^!", f"{n}^!"), end="")

    return 0 if not changed and not dropped and not extra else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
