# План: плагин devflow — форк qtim-workflow под YouTrack и GitHub

Источник: `~/dev/qtim-workflow`, версия 1.16.3, коммит `4da8726` (только чтение).
Цель: `~/dev/devflow` (репозиторий `LinkZzZzZZz/devflow`, ветка `main`, пока без коммитов).
Первая версия devflow — `0.1.0`; CHANGELOG начинается записью «форк qtim-workflow 1.16.3 (4da8726)».

## 0. Что нужно решить до старта

1. **Ключ задач YouTrack — `T`** (тикеты `T-123`, решение пользователя 2026-11-25). Хуки принимают (ветка тикета — `[A-Z][A-Z0-9]*-\d+`).
2. **Как подключать MCP YouTrack.** Предлагаю **не класть его в `plugin.json`**: у сервера свой адрес на каждую инсталляцию и личный токен. Каждый подключает сам одной командой из документации JetBrains (`claude mcp add --header "Authorization: Bearer <token>" --transport http youtrack https://<instance>.youtrack.cloud/mcp`), INSTALL это описывает. Хук подтверждения ловит оба варианта имени: `mcp__youtrack__*` и `mcp__plugin_devflow_youtrack__*`.
3. **Отчёты `tracker`.** У qtim-workflow это дейлик, дайджест, загрузка и флаги по часам на команду. Для двух человек без учёта часов предлагаю оставить три вещи: карточка тикета, вложения, «что в работе / что зависло» по стороне Бэк/Фронт/Оба. Дейлик, загрузку и аналитику по часам — убрать.

План и варианты п. 2 (без MCP в `plugin.json`) и п. 3 (урезанный `tracker`) согласованы пользователем 2026-11-25.

## 1. Переименования (по всему дереву)

| Было | Стало |
|---|---|
| плагин `qtim-workflow`, маркетплейс `qtim` | `devflow`, маркетплейс `devflow` (установка `devflow@devflow`) |
| `QTIM_WORKFLOW_ROOT` / `_ENV` / `_SRC` | `DEVFLOW_ROOT` / `DEVFLOW_ENV` / `DEVFLOW_SRC` |
| `QTIM_SKIP_HOOK_TESTS`, `QTIM_SKIP_RELEASE_TEST` | `DEVFLOW_SKIP_HOOK_TESTS`, `DEVFLOW_SKIP_RELEASE_TEST` |
| `~/.claude/qtim-workflow/` (`.env`, `voice.md`, `review-findings.jsonl`) | `~/.claude/devflow/` |
| `~/dev/qtim-workflow` (путь по умолчанию в `lib_env.py`) | `~/dev/devflow` |
| блок «Общие правила qtim-workflow» в `session-start.py` | «Общие правила devflow» |
| `qtim-workflow:<агент>` в текстах, регэкспах хуков и тестах | `devflow:<агент>` |
| `/qtim-workflow:<команда>` | `/devflow:<команда>` |
| автор `Egor Artamonov <artamanov@qtim.ru>` | `Egor Artamonov`, без почты |
| `license: UNLICENSED`, keywords `gitlab`, `yandex-tracker` | keywords `github`, `youtrack`; лицензию оставлю `UNLICENSED`, если не скажешь иначе |

Скиллы и команды про MR переименовываются под словарь GitHub: `review-mr` → `review-pr`, `resolve-mr-comments` → `resolve-pr-comments`, `/sync-mrs` → `/sync-prs`, `/learn-mr` → `/learn-pr`, «MR» → «PR» в текстах. Файл проекта `.claude/workflow.md` и служебные файлы в `.git` (`claude-make-check-trees`, `claude-tests.lock` и т. п.) оставляю как есть: оба плагина в одном проекте не включаются.

## 2. Состав: что куда

### 2.1 Копируются как есть (меняются только имена из §1)

