#!/usr/bin/env python3
"""Guarded owner-user ISE 14.7 installation and rootless Spartan-6 smoke test.

Run ONLY from the ordinary laptop user's canonical PanoLab checkout.
No sudo, rootful Docker, host packages, JTAG, flash writes, or token disclosure.
Installs through the already approved isolated PanoLab setup MCP service.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from storage_paths import provisioned_roots
import re
import secrets
import shutil
import stat
import subprocess
import sys
import tarfile
import time

ROOT = Path(__file__).resolve().parents[1]
PROJECT = "panolab-direct-external"
SETUP = "panolab-direct-connect-setup-1"
WORKER = "panolab-direct-ise14-worker-1"
WORKER_IMAGE = "panolab-direct-ise14-worker:local"
ISE_LICENSE_NETWORK = "panolab-direct-ise14-license-internal"
CONFIRM = "INSTALL_ISE_14_7_IN_PANOLAB_ONLY"
SMOKE_NAME = "panolab_ise_smoke"
SMOKE_PART = "xc6slx150-fgg484-2"
RPC_CLIENT = r'''
from __future__ import print_function
import json,sys,urllib2
port,token_path,name,arguments=sys.argv[1:]
try:
    authorization=open(token_path,"rb").read().strip()
    if not authorization.startswith(b"Bearer "):
        authorization=b"Bearer "+authorization
    authorization=authorization.decode("ascii")
    payload=json.dumps({
        "jsonrpc":"2.0","id":1,"method":"tools/call",
        "params":{"name":name,"arguments":json.loads(arguments)}
    })
    headers={"Authorization":authorization,"Content-Type":"application/json",
             "Accept":"application/json, text/event-stream",
             "MCP-Protocol-Version":"2025-06-18"}
    req=urllib2.Request("http://127.0.0.1:"+port+"/mcp",data=payload,headers=headers)
    response=urllib2.urlopen(req,timeout=900)
    value=json.loads(response.read())
    if value.get("error") or value.get("result",{}).get("isError"):
        # Report only a known failure CATEGORY. Never print raw remote messages:
        # they may include protected paths, license details or customer data.
        details=[]
        remote_error=value.get("error")
        if isinstance(remote_error,dict):
            details.append(str(remote_error.get("message","")))
        result_error=value.get("result",{})
        for item in result_error.get("content",[]) if isinstance(result_error,dict) else []:
            if isinstance(item,dict) and item.get("type")=="text":
                details.append(str(item.get("text","")))
        combined=" ".join(details).lower()
        categories=(
            ("permission denied","PERMISSION_DENIED"),
            ("operation not permitted","CAPABILITY_DENIED"),
            ("read-only file system","READ_ONLY_OUTPUT"),
            ("missing project manifest","PROJECT_MANIFEST_MISSING"),
            ("project path must be a real directory","PROJECT_DIRECTORY_INVALID"),
            ("project file must be regular","PROJECT_SOURCE_INVALID"),
            ("invalid top, part or source count","INVALID_PROJECT_MANIFEST"),
            ("no such file or directory","PATH_MISSING"),
            ("worker busy","WORKER_BUSY"),
            ("invalid arguments","INVALID_TOOL_ARGUMENTS"),
            ("unmarshal","ARGUMENT_DECODING"),
            ("unknown tool","UNKNOWN_TOOL"),
        )
        category=next((name for marker,name in categories if marker in combined),"MCP_REQUEST_REJECTED")
        print(json.dumps({"client_error":"MCP_TOOL_ERROR","category":category}))
        sys.exit(4)
    result=value["result"]
    structured=result.get("structuredContent")
    if structured is None:
        content=result.get("content") or []
        if not content or content[0].get("type")!="text":
            raise ValueError("No structured MCP tool response")
        structured=json.loads(content[0]["text"])
    print(json.dumps(structured,sort_keys=True))
except urllib2.HTTPError as e:
    # Numeric status is safe; the HTTP body can contain private information.
    print(json.dumps({"client_error":"HTTP_ERROR","status":int(e.code)}))
    sys.exit(4)
except Exception as e:
    # Do not accidentally expose authentication, installation logs or license text.
    print(json.dumps({"client_error":type(e).__name__}))
    sys.exit(4)
'''

def output(*args: str, timeout: int = 60, input_text: str | None = None, check: bool = True) -> str:
    p=subprocess.run(args, input=input_text, text=True, stdout=subprocess.PIPE,
                     stderr=subprocess.PIPE, timeout=timeout)
    if check and p.returncode:
        msg=p.stderr.strip()[-300:] if p.stderr else "subprocess returned nonzero"
        raise RuntimeError(f"Command failed: {args[0]} (exit {p.returncode}): {msg}")
    return p.stdout.strip()

def d(*args: str, timeout: int = 90, input_text: str | None = None, check: bool = True) -> str:
    return output("docker","-H",f"unix://{DOCKER_SOCK}",*args,timeout=timeout,input_text=input_text,check=check)

def read_rpc(container: str,port: int,secret: str,name: str,args: dict | None = None) -> dict:
    raw=d("exec","-i","--user","0:0",container,"python","-",str(port),secret,
          name,json.dumps(args or {},sort_keys=True),input_text=RPC_CLIENT,
          timeout=950,check=False)
    try:
        result=json.loads(raw)
    except (ValueError,TypeError):
        raise RuntimeError(f"{container} MCP call {name} failed (NO_VALID_RESPONSE)")
    if result.get("client_error"):
        category=result.get("category",result.get("client_error","UNKNOWN"))
        status=result.get("status")
        if status is not None:
            category="HTTP_STATUS_"+str(status)
        raise RuntimeError(f"{container} MCP call {name} rejected ({category})")
    if not isinstance(result,dict):
        raise RuntimeError(f"Unexpected {name} MCP response")
    return result

def check_docker_state(strict_source=True):
    if os.geteuid()==0:
        raise RuntimeError("Do not use sudo or the host root account")
    if sys.platform!="linux":
        raise RuntimeError("This installation is for the Linux laptop")
    if not (ROOT/".git").is_dir():
        raise RuntimeError("Run from the existing PanoLab Git checkout")
    branch=output("git","-C",str(ROOT),"symbolic-ref","--short","HEAD")
    if branch!="development":
        raise RuntimeError("Expected the PanoLab development checkout")
    if strict_source:
        # Installer mutations require an exact, committed source tree, but
        # should not be tied to the one-time pre-acceptance commit SHA.
        # Routine inspect/smoke-only modes remain usable while developing.
        porcelain=subprocess.run(
            ["git","-C",str(ROOT),"status","--porcelain","--untracked-files=normal"],
            text=True,capture_output=True
        )
        if porcelain.returncode:
            raise RuntimeError("Unable to inspect checkout changes")
        if porcelain.stdout.strip():
            raise RuntimeError("Installer requires a clean committed development checkout")
    docker_info=d("info","--format","{{json .SecurityOptions}}")
    if '"name=rootless"' not in docker_info:
        raise RuntimeError("Owner-user rootless Docker Engine required")
    inspected=json.loads(d("inspect",SETUP))
    setup=inspected[0]
    if not setup.get("State",{}).get("Running"):
        raise RuntimeError("Existing PanoLab ISE setup container is not running")
    labels=setup.get("Config",{}).get("Labels",{})
    if labels.get("com.docker.compose.project")!=PROJECT:
        raise RuntimeError("ISE setup container does not belong to PanoLab")
    print("PREFLIGHT: approved checkout, rootless Engine and isolated setup service PASS",flush=True)

def private_inputs() -> tuple[Path,Path,Path]:
    private,data=provisioned_roots(ROOT)
    lic=private/"Xilinx.lic"
    work=data/"ise-work"
    if private.is_symlink() or lic.is_symlink() or not lic.is_file() or not work.is_dir():
        raise RuntimeError("Expected protected ISE license/workspace absent")
    if stat.S_IMODE(lic.stat().st_mode) & 0o077:
        raise RuntimeError("Original Xilinx license must not be group/world-readable")
    archives=[]
    for pattern in ("*.tar","*.tar.gz","*.tgz","*.tar.bz2"):
        archives.extend(data.glob(pattern))
    if len(archives)!=1 or not archives[0].is_file() or archives[0].is_symlink():
        raise RuntimeError("Exactly one owner-supplied ISE archive required")
    return lic,work,archives[0]

def validate_media_archive(p:Path) -> None:
    """Mirror the setup server's fail-closed member policy before install state changes."""
    count=0
    total=0
    batch=0
    xsetup=0
    with tarfile.open(p,"r|*") as tar:
        for item in tar:
            count+=1
            total+=item.size
            if count>200000 or total>30<<30 or item.size>4<<30 or item.size<0:
                raise RuntimeError("Vendor archive exceeds setup service limits")
            n=item.name.replace("\\","/")
            canonical=os.path.normpath(n)
            if (not n or n.startswith("/") or canonical in (".","..")
                    or canonical.startswith("../") or "\\" in item.name):
                raise RuntimeError("Unsafe vendor archive path; installation refused")
            if not (item.isdir() or item.isfile()):
                raise RuntimeError("Vendor archive contains links/special files rejected by setup service")
            if canonical.endswith("/bin/lin64/batchxsetup") and item.isfile():
                batch+=1
            if canonical.endswith("/xsetup") and item.isfile():
                xsetup+=1
    if batch!=1 or xsetup<1:
        raise RuntimeError("Missing or ambiguous native Linux ISE batch installer in archive")
    print(f"MEDIA_ARCHIVE_VALIDATION=PASS members={count} uncompressed_bytes={total}",flush=True)

