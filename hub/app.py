"""Single-owner learning hub. No upstream collection or model calls."""
import datetime as dt
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import sqlite3
import time
from urllib.parse import urlsplit
from flask import Flask, request, session, jsonify, redirect, render_template, send_file, abort
from werkzeug.security import check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
from hub.discovery import INTERESTS, CATALOG, DEFAULT_WEIGHTS, rank_items, canonical_link, capture_key, normalize_profile
from hub.research import connect_sources, research_brief, interest_collections, suggested_research
from hub.content_category import classify_item, apply_owner_category, category_overview, CATEGORIES, LABELS as CATEGORY_LABELS
from hub.translation import original_parts, source_fingerprint, translate_deepl, TranslationError
from hub.recommendation import balance_recommendations

ROOT=Path(__file__).resolve().parent.parent
COURSES={'llm':'llm-learning.html','lab':'new-knowledge.html'}
KEYS={'xunxu-llm-course-v1','xunxu-llm-course-v2','xunxu-llm-course-v3','xunxu-knowledge-lab-v1'}
LABELS=['已用上','值得深读','有趣但暂不用','现在用不上','重复','证据不好']

def utc(): return dt.datetime.now(dt.timezone.utc).isoformat()
def connection(path):
    db=sqlite3.connect(path,timeout=15);db.row_factory=sqlite3.Row;db.execute('PRAGMA journal_mode=WAL'); return db

