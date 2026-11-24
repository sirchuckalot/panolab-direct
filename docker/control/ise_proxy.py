#!/usr/bin/env python3
"""Scoped ISE worker MCP calls and a read-only diagnostic through the broker.

No host shell, caller-supplied host paths, vendor license disclosure, Docker
network mutation or arbitrary Docker action. The worker bearer is read only
inside its own container. The worker's vendor-license Ethernet identity is
provided by a pre-existing, verified Docker-internal network.
"""
import json
import re
import subprocess

WORKER="panolab-direct-ise14-worker-1"
LICENSE_NETWORK="panolab-direct-ise14-license-internal"
TOOLS={"toolchain_info", "build_start", "build_status", "build_result", "build_cancel", "diagnose"}
NAME=re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
JOB=re.compile(r"^[0-9]{10,25}$")
ARTIFACTS={"xst.log","ngdbuild.log","map.log","par.log","trce.log","bitgen.log","design.bit","design.twr"}
# Python 2.6-compatible: the worker container uses the CentOS 6 runtime.
# Never print bearer, worker environment, raw user input, or raw errors.
RPC_CLIENT=r'''
import json,sys,urllib2
try:
 name=sys.argv[1]
 arguments=json.loads(sys.argv[2])
 token=open("/run/secrets/ise-worker-token","rb").read().strip()
 if not token.startswith(b"Bearer "): token=b"Bearer "+token
 if not isinstance(token,str): token=token.decode("ascii")
 payload=json.dumps({"jsonrpc":"2.0","id":1,"method":"tools/call",
                     "params":{"name":name,"arguments":arguments}})
 req=urllib2.Request("http://127.0.0.1:8765/mcp",data=payload,
    headers={"Authorization":token,"Content-Type":"application/json",
             "Accept":"application/json, text/event-stream",
             "MCP-Protocol-Version":"2025-06-18"})
 res=json.load(urllib2.urlopen(req,timeout=20))
 if res.get("error") or res.get("result",{}).get("isError"):
  details=[]
  error=res.get("error",{})
  if isinstance(error,dict): details.append(str(error.get("message","")))
  result=res.get("result",{})
  if isinstance(result,dict):
   for item in result.get("content",[]):
    if isinstance(item,dict) and item.get("type")=="text":
     details.append(str(item.get("text","")))
  msg=" ".join(details).lower()
  categories=(("permission denied","FILE_PERMISSION"),("operation not permitted","CAPABILITY_DENIED"),
   ("read-only file system","READ_ONLY_PATH"),("no such file or directory","MISSING_FILE"),
   ("missing project manifest","MISSING_MANIFEST"),("project path must be a real directory","PROJECT_DIR"),
   ("invalid project","INVALID_PROJECT"),("invalid top, part or source count","INVALID_MANIFEST"),
   ("invalid verilog source filename","INVALID_SOURCE"),("project file must be regular","INVALID_SOURCE"),
   ("worker busy","BUSY"),("unsupported build profile","BAD_PROFILE"),
   ("license unavailable","LICENSE_UNAVAILABLE"),("license path unset","LICENSE_UNAVAILABLE"),
   ("failed to persist job","PERSIST_FAILED"),("invalid arguments","BAD_ARGS"),
   ("unmarshal","BAD_ARGS"),("unknown tool","UNSUPPORTED_TOOL"),
   ("mkdir","MKDIR_FAILED"),("open ","FILE_OPEN_FAILED"))
  category="WORKER_REJECTED"
  for marker,code in categories:
   if marker in msg: category=code;break
  print(json.dumps({"ok":False,"category":category}))
  sys.exit(4)
 result=res.get("result",{})
 data=result.get("structuredContent")
 if data is None:
  text=result.get("content",[])
  if len(text)!=1 or text[0].get("type")!="text":
   print(json.dumps({"ok":False,"category":"MALFORMED_RESPONSE"}));sys.exit(4)
  data=json.loads(text[0]["text"])
 if not isinstance(data,dict):
  print(json.dumps({"ok":False,"category":"MALFORMED_RESPONSE"}));sys.exit(4)
 print(json.dumps({"ok":True,"data":data},sort_keys=True))
except urllib2.HTTPError as e:
 print(json.dumps({"ok":False,"category":"HTTP_"+str(e.code)}))
 sys.exit(4)
except Exception as e:
 print(json.dumps({"ok":False,"category":type(e).__name__.upper()}))
 sys.exit(4)
'''

