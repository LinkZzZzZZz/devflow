import json
import os
import shutil
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

CLIENT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                      'skills', 'tracker', 'youtrack.mjs')
TOKEN = 'perm:test'


class Handler(BaseHTTPRequestHandler):
    seen = []

    def log_message(self, *args):
        pass

    def reply(self, code, body, kind='application/json'):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        Handler.seen.append((self.path, self.headers.get('Authorization')))
        if self.headers.get('Authorization') != 'Bearer ' + TOKEN:
            return self.reply(401, {'error': 'unauthorized'})
        if self.path.startswith('/api/users/me'):
            return self.reply(200, {'login': 'egor', 'name': 'Egor'})
        if self.path.startswith('/api/issues/T-7/attachments?fields='):
            return self.reply(200, [
                {'id': '1-1', 'name': 'shot.png', 'size': 3, 'url': '/api/files/1-1?sign=abc', 'comment': None},
                {'id': '1-2', 'name': 'shot.png', 'size': 3, 'url': '/youtrack/api/files/1-2?sign=def',
                 'comment': {'id': '4-1'}},
                {'id': '1-3', 'name': 'gone.txt', 'removed': True, 'url': '/api/files/1-3?sign=x'},
                {'id': '1-4', 'name': 'secret.txt', 'url': None},
                {'id': '1-5', 'name': 'broken.txt', 'url': '/api/files/1-5?sign=bad'},
            ])
        if self.path == '/api/files/1-1?sign=abc':
            return self.reply(200, b'one', 'image/png')
        if self.path == '/api/files/1-2?sign=def':
            return self.reply(200, b'two', 'image/png')
        return self.reply(404, {'error': 'not found'})


@unittest.skipUnless(shutil.which('node'), 'нет node')
class YoutrackClientTest(unittest.TestCase):
    def setUp(self):
        self.server = HTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env_file = os.path.join(self.tmp.name, '.env')
        with open(self.env_file, 'w') as handle:
            handle.write('YOUTRACK_URL=http://127.0.0.1:%d/\nYOUTRACK_TOKEN="%s"\n' % (self.server.server_port, TOKEN))
        Handler.seen = []

    def run_client(self, *args):
        env = dict(os.environ, DEVFLOW_ENV=self.env_file)
        result = subprocess.run(['node', CLIENT, *args], capture_output=True, text=True, env=env, timeout=30)
        return result.returncode, result.stdout, result.stderr

    def test_check_uses_bearer_token(self):
        code, out, _ = self.run_client('check')
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)['login'], 'egor')
        self.assertEqual(Handler.seen[0], ('/api/users/me?fields=login,name', 'Bearer ' + TOKEN))

    def test_attachments_saved_and_failures_named(self):
        out_dir = os.path.join(self.tmp.name, 'attachments')
        code, out, err = self.run_client('attachments', '--key', 'T-7', '--out', out_dir)
        self.assertEqual(code, 0, err)
        result = json.loads(out)
        self.assertEqual(result['count'], 2)
        by_file = {os.path.basename(s['file']): s for s in result['saved'] if 'file' in s}
        self.assertEqual(sorted(by_file), ['shot-1-2.png', 'shot.png'])
        with open(os.path.join(out_dir, 'shot.png'), 'rb') as handle:
            self.assertEqual(handle.read(), b'one')
        with open(os.path.join(out_dir, 'shot-1-2.png'), 'rb') as handle:
            self.assertEqual(handle.read(), b'two')
        self.assertEqual(by_file['shot-1-2.png']['comment'], '4-1')
        errors = {s['name']: s['error'] for s in result['saved'] if 'error' in s}
        self.assertEqual(sorted(errors), ['broken.txt', 'secret.txt'])
        self.assertIn('404', errors['broken.txt'])
        self.assertNotIn('gone.txt', [s['name'] for s in result['saved']])
        self.assertNotIn('sign=bad', errors['broken.txt'])

    def test_missing_credentials_fail_loudly(self):
        with open(self.env_file, 'w') as handle:
            handle.write('YOUTRACK_URL=\n')
        code, _, err = self.run_client('check')
        self.assertEqual(code, 2)
        self.assertIn('YOUTRACK_TOKEN', err)


if __name__ == '__main__':
    unittest.main()
