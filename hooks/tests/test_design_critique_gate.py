import json
import os
import subprocess
import tempfile
import unittest

from tests.helpers import HOOKS, decision, make_repo, run_hook

HOOK = 'design-critique-gate.py'
DESIGN = """# CB-7: решения

## Принятые решения

1. Кладём сценарий в слой приложения по образцу X.
2. Отдаём ошибку провайдера кодом 503, потому что стандарт так велит.
%s
3. Токены храним в кеше.

## Домен и API
"""
DESIGN_R = """# CB-7: решения

## Принятые решения

Р1. **Кладём сценарий в слой приложения.** По образцу X.

Р2. **Отдаём ошибку провайдера кодом 503.** Потому что так велит стандарт.
%s

Р3. **Токены храним в кеше.**

## Домен и API
"""
FACT_CHECK = """# Проверка фактов

| утверждение | где в документе | решение | вердикт | кто решает | пруф |
|---|---|---|---|---|---|
| поле token в ответе WB | design.md Домен | 3 | ПОДТВЕРЖДЕНО | — | https://example/doc |
| 503 — для недоступности провайдера | design.md решение 2 | %s | %s | %s | RFC 9110 §15.6.4 |
| формат телефона | spec.md | — | НЕ ПОДТВЕРЖДЕНО | источник | код |
"""
USER_LINE = '   Решение пользователя (2026-11-17): «%s»'


def touch(path, content='x'):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write(content)


def user(text):
    return {'type': 'user', 'message': {'role': 'user', 'content': text}}


def assistant(text):
    return {'type': 'assistant', 'message': {'role': 'assistant', 'content': [{'type': 'text', 'text': text}]}}


def tool_result(text):
    return {'type': 'user', 'message': {'role': 'user', 'content': [
        {'type': 'tool_result', 'tool_use_id': 't1', 'content': text}]}}


