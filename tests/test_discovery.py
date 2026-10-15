import datetime as dt
import tempfile
import unittest
from pathlib import Path
from werkzeug.security import generate_password_hash
from hub.app import create_app, ingest, connection
from hub.discovery import CATALOG, canonical_link, capture_key, rank_items, normalize_profile


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / 'discovery.sqlite')
        self.app = create_app({
            'TESTING': True, 'PUBLIC': True, 'DB': self.db,
            'SECRET_KEY': 'test-discovery-key',
            'PASSWORD_HASH': generate_password_hash('pw-test', method='pbkdf2:sha256:1000'),
            'INGEST_TOKEN': 'only-collector', 'SESSION_COOKIE_SECURE': False
        })
        self.client = self.app.test_client()
        self.candidate = {
            'id':'repo-tool-1','title':'开源 GitHub Agent MCP 工具',
            'url':'https://github.com/example/agent',
            'summary':'工具使用教程','source':'测试源', 'topic':'开发',
            'published_at':'2026-10-14',
            'verification_status':'candidate',
            'expires_at':'2099-01-01T00:00:00+00:00'
        }
        self.research = {
            **self.candidate,
            'id':'rna-paper-2','title':'RNA 生物学研究论文',
            'url':'https://example.org/rna-paper',
            'summary':'跨领域探索','topic':'研究',
            'published_at':'2026-10-10'
        }

    def tearDown(self):
        self.tmp.cleanup()

    def login(self):
        self.client.get('/login')
        with self.client.session_transaction() as sess:
            token = sess['login_csrf']
        self.assertEqual(self.client.post('/login', data={'csrf':token,'password':'pw-test'}).status_code,302)
        with self.client.session_transaction() as sess:
            self.csrf = sess['csrf']

    def test_private_workbench_no_anonymous_read_or_write(self):
        self.assertEqual(self.client.get('/api/discover').status_code,401)
        self.assertEqual(self.client.post('/api/capture',json={'url':'https://github.com/a/b','title':'Hello'}).status_code,401)
        self.assertEqual(self.client.get('/').status_code,200)
        self.login()
        self.assertEqual(self.client.post('/api/capture',json={'url':'https://github.com/a/b','title':'Hello'}).status_code,403)

    def test_curated_sources_have_explicit_uncertain_access(self):
        self.login()
        data = self.client.get('/api/discover').json
        names = [row['name'] for row in data['sources']]
        self.assertTrue({'AIHOT','BestBlogs','GitHub','小红书','数字生命卡兹克'}.issubset(set(names)))
        self.assertTrue(all('access' in source for source in data['sources']))
        self.assertIn('没有调用模型',data['ranking_method'])
        self.assertIn('categories',data)
        self.assertTrue(any(c['key']=='paper' for c in data['categories']))
        self.assertNotIn('stars',str(data))

    def test_private_capture_idempotent_and_not_published(self):
        self.login()
        def add(url):
            return self.client.post('/api/capture',
                headers={'X-CSRF-Token':self.csrf},
                json={'url':url,'title':'看到的 GitHub 项目','source':'小红书','note':'待验证应用价值'})
        first = add('https://github.com/Example/Repo/?utm_source=xhs#readme')
        self.assertEqual(first.status_code,201)
        self.assertFalse(first.json['duplicate'])
        again = add('https://github.com/example/Repo')
        self.assertTrue(again.json['duplicate'])
        captures = self.client.get('/api/discover').json['captures']
        self.assertEqual(len(captures),1)
        self.assertEqual(captures[0]['source'],'小红书')
        self.assertIn('待验证应用价值',captures[0]['note'])
        self.assertEqual(captures[0]['category'],'code')
        self.assertIn('许可证',captures[0]['category_reason'])
        self.assertEqual(self.client.get('/api/items').json['items'],[])
        with connection(self.db) as c:
            self.assertEqual(c.execute('SELECT count(*) FROM items').fetchone()[0],0)
            self.assertEqual(c.execute("SELECT count(*) FROM personal WHERE id LIKE 'capture:%'").fetchone()[0],1)
        outsider = self.app.test_client()
        self.assertNotIn('看到的 GitHub',outsider.get('/').get_data(as_text=True))
        self.assertEqual(outsider.get('/api/discover').status_code,401)
        self.assertEqual(outsider.get('/api/capture').status_code,401)

    def test_capture_rejects_invalid_and_oversized_urls(self):
        self.login()
        for url in ('javascript:alert(1)','https://u:password@example.org/',
                    'http://example.org:8080/', 'ftp://example.org/path', ''):
            r=self.client.post('/api/capture',headers={'X-CSRF-Token':self.csrf},
                               json={'url':url,'title':'bad'})
            self.assertEqual(r.status_code,400,url)

    def test_rule_rank_and_feedback_are_explainable(self):
        rows = [dict(self.candidate),dict(self.research)]
        def ranked(profile):
            return rank_items(rows,profile,today=dt.date(2026,10,15))
        self.assertEqual(ranked(None)[0]['item']['id'],'repo-tool-1')
        changed = ranked({'weights':{'agent':0,'open_source':0,'science':5,'research':5}})
        self.assertEqual(changed[0]['item']['id'],'rna-paper-2')
        self.assertTrue(any('尚待核验' in x for x in changed[0]['reasons']))
        rows[0]['personal']={'feedback':'证据不好'}
        bad = ranked(None)
        self.assertIn('历史反馈：证据不好',next(x for x in bad if x['item']['id']=='repo-tool-1')['reasons'])

    def test_same_relevance_sorts_newer_publications_first(self):
        older={**self.candidate,'id':'older','title':'无匹配条目','published_at':'2026-05-01','url':'https://example.org/older'}
        newer={**older,'id':'newer','published_at':'2026-06-01','url':'https://example.org/newer'}
        ranked=rank_items([older,newer],today=dt.date(2026,10,15))
        self.assertEqual([r['item']['id'] for r in ranked],['newer','older'])

    def test_actual_profile_revision_and_persistence(self):
        ingest(self.db,{'schema':1,'items':[self.candidate,self.research]})
        self.login()
        first=self.client.get('/api/discover').json
        self.assertEqual(first['profile_revision'],0)
        changed = self.client.put('/api/state/profile%3Ainterests',
          headers={'X-CSRF-Token':self.csrf},
          json={'revision':0,'value':{'weights':{'agent':0,'open_source':0,'science':5,'research':5}}})
        self.assertEqual(changed.status_code,200)
        second=self.client.get('/api/discover').json
        self.assertEqual(second['profile_revision'],1)
        self.assertEqual(second['ranking'][0]['item']['id'],'rna-paper-2')
        self.assertEqual(self.client.put('/api/state/profile%3Ainterests',
          headers={'X-CSRF-Token':self.csrf},json={'revision':0,'value':{'weights':{}}}).status_code,409)
        self.assertEqual(second['profile']['weights']['science'],5)
        self.assertEqual(second['ranking'][0]['category'],'paper')
        self.assertEqual(sum(x['count'] for x in second['categories']),len(second['ranking']))

    def test_custom_hobbies_can_be_added_without_inventing_model_quality(self):
        profile=normalize_profile({'weights':{'agent':0,'open_source':0},
                                   'custom_interests':['天体物理','天体物理','蛋白质结构','','x'*100]})
        self.assertEqual(profile['custom_interests'],['天体物理','蛋白质结构'])
        custom={**self.candidate,'id':'new-hobby','title':'天体物理基础教程',
                'url':'https://example.org/astro','published_at':None}
        scored=rank_items([custom,self.candidate],profile,today=dt.date(2026,10,15))
        self.assertEqual(scored[0]['item']['id'],'new-hobby')
        self.assertIn('新增兴趣：天体物理',scored[0]['reasons'])
        self.assertEqual(scored[0]['item']['verification_status'],'candidate')

    def test_weights_are_bounded_and_unverified_cannot_be_auto_promoted(self):
        p=normalize_profile({'weights':{'agent':100,'open_source':True,'science':0}})
        self.assertEqual(p['weights']['agent'],5)
        self.assertEqual(p['weights']['open_source'],5)
        self.assertEqual(p['weights']['science'],0)
        rows=rank_items([self.candidate],today=dt.date(2026,10,15))
        self.assertEqual(rows[0]['item']['verification_status'],'candidate')
        self.assertNotIn('已编辑核验',str(rows))

    def test_link_normalization_removes_tracking_but_keeps_real_query(self):
        normalized=canonical_link('https://github.com/Team/X/?utm_campaign=ad&tab=readme#overview')
        self.assertEqual(normalized,'https://github.com/team/x?tab=readme')
        self.assertEqual(capture_key(normalized),
                         capture_key('https://github.com/team/X?tab=readme'))


if __name__ == '__main__':
    unittest.main()
