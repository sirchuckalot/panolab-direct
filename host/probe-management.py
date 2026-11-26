import json,sys,urllib.request,urllib.error,time
token=open('/run/secrets/mcp-bearer').read().strip()
url='http://manager:8767/mcp'
def call(obj,auth=True):
    hdr={'Content-Type':'application/json',
         'Accept':'application/json, text/event-stream',
         'MCP-Protocol-Version':'2025-06-18'}
    if auth: hdr['Authorization']=token
    req=urllib.request.Request(url,data=json.dumps(obj).encode(),headers=hdr,method='POST')
    with urllib.request.urlopen(req,timeout=10) as res:
        return res.status,json.load(res)
init={'jsonrpc':'2.0','id':1,'method':'initialize','params':{
    'protocolVersion':'2025-06-18','capabilities':{},
    'clientInfo':{'name':'panolab-laptop-local-acceptance','version':'1'}}}
for attempt in range(12):
    try:
        code,obj=call(init)
        assert code==200 and obj.get('result',{}).get('serverInfo',{}).get('name')=='panolab-manager'
        break
    except (urllib.error.URLError,AssertionError):
        if attempt==11: raise
        time.sleep(1)
try:
    call(init,False)
except urllib.error.HTTPError as e:
    if e.code!=401: raise
else:
    raise RuntimeError('Anonymous MCP call was accepted')
for i,tool in enumerate(('lab_status','repo_status'),2):
    code,obj=call({'jsonrpc':'2.0','id':i,'method':'tools/call',
                  'params':{'name':tool,'arguments':{}}})
    result = obj.get('result', {})
    assert code == 200 and not obj.get('error') and not result.get('isError'), tool
    details = result.get("structuredContent")
    if details is None:
        details = json.loads(result["content"][0]["text"])
    if tool == "lab_status":
        assert details.get("ok") is True and details.get("exit_code") == 0, tool
    elif len(sys.argv) > 1:
        assert details.get("branch") == "development" and details.get("head") == sys.argv[1], tool
        assert details.get("clean") is True, tool
    else:
        assert details.get("head") and not details.get("git_error"), tool
print('PASS: private authenticated MCP, anonymous request rejected, status and repo tools')
