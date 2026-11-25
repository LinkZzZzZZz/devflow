import os
import tempfile
import unittest
from unittest import mock

import lib_env


class LibEnvTest(unittest.TestCase):
    def test_default_path_and_override(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop('DEVFLOW_ENV', None)
            self.assertEqual(lib_env.env_path(), os.path.expanduser('~/.claude/devflow/.env'))
        with mock.patch.dict(os.environ, {'DEVFLOW_ENV': '~/x/.env'}):
            self.assertEqual(lib_env.env_path(), os.path.expanduser('~/x/.env'))

    def test_load_env_parses_and_tolerates_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, '.env')
            with open(path, 'w') as handle:
                handle.write('# комментарий\nTRACKER_TOKEN=abc\n\nDEVFLOW_SRC = ~/dev/plugin \nBAD LINE\n')
            env = lib_env.load_env(path)
            self.assertEqual(env['TRACKER_TOKEN'], 'abc')
            self.assertEqual(env['DEVFLOW_SRC'], '~/dev/plugin')
            self.assertEqual(lib_env.load_env(os.path.join(tmp, 'nope')), {})

    def test_plugin_src_expands_tilde_and_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, '.env')
            with open(path, 'w') as handle:
                handle.write('DEVFLOW_SRC=~/dev/plugin\n')
            with mock.patch.dict(os.environ, {'DEVFLOW_ENV': path}):
                self.assertEqual(lib_env.plugin_src(), os.path.expanduser('~/dev/plugin'))
            with mock.patch.dict(os.environ, {'DEVFLOW_ENV': os.path.join(tmp, 'nope')}):
                self.assertEqual(lib_env.plugin_src(), os.path.expanduser('~/dev/devflow'))

    def test_quotes_and_trailing_spaces_stripped(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, '.env')
            with open(path, 'w') as handle:
                handle.write('DEVFLOW_SRC="~/dev/plugin"  \nTRACKER_QUEUE=\'CB\'\n')
            env = lib_env.load_env(path)
            self.assertEqual(env['DEVFLOW_SRC'], '~/dev/plugin')
            self.assertEqual(env['TRACKER_QUEUE'], 'CB')

    def test_cli_prints_src_and_env_path(self):
        import subprocess
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, '.env')
            with open(path, 'w') as handle:
                handle.write('DEVFLOW_SRC=~/dev/plugin\n')
            env = dict(os.environ, DEVFLOW_ENV=path)
            src = subprocess.run(['python3', lib_env.__file__, 'src'], capture_output=True, text=True, env=env).stdout.strip()
            self.assertEqual(src, os.path.expanduser('~/dev/plugin'))
            shown = subprocess.run(['python3', lib_env.__file__, 'env-path'], capture_output=True, text=True, env=env).stdout.strip()
            self.assertEqual(shown, path)

    def test_plugin_root(self):
        with mock.patch.dict(os.environ, {'CLAUDE_PLUGIN_ROOT': '/tmp/root'}):
            self.assertEqual(lib_env.plugin_root(), '/tmp/root')
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop('CLAUDE_PLUGIN_ROOT', None)
            self.assertEqual(lib_env.plugin_root(), os.path.dirname(os.path.dirname(os.path.abspath(lib_env.__file__))))


if __name__ == '__main__':
    unittest.main()
