# Architecture and operating baseline

The current decision baseline is an ordinary-user rootless Docker FPGA laboratory with an
authenticated MCP control plane and a separately licensed vendor worker.
The [source and project standard](../specs/PANOLAB_SOURCE_AND_PROJECT_ARCHITECTURE.md)
governs repository ownership. Anchor is the active product. The
[Rescue project](../projects/rescue/README.md) is frozen engineering history.
The [evidence index](EVIDENCE.md) identifies the scope of earlier results.

## Implemented and observed on the laptop

```text
ChatGPT
   │ outbound authenticated Secure MCP tunnel
   ▼
tunnel ─── manager (Go MCP endpoint, private RPC)
               ├── repo-git (Python, constrained source checkout)
               └── docker-broker (rootless Docker/ISE broker)
                       └── licensed ISE 14.7 worker (persistent)
development (Ubuntu 24.04): ONE modern tools image; Codex, Python,
   Yosys, Icarus, Verilator, LiteX/BIOS, LiteEth/SPI, Migen, RISC-V
optional on demand: setup (stopped; vendor media and install inspection)
temporary, retained: trusted-maintenance sidecar (rootless Docker access)
```

The prior LM1 baseline was **six running containers**. The 2026-11-24
ISE bring-up initially expanded this to **eight active engineering
containers** (including setup and temporary trusted maintenance).
A subsequent [on-demand setup stress test](EVIDENCE.md#on-demand-ise-setup)
proved that setup can stay offline while normal development and licensed
ISE compilation continue. Setup is now stopped with `restart: no`;
Compose gives it an opt-in `ise-setup` profile, and manager/tunnel
no longer have setup startup dependencies. **Seven containers are now
active:** the proposed six steady-state services plus temporary maintenance.
The final **six-service** topology (tunnel, manager, docker-broker, repo-git,
modern dev and ISE worker) is a target, not a reboot-accepted deployment.
Provisioning the persistent setup service from complete absence, and
fresh-machine installation, are not yet proven. The independent **disposable**
ISE installation/build/cleanup path has passed twice through normal MCP
([evidence](ISE14_DISPOSABLE_INSTALL_ACCEPTANCE.md)); it does not establish
full host provisioning. The development container continues to use
approved source mounts and a private Codex bind with
**2 CPUs, 4 GiB memory, 256 PIDs**. The normal manager and developer
container have no Docker socket; the broker and, **temporarily**, the
owner-approved trusted-maintenance sidecar do. That temporary sidecar
has broad user-rootless Docker authority and must be retired before
production hardening claims. Rootless container UID 0 is mapped to the laptop owner's
ordinary UID, **not host root**; it can still affect files owned by
that user. See [security](SECURITY.md).

**Image boundary (accepted):** compatible general FPGA tools share
[one modern development image](../docker/modern/Dockerfile), organized
into seven functional sections. Board-specific hardware adaptation
belongs in BSPs, not new per-tool Docker images. The legacy/licensed
ISE 14.7 stack remains isolated in its separate vendor environment.
The new LiteX recipe and [guarded developer-image refresh](GETTING_STARTED.md#controlled-development-image-upgrade)
were **accepted on the actual laptop** following a rootless image rebuild,
23 passing tests, an unchanged six-service system and live generic
LiteX BIOS simulation. See the [acceptance evidence](EVIDENCE.md#unified-development-image). A stopped rollback container is
retained temporarily during acceptance, not promoted to another service.

The deployment merges `docker/compose.setup.yaml`,
`docker/compose.manage.yaml` and `host/compose.rootless-laptop.yaml`.
`panolab-install.sh` delegates to `host/rootless-install.sh`; the
modern development container is created through the restricted
Docker broker/launcher rather than as a Compose service.

The software-lab baseline was accepted on the owner's **already
provisioned** laptop on 2026-11-23: project-only teardown and
unmodified-installer rebuild, local/remote authenticated MCP acceptance,
and all six services auto-recovering after reboot. The standalone
development container required the `unless-stopped` restart policy.
At the LM1 freeze, the laptop `development` checkout matched
GitHub `main` at `006b6ee`; later engineering commits continued only on
`development`. New work must not modify `main`. A brand-new host install
and physical FPGA acceptance are not yet proven. However, later
**licensed ISE execution passed** with two
real six-stage Spartan-6 builds and distinct bitstream hashes on
2026-11-24. See [the ISE acceptance evidence](EVIDENCE.md#licensed-ise-bring-up);
the original [LM1 record](../specs/LAB_MILESTONE_1.md) remains historical
and correctly excludes these later achievements.

## Accepted external storage and source mounts

The laptop uses separate protected configuration and data roots. The canonical
checkout is mounted read-only at `/repo`, with a read-only tmpfs masking
`/repo/.git`. Workspace and Codex authentication have separate writable binds.
See [operations](GETTING_STARTED.md) for paths and [security](SECURITY.md)
for access boundaries.

At development commit `31534ed99072af490360a7882103031de8609594`,
independent verification recorded matching clean laptop and GitHub revisions,
seven running services, actual private mount boundaries, 172 migration tests
and successful managed Codex canary `93b0b562e05b42ec925d6ce594b8ee25`.
Generic ISE job `1795685528446716627` succeeded and returned metadata for
eight artifacts, including a 4,220,305-byte bitstream. The
`toolchain_info` license validation field remained false, and complete
large timing-report retrieval remains outstanding.

## FPGA design and evidence boundaries

The [system specification](../specs/PANOLAB_DIRECT_v1_0.txt) defines the
CPU-less LiteX/LiteEth/Etherbone application roadmap for the Pano Logic G2 Rev B
(XC6SLX150-2-FGG484). The [boot and recovery standard](../specs/PANOLAB_RESCUE_V1.md)
defines the separate recovery configuration, protected identity, independent
recovery, boot policy and A/B qualification. The [G2 BSP](../boards/pano_g2_rev_b/README.md)
owns board adaptation. The historical [iteration-15 checkpoint](../projects/rescue/experiments/iteration-15/README.md)
records a named G2 read-only diagnostic ISE timing pass and distinct simulated
components. [Stock research](../research/pano-stock/README.md) records physical
discovery and a 16 MiB acquisition from a stock board. Physical product boot,
Etherbone, flash, and recovery qualification remain open. Source and generated
artifact redistribution require separate review.

## Source and configuration inventory

| Purpose | Canonical source |
| --- | --- |
| Ordinary-user entrypoint | `panolab-install.sh` → `host/rootless-install.sh`; read-only prerequisite inspection `host/fresh-host-audit.py` |
| Rootless Compose configuration | `docker/compose.setup.yaml`, `docker/compose.manage.yaml`, `host/compose.rootless-laptop.yaml`, and optional scoped Git-push overlay `docker/compose.git-push.yaml` |
| Modern HDL/LiteX tools | `docker/modern/Dockerfile`, `litex-bootstrap.py`, `litex-requirements.txt`, `litex-upstream.lock.json` |
| Normal MCP control plane | `docker/control/mcp/`, `docker/control/broker.py`, `ise_proxy.py`, `ise_setup.py`, `ise_staging.py`, `ise_acceptance.py`, `repo_gateway.py` and their Dockerfiles |
| Legacy vendor setup/worker | `docker/ise14/Dockerfile`, `entrypoint.sh`, `ise-system-edition.batch`, `mcp/main.go`, `mcp/setup/main.go` and tests |
| Authorized disposable acceptance | `docker/ise14/acceptance-policy.json`, `acceptance_build.json`, `acceptance_design.v`; the policy applies **only** to the exactly identified ISE 14.7 archive and known terms |
| Physical board BSP | `boards/pano_g2_rev_b/` |
| Frozen Rescue source | `projects/rescue/` (project manifest, SoC, firmware/BIOS overlay, tests and build entrypoints) |
| Active product ownership | `projects/anchor/` under the source and project standard |
| Shared and third-party source | `shared/`, `third_party/registry.toml`, individual `upstream.toml`, retained license texts and per-file SHA-256 manifests |
| Security/licensing | [Security boundaries](SECURITY.md), [source architecture](../specs/PANOLAB_SOURCE_AND_PROJECT_ARCHITECTURE.md), [license summary](../LICENSES/README.md) and original upstream notices |
| Git publishing | [Scoped development-branch push](GETTING_STARTED.md#scoped-github-push); `main` remains frozen |

**Owner-private artifacts:** operational state in the [external config and data roots](EXTERNAL_STORAGE_CUTOVER.md), personal
tokens, Codex login state, node-locked license, proprietary Xilinx archive
and installed binaries, generated HDL/build directories, bitstreams and
private diagnostic traces. Local Docker image tags and backup containers
remain in the owner-user rootless Engine; committing sources does not
publish or serialize those images. The complete media/credential bootstrap
of a new host is **not** covered by a Git push.

## Remote staging and control-plane updates

The broker stages approved regular Verilog, UCF and manifest files as bounded,
atomic content-addressed revisions. The worker reads inputs from its read-only
project mount, records source hashes per job and retains private per-job
outputs. Project iteration needs no vendor worker rebuild or restart.
Nonprivileged diagnostics run within the bounded development workspace.

The temporary live broker directory bind lets atomic source writes become
visible without stale per-file bind inodes. ISE adapter modules reload per
request. Changes to broker main require a broker restart, and the compiled Go
manager and worker require a rebuild. The approved maintenance helper provides
`status`, `check`, `reload-broker` and `deploy-management`. Its detached
management deployment records status and logs in the maintenance workspace so
verification can resume after a transport reconnect.

The target control plane uses versioned releases, preflight, authenticated
canaries and independently recoverable rollback. Security-critical code and
policies must be protected from agent-writable hot reload. Normal remote
operation uses typed, bounded interfaces. Owner-local recovery remains
available when the management connection is lost.

## Temporary maintenance and retirement

See the [host script index](../host/README.md) for maintained helpers and
revision-locked scripts.

| Asset | Purpose today | Removal prerequisite |
| --- | --- | --- |
| `panolab-direct-trusted-maintenance` Docker container | Owner-approved rootless Docker owner-user maintenance, accelerated remote inspection, corrective image/container deployment and fault recovery | Prove a narrower, authenticated independent updater with rollback and loss-of-MCP recovery before stopping this sidecar |
| `docker/control/Maintenance.Dockerfile` and `host/trusted-maintenance.sh` | Build/operate the temporary sidecar and its safe maintenance diagnostics | Retire only after replacing operational responsibilities and testing the new update path |
| `docker/compose.manage.yaml` profile `trusted-maintenance` | Deliberate optional service with access to the rootless Docker socket | Remove profile and mount when new updater is accepted; only after explicit approval |
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

## Preserve (do not prune) existing local rollback assets

At the accepted ISE bring-up checkpoint, the following stopped
containers were retained on the owner's rootless Engine:

- `panolab-direct-ise14-worker-backup-network-none-20261124`
- `panolab-direct-ise14-worker-backup-absbin-20261124`
- `panolab-direct-dev-1-rollback-20261124T064055Z` (prior modern dev rollback)

Seven live/rollback image tags were recorded in
[the milestone review](EVIDENCE.md#remote-ise-milestone), including
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
