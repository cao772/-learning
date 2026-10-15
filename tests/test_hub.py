import copy
import json
import tempfile
import unittest
from pathlib import Path
from werkzeug.security import generate_password_hash
from hub.app import create_app, ingest, connection
from hub.manage import backup

class HubTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.db=str(Path(self.tmp.name)/'test.sqlite')
  self.app=create_app({'TESTING':True,'DB':self.db,'SECRET_KEY':'test-secret','PASSWORD_HASH':generate_password_hash('test-password',method='pbkdf2:sha256:1000'),'INGEST_TOKEN':'test-ingest','SESSION_COOKIE_SECURE':False})
  self.c=self.app.test_client();self.item={'id':'fixture-release-v1','title':'合成测试条目','url':'https://example.org/releases/v1','published_at':'2026-10-14','collected_at':'2026-10-15T01:00:00+00:00','source':'测试','topic':'测试','summary':'合成验收资料','verification_status':'candidate','scope':'标题','evidence':[],'expires_at':'2099-01-01T00:00:00+00:00'}
 def tearDown(self):self.tmp.cleanup()
 def login(self):
  self.c.get('/login')
  with self.c.session_transaction() as s:token=s['login_csrf']
  self.assertEqual(self.c.post('/login',data={'csrf':token,'password':'test-password'}).status_code,302)
  with self.c.session_transaction() as s:self.csrf=s['csrf']
 def put(self,key,value,revision=0):return self.c.put('/api/state/'+key,json={'value':value,'revision':revision},headers={'X-CSRF-Token':self.csrf})
 def test_auth_all_private_surfaces(self):
  for path in ['/','/learn/llm','/learn/lab']:self.assertEqual(self.c.get(path).status_code,302)
  for path in ['/api/items','/api/status','/api/export','/api/state/a']:self.assertEqual(self.c.get(path).status_code,401)
  self.assertEqual(self.c.post('/api/ingest',json={}).status_code,401)
  self.assertEqual(self.c.get('/healthz').json,{'ok':True})
 def test_csrf_and_logout_revocation(self):
  self.login();self.assertEqual(self.c.put('/api/state/a',json={}).status_code,403)
  with self.c.session_transaction() as s:old=dict(s)
  self.c.post('/logout',headers={'X-CSRF-Token':self.csrf})
  with self.c.session_transaction() as s:s.update(old)
  self.assertEqual(self.c.get('/api/items').status_code,401)
 def test_login_rate_limit(self):
  self.c.get('/login')
  with self.c.session_transaction() as s:token=s['login_csrf']
  for _ in range(8):self.c.post('/login',data={'csrf':token,'password':'wrong'})
  self.assertEqual(self.c.post('/login',data={'csrf':token,'password':'wrong'}).status_code,429)
 def test_real_schema_idempotent_versions_and_no_downgrade(self):
  data={'schema':1,'items':[self.item]};a=ingest(self.db,data);b=ingest(self.db,data)
  self.assertEqual(a['changed'],1);self.assertTrue(b['duplicate'])
  second=copy.deepcopy(self.item);second.update(id='fixture-release-v2',url='https://example.org/releases/v2')
  ingest(self.db,{'schema':1,'items':[second]})
  reviewed=copy.deepcopy(self.item);reviewed.update(verification_status='reviewed',learning_value='测试理由',evidence=[{'url':'https://example.org/source'}])
  ingest(self.db,{'schema':1,'items':[reviewed]});self.item['summary']='changed candidate';ingest(self.db,{'schema':1,'items':[self.item]})
  self.login();rows=self.c.get('/api/items').json['items'];self.assertEqual(len(rows),2)
  self.assertEqual(next(x for x in rows if x['id']==reviewed['id'])['verification_status'],'reviewed')
 def test_bad_batch_atomic_and_urls(self):
  bad=copy.deepcopy(self.item);bad['url']='javascript:alert(1)'
  with self.assertRaises(ValueError):ingest(self.db,{'schema':1,'items':[self.item,bad]})
  with connection(self.db) as c:self.assertEqual(c.execute('SELECT count(*) FROM items').fetchone()[0],0)
 def test_state_persistence_conflicts_and_backup_restore(self):
  self.login();v={'saved':True,'note':'<script>do not execute</script>','feedback':'值得深读'}
  self.assertEqual(self.put('fixture',v).status_code,200)
  self.assertEqual(self.put('fixture',{'note':'lost'},0).status_code,409)
  backup(self.db,Path(self.tmp.name)/'backup.sqlite')
  self.assertEqual(self.c.get('/api/state/fixture').json['value']['note'],v['note'])
  with connection(Path(self.tmp.name)/'backup.sqlite') as c:self.assertIn('script',c.execute('SELECT body FROM personal').fetchone()[0])
  app2=create_app(dict(self.app.config));c2=app2.test_client()
  with c2.session_transaction() as s:
   with self.c.session_transaction() as old:s.update(old)
  self.assertEqual(c2.get('/api/state/fixture').json['value']['note'],v['note'])
 def test_expired_candidate_hidden_reviewed_retained(self):
  self.item['expires_at']='2020-01-01T00:00:00+00:00';ingest(self.db,{'schema':1,'items':[self.item]});self.login();self.assertEqual(self.c.get('/api/items').json['items'],[])
 def test_expired_favorite_keeps_link_not_upstream_summary(self):
  self.item['expires_at']='2020-01-01T00:00:00+00:00';ingest(self.db,{'schema':1,'items':[self.item]});self.login()
  self.put(self.item['id'],{'saved':True,'note':'my own note'})
  row=self.c.get('/api/items').json['items'][0]
  self.assertEqual(row['summary'],'');self.assertTrue(row['expired']);self.assertEqual(row['personal']['note'],'my own note')
 def test_course_original_and_server_bridge(self):
  self.login()
  for name in ['llm','lab']:
   r=self.c.get('/learn/'+name);self.assertEqual(r.status_code,200);self.assertIn(b'/static/course-sync.js',r.data)
  self.assertEqual(self.c.get('/learn/../../.private/config.json').status_code,404)
 def test_ingest_token_and_headers(self):
  r=self.c.post('/api/ingest',json={'schema':1,'items':[self.item]},headers={'Authorization':'Bearer test-ingest'});self.assertEqual(r.status_code,200)
  self.assertEqual(r.headers['Cache-Control'],'no-store');self.assertIn('frame-ancestors',r.headers['Content-Security-Policy'])
 def test_task_and_course_state(self):
  self.login()
  for key,val in [('task:quality',{'status':'进行中','note':'实测记录'}),('xunxu-knowledge-lab-v1',{'last':'eval/0','done':['eval'],'answers':{},'notes':{'eval':'test'}})]:
   self.assertEqual(self.put(key,val).status_code,200);self.assertEqual(self.c.get('/api/state/'+key).json['value'],val)
 def test_feedback_return_channel(self):
  self.login();self.put('fixture',{'feedback':'值得深读','note':'private note'})
  self.assertEqual(self.c.get('/api/sync-feedback').status_code,401)
  r=self.c.get('/api/sync-feedback',headers={'Authorization':'Bearer test-ingest'})
  self.assertEqual(r.json['events'][0]['label'],'值得深读');self.assertNotIn('private note',r.text)
if __name__=='__main__':unittest.main(verbosity=2)
