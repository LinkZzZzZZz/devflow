---
description: Отправить ветку задачи — сквош, коммит от текущего времени, проверки, пуш, PR, проверки CI
disable-model-invocation: true
argument-hint: "[ветка или T-N] [название коммита]"
---

Используй скилл branch-ops, операция D («Отправка ветки задачи», справочник `${CLAUDE_PLUGIN_ROOT}/skills/branch-ops/references/ship.md`), для: $ARGUMENTS

Ветка не указана — текущая ветка этого worktree. Эта команда и есть команда на пуш: подтверждение даст хук guard-git-push. PR создаётся (`gh pr create`) после «да» на показанные заголовок и описание.
