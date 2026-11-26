# External storage cutover

Use an owner-local terminal connected to the laptop's ordinary-user rootless
Engine. The tunnel will disconnect during cutover. Keep the terminal and the
previous source revision available until authenticated service checks pass.
The filesystem command moves data and writes a metadata-only journal. Service
replacement and rollback are explicit owner-local steps.

The read-only preflight below is automated. Full cutover and rollback still
use the operator steps in this runbook. The existing launchers create
replacements under fixed names without a transaction-specific label.
An interruption between creation and recording the new ID leaves automatic
rollback without evidence that it owns that container. A full cutover
command needs recoverable replacement identity on every creation path and
must keep ingress and other writers quiescent throughout the transaction.

## Stage and verify

1. In an isolated candidate, pass the host, broker and source test suites.
   Render all profiles with synthetic inputs via the trusted rootless
   maintenance venue. Build the required candidate images before downtime.
   Tag the approved images locally and record image IDs. Use the exact already
   approved ISE worker and modern development image IDs. Keep the previous
   service image IDs and tags available for rollback.
2. On the laptop, use the recorded 12-container inventory. Refresh only
   names, IDs, image IDs, running state, restart policies, mount sources,
   targets and write flags. Compare the worker's resource requirements,
   internal network, owner mapping and read-only security flags with
   `host/ise14-bringup.py` before using its rebind action. Keep the worker
   virtual MAC private. Save the inventory locally with mode 0600 outside
   the checkout. Avoid full Docker inspection output.
3. Provision both external directories as owner-only directories on the
   checkout's filesystem. Verify physical paths (no symlinks). From a
   trusted owner shell, set the paths below or substitute previously
   approved absolute site-specific paths. Keep the journal outside the
   source checkout.

```bash
umask 077
export PYTHONDONTWRITEBYTECODE=1
export PANOLAB_CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/panolab"
export PANOLAB_DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/panolab"
export PANOLAB_REPO_HOST="$(pwd -P)"
export PANOLAB_ROOTLESS_SOCKET="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/docker.sock"
export PANOLAB_WORKSPACE_HOST="$PANOLAB_DATA_DIR/agent-workspace"
export PANOLAB_CODEX_AUTH_HOST="$PANOLAB_CONFIG_DIR/codex-auth"
export PANOLAB_ISE_TARBALL="$PANOLAB_DATA_DIR/Xilinx_ISE_DS_Lin_14.7_1015_1.tar"
r() { docker -H "unix://$PANOLAB_ROOTLESS_SOCKET" "$@"; }
# Create the two roots only if they do not already exist.
for directory in "$PANOLAB_CONFIG_DIR" "$PANOLAB_DATA_DIR"; do
  if [[ ! -e "$directory" && ! -L "$directory" ]]; then
    install -d -m 0700 -- "$directory"
  fi
done
compose() {
  r compose --project-name panolab-direct-external \
    --env-file "$PANOLAB_CONFIG_DIR/.env" \
    -f docker/compose.setup.yaml -f docker/compose.manage.yaml \
    -f host/compose.rootless-laptop.yaml "$@"
}
```

From the canonical checkout, fetch the reviewed `development` revision from
`origin` without switching or merging. Stage a separate clean checkout at
that exact target revision. With new submissions blocked, all jobs drained
and host writers quiescent, run the following from the owner-local terminal.
Set the variables to the approved full commit and image IDs, the path to the
clean reviewed checkout, and the path and approved SHA-256 of the mode-0600
sanitized inventory. Keep the inventory outside both checkouts and storage roots.

```bash
python3 -B "$reviewed_checkout/host/cutover-external-storage.py" --preflight \
  --checkout "$PANOLAB_REPO_HOST" --baseline "$baseline_sha" --target "$reviewed_sha" \
  --inventory "$inventory_file" --inventory-sha256 "$inventory_sha256" \
  --broker-image panolab-direct-broker:external-85ddd33 "$broker_image_id" \
  --repo-git-image panolab-direct-repo-git:external-85ddd33 "$repo_git_image_id" \
  --jobs-drained
```

