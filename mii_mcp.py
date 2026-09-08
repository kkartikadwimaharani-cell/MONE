"""Same-origin MCP JSON transport and owner-approved OAuth (PKCE S256).

Opaque credentials are hashed in SQLite. No provider secrets are sent to agents.
The browser session, not a generation key, controls consent and key management.
"""
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from urllib.parse import urlsplit, urlencode

from flask import Blueprint, request, session, jsonify, render_template, redirect, g
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

SCOPE = 'mii:generate'
VERSIONS = ('2025-11-25', '2025-06-18', '2025-03-26', '2024-11-05')


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def register_mcp(app, backend, data_dir):
    bp = Blueprint('mii_mcp', __name__)
    origin = os.environ.get('MII_PUBLIC_URL', 'https://makima.cloud').rstrip('/')
    if urlsplit(origin).scheme != 'https' or urlsplit(origin).path:
        raise ValueError('MII_PUBLIC_URL must be an HTTPS origin without a path')
    resource = origin + '/mcp'
    client_signer = URLSafeTimedSerializer(app.secret_key, salt='miiaivideo-mcp-client-v1')
    app.config.setdefault('MII_MCP_DB', os.environ.get('MII_MCP_DB') or os.path.join(data_dir, 'mcp_access.sqlite3'))

    @contextmanager
    def db():
        path = app.config['MII_MCP_DB']
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        conn = sqlite3.connect(path, timeout=15)
        conn.row_factory = sqlite3.Row
        try:
            conn.executescript('''
                CREATE TABLE IF NOT EXISTS clients(id TEXT PRIMARY KEY, name TEXT, redirects TEXT, created REAL);
                CREATE TABLE IF NOT EXISTS codes(hash TEXT PRIMARY KEY, client TEXT, redirect TEXT, challenge TEXT, expires REAL, resource TEXT);
                CREATE TABLE IF NOT EXISTS grants(id TEXT PRIMARY KEY, label TEXT, kind TEXT, created REAL, revoked INTEGER DEFAULT 0);
                CREATE TABLE IF NOT EXISTS tokens(hash TEXT PRIMARY KEY, grant_id TEXT, client TEXT, kind TEXT, expires REAL, resource TEXT);
            ''')
            with conn:
                yield conn
        finally:
            conn.close()

    def owner():
        return bool(session.get('mii_aivideo_auth'))

    def error(message, status=400):
        return jsonify(error=message), status

    def csrf():
        token = session.get('mii_csrf')
        supplied = request.headers.get('X-CSRF-Token') or request.form.get('csrf', '')
        return bool(token and hmac.compare_digest(token.encode(), supplied.encode()))

    def token_value():
        header = request.headers.get('Authorization', '')
        return header[7:] if header.lower().startswith('bearer ') else ''

    def valid_token(value):
        if not value or len(value) > 1024:
            return False
        with db() as c:
            row = c.execute('SELECT t.hash FROM tokens t JOIN grants g ON g.id=t.grant_id WHERE t.hash=? AND t.kind IN (\'access\',\'key\') AND t.expires>? AND t.resource=? AND g.revoked=0', (digest(value), time.time(), resource)).fetchone()
        return bool(row)

    @bp.after_request
    def headers(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        return response

    @bp.route('/ai-video/mcp')
    def dashboard():
        if not owner():
            return render_template('ai-video-lock.html', next_page='/ai-video/mcp')
        backend['_aivideo_ensure_csrf_token']()
        with db() as c:
            grants = [dict(r) for r in c.execute('SELECT id,label,kind,created FROM grants WHERE revoked=0 ORDER BY created DESC')]
        return render_template('ai-video-mcp.html', mcp_url=resource, grants=grants, csrf=session['mii_csrf'])

    @bp.route('/ai-video/mcp/keys', methods=['POST'])
    def create_key():
        if not owner():
            return error('unauthorized', 401)
        if not csrf():
            return error('invalid_csrf', 403)
        data = request.get_json(silent=True) or {}
        label = str(data.get('label', 'Agent pribadi')).strip()[:80] or 'Agent pribadi'
        raw = 'mii_' + secrets.token_urlsafe(36)
        grant = secrets.token_urlsafe(18)
        with db() as c:
            c.execute('INSERT INTO grants VALUES (?,?,?,?,0)', (grant, label, 'key', time.time()))
            c.execute('INSERT INTO tokens VALUES (?,?,?,?,?,?)', (digest(raw), grant, '', 'key', time.time()+365*86400, resource))
        return jsonify(key=raw, id=grant)

    @bp.route('/ai-video/mcp/revoke', methods=['POST'])
    def revoke():
        if not owner():
            return error('unauthorized', 401)
        if not csrf():
            return error('invalid_csrf', 403)
        ident = str((request.get_json(silent=True) or {}).get('id', ''))
        with db() as c:
            c.execute('UPDATE grants SET revoked=1 WHERE id=?', (ident,))
        return jsonify(ok=True)

    @bp.route('/.well-known/oauth-protected-resource')
    @bp.route('/.well-known/oauth-protected-resource/mcp')
    def protected_metadata():
        return jsonify(resource=resource, authorization_servers=[origin], scopes_supported=[SCOPE], bearer_methods_supported=['header'], resource_name='MIIAIVIDEO')

    @bp.route('/.well-known/oauth-authorization-server')
    def auth_metadata():
        return jsonify(issuer=origin, authorization_endpoint=origin+'/oauth/authorize', token_endpoint=origin+'/oauth/token', registration_endpoint=origin+'/oauth/register', response_types_supported=['code'], grant_types_supported=['authorization_code', 'refresh_token'], token_endpoint_auth_methods_supported=['none'], code_challenge_methods_supported=['S256'], scopes_supported=[SCOPE], authorization_response_iss_parameter_supported=True)

    def safe_redirect(uri):
        if not isinstance(uri, str) or len(uri)>2048 or any(ord(ch)<33 for ch in uri):
            return False
        try:
            u=urlsplit(uri)
            return bool(u.hostname and not u.username and not u.password and not u.fragment and (u.scheme=='https' or (u.scheme=='http' and u.hostname in ('localhost','127.0.0.1','::1'))))
        except ValueError:
            return False

    def registered_redirect(uri, registered):
        if uri in registered:
            return True
        # RFC 8252 allows ephemeral loopback ports; all other URI components match.
        try:
            target=urlsplit(uri)
            if target.scheme!='http' or target.hostname not in ('127.0.0.1','::1') or target.username or target.password or target.fragment:
                return False
            for candidate in registered:
                known=urlsplit(candidate)
                if known.scheme=='http' and known.hostname==target.hostname and known.port is None and known.path==target.path and known.query==target.query:
                    return True
        except ValueError:
            pass
        return False

    def signed_client(client_id):
        """Resolve a DCR client even when Railway restarted between registration
        and authorization. The signed ID contains only public client metadata."""
        try:
            data=client_signer.loads(client_id,max_age=30*86400)
        except (BadSignature,SignatureExpired):
            return None
        if not isinstance(data,dict) or not isinstance(data.get('redirects'),list):
            return None
        if not all(safe_redirect(uri) for uri in data['redirects']):
            return None
        return {'id':client_id,'name':str(data.get('name') or 'MCP agent')[:100],
                'redirects':json.dumps(data['redirects'])}

    def find_client(client_id, connection=None):
        if connection is not None:
            row=connection.execute('SELECT * FROM clients WHERE id=?',(client_id,)).fetchone()
            if row:
                return row
        return signed_client(client_id)

    @bp.route('/oauth/register', methods=['POST'])
    def register():
        if request.content_length and request.content_length > 16384:
            return error('invalid_client_metadata')
        data=request.get_json(silent=True)
        if not isinstance(data, dict):
            return error('invalid_client_metadata')
        uris=data.get('redirect_uris')
        if not isinstance(uris,list) or not 1<=len(uris)<=10 or not all(safe_redirect(u) for u in uris):
            return error('invalid_redirect_uri')
        if data.get('token_endpoint_auth_method','none')!='none':
            return error('invalid_client_metadata')
        name=str(data.get('client_name') or 'MCP agent')[:100]
        now=time.time()
        ident=client_signer.dumps({'name':name,'redirects':uris})
        with db() as c:
            if c.execute('SELECT COUNT(*) FROM clients WHERE created>?',(now-3600,)).fetchone()[0]>=100:
                return error('temporarily_unavailable',429)
            c.execute('DELETE FROM clients WHERE created<? AND id NOT IN (SELECT client FROM tokens)',(now-86400,))
            c.execute('INSERT INTO clients VALUES (?,?,?,?)',(ident,name,json.dumps(uris),now))
        return jsonify(client_id=ident,client_id_issued_at=int(now),client_name=name,redirect_uris=uris,token_endpoint_auth_method='none',grant_types=['authorization_code','refresh_token'],response_types=['code']),201

    @bp.route('/oauth/authorize', methods=['GET','POST'])
    def authorize():
        params=request.args
        with db() as c:
            client=find_client(params.get('client_id',''),c)
        uri=params.get('redirect_uri','')
        if not client or not safe_redirect(uri) or not registered_redirect(uri,json.loads(client['redirects'])):
            return error('invalid_client_or_redirect_uri')
        challenge=params.get('code_challenge','')
        if params.get('response_type')!='code' or params.get('code_challenge_method')!='S256' or not re.fullmatch(r'[A-Za-z0-9_-]{43}',challenge):
            return error('invalid_request')
        if params.get('resource',resource)!=resource:
            return error('invalid_target')
        if params.get('scope',SCOPE)!=SCOPE:
            return error('invalid_scope')
        if not owner():
            return render_template('ai-video-lock.html',next_page=request.full_path)
        backend['_aivideo_ensure_csrf_token']()
        if request.method=='GET':
            return render_template('mcp-consent.html',client_name=client['name'],redirect_host=urlsplit(uri).netloc,csrf=session['mii_csrf'])
        if not csrf():
            return error('invalid_csrf',403)
        response={'state':params.get('state',''),'iss':origin}
        if request.form.get('decision')!='approve':
            response['error']='access_denied'
        else:
            raw=secrets.token_urlsafe(32)
            with db() as c:
                c.execute('DELETE FROM codes WHERE expires<?',(time.time(),))
                c.execute('INSERT INTO codes VALUES (?,?,?,?,?,?)',(digest(raw),client['id'],uri,challenge,time.time()+120,resource))
            response['code']=raw
        return redirect(uri+('&' if '?' in uri else '?')+urlencode(response),303)

    @bp.route('/oauth/token',methods=['POST'])
    def exchange():
        form=request.form
        if form.get('resource',resource)!=resource:
            return error('invalid_target')
        client=form.get('client_id','')
        now=time.time()
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            if form.get('grant_type')=='authorization_code':
                code=c.execute('SELECT * FROM codes WHERE hash=?',(digest(form.get('code','')),)).fetchone()
                verifier=form.get('code_verifier','')
                challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
                if not code or code['expires']<now or code['client']!=client or code['redirect']!=form.get('redirect_uri') or code['resource']!=resource or not re.fullmatch(r'[A-Za-z0-9._~-]{43,128}',verifier) or not hmac.compare_digest(code['challenge'],challenge):
                    return error('invalid_grant')
                c.execute('DELETE FROM codes WHERE hash=?',(code['hash'],))
                info=find_client(client,c)
                if not info:
                    return error('invalid_client')
                grant=secrets.token_urlsafe(18)
                c.execute('INSERT INTO grants VALUES (?,?,?,?,0)',(grant,info['name'],'oauth',now))
            elif form.get('grant_type')=='refresh_token':
                row=c.execute('SELECT t.*,g.revoked FROM tokens t JOIN grants g ON g.id=t.grant_id WHERE t.hash=? AND t.kind IN (\'refresh\',\'used_refresh\')',(digest(form.get('refresh_token','')),)).fetchone()
                if not row or row['client']!=client or row['expires']<now or row['revoked'] or row['resource']!=resource:
                    return error('invalid_grant')
                grant=row['grant_id']
                if row['kind']=='used_refresh':
                    c.execute('UPDATE grants SET revoked=1 WHERE id=?',(grant,))
                    return error('invalid_grant')
                c.execute("UPDATE tokens SET kind='used_refresh' WHERE hash=?",(row['hash'],))
            else:
                return error('unsupported_grant_type')
            access=secrets.token_urlsafe(36)
            refresh=secrets.token_urlsafe(36)
            c.executemany('INSERT INTO tokens VALUES (?,?,?,?,?,?)',[(digest(access),grant,client,'access',now+3600,resource),(digest(refresh),grant,client,'refresh',now+30*86400,resource)])
            c.execute('DELETE FROM tokens WHERE expires<?',(now,))
        return jsonify(access_token=access,token_type='Bearer',expires_in=3600,refresh_token=refresh,scope=SCOPE)

    def tool(name,description,props=None,required=None,write=False):
        return dict(name=name,description=description,inputSchema={'type':'object','properties':props or {},'required':required or [],'additionalProperties':False},annotations={'readOnlyHint':not write,'destructiveHint':False,'idempotentHint':not write,'openWorldHint':True})

    string={'type':'string'}
    images={'type':'array','items':string,'maxItems':9}
    videos={'type':'array','items':string,'maxItems':3}
    common={'prompt':{'type':'string','minLength':1},'family':string,'variant':string,'resolution':string,'aspect_ratio':string,'negative_prompt':string,'image_urls':images}
    image_controls=dict(common, size=string, quality=string, output_format=string,
                        megapixel=string, num_images={'type':'integer','minimum':1,'maximum':4},
                        seed={'type':'integer'}, sequential_image_generation=string,
                        max_images={'type':'integer','minimum':1,'maximum':14})
    tools=[
        tool('list_models','List MIIAIVIDEO models, exact variants, allowed controls and configuration status. Call before generation.'),
        tool('clear_debug','Clear AI Video diagnostics only. Does not delete tasks, history, credentials, or media.',write=True),
        tool('generate_video','Clear old diagnostics, validate outbound media links, then start video generation using account credits only when requested. Returns task_id.',dict(common,duration={'type':'integer','minimum':1,'maximum':30},mute_audio={'type':'boolean'},first_frame_url=string,last_frame_url=string,video_urls=videos,audio_urls=videos),['prompt'],True),
        tool('generate_image','Start image generation using account credits only when requested. Returns task_id.',image_controls,['prompt'],True),
        tool('generate_audio','Start Seed Audio generation using account credits only when requested.',{'prompt':{'type':'string','minLength':1},'audio_format':string,'sample_rate':{'type':'integer'},'audio_urls':videos,'image_urls':images},['prompt'],True),
        tool('motion_control','Edit motion/character in a source video using account credits. Source video is validated before submission.',{'prompt':string,'variant':string,'video_urls':{'type':'array','items':string,'maxItems':1},'image_urls':{'type':'array','items':string,'maxItems':5},'mute_audio':{'type':'boolean'}},['video_urls'],True),
        tool('check_status','Read task status and output URL. Do not repeatedly poll unless requested.',{'task_id':{'type':'string','minLength':1}},['task_id']),
    ]
    for item in tools:
        item['name']='miiaivideo_'+item['name']
        if item['name']=='miiaivideo_check_status':
            item['_meta']={
                'ui':{'resourceUri':'ui://miiaivideo/video-preview.html'},
                'openai/outputTemplate':'ui://miiaivideo/video-preview.html',
                'openai/toolInvocation/invoking':'Memeriksa hasil MIIAIVIDEO…',
                'openai/toolInvocation/invoked':'Hasil MIIAIVIDEO siap',
            }

    def catalog():
        result={'video':{},'image':{},'audio':{},'motion':{}}
        bp_caps=backend['budgetpixel_provider'].public_video_capabilities()
        for key,caps in bp_caps.items():
            result['video'][key]=dict(caps,configured=bool(backend['_budgetpixel_api_key']()))
        bp_image_caps=backend['budgetpixel_provider'].public_image_capabilities()
        for key,caps in bp_image_caps.items():
            family,variant=key.split(':',1)
            public_family='gptimagebp' if family=='gptimage' else family
            item=dict(caps,configured=bool(backend['_budgetpixel_api_key']()),provider='MIIAIVIDEO')
            fields=['image_urls'] if (item.get('reference_images') or item.get('singular_image')) else []
            for public,cap in (('aspect_ratio','aspect_ratios'),('resolution','resolutions'),
                               ('size','sizes'),('quality','qualities'),('output_format','formats'),
                               ('megapixel','megapixels'),('num_images','image_count'),
                               ('seed','seed'),('negative_prompt','negative_prompt'),
                               ('sequential_image_generation','sequential_modes'),('max_images','max_images')):
                if item.get(cap): fields.append(public)
            item['fields']=fields
            result['image'][public_family+':'+variant]=item
        def add(kind,family,variants,ratios=(),resolutions=(),durations=(),fields=()):
            for variant in variants:
                result[kind][family+':'+variant]={'aspect_ratios':list(ratios),'resolutions':list(resolutions),'durations':list(durations),'fields':list(fields),'configured':bool(backend['_segmind_api_key']())}
        # All Seedance 2.0 tiers (MINI/FAST/PRO) come from bp_caps above —
        # confirmed fully routed through BudgetPixel per
        # docs.budgetpixel.com/concepts/models (see app.py's 'seedance'
        # branch). Nothing in this family needs Segmind anymore.
        add('video','kling',backend['KLING_MODEL_MAP'],backend['KLING_RATIOS'],durations=range(3,16),fields=('image_urls','first_frame_url','last_frame_url','negative_prompt','mute_audio'))
        add('video','veo',backend['VEO_ENDPOINT_BY_TIER'],backend['VEO_RATIOS'],backend['VEO_RESOLUTIONS'],backend['VEO_DURATIONS'],('image_urls','first_frame_url','last_frame_url','negative_prompt','mute_audio'))
        add('image','nanobanana',backend['NANOBANANA_RESOLUTION_BY_TIER'],backend['NANOBANANA_RATIOS'],('1K','2K','4K'),fields=('image_urls',))
        add('image','gptimage',backend['GPTIMAGE2_QUALITY_BY_TIER'],backend['GPTIMAGE2_SIZE_BY_RATIO'],fields=('image_urls',))
        add('image','seedream',['PRO'],backend['SEEDREAM5PRO_RATIOS'],backend['SEEDREAM5PRO_SIZES'],fields=('image_urls',))
        add('image','flux',backend['FLUX_ENDPOINT_BY_TIER'],backend['FLUX_RATIOS'])
        add('image','imagen',['STANDARD'],backend['IMAGEN4_RATIOS'],fields=('negative_prompt',))
        add('image','qwen',['STANDARD'],backend['QWENIMAGE_RATIOS'],fields=('negative_prompt',))
        add('audio','seedaudio',['STANDARD'],fields=('audio_format','sample_rate','audio_urls','image_urls'))
        result['audio']['seedaudio:STANDARD'].update(audio_formats=list(backend['SEEDAUDIO_FORMATS']),sample_rates=list(backend['SEEDAUDIO_SAMPLE_RATES']))
        add('motion','klingswap',['STD','PRO'],fields=('video_urls','image_urls','mute_audio'))
        for key,caps in result['video'].items():
            if 'fields' not in caps:
                caps['fields']=['image_urls','video_urls','audio_urls','first_frame_url','last_frame_url','mute_audio']
        return result

    def call_backend(name,args):
        name=name.removeprefix('miiaivideo_')
        if name=='list_models':
            return {'brand':'MIIAIVIDEO','models':catalog()}
        elif name=='clear_debug':
            return backend['_aivideo_clear_debug']()
        elif name=='check_status':
            endpoint='aivideo_task_status';payload=None;kwargs={'task_id':args['task_id']}
        else:
            endpoint='aivideo_generate';kwargs={};payload=dict(args)
            defaults={'generate_video':('video','seedance25'),'generate_image':('image','nanobanana'),'generate_audio':('audio','seedaudio'),'motion_control':('motion','klingswap')}
            kind,default_family=defaults[name]
            if name in ('generate_video','motion_control'):
                backend['_aivideo_clear_debug']()
            family=payload.setdefault('family',default_family).lower()
            variant=payload.pop('variant',{'seedance':'MINI','seedream':'PRO','flux':'SCHNELL','veo':'FAST','klingswap':'STD'}.get(family,'STANDARD')).upper()
            caps=catalog()[kind].get(family+':'+variant)
            if not caps:
                return {'error':'Unsupported model or variant. Call miiaivideo_list_models first.'}
            for field,key in (('resolution','resolutions'),('aspect_ratio','aspect_ratios'),('duration','durations')):
                value=payload.get(field)
                if value not in (None,''):
                    if key=='durations' and 'duration' in caps:
                        allowed=caps['duration'][0]<=value<=caps['duration'][1]
                    else:
                        allowed=value in caps.get(key,[])
                    if not allowed:
                        return {'error':'Unsupported '+field+' for '+family+':'+variant}
            controls=set(payload)-{'prompt','family','resolution','aspect_ratio','duration'}
            if any(key not in caps.get('fields',[]) for key in controls):
                return {'error':'This model does not accept one of the supplied controls.'}
            limits={'image_urls':9,'video_urls':3,'audio_urls':3}
            if family=='kling': limits.update(image_urls=1,video_urls=0,audio_urls=0)
            if family=='veo': limits.update(image_urls=3,video_urls=0,audio_urls=0)
            if family=='klingswap': limits.update(image_urls=5,video_urls=1,audio_urls=0)
            if family=='seedaudio': limits.update(image_urls=1)
            for field,maximum in limits.items():
                if len(payload.get(field,[]))>maximum:
                    return {'error':'Too many '+field+' for this model.'}
                for uri in payload.get(field,[]):
                    if not safe_redirect(uri) or urlsplit(uri).scheme!='https':
                        return {'error':'References must be HTTPS URLs.'}
            for field in ('first_frame_url','last_frame_url'):
                uri=payload.get(field)
                if uri and (not safe_redirect(uri) or urlsplit(uri).scheme!='https'):
                    return {'error':'Frames must be HTTPS URLs.'}
            if payload.get('last_frame_url') and not (payload.get('first_frame_url') or (family=='kling' and payload.get('image_urls'))):
                return {'error':'Last frame requires a first frame.'}
            if family=='seedaudio':
                if len(payload.get('prompt',''))>2048:
                    return {'error':'Audio prompt must be at most 2048 characters.'}
                if payload.get('audio_format','wav') not in caps['audio_formats'] or payload.get('sample_rate',44100) not in caps['sample_rates']:
                    return {'error':'Unsupported audio format or sample rate.'}
                if payload.get('audio_urls') and payload.get('image_urls'):
                    return {'error':'Use audio references or an image, not both.'}
            if family=='klingswap' and not payload.get('video_urls'):
                return {'error':'Motion control requires a source video.'}
            payload.update(family=family,model=variant,bitrate_mode='high')
        with app.test_request_context('/api/aivideo/mcp-internal',method='POST' if payload else 'GET',json=payload):
            g.mii_mcp_internal=True
            response=app.make_response(backend[endpoint](**kwargs))
            result=response.get_json(silent=True)
        if not isinstance(result,dict):
            return {'error':'Backend returned an invalid response.'}
        if 'id' in result:
            result['task_id']=result['id']
        return result

    @bp.route('/mcp',methods=['GET','POST','DELETE'])
    def mcp():
        supplied_origin=request.headers.get('Origin')
        if supplied_origin and supplied_origin!=origin:
            return error('invalid_origin',403)
        if not valid_token(token_value()):
            response=jsonify(error='unauthorized')
            response.status_code=401
            response.headers['WWW-Authenticate']='Bearer resource_metadata="'+origin+'/.well-known/oauth-protected-resource/mcp"'
            return response
        if request.method!='POST':
            return error('Streamable HTTP uses POST; no SSE stream or session to delete.',405)
        if request.content_length and request.content_length>256000:
            return error('request_too_large',413)
        msg=request.get_json(silent=True)
        def rpc_error(code,message):
            return jsonify(jsonrpc='2.0',id=msg.get('id') if isinstance(msg,dict) else None,error={'code':code,'message':message})
        if not isinstance(msg,dict) or msg.get('jsonrpc')!='2.0' or not isinstance(msg.get('method'),str):
            return rpc_error(-32600,'Invalid Request'),400
        if 'id' not in msg:
            return '',202
        method=msg['method'];params=msg.get('params') or {}
        if not isinstance(params,dict):
            return rpc_error(-32602,'Invalid params')
        version=request.headers.get('MCP-Protocol-Version')
        if version and version not in VERSIONS:
            return error('unsupported_protocol_version')
        if method=='initialize':
            result={'protocolVersion':params.get('protocolVersion') if params.get('protocolVersion') in VERSIONS else VERSIONS[0],'capabilities':{'tools':{'listChanged':False}},'serverInfo':{'name':'MIIAIVIDEO','version':'2.0.0','websiteUrl':origin+'/ai-video/mcp','icons':[{'src':origin+'/mcp/icon','mimeType':'image/jpeg'}]},'instructions':'Generate only when requested. Use miiaivideo_list_models first, then the appropriate miiaivideo generation tool. Tasks run asynchronously. Do not repeatedly poll without user approval.'}
        elif method=='ping':
            result={}
        elif method=='tools/list':
            result={'tools':tools}
        elif method=='resources/list':
            result={'resources':[{'uri':'ui://miiaivideo/video-preview.html','name':'MIIAIVIDEO video preview','mimeType':'text/html;profile=mcp-app'}]}
        elif method=='resources/read':
            if params.get('uri')!='ui://miiaivideo/video-preview.html':
                return rpc_error(-32602,'Unknown resource')
            html='''<!doctype html><html><head><meta charset="utf-8"><style>body{margin:0;background:#08090d;color:#fff;font:14px system-ui}main{padding:12px}video{display:none;width:100%;max-height:70vh;border-radius:14px;background:#000}a{color:#ff405f}#state{padding:18px;border:1px solid #35202a;border-radius:14px}</style></head><body><main><div id="state">Video sedang diproses.</div><video id="player" controls playsinline preload="metadata"></video><p><a id="open" target="_blank" rel="noopener"></a></p></main><script>function render(r){r=(r&&r.structuredContent)||r||{};var o=r.output||{},u=o.video_url;if(!u){document.getElementById('state').textContent=r.error||('Status: '+(r.status||'processing'));return}var v=document.getElementById('player'),a=document.getElementById('open');v.src=u;v.style.display='block';document.getElementById('state').style.display='none';a.href=u;a.textContent='Buka / download video'}render((window.openai&&window.openai.toolOutput)||{});window.addEventListener('openai:set_globals',function(e){if(e.detail&&e.detail.globals)render(e.detail.globals.toolOutput)});</script></body></html>'''
            meta={'ui':{'prefersBorder':True,'csp':{'resourceDomains':[origin,'https://*.dropboxusercontent.com']}},'openai/widgetDescription':'Pemutar hasil video MIIAIVIDEO','openai/widgetPrefersBorder':True,'openai/widgetCSP':{'resource_domains':[origin,'https://*.dropboxusercontent.com']}}
            result={'contents':[{'uri':params['uri'],'mimeType':'text/html;profile=mcp-app','text':html,'_meta':meta}]}
        elif method in ('prompts/list','resources/templates/list'):
            result={ {'prompts/list':'prompts','resources/templates/list':'resourceTemplates'}[method]:[]}
        elif method=='tools/call':
            definition=next((t for t in tools if t['name']==params.get('name')),None)
            args=params.get('arguments') or {}
            if not definition or not isinstance(args,dict):
                return rpc_error(-32602,'Unknown tool or invalid arguments')
            schema=definition['inputSchema'];props=schema['properties']
            if any(k not in props for k in args) or any(k not in args for k in schema['required']):
                return rpc_error(-32602,'Missing or unsupported arguments')
            for key,value in args.items():
                p=props[key];typ=p['type']
                if (typ=='string' and not isinstance(value,str)) or (typ=='integer' and type(value)!=int) or (typ=='boolean' and type(value)!=bool) or (typ=='array' and (not isinstance(value,list) or any(not isinstance(v,str) for v in value))):
                    return rpc_error(-32602,'Invalid argument type: '+key)
                if isinstance(value,str) and (len(value)<p.get('minLength',0) or len(value)>100000):
                    return rpc_error(-32602,'Invalid string: '+key)
                if typ=='integer' and not p.get('minimum',value)<=value<=p.get('maximum',value):
                    return rpc_error(-32602,'Argument outside limits: '+key)
                if typ=='array' and len(value)>p.get('maxItems',len(value)):
                    return rpc_error(-32602,'Too many references')
            try:
                data=call_backend(definition['name'],args)
            except Exception:
                app.logger.exception('MCP tool failed: %s',definition['name'])
                data={'error':'Generation backend failed. Check AI Video diagnostics.'}
            result={'content':[{'type':'text','text':json.dumps(data,ensure_ascii=False)}],
                    'structuredContent':data,'isError':bool(data.get('error'))}
        else:
            return rpc_error(-32601,'Method not found')
        return jsonify(jsonrpc='2.0',id=msg['id'],result=result)

    @bp.route('/mcp/icon')
    def icon():
        from flask import send_file
        return send_file(os.path.join(app.root_path,'mcp-server','icon.jpg'),mimetype='image/jpeg')

    app.register_blueprint(bp)
