---
description: Установить devflow на машину (.env, gh, MCP YouTrack) и подключить проект (.claude/workflow.md, worktree-links, docs/tasks)
disable-model-invocation: true
argument-hint: "[пусто — машина и текущий проект]"
---

Настрой devflow. Две части: машина (всегда), проект (если текущий каталог — git-репозиторий). Ничего не перезаписывай без «ок»; каждую правку показывай до записи.

## Машина

1. Требования — один вызов, вывод покажи целиком:
```bash
for t in git python3 node jq gh claude; do printf '%-8s %s\n' "$t" "$(command -v $t >/dev/null && { $t --version 2>&1 | head -1; } || echo 'НЕТ')"; done
claude plugin list 2>/dev/null | grep -i superpowers || echo "superpowers: НЕ УСТАНОВЛЕН (нужен для writing-plans на architectural-тикетах)"
```
`node` ниже 18 или чего-то нет — назови, что поставить, и остановись.

2. Креды: `ls -la ~/.claude/devflow/.env 2>/dev/null`. Нет файла:
```bash
mkdir -p ~/.claude/devflow && cp "${CLAUDE_PLUGIN_ROOT}/.env.example" ~/.claude/devflow/.env && chmod 600 ~/.claude/devflow/.env
```
и перечисли ключи, которые надо заполнить руками (`grep -E '^[A-Z_]+=$' ~/.claude/devflow/.env`). Значения токенов не спрашивай и не печатай. Есть файл — проверь, что в нём есть все ключи из `${CLAUDE_PLUGIN_ROOT}/.env.example`; недостающие допиши пустыми и назови.

3. GitHub: `gh auth status`. Не залогинен — скажи пользователю выполнить `gh auth login` самому (вход — в браузере, токен ты не видишь) и остановись на этом пункте.

4. YouTrack:
   - токен для вложений: `node "${CLAUDE_PLUGIN_ROOT}/skills/tracker/youtrack.mjs" check` — выводит логин; ошибка — назови её (нет ключей в `.env`, 401 — токен не тот);
   - MCP-сервер: `claude mcp list 2>/dev/null | grep -i youtrack`. Нет — дай пользователю команду для его терминала (токен подставит сам, в чат не присылает):
     ```
     claude mcp add --scope user --transport http --header "Authorization: Bearer <постоянный токен>" youtrack https://<instance>.youtrack.cloud/mcp
     ```
     Имя сервера — ровно `youtrack`: под него настроены скилл `tracker` и хук подтверждения записи `confirm-youtrack-write`. Сам команду не запускай.

5. Общие правила подаёт SessionStart-хук devflow блоком «Общие правила devflow». `~/.claude/CLAUDE.md` не трогай. Если в нём есть требование другого блока правил («если в контексте нет блока …») — скажи пользователю, что в проектах, где включён только devflow, это требование сработает ложно, и предложи строку в `CLAUDE.md` проекта: «В этом проекте общие правила подаёт плагин devflow (блок «Общие правила devflow»)».

6. Двойные хуки — старые копии хуков плагина в `~/.claude/settings.json` (по именам файлов из `hooks.json`, расширение не важно):
```bash
python3 - "${CLAUDE_PLUGIN_ROOT}/hooks/hooks.json" ~/.claude/settings.json <<'PY'
import json, os, sys
plugin = json.load(open(sys.argv[1]))
stems = {os.path.splitext(os.path.basename(h['command'].strip('"').split('"')[0]))[0]
         for groups in plugin['hooks'].values() for g in groups for h in g['hooks']}
try: settings = json.load(open(sys.argv[2]))
except OSError: sys.exit(0)
for event, groups in (settings.get('hooks') or {}).items():
    for g in groups:
        for h in g.get('hooks', []):
            cmd = h.get('command') or ''
            if os.path.splitext(os.path.basename(cmd.split()[0] if cmd.split() else ''))[0] in stems:
                print('%s: %s' % (event, cmd))
PY
```
Вывод не пуст — эти хуки продублируют хуки плагина. Покажи список и предложи удаление (бэкап `settings.json` рядом); выполняй после «ок»:
```bash
cp ~/.claude/settings.json ~/.claude/settings.json.bak-devflow && python3 - "${CLAUDE_PLUGIN_ROOT}/hooks/hooks.json" ~/.claude/settings.json <<'PY'
import json, os, sys
plugin = json.load(open(sys.argv[1]))
stems = {os.path.splitext(os.path.basename(h['command'].strip('"').split('"')[0]))[0]
         for groups in plugin['hooks'].values() for g in groups for h in g['hooks']}
path = sys.argv[2]; settings = json.load(open(path))
def dup(h):
    cmd = (h.get('command') or '').split()
    return bool(cmd) and os.path.splitext(os.path.basename(cmd[0]))[0] in stems
hooks = {}
for event, groups in (settings.get('hooks') or {}).items():
    kept = [dict(g, hooks=[h for h in g.get('hooks', []) if not dup(h)]) for g in groups]
    kept = [g for g in kept if g['hooks']]
    if kept: hooks[event] = kept
if hooks: settings['hooks'] = hooks
else: settings.pop('hooks', None)
json.dump(settings, open(path, 'w'), ensure_ascii=False, indent=2); open(path, 'a').write('\n')
PY
```

## Проект

Пропусти, если `git rev-parse --show-toplevel` даёт ошибку. Если `git rev-parse --git-common-dir` указывает не в `.git` текущего каталога — это worktree: откажись и попроси открыть сессию в основном каталоге (из worktree `.claude/` основного репозитория не правится).

1. `.claude/workflow.md` есть — прочитай, доложи, что секции на месте (в т.ч. есть ли `## Код`, `tracker: youtrack`, `github_repo`), ничего не меняй. Нет — собери черновик по `${CLAUDE_PLUGIN_ROOT}/skills/task-workflow/references/workflow-template.md`: `git branch -r`, `git remote get-url origin` (→ `github_repo`), `.github/workflows/*.yml`, `package.json`/`composer.json`/`Makefile`, `CLAUDE.md`. Базовую ветку, сторону репозитория (`side`) и команды проверок не угадывай — поля, которые не вывел из файлов, оставь с пометкой `<уточнить>` и спроси. Покажи целиком, запиши после «ок».
2. Есть `composer.json` и нет секции `## Код` — предложи:
```
## Код
- hooks: `strict_types, php_house_rules`
```
Ключи: `strict_types` — Write/Edit PHP без `declare(strict_types=1)` отклоняется; `php_house_rules` — после правки PHP хук перечисляет нестрогие сравнения, не-Yoda, прозу в PHPDoc и комментариях. Запиши после «ок».
3. `.claude/worktree-links`: должен содержать строки `.claude/workflow.md`, `docs/tasks`, `docs/epics` (по одной на строку); недостающие допиши, существующие не трогай.
4. `mkdir -p docs/tasks docs/epics`; скажи, попадают ли они под `.gitignore` (`git check-ignore -q docs/tasks && echo ignored || echo tracked`) — не меняй.
5. Другой плагин процесса включён в проекте вместе с devflow (`claude plugin list`, `enabledPlugins` в `.claude/settings.json` проекта) — скажи: хуки сработают дважды, правила придут двумя блоками; выключать — решение пользователя, сам не меняй.
6. Итог: что создано, что осталось заполнить руками, и напоминание: новые скиллы и агенты видны только в новой сессии.
