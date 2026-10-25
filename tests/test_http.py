"""Loopback endpoint and demo privacy regression checks, using synthetic records."""
import json,sys,threading,unittest
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from http.server import ThreadingHTTPServer
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'plugins/codex-usage-lab'))
import service

class HttpTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.old=(service.PORT,service.STATE,service.DEMO)
  cls.http=ThreadingHTTPServer(('127.0.0.1',0),service.Handler)
  service.PORT=cls.http.server_port;service.DEMO=True
  service.STATE=json.loads((service.ROOT/'demo.json').read_text())
  cls.base=f'http://127.0.0.1:{service.PORT}'
  cls.thread=threading.Thread(target=cls.http.serve_forever,daemon=True);cls.thread.start()
 @classmethod
 def tearDownClass(cls):
  cls.http.shutdown();cls.http.server_close();cls.thread.join()
  service.PORT,service.STATE,service.DEMO=cls.old
 def test_static_assets(self):
  for path,kind in [('/','text/html'),('/dashboard.css','text/css'),('/dashboard.js','text/javascript'),('/demo.json','application/json')]:
   with urlopen(self.base+path) as r:self.assertEqual(r.status,200);self.assertIn(kind,r.headers['Content-Type'])
 def test_host_rebinding_denied(self):
  with self.assertRaises(HTTPError) as e:urlopen(Request(self.base+'/api/usage',headers={'Host':'evil.example'}))
  self.assertEqual(e.exception.code,403)
 def test_files_outside_whitelist_denied(self):
  for path in ['/collector.py','/../README.md','/.mcp.json']:
   with self.assertRaises(HTTPError) as e:urlopen(self.base+path)
   self.assertEqual(e.exception.code,404)
 def test_cross_origin_post_denied(self):
  req=Request(self.base+'/api/query',data=b'{}',headers={'Content-Type':'application/json','Origin':'https://evil.example'})
  with self.assertRaises(HTTPError) as e:urlopen(req)
  self.assertEqual(e.exception.code,403)
 def test_annotation_requires_csrf(self):
  req=Request(self.base+'/api/annotate',data=b'{}',headers={'Content-Type':'application/json'})
  with self.assertRaises(HTTPError) as e:urlopen(req)
  self.assertEqual(e.exception.code,403)
 def test_demo_never_writes_annotations(self):
  with self.assertRaisesRegex(ValueError,'read-only'):service.annotate({})
 def test_demo_query_is_synthetic(self):
  req=Request(self.base+'/api/query',data=json.dumps({'group_by':'thread','limit':20}).encode(),headers={'Content-Type':'application/json'})
  with urlopen(req) as response:data=json.load(response)
  self.assertEqual(data['totalRows'],6)
  self.assertTrue(all(r['thread_id'].startswith('demo-') for r in data['rows']))
