#!/usr/bin/env python3
"""Install/remove per-user macOS or Windows launchers and optional login startup."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shlex
import shutil
import subprocess
import sys
import uuid
from workbench import atomic, encode, configure_console
from launcher import settings, ensure

TITLE = '打开 Codex 工作台'


def ps_literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def powershell_args(code):
    return ['-NoProfile', '-NonInteractive', '-WindowStyle', 'Hidden', '-EncodedCommand',
            base64.b64encode(code.encode('utf-16le')).decode('ascii')]


def powershell(code):
    result = subprocess.run(['powershell.exe', *powershell_args("$ErrorActionPreference='Stop';\n" + code)],
                            capture_output=True, timeout=30)
    if result.returncode:
        detail = result.stderr.decode('utf-8', errors='replace')[-4000:]
        raise ValueError('Windows 入口操作失败：' + detail)
    # Explicit UTF-8 console output avoids the user's legacy console code page.
    return result.stdout.decode('utf-8-sig').strip()


def win_folder(kind):
    value = powershell("[Console]::OutputEncoding=[Text.UTF8Encoding]::new(); "
                       f"[Environment]::GetFolderPath([Environment+SpecialFolder]::{kind})")
    if not value:
        raise ValueError('系统未提供 ' + kind + ' 路径，请让 Codex 检查。')
    return Path(value)


def fingerprint(path):
    path = Path(path)
    if path.is_symlink():
        raise ValueError('入口已被替换为符号链接，保留原文件，请先核对：' + str(path))
    if not path.exists():
        return None
    if path.is_file():
        return hashlib.sha256(path.read_bytes()).hexdigest()
    h = hashlib.sha256()
    for child in sorted(path.rglob('*')):
        if child.is_symlink():
            raise ValueError('入口内出现符号链接，请先核对：' + str(child))
        if child.is_file():
            h.update(str(child.relative_to(path)).encode()); h.update(b'\0'); h.update(child.read_bytes())
    return h.hexdigest()


def assert_owned(path, manifest):
    actual = fingerprint(path)
    if actual is not None and manifest.get('files', {}).get(str(path)) != actual:
        raise ValueError('入口文件已有其他内容或被手动修改，未覆盖/删除：' + str(path))


def remember(root, manifest, path):
    manifest.setdefault('files', {})[str(path)] = fingerprint(path)
    atomic(root / '.workbench/desktop.json', encode(manifest))


def remove_owned(root, manifest, path):
    path = Path(path)
    assert_owned(path, manifest)
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()
    manifest.setdefault('files', {}).pop(str(path), None)
    atomic(root / '.workbench/desktop.json', encode(manifest))


def bootstrap_windows(root, config, quiet=False):
    python = Path(config['pythonExecutable']).with_name('pythonw.exe')
    if not python.is_file():
        raise ValueError('当前 Python 缺少 pythonw.exe，无法创建无终端窗口的入口；请让 Codex 修复 Python 环境。')
    args = [str(root / 'scripts/launcher.py'), str(root), '--gui']
    if quiet:
        args.append('--ensure-only')
    checks = [str(python), str(root / 'scripts/launcher.py'), str(root / 'config/workbench.json')]
    array = ','.join(ps_literal(v) for v in checks)
    message = '工作台文件或原运行环境已找不到。请让 Codex 修复已有工作台的打开入口，不要重新初始化。'
    return ("$ErrorActionPreference='Stop'; try {\n"
            f"foreach ($p in @({array})) {{ if (!(Test-Path -LiteralPath $p)) {{ throw {ps_literal(message)} }} }}\n"
            f"& {ps_literal(python)} " + ' '.join(ps_literal(a) for a in args) + "\n} catch {\n"
            "Add-Type -AssemblyName System.Windows.Forms; "
            "[System.Windows.Forms.MessageBox]::Show($_.Exception.Message, 'Codex 工作台暂时无法打开') | Out-Null\n}")


def shortcut(path, root, config, quiet=False):
    code = bootstrap_windows(root, config, quiet)
    args = subprocess.list2cmdline(powershell_args(code))
    # Resolve redirected Desktop/Startup through Windows, never assume ~/Desktop.
    powershell("$s=(New-Object -ComObject WScript.Shell).CreateShortcut(" + ps_literal(path) + ");\n"
               "$s.TargetPath=(Get-Command powershell.exe).Source;\n"
               "$s.Arguments=" + ps_literal(args) + ";\n"
               "$s.WorkingDirectory=" + ps_literal(root) + ";\n"
               "$s.Description='打开 Codex 对话整理工作台'; $s.WindowStyle=7; $s.Save();\n"
               "if (!(Test-Path -LiteralPath " + ps_literal(path) + ")) { throw '快捷方式创建失败' }")


def mac_app(path, root, config):
    (path / 'Contents/MacOS').mkdir(parents=True)
    info = {'CFBundleName': TITLE, 'CFBundleDisplayName': TITLE, 'CFBundlePackageType': 'APPL',
            'CFBundleExecutable': 'open-workbench', 'CFBundleIdentifier': 'com.lukk.workbench.' + config['workbenchId'],
            'CFBundleVersion': '1', 'LSUIElement': True, 'NSHighResolutionCapable': True}
    (path / 'Contents/Info.plist').write_bytes(plistlib.dumps(info))
    python = shlex.quote(config['pythonExecutable'])
    launcher = shlex.quote(str(root / 'scripts/launcher.py'))
    root_arg = shlex.quote(str(root))
    script = (f'#!/bin/sh\nif [ ! -x {python} ] || [ ! -f {launcher} ]; then\n'
              '/usr/bin/osascript -e \'display dialog "工作台文件或原运行环境已找不到。请让 Codex 修复已有工作台的打开入口，不要重新初始化。" '
              'with title "Codex 工作台暂时无法打开" buttons {"好"} default button 1\'\nexit 1\nfi\n'
              f'exec {python} {launcher} {root_arg} --gui\n')
    executable = path / 'Contents/MacOS/open-workbench'
    executable.write_text(script, encoding='utf-8'); executable.chmod(0o755)


def login_path(config, platform):
    if platform == 'darwin':
        return Path.home() / 'Library/LaunchAgents' / ('com.lukk.workbench.' + config['workbenchId'] + '.plist')
    return win_folder('Startup') / (TITLE + '-' + config['workbenchId'][:8] + '.lnk')


def mac_login(config, root):
    return {'Label': 'com.lukk.workbench.' + config['workbenchId'],
            'ProgramArguments': [config['pythonExecutable'], str(root / 'scripts/launcher.py'), str(root), '--ensure-only'],
            'RunAtLoad': True, 'AbandonProcessGroup': True,
            'StandardOutPath': str(root / '.workbench/login.log'),
            'StandardErrorPath': str(root / '.workbench/login-error.log')}


def load(root):
    root = Path(root).expanduser().resolve()
    path = root / 'config/workbench.json'
    config = json.loads(path.read_text(encoding='utf-8'))
    manifest_path = root / '.workbench/desktop.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {'version': 1, 'files': {}}
    return root, config, manifest


def check_runtime(root, config):
    python = Path(config['pythonExecutable'])
    if not python.is_file():
        raise ValueError('配置中的 Python 已失效，请先修复运行环境。')
    subprocess.run([str(python), '-c', 'import sys, zoneinfo; assert sys.version_info >= (3, 9)'],
                   stdin=subprocess.DEVNULL, capture_output=True, check=True, timeout=15)
    for name in ('launcher.py', 'serve.py', 'workbench.py'):
        if not (root / 'scripts' / name).is_file():
            raise ValueError('运行脚本缺失：' + name + '，请先升级已有工作台运行脚本。')


def install(root, entry_dir=None, browser=None):
    platform = sys.platform
    if platform not in ('darwin', 'win32'):
        raise ValueError('系统入口目前支持 macOS 和 Windows；Linux 可继续使用 launcher.py 打开。')
    root, config, manifest = load(root)
    check_runtime(root, config)
    if not config.get('workbenchId'):
        atomic(root / '.workbench/config-before-desktop.json', encode(config))
        config['workbenchId'] = str(uuid.uuid4())
    if browser is not None:
        if browser != 'default' and not Path(browser).exists():
            raise ValueError('指定的浏览器不存在。')
        if browser == 'default':
            config.pop('browserApplication', None)
        else:
            config['browserApplication'] = str(Path(browser).resolve())
    atomic(root / 'config/workbench.json', encode(config))
    settings(root)
    if not (root / 'scripts/launcher.py').is_file():
        raise ValueError('尚未升级工作台运行脚本，请先按打开与维护流程同步 launcher.py 和 serve.py。')
    if manifest.get('entry'):
        path = Path(manifest['entry'])
        if entry_dir and path.parent != Path(entry_dir).expanduser().resolve():
            raise ValueError('已有入口位于其他位置，请先卸载入口后再选择新位置。')
    else:
        parent = Path(entry_dir).expanduser().resolve() if entry_dir else (Path.home() / 'Desktop' if platform == 'darwin' else win_folder('DesktopDirectory'))
        suffix = '.app' if platform == 'darwin' else '.lnk'
        path = parent / (TITLE + suffix)
        if path.exists():
            path = parent / (TITLE + '-' + config['workbenchId'][:8] + suffix)
    assert_owned(path, manifest)
    if path.exists():
        remove_owned(root, manifest, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if platform == 'darwin':
        mac_app(path, root, config)
    else:
        shortcut(path, root, config)
    manifest['entry'] = str(path)
    remember(root, manifest, path)
    if manifest.get('loginEnabled'):
        set_login(root, True)  # Repair the selected login entry alongside its desktop entry.
    return {'entry': str(path), 'url': config['url'], 'login': manifest.get('loginEnabled', False)}


def set_login(root, enabled):
    if sys.platform not in ('darwin', 'win32'):
        raise ValueError('登录后自动启动目前支持 macOS 和 Windows。')
    root, config, manifest = load(root)
    if enabled and (not manifest.get('entry') or not config.get('workbenchId')):
        raise ValueError('请先安装固定打开入口。')
    if not enabled and not manifest.get('loginPath'):
        return {'loginEnabled': False, 'takesEffect': 'disabled'}
    path = Path(manifest['loginPath']) if manifest.get('loginPath') else login_path(config, sys.platform)
    assert_owned(path, manifest)
    if enabled:
        check_runtime(root, config)
        # Verify service startup now; the login trigger itself runs on next login.
        ensure(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        if sys.platform == 'darwin':
            atomic(path, plistlib.dumps(mac_login(config, root)))
        else:
            shortcut(path, root, config, quiet=True)
        manifest.update(loginEnabled=True, loginPath=str(path))
        remember(root, manifest, path)
    else:
        if sys.platform == 'darwin':
            target = 'gui/' + str(os.getuid()) + '/com.lukk.workbench.' + config['workbenchId']
            found = subprocess.run(['/bin/launchctl', 'print', target], capture_output=True, timeout=15)
            if found.returncode == 0:
                subprocess.run(['/bin/launchctl', 'bootout', target], capture_output=True, check=True, timeout=15)
        remove_owned(root, manifest, path)
        manifest['loginEnabled'] = False
        atomic(root / '.workbench/desktop.json', encode(manifest))
    return {'loginEnabled': enabled, 'path': str(path), 'takesEffect': 'next_login' if enabled else 'disabled'}


def uninstall(root):
    root, config, manifest = load(root)
    # Check all artifacts before deleting any. Never remove data or user edits.
    for path in manifest.get('files', {}):
        assert_owned(Path(path), manifest)
    if manifest.get('loginPath'):
        set_login(root, False)
        root, config, manifest = load(root)
    for path in list(manifest.get('files', {})):
        remove_owned(root, manifest, path)
    manifest.pop('entry', None)
    manifest['loginEnabled'] = False
    atomic(root / '.workbench/desktop.json', encode(manifest))
    return {'removed': 'desktop_and_login_entries', 'dataPreserved': True,
            'service': 'already_running_service_is_not_stopped'}


def main():
    configure_console()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['install', 'enable-login', 'disable-login', 'uninstall', 'status'])
    p.add_argument('root'); p.add_argument('--entry-dir'); p.add_argument('--browser')
    a = p.parse_args()
    try:
        if a.action == 'install':
            result = install(a.root, a.entry_dir, a.browser)
        elif a.action in ('enable-login', 'disable-login'):
            result = set_login(a.root, a.action == 'enable-login')
        elif a.action == 'uninstall':
            result = uninstall(a.root)
        else:
            root, config, manifest = load(a.root)
            result = dict(manifest, url=config['url'])
            result['artifactsIntact'] = all(fingerprint(Path(path)) == value for path, value in manifest.get('files', {}).items())
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        p.exit(1, str(exc) + '\n')


if __name__ == '__main__':
    main()
