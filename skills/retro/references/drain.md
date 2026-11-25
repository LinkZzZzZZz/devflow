# retro — дренаж, сверка меток, метрики

Переменные между вызовами Bash не живут — задай заново: `F` (файл транскрипта, `transcript.md` шаг 1), `MAIN=$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")`, `M=~/.claude/projects/$(echo "$MAIN" | sed 's|[/._]|-|g')/memory` (`candidates.md`).

## Шаг 4. Дренаж и сверка меток

Выполняй всегда, даже если кандидатов ноль. Это третья ступень контура: память ловит, `CLAUDE.md` закрепляет, механика освобождает.

**Метки против реальности.** Для каждого правила с меткой `[хук]` — есть ли живой хук в `hooks.json` плагина, а для стекового — ещё и его ключ в поле `hooks` конфига? Для `[линтер]` — ловит ли это команда `pre_push` на самом деле?

```bash
jq -r '.hooks.PreToolUse[]? | (.matcher // "*") + " → " + (.hooks[].command)' "$DEVFLOW_ROOT/hooks/hooks.json"
grep -n -E '^- (pre_push|local_wip|migrations_dirs|serial_only|test_process|hooks):' "$MAIN/.claude/workflow.md"
```

Метка, обещающая защиту, которой нет, вреднее отсутствия метки: она создаёт ложное чувство безопасности. Такое расхождение — находка, о ней надо сказать. Мы на этом уже спотыкались: `[линтер]` стоял на `declare(strict_types=1)` и на границах deptrac, хотя `make check` не ловит ни то, ни другое.

**Обратный ход.** Правило, которое теперь ловит хук или линтер, из текста `CLAUDE.md` предложи убрать: механика не забывает, а место в бюджете освободится. Заменяй строкой-упоминанием в секции 5, а не удаляй смысл бесследно.

**Бюджет.** `wc -l "$MAIN/CLAUDE.md" "$DEVFLOW_ROOT/rules/general.md"` — лимит 150 строк для проектного, 80 для общих правил плагина. Приблизился — предложи, что вынести.


## Шаг 4а. Метрики сессии и калибровка критика

Числа за сессию (или N сессий), в сводку:

```bash
python3 - "$F" <<'PY'
import json,sys,re
agents=[];asst=[];users=[]
for line in open(sys.argv[1],errors="replace"):
    try: d=json.loads(line)
    except: continue
    c=(d.get("message") or {}).get("content")
    if d.get("type")=="assistant" and isinstance(c,list):
        for b in c:
            if b.get("type")=="tool_use" and b.get("name") in ("Agent","Task"):
                agents.append((b["input"].get("subagent_type") or "").split(":")[-1])
            if b.get("type")=="text": asst.append(b["text"])
    if d.get("type")=="user" and not d.get("isMeta") and isinstance(c,str): users.append(c)
ok=sum(1 for t in asst if re.match(r"^(ок|ok|хорошо|понял|принято|делаю)\b",t.strip().lower()))
print("агентов:",{a:agents.count(a) for a in set(agents)})
print("ответов «ок» без аргумента:",ok,"| реплик пользователя:",len(users))
PY
```

- **Решения пользователя без контраргумента** — ответы оркестратора, начинающиеся с согласия, на реплику с решением («делаем X», «добавь Y»): каждый — нарушение правила §1 `rules/general.md`; число в сводку, два и больше за сессию — кандидат на уточнение формулировки правила или триггеров `decision-critic`.
- **Утверждения без критика** — режимы, в которых `cycles.md` требовал `decision-critic` (fixes с `fix-N.md`, решения `design.md`, выводы `report.md`), а в транскрипте его вызова нет; Stop-хук блокирует только раз — остальное считает ретро.
- **Находки `[impl.blind-edit]`** — `grep -c '"rule_key": "impl.blind-edit"'` по журналу за неделю (`date` в строках); ноль за неделю при наличии architectural-тикетов — предложить снять п. 26 ревьюера и раздел «До первой правки» implementer: пункт, который ничего не ловит, — шум в брифе.
- **Калибровка критика.** `reports/critic-*.md` тикетов за неделю: ни одного `REVISE`/`BLOCK` — мандат сформулирован как «проверь» или критик зовётся для галочки; предложить проверить бриф (есть ли «потому что», не вложено ли мнение). Критик вызывался на чтение значения («в базе статус X») — сузить триггеры в шагах, где это случилось.
