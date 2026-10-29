#!/usr/bin/env python3
"""Portable, stdlib-only candidate/validate/publish/rollback pipeline. AI curates batches."""
import argparse
import errno
import sys
import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import tempfile
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from contextlib import contextmanager


def require(ok, message):
    if not ok:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def encode(obj):
    return (json.dumps(obj, ensure_ascii=False, indent=2) + '\n').encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def atomic(path, raw):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


_PLATFORM = sys.platform


def configure_console():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')


def load_timezone(name):
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError('时区不可用：' + name + '。请检查 IANA 时区名称，并用当前 Python 执行 -m pip install tzdata。') from exc


def lock_file(file, unlock=False):
    if _PLATFORM == 'win32':
        import msvcrt
        # Lock exactly the same byte on acquire/release, including an empty file.
        file.seek(0)
        msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK if unlock else msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(file.fileno(), fcntl.LOCK_UN if unlock else fcntl.LOCK_EX | fcntl.LOCK_NB)


@contextmanager
def lock(root):
    # OS releases the lock on process exit. Never unlink the lock file.
    path = Path(root) / '.workbench' / 'update.lock'
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as f:
        try:
            lock_file(f)
        except OSError as exc:
            if exc.errno in (errno.EACCES, errno.EAGAIN, errno.EDEADLK) or getattr(exc, 'winerror', None) in (33, 36):
                raise ValueError('另一个更新正在发布，请稍后重试') from exc
            raise
        try:
            yield
        finally:
            lock_file(f, unlock=True)


def indexed(rows, label):
    require(isinstance(rows, list), label + ' 必须为数组')
    out = {}
    for row in rows:
        require(isinstance(row, dict) and isinstance(row.get('id'), str) and row['id'], label + ' 缺少 id')
        require(row['id'] not in out, label + ' 重复 id: ' + row['id'])
        out[row['id']] = row
    return out


def date(value):
    require(isinstance(value, str), '日期必须是 ISO 字符串')
    parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    return parsed.replace(tzinfo=parsed.tzinfo or dt.timezone.utc)


def text_fields(row, fields, label):
    for field in fields:
        require(isinstance(row.get(field), str), label + ' 缺少文本字段 ' + field)


def latest_date_matches(row, children, label):
    # Compare instants, not ISO text or collection order. Backfills may use
    # another offset and arrive after newer records have already been stored.
    if children:
        latest = max(children, key=lambda child: date(child['date']))['date']
        require(date(row['date']) == date(latest),
                label + '日期不一致: ' + row['id'] + '，当前 ' + row['date'] +
                '，最新记录 ' + latest + '；请核对完整记录后重新准备候选')


def validate(data):
    text_fields(data, ('snapshot', 'checked', 'scopeDescription'), '数据')
    date(data['snapshot'])
    zone = load_timezone(data.get('timezone', 'Asia/Shanghai'))
    types = indexed(data['types'], 'types')
    threads = indexed(data['threads'], 'threads')
    items = indexed(data['items'] + data.get('legacyItems', []), 'items')
    tasks = indexed(data['tasks'], 'tasks')
    sources = {}
    for t in threads.values():
        text_fields(t, ('title', 'date'), '对话')
        date(t['date'])
        for m in indexed(t['messages'], 'messages').values():
            text_fields(m, ('text', 'date'), '消息')
            require(m['role'] in ('user', 'assistant'), '只允许用户正文和助手最终回复')
            date(m['date'])
            sources[(t['id'], m['id'])] = m
        latest_date_matches(t, t['messages'], '对话')
    for item in items.values():
        text_fields(item, ('title', 'summary', 'description', 'status', 'date'), '事项')
        date(item['date'])
        require(item['type'] in types, '无效分类: ' + item['type'])
        require(isinstance(item.get('terms'), list), 'terms 必须是数组')
        nodes = indexed(item['nodes'], 'nodes')
        require(bool(nodes), '事项至少需要一个证据节点')
        for node in nodes.values():
            text_fields(node, ('title', 'event', 'quote', 'sourceTitle', 'date'), '节点')
            source = sources.get((node['thread'], node['messageId']))
            require(source is not None, '节点引用不存在: ' + node['id'])
            require(node['quote'] == source['text'], '节点原文不一致: ' + node['id'])
            require(node['date'] == source['date'], '节点日期不一致: ' + node['id'])
            require(node['quoteRole'] == source['role'], '节点角色不一致: ' + node['id'])
            for ctx in node.get('context', []):
                original = sources.get((node['thread'], ctx['id']))
                require(original is not None and all(ctx.get(k) == original.get(k) for k in ('text', 'role', 'date')), '上下文不一致')
        latest_date_matches(item, item['nodes'], '事项')
        for dec in item['decisions']:
            require(dec['node'] in nodes, '决定引用不存在')
            text_fields(dec, ('text', 'label', 'date'), '决定')
        require(all(x in items for x in item.get('related', [])), '关联事项不存在')
    for task in tasks.values():
        require(task['item'] in items, '任务事项不存在')
        nodes = indexed(items[task['item']]['nodes'], 'nodes')
        require(task['node'] in nodes, '任务节点不存在')
        require(task['thread'] == nodes[task['node']]['thread'], '任务来源不一致')
        require(task['date'] == nodes[task['node']]['date'], '任务日期不一致')
        require(task['level'] in ('有明确接续', '状态待核实'), '无效任务状态')
        text_fields(task, ('title', 'stop', 'reason', 'sourceTitle'), '任务')
    for key, value in data.get('dailySummaries', {}).items():
        day, itemid = key.split('|', 1)
        require(itemid in items and any(date(n['date']).astimezone(zone).date().isoformat() == day for n in items[itemid]['nodes']), '每日小结无对应节点')
        require(isinstance(value, str), '每日小结必须是文本')
    return {k: len(data[k]) for k in ('threads', 'items', 'tasks')}


