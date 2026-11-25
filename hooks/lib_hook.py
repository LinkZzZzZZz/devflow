"""Общее для PreToolUse-хуков: ответ в JSON и fail-closed обёртка.

Claude Code блокирует действие только при exit 2 или permissionDecision deny/ask; любой другой сбой хука
(исключение, битый stdin) считается «неблокирующей ошибкой», и действие проходит. Политика, которая падает,
равна отсутствию политики, поэтому упавший хук отвечает ask с текстом ошибки."""
import json


def respond(decision, reason):
    print(json.dumps({'hookSpecificOutput': {
        'hookEventName': 'PreToolUse',
        'permissionDecision': decision,
        'permissionDecisionReason': reason,
    }}, ensure_ascii=False))


def guarded(name, run, on_error='ask'):
    try:
        run()
    except Exception as error:
        respond(on_error, '%s: хук упал (%s: %s). Действие не проверено — подтверди осознанно или почини хук.'
                % (name, type(error).__name__, error))
