import datetime as dt
import tempfile
import unittest
from pathlib import Path

from werkzeug.security import generate_password_hash
from hub.app import create_app, ingest, connection
from hub.research import connect_sources, research_brief, classify_source, interest_collections, suggested_research


class ResearchLoopTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.temp.name) / "hub.sqlite")
        self.app = create_app({
            'TESTING': True, 'PUBLIC': True, 'DB': self.db,
            'SECRET_KEY': 'research-secret',
            'PASSWORD_HASH': generate_password_hash('pw', method='pbkdf2:sha256:1000'),
            'INGEST_TOKEN': 'research-token', 'SESSION_COOKIE_SECURE': False
        })
        self.client = self.app.test_client()
        self.item = {
            'id':'paper-rna', 'title':'可复现的 RNA 结构建模新方法与实验报告',
            'url':'https://arxiv.org/abs/2610.12345',
            'source':'BestBlogs', 'topic':'研究',
            'published_at':'2026-10-14', 'collected_at':'2026-10-15T01:00:00+00:00',
            'summary':'待复查论文摘要', 'verification_status':'candidate',
            'expires_at':'2099-01-01T00:00:00+00:00'
        }

    def tearDown(self):
        self.temp.cleanup()

    def login(self):
        self.client.get('/login')
        with self.client.session_transaction() as sess: token=sess['login_csrf']
        self.assertEqual(self.client.post('/login', data={'csrf':token,'password':'pw'}).status_code,302)
        with self.client.session_transaction() as sess: self.csrf=sess['csrf']

    def test_classification_is_not_auto_evaluation(self):
        github = research_brief({'url':'https://github.com/example/project'})
        paper = research_brief({'url':self.item['url']})
        self.assertEqual(github['kind'],'repository')
        self.assertEqual(paper['kind'],'paper')
        self.assertIsNone(github['metrics']['github_stars'])
        self.assertIsNone(github['metrics']['license'])
        self.assertIsNone(paper['metrics']['paper_fulltext_read'])
        self.assertEqual(paper['evidence_level'],'待验证')
        self.assertEqual(classify_source('https://github.com/trending'),'general')

    def test_strict_same_url_and_weak_same_title(self):
        a={'item':self.item}
        b={'item':{**self.item,'id':'another','url':'https://doi.org/10.1000/demo',
                   'source':'AIHOT'}}
        c={'id':'capture:manual','url':'https://arxiv.org/abs/2610.12345?utm_source=xhs',
           'source':'小红书','title':'在别处看到 RNA 论文','verification_status':'candidate'}
        out=connect_sources([a,b],[c])
        self.assertEqual(len(out['same_link']),1)
        self.assertEqual(len(out['similar_title']),1)
        self.assertEqual(len(out['same_link'][0]['members']),2)
        self.assertIn('非独立来源证明',out['same_link'][0]['basis'])
        self.assertIn('需核实',out['similar_title'][0]['basis'])
        self.assertEqual(self.item['verification_status'],'candidate')

    def test_different_short_titles_do_not_cluster(self):
        rows=[
            {'item':{'id': 'one','url':'https://example.org/a','title':'Agent 新工具'}},
            {'item':{'id': 'two','url':'https://example.org/b','title':'Agent 新工具'}},
        ]
        out=connect_sources(rows,[])
        self.assertFalse(out['same_link'])
        self.assertFalse(out['similar_title'])

    def test_interest_theme_does_not_pretend_corrob_and_saved_suggestions_are_not_persisted(self):
        matching=[
            {'item':{'id':'a','title':'Agent Harness 讨论','source':'BestBlogs',
                     'url':'https://example.org/a','personal':{'saved':True}},'match_keys':['agent']},
            {'item':{'id':'b','title':'另一个 Agent 项目','source':'AIHOT',
                     'url':'https://example.org/b','personal':{'feedback':'值得深读'}},'match_keys':['agent']},
        ]
        groups=interest_collections(matching)
        self.assertEqual(len(groups),1)
        self.assertEqual(groups[0]['source_count'],2)
        self.assertIn('不代表',groups[0]['basis'])
        self.assertEqual([r['id'] for r in suggested_research(matching,[])],['a','b'])
        self.assertEqual([r['id'] for r in suggested_research(matching,['a'])],['b'])
        self.assertTrue(all(r['status'].startswith('仅建议') for r in suggested_research(matching,[])))
        matching[1]['item']['source']='BestBlogs'
        self.assertEqual(interest_collections(matching),[])

    def test_private_discovery_and_plan_remain_private(self):
        ingest(self.db,{'schema':1,'items':[self.item]})
        self.assertEqual(self.client.get('/api/discover').status_code,401)
        self.assertEqual(self.client.get('/api/state/research%3Apaper-rna').status_code,401)
        self.login()
        response=self.client.get('/api/discover')
        self.assertEqual(response.status_code,200)
        self.assertIn('connections', response.json)
        self.assertIn('topic_groups',response.json)
        self.assertIn('research_suggestions',response.json)
        self.assertEqual(response.json['research_guides']['paper-rna']['kind'],'paper')
        self.assertEqual(response.json['research_records'],[])
        note={
            'title':'私人 RNA 复现计划','url':self.item['url'], 'source':'BestBlogs',
            'decision':'待复现','test_status':'未运行','effort':'1–3 天',
            'question':'数据和基线是什么？','project':'私人研究','step':1,
            'evidence':'仅看摘要，尚未核验全文', 'conclusion':'尚无结论'
        }
        path='/api/state/research%3Apaper-rna'
        self.assertEqual(self.client.put(path,json={'revision':0,'value':note}).status_code,403)
        saved=self.client.put(path,json={'revision':0,'value':note},
            headers={'X-CSRF-Token':self.csrf})
        self.assertEqual(saved.status_code,200)
        self.assertEqual(self.client.put(path,json={'revision':0,'value':note},
            headers={'X-CSRF-Token':self.csrf}).status_code,409)
        mine=self.client.get('/api/discover').json['research_records']
        self.assertEqual(mine[0]['decision'],'待复现')
        self.assertEqual(mine[0]['test_status'],'未运行')
        other=self.app.test_client()
        self.assertEqual(other.get('/api/discover').status_code,401)
        self.assertEqual(other.get(path).status_code,401)
        self.assertNotIn('私人 RNA 复现计划',other.get('/').get_data(as_text=True))
        self.assertNotIn('私人 RNA 复现计划',other.get('/api/items').get_data(as_text=True))
        second=create_app(dict(self.app.config))
        with connection(self.db) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM personal WHERE id=?",
                               ('research:paper-rna',)).fetchone()[0],1)
        self.assertTrue(second.config['PUBLIC'])


if __name__ == '__main__':
    unittest.main()
