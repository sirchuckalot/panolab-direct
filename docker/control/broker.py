#!/usr/bin/env python3
"""Restricted Docker broker: only this service gets the user rootless socket.

The MCP manager communicates through private RPC, not via direct Docker access.
"""
import json, os, socket, subprocess, threading
S="/rpc/panolab.sock"
W=os.environ["PANOLAB_WORKSPACE_HOST"]
REPO=os.environ["PANOLAB_REPO_HOST"]
CODEX_AUTH=os.environ["PANOLAB_CODEX_AUTH_HOST"]
# Rootless namespace UID 0 maps to the ordinary host owner, enabling
# existing private 0700 mounts without changing host permissions.
# Enforce rootless Engine identity before honoring this owner-mapped mode.
ROOTLESS_MODE=os.environ.get("PANOLAB_ROOTLESS_MODE") == "1"
CONTAINER_DEV_USER="0:0" if ROOTLESS_MODE else "1000:1000"
# Restricted dev-container reconfiguration uses project-scoped temporary
# names and restores the prior dev container if the replacement fails.
STAGE="panolab-direct-dev-stage"
BACKUP="panolab-direct-dev-backup"
SOURCE_MOUNTS=(("projects","ro"),("boards","ro"),("shared","ro"),
               ("third_party","ro"),("agent","rw"),("specs","ro"),
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

def launch_dev(name,image):
    cmd=["docker","run","-d","--name",name,"--label","panolab.managed=true",
         "--user",CONTAINER_DEV_USER,"--workdir","/workspace","--cap-drop","ALL",
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
    if not out["ok"]: return False
    mounts=json.loads(out["stdout"])
    active={m.get("Destination"):(m.get("Source"),not m.get("RW")) for m in mounts if m.get("Type")=="bind"}
    return all(active.get("/repo/"+name)==(os.path.join(REPO,name),mode=="ro") for name,mode in SOURCE_MOUNTS)

def migrate_dev(image):
    image_allowed(image)
    old=command(["docker","inspect","--format","{{index .Config.Labels \"panolab.managed\"}}",DEV],15)
    if not old["ok"] or old["stdout"].strip()!="true":
        raise ValueError("existing dev container not PanoLab-managed")
    if repo_configured(DEV):
        return {"ok":True,"already_configured":True}
    if command(["docker","inspect",STAGE],15)["ok"] or command(["docker","inspect",BACKUP],15)["ok"]:
        raise ValueError("staged or backup container already exists; inspect before migration")
    prepared=launch_dev(STAGE,image)
    if not prepared["ok"]: return prepared
    probe=command(["docker","exec","--user",CONTAINER_DEV_USER,STAGE,
                   "/bin/sh","-c","test -d /repo/projects && test -d /repo/boards && test -d /repo/shared && test -d /repo/third_party && test ! -e /repo/docker/private"],30)
    command(["docker","rm","-f",STAGE],30)
    if not probe["ok"]:
        return {"ok":False,"error":"staged container cannot see approved source mounts"}
    stop=command(["docker","stop",DEV],45)
    if not stop["ok"]: return stop
    rename=command(["docker","rename",DEV,BACKUP],20)
    if not rename["ok"]:
        command(["docker","start",DEV],30)
        return rename
    deployed=launch_dev(DEV,image)
    if not deployed["ok"]:
        command(["docker","rm","-f",DEV],20)
        command(["docker","rename",BACKUP,DEV],20)
        command(["docker","start",DEV],30)
        return {"ok":False,"error":"new container failed; original container restored","detail":deployed}
    verified=command(["docker","exec","--user",CONTAINER_DEV_USER,DEV,
                      "/bin/sh","-c","test -d /repo/projects && test -d /repo/shared && test -d /repo/third_party && test -d /workspace"],30)
    if not verified["ok"]:
        command(["docker","rm","-f",DEV],30)
        command(["docker","rename",BACKUP,DEV],20)
        command(["docker","start",DEV],30)
        return {"ok":False,"error":"post-creation probe failed; original restored"}
    command(["docker","rm","-f",BACKUP],30)
    return {"ok":True,"migrated":True,"source_tree":"/repo","private_mounted":False}

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
        image=image_allowed(r.get("image","panolab-direct-modern:local"))
        return migrate_dev(image)
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
