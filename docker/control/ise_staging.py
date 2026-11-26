#!/usr/bin/env python3
"""Immutable remote staging of verified, bounded ISE project inputs.

The rootless broker has the Docker socket, but does NOT mount editable sources
or private vendor credentials. A one-shot networkless helper copies from the
agent workspace to the existing worker project volume with fixed bind mounts.
No caller-supplied Docker flags, paths, programs, or shell commands.
"""
import json
import re

import ise_proxy

BROKER = "panolab-direct-connect-docker-broker-1"
PROJECT = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,44}$")

# Runs only in a disposable rootless Docker container with two exact mounts:
# /workspace (read-only agent workspace) and /output (ISE project directory).
# Python 3.12 helper has no network, Docker socket, secrets or vendor files.
STAGE_HELPER = r'''
import hashlib,json,os,re,stat,sys
NAME=re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
FILE=re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
PROJECT=re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,44}$")

def check_regular_at(parent,name,max_bytes):
    fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=parent)
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size<0 or info.st_size>max_bytes:
            raise ValueError("INVALID_PROJECT_FILE")
        with os.fdopen(fd,"rb",closefd=False) as stream:
            data=stream.read(max_bytes+1)
        if len(data)>max_bytes:
            raise ValueError("FILE_TOO_LARGE")
        return data
    finally:
        os.close(fd)

def read_inputs(source,project):
    if not PROJECT.fullmatch(project):
        raise ValueError("INVALID_PROJECT_ID")
    # Open *each* directory without following an attacker-controlled symlink.
    root=os.open(source,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        staging=os.open("ise-staging",os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=root)
        try:
            folder=os.open(project,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=staging)
            try:
                raw=check_regular_at(folder,"build.json",8192)
                def unique(pairs):
                    d={}
                    for key,value in pairs:
                        if key in d:raise ValueError("DUPLICATE_MANIFEST_KEY")
                        d[key]=value
                    return d
                p=json.loads(raw.decode("utf-8"),object_pairs_hook=unique)
                if not isinstance(p,dict) or set(p)!={"top","part","verilog","ucf"}:
                    raise ValueError("UNSUPPORTED_PROJECT_SCHEMA")
                if (not isinstance(p["top"],str) or not NAME.fullmatch(p["top"])
                        or p["part"]!="xc6slx150-fgg484-2"
                        or type(p["verilog"])!=list or not 1<=len(p["verilog"])<=64):
                    raise ValueError("INVALID_FPGA_TARGET")
                verilog=p["verilog"]
                if len(set(verilog))!=len(verilog):
                    raise ValueError("DUPLICATE_VERILOG")
                for name in verilog:
                    if not isinstance(name,str) or not FILE.fullmatch(name) or not name.endswith(".v"):
                        raise ValueError("INVALID_VERILOG_NAME")
                ucf=p["ucf"]
                if ucf:
                    if not isinstance(ucf,str) or not FILE.fullmatch(ucf) or not ucf.endswith(".ucf"):
                        raise ValueError("INVALID_UCF_NAME")
                elif ucf!="":
                    raise ValueError("INVALID_UCF_NAME")
                allnames=["build.json"]+verilog+([ucf] if ucf else [])
                if len(set(allnames))!=len(allnames):
                    raise ValueError("DUPLICATE_PROJECT_FILE")
                inputs={"build.json":raw}
                for name in allnames[1:]:
                    inputs[name]=check_regular_at(folder,name,8*1024*1024)
                if sum(map(len,inputs.values()))>16*1024*1024:
                    raise ValueError("PROJECT_TOO_LARGE")
                return inputs
            finally:os.close(folder)
        finally:os.close(staging)
    finally:os.close(root)

def publish(source,target,project):
    inputs=read_inputs(source,project)
    h=hashlib.sha256()
    for name in sorted(inputs):
        body=inputs[name]
        h.update(name.encode("utf-8")+b"\0"+str(len(body)).encode("ascii")+b"\0"+body)
    digest=h.hexdigest()
    name=project+"-"+digest[:12]
    root=os.open(target,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        try:
            candidate=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=root)
        except FileNotFoundError:
            candidate=None
        if candidate is not None:
            try:
                if set(os.listdir(candidate))!=set(inputs):
                    raise ValueError("STAGED_REVISION_MISMATCH")
                for file,data in inputs.items():
                    if check_regular_at(candidate,file,8*1024*1024)!=data:
                        raise ValueError("STAGED_REVISION_MISMATCH")
            finally:os.close(candidate)
            return {"ok":True,"project":name,"sha256":digest,"already_staged":True}
        tmp="."+name+"-"+str(os.getpid())+".tmp"
        os.mkdir(tmp,0o700,dir_fd=root)
        work=os.open(tmp,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=root)
        try:
            for file,data in inputs.items():
                f=os.open(file,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=work)
                try:
                    with os.fdopen(f,"wb",closefd=False) as writer:
                        writer.write(data)
                        writer.flush()
                    os.fsync(f)
                finally:os.close(f)
            os.fsync(work)
        finally:os.close(work)
        os.rename(tmp,name,src_dir_fd=root,dst_dir_fd=root)
        os.fsync(root)
        return {"ok":True,"project":name,"sha256":digest,"already_staged":False}
    finally:os.close(root)

if __name__=="__main__":
    try:
        result=publish("/workspace","/output",sys.argv[1])
        print(json.dumps(result,sort_keys=True))
    except Exception as e:
        # Never echo filenames or file contents; return only the error class.
        category=str(e) if isinstance(e,ValueError) else type(e).__name__.upper()
        print(json.dumps({"ok":False,"category":category[:64]}))
        sys.exit(4)
'''