def inspect_install() -> dict:
    info=read_rpc(SETUP,8766,"/run/secrets/mcp-bearer","lab_status")
    state=read_rpc(SETUP,8766,"/run/secrets/mcp-bearer","ise_install_status")
    print("ISE_SETUP:",json.dumps({"archive_present":info.get("tarball"),
                                  "license_present":info.get("license"),
                                  "installed":info.get("installed"),
                                  "install_state":state.get("state")},sort_keys=True),flush=True)
    return {"info":info,"state":state}

def install_ise(license_path:Path,archive:Path):
    inspected=inspect_install()
    installed=bool(inspected["info"].get("installed"))
    state=inspected["state"].get("state")
    if installed and state in ("succeeded","not_started"):
        print("ISE_INSTALL=ALREADY_PRESENT (tool execution still to be verified)",flush=True)
        return
    if state!="not_started":
        raise RuntimeError("Existing ISE installation state is "+str(state)+"; no destructive retry")
    if not (inspected["info"].get("tarball") and inspected["info"].get("license")):
        raise RuntimeError("Setup service cannot access expected private input files")
    validate_media_archive(archive)
    inspected_archive=read_rpc(SETUP,8766,"/run/secrets/mcp-bearer","ise_media_inspect")
    sha=inspected_archive.get("sha256","")
    if not re.fullmatch(r"[0-9a-f]{64}",sha):
        raise RuntimeError("Setup returned invalid media SHA256")
    # This confirmation is intentionally interactive; the user must approve the vendor terms.
    print("\nThe native Xilinx batch installer will run only inside the isolated CentOS worker.")
    answer=input("If you reviewed and accept the Xilinx ISE vendor terms, type ACCEPT_ISE_EULA: ").strip()
    if answer!="ACCEPT_ISE_EULA":
        raise RuntimeError("Vendor terms not accepted; no installation started")
    started=read_rpc(SETUP,8766,"/run/secrets/mcp-bearer","ise_install_start",
                     {"SHA256":sha,"Confirmation":CONFIRM})
    if started.get("state") not in ("running","succeeded"):
        raise RuntimeError("Unexpected installer start response")
    print("ISE_INSTALL=STARTED (inside isolated CentOS setup service)",flush=True)
    deadline=time.monotonic()+7200
    while time.monotonic()<deadline:
        time.sleep(20)
        latest=read_rpc(SETUP,8766,"/run/secrets/mcp-bearer","ise_install_status")
        state=latest.get("state")
        if state=="succeeded":
            print("ISE_INSTALL=SUCCEEDED",flush=True)
            return
        if state in ("failed","interrupted","corrupt"):
            raise RuntimeError("Vendor installer reported "+str(state)+"; inspect private logs locally")
    raise RuntimeError("Vendor installation status not resolved within bounded timeout; inspect state")