# Read-only health signals for troubleshooting a rejected build_start. No
# license contents, tokens, path strings or vendor logs are returned.
WORKER_PROBE=r'''
import os,json,stat
def regular(p):
 try: return stat.S_ISREG(os.stat(p).st_mode)
 except OSError: return False
def directory(p):
 try: return stat.S_ISDIR(os.stat(p).st_mode)
 except OSError: return False
fields={
 "project_directory":directory("/projects/panolab_ise_smoke"),
 "project_manifest_readable":os.access("/projects/panolab_ise_smoke/build.json",os.R_OK) and regular("/projects/panolab_ise_smoke/build.json"),
 "project_verilog_readable":os.access("/projects/panolab_ise_smoke/design.v",os.R_OK) and regular("/projects/panolab_ise_smoke/design.v"),
 "project_constraints_readable":os.access("/projects/panolab_ise_smoke/design.ucf",os.R_OK) and regular("/projects/panolab_ise_smoke/design.ucf"),
 "results_directory":directory("/results/jobs"),
 "results_writable":os.access("/results/jobs",os.W_OK),
 "ise_settings_readable":os.access("/opt/Xilinx/14.7/ISE_DS/settings64.sh",os.R_OK),
 "license_file_readable":os.access("/licenses/Xilinx.lic",os.R_OK)
}
print(json.dumps(fields,sort_keys=True))
'''

def fail(category):
    return {"ok":False,"error":str(category)[:80]}

def validate_tool(request):
    name=request.get("tool")
    if name not in TOOLS:
        raise ValueError("ISE_TOOL_OUTSIDE_ALLOWLIST")
    args=request.get("arguments",{})
    if not isinstance(args,dict):
        raise ValueError("INVALID_ARGUMENT_SHAPE")
    if name in ("toolchain_info","diagnose"):
        if args:
            raise ValueError("UNEXPECTED_INFO_ARGS")
        return name,{}
    if name=="build_start":
        profile=args.get("Profile",args.get("profile"))
        project=args.get("Project",args.get("project"))
        if set(args)-{"Profile","Project","profile","project"} or profile!="ise14-implementation" or not isinstance(project,str) or not NAME.fullmatch(project):
            raise ValueError("INVALID_BUILD_REQUEST")
        return name,{"profile":profile,"project":project}
    jobid=args.get("ID",args.get("job_id"))
    if not isinstance(jobid,str) or not JOB.fullmatch(jobid):
        raise ValueError("INVALID_JOB_ID")
    if name in ("build_status","build_cancel"):
        if set(args)-{"ID","job_id"}:
            raise ValueError("UNEXPECTED_JOB_ARGS")
        return name,{"job_id":jobid}
    if name=="build_result":
        if set(args)-{"ID","job_id","Artifact","artifact","Offset","offset"}:
            raise ValueError("UNEXPECTED_RESULT_ARGS")
        artifact=args.get("Artifact",args.get("artifact",""))
        offset=args.get("Offset",args.get("offset",0))
        if not isinstance(artifact,str) or (artifact and artifact not in ARTIFACTS) or type(offset)!=int or not 0<=offset<=1024*1024*64:
            raise ValueError("INVALID_RESULT_ARGUMENTS")
        return name,{"job_id":jobid,"artifact":artifact,"offset":offset}
    raise ValueError("UNKNOWN_TOOL")

