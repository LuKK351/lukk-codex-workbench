#!/usr/bin/env python3
"""Verify evidence-backed batch review before publishing. Not a semantic judge."""
import argparse
import json
from pathlib import Path
import workbench as w


def nonempty(value, label):
    w.require(isinstance(value, str) and bool(value.strip()), label + '不能为空')


def check(root, candidate, review_path):
    root, candidate = Path(root), Path(candidate)
    raw = (candidate / 'data.json').read_bytes()
    batch_raw = (candidate / 'batch.json').read_bytes()
    data, batch = json.loads(raw), json.loads(batch_raw)
    report, review = w.read(candidate / 'report.json'), w.read(review_path)
    base = w.read(root / 'data.json')
    w.require(review.get('version') == 1, '质量记录 version 必须为 1')
    w.require(review.get('candidateSha256') == w.sha(raw) == report['candidateSha256'], '质量记录或候选已过期')
    w.require(review.get('batchSha256') == w.sha(batch_raw), '批次已变化，需重新检查')
    w.require(w.sha((root / 'data.json').read_bytes()) == report['baseSha256'] == batch['baseSha256'], '正式数据已变化')
    w.require(w.config_hash(root) == report['configSha256'], '配置已变化')
    w.validate(data)
    items = w.indexed(data['items'] + data.get('legacyItems', []), 'items')
    sources = {(t['id'], m['id']): m for t in data['threads'] for m in t['messages']}
    incoming = w.indexed(batch.get('threads', []), 'threads')
    source_reviews = w.indexed(review.get('sources', []), 'source reviews')
    w.require(set(source_reviews) == set(incoming), '来源检查未覆盖本批所有窗口')
    for tid, t in incoming.items():
        row = source_reviews[tid]
        ids = row.get('messageIds')
        w.require(isinstance(ids, list) and all(isinstance(x, str) for x in ids), '来源检查缺少消息区段')
        w.require(len(ids) == len(set(ids)) and set(ids) == {m['id'] for m in t['messages']}, '来源检查区段与本批消息不一致')
        nonempty(row.get('filterNote'), '来源过滤依据')
        nonempty(row.get('coverageNote'), '本批消息的事项归属或仅保留原文的原因')
        w.require(row.get('curation') == 'complete', '本批消息仍未完成整理，应缩小批次或补齐')

    affected = {i['id'] for i in batch.get('items', [])}
    affected.update(t['item'] for t in batch.get('tasks', []))
    affected.update(k.split('|', 1)[1] for k in batch.get('dailySummaries', {}))
    # New text can change the status of an existing matter in the same source.
    affected.update(i['id'] for i in items.values() if any(n['thread'] in incoming for n in i['nodes']))
    previous_tasks = w.indexed(base['tasks'], 'tasks')
    for t in batch.get('retireTasks', []):
        w.require(t['id'] in previous_tasks, '撤销任务不存在，需核对基线')
        affected.add(previous_tasks[t['id']]['item'])
    rows = w.indexed(review.get('items', []), 'item reviews')
    w.require(set(rows) == affected, '事项检查遗漏或包含非本批事项: ' + ', '.join(sorted(set(rows) ^ affected)))
    for iid, row in rows.items():
        w.require(iid in items, '检查事项不存在')
        threads = {n['thread'] for n in items[iid]['nodes']}
        evidence = row.get('evidence')
        w.require(isinstance(evidence, list) and bool(evidence), '事项检查缺少原文证据')
        for e in evidence:
            w.require(isinstance(e, dict) and e.get('thread') in threads and (e.get('thread'), e.get('messageId')) in sources, '检查证据不存在或不属于事项来源')
        for field in ('boundary', 'summary', 'daily'):
            nonempty(row.get(field), field + '检查说明')
        for field in ('decisions', 'continuation'):
            value = row.get(field)
            w.require(isinstance(value, dict) and value.get('result') in ('present', 'checked_none'), field + '未检查')
            nonempty(value.get('reason'), field + '判断依据')
        has_decision = bool(items[iid]['decisions'])
        has_task = any(t['item'] == iid for t in data['tasks'])
        w.require((row['decisions']['result'] == 'present') == has_decision, '决定检查与候选不一致')
        w.require((row['continuation']['result'] == 'present') == has_task, '接续检查与候选不一致')
    warnings = []
    placeholders = ('见当日收录的讨论', '用户提出需求或作出修正。', '用户提出要求或反馈。', '助手当时的回复。')
    for iid in affected:
        item = items[iid]
        fields = [item['summary']] + [n['event'] for n in item['nodes']]
        fields += [v for k, v in data.get('dailySummaries', {}).items() if k.endswith('|' + iid)]
        if any(p in value for value in fields for p in placeholders):
            warnings.append(iid + ': 检出可能的占位说明，请对照原文复核')
    return {'version': 1, 'candidateSha256': w.sha(raw), 'batchSha256': w.sha(batch_raw),
            'reviewSha256': w.sha(Path(review_path).read_bytes()), 'affectedItems': sorted(affected),
            'warnings': warnings, 'semanticAccuracyVerified': False}


def release(root, candidate, review_path):
    receipt = check(root, candidate, review_path)
    # publish rechecks baseline/config/candidate under its own writer lock.
    w.atomic(Path(candidate) / 'quality-receipt.json', w.encode(receipt))
    result = w.publish(root, candidate, expected_sha=receipt['candidateSha256'])
    w.atomic(Path(candidate) / 'published.json', w.encode(result))
    return {**result, 'quality': receipt,
            'nextAction': '本批发布不是初始化完成。先更新 history-collection.json 的本批进度，然后运行当前 Skill 的 scripts/next_step.py <工作台>，按返回的具体动作继续；预览地址用进度消息提供。'}


def main():
    w.configure_console()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root'); p.add_argument('candidate'); p.add_argument('review')
    p.add_argument('--check-only', action='store_true')
    a = p.parse_args()
    try:
        result = (check if a.check_only else release)(a.root, a.candidate, a.review)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, KeyError, TypeError, OSError) as exc:
        p.exit(1, '未发布：' + str(exc) + '\n')


if __name__ == '__main__':
    main()
