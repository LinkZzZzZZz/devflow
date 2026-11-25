import json
import os
import subprocess
import tempfile
import unittest

from tests.helpers import HOOKS

ROOT = os.path.dirname(HOOKS)


def run(root=ROOT, source='startup', event='SessionStart', env_file=None, agent_type=None):
    env = dict(os.environ, CLAUDE_PLUGIN_ROOT=root)
    env.pop('CLAUDE_ENV_FILE', None)
    if env_file:
        env['CLAUDE_ENV_FILE'] = env_file
    payload = {'hook_event_name': event, 'source': source}
    if agent_type:
        payload['agent_type'] = agent_type
    result = subprocess.run([os.path.join(HOOKS, 'session-start.py')], input=json.dumps(payload),
                            capture_output=True, text=True, timeout=30, env=env)
    return json.loads(result.stdout), result.stderr


class SessionStartTest(unittest.TestCase):
    def test_outputs_rules_with_version(self):
        out, err = run()
        ctx = out['hookSpecificOutput']['additionalContext']
        self.assertEqual(out['hookSpecificOutput']['hookEventName'], 'SessionStart')
        self.assertTrue(ctx.startswith('# Общие правила devflow (плагин, версия '))
        self.assertIn('## 0. Стоп-правила', ctx)
        self.assertEqual(err, '')

    def test_context_names_plugin_root(self):
        out, _ = run()
        self.assertIn('Корень плагина devflow: %s' % ROOT, out['hookSpecificOutput']['additionalContext'])
        self.assertIn('$DEVFLOW_ROOT', out['hookSpecificOutput']['additionalContext'])

    def test_session_start_exports_root_to_env_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_file = os.path.join(tmp, 'env')
            run(env_file=env_file)
            with open(env_file) as handle:
                self.assertIn('export DEVFLOW_ROOT=%s' % json.dumps(ROOT), handle.read())

    def test_subagent_start_event_name_and_no_env_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_file = os.path.join(tmp, 'env')
            out, _ = run(event='SubagentStart', env_file=env_file, agent_type='devflow:quality-reviewer')
            self.assertEqual(out['hookSpecificOutput']['hookEventName'], 'SubagentStart')
            self.assertIn('## 0. Стоп-правила', out['hookSpecificOutput']['additionalContext'])
            self.assertFalse(os.path.exists(env_file))

    def test_subagent_gets_subset_of_sections(self):
        out, _ = run(event='SubagentStart', agent_type='devflow:implementer')
        ctx = out['hookSpecificOutput']['additionalContext']
        self.assertTrue(ctx.startswith('# Общие правила devflow (плагин, версия '))
        for present in ('## 0. Стоп-правила', '## 2. Git', '## 3. Проверки', 'оркестратору'):
            self.assertIn(present, ctx)
        for absent in ('## 1. Общение', '## 4. Тикеты', '<!-- subagent'):
            self.assertNotIn(absent, ctx)

    def test_session_gets_all_sections_without_markers(self):
        out, _ = run()
        ctx = out['hookSpecificOutput']['additionalContext']
        for present in ('## 0. Стоп-правила', '## 1. Общение', '## 2. Git', '## 3. Проверки', '## 4. Тикеты'):
            self.assertIn(present, ctx)
        self.assertNotIn('<!-- subagent', ctx)
        self.assertNotIn('оркестратору', ctx)

    def test_context_lists_project_stack_hooks(self):
        from tests.helpers import make_repo
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp, '## Код\n- Hooks: `strict_types, php_house_rules`\n')
            env = dict(os.environ, CLAUDE_PLUGIN_ROOT=ROOT)
            env.pop('CLAUDE_ENV_FILE', None)
            result = subprocess.run([os.path.join(HOOKS, 'session-start.py')], input=json.dumps({'cwd': repo}),
                                    capture_output=True, text=True, timeout=30, env=env)
            ctx = json.loads(result.stdout)['hookSpecificOutput']['additionalContext']
            self.assertIn('Стековые хуки проекта: strict_types, php_house_rules', ctx)
            result = subprocess.run([os.path.join(HOOKS, 'session-start.py')], input=json.dumps({'cwd': tmp}),
                                    capture_output=True, text=True, timeout=30, env=env)
            ctx = json.loads(result.stdout)['hookSpecificOutput']['additionalContext']
            self.assertIn('Стековые хуки проекта: нет', ctx)

    def test_truncates_long_rules_at_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, 'rules'))
            os.makedirs(os.path.join(tmp, '.claude-plugin'))
            with open(os.path.join(tmp, '.claude-plugin', 'plugin.json'), 'w') as handle:
                json.dump({'name': 'x', 'version': '9.9.9'}, handle)
            with open(os.path.join(tmp, 'rules', 'general.md'), 'w') as handle:
                handle.write('# Общие правила\n\n' + ''.join('## %d\n%s\n' % (i, 'x' * 2000) for i in range(8)))
            out, err = run(tmp)
            ctx = out['hookSpecificOutput']['additionalContext']
            self.assertLessEqual(len(ctx), 9500)
            self.assertTrue(ctx.rstrip().endswith('x' * 2000))
            self.assertIn('обрезан', err)
            self.assertIn('обрезан', ctx[:400])


if __name__ == '__main__':
    unittest.main()
