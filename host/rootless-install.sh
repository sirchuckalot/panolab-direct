#!/usr/bin/env bash
# Install or inspect the owner-user rootless PanoLab Docker stack.
# Host Docker provisioning and private inputs are preconditions, not installer actions.
# No sudo, host packages, global Docker cleanup, CI execution or FPGA programming.
set -Eeuo pipefail
umask 077
root="$(cd "$(dirname "$0")/.." && pwd -P)"
mode="${1:---install}"
case "$mode" in --install|--check|--status|--upgrade-dev|--help) ;; *) echo "Usage: bash ./panolab-install.sh [--check|--status|--upgrade-dev|--help]" >&2; exit 2;; esac
if [[ "$mode" == --help ]]; then echo "Usage: bash ./panolab-install.sh [--check|--status|--upgrade-dev|--help]"; exit 0; fi
fail() { echo "PANOLAB ROOTLESS BLOCKED: $*" >&2; exit 9; }
say() { echo "PanoLab rootless: $*"; }
[[ "$(id -u)" != 0 ]] || fail "Run as ordinary laptop user, never sudo."
[[ "$(uname -s)" == Linux && "$(uname -m)" == x86_64 ]] || fail "Requires Linux x86_64."
command -v docker >/dev/null && docker compose version >/dev/null || fail "Docker CLI/Compose missing."
command -v python3 >/dev/null || fail "Python 3 missing."
[[ -d "$root/.git" ]] || fail "Run from the PanoLab Direct Git checkout."
runtime="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
[[ -O "$runtime" ]] || fail "Session runtime directory absent."
sock="$runtime/docker.sock"
rootless="unix://$sock"
export PANOLAB_ROOTLESS_SOCKET="$sock"
unset DOCKER_CONTEXT DOCKER_HOST
r() { docker -H "$rootless" "$@"; }
project=panolab-direct-connect
dev=panolab-direct-dev-1
tunnel="$project-tunnel-1"
envfile="$root/docker/.env"
private="$root/docker/private"
compose=(docker -H "$rootless" compose --project-name "$project" --env-file "$envfile"
  -f "$root/docker/compose.setup.yaml" -f "$root/docker/compose.manage.yaml"
  -f "$root/host/compose.rootless-laptop.yaml")
rootless_ok() {
  [[ -S "$sock" ]] || return 1
  [[ "$(r info --format '{{json .SecurityOptions}}' 2>/dev/null)" == *'"name=rootless"'* ]] || return 1
  [[ "$(r info --format '{{.CgroupDriver}}' 2>/dev/null)" == systemd ]] || return 1
  [[ "$(r info --format '{{.CgroupVersion}}' 2>/dev/null)" == 2 ]]
}
new_exists() { r container inspect "$1" >/dev/null 2>&1; }
new_valid() {
  [[ "$(r inspect -f '{{index .Config.Labels "com.docker.compose.project"}}' "$1" 2>/dev/null)" == "$project" ]]
}
dev_valid() {
  [[ "$(docker -H "$1" inspect -f '{{index .Config.Labels "panolab.managed"}}' "$dev" 2>/dev/null)" == true ]]
}
running_new() { [[ "$(r inspect -f '{{.State.Running}}' "$1" 2>/dev/null)" == true ]]; }
status() {
  if rootless_ok; then
    say "Rootless Engine: PASS, systemd cgroups v2"
    r ps -a --filter name=panolab-direct --format '{{.Names}} {{.Status}}'
  else say "Rootless Engine not reachable."; fi
}
if [[ "$mode" == --status ]]; then status; exit 0; fi
# Start only the known owner-user rootless service when the socket is unavailable.
if [[ "$mode" == --install ]] && ! rootless_ok; then
  # Start the user-scoped rootless service from its pre-provisioned helper.
  unit="$HOME/.config/systemd/user/panolab-rootless-docker.service"
  launcher="$HOME/.local/libexec/panolab-rootless-29.1.3/dockerd-rootless.sh"
  [[ -x "$launcher" && ! -L "$launcher" ]] || fail "The configured rootless launcher is missing or a symlink."
  if [[ ! -e "$unit" && ! -L "$unit" ]]; then
    mkdir -p "$(dirname "$unit")"
    cat > "$unit" <<'UNIT'
