#!/usr/bin/env python3
"""Guarded recovery of the known GNU tar ownership failure in rootless ISE setup.

This is a ONE-TIME owner-user operation, not a general installation reset.
Preserves the failed state and extracted data; only replaces PanoLab setup
service after compiling its patched source. All private material stays local.
"""
from __future__ import annotations
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
SETUP_NAME="panolab-direct-connect-setup-1"
SETUP_IMAGE="panolab-direct-ise14-setup:local"
NEW_IMAGE="panolab-direct-ise14-setup:rootless-owner-fix-20261124"
BACKUP_IMAGE="panolab-direct-ise14-setup:pre-owner-fix-20261124"
OLD_ERROR_MARKERS=("tar extraction failed","Cannot change ownership")
BACKUP_SUFFIX=".failed-rootless-ownership-20261124"

def fail(reason):
    raise RuntimeError(reason)

def load_bringup():
    p=ROOT/"host/ise14-bringup.py"
    spec=importlib.util.spec_from_file_location("ise14_bringup",p)
    module=importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    module.DOCKER_SOCK=Path(os.environ.get("XDG_RUNTIME_DIR",f"/run/user/{os.getuid()}"))/"docker.sock"
    return module

def ensure_regular(path:Path):
    if path.is_symlink() or not path.is_file():
        fail(f"Expected regular private state file is missing: {path.name}")

def preflight(b):
    b.check_docker_state()
    lic,work,archive=b.private_inputs()
    source=(ROOT/"docker/ise14/mcp/setup/main.go").read_text()
    test_source=(ROOT/"docker/ise14/mcp/setup/main_test.go").read_text()
    required='rootlessExtractionArgs()'
    if required not in source or '"--no-same-owner"' not in source or '"--no-same-permissions"' not in source or required not in test_source:
        fail("Patched ownership-safe setup source and regression test not present")
    state_path=work/"install-state.json"
    media=work/"ise-media"
    ensure_regular(state_path)
    if media.is_symlink() or not media.is_dir():
        fail("Expected partial ISE-media extraction directory absent; manual review needed")
    if not any(media.iterdir()):
        fail("Partial ISE-media directory is empty; manual review needed")
    state=json.loads(state_path.read_text())
    if not isinstance(state,dict):
        fail("Bad setup state")
    current=state.get("State",state.get("state"))
    err=str(state.get("Error",state.get("error","")))
    if current!="failed" or not all(s in err for s in OLD_ERROR_MARKERS):
        fail("Failure is not the previously diagnosed GNU tar ownership problem")
    if (work/"ise-install.log").exists():
        fail("Vendor installer log already exists; failure is beyond extraction phase")
    xilinx=ROOT/"docker/private/Xilinx"
    if xilinx.is_symlink() or not xilinx.is_dir() or any(xilinx.iterdir()):
        fail("ISE destination is not empty; do not disturb a partial tool installation")
    if shutil.disk_usage(work).free < 12*1024**3:
        fail("Insufficient free space for preserved failure and fresh extraction")
    existing=b.read_rpc(SETUP_NAME,8766,"/run/secrets/mcp-bearer","ise_install_status")
    if existing.get("state")!="failed":
        fail("Live setup service is not in expected failed state")
    c=json.loads(b.d("inspect",SETUP_NAME))[0]
    if not c["State"]["Running"] or c["Config"]["Labels"].get("com.docker.compose.project")!="panolab-direct-connect":
        fail("Unexpected setup container state")
    mounts={m["Destination"]:(m["Source"],not m["RW"]) for m in c["Mounts"] if m["Type"]=="bind"}
    required_mounts={
        "/work":(str(work),False),
        "/opt/Xilinx":(str(xilinx),False),
        "/media/ise.tar":(str(archive),True),
        "/licenses/Xilinx.lic":(str(lic),True)
    }
    for dest,expected in required_mounts.items():
        if mounts.get(dest)!=expected:
            fail(f"Unexpected PanoLab setup bind: {dest}")
    if c["HostConfig"].get("Privileged"):
        fail("Refusing privileged setup container")
    saved_state=work/("install-state"+BACKUP_SUFFIX+".json")
    saved_media=work/("ise-media"+BACKUP_SUFFIX)
    if saved_state.exists() or saved_media.exists():
        fail("An earlier recovery checkpoint already exists; refuse repeated recovery")
    print("OWNER_FIX_PREFLIGHT=PASS (failed state, partial media, isolated setup container)",flush=True)
    return work,archive,state_path,media,saved_state,saved_media