The preflight verifies the clean baseline and reviewed descendant, the
rootless Engine, container identities, mounts and image tags, and calls the
existing migration dry-run. The dry-run checks the exact archive basename,
all 11 entries, the separate legacy env file, ownership, modes, types and
filesystem, and terminal ISE status. The owner confirms job drain and writer
quiescence. Repeat the dry-run from the canonical checkout immediately before
applying the moves.

For synthetic Compose rendering, export temporary absolute config/data roots
and derived paths as above, and use a synthetic `.env` with a fake tunnel ID
and fake MCP token. Run:

```bash
compose --profile ise-setup --profile trusted-maintenance config --quiet
compose --profile ise-setup --profile trusted-maintenance config --format json
```

Inspect the synthetic render for each external bind and matching access mode.
The Git push overlay adds a read-only `/run/panolab-git-auth` bind only to
`repo-git`. Check the overlay by appending
`-f docker/compose.git-push.yaml` before `config --format json`. For the
real owner env, use quiet mode and keep command output limited to sanitized
mount and container metadata. The new Compose project retains the canonical
container names and uses a separate service network. It reuses the external
`panolab-direct-connect_management-rpc` volume with the old broker stopped.

## Cut over from the local terminal

1. Record a local rollback branch pointing to the previous exact
   `development` HEAD while the checkout is clean. Block new submissions
   and confirm that normal dev/Codex, vendor/setup and disposable acceptance
   jobs are all terminal. Preserve the pending result and job records.
   Verify no other owner process is writing either storage location.
2. Match all seven running containers, stopped setup and four stopped
   backups by exact full ID, name, image and restart policy. Use
   `r inspect --format '{{.Id}}|{{.Name}}|{{.Image}}|{{.State.Status}}|{{.HostConfig.RestartPolicy.Name}}|{{.HostConfig.RestartPolicy.MaximumRetryCount}}' NAME`.
   For each of the 12 IDs, use `r update --restart=no "$old_id"`. Keep their
   original restart values in the protected inventory. This temporarily
   prevents a daemon restart from restarting an old container with moved
   binds. Do not start or rename the four pre-existing stopped backups.
3. Stop the old tunnel to close ingress, then manager, broker, Git gateway,
   worker and development by recorded ID. Stop maintenance last. Setup
   stays stopped. Confirm every legacy container is stopped. Rename the
   seven formerly active containers and stopped setup by exact ID using
   `r rename "$old_id" "$old_name-pre-external-$unique_suffix"`. Check
   destination names are free before the first rename and journal names
   as each rename succeeds. Keep all old containers and their images.
4. Fast-forward the clean canonical `development` checkout to the reviewed
   candidate while the old broker's live source bind is stopped. Run:

   ```bash
   python3 -B host/migrate-external-storage.py dry-run
   python3 -B host/migrate-external-storage.py apply --jobs-drained
   python3 -B docker/control/dev_source.py "$PANOLAB_REPO_HOST"
   bash ./panolab-install.sh --check
   ```

   The migration checks that no running container has a bind at, above or
   below any affected root. It uses same-filesystem non-overwriting renames
   and journals intent before every move, then saves completion after syncing
   each directory. On a recoverable move error it reverses completed moves.
   The explicit rollback action reconciles an interrupted rename from
   source/destination inode identity. No mount should keep the old source
   and destination inode exposed concurrently.
5. With the pre-staged tags verified, run:

   ```bash
   compose --profile ise-setup create --no-build setup
   compose --profile trusted-maintenance up -d --no-deps --no-build trusted-maintenance
   python3 -B host/ise14-bringup.py rebind-worker \
     --expected-worker-image "$recorded_worker_image_id" \
     --worker-restart "$recorded_worker_restart"
   bash ./panolab-install.sh
   ```

   If the original gateway carried Git auth, run
   `compose -f docker/compose.git-push.yaml create --no-build repo-git`
   **before** invoking the installer. The installer reuses that staged
   gateway. It starts broker, gateway, manager and development, runs local
   authentication and starts the tunnel last.
   Use the recorded restart policies to validate the replacements. Setup
   remains stopped, and the worker binds its existing installed binaries,
   license, token, projects and results. Its rebind action uses the exact
   image ID and skips all installer, fixture-write and token-generation work.

