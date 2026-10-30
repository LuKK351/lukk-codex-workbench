#!/usr/bin/env python3
"""Open the same local workbench, starting its reader service when necessary."""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.parse import urlsplit
from urllib.request import build_opener, ProxyHandler
import webbrowser


def identity(root, config):
    return {'workbenchId': config.get('workbenchId'),
            'rootHash': hashlib.sha256(os.path.normcase(str(Path(root).resolve())).encode()).hexdigest()}


def settings(root):
    root = Path(root).resolve()
    config = json.loads((root / 'config/workbench.json').read_text(encoding='utf-8'))
    url = urlsplit(config['url'])
    if (url.scheme != 'http' or url.hostname not in ('localhost', '127.0.0.1') or
            url.port != config['port'] or url.path not in ('', '/') or
            url.username or url.password or url.query or url.fragment):
        raise ValueError('工作台地址配置异常，请让 Codex 检查；不会自动更换地址。')
    if not config.get('workbenchId'):
        raise ValueError('尚未配置固定入口，请让 Codex 为这个已有工作台安装打开入口。')
    for name in ('index.html', 'app.js', 'core.js', 'style.css', 'data.json'):
        if not (root / name).is_file():
            raise ValueError('工作台文件缺失：' + name + '。请让 Codex 恢复文件，不必重新整理。')
    return config


def probe(root, config):
    # Bypass proxy environment settings for a strictly local service.
    try:
        with build_opener(ProxyHandler({})).open(config['url'].rstrip('/') + '/__workbench_health', timeout=1) as r:
            health = json.loads(r.read(8192))
        if isinstance(health, dict) and all(health.get(k) == v for k, v in identity(root, config).items()):
            return {'status': 'ready', 'pid': health.get('pid'), 'url': config['url']}
    except (OSError, ValueError):
        pass
    try:
        with socket.create_connection(('127.0.0.1', config['port']), timeout=0.3):
            return {'status': 'conflict', 'url': config['url']}
    except OSError:
        return {'status': 'stopped', 'url': config['url']}


@contextmanager
def startup_lock(root, timeout=15):
    # Separate from the publication lock: opening never blocks data publication.
    from workbench import lock_file
    path = Path(root) / '.workbench/launcher.lock'
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as f:
        if f.tell() == 0:
            f.write(b'0'); f.flush()
        deadline = time.monotonic() + timeout
        while True:
            try:
                lock_file(f)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise ValueError('另一个打开操作尚未完成，请稍后再点一次入口。')
                time.sleep(0.1)
        try:
            yield
        finally:
            lock_file(f, unlock=True)


def detached_options(platform=None):
    if (platform or sys.platform) == 'win32':
        # Windows CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS; no console/job UI.
        return {'creationflags': 0x00000200 | 0x00000008, 'close_fds': True}
    return {'start_new_session': True, 'close_fds': True}


def ensure(root):
    root = Path(root).resolve()
    config = settings(root)
    with startup_lock(root):
        result = probe(root, config)
        if result['status'] == 'ready':
            return result
        if result['status'] == 'conflict':
            raise ValueError('原网页地址被其他程序或旧版服务占用。请把此提示交给 Codex 核对；不会停掉其他程序，也不会更改收藏所在的地址。')
        python = Path(config['pythonExecutable'])
        if not python.is_file():
            raise ValueError('原 Python 运行环境已不存在，请让 Codex 修复打开入口。已整理内容仍在原目录。')
        log_path = root / '.workbench/service.log'
        if log_path.exists() and log_path.stat().st_size > 1_000_000:
            log_path.replace(log_path.with_suffix('.previous.log'))
        with log_path.open('ab') as log:
            child = subprocess.Popen([str(python), str(root / 'scripts/serve.py'), str(root),
                                      '--port', str(config['port'])], stdin=subprocess.DEVNULL,
                                     stdout=log, stderr=log, **detached_options())
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            result = probe(root, config)
            if result['status'] == 'ready':
                return result
            if child.poll() is not None:
                raise ValueError('工作台没有成功启动。请让 Codex 检查 .workbench/service.log；已有内容无需重新整理。')
            time.sleep(0.15)
        # Only terminate the exact process we just created, never a PID from disk.
        child.terminate()
        child.wait(timeout=5)
        raise ValueError('工作台启动超时。请把启动诊断交给 Codex，已有内容不会被覆盖。')


def open_browser(url, browser=None):
    if browser:
        path = Path(browser)
        if not path.exists():
            raise ValueError('之前选择的浏览器已找不到，请让 Codex 重新选择；不会自动切换浏览器，以免看不到原收藏。')
        if sys.platform == 'darwin':
            subprocess.run(['/usr/bin/open', '-a', str(path), url], check=True, timeout=15)
        else:
            subprocess.Popen([str(path), url], stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif not webbrowser.open(url):
        raise ValueError('网页服务已经启动，但浏览器未能打开。请在常用浏览器访问：' + url)


def show_error(message):
    try:
        if sys.platform == 'darwin':
            code = 'on run argv\ndisplay dialog (item 1 of argv) with title "Codex 工作台暂时无法打开" buttons {"好"} default button 1\nend run'
            subprocess.run(['/usr/bin/osascript', '-e', code, message], timeout=60, check=False)
        elif sys.platform == 'win32':
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, message, 'Codex 工作台暂时无法打开', 0x10)
    except (OSError, subprocess.SubprocessError):
        pass


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root')
    p.add_argument('--ensure-only', action='store_true', help='Start without opening a browser')
    p.add_argument('--status', action='store_true')
    p.add_argument('--gui', action='store_true', help='Show actionable errors in a native dialog')
    a = p.parse_args()
    root = Path(a.root).resolve()
    try:
        if a.status:
            result = probe(root, settings(root))
        else:
            result = ensure(root)
            if not a.ensure_only:
                open_browser(result['url'], settings(root).get('browserApplication'))
        if sys.stdout:
            print(json.dumps(result, ensure_ascii=False))
        return 0 if result['status'] == 'ready' else 2
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        message = str(exc)
        diagnostic = root / '.workbench/launcher-error.txt'
        try:
            diagnostic.parent.mkdir(parents=True, exist_ok=True)
            diagnostic.write_text('请帮我修复已有 Codex 工作台的打开入口，不要重新初始化。\n工作台：' + str(root) +
                                  '\n问题：' + message + '\n', encoding='utf-8')
            message += '\n\n启动诊断已保存：' + str(diagnostic) + '\n可将这份文件交给 Codex。'
        except OSError:
            message += '\n请将此提示交给 Codex 检查原工作台路径。'
        if sys.stderr:
            print(message, file=sys.stderr)
        if a.gui:
            show_error(message)
        return 1


if __name__ == '__main__':
    sys.exit(main())
