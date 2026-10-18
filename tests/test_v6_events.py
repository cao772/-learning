import copy
import datetime as dt
import tempfile
import unittest
from pathlib import Path
from hub.v6.events import candidates, minhash, shingles, approved_groups
from hub.v6.scoring import score, WEIGHTS
from hub.v6.private_ranking import rank
from hub.v6.review import decide

class EventTests(unittest.TestCase):
    def setUp(self):
        self.a={'url':'https://publisher-a.org/release','title':'Acme announces Widget 2.0',
                'summary':'Specific documented operation with reproducible inputs output example installation configuration runtime deployment benchmark reliability latency cost detailed evaluation memory scheduling throughput analysis methodology results limitations future validation research artifact instructions',
                'published_at':'2026-10-17T00:00:00+00:00','fingerprint':'a'}
        self.b={**self.a,'url':'https://publisher-b.org/release','fingerprint':'b'}
        self.as_of=dt.datetime(2026,10,18,tzinfo=dt.timezone.utc)
    def pairs(self,b=None):return candidates([self.a,b or self.b],[[1,.96],[.96,1]])
    def test_reprint_proposal_needs_review(self):
        p=self.pairs();self.assertEqual(p[0]['kind'],'possible_reprint')
        self.assertEqual(len(approved_groups([self.a,self.b],p,{})),2)
    def test_paper_code_never_same_event(self):
        a={**self.a,'url':'https://arxiv.org/abs/2601.00001'}
        b={**self.b,'url':'https://github.com/org/repo'}
        p=candidates([a,b],[[1,.99],[.99,1]])[0]
        self.assertEqual(p['kind'],'same_topic');self.assertIn('different_content_types',p['blockers'])
    def test_distinct_papers_are_not_one_event_even_at_high_similarity(self):
        a={**self.a,'url':'https://arxiv.org/abs/2406.20031'}
        b={**self.b,'url':'https://arxiv.org/abs/2610.21554'}
        p=candidates([a,b],[[1,.99],[.99,1]])[0]
        self.assertEqual(p['kind'],'same_topic');self.assertIn('different_paper_identifiers',p['blockers'])
    def test_cross_domain_reprints_not_independent_sources(self):
        r=score([self.a,self.b],self.as_of)
        self.assertEqual(r['independent_origin_lower_bound'],1)
    def test_version_conflict_and_time_window(self):
        for patch,reason in [({'title':'Acme announces Widget 3.0'},'conflicting_versions'),
                             ({'published_at':'2026-09-01T00:00:00+00:00'},'outside_72h_window'),
                             ({'published_at':None},'unknown_publication_time')]:
            p=self.pairs({**self.b,**patch})[0]
            self.assertEqual(p['kind'],'same_topic');self.assertIn(reason,p['blockers'])
    def test_valid_review_applied_and_stale_review_ignored(self):
        pairs=self.pairs();report={'items':[self.a,self.b],'pairs':pairs}
        with tempfile.TemporaryDirectory() as tmp:
            r=decide(report,Path(tmp)/'reviews.json',pairs[0]['id'],'merge','test-only synthetic reviewer')
        self.assertEqual(len(approved_groups(report['items'],pairs,{pairs[0]['id']:r})),1)
        changed={**self.b,'fingerprint':'new'}
        self.assertEqual(len(approved_groups([self.a,changed],pairs,{pairs[0]['id']:r})),2)
    def test_replay_fields_never_affect_score(self):
        before=score([self.a],self.as_of)
        after=score([{**self.a,'last_seen':'2099','last_changed_at':'2099','last_fetched_at':'2099'}],self.as_of)
        self.assertEqual(before,after)
    def test_missing_dates_no_invented_freshness(self):
        r=score([{**self.a,'published_at':None}],self.as_of)
        self.assertEqual(r['heat'],0);self.assertIn('publication_time',r['missing'])
    def test_private_ranking_cannot_mutate_public_score(self):
        rows=[{'event_id':'a',**score([self.a],self.as_of)}];before=copy.deepcopy(rows)
        rank(rows,{rows[0]['category']:5});self.assertEqual(rows,before)
        self.assertEqual(len(WEIGHTS),9)
    def test_minhash_deterministic_and_exact(self):
        p=shingles(self.a['summary']);self.assertEqual(minhash(p),minhash(set(reversed(sorted(p)))))
    def test_no_transitive_unreviewed_merge(self):
        c={**self.b,'url':'https://publisher-c.org/release','fingerprint':'c'}
        items=[self.a,self.b,c];pairs=candidates(items,[[1,.99,.99],[.99,1,.99],[.99,.99,1]])
        lookup={x['url']:x for x in items};reviews={}
        for p in pairs:
            if {p['left'],p['right']}=={self.a['url'],c['url']}:continue
            reviews[p['id']]={'decision':'merge','left_fingerprint':lookup[p['left']]['fingerprint'],'right_fingerprint':lookup[p['right']]['fingerprint']}
        self.assertEqual(len(approved_groups(items,pairs,reviews)),2)