- `agents/` — все 9 агентов. В `quality-reviewer`, `decision-critic` «MR» становится «PR», в `black-box-tester`/`fact-checker`/`system-mapper` «стенд» означает локальный стек, это не трогаю.
- `hooks/`: `block-manual-migration.py`, `branch-files.py`, `cycle-check.py` (правки по §2.2), `design-critique-gate.py`, `guard-local-wip.py`, `guard-worktree-writes.py`, `knowledge-base-check.py`, `lib_git_cmd.py`, `lib_hook.py`, `lib_workflow.py`, `lib_env.py`, `pre-push-check.py`, `record-make-check.py`, `worktree-links.py`, `session-start.py`, `php-house-rules.py`, `require-strict-types.py`.
- Тесты к ним в `hooks/tests/` — все, кроме перечисленных в §2.3 и §2.2.
- `skills/retro/` целиком; `skills/task-workflow/` — каркас и справочники без трекера и GitLab (`brief.md`, `catalog.md`, `cycles.md`, `epics.md`, `finish.md`, `implement.md`, `research.md`, `show.md`, `start.md`, `team-report.md`, `worktree.md`, `scripts/brief-rules.py`); места с трекером и MR — по §2.2.
- `skills/branch-ops/`: `protocol.md`, `rebase.md`, `conflicts.md`, `scripts/verify_moved.py`, `scripts/lost_commits.sh`.
- `skills/resolve-mr-comments/references/learn.md` (журнал без привязки к GitLab, меняются пути и словарь).
- `commands/map.md`, `commands/retro.md`.
- `docs/skill-standard.md`, `tools/check.sh`, `tools/release.sh`, `tools/skill-lint.py`, `tools/tests/test_release.sh`, `.gitignore`.

### 2.2 Переписываются

