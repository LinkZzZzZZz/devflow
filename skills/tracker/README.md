# tracker — YouTrack для Claude Code (только чтение)

Скилл плагина devflow: карточка тикета, комментарии, вложения и короткие списки «что в работе» / «что зависло»
по стороне Бэк/Фронт/Оба. Ничего не пишет в YouTrack.

## Из чего состоит

- **MCP-сервер YouTrack** — встроен в YouTrack Cloud (`https://<instance>.youtrack.cloud/mcp`). Через него скилл читает
  задачи, комментарии и поля. Подключение — `INSTALL.md` плагина, имя сервера должно быть `youtrack`.
- **`youtrack.mjs`** — маленький клиент на Node 18+ без зависимостей для того, чего в MCP нет: скачивания вложений.
  Ходит в REST API YouTrack с постоянным токеном.

## Настройка

1. Постоянный токен со scope YouTrack — по инструкции JetBrains: https://www.jetbrains.com/help/youtrack/cloud/manage-permanent-token.html
2. В `~/.claude/devflow/.env` (создаёт `/devflow:setup`):
   ```
   YOUTRACK_URL=https://<instance>.youtrack.cloud
   YOUTRACK_TOKEN=perm:...
   YOUTRACK_PROJECT=T
   ```
3. Проверка: `node <плагин>/skills/tracker/youtrack.mjs check` — должен вывести твой логин.

## Команды клиента

```bash
node youtrack.mjs check
node youtrack.mjs attachments --key T-12 --out docs/tasks/T-12/attachments
```

Вывод — JSON. Файл, который не скачался, приходит с полем `error` — скилл называет его пользователю.

Остальное (карточка, поиск, формы) — `SKILL.md` и `references/`.
