# PanoLab Direct

A local, rootless-Docker FPGA development laboratory for the **Pano Logic G2 Rev B**
(Xilinx Spartan-6 XC6SLX150-2-FGG484). ChatGPT reaches the laptop through an
outbound authenticated MCP tunnel. Build, development, simulation and management
belong inside isolated Docker containers on the owner's laptop.

## Repository map

| Path | Purpose |
| --- | --- |
| `panolab-install.sh`, `host/rootless-install.sh` | User-level rootless deployment and checks |
| `docker/compose.setup.yaml`, `docker/compose.manage.yaml`, `host/compose.rootless-laptop.yaml` | The deployed six-service stack and rootless overrides |
| `docker/modern/` | Pinned Ubuntu HDL/Codex toolchain image |
| `docker/control/` | Restricted Docker broker, Git gateway, Go MCP manager |
| `docker/ise14/` | CentOS ISE setup and embedded five-tool MCP worker source |
| `agent/`, `boards/`, `gateware/`, `specs/` | G2 design and agent interface scaffold |
| `tests/` | Small local source/MCP tests and external FPGA fixture |
| `docs/` | Installation, operations, architecture and security |

**Start here:** [Install and prerequisites](docs/SETUP.md) ·
[Operations](docs/OPERATIONS.md) ·
[Architecture](docs/ARCHITECTURE.md) ·
[Engineering rules](AGENTS.md).

## Quick commands

The rootless Engine and private files must be provisioned first. Never
run this installer with sudo.

```sh
bash ./panolab-install.sh --status
bash ./panolab-install.sh --check
bash ./panolab-install.sh
```

All image builds and runtime checks run on the **actual laptop**, not
GitHub Actions or KVM. `--status` is read-only; `--check` validates
preconditions; the default command deploys/reuses rootless services.

## What exists, and what does not

The six-container rootless management/development lab, private MCP
authentication, remote ChatGPT access, Codex login reuse, and CPU/RAM/PID
limits were verified on the owner's laptop. The private credentials,
licensed Xilinx ISE installation and vendor media are **not** stored
in this Git repository. The embedded ISE worker sources and setup
recipe are included, but **licensed ISE execution and physical FPGA
operation remain unverified**.

M1 is a **CPU-less** LiteX/LiteEth/Etherbone design with board identity
and CSR read/write; later stages add LiteScope and framebuffer
observation. The USB3300 project is an example future workload, not
part of this repository's gateware.

## Source control

`main` is the accepted source snapshot. Use a temporary review branch
for changes that need validation; publish through the connected GitHub
integration and fast-forward the approved laptop checkout. Private
files, media, tokens, generated outputs and history logs never belong
in the source snapshot.

This repository deliberately contains **source and recipes, not CI
experiment history**. See [local test policy](docs/TESTING.md).