[Unit]
Description=PanoLab rootless Docker (ordinary laptop user)
After=network-online.target
[Service]
Type=simple
Delegate=yes
Environment=PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ExecStart=%h/.local/libexec/panolab-rootless-29.1.3/dockerd-rootless.sh
Restart=on-failure
RestartSec=3
[Install]
WantedBy=default.target
UNIT
    systemctl --user daemon-reload
    systemctl --user enable panolab-rootless-docker.service >/dev/null
    say "Created the missing user-level rootless Docker service (no sudo)."
  fi
  [[ -f "$unit" && ! -L "$unit" ]] || fail "Unexpected rootless user-service path."
  grep -Fxq 'ExecStart=%h/.local/libexec/panolab-rootless-29.1.3/dockerd-rootless.sh' "$unit" ||
    fail "Unexpected user unit contents, refusing to start."
  grep -Fxq 'Delegate=yes' "$unit" || fail "Rootless unit lacks cgroup delegation."
  systemctl --user start panolab-rootless-docker.service ||
    fail "Could not start the approved user-level rootless Docker service."
  for attempt in 1 2 3 4 5 6 7 8 9 10; do
    if rootless_ok; then break; fi
    sleep 1
  done
fi
rootless_ok || fail "The user rootless Engine (systemd cgroup v2) is not running."
# This recipe targets only the owner-user rootless Engine.
[[ -f "$envfile" && ! -L "$envfile" && -d "$private" && ! -L "$private" ]] || fail "Existing private configuration missing."
for name in tunnel-api-key mcp-bearer Xilinx.lic; do
  [[ -s "$private/$name" && ! -L "$private/$name" ]] || fail "Private $name missing."
done
for name in tunnel-api-key mcp-bearer; do
  [[ "$(stat -c %a "$private/$name")" == 600 ]] || fail "$name must be mode 0600."
done
python3 - "$envfile" "$private/mcp-bearer" <<'PY'
from pathlib import Path
import sys
pairs={}
for ln in Path(sys.argv[1]).read_text().splitlines():
    if '=' in ln and not ln.lstrip().startswith('#'):
        k,v=ln.split('=',1)
        if k in ('PANOLAB_MCP_TOKEN','PANOLAB_TUNNEL_ID'):
            if k in pairs: raise SystemExit('Duplicate credential key')
            pairs[k]=v
if len(pairs.get('PANOLAB_MCP_TOKEN',''))<32 or not pairs.get('PANOLAB_TUNNEL_ID','').startswith('tunnel_'):
    raise SystemExit('Existing authentication missing')
if Path(sys.argv[2]).read_text().strip() != 'Bearer '+pairs['PANOLAB_MCP_TOKEN']:
    raise SystemExit('Private MCP bearer does not match')