def command_probe():
    # Fixed, read-only command check inside the isolated setup service.
    code=("set -e; test -r /opt/Xilinx/14.7/ISE_DS/settings64.sh; "
          ". /opt/Xilinx/14.7/ISE_DS/settings64.sh >/dev/null 2>&1; "
          "for t in xst ngdbuild map par trce bitgen; do "
          "command -v \"$t\" >/dev/null || exit 11; "
          "done; echo ISE_TOOL_BINARIES=PASS")
    print(d("exec",SETUP,"/bin/bash","-c",code,timeout=40),flush=True)

def mkdir_secure(p:Path,mode:int) -> None:
    if p.is_symlink():raise RuntimeError("Unsafe symlink in private worker workspace")
    p.mkdir(parents=True,exist_ok=True)
    p.chmod(mode)

def prepare_worker_inputs(private_license:Path,work:Path) -> tuple[Path,Path,Path,Path]:
    root=work/"worker"
    mkdir_secure(root,0o700)
    project_root=root/"projects"
    results=root/"results"
    runtime_licdir=root/"license"
    mkdir_secure(project_root,0o755)
    mkdir_secure(results,0o700)
    mkdir_secure(runtime_licdir,0o700)
    smoke=project_root/SMOKE_NAME
    mkdir_secure(smoke,0o755)
    fixture={
        "build.json":json.dumps({"top":SMOKE_NAME,"part":SMOKE_PART,
                                 "verilog":["design.v"],"ucf":"design.ucf"},indent=2)+"\n",
        "design.v":(
           "module panolab_ise_smoke(input wire clk125, input wire rst_n, output wire led);\n"
           "reg [23:0] counter;\n"
           "always @(posedge clk125 or negedge rst_n) begin\n"
           "  if (!rst_n) counter <= 24'd0;\n"
           "  else counter <= counter + 24'd1;\n"
           "end\n"
           "assign led = counter[23];\n"
           "endmodule\n"
        ),
        "design.ucf":(
            'NET "clk125" LOC = "Y13" | IOSTANDARD = LVCMOS33;\n'
            'NET "rst_n" LOC = "AB14" | IOSTANDARD = LVCMOS33;\n'
            'NET "led" LOC = "E12" | IOSTANDARD = LVCMOS33;\n'
            'NET "clk125" TNM_NET = "clock";\n'
            'TIMESPEC "TS_clock" = PERIOD "clock" 8 ns HIGH 50%;\n'
        )
    }
    for name,content in fixture.items():
        path=smoke/name
        if path.is_symlink():raise RuntimeError("Unsafe project-file symlink")
        if path.exists() and path.read_text()!=content:
            raise RuntimeError(f"Existing worker smoke fixture differs: {name}")
        path.write_text(content)
        path.chmod(0o644)
    licensed_copy=runtime_licdir/"Xilinx.lic"
    if licensed_copy.is_symlink():raise RuntimeError("Unsafe private license symlink")
    if licensed_copy.exists():
        if hashlib.sha256(licensed_copy.read_bytes()).digest()!=hashlib.sha256(private_license.read_bytes()).digest():
            raise RuntimeError("Existing worker license copy differs from protected original")
    else:
        # Private parent stays 0700; the bind-mounted copy alone is readable by
        # a non-root vendor process inside the worker.
        shutil.copyfile(private_license,licensed_copy)
    licensed_copy.chmod(0o644)
    token=root/"worker-token"
    if token.is_symlink():raise RuntimeError("Unsafe worker token")
    if not token.exists():
        token.write_text(secrets.token_urlsafe(40)+"\n")
    token.chmod(0o600)
    return project_root,results,licensed_copy,token

