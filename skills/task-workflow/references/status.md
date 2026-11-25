# status — статус тикета

Триггеры: «что по статусу <KEY>», «мы сделали <KEY> или нет».

1. Каталог тикета — через Bash по `catalog.md` (`tasks_dir`, `epics_dir`, затем `legacy_dirs`), не через `Glob`.
2. Прочитать `spec.md`, `tasks.md`/`plan.md`, `reports/` (в legacy-каталоге — что есть).
3. Фактическое состояние:
   - ветка: `git fetch origin && git log --oneline origin/<base>..origin/<KEY>` (или локальная);
   - влита ли: `git merge-base --is-ancestor origin/<KEY> origin/<base>`;
   - PR: `gh pr list --head <KEY> --state all --json number,state,url,mergeStateStatus`, проверки CI — `gh pr checks <KEY>`;
   - статус в YouTrack: `mcp__youtrack__get_issue` (id = `<KEY>`) → поле `status_field` из `workflow.md` (по умолчанию `State`); у подзадачи стороны — ещё статус общей задачи и соседней подзадачи (`subtask of: <ключ общей>`).
4. Краткая сводка: что сделано, что осталось, где лежит, PR и его состояние.

Отвечать по фактам из файлов, git и трекера, а не по памяти о сессии.
