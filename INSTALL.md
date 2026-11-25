# Установка devflow

## Требования

Claude Code ≥ 2.1.236, git, python3, node ≥ 18, jq, GitHub CLI `gh` (залогинен: `gh auth login`),
YouTrack Cloud с постоянным токеном, плагин `superpowers` (`claude plugin install superpowers@claude-plugins-official`).

## 1. Подключить плагин

Из локального клона:

```bash
git clone git@github.com:LinkZzZzZZz/devflow.git ~/dev/devflow
claude plugin marketplace add ~/dev/devflow
claude plugin install devflow@devflow
```

Из git-репозитория — обновления по версии:

```bash
claude plugin marketplace add <git-URL>
claude plugin install devflow@devflow
```

Открой новую сессию. Проверка: `claude plugin details devflow@devflow` — 6 скиллов, 9 агентов, 7 команд, хуки.

**Один плагин процесса на проект.** Если на машине стоит другой плагин с тем же процессом, в проекте должен быть
включён только один: иначе хуки сработают дважды, а общие правила придут двумя блоками. Включение по проекту —
`enabledPlugins` в `.claude/settings.json` репозитория.

## 2. Машина

В любой сессии: `/devflow:setup`. Заполни `~/.claude/devflow/.env`: адрес YouTrack, постоянный токен, ключ проекта,
путь к рабочей копии плагина (`DEVFLOW_SRC`). Ключи описаны в `.env.example`.

**YouTrack MCP.** YouTrack Cloud сам отдаёт MCP-сервер по адресу `https://<instance>.youtrack.cloud/mcp`
(https://www.jetbrains.com/help/youtrack/cloud/model-context-protocol-server.html). Подключи его в своём терминале
постоянным токеном (как выпустить — https://www.jetbrains.com/help/youtrack/cloud/manage-permanent-token.html):

```bash
claude mcp add --scope user --transport http --header "Authorization: Bearer <постоянный токен>" youtrack https://<instance>.youtrack.cloud/mcp
```

Имя сервера — ровно `youtrack`: скилл `tracker` зовёт `mcp__youtrack__*`, хук `confirm-youtrack-write` спрашивает
подтверждение на инструменты записи (задачи, комментарии, поля, теги, связи, статьи, вложения, учёт работы).
Скачивать вложения MCP не умеет — это делает `skills/tracker/youtrack.mjs` с тем же токеном из `.env`.

**GitHub.** `gh auth login`. PR, ревью и ответы в треды идут через `gh`; хук показывает, что уйдёт, и спрашивает.

## 3. Проект

Сессия в основном каталоге репозитория (не worktree): `/devflow:setup`. Проверь черновик `.claude/workflow.md` —
особенно `github_repo`, базовую ветку, сторону репозитория (`side`: Бэк или Фронт) и команды проверок. Для PHP-проекта
добавится секция `## Код` со стековыми хуками (`strict_types`, `php_house_rules`).

**YouTrack-проект.** Один проект на бэк и фронт (ключ `T`, тикеты `T-123`) с полем «Сторона» (Бэк / Фронт / Оба).
Имя поля — `side_field` в `workflow.md`, если назовёте иначе.

**База знаний.** Чтобы включить карты модулей и гейт базы знаний, добавь в `workflow.md` секцию:

```markdown
## База знаний
- architecture_dir: `docs/architecture`
- architecture_ignore: `tests/**, migrations/**, fixtures/**`
```

и построй первую карту: `/devflow:map <модуль>` (например, `/devflow:map app/Services/Lessons`). Дальше карты сверяет `task-workflow` на шагах start и finish; пуш ветки тикета без карты по файлу ветки или с изменённым после `сверено` модулем гейт не засчитает (текст отказа называет, что сделать). Без секции гейт молчит.

Две оговорки. Карты плоские: гейт читает только `<architecture_dir>/*.md`, подкаталоги не смотрит; карта — файл с полем `module:` во фронтматтере. Тикет от ветки эпика: эпик-ветка должна быть запушена в `origin`, иначе её коммиты считаются коммитами тикета и гейт потребует карты на файлы эпика.

## Обновление

```bash
git -C ~/dev/devflow pull                      # для локального клона
claude plugin marketplace update devflow
claude plugin update devflow@devflow
```

и новая сессия. Что изменилось — `CHANGELOG.md`. Плагин ставится **копией** в `~/.claude/plugins/cache/devflow/devflow/<версия>/`,
поэтому после каждого релиза нужен `claude plugin update devflow@devflow` — `/devflow:rule` делает это сам.

## Правки плагина

Из сессии любого проекта: «добавь правило: …» (`/devflow:rule`) — правило ложится в репозиторий плагина
с bump версии и записью в CHANGELOG. Вручную: правка в клоне + `tools/release.sh patch "<суть>" <файлы>` + `claude plugin update devflow@devflow`.
Проверка пакета — `tools/check.sh`.
