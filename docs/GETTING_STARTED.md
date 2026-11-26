# Install and operate the rootless laptop laboratory

This describes the **current supported deployment recipe** and its
explicit prerequisites. Read the [engineering baseline](ENGINEERING_BASELINE.md)
for current acceptance results and the
[host script index](../host/README.md) before running an old helper.
The installer does not perform host Docker installation and has not
been validated as an unattended fresh-machine install.

## 1. Host prerequisites

Use an ordinary non-root user on Linux x86_64 with Git, Bash,
Python 3, Docker CLI/Compose and **Buildx**, and an already provisioned **rootless
Docker Engine** with systemd cgroups v2 and CPU/memory/PID delegation.
The laptop installation uses the preprovisioned user helper at
`~/.local/libexec/panolab-rootless-29.1.3/dockerd-rootless.sh`.
If a different host lacks this helper or delegated resources,
**stop and review the prerequisite**; do not silently run `sudo`,
host `apt` or a nested/rootful Docker daemon.

Containerized tooling includes Python, Git, Yosys, Icarus, Verilator,
Codex and the [pinned LiteX/VexRiscv Rescue stack](RESCUE_ENVIRONMENT_RECIPE.md):
LiteX BIOS, LiteX-Boards, LiteEth, LiteSPI, Migen, SPI/PHY support,
RISC-V GCC/binutils, Meson/Ninja and simulation C libraries.
Licensed ISE remains separately approved. **Host Docker Buildx** is a
Docker CLI extension (not another Docker image or development service).
For the owner-laptop version-pinned, no-sudo bootstrap and exact
old-development-rollback cleanup, see the
[toolchain cleanup procedure](DEV_TOOLCHAIN_WARNING_CLEANUP.md).
The installer now builds images with BuildKit and fails rather than
falling back to Docker's deprecated legacy builder.

### Clean-host prerequisite admission

Use `bash ./panolab-install.sh --fresh-host-check` before attempting
an installation on a new host. This **read-only** check reports missing
Docker/Compose/Buildx, rootless/user-session/cgroup requirements,
subordinate UID/GID mappings, checkout identity and private-input
presence. It does not start services, provision operating-system packages,
download vendor media, read secret values or accept license terms.
A missing-prerequisite report returns exit code `10`; even a `READY`
report establishes **prerequisite readiness only**, not a working
installation. A genuinely new host may require a reviewed OS
administrator provisioning step and owner-provided private media.
Read [the actual test and remaining gates](FRESH_HOST_ACCEPTANCE.md).

## 2. Owner-private inputs

Provision two separate owner-owned mode 0700 directories outside the
checkout. The defaults are `${XDG_CONFIG_HOME:-$HOME/.config}/panolab`
and `${XDG_DATA_HOME:-$HOME/.local/share}/panolab`. Use
`PANOLAB_CONFIG_DIR` and `PANOLAB_DATA_DIR` to override them with absolute,
non-overlapping paths. The roots and their path components must be free of
symlinks.

| Directory | Owner-provisioned input |
| --- | --- |
| Config | Copy `docker/.env.example` to `.env`, mode 0600, and supply the tunnel ID and MCP token |
| Config | `tunnel-api-key`, `mcp-bearer`, and `Xilinx.lic`, mode 0600. The bearer file contains `Bearer <PANOLAB_MCP_TOKEN>` |
| Config | `codex-auth/` plus optional `github-git-auth/`, mode 0700 |
| Data | `agent-workspace/`, `repo-rpc/`, `Xilinx/`, `ise-work/`, mode 0700 |
| Data | Exactly one owner-provided ISE archive (`.tar`, `.tar.gz`, `.tgz`, or `.tar.bz2`). Existing `sync-backups/` and worker credentials remain under this root |

The installer requires these inputs to exist and preserves the existing
vendor installation. Keep credential contents, license details and archives
private. On the already provisioned laptop, follow the guarded
[external storage cutover](EXTERNAL_STORAGE_CUTOVER.md) before using this
candidate's launcher. The cutover has its own live acceptance gate.

## 3. Commands

From the repository checkout on the laptop:

```bash
bash ./panolab-install.sh --fresh-host-check  # read-only missing-prerequisite inventory, even before Docker
bash ./panolab-install.sh --status   # read-only status
bash ./panolab-install.sh --check    # local configuration preflight
bash ./panolab-install.sh            # build missing/stale-labeled images; start/reuse services
bash ./panolab-install.sh --upgrade-dev   # explicitly upgrade only the dev image/container
bash ./panolab-install.sh --enable-github-push  # opt-in GitHub direct push for repo-git only
```

The launcher verifies the user rootless Engine and private inputs,
merges the three Compose recipes, builds missing images **on the
laptop**, and brings up broker/repo/manager **without activating the
optional `ise-setup` profile**. It creates the bounded development
container if absent, checks available HDL tools, resource quotas
and Codex login, probes authenticated MCP (including anonymous denial),
then starts the outbound tunnel. The optional setup image can be built
but its container is not started during ordinary deployment.
This adjusted startup path has passed source/Compose tests, **not
an independent fresh-host installation**. Nothing in this recipe
touches the system/rootful Docker Engine, installs host packages,
changes unrelated containers or programs an FPGA.

GitHub publishes through the connected integration even without a laptop PAT.
To enable direct `repo_push` through the existing container, use the
[one-time fine-grained GitHub setup](GITHUB_PUBLISHING.md), which puts
only a narrowly scoped token in the external owner configuration directory.
Never put that token in the ordinary development container or Git config.

