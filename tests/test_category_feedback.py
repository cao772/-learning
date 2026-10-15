import tempfile
import unittest
from pathlib import Path

from werkzeug.security import generate_password_hash
from hub.app import create_app, ingest, connection
from hub.content_category import apply_owner_category, CATEGORIES


class CategoryCorrectionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.db=str(Path(self.temp.name)/'hub.sqlite')
        self.app=create_app({
            'TESTING':True,'PUBLIC':True,'DB':self.db,
            'SECRET_KEY':'correction-test-secret',
            'PASSWORD_HASH':generate_password_hash('pw',method='pbkdf2:sha256:1000'),
            'INGEST_TOKEN':'collector-only','SESSION_COOKIE_SECURE':False
        })
        self.client=self.app.test_client()
        self.item={
            'id':'paper-rna','title':'RNA 学术论文',
            'url':'https://arxiv.org/abs/2610.54321','source':'Synthetic Journal',
            'verification_status':'candidate',
            'expires_at':'2099-01-01T00:00:00+00:00'
        }
        ingest(self.db,{'schema':1,'items':[self.item]})

    def tearDown(self):
        self.temp.cleanup()

    def login(self):
        self.client.get('/login')
        with self.client.session_transaction() as sess:csrf=sess['login_csrf']
        self.assertEqual(self.client.post('/login',data={'csrf':csrf,'password':'pw'}).status_code,302)
        with self.client.session_transaction() as sess:self.csrf=sess['csrf']

    def put_category(self, key='category:paper-rna',category='science',revision=0,note='人工检查后调整'):
        return self.client.put('/api/state/'+key.replace(':','%3A'),json={
            'revision':revision,'value':{'category':category,'note':note}
        },headers={'X-CSRF-Token':self.csrf})

    def test_override_survives_new_feed_import_and_restart_without_publishing(self):
        outsider=self.app.test_client()
        self.assertEqual(outsider.get('/api/state/category%3Apaper-rna').status_code,401)
        self.assertEqual(outsider.get('/api/discover').status_code,401)
        self.login()
        self.assertEqual(self.client.get('/api/discover').json['ranking'][0]['category'],'paper')
        forbidden=self.client.put('/api/state/category%3Apaper-rna',
            json={'revision':0,'value':{'category':'science'}})
        self.assertEqual(forbidden.status_code,403)
        saved=self.put_category()
        self.assertEqual(saved.status_code,200)
        self.assertEqual(saved.json['revision'],1)
        data=self.client.get('/api/discover').json
        self.assertEqual(data['ranking'][0]['category'],'science')
        self.assertTrue(data['ranking'][0]['category_override'])
        self.assertEqual(data['ranking'][0]['category_revision'],1)
        self.assertEqual(data['ranking'][0]['item']['verification_status'],'candidate')
        self.assertEqual(sum(v['count'] for v in data['categories']),len(data['ranking']))
        with connection(self.db) as conn:
            item=conn.execute('SELECT body FROM items WHERE id=?',('paper-rna',)).fetchone()['body']
            self.assertNotIn('人工检查后调整',item)
            self.assertNotIn('category',item)
        self.assertNotIn('人工检查后调整',outsider.get('/').get_data(as_text=True))
        self.assertNotIn('人工检查后调整',outsider.get('/api/items').get_data(as_text=True))
        ingest(self.db,{'schema':1,'items':[{**self.item,'summary':'更新的摘要'}]})
        self.assertEqual(self.client.get('/api/discover').json['ranking'][0]['category'],'science')
        restarted=create_app(dict(self.app.config))
        other=restarted.test_client()
        self.assertEqual(other.get('/api/discover').status_code,401)

    def test_reset_returns_to_original_category_and_revisions_protect(self):
        self.login()
        self.assertEqual(self.put_category().status_code,200)
        self.assertEqual(self.put_category(revision=0).status_code,409)
        reset=self.put_category(category='auto',revision=1,note='')
        self.assertEqual(reset.status_code,200)
        after=self.client.get('/api/discover').json['ranking'][0]
        self.assertEqual(after['category'],'paper')
        self.assertFalse(after['category_override'])
        self.assertEqual(after['category_revision'],2)

    def test_bad_category_and_malicious_fields_rejected(self):
        self.login()
        for category in ('all','__proto__','',123,'<script>'):
            self.assertEqual(self.put_category(category=category).status_code,400)
        self.assertEqual(self.put_category(note='x'*201).status_code,400)
        for payload in ({'category':'paper','verification_status':'reviewed'},
                        {'category':'code','saved':True},
                        {'category':'paper','note':123}):
            result=self.client.put('/api/state/category%3Apaper-rna',
                json={'revision':0,'value':payload},
                headers={'X-CSRF-Token':self.csrf})
            self.assertEqual(result.status_code,400)
        self.assertEqual(self.put_category(key='category:does-not-exist').status_code,404)
        self.assertEqual(self.put_category(key='category:capture:fake').status_code,404)

    def test_private_capture_can_be_reclassified_without_publication(self):
        self.login()
        created=self.client.post('/api/capture',
            json={'url':'https://github.com/acme/repo','title':'Agent 项目',
                  'source':'小红书','note':'值得调查'},
            headers={'X-CSRF-Token':self.csrf})
        self.assertEqual(created.status_code,201)
        item_id=created.json['id']
        key='category:'+item_id
        self.assertEqual(self.put_category(key=key,category='product').status_code,200)
        mine=self.client.get('/api/discover').json['captures'][0]
        self.assertEqual(mine['category'],'product')
        self.assertTrue(mine['category_override'])
        self.assertNotIn('Agent 项目',str(self.app.test_client().get('/api/items').json['items']))

    def test_no_op_override_is_independent_of_personal_state(self):
        item={'id':'a','title':'Agent 论文','url':'https://arxiv.org/abs/123'}
        plain=apply_owner_category(item)
        manual=apply_owner_category(item,{'category':'agent','note':'用于 Agent 专题','revision':4})
        self.assertEqual(plain['category'],'paper')
        self.assertEqual(manual['category'],'agent')
        self.assertEqual(manual['category_revision'],4)
        self.assertEqual(manual['topic_tags'],plain['topic_tags'])
        self.assertEqual(item['title'],'Agent 论文')
        self.assertEqual(len(CATEGORIES),9)


if __name__=='__main__':
    unittest.main()