def build_worker_image():
    print("WORKER_IMAGE: building isolated ISE 14.7 runtime on rootless Docker",flush=True)
    d("buildx","build","--builder","default","--load","--target","final",
      "-t",WORKER_IMAGE,"-f",str(ROOT/"docker/ise14/Dockerfile"),
      str(ROOT/"docker/ise14"),timeout=1800)
    print("WORKER_IMAGE=BUILT",flush=True)

def verified_node_locked_interface(license_path:Path)->str:
    # Keep this MAC private; it is the authorized container's stable virtual
    # interface identity, not a host-NIC change or license file edit.
    text=license_path.read_text(errors="replace")
    ids=set(v.lower() for v in re.findall(r"\bHOSTID\s*=\s*([0-9A-Fa-f]{12})",text,re.I))
    if len(ids)!=1:
        raise RuntimeError("Expected one stable Ethernet node-locked host ID")
    uid=next(iter(ids))
    return ":".join(uid[i:i+2] for i in range(0,12,2))

def verify_ise_license_network():
    info=d("network","inspect","--format",
           '{{.Internal}}|{{index .Labels "panolab.managed"}}',ISE_LICENSE_NETWORK,
           check=False).strip()
    if info:
        if info!="true|true":
            raise RuntimeError("ISE licensing network is not internal and PanoLab managed")
        return
    d("network","create","--internal","--label",
      "panolab.managed=true",ISE_LICENSE_NETWORK)
    if d("network","inspect","--format",
         '{{.Internal}}|{{index .Labels "panolab.managed"}}',
         ISE_LICENSE_NETWORK).strip()!="true|true":
        raise RuntimeError("Could not verify isolated ISE licensing network")

