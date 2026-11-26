#!/usr/bin/env python3
"""Restricted Docker broker: only this service gets the user rootless socket.

The MCP manager communicates through private RPC, not via direct Docker access.
"""
import json, os, socket, subprocess, threading, importlib
import ise_proxy
import ise_staging
import ise_setup
import ise_acceptance
S="/rpc/panolab.sock"
W=os.environ["PANOLAB_WORKSPACE_HOST"]
REPO=os.environ["PANOLAB_REPO_HOST"]
CODEX_AUTH=os.environ["PANOLAB_CODEX_AUTH_HOST"]
# Rootless namespace UID 0 maps to the ordinary host owner, enabling
# existing private 0700 mounts without changing host permissions.
# Enforce rootless Engine identity before honoring this owner-mapped mode.
ROOTLESS_MODE=os.environ.get("PANOLAB_ROOTLESS_MODE") == "1"
TRUSTED_MAINTENANCE=ROOTLESS_MODE and os.environ.get("PANOLAB_TRUSTED_MAINTENANCE") == "1"
MAINTENANCE="panolab-direct-trusted-maintenance"
CONTAINER_DEV_USER="0:0" if ROOTLESS_MODE else "1000:1000"
# Restricted dev-container reconfiguration uses project-scoped temporary
# names and restores the prior dev container if the replacement fails.
STAGE="panolab-direct-dev-stage"
BACKUP="panolab-direct-dev-backup"
SOURCE_MOUNTS=(("projects","ro"),("boards","ro"),("shared","ro"),
               ("third_party","ro"),("research","ro"),("agent","rw"),("specs","ro"),
               ("tests","ro"),("docs","ro"),("host","ro"),("docker/modern","ro"))
DEV="panolab-direct-dev-1"
NAMES=(DEV,"panolab-direct-connect-setup-1","panolab-direct-connect-tunnel-1")
IMAGES=("panolab-direct-modern:local","python:3.12-slim","ubuntu:24.04")
lock=threading.Lock()

def command(args,timeout=120):
    try:
        p=subprocess.run(args,text=True,capture_output=True,timeout=timeout)
        return dict(ok=p.returncode==0,exit_code=p.returncode,stdout=p.stdout[-24000:],stderr=p.stderr[-12000:])
    except subprocess.TimeoutExpired:
        return dict(ok=False,error="timeout")
    except Exception as e:
        return dict(ok=False,error=type(e).__name__)

def checked(name):
    if name not in NAMES:
        raise ValueError("container outside PanoLab allowlist")
    if not command(["docker","inspect",name],15)["ok"]:
        raise ValueError("container not present")
    return name

def image_allowed(image):
    if image not in IMAGES:
        raise ValueError("image outside approved catalog")
    return image

def launch_dev(name,image,restart="unless-stopped"):
    cmd=["docker","run","-d","--name",name,"--label","panolab.managed=true",
         "--restart",restart,"--user",CONTAINER_DEV_USER,"--workdir","/workspace","--cap-drop","ALL",
         "--security-opt","no-new-privileges:true","--memory","4g","--cpus","2",
         "--pids-limit","256","--tmpfs","/tmp:rw,nosuid,nodev,size=256m",
         "--tmpfs","/home:rw,nosuid,nodev,size=64m",
         "--mount","type=bind,src="+W+",dst=/workspace",
         "--mount","type=bind,src="+CODEX_AUTH+",dst=/codex-auth",
         "--env","CODEX_HOME=/codex-auth"]
    for relative,mode in SOURCE_MOUNTS:
        source=os.path.join(REPO,relative)
        target="/repo/"+relative
        cmd+=["--mount","type=bind,src="+source+",dst="+target+(",readonly" if mode=="ro" else "")]
    return command(cmd+[image,"sleep","infinity"],120)

