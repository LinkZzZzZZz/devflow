#!/usr/bin/env bash
# Что потеряется, если ветку <old> заменить на <new> force-push'ем.
#   lost_commits.sh <old> <new> [limit]
# 1) обычные коммиты из <old>, которых в <new> нет ни по SHA, ни по содержимому (patch-id);
# 2) merge-коммиты из <old>, недостижимые из <new> — их собственные изменения
#    (разрешения конфликтов) сравнить нельзя, смотреть вручную.
set -euo pipefail

old=${1:?old ref}
new=${2:?new ref}
limit=${3:-40}

lost=$(git log --left-only --cherry-pick --no-merges --format='%h %ad %an: %s' --date=short "$old...$new")
merges=$(git log --merges --format='%h %ad %an: %s' --date=short "$new..$old")

count() { [ -z "$1" ] && echo 0 || printf '%s\n' "$1" | wc -l | tr -d ' '; }

echo "Коммиты только в $old (нет в $new по содержимому): $(count "$lost")"
[ -n "$lost" ] && printf '%s\n' "$lost" | head -n "$limit"
echo
echo "Merge-коммиты только в $old: $(count "$merges")"
[ -n "$merges" ] && printf '%s\n' "$merges" | head -n "$limit"

[ -z "$lost" ] && [ -z "$merges" ]
