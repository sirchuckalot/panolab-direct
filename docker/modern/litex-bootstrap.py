#!/usr/bin/env python3
"""Provision pinned LiteX in a container prefix: no sudo, host installs or FPGA writes."""
import argparse, json, os, re, shutil, subprocess, sys
from pathlib import Path

NAMES = {"litex":"litex", "litex-boards":"litex-boards", "liteeth":"liteeth",
         "litespi":"litespi", "migen":"migen", "picolibc_data":"picolibc",
         "picolibc_pythondata":"pythondata-software-picolibc"}
PYTHON_MODULE_DIRS = ("migen","litex","litex-boards","liteeth","litespi",
                      "pythondata-software-picolibc")

def run(*argv, env=None):
    subprocess.run([str(x) for x in argv], check=True, env=env)

def output(*argv):
    return subprocess.check_output([str(x) for x in argv], text=True).strip()

def load_lock(path):
    data = json.loads(path.read_text())
    if data.get("schema") != "panolab-rescue-upstream-lock-v1":
        raise ValueError("wrong lock schema")
    sources = data["repositories"]
    if set(sources) != set(NAMES):
        raise ValueError("upstream set does not match locked recipe")
    for name, src in sources.items():
        if not re.fullmatch("[0-9a-f]{40}", src["commit"]):
            raise ValueError(f"unpinned source: {name}")
        if not re.fullmatch(r"https://github\.com/[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+\.git", src["url"]):
            raise ValueError(f"non-approved source URL: {name}")
    return sources

def checkout(root, name, src):
    dest = root / NAMES[name]
    sha = src["commit"]
    if dest.exists():
        if not (dest/".git").is_dir():
            raise RuntimeError(f"unexpected existing path: {dest}")
        if output("git","-C",dest,"rev-parse","HEAD") != sha:
            raise RuntimeError(f"pin mismatch in existing {dest}; refusing to overwrite")
    else:
        run("git","clone","--quiet","--filter=blob:none","--no-checkout",src["url"],dest)
        run("git","-C",dest,"fetch","--quiet","--depth","1","origin",sha)
        run("git","-C",dest,"checkout","--quiet","--detach",sha)
    if output("git","-C",dest,"rev-parse","HEAD") != sha:
        raise RuntimeError(f"source SHA mismatch: {name}")
    print(f"PIN_OK {name} {sha}",flush=True)

def picolibc_link(root):
    data = root/"pythondata-software-picolibc"/"pythondata_software_picolibc"/"data"
    target = root/"picolibc"
    if data.is_symlink():
        if data.resolve(strict=True) != target.resolve(strict=True):
            raise RuntimeError("unexpected Picolibc symlink")
        if not data.readlink().is_absolute():
            # LiteX uses cp -a for Pythondata into each generated BIOS build.
            # A relative link is then copied to a different directory and breaks.
            data.unlink()
            data.symlink_to(target.resolve(strict=True), target_is_directory=True)
    else:
        if data.exists():
            if not data.is_dir() or any(data.iterdir()):
                raise RuntimeError("unexpected populated Picolibc wrapper submodule")
            data.rmdir()
        data.symlink_to(target.resolve(strict=True), target_is_directory=True)
    if not (data/"libc/stdio/printf.c").is_file():
        raise RuntimeError("pinned Picolibc data layout does not meet LiteX expectations")

def env_for(prefix):
    repo = prefix/"upstream"
    venv = prefix/"venv"
    site = venv/"lib"/f"python{sys.version_info.major}.{sys.version_info.minor}"/"site-packages"
    return {**os.environ,
            "PATH":f"{venv/'bin'}:{os.environ.get('PATH','')}",
            "PYTHONPATH":":".join([str(repo/x) for x in PYTHON_MODULE_DIRS] + [str(site)]),
            "PANOLAB_RESCUE_UPSTREAM":str(repo),
            "PANOLAB_RESCUE_PYDEPS":str(site),
            "PANOLAB_RESCUE_BIN":str(venv/"bin")}

