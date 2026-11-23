#!/usr/bin/env python3
"""Source-control gateway for one approved mounted laptop checkout.

Only allowlisted source files are reachable. Private media, auth data,
Docker socket and host shell operations are outside this gateway.
Its container user is owner-mapped by the rootless Compose overlay.
"""
import json
import os
import pathlib
import socket
import stat
import subprocess
import tempfile
import threading

ROOT = pathlib.Path("/repo")
SOCKET = "/repo-rpc/panolab-git.sock"
ALLOWED = ("agent", "boards", "docker/control", "docker/ise14", "docker/modern",
           "docs", "gateware", "host", "specs", "tests")
ROOT_FILES = ("AGENTS.md", "README.md", "panolab-install.sh")
# Explicit top-level Docker recipes are readable/editable without opening the
# entire docker/ directory or exposing docker/private and docker/.env.
CONFIG_FILES = ("docker/compose.setup.yaml", "docker/compose.manage.yaml")
SENSITIVE_SUFFIXES = (".key", ".pem", ".p12", ".pfx", ".lic")
MAX_FILE = 1024 * 1024
MAX_MESSAGE = 160
mutex = threading.Lock()

def git(*args, timeout=30):
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_CONFIG_GLOBAL="/dev/null",
               GIT_LFS_SKIP_SMUDGE="1")
    proc = subprocess.run(
        ["git", "-C", str(ROOT), "-c", "core.hooksPath=/dev/null",
         "-c", "core.fsmonitor=false", "-c", "protocol.file.allow=never", *args],
        capture_output=True, text=True, timeout=timeout, env=env)
    return {"ok": proc.returncode == 0, "exit_code": proc.returncode,
            "stdout": proc.stdout[-20000:], "stderr": proc.stderr[-2000:]}

def branch_ok():
    b = git("symbolic-ref", "--quiet", "--short", "HEAD")
    branch = b["stdout"].strip() if b["ok"] else ""
    # Keep development only while the running laptop checkout still uses it.
    # Routine work targets the clean main history; cross-history merges are refused.
    if branch not in ("main", "development"):
        raise ValueError("refusing operation outside main/development branch")
    return branch

def origin_ok():
    r = git("remote", "get-url", "origin")
    allowed = ("https://github.com/sirchuckalot/panolab-direct",
               "https://github.com/sirchuckalot/panolab-direct.git",
               "git@github.com:sirchuckalot/panolab-direct.git")
    if not r["ok"] or r["stdout"].strip() not in allowed:
        raise ValueError("unexpected Git origin; refusing remote operation")

def safe_path(raw, directory=False):
    if not isinstance(raw, str) or not raw or len(raw) > 240:
        raise ValueError("invalid path")
    if chr(0) in raw or "\\" in raw or raw.startswith("/"):
        raise ValueError("unsafe path")
    parts = raw.split("/")
    if any(p in ("", ".", "..") or p.startswith(".") for p in parts):
        raise ValueError("hidden/traversal path refused")
    permitted = raw in ROOT_FILES or raw in CONFIG_FILES or any(
        raw == p or raw.startswith(p + "/") for p in ALLOWED)
    if not permitted or raw.startswith("docker/private/"):
        raise ValueError("path not in approved source tree")
    if raw.lower().endswith(SENSITIVE_SUFFIXES) or pathlib.PurePosixPath(raw).name in ("auth.json", ".env"):
        raise ValueError("secret-looking source path refused")
    path = ROOT
    for component in parts:
        path /= component
        try:
            info = path.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode):
            raise ValueError("symlinks are not accepted")
    if not directory and raw in ALLOWED:
        raise ValueError("expected file rather than directory")
    return path

def list_files(path):
    if path in ("", "."):
        return {"entries": [{"name": n, "directory": n in ALLOWED}
                            for n in ROOT_FILES + CONFIG_FILES + ALLOWED]}
    p = safe_path(path, directory=True)
    if not p.is_dir():
        raise ValueError("not an approved directory")
    out = []
    for e in sorted(p.iterdir(), key=lambda x: x.name):
        child = path + "/" + e.name
        try:
            safe_path(child, directory=True)
        except ValueError:
            continue
        out.append({"name": e.name, "directory": e.is_dir()})
        if len(out) == 150:
            break
    return {"entries": out}

def read_file(path):
    p = safe_path(path)
    st = p.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_size > MAX_FILE:
        raise ValueError("not a regular file or too large")
    data = p.read_bytes()
    if len(data) > MAX_FILE:
        raise ValueError("file too large")
    return {"path": path, "content": data.decode("utf-8")}

def write_file(path, content):
    p = safe_path(path)
    if not isinstance(content, str) or len(content.encode("utf-8")) > MAX_FILE:
        raise ValueError("text exceeds 1 MiB")
    if not p.parent.is_dir():
        raise ValueError("create parent directory through reviewed source change first")
    if p.exists() and (not stat.S_ISREG(p.lstat().st_mode) or p.stat().st_size > MAX_FILE):
        raise ValueError("existing file is unsafe or too large")
    fd, tmp = tempfile.mkstemp(prefix=".panolab-", dir=p.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(content.encode("utf-8"))
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, (p.stat().st_mode & 0o777) if p.exists() else 0o644)
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return {"written": path, "bytes": len(content.encode("utf-8"))}

