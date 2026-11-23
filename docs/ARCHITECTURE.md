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

The current clean `main` source is a reviewed **recipe**, not proof of
a fresh installation from that revision. The live laptop checkout
follows a different Git ancestry and is intentionally left intact
until an explicitly reviewed migration. Licensed ISE execution,
physical FPGA acceptance and reboot persistence are **not yet proven**.

## Accepted functional design (planned)

- **Board:** Pano Logic G2 **Rev B**, Xilinx Spartan-6
  `XC6SLX150-2-FGG484`; do not use Rev C constraints by assumption.
- **Minimal FPGA:** CPU-less LiteX, clock/reset, LiteEth PHY/MAC,
  Etherbone as Wishbone master, CSR identity/status and a bounded
  read/write test register. No soft CPU, BIOS, Linux-on-FPGA, HDMI
  capture device, Raspberry Pi or USB3300 protocol in the first design.
- **Hardware interfaces:** Etherbone is an unauthenticated,
  *trusted-LAN-only* register access protocol; it cannot itself
  configure an unprogrammed FPGA. JTAG/volatile configuration and
  flash writes require exact owner authorization and recovery.
  Factory SPI must be preserved.
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
The minimal board/agent/gateware directories deliberately remain
source placeholders until corresponding implementations are verified.

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
