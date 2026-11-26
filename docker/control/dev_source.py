"""Bounded, metadata-only checks before exposing a canonical source checkout."""
import os
import re
from pathlib import Path
import stat
import subprocess
import sys

MASK = "ro,nosuid,nodev,noexec,size=64k"
ROOT_FILES = ("AGENTS.md", "README.md", "LICENSE", "docs/AGENT_EXECUTION_POLICY.md")
ROOT_DIRS = ("agent", "boards", "docker/control", "docker/ise14", "docker/modern",
             "docs", "host", "projects", "research", "shared", "specs", "tests", "third_party")
PROBE = " && ".join(
    [f"test -r /repo/{p}" for p in ROOT_FILES] +
    [f"test -d /repo/{p}" for p in ROOT_DIRS] +
    ['test -d /repo/.git', 'test -z "$(ls -A /repo/.git)"',
     'test ! -e /repo/docker/.env', 'test ! -L /repo/docker/.env',
     'test ! -e /repo/docker/private', 'test ! -L /repo/docker/private',
     """awk '$5=="/repo" || $5=="/repo/.git" {if ($6 !~ /^ro(,|$)/) exit 1; if ($5=="/repo/.git" && $0 !~ / - tmpfs /) exit 1; n++} END {if (n != 2) exit 1}' /proc/self/mountinfo"""]
)


def checkout(root):
    root = Path(root)
    if not (root / ".git").is_dir() or (root / ".git").is_symlink():
        raise ValueError("Expected canonical Git directory")
    tracked = subprocess.check_output(
        ["git", "-c", f"safe.directory={root}", "-C", str(root), "ls-files", "-z"],
        stderr=subprocess.DEVNULL,
    )
    allowed = {os.fsdecode(p) for p in tracked.split(b"\0") if p}
    if not set(ROOT_FILES) <= allowed or not all(
        any(p.startswith(directory + "/") for p in allowed) for directory in ROOT_DIRS
    ):
        raise ValueError("Required canonical source missing from index")
    approved_dirs = {parent for p in allowed for parent in Path(p).parents}

    def allowed_cache(rel):
        if rel.parent.name != "__pycache__":
            return False
        match = re.fullmatch(r"(.+)\.cpython-[0-9]+(?:\.opt-[0-9]+)?\.pyc", rel.name)
        return bool(match and str(rel.parent.parent / (match[1] + ".py")) in allowed)

    def fail_walk(error):
        raise error

    for parent, dirs, files in os.walk(root, followlinks=False, onerror=fail_walk):
        if Path(parent) == root:
            dirs.remove(".git")
        for name in dirs + files:
            p = Path(parent) / name
            rel = p.relative_to(root)
            mode = p.lstat()
            if rel.parts[:2] in (("docker", "private"), ("docker", ".env")):
                raise ValueError("Legacy private state remains in checkout")
            if stat.S_ISDIR(mode.st_mode):
                if rel not in approved_dirs and not (name == "__pycache__" and rel.parent in approved_dirs):
                    raise ValueError("Unapproved source directory")
            elif (not stat.S_ISREG(mode.st_mode) or mode.st_nlink != 1 or
                  (str(rel) not in allowed and
                   not allowed_cache(rel))):
                raise ValueError("Unapproved source entry")
    if not all((root / p).is_file() for p in allowed):
        raise ValueError("Tracked canonical source missing")


def mount_layout(mounts, tmpfs, root, workspace, auth):
    expected = {"/repo": (root, False), "/workspace": (workspace, True),
                "/codex-auth": (auth, True)}
    local = {"/tmp", "/home", "/repo/.git"}
    binds = [m for m in mounts if m["Type"] == "bind"]
    actual = {m["Destination"]: (m["Source"], m["RW"]) for m in binds}
    return (len(binds) == len(actual) and actual == expected and
            all(m["Type"] == "bind" or
                (m["Type"] == "tmpfs" and m["Destination"] in local) for m in mounts) and
            set(tmpfs) == local and tmpfs["/repo/.git"] == MASK)


if __name__ == "__main__":
    import json

    try:
        if sys.argv[1] == "--probe":
            print(PROBE)
        elif sys.argv[1] == "--mounts":
            decoder = json.JSONDecoder()
            raw = sys.stdin.read()
            mounts, end = decoder.raw_decode(raw)
            if not mount_layout(mounts, json.loads(raw[end:]), *sys.argv[2:]):
                raise ValueError("Unexpected source mounts")
        else:
            checkout(sys.argv[1])
    except (OSError, ValueError, TypeError, KeyError, subprocess.CalledProcessError):
        sys.exit("Canonical source admission failed")
