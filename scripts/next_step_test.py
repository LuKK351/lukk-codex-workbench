#!/usr/bin/env python3
"""Synthetic continuation decisions; no source conversations read."""
import tempfile
from pathlib import Path
import workbench as w
from next_step import next_step


def main():
    with tempfile.TemporaryDirectory() as d:
        root=Path(d);p=root/'.workbench/history-collection.json'
        assert next_step(root)['action']=='rebuild_progress'
        ledger={'status':'in_progress','discovery':{'status':'in_progress'},'threads':{
            'a':{'status':'published','curationStatus':'complete','gaps':[]},
            'b':{'status':'pending','curationStatus':'pending'},
            'c':{'status':'reading','curationStatus':'partial','readThrough':{'source':'saved.json'},'gaps':[{'type':'curation_pending'}]}}}
        def check():w.atomic(p,w.encode(ledger));return next_step(root)
        assert check()['threadId']=='c' and not check()['canFinish']
        ledger['threads']['c']={'status':'published','curationStatus':'complete','gaps':[]}
        assert check()['threadId']=='b' and check()['action']=='read'
        ledger['threads']['b']={'status':'published','curationStatus':'complete','gaps':[]}
        assert check()['action']=='verify_discovery' and not check()['canFinish']
        ledger['discovery']={'status':'complete','evidence':'synthetic directory exhausted'}
        assert check()['action']=='complete'
        ledger['threads']['b']['curationStatus']='pending'
        assert check()['action']=='reconcile_progress'
        ledger['threads']['b']={'status':'blocked','curationStatus':'pending','gaps':[{'type':'read_error'}]}
        assert check()['action']=='report_blockers'
        ledger['threads']['d']={'status':'pending'}
        assert check()['action']=='read'
        ledger['status']='paused'
        assert check()['action']=='paused'
    print('PASS multi-batch continuation / read backlog / unknown discovery / stale completion / blockers with runnable work / explicit pause')

if __name__=='__main__':main()
