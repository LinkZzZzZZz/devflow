#!/bin/bash
# Проверяет release.sh на копии репозитория во временном каталоге.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
git clone -q "$ROOT" "$T/repo"; cd "$T/repo"
git config user.email t@t; git config user.name t
cp -R "$ROOT/tools/." tools/ && git add -A tools && { git commit -qm "tools из рабочего дерева" >/dev/null 2>&1 || true; }
mkdir -p "$T/claude-bin"; printf '#!/bin/bash\nexit 0\n' > "$T/claude-bin/claude"; chmod +x "$T/claude-bin/claude"
export PATH="$T/claude-bin:$PATH"   # claude plugin validate заглушен: репозиторий-копия без установки
export DEVFLOW_SKIP_RELEASE_TEST=1      # check.sh внутри release.sh не должен звать этот же тест
export DEVFLOW_SKIP_HOOK_TESTS=1        # тесты хуков гоняет внешний check.sh, внутри клона они только тратят время

ver() { python3 -c 'import json;print(json.load(open(".claude-plugin/plugin.json"))["version"])'; }
v0=$(ver)

# 1. грязный файл вне путей — отказ, версия не тронута
echo x >> README.md
if tools/release.sh patch "тест" rules/general.md 2>/dev/null; then echo "FAIL: прошёл с грязным README"; exit 1; fi
[ "$(ver)" = "$v0" ] || { echo "FAIL: версия изменилась при отказе"; exit 1; }
git checkout -q -- README.md

# 2. правка в переданном пути — bump, CHANGELOG, коммит
echo "- Тестовое правило. \`[слово]\`" >> rules/general.md
tools/release.sh patch "тестовое правило" rules/general.md >/dev/null
v1=$(ver)
[ "$v1" != "$v0" ] || { echo "FAIL: версия не поднята"; exit 1; }
grep -q "^## $v1 — " CHANGELOG.md || { echo "FAIL: нет записи CHANGELOG $v1"; exit 1; }
grep -q "тестовое правило" CHANGELOG.md || { echo "FAIL: нет сути в CHANGELOG"; exit 1; }
[ -z "$(git status --short)" ] || { echo "FAIL: дерево грязное после релиза"; exit 1; }
git log -1 --format=%s | grep -q "^release: $v1 — тестовое правило$" || { echo "FAIL: сообщение коммита: $(git log -1 --format=%s)"; exit 1; }
if git log -1 --format=%B | grep -qi 'co-authored\|generated'; then echo "FAIL: трейлер в коммите"; exit 1; fi

# 3. падение коммита (pre-commit exit 1) — версия и CHANGELOG откатываются, правка на месте
n=$(grep -c "^## " CHANGELOG.md)
mkdir -p .git/hooks && printf '#!/bin/bash\nexit 1\n' > .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit
echo "- Ещё правило. \`[слово]\`" >> rules/general.md
if tools/release.sh patch "сбой коммита" rules/general.md 2>/dev/null; then echo "FAIL: прошёл при падающем pre-commit"; exit 1; fi
[ "$(ver)" = "$v1" ] || { echo "FAIL: версия после сбоя коммита: $(ver), ожидалась $v1"; exit 1; }
[ "$(grep -c "^## " CHANGELOG.md)" = "$n" ] || { echo "FAIL: CHANGELOG изменился после сбоя коммита"; exit 1; }
git diff --quiet -- .claude-plugin/plugin.json CHANGELOG.md || { echo "FAIL: plugin.json/CHANGELOG грязные после сбоя"; exit 1; }
git diff --cached --quiet || { echo "FAIL: индекс не пуст после сбоя"; exit 1; }
grep -q "Ещё правило" rules/general.md || { echo "FAIL: правка пропала после сбоя"; exit 1; }
rm .git/hooks/pre-commit
tools/release.sh patch "после сбоя" rules/general.md >/dev/null || { echo "FAIL: повтор после сбоя не прошёл"; exit 1; }
[ "$(grep -c '^## ' CHANGELOG.md)" = "$((n + 1))" ] || { echo "FAIL: записей CHANGELOG после повтора: $(grep -c '^## ' CHANGELOG.md), ожидалось $((n + 1))"; exit 1; }
v1=$(ver)

# 4. формы путей: ./x, абсолютный внутри репозитория, переименование в индексе
echo "- Путь с точкой. \`[слово]\`" >> rules/general.md
tools/release.sh patch "путь с точкой" ./rules/general.md >/dev/null || { echo "FAIL: ./путь отвергнут"; exit 1; }
echo "- Абсолютный путь. \`[слово]\`" >> rules/general.md
tools/release.sh patch "абсолютный путь" "$PWD/rules/general.md" >/dev/null || { echo "FAIL: абсолютный путь отвергнут"; exit 1; }
git mv README.md README-x.md
tools/release.sh patch "переименование" README.md README-x.md >/dev/null || { echo "FAIL: переименование не принято"; exit 1; }
[ -z "$(git status --short)" ] || { echo "FAIL: дерево грязное после переименования"; exit 1; }
git rm -q README-x.md
tools/release.sh patch "удаление в индексе" README-x.md >/dev/null || { echo "FAIL: staged-удаление не принято"; exit 1; }
[ -z "$(git status --short)" ] || { echo "FAIL: дерево грязное после удаления"; exit 1; }

# 5. minor и major без путей
tools/release.sh minor "новый режим" >/dev/null; v2=$(ver)
tools/release.sh major "новый формат" >/dev/null; v3=$(ver)
echo "$v0 → $v1 → $v2 → $v3"
[[ "$v1" == *.*.* && "$v2" == *.*.0 && "$v3" == *.0.0 ]] || { echo "FAIL: схема версий"; exit 1; }
echo "release.sh: OK"