def status():
    current = git("symbolic-ref", "--quiet", "--short", "HEAD")
    head = git("rev-parse", "--verify", "HEAD")
    dirty = git("status", "--porcelain=v1", "--untracked-files=normal")
    return {"branch": current["stdout"].strip() if current["ok"] else "(detached)",
            "head": head["stdout"].strip() if head["ok"] else None,
            "clean": dirty["ok"] and dirty["stdout"] == "",
            "changes": dirty["stdout"][:12000],
            "git_error": dirty["stderr"] if not dirty["ok"] else "",
            "root": "existing laptop clone"}

def sync():
    branch_ok()
    origin_ok()
    dirty = git("status", "--porcelain=v1", "--untracked-files=normal")
    if not dirty["ok"]:
        return {"ok": False, "reason": "git status failed", "details": dirty["stderr"]}
    if dirty["stdout"]:
        return {"ok": False, "reason": "local checkout contains changes; refusing pull",
                "changes": dirty["stdout"][:8000]}
    # Only fetch the exact current approved branch; never reset local work.
    fetched = git("fetch", "--no-tags", "origin", branch_ok(), timeout=120)
    if not fetched["ok"]:
        return {"ok": False, "reason": "fetch failed; no local changes made",
                "details": fetched["stderr"]}
    fast_forward = git("merge-base", "--is-ancestor", "HEAD", "FETCH_HEAD")
    if not fast_forward["ok"]:
        return {"ok": False, "reason": "branches diverged; refusing merge"}
    merged = git("merge", "--ff-only", "FETCH_HEAD", timeout=90)
    return {"ok": merged["ok"], "result": merged["stdout"][-8000:],
            "error": merged["stderr"] if not merged["ok"] else "",
            "head": git("rev-parse", "HEAD")["stdout"].strip()}

def commit(paths, message):
    branch_ok()
    if not isinstance(paths, list) or not 1 <= len(paths) <= 20:
        raise ValueError("choose between 1 and 20 approved paths")
    checked = [str(safe_path(p)) for p in paths]
    if any(pathlib.Path(p).is_dir() for p in checked):
        raise ValueError("commit requires explicit files, not whole directories")
    if len(set(checked)) != len(checked):
        raise ValueError("duplicate path")
    if not isinstance(message, str) or not 3 <= len(message) <= MAX_MESSAGE or "\n" in message:
        raise ValueError("invalid commit message")
    staged = git("diff", "--cached", "--name-only")
    if not staged["ok"] or staged["stdout"]:
        raise ValueError("existing staged changes; refusing to mix unrelated work")
    added = git("add", "--", *paths)
    if not added["ok"]:
        return {"ok": False, "reason": "git add failed", "details": added["stderr"]}
    changed = git("diff", "--cached", "--name-only")
    if not changed["ok"] or not changed["stdout"]:
        return {"ok": False, "reason": "no changes to commit"}
    selected = set(paths)
    if not all(p in selected for p in changed["stdout"].splitlines()):
        raise ValueError("unexpected staged paths; refusing commit")
    result = git("-c", "user.name=PanoLab Direct", "-c",
                 "user.email=panolab-direct@users.noreply.github.com",
                 "commit", "-m", message, timeout=60)
    return {"ok": result["ok"], "message": result["stdout"][-4000:],
            "error": result["stderr"] if not result["ok"] else "",
            "head": git("rev-parse", "HEAD")["stdout"].strip()}

def push():
    branch_ok()
    origin_ok()
    # The ordinary publishing path uses the connected GitHub integration,
    # not credentials in this gateway. Direct push works only if explicitly
    # configured with separately approved, narrowly scoped authentication.
    check = git("status", "--porcelain=v1")
    if not check["ok"] or check["stdout"]:
        raise ValueError("checkout must be clean before push")
    return git("push", "origin", "HEAD:refs/heads/" + branch_ok(), timeout=120)

def dispatch(r):
    op = r.get("action")
    if op == "status": return status()
    if op == "list": return list_files(r.get("path", ""))
    if op == "read": return read_file(r.get("path"))
    if op == "write": return write_file(r.get("path"), r.get("content"))
    if op == "sync": return sync()
    if op == "commit": return commit(r.get("paths"), r.get("message"))
    if op == "push": return push()
    raise ValueError("operation not allowlisted")

def handle(c):
    with c:
        try:
            c.settimeout(180)
            data = b""
            while not data.endswith(b"\n"):
                part = c.recv(8192)
                if not part: return
                data += part
                if len(data) > MAX_FILE + 4096:
                    raise ValueError("request too large")
            with mutex:
                result = dispatch(json.loads(data))
        except Exception as exc:
            result = {"ok": False, "error": str(exc)[:300]}
        c.sendall((json.dumps(result) + "\n").encode())

if not (ROOT / ".git").is_dir():
    raise SystemExit("expected existing local Git clone mounted at /repo")
os.makedirs("/repo-rpc", exist_ok=True)
if os.path.exists(SOCKET): os.unlink(SOCKET)
s = socket.socket(socket.AF_UNIX)
s.bind(SOCKET)
os.chmod(SOCKET, 0o600)
s.listen(8)
while True:
    conn, _ = s.accept()
    threading.Thread(target=handle, args=(conn,), daemon=True).start()
