#!/usr/bin/env bash
# Scoped replacement of the existing PanoLab modern dev container.
# Preserves host-bound workspace, old container rollback, tunnel and ISE.
set -Eeuo pipefail
umask 077
(( $# == 4 )) || { echo "Usage (internal): upgrade-dev-image.sh ROOT SOCKET WORKSPACE CODEX_AUTH" >&2; exit 2; }
root="$(realpath -e "$1")"; socket="$2"
workspace="$(realpath -e "$3")"; auth="$(realpath -e "$4")"
dev=panolab-direct-dev-1
image=panolab-direct-modern:local
recipe=modern-unified-dev-20261123-v2
r() { docker -H "unix://$socket" "$@"; }
die() { echo "PANOLAB DEV UPGRADE BLOCKED: $*" >&2; exit 9; }
say() { printf 'PanoLab dev upgrade: %s\n' "$*"; }
[[ "$(id -u)" != 0 && -S "$socket" ]] || die "Expected ordinary user/rootless socket."
[[ "$(r info --format '{{json .SecurityOptions}}')" == *'"name=rootless"'* ]] || die "Rootless Engine required."
[[ -d "$root/.git" ]] || die "Expected PanoLab checkout missing."
for rel in projects boards shared third_party agent specs tests docs host docker/modern; do
  [[ -d "$root/$rel" && ! -L "$root/$rel" ]] || die "Unexpected source directory: $rel"
done
old_present=0; old_running=false
if r container inspect "$dev" >/dev/null 2>&1; then
  old_present=1
  r inspect "$dev" | python3 -c '
import json,sys
c=json.load(sys.stdin)[0]; root,work,auth=sys.argv[1:]
assert c["Config"]["Labels"].get("panolab.managed")=="true"
assert c["Config"]["User"]=="0:0" and c["Config"]["WorkingDir"]=="/workspace"
assert "CODEX_HOME=/codex-auth" in c["Config"]["Env"]
assert not c["HostConfig"]["Privileged"]
assert any("no-new-privileges" in s for s in c["HostConfig"].get("SecurityOpt",[]))
assert any(s.lower()=="all" for s in c["HostConfig"].get("CapDrop",[]))
expected={"/workspace":(work,False),"/codex-auth":(auth,False)}
legacy=(("gateware",False),("agent",False),("boards",True),
        ("specs",True),("tests",True),("docs",True),("host",True),
        ("docker/modern",True))
current=(("projects",True),("boards",True),("shared",True),
         ("third_party",True),("agent",False),("specs",True),
         ("tests",True),("docs",True),("host",True),("docker/modern",True))
def layout(mounts):
    result=dict(expected)
    for name,ro in mounts:
        result["/repo/"+name]=(root+"/"+name,ro)
    return result
got={x["Destination"]:(x["Source"],not x["RW"]) for x in c["Mounts"] if x["Type"]=="bind"}
assert got in (layout(legacy),layout(current)), "Unexpected bind mount set"
' "$root" "$workspace" "$auth" || die "Dev container differs from approved configuration; unchanged."
  old_running="$(r inspect -f '{{.State.Running}}' "$dev")"
fi
label="$(r image inspect -f '{{index .Config.Labels "org.panolab.litex.recipe"}}' "$image" 2>/dev/null || true)"
if [[ "$label" != "$recipe" ]]; then
  say "Building the SAME modern development image with the unified toolchain."
  r buildx version >/dev/null || die "Buildx CLI missing; run --finalize-maintenance first."
  r buildx build --builder default --load -t "$image" "$root/docker/modern" || die "Build failed; old dev untouched."
fi
new_id="$(r image inspect -f '{{.Id}}' "$image")"
[[ "$(r image inspect -f '{{index .Config.Labels "org.panolab.litex.recipe"}}' "$image")" == "$recipe" ]] ||
  die "Missing unified image label."
say "Offline, read-only image smoke test."
r run --rm --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges:true --env PYTHONDONTWRITEBYTECODE=1 \
  --entrypoint /bin/sh "$image" -ec '
command -v python3; command -v yosys; command -v verilator; command -v iverilog
command -v riscv64-unknown-elf-gcc; command -v meson; command -v ninja; command -v codex
test -s /opt/panolab/litex/env.sh
python3 /opt/panolab/recipes/litex-bootstrap.py \
  --prefix /opt/panolab/litex --lock /opt/panolab/recipes/litex-upstream.lock.json \
  --requirements /opt/panolab/recipes/litex-requirements.txt --verify-only' ||
  die "Image smoke failed; old dev untouched."
if (( old_present )); then
  if [[ "$(r inspect -f '{{.Image}}' "$dev")" == "$new_id" ]]; then
    if r inspect "$dev" | python3 -c '
import json,sys
c=json.load(sys.stdin)[0]
d={x["Destination"] for x in c["Mounts"] if x["Type"]=="bind"}
sys.exit(0 if "/repo/projects" in d and "/repo/third_party" in d else 1)
'; then
      say "DEV_IMAGE_AND_SOURCE_MOUNTS_ALREADY_CURRENT=1; no container replacement."
      exit 0
    fi
    say "Current image uses previous source mounts; controlled source-mount replacement required."
  fi
fi
# Do not stack multiple backups; a prior transition must be reviewed first.
if r ps -a --format '{{.Names}}' --filter "name=^$dev-rollback-" | grep -q .; then
  die "Outstanding stopped rollback dev container exists; review before retry."
fi
backup="$dev-rollback-$(date -u +%Y%m%dT%H%M%SZ)"
r container inspect "$backup" >/dev/null 2>&1 && die "Backup container name already occupied."
renamed=0
rollback() {
  local rc=$?
  trap - ERR INT TERM
  set +e
  echo "DEV_UPGRADE_FAILED=$rc; restoring the previous dev if possible" >&2
  if (( renamed )); then
    if r container inspect "$dev" >/dev/null 2>&1; then
      r stop -t 10 "$dev" >/dev/null 2>&1
      r rm "$dev" >/dev/null 2>&1
    fi
    r rename "$backup" "$dev" || echo "RESTORE_MANUAL: rename $backup to $dev" >&2
    if [[ "$old_running" == true ]]; then r start "$dev" >/dev/null || :; fi
  elif (( ! old_present )); then
    if r container inspect "$dev" >/dev/null 2>&1; then
      r stop -t 10 "$dev" >/dev/null 2>&1
      r rm "$dev" >/dev/null 2>&1
    fi
  elif [[ "$old_running" == true ]]; then
    r start "$dev" >/dev/null 2>&1
  fi
  exit "$rc"
}
trap rollback ERR
trap 'false' INT TERM
if (( old_present )); then
  say "Stopping only old dev; preserving all workspace and private data."
  if [[ "$old_running" == true ]]; then r stop -t 20 "$dev" >/dev/null; fi
  r rename "$dev" "$backup"
  renamed=1
fi
cmd=(run -d --name "$dev" --restart unless-stopped --label panolab.managed=true
  --user 0:0 --workdir /workspace --cap-drop ALL
  --security-opt no-new-privileges:true
  --memory 4g --cpus 2 --pids-limit 256
  --tmpfs /tmp:rw,nosuid,nodev,size=256m
  --tmpfs /home:rw,nosuid,nodev,size=64m
  --mount "type=bind,src=$workspace,dst=/workspace"
  --mount "type=bind,src=$auth,dst=/codex-auth"
  --env CODEX_HOME=/codex-auth)
for spec in projects:ro boards:ro shared:ro third_party:ro agent:rw specs:ro tests:ro docs:ro host:ro docker/modern:ro; do
  rel="${spec%:*}"; perm="${spec#*:}"
  mount="type=bind,src=$root/$rel,dst=/repo/$rel"
  [[ "$perm" == ro ]] && mount+=",readonly"
  cmd+=(--mount "$mount")
done
say "Starting replacement dev with new source mounts, unchanged quotas, security and name."
r "${cmd[@]}" "$image" sleep infinity >/dev/null
[[ "$(r inspect -f '{{.State.Running}}' "$dev")" == true ]]
[[ "$(r inspect -f '{{.Image}}' "$dev")" == "$new_id" ]]
say "Testing new dev tools, source, Codex credentials and firmware."
r exec -e PYTHONDONTWRITEBYTECODE=1 "$dev" /bin/sh -ec '
test -d /repo/boards && test -d /repo/projects && test -d /repo/shared && test -d /repo/third_party && test -d /workspace
test ! -e /repo/docker/private
command -v yosys; command -v iverilog; command -v verilator
command -v riscv64-unknown-elf-gcc; command -v meson; command -v ninja
test -x /usr/local/bin/codex; test -s /opt/panolab/litex/env.sh'
r exec "$dev" /usr/local/bin/codex login status >/dev/null
for pair in 'cpu.max:200000 100000' 'memory.max:4294967296' 'pids.max:256'; do
  key="${pair%%:*}"; expect="${pair#*:}"
  [[ "$(r exec "$dev" cat "/sys/fs/cgroup/$key" | tr -d '\r')" == "$expect" ]]
done
r exec -e PYTHONDONTWRITEBYTECODE=1 "$dev" /bin/sh -ec \
  'cd /repo && python3 shared/source_registry.py verify --project projects/rescue/project.toml' >/dev/null
# No flashing or ISE invocation: source-only BIOS/HDL compilation.
out="/workspace/panolab-rescue-upgrade-$(date -u +%Y%m%dT%H%M%SZ)"
r exec -e PANOLAB_LAB_MAC=02:00:00:00:00:fa \
  -e PANOLAB_RESCUE_OUT="$out" -e PYTHONDONTWRITEBYTECODE=1 \
  "$dev" bash /repo/projects/rescue/build.sh >/dev/null
r exec "$dev" /bin/sh -ec \
  "test -s '$out/software/bios/bios.bin' && test -s '$out/gateware/pano_logic_g2.v' && \
   iverilog -g2012 -i -tnull -s pano_logic_g2 '$out/gateware/pano_logic_g2.v'"
trap - ERR INT TERM
say "DEV_UPGRADE_RESULT=PASS; unified tools image accepted."
say "IMAGE_ID=$new_id"
say "BIOS_AND_HDL_ARTIFACTS=$out"
if (( old_present )); then
  say "ROLLBACK_CONTAINER=$backup (stopped; preserved temporarily, not another service)."
fi
say "ISE, manager, broker, tunnel and FPGA untouched."
