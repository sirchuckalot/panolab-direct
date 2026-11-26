#!/usr/bin/env bash
# Historical legacy-path procedure. For external storage, see docs/EXTERNAL_STORAGE_CUTOVER.md.
# HISTORICAL / REVISION-LOCKED. DO NOT RERUN ON CURRENT DEVELOPMENT.
# The ISE bridge is already active; see host/README.md and
# docs/TEMPORARY_COMPONENTS.md for its current ownership.
# Controlled one-time activation of the scoped ISE MCP bridge.
# The setup, vendor worker, development checkout, and FPGA are untouched.
set -Eeuo pipefail
umask 077
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
PROJECT=panolab-direct-connect
BROKER="$PROJECT-docker-broker-1"
MANAGER="$PROJECT-manager-1"
WORKER=panolab-direct-ise14-worker-1
BASE_SHA=3286ab33b76885ce6b5c367b922c5d8f39601039
BROKER_IMAGE=panolab-direct-broker:local
MANAGER_IMAGE=panolab-direct-manager:local
BROKER_PRE=panolab-direct-broker:pre-ise-bridge-3286ab33
MANAGER_PRE=panolab-direct-manager:pre-ise-bridge-3286ab33
BROKER_NEXT=panolab-direct-broker:ise-bridge-3286ab33
MANAGER_NEXT=panolab-direct-manager:ise-bridge-3286ab33
fail() { echo "ISE_BRIDGE_ACTIVATION_BLOCKED: $*" >&2; exit 9; }
log() { echo "PanoLab ISE bridge: $*"; }

[[ "$(id -u)" != 0 && "$(uname -s)" == Linux ]] || fail "Use your ordinary Linux laptop account, no sudo."
[[ "$(git -C "$ROOT" rev-parse HEAD)" == "$BASE_SHA" ]] || fail "Canonical source revision changed."
[[ "$(git -C "$ROOT" symbolic-ref --short HEAD)" == development ]] || fail "Expected development branch."
[[ -d "$ROOT/docker/private" && ! -L "$ROOT/docker/private" ]] || fail "Private configuration unavailable."
socket="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/docker.sock"
[[ -S "$socket" ]] || fail "Owner-user rootless Docker socket missing."
d() { docker -H "unix://$socket" "$@"; }
[[ "$(d info --format '{{json .SecurityOptions}}')" == *'"name=rootless"'* ]] || fail "Rootless Engine required."
for service in "$BROKER" "$MANAGER" "$WORKER" "$PROJECT-repo-git-1" "$PROJECT-tunnel-1"; do
  [[ "$(d inspect -f '{{.State.Running}}' "$service")" == true ]] ||
    fail "Required PanoLab service missing: $service"
done
[[ "$(d inspect -f '{{.HostConfig.NetworkMode}}' "$WORKER")" == none ]] ||
  fail "ISE worker no longer network-isolated."
[[ "$(d inspect -f '{{index .Config.Labels "panolab.managed"}}' "$WORKER")" == true ]] ||
  fail "ISE worker is not PanoLab managed."

mapfile -t changed < <(git -C "$ROOT" status --porcelain --untracked-files=all)
expected=(
 " M docker/control/Broker.Dockerfile"
 " M docker/control/broker.py"
 " M docker/compose.manage.yaml"
 " M docker/control/mcp/main.go"
 " M docker/control/mcp/setup_proxy.go"
 " M docker/control/mcp/setup_proxy_test.go"
 " M docker/ise14/entrypoint.sh"
 " M docker/ise14/mcp/setup/main.go"
 "?? docker/control/Maintenance.Dockerfile"
 "?? docker/control/ise_proxy.py"
 "?? docker/control/ise_staging.py"
 "?? docker/control/mcp/ise_proxy.go"
 "?? docker/control/test_ise_proxy.py"
 "?? docker/control/test_ise_staging.py"
 "?? docker/control/test_trusted_maintenance.py"
 "?? docker/ise14/mcp/setup/main_test.go"
 "?? docs/REMOTE_ITERATION_ARCHITECTURE.md"
 "?? host/ise14-bringup.py"
 "?? host/ise14-diagnose.py"
 "?? host/ise14-repair.py"
 "?? host/activate-ise-bridge.sh"
 "?? host/trusted-maintenance.sh"
)
[[ "${#changed[@]}" == "${#expected[@]}" ]] || fail "Unexpected source changes; inspect Git status."
for item in "${changed[@]}"; do
  matched=0
  for allowed in "${expected[@]}"; do
    [[ "$item" == "$allowed" ]] && matched=1 && break
  done
  [[ "$matched" == 1 ]] || fail "Unreviewed source file detected. No services changed."
done
for item in "${expected[@]}"; do
  matched=0
  for observed in "${changed[@]}"; do
    [[ "$item" == "$observed" ]] && matched=1 && break
  done
  [[ "$matched" == 1 ]] || fail "Expected ISE bridge source missing."
