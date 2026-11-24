#!/usr/bin/env python3
"""Read-only, redacted diagnosis for the PanoLab ISE 14.7 installer.

Reads only install state and the installer log under the private work directory.
Never opens or displays the Xilinx license, private tokens, or the vendor archive.
"""
from pathlib import Path
import json
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "docker/private/ise-work"
STATE = WORK / "install-state.json"
LOG = WORK / "ise-install.log"
INSTALLED = ROOT / "docker/private/Xilinx/14.7/ISE_DS/settings64.sh"

SIGNATURES = (
    ("STORAGE_EXHAUSTED", r"no space left|disk full|out of disk|not enough space|insufficient disk|enospc"),
    ("PERMISSION_ERROR", r"permission denied|operation not permitted|read-only file system|access is denied|eacces"),
    ("MISSING_LIBRARY", r"error while loading shared libraries|cannot open shared object|libstdc\+\+|libx11|glibc|libmotif"),
    ("MISSING_EXECUTABLE", r"command not found|not found|no such file or directory|cannot execute|bad interpreter"),
    ("INSTALLER_OPTIONS", r"unknown option|invalid argument|unrecognized option|usage:.*(xsetup|batchxsetup)"),
    ("DISPLAY_X11", r"cannot open display|display.*not set|x11.*error|could not connect to.*display"),
    ("JAVA_RUNTIME", r"java\.lang\.|java exception|jvm.*error|exception in thread"),
    ("LICENSE_REJECTION", r"invalid license|license not found|license checkout failed|license validation failed"),
    ("TERMINATED_PROCESS", r"killed|segmentation fault|signal: killed|exit status 137|out of memory"),
    ("INSTALLATION_FAILURE", r"installation failed|installer failed|install failed|failed to install|installation aborted"),
)
# Every string printed from private files is sanitized before printing.
def redact(line: str) -> str:
    line = line.replace(str(ROOT), "<REPO>")
    line = re.sub(r"/home/[^/\s]+", "<HOME>", line)
    line = re.sub(r"/work/ise-media/[^\s]+", "<PRIVATE_MEDIA_PATH>", line)
    line = re.sub(r"/opt/Xilinx/[^\s]+", "<ISE_PATH>", line)
    line = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "<EMAIL>", line)
    line = re.sub(r"\b(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}\b", "<MAC>", line)
    line = re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "<IP>", line)
    line = re.sub(r"\b[A-Fa-f0-9]{24,}\b", "<HEX_ID>", line)
    line = re.sub(r"(?i)\b(key|token|password|hostid|license\s*code|serial)\s*[:=]\s*\S+",
                  r"\1=<REDACTED>", line)
    return line[:240]

def safe_read(path: Path, max_size: int) -> str | None:
    if path.is_symlink():
        print(f"UNSAFE_SYMLINK={path.name}")
        return None
    if not path.is_file():
        return None
    if path.stat().st_size > max_size:
        print(f"FILE_TOO_LARGE={path.name}")
        return None
    return path.read_text(errors="replace")

def diagnose():
    print("ISE14_DIAGNOSIS=READ_ONLY")
    data=safe_read(STATE,65536)
    if not data:
        print("INSTALL_STATE=NOT_AVAILABLE")
    else:
        try:
            st=json.loads(data)
            print("INSTALL_STATE="+str(st.get("state",st.get("State","UNKNOWN"))).upper())
            err=str(st.get("error",st.get("Error",""))).strip()
            if err:
                print("INSTALL_ERROR_SUMMARY="+redact(err))
            else:
                print("INSTALL_ERROR_SUMMARY=UNAVAILABLE")
        except (ValueError,TypeError):
            print("INSTALL_STATE=UNREADABLE")
    text=safe_read(LOG,50*1024*1024)
    if text is None:
        print("VENDOR_LOG=NOT_PRESENT")
    else:
        lines=text.splitlines()
        print(f"VENDOR_LOG_PRESENT=YES lines={len(lines)} bytes={len(text.encode('utf-8'))}")
        matched=[]
        for label,regex in SIGNATURES:
            matches=[line for line in lines if re.search(regex,line,re.I)]
            if matches:
                matched.append(label)
                # Avoid exposing license content: only show categories unless
                # the line is an unambiguous file/runtime error.
                if label in ("STORAGE_EXHAUSTED","MISSING_LIBRARY","PERMISSION_ERROR","MISSING_EXECUTABLE","DISPLAY_X11"):
                    print(label+"_EXAMPLE="+redact(matches[-1]))
        print("ERROR_CATEGORIES="+(",".join(matched) if matched else "NONE_DETECTED"))
        if not matched:
            print("LOG_TAIL_NOT_SHOWN=Review private log locally if more detail is needed")
    print("ISE_SETTINGS_PRESENT="+str(INSTALLED.is_file() and not INSTALLED.is_symlink()).upper())
    try:
        free=shutil.disk_usage(WORK).free
        print("WORKSPACE_FREE_GIB="+str(round(free/(1024**3),2)))
    except OSError:
        print("WORKSPACE_FREE_GIB=UNAVAILABLE")
    # A failed install may have left partial files. Report only number of top-level
    # paths, never print their names or private path contents.
    root=ROOT/"docker/private/Xilinx"
    if root.is_dir() and not root.is_symlink():
        print("ISE_INSTALL_ROOT_TOP_LEVEL_ENTRIES="+str(len(list(root.iterdir()))))
    else:
        print("ISE_INSTALL_ROOT=NOT_AVAILABLE")
    print("NO_INSTALLATION_OR_CLEANUP_PERFORMED=TRUE")

if __name__=="__main__":
    try:
        diagnose()
    except Exception as exc:
        print("DIAGNOSIS_BLOCKED="+type(exc).__name__,file=sys.stderr)
        raise SystemExit(3)
