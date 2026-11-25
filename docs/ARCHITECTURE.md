# Architecture and engineering baseline

This is the **current decision baseline**. The system is a laptop-local,
ordinary-user **rootless Docker** laboratory with a restricted MCP control
plane and a separately approval-gated FPGA toolchain. Decisions here
are current requirements; this is not an ADR or experiment history.

For the **agreed future source/project organization**, the authoritative
standard is [PanoLab Source and Project Architecture](../specs/PANOLAB_SOURCE_AND_PROJECT_ARCHITECTURE.md).
That document specifies `projects/`, board and shared-code ownership,
selective upstream snapshots, dependency manifests, build provenance,
and licensing/attribution. The source organization now has a migrated
development candidate with board and third-party snapshot directories.
**This file describes the operational deployment**; source-layout changes
and the live service/mount cutover have separate acceptance evidence.

The current handoff, checked-in recipes and temporary-component lifecycle
are indexed in [the engineering baseline](ENGINEERING_BASELINE.md) and
[temporary-component register](TEMPORARY_COMPONENTS.md).
Dated acceptance documents record historical snapshots, not competing
operational authorities.

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
A subsequent [on-demand setup stress test](ISE14_SETUP_ONDEMAND_STRESS.md)
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
approved source mounts and a private Codex volume with
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
The new LiteX recipe and [guarded developer-image refresh](UNIFIED_DEV_IMAGE_UPGRADE.md)
were **accepted on the actual laptop** following a rootless image rebuild,
23 passing tests, an unchanged six-service system and live generic
LiteX BIOS simulation. See the [acceptance evidence](UNIFIED_DEV_IMAGE_ACCEPTANCE.md). A stopped rollback container is
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
2026-11-24. See [the ISE acceptance evidence](ISE14_REMOTE_BRINGUP_EVIDENCE.md);
the original [LM1 record](../specs/LAB_MILESTONE_1.md) remains historical
and correctly excludes these later achievements.

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
- **ISE worker:** persistent CentOS vendor toolchain and MCP server in
  **one runtime container**, with exactly five canonical worker build tools.
  A separate authenticated manager/broker adapter provides approved project
  staging and safe diagnostics. Both real licensed implementation and
  node-locked virtual Ethernet operation are now accepted on the laptop;
  these results do **not** prove G2 board constraints or physical operation.
  See [worker contract](TOOLCHAIN_MCP_CONTRACT.md) and
  [real vendor test evidence](ISE14_REMOTE_BRINGUP_EVIDENCE.md).
- **Agent:** local source edits and verification via restricted MCP
  capabilities. Physical reads, traces and any writes need a separate
  bounded, approved hardware access mechanism.

The detailed functional requirements live in
[`specs/PANOLAB_DIRECT_v1_0.txt`](../specs/PANOLAB_DIRECT_v1_0.txt).
The [Rescue project](../projects/rescue/README.md) now owns its
source-level SoC/BIOS integration and build entry point; the G2
[board BSP](../boards/pano_g2_rev_b/README.md) owns physical board behavior.
The selected original LiteX G2 [platform](../third_party/litex-boards/2ccda127/src/litex_boards/platforms/pano_logic_g2.py)
and [target](../third_party/litex-boards/2ccda127/src/litex_boards/targets/pano_logic_g2.py)
are tracked under their upstream identity. This is not yet an ISE-built
bitstream or hardware-accepted design. `tests/fixtures/panolab_csr_demo.v` is a standalone
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
**Historical first implementation was source-level:** [G2 Rev B Rescue SoC](../projects/rescue/README.md) elaborates VexRiscv/LiteEth/LiteSPI, compiles standard LiteX BIOS and produces Verilog/UCF; a generic upstream LiteX Verilator simulation reached the BIOS prompt. [Evidence](RESCUE_BUILD_EVIDENCE.md) distinguishes these PASS results from still-missing ICAP, per-board identity, A/B firmware policy, network update API, vendor bitstream and physical hardware proof. The broader v1.1 standard remains **not hardware-qualified**. The [iteration-15 checkpoint](../projects/rescue/experiments/iteration-15/README.md) now records subsequent G2-specific diagnostic ISE timing closure and distinct simulation-only components; stock Ethernet access/backup is documented under [research/pano-stock](../research/pano-stock/README.md). Neither establishes physical Rescue operation.

## Next capabilities and acceptance gates

1. **G2 Rev B design:** pin compatible LiteX/Migen/LiteEth sources,
   verify exact clock, PHY, pinout and constraints, and simulate the
   CPU-less Etherbone/CSR design locally.
2. **Vendor compilation:** **accepted for generic XC6SLX150 toolchain smoke
   designs** on the licensed rootless worker: two real six-stage builds,
   distinct artifacts and SHA-256 hashes. A real G2-specific constrained
   implementation remains to be verified.
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
| LiteSPI (active G2 Rescue SPI driver) | https://github.com/litex-hub/litespi |

Do not vendor unverified upstream master archives into this repo.
The **Rescue project source dependencies are selected** by
[`project.toml`](../projects/rescue/project.toml) and
[`third_party/registry.toml`](../third_party/registry.toml), with
a complete per-snapshot file-hash manifest. `docker/modern/` still
pins the existing *toolchain bootstrap* source and Python versions;
the product resolver verifies and imports its committed source instead
of silently falling back to those bootstrap checkouts. This establishes a reproducible *software build recipe*, not a
qualified FPGA image. Before claiming repeatable FPGA results, also
validate image digests on an actual new Docker build, vendor ISE,
generated constraints, device variant and hardware test artifacts.
Modern Docker tooling pins the Codex release by checksum, but does
not ship ISE binaries or prove FPGA behavior.

[Installation and operation](GETTING_STARTED.md) ·
[Local tests and publication](DEVELOPMENT.md) ·
[Security](SECURITY.md)
