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
    if config: app.config.update(config)
    # Only enable when the app container is isolated behind exactly one trusted reverse proxy.
    # Otherwise users can forge X-Forwarded-For and bypass per-client login throttling.
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
                result.append({k:v for k,v in x.items() if k in fields})
        return sorted(result,key=lambda x:x.get('published_at') or '',reverse=True)
    @app.get('/')
    def home():
        if app.config['PUBLIC']:
            with db() as c:
                last=c.execute('SELECT at FROM batches ORDER BY at DESC LIMIT 1').fetchone()
            return render_template('public.html',items=public_items(),last_sync=last['at'] if last else None)
        return render_template('index.html',csrf=session['csrf'])
    @app.get('/admin')
    def admin():return render_template('index.html',csrf=session['csrf'])
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
        return markup
    return app
