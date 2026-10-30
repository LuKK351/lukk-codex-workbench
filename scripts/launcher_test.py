#!/usr/bin/env python3
"""Isolated launch/restart/concurrency tests; no private chats or real login entries."""
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import plistlib
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from initialize import initialize
import desktop
import launcher


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='workbench-launch-test-')
        self.base = Path(self.temp.name)
        self.root = self.base / "中文 空格 ' $ 工作台"
        self.config = initialize(self.root, '2026-01-01', '2026-01-02', 'Asia/Shanghai', free_port())
        self.script = self.root / 'scripts/launcher.py'
        self.before = (self.root / 'data.json').read_bytes()
        self.children = set()

    def track(self, result):
        self.children.add(result['pid'])
        return result

    def stop(self, pid):
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        for _ in range(50):
            if launcher.probe(self.root, self.config)['status'] == 'stopped':
                break
            time.sleep(.05)
        self.children.discard(pid)

    def tearDown(self):
        for pid in list(self.children):
            self.stop(pid)
        self.assertEqual((self.root / 'data.json').read_bytes(), self.before)
        self.temp.cleanup()

    def test_starts_survives_parent_exit_reuses_and_recovers(self):
        first = subprocess.run([sys.executable, str(self.script), str(self.root), '--ensure-only'], capture_output=True, text=True, check=True)
        result = self.track(json.loads(first.stdout))
        self.assertEqual(launcher.probe(self.root, self.config)['pid'], result['pid'])
        self.assertEqual(launcher.ensure(self.root)['pid'], result['pid'])
        self.stop(result['pid'])
        recovered = self.track(launcher.ensure(self.root))
        self.assertNotEqual(recovered['pid'], result['pid'])
        self.assertEqual(recovered['url'], self.config['url'])
        self.assertEqual(json.loads((self.root / 'config/workbench.json').read_text(encoding='utf-8'))['url'], self.config['url'])

    def test_simultaneous_clicks_share_one_service(self):
        processes = [subprocess.Popen([sys.executable, str(self.script), str(self.root), '--ensure-only'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(4)]
        results = []
        for process in processes:
            out, err = process.communicate(timeout=25)
            self.assertEqual(process.returncode, 0, err)
            results.append(self.track(json.loads(out)))
        self.assertEqual(len({r['pid'] for r in results}), 1)

    def test_conflicting_service_is_not_stopped_or_silently_moved(self):
        class Other(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200); self.end_headers(); self.wfile.write(b'[]')
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(('127.0.0.1', self.config['port']), Other)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            with self.assertRaisesRegex(ValueError, '占用'):
                launcher.ensure(self.root)
            self.assertEqual(launcher.probe(self.root, self.config)['status'], 'conflict')
            self.assertEqual(json.loads((self.root / 'config/workbench.json').read_text(encoding='utf-8'))['port'], self.config['port'])
        finally:
            server.shutdown(); server.server_close(); thread.join()

    def test_failure_saves_diagnostic_and_does_not_open_browser(self):
        self.config['pythonExecutable'] = str(self.base / 'missing-python')
        (self.root / 'config/workbench.json').write_text(json.dumps(self.config))
        with patch.object(sys, 'argv', ['launcher.py', str(self.root)]), patch.object(launcher, 'open_browser') as browser:
            self.assertEqual(launcher.main(), 1)
            browser.assert_not_called()
        text = (self.root / '.workbench/launcher-error.txt').read_text(encoding='utf-8')
        self.assertIn('不要重新初始化', text)
        self.assertIn('运行环境已不存在', text)

    def test_config_rejects_remote_or_changed_origin_and_missing_browser(self):
        for url in ('https://example.org/', 'http://127.0.0.1:9999/', self.config['url'] + '?remote=true'):
            changed = dict(self.config, url=url)
            (self.root / 'config/workbench.json').write_text(json.dumps(changed))
            with self.assertRaisesRegex(ValueError, '地址配置'):
                launcher.settings(self.root)
        with patch.object(launcher.webbrowser, 'open') as default:
            with self.assertRaisesRegex(ValueError, '浏览器已找不到'):
                launcher.open_browser(self.config['url'], str(self.base / 'removed-browser'))
            default.assert_not_called()

    @unittest.skipUnless(sys.platform == 'darwin', 'macOS artifact test')
    def test_mac_install_login_disable_and_uninstall_preserve_data(self):
        home = self.base / 'home'
        with patch.object(Path, 'home', return_value=home):
            installed = desktop.install(self.root)
            entry = Path(installed['entry'])
            self.assertTrue(entry.is_dir())
            self.assertEqual(desktop.install(self.root)['entry'], str(entry))
            plist = plistlib.loads((entry / 'Contents/Info.plist').read_bytes())
            self.assertEqual(plist['CFBundleExecutable'], 'open-workbench')
            self.assertTrue(os.access(entry / 'Contents/MacOS/open-workbench', os.X_OK))
            subprocess.run(['/bin/sh', '-n', str(entry / 'Contents/MacOS/open-workbench')], check=True)
            self.track(launcher.ensure(self.root))
            result = desktop.set_login(self.root, True)
            job = plistlib.loads(Path(result['path']).read_bytes())
            self.assertIn('--ensure-only', job['ProgramArguments'])
            self.assertNotIn('--gui', job['ProgramArguments'])
            self.assertTrue(job['RunAtLoad'])
            self.assertTrue(job['AbandonProcessGroup'])
            self.assertNotIn('KeepAlive', job)
            alternative = self.base / 'alternate-python'
            alternative.symlink_to(self.config['pythonExecutable'])
            updated = dict(self.config, pythonExecutable=str(alternative))
            (self.root / 'config/workbench.json').write_text(json.dumps(updated))
            desktop.install(self.root)
            refreshed = plistlib.loads(Path(result['path']).read_bytes())
            self.assertEqual(refreshed['ProgramArguments'][0], str(alternative))
            alternative.unlink()
            with self.assertRaisesRegex(ValueError, 'Python 已失效'):
                desktop.set_login(self.root, True)
            desktop.set_login(self.root, False)
            self.assertFalse(Path(result['path']).exists())
            self.assertEqual(launcher.probe(self.root, self.config)['status'], 'ready')
            desktop.uninstall(self.root)
            desktop.uninstall(self.root)
            desktop.set_login(self.root, False)
            self.assertFalse(entry.exists())
            self.assertEqual(launcher.probe(self.root, self.config)['status'], 'ready')

    @unittest.skipUnless(sys.platform == 'darwin', 'macOS artifact test')
    def test_install_does_not_overwrite_other_entry_or_modified_artifact(self):
        directory = self.base / 'Desktop'; directory.mkdir()
        other = directory / (desktop.TITLE + '.app'); other.mkdir()
        (other / 'private.txt').write_text('leave me')
        installed = desktop.install(self.root, directory)
        self.assertNotEqual(installed['entry'], str(other))
        self.assertEqual((other / 'private.txt').read_text(encoding='utf-8'), 'leave me')
        entry = Path(installed['entry'])
        (entry / 'user-note.txt').write_text('preserve')
        with self.assertRaisesRegex(ValueError, '手动修改'):
            desktop.uninstall(self.root)
        self.assertTrue(entry.exists())

    def test_windows_bootstrap_quotes_unicode_and_missing_runtime_fallback(self):
        # Generate Windows host commands on any OS; COM is exercised only on Windows.
        fakepython = self.base / "Python ' 空格" / 'python.exe'
        fakepython.parent.mkdir(); fakepython.touch(); fakepython.with_name('pythonw.exe').touch()
        config = dict(self.config, pythonExecutable=str(fakepython))
        code = desktop.bootstrap_windows(self.root, config, quiet=True)
        self.assertIn("''", code)
        self.assertIn('--ensure-only', code)
        self.assertIn('Test-Path -LiteralPath', code)
        self.assertIn('MessageBox', code)
        args = desktop.powershell_args(code)
        self.assertEqual(base64.b64decode(args[-1]).decode('utf-16le'), code)
        self.assertEqual(launcher.detached_options('win32')['creationflags'], 0x208)
        fakepython.with_name('pythonw.exe').unlink()
        with self.assertRaisesRegex(ValueError, 'pythonw'):
            desktop.bootstrap_windows(self.root, config)

    @unittest.skipUnless(sys.platform == 'win32', 'Windows native shortcut round-trip')
    def test_windows_shortcut_roundtrip_and_native_launch(self):
        installed = desktop.install(self.root, self.base / '桌面')
        entry = Path(installed['entry'])
        output = desktop.powershell("[Console]::OutputEncoding=[Text.UTF8Encoding]::new(); $s=(New-Object -ComObject WScript.Shell).CreateShortcut(" + desktop.ps_literal(entry) + "); @{target=$s.TargetPath; args=$s.Arguments} | ConvertTo-Json -Compress")
        shortcut = json.loads(output)
        self.assertTrue(shortcut['target'].lower().endswith('powershell.exe'))
        # Quiet variant uses the same bootstrap without opening a real browser.
        quiet = self.base / '登录入口.lnk'
        desktop.shortcut(quiet, self.root, self.config, quiet=True)
        os.startfile(str(quiet))
        for _ in range(100):
            result = launcher.probe(self.root, self.config)
            if result['status'] == 'ready':
                self.track(result); break
            time.sleep(.1)
        else:
            self.fail('Windows shortcut did not start the workbench')
        desktop.uninstall(self.root)
        self.assertFalse(entry.exists())

    def test_runtime_copies_are_current(self):
        scripts = Path(__file__).resolve().parent
        for name in ('launcher.py', 'serve.py'):
            self.assertEqual((scripts / name).read_bytes(), (self.root / 'scripts' / name).read_bytes())


if __name__ == '__main__':
    unittest.main(verbosity=2)