def ensure_worker(projects:Path,results:Path,license_copy:Path,token:Path, *, image=WORKER_IMAGE, restart="unless-stopped", transaction=None):
    # Query exact container identity first. A missing Docker container can produce
    # [] (valid JSON), not merely an empty output; indexing [0] was unsafe.
    ids=d("ps","-a","--filter",f"name=^/{WORKER}$","--format","{{.ID}}").splitlines()
    if len(ids)>1:
        raise RuntimeError("Ambiguous ISE worker identity; refusing replacement")
    if ids:
        if transaction is not None:
            raise RuntimeError("Canonical worker name still occupied")
        inspected=json.loads(d("inspect",ids[0]))
        if len(inspected)!=1 or inspected[0].get("Name")!="/"+WORKER:
            raise RuntimeError("Unexpected ISE worker inspection response")
        c=inspected[0]
        if c["Config"]["Labels"].get("panolab.managed")!="true":
            raise RuntimeError("Unrecognized ISE worker container name occupied")
        mounts={m["Destination"]:(m["Source"],not m["RW"]) for m in c["Mounts"] if m["Type"]=="bind"}
        expected={
            "/opt/Xilinx":(str(provisioned_roots(ROOT)[1]/"Xilinx"),True),
            "/licenses/Xilinx.lic":(str(license_copy),True),
            "/results":(str(results),False),
            "/projects":(str(projects),True),
            "/run/secrets/ise-worker-token":(str(token),True)
        }
        if mounts!=expected or c["HostConfig"].get("NetworkMode")!=ISE_LICENSE_NETWORK:
            raise RuntimeError("Existing worker has unexpected security mounts/network")
        verify_ise_license_network()
        if not c["State"]["Running"]:
            d("start",WORKER)
        print("ISE_WORKER=REUSED",flush=True)
        return
    installed=provisioned_roots(ROOT)[1]/"Xilinx"
    if installed.is_symlink() or not installed.is_dir():
        raise RuntimeError("Private installed ISE volume missing")
    verify_ise_license_network()
    interface_mac=verified_node_locked_interface(license_copy)
    cmd=[
        *(["create", "--label", f"panolab.cutover={transaction}"]
          if transaction is not None else ["run", "-d"]),
        "--name",WORKER,"--restart",restart,
        "--label","panolab.managed=true",
        "--network",ISE_LICENSE_NETWORK,"--mac-address",interface_mac,
        "--read-only","--cap-drop","ALL",
        "--security-opt","no-new-privileges:true",
        "--user","0:0",
        "--memory","8g","--cpus","4","--pids-limit","512",
        "--tmpfs","/tmp:rw,nosuid,nodev,size=1024m",
        "--tmpfs","/home/ise:rw,nosuid,nodev,size=64m",
        "--mount",f"type=bind,src={installed},dst=/opt/Xilinx,readonly",
        "--mount",f"type=bind,src={license_copy},dst=/licenses/Xilinx.lic,readonly",
        "--mount",f"type=bind,src={projects},dst=/projects,readonly",
        "--mount",f"type=bind,src={results},dst=/results",
        "--mount",f"type=bind,src={token},dst=/run/secrets/ise-worker-token,readonly",
        "--env","PANOLAB_MCP_TRANSPORT=http",
        "--entrypoint","/bin/bash",image,
        "-c",'export PANOLAB_MCP_TOKEN="$(cat /run/secrets/ise-worker-token)"; exec /usr/local/bin/panolab-ise-entrypoint mcp'
    ]
    identity = d(*cmd,timeout=120)
    if transaction is None:
        print("ISE_WORKER=CREATED (rootless, internal-only licensed identity, restricted mounts)",flush=True)
    return identity