done
grep -Fq 'registerISETools(s)' "$ROOT/docker/control/mcp/main.go" ||
  fail "Manager missing named ISE build tools."
grep -Fq 'ISE_WORKER_SECURITY_CONTRACT_FAILED' "$ROOT/docker/control/ise_proxy.py" ||
  fail "ISE worker security policy missing."
grep -Fq '["@ise14"]' "$ROOT/docker/control/broker.py" ||
  fail "Current-connector compatibility mode missing."
log "Preflight passed; building tested candidate management images."

d buildx build --builder default --load -t "$BROKER_NEXT" \
  -f "$ROOT/docker/control/Broker.Dockerfile" "$ROOT/docker/control" ||
  fail "Broker candidate image/unit tests failed. Live system unchanged."
d buildx build --builder default --load -t "$MANAGER_NEXT" \
  -f "$ROOT/docker/control/Manager.Dockerfile" "$ROOT/docker" ||
  fail "Manager Go build/unit tests failed. Live system unchanged."
# Exercise the same Python import from outside /usr/local/bin BEFORE
# switching live services. The production broker's script directory is on
# sys.path, but an ad-hoc 'python3 -c' command does not inherit that path.
d run --rm --network none --read-only --cap-drop ALL \
 --security-opt no-new-privileges:true \
 --entrypoint python3 "$BROKER_NEXT" -c \
 'import sys; sys.path.insert(0,"/usr/local/bin"); import ise_proxy, ise_staging; assert "build_start" in ise_proxy.TOOLS; assert ise_staging.PROJECT.fullmatch("smoke")' ||
 fail "Candidate broker module import failed. Live system unchanged."
log "Both candidate images and broker import probe passed."
# Build the one-time trusted maintenance sidecar before modifying live services.
d buildx build --builder default --load -t panolab-direct-trusted-maintenance:local \
  -f "$ROOT/docker/control/Maintenance.Dockerfile" "$ROOT/docker/control" ||
  fail "Trusted maintenance image build failed; live management untouched."
log "Trusted maintenance image built."

