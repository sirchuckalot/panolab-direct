# Temporary infrastructure, historical scripts and rollback register

**Snapshot:** 2026-11-24 · **Status:** Retain for accelerated remote
engineering. **No cleanup/removal authorized by this document.**
See [the engineering baseline](ENGINEERING_BASELINE.md) and the
[host script index](../host/README.md) (`host/README.md`).

## Active but intentionally temporary

| Asset | Purpose today | Removal prerequisite |
| --- | --- | --- |
| `panolab-direct-trusted-maintenance` Docker container | Owner-approved rootless Docker owner-user maintenance, accelerated remote inspection, corrective image/container deployment and fault recovery | Prove a narrower, authenticated independent updater with rollback and loss-of-MCP recovery before stopping this sidecar |
| `docker/control/Maintenance.Dockerfile` and `host/trusted-maintenance.sh` | Build/operate the temporary sidecar and its safe maintenance diagnostics | Retire only after replacing operational responsibilities and testing the new update path |
| `docker/compose.manage.yaml` profile `trusted-maintenance` | Deliberate optional service with access to the rootless Docker socket | Remove profile and mount when new updater is accepted; never during this baseline handoff |
| `docker/control/broker.py` `@maintenance` compatibility route | Accelerated owner-approved review, recovery and source promotion | Replace with typed/allowlisted management actions; verify normal `@setup`, `@ise14`, `@ise-e2e` continue independently |
| Read-only live broker Python source directory bind in `docker/compose.manage.yaml` | Fast code iteration without rebuilding the broker after each Python edit | Replace with pinned, signed/tested release artifacts and automatic rollback after validating the release updater |
| `docker/control/test_trusted_maintenance.py` | Regression tests for the explicitly temporary broad route | Keep passing while that route exists; archive with its retirement change |

**Security:** rootless Docker socket access is powerful over owner-owned
containers, mounts and accessible files; it is not least privilege.
The temporary service is owner-authorized for the development phase,
but **must never be the execution path for acceptance of normal vendor
installation or licensed compilation**. Running `@ise-e2e` must work
through ordinary authenticated manager/broker, without maintenance
executing any install/build/cleanup step.

## Historical, revision-locked scripts: preserve source, DO NOT RERUN

These files document the specific state transitions that brought the
laptop to its present accepted baseline. They are **not the current
installer/upgrade entry point**, and their original commit guards,
migration assumptions and rollback names refer to previous states.

| Source | Historical purpose |
| --- | --- |
| `host/reconcile-and-upgrade.sh` | One-off reconciliation of two prior `development` histories, with a guarded historical `git reset --hard` path |
| `host/apply-source-migration.sh` | Source-tree migration from a pinned, earlier candidate revision |
| `host/activate-ise-bridge.sh` | One-time ISE broker/manager activation at an old base SHA |
| `host/ise14-repair.py` | One-time recovery from GNU tar ownership failure during the initial rootless ISE installation |

Do **not** delete or execute them as a general recovery strategy. The
safe everyday entrypoint is `panolab-install.sh`; the normal disposable
vendor acceptance route is `@ise-e2e`. Before any future removal, review
references/tests and historical evidence; delete only in a deliberate
separate commit with a verified replacement.

## Guarded maintenance helpers: keep but do not run routinely

| Source | Role |
| --- | --- |
| `host/ise14-bringup.py` and `host/ise14-diagnose.py` | Owner-only guarded vendor commissioning/diagnostics; normal MCP setup and worker routes are preferred for day-to-day operation |
| `host/finalize-dev-maintenance.sh` | Exact-match cleanup of a previously approved stopped dev rollback, **not** global image/container pruning |
| `host/install-rootless-buildx.sh` | Explicit owner-scoped Buildx CLI bootstrap/repair |
| `host/enable-github-push.sh` | Owner-only scoped GitHub credential configuration or rotation |
| `host/upgrade-dev-image.sh` | Explicit, guarded modern image update with rollback |
| `host/apply-source-migration.sh` | Listed above: historical only; not a normal upgrade |

The control/worker source, version pins, fixture tests and license
notices are **permanent source assets** even if a testing or helper
environment is temporary.

## Preserve (do not prune) existing local rollback assets

At the accepted ISE bring-up checkpoint, the following stopped
containers were retained on the owner's rootless Engine:

- `panolab-direct-ise14-worker-backup-network-none-20261124`
- `panolab-direct-ise14-worker-backup-absbin-20261124`
- `panolab-direct-dev-1-rollback-20261124T064055Z` (prior modern dev rollback)

Seven live/rollback image tags were recorded in
[the milestone review](ISE14_REMOTE_MILESTONE_REVIEW.md), including
`panolab-direct-ise14-worker:checkpoint-20261124` and
`panolab-direct-ise14-worker:pre-absolute-path-fix-20261124`.
These are **local Docker objects, not tracked Git files**, and may be
host-specific. A private, machine-readable image/container inventory
was saved in the owner workspace at
`maintenance/checkpoint-20261124-images-and-rollbacks.json`.
Do not `docker system prune`, use broad selectors, or remove backups
as part of the source publication. Recheck image labels/IDs and
mounts before any later rollback or deletion.

## Approved future retirement gate

1. Implement a pinned, typed, independently recoverable management updater
   that can install, verify, roll back and reboot-test the normal manager,
   broker and worker without broad `@maintenance` shell/engine commands.
2. Prove the update flow survives source mistakes, bad image, broker crash,
   lost tunnel session and a rootless Docker restart; preserve a separate
   owner-controlled recovery channel.
3. Rerun `@ise14` compilation, `@setup` on-demand cycle, and
   `@ise-e2e` disposable fresh vendor install/build/cleanup **without**
   temporary maintenance as an executor.
4. Confirm scoped GitHub `development` push, license protection,
   immutable source project staging and all expected rollback resources.
5. Only with explicit later approval, stop trusted maintenance, remove
   its broad socket mount/profile/broker path, update tests and docs,
   and separately prune **named** old objects after inventory review.

Until then, retaining this temporary environment is **intentional**.
It accelerates development and failure diagnosis; its presence does
not make the actual FPGA hardware or the eventual production appliance
qualified.
