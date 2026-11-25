import os
import tempfile
import unittest

from tests.helpers import decision, make_repo, run_hook

WF = ('## Миграции\n- migrations_dirs: `common/migrations, common/clickhouse-migrations`\n'
      '- migration_create: `npm run migration:create --name=<имя>`\n')


def write(path):
    return decision(run_hook('block-manual-migration.py',
                             {'tool_name': 'Write', 'tool_input': {'file_path': path, 'content': 'x'}}))


class MigrationTest(unittest.TestCase):
    def test_new_file_in_migrations_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp, WF, {'common/migrations/1-a.ts': 'x\n'})
            self.assertEqual(write(os.path.join(repo, 'common/migrations/2-b.ts')), 'deny')
            self.assertEqual(write(os.path.join(repo, 'common/clickhouse-migrations/new/x.sql')), 'deny')

    def test_existing_file_and_other_dirs_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp, WF, {'common/migrations/1-a.ts': 'x\n'})
            self.assertIsNone(write(os.path.join(repo, 'common/migrations/1-a.ts')))
            self.assertIsNone(write(os.path.join(repo, 'src/main.ts')))

    def test_no_config_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp, None, {'common/migrations/1-a.ts': 'x\n'})
            self.assertIsNone(write(os.path.join(repo, 'common/migrations/2-b.ts')))

    def test_no_config_silent_everywhere(self):
        self.assertIsNone(write('/anything/database/migrations/2099_01_01_000000_x.php'))


if __name__ == '__main__':
    unittest.main()
