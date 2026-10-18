import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from hub.v6.ledger import open_ledger, record

class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = open_ledger(Path(self.tmp.name) / 'v6.sqlite')
        self.addCleanup(self.db.close)
        self.row = {'url':'https://example.org/item', 'title':'A report', 'published_at':'2026-10-17T01:00:00+00:00',
                    'personal':{'note':'must not leak'}, 'sources':[{'id':'s1'}]}
        self.info = {'status':'ok','checked_at':'2026-10-18T01:00:00+00:00'}
    def put(self, rows=None, info=None, source='s1'):
        return record(self.db,source,rows if rows is not None else [self.row],info or self.info,lambda u:u)
    def test_idempotency_and_private_exclusion(self):
        self.assertEqual(self.put(),1)
        self.assertEqual(self.put(),0)
        body,status=self.db.execute('SELECT body,verification_status FROM articles').fetchone()
        self.assertNotIn('personal',json.loads(body))
        self.assertEqual(status,'candidate')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM source_runs').fetchone()[0],2)
    def test_failed_run_does_not_advance_watermark(self):
        self.put()
        before=self.db.execute('SELECT * FROM source_state').fetchall()
        self.put([],{'status':'http_error','http_status':429,'retry_after':'3600','checked_at':'2026-10-19T01:00:00+00:00'})
        self.assertEqual(before,self.db.execute('SELECT * FROM source_state').fetchall())
    def test_cache_is_not_new_fetch(self):
        self.put(info={**self.info,'status':'cached'})
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM source_state').fetchone()[0],0)
    def test_sources_preserved_without_duplicate_article(self):
        self.put();self.put([{**self.row,'summary':'Other source wording'}],source='s2')
        self.assertEqual(self.put(),0)
        self.assertEqual(self.put([{**self.row,'summary':'Other source wording'}],source='s2'),0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM articles').fetchone()[0],1)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM observations').fetchone()[0],2)
    def test_future_date_not_watermark(self):
        self.put([{**self.row,'published_at':'2099-01-01T00:00:00+00:00'}])
        self.assertIsNone(self.db.execute('SELECT published_watermark FROM source_state').fetchone()[0])
    def test_refuses_existing_production_db(self):
        path=Path(self.tmp.name)/'hub.sqlite'
        c=sqlite3.connect(path);c.execute('CREATE TABLE personal(note TEXT)');c.commit();c.close()
        with self.assertRaises(ValueError):open_ledger(path)
        c=sqlite3.connect(path)
        self.assertEqual(c.execute('PRAGMA application_id').fetchone()[0],0);c.close()
    def test_malformed_batch_rolls_back(self):
        with self.assertRaises(ValueError):self.put([self.row,{'title':'broken'}])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM articles').fetchone()[0],0)