def stage_project(project, command, workspace_host, data_host):
    if not isinstance(project,str) or not PROJECT.fullmatch(project):
        return ise_proxy.fail("INVALID_PROJECT_ID")
    try:
        ise_proxy.validate_worker(command)
        inspect=command(["docker","inspect","--format","{{json .Mounts}}",ise_proxy.WORKER],15)
        if not inspect.get("ok"):
            return ise_proxy.fail("ISE_WORKER_MOUNTS_UNAVAILABLE")
        mounts=json.loads(inspect["stdout"])
        entries=[m for m in mounts if m.get("Destination")=="/projects"]
        expected=data_host+"/ise-work/worker/projects"
        if (len(entries)!=1 or entries[0].get("Type")!="bind" or
                entries[0].get("Source")!=expected or entries[0].get("RW") is not False):
            return ise_proxy.fail("ISE_PROJECT_MOUNT_CHANGED")
        image=command(["docker","inspect","--format","{{.Image}}",BROKER],15)
        if not image.get("ok"):
            return ise_proxy.fail("ISE_STAGE_IMAGE_UNAVAILABLE")
        immutable_image=image.get("stdout","").strip()
        if not re.fullmatch(r"sha256:[a-f0-9]{64}",immutable_image):
            return ise_proxy.fail("INVALID_STAGE_IMAGE_ID")
        # Fixed source and destination directory bind mounts, not caller paths.
        cmd=[
            "docker","run","--rm","--network","none","--read-only",
            "--cap-drop","ALL","--security-opt","no-new-privileges:true",
            "--user","0:0","--memory","512m","--cpus","1","--pids-limit","64",
            "--tmpfs","/tmp:rw,nosuid,nodev,size=16m",
            "--mount","type=bind,src="+workspace_host+",dst=/workspace,readonly",
            "--mount","type=bind,src="+expected+",dst=/output",
            "--entrypoint","python3",immutable_image,"-c",STAGE_HELPER,project
        ]
        result=command(cmd,120)
        raw=(result.get("stdout") or "").strip()
        if len(raw)>4096:
            return ise_proxy.fail("STAGE_RESPONSE_TOO_LARGE")
        try:
            outcome=json.loads(raw)
        except (ValueError,TypeError):
            return ise_proxy.fail("ISE_STAGE_HELPER_FAILED")
        if not isinstance(outcome,dict) or outcome.get("ok") is not True:
            category=outcome.get("category","ISE_STAGE_REJECTED") if isinstance(outcome,dict) else "ISE_STAGE_REJECTED"
            if category not in (
                "INVALID_PROJECT_ID","INVALID_PROJECT_FILE","FILE_TOO_LARGE",
                "DUPLICATE_MANIFEST_KEY","UNSUPPORTED_PROJECT_SCHEMA",
                "INVALID_FPGA_TARGET","DUPLICATE_VERILOG",
                "INVALID_VERILOG_NAME","INVALID_UCF_NAME",
                "DUPLICATE_PROJECT_FILE","PROJECT_TOO_LARGE",
                "STAGED_REVISION_MISMATCH","FILENOTFOUNDERROR",
                "PERMISSIONERROR","NOTADIRECTORYERROR","FILEEXISTSERROR",
                "VALUEERROR","OSERROR","JSONDECODEERROR","TYPEERROR"):
                category="ISE_STAGE_REJECTED"
            return ise_proxy.fail(category)
        name=outcome.get("project")
        digest=outcome.get("sha256")
        if (not isinstance(name,str) or not name.startswith(project+"-")
            or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}",name)
            or not isinstance(digest,str) or not re.fullmatch("[a-f0-9]{64}",digest)
            or name!=project+"-"+digest[:12]):
            return ise_proxy.fail("INVALID_STAGED_REVISION")
        return {"ok":True,"project":name,"sha256":digest,
                "already_staged":outcome.get("already_staged") is True}
    except (ValueError,TypeError,KeyError):
        return ise_proxy.fail("ISE_STAGE_PRECHECK_FAILED")
    except Exception:
        return ise_proxy.fail("ISE_STAGE_INTERNAL_ERROR")
