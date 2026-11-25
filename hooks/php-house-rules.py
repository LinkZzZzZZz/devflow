#!/usr/bin/env python3
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_workflow import enabled, load, skipped


NON_STRICT = re.compile(r'(?<![=!<>])(==|!=)(?!=)|<>')
CONSTANT = r"(?:null|true|false|-?\d+(?:\.\d+)?|'[^']*'|\"[^\"]*\"|(?:[A-Z][\w\\]*|self|static)::[A-Za-z_]\w*|\[\])"
VARIABLE = r"\$\w+(?:(?:->|\?->|::)\w+(?:\([^()]*\))?|\[[^\]]*\])*"
NOT_YODA = re.compile(r'(%s)\s*(===|!==|==|!=)\s*(%s)(?![\w(:\[-])' % (VARIABLE, CONSTANT), re.I)
TAG_WITH_TEXT = re.compile(r'^\s*\*\s*@(param|var)\s+.*?\$\w+\s+\S|^\s*\*\s*@throws\s+\S+\s+\S')
DOC_PROSE = re.compile(r'^\s*\*\s+(?!@)[^\s/*]')
LOOSE_DOC_LINE = re.compile(r'^\s*\*(?:/|\s*$|\s+@|\s+[A-Za-zА-Яа-яЁё][^$;]*$)')
ALLOWED_COMMENT = re.compile(r'^(@var\b|@phpstan-|@psalm-|phpcs:|@codeCoverage|@infection|todo\b|fixme\b)', re.I)


def added_lines(payload):
    tool = payload.get('tool_name')
    tool_input = payload.get('tool_input', {})
    if tool == 'Edit':
        old = set(line.strip() for line in tool_input.get('old_string', '').splitlines())
        return [line for line in tool_input.get('new_string', '').splitlines() if line.strip() not in old]
    if tool == 'Write':
        response = payload.get('tool_response') or {}
        original = response.get('originalFile') if isinstance(response, dict) else None
        old = set(line.strip() for line in (original or '').splitlines())
        return [line for line in tool_input.get('content', '').splitlines() if line.strip() not in old]
    return []


HEREDOC = re.compile(r"<<<\s*['\"]?([A-Za-z_]\w*)['\"]?\s*$")


def split_line(line, state):
    code = []
    comment = None
    index = 0
    while index < len(line):
        char = line[index]
        if state:
            if char == '\\':
                index += 2
                continue
            if char == state:
                state = None
                code.append("''")
            index += 1
            continue
        heredoc = HEREDOC.match(line[index:])
        if heredoc and line[index:].startswith('<<<'):
            return ''.join(code), comment, ('heredoc', heredoc.group(1))
        if char in ('\'', '"'):
            state = char
        elif line.startswith('//', index) or (char == '#' and not line.startswith('#[', index)):
            comment = line[index:].lstrip('/#').strip()
            break
        else:
            code.append(char)
        index += 1
    return ''.join(code), comment, state


def violations(lines):
    found = []
    in_doc = False
    state = None
    for line in lines:
        stripped = line.strip()
        if isinstance(state, tuple):
            if re.match(r'^%s\b' % re.escape(state[1]), stripped):
                state = None
            continue
        if state:
            _code, _comment, state = split_line(line, state)
            continue

        if stripped.startswith('/**'):
            in_doc = not stripped.endswith('*/')
            inline = stripped[3:-2].strip() if stripped.endswith('*/') else ''
            if inline and not inline.startswith('@'):
                found.append((line, 'прозаический текст в PHPDoc — PHPDoc только для типов'))
            elif inline and TAG_WITH_TEXT.match(' * ' + inline):
                found.append((line, 'описание после типа в PHPDoc — оставь только тип и переменную'))
            continue
        if in_doc or LOOSE_DOC_LINE.match(line):
            if stripped.endswith('*/'):
                in_doc = False
            if TAG_WITH_TEXT.match(line):
                found.append((line, 'описание после типа в PHPDoc — оставь только тип и переменную'))
            elif DOC_PROSE.match(line):
                found.append((line, 'прозаический текст в PHPDoc — PHPDoc только для типов'))
            continue

        code, comment, state = split_line(line, None)
        if comment and not ALLOWED_COMMENT.match(comment):
            found.append((line, 'прозаический комментарий — обоснование идёт в отчёт задачи, не в код'))
        if re.search(r'/\*(?![*\s]*@)(?!\*).*?\S.*?\*/', code):
            found.append((line, 'прозаический комментарий — обоснование идёт в отчёт задачи, не в код'))
        if NON_STRICT.search(code):
            found.append((line, 'нестрогое сравнение — только === / !=='))
        for match in NOT_YODA.finditer(line):
            found.append((line, 'не Yoda: %s %s %s → %s %s %s' % (
                match.group(1), match.group(2), match.group(3), match.group(3), match.group(2), match.group(1),
            )))
    return found


def line_numbers(path, found):
    try:
        with open(path) as handle:
            content = handle.read().splitlines()
    except OSError:
        return [(None, line, why) for line, why in found]
    result = []
    for line, why in found:
        number = next((index + 1 for index, text in enumerate(content) if text == line), None)
        result.append((number, line, why))
    return result


def main():
    payload = json.load(sys.stdin)
    path = payload.get('tool_input', {}).get('file_path', '')
    if not path.endswith('.php') or path.endswith('.blade.php'):
        return
    cfg = load(os.path.dirname(path))
    if not enabled(cfg, 'php_house_rules') or skipped(cfg, path):
        return

    found = violations(added_lines(payload))
    if not found:
        return

    report = '\n'.join(
        '- %s: `%s` — %s' % ('стр. %d' % number if number else '?', line.strip()[:120], why)
        for number, line, why in line_numbers(path, found)
    )
    print(json.dumps({
        'decision': 'block',
        'reason': 'Правки в %s нарушают правила проекта (хук php-house-rules). Исправь сейчас:\n%s' % (path, report),
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()