def repo_configured(name):
    out=command(["docker","inspect","--format","{{json .Mounts}}",name],15)
    if not out["ok"]:
        raise ValueError("could not inspect dev mounts")
    mounts=json.loads(out["stdout"])
    expected={"/workspace":(W,False),"/codex-auth":(CODEX_AUTH,False)}
    expected.update({"/repo/"+relative:(os.path.join(REPO,relative),mode=="ro")
                     for relative,mode in SOURCE_MOUNTS})
    mounts=[m for m in mounts if not (m["Type"]=="tmpfs" and m["Destination"] in ("/tmp","/home"))]
    active={m["Destination"]:(m["Source"],not m["RW"]) for m in mounts if m["Type"]=="bind"}
    return len(active)==len(mounts) and active==expected

def verify_dev_sources(name):
    if not repo_configured(name):
        return False
    probe=" && ".join(
        ["test -d /repo/"+relative for relative,_ in SOURCE_MOUNTS]
        + ["test -d /workspace", "test ! -e /repo/docker/private",
           "test ! -e /repo/docker/.env", "test ! -e /repo/.git"])
    return command(["docker","exec","--user",CONTAINER_DEV_USER,name,
                    "/bin/sh","-c",probe],30)["ok"]

def migrate_dev(image=None):
    old=command(["docker","inspect","--format",
                 '{{index .Config.Labels "panolab.managed"}}|{{.State.Running}}|'
                 '{{json .HostConfig.RestartPolicy}}|{{.Image}}',DEV],15)
    if not old["ok"]:
        raise ValueError("existing dev container not PanoLab-managed")
    managed,running,policy,old_image=old["stdout"].strip().split("|")
    if managed!="true":
        raise ValueError("existing dev container not PanoLab-managed")
    if repo_configured(DEV):
        return {"ok":True,"already_configured":True}
    restart_policy=json.loads(policy)
    restart=restart_policy["Name"] or "no"
    if restart=="on-failure" and restart_policy["MaximumRetryCount"]:
        restart+=":"+str(restart_policy["MaximumRetryCount"])
    target_image=image
    if target_image is None:
        approved=command(["docker","image","inspect","--format","{{.Id}}",IMAGES[0]],15)
        if not approved["ok"] or approved["stdout"].strip()!=old_image:
            raise ValueError("current dev image differs from the approved modern image; select an approved image explicitly")
        target_image=old_image
    if command(["docker","inspect",STAGE],15)["ok"] or command(["docker","inspect",BACKUP],15)["ok"]:
        raise ValueError("staged or backup container already exists; inspect before migration")
    prepared=launch_dev(STAGE,target_image,"no")
    if not prepared["ok"]: return prepared
    try:
        staged=verify_dev_sources(STAGE)
    finally:
        removed=command(["docker","rm","-f",STAGE],30)
    if not removed["ok"]: return removed
    if not staged:
        return {"ok":False,"error":"staged container cannot see approved source mounts"}
    if running=="true":
        stop=command(["docker","stop",DEV],45)
        if not stop["ok"]: return stop
    rename=command(["docker","rename",DEV,BACKUP],20)
    if not rename["ok"]:
        if running=="true":
            command(["docker","start",DEV],30)
        return rename
    deployed=launch_dev(DEV,target_image,restart)
    error=None
    try:
        if not deployed["ok"]:
            error="new container failed"
        elif not verify_dev_sources(DEV):
            error="post-creation source probe failed"
        elif running!="true" and not command(["docker","stop",DEV],45)["ok"]:
            error="could not restore stopped state"
        elif restart=="always" and not command(["docker","update","--restart","no",BACKUP],30)["ok"]:
            error="could not disable automatic restart on the stopped rollback"
    except (ValueError, KeyError, TypeError):
        error="post-creation mount inspection failed"
    if error:
        command(["docker","rm","-f",DEV],30)
        restored=command(["docker","rename",BACKUP,DEV],20)["ok"]
        if restored and running=="true":
            restored=command(["docker","start",DEV],30)["ok"]
        return {"ok":False,"error":error,"original_restored":restored}
    return {"ok":True,"migrated":True,"source_tree":"/repo","private_mounted":False,"rollback":BACKUP}