| Файл | Как |
|---|---|
| `.claude-plugin/plugin.json` | имя, версия 0.1.0, описание без трекера Яндекса, GitLab и учёта времени; без `mcpServers`; `dependencies: superpowers` оставить |
| `.claude-plugin/marketplace.json` | маркетплейс `devflow`, владелец без почты |
| `.env.example` | `YOUTRACK_URL`, `YOUTRACK_TOKEN` (постоянный токен, нужен для скачивания вложений, п. YouTrack), `YOUTRACK_PROJECT`, `DEVFLOW_SRC`; ключи Яндекса, `DAY_TRACK_*`, `TIME_USERNAME` убрать |
| `hooks/hooks.json` | убрать `block-orchid-tests`, `confirm-time-write`, `confirm-gitlab-write`; добавить `confirm-youtrack-write` (матчер — меняющие данные инструменты MCP YouTrack) и проверку записи в GitHub в Bash (`gh`) |
| `hooks/guard-bash-rules.py` | проверку `glab`/`curl /api/v4` заменить на `gh`: `gh pr create` — ask с заголовком, базой, веткой, ревьюерами и длиной описания (аналог `confirm-gitlab-write` для `create_merge_request`; у GitHub это единственный путь создать PR, поэтому не deny); `gh pr create --fill`/без `--title` и `--body-file` — deny: заголовок и описание пользователь должен увидеть до создания; `gh pr comment/review/merge/edit/close/ready`, `gh issue create/comment/edit/close`, `gh api` с методом POST/PATCH/PUT/DELETE или с полями `-f/-F/--input` — ask с тем, что уйдёт; `curl` к `api.github.com` на запись — deny. Регэкспы ролей агентов — `devflow:` |
| `hooks/guard-git-push.py` | GitLab-специфичный отказ на `-o merge_request.*` убрать (у GitHub нет создания PR через push-option); остальное без изменений |
| `hooks/confirm-youtrack-write.py` (новый, на основе `confirm-gitlab-write.py`) | ask на `create_issue`, `create_draft_issue`, `update_draft_issue`, `publish_draft_issue`, `update_issue`, `change_issue_assignee`, `add_issue_comment`, `manage_issue_tags`, `link_issues`, `create_article`, `update_article`, `add_attachment`, `log_work`, `update_work_item`; в вопросе — ключ задачи и текст (комментарий, поля) |
| `hooks/cycle-check.py` + `cycles.md` | признаки review/resolve сейчас — вызовы `mcp__gitlab__create_draft_note`; на GitHub ревью публикуется через `gh api`. Добавить признак публикации ревью и ответа в тред по команде `gh` (засчитывается и без каталога тикета) и переписать машинные строки `review-pr`, `resolve-pr-comments`, `finish` |
| `hooks/tests/test_bypasses.py`, `test_fail_closed.py`, `test_agent_roles.py`, `test_cycle_check.py`, `test_session_start.py`, `test_lib_env.py`, `test_stack_hooks.py` | под новые имена, `gh` вместо `glab`, YouTrack вместо GitLab; из `test_stack_hooks.py` убрать orchid; новый `test_youtrack_write.py`, `test_github_write.py` |
| `rules/general.md` | §0 п. 3: `[хук]` для GitHub (`gh`, API) и YouTrack (MCP); §2: PR создаётся только шагом отправки через `gh pr create` после «да»; §4: трекер — YouTrack, вложения — `tracker attachments`; стенды убрать. Влезть в лимит 9500 символов (`check.sh` п. 6) |
| `skills/tracker/` | новый `SKILL.md` + маленький клиент `youtrack.mjs` вместо `tracker.mjs` (402 строки API Яндекса): карточка и комментарии — MCP `get_issue`/`get_issue_comments`; поиск «в работе / зависло» — MCP `search_issues` с запросом YouTrack; вложения — клиент по REST с `YOUTRACK_TOKEN` (у MCP нет инструмента на скачивание файлов). `README.md`, `references/commands.md`, `forms.md` переписать под это |
| `skills/task-workflow/SKILL.md` и `new-ticket.md`, `fixes.md`, `estimate.md`, `research.md`, `status.md`, `start.md` | чтение тикета, вложений и статуса — через `tracker` (MCP YouTrack + клиент вложений); поле «Сторона»; `## MR` в `spec.md` → `## PR`; статус PR — `gh pr view`/`gh pr checks` |
| `skills/task-workflow/references/workflow-template.md` | `tracker: youtrack`, `project`, `url: https://<instance>.youtrack.cloud/issue/{KEY}`, поле стороны; `gitlab_project` → `github_repo: <org/repo>`; секции «Стенды», «Time» убрать; «Ответы в MR» → «Ответы в PR» |
| `skills/branch-ops/SKILL.md`, `ship.md`, `sync-mrs.md` → `sync-prs.md`, `config-template.md` | операции A (ребейз), D (отправка), E (синхронизация); B/C (стенды) удалить. D: поиск PR — `gh pr list --head <ветка>`, создание — `gh pr create --base --head --title --body-file --reviewer` после «да» на заголовок и описание (хук спросит подтверждение ещё раз), проверки — `gh pr checks`. Ревьюер — из тикета YouTrack, сопоставление с логином GitHub спрашивать, если не очевидно. E: `gh pr list --author @me`, `mergeable`/`mergeStateStatus` |
| `skills/review-mr` → `skills/review-pr` | контекст `gh pr view --json`, дифф `gh pr diff`; находки — одним ревью через `gh api .../pulls/{n}/reviews` с массивом комментариев после «публикуй N, M»; повторная проверка — треды через GraphQL `reviewThreads`. Точные параметры API сверяю с документацией GitHub на этапе, не по памяти |
| `skills/resolve-mr-comments` → `skills/resolve-pr-comments` | треды и их статус «resolved» — GraphQL `reviewThreads` (в REST статуса нет — проверю по доке на этапе); ответы — reply на комментарий ревью одним заходом после «ок»; резолв — только по слову пользователя |
| `commands/ship.md`, `sync-mrs.md` → `sync-prs.md`, `learn-mr.md` → `learn-pr.md` | словарь PR и `gh` |
| `commands/setup.md` | `~/.claude/devflow/.env`; проверка `gh auth status` и MCP YouTrack (`claude mcp list`), а не GitLab; запрет `glab mr create` в `permissions.deny` → `Bash(gh pr create *)` предложить как опцию; секция `## Код` без `no_orchid_unit_tests`. Пункт про сжатие `~/.claude/CLAUDE.md` убрать — этот файл общий с рабочим плагином |
| `commands/rule.md` | `DEVFLOW_SRC`, `/devflow:rule`, `claude plugin update devflow@devflow`; у devflow есть remote на GitHub — после релиза пуш не делать без просьбы |
| `README.md`, `INSTALL.md` | заново под состав devflow: требования (`gh`, токен YouTrack), подключение MCP YouTrack, поле «Сторона», включение плагина в проекте |
| `CHANGELOG.md` | новый, первая запись `0.1.0` с пометкой происхождения форка (единственное место со словом qtim) |

### 2.3 Выкидываются

- Учёт времени и мессенджер: `skills/time/`, `skills/day-track/`, `skills/track-time/`, `tools/time-auth.py`, `hooks/confirm-time-write.py`, `hooks/tests/test_time_auth.py`, `test_time_write.py`, `mcpServers` в `plugin.json`.
- GitLab: `hooks/confirm-gitlab-write.py` (его тест — в `test_fail_closed.py`, заменяется на YouTrack/GitHub).
- Стенды: `skills/branch-ops/references/stand.md`, `rebuild.md`.
- Orchid: `hooks/block-orchid-tests.py` и его тесты — в `tutor-back` нет `orchid/platform` (проверил `composer.json`).
- Рабочая история: `docs/audit-2026-10-20.md`, `docs/findings.jsonl`, `docs/research/`, `docs/superpowers/` — это находки и планы по рабочим проектам.
- `tracker.mjs` (заменяется, §2.2).
- `skills/resolve-mr-comments/scripts/seed-findings.py` и `hooks/tests/test_seed_findings.py` — разовый сид журнала из `docs/findings.jsonl`; датасет выкинут, скрипт ни один скилл не вызывает (решено при сборке 2026-11-25).

