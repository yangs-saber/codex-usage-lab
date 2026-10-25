import importlib.util,json,sys,tempfile,unittest,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]/'plugins/codex-usage-lab';sys.path.insert(0,str(ROOT))
import collector,analytics,plugin_api
class UsageTests(unittest.TestCase):
 def parse(self,items):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'a.jsonl';p.write_text('\n'.join(json.dumps(x) for x in items));return collector.parse(p)
 def test_settings_changes(self):
  def d(t,p):return {'timestamp':'2026-10-23T01:00:00Z','type':t,'payload':p}
  rows=[d('session_meta',{'id':'thread1'}),d('event_msg',{'type':'thread_settings_applied','thread_settings':{'model':'gpt-6.1-sol','service_tier':'priority','reasoning_effort':'high'}}),d('turn_context',{'turn_id':'turn1','model':'gpt-6.1-sol','effort':'high'}),d('token_usage_record',{'response_id':'r1','turn_id':'turn1','usage':{'input_tokens':100,'cached_input_tokens':90,'output_tokens':10}}),d('event_msg',{'type':'thread_settings_applied','thread_settings':{'model':'gpt-6-astra','service_tier':'default','reasoning_effort':'low'}}),d('token_usage_record',{'response_id':'r2','turn_id':'turn1','usage':{'input_tokens':200,'output_tokens':10}})]
  r=self.parse(rows)['records'];self.assertEqual(r[0]['tier'],'priority');self.assertEqual(r[1]['model'],'gpt-6-astra');self.assertEqual(r[1]['effort'],'low')
 def test_cost_no_double_count(self):
  self.assertEqual(collector.cost({'input_tokens':1000000,'cached_input_tokens':400000,'output_tokens':100000,'reasoning_output_tokens':50000},'gpt-6.1-sol'),56)
  self.assertIsNone(collector.cost({},'unpriced'))
 def test_missing_prices_not_zero(self):
  self.assertIsNone(analytics.summarize([{'credits':None,'total':20,'input':10,'cached':0,'output':10}])['credits'])
 def test_comparison_pricing_coverage_and_ratings(self):
  row={'id':'r','thread':'t','turn':'1','time':'2026-10-23T01:00:00Z','date':'2026-10-23','title':'Synthetic','projectId':'p','project':'P','model':'gpt-6.1-sol','effort':'high','tier':'default','tierKnown':True,'input':100,'cached':90,'output':10,'total':110,'credits':1}
  data={'records':[row,{**row,'id':'r2','turn':'2','credits':None}],'annotations':{'t:1':{'task':'coding','outcome':'success'},'t:2':{'task':'coding','outcome':'failed'}}}
  result=analytics.query(data,{'group_by':'comparison'})['rows'][0]
  self.assertEqual(result['turns'],2);self.assertEqual(result['pricedTurns'],1);self.assertEqual(result['meanCredits'],1);self.assertEqual(result['successfulTurns'],1)
 def test_query_validation(self):
  for args in [{'limit':True},{'limit':101},{'group_by':'sql'},{'since':'not-a-date'}]:
   with self.assertRaises(ValueError):plugin_api.validate_query(args)
 def test_mcp_handshake_and_invalid_request(self):
  messages=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'test','version':'1'}}},{'jsonrpc':'2.0','id':2,'method':'tools/list'},{'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'query_usage','arguments':{'limit':999}}}]
  p=subprocess.run([sys.executable,str(ROOT/'mcp_server.py')],input='\n'.join(json.dumps(m) for m in messages)+'\n',text=True,capture_output=True,check=True)
  out=[json.loads(l) for l in p.stdout.splitlines()];self.assertEqual(len(out[1]['result']['tools']),3);self.assertTrue(out[2]['result']['isError'])
 def test_embedded_meter_entrypoint_and_resource(self):
  from mcp_server import McpServer
  server=McpServer(None)
  def ask(i,method,params=None):return server.handle({'jsonrpc':'2.0','id':i,'method':method,'params':params or {}})['result']
  tools=ask(1,'tools/list')['tools']
  meter=next(t for t in tools if t['name']=='open_usage_dashboard')
  self.assertEqual(meter['_meta']['openai/ui']['entrypoints'],[{'type':'thread'}])
  uri=meter['_meta']['ui']['resourceUri']
  resources=ask(2,'resources/list')['resources']
  self.assertTrue(any(r['uri']==uri for r in resources))
  page=ask(3,'resources/read',{'uri':uri})['contents'][0]
  self.assertEqual(page['mimeType'],'text/html;profile=mcp-app')
  self.assertIn('实时用量',page['text'])
  self.assertIn('callServerTool',page['text'])
 def test_dashboard_binds_launching_thread(self):
  from unittest.mock import patch
  with patch.dict('os.environ',{'CODEX_THREAD_ID':'current-chat'}),patch.object(plugin_api,'ensure_service'),patch.object(plugin_api,'http',return_value={'rows':[]}):
   result=plugin_api.KernelApplication().dispatch('open_usage_dashboard',{})
  self.assertEqual(result['thread_id'],'current-chat')
class TurnMessageTests(unittest.TestCase):
 parse=UsageTests.parse
 def test_user_excerpt_attribution(self):
  def e(t,p):return {'type':t,'timestamp':'2026-10-25T00:00:00Z','payload':p}
  result=self.parse([e('event_msg',{'type':'task_started','turn_id':'turn1'}),e('response_item',{'type':'message','role':'user','content':[{'type':'input_text','text':'<environment_context>private context</environment_context>\n## My request:\n请优化首页'}]}),e('event_msg',{'type':'user_message','message':'请优化首页'}),e('response_item',{'type':'message','role':'assistant','content':[{'type':'output_text','text':'not user text'}]}),e('event_msg',{'type':'task_complete','turn_id':'turn1'}),e('response_item',{'type':'message','role':'user','content':[{'type':'input_text','text':'unattributed'}]}),e('event_msg',{'type':'task_started','turn_id':'turn2'}),e('event_msg',{'type':'user_message','message':'第二个请求'})])
  self.assertEqual(result['turns']['turn1']['message'],'请优化首页')
  self.assertEqual(result['turns']['turn2']['message'],'第二个请求')
  self.assertNotIn('unattributed',str(result['turns']))
 def test_excerpt_bound_and_context_only(self):
  self.assertEqual(collector.message_excerpt('<environment_context>hidden</environment_context>'),'')
  self.assertEqual(len(collector.message_excerpt('a'*5000)),1200)
if __name__=='__main__':unittest.main()