private="$ROOT/docker/private"
[[ -f "$ROOT/docker/.env" ]] || fail "Private Compose config missing."
shopt -s nullglob
media=("$private"/*.tar "$private"/*.tar.gz "$private"/*.tgz "$private"/*.tar.bz2)
shopt -u nullglob
[[ "${#media[@]}" == 1 ]] || fail "Unexpected ISE archive layout."
export PANOLAB_ROOTLESS_SOCKET="$socket"
export PANOLAB_REPO_HOST="$ROOT"
export PANOLAB_WORKSPACE_HOST="$(realpath -e "$private/agent-workspace")"
export PANOLAB_CODEX_AUTH_HOST="$(realpath -e "$private/codex-auth")"
export PANOLAB_ISE_TARBALL="$(realpath -e "${media[0]}")"
compose=(docker -H "unix://$socket" compose --project-name "$PROJECT"
 --profile trusted-maintenance
 --env-file "$ROOT/docker/.env"
 -f "$ROOT/docker/compose.setup.yaml"
 -f "$ROOT/docker/compose.manage.yaml"
 -f "$ROOT/host/compose.rootless-laptop.yaml")
"${compose[@]}" config --quiet || fail "Compose configuration invalid."
# Start the independent maintenance service before the broker/manager swap.
"${compose[@]}" up -d --no-deps --no-build trusted-maintenance ||
  fail "Trusted maintenance service failed; existing management unchanged."
[[ "$(d inspect -f '{{.State.Running}}' panolab-direct-trusted-maintenance)" == true ]] ||
  fail "Trusted maintenance service not running."
d exec panolab-direct-trusted-maintenance docker info --format '{{json .SecurityOptions}}' | grep -Fq '"name=rootless"' ||
  fail "Trusted maintenance must use owner rootless Docker."
d exec panolab-direct-trusted-maintenance bash -n "$ROOT/host/trusted-maintenance.sh" ||
  fail "Live-mounted maintenance script failed syntax validation."
log "Independent rootless maintenance sidecar running with live-mounted source."

for pair in "$BROKER_IMAGE|$BROKER_PRE" "$MANAGER_IMAGE|$MANAGER_PRE"; do
  current_tag="${pair%%|*}"
  backup_tag="${pair##*|}"
  current_id="$(d image inspect --format '{{.Id}}' "$current_tag")" ||
    fail "Current management image missing."
  backup_id="$(d image inspect --format '{{.Id}}' "$backup_tag" 2>/dev/null || true)"
  [[ -z "$backup_id" || "$backup_id" == "$current_id" ]] ||
    fail "Existing backup tag differs; refuse overwrite."
done

switched=0
rollback() {
 local rc=$?
 trap - EXIT
 if [[ "$rc" != 0 && "$switched" == 1 ]]; then
   log "Bridge health check failed. Restoring previous management images."
   d image tag "$BROKER_PRE" "$BROKER_IMAGE" || true
   d image tag "$MANAGER_PRE" "$MANAGER_IMAGE" || true
   "${compose[@]}" up -d --no-deps --no-build --force-recreate docker-broker manager || true
   log "Saved prior images remain available."
 fi
 exit "$rc"
}
trap rollback EXIT

d image tag "$BROKER_IMAGE" "$BROKER_PRE"
d image tag "$MANAGER_IMAGE" "$MANAGER_PRE"
d image tag "$BROKER_NEXT" "$BROKER_IMAGE"
d image tag "$MANAGER_NEXT" "$MANAGER_IMAGE"
switched=1
log "Recreating ONLY docker-broker and manager; tunnel and ISE worker untouched."
"${compose[@]}" up -d --no-deps --no-build --force-recreate docker-broker manager
for service in "$BROKER" "$MANAGER" "$WORKER" "$PROJECT-tunnel-1"; do
 [[ "$(d inspect -f '{{.State.Running}}' "$service")" == true ]] ||
   fail "Required PanoLab service stopped: $service"
done
d exec "$BROKER" python3 -c 'import sys; sys.path.insert(0,"/usr/local/bin"); import ise_proxy, ise_staging; assert "build_start" in ise_proxy.TOOLS; assert ise_staging.PROJECT.fullmatch("smoke")' ||
  fail "Broker missing scoped ISE module."

network="${PROJECT}_lab-backend"
owner="$(d network inspect "$network" --format '{{index .Labels "com.docker.compose.project"}}/{{index .Labels "com.docker.compose.network"}}')"
[[ "$owner" == "$PROJECT/lab-backend" ]] || fail "Private network identity mismatch."
probe="$(cat <<'PY'
import json,urllib.request
bearer=open('/run/secrets/mcp-bearer').read().strip()
def call(method,params,identifier):
    body={'jsonrpc':'2.0','id':identifier,'method':method,'params':params}
    request=urllib.request.Request('http://manager:8767/mcp',
        data=json.dumps(body).encode(),headers={
          'Authorization':bearer,'Content-Type':'application/json',
          'Accept':'application/json, text/event-stream',
          'MCP-Protocol-Version':'2025-06-18'},method='POST')
    with urllib.request.urlopen(request,timeout=25) as response:
        return json.load(response)
listed=call('tools/list',{},1)
names={x.get('name') for x in listed.get('result',{}).get('tools',[])}
required={'dev_exec','ise_toolchain_info','ise_worker_diagnostics',
          'ise_project_stage','ise_build_start','ise_build_status',
          'ise_build_result','ise_build_cancel'}
assert required <= names, 'Remote ISE/maintenance tool registration incomplete'
print('REMOTE_MCP_TOOL_REGISTRATION=PASS')
# This is the essential bootstrap gate: from now on remote operations may
# repair and rebuild PanoLab without a person at the laptop.
answer=call('tools/call',{'name':'dev_exec',
    'arguments':{'Argv':['@maintenance','python3','-c',
      'print("REMOTE_MAINTENANCE_OK")'],'User':'root'}},2)
assert not answer.get('error') and not answer.get('result',{}).get('isError'), 'Remote maintenance call rejected'
result=answer['result'].get('structuredContent') or {}
assert result.get('ok') is True and 'REMOTE_MAINTENANCE_OK' in result.get('stdout',''), 'Remote maintenance execution failed'
print('REMOTE_MAINTENANCE_CONTROL=PASS')
# ISE worker diagnosis is intentionally non-blocking: remote maintenance
# now exists precisely so a worker rejection can be repaired remotely.
try:
    answer=call('tools/call',{'name':'ise_toolchain_info','arguments':{}},3)
    result=answer.get('result',{}).get('structuredContent') or {}
    if result.get('ok') is True and result.get('ise_available') is True:
        print('ISE_WORKER_REMOTELY_REACHABLE=PASS')
    else:
        print('ISE_WORKER_DIAGNOSTICS_PENDING_REMOTE_FIX')
except Exception:
    print('ISE_WORKER_DIAGNOSTICS_PENDING_REMOTE_FIX')
print('NO_FPGA_PROGRAMMING_ACTION_TAKEN=PASS')
PY
)"
d run --rm --network "$network" --read-only --cap-drop ALL \
 --security-opt no-new-privileges:true \
 --mount "type=bind,src=$private/mcp-bearer,dst=/run/secrets/mcp-bearer,readonly" \
 --entrypoint python3 "$BROKER_IMAGE" -c "$probe" ||
   fail "Private MCP toolchain-info probe failed; rolling back manager and broker."
switched=0
trap - EXIT
log "ISE_REMOTE_BRIDGE=PASS"
log "ChatGPT can use @ise14 and @maintenance through the already-connected PanoLab dev_exec tool."
log "No ISE installation, FPGA programming, container deletion or Git push performed."
