#!/usr/bin/env python3
"""Read-only admission check for a genuinely new PanoLab Linux laptop.

Checks host prerequisites WITHOUT installing Docker, starting a service,
touching the rootful Engine, downloading vendor media, or reading secrets.
A READY result is prerequisite readiness, never deployment acceptance.
"""
from __future__ import annotations

import os
import platform
import pwd
import shutil
import socket
import stat
import subprocess
import sys
from pathlib import Path

CHECK_NAMES = (
    "linux_x86_64", "non_root_user", "git_checkout",
    "git_cli", "bash", "python3", "docker_cli", "docker_compose_v2",
    "docker_buildx", "newuidmap", "newgidmap", "unprivileged_userns",
    "subordinate_uids", "subordinate_gids", "user_runtime_directory",
    "user_systemd", "rootless_docker_engine", "systemd_cgroups_v2",
    "rootless_start_path", "private_env_and_directory",
    "tunnel_api_key", "mcp_bearer", "xilinx_license",
    "ise_archive", "owner_workspaces",
)


def succeeds(*args: str, environment: dict | None = None) -> bool:
    try:
        return subprocess.run(
            list(args), capture_output=True, timeout=8,
            env=environment, check=False,
        ).returncode == 0
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return False


def output(*args: str, environment: dict | None = None) -> str:
    try:
        p = subprocess.run(
            list(args), capture_output=True, text=True, timeout=8,
            env=environment, check=False,
        )
        return p.stdout.strip()[:8192] if p.returncode == 0 else ""
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return ""


def subid_exists(kind: str, username: str) -> bool:
    try:
        for line in Path("/etc/" + kind).read_text().splitlines():
            fields = line.split(":")
            if len(fields) == 3 and fields[0] == username and int(fields[2]) >= 65536:
                return True
    except (OSError, ValueError):
        pass
    return False


def private_regular(path: Path) -> bool:
    try:
        info = path.lstat()
        return stat.S_ISREG(info.st_mode) and info.st_size > 0
    except OSError:
        return False


def scan(root: Path, home: Path | None = None) -> dict[str, bool]:
    """All checks are read-only. Never print input paths or secret contents."""
    home = home if home is not None else Path.home()
    uid = os.geteuid()
    result: dict[str, bool] = {}
    result["linux_x86_64"] = platform.system() == "Linux" and platform.machine() == "x86_64"
    result["non_root_user"] = uid != 0
    result["git_checkout"] = (root / ".git").is_dir()
    for name, binary in (
        ("git_cli", "git"), ("bash", "bash"), ("python3", "python3"),
        ("docker_cli", "docker"), ("newuidmap", "newuidmap"),
        ("newgidmap", "newgidmap"),
    ):
        result[name] = shutil.which(binary) is not None
    result["docker_compose_v2"] = result["docker_cli"] and succeeds("docker", "compose", "version")
    result["docker_buildx"] = result["docker_cli"] and succeeds("docker", "buildx", "version")
    try:
        result["unprivileged_userns"] = Path("/proc/sys/kernel/unprivileged_userns_clone").read_text().strip() == "1"
    except OSError:
        result["unprivileged_userns"] = False
    try:
        username = pwd.getpwuid(uid).pw_name
    except KeyError:
        username = ""
    result["subordinate_uids"] = bool(username) and subid_exists("subuid", username)
    result["subordinate_gids"] = bool(username) and subid_exists("subgid", username)
    runtime = Path(os.environ.get("XDG_RUNTIME_DIR", "/run/user/" + str(uid)))
    try:
        runtime_info = runtime.stat()
        result["user_runtime_directory"] = (
            stat.S_ISDIR(runtime_info.st_mode) and runtime_info.st_uid == uid
        )
    except OSError:
        result["user_runtime_directory"] = False
    result["user_systemd"] = shutil.which("systemctl") is not None and succeeds(
        "systemctl", "--user", "show-environment"
    )
    docker_socket = runtime / "docker.sock"
    try:
        sock_info = docker_socket.lstat()
        socket_ok = stat.S_ISSOCK(sock_info.st_mode) and sock_info.st_uid == uid
    except OSError:
        socket_ok = False
    info = ""
    if result["docker_cli"] and socket_ok:
        env = os.environ.copy()
        env.pop("DOCKER_CONTEXT", None)
        env["DOCKER_HOST"] = "unix://" + str(docker_socket)
        info = output(
            "docker", "info", "--format",
            "{{json .SecurityOptions}}|{{.CgroupDriver}}|{{.CgroupVersion}}",
            environment=env,
        )
    result["rootless_docker_engine"] = '"name=rootless"' in info
    result["systemd_cgroups_v2"] = result["rootless_docker_engine"] and info.endswith("|systemd|2")
    launcher = home / ".local/libexec/panolab-rootless-29.1.3/dockerd-rootless.sh"
    result["rootless_start_path"] = result["rootless_docker_engine"] or (
        launcher.is_file() and not launcher.is_symlink() and os.access(launcher, os.X_OK)
    )
    private = root / "docker/private"
    env = root / "docker/.env"
    result["private_env_and_directory"] = (
        env.is_file() and not env.is_symlink()
        and private.is_dir() and not private.is_symlink()
    )
    result["tunnel_api_key"] = private_regular(private / "tunnel-api-key")
    result["mcp_bearer"] = private_regular(private / "mcp-bearer")
    result["xilinx_license"] = private_regular(private / "Xilinx.lic")
    archives = []
    if private.is_dir():
        for glob in ("*.tar", "*.tar.gz", "*.tgz", "*.tar.bz2"):
            archives.extend(private.glob(glob))
    result["ise_archive"] = len(archives) == 1 and private_regular(archives[0])
    result["owner_workspaces"] = all(
        (private / name).is_dir() and not (private / name).is_symlink()
        for name in ("agent-workspace", "codex-auth", "repo-rpc")
    )
    assert set(result) == set(CHECK_NAMES)
    return result


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Usage: fresh-host-audit.py <checkout-directory>", file=sys.stderr)
        return 2
    result = scan(Path(argv[1]))
    for name in CHECK_NAMES:
        print(("PASS" if result[name] else "MISSING") + " " + name)
    missing = sum(not value for value in result.values())
    if missing:
        print("FRESH_HOST_PREREQUISITES=BLOCKED missing_count=" + str(missing))
        return 10
    print("FRESH_HOST_PREREQUISITES=READY (deployment NOT tested)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
