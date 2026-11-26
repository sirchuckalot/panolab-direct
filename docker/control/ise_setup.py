#!/usr/bin/env python3
"""Ordinary PanoLab restricted broker setup probe.

The setup service may be stopped during normal operation. This adapter uses
the *existing* manager's authenticated proxy, never the maintenance sidecar
or a host-side bearer. It cannot start the native installer.
"""
import json
import re

SETUP="panolab-direct-connect-setup-1"
CALLS={
 "info":"ise_setup_status",
 "status":"ise_install_status",
 "inspect":"ise_media_inspect",
 "reject_invalid_install":"ise_install_start",
}
PROBE=r'''
import json,sys,urllib2
try:
 operation=sys.argv[1]
 names={"info":"ise_setup_status","status":"ise_install_status",
        "inspect":"ise_media_inspect",
        "reject_invalid_install":"ise_install_start"}
 if operation not in names:
  print(json.dumps({"ok":False,"category":"OPERATION_NOT_ALLOWED"}));sys.exit(4)
 token=open('/run/secrets/mcp-bearer','rb').read().strip()
 if not token.startswith(b'Bearer '):token=b'Bearer '+token
 if not isinstance(token,str):token=token.decode('ascii')
 args={}
 if operation=="reject_invalid_install":
  # Do NOT send real SHA or owner confirmation.
  args={"SHA256":"0"*64,"Confirmation":"INTENTIONALLY_INVALID"}
 payload=json.dumps({"jsonrpc":"2.0","id":1,"method":"tools/call",
   "params":{"name":names[operation],"arguments":args}})
 req=urllib2.Request('http://manager:8767/mcp',data=payload,
  headers={"Authorization":token,"Content-Type":"application/json",
   "Accept":"application/json, text/event-stream",
   "MCP-Protocol-Version":"2025-06-18"})
 response=json.load(urllib2.urlopen(req,timeout=120))
 if response.get("error") or response.get("result",{}).get("isError"):
  # Rejected requests must not disclose raw error message or bearer.
  print(json.dumps({"ok":False,"category":"REJECTED"}));sys.exit(4)
 result=response.get("result",{})
 data=result.get("structuredContent")
 if data is None:
  texts=result.get("content",[])
  if len(texts)==1 and texts[0].get("type")=="text":
   try:data=json.loads(texts[0]["text"])
   except Exception:data={"text":texts[0]["text"]}
 if not isinstance(data,dict):data={}
 print(json.dumps({"ok":True,"fields":data},sort_keys=True))
except urllib2.HTTPError as e:
 print(json.dumps({"ok":False,"category":"HTTP_"+str(e.code)}));sys.exit(4)
except Exception as e:
 print(json.dumps({"ok":False,"category":type(e).__name__.upper()}));sys.exit(4)
'''

def call_setup(request,command):
    operation=request.get("operation")
    if operation not in CALLS:
        return {"ok":False,"error":"SETUP_OPERATION_NOT_ALLOWED"}
    check=command(["docker","inspect","--format",
                   '{{.Name}}|{{.State.Running}}|{{index .Config.Labels "com.docker.compose.project"}}|{{.HostConfig.Privileged}}',
                   SETUP],15)
    if not check.get("ok"):
        return {"ok":True,"operation":operation,"available":False,"state":"not_created"}
    parts=(check.get("stdout") or "").strip().split("|")
    if len(parts)!=4 or parts[0]!="/"+SETUP or parts[2]!="panolab-direct-external" or parts[3]!="false":
        return {"ok":False,"error":"SETUP_IDENTITY_CHANGED"}
    if parts[1]=="false":
        return {"ok":True,"operation":operation,"available":False,"state":"stopped"}
    if parts[1]!="true":
        return {"ok":False,"error":"SETUP_STATE_UNKNOWN"}
    invocation=command(["docker","exec","--user","0:0",SETUP,
                        "python","-c",PROBE,operation],145)
    raw=(invocation.get("stdout") or "").strip()
    if len(raw)>64000:
        return {"ok":False,"error":"SETUP_RESPONSE_TOO_LARGE"}
    try:
        result=json.loads(raw)
    except (TypeError,ValueError):
        return {"ok":False,"error":"SETUP_RESPONSE_UNAVAILABLE"}
    if not isinstance(result,dict):
        return {"ok":False,"error":"SETUP_RESPONSE_INVALID"}
    if operation=="reject_invalid_install":
        if result.get("category")=="REJECTED" and not result.get("ok"):
            return {"ok":True,"operation":operation,"available":True,
                    "rejected_without_install":True}
        return {"ok":False,"error":"UNEXPECTED_INSTALL_ACCEPTANCE"}
    if not result.get("ok") or not invocation.get("ok"):
        return {"ok":False,"error":"SETUP_"+str(result.get("category","PROXY_ERROR"))[:48]}
    fields=result.get("fields",{})
    if not isinstance(fields,dict):
        return {"ok":False,"error":"SETUP_FIELDS_INVALID"}
    if operation=="info":
        return {"ok":True,"operation":operation,"available":True,
                "tarball":fields.get("tarball") is True,
                "license":fields.get("license") is True,
                "installed":fields.get("installed") is True,
                "docker_socket":fields.get("docker_socket") is True}
    if operation=="status":
        state=fields.get("state")
        if state not in ("not_started","running","interrupted","failed","succeeded","corrupt"):
            return {"ok":False,"error":"SETUP_STATE_INVALID"}
        return {"ok":True,"operation":operation,"available":True,"install_state":state,
                "error_present":bool(fields.get("error"))}
    if operation=="inspect":
        sha=fields.get("sha256","")
        size=fields.get("bytes")
        if not isinstance(sha,str) or not re.fullmatch("[0-9a-f]{64}",sha) or type(size)!=int or size<=0:
            return {"ok":False,"error":"SETUP_MEDIA_RESULT_INVALID"}
        return {"ok":True,"operation":operation,"available":True,
                "archive_sha256":sha,"archive_bytes":size,
                "license":fields.get("license") is True}
    return {"ok":False,"error":"SETUP_UNEXPECTED_OPERATION"}
