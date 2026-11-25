#!/bin/bash
# Линт пакета devflow. Выход 1 при любой находке.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
fail=0
say() { echo "check: $*" >&2; fail=1; }

# 1. Манифесты
command -v claude >/dev/null || { echo "check: нет claude в PATH" >&2; exit 1; }
for target in . .claude-plugin/plugin.json; do
  claude plugin validate --strict "$target" >/dev/null 2>&1 || say "claude plugin validate --strict $target — ошибки: $(claude plugin validate --strict "$target" 2>&1 | tail -5)"
done

# 2. Привязки к машине и проектам
if [ -d skills ] || [ -d agents ] || [ -d commands ] || [ -d hooks ] || [ -d rules ]; then
  hits=$(grep -rn -E '/Users/|~/\.claude/hooks|~/\.claude/skills|~/\.claude/agents|~/\.claude/CLAUDE\.md' \
    skills agents commands hooks rules 2>/dev/null | grep -v '/tests/' | grep -v -E '^commands/setup\.md:.*~/\.claude/CLAUDE\.md' || true)
  [ -z "$hits" ] || say "привязки к машине/проектам:"$'\n'"$hits"
fi

# 2b. ${CLAUDE_PLUGIN_ROOT} подставляется только в SKILL.md, commands/, agents/, hooks.json — в справочниках и README он не работает
raw=$(grep -rln -F '${CLAUDE_PLUGIN_ROOT}' skills rules 2>/dev/null | grep -v -E '/SKILL\.md$' || true)
[ -z "$raw" ] || say "литерал \${CLAUDE_PLUGIN_ROOT} вне подставляемых текстов (используй \$DEVFLOW_ROOT):"$'\n'"$raw"

# 3. Версия = верхняя запись CHANGELOG
ver=$(python3 -c 'import json;print(json.load(open(".claude-plugin/plugin.json"))["version"])')
top=$(grep -m1 -E '^## ' CHANGELOG.md | sed -E 's/^## ([0-9.]+).*/\1/')
[ "$ver" = "$top" ] || say "version в plugin.json ($ver) ≠ верхней записи CHANGELOG ($top)"

# 4. hooks.json: каждый command существует и исполняемый
if [ -f hooks/hooks.json ]; then
  python3 - <<'PY' || fail=1
import json, os, re, sys
data = json.load(open('hooks/hooks.json'))
bad = []
for event, groups in data['hooks'].items():
    for group in groups:
        for hook in group['hooks']:
            path = re.sub(r'^"\$\{CLAUDE_PLUGIN_ROOT\}/(.+?)".*$', r'\1', hook['command'])
            if not os.path.isfile(path) or not os.access(path, os.X_OK):
                bad.append('%s: %s' % (event, path))
if bad:
    sys.stderr.write('check: hooks.json ссылается на отсутствующие или неисполняемые файлы:\n  ' + '\n  '.join(bad) + '\n')
    sys.exit(1)
PY
fi

# 5. Тесты хуков
[ -d hooks/tests ] && [ -z "${DEVFLOW_SKIP_HOOK_TESTS:-}" ] && { python3 -m unittest discover -s hooks/tests -t hooks >/dev/null 2>&1 || say "тесты хуков красные"; }

# 6. Общие правила влезают в лимит хука: session-start.py не должен обрезать текст
if [ -x hooks/session-start.py ]; then
  cut=$(echo '{}' | CLAUDE_PLUGIN_ROOT="$ROOT" CLAUDE_ENV_FILE= hooks/session-start.py 2>&1 >/dev/null || true)
  [ -z "$cut" ] || say "session-start.py: $cut"
fi

# 7. Тест release.sh (на временной копии; переменная защищает от рекурсии release.sh → check.sh → тест)
if [ -x tools/tests/test_release.sh ] && [ -z "${DEVFLOW_SKIP_RELEASE_TEST:-}" ]; then
  DEVFLOW_SKIP_RELEASE_TEST=1 tools/tests/test_release.sh >/dev/null 2>&1 || say "tools/tests/test_release.sh красный"
fi

# 8. Стандарт скиллов (docs/skill-standard.md): разделы, размер, русский description, ссылки на references/
if [ -x tools/skill-lint.py ] && [ -d skills ]; then
  lint=$(python3 tools/skill-lint.py skills 2>&1) || say "стандарт скиллов:"$'\n'"$lint"
fi

[ "$fail" = 0 ] && echo "check: OK"
exit $fail
