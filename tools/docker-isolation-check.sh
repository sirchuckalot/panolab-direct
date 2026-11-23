#!/usr/bin/env bash
# Read-only laptop preflight for proposed PanoLab Docker-only deployment.
# Does not install Docker, create containers, change contexts, or touch hardware.
set -euo pipefail

usage() { printf '%s\n' 'Usage: bash ./tools/docker-isolation-check.sh [--check|--help]'; }
mode="${1:---check}"
if [[ $# -gt 1 ]]; then usage >&2; exit 2; fi
case "$mode" in
  --check) ;;
  --help|-h) usage; exit 0 ;;
  *) usage >&2; exit 2 ;;
esac
if [[ "$(id -u)" == 0 ]]; then
  echo 'BLOCKED: run as your ordinary laptop user, not root.' >&2
  exit 2
fi
if [[ "$(uname -s)" != Linux || "$(uname -m)" != x86_64 ]]; then
  echo 'BLOCKED: current legacy ISE deployment requires Linux x86_64.' >&2
  exit 3
fi
if ! command -v docker >/dev/null 2>&1; then
  echo 'BLOCKED: Docker CLI is missing; no host packages installed.' >&2
  exit 4
fi
if ! docker compose version >/dev/null 2>&1; then
  echo 'BLOCKED: Docker Compose plugin is missing.' >&2
  exit 5
fi
if ! options="$(docker info --format '{{json .SecurityOptions}}' 2>/dev/null)"; then
  echo 'BLOCKED: Docker daemon is unavailable.' >&2
  exit 6
fi
case "$options" in
  *'"name=rootless"'*|*'"rootless"'*) ;;
  *)
    echo 'BLOCKED: Docker daemon does not report rootless mode.' >&2
    exit 10 ;;
esac
# A local per-user Unix socket is the only approved first-release endpoint.
# Do not silently connect to rootful, remote TCP/SSH, or ambiguous daemons.
if [[ -n "${DOCKER_HOST:-}" && -n "${DOCKER_CONTEXT:-}" ]]; then
  echo 'BLOCKED: both DOCKER_HOST and DOCKER_CONTEXT are set.' >&2
  exit 11
fi
if [[ -n "${DOCKER_HOST:-}" ]]; then
  endpoint="$DOCKER_HOST"
elif ! endpoint="$(docker context inspect --format '{{.Endpoints.docker.Host}}' 2>/dev/null)"; then
  echo 'BLOCKED: cannot verify selected Docker context.' >&2
  exit 11
fi
uid="$(id -u)"
if [[ "$endpoint" != "unix:///run/user/${uid}/docker.sock" ]]; then
  echo "BLOCKED: expected this user's local rootless Docker Unix socket." >&2
  echo 'No installation is authorized through the selected endpoint.' >&2
  exit 11
fi
# Rootless without systemd-delegated cgroup v2 cannot reliably enforce the
# CPU/RAM/PID quotas expected to protect the owner's daily driver.
if ! cgroups="$(docker info --format '{{.CgroupVersion}} {{.CgroupDriver}}' 2>/dev/null)"; then
  echo 'BLOCKED: unable to inspect cgroup isolation capabilities.' >&2
  exit 12
fi
if [[ "$cgroups" != "2 systemd" ]]; then
  echo 'BLOCKED: rootless daemon lacks systemd cgroup v2 delegation.' >&2
  echo 'Required CPU/RAM/PID quotas cannot be assumed on this host.' >&2
  exit 12
fi
printf '%s\n' 'PASS: local rootless Docker daemon and Compose detected.'
printf '%s\n' 'READ-ONLY CHECK ONLY: actual CPU/memory quota enforcement, mounts, ISE, Etherbone and installation remain UNVERIFIED.'
