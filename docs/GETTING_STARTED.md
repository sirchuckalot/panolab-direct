# Install and operate the rootless laptop laboratory

This describes the **current supported deployment recipe** and its
explicit prerequisites. It does not perform host Docker installation
and has not been validated as an unattended fresh-machine install.

## 1. Host prerequisites

Use an ordinary non-root user on Linux x86_64 with Git, Bash,
Python 3, Docker CLI/Compose, and an already provisioned **rootless
Docker Engine** with systemd cgroups v2 and CPU/memory/PID delegation.
The laptop installation uses the preprovisioned user helper at
`~/.local/libexec/panolab-rootless-29.1.3/dockerd-rootless.sh`.
If a different host lacks this helper or delegated resources,
**stop and review the prerequisite**; do not silently run `sudo`,
host `apt` or a nested/rootful Docker daemon.

Containerized tooling includes Python, Git, Yosys, Icarus,
Verilator and Codex; licensed ISE remains separately approved.

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
bash ./panolab-install.sh            # build missing images and start/reuse services
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
**not** a destructive repair utility. Before any service replacement,
review effects on the remote tunnel, host resources, private mounts,
licenses and persistent results. Do not globally prune Docker.
Full reboot/logout recovery remains a separate acceptance gate;
ordinary uptime does not prove it.

## 5. Source synchronization boundary

GitHub `main` contains the clean source recipe, while the currently
running laptop gateway was launched from a separate checkout
history. **Do not** reset that checkout, force-update GitHub, or
attempt `repo_sync` across unrelated histories. A future laptop
checkout/gateway migration needs a separate, explicit, nondestructive
plan and verification; until then the running environment takes
priority. Follow [development and publishing](DEVELOPMENT.md).

[Architecture](ARCHITECTURE.md) · [Security](SECURITY.md)
