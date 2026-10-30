#!/usr/bin/env python3
"""Date regressions through prepare/release/publish, with isolated synthetic data."""
import copy
import tempfile
import unittest
from pathlib import Path
from initialize import initialize
import workbench as w
import release

EARLY = '2026-01-01T10:00:00+08:00'
CURRENT = '2026-01-02T10:00:00+08:00'
LATER = '2026-01-03T10:00:00+08:00'


def message(ident, stamp):
    return {'id':ident, 'role':'user', 'text':'讨论记录 ' + ident, 'date':stamp}


def node(msg):
    return {'id':'t:' + msg['id'], 'title':'讨论变化', 'event':'讨论方案的变化',
            'thread':'t', 'messageId':msg['id'], 'quote':msg['text'],
            'quoteRole':'user', 'sourceTitle':'示例对话', 'date':msg['date']}


class DateConsistencyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / '工作台'
        initialize(self.root, '2026-01-01', '2026-01-31', 'Asia/Shanghai')
        self.seq = 0
        self.msg = message('m1', CURRENT)
        self.thread = {'id':'t', 'title':'示例对话', 'date':CURRENT, 'messages':[self.msg]}
        self.item = {'id':'i', 'title':'讨论方案', 'description':'比较方案', 'summary':'比较方案的变化',
                     'status':'讨论中', 'date':CURRENT, 'type':'planning-decisions', 'terms':[],
                     'nodes':[node(self.msg)], 'decisions':[]}
        # Use a configured type so the fixture is independent of type naming.
        self.item['type'] = w.read(self.root/'data.json')['types'][0]['id']

    def batch(self, thread=None, item=None):
        return {'version':1, 'baseSha256':w.sha((self.root/'data.json').read_bytes()),
                'provenance':[{'method':'synthetic regression', 'status':'complete'}],
                'threads':[copy.deepcopy(thread or self.thread)], 'items':[copy.deepcopy(item or self.item)]}

    def prepare(self, batch):
        self.seq += 1
        path = self.root / ('batch%d.json' % self.seq)
        candidate = self.root / ('candidate%d' % self.seq)
        w.atomic(path, w.encode(batch))
        w.prepare(self.root, path, candidate)
        return candidate

    def review(self, candidate):
        data = w.read(candidate/'data.json'); batch = w.read(candidate/'batch.json')
        value = {'version':1, 'candidateSha256':w.sha((candidate/'data.json').read_bytes()),
                 'batchSha256':w.sha((candidate/'batch.json').read_bytes()),
                 'sources':[{'id':'t', 'messageIds':[m['id'] for m in batch['threads'][0]['messages']],
                             'filterNote':'合成用户消息。', 'coverageNote':'均属于方案讨论。', 'curation':'complete'}],
                 'items':[{'id':'i', 'evidence':[{'thread':'t', 'messageId':data['threads'][0]['messages'][-1]['id']}],
                           'boundary':'同一方案讨论。', 'summary':'检查最新讨论。', 'daily':'没有新增每日小结。',
                           'decisions':{'result':'checked_none', 'reason':'没有明确采用。'},
                           'continuation':{'result':'checked_none', 'reason':'没有明确接续目标。'}}]}
        path = candidate/'review.json'; w.atomic(path, w.encode(value)); return path

    def seed(self):
        c = self.prepare(self.batch())
        release.release(self.root, c, self.review(c))

    def test_stale_and_future_dates_block_prepare_without_touching_live(self):
        original = (self.root/'data.json').read_bytes()
        for collection in ('threads', 'items'):
            for stamp in (EARLY, LATER):
                with self.subTest(collection=collection, stamp=stamp):
                    b = self.batch(); b[collection][0]['date'] = stamp
                    with self.assertRaisesRegex(ValueError, '日期不一致'):
                        self.prepare(b)
                    self.assertEqual((self.root/'data.json').read_bytes(), original)

    def test_new_discussion_requires_updated_parent_dates(self):
        self.seed(); original = (self.root/'data.json').read_bytes()
        m = message('m2', LATER)
        t = {**self.thread, 'date':LATER, 'messages':[m]}
        i = {**self.item, 'nodes':[node(m)]}
        with self.assertRaisesRegex(ValueError, '事项.*日期不一致'):
            self.prepare(self.batch(t, i))
        self.assertEqual((self.root/'data.json').read_bytes(), original)
        i['date'] = LATER
        with self.assertRaisesRegex(ValueError, '对话.*日期不一致'):
            self.prepare(self.batch({**t, 'date':CURRENT}, i))
        c = self.prepare(self.batch(t, i))
        release.release(self.root, c, self.review(c))
        data = w.read(self.root/'data.json')
        self.assertEqual(data['items'][0]['date'], LATER)
        self.assertEqual(len(data['items'][0]['nodes']), 2)

    def test_historical_backfill_preserves_latest_date_and_content(self):
        self.seed()
        m = message('m0', EARLY)
        c = self.prepare(self.batch({**self.thread, 'messages':[m]}, {**self.item, 'nodes':[node(m)]}))
        release.release(self.root, c, self.review(c))
        data = w.read(self.root/'data.json')
        self.assertEqual(data['items'][0]['date'], CURRENT)
        self.assertEqual(data['threads'][0]['date'], CURRENT)
        self.assertEqual([m['id'] for m in data['threads'][0]['messages']], ['m0','m1'])
        self.assertEqual(data['items'][0]['summary'], self.item['summary'])

    def test_equal_instants_accept_different_offsets(self):
        b = self.batch()
        for collection in ('threads', 'items'):
            b[collection][0]['date'] = '2026-01-02T02:00:00Z'
        c = self.prepare(b)
        self.assertEqual(w.validate(w.read(c/'data.json'))['items'], 1)

    def test_unrelated_new_message_does_not_advance_existing_matter(self):
        self.seed()
        b = self.batch({**self.thread, 'date':LATER, 'messages':[message('other', LATER)]})
        b['items'] = []  # New source text need not be a node of this matter.
        c = self.prepare(b)
        data = w.read(c/'data.json')
        self.assertEqual(data['threads'][0]['date'], LATER)
        self.assertEqual(data['items'][0]['date'], CURRENT)

    def test_latest_is_by_instant_not_array_order_or_timestamp_text(self):
        # Earlier local date is later in UTC; neither list order nor string max works.
        newer = message('newer', '2026-01-01T23:30:00-05:00')
        older = message('older', '2026-01-02T10:00:00+08:00')
        c = self.prepare(self.batch({**self.thread, 'date':newer['date'], 'messages':[newer,older]},
                                    {**self.item, 'date':newer['date'], 'nodes':[node(newer),node(older)]}))
        data = w.read(c/'data.json')
        self.assertEqual(w.validate(data)['threads'], 1)

    def test_existing_bad_candidate_blocked_by_release_and_direct_publish(self):
        c = self.prepare(self.batch())
        original = (self.root/'data.json').read_bytes()
        # Simulate a candidate created by an older validator, with valid hashes.
        data = w.read(c/'data.json'); data['items'][0]['date'] = EARLY
        w.atomic(c/'data.json', w.encode(data))
        report = w.read(c/'report.json'); report['candidateSha256'] = w.sha((c/'data.json').read_bytes())
        w.atomic(c/'report.json', w.encode(report))
        review = self.review(c)
        for publish in (lambda: release.release(self.root,c,review), lambda: w.publish(self.root,c)):
            with self.assertRaisesRegex(ValueError, '事项.*日期不一致'):
                publish()
            self.assertEqual((self.root/'data.json').read_bytes(), original)
        self.assertFalse((c/'published.json').exists())

    def test_decision_date_must_match_its_evidence_node(self):
        original = (self.root/'data.json').read_bytes()
        for stamp in (EARLY, LATER, 'not-a-date'):
            with self.subTest(stamp=stamp):
                b = self.batch()
                b['items'][0]['decisions'] = [{'text':'选择方案', 'label':'明确采用',
                                              'node':'t:m1', 'date':stamp}]
                with self.assertRaises(ValueError):
                    self.prepare(b)
                self.assertEqual((self.root/'data.json').read_bytes(), original)

    def test_decision_date_accepts_equivalent_timezone(self):
        b = self.batch()
        b['items'][0]['decisions'] = [{'text':'选择方案', 'label':'明确采用',
                                      'node':'t:m1', 'date':'2026-01-02T02:00:00Z'}]
        candidate = self.prepare(b)
        self.assertEqual(w.validate(w.read(candidate/'data.json'))['items'], 1)

    def test_template_contains_same_validator(self):
        skill = Path(__file__).resolve().parent.parent
        self.assertEqual((skill/'scripts/workbench.py').read_bytes(),
                         (skill/'assets/template/scripts/workbench.py').read_bytes())
        self.assertEqual((self.root/'scripts/workbench.py').read_bytes(),
                         (skill/'scripts/workbench.py').read_bytes())


if __name__ == '__main__':
    unittest.main(verbosity=2)
