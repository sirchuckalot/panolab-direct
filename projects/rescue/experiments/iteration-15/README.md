# Rescue engineering checkpoint — iteration 15

**PLR-CHECKPOINT-015 | 2026-11-25 UTC / November 24 Pacific**
**Status: preserved experimental development milestone; NOT a Rescue v1 release, NOT a physical deployment candidate.**

Original starting source revision: `ef250a4fe2641c27939027dcec0aba13e52cf37a`.
Publication parent: `50e8529d50d25a040ebbd982668c9a96d1f137f4`.

## What this checkpoint preserves

This is the finite stopping point following fifteen local engineering iterations, not a newly consolidated implementation. The canonical [project manifest and build entry](../../README.md) remain unchanged in behavior. These historical source variants are deliberately kept in their original relative directory structure so that their independent tests and cross-component references remain intelligible. They are not additional production source roots or a second upstream dependency registry. No experimental variant is selected automatically by the normal project build. Future consolidation must move board-specific changes to the BSP, reusable logic only when demonstrably shared, and application-specific sources into the normal Rescue-owned tree. Do not treat all variants as simultaneously linked.

All authored Python, C, headers, shell scripts, Makefiles, handwritten HDL, historical patches and component documents selected from the iteration workspace are preserved. Original and whitespace-normalized hashes are in [SOURCE_INVENTORY.json](SOURCE_INVENTORY.json). Upstream license notices and pinned source remain in the repository's single third-party registry; original source headers are retained. No new third-party import or license reassignment. Generated HDL, ROM initialization, tool-generated BIOS source copies, object files, bitstreams, vendor binaries, caches and tool intermediates remain private build outputs under the established source architecture. Their original complete workspace hash inventory is held locally; selected artifact identifiers are recorded in [BUILD_RECORD.md](BUILD_RECORD.md). No raw stock firmware or factory identifiers are included.

## Navigation

- [Iteration history](ITERATIONS.md): 1–15 chronology and original detailed reports.
- [Build record](BUILD_RECORD.md): diagnostic ISE timing proof vs simulation-only images.
- [Source and test instructions](REPRODUCE.md): offline test closure and known reproduction limitations.
- [Closure and outstanding gates](RELEASE_CLOSURE.md): historical plan at end of iteration 15, before stock acquisition. Its geometry and stock-entry status are superseded by the separate [stock research](../../../../research/pano-stock/README.md), not by physical Rescue acceptance.
- [Evidence](evidence/iteration-15-regressions.txt): original iteration 15 regression output; previous reports remain in evidence/.
- [Fresh regression evidence](evidence/checkpoint-regressions.txt): independent tests on a clean copy of the checkpoint.

## Boundary

The latest real ISE implementation is a read-only diagnostic candidate, job 1795571940203944746. Its BIOS contains no linked flash erase/program or trial-launch operations. The later synthetic RAM BIOS, byte-bus NOR models, mocked trial confirmation, standalone ICAP RTL, operation ledger and host reconciliation demonstrate separate components and simulated integrations only. They do not constitute a deployable combined Rescue. No physical CSR write adapter was created in iteration 12. No physical FPGA load, flash mutation, JTAG restoration, real Rescue network service, unique MAC initialization or live application return has been qualified.

The stock G2 Rev B acquisition and post-power-cycle rediscovery are a separate milestone. Complete stock-image address coverage and factory records are preserved privately; chip JEDEC identification and independent restoration still remain open. The owner elected to close stock research and proceed to Rescue bench development. This publication is not authorization to program the board. Freeze further feature expansion; next review the existing candidates and establish the first physically qualified Rescue boot.
