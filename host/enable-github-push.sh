#!/usr/bin/env bash
set -Eeuo pipefail
set +x
umask 077
(( $# == 2 )) || exit 2
root="$(realpath -e "$1")"
sock="$2"
fail() { echo "PANOLAB GITHUB PUSH BLOCKED: $*" >&2; exit 9; }
[[ "$(id -u)" != 0 ]] || fail "Run as your laptop user, not sudo."
[[ -S "$sock" ]] || fail "Rootless Docker socket missing."
[[ "$(git -C "$root" branch --show-current)" == development ]] || fail "Use development branch."
[[ -z "$(git -C "$root" status --porcelain --untracked-files=all)" ]] || fail "Checkout has uncommitted changes."
case "$(git -C "$root" remote get-url origin)" in
  https://github.com/sirchuckalot/panolab-direct|https://github.com/sirchuckalot/panolab-direct.git) ;;
  *) fail "Unexpected GitHub origin." ;;
esac
r() { docker -H "unix://$sock" "$@"; }
[[ "$(r info --format '{{json .SecurityOptions}}')" == *'"name=rootless"'* ]] || fail "Use rootless Docker."
dir="$root/docker/private/github-git-auth"
[[ ! -L "$dir" ]] || fail "Credential directory is a symlink."
mkdir -p -m 0700 "$dir"
[[ -O "$dir" ]] || fail "Credential directory ownership mismatch."
chmod 0700 "$dir"
secret="$dir/github-push-token"
[[ ! -L "$secret" ]] || fail "Token path is a symlink."
if [[ -e "$secret" ]]; then
  [[ -f "$secret" && -O "$secret" && -s "$secret" && "$(stat -c %a "$secret")" == 600 ]] || fail "Existing token has unsafe permissions."
  echo "PanoLab GitHub: Reusing owner-private token file."
else
  [[ -t 0 ]] || fail "Interactive terminal required."
  echo "Create a fine-grained PAT for only sirchuckalot/panolab-direct (Contents: read/write)."
  IFS= read -r -s -p "Paste PAT (hidden): " token
  printf '\n'
  [[ "$token" =~ ^github_pat_[A-Za-z0-9_]{20,}$ ]] || fail "Expected github_pat_ fine-grained token."
  tmp="$(mktemp "$dir/.github-token.XXXXXXXX")"
  trap 'rm -f "$tmp"' EXIT
  printf '%s\n' "$token" > "$tmp"
  unset token
  chmod 0600 "$tmp"
  mv -n "$tmp" "$secret"
  trap - EXIT
  [[ -s "$secret" && "$(stat -c %a "$secret")" == 600 ]] || fail "Token file creation failed."
  echo "PanoLab GitHub: Saved token in owner-private directory (0600)."
fi
# Activate the opt-in Compose overlay for ONLY the existing repo-git service.
export PANOLAB_ROOTLESS_SOCKET="$sock"
compose=(docker -H "unix://$sock" compose --project-name panolab-direct-connect
  --env-file "$root/docker/.env"
  -f "$root/docker/compose.setup.yaml"
  -f "$root/docker/compose.manage.yaml"
  -f "$root/host/compose.rootless-laptop.yaml"
  -f "$root/docker/compose.git-push.yaml")
"${compose[@]}" config --format json | python3 -c '
import json,sys
services=json.load(sys.stdin)["services"]
for name,svc in services.items():
    mounts=[m.get("target") for m in svc.get("volumes",[]) if isinstance(m,dict)]
    if name=="repo-git":
        assert mounts.count("/run/panolab-git-auth")==1, "missing scoped auth mount"
    else:
        assert "/run/panolab-git-auth" not in mounts, "auth visible to another service"
print("GITHUB_SECRET_MOUNT_SCOPE=PASS")
'
echo "PanoLab GitHub: Building existing repo-git image only."
DOCKER_BUILDKIT=1 "${compose[@]}" build repo-git || fail "Repo-git build failed; existing service preserved."
echo "PanoLab GitHub: Recreating only existing repo-git container."
"${compose[@]}" up -d --no-deps --no-build --force-recreate repo-git || fail "Gateway service recreate failed."
gateway=panolab-direct-connect-repo-git-1
[[ "$(r inspect -f '{{.State.Running}}' "$gateway")" == true ]] || fail "Repo-git not running."
r exec "$gateway" python3 -c '
from pathlib import Path
import stat
p=Path("/run/panolab-git-auth/github-push-token")
v=p.lstat()
assert stat.S_ISREG(v.st_mode) and v.st_mode & 0o077 == 0 and v.st_size > 0
assert Path("/usr/local/bin/panolab-git-askpass").is_file()
print("GITHUB_SECRET_AND_ASKPASS=PASS")
'
echo "PanoLab GitHub: Verifying authenticated push without making a remote change."
r exec -e GIT_TERMINAL_PROMPT=0 -e GIT_CONFIG_GLOBAL=/dev/null -e GIT_CONFIG_NOSYSTEM=1 -e GIT_ASKPASS=/usr/local/bin/panolab-git-askpass "$gateway" git -C /repo -c credential.helper= -c core.hooksPath=/dev/null -c protocol.file.allow=never push --dry-run origin HEAD:refs/heads/development || fail "Push dry-run failed: check fine-grained token repository and Contents write permission."
echo "PanoLab GitHub: GITHUB_PUSH_AUTH=PASS (dry-run only)."
echo "PanoLab GitHub: Only repo-git was replaced; no development, ISE or FPGA changes."