def validate_worker(command):
    show=command(["docker","inspect","--format",
                  '{{.Name}}|{{.State.Running}}|{{index .Config.Labels "panolab.managed"}}|{{.HostConfig.NetworkMode}}|{{.HostConfig.Privileged}}|{{.HostConfig.ReadonlyRootfs}}|{{.Config.User}}',WORKER],15)
    if not show.get("ok"):
        raise ValueError("ISE_WORKER_UNAVAILABLE")
    fields=show.get("stdout","").strip().split("|")
    if (len(fields)!=7 or fields[0]!="/"+WORKER or
            fields[1:3]!=["true","true"] or
            fields[4:]!=["false","true","0:0"] or
            fields[3] not in ("none",LICENSE_NETWORK)):
        raise ValueError("ISE_WORKER_SECURITY_CONTRACT_FAILED")
    if fields[3]==LICENSE_NETWORK:
        # The licensed vendor tool requires an Ethernet hostid; use a
        # named Docker-INTERNAL network, never host/LAN/Internet access.
        net=command(["docker","network","inspect","--format",
                     '{{.Internal}}|{{index .Labels "panolab.managed"}}',
                     LICENSE_NETWORK],15)
        if not net.get("ok") or net.get("stdout","").strip()!="true|true":
            raise ValueError("ISE_LICENSE_NETWORK_NOT_INTERNAL")
        attached=command(["docker","inspect","--format",
                          "{{json .NetworkSettings.Networks}}",WORKER],15)
        if not attached.get("ok"):
            raise ValueError("ISE_WORKER_NETWORK_INSPECT_FAILED")
        try:
            active=json.loads(attached["stdout"])
        except (ValueError,TypeError):
            raise ValueError("ISE_WORKER_NETWORK_INSPECT_INVALID")
        nic=active.get(LICENSE_NETWORK) if isinstance(active,dict) else None
        if (not isinstance(active,dict) or set(active)!={LICENSE_NETWORK} or
                not isinstance(nic,dict) or
                not isinstance(nic.get("MacAddress"),str) or
                len(nic["MacAddress"].split(":"))!=6):
            raise ValueError("ISE_WORKER_NETWORK_IDENTITY_FAILED")
    mounts=command(["docker","inspect","--format","{{json .Mounts}}",WORKER],15)
    if not mounts.get("ok"):
        raise ValueError("ISE_WORKER_MOUNTS_UNAVAILABLE")
    try:
        allmounts=json.loads(mounts["stdout"])
    except (ValueError,TypeError,KeyError):
        raise ValueError("ISE_WORKER_MOUNTS_INVALID")
    binds={m.get("Destination"):(m.get("RW"),m.get("Type"))
           for m in allmounts if m.get("Type")=="bind"}
    needed={"/opt/Xilinx":(False,"bind"),"/licenses/Xilinx.lic":(False,"bind"),
            "/projects":(False,"bind"),"/results":(True,"bind"),
            "/run/secrets/ise-worker-token":(False,"bind")}
    extras={(m.get("Type"),m.get("Destination")) for m in allmounts
            if m.get("Type")!="bind"}
    if binds!=needed or not extras<={("tmpfs","/tmp"),("tmpfs","/home/ise")}:
        raise ValueError("ISE_WORKER_MOUNT_POLICY_FAILED")
    security=command(["docker","inspect","--format",
                      "{{json .HostConfig.CapDrop}}|{{json .HostConfig.SecurityOpt}}",WORKER],15)
    if not security.get("ok"):
        raise ValueError("ISE_WORKER_SECURITY_OPTIONS_MISSING")
    try:
        cap,options=security["stdout"].strip().split("|",1)
        cap=json.loads(cap)
        options=json.loads(options)
    except (ValueError,TypeError,KeyError):
        raise ValueError("ISE_WORKER_SECURITY_OPTIONS_INVALID")
    if (not isinstance(cap,list) or
            "all" not in [str(x).lower() for x in cap] or
            not isinstance(options,list) or
            not any(x in ("no-new-privileges:true","no-new-privileges") for x in options)):
        raise ValueError("ISE_WORKER_SECURITY_OPTIONS_FAILED")