def maintenance_identity(command_fn):
    # This is explicitly owner-trusted and temporary. The sidecar has the
    # ordinary user's rootless Docker socket, never host-root Docker.
    inspect=command_fn(["docker","inspect","--format",
       '{{.Name}}|{{.State.Running}}|{{index .Config.Labels "com.docker.compose.project"}}|{{.HostConfig.NetworkMode}}|{{.HostConfig.Privileged}}',
       MAINTENANCE],15)
    if not inspect.get("ok") or inspect.get("stdout","").strip()!=(
        "/"+MAINTENANCE+"|true|panolab-direct-connect|none|false"):
        raise ValueError("trusted maintenance service unavailable or misconfigured")

def dispatch(r):
    a=r.get("action")
    if a=="status":
        return command(["docker","ps","-a","--filter","name=panolab-direct","--format","{{.Names}} {{.Status}}"],20)
    if a=="build":
        return command(["docker","build","-t","panolab-direct-modern:local","/source/modern"],1200)
    if a=="pull":
        image=r.get("image")
        if image not in IMAGES[1:]:
            raise ValueError("image outside approved catalog")
        return command(["docker","pull",image],600)
    if a=="create":
        image=image_allowed(r.get("image","panolab-direct-modern:local"))
        if command(["docker","inspect",DEV],15)["ok"]:
            raise ValueError("development instance already exists; use dev_attach_checkout")
        return launch_dev(DEV,image)
    if a=="attach_checkout":
        return migrate_dev(image_allowed(r["image"]) if "image" in r else None)
    if a=="lifecycle":
        op=r.get("operation")
        if op not in ("start","stop","restart"):
            raise ValueError("unsupported lifecycle action")
        name=checked(r.get("container"))
        if name==NAMES[2] and op=="stop":
            raise ValueError("refusing to stop the only remote tunnel; use restart instead")
        return command(["docker",op,name],90)
    if a=="logs":
        return command(["docker","logs","--tail","100",checked(r.get("container"))],30)
    if a=="ise_e2e":
        # Authenticated manager -> broker -> disposable vendor setup/worker.
        # No trusted-maintenance route or source of Docker authority is used.
        if TRUSTED_MAINTENANCE:
            importlib.reload(ise_acceptance)
        return ise_acceptance.interface(r.get("operation"),r.get("id"))
    if a=="exec" and isinstance(r.get("argv"),list) and r["argv"][:1]==["@ise-e2e"]:
        if TRUSTED_MAINTENANCE:
            importlib.reload(ise_acceptance)
        argv=r["argv"]
        if len(argv)==2 and argv[1] in ("start","preflight"):
            return ise_acceptance.interface(argv[1])
        if len(argv)==3 and argv[1] in ("status","result"):
            return ise_acceptance.interface(argv[1],argv[2])
        raise ValueError("invalid disposable ISE acceptance operation")
    if a=="ise_setup":
        # Setup is on-demand and not part of routine vendor compilation.
        # This path uses the ordinary manager's authenticated setup proxy;
        # no temporary maintenance service, installer action or Docker shell.
        return ise_setup.call_setup(r,command)
    if a=="exec" and isinstance(r.get("argv"),list) and r["argv"][:1]==["@setup"]:
        argv=r["argv"]
        if len(argv)!=2:
            raise ValueError("invalid setup inspection request")
        if TRUSTED_MAINTENANCE:
            importlib.reload(ise_setup)
        return ise_setup.call_setup({"operation":argv[1]},command)
    if a=="ise_rpc":
        # Remote iteration: import the currently mounted Python modules for
        # each authenticated call. Broker core policy remains startup-loaded.
        if TRUSTED_MAINTENANCE:
            importlib.reload(ise_proxy)
        return ise_proxy.call_worker(r,command)
    if a=="ise_stage":
        # Editable staging adapter; immutable input snapshots still enforced.
        if TRUSTED_MAINTENANCE:
            importlib.reload(ise_proxy)
            importlib.reload(ise_staging)
        return ise_staging.stage_project(r.get("project"),command,W,REPO)
    if a=="exec" and isinstance(r.get("argv"),list) and r["argv"][:1]==["@maintenance"]:
        if not TRUSTED_MAINTENANCE:
            raise ValueError("temporary trusted remote maintenance is disabled")
        argv=r["argv"][1:]
        if (not 1<=len(argv)<=32 or
            any(not isinstance(x,str) or not x or len(x)>8192 or "\x00" in x for x in argv)):
            raise ValueError("invalid trusted maintenance command")
        maintenance_identity(command)
        # Intentionally broad access ONLY inside the explicitly opted-in,
        # offline, rootless trusted maintenance sidecar. Never host root.
        return command(["docker","exec","--user","0:0",MAINTENANCE]+argv,170)
    if a=="exec" and isinstance(r.get("argv"),list) and r["argv"][:1]==["@ise14"]:
        # Live source-mounted Python protocol fixes must be visible on every
        # request; no management image rebuild or process restart required.
        if TRUSTED_MAINTENANCE:
            importlib.reload(ise_proxy)
            importlib.reload(ise_staging)
        # Compatibility shim for the existing remote dev_exec connector schema.
        # Only approved ISE tools and project staging are accepted here.
        argv=r["argv"]
        if not 2<=len(argv)<=4:
            raise ValueError("invalid ISE compatibility action")
        tool=argv[1]
        arguments={}
        if tool=="stage" and len(argv)==3:
            return ise_staging.stage_project(argv[2],command,W,REPO)
        if tool=="build_start" and len(argv)==3:
            arguments={"Profile":"ise14-implementation","Project":argv[2]}
        elif tool in ("build_status","build_cancel","build_result") and len(argv)==3:
            arguments={"ID":argv[2]}
        elif tool=="build_result" and len(argv)==4:
            arguments={"ID":argv[2],"Artifact":argv[3]}
        elif tool in ("toolchain_info","diagnose") and len(argv)==2:
            arguments={}
        else:
            raise ValueError("ISE compatibility call has invalid arguments")
        return ise_proxy.call_worker({"tool":tool,"arguments":arguments},command)
    if a=="exec":
        checked(DEV)
        argv=r.get("argv")
        if not isinstance(argv,list) or not 1<=len(argv)<=20 or any(not isinstance(x,str) or len(x)>4096 or not x or "\x00" in x for x in argv):
            raise ValueError("invalid command arguments")
        user=r.get("user","dev")
        if user not in ("dev","root"):
            raise ValueError("unsupported dev user")
        return command(["docker","exec","--user","0:0" if user=="root" else CONTAINER_DEV_USER,DEV]+argv,180)
    raise ValueError("unknown action")

def handle(conn):
    with conn:
        try:
            conn.settimeout(185)
            raw=b""
            while not raw.endswith(b"\n"):
                b=conn.recv(4096)
                if not b: return
                raw+=b
                if len(raw)>65536: raise ValueError("request too large")
            with lock:
                answer=dispatch(json.loads(raw))
        except Exception as e:
            answer={"ok":False,"error":str(e)[:250]}
        conn.sendall((json.dumps(answer)+"\n").encode())

if ROOTLESS_MODE:
    engine=command(["docker","info","--format","{{json .SecurityOptions}}"],20)
    if not engine.get("ok") or '"name=rootless"' not in engine.get("stdout",""):
        raise SystemExit("PANOLAB_ROOTLESS_MODE requires a verified rootless Docker daemon")
os.makedirs("/rpc",exist_ok=True)
if os.path.exists(S): os.unlink(S)
sock=socket.socket(socket.AF_UNIX)
sock.bind(S)
os.chmod(S,0o666)
sock.listen(8)
while True:
    conn,_=sock.accept()
    threading.Thread(target=handle,args=(conn,),daemon=True).start()