PY
shopt -s nullglob
media=("$private"/*.tar "$private"/*.tar.gz "$private"/*.tgz "$private"/*.tar.bz2)
shopt -u nullglob
[[ "${#media[@]}" == 1 && -f "${media[0]}" && ! -L "${media[0]}" ]] || fail "Expected exactly one owner ISE archive (no toolchain install will occur)."
for sub in agent-workspace repo-rpc codex-auth Xilinx ise-work; do [[ -d "$private/$sub" ]] || fail "Existing $sub data directory absent."; done
export PANOLAB_WORKSPACE_HOST="$(realpath "$private/agent-workspace")"
export PANOLAB_CODEX_AUTH_HOST="$(realpath "$private/codex-auth")"
export PANOLAB_REPO_HOST="$root"
export PANOLAB_ISE_TARBALL="$(realpath "${media[0]}")"
"${compose[@]}" config --format json | python3 -c '
import json,sys
d=json.load(sys.stdin)["services"]; s=sys.argv[1]
v=[x for x in d["docker-broker"]["volumes"] if x.get("target")=="/var/run/docker.sock"]
assert len(v)==1 and v[0]["source"]==s and v[0]["type"]=="bind", "wrong Docker broker socket"
assert d["docker-broker"]["environment"]["PANOLAB_ROOTLESS_MODE"]=="1"
for n in ("setup","tunnel","repo-git","manager"):
    assert d[n]["user"]=="0:0", "rootless host-owner mapping missing"
for n,svc in d.items():
    assert not svc.get("privileged"), "privileged container rejected"
    assert not any(x.get("source")=="/var/run/docker.sock" for x in svc.get("volumes",[]))
' "$sock" || fail "Merged Compose violates rootless isolation policy."
say "PASS: rootless Engine, private credentials, owner data, merged Compose."
if [[ "$mode" == --check ]]; then say "Read-only preflight completed; no changes."; exit 0; fi
# Explicitly requested dev-only image upgrade. Management services are not
# restarted, and the previous dev is retained as a stopped rollback container.
if [[ "$mode" == --upgrade-dev ]]; then
  bash "$root/host/upgrade-dev-image.sh" "$root" "$sock" "$PANOLAB_WORKSPACE_HOST" "$PANOLAB_CODEX_AUTH_HOST"
  exit $?
fi
# Establish restart-on-login without sudo. A manually running Docker daemon
# cannot be adopted by systemd; never kill an unknown process to force a swap.
unit="$HOME/.config/systemd/user/panolab-rootless-docker.service"
if ! systemctl --user is-active --quiet panolab-rootless-docker.service; then
  [[ ! -e "$unit" && ! -L "$unit" ]] || fail "Existing inactive user service requires manual inspection: $unit"
  launcher="$HOME/.local/libexec/panolab-rootless-29.1.3/dockerd-rootless.sh"
  [[ -x "$launcher" ]] || fail "Docker 29.1.3 rootless launcher missing."
  mkdir -p "$(dirname "$unit")"
  cat > "$unit" <<'UNIT'
[Unit]
Description=PanoLab rootless Docker (ordinary laptop user)
After=network-online.target
[Service]
Type=simple
# Docker needs delegated cgroup controllers for enforceable per-container limits.
Delegate=yes
Environment=PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ExecStart=%h/.local/libexec/panolab-rootless-29.1.3/dockerd-rootless.sh
Restart=on-failure
RestartSec=3
[Install]
WantedBy=default.target
UNIT
  systemctl --user daemon-reload
  systemctl --user enable panolab-rootless-docker.service >/dev/null
  say "Installed owner-user systemd service. The current rootless daemon is foreground/manual."
  say "If a rootless daemon is running manually, stop it in its own terminal and rerun this installer."
  say "No PanoLab containers were changed."
  exit 20
fi
rootless_ok || fail "Systemd-managed rootless Engine did not pass checks."
# Fail closed if anything foreign occupies an expected rootless name.
for n in "$project-setup-1" "$project-docker-broker-1" "$project-repo-git-1" "$project-manager-1" "$tunnel"; do
  if new_exists "$n"; then new_valid "$n" || fail "Foreign rootless container: $n"; fi
done
if new_exists "$dev"; then dev_valid "$rootless" || fail "Foreign rootless dev container."; fi
modern_recipe="modern-unified-dev-20261123-v2"
installed_recipe="$(r image inspect -f '{{index .Config.Labels "org.panolab.litex.recipe"}}' panolab-direct-modern:local 2>/dev/null || true)"
if [[ "$installed_recipe" != "$modern_recipe" ]]; then
  say "Building pinned LiteX/BIOS modern tools in local laptop rootless Docker."
  # Rebuild the IMAGE only. Never implicitly destroy a running development
  # container or its private workspace when the image recipe changes.
  r build -t panolab-direct-modern:local "$root/docker/modern"
fi
r run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges:true \
  --env PYTHONDONTWRITEBYTECODE=1 \
  --entrypoint /bin/sh panolab-direct-modern:local -ec \
  'command -v yosys; command -v iverilog; command -v verilator;
   command -v riscv64-unknown-elf-gcc; command -v meson; command -v ninja;
   test -x /usr/local/bin/codex; test -x /usr/local/bin/codex-code-mode-host;
   test -s /opt/panolab/litex/env.sh;
   python3 /opt/panolab/recipes/litex-bootstrap.py
     --prefix /opt/panolab/litex
     --lock /opt/panolab/recipes/litex-upstream.lock.json
     --requirements /opt/panolab/recipes/litex-requirements.txt
     --verify-only' >/dev/null
images=(panolab-direct-ise14-setup:local panolab-direct-broker:local
        panolab-direct-repo-git:local panolab-direct-manager:local)
need_build=0
for image in "${images[@]}"; do if ! r image inspect "$image" >/dev/null 2>&1; then need_build=1; fi; done
if [[ "$need_build" == 1 ]]; then
  say "Building management images on the laptop rootless Engine."
  "${compose[@]}" build setup docker-broker repo-git manager
fi
say "Starting rootless management services before tunnel acceptance."
"${compose[@]}" up -d --no-build --no-recreate setup docker-broker repo-git manager
for n in "$project-setup-1" "$project-docker-broker-1" "$project-repo-git-1" "$project-manager-1"; do
  running_new "$n" || fail "Rootless $n not running."
done
broker="$project-docker-broker-1"
mounted="$(r inspect -f '{{range .Mounts}}{{if eq .Destination "/var/run/docker.sock"}}{{.Source}}{{end}}{{end}}' "$broker")"
[[ "$mounted" == "$sock" ]] || fail "Broker is not bound to rootless Docker socket."
options="$(r exec "$broker" docker info --format '{{json .SecurityOptions}}' 2>/dev/null || true)"
[[ "$options" == *'"name=rootless"'* ]] || fail "Broker does not connect to rootless Engine."
# In the rootless user namespace, UID 0 maps to the current ordinary
# laptop owner, allowing access to existing owner-only credentials.
# Do not change host permissions or treat namespace root as host root.
if ! new_exists "$dev"; then
  cmd=(run -d --name "$dev" --restart unless-stopped --label panolab.managed=true
    --user 0:0 --workdir /workspace --cap-drop ALL
    --security-opt no-new-privileges:true
    --memory 4g --cpus 2 --pids-limit 256
    --tmpfs /tmp:rw,nosuid,nodev,size=256m
    --tmpfs /home:rw,nosuid,nodev,size=64m
    --mount "type=bind,src=$PANOLAB_WORKSPACE_HOST,dst=/workspace"
    --mount "type=bind,src=$PANOLAB_CODEX_AUTH_HOST,dst=/codex-auth"
    --env CODEX_HOME=/codex-auth)
  for spec in gateware:rw agent:rw boards:ro specs:ro tests:ro docs:ro host:ro docker/modern:ro; do
    rel="${spec%:*}"; perm="${spec#*:}"
    mount="type=bind,src=$root/$rel,dst=/repo/$rel"
    [[ "$perm" == ro ]] && mount+=",readonly"
    cmd+=(--mount "$mount")
  done
  r "${cmd[@]}" panolab-direct-modern:local sleep infinity >/dev/null
else
  # The standalone dev is not a Compose service. Adopt it only when
  # its host mounts point at this checkout and these private inputs.
  current_workspace="$(r inspect -f '{{range .Mounts}}{{if eq .Destination "/workspace"}}{{.Source}}{{end}}{{end}}' "$dev")"
  current_codex="$(r inspect -f '{{range .Mounts}}{{if eq .Destination "/codex-auth"}}{{.Source}}{{end}}{{end}}' "$dev")"
  current_gateware="$(r inspect -f '{{range .Mounts}}{{if eq .Destination "/repo/gateware"}}{{.Source}}{{end}}{{end}}' "$dev")"
  [[ "$current_workspace" == "$PANOLAB_WORKSPACE_HOST" &&
     "$current_codex" == "$PANOLAB_CODEX_AUTH_HOST" &&
     "$current_gateware" == "$root/gateware" ]] ||
    fail "Existing dev container has unexpected bind mounts; inspect before recovery."
fi
# Repair pre-policy dev containers in place; never recreate or discard work.
restart_policy="$(r inspect -f '{{.HostConfig.RestartPolicy.Name}}' "$dev")"
if [[ "$restart_policy" != unless-stopped ]]; then
  r update --restart unless-stopped "$dev" >/dev/null ||
    fail "Cannot configure automatic restart for the managed dev container."
fi
if ! running_new "$dev"; then
  say "Starting verified existing dev container."
  r start "$dev" >/dev/null || fail "Could not restart the managed dev container."
fi
running_new "$dev" || fail "Rootless dev container failed."
current_modern_image="$(r image inspect -f '{{.Id}}' panolab-direct-modern:local)"
dev_image="$(r inspect -f '{{.Image}}' "$dev")"
if [[ "$dev_image" != "$current_modern_image" ]]; then
  say "NOTICE: the existing development container runs an older image. Preserving it and all mounts."
  say "Pinned LiteX tools are baked into the new image; explicit controlled dev-container migration is required."
else
  r exec "$dev" /bin/sh -ec \
    'test -s /opt/panolab/litex/env.sh && command -v riscv64-unknown-elf-gcc && command -v meson' >/dev/null ||
    fail "New development image lacks the pinned LiteX toolchain."
fi
r exec "$dev" /bin/sh -ec \
  'test -d /repo/gateware && test -d /workspace && test ! -e /repo/docker/private && command -v yosys && command -v iverilog && command -v verilator && test -x /usr/local/bin/codex' >/dev/null ||
  fail "Rootless development toolchain/source mounts failed."
for pair in 'cpu.max:200000 100000' 'memory.max:4294967296' 'pids.max:256'; do
  key="${pair%%:*}"; expect="${pair#*:}"
  actual="$(r exec "$dev" cat "/sys/fs/cgroup/$key" | tr -d '\r')"
  [[ "$actual" == "$expect" ]] || fail "Kernel resource quota $key differs from expected."
done
r exec "$dev" /usr/local/bin/codex login status >/dev/null ||
  fail "Codex login unavailable; authenticate inside the rootless dev container and rerun."
say "PASS: tools, 2 CPU, 4 GiB, 256 PIDs, Codex credentials."
# Authenticated MCP test from an ephemeral container on the PRIVATE bridge.
# Never print credentials, publish MCP ports or use system Docker.
probe="$(cat <<'PY'
import json,sys,urllib.request,urllib.error,time
token=open('/run/secrets/mcp-bearer').read().strip()
url='http://manager:8767/mcp'
def call(obj,auth=True):
    hdr={'Content-Type':'application/json',
         'Accept':'application/json, text/event-stream',
         'MCP-Protocol-Version':'2025-06-18'}
    if auth: hdr['Authorization']=token
    req=urllib.request.Request(url,data=json.dumps(obj).encode(),headers=hdr,method='POST')
    with urllib.request.urlopen(req,timeout=10) as res:
        return res.status,json.load(res)
init={'jsonrpc':'2.0','id':1,'method':'initialize','params':{
    'protocolVersion':'2025-06-18','capabilities':{},
    'clientInfo':{'name':'panolab-laptop-local-acceptance','version':'1'}}}
try:
    call(init,False)
except urllib.error.HTTPError as e:
    if e.code!=401: raise
else:
    raise RuntimeError('Anonymous MCP call was accepted')
for attempt in range(12):
    try:
        code,obj=call(init)
        assert code==200 and obj.get('result',{}).get('serverInfo',{}).get('name')=='panolab-manager'
        break
    except (urllib.error.URLError,AssertionError):
        if attempt==11: raise
        time.sleep(1)
for i,tool in enumerate(('lab_status','repo_status'),2):
    code,obj=call({'jsonrpc':'2.0','id':i,'method':'tools/call',
                  'params':{'name':tool,'arguments':{}}})
    assert code==200 and not obj.get('error') and not obj.get('result',{}).get('isError'),tool
print('PASS: private authenticated MCP, anonymous request rejected, status and repo tools')
PY
)"
# Match Compose's project-scoped bridge and verify its labels before
# attaching the one-shot authenticated MCP probe.
mcp_network="${project}_lab-backend"
network_owner="$(r network inspect "$mcp_network" \
  --format '{{index .Labels "com.docker.compose.project"}}/{{index .Labels "com.docker.compose.network"}}' \
  2>/dev/null || true)"
[[ "$network_owner" == "$project/lab-backend" ]] ||
  fail "Expected project-owned rootless MCP bridge unavailable."
r run --rm --network "$mcp_network" --read-only --cap-drop ALL \
  --security-opt no-new-privileges:true \
  --mount "type=bind,src=$private/mcp-bearer,dst=/run/secrets/mcp-bearer,readonly" \
  --entrypoint python3 panolab-direct-broker:local -c "$probe" ||
  fail "Authenticated MCP test failed; rootless services retained."
say "PASS: rootless manager and MCP broker; starting private tunnel."
# Standalone rootless deployment: never touch the system Docker Engine.
if ! "${compose[@]}" up -d --no-build --no-recreate tunnel; then
  fail "Rootless tunnel failed to start."
fi
sleep 5
running_new "$tunnel" || fail "Rootless tunnel is not running."
say "SUCCESS: rootless Docker PanoLab stack deployed on your laptop."
say "Confirm authenticated remote lab_status and repo_status separately."
say "No host package install, global Docker cleanup, ISE installation or FPGA programming."
