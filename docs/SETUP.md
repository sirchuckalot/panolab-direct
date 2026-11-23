# Rootless laptop setup

PanoLab is a **local Docker project**, not a GitHub Actions runner or a
Docker-in-Docker appliance. The laptop's ordinary user runs the Docker
Engine with systemd cgroup v2; all application tooling is containerized.

## Host prerequisites

- Linux x86_64 with an already provisioned **rootless Docker Engine**,
  working Docker CLI and Compose plugin, and delegated CPU/memory/PID
  controllers in a user systemd session.
- Python 3 and Git for the small audited host launcher and checkout.
- The provisioned rootless helper used by this laptop is
  `~/.local/libexec/panolab-rootless-29.1.3/dockerd-rootless.sh`.
  Docker/RootlessKit installation is a separately reviewed **host
  prerequisite**; the PanoLab installer never performs sudo or host apt.
- Sufficient local disk, RAM and CPU for Ubuntu modern tools and the
  optional licensed ISE toolchain. Never run as root.

## Private inputs (not checked in)

Create `docker/.env` from `docker/.env.example` and supply the
outbound tunnel ID and 32+-character MCP token. Create a private
`docker/private/` directory, owned only by the laptop user, containing:

| Input | Path / requirement |
| --- | --- |
| Tunnel control-plane API key | `docker/private/tunnel-api-key` (0600) |
| MCP bearer | `docker/private/mcp-bearer` (0600), exactly `Bearer <PANOLAB_MCP_TOKEN>` |
| Licensed Xilinx file | `docker/private/Xilinx.lic` |
| Installer media | Exactly one owner-supplied `*.tar`, `*.tar.gz`, `*.tgz`, or `*.tar.bz2` archive |
| Owner data directories | `agent-workspace/`, `repo-rpc/`, `codex-auth/`, `Xilinx/`, `ise-work/` |

Do not put secrets into environment variables shown in chat or Git.
The source repository contains **none** of these private files.
The setup service does not automatically install licensed ISE or
accept Xilinx licensing.

## Commands on the laptop

```bash
cd ~/Projects/repos/panolab-direct
bash ./panolab-install.sh --check
bash ./panolab-install.sh
bash ./panolab-install.sh --status
```

The normal installer requires the rootless Engine and private inputs,
builds images locally only when absent, starts the management services,
creates the bounded development container when needed, verifies its
toolchain and kernel quotas, and performs a private authenticated MCP
probe **before** starting the outbound tunnel. No system Docker/old
rootful migration or rollback is part of this clean recipe.

For a **new** Codex login, the development container may be created
before authentication is available; sign in through the owner's
approved local container interface, then rerun the installer. Existing
Codex auth stays in `docker/private/codex-auth/`. Confirm the remote
MCP connection after a successful tunnel start.

The rootless user service starts at login; availability across full
logout or laptop reboot must be established separately. Do not set
lingering or change system policy automatically.

See [operations](OPERATIONS.md) and [security](SECURITY.md).
