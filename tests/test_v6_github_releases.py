import datetime as dt
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from hub.v6.github_releases import (
    Response, endpoint, normalize_releases, one_source,
    retry_seconds, run, validate_repo,
)
from hub.v6.ledger import open_ledger


def release(name='v1.2.3', repo='acme/tool', date='2026-10-17T08:00:00Z'):
    return {
        'draft': False, 'prerelease': False, 'tag_name': name,
        'name': 'Update ' + name,
        'published_at': date,
        'html_url': 'https://github.com/' + repo + '/releases/tag/' + name,
        'body': 'PRIVATE? Only GitHub public release notes, intentionally not copied',
        'author': {'email': 'must-not-save@example.com'},
    }


class PublicGithubSourcesTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.state = Path(self.directory.name) / 'isolated'
        self.c = open_ledger(self.state / 'v6.sqlite')
        self.addCleanup(self.c.close)
        self.now = dt.datetime(2026, 10, 18, 12, tzinfo=dt.timezone.utc)

    def test_fixed_api_host_and_repository_validation(self):
        self.assertEqual(endpoint('acme/tool'),
                         'https://api.github.com/repos/acme/tool/releases?per_page=20')
        for value in ('http://127.0.0.1/', 'https://github.com/o/r', 'owner/', 
                      '../secret', 'foo/repo/../x', 'a/b.git', 'a/.', '', 'bad host/x'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_repo(value)

    def test_release_mapping_drops_body_and_private_fields(self):
        rows = normalize_releases('acme/tool', [release()])
        self.assertEqual(len(rows), 1)
        self.assertIn('2026-10-17', rows[0]['published_at'])
        self.assertEqual(rows[0]['updated_at'], None)
        serialized = json.dumps(rows)
        self.assertNotIn('must-not-save@example.com', serialized)
        self.assertNotIn('PRIVATE?', serialized)
        self.assertNotIn('author', serialized)
        self.assertEqual(len(rows[0]['sources']), 1)
        self.assertEqual(rows[0]['scope'], 'GitHub public release metadata; unverified candidate')

    def test_rejects_wrong_host_draft_and_bad_payload(self):
        with self.assertRaises(ValueError):
            normalize_releases('acme/tool', [{**release(), 'html_url':'http://127.0.0.1/'}])
        with self.assertRaises(ValueError):
            normalize_releases('acme/tool', {})
        self.assertEqual(normalize_releases('acme/tool', [{**release(), 'draft':True}]), [])

    def test_conditional_get_304_and_idempotency(self):
        state = {}
        calls = []
        def get(url, headers):
            calls.append((url, dict(headers)))
            if headers.get('If-None-Match'):
                return Response(304, {'ETag':'"release-v1"'}, b'')
            return Response(200, {'ETag':'"release-v1"'}, json.dumps([release()]).encode())
        first = one_source(self.c, 'acme/tool', state, get, self.now)
        second = one_source(self.c, 'acme/tool', state, get, self.now + dt.timedelta(hours=1))
        self.assertEqual((first['changed'],second['changed']), (1,0))
        self.assertEqual(second['status'],'not_modified')
        self.assertEqual(calls[1][1]['If-None-Match'],'"release-v1"')
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM articles').fetchone()[0],1)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM observations').fetchone()[0],1)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM source_runs').fetchone()[0],2)

    def test_429_durable_backoff_prevents_requests(self):
        state = {}
        calls = []
        def get(url, headers):
            calls.append(url)
            return Response(429,{'Retry-After':'3600'},b'')
        first = one_source(self.c,'acme/tool',state,get,self.now)
        self.assertEqual(first['status'],'http_error')
        second = one_source(self.c,'acme/tool',state,get,self.now+dt.timedelta(minutes=2))
        self.assertEqual(second['status'],'backoff')
        self.assertEqual(len(calls),1)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM articles').fetchone()[0],0)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM source_runs').fetchone()[0],1)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM source_state').fetchone()[0],0)
        self.assertEqual(retry_seconds({'Retry-After':'999999999'},429),86400)

    def test_invalid_200_fails_closed_without_advancing_watermark(self):
        state={}
        result=one_source(self.c,'acme/tool',state,
                          lambda url,headers: Response(200,{},b'{"items":[]}'),self.now)
        self.assertEqual(result['status'],'parse_error')
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM source_state').fetchone()[0],0)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM source_runs').fetchone()[0],1)

    def test_cli_run_reuses_isolated_ledger_and_replay(self):
        # The CLI path is tested with transport injection; CI never scrapes live GitHub.
        def get(url,headers):
            return Response(200, {'ETag':'"a"'}, json.dumps([release()]).encode())
        result=run(self.state,['acme/tool'],get=get)
        again=run(self.state,['acme/tool'],get=get)
        self.assertEqual(result[0]['changed'],1)
        self.assertEqual(again[0]['changed'],0)
        self.assertTrue((self.state/'github-release-state.json').exists())
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM articles').fetchone()[0],1)

    def test_production_database_application_id_rejected(self):
        state = Path(self.directory.name) / 'wrong'
        state.mkdir()
        with sqlite3.connect(state/'v6.sqlite') as db:
            db.execute('CREATE TABLE personal(key TEXT)')
        with self.assertRaises(ValueError):
            run(state,['acme/tool'], get=lambda url,headers: Response(200,{},b'[]'))
        self.assertFalse((state/'github-release-state.json').exists())

    def test_repo_budget_and_duplicates(self):
        with self.assertRaises(ValueError):
            run(self.state,['Acme/tool','acme/TOOL'], get=lambda url,headers: Response(200,{},b'[]'))
        with self.assertRaises(ValueError):
            run(self.state, ['owner/repo%d' % i for i in range(13)],
                get=lambda url,headers: Response(200,{},b'[]'))


if __name__=='__main__':
    unittest.main()
