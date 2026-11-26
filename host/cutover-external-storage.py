#!/usr/bin/env python3
"""Admit or run the owner-authorized external-storage cutover."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

from storage_paths import check_path, provisioned_roots

SOURCE = Path(__file__).resolve().parents[1]
PREFIX = "panolab-direct-connect-"
DEV = "panolab-direct-dev-1"
WORKER = "panolab-direct-ise14-worker-1"
MAINTENANCE = "panolab-direct-trusted-maintenance"
RUNNING = {PREFIX + role + "-1" for role in ("tunnel", "manager", "docker-broker", "repo-git")}
RUNNING.update((DEV, WORKER, MAINTENANCE))
SETUP = PREFIX + "setup-1"
SERVICE_TAGS = {
    DEV: "panolab-direct-modern:local",
    WORKER: "panolab-direct-ise14-worker:local",
    MAINTENANCE: "panolab-direct-trusted-maintenance:local",
    SETUP: "panolab-direct-ise14-setup:local",
    PREFIX + "manager-1": "panolab-direct-manager:local",
    PREFIX + "docker-broker-1": "panolab-direct-broker:local",
    PREFIX + "repo-git-1": "panolab-direct-repo-git:local",
    PREFIX + "tunnel-1": "ghcr.io/openai/tunnel-client:v0.0.21",
}
INSPECT = "|".join("{{json ." + field + "}}" for field in (
    "Id", "Name", "Image", "State.Status", "HostConfig.RestartPolicy", "Mounts",
))
SHA = r"[0-9a-f]{40}"
DIGEST = r"[0-9a-f]{64}"
IMAGE = "sha256:" + DIGEST


def require(condition, message):
    if not condition:
        raise ValueError(message)


def query(*command):
    # Compose/Git/Docker diagnostic output can include private paths or settings.
    return subprocess.check_output(command, text=True, stderr=subprocess.DEVNULL, timeout=60).rstrip("\n")


def git(run, path, *args):
    return run("git", "--no-optional-locks", "-C", str(path), *args)


def require_checkout(run, path, revision):
    require(path.is_absolute() and path.resolve() == path and (path / ".git").is_dir()
            and not (path / ".git").is_symlink(), "Expected a physical Git checkout")
    require(git(run, path, "rev-parse", "HEAD") == revision, "Checkout revision differs")
    require(not git(run, path, "status", "--porcelain=v1", "--untracked-files=all"),
            "Checkout is dirty")


def inventory(path, digest, excluded_roots):
    require(path.is_absolute() and not any(path.is_relative_to(root) for root in excluded_roots),
            "Store the pinned inventory outside source and storage roots")
    require(check_path(path, 0o600).st_size <= 131072, "Inventory exceeds metadata limit")
    contents = path.read_bytes()
    require(hashlib.sha256(contents).hexdigest() == digest, "Pinned inventory hash differs")
    records = json.loads(contents)["containers"]
    require(len(records) == 12 and RUNNING | {SETUP} <= records.keys(),
            "Inventory must contain the original twelve containers")
    require(len({entry["id"] for entry in records.values()}) == 12, "Duplicate inventory ID")
    for name, entry in records.items():
        require(re.fullmatch(DIGEST, entry["id"]) and re.fullmatch(IMAGE, entry["image_id"])
                and entry["state"] == ("running" if name in RUNNING else "exited"),
                "Invalid inventory identity or state")
    return records


def mount_metadata(mount, repo, sock):
    source = Path(mount["Source"])
    target = mount["Destination"]
    kind = mount["Type"]
    record = {"type": kind, "target": target, "rw": mount["RW"]}
    if kind == "volume":
        require(target in ("/repo/docker/private", "/rpc"), "Unexpected named volume target")
        volume = ("panolab-direct-connect_management-rpc" if target == "/rpc"
                  else "panolab-direct-connect_repo-private-mask")
        require(mount["Name"] == volume, "Unexpected named volume identity")
        record["other_source_class"] = "named-volume"
    elif kind == "bind":
        legacy = repo / "docker/private"
        if source.is_relative_to(legacy):
            record["legacy_private_relative"] = str(source.relative_to(legacy))
        elif source.is_relative_to(repo):
            record["canonical_relative"] = str(source.relative_to(repo))
        else:
            allowed = {"/var/run/docker.sock": sock, "/repo/docker/.env": Path("/dev/null")}
            require(allowed.get(target) == source, "Unexpected external bind source")
            record["other_source_class"] = "external-or-runtime"
    else:
        raise ValueError("Unexpected mount type")
    return record


def verify_engine(run, repo, sock, records, candidates, extra_ids=()):
    def docker(*args):
        return run("docker", "-H", "unix://" + str(sock), *args)

    require('"name=rootless"' in docker("info", "--format", "{{json .SecurityOptions}}")
            and docker("info", "--format", "{{.CgroupDriver}}/{{.CgroupVersion}}") == "systemd/2",
            "Expected systemd cgroups v2 on the owner rootless Engine")
    docker("compose", "version")
    ids = docker("ps", "-aq", "--no-trunc").splitlines()
    require(set(ids) == {entry["id"] for entry in records.values()}.union(extra_ids),
            "Rootless Engine container set differs from the pinned inventory")
    # Decode single JSON fields rather than logging the container environment.
    for name, expected in records.items():
        raw = docker("inspect", "--format", INSPECT, expected["id"])
        decoder = json.JSONDecoder()
        values = []
        for index in range(6):
            value, end = decoder.raw_decode(raw)
            values.append(value)
            require(raw[end:end+1] == ("|" if index < 5 else ""), "Malformed inspection")
            raw = raw[end+1:]
        identity, actual_name, image, state, restart, mounts = values
        require((identity, actual_name, image, state, restart) ==
                (expected["id"], "/" + name, expected["image_id"], expected["state"], expected["restart"]),
                "Container identity, state, image or restart policy differs")
        actual = [mount_metadata(mount, repo, sock) for mount in mounts]
        require(sorted(json.dumps(m, sort_keys=True) for m in actual) ==
                sorted(json.dumps(m, sort_keys=True) for m in expected["mounts"]),
                "Container mount layout differs")
    for name, tag in SERVICE_TAGS.items():
        require(docker("image", "inspect", "--format", "{{.Id}}", tag) == records[name]["image_id"],
                "Preserved service tag differs from its original image")
    for role, (tag, image) in candidates.items():
        installed_tag = "panolab-direct-" + role + ":local"
        require(re.fullmatch(r"panolab-direct-" + role + r":[\w][\w.-]{0,127}", tag)
                and tag != installed_tag and re.fullmatch(IMAGE, image),
                "Expected a separate candidate tag and full image ID")
        require(docker("image", "inspect", "--format", "{{.Id}}", tag) == image,
                "Candidate tag differs from its reviewed image")


def preflight(args, sock, run=query):
    repo = args.checkout
    require(args.baseline != args.target, "Reviewed target must advance development")
    require_checkout(run, repo, args.baseline)
    require(git(run, repo, "symbolic-ref", "--short", "HEAD") == "development",
            "Canonical checkout must be on development")
    require(git(run, repo, "rev-parse", "refs/remotes/origin/development") == args.target,
            "Fetch the reviewed development revision into origin/development before admission")
    git(run, repo, "merge-base", "--is-ancestor", args.baseline, args.target)
    require_checkout(run, SOURCE, args.target)
    run("python3", "-B", str(SOURCE / "docker/control/dev_source.py"), str(SOURCE))
    config, data = provisioned_roots(repo)
    require(not any(config.iterdir()) and not any(data.iterdir()), "External roots must be empty")
    records = inventory(args.inventory, args.inventory_sha256, (repo, SOURCE, config, data))
    verify_engine(run, repo, sock, records,
                  {"broker": args.broker_image, "repo-git": args.repo_git_image})
    try:
        run("python3", "-B", str(SOURCE / "host/migrate-external-storage.py"),
            "dry-run", "--checkout", str(repo))
    except (OSError, subprocess.SubprocessError) as error:
        raise ValueError(f"phase=storage-migration-dry-run {type(error).__name__}") from None


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog="Launch from trusted maintenance after draining jobs. Use a separate, "
               "clean reviewed Git checkout and an owner-only journal directory containing "
               "the pinned inventory. Read the returned supervisor ID with Docker logs. "
               "Use the same pins with --launch --rollback for explicit recovery.",
    )
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--preflight", action="store_true", help="Check owner-local admission only.")
    modes.add_argument("--launch", action="store_true", help="Create and start the isolated supervisor.")
    modes.add_argument("--supervise", action="store_true", help="Run inside the isolated supervisor.")
    parser.add_argument("--reviewed", type=Path, help="Exact host path of the clean reviewed checkout.")
    parser.add_argument("--journal", type=Path, help="Dedicated owner-only journal directory outside both checkouts.")
    parser.add_argument("--config", type=Path, help="Exact external configuration bind.")
    parser.add_argument("--data", type=Path, help="Exact external operational data bind.")
    parser.add_argument("--socket", type=Path, help="Exact host rootless socket bind.")
    parser.add_argument("--client-socket", type=Path, default=Path("/var/run/docker.sock"),
                        help="Rootless Docker socket as seen by the launching maintenance container.")
    parser.add_argument("--supervisor-image", help="Full approved maintenance image ID.")
    parser.add_argument("--transaction", help="32 lowercase hexadecimal digits identifying this transaction.")
    parser.add_argument("--rollback", action="store_true", help="Explicitly roll back the named transaction.")
    parser.add_argument("--checkout", required=True, type=Path)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--inventory-sha256", required=True)
    parser.add_argument("--broker-image", required=True, nargs=2, metavar=("TAG", "ID"))
    parser.add_argument("--repo-git-image", required=True, nargs=2, metavar=("TAG", "ID"))
    parser.add_argument("--jobs-drained", action="store_true", required=True,
                        help="Confirm submissions are blocked and jobs and host writers are quiescent.")
    args = parser.parse_args()
    blocked = "PANOLAB_CUTOVER_PREFLIGHT_BLOCKED" if args.preflight else "PANOLAB_CUTOVER_BLOCKED"
    try:
        require(all(re.fullmatch(SHA, value) for value in (args.baseline, args.target))
                and re.fullmatch(DIGEST, args.inventory_sha256), "Expected full pinned digests")
        if not args.preflight:
            from cutover_remote import launch, supervise
            return launch(sys.modules[__name__], args) if args.launch else supervise(sys.modules[__name__], args)
        uid = os.getuid()
        require(uid != 0 and os.geteuid() == uid, "Run as the ordinary host owner")
        runtime = Path(os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{uid}")
        sock = runtime / "docker.sock"
        info = sock.lstat()
        require(sock.is_absolute() and sock.resolve() == sock and runtime.stat().st_uid == uid
                and info.st_uid == uid and stat.S_ISSOCK(info.st_mode),
                "Expected the owner-user rootless socket")
        os.environ.pop("DOCKER_CONTEXT", None)
        os.environ.pop("DOCKER_HOST", None)
        preflight(args, sock)
    except ValueError as error:
        # JSON decoding errors may echo input fragments. Only our messages are safe.
        message = str(error) if type(error) is ValueError else type(error).__name__
        print(f"{blocked} {message}", file=sys.stderr)
        return 9
    except (KeyError, TypeError, OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"{blocked} {type(error).__name__}", file=sys.stderr)
        return 9
    print("PANOLAB_CUTOVER_PREFLIGHT_READY (read-only)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
