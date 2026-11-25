# review-pr — повторная проверка после правок автора

## 5. Повторная проверка после правок автора

«Автор внёс правки, проверь»:

1. Треды ревью со статусом — GraphQL (в REST статуса «resolved» у комментария нет):
   ```bash
   gh api graphql -F owner='{owner}' -F name='{repo}' -F number=<n> -f query='
     query($owner: String!, $name: String!, $number: Int!) {
       repository(owner: $owner, name: $name) { pullRequest(number: $number) {
         headRefOid
         reviewThreads(first: 100) { nodes { id isResolved isOutdated path line
           comments(first: 50) { nodes { fullDatabaseId author { login } body createdAt } } } } } } }'
   ```
   Твои (пользователя) нерешённые треды — `isResolved: false`, первый комментарий его. Больше 100 тредов — пагинация `after`.
2. Для каждого — код по новому head-коммиту в месте треда: исправлено / частично / нет, с `path:line`.
3. Новый дифф с прошлого ревью: `git diff <head прошлого ревью>..origin/<head>` (head прошлого ревью — `commit_id` из файла `reports/pr-review-<n>.json` или `gh api repos/{owner}/{repo}/pulls/<n>/reviews` → `commit_id` твоего ревью) — прогони по нему шаг 2 из `review.md`.
4. Пользователю — список по тредам и новые находки в формате `SKILL.md` §4. Ответы в треды — только выбранное им: `gh api repos/{owner}/{repo}/pulls/<n>/comments/<fullDatabaseId первого комментария>/replies -f body='…'` (ответ на ответ API не принимает — только на первый комментарий треда); новые находки — новым ревью (шаг 4 `review.md`). Резолвь тред (`resolveReviewThread` с `threadId` = `id` треда), только если пользователь сказал.