def filtered_result(name,data):
    if not isinstance(data,dict):
        return fail("INVALID_WORKER_RESULT")
    if name=="toolchain_info":
        return {"ok":True,"tool":name,"vendor":str(data.get("vendor",""))[:40],
                "version":str(data.get("toolchain_version",""))[:80],
                "ise_available":data.get("ise_available") is True,
                "license_available":data.get("license_available") is True,
                "license_validated":data.get("license_validated") is True,
                "programming_supported":data.get("programming_supported") is True}
    if name=="build_start":
        job=data.get("job_id","")
        if not isinstance(job,str) or not JOB.fullmatch(job):
            return fail("INVALID_NEW_JOB_ID")
        return {"ok":True,"tool":name,"job_id":job,"state":str(data.get("state",""))[:24]}
    if name in ("build_status","build_cancel"):
        return {"ok":True,"tool":name,"job_id":str(data.get("job_id",""))[:32],
                "state":str(data.get("state",""))[:24],"exit_code":data.get("exit_code",-1)}
    # Return only bounded metadata; never return raw vendor logs or bitstream content.
    artifacts=[]
    for a in data.get("artifacts",[]):
        if isinstance(a,dict) and a.get("name") in ARTIFACTS and len(artifacts)<8:
            artifacts.append({"name":a["name"],"bytes":a.get("bytes",0),
                              "sha256":str(a.get("sha256",""))[:64]})
    return {"ok":True,"tool":name,"job_id":str(data.get("job_id",""))[:32],
            "state":str(data.get("state",""))[:24],
            "exit_code":data.get("exit_code",-1),"artifacts":artifacts,
            "logs_truncated":bool(data.get("logs_truncated",False)),
            "log_categories":categorized_logs(str(data.get("log_tail","")))}

def categorized_logs(s):
    # Intentionally no raw vendor log content, path or license text.
    lower=s.lower()
    categories=[]
    for word,category in (
        ("error:","ERROR"),("warning:","WARNING"),("license","LICENSE_MENTION"),
        ("permission denied","FILE_PERMISSION"),("not found","FILE_NOT_FOUND"),
        ("constraint","CONSTRAINT"),("timing","TIMING"),
        ("placed","PLACEMENT"),("route","ROUTING")):
        if word in lower:
            categories.append(category)
    return categories

def call_worker(request,command):
    try:
        name,args=validate_tool(request)
        validate_worker(command)
        if name=="diagnose":
            check=command(["docker","exec","--user","0:0",WORKER,"python","-c",WORKER_PROBE],20)
            try:
                signals=json.loads((check.get("stdout") or "").strip())
            except (ValueError,TypeError):
                return fail("ISE_WORKER_DIAGNOSTIC_UNAVAILABLE")
            approved={"project_directory","project_manifest_readable","project_verilog_readable",
                      "project_constraints_readable","results_directory","results_writable",
                      "ise_settings_readable","license_file_readable"}
            if set(signals)!=approved or any(type(x)!=bool for x in signals.values()):
                return fail("ISE_WORKER_DIAGNOSTIC_INVALID")
            return dict({"ok":True,"tool":"diagnose"},**signals)
        # Nothing crosses from the worker's private token file to the broker.
        docker=["docker","exec","--user","0:0",WORKER,"python","-c",
                RPC_CLIENT,name,json.dumps(args,sort_keys=True)]
        run=command(docker,45)
        raw=(run.get("stdout") or "").strip()
        if len(raw)>24000:
            return fail("ISE_RPC_RESPONSE_TOO_LARGE")
        try:
            reply=json.loads(raw)
        except (ValueError,TypeError):
            return fail("ISE_RPC_UNREADABLE")
        if not isinstance(reply,dict) or not reply.get("ok"):
            return fail(str(reply.get("category","ISE_RPC_ERROR")) if isinstance(reply,dict) else "ISE_RPC_ERROR")
        return filtered_result(name,reply.get("data"))
    except ValueError as exc:
        return fail(str(exc))
    except Exception:
        return fail("ISE_PROXY_INTERNAL_ERROR")
