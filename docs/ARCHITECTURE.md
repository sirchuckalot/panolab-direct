# Architecture and engineering baseline

This is the **current decision baseline**. The system is a laptop-local,
ordinary-user **rootless Docker** laboratory with a restricted MCP control
plane and a separately approval-gated FPGA toolchain. Decisions here
are current requirements; this is not an ADR or experiment history.

## Implemented and observed on the laptop

```text
ChatGPT
   │ outbound authenticated Secure MCP tunnel
   ▼
tunnel ─── manager (Go MCP endpoint, private RPC)
               ├── repo-git (Python, constrained source checkout)
               ├── docker-broker (Python, allowlisted rootless Docker operations)
               └── setup (CentOS 6.10 ISE media/license inspection)
development (Ubuntu 24.04): Codex, Python, Yosys, Icarus, Verilator
```

Six running containers were observed on the owner's laptop. The
development container uses approved source mounts and a private Codex
volume with **2 CPUs, 4 GiB memory, 256 PIDs**. Only the restricted
broker sees the *user-scoped* Docker socket; the manager and developer
container do not. The broker cannot be treated as a general privileged
host shell. Rootless container UID 0 is mapped to the laptop owner's
ordinary UID, **not host root**; it can still affect files owned by
that user. See [security](SECURITY.md).

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
The canonical source checkout is on `development`, matching GitHub
`main` at the LM1 freeze `006b6ee`. New work must not modify `main`.
A brand-new host install, licensed ISE execution and physical FPGA
acceptance are **not yet proven**. See the
[LM1 evidence record](../specs/LAB_MILESTONE_1.md).

## Accepted functional design (planned)

- **Board:** Pano Logic G2 **Rev B**, Xilinx Spartan-6
  `XC6SLX150-2-FGG484`; do not use Rev C constraints by assumption.
- **Normal application FPGA:** CPU-less LiteX, clock/reset, LiteEth PHY/MAC,
  Etherbone as Wishbone master, CSR identity/status and a bounded
  read/write test register. No soft CPU, BIOS, Linux-on-FPGA, HDMI
  capture device, Raspberry Pi or USB3300 protocol in the first design.
- **Hardware interfaces:** Etherbone is an unauthenticated,
  *trusted-LAN-only* register access protocol; it cannot itself
  configure an unprogrammed FPGA. JTAG/volatile configuration and
  flash writes require exact owner authorization and recovery.
  Board-specific identity data and an independently bootable recovery
  path must survive any approved factory conversion; preserving the
  obsolete factory firmware is not a permanent product requirement.
- **ISE worker:** persistent vendor toolchain and MCP server in
  **one runtime container**, with exactly five canonical build tools.
  The current CentOS setup and worker source do not prove licensing,
  completed vendor implementation or hardware operation.
  See [worker contract](TOOLCHAIN_MCP_CONTRACT.md).
- **Agent:** local source edits and verification via restricted MCP
  capabilities. Physical reads, traces and any writes need a separate
  bounded, approved hardware access mechanism.

The detailed functional requirements live in
[`specs/PANOLAB_DIRECT_v1_0.txt`](../specs/PANOLAB_DIRECT_v1_0.txt).
The board and agent directories remain placeholders for target
integration. `gateware/panolab_csr_demo.v` is a standalone
simulation-only verification fixture, **not** the G2 Rev B Etherbone
or LiteX implementation. FPGA board integration remains unverified.

## Cross-platform boot and update architecture (accepted direction; unimplemented)

[PanoLab Rescue v1](../specs/PANOLAB_RESCUE_V1.md) defines a separate
LiteX CPU-equipped recovery personality with A/B FPGA application slots,
protected per-device identity, durable trial-boot and rollback metadata,
profile-aware Ethernet management, and per-board BSP qualification.
The [BIOS-first Rescue implementation plan](RESCUE_IMPLEMENTATION.md)
reuses LiteX BIOS and its drivers, provides configurable autoboot,
and holds Rescue over Ethernet when the Pano button is held at power-on.
On an isolated owner-controlled LAN, the first-use `trusted-lan` profile
permits unpaired, partition-scoped update commands; shared or production
use paired/authenticated modes. Physical recovery and all network modes
still require BSP/hardware qualification.
The normal Etherbone application may remain CPU-less. Rescue and an
application cannot execute concurrently in one reconfigured FPGA.
Independent power-cycle/button recovery from a hung application must
be physically demonstrated; Spartan-6 ICAP alone does not guarantee it.
The standard is an architectural commitment, **not an implemented or
hardware-accepted feature**.

## Next capabilities and acceptance gates

1. **G2 Rev B design:** pin compatible LiteX/Migen/LiteEth sources,
   verify exact clock, PHY, pinout and constraints, and simulate the
   CPU-less Etherbone/CSR design locally.
2. **Vendor compilation:** obtain separate approval for private ISE
   installation/licensing, then verify a persistent worker, real
   XST/NGDBuild/MAP/PAR/TRACE/BitGen results and artifact hashes.
3. **Physical G2:** with exact approval and a recovery path, validate
   a volatile load and trusted-LAN CSR identity/read/write.
4. **Observability:** bounded LiteScope captures, then coherent
   internal BRAM framebuffer snapshots and Linux display.
5. **Optional scale-up:** DDR2, DMA/video streaming and controlled
   programming only after measurements and additional approval.

These are forward requirements **not claims of implementation**.
Each gate is tested in the appropriate laptop-local environment;
simulation or successful source checks cannot substitute for licensed
ISE or measurements on the real board.

## Dependency and reproducibility rules

| Dependency | Upstream project |
| --- | --- |
| LiteX | https://github.com/enjoy-digital/litex |
| LiteX-Boards (G2 target/platform) | https://github.com/litex-hub/litex-boards |
| Migen | https://github.com/m-labs/migen |
| LiteEth/Etherbone | https://github.com/enjoy-digital/liteeth |
| LiteScope | https://github.com/enjoy-digital/litescope |
| LiteDRAM (optional later) | https://github.com/enjoy-digital/litedram |
| LiteSPI (optional later) | https://github.com/litex-hub/litespi |

Do not vendor unverified upstream master archives into this repo.
The full compatible LiteX dependency set **is not yet pinned**.
For reproducibility, pin source commits and hashes, vendor/package
versions, image digests, generated constraints, device variant and
licensed build artifacts before claiming repeatable FPGA results.
Modern Docker tooling pins the Codex release by checksum, but does
not ship ISE binaries or prove FPGA behavior.

[Installation and operation](GETTING_STARTED.md) ·
[Local tests and publication](DEVELOPMENT.md) ·
[Security](SECURITY.md)