def merge_rows(old, new, label):
    result = copy.deepcopy(indexed(old, label))
    for ident, row in indexed(new, label).items():
        if ident in result:
            previous = result[ident]
            if label == 'tasks':
                require(row['item'] == previous['item'], '任务 ID 不能改指另一件事')
            if label == 'nodes':
                require((row['thread'], row['messageId']) == (previous['thread'], previous['messageId']), '节点 ID 不能改指另一条原文')
            if label == 'messages':
                require(row == previous, '已有消息不能静默改写；需单独核对来源: ' + ident)
            else:
                if 'date' in row and 'date' in previous:
                    require(date(row['date']) >= date(previous['date']), '不能用旧记录覆盖最新状态: ' + ident)
                if label == 'threads':
                    row = {**row, 'messages': merge_rows(previous['messages'], row['messages'], 'messages')}
                if label == 'items':
                    row = {**row, 'nodes': merge_rows(previous['nodes'], row['nodes'], 'nodes')}
                    # Historical decisions and search aliases survive incremental updates.
                    for field in ('decisions', 'terms'):
                        row[field] = previous.get(field, []) + [x for x in row.get(field, []) if x not in previous.get(field, [])]
        result[ident] = copy.deepcopy(row)
    rows = list(result.values())
    if label in ('messages', 'nodes'):
        rows.sort(key=lambda row: date(row['date']))
    return rows


def config_types(root, data):
    settings = root / 'config/workbench.json'
    if settings.exists():
        data['timezone'] = read(settings)['timezone']
    cfg = read(root / 'config/default-types.json')
    data['types'] = cfg['types'] + [cfg['unclassified']]
    ids = set(indexed(data['types'], 'types'))
    overrides = read(root / 'config/item-types.json')
    for item in data['items'] + data.get('legacyItems', []):
        item['type'] = overrides.get(item['id'], item.get('type', cfg['fallback']))
        require(item['type'] in ids, '用户分类配置无效: ' + item['id'])


