# catalog — каталог тикета

`<tasks_dir>/<KEY>/` или `<epics_dir>/<эпик>/tickets/<KEY>/`. Каталог в `.gitignore` — `Glob`/`Grep` его не видят. Ищи только так:

```bash
ls -d <tasks_dir>/<KEY> 2>/dev/null || find <epics_dir> -maxdepth 3 -type d -name '<KEY>' 2>/dev/null
```

Не нашёл — проверь, не тикет ли это эпика без каталога (первый заход): `grep -l '<KEY>' <epics_dir>/*/tasks.md 2>/dev/null` (через Bash — `Grep` gitignored-каталоги не видит). Нашёлся — тикет эпика: каталог `<epics_dir>/<эпик>/tickets/<KEY>/`, и до любой работы прочитать раздел эпика (`references/epics.md`, «Тикет эпика: вход»). Не нашёлся — проверь `legacy_dirs` (там старые тикеты в произвольной раскладке: читай как есть, новые файлы пиши уже в `<tasks_dir>/<KEY>/`).

```
<KEY>/
  spec.md            постановка, размер, сценарии приёмки, вопросы, кэш ссылки на PR
  map.md             карта области (system-mapper area): что затрагивает, было → стало
  tasks.md           small/bounded: чек-лист подзадач
  design.md, plan.md architectural: решения и риски, план
  estimate.md        режим оценки
  report.md, research/notes/  режим research: единственный отчёт и заметки субагентов
  MANUAL_TESTING.md  выход black-box-tester (адресат — агент)
  attachments/       вложения из трекера
  reports/ notes.md  report-N.md  fix-N.md  test-report.md  review-N-rM.md  review-fix-N-rM.md  feature-map.md
           spec-critique.md  branch-review.md  security-review.md  db-review.md  critic-N.md
```