def build_setup(b):
    print("BUILDING_PATCHED_ISE_SETUP_IMAGE=START",flush=True)
    # This Dockerfile runs the pinned Go unit tests in the build stage.
    b.d("buildx","build","--builder","default","--load",
        "--target","setup-runtime","-t",NEW_IMAGE,
        "-f",str(ROOT/"docker/ise14/Dockerfile"),
        str(ROOT/"docker/ise14"),timeout=1800)
    print("PATCHED_ISE_SETUP_IMAGE=BUILT_AND_TESTED",flush=True)

def move_failed_evidence(state_path,media,saved_state,saved_media):
    # Retain both: no rm/rmtree, no overwriting pre-existing records.
    os.rename(state_path,saved_state)
    try:
        os.rename(media,saved_media)
    except BaseException:
        os.rename(saved_state,state_path)
        raise
    print("FAILED_STATE_AND_PARTIAL_MEDIA=PRESERVED",flush=True)

def reconfigure_service(b,archive):
    current=b.d("image","inspect","--format","{{.Id}}",SETUP_IMAGE)
    previous=b.d("image","inspect","--format","{{.Id}}",BACKUP_IMAGE,check=False)
    if previous and previous!=current:
        fail("Existing backup image tag points at different image; refuse overwrite")
    b.d("image","tag",SETUP_IMAGE,BACKUP_IMAGE)
    b.d("image","tag",NEW_IMAGE,SETUP_IMAGE)
    private=ROOT/"docker/private"
    env=os.environ.copy()
    env.update({
        "PANOLAB_ROOTLESS_SOCKET":str(b.DOCKER_SOCK),
        "PANOLAB_REPO_HOST":str(ROOT),
        "PANOLAB_WORKSPACE_HOST":str((private/"agent-workspace").resolve(strict=True)),
        "PANOLAB_CODEX_AUTH_HOST":str((private/"codex-auth").resolve(strict=True)),
        "PANOLAB_ISE_TARBALL":str(archive),
    })
    base=["docker","-H",f"unix://{b.DOCKER_SOCK}","compose",
        "--project-name","panolab-direct-connect",
        "--env-file",str(ROOT/"docker/.env"),
        "-f",str(ROOT/"docker/compose.setup.yaml"),
        "-f",str(ROOT/"docker/compose.manage.yaml"),
        "-f",str(ROOT/"host/compose.rootless-laptop.yaml")]
    cfg=subprocess.run(base+["config","--quiet"],env=env,text=True,capture_output=True)
    if cfg.returncode:
        fail("Merged Compose config failed validation; existing service not changed")
    command=base+["up","-d","--no-deps","--no-build","--force-recreate","setup"]
    result=subprocess.run(command,env=env,text=True,capture_output=True,timeout=180)
    if result.returncode:
        fail("Isolated setup recreation failed; earlier image remains backed up")
    print("ISE_SETUP_SERVICE=RECREATED_ONLY_SETUP",flush=True)
    for i in range(15):
        try:
            fresh=b.read_rpc(SETUP_NAME,8766,"/run/secrets/mcp-bearer","ise_install_status")
        except (RuntimeError,OSError):
            time.sleep(2)
            continue
        if fresh.get("state")=="not_started":
            print("PATCHED_SETUP_ACCEPTED_NEW_STATE=PASS",flush=True)
            return
        fail("Patched setup did not start from clean recovery state")
    fail("Replaced setup MCP endpoint did not become healthy")

def main():
    b=load_bringup()
    work,archive,state_path,media,saved_state,saved_media=preflight(b)
    build_setup(b)
    # Image is fully built before making any private-state changes.
    # Fail-closed preconditions on the old state are checked once more.
    current=json.loads(state_path.read_text())
    if current.get("State",current.get("state"))!="failed":
        fail("Installer state changed while patched image was building")
    move_failed_evidence(state_path,media,saved_state,saved_media)
    reconfigure_service(b,archive)
    print("OWNER_FIX_READY_FOR_RETRY=PASS",flush=True)
    print("Continuing the existing guarded ISE installer and six-stage smoke test.",flush=True)
    # The ISE EULA confirmation is requested again by the standard installer.
    result=subprocess.run([sys.executable,str(ROOT/"host/ise14-bringup.py"),"install-smoke"])
    if result.returncode:
        fail("ISE retry or smoke test did not pass; keep recovery evidence and inspect new error")
    print("ISE14_7_REPAIR_AND_SMOKE=PASS",flush=True)

if __name__=="__main__":
    try:
        main()
    except (ValueError,RuntimeError,OSError,subprocess.TimeoutExpired,KeyboardInterrupt) as exc:
        print("ISE14_7_REPAIR_BLOCKED="+str(exc),file=sys.stderr,flush=True)
        raise SystemExit(9)