def verify(prefix, sources, requirements):
    repo = prefix/"upstream"
    for name, src in sources.items():
        folder = repo/NAMES[name]
        if not (folder/".git").is_dir() or output("git","-C",folder,"rev-parse","HEAD") != src["commit"]:
            raise RuntimeError(f"missing or changed pinned checkout: {name}")
    picolibc_link(repo)
    env = env_for(prefix)
    py = prefix/"venv/bin/python3"
    if not py.is_file():
        raise RuntimeError("venv interpreter missing")
    code = """
import importlib
from pathlib import Path
for mod in ('litex','migen','litex_boards','liteeth','litespi',
            'pythondata_cpu_vexriscv','pythondata_software_compiler_rt'):
    importlib.import_module(mod)
from litex import get_data_mod
from litespi.modules import M25P128
from litespi.opcodes import SpiNorFlashOpCodes
assert Path(get_data_mod('software','picolibc').data_location, 'libc/stdio/printf.c').is_file()
assert M25P128(default_read_cmd=SpiNorFlashOpCodes.READ_1_1_1).total_size == 16777216
print('LITEX_IMPORT_SPI_AND_PICOLIBC=PASS')
"""
    run(py,"-c",code,env=env)
    check_versions = """
import importlib.metadata as md
import re,sys
from pathlib import Path
for line in Path(sys.argv[1]).read_text().splitlines():
    line=line.strip()
    if not line or line.startswith('#'): continue
    match=re.fullmatch(r'([A-Za-z0-9_.-]+)==([A-Za-z0-9_.+-]+)',line)
    if not match: raise RuntimeError('non-pinned requirement: '+line)
    name,expected=match.groups()
    got=md.version(name)
    if got!=expected: raise RuntimeError(f'{name}: expected {expected}, found {got}')
print('PYTHON_PACKAGE_VERSIONS=PASS')
"""
    run(py,"-c",check_versions,requirements,env=env)
    run(py,"-m","pip","check",env=env)
    for cmd in ("riscv64-unknown-elf-gcc","riscv64-unknown-elf-as",
                "meson","ninja","iverilog","yosys","verilator"):
        if shutil.which(cmd,path=env["PATH"]) is None:
            raise RuntimeError(f"missing executable in recipe image: {cmd}")
    print("LITEX_REQUIRED_TOOLS=PASS",flush=True)

def write_env(prefix):
    env = env_for(prefix)
    path = prefix/"env.sh"
    keys = ("PANOLAB_RESCUE_UPSTREAM","PANOLAB_RESCUE_PYDEPS","PANOLAB_RESCUE_BIN")
    body = "# Generated by the PanoLab LiteX recipe. Source inside a container only.\n"
    body += "".join(f"export {key}='{env[key]}'\n" for key in keys)
    body += 'export PATH="$PANOLAB_RESCUE_BIN:$PATH"\n'
    body += ('export PYTHONPATH="$PANOLAB_RESCUE_UPSTREAM/pythondata-software-picolibc:'
             '$PANOLAB_RESCUE_UPSTREAM/migen:$PANOLAB_RESCUE_UPSTREAM/litex:'
             '$PANOLAB_RESCUE_UPSTREAM/litex-boards:$PANOLAB_RESCUE_UPSTREAM/liteeth:'
             '$PANOLAB_RESCUE_UPSTREAM/litespi:$PANOLAB_RESCUE_PYDEPS${PYTHONPATH:+:$PYTHONPATH}"\n')
    path.write_text(body)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--prefix",type=Path,required=True)
    p.add_argument("--lock",type=Path,required=True)
    p.add_argument("--requirements",type=Path,required=True)
    p.add_argument("--verify-only",action="store_true")
    a=p.parse_args()
    prefix=a.prefix.resolve()
    if prefix==Path("/") or str(prefix).startswith("/usr/"):
        p.error("refuse to touch host/system package paths")
    sources=load_lock(a.lock)
    if not a.verify_only:
        upstream=prefix/"upstream"
        upstream.mkdir(parents=True,exist_ok=True)
        for name,src in sources.items():
            checkout(upstream,name,src)
        picolibc_link(upstream)
        venv=prefix/"venv"
        if not (venv/"bin/python3").is_file():
            run(sys.executable,"-m","venv",venv)
        tmp=prefix/"tmp"
        tmp.mkdir(exist_ok=True)
        pip_env={**os.environ,"TMPDIR":str(tmp)}
        run(venv/"bin/python3","-m","pip","install","--no-cache-dir",
            "--disable-pip-version-check", "--quiet","-r",a.requirements,env=pip_env)
    verify(prefix,sources,a.requirements)
    if a.verify_only:
        if not (prefix/"env.sh").is_file():
            raise RuntimeError("environment file not produced by image recipe")
    else:
        write_env(prefix)
    print(f"LITEX_IMAGE_RECIPE_READY={prefix}",flush=True)

if __name__=="__main__":
    try: main()
    except (OSError,RuntimeError,ValueError,subprocess.CalledProcessError) as e:
        print(f"LITEX_RECIPE_FAILURE: {e}",file=sys.stderr)
        sys.exit(1)
