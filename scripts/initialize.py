#!/usr/bin/env python3
"""Create a new workbench without overwriting an existing directory."""
import argparse
import datetime as dt
import json
from pathlib import Path
import shutil
import sys
from workbench import load_timezone, configure_console, atomic, encode


def initialize(destination, since, until, timezone, port=8770):
    destination = Path(destination).expanduser().resolve()
    start, end = dt.date.fromisoformat(since), dt.date.fromisoformat(until)
    if start > end: raise ValueError('起始日期不能晚于截止日期')
    zone = load_timezone(timezone)
    if not 1024 <= port <= 65535: raise ValueError('端口应在 1024—65535 之间')
    if destination.exists(): raise ValueError('目标目录已存在；更新现有工作台请使用 prepare/publish')
    source = Path(__file__).resolve().parents[1] / 'assets/template'
    shutil.copytree(source, destination)
    settings = {'version': 1, 'pythonExecutable': sys.executable, 'timezone': timezone, 'initialRange': {'start': since, 'end': until},
                'port': port, 'url': f'http://127.0.0.1:{port}/', 'sources': ['codex'],
                'createdAt': dt.datetime.now(zone).isoformat()}
    (destination / 'config/workbench.json').write_text(json.dumps(settings, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    data = json.loads((destination / 'data.json').read_text(encoding='utf-8'))
    data['timezone'] = timezone
    data['snapshot'] = dt.datetime.now(zone).date().isoformat()
    data['scopeDescription'] = f'尚未收录。首次计划范围：{since}—{until}（{timezone}）。'
    (destination / 'data.json').write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    progress = {'version': 1,
                'range': {'start': since, 'end': until, 'timezone': timezone},
                'status': 'in_progress',
                'discovery': {'status': 'in_progress', 'method': '', 'cursor': None,
                              'evidence': '', 'limitations': []},
                'threads': {}, 'updatedAt': settings['createdAt'],
                'nextAction': '发现授权范围内的候选窗口，登记清单并逐批读取、整理、发布。'}
    atomic(destination / '.workbench/history-collection.json', encode(progress))
    return settings


if __name__ == '__main__':
    configure_console()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('destination'); p.add_argument('--since', required=True)
    p.add_argument('--until', required=True); p.add_argument('--timezone', required=True)
    p.add_argument('--port', type=int, default=8770)
    a = p.parse_args()
    try:
        print(json.dumps(initialize(a.destination, a.since, a.until, a.timezone, a.port), ensure_ascii=False, indent=2))
    except (ValueError, OSError) as e: p.exit(1, str(e)+'\n')
