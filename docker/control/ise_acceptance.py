#!/usr/bin/env python3
"""PanoLab ISE 14.7 disposable acceptance, via the ordinary rootless broker.

This module is invoked through authenticated manager -> broker RPC
("@ise-e2e start/status/result"). It never calls the temporary maintenance
service, does not mount the Docker socket into child containers, and never
modifies the persistent setup/ISE worker or their vendor installation.

Owner-authorized ISE 14.7 System Edition EULA acceptance is tied to the
specific archive SHA-256 and acceptance policy in docker/ise14. The vendor's
batchxsetup command receives its supported unattended answers. Different
media/terms fail closed; this is NOT general license-term acceptance.
"""
import hashlib
import importlib
import json
import os
import re
import secrets
import subprocess
import sys
import time
from pathlib import Path

ROOT = os.environ["PANOLAB_REPO_HOST"]
RUN_ROOT = Path("/rpc/ise-e2e")
SETUP_ORIGINAL = "panolab-direct-connect-setup-1"
WORKER_ORIGINAL = "panolab-direct-ise14-worker-1"
SETUP_IMAGE = "panolab-direct-ise14-setup:checkpoint-20261124"
WORKER_IMAGE = "panolab-direct-ise14-worker:checkpoint-20261124"
HELPER_IMAGE = "python:3.12-alpine"
ARCHIVE_SHA = "cee0b046c1bbcfafcae59a96c7596c55c5477628c39bafefff8992cb8d33adaa"
ARCHIVE_SIZE = 6538618880
ACCEPTANCE_CONFIRMATION = "INSTALL_ISE_14_7_IN_PANOLAB_ONLY"
PROJECT = "panolab_ise_acceptance"
RUN_ID = re.compile(r"^[0-9a-f]{12}$")
RUN_PHASES = ("queued", "running", "passed", "failed", "cleanup_failed")
MANDATORY = ("xst.log", "ngdbuild.log", "map.log", "par.log",
             "trce.log", "bitgen.log", "design.bit", "design.twr")

class AcceptanceError(RuntimeError):
    pass

