# Changelog

## 0.2.0 — 2026-11-25
- стороны back/front без «Оба»: общая задача фичи и подзадачи сторон, поле статуса status_field (skills/tracker, skills/task-workflow/references/new-ticket.md, skills/task-workflow/references/status.md, skills/task-workflow/references/workflow-template.md, INSTALL.md)

## 0.1.1 — 2026-11-25
- заголовок авторизации после имени и адреса в команде claude mcp add (INSTALL, setup)

## 0.1.0 — 2026-11-25
- первая версия: форк qtim-workflow 1.16.3 (коммит 4da8726) под YouTrack и GitHub (план — docs/plan.md)
- трекер — YouTrack: скилл tracker читает тикет через MCP-сервер YouTrack, вложения скачивает клиент skills/tracker/youtrack.mjs (REST, постоянный токен); хук confirm-youtrack-write — подтверждение MCP-инструментов записи; поле стороны Бэк/Фронт/Оба в workflow.md
- git-хостинг — GitHub через gh: отправка ветки создаёт PR (gh pr create) после «да» на заголовок и описание; review-pr и resolve-pr-comments вместо review-mr и resolve-mr-comments; guard-bash-rules подтверждает запись через gh и отклоняет PR без показанного текста и запись в API GitHub в обход gh; признаки gh:review и gh:reply в cycle-check (hooks/lib_gh.py)
- переименование: плагин и маркетплейс devflow, переменные DEVFLOW_ROOT/ENV/SRC/SKIP_*, каталог ~/.claude/devflow/, блок «Общие правила devflow», команды /sync-prs и /learn-pr
- убрано: учёт времени (day-track, track-time), мессенджер и его MCP, стенды в branch-ops, хук block-orchid-tests, рабочие документы и сид журнала находок
