"""Detached Codex jobs for the rootless development container."""

import argparse
import datetime
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import uuid

WORKSPACE = Path("/workspace")
REPO = Path("/repo")
POLICY = REPO / "AGENTS.md"
MAX_INPUT = 1024 * 1024
SCRIPT = Path(__file__).resolve()
JOB_ROOT = SCRIPT.parent / "jobs"
CODEX = ("codex", "exec", "--skip-git-repo-check",
         "--dangerously-bypass-approvals-and-sandbox", "-")
MAX_TAIL_BYTES = 1024 * 1024


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def scoped(path):
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(WORKSPACE):
        raise ValueError("path must resolve inside /workspace")
    return resolved


class Blocked(ValueError):
    def __init__(self, resource, error, step):
        self.details = dict(resource=str(resource), error=str(error),
                            last_step=step, stopped_work="dependent work")
        super().__init__(str(error))


def digest(data):
    return hashlib.sha256(data).hexdigest()


def input_path(path):
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("expected an absolute path without parent traversal")
    if not any(path.is_relative_to(root) for root in (REPO, WORKSPACE)):
        raise ValueError("expected a path inside /repo or /workspace")
    for part in path.parts:
        if part.startswith(".") or re.search(
            r"secret|credential|private|token|password|\.(?:pem|key|p12)$", part, re.I
        ):
            raise ValueError("private or credential path is outside admission scope")
    if path.resolve(strict=True) != path:
        raise ValueError("symlinked inputs are outside admission scope")
    return path


def file_read(path, limit=None, *, atomic_snapshot=False):
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW), "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or not before.st_mode & 0o444:
            raise ValueError("expected a readable regular file")
        if limit is None:
            checksum = hashlib.sha256()
            for chunk in iter(lambda: stream.read(65536), b""):
                checksum.update(chunk)
            result = checksum.hexdigest()
        else:
            result = stream.read(limit + 1)
            if len(result) > limit:
                raise ValueError(f"input exceeds {limit} bytes")
        if not atomic_snapshot:
            if fingerprint(before) != fingerprint(os.fstat(stream.fileno())):
                raise ValueError("file changed during verification")
            if fingerprint(before) != fingerprint(path.stat()):
                raise ValueError("file was replaced during verification")
    return result


def fingerprint(info):
    return [info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns]


def read_text_input(path, limit=MAX_INPUT):
    data = file_read(input_path(path), limit)
    decoded = data.decode("utf-8")
    if not decoded.strip() or "\x00" in decoded:
        raise ValueError("expected nonempty UTF-8 text without NUL bytes")
    return data


def directory(path):
    path = input_path(path)
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if not info.st_mode & 0o444 or not info.st_mode & 0o111 or not os.access(
            path, os.R_OK | os.X_OK, effective_ids=True
        ):
            raise ValueError("directory requires read and search permission")
        return [info.st_dev, info.st_ino, info.st_mode]
    finally:
        os.close(fd)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def declaration(data):
    values = json.loads(data, object_pairs_hook=unique_object)
    if not isinstance(values, dict) or set(values) != {"files", "directories", "executables"}:
        raise ValueError("manifest requires files, directories and executables arrays")
    if any(not isinstance(items, list) or len(items) > 128 for items in values.values()):
        raise ValueError("each prerequisite array permits at most 128 entries")
    for item in values["files"]:
        if (not isinstance(item, dict) or set(item) - {"path", "sha256"}
                or not isinstance(item.get("path"), str) or not item["path"]):
            raise ValueError("file entries require a path and optional sha256")
        if "sha256" in item and (not isinstance(item["sha256"], str)
                                or not re.fullmatch("[a-f0-9]{64}", item["sha256"])):
            raise ValueError("sha256 must contain 64 lowercase hexadecimal digits")
    if any(not isinstance(item, str) or not item for item in values["directories"]):
        raise ValueError("directory entries require path strings")
    if any(not isinstance(item, str) or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.+-]{0,127}", item)
           for item in values["executables"]):
        raise ValueError("executable entries require bare names")
    for entries in ([item["path"] for item in values["files"]],
                    values["directories"], values["executables"]):
        if len(set(entries)) != len(entries):
            raise ValueError("duplicate prerequisite")
    return values