def docker(args, timeout=120):
    if not isinstance(args, list) or not args or args[0] != "docker":
        raise AcceptanceError("INVALID_DOCKER_INVOCATION")
    try:
        p = subprocess.run(args, text=True, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise AcceptanceError("DOCKER_COMMAND_TIMEOUT")
    if p.returncode:
        # No raw logs or secret-bearing paths are ever reported through MCP.
        raise AcceptanceError("DOCKER_" + re.sub("[^A-Za-z0-9]", "_", args[1].upper())[:24] + "_FAILED")
    if len(p.stdout) > 100000:
        raise AcceptanceError("DOCKER_RESPONSE_TOO_LARGE")
    return p.stdout.strip()

def try_inspect(kind, name):
    p = subprocess.run(["docker", kind, "inspect", name],
                       text=True, capture_output=True, timeout=30)
    if p.returncode:
        return None
    data = json.loads(p.stdout)
    if len(data) != 1:
        raise AcceptanceError("UNEXPECTED_INSPECT_COUNT")
    return data[0]

def resources(run_id):
    if not RUN_ID.fullmatch(run_id):
        raise AcceptanceError("INVALID_RUN_ID")
    base = "panolab-ise-e2e-" + run_id
    return {
        "setup": base+"-setup",
        "worker": base+"-worker",
        "network": base+"-net",
        "install": base+"-install",
        "work": base+"-work",
        "projects": base+"-projects",
        "results": base+"-results",
        "secrets": base+"-secrets",
    }

def state_path(run_id):
    resources(run_id)
    return RUN_ROOT / (run_id+".json")

def load_state(run_id):
    p=state_path(run_id)
    if not p.is_file() or p.is_symlink():
        return None
    data=json.loads(p.read_text())
    if data.get("id")!=run_id:
        raise AcceptanceError("CORRUPT_RUN_RECORD")
    return data

def save_state(data):
    RUN_ROOT.mkdir(mode=0o700, parents=True,exist_ok=True)
    data["updated_at"]=int(time.time())
    p=state_path(data["id"])
    tmp=p.with_name(p.name+"."+secrets.token_hex(4)+".tmp")
    with open(tmp,"x") as fp:
        os.chmod(tmp,0o600)
        json.dump(data,fp,sort_keys=True)
        fp.flush()
        os.fsync(fp.fileno())
    os.replace(tmp,p)

def phase(data,label):
    data["phase"]=label
    save_state(data)

def image_id(tag):
    return docker(["docker","image","inspect","--format","{{.Id}}",tag],25)

def preflight():
    info=docker(["docker","info","--format","{{json .SecurityOptions}}"],25)
    if '"name=rootless"' not in info:
        raise AcceptanceError("ROOTLESS_ENGINE_REQUIRED")
    if len(str(ROOT))<10 or not os.path.isabs(ROOT):
        raise AcceptanceError("UNEXPECTED_CHECKOUT")
    setup=try_inspect("container",SETUP_ORIGINAL)
    worker=try_inspect("container",WORKER_ORIGINAL)
    if not setup or not worker:
        raise AcceptanceError("BASELINE_MISSING")
    if setup["Config"]["Labels"].get("com.docker.compose.project")!="panolab-direct-connect":
        raise AcceptanceError("BASELINE_SETUP_IDENTITY_CHANGED")
    if setup["State"]["Running"] or setup["HostConfig"]["RestartPolicy"]["Name"]!="no":
        raise AcceptanceError("SETUP_MUST_BE_STOPPED_ON_DEMAND")
    if (not worker["State"]["Running"] or
        worker["Config"]["Labels"].get("panolab.managed")!="true" or
        not worker["HostConfig"]["ReadonlyRootfs"] or
        worker["HostConfig"]["Privileged"]):
        raise AcceptanceError("BASELINE_WORKER_SECURITY_CHANGED")
    if image_id(SETUP_IMAGE)!=setup["Image"] or image_id(WORKER_IMAGE)!=worker["Image"]:
        raise AcceptanceError("CHECKPOINT_IMAGE_MISMATCH")
    mounts={}
    for m in setup["Mounts"]:
        if m.get("Type")=="bind":
            mounts[m["Destination"]]=(m["Source"],not m["RW"])
    expected={
        "/media/ise.tar":True,
        "/licenses/Xilinx.lic":True,
        "/run/secrets/mcp-bearer":True,
        "/config/ise-system-edition.batch":True,
    }
    if any(k not in mounts or mounts[k][1]!=v for k,v in expected.items()):
        raise AcceptanceError("SETUP_PRIVATE_MOUNTS_CHANGED")
    if mounts["/licenses/Xilinx.lic"][0] != ROOT+"/docker/private/Xilinx.lic":
        raise AcceptanceError("LICENSE_SOURCE_CHANGED")
    if mounts["/run/secrets/mcp-bearer"][0] != ROOT+"/docker/private/mcp-bearer":
        raise AcceptanceError("BEARER_SOURCE_CHANGED")
    if mounts["/config/ise-system-edition.batch"][0] != ROOT+"/docker/ise14/ise-system-edition.batch":
        raise AcceptanceError("INSTALLER_BATCH_CONFIG_CHANGED")
    # Broker handles known private paths; requests supply NO host path.
    return {k:mounts[k][0] for k in expected}

def labels(run_id):
    return ["--label","panolab.managed=true",
            "--label","panolab.ise.acceptance="+run_id]

def docker_helper(run_id,script,extra=None,timeout=45):
    args=["docker","run","--rm","--network","none","--read-only",
          "--cap-drop","ALL","--security-opt","no-new-privileges:true",
          "--user","0:0"] + labels(run_id)
    args+=(extra or [])
    args+=["--entrypoint","python3",HELPER_IMAGE,"-c",script]
    return docker(args,timeout)

POLICY_PROBE=r'''
import json
d=json.load(open("/input/policy"))
print(json.dumps({"sha":d.get("archive_sha256"),
 "bytes":d.get("archive_bytes"),
 "approved":d.get("unattended_terms_acceptance") is True,
 "product":d.get("product"),
 "schema":d.get("schema"),
 "scope":bool(d.get("approval_scope"))}))
'''
IDENTITY_PROBE=r'''
import re
s=open("/private/license","rb").read().decode("utf-8","replace")
ids=set(x.lower() for x in re.findall(r"\bHOSTID\s*=\s*([0-9A-Fa-f]{12})",s,re.I))
if len(ids)!=1:raise ValueError("LICENSE_HOSTID_FORM_INVALID")
a=next(iter(ids))
print(":".join(a[i:i+2] for i in range(0,12,2)))
'''
STAGE_PROBE=r'''
import json,os,hashlib,stat
from pathlib import Path
src=Path("/fixture")
target=Path("/projects/panolab_ise_acceptance")
target.mkdir(mode=0o700)
mapping={"acceptance_build.json":"build.json",
         "acceptance_design.v":"design.v"}
items={}
for old,new in mapping.items():
 p=src/old
 if p.is_symlink() or not p.is_file() or p.stat().st_size>16384:
  raise ValueError("INVALID_ACCEPTANCE_FIXTURE")
 data=p.read_bytes()
 with open(target/new,"xb") as f:f.write(data)
 items[new]=hashlib.sha256(data).hexdigest()
spec=json.loads((target/"build.json").read_text())
if spec!={"top":"panolab_ise_acceptance","part":"xc6slx150-fgg484-2",
          "verilog":["design.v"],"ucf":""}:
 raise ValueError("UNEXPECTED_SMOKE_PROJECT")
print(json.dumps({"fixture_sha256":items},sort_keys=True))
'''
SECRET_PROBE=r'''
import secrets,os
fd=os.open("/secrets/token",os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,"w") as f:f.write(secrets.token_urlsafe(40)+"\n")
print("WORKER_TOKEN_CREATED")
'''
MCP_PROBE=r'''
import sys,json,urllib2
name=sys.argv[1]
args=json.loads(sys.argv[2])
secret=sys.argv[3]
port=int(sys.argv[4])
token=open(secret,"rb").read().strip()
if not token.startswith(b"Bearer "):token=b"Bearer "+token
payload=json.dumps({"jsonrpc":"2.0","id":1,"method":"tools/call",
 "params":{"name":name,"arguments":args}})
req=urllib2.Request("http://127.0.0.1:"+str(port)+"/mcp",
 data=payload,
 headers={"Authorization":token,"Content-Type":"application/json",
          "Accept":"application/json, text/event-stream",
          "MCP-Protocol-Version":"2025-06-18"})
try:
 response=json.load(urllib2.urlopen(req,timeout=120))
 if response.get("error") or response.get("result",{}).get("isError"):
  print(json.dumps({"ok":False,"category":"MCP_REJECTED"}))
 else:
  result=response.get("result") or {}
  data=result.get("structuredContent")
  if data is None:
   items=result.get("content") or []
   if len(items)==1 and items[0].get("type")=="text":
    data=json.loads(items[0]["text"])
  if not isinstance(data,dict):data={}
  print(json.dumps({"ok":True,"fields":data},sort_keys=True))
except urllib2.HTTPError as e:
 print(json.dumps({"ok":False,"category":"HTTP_"+str(e.code)}))
except Exception as e:
 print(json.dumps({"ok":False,"category":type(e).__name__.upper()}))
'''

def rpc(container,name,arguments,setup=False):
    path="/run/secrets/mcp-bearer" if setup else "/run/secrets/ise-worker-token"
    port="8766" if setup else "8765"
    value=docker(["docker","exec","--user","0:0",container,
                  "python","-c",MCP_PROBE,name,json.dumps(arguments),path,port],145)
    try:
        obj=json.loads(value)
    except (TypeError,ValueError):
        raise AcceptanceError("VENDOR_MCP_RESPONSE_INVALID")
    if not obj.get("ok") or not isinstance(obj.get("fields"),dict):
        raise AcceptanceError("VENDOR_MCP_"+str(obj.get("category","UNAVAILABLE"))[:40])
    return obj["fields"]

def retry_rpc(container,name,arguments,setup=False):
    for attempt in range(20):
        try:
            return rpc(container,name,arguments,setup=setup)
        except AcceptanceError:
            if attempt>=19:raise
            time.sleep(2)
    raise AcceptanceError("MCP_TIMEOUT")

def create_volumes(r):
    for key in ("install","work","projects","results","secrets"):
        name=r[key]
        if try_inspect("volume",name):
            raise AcceptanceError("ACCEPTANCE_VOLUME_ALREADY_EXISTS")
        docker(["docker","volume","create"]+labels(r["id"])+[name],30)

def start_setup(r,inputs):
    args=["docker","run","-d","--name",r["setup"],"--network","none",
          "--restart","no","--read-only","--cap-drop","ALL",
          "--security-opt","no-new-privileges:true",
          "--user","0:0","--memory","12g","--cpus","6",
          "--pids-limit","1024","--tmpfs","/tmp:rw,nosuid,nodev,size=1024m"]
    args+=labels(r["id"])
    for source,target in (("/media/ise.tar","/media/ise.tar"),
                          ("/licenses/Xilinx.lic","/licenses/Xilinx.lic"),
                          ("/run/secrets/mcp-bearer","/run/secrets/mcp-bearer"),
                          ("/config/ise-system-edition.batch","/config/ise-system-edition.batch")):
        args+=["--mount","type=bind,src="+inputs[source]+",dst="+target+",readonly"]
    for key,target in (("install","/opt/Xilinx"),("work","/work")):
        args+=["--mount","type=volume,src="+r[key]+",dst="+target]
    args+=[SETUP_IMAGE]
    docker(args,90)

def pre_install_policy(r,inputs):
    text=docker_helper(r["id"],POLICY_PROBE,
      ["--mount","type=bind,src="+ROOT+"/docker/ise14/acceptance-policy.json,dst=/input/policy,readonly"],35)
    policy=json.loads(text)
    if policy!={"sha":ARCHIVE_SHA,"bytes":ARCHIVE_SIZE,
               "approved":True,"product":"Xilinx ISE Design Suite 14.7 System Edition",
               "schema":1,"scope":True}:
        raise AcceptanceError("VENDOR_MEDIA_TERMS_NOT_AUTHORIZED")
    return policy

def stage_project(r):
    text=docker_helper(r["id"],STAGE_PROBE,
      ["--mount","type=bind,src="+ROOT+"/docker/ise14,dst=/fixture,readonly",
       "--mount","type=volume,src="+r["projects"]+",dst=/projects"],35)
    outcome=json.loads(text)
    files=outcome.get("fixture_sha256") or {}
    if set(files)!={"build.json","design.v"} or any(not re.fullmatch("[0-9a-f]{64}",x) for x in files.values()):
        raise AcceptanceError("FIXTURE_HASH_INVALID")
    r["fixture_sha256"]=files

def create_token(r):
    output=docker_helper(r["id"],SECRET_PROBE,
      ["--mount","type=volume,src="+r["secrets"]+",dst=/secrets"],35)
    if output!="WORKER_TOKEN_CREATED":
        raise AcceptanceError("WORKER_TOKEN_NOT_CREATED")

def mac_for_license(r,inputs):
    mac=docker_helper(r["id"],IDENTITY_PROBE,
        ["--mount","type=bind,src="+inputs["/licenses/Xilinx.lic"]+
         ",dst=/private/license,readonly"],35)
    if not re.fullmatch(r"(?:[0-9a-f]{2}:){5}[0-9a-f]{2}",mac):
        raise AcceptanceError("INVALID_LICENSE_ETHERNET_IDENTITY")
    return mac

def start_worker(r,inputs,mac):
    if try_inspect("network",r["network"]):
        raise AcceptanceError("NETWORK_NAME_ALREADY_EXISTS")
    docker(["docker","network","create","--internal"]+labels(r["id"])+[r["network"]],40)
    net=try_inspect("network",r["network"])
    if not net or not net.get("Internal"):
        raise AcceptanceError("NONINTERNAL_ACCEPTANCE_NETWORK")
    args=["docker","run","-d","--name",r["worker"],"--restart","no",
          "--network",r["network"],"--mac-address",mac,
          "--read-only","--cap-drop","ALL",
          "--security-opt","no-new-privileges:true",
          "--user","0:0","--memory","8g","--cpus","4",
          "--pids-limit","512",
          "--tmpfs","/tmp:rw,nosuid,nodev,size=1024m",
          "--tmpfs","/home/ise:rw,nosuid,nodev,size=64m"]
    args+=labels(r["id"])
    args+=["--mount","type=volume,src="+r["install"]+",dst=/opt/Xilinx,readonly",
           "--mount","type=volume,src="+r["projects"]+",dst=/projects,readonly",
           "--mount","type=volume,src="+r["results"]+",dst=/results",
           "--mount","type=volume,src="+r["secrets"]+",dst=/run/secrets,readonly",
           "--mount","type=bind,src="+inputs["/licenses/Xilinx.lic"]+
              ",dst=/licenses/Xilinx.lic,readonly",
           "--env","PANOLAB_MCP_TRANSPORT=http",
           "--entrypoint","/bin/bash",WORKER_IMAGE,
           "-c",'export PANOLAB_MCP_TOKEN="$(cat /run/secrets/token)"; exec /usr/local/bin/panolab-ise-entrypoint mcp']
    # Worker entrypoint expects /run/secrets/ise-worker-token, so its source
    # is a private token volume, not a bearer in the container environment.
    args[-1]='export PANOLAB_MCP_TOKEN="$(cat /run/secrets/token)"; exec /usr/local/bin/panolab-ise-entrypoint mcp'
    docker(args,90)
    current=try_inspect("container",r["worker"])
    if (not current or not current["State"]["Running"] or
        set(current["NetworkSettings"]["Networks"])!={r["network"]} or
        current["NetworkSettings"]["Networks"][r["network"]]["MacAddress"].lower()!=mac):
        raise AcceptanceError("ACCEPTANCE_WORKER_IDENTITY_FAILED")

def worker_rpc(r,name,arguments):
    # The only token generated is at /run/secrets/token in the volume.
    path="/run/secrets/token"
    raw=docker(["docker","exec","--user","0:0",r["worker"],"python",
       "-c",MCP_PROBE,name,json.dumps(arguments),path,"8765"],145)
    obj=json.loads(raw)
    if not obj.get("ok") or not isinstance(obj.get("fields"),dict):
        raise AcceptanceError("WORKER_MCP_"+str(obj.get("category","UNAVAILABLE"))[:45])
    return obj["fields"]

def wait_worker(r,name,args):
    for i in range(25):
        try:return worker_rpc(r,name,args)
        except AcceptanceError:
            if i>=24:raise
            time.sleep(2)

def run_install(r,inputs,state):
    phase(state,"setup_started")
    start_setup(r,inputs)
    info=retry_rpc(r["setup"],"lab_status",{},setup=True)
    if info.get("installed") or not info.get("license") or not info.get("tarball"):
        raise AcceptanceError("FRESH_INSTALL_NOT_EMPTY_OR_INPUTS_MISSING")
    cur=rpc(r["setup"],"ise_install_status",{},setup=True)
    if cur.get("state")!="not_started":
        raise AcceptanceError("FRESH_INSTALL_STATE_NOT_CLEAN")
    phase(state,"media_validation")
    media=rpc(r["setup"],"ise_media_inspect",{},setup=True)
    if media.get("sha256")!=ARCHIVE_SHA or media.get("bytes")!=ARCHIVE_SIZE:
        raise AcceptanceError("APPROVED_ARCHIVE_CHECKSUM_MISMATCH")
    state["archive_verified"]=True
    phase(state,"installing")
    started=rpc(r["setup"],"ise_install_start",
      {"SHA256":ARCHIVE_SHA,"Confirmation":ACCEPTANCE_CONFIRMATION},setup=True)
    if started.get("state")!="running":
        raise AcceptanceError("VENDOR_INSTALL_DID_NOT_START")
    deadline=time.monotonic()+7100
    while time.monotonic()<deadline:
        time.sleep(15)
        progress=rpc(r["setup"],"ise_install_status",{},setup=True)
        code=progress.get("state")
        if code=="succeeded":
            info=rpc(r["setup"],"lab_status",{},setup=True)
            if info.get("installed") is not True:
                raise AcceptanceError("INSTALL_STATE_SUCCESS_WITHOUT_XILINX")
            state["install_verified"]=True
            phase(state,"installed")
            return
        if code in ("failed","interrupted","corrupt"):
            raise AcceptanceError("VENDOR_INSTALL_"+str(code).upper())
    raise AcceptanceError("VENDOR_INSTALL_TIMEOUT")

def run_build(r,inputs,state):
    phase(state,"worker_start")
    stage_project(r)
    state["fixture_sha256"]=r["fixture_sha256"]
    create_token(r)
    mac=mac_for_license(r,inputs)
    start_worker(r,inputs,mac)
    info=wait_worker(r,"toolchain_info",{})
    if (not info.get("ise_available") or
        not info.get("license_available") or info.get("programming_supported")):
        raise AcceptanceError("VENDOR_WORKER_PREFLIGHT_FAILED")
    phase(state,"building")
    started=worker_rpc(r,"build_start",{"profile":"ise14-implementation","project":PROJECT})
    job_id=started.get("job_id")
    if not isinstance(job_id,str) or not re.fullmatch("[0-9]{10,25}",job_id):
        raise AcceptanceError("VENDOR_JOB_ID_INVALID")
    state["vendor_job_id"]=job_id
    save_state(state)
    deadline=time.monotonic()+1200
    while time.monotonic()<deadline:
        time.sleep(8)
        result=worker_rpc(r,"build_status",{"job_id":job_id})
        if result.get("state")=="succeeded" and result.get("exit_code")==0:
            break
        if result.get("state") in ("failed","cancelled","interrupted"):
            raise AcceptanceError("VENDOR_BUILD_"+str(result.get("state")).upper())
    else:
        raise AcceptanceError("VENDOR_BUILD_TIMEOUT")
    final=worker_rpc(r,"build_result",{"job_id":job_id})
    if final.get("state")!="succeeded" or final.get("exit_code")!=0:
        raise AcceptanceError("VENDOR_BUILD_NOT_SUCCEEDED")
    found={f.get("name"):f for f in final.get("artifacts",[]) if isinstance(f,dict)}
    if any(name not in found or type(found[name].get("bytes"))!=int
           or found[name]["bytes"]<=0 or
           not isinstance(found[name].get("sha256"),str) or
           not re.fullmatch("[0-9a-f]{64}",found[name]["sha256"])
           for name in MANDATORY):
        raise AcceptanceError("VENDOR_BUILD_ARTIFACT_VALIDATION_FAILED")
    state["bitstream_bytes"]=found["design.bit"]["bytes"]
    state["bitstream_sha256"]=found["design.bit"]["sha256"]
    state["artifact_sha256"]={name:found[name]["sha256"] for name in MANDATORY}
    state["build_verified"]=True
    phase(state,"verified")

def identity_ok(kind,name,run_id):
    obj=try_inspect(kind,name)
    if not obj:return False
    lab=obj.get("Labels") if kind in ("volume","network") else obj.get("Config",{}).get("Labels")
    if not isinstance(lab,dict) or lab.get("panolab.ise.acceptance")!=run_id or lab.get("panolab.managed")!="true":
        raise AcceptanceError("CLEANUP_RESOURCE_IDENTITY_CHANGED")
    return True

def cleanup(r):
    # No broad prunes, no caller-selected names/volumes, no access to
    # persistent ISE resources. Strict exact resource names and labels.
    for key in ("worker","setup"):
        if identity_ok("container",r[key],r["id"]):
            docker(["docker","rm","-f",r[key]],70)
    if identity_ok("network",r["network"],r["id"]):
        docker(["docker","network","rm",r["network"]],40)
    for key in ("secrets","results","projects","work","install"):
        if identity_ok("volume",r[key],r["id"]):
            docker(["docker","volume","rm",r[key]],75)
    for key in ("setup","worker"):
        if try_inspect("container",r[key]):
            raise AcceptanceError("DISPOSAL_CONTAINER_REMAINS")
    if try_inspect("network",r["network"]):
        raise AcceptanceError("DISPOSAL_NETWORK_REMAINS")
    if any(try_inspect("volume",r[key]) for key in ("secrets","results","projects","work","install")):
        raise AcceptanceError("DISPOSAL_VOLUME_REMAINS")

def run(run_id):
    r=resources(run_id)
    r["id"]=run_id
    state=load_state(run_id)
    if not state or state.get("status")!="queued":
        raise AcceptanceError("ACCEPTANCE_RUN_RECORD_INVALID")
    state["status"]="running"
    try:
        phase(state,"preflight")
        inputs=preflight()
        pre_install_policy(r,inputs)
        # A second preflight prevents accidental collision with an
        # unrelated Docker workload sharing a seemingly free name.
        for key in ("setup","worker"):
            if try_inspect("container",r[key]):
                raise AcceptanceError("ACCEPTANCE_NAME_COLLISION")
        for key in ("install","work","projects","results","secrets"):
            if try_inspect("volume",r[key]):
                raise AcceptanceError("ACCEPTANCE_VOLUME_COLLISION")
        if try_inspect("network",r["network"]):
            raise AcceptanceError("ACCEPTANCE_NETWORK_COLLISION")
        phase(state,"creating_disposable_volumes")
        create_volumes(r)
        run_install(r,inputs,state)
        run_build(r,inputs,state)
        state["status"]="passed"
    except Exception as err:
        state["status"]="failed"
        state["error_category"]=type(err).__name__+":"+(
            str(err)[:80] if isinstance(err,AcceptanceError) else "INTERNAL_ERROR")
    finally:
        # The run may need separate remote inspection if cleanup fails.
        state["phase"]="disposing"
        save_state(state)
        try:
            cleanup(r)
            state["disposed"]=True
        except Exception as exc:
            state["disposed"]=False
            state["cleanup_error"]=type(exc).__name__
            state["status"]="cleanup_failed"
        state["phase"]="finished"
        save_state(state)

def interface(operation,run_id=None):
    if operation=="preflight":
        try:
            preflight()
            return {"ok":True,"ready":True,"path":"normal_manager_broker"}
        except Exception as exc:
            return {"ok":False,"ready":False,"category":str(exc)[:64] if isinstance(exc,AcceptanceError) else type(exc).__name__}
    if operation=="start":
        RUN_ROOT.mkdir(mode=0o700,parents=True,exist_ok=True)
        for p in RUN_ROOT.glob("*.json"):
            try:
                status=json.loads(p.read_text()).get("status")
            except Exception:
                return {"ok":False,"error":"PREVIOUS_RUN_CORRUPT"}
            if status in ("queued","running"):
                return {"ok":False,"error":"ACCEPTANCE_RUN_ALREADY_RUNNING"}
        run_id=secrets.token_hex(6)
        data={"id":run_id,"status":"queued","phase":"queued","disposed":False,
              "mode":"owner_authorized_disposable_ise14"}
        save_state(data)
        # This process executes inside the NORMAL rootless Docker broker.
        # It does not require or invoke the trusted maintenance sidecar.
        with open(RUN_ROOT/(run_id+".log"),"ab") as stream:
            subprocess.Popen(["python3",str(Path(__file__).resolve()),"run",run_id],
                stdin=subprocess.DEVNULL,stdout=stream,stderr=stream,
                start_new_session=True,close_fds=True)
        return {"ok":True,"id":run_id,"status":"queued"}
    if operation in ("status","result"):
        if not isinstance(run_id,str) or not RUN_ID.fullmatch(run_id):
            return {"ok":False,"error":"INVALID_RUN_ID"}
        data=load_state(run_id)
        if data is None:return {"ok":False,"error":"UNKNOWN_RUN"}
        result={"ok":True,"id":run_id,"status":data.get("status"),"phase":data.get("phase"),
                "disposed":data.get("disposed") is True}
        if operation=="result" and data.get("status") in ("passed","failed","cleanup_failed"):
            for name in ("archive_verified","install_verified","build_verified",
                         "vendor_job_id","bitstream_bytes","bitstream_sha256",
                         "fixture_sha256","artifact_sha256","error_category","cleanup_error"):
                if name in data:result[name]=data[name]
        return result
    return {"ok":False,"error":"UNSUPPORTED_ACCEPTANCE_OPERATION"}

if __name__=="__main__":
    if len(sys.argv)==3 and sys.argv[1]=="run" and RUN_ID.fullmatch(sys.argv[2]):
        run(sys.argv[2])
    else:
        raise SystemExit("Internal acceptance controller only; use authenticated PanoLab RPC")
