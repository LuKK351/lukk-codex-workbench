#!/usr/bin/env python3
"""macOS-only isolated LaunchServices/launchd check. Creates and removes one test job."""
import json
import os
from pathlib import Path
import plistlib
import shlex
import signal
import socket
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch
from initialize import initialize
import desktop
import launcher


def wait_ready(root, config):
    for _ in range(100):
        result = launcher.probe(root, config)
        if result['status'] == 'ready':
            return result['pid']
        time.sleep(.1)
    raise AssertionError('Native entry did not start the workbench')


def main():
    if sys.platform != 'darwin':
        raise SystemExit('This test exercises macOS LaunchServices and launchd only.')
    with tempfile.TemporaryDirectory(prefix='workbench-native-test-') as temporary:
        base = Path(temporary)
        root = base / "中文 ' 工作台"
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]
        config = initialize(root, '2026-01-01', '2026-01-02', 'Asia/Shanghai', port)
        browser = base / 'TestBrowser.app'
        (browser / 'Contents/MacOS').mkdir(parents=True)
        (browser / 'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleExecutable': 'browser', 'CFBundlePackageType': 'APPL', 'CFBundleIdentifier': 'com.lukk.testbrowser.' + config['workbenchId']}))
        marker = base / 'browser-opened'
        executable = browser / 'Contents/MacOS/browser'
        executable.write_text('#!/bin/sh\ntouch ' + shlex.quote(str(marker)) + '\n'); executable.chmod(0o755)
        pids = set()
        target = 'gui/' + str(os.getuid()) + '/com.lukk.workbench.' + config['workbenchId']
        try:
            with patch.object(Path, 'home', return_value=base / 'home'):
                entry = desktop.install(root, base / 'Desktop', browser=str(browser))['entry']
                subprocess.run(['/usr/bin/open', '-n', entry], check=True, timeout=15)
                pid = wait_ready(root, config); pids.add(pid)
                for _ in range(100):
                    if marker.exists(): break
                    time.sleep(.1)
                assert marker.exists(), 'Selected browser was not opened by the app entry'
                subprocess.run(['/usr/bin/open', '-n', entry], check=True, timeout=15)
                time.sleep(.5)
                assert wait_ready(root, config) == pid, 'Repeated entry created another server'
                result = desktop.set_login(root, True)
                os.kill(pid, signal.SIGTERM); pids.discard(pid)
                for _ in range(100):
                    if launcher.probe(root, config)['status'] == 'stopped': break
                    time.sleep(.05)
                marker.unlink()
                # Load the exact generated login job in the current GUI session.
                subprocess.run(['/bin/launchctl', 'bootstrap', 'gui/' + str(os.getuid()), result['path']], check=True, timeout=15)
                login_pid = wait_ready(root, config); pids.add(login_pid)
                time.sleep(.5)
                assert not marker.exists(), 'Login startup opened a browser'
                desktop.set_login(root, False)
                assert launcher.probe(root, config)['status'] == 'ready', 'Disabling startup killed the reading service'
                desktop.uninstall(root)
                assert not Path(entry).exists()
                assert not Path(result['path']).exists()
            print(json.dumps({'platform': 'macOS', 'nativeAppOpensSelectedBrowser': True,
                              'repeatedOpenReusesService': True, 'launchdStartsWithoutBrowser': True,
                              'serviceSurvivesLauncherAndJobExit': True, 'uninstallPreservesData': (root / 'data.json').is_file(),
                              'fullLogoutLoginTested': False}, ensure_ascii=False, indent=2))
        finally:
            subprocess.run(['/bin/launchctl', 'bootout', target], capture_output=True, timeout=15)
            for pid in pids:
                try: os.kill(pid, signal.SIGTERM)
                except ProcessLookupError: pass


if __name__ == '__main__':
    main()
