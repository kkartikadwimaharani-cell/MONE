import base64
import hashlib
import json
import os
import tempfile
import unittest
from urllib.parse import urlencode, urlsplit, parse_qs
from unittest.mock import Mock, patch


class MiiMcpIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import app
        cls.module=app
        cls.app=app.app

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app.config.update(TESTING=True, MII_MCP_DB=os.path.join(self.tmp.name,'access.db'))
        self.client=self.app.test_client()
        self.addCleanup(patch.stopall)
        patch.object(self.module,'get_site_status',return_value={'maintenance':False}).start()
        self.owner()

    def owner(self):
        with self.client.session_transaction() as s:
            s['mii_aivideo_auth']=True
            s['mii_csrf']='test-csrf'

    def key(self):
        r=self.client.post('/ai-video/mcp/keys',json={'label':'Test'},headers={'X-CSRF-Token':'test-csrf'})
        self.assertEqual(r.status_code,200,r.data)
        return r.get_json()

    def rpc(self,key,method,params=None):
        return self.client.post('/mcp',json={'jsonrpc':'2.0','id':1,'method':method,'params':params or {}},headers={'Authorization':'Bearer '+key})

    def call(self,key,name,args=None):
        r=self.rpc(key,'tools/call',{'name':'mii_ai_studio_'+name,'arguments':args or {}})
        self.assertEqual(r.status_code,200,r.data)
        return r.get_json()['result']

    def test_debug_page_and_refresh_contract(self):
        patch.object(self.module,'_dropbox_status_check',side_effect=AssertionError('No network for rendering')).start()
        r=self.client.get('/ai-video/debug')
        self.assertEqual(r.status_code,200)
        self.assertIn(b'MII AI STUDIO MCP',r.data)
        data=self.client.get('/api/aivideo/debug-data').get_json()
        for key in ('storage','generation','motion','pipeline','request_log'):
            self.assertIsInstance(data[key],dict)
        self.assertIsInstance(data['request_log']['entries'],list)

    def test_telegram_webhook_auth_health_and_maintenance_bypass(self):
        update={'update_id':123,'message':{'chat':{'id':99},'from':{'id':99},'text':'/start'}}
        self.assertEqual(self.client.post('/telegram/webhook',json=update).status_code,401)
        original_get_secret=self.module.get_secret
        def test_secret(key,*fallbacks):
            return 'test-telegram-token' if key=='TELEGRAM_BOT_TOKEN' else original_get_secret(key,*fallbacks)
        with patch.object(self.module,'get_secret',side_effect=test_secret), \
             patch.object(self.module,'process_telegram_update') as process:
            secret=self.module._telegram_webhook_secret()
            response=self.client.post('/telegram/webhook',json=update,headers={
                'X-Telegram-Bot-Api-Secret-Token':secret,
            })
            health=self.client.get('/telegram/health')
        self.assertEqual(response.status_code,200,response.data)
        process.assert_called_once_with(update)
        self.assertEqual(health.status_code,200)
        self.assertIn('delivery',health.get_json())

    def test_dashboard_key_and_revoke(self):
        self.assertEqual(self.client.get('/ai-video/mcp').status_code,200)
        issued=self.key()
        self.assertNotIn(issued['key'].encode(),self.client.get('/ai-video/mcp').data)
        self.assertEqual(self.rpc(issued['key'],'initialize').get_json()['result']['serverInfo']['name'],'MII AI STUDIO')
        self.assertEqual(self.client.post('/ai-video/mcp/revoke',json={'id':issued['id']},headers={'X-CSRF-Token':'test-csrf'}).status_code,200)
        self.assertEqual(self.rpc(issued['key'],'ping').status_code,401)

    def test_cookie_is_not_mcp_authorization(self):
        self.assertEqual(self.client.post('/mcp',json={}).status_code,401)
        with self.client.session_transaction() as s:s.clear()
        self.assertIn(b'Unlock',self.client.get('/ai-video/mcp').data)
        self.assertEqual(self.client.post('/ai-video/mcp/keys',json={}).status_code,401)

    def test_key_cannot_admin_or_skip_csrf(self):
        issued=self.key()['key']
        self.assertEqual(self.client.post('/ai-video/mcp/keys',json={}).status_code,403)
        with self.client.session_transaction() as s:s.clear()
        self.assertEqual(self.client.get('/api/aivideo/app-secrets/list',headers={'Authorization':'Bearer '+issued}).status_code,401)

    def test_all_tools_and_every_advertised_variant_without_spending(self):
        key=self.key()['key']
        defs=self.rpc(key,'tools/list').get_json()['result']['tools']
        self.assertEqual(len(defs),13)
        models=json.loads(self.call(key,'list_models')['content'][0]['text'])['models']
        patch.object(self.module,'_segmind_api_key',return_value='test-only').start()
        patch.object(self.module,'_budgetpixel_api_key',return_value='test-only').start()
        worker=patch.object(self.module.threading,'Thread').start()
        patch.object(self.module,'validateVideo',return_value={'dropbox_url_processed':'https://example.com/video.mp4','processed':{'duration':5,'aspect_ratio':'16:9'}}).start()
        count=0
        for kind,items in models.items():
            for combo in items:
                with self.subTest(model=combo):
                    family,variant=combo.split(':')
                    args={'prompt':'A quiet city','family':family,'variant':variant}
                    name={'video':'generate_video','image':'generate_image','audio':'generate_audio','motion':'motion_control'}[kind]
                    if kind=='audio':args={'prompt':'Quiet rain','audio_format':'wav','sample_rate':44100}
                    if kind=='motion':args={'prompt':'Maintain movement','variant':variant,'video_urls':['https://example.com/video.mp4']}
                    data=self.call(key,name,args)
                    self.assertFalse(data['isError'],data)
                    result=json.loads(data['content'][0]['text'])
                    self.assertIn('task_id',result)
                    status=self.call(key,'check_status',{'task_id':result['task_id']})
                    self.assertFalse(status['isError'],status)
                    count+=1
        self.assertEqual(worker.call_count,count)
        self.assertGreaterEqual(count,37)

    def test_large_reference_uploads_then_seedance_submission_without_spending(self):
        key=self.key()['key']
        # The old 256 KB MCP cap rejected even one ordinary reference sheet.
        image=b'\x89PNG\r\n\x1a\n'+b'x'*300000
        uploads=patch.object(self.module,'_dropbox_upload_and_link',
                             side_effect=lambda raw,filename: 'https://example.com/refs/'+filename).start()
        urls=[]
        for index in range(8):
            encoded=base64.b64encode(image+str(index).encode()).decode()
            result=self.call(key,'upload_reference',{'image_base64':'data:image/png;base64,'+encoded})
            self.assertFalse(result['isError'],result)
            urls.append(result['structuredContent']['url'])
        self.assertEqual(len(set(urls)),8)
        self.assertEqual(uploads.call_count,8)
        self.assertEqual(uploads.call_args_list[0].args[0],image+b'0')

        caps=self.call(key,'get_model_capabilities',
                       {'slug':'bpx-seedance-2.5:STANDARD','category':'video'})
        self.assertFalse(caps['isError'],caps)
        self.assertEqual(caps['structuredContent']['model_id'],
                         'bpx-seedance-2.5:STANDARD')
        patch.object(self.module,'_budgetpixel_api_key',return_value='test-only').start()
        worker=patch.object(self.module.threading,'Thread').start()
        result=self.call(key,'generate_video',{
            'prompt':'Eight distinct adults in a modern home',
            'model_slug':'bpx-seedance-2.5:STANDARD',
            'duration':30,'resolution':'720p','aspect_ratio':'16:9',
            'mute_audio':False,'image_urls':urls,
        })
        self.assertFalse(result['isError'],result)
        self.assertIn('task_id',result['structuredContent'])
        worker.assert_called_once()
        audit=self.module._aivideo_debug_snapshot()['last_provider_links']
        self.assertEqual(audit['count'],8)
        self.assertEqual([link['url'] for link in audit['links']],urls)

        invalid=self.call(key,'upload_reference',{'image_base64':'data:text/plain;base64,'+encoded})
        self.assertTrue(invalid['isError'])
        self.assertEqual(uploads.call_count,8)

    def test_non_upload_mcp_requests_keep_small_body_limit(self):
        key=self.key()['key']
        response=self.rpc(key,'tools/list',{'padding':'x'*300000})
        self.assertEqual(response.status_code,413)
        self.assertEqual(response.get_json()['error'],'request_too_large')

    def test_budgetpixel_image_runner_uses_image_lifecycle(self):
        task_id='image-runner-test'
        with self.module.AIVIDEO_TASKS_LOCK:
            self.module.AIVIDEO_TASKS[task_id]={'status':'pending','progress':5,'output':None,'error':None}
        submit=patch.object(self.module.budgetpixel_provider,'submit_image',return_value={'job_id':'img-job'}).start()
        submit_video=patch.object(self.module.budgetpixel_provider,'submit_video').start()
        poll=patch.object(self.module.budgetpixel_provider,'poll',return_value={'status':'completed','url':'https://example.com/result.png'}).start()
        response=Mock(status_code=200,content=b'fake-image-bytes')
        patch.object(self.module.requests_lib,'get',return_value=response).start()
        patch.object(self.module,'_budgetpixel_api_key',return_value='test-only').start()
        patch.object(self.module,'_dropbox_upload_and_link',return_value='https://example.com/permanent.png').start()
        self.module._run_budgetpixel_task(task_id,'flux2','KLEIN',{'prompt':'x'},'image')
        submit.assert_called_once()
        submit_video.assert_not_called()
        poll.assert_called_once_with('img-job','test-only',kind='image')
        with self.module.AIVIDEO_TASKS_LOCK:
            task=dict(self.module.AIVIDEO_TASKS[task_id])
        self.assertEqual(task['status'],'completed')
        self.assertEqual(task['output']['image_url'],'https://example.com/permanent.png')

    def test_bad_controls_unknown_tool_missing_task_and_provider_failure(self):
        key=self.key()['key']
        for args in ({'prompt':'x','family':'flux','variant':'STANDARD'}, {'prompt':'x','family':'imagen','image_urls':['https://example.com/a.png']}, {'prompt':'x','family':'gptimage','resolution':'4K'}, {'prompt':'x','family':'bpx-midjourney-v7','model_slug':'flux-2-klein'}):
            self.assertTrue(self.call(key,'generate_image',args)['isError'])
        self.assertTrue(self.call(key,'check_status',{'task_id':'missing'})['isError'])
        self.assertTrue(self.call(key,'motion_control',{'video_urls':[]})['isError'])
        self.assertIn('error',self.rpc(key,'tools/call',{'name':'not_a_tool'}).get_json())
        self.assertIn('error',self.rpc(key,'tools/call',{'name':'miiaivideo_generate_video','arguments':{'prompt':9}}).get_json())
        legacy=self.rpc(key,'tools/call',{'name':'miiaivideo_list_models','arguments':{}}).get_json()
        self.assertIn('models',legacy['result']['structuredContent'])
        patch.object(self.module,'_budgetpixel_api_key',return_value='').start()
        self.assertTrue(self.call(key,'generate_video',{'prompt':'x'})['isError'])

    def test_clear_debug_auto_clear_link_audit_and_preview_resource(self):
        key=self.key()['key']
        self.module._aivideo_debug_set('last_error',source='old',message='old')
        self.assertFalse(self.call(key,'clear_debug')['isError'])
        self.assertIsNone(self.module._aivideo_debug_snapshot()['last_error'])

        patch.object(self.module,'_budgetpixel_api_key',return_value='test-only').start()
        patch.object(self.module.threading,'Thread').start()
        result=self.call(key,'generate_video',{
            'prompt':'Test links','family':'seedance25','variant':'STANDARD',
            'image_urls':['https://dl.dropboxusercontent.com/s/test/reference.png'],
        })
        self.assertFalse(result['isError'],result)
        audit=self.module._aivideo_debug_snapshot()['last_provider_links']
        self.assertEqual(audit['count'],1)
        self.assertTrue(audit['links'][0]['direct_dropbox'])

        listed=self.rpc(key,'resources/list').get_json()['result']['resources']
        self.assertEqual(listed[0]['mimeType'],'text/html;profile=mcp-app')
        read=self.rpc(key,'resources/read',{'uri':listed[0]['uri']}).get_json()
        widget=read['result']['contents'][0]['text']
        for element in ('<video', '<audio', '<img', 'ui/notifications/tool-result',
                        'ui/notifications/initialized',
                        "if(typeof u!=='string'||!u.trim())return '';"):
            self.assertIn(element,widget)

    def test_signed_widget_status_and_typed_previews_without_provider_calls(self):
        key=self.key()['key']
        initialize=self.rpc(key,'initialize').get_json()['result']
        self.assertIn('resources',initialize['capabilities'])
        listed=self.rpc(key,'tools/list').get_json()['result']['tools']
        self.assertEqual(len(listed),len({t['name'] for t in listed}))
        self.assertTrue(all(t['name'].startswith('mii_ai_studio_') for t in listed))
        self.assertTrue(all(t['title'].startswith('MII AI STUDIO ') for t in listed))
        generation=next(t for t in listed if t['name']=='mii_ai_studio_generate_video')
        self.assertEqual(generation['_meta']['ui']['resourceUri'],
                         self.rpc(key,'resources/list').get_json()['result']['resources'][0]['uri'])
        patch.object(self.module,'_budgetpixel_api_key',return_value='test-only').start()
        worker=patch.object(self.module.threading,'Thread').start()
        started=self.call(key,'generate_video',{'prompt':'Preview contract test',
                                                'family':'seedance25','variant':'STANDARD'})
        self.assertFalse(started['isError'],started)
        payload=started['structuredContent']
        task_id=payload['task_id']
        token=payload['status_token']
        self.assertTrue(token)
        worker.assert_called_once()
        pending=self.client.post('/mcp/widget-status',data=token,
                                 content_type='text/plain').get_json()
        self.assertNotIn('preview',pending)
        self.assertEqual(self.client.post('/mcp/widget-status',data='bad-token',
                                          content_type='text/plain').status_code,401)
        media=(
            ('video','video_url','https://dl.dropboxusercontent.com/s/demo/clip.mp4','video/mp4'),
            ('image','image_url','/static/aivideo_uploads/demo.png','image/png'),
            ('audio','audio_url','https://dl.dropboxusercontent.com/s/demo/track.mp3','audio/mpeg'),
        )
        for kind,field,url,mime in media:
            with self.subTest(kind=kind):
                with patch.dict(self.module.AIVIDEO_TASKS,{task_id:{
                    'status':'completed','progress':100,'output':{field:url},
                    'error':None,
                }}):
                    expected='https://makima.cloud'+url if url.startswith('/') else url
                    status=self.call(key,'check_status',{'task_id':task_id})
                    self.assertFalse(status['isError'],status)
                    self.assertEqual(status['structuredContent']['preview'],
                                     {'kind':kind,'url':expected,'mime_type':mime})
                    self.assertEqual(status['content'][1]['type'],'resource_link')
                    self.assertEqual(status['content'][1]['uri'],expected)
                    self.assertEqual(status['content'][1]['mimeType'],mime)
                    widget=self.client.post('/mcp/widget-status',data=token,
                                            content_type='text/plain')
                    self.assertEqual(widget.status_code,200,widget.data)
                    self.assertEqual(widget.get_json()['preview']['url'],expected)

    def oauth_code(self, simulate_restart=False):
        r=self.client.post('/oauth/register',json={'client_name':'Test agent','redirect_uris':['https://agent.example/callback'],'token_endpoint_auth_method':'none'})
        self.assertEqual(r.status_code,201,r.data)
        client=r.get_json()['client_id']
        if simulate_restart:
            # Railway's local filesystem may be replaced between DCR and consent.
            os.remove(self.app.config['MII_MCP_DB'])
        verifier='a'*64
        challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
        params={'client_id':client,'redirect_uri':'https://agent.example/callback','response_type':'code','code_challenge':challenge,'code_challenge_method':'S256','resource':'https://makima.cloud/mcp','scope':'mii:generate','state':'original-state'}
        url='/oauth/authorize?'+urlencode(params)
        self.assertEqual(self.client.get(url).status_code,200)
        self.assertEqual(self.client.post(url,data={'decision':'approve'}).status_code,403)
        r=self.client.post(url,data={'decision':'approve','csrf':'test-csrf'})
        self.assertEqual(r.status_code,303,r.data)
        query=parse_qs(urlsplit(r.location).query)
        self.assertEqual(query['state'],['original-state'])
        return {'grant_type':'authorization_code','client_id':client,'redirect_uri':params['redirect_uri'],'code':query['code'][0],'code_verifier':verifier,'resource':params['resource']}

    def test_oauth_client_survives_ephemeral_database_restart(self):
        form=self.oauth_code(simulate_restart=True)
        response=self.client.post('/oauth/token',data=form)
        self.assertEqual(response.status_code,200,response.data)

    def test_oauth_full_flow_pkce_replay_refresh_rotation_and_revocation(self):
        form=self.oauth_code()
        self.assertEqual(self.client.post('/oauth/token',data=dict(form,code_verifier='b'*64)).status_code,400)
        r=self.client.post('/oauth/token',data=form)
        self.assertEqual(r.status_code,200,r.data)
        tokens=r.get_json()
        self.assertEqual(self.rpc(tokens['access_token'],'tools/list').status_code,200)
        self.assertEqual(self.client.post('/oauth/token',data=form).status_code,400)
        refresh={'grant_type':'refresh_token','client_id':form['client_id'],'refresh_token':tokens['refresh_token'],'resource':form['resource']}
        rotated=self.client.post('/oauth/token',data=refresh)
        self.assertEqual(rotated.status_code,200,rotated.data)
        self.assertEqual(self.client.post('/oauth/token',data=refresh).status_code,400)
        self.assertEqual(self.rpc(rotated.get_json()['access_token'],'ping').status_code,401)

    def test_official_mcp_sdk_can_initialize_list_and_call(self):
        import asyncio
        import httpx
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client
        from starlette.middleware.wsgi import WSGIMiddleware
        key=self.key()['key']
        async def run():
            transport=httpx.ASGITransport(app=WSGIMiddleware(self.app))
            async with httpx.AsyncClient(transport=transport,headers={'Authorization':'Bearer '+key}) as http:
                async with streamable_http_client('https://makima.cloud/mcp',http_client=http) as (read,write,_):
                    async with ClientSession(read,write) as client:
                        info=await client.initialize()
                        self.assertEqual(info.serverInfo.name,'MII AI STUDIO')
                        definitions=await client.list_tools()
                        self.assertEqual(len(definitions.tools),13)
                        result=await client.call_tool('mii_ai_studio_list_models',{})
                        self.assertFalse(result.isError)
                        self.assertIn('models',json.loads(result.content[0].text))
        asyncio.run(run())

    def test_metadata_and_invalid_redirects(self):
        challenge=self.client.post('/mcp',json={})
        self.assertIn('resource_metadata',challenge.headers['WWW-Authenticate'])
        self.assertEqual(self.client.get('/.well-known/oauth-protected-resource/mcp').get_json()['resource'],'https://makima.cloud/mcp')
        self.assertEqual(self.client.get('/.well-known/oauth-authorization-server').get_json()['code_challenge_methods_supported'],['S256'])
        for uri in ('javascript:alert(1)','http://remote.example/cb','https://example.com/#fragment'):
            self.assertEqual(self.client.post('/oauth/register',json={'redirect_uris':[uri]}).status_code,400)
        self.assertEqual(self.client.get('/oauth/authorize?client_id=bad&redirect_uri=https://evil.example').status_code,400)


if __name__=='__main__':unittest.main()
