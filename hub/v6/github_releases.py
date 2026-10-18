"""Optional GitHub public-release ingestion for the isolated V6 research ledger.

No GitHub credentials, no arbitrary-URL fetches, no private repositories,
no publishing to the website, no background schedule. The upstream API is
public and the resulting records remain candidate until independently checked.
"""
import argparse
import datetime as dt
import fcntl
import gzip
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from hub.v6.ledger import open_ledger, record
from hub.v6.schema import sanitize

API_ROOT = 'https://api.github.com'
MAX_REPOS = 12
MAX_RELEASES = 20
MAX_BODY_BYTES = 1024 * 1024
REPO_RE = re.compile(r'^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9_.-]{1,80}$')


@dataclass(frozen=True)
class Response:
    status: int
    headers: dict
    body: bytes


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def http_get(url, headers):
    """Fixed-host unauthenticated GET; redirect and response size restricted."""
    if not url.startswith(API_ROOT + '/repos/'):
        raise ValueError('Refusing non-GitHub API URL')
    req = Request(url, headers={**headers, 'User-Agent': 'xunxu-v6-public-research/0.1',
                                'Accept': 'application/vnd.github+json',
                                'Accept-Encoding': 'gzip'})
    try:
        response = build_opener(NoRedirects()).open(req, timeout=12)
    except HTTPError as ex:
        if ex.code in (304, 403, 404, 429, 500, 502, 503):
            return Response(ex.code, dict(ex.headers), b'')
        raise
    with response as r:
        body = r.read(MAX_BODY_BYTES + 1)
        if len(body) > MAX_BODY_BYTES:
            raise ValueError('Oversized GitHub response')
        if r.headers.get('Content-Encoding', '').lower() == 'gzip':
            body = gzip.decompress(body)
        if len(body) > MAX_BODY_BYTES:
            raise ValueError('Oversized decoded GitHub response')
        return Response(r.status, dict(r.headers), body)


def validate_repo(repo):
    if not isinstance(repo, str) or not REPO_RE.fullmatch(repo):
        raise ValueError('Provide a public GitHub owner/repository identifier')
    owner, name = repo.split('/')
    if name in ('.', '..') or name.endswith('.git'):
        raise ValueError('Repository slug not supported')
    return owner + '/' + name


def source_id(repo):
    return 'github-release:' + hashlib.sha256(repo.casefold().encode()).hexdigest()[:24]


def endpoint(repo):
    repo = validate_repo(repo)
    return API_ROOT + '/repos/' + repo + '/releases?per_page=' + str(MAX_RELEASES)


def normalize_releases(repo, data):
    """Map official metadata only; no release-note bulk redistribution."""
    repo = validate_repo(repo)
    if not isinstance(data, list) or len(data) > MAX_RELEASES:
        raise ValueError('Invalid GitHub releases JSON')
    prefix = 'https://github.com/' + repo.casefold() + '/releases/tag/'
    base_url = 'https://github.com/' + repo
    rows = []
    for entry in data:
        if not isinstance(entry, dict) or entry.get('draft') is not False:
            continue
        url = entry.get('html_url')
        if not isinstance(url, str) or not url.casefold().startswith(prefix):
            raise ValueError('Unexpected GitHub release URL')
        published = entry.get('published_at')
        if published is not None and (not isinstance(published, str) or not published):
            raise ValueError('Invalid GitHub publication timestamp')
        tag = entry.get('tag_name')
        if not isinstance(tag, str) or not tag or len(tag) > 180:
            raise ValueError('Invalid GitHub release tag')
        name = entry.get('name') if isinstance(entry.get('name'), str) else ''
        title = (repo + ' — ' + (name or tag))[:2000]
        summary = ('GitHub 官方公开 Release 元数据；版本 ' + tag +
                   ('（预发布）' if entry.get('prerelease') else '') +
                   '。尚未核验许可证、运行效果或原文细节。')
        # A normalized public item is not a verified editorial selection.
        rows.append(sanitize({
            'url': url, 'title': title, 'summary': summary,
            'published_at': published, 'updated_at': None,
            'scope': 'GitHub public release metadata; unverified candidate',
            'categories': ['GitHub Release', '开源项目'],
            'sources': [{'id': 'github-public-releases', 'name': repo,
                         'entry_url': base_url}],
        }))
    return rows


def header(headers, key, default=''):
    return next((str(v) for k, v in headers.items() if k.casefold() == key.casefold()), default)


