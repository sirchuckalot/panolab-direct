# Install and operate the rootless laptop laboratory

This describes the **current supported deployment recipe** and its
explicit prerequisites. It does not perform host Docker installation
and has not been validated as an unattended fresh-machine install.

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

## 2. Owner-private inputs

Copy `docker/.env.example` to ignored `docker/.env` and supply
the tunnel ID and MCP token. Provision ignored
`docker/private/` with owner-only permissions:

| File or directory | Requirement |
| --- | --- |
| `tunnel-api-key` | Tunnel control-plane secret, mode 0600 |
| `mcp-bearer` | Exactly `Bearer <PANOLAB_MCP_TOKEN>`, mode 0600 |
| `Xilinx.lic` | Owner-supplied license file, never commit |
| One ISE `*.tar`, `*.tar.gz`, `*.tgz` or `*.tar.bz2` | Existing vendor media; installer does **not** perform vendor installation |
| `agent-workspace/`, `repo-rpc/`, `codex-auth/`, `Xilinx/`, `ise-work/` | Existing, persistent owner-controlled directories |

The authenticated setup and management services require the
pre-existing private inputs. Never publish or paste the actual
credential, archive, host ID or private directory contents.

## 3. Commands

From the repository checkout on the laptop:

```bash
bash ./panolab-install.sh --status   # read-only status
bash ./panolab-install.sh --check    # local configuration preflight
bash ./panolab-install.sh            # build missing/stale-labeled images; start/reuse services
bash ./panolab-install.sh --upgrade-dev   # explicitly upgrade only the dev image/container
```

The launcher verifies the user rootless Engine and private inputs,
merges the three Compose recipes, builds missing images **on the
laptop**, brings up setup/broker/repo/manager, creates the bounded
development container if absent, checks available HDL tools,
resource quotas and Codex login, probes authenticated MCP (including
anonymous denial), then starts the outbound tunnel. Nothing in this
recipe touches the system/rootful Docker Engine, installs host
packages, changes unrelated containers or programs an FPGA.

A first-time Codex account may need an interactive owner-approved
login **inside the local development container** before installation
can complete; existing Codex credentials are kept in the private
volume. A successful local tunnel start still needs independent
confirmation that remote `lab_status` and `repo_status` work.

## 4. Operate and inspect

The live logical services are `tunnel`, `manager`,
`docker-broker`, `repo-git`, `setup` and `dev`.
Inspect with PanoLab MCP `lab_status` / `repo_status`, or the
read-only `--status` command. The user Docker socket is
`/run/user/$(id -u)/docker.sock`; never manage PanoLab through
the default system/rootful Docker Engine.

Use `dev_exec` for approved operations **inside** the already
running development container and its `/workspace` scratch.
Request a reviewed, bounded broker capability for any additional
isolated local test container; `dev_exec` does not grant host
Docker access. Do not restart the authenticated tunnel or persistent
workers to run an experiment.

The installer reuses existing services with `--no-recreate`; it is
**not** a destructive repair utility. The explicit `--upgrade-dev` mode uses [the safeguarded unified image migration](UNIFIED_DEV_IMAGE_UPGRADE.md): validate the new image before renaming/stopping only the dev container, retain its previous instance stopped for rollback, and reuse the same owner workspace, source mounts and Codex credentials. It neither creates a new development service nor restarts management/ISE. If the modern tools image recipe
is newer, the installer rebuilds the image tag and performs its read-only
LiteX environment smoke check, but **preserves the running old dev
container** and reports the pending explicit container migration.
See the [LiteX environment recipe](RESCUE_ENVIRONMENT_RECIPE.md). Before any service replacement,
review effects on the remote tunnel, host resources, private mounts,
licenses and persistent results. Do not globally prune Docker.
Reboot recovery was accepted on the owner's provisioned laptop:
all six PanoLab services (including standalone developer container)
started automatically after an ordinary reboot and sign-in, using
the developer's `unless-stopped` policy. This does not prove
unattended headless startup before login or a fresh-host installation.

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
