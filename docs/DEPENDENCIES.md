# Upstream dependencies and pinning

PanoLab does not commit vendor ISE binaries, proprietary media or
whole third-party source trees. The owner supplies the licensed ISE
14.7 installer and license outside Git.

The G2 development design uses repositories such as:

| Component | Upstream |
| --- | --- |
| LiteX | https://github.com/enjoy-digital/litex |
| LiteX-Boards (G2 platform/target) | https://github.com/litex-hub/litex-boards |
| Migen | https://github.com/m-labs/migen |
| LiteEth/Etherbone | https://github.com/enjoy-digital/liteeth |
| LiteScope | https://github.com/enjoy-digital/litescope |
| LiteDRAM (later) | https://github.com/enjoy-digital/litedram |
| LiteSPI (later, approval-gated) | https://github.com/litex-hub/litespi |

The exact LiteX/Migen/LiteEth revisions and board constraints are
**not locked or verified** in this source snapshot. Before using them
for reproducible build acceptance, pin compatible commits and record
digests, licenses and generated constraints. Do not silently install
these packages into the host OS or claim a master-branch archive is
a stable released dependency.

The modern Dockerfile pins Codex CLI and Code Mode host release and
SHA-256 digests. The current image includes Yosys, Icarus, Verilator,
GCC and Python. A built modern image is not proof that licensed ISE
or physical FPGA integration works.
