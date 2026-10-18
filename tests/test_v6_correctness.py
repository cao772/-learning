import itertools
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from hub.v6.ledger import open_ledger, record
from hub.v6.schema import sanitize

class CorrectnessTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.c=open_ledger(Path(self.tmp.name)/'data.sqlite');self.addCleanup(self.c.close)
        self.row={'url':'https://example.org/news','title':'Release A', 'sources':[{'id':'feed','metadata':{'note':'SECRET'},'note':'SECRET'}], 'categories':['AI']}
    def put(self, status='ok', day=1, source='feed', row=None):
        return record(self.c,source,[row or self.row],{'status':status,'checked_at':f'2026-10-{day:02}T00:00:00+00:00'},lambda u:u)
    def test_cache_and_304_do_not_change_evidence_times(self):
        self.put()
        for day in range(2,20):self.put('cached',day)
        self.put('not_modified',20)
        changed,fetched,validated,observed=self.c.execute('SELECT last_changed_at,last_fetched_at,last_validated_at,last_observed_at FROM articles').fetchone()
        self.assertEqual(changed,fetched);self.assertTrue(changed.startswith('2026-10-01'))
        self.assertTrue(validated.startswith('2026-10-20'));self.assertEqual(observed,validated)
    def test_cache_cannot_revert_new_text(self):
        self.put(row={**self.row,'title':'New report'})
        self.put('cached',2)
        self.assertEqual(json.loads(self.c.execute('select body from articles').fetchone()[0])['title'],'New report')
    def test_unmodified_200_not_new_change(self):
        self.put();self.put(day=2)
        change,fetch=self.c.execute('SELECT last_changed_at,last_fetched_at FROM articles').fetchone()
        self.assertTrue(change.startswith('2026-10-01'));self.assertTrue(fetch.startswith('2026-10-02'))
    def test_nested_private_fields_dropped(self):
        self.put()
        for table in ('articles','observations'):
            self.assertNotIn('SECRET',self.c.execute('select body from '+table).fetchone()[0])
    def test_malformed_nested_values_rejected(self):
        for patch in ({'sources':[{'name':{'note':'private'}}]}, {'categories':[{'note':'private'}]},
                      {'sources':[{'feed_url':'http://127.0.0.1/x'}]}, {'url':'https://example.org/?token=secret'},
                      {'summary':['private']}, {'sources':'not-a-list'}, {'categories':['x'*121]}):
            with self.subTest(patch=patch),self.assertRaises(ValueError):sanitize({**self.row,**patch})
    def test_source_order_stable(self):
        representations=[];outputs=[]
        for i,order in enumerate(itertools.permutations(['a','z'])):
            c=open_ledger(Path(self.tmp.name)/f'{i}.sqlite')
            for source in order:
                record(c,source,[{**self.row,'title':source}],{'status':'ok','checked_at':'2026-10-01T00:00:00+00:00'},lambda u:u)
            representations.append(c.execute('select body,fingerprint from articles').fetchone());c.close()
            from hub.v6.offline import load_items
            from hub.v6.scoring import score
            from hub.v6.events import candidates
            import datetime as dt
            items=load_items(Path(self.tmp.name)/f'{i}.sqlite')
            outputs.append((items,candidates(items,[[1.0]]),score(items,dt.datetime(2026,10,2,tzinfo=dt.timezone.utc))))
        self.assertEqual(*representations)
        self.assertEqual(*outputs)
    def test_legacy_upgrade_does_not_invent_timestamps(self):
        p=Path(self.tmp.name)/'legacy.sqlite';c=sqlite3.connect(p)
        c.executescript('''PRAGMA application_id=1481987638;
        CREATE TABLE articles(url TEXT PRIMARY KEY,body TEXT,fingerprint TEXT,first_seen TEXT,last_seen TEXT,verification_status TEXT DEFAULT 'candidate');
        CREATE TABLE observations(source TEXT,url TEXT,first_seen TEXT,last_seen TEXT,body TEXT,PRIMARY KEY(source,url));''')
        from hub.v6.ledger import APP_ID
        c.execute(f'PRAGMA application_id={APP_ID}')
        body=json.dumps(self.row)
        c.execute('insert into articles values(?,?,?,?,?,?)',(self.row['url'],body,'old','old','old','candidate'))
        c.execute('insert into observations values(?,?,?,?,?)',('feed',self.row['url'],'old','old',body));c.commit();c.close()
        c=open_ledger(p)
        self.assertEqual(c.execute('select last_changed_at,last_fetched_at from articles').fetchone(),(None,None))
        self.assertNotIn('SECRET',c.execute('select body from articles').fetchone()[0]);c.close()