class DesignCritiqueGateTest(unittest.TestCase):
    def setUp(self):
        self.tmp_ctx = tempfile.TemporaryDirectory()
        self.tmp = self.tmp_ctx.name
        self.ticket = os.path.join(self.tmp, 'docs', 'tasks', 'CB-7')
        self.transcripts = os.path.join(self.tmp, 'projects', 'p')
        touch(os.path.join(self.ticket, 'spec.md'))
        self.design()

    def tearDown(self):
        self.tmp_ctx.cleanup()

    def design(self, user_line=''):
        touch(os.path.join(self.ticket, 'design.md'), DESIGN % user_line)

    def fact_check(self, decision_cell='2', verdict='НЕ ПОДТВЕРЖДЕНО', who='пользователь'):
        touch(os.path.join(self.ticket, 'reports', 'fact-check.md'), FACT_CHECK % (decision_cell, verdict, who))

    def transcript(self, events, name='s1.jsonl'):
        path = os.path.join(self.transcripts, name)
        touch(path, ''.join(json.dumps(e, ensure_ascii=False) + '\n' for e in events))
        return path

    def write(self, path):
        return run_hook(HOOK, {'tool_name': 'Write', 'cwd': self.tmp, 'tool_input': {'file_path': path, 'content': 'x'}})

    def implementer(self, prompt=None, kind='devflow:implementer', tool='Agent', transcript=''):
        prompt = prompt if prompt is not None else 'задача 1\nкаталог тикета: `%s/` — читать plan.md §1' % self.ticket
        return run_hook(HOOK, {'tool_name': tool, 'cwd': self.tmp, 'transcript_path': transcript,
                               'tool_input': {'subagent_type': kind, 'prompt': prompt, 'description': 'x'}})

    def critique(self):
        touch(os.path.join(self.ticket, 'reports', 'design-critique.md'))

    def reason(self, out):
        return out['hookSpecificOutput']['permissionDecisionReason']

    def test_plan_without_critique_denied(self):
        out = self.write(os.path.join(self.ticket, 'plan.md'))
        self.assertEqual(decision(out), 'deny')
        self.assertIn('CB-7', self.reason(out))
        self.assertIn('режим: design', self.reason(out))

    def test_relative_plan_path_denied(self):
        self.assertEqual(decision(self.write('docs/tasks/CB-7/plan.md')), 'deny')

    def test_plan_after_critique_passes(self):
        self.critique()
        self.assertIsNone(self.write(os.path.join(self.ticket, 'plan.md')))

    def test_ticket_without_design_not_gated(self):
        other = os.path.join(self.tmp, 'docs', 'tasks', 'CB-8')
        touch(os.path.join(other, 'spec.md'))
        self.assertIsNone(self.write(os.path.join(other, 'plan.md')))
        self.assertIsNone(self.implementer('каталог тикета: %s, tasks.md п. 1' % other))

    def test_other_files_not_gated(self):
        self.assertIsNone(self.write(os.path.join(self.ticket, 'tasks.md')))
        self.assertIsNone(self.write(os.path.join(self.tmp, 'docs', 'plan.md')))

    def test_implementer_without_critique_denied(self):
        self.fact_check(verdict='ПОДТВЕРЖДЕНО')
        self.assertEqual(decision(self.implementer()), 'deny')
        self.assertIn('режим: design', self.reason(self.implementer()))
        self.assertEqual(decision(self.implementer(kind='implementer', tool='Task')), 'deny')
        self.assertEqual(decision(self.implementer('каталог тикета docs/tasks/CB-7, план')), 'deny')

    def test_implementer_without_fact_check_denied(self):
        self.critique()
        out = self.implementer()
        self.assertEqual(decision(out), 'deny')
        self.assertIn('fact-checker', self.reason(out))

    def test_implementer_after_both_checks_passes(self):
        self.critique()
        self.fact_check(verdict='ПОДТВЕРЖДЕНО')
        self.assertIsNone(self.implementer())

    def test_refuted_decision_without_user_answer_denied(self):
        self.critique()
        for verdict in ('НЕ ПОДТВЕРЖДЕНО', 'ТОЛКОВАНИЕ'):
            self.fact_check(verdict=verdict)
            out = self.implementer()
            self.assertEqual(decision(out), 'deny', verdict)
            self.assertIn('решение 2', self.reason(out))
            self.assertIn('Решение пользователя', self.reason(out))

    def test_refuted_row_without_decision_number_not_gated(self):
        self.critique()
        self.fact_check(decision_cell='—')
        self.assertIsNone(self.implementer())

    def test_user_answer_quoted_from_transcript_passes(self):
        self.critique()
        self.fact_check()
        self.design(USER_LINE % 'Оставляем 503, это продуктовое решение')
        path = self.transcript([assistant('RFC этого не предписывает, варианты: 503 или 502'),
                                user('оставляем   503, это продуктовое решение\nи пометь как толкование')])
        self.assertIsNone(self.implementer(transcript=path))

    def test_short_answer_must_be_whole_message(self):
        self.critique()
        self.fact_check()
        self.design(USER_LINE % 'да')
        path = self.transcript([user('давай подождём с этим')])
        self.assertEqual(decision(self.implementer(transcript=path)), 'deny')
        path = self.transcript([user('Да')], name='s2.jsonl')
        self.assertIsNone(self.implementer(transcript=path))

    def test_quote_from_assistant_or_tool_result_denied(self):
        self.critique()
        self.fact_check()
        self.design(USER_LINE % 'решение не меняю, фиксирую')
        path = self.transcript([assistant('решение не меняю, фиксирую'), tool_result('решение не меняю, фиксирую')])
        out = self.implementer(transcript=path)
        self.assertEqual(decision(out), 'deny')
        self.assertIn('нет в сообщениях пользователя', self.reason(out))

    def test_quote_found_in_sibling_transcript(self):
        self.critique()
        self.fact_check()
        self.design(USER_LINE % 'берём 502 и 504, согласен')
        self.transcript([user('Берём 502 и 504, согласен')], name='old.jsonl')
        current = self.transcript([user('продолжай')], name='new.jsonl')
        self.assertIsNone(self.implementer(transcript=current))

    def test_user_line_in_other_decision_does_not_count(self):
        self.critique()
        self.fact_check(decision_cell='3')
        self.design(USER_LINE % 'Оставляем 503, это продуктовое решение')
        path = self.transcript([user('Оставляем 503, это продуктовое решение')])
        self.assertEqual(decision(self.implementer(transcript=path)), 'deny')

    def test_legacy_fact_check_without_decision_column_denied(self):
        self.critique()
        touch(os.path.join(self.ticket, 'reports', 'fact-check.md'),
              '| # | Утверждение | Где | Вердикт | Пруф |\n|---|---|---|---|---|\n| 1 | x | design Р2 | ПОДТВЕРЖДЕНО | y |\n')
        out = self.implementer()
        self.assertEqual(decision(out), 'deny')
        self.assertIn('старый формат', self.reason(out))

    def test_decision_column_without_decider_is_legacy(self):
        self.critique()
        touch(os.path.join(self.ticket, 'reports', 'fact-check.md'),
              '| утверждение | решение | вердикт | пруф |\n|---|---|---|---|\n| x | 2 | ПОДТВЕРЖДЕНО | y |\n')
        out = self.implementer()
        self.assertEqual(decision(out), 'deny')
        self.assertIn('кто решает', self.reason(out))

    def test_source_decided_needs_fix_line_not_user(self):
        self.critique()
        for who in ('источник', 'образец', 'умолчание'):
            self.fact_check(who=who)
            self.design()
            out = self.implementer()
            self.assertEqual(decision(out), 'deny', who)
            self.assertIn('Исправлено по проверке', self.reason(out))
            self.assertNotIn('Вынеси пользователю', self.reason(out))
            self.design('   Исправлено по проверке (2026-11-17): 502 при 5xx, 504 при таймауте')
            self.assertIsNone(self.implementer(), who)

    def test_user_decided_ignores_fix_line(self):
        self.critique()
        self.fact_check(who='пользователь')
        self.design('   Исправлено по проверке (2026-11-17): сам решил оставить 503')
        out = self.implementer()
        self.assertEqual(decision(out), 'deny')
        self.assertIn('Вынеси пользователю', self.reason(out))

    def test_refuted_without_decider_denied(self):
        self.critique()
        self.fact_check(who='—')
        self.design(USER_LINE % 'Оставляем 503, это продуктовое решение')
        out = self.implementer()
        self.assertEqual(decision(out), 'deny')
        self.assertIn('перезапусти', self.reason(out))

    def test_quote_found_in_other_worktree_of_same_repo(self):
        repo = make_repo(os.path.join(self.tmp, 'git'))
        ticket = os.path.join(repo, 'docs', 'tasks', 'CB-9')
        for rel in ('spec.md', 'reports/design-critique.md'):
            touch(os.path.join(ticket, rel))
        touch(os.path.join(ticket, 'reports', 'fact-check.md'), FACT_CHECK % ('2', 'ТОЛКОВАНИЕ', 'пользователь'))
        touch(os.path.join(ticket, 'design.md'), DESIGN % (USER_LINE % 'aud пока не проверяем, отступление от доки'))
        prefix = os.path.realpath(repo).replace('/', '-').replace('.', '-').replace('_', '-')
        projects = os.path.join(self.tmp, 'projects')
        current = os.path.join(projects, prefix + '--claude-worktrees-new', 's.jsonl')
        touch(current, json.dumps(user('продолжай')) + '\n')
        prompt = 'каталог тикета: %s' % ticket
        payload = {'tool_name': 'Agent', 'cwd': repo, 'transcript_path': current,
                   'tool_input': {'subagent_type': 'implementer', 'prompt': prompt}}
        self.assertEqual(decision(run_hook(HOOK, payload)), 'deny')
        other_repo = os.path.join(projects, prefix + 'x', 'o.jsonl')
        touch(other_repo, json.dumps(user('aud пока не проверяем, отступление от доки'), ensure_ascii=False) + '\n')
        self.assertEqual(decision(run_hook(HOOK, payload)), 'deny')
        old = os.path.join(projects, prefix + '--claude-worktrees-old', 'o.jsonl')
        touch(old, json.dumps(user('aud пока не проверяем, отступление от доки'), ensure_ascii=False) + '\n')
        self.assertIsNone(run_hook(HOOK, payload))

    def test_fact_check_without_table_passes(self):
        self.critique()
        touch(os.path.join(self.ticket, 'reports', 'fact-check.md'), 'Непроверенных утверждений нет.\n')
        self.assertIsNone(self.implementer())

    def test_r_prefixed_decisions(self):
        self.critique()
        touch(os.path.join(self.ticket, 'design.md'), DESIGN_R % '')
        self.fact_check(decision_cell='Р2')
        out = self.implementer()
        self.assertEqual(decision(out), 'deny')
        self.assertIn('решение 2', self.reason(out))
        touch(os.path.join(self.ticket, 'design.md'), DESIGN_R % (USER_LINE % 'Оставляем 503, это продуктовое решение'))
        path = self.transcript([user('Оставляем 503, это продуктовое решение')])
        self.assertIsNone(self.implementer(transcript=path))

    def test_indented_sub_item_does_not_split_decision(self):
        self.critique()
        self.fact_check()
        self.design('   1. подпункт решения 2\n' + USER_LINE % 'Оставляем 503, это продуктовое решение')
        path = self.transcript([user('Оставляем 503, это продуктовое решение')])
        self.assertIsNone(self.implementer(transcript=path))

    def test_other_agents_and_bare_key_pass(self):
        self.assertIsNone(self.implementer(kind='devflow:spec-critic'))
        self.assertIsNone(self.implementer('тикет CB-7 без пути'))

    def test_broken_stdin_asks(self):
        result = subprocess.run([os.path.join(HOOKS, HOOK)], input='{not json', capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0)
        self.assertIn('"ask"', result.stdout)


if __name__ == '__main__':
    unittest.main()