def executable(name):
    # Relative PATH entries could resolve differently in the supervisor and worker.
    search = os.pathsep.join(entry for entry in os.get_exec_path() if os.path.isabs(entry))
    location = shutil.which(name, path=search) if search else None
    if not location:
        raise ValueError("required executable unavailable on absolute PATH")
    path = Path(location).resolve(strict=True)
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or not os.access(path, os.X_OK, effective_ids=True):
        raise ValueError("expected an executable regular file")
    return [str(path), fingerprint(info)]


def admit(workdir, prompt_path, manifest, expected=None):
    checks = {}
    last = "job request received"

    def verify(label, resource, operation):
        nonlocal last
        try:
            value = operation()
            identity = digest(value) if isinstance(value, bytes) else value
            if expected is not None and expected.get(label) != identity:
                raise ValueError("verified input changed since start")
            checks[label] = identity
        except (OSError, ValueError, RuntimeError) as error:
            raise Blocked(resource, error, last) from error
        last = f"verified {label}"
        return value

    policy = verify("policy_sha256", POLICY, lambda: read_text_input(POLICY))
    manifest_data = verify("declaration_sha256", manifest, lambda: read_text_input(manifest, 65536))
    # Parse the exact bytes verified above.
    values = verify("declaration", manifest, lambda: declaration(manifest_data))
    prompt = verify("prompt_sha256", prompt_path, lambda: read_text_input(prompt_path))
    verify("workdir", workdir, lambda: directory(workdir))
    for item in values["files"]:
        path = Path(item["path"])

        def file_digest():
            actual = file_read(input_path(path))
            if "sha256" in item and actual != item["sha256"]:
                raise ValueError(f"expected SHA-256 {item['sha256']}, observed {actual}")
            return actual

        verify(f"file {path}", path, file_digest)
    for entry in values["directories"]:
        verify(f"directory {entry}", entry, lambda: directory(Path(entry)))
    for name in dict.fromkeys(["codex", *values["executables"]]):
        verify(f"executable {name}", name, lambda: executable(name))
    return checks, policy, prompt


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def save_status(job, status):
    with tempfile.NamedTemporaryFile(mode="w", dir=job, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(status, stream)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
            temporary.replace(job / "status.json")
            sync_directory(job)
        finally:
            temporary.unlink(missing_ok=True)


def read_status(job):
    path = job / "status.json"
    try:
        status = json.loads(file_read(path, 8 * MAX_INPUT, atomic_snapshot=True))
        if (not isinstance(status, dict) or status.get("job_id") != job.name
                or status.get("state") not in
                ("running", "succeeded", "failed", "interrupted", "lost")):
            raise ValueError("invalid job status record")
        return status
    except (OSError, ValueError, RecursionError) as error:
        raise Blocked(path, error, "located job directory") from error


def terminal(job, status, state, exit_code=None, reason=None):
    save_status(job, dict(status, state=state, exit_code=exit_code,
                          finished_at=utc_now(), reason=reason))


def job_directory(job_id):
    if not re.fullmatch(r"[0-9a-f]{32}", job_id):
        raise ValueError("invalid job ID")
    job = JOB_ROOT / job_id
    if scoped(job) != job or not job.is_dir():
        raise ValueError("invalid job directory")
    return job


VERDICT_INSTRUCTIONS = b"""
End your final response with a single JSON object on its own last line.
Use {"outcome":"COMPLETED"} or {"outcome":"ENGINEERING_BLOCKED"} for engineering
outcomes, or {"outcome":"INFRASTRUCTURE_BLOCKED","resource":"...","error":"...",
"last_step":"...","stopped_work":"..."} on one line for an infrastructure blocker.
Use {"outcome":"PASS"} only for an explicitly assigned gate whose acceptance
criteria were verified. Include evidence in the preceding text. Redact secrets.
"""


def instructions(policy, prompt):
    return policy + b"\n\n" + VERDICT_INSTRUCTIONS + b"\nJob instructions\n" + prompt


def verdict(path):
    data = file_read(path, MAX_INPUT).decode("utf-8")
    lines = data.rstrip().splitlines()
    if not lines:
        raise ValueError("missing final verdict")
    result = json.loads(lines[-1], object_pairs_hook=unique_object)
    if not isinstance(result, dict):
        raise ValueError("final verdict must be a JSON object")
    outcome = result.get("outcome")
    if outcome == "INFRASTRUCTURE_BLOCKED":
        fields = {"resource", "error", "last_step", "stopped_work"}
        if set(result) != fields | {"outcome"} or any(
            not isinstance(result[key], str) or not result[key].strip() for key in fields
        ):
            raise ValueError("infrastructure verdict requires blocker details")
        return None, {key: result[key] for key in sorted(fields)}
    if set(result) != {"outcome"} or outcome not in ("COMPLETED", "ENGINEERING_BLOCKED", "PASS"):
        raise ValueError("invalid engineering outcome")
    return outcome, None


def start(workdir, prompt_file, manifest):
    checks, policy, prompt = admit(workdir, prompt_file, manifest)
    JOB_ROOT.mkdir(mode=0o700, exist_ok=True)
    if scoped(JOB_ROOT) != JOB_ROOT:
        raise ValueError("invalid job store")
    sync_directory(JOB_ROOT.parent)

    job_id = uuid.uuid4().hex
    job = JOB_ROOT / job_id
    job.mkdir(mode=0o700)
    sync_directory(JOB_ROOT)
    fd = os.open(job / "prompt.txt", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
    with os.fdopen(fd, "wb") as stream:
        stream.write(instructions(policy, prompt))
        stream.flush()
        os.fsync(stream.fileno())

    lock = os.open(job / "supervisor.lock", os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX)
        status = dict(job_id=job_id, workdir=str(workdir), state="running",
                      created_at=utc_now(), started_at=None, finished_at=None,
                      exit_code=None, reason=None, engineering_outcome=None,
                      infrastructure_verdict=None, infrastructure_blocker=None,
                      policy_sha256=checks["policy_sha256"], admission=checks,
                      prompt_source=str(prompt_file), prerequisite_manifest=str(manifest))
        fd = os.open(job / "codex.log", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as log:
            save_status(job, status)
            try:
                subprocess.Popen(
                    [sys.executable, str(SCRIPT), "_supervise", job_id, str(lock)],
                    stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                    cwd=SCRIPT.parent, start_new_session=True, pass_fds=(lock,),
                )
            except OSError as error:
                blocker = Blocked(SCRIPT, error, "saved admission record")
                terminal(job, blocked_status(status, blocker.details), "interrupted",
                         reason="supervisor_start_failed")
                blocker.details["job_id"] = job_id
                raise blocker from error
    finally:
        # Closing preserves the lock on the supervisor's inherited descriptor.
        os.close(lock)
    return job_id


def blocked_status(status, details):
    return dict(status, infrastructure_verdict="INFRASTRUCTURE_BLOCKED",
                infrastructure_blocker=details)


def supervise(job_id, lock):
    job = job_directory(job_id)
    try:
        status = read_status(job)
        resource = job / "status.json"
        last = "read job status"
        report = job / "final-message.txt"
        try:
            if not isinstance(status["admission"], dict):
                raise ValueError("missing or malformed admission record")
            workdir = Path(status["workdir"])
            checks, policy, prompt = admit(
                workdir, Path(status["prompt_source"]), Path(status["prerequisite_manifest"]),
                expected=status["admission"],
            )
            resource = job / "prompt.txt"
            with os.fdopen(os.open(resource, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW),
                           "rb") as snapshot:
                if not stat.S_ISREG(os.fstat(snapshot.fileno()).st_mode):
                    raise ValueError("stored instructions must be a regular file")
                assembled = instructions(policy, prompt)
                if snapshot.read(len(assembled) + 1) != assembled:
                    raise ValueError("stored instructions differ from verified inputs")
                snapshot.seek(0)
                resource = checks["executable codex"][0]
                last = "reverified admission and stored instructions"
                status["started_at"] = utc_now()
                save_status(job, status)
                command = [resource, *CODEX[1:-1], "--output-last-message", str(report), "-"]
                process = subprocess.Popen(command, stdin=snapshot, cwd=workdir)
        except (OSError, ValueError, KeyError, TypeError) as error:
            blocker = error if isinstance(error, Blocked) else Blocked(resource, error, last)
            terminal(job, blocked_status(status, blocker.details), "interrupted",
                     reason="codex_start_failed")
            return
        exit_code = process.wait()
        state = "succeeded" if exit_code == 0 else "failed"
        reason = None
        try:
            os.fsync(sys.stdout.fileno())
        except OSError as error:
            status = blocked_status(status, Blocked(job / "codex.log", error,
                                                    "collected Codex exit code").details)
            terminal(job, status, state, exit_code, "log_sync_failed")
            return
        try:
            outcome, blocker = verdict(report)
            status["engineering_outcome"] = outcome
            if blocker:
                status = blocked_status(status, blocker)
                reason = "worker_infrastructure_blocked"
        except (OSError, ValueError, RecursionError) as error:
            status = blocked_status(status, Blocked(report, error, "synced worker log").details)
            reason = "invalid_or_missing_worker_verdict"
        terminal(job, status, state, exit_code, reason)
    finally:
        os.close(lock)


def status_for(job):
    lock_path = job / "supervisor.lock"
    try:
        lock = os.open(lock_path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as error:
        raise Blocked(lock_path, error, "located job directory") from error
    try:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            if error.errno not in (errno.EACCES, errno.EAGAIN):
                raise Blocked(lock_path, error, "opened supervisor lock") from error
            return read_status(job)
        status = read_status(job)
        if status["state"] == "running":
            lost = dict(status, state="lost", reason="supervisor_exited_without_result")
            return blocked_status(lost, Blocked(
                job / "supervisor.lock", "supervisor exited without recording a result",
                "read last stored job status",
            ).details)
        return status
    finally:
        os.close(lock)


def tail(job, byte_count):
    if not 1 <= byte_count <= MAX_TAIL_BYTES:
        raise ValueError("tail size must be between 1 and 1048576 bytes")
    with (job / "codex.log").open("rb") as log:
        end = log.seek(0, os.SEEK_END)
        log.seek(max(0, end - byte_count))
        data = log.read(min(end, byte_count))
    with tempfile.NamedTemporaryFile(dir=job, prefix="tail-", suffix=".log",
                                     delete=False) as snapshot:
        snapshot.write(data)
    return {"tail_file": snapshot.name, "bytes": len(data)}


def main():
    # Internal supervisor entry point receives the inherited lock descriptor.
    if len(sys.argv) == 4 and sys.argv[1] == "_supervise":
        try:
            supervise(sys.argv[2], int(sys.argv[3]))
        except (OSError, ValueError) as error:
            blocker = error if isinstance(error, Blocked) else Blocked(
                "supervisor", error, "received supervisor request"
            )
            print("INFRASTRUCTURE_BLOCKED " + json.dumps(
                dict(blocker.details, job_id=sys.argv[2])
            ), file=sys.stderr)
            return 2
        return 0

    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    launch = commands.add_parser("start")
    launch.add_argument("--workdir", type=Path)
    launch.add_argument("--prompt-file", type=Path)
    launch.add_argument("--prerequisites", type=Path)
    for name in ("status", "result", "tail"):
        command = commands.add_parser(name)
        command.add_argument("job_id")
        if name == "tail":
            command.add_argument("--bytes", type=int, default=8192)
    args = parser.parse_args()
    resource = JOB_ROOT
    last = "parsed launcher request"
    try:
        if args.command == "start":
            for name, value in (("--workdir", args.workdir), ("--prompt-file", args.prompt_file),
                                ("--prerequisites", args.prerequisites)):
                if value is None:
                    raise Blocked(name, "required start argument is missing", last)
            print(start(args.workdir, args.prompt_file, args.prerequisites))
        else:
            resource = JOB_ROOT / args.job_id
            job = job_directory(args.job_id)
            resource = job / ("codex.log" if args.command == "tail" else "status.json")
            result = tail(job, args.bytes) if args.command == "tail" else status_for(job)
            if args.command == "tail":
                result["job_id"] = args.job_id
            else:
                result.pop("workdir", None)
                for key in ("admission", "prompt_source", "prerequisite_manifest"):
                    result.pop(key, None)
                if args.command == "result":
                    result["log_file"] = "codex.log"
            if result.get("infrastructure_verdict") == "INFRASTRUCTURE_BLOCKED":
                print("INFRASTRUCTURE_BLOCKED " + json.dumps(
                    dict(result["infrastructure_blocker"], job_id=args.job_id)
                ), file=sys.stderr)
                print(json.dumps(result))
                return 2
            print(json.dumps(result))
    except (OSError, ValueError) as error:
        blocker = error if isinstance(error, Blocked) else Blocked(resource, error, last)
        print("INFRASTRUCTURE_BLOCKED " + json.dumps(blocker.details), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
