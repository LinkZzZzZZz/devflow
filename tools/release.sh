#!/bin/bash
# Выпуск версии плагина: проверка чистоты дерева, check.sh, bump version, CHANGELOG, коммит. Пуша нет.
# Использование: tools/release.sh <patch|minor|major> "<суть>" [<путь правки>…]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
level="${1:?уровень: patch | minor | major}"
summary="${2:?суть изменения одной строкой}"
shift 2
MANIFEST=.claude-plugin/plugin.json
# Пути правки — относительно корня репозитория: ./x, x/ и абсолютные внутри репозитория приводятся к одному виду.
paths=()
for p in "$@"; do
  case "$p" in
    "$ROOT"/*) p="${p#"$ROOT"/}";;
    /*) echo "release.sh: путь вне репозитория: $p" >&2; exit 1;;
  esac
  p="${p#./}"; p="${p%/}"
  paths+=("$p")
done

inside() {  # файл входит в переданные пути?
  local f="$1" p
  for p in ${paths[@]+"${paths[@]}"}; do
    [ "$f" = "$p" ] && return 0
    [[ "$f" == "$p/"* ]] && return 0
  done
  return 1
}
# porcelain -z: записи разделены NUL; у переименования (R/C) второе поле — старый путь, его пропускаем
dirty=$(git status --porcelain=v1 -z --untracked-files=all | python3 -c '
import sys
items = sys.stdin.buffer.read().split(b"\0")
out, skip = [], False
for item in items:
    if skip:
        skip = False
        continue
    if not item:
        continue
    code, path = item[:2].decode(), item[3:].decode("utf-8", "replace")
    out.append(path)
    if code[0] in "RC":
        skip = True
print("\n".join(out))
')
to_add=()
while IFS= read -r f; do
  [ -n "$f" ] || continue
  inside "$f" || { echo "release.sh: незакоммиченный файл вне правки: $f — закоммить отдельно или передай путь (plugin.json и CHANGELOG правит сам скрипт)" >&2; exit 1; }
  to_add+=("$f")
done <<<"$dirty"
git var GIT_COMMITTER_IDENT >/dev/null 2>&1 || { echo "release.sh: git не знает автора коммита — задай user.name и user.email" >&2; exit 1; }

# Снимок plugin.json и CHANGELOG: любой сбой после bump возвращает их и снимает индекс, правка остаётся в рабочем дереве.
SNAP=$(mktemp -d)
cp "$MANIFEST" "$SNAP/plugin.json"; cp CHANGELOG.md "$SNAP/CHANGELOG.md"
rollback() {
  cp "$SNAP/plugin.json" "$MANIFEST"; cp "$SNAP/CHANGELOG.md" CHANGELOG.md
  git reset -q -- "$MANIFEST" CHANGELOG.md ${paths[@]+"${paths[@]}"} 2>/dev/null || true
  echo "release.sh: сбой — версия и CHANGELOG откачены, правка на месте" >&2
}
trap 'rollback; rm -rf "$SNAP"; exit 1' ERR INT TERM

cur=$(python3 -c "import json;print(json.load(open('$MANIFEST'))['version'])")
IFS=. read -r a b c <<<"$cur"
case "$level" in
  patch) c=$((c+1));;
  minor) b=$((b+1)); c=0;;
  major) a=$((a+1)); b=0; c=0;;
  *) echo "release.sh: уровень $level не из patch|minor|major" >&2; exit 1;;
esac
new="$a.$b.$c"

python3 - "$MANIFEST" "$new" <<'PY'
import json, sys
path, version = sys.argv[1], sys.argv[2]
data = json.load(open(path, encoding='utf-8'))
data['version'] = version
with open(path, 'w', encoding='utf-8') as handle:
    json.dump(data, handle, ensure_ascii=False, indent=2)
    handle.write('\n')
PY

python3 - "$new" "$summary" ${paths[@]+"${paths[@]}"} <<'PY'
import datetime, sys
version, summary, paths = sys.argv[1], sys.argv[2], sys.argv[3:]
lines = open('CHANGELOG.md', encoding='utf-8').read().split('\n')
where = next(i for i, line in enumerate(lines) if line.startswith('## '))
entry = '- %s%s' % (summary, ' (%s)' % ', '.join(paths) if paths else '')
block = ['## %s — %s' % (version, datetime.date.today().isoformat()), entry, '']
open('CHANGELOG.md', 'w', encoding='utf-8').write('\n'.join(lines[:where] + block + lines[where:]))
PY

tools/check.sh || { echo "release.sh: check.sh красный" >&2; false; }

# Файл, удалённый уже в индексе, не существует ни в дереве, ни в индексе — git add на такой pathspec падает; пропускаем.
addable=()
for p in "$MANIFEST" CHANGELOG.md ${to_add[@]+"${to_add[@]}"}; do
  if [ -e "$p" ] || git ls-files --cached --error-unmatch -- "$p" >/dev/null 2>&1; then addable+=("$p"); fi
done
git add -A -- "${addable[@]}"
git commit -q -m "release: $new — $summary"
trap - ERR INT TERM
rm -rf "$SNAP"
echo "devflow $new: $summary ($(git rev-parse --short HEAD)) — установить: claude plugin update devflow@devflow"
