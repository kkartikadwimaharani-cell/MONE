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
    widget_status_signer = URLSafeTimedSerializer(app.secret_key, salt='miiaivideo-widget-status-v1')
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
    common={'prompt':{'type':'string','minLength':1},'family':string,'variant':string,
            'model_slug':string,'resolution':string,'aspect_ratio':string,
            'negative_prompt':string,'image_urls':images}
    image_controls=dict(common, size=string, quality=string, output_format=string,
                        megapixel=string, num_images={'type':'integer','minimum':1,'maximum':4},
                        seed={'type':'integer'}, sequential_image_generation=string,
                        max_images={'type':'integer','minimum':1,'maximum':14})
    tools=[
        tool('list_models','List supported MIIAIVIDEO model IDs quickly. Optionally filter by category or search text; use get_model_capabilities for one model\'s detailed controls.',
             {'category':{'type':'string','enum':['video','image','audio','motion']},
              'query':{'type':'string','minLength':1}}),
        tool('clear_debug','Clear AI Video diagnostics only. Does not delete tasks, history, credentials, or media.',write=True),
        tool('generate_video','Clear old diagnostics, validate outbound media links, then start video generation using account credits only when requested. Returns task_id.',dict(common,duration={'type':'integer','minimum':1,'maximum':30},mute_audio={'type':'boolean'},first_frame_url=string,last_frame_url=string,video_urls=videos,audio_urls=videos),['prompt'],True),
        tool('generate_image','Start image generation using account credits only when requested. Returns task_id.',image_controls,['prompt'],True),
        tool('generate_audio','Start Seed Audio generation using account credits only when requested.',{'prompt':{'type':'string','minLength':1},'audio_format':string,'sample_rate':{'type':'integer'},'audio_urls':videos,'image_urls':images},['prompt'],True),
        tool('generate_music','Generate music only with a model listed as available for music.',dict(common,lyrics=string,duration={'type':'integer','minimum':1}),['prompt'],True),
        tool('generate_sfx','Generate a sound effect only with a listed SFX model.',dict(common,duration={'type':'integer','minimum':1}),['prompt'],True),
        tool('video_to_music','Generate music from one source video.',dict(common,video_urls={'type':'array','items':string,'minItems':1,'maxItems':1}),['video_urls'],True),
        tool('video_to_sfx','Generate sound effects from one source video.',dict(common,video_urls={'type':'array','items':string,'minItems':1,'maxItems':1}),['video_urls'],True),
        tool('get_model_capabilities','Return the exact local schema and status for one catalogue slug.',
             {'slug':{'type':'string','minLength':1},'category':{'type':'string','enum':['image','video','audio','motion']}},['slug']),
        tool('motion_control','Animate one character image using one source video.',{'prompt':string,'model_slug':string,'video_urls':{'type':'array','items':string,'minItems':1,'maxItems':1},'image_urls':{'type':'array','items':string,'minItems':1,'maxItems':1},'mute_audio':{'type':'boolean'},'character_orientation':{'type':'string','enum':['video','image']},'trim_intro':{'type':'boolean'}},['video_urls','image_urls'],True),
        tool('check_status','Read one task status. Call at most once for troubleshooting: every generation card already refreshes itself until completed or failed. Never loop or repeatedly call this tool.',{'task_id':{'type':'string','minLength':1}},['task_id']),
    ]
    generation_tools={
        'miiaivideo_generate_video','miiaivideo_generate_image','miiaivideo_generate_audio',
        'miiaivideo_generate_music','miiaivideo_generate_sfx','miiaivideo_video_to_music',
        'miiaivideo_video_to_sfx','miiaivideo_motion_control',
    }
    for item in tools:
        item['name']='miiaivideo_'+item['name']
        if item['name'] in generation_tools:
            item['_meta']={
                'ui':{'resourceUri':'ui://miiaivideo/result-preview-v2.html'},
                'openai/outputTemplate':'ui://miiaivideo/result-preview-v2.html',
                'openai/toolInvocation/invoking':'Memulai proses MIIAIVIDEO…',
                'openai/toolInvocation/invoked':'Proses MIIAIVIDEO berjalan',
            }
        elif item['name']=='miiaivideo_check_status':
            # Allows the single generation widget to refresh itself through
            # the Apps SDK bridge. No outputTemplate here: manual status
            # checks stay text-only and cannot clone another preview card.
            item['_meta']={'openai/widgetAccessible':True}

    def catalog():
        result={'video':{},'image':{},'audio':{},'motion':{}}
        if 'budgetpixel_video_catalog' in backend:
            for slug,item in backend['budgetpixel_video_catalog'].VIDEO_CATALOG.items():
                fields=[]
                if item.get('resolutions'): fields.append('resolution')
                if item.get('aspect_ratios'): fields.append('aspect_ratio')
                if item.get('durations'): fields.append('duration')
                if item.get('first_frame'): fields.extend(('image_urls','first_frame_url'))
                if item.get('end_frame'): fields.append('last_frame_url')
                if item.get('reference_videos'): fields.append('video_urls')
                if item.get('reference_audios'): fields.append('audio_urls')
                if item.get('generate_audio'): fields.append('mute_audio')
                result['video']['bpx-'+slug+':STANDARD']={
                    'slug':slug, 'modes':list(item.get('modes',())),
                    'aspect_ratios':list(item.get('aspect_ratios',())),
                    'resolutions':list(item.get('resolutions',())),
                    'durations':list(item.get('durations',())),
                    'fields':list(dict.fromkeys(fields))}
        if 'budgetpixel_media_catalog' in backend:
            media=backend['budgetpixel_media_catalog']
            for slug,item in media.IMAGE_CATALOG.items():
                accepts_references=bool(item.get('reference_images') or item.get('singular_image'))
                fields=['image_urls'] if accepts_references else []
                contract=media.image_contract(slug)
                for public,cap in (('aspect_ratio','aspect_ratios'),('resolution','resolutions'),
                                   ('size','sizes'),('quality','qualities'),('output_format','formats'),
                                   ('megapixel','megapixels'),('num_images','image_count'),
                                   ('seed','seed'),('negative_prompt','negative_prompt'),
                                   ('sequential_image_generation','sequential_modes'),('max_images','max_images')):
                    if contract.get(cap): fields.append(public)
                result['image']['bpx-'+slug+':STANDARD']={
                    'slug':slug, 'modes':['text-to-image'] + (['image-editing'] if accepts_references else []),
                    'aspect_ratios':list(contract.get('aspect_ratios',())),
                    'resolutions':list(contract.get('resolutions',())) or
                                  (['NATIVE'] if contract.get('native_resolution') else []),
                    'sizes':list(contract.get('sizes',())),
                    'megapixels':list(contract.get('megapixels',())),
                    'qualities':list(contract.get('qualities',())),
                    'output_formats':list(contract.get('formats',())),
                    'image_count':list(contract.get('image_count',())),
                    'fields':list(dict.fromkeys(fields)),
                    'requires_image':bool(item.get('requires_image'))}
            for slug,item in media.AUDIO_CATALOG.items():
                fields=media.audio_fields(item)
                result['audio']['bpx-'+slug+':STANDARD']={
                    'slug':slug, 'modes':[item.get('subtype','audio')],
                    'durations':list(item.get('durations',())),
                    'audio_formats':list(item.get('formats',())), 'fields':fields,
                    'requires_video':bool(item.get('reference_videos'))}
        if 'budgetpixel_motion_catalog' in backend:
            for slug,item in backend['budgetpixel_motion_catalog'].MOTION_CATALOG.items():
                result['motion']['bpx-'+slug+':STANDARD']={
                    'slug':slug, 'modes':['motion-control'],
                    'fields':['image_urls','video_urls','mute_audio','character_orientation','trim_intro']}
        return result
        # Legacy catalogue kept below temporarily for migration reference; it
        # is intentionally unreachable and cannot appear in MCP responses.
        bp_caps=backend['budgetpixel_provider'].public_video_capabilities()
        for key,caps in bp_caps.items():
            result['video'][key]=dict(caps,configured=bool(backend['_budgetpixel_api_key']()))
        if 'budgetpixel_video_catalog' in backend:
            for slug,item in backend['budgetpixel_video_catalog'].VIDEO_CATALOG.items():
                family='bpx-'+slug
                fields=[]
                if item.get('resolutions'): fields.append('resolution')
                if item.get('aspect_ratios'): fields.append('aspect_ratio')
                if item.get('durations'): fields.append('duration')
                if item.get('first_frame'): fields.extend(('image_urls','first_frame_url'))
                if item.get('end_frame'): fields.append('last_frame_url')
                if item.get('reference_videos'): fields.append('video_urls')
                if item.get('reference_audios'): fields.append('audio_urls')
                if item.get('generate_audio'): fields.append('mute_audio')
                result['video'][family+':STANDARD']={
                    'slug':slug,'provider':'BudgetPixel','modes':list(item.get('modes',())),
                    'aspect_ratios':list(item.get('aspect_ratios',())),
                    'resolutions':list(item.get('resolutions',())),
                    'durations':list(item.get('durations',())),
                    'fields':list(dict.fromkeys(fields)),
                    'configured':bool(backend['_budgetpixel_api_key']()),
                }
        if 'budgetpixel_media_catalog' in backend:
            for slug,item in backend['budgetpixel_media_catalog'].IMAGE_CATALOG.items():
                fields=['image_urls'] if item.get('reference_images') or item.get('singular_image') else []
                result['image']['bpx-'+slug+':STANDARD']={
                    'slug':slug,'provider':'BudgetPixel',
                    'modes':['text-to-image'] + (['image-editing'] if fields else []),
                    'fields':fields,'configured':bool(backend['_budgetpixel_api_key']()),
                    'requires_image':bool(item.get('requires_image')),
                }
            for slug,item in backend['budgetpixel_media_catalog'].AUDIO_CATALOG.items():
                fields=backend['budgetpixel_media_catalog'].audio_fields(item)
                result['audio']['bpx-'+slug+':STANDARD']={
                    'slug':slug,'provider':'BudgetPixel','modes':[item.get('subtype','audio')],
                    'durations':list(item.get('durations',())),
                    'audio_formats':list(item.get('formats',())),
                    'fields':fields,'configured':bool(backend['_budgetpixel_api_key']()),
                    'requires_video':bool(item.get('reference_videos') and item.get('label')=='VIDEO'),
                }
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
            # Keep discovery fast and comfortably below connector response limits.
            # The previous response duplicated every full capability record and
            # synchronously contacted the provider catalogue, which could time out
            # as an MCP -32603 internal error. Exact controls remain available from
            # get_model_capabilities and generation still validates against catalog().
            complete=catalog()
            category=str(args.get('category') or '').lower()
            query=str(args.get('query') or '').strip().lower()
            selected={}
            for kind,items in complete.items():
                if category and kind!=category:
                    continue
                model_ids=sorted(key for key in items if not query or query in key.lower())
                selected[kind]=model_ids
            counts={kind:len(items) for kind,items in complete.items()}
            returned=sum(len(items) for items in selected.values())
            return {
                'brand':'MIIAIVIDEO',
                'models':selected,
                'counts':counts,
                'returned':returned,
                'detail_tool':'miiaivideo_get_model_capabilities',
                'note':'Model IDs are FAMILY:VARIANT. Use model_slug for IDs beginning with bpx-.',
            }
        elif name=='get_model_capabilities':
            slug=str(args['slug']).lower()
            for kind,items in catalog().items():
                if args.get('category') and args.get('category') != kind:
                    continue
                for model_id,model in items.items():
                    if model.get('slug') == slug:
                        return {'brand':'MIIAIVIDEO','category':kind,'model_id':model_id,'model':model}
            return {'error':'Unknown model slug.'}
        elif name=='clear_debug':
            return backend['_aivideo_clear_debug']()
        elif name=='check_status':
            endpoint='aivideo_task_status';payload=None;kwargs={'task_id':args['task_id']}
        else:
            endpoint='aivideo_generate';kwargs={};payload=dict(args)
            defaults={'generate_video':('video','seedance25'),'generate_image':('image','nanobanana'),
                      'generate_audio':('audio','seedaudio'),'generate_music':('audio','bpx-music-3.0'),
                      'generate_sfx':('audio','bpx-sonilo-sfx'),
                      'video_to_music':('audio','bpx-sonilo-video-music'),
                      'video_to_sfx':('audio','bpx-sonilo-video-sfx'),
                      'motion_control':('motion','bpx-kling-3-motion-control-std')}
            if name=='video_to_music' and not payload.get('prompt'):
                payload['prompt']='Create music that follows the pacing and mood of the source video.'
            if name=='video_to_sfx' and not payload.get('prompt'):
                payload['prompt']='Create synchronized sound effects for the visible actions in the source video.'
            kind,default_family=defaults[name]
            if name in ('generate_video','motion_control'):
                backend['_aivideo_clear_debug']()
            default_catalog_slug={'generate_video':'seedance-2.5',
                                  'generate_image':'midjourney-v7',
                                  'generate_audio':'sonilo-sfx',
                                  'generate_music':'music-3.0','generate_sfx':'sonilo-sfx',
                                  'video_to_music':'sonilo-video-music',
                                  'video_to_sfx':'sonilo-video-sfx',
                                  'motion_control':'kling-3-motion-control-std'}.get(name,'')
            requested_slug=str(payload.get('model_slug') or default_catalog_slug).lower()
            catalog_selected=False
            if requested_slug and name in ('generate_video','generate_image','generate_audio',
                                           'generate_music','generate_sfx','video_to_music','video_to_sfx','motion_control'):
                expected_kind=('video' if name=='generate_video' else
                               ('image' if name=='generate_image' else ('motion' if name=='motion_control' else 'audio')))
                live=backend['budgetpixel_registry'].get_registry(backend['_budgetpixel_api_key']())
                selected=backend['budgetpixel_registry'].model_by_slug(requested_slug,live,expected_kind)
                if not selected or selected.get('category')!=expected_kind or not selected.get('handler'):
                    return {'error':'Unknown or unavailable MIIAIVIDEO model slug for this output type.'}
                payload['family']='bpx-'+requested_slug
                payload['model_slug']=requested_slug
                catalog_selected=True
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
            controls=set(payload)-{'prompt','family','model_slug','resolution','aspect_ratio','duration'}
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
            if catalog_selected:
                payload['catalog_model']=True
                payload['output_type']=kind
            payload.update(family=family,model=variant,bitrate_mode='high')
        with app.test_request_context('/api/aivideo/mcp-internal',method='POST' if payload else 'GET',json=payload):
            g.mii_mcp_internal=True
            response=app.make_response(backend[endpoint](**kwargs))
            result=response.get_json(silent=True)
        if not isinstance(result,dict):
            return {'error':'Backend returned an invalid response.'}
        if 'id' in result:
            result['task_id']=result['id']
        if name in generation_tools and result.get('task_id') and not result.get('error'):
            # Task-scoped, expiring read capability for the one embedded card.
            # Polling must not call another MCP tool (which creates a new card).
            result['status_token']=widget_status_signer.dumps({'task_id':result['task_id']})
        return result

    @bp.route('/mcp/widget-status', methods=['POST','OPTIONS'])
    def widget_status():
        def widget_response(data, code=200):
            response=jsonify(data)
            response.status_code=code
            response.headers['Access-Control-Allow-Origin']='*'
            response.headers['Access-Control-Allow-Methods']='POST, OPTIONS'
            response.headers['Access-Control-Allow-Headers']='Content-Type'
            return response
        if request.method=='OPTIONS':
            return widget_response({})
        if request.content_length and request.content_length>4096:
            return widget_response({'error':'Invalid status token.'},413)
        token=request.get_data(as_text=True)
        try:
            signed=widget_status_signer.loads(token, max_age=6*3600)
        except (BadSignature, SignatureExpired):
            return widget_response({'error':'Status link expired.'},401)
        task_id=signed.get('task_id') if isinstance(signed,dict) else None
        if not isinstance(task_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',task_id):
            return widget_response({'error':'Invalid status token.'},401)
        try:
            data=call_backend('miiaivideo_check_status',{'task_id':task_id})
        except Exception:
            app.logger.exception('MCP widget status failed')
            return widget_response({'error':'Status temporarily unavailable.'},503)
        if not isinstance(data,dict):
            return widget_response({'error':'Status temporarily unavailable.'},503)
        if data.get('error') and not data.get('status'):
            return widget_response({'error':str(data['error'])[:200]},404)
        return widget_response({key:data[key] for key in ('id','status','progress','output','error') if key in data})

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
            result={'protocolVersion':params.get('protocolVersion') if params.get('protocolVersion') in VERSIONS else VERSIONS[0],'capabilities':{'tools':{'listChanged':False}},'serverInfo':{'name':'MIIAIVIDEO','version':'2.1.0','websiteUrl':origin+'/ai-video/mcp','icons':[{'src':origin+'/mcp/icon','mimeType':'image/jpeg'}]},'instructions':'Generate only when requested. Use miiaivideo_list_models first, then the appropriate generation tool. Its single result card tracks the task automatically. Never poll miiaivideo_check_status in a loop or call it repeatedly; use it at most once for troubleshooting.'}
        elif method=='ping':
            result={}
        elif method=='tools/list':
            result={'tools':tools}
        elif method=='resources/list':
            result={'resources':[{'uri':'ui://miiaivideo/result-preview-v2.html','name':'MIIAIVIDEO result preview','mimeType':'text/html;profile=mcp-app'}]}
        elif method=='resources/read':
            if params.get('uri')!='ui://miiaivideo/result-preview-v2.html':
                return rpc_error(-32602,'Unknown resource')
            html='''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>
*{box-sizing:border-box}body{margin:0;background:#08090d;color:#fff;font:13px system-ui,-apple-system,sans-serif}main{padding:10px}.card{overflow:hidden;border:1px solid #35202a;border-radius:14px;background:linear-gradient(145deg,#151116,#0b0c10)}.head{display:grid;grid-template-columns:32px minmax(0,1fr) auto;align-items:center;gap:9px;padding:10px}.mark{width:30px;height:30px;border-radius:9px;display:grid;place-items:center;background:linear-gradient(135deg,#ff2446,#8a0018);font-weight:850;box-shadow:0 0 18px #ff204044}.copy{min-width:0}.title{font-weight:800;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.sub{margin-top:2px;color:#a7a1a5;font:10px ui-monospace,monospace;text-transform:uppercase;letter-spacing:.04em}.pct{color:#ff526b;font:700 11px ui-monospace,monospace}.bar{height:3px;margin:0 10px 10px;background:#ffffff12;border-radius:9px;overflow:hidden}.fill{height:100%;width:0;background:linear-gradient(90deg,#ff1638,#ff6078);transition:width .35s}.media{display:none;border-top:1px solid #35202a;background:#050506}.media img,.media video{display:block;width:100%;max-height:300px;object-fit:contain;background:#050506}.media audio{display:block;width:calc(100% - 20px);margin:12px 10px}.foot{display:none;align-items:center;justify-content:space-between;gap:10px;padding:8px 10px;border-top:1px solid #35202a}.foot a{color:#ff6078;font-size:11px;font-weight:750;text-decoration:none}.err{color:#ff7187}.done .mark{background:linear-gradient(135deg,#21b879,#0a6643);box-shadow:0 0 18px #35e6a033}.done .pct{color:#48e6aa}.failed .mark{background:linear-gradient(135deg,#ff2446,#710014)}.failed .pct{color:#ff7187}@media(max-width:420px){main{padding:7px}.head{padding:8px}.media img,.media video{max-height:230px}}
</style></head><body><main><section class="card" id="card"><div class="head"><div class="mark">M</div><div class="copy"><div class="title" id="title">MIIAIVIDEO</div><div class="sub" id="state">MENYIAPKAN TASK</div></div><div class="pct" id="pct">0%</div></div><div class="bar" id="bar"><div class="fill" id="fill"></div></div><div class="media" id="media"><img id="image" alt="Hasil MIIAIVIDEO"><video id="video" controls playsinline preload="metadata"></video><audio id="audio" controls preload="metadata"></audio></div><div class="foot" id="foot"><span id="kind"></span><a id="open" target="_blank" rel="noopener">BUKA HASIL</a></div></section></main><script>
(function(){var taskId='',statusToken='',timer=0,attempts=0,terminal=false,last={};var $=function(id){return document.getElementById(id)};
function unwrap(r){return r&&r.structuredContent?r.structuredContent:(r||{})}
function mediaOf(r){var o=r.output||r.result||{},imgs=o.images||[];return{video:o.video_url||(o.type==='video'?o.url:'')||'',image:o.image_url||(imgs[0]&&((imgs[0].url)||imgs[0]))||(o.type==='image'?o.url:'')||'',audio:o.audio_url||(o.type==='audio'?o.url:'')||''}}
function schedule(){if(terminal||!taskId||!statusToken)return;if(attempts>=360){$('state').textContent='CEK STATUS DI WEB';$('foot').style.display='flex';$('open').href='https://makima.cloud/ai-video';return}clearTimeout(timer);timer=setTimeout(function(){attempts++;fetch(__MII_WIDGET_STATUS_ENDPOINT__,{method:'POST',headers:{'Content-Type':'text/plain'},body:statusToken,credentials:'omit',cache:'no-store'}).then(function(response){if(response.status===401){terminal=true;$('state').textContent='STATUS KEDALUWARSA';return null}if(!response.ok)throw Error('Status unavailable');return response.json()}).then(function(data){if(data)render(data)}).catch(function(){$('state').textContent='MENUNGGU KONEKSI';schedule()})},attempts<6?3000:6000)}
function render(raw){var r=unwrap(raw);if(!r||typeof r!=='object')return;last=r;taskId=r.task_id||r.id||taskId;statusToken=r.status_token||statusToken;var status=String(r.status||'pending').toLowerCase(),p=Math.max(0,Math.min(100,Number(r.progress)||0)),m=mediaOf(r);$('fill').style.width=p+'%';$('pct').textContent=p+'%';$('title').textContent=(r.model||r.model_name||'MIIAIVIDEO').toString();$('state').textContent=r.error?String(r.error):(status==='completed'?'HASIL SIAP':status==='failed'?'PROSES GAGAL':status==='pending'||status==='queued'?'MENUNGGU PROSES':'SEDANG MEMPROSES');$('state').className='sub'+(r.error?' err':'');terminal=status==='completed'||status==='failed'||!!r.error;if(terminal){$('card').classList.add(status==='completed'?'done':'failed');$('bar').style.display='none'}var u=m.video||m.image||m.audio;if(u){terminal=true;$('card').classList.add('done');$('media').style.display='block';$('foot').style.display='flex';$('open').href=u;var kind=m.video?'VIDEO':m.image?'IMAGE':'AUDIO';$('kind').textContent=kind;if(m.video){$('video').src=m.video;$('video').style.display='block';$('image').style.display=$('audio').style.display='none'}else if(m.image){$('image').src=m.image;$('image').style.display='block';$('video').style.display=$('audio').style.display='none'}else{$('audio').src=m.audio;$('audio').style.display='block';$('image').style.display=$('video').style.display='none'}}if(!terminal)schedule()}
render((window.openai&&window.openai.toolOutput)||{});window.addEventListener('openai:set_globals',function(e){if(e.detail&&e.detail.globals)render(e.detail.globals.toolOutput)});
})();</script></body></html>'''
            html=html.replace('__MII_WIDGET_STATUS_ENDPOINT__',json.dumps(origin+'/mcp/widget-status'))
            meta={'ui':{'prefersBorder':True,'csp':{'connectDomains':[origin],'resourceDomains':[origin,'https://*.dropboxusercontent.com']}},'openai/widgetDescription':'Status dan preview hasil Image, Video, atau Audio MIIAIVIDEO dalam satu kartu yang diperbarui otomatis.','openai/widgetPrefersBorder':True,'openai/widgetCSP':{'connect_domains':[origin],'resource_domains':[origin,'https://*.dropboxusercontent.com']}}
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
