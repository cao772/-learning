import datetime as dt
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from werkzeug.security import generate_password_hash
from hub.app import create_app, ingest, connection
from hub.translation import (original_parts, source_fingerprint,
                             translate_deepl, TranslationError)


class TranslationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.database=str(Path(self.temp.name)/"translate.sqlite")
        self.app=create_app({
            "TESTING":True,"PUBLIC":True,"DB":self.database,
            "SECRET_KEY":"translation-tests","PASSWORD_HASH":
                generate_password_hash("pw",method="pbkdf2:sha256:1000"),
            "INGEST_TOKEN":"collector-secret","SESSION_COOKIE_SECURE":False,
            "TRANSLATE_KEY":"","TRANSLATE_PLAN":"free"
        })
        self.client=self.app.test_client()
        self.item={
            "id":"harness-info","title":"Agent Harness optimizes inference cost",
            "summary":"A source summary that needs independent verification.",
            "source":"Synthetic",
            "url":"https://example.org/agent/harness",
            "published_at":"2026-10-14","collected_at":"2026-10-15T01:00:00+00:00",
            "verification_status":"candidate",
            "expires_at":"2099-01-01T00:00:00+00:00"
        }
        ingest(self.database,{"schema":1,"items":[self.item]})

    def tearDown(self):
        self.temp.cleanup()

    def login(self):
        self.client.get('/login')
        with self.client.session_transaction() as session:
            csrf=session['login_csrf']
        self.assertEqual(self.client.post('/login',
             data={"csrf":csrf,"password":"pw"}).status_code,302)
        with self.client.session_transaction() as session:
            self.csrf=session['csrf']

    def post(self,body,token=True,identifier="harness-info"):
        return self.client.post('/api/translation/'+identifier,
          json=body,headers={"X-CSRF-Token":self.csrf} if token else {})

    def test_translation_is_private_and_manual_edits_never_update_feed(self):
        url='/api/translation/harness-info'
        guest=self.app.test_client()
        self.assertEqual(guest.get(url).status_code,401)
        self.assertEqual(guest.post(url,json={'mode':'automatic'}).status_code,401)
        self.login()
        first=self.client.get(url)
        self.assertEqual(first.status_code,200)
        self.assertFalse(first.json['automatic_available'])
        self.assertEqual(first.json['source']['title'],self.item['title'])
        self.assertIsNone(first.json['translation'])
        payload={'mode':'manual','revision':0,'title_zh':'Agent Harness 的推理成本优化',
                 'summary_zh':'这是需要核对的中文摘要'}
        self.assertEqual(self.post(payload,token=False).status_code,403)
        saved=self.post(payload)
        self.assertEqual(saved.status_code,200)
        self.assertEqual(saved.json['translation']['mode'],'manual')
        self.assertEqual(saved.json['revision'],1)
        self.assertEqual(self.client.get(url).json['translation']['title_zh'],
                         'Agent Harness 的推理成本优化')
        self.assertEqual(self.post(payload).status_code,409)
        with connection(self.database) as db:
            raw=json.loads(db.execute('SELECT body FROM items WHERE id=?',
                                      ('harness-info',)).fetchone()['body'])
            self.assertEqual(raw['title'],self.item['title'])
            self.assertNotIn('title_zh',raw)
        self.assertNotIn('中文摘要',guest.get('/').get_data(as_text=True))
        self.assertNotIn('中文摘要',str(guest.get('/api/items').json))

    def test_stale_translation_is_clearly_withheld(self):
        self.login()
        self.assertEqual(self.post({'mode':'manual','revision':0,
                   'title_zh':'人工翻译标题','summary_zh':'人工翻译内容'}).status_code,200)
        new={**self.item,'summary':'The source was revised by its publisher.'}
        ingest(self.database,{'schema':1,'items':[new]})
        value=self.client.get('/api/translation/harness-info').json
        self.assertTrue(value['stale'])
        self.assertIsNone(value['translation'])
        self.assertEqual(value['revision'],1)
        self.assertEqual(self.post({'mode':'manual','revision':1,
                   'title_zh':'更新的人工译文','summary_zh':'更新的译文'}).status_code,200)

    def test_automatic_opt_in_disabled_without_key(self):
        self.login()
        response=self.post({'mode':'automatic'})
        self.assertEqual(response.status_code,503)
        self.assertIn('尚未配置',response.json['error'])
        with connection(self.database) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM events WHERE kind='translation-request'").fetchone()[0],0)

    @patch('hub.app.translate_deepl',return_value=('Harness 翻译标题','正确摘要'))
    def test_provider_is_called_once_and_cached(self, provider):
        self.app.config['TRANSLATE_KEY']='testing-only'
        self.login()
        first=self.post({'mode':'automatic'})
        self.assertEqual(first.status_code,200)
        self.assertEqual(first.json['translation']['mode'],'automatic')
        self.assertEqual(first.json['translation']['title_zh'],'Harness 翻译标题')
        self.assertEqual(self.post({'mode':'automatic'}).json['cached'],True)
        provider.assert_called_once()
        with connection(self.database) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM events WHERE kind='translation-request'").fetchone()[0],1)
        manual=self.post({'mode':'manual','revision':1,'title_zh':'我修正的译文','summary_zh':'术语修正'})
        self.assertEqual(manual.status_code,200)
        self.assertEqual(self.post({'mode':'automatic'}).json['translation']['mode'],'manual')
        provider.assert_called_once()

    @patch('hub.app.translate_deepl')
    def test_daily_provider_quota(self, provider):
        self.app.config['TRANSLATE_KEY']='testing-only'
        self.login()
        with connection(self.database) as db:
            for _ in range(10):
                db.execute("INSERT INTO events(at,kind,item_id) VALUES(?,?,?)",
                    (dt.datetime.now(dt.timezone.utc).isoformat(),
                     'translation-request','test'))
        self.assertEqual(self.post({'mode':'automatic'}).status_code,429)
        provider.assert_not_called()

    def test_fake_source_ids_and_long_text_rejected(self):
        self.login()
        self.assertEqual(self.post({'mode':'manual','revision':0,
            'title_zh':'a'},identifier='not-a-real-id').status_code,404)
        self.assertEqual(self.post({'mode':'manual','revision':0,
            'title_zh':'a','extra':'unexpected'}).status_code,400)
        self.assertEqual(self.post({'mode':'manual','revision':0,
            'title_zh':'a'*1001}).status_code,400)

    def test_provider_uses_only_fixed_https_endpoint_and_existing_snippets(self):
        called=[]
        def fake_open(request,timeout):
            called.append((request.full_url,request.get_method(),
                           request.data.decode('utf-8'),timeout))
            return io.BytesIO(json.dumps({'translations':[
                {'text':'中译标题'},{'text':'中译摘要'}]}).encode())
        result=translate_deepl('Agent tools','A short summary','test-key',
                               opener=fake_open)
        self.assertEqual(result,('中译标题','中译摘要'))
        self.assertEqual(called[0][0],'https://api-free.deepl.com/v2/translate')
        self.assertIn('target_lang=ZH',called[0][2])
        self.assertNotIn('https://example.org',called[0][2])
        self.assertEqual(original_parts({'title':'X','summary':'Y'}),('X','Y'))
        self.assertNotEqual(source_fingerprint('X','Y'),source_fingerprint('X','Z'))


if __name__=='__main__':
    unittest.main()
