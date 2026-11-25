"""confirm-youtrack-write.py: запись в YouTrack — только по подтверждению, с параметрами; чтение матчер не ловит."""
import json
import os
import re
import unittest

from tests.helpers import HOOKS, decision, run_hook

WRITES = ('create_issue', 'create_draft_issue', 'update_draft_issue', 'publish_draft_issue', 'update_issue',
          'change_issue_assignee', 'add_issue_comment', 'manage_issue_tags', 'link_issues', 'create_article',
          'update_article', 'add_attachment', 'log_work', 'update_work_item')
READS = ('search_issues', 'get_issue_fields_schema', 'get_issue', 'get_issue_comments', 'get_saved_issue_searches',
         'find_tags', 'get_article', 'search_articles', 'find_projects', 'get_project', 'find_user_groups',
         'get_user_group_members', 'find_user', 'get_current_user', 'get_issue_work_items', 'search_documentation')
PREFIXES = ('mcp__youtrack__', 'mcp__plugin_devflow_youtrack__')


def matcher():
    with open(os.path.join(HOOKS, 'hooks.json'), encoding='utf-8') as handle:
        for entry in json.load(handle)['hooks']['PreToolUse']:
            if any('confirm-youtrack-write' in hook['command'] for hook in entry['hooks']):
                return re.compile(entry['matcher'])
    raise AssertionError('в hooks.json нет confirm-youtrack-write')


def call(tool, args=None):
    return run_hook('confirm-youtrack-write.py', {'tool_name': tool, 'tool_input': args or {}})


def reason(out):
    return out['hookSpecificOutput']['permissionDecisionReason']


class YoutrackWriteMatcherTest(unittest.TestCase):
    def test_writes_match_under_local_and_plugin_names(self):
        pattern = matcher()
        for name in WRITES:
            for prefix in PREFIXES:
                self.assertTrue(pattern.search(prefix + name), prefix + name)

    def test_reads_do_not_match(self):
        pattern = matcher()
        for name in READS:
            for prefix in PREFIXES:
                self.assertIsNone(pattern.search(prefix + name), prefix + name)


class YoutrackWriteHookTest(unittest.TestCase):
    def test_every_write_asks(self):
        for name in WRITES:
            self.assertEqual(decision(call('mcp__youtrack__' + name, {'issueId': 'T-1'})), 'ask', name)

    def test_comment_shows_issue_and_text(self):
        out = call('mcp__youtrack__add_issue_comment', {'issueId': 'T-12', 'text': 'ветка готова, PR на ревью'})
        self.assertEqual(decision(out), 'ask')
        self.assertIn('Комментарий в задачу', reason(out))
        self.assertIn('T-12', reason(out))
        self.assertIn('ветка готова, PR на ревью', reason(out))

    def test_long_values_and_base64_trimmed(self):
        out = call('mcp__plugin_devflow_youtrack__add_attachment', {'issueId': 'T-3', 'content': 'A' * 5000,
                                                                   'description': 'б' * 1000})
        self.assertIn('<5000 символов base64>', reason(out))
        self.assertNotIn('A' * 50, reason(out))
        self.assertIn('…', reason(out))

    def test_unknown_tool_still_asks(self):
        self.assertEqual(decision(call('mcp__other__thing')), 'ask')
