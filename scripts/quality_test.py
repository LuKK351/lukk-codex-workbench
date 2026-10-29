#!/usr/bin/env python3
"""Synthetic release-gate regressions; no personal data or network."""
import copy
import tempfile
from pathlib import Path
from unittest.mock import patch
from initialize import initialize
import workbench as w
import release as q


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / '中文 工作台'
        initialize(root, '2026-01-01', '2026-01-31', 'Asia/Shanghai')
        stamp = '2026-01-02T10:00:00+08:00'
        msg = {'id':'m1','role':'assistant','text':'缓存会暂存读取结果，以减少重复读取。','date':stamp}
        node = {'id':'n1','ref':'t:m1','title':'理解缓存','event':'解释缓存如何减少重复读取',
                'quote':msg['text'],'quoteRole':'assistant','date':stamp,'sourceTitle':'问答','thread':'t','messageId':'m1','context':[]}
        item = {'id':'i','title':'理解缓存','description':'缓存概念问答','summary':'解释缓存暂存结果的用途。',
                'status':'问答已答复','date':stamp,'type':'learning-research','terms':[],'nodes':[node],'decisions':[]}
        batch = {'version':1,'baseSha256':w.sha((root/'data.json').read_bytes()),
                 'provenance':[{'method':'synthetic','status':'partial'}],
                 'threads':[{'id':'t','title':'问答','date':stamp,'messages':[msg]}], 'items':[item]}
        w.atomic(root/'batch.json',w.encode(batch));candidate=root/'candidate'
        report=w.prepare(root,root/'batch.json',candidate)
        review={'version':1,'candidateSha256':report['candidateSha256'],'batchSha256':w.sha((candidate/'batch.json').read_bytes()),
                'sources':[{'id':'t','messageIds':['m1'],'filterNote':'合成助手最终答复，无工具输出。','coverageNote':'本区段是缓存问答，归i，后续未读区段独立登记。','curation':'complete'}],
                'items':[{'id':'i','evidence':[{'thread':'t','messageId':'m1'}],'boundary':'单个缓存问答。','summary':'解释缓存暂存结果。','daily':'当日只有概念答复，无决定。',
                          'decisions':{'result':'checked_none','reason':'解释概念，没有选择方案。'},'continuation':{'result':'checked_none','reason':'问题已回答，未提出继续目标。'}}]}
        path=root/'review.json'
        def verify(value):
            w.atomic(path,w.encode(value));return q.check(root,candidate,path)
        def rejected(value):
            try:verify(value)
            except (ValueError,KeyError,TypeError):return
            raise AssertionError('Invalid review was accepted')
        assert verify(review)['affectedItems']==['i']
        for mutation in ('missing','evidence','range','pending','false_present','hash'):
            bad=copy.deepcopy(review)
            if mutation=='missing':bad['items']=[]
            elif mutation=='evidence':bad['items'][0]['evidence'][0]['messageId']='missing'
            elif mutation=='range':bad['sources'][0]['messageIds']=[]
            elif mutation=='pending':bad['sources'][0]['curation']='partial'
            elif mutation=='false_present':bad['items'][0]['continuation']['result']='present'
            else:bad['candidateSha256']='outdated'
            rejected(bad)
        # The wrapper must publish exactly the reviewed candidate, even if another
        # actor rewrites both candidate and its normal report after gate checking.
        verify(review)
        original_publish=w.publish
        def changed_publish(root_,candidate_,expected_sha=None):
            data=w.read(candidate_/'data.json');data['items'][0]['summary']='Changed after review'
            w.atomic(candidate_/'data.json',w.encode(data))
            rpt=w.read(candidate_/'report.json');rpt['candidateSha256']=w.sha((candidate_/'data.json').read_bytes())
            w.atomic(candidate_/'report.json',w.encode(rpt))
            return original_publish(root_,candidate_,expected_sha=expected_sha)
        raw=(candidate/'data.json').read_bytes();rpt=(candidate/'report.json').read_bytes()
        with patch.object(w,'publish',changed_publish):
            try:q.release(root,candidate,path)
            except ValueError:pass
            else:raise AssertionError('Changed candidate published')
        w.atomic(candidate/'data.json',raw);w.atomic(candidate/'report.json',rpt)
        assert w.read(root/'data.json')['items']==[]
        result=q.release(root,candidate,path)
        assert result['status']=='published' and not result['quality']['semanticAccuracyVerified']
        assert (candidate/'published.json').exists()
        # Task-only update must still require reviewing its owner.
        task={'id':'k','item':'i','node':'n1','thread':'t','sourceTitle':'问答','date':stamp,'title':'继续研究','stop':'待研究','reason':'合成验证','level':'状态待核实'}
        b2={'version':1,'baseSha256':w.sha((root/'data.json').read_bytes()),'provenance':batch['provenance'],'tasks':[task]}
        w.atomic(root/'b2.json',w.encode(b2));c2=root/'c2';r2=w.prepare(root,root/'b2.json',c2)
        v2=copy.deepcopy(review);v2.update(candidateSha256=r2['candidateSha256'],batchSha256=w.sha((c2/'batch.json').read_bytes()),sources=[],items=[])
        w.atomic(path,w.encode(v2))
        try:q.check(root,c2,path)
        except ValueError:pass
        else:raise AssertionError('Task-only owner review missing')
        # Warnings must not reject a quoted user sentence or pretend to judge meaning.
        data=w.read(c2/'data.json');data['items'][0]['nodes'][0]['event']='助手当时的回复。'
        w.atomic(c2/'data.json',w.encode(data));r2['candidateSha256']=w.sha((c2/'data.json').read_bytes());w.atomic(c2/'report.json',w.encode(r2))
        v2['candidateSha256']=r2['candidateSha256'];v2['items']=copy.deepcopy(review['items']);v2['items'][0]['continuation']={'result':'present','reason':'合成候选保留待确认任务。'}
        w.atomic(path,w.encode(v2));assert q.check(root,c2,path)['warnings']
    print('PASS zero outcomes / partial source batch / missing review / invalid evidence / message coverage / stale hash / post-check mutation / task-only review / placeholder warning')

if __name__=='__main__':main()
