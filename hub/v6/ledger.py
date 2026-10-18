"""Phase-one ingestion ledger. Reuses the existing collector, no private ranking.

All network caches and SQLite state belong to the explicitly supplied V6 directory.
The application_id guard refuses existing hub databases, even if paths are mistaken.
"""
import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import sqlite3
from pathlib import Path

APP_ID = 0x58555636
PUBLIC_FIELDS = ('url', 'title', 'summary', 'published_at', 'updated_at', 'scope', 'categories', 'sources')
SUCCESS = {'ok', 'empty', 'not_modified'}


def open_ledger(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(path)
    tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if tables and c.execute('PRAGMA application_id').fetchone()[0] != APP_ID:
        c.close()
        raise ValueError('Refusing a non-V6 database; production databases are never migrated')
    c.executescript(f'''
        PRAGMA application_id={APP_ID};
        PRAGMA foreign_keys=ON;
        CREATE TABLE IF NOT EXISTS source_runs(
          id INTEGER PRIMARY KEY, source TEXT NOT NULL, checked_at TEXT NOT NULL,
          status TEXT NOT NULL, fetched_count INTEGER NOT NULL, changed_count INTEGER NOT NULL,
          detail TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS articles(
          url TEXT PRIMARY KEY, body TEXT NOT NULL, fingerprint TEXT NOT NULL,
          first_seen TEXT NOT NULL, last_seen TEXT NOT NULL,
          verification_status TEXT NOT NULL DEFAULT 'candidate');
        CREATE TABLE IF NOT EXISTS observations(
          source TEXT NOT NULL, url TEXT NOT NULL REFERENCES articles(url),
          first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, body TEXT NOT NULL, PRIMARY KEY(source,url));
        CREATE TABLE IF NOT EXISTS source_state(
          source TEXT PRIMARY KEY, last_success TEXT, published_watermark TEXT);
    ''')
    return c


def record(c, source, rows, info, canonical):
    """Atomic upsert plus durable per-source observations; never copies personal fields."""
    at = info['checked_at']
    status = info['status']
    changed = 0
    with c:
        for raw in rows:
            item = {key: raw.get(key) for key in PUBLIC_FIELDS}
            if not isinstance(item['url'], str) or not item['url']:
                raise ValueError('Missing public URL')
            item['url'] = canonical(item['url'])
            # Provenance is retained per source in observations, not collapsed into a
            # fabricated independent-source count. Cache responses are not fresh fetches.
            body = json.dumps(item, ensure_ascii=False, sort_keys=True)
            fp = hashlib.sha256(body.encode()).hexdigest()
            old = c.execute('SELECT body FROM observations WHERE source=? AND url=?', (source, item['url'])).fetchone()
            changed += int(old is None or old[0] != body)
            c.execute('''INSERT INTO articles(url,body,fingerprint,first_seen,last_seen) VALUES(?,?,?,?,?)
              ON CONFLICT(url) DO UPDATE SET body=excluded.body,fingerprint=excluded.fingerprint,
              last_seen=excluded.last_seen''', (item['url'], body, fp, at, at))
            c.execute('''INSERT INTO observations VALUES(?,?,?,?,?) ON CONFLICT(source,url)
              DO UPDATE SET last_seen=excluded.last_seen,body=excluded.body''', (source, item['url'], at, at, body))
        # Only a successful upstream response advances the success clock.
        if status in SUCCESS:
            dates = []
            for row in rows:
                try:
                    value = dt.datetime.fromisoformat((row.get('published_at') or '').replace('Z', '+00:00'))
                    if value.tzinfo and value <= dt.datetime.fromisoformat(at):
                        dates.append(value.astimezone(dt.timezone.utc).isoformat())
                except ValueError:
                    pass
            watermark = max(dates) if dates else None
            c.execute('''INSERT INTO source_state VALUES(?,?,?) ON CONFLICT(source)
              DO UPDATE SET last_success=excluded.last_success,
              published_watermark=CASE WHEN excluded.published_watermark IS NULL THEN published_watermark
              WHEN published_watermark IS NULL THEN excluded.published_watermark
              ELSE MAX(published_watermark,excluded.published_watermark) END''', (source, at, watermark))
        detail = {k: info[k] for k in ('http_status', 'retry_after', 'error', 'bytes') if k in info}
        c.execute('INSERT INTO source_runs(source,checked_at,status,fetched_count,changed_count,detail) VALUES(?,?,?,?,?,?)',
                  (source, at, status, len(rows), changed, json.dumps(detail)))
    return changed


def run(collector, sources, state, offline=False):
    collector, state = Path(collector).resolve(), Path(state).resolve()
    # Do not allow the new runner to modify the old collector's caches/state.
    if state == collector.parent.parent or collector.parent.parent in state.parents:
        raise ValueError('V6 state must be outside the existing collector directory')
    spec = importlib.util.spec_from_file_location('existing_inbox', collector)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    state.mkdir(parents=True, exist_ok=True)
    # POSIX lock guards the entire fetch+commit batch against overlapping schedulers.
    import fcntl
    with (state / 'run.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        c = open_ledger(state / 'v6.sqlite')
        result = []
        try:
            for source in sources:
                rows, info = module.fetch(source, state / 'cache', offline=offline)
                changed = record(c, source['id'], rows, info, module.canonical)
                result.append({'source': source['id'], 'status': info['status'], 'count': len(rows), 'changed': changed})
            report = {'stage':'V6 phase 1; no semantic clustering or quality scores yet',
                      'runs':result, 'articles':c.execute('SELECT COUNT(*) FROM articles').fetchone()[0]}
            temp = state / 'report.tmp'
            temp.write_text(json.dumps(report, ensure_ascii=False, indent=2))
            temp.replace(state / 'report.json')
            return report
        finally:
            c.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--collector', type=Path, required=True)
    p.add_argument('--sources', type=Path, required=True)
    p.add_argument('--state', type=Path, required=True)
    p.add_argument('--offline', action='store_true')
    args = p.parse_args()
    result = run(args.collector, json.loads(args.sources.read_text()), args.state, args.offline)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if any(row['status'] not in SUCCESS | {'cached','cache_interval'} for row in result['runs']):
        raise SystemExit(2)


if __name__ == '__main__':
    main()