## 3. Этапы и проверка каждого

После **каждого** этапа — проверка рабочего плагина (команды и вывод в отчёт этапа):

```bash
git -C ~/dev/qtim-workflow status --short          # пусто
git -C ~/dev/qtim-workflow rev-parse --short HEAD  # 4da8726
grep '"version"' ~/dev/qtim-workflow/.claude-plugin/plugin.json   # 1.16.3
```

Копирование — `git -C ~/dev/qtim-workflow archive 4da8726 <пути> | tar -x -C ~/dev/devflow`: берётся ровно закоммиченное, без `.claude/worktrees/` и `__pycache__`, в рабочую копию источника ничего не пишется.

| № | Этап | Готово, когда |
|---|---|---|
| 1 | Ядро: копирование файлов §2.1 и §2.2 (переписываемые — как заготовки), без §2.3 | список файлов devflow совпадает с планом (`find`), в devflow нет файлов §2.3 |
| 2 | Переименование §1 | `grep -rn 'QTIM\|qtim-workflow\|~/.claude/qtim' ~/dev/devflow` находит только ещё не переписанные места GitLab/трекера; `python3 -m unittest discover -s hooks/tests -t hooks` — зелёные все тесты, кроме помеченных к переписке на этапах 4–5 (список в отчёте) |
| 3 | Тесты хуков | полный прогон `hooks/tests` зелёный; вывод `Ran N tests … OK` в отчёте |
| 4 | YouTrack: `tracker`, `confirm-youtrack-write`, места в `task-workflow`, шаблон `workflow.md`, `.env.example` | тесты нового хука зелёные; клиент вложений проверен на живом тикете, если дашь инстанс и токен в `~/.claude/devflow/.env` (иначе — «не проверено вживую» в отчёте); REST-адреса вложений сверены с документацией JetBrains |
| 5 | GitHub: `guard-bash-rules`, `cycle-check` + `cycles.md`, `branch-ops`, `review-pr`, `resolve-pr-comments`, команды | тесты `gh`-проверок и циклов зелёные; параметры `gh`/API сверены с документацией GitHub (ссылки в отчёте); на GitHub ничего не пишется |
| 6 | `setup`, `INSTALL`, `README`, `rules/general.md`, CHANGELOG | `tools/check.sh` — `check: OK` (в нём `claude plugin validate --strict`, линт скиллов, лимит правил, тесты); установка плагина не делается |
| 7 | Финальная проверка | `grep -rniI 'qtim\|yandex\|яндекс\|gitlab\|glab\|time-messenger' ~/dev/devflow --exclude-dir=.git` — только строка происхождения в `CHANGELOG.md`; тесты зелёные; проверка рабочего плагина — три команды выше |

Не делаю без отдельной просьбы: установку devflow в Claude Code, включение/выключение плагинов в проектах, коммиты и пуш в `LinkZzZzZZz/devflow`.

## 4. Риски

- **Оба плагина в одной сессии.** Если в проекте включены и qtim-workflow, и devflow, хуки сработают дважды, а правила придут двумя блоками. В проектах UrokKit нужно выключить qtim-workflow (следующий шаг, не в этой сессии).
- **`~/.claude/CLAUDE.md` требует блок «Общие правила qtim-workflow».** В проекте только с devflow агент будет предупреждать, что плагин не загружен. Менять этот файл нельзя. Решение — на шаге переноса: строка в `CLAUDE.md` проекта, что в UrokKit вместо qtim-workflow работает devflow.
- **Публикация ревью через `gh api`** обходит интерактивный «черновик → публикация» GitLab. Защита — хук ask с числом комментариев и текстом перед отправкой и правило «публикую только выбранное».
- **Нет инструмента MCP на скачивание вложений.** Поэтому нужен постоянный токен в `.env`. Без него `tracker attachments` не работает: клиент скажет об этом прямо, ошибку не проглотит.
