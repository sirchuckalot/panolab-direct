#!/usr/bin/env bash
# Explicit owner-approved PanoLab maintenance: Buildx CLI and exact old dev
# rollback container only. This does not prune images/volumes or touch FPGA/ISE.
set -Eeuo pipefail
umask 077
(( $# == 3 )) || { echo "Usage (internal): finalize-dev-maintenance.sh ROOT ROOTLESS_SOCKET WORKSPACE" >&2; exit 2; }
root="$(realpath -e "$1")"
socket="$2"
workspace="$(realpath -e "$3")"
die() { echo "PANOLAB MAINTENANCE BLOCKED: $*" >&2; exit 9; }
say() { printf 'PanoLab maintenance: %s\n' "$*"; }
[[ "$(id -u)" != 0 && -S "$socket" ]] || die "Ordinary user and rootless Docker socket required."
[[ "$(docker -H "unix://$socket" info --format '{{json .SecurityOptions}}')" == *'"name=rootless"'* ]] ||
    die "Not the owner rootless Docker daemon."
r() { docker -H "unix://$socket" "$@"; }
dev=panolab-direct-dev-1
backup=panolab-direct-dev-1-rollback-20261124T020818Z
tag=panolab-direct-modern:local
[[ "$(r inspect -f '{{.State.Running}}' "$dev")" == true ]] || die "Current development container stopped."
[[ "$(r inspect -f '{{index .Config.Labels "panolab.managed"}}' "$dev")" == true ]] ||
    die "Current dev not PanoLab-managed."
[[ "$(r inspect -f '{{.Image}}' "$dev")" == "$(r image inspect -f '{{.Id}}' "$tag")" ]] ||
    die "Current dev not running accepted modern image."
[[ "$(r image inspect -f '{{index .Config.Labels "org.panolab.litex.recipe"}}' "$tag")" == modern-unified-dev-20261123-v2 ]] ||
    die "Unknown modern image recipe."
[[ "$(r inspect -f '{{range .Mounts}}{{if eq .Destination "/workspace"}}{{.Source}}{{end}}{{end}}' "$dev")" == "$workspace" ]] ||
    die "Unexpected workspace mount."
r exec "$dev" /bin/sh -ec \
    'test -s /opt/panolab/litex/env.sh; command -v riscv64-unknown-elf-gcc; command -v verilator; command -v codex' >/dev/null ||
    die "Modern toolchain validation failed."

# Install/accept only a pinned owner-local Docker CLI plugin (no host package
# change or new Docker image); leave the embedded legacy fallback unused.
bash "$root/host/install-rootless-buildx.sh"
r buildx version >/dev/null || die "Rootless Buildx CLI not available."
# Fail if using an external docker-container builder, which would create
# a seventh service/image. The default docker driver is sufficient here.
r buildx inspect default | grep -Eq '^Driver:[[:space:]]+docker$' ||
    die "Existing rootless default builder must use embedded docker driver."
say "BUILDKIT_DEFAULT_DRIVER=PASS (existing rootless Docker engine)."

if ! r inspect "$backup" >/dev/null 2>&1; then
    say "ROLLBACK_ALREADY_ABSENT=PASS"
else
    [[ "$(r inspect -f '{{.Name}}' "$backup")" == "/$backup" ]] ||
        die "Unexpected backup container name."
    [[ "$(r inspect -f '{{index .Config.Labels "panolab.managed"}}' "$backup")" == true ]] ||
        die "Backup is not PanoLab-managed."
    [[ "$(r inspect -f '{{.State.Running}}' "$backup")" == false ]] ||
        die "Refusing to remove a running rollback container."
    old_image="$(r inspect -f '{{.Image}}' "$backup")"
    new_image="$(r inspect -f '{{.Image}}' "$dev")"
    [[ "$old_image" != "$new_image" ]] ||
        die "Rollback image equals active image, refusing deletion."
    [[ "$(r inspect -f '{{range .Mounts}}{{if eq .Destination "/workspace"}}{{.Source}}{{end}}{{end}}' "$backup")" == "$workspace" ]] ||
        die "Rollback workspace differs; refusing deletion."
    [[ "$(r inspect -f '{{.Config.WorkingDir}}' "$backup")" == /workspace ]] ||
        die "Unexpected rollback container workdir."
    # Only exact stopped container object. Docker rm (no -v) leaves all bind
    # mounts, persistent files, images and Docker volumes unchanged.
    r container rm "$backup" >/dev/null
    if r container inspect "$backup" >/dev/null 2>&1; then
        die "Rollback container still exists after removal."
    fi
    say "ROLLBACK_CONTAINER_REMOVED=PASS ($backup only)"
fi
for c in panolab-direct-dev-1 panolab-direct-connect-tunnel-1 \
  panolab-direct-connect-manager-1 panolab-direct-connect-repo-git-1 \
  panolab-direct-connect-docker-broker-1 panolab-direct-connect-setup-1; do
    [[ "$(r inspect -f '{{.State.Running}}' "$c")" == true ]] ||
        die "Expected service not running: $c"
done
say "SIX_SERVICE_HEALTH=PASS; no new service, no global prune, no FPGA operation."
