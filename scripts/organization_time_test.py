#!/usr/bin/env python3
"""Verify truthful collection/organization clocks without changing message times."""
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from initialize import initialize
import workbench as w


class OrganizationTimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='workbench-time-test-')
        self.root = Path(self.tmp.name) / 'workbench'
        initialize(self.root, '2026-01-01', '2026-01-02', 'Asia/Shanghai')

    def tearDown(self):
        self.tmp.cleanup()

    def prepare(self, **fields):
        batch = dict(version=1, baseSha256=w.sha((self.root/'data.json').read_bytes()),
                     provenance=[{'method':'isolated timestamp check','status':'complete'}], **fields)
        path = self.root / 'batch.json'; w.atomic(path, w.encode(batch))
        candidate = self.root / ('candidate-' + str(len(list(self.root.glob('candidate-*')))))
        w.prepare(self.root, path, candidate)
        return candidate, w.read(candidate / 'data.json')

    def test_changes_get_precise_time_and_noop_keeps_it(self):
        started = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        candidate, data = self.prepare(scopeDescription='Time metadata fixture', collectionCutoff=started.isoformat())
        self.assertGreaterEqual(w.date(data['organizedAt']), started)
        self.assertEqual(data['collectionCutoff'], started.isoformat())
        self.assertEqual(data['threads'], [])
        w.publish(self.root, candidate)
        candidate2, again = self.prepare(scopeDescription='Time metadata fixture', collectionCutoff=started.isoformat())
        self.assertEqual(again, data)
        self.assertEqual(w.publish(self.root, candidate2)['status'], 'unchanged')

    def test_legacy_dates_remain_valid_without_invented_clock(self):
        data = w.read(self.root/'data.json')
        w.validate(data)
        self.assertNotIn('organizedAt', data)
        _, unchanged = self.prepare()
        self.assertNotIn('organizedAt', unchanged)

    def test_recovered_historical_time_is_preserved_with_offset(self):
        _, data = self.prepare(organizedAt='2026-10-30T00:07:55Z', collectionCutoff='2026-10-30T08:05:06+08:00')
        self.assertEqual(data['organizedAt'], '2026-10-30T00:07:55Z')
        self.assertEqual(data['collectionCutoff'], '2026-10-30T08:05:06+08:00')

    def test_date_only_unzoned_or_reversed_timestamps_are_rejected(self):
        original = (self.root/'data.json').read_bytes()
        for fields in ({'organizedAt':'2026-10-30'}, {'collectionCutoff':'2026-10-30T08:05:06'},
                       {'organizedAt':'2026-10-30T08:00:00+08:00','collectionCutoff':'2026-10-30T08:05:06+08:00'}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                self.prepare(**fields)
            self.assertEqual((self.root/'data.json').read_bytes(), original)


if __name__ == '__main__':
    unittest.main(verbosity=2)
