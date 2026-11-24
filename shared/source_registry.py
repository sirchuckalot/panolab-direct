#!/usr/bin/env python3
"""PanoLab source registry validator and clean project runner.

No source downloads, hidden upstream checkout, Docker, or host privilege required.
Only source snapshots listed in project.toml and third_party/registry.toml are allowed.
"""
from __future__ import annotations
import argparse, hashlib, os, pathlib, shutil, subprocess, sys, tomllib

ROOT=pathlib.Path(__file__).resolve().parents[1]
REGISTRY=ROOT/"third_party/registry.toml"
COMPONENTS=("litex","litex-boards","liteeth","litespi","migen",
            "picolibc","pythondata-software-picolibc","pythondata-cpu-vexriscv",
            "pythondata-software-compiler-rt")
def digest(p):
    h=hashlib.sha256()
    with p.open("rb") as fh:
        for block in iter(lambda:fh.read(1048576),b""):
            h.update(block)
    return h.hexdigest()
def load_project(project: pathlib.Path):
    path=(ROOT/project).resolve()
    if not path.is_relative_to(ROOT/"projects") or not path.is_file():
        raise ValueError("project manifest outside projects/")
    cfg=tomllib.loads(path.read_text())
    if cfg["schema"]!="panolab-project-v1":
        raise ValueError("unknown project manifest schema")
    return cfg
def resolve(cfg):
    catalog=tomllib.loads(REGISTRY.read_text())
    declared=cfg["dependencies"]
    if len(declared)!=len(set(item["name"] for item in declared)):
        raise ValueError("duplicate dependency")
    result={}
    for dep in declared:
        item=catalog["snapshots"].get(dep["name"])
        if item is None or item["revision"]!=dep["revision"]:
            raise ValueError(f"unapproved source revision {dep}")
        target=(ROOT/"third_party"/item["path"]).resolve()
        if not target.is_relative_to(ROOT/"third_party") or not target.is_dir():
            raise ValueError("unsafe source path")
        meta=tomllib.loads((target/"upstream.toml").read_text())
        if meta["name"]!=dep["name"] or meta["snapshot"]!=dep["revision"]:
            raise ValueError("source record does not match registry")
        manifest=target/"files.sha256"
        if digest(manifest)!=meta["file_manifest_sha256"]:
            raise ValueError("upstream file list tampered: "+dep["name"])
        expected={}
        for line in manifest.read_text().splitlines():
            sha,relative=line.split("  ",1)
            candidate=pathlib.PurePosixPath(relative)
            if candidate.is_absolute() or ".." in candidate.parts:
                raise ValueError("unsafe source file list")
            if relative in expected:
                raise ValueError("duplicate file in source manifest")
            expected[relative]=sha
        src=target/"src"
        actual={}
        for file in src.rglob("*"):
            if file.is_symlink(): raise ValueError("source symlink not permitted: "+str(file))
            if file.is_file():
                actual[file.relative_to(src).as_posix()]=digest(file)
        if actual!=expected or len(actual)!=meta["file_count"]:
            missing=set(expected)-set(actual)
            extra=set(actual)-set(expected)
            changed={x for x in set(expected)&set(actual) if expected[x]!=actual[x]}
            raise ValueError(f"source integrity failure {dep['name']}: missing={len(missing)}, extra={len(extra)}, modified={len(changed)}")
        lic=target/meta["license_file"]
        if not lic.is_file(): raise ValueError("missing third-party license "+dep["name"])
        if digest(lic)!=meta["license_sha256"]: raise ValueError("third-party license modified: "+dep["name"])
        result[dep["name"]]=src
    if cfg["name"]=="rescue" and set(result)!=set(COMPONENTS):
        raise ValueError("Rescue source closure incomplete: "+repr(set(COMPONENTS)-set(result)))
    return result
def launch(cfg,paths,cmd):
    prefix=pathlib.Path(os.environ.get("PANOLAB_TOOLCHAIN_PREFIX","/opt/panolab/litex"))
    site=prefix/"venv/lib/python3.12/site-packages"
    binpath=prefix/"venv/bin"
    if not site.is_dir() or not binpath.is_dir():
        raise ValueError("pinned development image unavailable")
    out=pathlib.Path(os.environ.get("PANOLAB_RESCUE_OUT","/workspace/panolab-projects/rescue-g2b")).resolve()
    if out==ROOT or ROOT in out.parents or out==pathlib.Path("/"):
        raise ValueError("never generate artifacts in source checkout")
    out.mkdir(parents=True,exist_ok=True)
    overlay=out/".panolab-source-overlays"
    pkg=overlay/"pythondata_software_picolibc"
    pkg.mkdir(parents=True,exist_ok=True)
    original=paths["pythondata-software-picolibc"]/"pythondata_software_picolibc/__init__.py"
    shutil.copy2(original,pkg/"__init__.py")
    link=pkg/"data"
    expected=paths["picolibc"].resolve()
    if link.is_symlink():
        if link.resolve()!=expected:raise ValueError("different Picolibc source overlay present")
    elif link.exists():
        raise ValueError("occupied Picolibc data overlay path")
    else:
        link.symlink_to(expected,target_is_directory=True)
    env=os.environ.copy()
    env["PANOLAB_RESCUE_OUT"]=str(out)
    env["PANOLAB_SOURCE_VERIFIED"]="1"
    env["PANOLAB_LITEX_SOURCE_REVISION"]=tomllib.loads((ROOT/"third_party/litex/afed6623/upstream.toml").read_text())["revision"]
    env["PYTHONNOUSERSITE"]="1"
    env["PYTHONDONTWRITEBYTECODE"]="1"
    env["PYTHONPATH"]=os.pathsep.join([str(overlay),str(ROOT),str(ROOT/"projects/rescue/soc")]+[str(x) for x in paths.values() if x!=paths["pythondata-software-picolibc"]]+[str(site)])
    env["PATH"]=str(binpath)+os.pathsep+env.get("PATH","")
    # Check actual loaded modules, not just directory naming. No hidden upstream source.
    check='''import importlib,os
for name in ("litex","litex_boards","liteeth","litespi","migen","pythondata_software_picolibc","pythondata_cpu_vexriscv","pythondata_software_compiler_rt"):
 m=importlib.import_module(name)
 p=os.path.realpath(m.__file__)
 if not ("/third_party/" in p or "/.panolab-source-overlays/" in p):
  raise SystemExit("unapproved module path "+name+" "+p)
 print("SOURCE="+name+" "+p)
'''
    subprocess.run([sys.executable,"-c",check],env=env,cwd=ROOT,check=True)
    if not cmd: raise ValueError("no declared project command")
    if cmd[0] not in ("bash","python3","/bin/bash"):
        raise ValueError("only project build and test tools are supported")
    return subprocess.run(cmd,env=env,cwd=ROOT,check=False).returncode
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("mode",choices=["verify","run"])
    parser.add_argument("--project",default="projects/rescue/project.toml")
    args, extra=parser.parse_known_args()
    cfg=load_project(pathlib.Path(args.project))
    paths=resolve(cfg)
    print(f"PANOLAB_SOURCE_VERIFY=PASS components={len(paths)}",flush=True)
    if args.mode=="run":
        command=extra
        if command and command[0]=="--":command=command[1:]
        return launch(cfg,paths,command)
    return 0
if __name__=="__main__":
    try:raise SystemExit(main())
    except (ValueError,OSError,KeyError) as exc:
        print("PANOLAB_SOURCE_VERIFY=FAIL "+str(exc),file=sys.stderr)
        raise SystemExit(3)
