import json
import os
import shutil
import subprocess
import tempfile
import unittest

from tests.helpers import HOOKS, make_repo

ROOT = os.path.dirname(HOOKS)
HOOK = os.path.join(HOOKS, 'cycle-check.py')


def tool_use(name, **inp):
    return {'type': 'assistant', 'message': {'content': [{'type': 'tool_use', 'name': name, 'input': inp}]}}


def agent(kind, prompt='…'):
    return tool_use('Agent', subagent_type=kind, prompt=prompt)


def text(body):
    return {'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': body}]}}


FINISH_LINE = 'Готово к пушу: да · проверки ✓ на abc1234 · тесты: 10 OK'
PRE_PUSH = tool_use('Bash', command='$DEVFLOW_ROOT/hooks/pre-push-check.py')
FIX_BUG = '# CB-7, заход 1: баг — 2026-11-16\n'
FIX_REVIEW = '# CB-7, заход 1: ревью — 2026-11-16\n'


def transcript(tmp, events, raw_lines=()):
    path = os.path.join(tmp, 'session.jsonl')
    with open(path, 'w', encoding='utf-8') as handle:
        for event in events:
            handle.write(json.dumps(event, ensure_ascii=False) + '\n')
        for line in raw_lines:
            handle.write(line + '\n')
    return path


def run(cwd, transcript_path, session='s1', root=ROOT, stop_hook_active=False):
    payload = {'session_id': session, 'transcript_path': transcript_path, 'cwd': cwd,
               'hook_event_name': 'Stop', 'stop_hook_active': stop_hook_active}
    env = dict(os.environ, CLAUDE_PLUGIN_ROOT=root)
    result = subprocess.run([HOOK], input=json.dumps(payload), capture_output=True, text=True, timeout=60, env=env)
    out = result.stdout.strip()
    return (json.loads(out) if out else None), result.stderr


def spec(repo, key, size=None):
    path = os.path.join(repo, 'docs', 'tasks', key, 'spec.md')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write('# %s\n\nСтатус: Открыт\n%s\n' % (key, 'Размер: %s' % size if size else ''))
    return os.path.dirname(path)


class CycleCheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.repo = make_repo(self.tmp)
        self.ticket = spec(self.repo, 'CB-7', 'bounded')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, rel, content='x'):
        return tool_use('Write', file_path=os.path.join(self.ticket, rel), content=content)

    def check(self, events, session='s1', root=ROOT):
        return run(self.repo, transcript(self.tmp, events), session=session, root=root)

    def assertBlocks(self, out, mode, agent_name):
        self.assertIsNotNone(out, 'ожидался блок')
        self.assertEqual(out['decision'], 'block')
        self.assertIn('цикл %s' % mode, out['reason'])
        self.assertIn(agent_name, out['reason'])

    def test_new_ticket_without_spec_critic_blocks(self):
        out, _ = self.check([self.write('spec.md')])
        self.assertBlocks(out, 'new-ticket', 'spec-critic')
        self.assertIn('brief', out['reason'] + 'brief')

    def test_new_ticket_with_spec_critic_ok(self):
        out, _ = self.check([self.write('spec.md'), agent('devflow:spec-critic')])
        self.assertIsNone(out)

    def test_small_spec_no_spec_critic_ok(self):
        spec(self.repo, 'CB-7', 'small (предварительно)')
        out, _ = self.check([self.write('spec.md')])
        self.assertIsNone(out)

    def test_start_without_mapper_blocks(self):
        out, _ = self.check([self.write('tasks.md')])
        self.assertBlocks(out, 'start', 'system-mapper')

    def test_start_plan_with_mapper_ok(self):
        out, _ = self.check([agent('devflow:system-mapper'), self.write('plan.md')])
        self.assertIsNone(out)

    def test_design_without_critic_blocks(self):
        out, _ = self.check([agent('devflow:system-mapper'), self.write('design.md')])
        self.assertBlocks(out, 'start', 'decision-critic')
        self.assertIn('design.md', out['reason'])
        out, _ = self.check([agent('devflow:system-mapper'), agent('devflow:decision-critic'),
                             agent('devflow:spec-critic', 'режим: design\nspec.md, design.md'),
                             self.write('design.md')], session='s2')
        self.assertIsNone(out)

    def test_design_needs_spec_critic_in_design_mode(self):
        base = [agent('devflow:system-mapper'), agent('devflow:decision-critic'), self.write('design.md')]
        out, _ = self.check(base)
        self.assertBlocks(out, 'start', 'spec-critic')
        self.assertIn('Паттерны и образцы', out['reason'])
        out, _ = self.check([agent('devflow:spec-critic', 'режим: spec\nspec.md')] + base, session='s2')
        self.assertBlocks(out, 'start', 'spec-critic')
        out, _ = self.check([agent('devflow:spec-critic', 'Режим:  design\nspec.md')] + base, session='s3')
        self.assertIsNone(out)

    def test_agent_prompt_filter_parsed_with_condition(self):
        root = os.path.join(self.tmp, 'plugin')
        os.makedirs(os.path.join(root, 'skills', 'task-workflow', 'references'))
        with open(os.path.join(root, 'skills', 'task-workflow', 'references', 'cycles.md'), 'w', encoding='utf-8') as handle:
            handle.write('## Машинные строки\n\n- fixes: write:<KEY>/reports/fix-N.md | fact-checker#режим:\\s*x[bounded, architectural], decision-critic | зови\n')
        events = [agent('decision-critic'), self.write('reports/fix-1.md', FIX_REVIEW)]
        out, _ = self.check([agent('fact-checker', 'режим: y')] + events, root=root)
        self.assertBlocks(out, 'fixes', 'fact-checker')
        out, _ = self.check([agent('fact-checker', 'режим: x')] + events, session='s2', root=root)
        self.assertIsNone(out)
        spec(self.repo, 'CB-7', 'small')
        out, _ = self.check(events, session='s3', root=root)
        self.assertIsNone(out)

    def test_finish_bounded_without_black_box_blocks(self):
        out, _ = self.check([agent('devflow:system-mapper'), agent('devflow:quality-reviewer'),
                             self.write('reports/report-3.md'), PRE_PUSH])
        self.assertBlocks(out, 'finish', 'black-box-tester')

    def test_subagent_write_is_not_finish_sign(self):
        out, _ = self.check([self.write('reports/test-report.md')])
        self.assertIsNone(out)

    def test_status_line_without_pre_push_check_silent(self):
        out, _ = self.check([self.write('reports/report-3.md'), text(FINISH_LINE)])
        self.assertIsNone(out)

    def test_pre_push_check_in_fixes_session_is_not_finish(self):
        out, _ = self.check([agent('decision-critic'), self.write('reports/fix-1.md', FIX_BUG), PRE_PUSH])
        self.assertIsNone(out)

    def test_pre_push_check_without_ticket_writes_silent(self):
        out, _ = self.check([tool_use('Bash', command='git status'), PRE_PUSH])
        self.assertIsNone(out)

    def test_ship_squash_is_not_finish(self):
        out, _ = self.check([self.write('reports/notes.md'), PRE_PUSH, tool_use('Bash', command='git reset --soft origin/dev && git commit -m x')])
        self.assertIsNone(out)

    def test_resolve_reply_is_not_finish(self):
        out, _ = self.check([self.write('reports/notes.md'), PRE_PUSH, tool_use('Bash', command='gh api repos/o/r/pulls/5/comments/77/replies -f body=x')])
        self.assertIsNone(out)

    def test_finish_small_without_black_box_ok(self):
        spec(self.repo, 'CB-7', 'small')
        out, _ = self.check([agent('devflow:system-mapper'), agent('devflow:quality-reviewer'),
                             self.write('reports/report-1.md'), PRE_PUSH])
        self.assertIsNone(out)

    def test_finish_without_mapper_blocks(self):
        out, _ = self.check([agent('devflow:quality-reviewer'), agent('devflow:black-box-tester'),
                             self.write('reports/report-1.md'), PRE_PUSH])
        self.assertBlocks(out, 'finish', 'system-mapper')

    def test_fixes_without_critic_blocks(self):
        out, _ = self.check([self.write('reports/fix-2.md', FIX_BUG)])
        self.assertBlocks(out, 'fixes', 'decision-critic')
        self.assertIn('причина бага', out['reason'])
        out, _ = self.check([self.write('reports/fix-2.md', '# CB-7, заход 2: CI — 2026-11-16\n')], session='s2')
        self.assertBlocks(out, 'fixes', 'decision-critic')

    def test_fixes_tester_not_gated(self):
        out, _ = self.check([self.write('reports/fix-3.md', '# CB-7, заход 3: тестер — 2026-11-16\n')])
        self.assertIsNone(out)

    def test_fixes_review_without_reviewer_blocks(self):
        out, _ = self.check([self.write('reports/fix-2.md', FIX_REVIEW)])
        self.assertBlocks(out, 'resolve-pr-comments', 'quality-reviewer')
        self.assertIn('review-fix-N-r1.md', out['reason'])
        self.assertNotIn('цикл fixes', out['reason'])

    def test_fixes_review_needs_reviewer_in_subtask_mode(self):
        out, _ = self.check([agent('quality-reviewer', 'режим: branch\nдифф ветки'), self.write('reports/fix-2.md', FIX_REVIEW)])
        self.assertBlocks(out, 'resolve-pr-comments', 'quality-reviewer')
        out, _ = self.check([self.write('reports/fix-2.md', FIX_REVIEW), agent('quality-reviewer', 'режим: subtask\nSHA abc1234')], session='s2')
        self.assertIsNone(out)

    def test_fixes_with_critic_ok(self):
        out, _ = self.check([agent('decision-critic'), self.write('reports/fix-2.md', FIX_BUG)])
        self.assertIsNone(out)

    def test_estimate_requires_both(self):
        out, _ = self.check([agent('devflow:system-mapper'), self.write('estimate.md')])
        self.assertBlocks(out, 'estimate', 'decision-critic')
        out, _ = self.check([agent('devflow:system-mapper'), agent('devflow:decision-critic'),
                             self.write('estimate.md')], session='s2')
        self.assertIsNone(out)

    def test_research_without_critic_blocks(self):
        out, _ = self.check([self.write('report.md')])
        self.assertBlocks(out, 'research', 'decision-critic')

    def test_review_pr_without_mapper_blocks(self):
        out, _ = self.check([agent('devflow:quality-reviewer'), tool_use('Bash', command='gh api repos/o/r/pulls/5/reviews -f event=COMMENT -f body=x')])
        self.assertBlocks(out, 'review-pr', 'system-mapper')

    def test_review_pr_with_both_ok(self):
        out, _ = self.check([agent('devflow:quality-reviewer'), agent('devflow:system-mapper'), tool_use('Bash', command='gh api repos/o/r/pulls/5/reviews -f event=COMMENT -f body=x')])
        self.assertIsNone(out)

    def test_reply_is_not_review_pr(self):
        out, _ = self.check([tool_use('Bash', command='gh api repos/o/r/pulls/5/comments/77/replies -f body=x')])
        self.assertIsNone(out)

    def test_review_pr_via_gh_pr_review_and_input_file(self):
        out, _ = self.check([tool_use('Bash', command='gh pr review 5 --comment --body x')])
        self.assertBlocks(out, 'review-pr', 'system-mapper')
        out, _ = self.check([tool_use('Bash', command='gh api repos/{owner}/{repo}/pulls/5/reviews --input r.json')],
                            session='s2')
        self.assertBlocks(out, 'review-pr', 'quality-reviewer')

    def test_reading_reviews_is_not_review_pr(self):
        out, _ = self.check([tool_use('Bash', command='gh api repos/o/r/pulls/5/reviews')])
        self.assertIsNone(out)

    def test_edit_is_not_a_sign(self):
        out, _ = self.check([tool_use('Edit', file_path=os.path.join(self.ticket, 'spec.md'),
                                      old_string='Статус: Открыт', new_string='Статус: Открыт\nРазмер: bounded'),
                             tool_use('Edit', file_path=os.path.join(self.ticket, 'tasks.md'),
                                      old_string='- [ ] 1.', new_string='- [x] 1.'),
                             tool_use('Edit', file_path=os.path.join(self.ticket, 'reports', 'fix-1.md'),
                                      old_string='a', new_string='b')])
        self.assertIsNone(out)

    def test_marker_is_per_ticket(self):
        events = [self.write('reports/fix-1.md', FIX_BUG)]
        out, _ = self.check(events, session='same')
        self.assertBlocks(out, 'fixes', 'decision-critic')
        other = spec(self.repo, 'CB-8', 'bounded')
        events_b = [tool_use('Write', file_path=os.path.join(other, 'reports', 'fix-1.md'), content=FIX_BUG.replace('CB-7', 'CB-8'))]
        out, _ = self.check(events_b, session='same')
        self.assertBlocks(out, 'fixes', 'decision-critic')
        out, _ = self.check(events_b, session='same')
        self.assertIsNone(out)

    def test_unclear_mode_silent(self):
        out, _ = self.check([tool_use('Read', file_path='/x/y.md'), tool_use('Bash', command='ls'),
                             tool_use('Write', file_path=os.path.join(self.repo, 'src', 'a.php'), content='x')])
        self.assertIsNone(out)

    def test_repeat_not_blocked(self):
        events = [self.write('reports/fix-1.md', FIX_BUG)]
        out, _ = self.check(events, session='same')
        self.assertBlocks(out, 'fixes', 'decision-critic')
        out, _ = run(self.repo, transcript(self.tmp, events), session='same', stop_hook_active=True)
        self.assertIsNone(out)
        out, _ = self.check(events, session='other')
        self.assertBlocks(out, 'fixes', 'decision-critic')

    def test_broken_transcript_silent(self):
        path = transcript(self.tmp, [{'type': 'summary'}, {'type': 'assistant', 'message': None}],
                          raw_lines=['{not json'])
        out, err = run(self.repo, path)
        self.assertIsNone(out)
        self.assertEqual(err, '')
        out, err = run(self.repo, os.path.join(self.tmp, 'missing.jsonl'))
        self.assertIsNone(out)
        self.assertIn('cycle-check', err)

    def test_reads_table_from_cycles_md(self):
        root = os.path.join(self.tmp, 'plugin')
        os.makedirs(os.path.join(root, 'hooks'))
        os.makedirs(os.path.join(root, 'skills', 'task-workflow', 'references'))
        with open(os.path.join(root, 'skills', 'task-workflow', 'references', 'cycles.md'), 'w', encoding='utf-8') as handle:
            handle.write('## Машинные строки\n\n- fixes: write:<KEY>/reports/fix-N.md | fact-checker | зови fact-checker\n')
        out, _ = self.check([agent('decision-critic'), self.write('reports/fix-1.md', FIX_REVIEW)], root=root)
        self.assertBlocks(out, 'fixes', 'fact-checker')
        self.assertIn('зови fact-checker', out['reason'])


if __name__ == '__main__':
    unittest.main()