def retry_seconds(headers, status):
    raw = header(headers, 'Retry-After').strip()
    if raw.isdecimal():
        return min(24 * 3600, max(1, int(raw)))
    if status == 403 and header(headers, 'X-RateLimit-Remaining') == '0':
        reset = header(headers, 'X-RateLimit-Reset').strip()
        if reset.isdecimal():
            return max(60, min(24 * 3600, int(reset) - int(dt.datetime.now(dt.timezone.utc).timestamp())))
    return 0


def one_source(c, repo, meta, get=http_get, now=None):
    """One idempotent source run. ETag and 429 backoff survive process restart."""
    repo = validate_repo(repo)
    now = now or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:
        raise ValueError('now must be timezone-aware')
    checked = now.astimezone(dt.timezone.utc).isoformat()
    key = repo.casefold()
    snapshot = dict(meta.get(key) or {})
    if snapshot.get('next_allowed'):
        try:
            until = dt.datetime.fromisoformat(snapshot['next_allowed'])
            if now.astimezone(dt.timezone.utc) < until:
                return {'repo': repo, 'status': 'backoff', 'changed': 0,
                        'retry_at': until.isoformat()}
        except (TypeError, ValueError):
            snapshot.pop('next_allowed', None)

    headers = {}
    if snapshot.get('etag'):
        headers['If-None-Match'] = snapshot['etag']
    try:
        response = get(endpoint(repo), headers)
        if not isinstance(response, Response):
            raise TypeError('Transport must return Response')
        delay = retry_seconds(response.headers, response.status)
        if response.status == 200:
            data = json.loads(response.body)
            rows = normalize_releases(repo, data)
            status = 'ok' if rows else 'empty'
        elif response.status == 304:
            rows, status = [], 'not_modified'
        else:
            rows, status = [], 'http_error'
        detail = {'status': status, 'checked_at': checked, 'http_status': response.status}
        if delay:
            detail['retry_after'] = str(delay)
        changed = record(c, source_id(repo), rows, detail, lambda x: x)
        if status in ('ok', 'empty', 'not_modified'):
            etag = header(response.headers, 'ETag')
            if etag and len(etag) < 200:
                snapshot['etag'] = etag
            snapshot.pop('next_allowed', None)
        elif delay:
            snapshot['next_allowed'] = (now + dt.timedelta(seconds=delay)).isoformat()
        meta[key] = snapshot
        return {'repo': repo, 'status': status, 'changed': changed,
                'fetched': len(rows), 'http_status': response.status}
    except (ValueError, TypeError, UnicodeError, URLError, json.JSONDecodeError) as exc:
        # Error logs must not contain response bodies, tokens or user data.
        detail = {'status': 'parse_error', 'checked_at': checked, 'error': type(exc).__name__}
        record(c, source_id(repo), [], detail, lambda x: x)
        return {'repo': repo, 'status': 'parse_error', 'changed': 0}


def run(state, repositories, get=http_get):
    repos = [validate_repo(r) for r in repositories]
    if not repos or len(repos) > MAX_REPOS or len(set(r.casefold() for r in repos)) != len(repos):
        raise ValueError('Specify 1–12 unique public repositories')
    state = Path(state).resolve()
    state.mkdir(parents=True, exist_ok=True)
    with (state / 'run.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # application_id guard first, prior to writing any source-specific metadata.
        c = open_ledger(state / 'v6.sqlite')
        try:
            meta_path = state / 'github-release-state.json'
            meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
            if not isinstance(meta, dict):
                raise ValueError('Invalid GitHub state')
            results = []
            for repo in repos:
                results.append(one_source(c, repo, meta, get))
                # Write after durable ledger commit to avoid ETag skipping a failed transaction.
                temp = meta_path.with_suffix('.tmp')
                temp.write_text(json.dumps(meta, sort_keys=True))
                temp.replace(meta_path)
            return results
        finally:
            c.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--state', type=Path, required=True, help='Existing *isolated* V6 state directory')
    p.add_argument('--repo', action='append', required=True, help='Public owner/name; repeat up to 12 times')
    a = p.parse_args()
    results = run(a.state, a.repo)
    print(json.dumps(results, ensure_ascii=False, indent=2))
    if any(x['status'] in ('parse_error', 'http_error') for x in results):
        raise SystemExit(2)


if __name__ == '__main__':
    main()
