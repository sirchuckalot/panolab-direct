#!/usr/bin/env bash
# Historical legacy-path procedure. For external storage, see docs/EXTERNAL_STORAGE_CUTOVER.md.
# HISTORICAL / REVISION-LOCKED. DO NOT RERUN ON CURRENT DEVELOPMENT.
# Preserved for source-migration provenance; see host/README.md and
# docs/TEMPORARY_COMPONENTS.md for the current controlled path.
# PanoLab Source and Project Architecture migration — owner-controlled laptop cutover.
# This launches on the owner's laptop AS THE ORDINARY USER, after the source
# candidate has been prepared and tested inside the existing PanoLab dev container.
# Never sudo; no host-wide Docker cleanup, no force push, no FPGA programming.
set -Eeuo pipefail
umask 077
EXPECTED_BASE=fa33395bb907186e1d6f16fcf632fcee5786eb9a
STAGE=/workspace/panolab-source-migration
DEV=panolab-direct-dev-1
PROJECT=panolab-direct-connect
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
SCRIPT="$ROOT/host/apply-source-migration.sh"
fail() { echo "PANOLAB_SOURCE_MIGRATION_BLOCKED: $*" >&2; exit 9; }
say() { printf 'PanoLab source migration: %s\n' "$*"; }
[[ "$(id -u)" != 0 ]] || fail "Use an ordinary laptop account, never sudo."
[[ "$(uname -s)" == Linux ]] || fail "Linux host required."
[[ -d "$ROOT/.git" && -f "$SCRIPT" ]] || fail "Run from the canonical Git checkout."
command -v docker >/dev/null && command -v git >/dev/null && command -v python3 >/dev/null || fail "Missing host prerequisites."
[[ "$(git -C "$ROOT" branch --show-current)" == development ]] || fail "Expected development branch."
[[ "$(git -C "$ROOT" rev-parse HEAD)" == "$EXPECTED_BASE" ]] || fail "Unexpected baseline SHA; not rebasing or overwriting history."
[[ "$(git -C "$ROOT" status --porcelain --untracked-files=all)" == "?? host/apply-source-migration.sh" ]] ||
  fail "Checkout contains changes other than this reviewed, untracked launcher."