A first-time Codex account may need an interactive owner-approved
login **inside the local development container** before installation
can complete; existing Codex credentials are kept in the private
volume. A successful local tunnel start still needs independent
confirmation that remote `lab_status` and `repo_status` work.

## 4. Operate and inspect

The original LM1 deployment ran `tunnel`, `manager`,
`docker-broker`, `repo-git`, `setup` and `dev`. The ISE bring-up
temporarily ran eight containers. The subsequent
[on-demand setup acceptance](ISE14_SETUP_ONDEMAND_STRESS.md) removed
the manager/tunnel startup dependencies on setup and placed it behind
the opt-in `ise-setup` profile. Setup is now **stopped**, with
`restart: no`. The active configuration has **seven running
containers**: tunnel, manager, broker, repo-git, modern dev, licensed
ISE worker, and the explicitly temporary trusted-maintenance sidecar.
The proposed six-service steady state removes that last temporary
sidecar; it has **not** been reboot-accepted. The setup container must
already exist for normal `lab_lifecycle start`; creation from absence
and fresh-host installation are still separate work.

Inspect with authenticated PanoLab MCP `lab_status` / `repo_status`
or the read-only `--status` command.
The ordinary installer is **not yet** a clean-room reproducer of this
expanded configuration; see [the ISE milestone review](ISE14_REMOTE_MILESTONE_REVIEW.md). The user Docker socket is
`/run/user/$(id -u)/docker.sock`; never manage PanoLab through
the default system/rootful Docker Engine.

Use `dev_exec` for approved operations **inside** the already
running development container and its `/workspace` scratch.
The normal `dev_exec` operation runs inside the approved modern development
container and is not host Docker access. The explicitly owner-approved,
**temporary** `@maintenance` compatibility route is an exception: it
can perform broad operations on the **owner's rootless Docker Engine**
through the internal maintenance sidecar. Do not infer that rootless
Docker makes this control production-safe. The separate `@ise14` path
stages immutable RTL revisions and calls the installed licensed worker.
Neither grants authorization to JTAG, SPI, flash or hardware programming.
Avoid restarting the authenticated tunnel or worker for ordinary source edits.

The installer reuses existing services with `--no-recreate`; it is
**not** a destructive repair utility. The explicit `--upgrade-dev` mode uses [the safeguarded unified image migration](UNIFIED_DEV_IMAGE_UPGRADE.md): validate the new image before renaming/stopping only the dev container, retain its previous instance stopped for rollback, and reuse the same owner workspace and Codex credentials with the approved read-only source bind. It neither creates a new development service nor restarts management/ISE. If the modern tools image recipe
is newer, the installer rebuilds the image tag and performs its read-only
LiteX environment smoke check, but **preserves the running old dev
container** and reports the pending explicit container migration.
See the [LiteX environment recipe](RESCUE_ENVIRONMENT_RECIPE.md). Before any service replacement,
review effects on the remote tunnel, host resources, private mounts,
licenses and persistent results. Do not globally prune Docker.
Reboot recovery was accepted for the **earlier six-service LM1 configuration**
on the owner's provisioned laptop, using `unless-stopped` for the
standalone developer container. The later eight-service deployment,
Docker-internal node-locked ISE network, and trusted maintenance bridge
**have not yet undergone a clean reboot acceptance test**. The earlier
test does not prove unattended headless startup before login or a
fresh-host installation.

### Disposable unattended ISE 14.7 acceptance

The **normal authenticated PanoLab interface**, not `@maintenance`,
owns the disposable acceptance test. The owner-approved
[ISE 14.7 acceptance policy](../docker/ise14/acceptance-policy.json)
pins the approved System Edition vendor archive by SHA-256 and
records the limited authorization to accept its known batch-installer
terms without an interactive prompt. New media or changed terms
require separate review.

The remote PanoLab connector's `dev_exec` supports these **fixed,
broker-intercepted argument arrays**, not general shell commands:

```text
["@ise-e2e", "preflight"]
["@ise-e2e", "start"]
["@ise-e2e", "status", "<12-hex-run-id>"]
["@ise-e2e", "result", "<12-hex-run-id>"]
```

`start` provisions fresh Docker **named volumes** and a separate
setup service, runs actual unattended installation and a separate
licensed worker build, validates six tool stages and their artifacts,
and deletes only that run's labeled Docker resources. Result metadata
and SHA-256 hashes are preserved in the broker's private management
volume. `@ise-e2e` never invokes the temporary maintenance route
and requires no laptop-side manual terminal steps after the approved
inputs are provisioned. The existing installation, license, normal
setup and persistent worker are never writable test inputs.

The successful end-to-end evidence and limitations are recorded in
[disposable ISE acceptance](ISE14_DISPOSABLE_INSTALL_ACCEPTANCE.md).
This capability proves a **fresh ISE vendor installation on the
already-provisioned laptop**, not an untouched-host installation of
Docker, a new entitlement, the tunnel, or Pano G2 hardware programming.

## 5. Source synchronization boundary

The canonical checkout is `~/Projects/repos/panolab-direct-main`,
but its **active branch** is `development`, tracking
`origin/development`. GitHub has exactly `main` and `development`.
At the LM1 freeze both were identical at `006b6ee`, with `main`
preserved as the accepted baseline. All engineering goes through
`development`, and promotion to `main` requires explicit owner
acceptance. Use guarded fast-forward sync only while the checkout
is clean and source history permits it; never reset or force-push
to hide divergence. Follow [development and publishing](DEVELOPMENT.md)
and [LM1 evidence](../specs/LAB_MILESTONE_1.md).

[Architecture](ARCHITECTURE.md) · [Security](SECURITY.md)
