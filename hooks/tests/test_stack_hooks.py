import os
import tempfile
import unittest

from tests.helpers import decision, make_repo, run_hook

PHP_OK = "<?php\n\ndeclare(strict_types=1);\n\nfinal class A {}\n"
PHP_NO_DECLARE = "<?php\n\nfinal class A {}\n"
PHP_LOOSE = "<?php\n\ndeclare(strict_types=1);\n\nif ($a == 1) {}\n"
ALL = '## Код\n- hooks: `Strict_Types , php_house_rules`\n'


def write(path, content):
    return {'tool_name': 'Write', 'tool_input': {'file_path': path, 'content': content}}


class StrictTypesTest(unittest.TestCase):
    def test_denied_when_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp, ALL)
            self.assertEqual(decision(run_hook('require-strict-types.py', write(os.path.join(repo, 'a.php'), PHP_NO_DECLARE))), 'deny')
            self.assertIsNone(run_hook('require-strict-types.py', write(os.path.join(repo, 'a.php'), PHP_OK)))

    def test_edit_removing_declare_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp, ALL)
            out = run_hook('require-strict-types.py', {'tool_name': 'Edit', 'tool_input': {
                'file_path': os.path.join(repo, 'a.php'), 'old_string': 'declare(strict_types=1);', 'new_string': ''}})
            self.assertEqual(decision(out), 'deny')

    def test_silent_without_key_or_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp, '## Код\n- hooks: `php_house_rules`\n')
            self.assertIsNone(run_hook('require-strict-types.py', write(os.path.join(repo, 'a.php'), PHP_NO_DECLARE)))
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp, None)
            self.assertIsNone(run_hook('require-strict-types.py', write(os.path.join(repo, 'a.php'), PHP_NO_DECLARE)))


    def test_blade_and_vendor_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp, ALL)
            self.assertIsNone(run_hook('require-strict-types.py', write(os.path.join(repo, 'resources/views/x.blade.php'), PHP_NO_DECLARE)))
            self.assertIsNone(run_hook('require-strict-types.py', write(os.path.join(repo, 'vendor/a.php'), PHP_NO_DECLARE)))


class HouseRulesTest(unittest.TestCase):
    def test_repo_inside_vendor_dir_still_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            outer = os.path.join(tmp, 'vendor')
            os.makedirs(outer)
            repo = make_repo(outer, ALL)
            out = run_hook('php-house-rules.py', write(os.path.join(repo, 'app/A.php'), PHP_LOOSE))
            self.assertEqual(out['decision'], 'block')
            self.assertIsNone(run_hook('php-house-rules.py', write(os.path.join(repo, 'vendor/a.php'), PHP_LOOSE)))


    def test_blocks_loose_comparison_when_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp, ALL)
            out = run_hook('php-house-rules.py', write(os.path.join(repo, 'a.php'), PHP_LOOSE))
            self.assertEqual(out['decision'], 'block')
            self.assertIn('нестрогое сравнение', out['reason'])

    def test_loose_comparison_reports_both_violations(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp, ALL)
            out = run_hook('php-house-rules.py', write(os.path.join(repo, 'a.php'), PHP_LOOSE))
            self.assertIn('нестрогое сравнение', out['reason'])
            self.assertIn('не Yoda: $a == 1 → 1 == $a', out['reason'])

    def test_silent_for_blade_vendor_and_without_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp, ALL)
            self.assertIsNone(run_hook('php-house-rules.py', write(os.path.join(repo, 'x.blade.php'), PHP_LOOSE)))
            self.assertIsNone(run_hook('php-house-rules.py', write(os.path.join(repo, 'vendor/a.php'), PHP_LOOSE)))
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp, None)
            self.assertIsNone(run_hook('php-house-rules.py', write(os.path.join(repo, 'a.php'), PHP_LOOSE)))


if __name__ == '__main__':
    unittest.main()