## Verify the original interfaces

- On the rootless Engine, compare the dev bind and its Git mask using
  `r inspect --format '{{json .Mounts}} {{json .HostConfig.Tmpfs}}' panolab-direct-dev-1 |
  python3 -B docker/control/dev_source.py --mounts "$PANOLAB_REPO_HOST"
  "$PANOLAB_WORKSPACE_HOST" "$PANOLAB_CODEX_AUTH_HOST"` and then run
  `r exec panolab-direct-dev-1 /bin/sh -ec "$(python3 -B docker/control/dev_source.py --probe)"`.
  Confirm only the approved workspace and auth binds are writable. Check
  write denial with `r exec panolab-direct-dev-1 touch /repo/.source-write-test`
  and require a read-only filesystem error. Stop if the write succeeds.
- Under independent local supervision, atomically replace a tracked root
  document with byte-identical content and preserved mode using a temporary
  file in the same directory. Compare `stat -c %i /repo/AGENTS.md` inside dev
  before and after. Require an inode change, identical file hash, an empty
  read-only Git mask and absent legacy paths. Recheck the clean checkout.
- Use authenticated MCP `lab_status`, `repo_status` and ordinary `dev_exec`
  on the recreated stack. Require anonymous denial and verify Codex login and
  kernel resource limits. Run `dev_exec` with
  `["@maintenance","bash","-c","bash \"$PANOLAB_REPO_HOST/host/trusted-maintenance.sh\" check"]`
  from the new sidecar only. Use normal MCP to start setup, run
  `["@setup","status"]` and stop setup. Then run
  `["@ise14","toolchain_info"]`, stage the known approved smoke fixture
  with `["@ise14","stage","smoke"]` and use the returned immutable project name
  for `["@ise14","build_start","PROJECT"]`. Poll `build_status` and obtain
  `build_result` with the returned ID. Check all six stages, output and
  SHA-256 while setup stays stopped. Where disposable install acceptance is
  required, run the existing `["@ise-e2e","preflight"]`, `start`, `status`
  and `result` workflow through normal MCP. Preserve bounded evidence.
- Verify all 12 old IDs still exist with the exact original images. Keep
  their restart settings disabled while their source paths remain absent.
  Keep the original policies in the protected rollback inventory.

## Roll back from the local terminal

1. Disable replacement restarts and stop only the explicitly recorded new
   IDs, tunnel first and maintenance last. Remove only those replacement
   IDs after rechecking their identity. Keep the original management RPC
   volume and old network. Do not run Compose `down` against the old project.
2. With all affected containers quiescent and the candidate source still
   available, run `python3 -B host/migrate-external-storage.py rollback
   --jobs-drained`. Verify legacy paths, modes and original entry identities
   against the saved inventory and journal. Do not start any old container
   while its legacy paths are absent. If a rename cannot be reversed, keep
   affected services stopped and preserve the journal.
3. Switch the clean canonical checkout to the pre-cutover local rollback
   branch so the old broker sees its matching live source. Restore original
   tags where needed. Rename the eight retained containers back by stored
   ID, and restore all 12 recorded restart policies with
   `r update --restart="$old_policy" "$old_id"` (include the recorded retry
   count for `on-failure:N`). Start only the seven originally running IDs.
   Start broker, Git gateway, worker and dev first, then manager and
   maintenance, then tunnel. Confirm the on-demand setup and four
   pre-existing backups remain stopped.
4. Verify local authenticated and anonymous probes, remote status, Git,
   development credentials and licensed worker health through the previous
   normal interface. Keep the metadata journal for review.