origin="$(git -C "$ROOT" remote get-url origin)"
[[ "$origin" == https://github.com/sirchuckalot/panolab-direct.git ||
   "$origin" == https://github.com/sirchuckalot/panolab-direct ]] || fail "Unexpected GitHub origin."
remote="$(GIT_TERMINAL_PROMPT=0 git -C "$ROOT" ls-remote origin refs/heads/development | awk '{print $1}')"
[[ "$remote" == "$EXPECTED_BASE" ]] || fail "GitHub development has advanced; refusing to overwrite."
socket="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/docker.sock"
[[ -S "$socket" ]] || fail "Owner-user rootless Docker socket missing."
r() { docker -H "unix://$socket" "$@"; }
[[ "$(r info --format '{{json .SecurityOptions}}')" == *'"name=rootless"'* ]] ||
  fail "Docker Engine must be rootless."
[[ "$(r inspect -f '{{.State.Running}}' "$DEV")" == true ]] || fail "Existing PanoLab dev container not running."
for name in "$PROJECT-repo-git-1" "$PROJECT-docker-broker-1" "$PROJECT-manager-1" "$PROJECT-tunnel-1" "$PROJECT-setup-1"; do
  [[ "$(r inspect -f '{{.State.Running}}' "$name")" == true ]] ||
    fail "Expected PanoLab service not running: $name"
done
say "Read-only preflight passed; testing candidate in the existing development container."
r exec -e PYTHONDONTWRITEBYTECODE=1 "$DEV" /bin/bash -lc   "cd '$STAGE' && python3 shared/source_registry.py verify &&
   python3 -m unittest discover -s tests -p 'test_*.py' &&
   bash -n host/rootless-install.sh host/upgrade-dev-image.sh" >/dev/null ||
  fail "Candidate source and tests failed."
r exec -e PYTHONDONTWRITEBYTECODE=1 -e PANOLAB_LAB_MAC=02:00:00:00:00:01   -e PANOLAB_RESCUE_OUT=/workspace/panolab-source-migration-owner-preflight   "$DEV" /bin/bash -lc "cd '$STAGE' && bash projects/rescue/build.sh" >/dev/null ||
  fail "G2 BIOS/HDL candidate build failed."
r exec "$DEV" /bin/sh -c   'test -s /workspace/panolab-source-migration-owner-preflight/software/bios/bios.bin &&
   test -s /workspace/panolab-source-migration-owner-preflight/gateware/pano_logic_g2.v' ||
  fail "Build artifacts absent."
workbase="${XDG_CACHE_HOME:-$HOME/.cache}"
mkdir -p "$workbase"
checkpoint="$(mktemp -d "$workbase/panolab-source-migration.XXXXXXXX")"
say "Preserving local inspection checkpoint at $checkpoint"
mkdir -p "$checkpoint/candidate"
r cp "${DEV}:${STAGE}/." "$checkpoint/candidate/" ||
  fail "Unable to copy staged Git candidate; canonical checkout unchanged."
candidate="$checkpoint/candidate"
[[ -d "$candidate/.git" ]] || fail "Candidate Git metadata missing."
[[ "$(git -C "$candidate" branch --show-current)" == development ]] || fail "Candidate branch mismatch."
[[ "$(git -C "$candidate" status --porcelain --untracked-files=normal)" == "" ]] ||
  fail "Candidate working tree not clean."
head="$(git -C "$candidate" rev-parse HEAD)"
parent="$(git -C "$candidate" rev-list --parents -n 1 HEAD)"
[[ "$parent" == "$head $EXPECTED_BASE" ]] || fail "Candidate must contain exactly one reviewed descendant commit."
cmp -s "$SCRIPT" "$candidate/host/apply-source-migration.sh" ||
  fail "Launcher differs from tested candidate. Refusing cutover."
python3 "$candidate/shared/source_registry.py" verify >/dev/null ||
  fail "Copied source snapshot hashes failed host-side verification."
[[ "$(git -C "$candidate" status --porcelain)" == "" ]] ||
  fail "Copied source verifier modified the candidate."
say "Git candidate validated: $head; preparing recoverable source checkpoint."
backup="panolab/backup-source-before-${EXPECTED_BASE:0:8}"
if git -C "$ROOT" show-ref --verify --quiet "refs/heads/$backup"; then
  [[ "$(git -C "$ROOT" rev-parse "$backup")" == "$EXPECTED_BASE" ]] ||
    fail "Existing backup ref conflicts."
else
  git -C "$ROOT" branch "$backup" "$EXPECTED_BASE"
fi
mkdir -p "$checkpoint/pre-source"
cp -a "$ROOT/boards" "$checkpoint/pre-source/boards"
if [[ -d "$ROOT/gateware" ]]; then cp -a "$ROOT/gateware" "$checkpoint/pre-source/gateware"; fi
git -C "$ROOT" fetch --no-tags "$candidate" development >/dev/null ||
  fail "Candidate local Git object fetch failed."
[[ "$(git -C "$ROOT" rev-parse FETCH_HEAD)" == "$head" ]] ||
  fail "Fetched candidate does not match validated hash."
# This untracked launcher exactly matches the candidate's tracked file; remove
# only this one known file to avoid Git overwrite conflict during fast-forward.
rm -- "$SCRIPT"
[[ -z "$(git -C "$ROOT" status --porcelain --untracked-files=all)" ]] ||
  fail "Unexpected changed files after releasing single launcher."
git -C "$ROOT" merge --ff-only "$head" >/dev/null ||
  fail "Fast-forward failed; source checkpoint preserved at $checkpoint."
[[ "$(git -C "$ROOT" rev-parse HEAD)" == "$head" ]] || fail "Wrong local HEAD after fast-forward."
say "LOCAL_SOURCE_FAST_FORWARD=PASS $head"
# The existing dev image is reused; the guarded upgrade replaces ONLY the dev
# container's source-mount contract, retaining the prior container as rollback.
(
  cd "$ROOT"
  bash ./panolab-install.sh --upgrade-dev
) || fail "Dev cutover failed. Backup ref $backup, old source copy $checkpoint/pre-source. Do not push."
r exec -e PYTHONDONTWRITEBYTECODE=1 "$DEV" /bin/sh -ec   'test -d /repo/projects && test -d /repo/third_party &&
   test ! -e /repo/docker/private &&
   cd /repo && python3 shared/source_registry.py verify' >/dev/null ||
  fail "New dev source mounts did not validate. Do not push."
say "DEV_SOURCE_MOUNTS=PASS; rebuilding only the affected Git gateway and Docker broker images."
# Preserve image IDs for a manually reviewed rollback. Never touch the manager,
# tunnel, setup, ISE media, other Docker projects, or the licensed toolchain.
r image tag panolab-direct-broker:local "panolab-direct-broker:pre-source-${EXPECTED_BASE:0:8}" ||
  fail "Unable to preserve broker image."
r image tag panolab-direct-repo-git:local "panolab-direct-repo-git:pre-source-${EXPECTED_BASE:0:8}" ||
  fail "Unable to preserve Git gateway image."
private="$ROOT/docker/private"
[[ -f "$ROOT/docker/.env" && -d "$private" ]] || fail "Private Compose configuration missing."
shopt -s nullglob
media=("$private"/*.tar "$private"/*.tar.gz "$private"/*.tgz "$private"/*.tar.bz2)
shopt -u nullglob
[[ "${#media[@]}" == 1 ]] || fail "Unexpected vendor-media precondition."
export PANOLAB_ROOTLESS_SOCKET="$socket"
export PANOLAB_REPO_HOST="$ROOT"
export PANOLAB_WORKSPACE_HOST="$(realpath -e "$private/agent-workspace")"
export PANOLAB_CODEX_AUTH_HOST="$(realpath -e "$private/codex-auth")"
export PANOLAB_ISE_TARBALL="$(realpath -e "${media[0]}")"
compose=(docker -H "unix://$socket" compose --project-name "$PROJECT" --env-file "$ROOT/docker/.env"
    -f "$ROOT/docker/compose.setup.yaml"
    -f "$ROOT/docker/compose.manage.yaml"
    -f "$ROOT/host/compose.rootless-laptop.yaml")
# Preserve the already-enabled optional private Git push credential overlay.
auth_mount="$(r inspect -f '{{range .Mounts}}{{if eq .Destination "/run/panolab-git-auth"}}{{.Source}}{{end}}{{end}}' "$PROJECT-repo-git-1")"
if [[ -n "$auth_mount" ]]; then
    [[ "$auth_mount" == "$ROOT/docker/private/github-git-auth" ]] ||
      fail "Unknown Git push auth mount; refusing to recreate gateway."
    compose+=(-f "$ROOT/docker/compose.git-push.yaml")
fi
"${compose[@]}" config --format json >/dev/null || fail "Source-migration Compose config invalid."
"${compose[@]}" build repo-git docker-broker ||
  fail "Restricted services image rebuild failed; existing services left intact."
"${compose[@]}" up -d --no-deps --no-build --force-recreate repo-git docker-broker ||
  fail "Management service replacement failed. Check existing containers and saved images; do not push."
r exec "$PROJECT-repo-git-1" /bin/sh -ec   'grep -q "third_party" /usr/local/bin/panolab-repo-gateway.py' ||
  fail "Running Git gateway does not have new source allowlist."
r exec "$PROJECT-docker-broker-1" /bin/sh -ec   'grep -q "third_party" /usr/local/bin/panolab-broker.py' ||
  fail "Running broker does not have new source mounts."
for name in "$DEV" "$PROJECT-repo-git-1" "$PROJECT-docker-broker-1" "$PROJECT-manager-1" "$PROJECT-tunnel-1" "$PROJECT-setup-1"; do
  [[ "$(r inspect -f '{{.State.Running}}' "$name")" == true ]] ||
    fail "Service stopped after cutover: $name. Do not push."
done
[[ "$(git -C "$ROOT" status --porcelain --untracked-files=normal)" == "" ]] ||
  fail "Unexpected local Git changes after cutover. Do not push."
say "MIGRATION_LOCAL_PASS commit=$head"
say "CHECKPOINT=$checkpoint"
say "BACKUP_REF=$backup"
say "GitHub has NOT been pushed by this script."
say "Send MIGRATION_LOCAL_PASS to ChatGPT for remote MCP acceptance and ONE reviewed GitHub development push."