def initialize(path):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    with connection(path) as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS items(id TEXT PRIMARY KEY, body TEXT NOT NULL, updated TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS personal(id TEXT PRIMARY KEY, body TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS batches(id TEXT PRIMARY KEY, at TEXT NOT NULL, count INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, at TEXT NOT NULL, kind TEXT NOT NULL, item_id TEXT);
        CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS attempts(ip TEXT NOT NULL, at REAL NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_attempts_ip_at ON attempts(ip, at);
        CREATE INDEX IF NOT EXISTS idx_batches_at ON batches(at DESC);
        PRAGMA user_version=1;
        ''')
    os.chmod(path,0o600)

def safe_url(value):
    u=urlsplit(value)
    if u.scheme not in ('http','https') or not u.hostname or u.username or u.password: raise ValueError('invalid URL')
    return value

def ingest(path,payload):
    if not isinstance(payload,dict) or payload.get('schema')!=1: raise ValueError('schema must be 1')
    rows=payload.get('items')
    if not isinstance(rows,list) or len(rows)>1000: raise ValueError('items limit 1000')
    for x in rows:
        if not isinstance(x,dict) or not isinstance(x.get('id'),str) or not 1<=len(x['id'])<=100: raise ValueError('invalid id')
        if not isinstance(x.get('title'),str) or len(x['title'])>1000: raise ValueError('invalid title')
        if x.get('verification_status') not in ('candidate','reviewed'): raise ValueError('invalid status')
        if x['verification_status']=='candidate' and not x.get('expires_at'):raise ValueError('candidate expiry required')
        safe_url(x['url'])
        for e in x.get('evidence',[]): safe_url(e['url'])
        if x['verification_status']=='reviewed' and not (x.get('evidence') and x.get('scope') and x.get('learning_value')): raise ValueError('review evidence required')
        for field in ('published_at','collected_at','expires_at'):
            if x.get(field):
                parsed=dt.datetime.fromisoformat(x[field].replace('Z','+00:00'))
                if field=='expires_at' and parsed.tzinfo is None:raise ValueError('expiry needs timezone')
    canonical=json.dumps(payload,sort_keys=True,ensure_ascii=False)
    batch=hashlib.sha256(canonical.encode()).hexdigest()
    with connection(path) as db:
        if db.execute('SELECT 1 FROM batches WHERE id=?',(batch,)).fetchone(): return {'batch_id':batch,'changed':0,'duplicate':True}
        changed=0
        for x in rows:
            old=db.execute('SELECT body FROM items WHERE id=?',(x['id'],)).fetchone()
            body=json.dumps(x,sort_keys=True,ensure_ascii=False)
            # A candidate update must never downgrade an editorial decision.
            if old and json.loads(old['body'])['verification_status']=='reviewed' and x['verification_status']=='candidate': continue
            if not old or old['body']!=body:
                db.execute('INSERT INTO items VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body,updated=excluded.updated',(x['id'],body,utc()));changed+=1
        db.execute('INSERT INTO metadata VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',('source_status',json.dumps(payload.get('source_status',{}))))
        db.execute('INSERT INTO batches VALUES(?,?,?)',(batch,utc(),len(rows)))
        db.execute('INSERT INTO events(at,kind) VALUES(?,?)',(utc(),'ingest'))
    return {'batch_id':batch,'changed':changed,'duplicate':False}

def create_app(config=None):
    app=Flask(__name__)
    app.config.update(PUBLIC=os.environ.get('HUB_PUBLIC','0')=='1',SECRET_KEY=os.environ.get('HUB_SECRET'),DB=os.environ.get('HUB_DB',str(ROOT/'.private/hub.sqlite')),PASSWORD_HASH=os.environ.get('HUB_PASSWORD_HASH'),INGEST_TOKEN=os.environ.get('HUB_INGEST_TOKEN'),MAX_CONTENT_LENGTH=2*1024*1024,SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Strict',SESSION_COOKIE_SECURE=os.environ.get('HUB_SECURE','1')=='1',PERMANENT_SESSION_LIFETIME=dt.timedelta(hours=12),TRUST_PROXY=os.environ.get('HUB_TRUST_PROXY','0')=='1',TRUSTED_HOSTS=['localhost','127.0.0.1','yanhaoo.com'])
    app.config.update(TRANSLATE_KEY=os.environ.get('HUB_TRANSLATE_DEEPL_KEY',''),TRANSLATE_PLAN=os.environ.get('HUB_TRANSLATE_DEEPL_PLAN','free'))
    if config: app.config.update(config)
    # Trust only the single Caddy hop in production; preflight direct access must disable this.
    if app.config['TRUST_PROXY']:
        app.wsgi_app=ProxyFix(app.wsgi_app,x_for=1,x_proto=1)
    if not all(app.config.get(k) for k in ('SECRET_KEY','PASSWORD_HASH','INGEST_TOKEN')): raise RuntimeError('Initialize private config before starting')
    initialize(app.config['DB'])
    def db(): return connection(app.config['DB'])
    def authenticated():
        if not session.get('sid'): return False
        with db() as c: return c.execute('SELECT 1 FROM sessions WHERE id=? AND expires>?',(session['sid'],time.time())).fetchone() is not None
    @app.before_request
    def guard():
        if request.path in ('/healthz','/favicon.ico'): return None
        if request.path in ('/api/ingest','/api/sync-feedback'):
            token=request.headers.get('Authorization','').removeprefix('Bearer ')
            if not hmac.compare_digest(token,app.config['INGEST_TOKEN']): abort(401)
            return None
        if request.path.startswith('/static/') or request.path=='/login': return None
        if app.config['PUBLIC'] and request.method in ('GET','HEAD') and (request.path in ('/','/api/items') or request.path in ('/learn/llm','/learn/lab')): return None
        if not authenticated():
            if request.path.startswith('/api/'): abort(401)
            return redirect('/login')
        if request.method not in ('GET','HEAD','OPTIONS'):
            token=request.headers.get('X-CSRF-Token') or request.form.get('csrf','')
            if not hmac.compare_digest(token,session.get('csrf','!')): abort(403)
    @app.after_request
    def headers(response):
        response.headers['Cache-Control']='no-store'
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['X-Frame-Options']='SAMEORIGIN'
        response.headers['Referrer-Policy']='same-origin'
        response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'self'; base-uri 'self'; form-action 'self'; object-src 'none'"
        response.headers['Permissions-Policy']='camera=(), microphone=(), geolocation=(), payment=()'
        response.headers['Cross-Origin-Opener-Policy']='same-origin'
        response.headers['Cross-Origin-Resource-Policy']='same-origin'
        if app.config['SESSION_COOKIE_SECURE']:response.headers['Strict-Transport-Security']='max-age=31536000'
        return response
    @app.route('/login',methods=['GET','POST'])
    def login():
        session.setdefault('login_csrf',secrets.token_urlsafe(24));error=None
        if request.method=='POST':
            if not hmac.compare_digest(request.form.get('csrf',''),session['login_csrf']):abort(403)
            ip=request.remote_addr or 'unknown'
            with db() as c:
                c.execute('DELETE FROM attempts WHERE at<?',(time.time()-900,))
                count=c.execute('SELECT count(*) FROM attempts WHERE ip=?',(ip,)).fetchone()[0]
                if count>=8:abort(429)
                c.execute('INSERT INTO attempts VALUES(?,?)',(ip,time.time()))
            if check_password_hash(app.config['PASSWORD_HASH'],request.form.get('password','')):
                session.clear();session.permanent=True;session['sid']=secrets.token_urlsafe(32);session['csrf']=secrets.token_urlsafe(32)
                with db() as c:
                    c.execute('DELETE FROM sessions WHERE expires<?',(time.time(),));c.execute('INSERT INTO sessions VALUES(?,?)',(session['sid'],time.time()+43200));c.execute('DELETE FROM attempts WHERE ip=?',(ip,))
                return redirect('/admin' if app.config['PUBLIC'] else '/')
            error='口令不正确，请重试。'
        return render_template('login.html',csrf=session['login_csrf'],error=error)
    @app.post('/logout')
    def logout():
        with db() as c:c.execute('DELETE FROM sessions WHERE id=?',(session['sid'],))
        session.clear();return redirect('/login')
    @app.get('/favicon.ico')
    def favicon():return '',204
    @app.get('/healthz')
    def health():
        with db() as c:c.execute('SELECT 1')
        return jsonify(ok=True)
    def public_items():
        # Explicit allowlist: never serialize personal state or arbitrary ingest fields.
        fields={'id','title','url','published_at','source','topic','summary','verification_status','scope','verification_notes','learning_value'}
        result=[]
        with db() as c:
            for row in c.execute('SELECT body FROM items'):
                x=json.loads(row['body'])
                if x.get('expires_at') and x['verification_status']=='candidate' and dt.datetime.fromisoformat(x['expires_at'])<dt.datetime.now(dt.timezone.utc):continue
                result.append({**{k:v for k,v in x.items() if k in fields}, **classify_item(x)})
        return sorted(result,key=lambda x:x.get('published_at') or '',reverse=True)
    @app.get('/')
    def home():
        if app.config['PUBLIC']:
            with db() as c:
                last=c.execute('SELECT at FROM batches ORDER BY at DESC LIMIT 1').fetchone()
            return render_template('public.html',items=public_items(),last_sync=last['at'] if last else None,categories=CATEGORIES)
        return render_template('index.html',csrf=session['csrf'])
    @app.get('/admin')
    def admin():return render_template('index.html',csrf=session['csrf'])
    @app.get('/api/discover')
    def discover():
        # Protected by before_request. Never expose the owner's interests or bookmarks publicly.
        with db() as c:
            state_rows = c.execute('SELECT id,body,revision FROM personal').fetchall()
            stored = {row['id']:{**json.loads(row['body']),'revision':row['revision']} for row in state_rows}
            profile_record = stored.get('profile:interests', {})
            profile = normalize_profile(profile_record)
            candidates = []
            for row in c.execute('SELECT body FROM items'):
                item = json.loads(row['body'])
                item['personal'] = stored.get(item['id'], {})
                candidates.append(item)
            captures = [{**value, 'id': key}
                        for key,value in stored.items() if key.startswith('capture:')]
        captures.sort(key=lambda x: x.get('added_at') or '', reverse=True)
        ranked = rank_items(candidates, profile, limit=300)
        # Category presentation is independent of interest preference weights.
        for row in ranked:
            row.update(apply_owner_category(row['item'],stored.get('category:'+str(row['item']['id']))))
        study_records={key[len('research:'):]:value for key,value in stored.items()
                       if key.startswith('research:') and isinstance(value,dict)}
        balanced=balance_recommendations(ranked,study_records,limit=80)
        ranked=balanced['ranking']
        captures = captures[:100]
        for entry in captures:
            entry.update(apply_owner_category(entry,stored.get('category:'+str(entry['id']))))
        guidance = {str(row['item']['id']): research_brief(row['item']) for row in ranked}
        guidance.update({str(x['id']):research_brief(x) for x in captures})
        return jsonify(
            topics=[{'key':key,'label':value['label']} for key,value in INTERESTS.items()],
            profile=profile, profile_revision=profile_record.get('revision',0),
            sources=CATALOG, ranking=ranked, recommendation=balanced['meta'], categories=category_overview(ranked), captures=captures,
            connections=connect_sources(ranked,captures), topic_groups=interest_collections(ranked),
            research_suggestions=suggested_research(
                ranked, [key[len('research:'):] for key in stored if key.startswith('research:')]),
            research_guides=guidance,
            research_records=[
                {'key':key[len('research:'):],**value} for key,value in stored.items()
                if key.startswith('research:') and isinstance(value,dict)
            ],
            ranking_method='显式关键词、时间、核验、收藏与研究状态；前排来源/类别柔性分散；没有调用模型，也没有查询 Github 星数'
        )

    @app.route('/api/translation/<path:item_id>',methods=['GET','POST'])
    def translate_item(item_id):
        # This is owner-only via the existing session/CSRF guard.
        if not item_id or len(item_id)>100:abort(400)
        with db() as c:
            if item_id.startswith('capture:'):
                row=c.execute('SELECT body FROM personal WHERE id=?',(item_id,)).fetchone()
            else:
                row=c.execute('SELECT body FROM items WHERE id=?',(item_id,)).fetchone()
            if not row:abort(404)
            original=json.loads(row['body'])
            try:
                title,summary=original_parts(original)
            except ValueError:
                abort(422,description='原文摘要超出翻译长度限制')
            digest=source_fingerprint(title,summary)
            key='translation:'+item_id
            row=c.execute('SELECT body,revision FROM personal WHERE id=?',(key,)).fetchone()
            existing=json.loads(row['body']) if row else None
            revision=row['revision'] if row else 0
            fresh=bool(existing and existing.get('source_hash')==digest)
            cached=existing if fresh else None
            if request.method=='GET':
                return jsonify(source={'title':title,'summary':summary,'url':original.get('url')},
                    translation=cached,stale=bool(existing and not fresh),revision=revision,
                    automatic_available=bool(app.config['TRANSLATE_KEY']),
                    provider='DeepL（用户明确触发，按服务套餐计费/计量）' if app.config['TRANSLATE_KEY'] else None)
            payload=request.get_json(silent=True)
            if not isinstance(payload,dict):abort(400)
            action=payload.get('mode')
            if action not in ('manual','automatic') or set(payload)-({'mode','title_zh','summary_zh','revision'} if action=='manual' else {'mode'}):
                abort(400)
            if action=='automatic' and cached:
                return jsonify(translation=cached,revision=revision,cached=True)
            if action=='manual' and (type(payload.get('revision')) is not int
                                      or payload['revision']!=revision):
                return jsonify(error='译文已被其他设备更新，请刷新后重试',revision=revision),409
            if action=='automatic':
                if not app.config['TRANSLATE_KEY']:
                    return jsonify(error='尚未配置自动翻译服务，可手工录入译文'),503
                # Strict per-owner daily ceiling protects billing. Count requests, not
                # claimed success; the source itself is never re-fetched.
                start=dt.datetime.now(dt.timezone.utc).date().isoformat()
                n=c.execute("SELECT count(*) FROM events WHERE kind='translation-request' AND at>=?",(start,)).fetchone()[0]
                if n>=10:return jsonify(error='今天的自动翻译次数达到 10 次上限'),429
                c.execute('INSERT INTO events(at,kind,item_id) VALUES(?,?,?)',(utc(),'translation-request',item_id))
        if action=='automatic':
            try:
                translated_title,translated_summary=translate_deepl(
                    title,summary,app.config['TRANSLATE_KEY'],app.config['TRANSLATE_PLAN'])
            except TranslationError as ex:
                return jsonify(error=str(ex)),502
            mode='automatic';origin='DeepL · 机器译文，未经人工校核'
        else:
            translated_title=payload.get('title_zh')
            translated_summary=payload.get('summary_zh','')
            if (not isinstance(translated_title,str) or not isinstance(translated_summary,str)
                    or not 1<=len(translated_title.strip())<=1000
                    or len(translated_summary)>5000):abort(400)
            mode='manual';origin='站主人工录入或修订'
        result={'title_zh':translated_title.strip(),
                'summary_zh':translated_summary.strip(),
                'mode':mode,'label':origin,'source_hash':digest,
                'translated_at':utc(),'target_language':'zh-CN'}
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            # Re-fetch to prevent storing a stale translation if an ingest raced
            # the outbound request.
            table='personal' if item_id.startswith('capture:') else 'items'
            latest=c.execute('SELECT body FROM '+table+' WHERE id=?',(item_id,)).fetchone()
            if not latest:abort(409)
            a,b=original_parts(json.loads(latest['body']))
            if source_fingerprint(a,b)!=digest:return jsonify(error='原文已更新，请刷新后重试'),409
            old=c.execute('SELECT revision FROM personal WHERE id=?',(key,)).fetchone()
            revision=old['revision'] if old else 0
            if action=='manual' and revision!=payload['revision']:
                return jsonify(error='译文已被其他设备更新，请刷新后重试',revision=revision),409
            c.execute('INSERT INTO personal VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body,revision=excluded.revision',
                      (key,json.dumps(result,ensure_ascii=False),revision+1))
        return jsonify(translation=result,revision=revision+1,cached=False)

    @app.post('/api/capture')
    def capture():
        body = request.get_json(silent=True)
        if not isinstance(body,dict): abort(400)
        try:
            url = canonical_link(body.get('url'))
        except (ValueError, TypeError):
            abort(400)
        title, note, source = body.get('title'), body.get('note',''), body.get('source','手动收集')
        if not isinstance(title,str) or not 1 <= len(title.strip()) <= 200: abort(400)
        if not isinstance(note,str) or len(note) > 3000: abort(400)
        if not isinstance(source,str) or len(source) > 80: abort(400)
        key = capture_key(url)
        record = {'url':url,'title':title.strip(),'note':note.strip(),'source':source.strip() or '手动收集',
                  'added_at':utc(),'verification_status':'candidate','reviewed':False}
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            existing = c.execute('SELECT 1 FROM personal WHERE id=?',(key,)).fetchone()
            if existing: return jsonify(id=key,duplicate=True)
            c.execute('INSERT INTO personal VALUES(?,?,?)',
                      (key,json.dumps(record,ensure_ascii=False),1))
        return jsonify(id=key,duplicate=False),201

    @app.get('/api/items')
    def items():
        if app.config['PUBLIC'] and not authenticated():return jsonify(items=public_items())
        result=[]
        with db() as c:
            rows=c.execute('SELECT id,body FROM items').fetchall()
            personal={x['id']:{**json.loads(x['body']),'revision':x['revision']} for x in c.execute('SELECT * FROM personal')}
            for row in rows:
                x=json.loads(row['body']); state=personal.get(x['id'],{'revision':0})
                expired=x.get('expires_at') and x['verification_status']=='candidate' and dt.datetime.fromisoformat(x['expires_at'])<dt.datetime.now(dt.timezone.utc)
                if expired:
                    if state.get('saved') or state.get('note') or state.get('draft'):
                        # Keep only link metadata and user's own work after upstream cache expiry.
                        x['summary']='';x['scope']='订阅摘要已过期，仅保留来源链接与自己的笔记';x['expired']=True
                        c.execute('UPDATE items SET body=? WHERE id=?',(json.dumps(x,ensure_ascii=False),x['id']))
                    else:
                        c.execute('DELETE FROM items WHERE id=?',(x['id'],));continue
                x['personal']=state;result.append(x)
        result.sort(key=lambda x:x.get('published_at') or '',reverse=True)
        return jsonify(items=result)
    @app.post('/api/ingest')
    def incoming():
        try:return jsonify(ingest(app.config['DB'],request.get_json()))
        except (ValueError,KeyError,TypeError):abort(400)
    @app.route('/api/state/<path:key>',methods=['GET','PUT'])
    def state(key):
        if len(key)>160:abort(400)
        with db() as c:
            row=c.execute('SELECT * FROM personal WHERE id=?',(key,)).fetchone()
            if request.method=='GET':return jsonify(value=json.loads(row['body']) if row else None,revision=row['revision'] if row else 0)
            data=request.get_json(); value=data.get('value');expected=data.get('revision')
            if not isinstance(value,dict) or len(json.dumps(value))>300000:abort(400)
            if key in KEYS and any(k not in {'last','lesson','step','done','answers','notes'} for k in value):abort(400)
            if value.get('feedback') and value['feedback'] not in LABELS:abort(400)
            if key.startswith('category:'):
                item_id=key[len('category:'):]
                if not item_id or len(item_id)>100:abort(400)
                # Category corrections only apply to an existing feed or private capture.
                exists_feed=c.execute('SELECT 1 FROM items WHERE id=?',(item_id,)).fetchone()
                exists_capture=(item_id.startswith('capture:') and
                                c.execute('SELECT 1 FROM personal WHERE id=?',(item_id,)).fetchone())
                if not (exists_feed or exists_capture):abort(404)
                if (set(value) - {'category','note'}
                    or type(value.get('category')) is not str
                    or value.get('category') not in (set(CATEGORY_LABELS)|{'auto'})
                    or not isinstance(value.get('note',''),str)
                    or len(value.get('note',''))>200):abort(400)
                value={'category':value['category'],'note':value.get('note','').strip()}
            c.execute('BEGIN IMMEDIATE')
            row=c.execute('SELECT * FROM personal WHERE id=?',(key,)).fetchone();revision=row['revision'] if row else 0
            previous=json.loads(row['body']) if row else {}
            if value.get('feedback') and value.get('feedback')!=previous.get('feedback'):value['feedback_at']=utc()
            elif previous.get('feedback_at'):value['feedback_at']=previous['feedback_at']
            if expected!=revision:return jsonify(error='conflict',revision=revision),409
            c.execute('INSERT INTO personal VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body,revision=excluded.revision',(key,json.dumps(value,ensure_ascii=False),revision+1))
        return jsonify(revision=revision+1)
    @app.get('/api/sync-feedback')
    def sync_feedback():
        with db() as c:rows=c.execute('SELECT id,body FROM personal').fetchall()
        events=[]
        for row in rows:
            value=json.loads(row['body'])
            if value.get('feedback') in LABELS and value.get('feedback_at'):events.append({'id':row['id'],'label':value['feedback'],'at':value['feedback_at'],'note':'网页显式反馈'})
        return jsonify(events=events)
    @app.get('/api/status')
    def status():
        with db() as c:
            latest=c.execute('SELECT * FROM batches ORDER BY at DESC LIMIT 1').fetchone()
            counts=c.execute('SELECT count(*) FROM items').fetchone()[0]
            source_status=c.execute('SELECT value FROM metadata WHERE key=?',('source_status',)).fetchone()
        return jsonify(last_batch=dict(latest) if latest else None,count=counts,source_status=json.loads(source_status[0]) if source_status else {},production='未上线',source='本地导出；精选由编辑核验',model_calls=0)
    @app.get('/api/export')
    def export():
        with db() as c: states=[dict(x) for x in c.execute('SELECT * FROM personal')]
        return jsonify(schema=1,exported_at=utc(),states=states)
    @app.get('/learn/<course>')
    def course(course):
        if course not in COURSES:abort(404)
        # Inject synchronization only in the authenticated server copy; offline artifacts stay byte-identical.
        markup=(ROOT/COURSES[course]).read_text()
        bridge='<script src="/static/course-sync.js"></script>'
        if authenticated():markup=markup.replace('<head>','<head>'+bridge,1)
        filing='<div style="text-align:center;padding:20px;font-size:12px"><a href="https://beian.miit.gov.cn/" target="_blank" rel="noopener noreferrer">冀ICP备2026047626号-1</a></div>'
        markup=markup.replace('</body>',filing+'</body>',1)
        return markup
    return app
