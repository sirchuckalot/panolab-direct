#!/usr/bin/env python3
"""One-time owner-local migration of the inventoried PanoLab storage."""
import argparse
import ctypes
import fcntl
import json
import os
import stat
from pathlib import Path
import platform
import subprocess
import sys
import tempfile

from storage_paths import check_path, provisioned_roots

ARCHIVE = "Xilinx_ISE_DS_Lin_14.7_1015_1.tar"
FILES = (".env", "Xilinx.lic", "mcp-bearer", "tunnel-api-key", ARCHIVE)
CONFIG = (*FILES[:-1], "codex-auth", "github-git-auth")
DATA = ("Xilinx", "ise-work", "agent-workspace", "repo-rpc", "sync-backups", ARCHIVE)
JOURNAL = ".storage-migration.json"
LOCK = ".storage-migration.lock"


def sync_directory(path):
    fd = os.open(path, os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_journal(path, record):
    # A crash during this write leaves the previous journal intact.
    # Use a distinct temp file and remove it in normal error paths.
    fd, filename = tempfile.mkstemp(prefix=".storage-journal-", dir=path.parent)
    tmp = Path(filename)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(record, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
        sync_directory(path.parent)
    finally:
        tmp.unlink(missing_ok=True)


def inventory(repo, config, data, resumed):
    docker = repo / "docker"
    legacy = docker / "private"
    device = docker.stat().st_dev
    if docker.resolve() != docker:
        raise ValueError("Unsafe source parent")
    for path in (config, data):
        if path.stat().st_dev != device:
            raise ValueError("External storage must be on the same filesystem")
    plan = [(docker / ".env" if name == ".env" else legacy / name, root / name)
            for root, names in ((config, CONFIG), (data, DATA)) for name in names]
    for folder, known in ((config, {*CONFIG, JOURNAL, LOCK}), (data, set(DATA)),
                          (legacy, set(CONFIG + DATA) - {".env"})):
        if folder == legacy and not os.path.lexists(folder) and resumed:
            continue
        info = check_path(folder, 0o700, True)
        found = {p.name for p in folder.iterdir()}
        if folder == config:
            for name in found - known:
                if name.startswith(".storage-journal-"):
                    check_path(folder / name, 0o600)
                    known.add(name)
        if info.st_dev != device or found - known:
            raise ValueError("Unexpected migration directory contents or device")
    positions = {}
    for old, new in plan:
        name = new.name
        old_present, new_present = map(os.path.lexists, (old, new))
        if old_present == new_present or (new_present and not resumed):
            raise ValueError("Missing or conflicting migration entry")
        mode = 0o664 if name == ARCHIVE else 0o600 if name in FILES else 0o700
        info = check_path(new if new_present else old, mode, name not in FILES)
        if info.st_dev != device:
            raise ValueError("Migration entry is on a different device")
        positions[name] = [info.st_dev, info.st_ino, new_present]
    return plan, positions


def rename_without_replacement(source, destination):
    libc = ctypes.CDLL(None, use_errno=True)
    # Linux AT_FDCWD and RENAME_NOREPLACE.
    arguments = (-100, os.fsencode(source), -100, os.fsencode(destination), 1)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is not None:
        result = renameat2(*arguments)
    elif platform.machine() == "x86_64":
        # Alpine's musl may lack the libc wrapper for this Linux syscall.
        result = libc.syscall(316, *arguments)
    else:
        raise RuntimeError("Linux atomic non-replacing rename unavailable")
    if result:
        errno = ctypes.get_errno()
        raise OSError(errno, os.strerror(errno))


class ISEAdmissionError(ValueError):
    """Admission failure with a message safe for operator logs."""


def require_terminal_ise_jobs(work):
    def unique_fields(pairs):
        fields = {}
        for key, value in pairs:
            if key in fields:
                raise ValueError("Duplicate JSON field")
            fields[key] = value
        return fields

    def require_terminal(path, phase, terminal, *, setup=False):
        try:
            info = path.lstat()
        except FileNotFoundError:
            if setup:
                return  # No setup state has been persisted.
            raise ISEAdmissionError(f"{phase}: missing record") from None
        except OSError:
            raise ISEAdmissionError(f"{phase}: cannot inspect record") from None
        try:
            if (not stat.S_ISREG(info.st_mode) or path.resolve() != path
                    or info.st_size > 16384):
                raise ISEAdmissionError(f"{phase}: unsafe record path, type, or size")
            raw = path.read_text(encoding="utf-8")
        except (OSError, RuntimeError):
            raise ISEAdmissionError(f"{phase}: cannot read record") from None
        except UnicodeError:
            raise ISEAdmissionError(f"{phase}: invalid UTF-8") from None
        try:
            record = json.loads(raw, object_pairs_hook=unique_fields)
        except (ValueError, RecursionError):
            raise ISEAdmissionError(f"{phase}: invalid JSON or duplicate fields") from None
        if not isinstance(record, dict):
            raise ISEAdmissionError(f"{phase}: expected a JSON object")
        key = "state"
        if setup and "State" in record:
            if "state" in record:
                raise ISEAdmissionError(f"{phase}: ambiguous State and state fields")
            key = "State"
        if key not in record:
            raise ISEAdmissionError(f"{phase}: missing state field")
        if not isinstance(record[key], str):
            raise ISEAdmissionError(f"{phase}: state field must be a string")
        if record[key] not in terminal:
            raise ISEAdmissionError(f"{phase}: nonterminal or unknown state")

    require_terminal(work / "install-state.json", "ISE setup state (install-state.json)",
                     {"succeeded", "failed", "not_started"}, setup=True)
    jobs = work / "worker/results/jobs"
    try:
        info = jobs.lstat()
    except FileNotFoundError:
        return  # An unused worker may have no results directory.
    except OSError:
        raise ISEAdmissionError("ISE worker job inventory: cannot inspect directory") from None
    try:
        if not stat.S_ISDIR(info.st_mode) or jobs.resolve() != jobs:
            raise ISEAdmissionError("ISE worker job inventory: unsafe directory")
        job_dirs = list(jobs.iterdir())
    except (OSError, RuntimeError):
        raise ISEAdmissionError("ISE worker job inventory: cannot list directory") from None
    for job in job_dirs:
        require_terminal(job / "job.json", "ISE worker job (job.json)",
                         {"succeeded", "failed", "cancelled", "interrupted"})


def migrate(repo, config, data, direction, rename=rename_without_replacement):
    journal = config / JOURNAL
    legacy = repo / "docker/private"
    resumed = os.path.lexists(journal)
    plan, positions = inventory(repo, config, data, resumed)
    work = (data if positions["ise-work"][2] else legacy) / "ise-work"
    require_terminal_ise_jobs(work)
    if resumed:
        check_path(journal, 0o600)
        record = json.loads(journal.read_text())
        if record["roots"] != [str(p) for p in (repo, config, data)] or record["entries"] != {
            name: position[:2] for name, position in positions.items()
        }:
            raise ValueError("Migration journal identity mismatch")
        completed = set(record["completed"])
        pending = record["pending"]
        moved = {name for name, position in positions.items() if position[2]}
        if completed != moved:  # reconcile a rename interrupted before its journal update
            if not pending or completed ^ moved != {pending}:
                raise ValueError("Unexpected migration state")
        record.update(completed=sorted(moved), pending=None)
    else:
        if direction == "rollback":
            raise ValueError("No migration journal")
        record = {"roots": [str(p) for p in (repo, config, data)],
                  "entries": {name: pos[:2] for name, pos in positions.items()},
                  "completed": [], "pending": None}

    if direction == "dry-run":
        return len(plan)
    write_journal(journal, record)
    forward = direction == "apply"
    if not forward and not legacy.exists():
        legacy.mkdir(mode=0o700)
        sync_directory(legacy.parent)
    try:
        for old, new in plan if forward else reversed(plan):
            name = new.name
            if positions[name][2] == forward:
                continue
            src, dst = (old, new) if forward else (new, old)
            record["pending"] = name
            write_journal(journal, record)
            if os.path.lexists(dst):
                raise ValueError("Migration destination appeared")
            rename(src, dst)
            for parent in (src.parent, dst.parent):
                sync_directory(parent)
            completed = set(record["completed"])
            completed.symmetric_difference_update({name})
            record.update(completed=sorted(completed), pending=None)
            write_journal(journal, record)
        if forward and legacy.exists():
            legacy.rmdir()
            sync_directory(legacy.parent)
    except (OSError, ValueError, RuntimeError):
        if forward:
            migrate(repo, config, data, "rollback", rename=rename)
        raise
    return len(plan)


def require_quiescence(repo, config, data):
    runtime = os.getenv("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    cli = ["docker", "-H", f"unix://{runtime}/docker.sock"]

    def query(*args):
        return subprocess.check_output(cli + list(args), stderr=subprocess.DEVNULL,
                                       text=True, timeout=20).strip()

    if '"name=rootless"' not in query("info", "--format", "{{json .SecurityOptions}}"):
        raise ValueError("Rootless Engine required")
    roots = (repo, config, data)
    for container_id in query("ps", "-q").splitlines():
        mounts = json.loads(query("inspect", "--format", "{{json .Mounts}}", container_id))
        for mount in mounts:
            if mount.get("Type") != "bind":
                continue
            source = Path(mount["Source"]).resolve()
            if any(source.is_relative_to(root) or root.is_relative_to(source) for root in roots):
                raise ValueError("A running container still binds affected storage")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("dry-run", "apply", "rollback"))
    parser.add_argument("--checkout", type=Path,
                        help="Read-only dry-run against the canonical checkout before cutover.")
    parser.add_argument("--jobs-drained", action="store_true",
                        help="Confirm that clients are disconnected and all jobs are terminal.")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    os.umask(0o077)
    sys.dont_write_bytecode = True
    try:
        if os.getuid() == 0:
            raise ValueError("Run as the ordinary owner")
        if args.checkout is not None:
            if (args.action != "dry-run" or not args.checkout.is_absolute() or
                    args.checkout.resolve() != args.checkout or not (args.checkout / ".git").is_dir()):
                raise ValueError("Expected absolute canonical checkout for dry-run")
            repo = args.checkout
        config, data = provisioned_roots(repo)
        if args.action == "dry-run":
            count = migrate(repo, config, data, args.action)
        else:
            if not args.jobs_drained:
                raise ValueError("Drain jobs and block new submissions first")
            fd = os.open(config / LOCK, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "r+") as lock:
                check_path(config / LOCK, 0o600)
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                require_quiescence(repo, config, data)
                count = migrate(repo, config, data, args.action)
        print(f"PANOLAB_STORAGE_MIGRATION={args.action} entries={count}")
    except ISEAdmissionError as error:
        print(f"PANOLAB_STORAGE_MIGRATION_BLOCKED phase=ise-admission {error}", file=sys.stderr)
        return 9
    except (KeyError, TypeError, OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        # Exception paths and subprocess diagnostics may contain private names.
        print(f"PANOLAB_STORAGE_MIGRATION_BLOCKED={type(error).__name__}", file=sys.stderr)
        return 9
    return 0


if __name__ == "__main__":
    sys.exit(main())
