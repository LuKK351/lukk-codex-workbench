#!/usr/bin/env python3
"""Isolated end-to-end smoke test; never reads a user's workbench."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from urllib.request import urlopen
from urllib.error import HTTPError
from initialize import initialize
import workbench as w


def main():
    w.configure_console()
    with tempfile.TemporaryDirectory(prefix='workbench-test-') as tmp:
        root = Path(tmp) / '中文 空格 工作台'
        initialize(root, '2026-01-01', '2026-01-02', 'Asia/Shanghai')
        original = (root / 'data.json').read_bytes()
        try:
            initialize(root, '2026-01-01', '2026-01-02', 'Asia/Shanghai')
            raise AssertionError('Existing directory was overwritten')
        except ValueError:
            pass
        assert (root / 'data.json').read_bytes() == original
        stamp = '2026-01-02T10:00:00+08:00'
        thread = {'id':'11111111-1111-4111-8111-111111111111','title':'测试对话','date':stamp,
                  'messages':[{'id':'m1','role':'user','text':'索引已完成，同步先不做。','date':stamp}]}
        node = {'id':thread['id']+':m1','ref':'m1','title':'确认结束','event':'用户报告完成',
                'quote':thread['messages'][0]['text'],'quoteRole':'user','date':stamp,
                'sourceTitle':thread['title'],'thread':thread['id'],'messageId':'m1','context':[]}
        item = {'id':'index','title':'整理笔记索引','summary':'用户报告完成，同步暂不开展。',
                'description':'整理笔记','status':'用户报告完成','recap':'','openQuestion':'','nextUse':'',
                'date':stamp,'type':'organization-admin','terms':[],'related':[],'workBranches':[],
                'nodes':[node],'decisions':[]}
        batch={'version':1,'baseSha256':w.sha(original),'provenance':[{'method':'self-test fixture','status':'complete'}],
               'threads':[thread],'items':[item],'scopeDescription':'隔离测试数据'}
        w.atomic(root/'batch.json',w.encode(batch))
        w.prepare(root, root/'batch.json', root/'candidate')
        result=w.publish(root,root/'candidate')
        assert w.validate(w.read(root/'data.json')) == {'threads':1,'items':1,'tasks':0}
        live=(root/'data.json').read_bytes()
        batch['baseSha256']=w.sha(live); w.atomic(root/'batch.json',w.encode(batch))
        w.prepare(root,root/'batch.json',root/'retry')
        assert w.publish(root,root/'retry')['status']=='unchanged'
        w.rollback(root,result['backup'])
        assert (root/'data.json').read_bytes()==original
        print('PASS initialize / Chinese path / publish / idempotency / rollback', flush=True)

        script_dir=str(Path(__file__).resolve().parent)
        holder_code='import sys;sys.path.insert(0,sys.argv[1]);from workbench import lock\nwith lock(sys.argv[2]):\n print("LOCKED",flush=True)\n sys.stdin.readline()'
        holder=subprocess.Popen([sys.executable,'-c',holder_code,script_dir,str(root)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8')
        try:
            assert holder.stdout.readline().strip()=='LOCKED'
            try:
                with w.lock(root): raise AssertionError('Concurrent writer entered')
            except ValueError: pass
            holder.terminate(); holder.wait(timeout=10)
            with w.lock(root): pass
        finally:
            if holder.poll() is None: holder.kill(); holder.wait(timeout=10)
            for stream in (holder.stdin,holder.stdout,holder.stderr): stream.close()
        print('PASS cross-process exclusion / termination releases lock', flush=True)

        server=subprocess.Popen([sys.executable,str(root/'scripts/serve.py'),str(root),'--port','0'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8')
        try:
            url=server.stdout.readline().strip().rstrip('/')
            assert url.startswith('http://127.0.0.1:')
            with urlopen(url+'/data.json',timeout=5) as response: assert json.load(response)['threads']==[]
            for private in ('config/workbench.json','scripts/serve.py'):
                try: urlopen(url+'/'+private,timeout=5)
                except HTTPError as exc: assert exc.code==404
                else: raise AssertionError('Private file exposed')
        finally:
            server.terminate(); server.wait(timeout=10)
            server.stdout.close(); server.stderr.close()
        print('PASS localhost serving / private file exclusion',flush=True)
    print('PASS all smoke checks on '+sys.platform)


if __name__=='__main__':
    main()
