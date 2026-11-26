# Host scripts: supported, guarded and historical

The supported ordinary-user entrypoint is
[`../panolab-install.sh`](../panolab-install.sh), which delegates to
[`rootless-install.sh`](rootless-install.sh). Do not run migration or
recovery scripts solely because they remain in this directory.

See [architecture](../docs/ARCHITECTURE.md) for current operation and
[temporary maintenance retirement](../docs/ARCHITECTURE.md#temporary-maintenance-and-retirement).

## Supported entrypoint and explicit operations

| File | Status | Expected use |
| --- | --- | --- |
| `migrate-external-storage.py` | Historical owner-local storage transaction | See the [cutover and rollback procedure](../docs/EXTERNAL_STORAGE_CUTOVER.md) |
| `rootless-install.sh` | Current supported host launcher | Ordinary-user, rootless Docker, already provisioned private inputs; default setup remains on demand |
| `fresh-host-audit.py` | Current read-only diagnostic | `panolab-install.sh --fresh-host-check`; **never** treats prerequisite readiness as a successful fresh-host install |
| `compose.rootless-laptop.yaml` | Current host-specific Compose overlay | Rootless owner mapping, safe private mounts and resource policy |
| `test_fresh_host_audit.py` | Regression tests | Clean-home/credential-exclusion/source validation |
| `upgrade-dev-image.sh` | Guarded explicit maintenance | Modern tool image upgrade only after version and rollback checks |
| `enable-github-push.sh` | Guarded opt-in credential setup | Fine-grained, owner-scoped push credential for `development`; never general agent credentials |
| `install-rootless-buildx.sh` | Guarded one-time dependency helper | Only if Buildx is actually missing; preserve unrelated Docker installations |
| `finalize-dev-maintenance.sh` | Guarded one-time cleanup tool | Named previously approved dev rollback only, no global prune |
| `ise14-bringup.py` / `ise14-diagnose.py` | Guarded specialized vendor tools | Historical/diagnostic commissioning; normal remote builds use `@ise14`, disposable installation uses `@ise-e2e` |
| `trusted-maintenance.sh` | **Active temporary** | Only to inspect, correct or recover normal remote infrastructure |

## Historical — DO NOT RERUN on current branch

The following revision-locked operations are preserved for provenance and
recovery research but are **not routine commands**:

- `reconcile-and-upgrade.sh` — a specific old Git-history reconciliation
- `apply-source-migration.sh` — old source-migration candidate cutover
- `activate-ise-bridge.sh` — old ISE manager/broker bootstrap
- `ise14-repair.py` — old GNU tar ownership repair

They have hard-coded past revision assumptions; **do not silently edit
those pins to force them to run**. Use the current control plane or a
reviewed new migration procedure instead.

No host script in this directory authorizes FPGA programming, physical
flash erase, rootful Docker cleanup, moving private credentials to Git,
or treating generic vendor bitstreams as Pano G2 board-accepted.