def smoke_build():
    # Worker TCP is deliberately not exposed to the laptop or network.
    # Run the client via docker exec into the same isolated container.
    def rpc(name,args=None):
        return read_rpc(WORKER,8765,"/run/secrets/ise-worker-token",name,args)
    for trial in range(12):
        try:
            info=rpc("toolchain_info")
            break
        except Exception:
            time.sleep(2)
    else:
        raise RuntimeError("Worker MCP did not become healthy; inspect private container logs")
    if not info.get("ise_available") or not info.get("license_available"):
        raise RuntimeError("ISE files or license inaccessible to non-root vendor worker")
    print("ISE_WORKER_INFO:",json.dumps({
        "vendor":info.get("vendor"),"version":info.get("toolchain_version"),
        "ise_available":info.get("ise_available"),"license_available":info.get("license_available"),
        "programming_supported":info.get("programming_supported")
    },sort_keys=True),flush=True)
    started=rpc("build_start",{"profile":"ise14-implementation","project":SMOKE_NAME})
    job=started.get("job_id","")
    if not re.fullmatch(r"[0-9]{10,25}",str(job)):
        raise RuntimeError("ISE worker did not return a valid job ID")
    print(f"ISE_SMOKE_JOB_ID={job}",flush=True)
    until=time.monotonic()+1300
    while time.monotonic()<until:
        time.sleep(8)
        st=rpc("build_status",{"job_id":str(job)})
        state=st.get("state")
        if state=="succeeded":break
        if state in ("failed","cancelled","interrupted"):
            result=rpc("build_result",{"job_id":str(job)})
            artifacts=[a.get("name") for a in result.get("artifacts",[])]
            print("FAILED_STAGE_ARTIFACTS:",artifacts,flush=True)
            # Last vendor diagnostics intentionally stay local to private results.
            raise RuntimeError("ISE real six-stage build did not complete; review private stage logs")
    else:
        raise RuntimeError("ISE smoke build still incomplete; inspect job state")
    result=rpc("build_result",{"job_id":str(job)})
    found={a["name"]:a for a in result.get("artifacts",[])}
    mandatory=("xst.log","ngdbuild.log","map.log","par.log","trce.log","bitgen.log","design.bit")
    for file in mandatory:
        if file not in found or found[file].get("bytes",0)<=0:
            raise RuntimeError("Vendor smoke result missing "+file)
    bit=found["design.bit"]
    if not re.fullmatch(r"[a-f0-9]{64}",bit["sha256"]):
        raise RuntimeError("Vendor bitstream SHA-256 missing")
    print("ISE_FULL_PIPELINE=PASS (XST NGDBuild MAP PAR TRACE BitGen)",flush=True)
    print(f"ISE_SMOKE_BITSTREAM={bit['bytes']} bytes SHA256={bit['sha256']}",flush=True)
    print(f"ISE_ARTIFACTS=private ISE worker results, job {job}",flush=True)
    print("NO_FPGA_PROGRAMMING=CONFIRMED",flush=True)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode",nargs="?",choices=["inspect","install-smoke","smoke-only","rebind-worker"],default="install-smoke")
    parser.add_argument("--expected-worker-image")
    parser.add_argument("--worker-restart", default="unless-stopped")
    args=parser.parse_args()
    global DOCKER_SOCK
    DOCKER_SOCK=Path(os.environ.get("XDG_RUNTIME_DIR",f"/run/user/{os.getuid()}"))/"docker.sock"
    if not DOCKER_SOCK.is_socket():
        raise RuntimeError("Expected the owner-user rootless Docker socket")
    if args.mode == "rebind-worker":
        image = args.expected_worker_image or ""
        if not re.fullmatch(r"sha256:[a-f0-9]{64}", image) or not re.fullmatch(
            r"(?:no|always|unless-stopped|on-failure(?::[1-9][0-9]*)?)", args.worker_restart
        ):
            raise RuntimeError("Expected exact worker image ID and valid restart policy")
        if os.getuid() == 0 or '"name=rootless"' not in d("info", "--format", "{{json .SecurityOptions}}"):
            raise RuntimeError("Owner-user rootless Docker required")
        if d("ps", "-aq", "--filter", f"name=^{WORKER}$").strip():
            raise RuntimeError("Canonical worker name still occupied")
        if d("image", "inspect", "--format", "{{.Id}}", WORKER_IMAGE).strip() != image:
            raise RuntimeError("Approved worker tag differs from preserved image ID")
        license_file, work, _ = private_inputs()
        worker = work / "worker"
        projects, results = worker / "projects", worker / "results"
        license_copy, token = worker / "license/Xilinx.lic", worker / "worker-token"
        paths = (projects, results, license_copy, token)
        if any(path.resolve() != path for path in paths) or not (
            projects.is_dir() and results.is_dir() and license_copy.is_file() and token.is_file()
        ):
            raise RuntimeError("Preserved worker inputs unavailable")
        if license_file.read_bytes() != license_copy.read_bytes():
            raise RuntimeError("Preserved worker license differs from owner license")
        ensure_worker(*paths, image=image, restart=args.worker_restart)
        return
    check_docker_state(strict_source=(args.mode=="install-smoke"))
    license_file,work,archive=private_inputs()
    if args.mode=="inspect":
        inspect_install()
        return
    if args.mode=="smoke-only":
        state=inspect_install()
        if not state["info"].get("installed") or state["state"].get("state")!="succeeded":
            raise RuntimeError("ISE setup not installed successfully; refusing build attempt")
        fixture=work/"worker/projects"/SMOKE_NAME
        if not all((fixture/name).is_file() for name in ("build.json","design.v","design.ucf")):
            raise RuntimeError("ISE worker smoke fixture is missing")
        result_dir=work/"worker/results"
        if not result_dir.is_dir() or not os.access(result_dir,os.W_OK):
            raise RuntimeError("ISE worker results directory is inaccessible to owner")
        jobs_dir=result_dir/"jobs"
        if jobs_dir.is_dir():
            for folder in jobs_dir.iterdir():
                if not folder.is_dir():
                    continue
                record=folder/"job.json"
                if record.is_symlink() or not record.is_file():
                    raise RuntimeError("Existing worker job is not safely inspectable")
                try:
                    prior=json.loads(record.read_text())
                except (OSError,ValueError):
                    raise RuntimeError("Existing worker job metadata invalid")
                if prior.get("state")=="running":
                    raise RuntimeError("An ISE worker build is already running; refusing duplicate")
        print("SMOKE_ONLY_PREFLIGHT=PASS (installation and worker preserved)",flush=True)
        smoke_build()
        print("ISE14_7_OPERATIONAL_SMOKE_PASS",flush=True)
        return
    install_ise(license_file,archive)
    command_probe()
    inputs=prepare_worker_inputs(license_file,work)
    build_worker_image()
    ensure_worker(*inputs)
    smoke_build()
    print("ISE14_7_OPERATIONAL_SMOKE_PASS",flush=True)

if __name__=="__main__":
    try:
        main()
    except (RuntimeError,OSError,ValueError,subprocess.TimeoutExpired,tarfile.TarError,EOFError,KeyboardInterrupt) as exc:
        print("ISE14_7_BRINGUP_BLOCKED: "+str(exc),file=sys.stderr,flush=True)
        raise SystemExit(9)