def prepare(root, batchpath, destination):
    root, destination = Path(root), Path(destination)
    require(not destination.exists(), '候选目录已存在，请使用新的批次目录')
    original = (root / 'data.json').read_bytes()
    data = json.loads(original)
    batch = read(batchpath)
    require(batch.get('version') == 1, '批次 version 必须为 1')
    require(batch.get('baseSha256') == sha(original), '批次依据已过期，请重新读取现有数据')
    require(isinstance(batch.get('provenance'), list) and bool(batch['provenance']), '缺少来源采集清单')
    for entry in batch['provenance']:
        require(isinstance(entry, dict) and entry.get('method') and entry.get('status') in ('complete', 'partial', 'failed'), '来源清单缺少 method 或有效 status')
    require(set(batch) <= {'version','baseSha256','provenance','threads','items','tasks','retireTasks','dailySummaries','snapshot','checked','scopeDescription'}, '批次存在未支持字段')
    for key in ('threads', 'items', 'tasks'):
        data[key] = merge_rows(data[key], batch.get(key, []), key)
    retired = indexed(batch.get('retireTasks', []), 'retireTasks')
    existing_tasks = indexed(data['tasks'], 'tasks')
    for tid, record in retired.items():
        require(record.get('reason') and record.get('node'), '移除接续项需要原因和证据节点')
        require(any(record['node'] == n['id'] for i in data['items'] for n in i['nodes']), '移除接续项的证据不存在')
        if tid in existing_tasks:
            owner = next(i for i in data['items'] if i['id'] == existing_tasks[tid]['item'])
            evidence = next((n for n in owner['nodes'] if n['id'] == record['node']), None)
            require(evidence is not None and date(evidence['date']) >= date(existing_tasks[tid]['date']), '移除证据必须属于同一事项且不早于当前停点')
        require(not any(t['id'] == tid for t in batch.get('tasks', [])), '同批不能既更新又移除任务')
    data['tasks'] = [t for t in data['tasks'] if t['id'] not in retired]
    data.setdefault('dailySummaries', {}).update(batch.get('dailySummaries', {}))
    for key in ('snapshot', 'checked', 'scopeDescription'):
        if key in batch:
            data[key] = batch[key]
    require(date(data['snapshot']) >= date(json.loads(original)['snapshot']), '快照时间不能倒退')
    config_types(root, data)
    counts = validate(data)
    raw = encode(data)
    report = {'version': 1, 'baseSha256': sha(original), 'candidateSha256': sha(raw),
              'configSha256': config_hash(root), 'counts': counts,
              'provenance': batch['provenance'], 'retireTasks': list(retired.values())}
    destination.mkdir(parents=True)
    atomic(destination / 'data.json', raw)
    atomic(destination / 'report.json', encode(report))
    atomic(destination / 'batch.json', encode(batch))
    return report


def config_hash(root):
    return sha(b'\0'.join((root / 'config' / name).read_bytes() if (root / 'config' / name).exists() else b'' for name in ('default-types.json', 'item-types.json', 'workbench.json')))


def replace_live(root, raw, action):
    validate(json.loads(raw))
    old = (root / 'data.json').read_bytes()
    if json.loads(old) == json.loads(raw):
        return {'status': 'unchanged'}
    stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:8]
    backup = root / '.workbench/backups' / (stamp + '.json')
    # Backup is durable before touching the live file.
    atomic(backup, old)
    atomic(root / 'data.json', raw)
    return {'status': action, 'backup': str(backup), 'sha256': sha(raw)}


def publish(root, candidate, expected_sha=None):
    root, candidate = Path(root), Path(candidate)
    with lock(root):
        report = read(candidate / 'report.json')
        raw = (candidate / 'data.json').read_bytes()
        require(sha(raw) == report['candidateSha256'], '候选文件已被改动，请重新准备')
        if expected_sha is not None:
            require(sha(raw) == expected_sha, '候选在质量检查后变化，请重新检查')
        require(config_hash(root) == report['configSha256'], '分类配置已变化，请重新准备')
        require(sha((root / 'data.json').read_bytes()) == report['baseSha256'], '正式数据已更新，请重新准备，不能覆盖其他批次')
        return replace_live(root, raw, 'published')


def rollback(root, backup):
    root, backup = Path(root), Path(backup).resolve()
    require(backup.parent == (root / '.workbench/backups').resolve(), '只允许恢复本工作台的备份')
    with lock(root):
        return replace_live(root, backup.read_bytes(), 'restored')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    a = sub.add_parser('validate'); a.add_argument('data')
    a = sub.add_parser('hash'); a.add_argument('data')
    a = sub.add_parser('prepare'); a.add_argument('root'); a.add_argument('batch'); a.add_argument('candidate')
    a = sub.add_parser('publish'); a.add_argument('root'); a.add_argument('candidate')
    a = sub.add_parser('rollback'); a.add_argument('root'); a.add_argument('backup')
    args = p.parse_args()
    try:
        if args.command == 'validate': result = validate(read(args.data))
        elif args.command == 'hash': result = sha(Path(args.data).read_bytes())
        elif args.command == 'prepare': result = prepare(args.root, args.batch, args.candidate)
        elif args.command == 'publish': result = publish(args.root, args.candidate)
        else: result = rollback(args.root, args.backup)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, KeyError, TypeError, OSError) as e:
        p.exit(1, '未发布：' + str(e) + '\n')


if __name__ == '__main__':
    configure_console()
    main()
