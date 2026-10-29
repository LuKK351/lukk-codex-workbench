#!/usr/bin/env python3
"""Read the collection ledger and choose the next action; never changes progress."""
import argparse
import json
from pathlib import Path
import workbench as w


def next_step(root):
    path = Path(root) / '.workbench/history-collection.json'
    if not path.is_file():
        return {'action':'rebuild_progress','canFinish':False,'reason':'缺少收录清单，先从正式数据与批次证据重建，不能结束初始化。'}
    ledger = w.read(path)
    threads = ledger.get('threads')
    w.require(isinstance(threads, dict), 'threads 必须是按窗口 ID 保存的对象')
    counts = {}
    for row in threads.values():
        key = row.get('status', 'unknown'); counts[key] = counts.get(key, 0) + 1
    common = {'counts':counts,'ledgerStatus':ledger.get('status'),'discoveryStatus':ledger.get('discovery',{}).get('status')}
    if ledger.get('status') == 'paused':
        return {**common,'action':'paused','canFinish':True,'reason':'仅在当前用户明确暂停时适用；恢复请求到来后先改回 in_progress。'}
    # A stored readable slice takes precedence over opening more windows,
    # even if older pages of that same source are blocked.
    for tid, row in threads.items():
        if row.get('status') == 'excluded': continue
        gaps = row.get('gaps', [])
        pending = row.get('curationStatus') in ('pending', 'partial')
        if row.get('status') == 'ready' or (pending and (row.get('readThrough') or any(g.get('type') == 'curation_pending' for g in gaps))):
            return {**common,'action':'curate_or_publish','canFinish':False,'threadId':tid,
                    'readThrough':row.get('readThrough'),'curatedThrough':row.get('curatedThrough'),
                    'reason':'继续整理已读区段，核对原文并通过 release 发布；更新清单后再次运行 next_step。'}
    for tid, row in threads.items():
        if row.get('status') in ('pending', 'reading'):
            return {**common,'action':'read','canFinish':False,'threadId':tid,'cursor':row.get('cursor'),
                    'reason':'用实际来源工具继续读取此窗口；保存进度并整理，不发送最终交付。'}
        if row.get('status') == 'published' and (row.get('curationStatus') != 'complete' or row.get('gaps')):
            return {**common,'action':'reconcile_progress','canFinish':False,'threadId':tid,
                    'reason':'已发布不等于完成，核对缺口和整理状态，不能直接将其算作完成。'}
    unknown = [tid for tid,row in threads.items() if row.get('status') not in ('published','excluded','blocked')]
    if unknown:
        return {**common,'action':'reconcile_progress','canFinish':False,'threadId':unknown[0],'reason':'未知状态需核对，不能结束。'}
    discovery = ledger.get('discovery', {})
    if discovery.get('status') not in ('complete', 'blocked'):
        return {**common,'action':'verify_discovery','canFinish':False,'reason':'核对目录分页与已授权入口；确实无法继续才登记具体阻碍。'}
    blocked = [tid for tid,row in threads.items() if row.get('status') == 'blocked']
    if blocked or discovery.get('status') == 'blocked':
        return {**common,'action':'report_blockers','canFinish':True,'blockedThreads':blocked,
                'reason':'程序只识别登记的阻碍；逐一核对确实无法继续，明确部分完成，不能报全量完成。'}
    w.require(discovery.get('evidence'), '目录 complete 缺少覆盖证据')
    return {**common,'action':'complete','canFinish':True,'reason':'清单无可执行项；核对发布及质量回执后才可交付完成。'}


def main():
    w.configure_console()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root');p.add_argument('--finish-check',action='store_true')
    a=p.parse_args()
    try:
        result=next_step(a.root)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        if a.finish_check and not result['canFinish']: raise SystemExit(2)
    except (ValueError,KeyError,TypeError,OSError) as e:p.exit(1,str(e)+'\n')


if __name__=='__main__':main()
