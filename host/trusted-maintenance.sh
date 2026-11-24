#!/usr/bin/env bash
# TEMPORARY trusted owner-user maintenance inside the rootless sidecar.
# Source is live mounted. No sudo, rootful Engine, or FPGA programming.
set -Eeuo pipefail
umask 077
ACTION=status
if [[ "$#" -gt 0 ]]; then ACTION="$1"; fi
PROJECT=panolab-direct-connect
BROKER=panolab-direct-connect-docker-broker-1
MANAGER=panolab-direct-connect-manager-1
MAINT=panolab-direct-trusted-maintenance
REPO="$PANOLAB_REPO_HOST"
[[ "$PANOLAB_TRUSTED_MAINTENANCE" == 1 ]] || { echo "TRUSTED_MAINTENANCE_DISABLED"; exit 9; }
[[ "$DOCKER_HOST" == unix:///var/run/docker.sock ]] || { echo "WRONG_DOCKER_SOCKET"; exit 9; }
[[ -d "$REPO/docker/control" && -f "$REPO/docker/.env" ]] || { echo "REPO_NOT_MOUNTED"; exit 9; }
docker info --format '{{json .SecurityOptions}}' | grep -Fq '"name=rootless"' || {
  echo "ROOTLESS_DOCKER_REQUIRED"; exit 9;
}
mkdir -p /workspace/maintenance
export PANOLAB_MAINTENANCE_ACTION="$ACTION"
report=/workspace/maintenance/latest.log
status() {
  python3 - "$1" "$2" <<'PY'
import json,os,sys,tempfile
target="/workspace/maintenance/status.json"
fd,temp=tempfile.mkstemp(dir="/workspace/maintenance",prefix=".status-")
with os.fdopen(fd,"w") as out:
    json.dump({"operation":os.environ["PANOLAB_MAINTENANCE_ACTION"],
               "status":sys.argv[1],"detail":sys.argv[2]},out)
os.replace(temp,target)
PY
}
composed() {
 docker compose --project-name "$PROJECT" --profile trusted-maintenance \
  --env-file "$REPO/docker/.env" \
  -f "$REPO/docker/compose.setup.yaml" \
  -f "$REPO/docker/compose.manage.yaml" \
  -f "$REPO/host/compose.rootless-laptop.yaml" "$@"
}
canary() {
  docker exec "$BROKER" python3 -c \
    'import sys;sys.path.insert(0,"/usr/local/lib/panolab-control");import ise_proxy,ise_staging;assert "build_start" in ise_proxy.TOOLS'
  for name in "$BROKER" "$MANAGER" "$MAINT" "$PROJECT-tunnel-1"; do
    [[ "$(docker inspect --format '{{.State.Running}}' "$name")" == true ]]
  done
  probe="$(cat <<'PY'
import json,urllib.request
secret=open('/run/secrets/mcp-bearer').read().strip()
def call(method,params,i):
    body={'jsonrpc':'2.0','id':i,'method':method,'params':params}
    req=urllib.request.Request('http://manager:8767/mcp',
      data=json.dumps(body).encode(),headers={
       'Authorization':secret,'Content-Type':'application/json',
       'Accept':'application/json, text/event-stream',
       'MCP-Protocol-Version':'2025-06-18'},method='POST')
    with urllib.request.urlopen(req,timeout=25) as resp:return json.load(resp)
names={x['name'] for x in call('tools/list',{},1).get('result',{}).get('tools',[])}
assert 'dev_exec' in names
answer=call('tools/call',{'name':'dev_exec','arguments':{
    'Argv':['@maintenance','python3','-c','print("REMOTE_MAINTENANCE_OK")'],
    'User':'root'}},2)
assert not answer.get('error') and not answer.get('result',{}).get('isError')
r=answer['result'].get('structuredContent') or {}
assert r.get('ok') is True and 'REMOTE_MAINTENANCE_OK' in r.get('stdout','')
print('TRUSTED_REMOTE_MAINTENANCE_MCP=PASS')
PY
)"
  docker run --rm --network "$PROJECT"_lab-backend --read-only --cap-drop ALL \
   --security-opt no-new-privileges:true \
   --mount "type=bind,src=$REPO/docker/private/mcp-bearer,dst=/run/secrets/mcp-bearer,readonly" \
   --entrypoint python3 python:3.12-alpine -c "$probe"
}
case "$ACTION" in
  status)
    docker ps -a --filter name=panolab-direct --format '{{.Names}} {{.Status}}'
    echo "TEMPORARY_TRUSTED_MAINTENANCE=ACTIVE"
    ;;
  check)
    # This command can be called *synchronously* via the broker. Do not
    # recurse into MCP while the broker's serialized request is in flight.
    composed config --quiet
    docker exec "$BROKER" python3 -c       'import sys;sys.path.insert(0,"/usr/local/lib/panolab-control");import ise_proxy,ise_staging;assert "build_start" in ise_proxy.TOOLS'
    [[ "$(docker inspect --format '{{.State.Running}}' "$MANAGER")" == true ]]
    [[ "$(docker inspect --format '{{.State.Running}}' "$MAINT")" == true ]]
    echo "REMOTE_MAINTENANCE_DIRECT_CHECK=PASS"
    ;;
  reload-broker)
    # Run detached: restart interrupts the originating MCP broker request.
    status running "Restarting broker from live-mounted Python source"
    if (docker restart "$BROKER" && canary); then
      status pass "Broker restarted, remote maintenance canary passed"
      echo "REMOTE_BROKER_RELOAD=PASS"
    else
      status failed "Broker restart or remote canary failed; inspect latest.log"
      exit 9
    fi > "$report" 2>&1
    ;;
  deploy-management)
    # Run detached. Only local PanoLab manager and broker are recreated.
    status running "Compiling and testing management images"
    {
      stamp="$(date -u +%Y%m%dT%H%M%SZ)"
      old_broker="panolab-direct-broker:remote-backup-$stamp"
      old_manager="panolab-direct-manager:remote-backup-$stamp"
      new_broker="panolab-direct-broker:remote-candidate-$stamp"
      new_manager="panolab-direct-manager:remote-candidate-$stamp"
      docker buildx build --builder default --load -t "$new_broker" \
        -f "$REPO/docker/control/Broker.Dockerfile" "$REPO/docker/control" ||
        { status failed "Broker candidate build/tests failed; running services untouched"; exit 9; }
      docker buildx build --builder default --load -t "$new_manager" \
        -f "$REPO/docker/control/Manager.Dockerfile" "$REPO/docker" ||
        { status failed "Manager candidate build/tests failed; running services untouched"; exit 9; }
      docker image tag panolab-direct-broker:local "$old_broker" ||
        { status failed "Broker backup image unavailable; deployment aborted"; exit 9; }
      docker image tag panolab-direct-manager:local "$old_manager" ||
        { status failed "Manager backup image unavailable; deployment aborted"; exit 9; }
      docker image tag "$new_broker" panolab-direct-broker:local ||
        { status failed "Broker candidate tagging failed; no service recreated"; exit 9; }
      docker image tag "$new_manager" panolab-direct-manager:local ||
        { docker image tag "$old_broker" panolab-direct-broker:local || true;
          status failed "Manager candidate tagging failed; no service recreated"; exit 9; }
      echo "BACKUP_TAGS=$old_broker $old_manager"
      if ! composed up -d --no-deps --no-build --force-recreate docker-broker manager ||
         ! canary; then
        echo "REMOTE_CANARY_FAILED_ROLLBACK=START"
        docker image tag "$old_broker" panolab-direct-broker:local
        docker image tag "$old_manager" panolab-direct-manager:local
        composed up -d --no-deps --no-build --force-recreate docker-broker manager || true
        status failed "Management deploy failed; old image tags restored"
        exit 9
      fi
      status pass "Manager and broker tested, replaced and canary verified"
      echo "REMOTE_MANAGEMENT_DEPLOY=PASS"
    } > "$report" 2>&1 || {
      status failed "Remote deployment error; inspect maintenance/latest.log"
      exit 9
    }
    ;;
  *)
    echo "USAGE: trusted-maintenance.sh status|check|reload-broker|deploy-management" >&2
    exit 9
    ;;
esac
