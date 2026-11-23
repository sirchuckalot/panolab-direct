# PanoLab Direct

**Rootless Docker FPGA development laboratory on the owner's Linux laptop.**

PanoLab Direct provides a containerized HDL/Codex development environment,
restricted source and Docker management, an authenticated MCP connection from
ChatGPT, and a provisioned path for a separately licensed Xilinx ISE 14.7
build worker. The FPGA target is **Pano Logic G2 Rev B
(XC6SLX150-2-FGG484)** with a future CPU-less LiteX/LiteEth/Etherbone design.

## Start here

| Read | What it covers |
| --- | --- |
| [Architecture and baseline decisions](docs/ARCHITECTURE.md) | What exists, system boundaries, G2 design and planned capabilities |
| [Install and operate](docs/GETTING_STARTED.md) | Host prerequisites, private inputs, rootless deployment, status and recovery limits |
| [Develop, test and publish](docs/DEVELOPMENT.md) | Laptop-local testing, appropriate CI use and verified low-noise commits |
| [Security](docs/SECURITY.md) | Credentials, mounts, rootless authority, approval gates and hardware safety |
| [Toolchain MCP contract](docs/TOOLCHAIN_MCP_CONTRACT.md) | Persistent vendor build worker and canonical five MCP tools |
| [Agent instructions](AGENTS.md) | Rules for automated engineering sessions |

The selected [FPGA system specification](specs/PANOLAB_DIRECT_v1_0.txt)
is the companion concise functional requirements file. These documents
describe the **current baseline and forward design**, not an experiment
log or chronology of past engineering attempts.

## Operational baseline

The owner's laptop has demonstrated six running PanoLab rootless
containers: tunnel, manager, restricted Docker broker, Git gateway,
ISE setup service, and modern development container. Authenticated
remote MCP, reused Codex authentication and kernel-enforced 2-CPU,
4-GiB, 256-PID development limits were observed on that laptop.

The clean `main` source snapshot has passed **local source checks**;
it has **not** itself been accepted as a fresh, unattended laptop
installation. The current live checkout is on a separate Git history,
so do not reset it or attempt a cross-history fast-forward as part
of ordinary documentation or development changes.

**Not yet verified:** licensed ISE build, pinned LiteX dependency set,
G2 Rev B constraints and bitstream, real FPGA/Etherbone response,
full logout/reboot persistence, or a fresh machine installation.

## Entrypoint

Run as the ordinary laptop user, with rootless Docker and private inputs
already provisioned (see [setup](docs/GETTING_STARTED.md)):

```sh
bash ./panolab-install.sh --status
bash ./panolab-install.sh --check
bash ./panolab-install.sh
```

No `sudo`, host-wide Docker cleanup, FPGA programming or GitHub CI
is part of the installer. Source and third-party vendor media must not
be confused: credentials, license files, ISE installers and build
outputs stay in private ignored locations.

## Source organization

| Directory | Active role |
| --- | --- |
| `host/` | Rootless user-level installer and Compose overlay |
| `docker/` | Compose recipes, modern toolchain, broker, Git gateway, manager and ISE sources |
| `tests/` | Laptop-local source/protocol tests and external ISE fixture |
| `specs/` | G2 functional design baseline |
| `boards/`, `gateware/`, `agent/` | Intentionally minimal source placeholders for upcoming G2 integration |
| `docs/` | The five current engineering documents linked above |

**Publish only working milestones:** experiment and verify inside the
laptop's local containers, review changes, then make one coherent
commit. GitHub CI is optional for small, justified clean-runner checks,
not a replacement for testing the actual laptop.
