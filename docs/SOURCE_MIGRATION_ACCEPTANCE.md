# Source and Project Migration — Candidate Acceptance

**Status:** Isolated laptop development-container candidate verified.
**Not yet established:** canonical laptop checkout cutover, GitHub branch publication,
reconfigured live broker/Git service containers, licensed ISE bitstream or physical G2 test.

## Candidate scope

- G2 physical reset/button BSP separated under `boards/pano_g2_rev_b/`.
- Rescue SoC, BIOS overlay, project manifest, project tests and reproducible entrypoints under `projects/rescue/`.
- Selected source-visible upstream snapshots and original licenses under `third_party/`, including official LiteX-Boards Rev B platform and target, LiteX BIOS C files, LiteEth, LiteSPI, Migen, Picolibc and CPU/compiler runtime source.
- Central source registry and per-file SHA-256 checks, with recorded upstream revisions and one explicit LiteX revision-reporting adaptation.
- Shared source resolver blocks unapproved imports, missing files and digest changes; outputs remain outside tracked source.

## Laptop-local verification (candidate workspace)

- Before migration, G2 Rescue source and BIOS build passed on the pinned original upstream Docker image environment.
- Candidate source resolver loaded LiteX, LiteX-Boards, LiteEth, LiteSPI, Migen, Pythondata Picolibc wrapper, CPU Verilog and Compiler-RT Python sources from the committed-snapshot paths rather than the toolchain's old upstream checkouts.
- Candidate BIOS generation: `BIOS_BUILD_DIAGNOSTICS=ZERO`, `BIOS_ELF_NO_RWX=PASS`, 39,156-byte `bios.bin`.
- Candidate BIOS SHA-256: `52323e59edb6fe30c9b6d5d12b20be1ad7569eac2093217dacc4545db1d822a9`, **identical** to the pre-migration BIOS after fixing the selected-source revision metadata.
- G2 UCF unchanged byte-for-byte; Verilog differs in generated timestamps and nonfunctional blackbox-display ordering. The `LiteX sha1` header now correctly identifies pinned LiteX revision `afed6623`.
- Nine Rescue SoC Python tests passed; 66 cross-repository source regression tests passed in the isolated candidate.
- Existing pre-migration source tests had five failures unrelated to new source layout (four outdated mock expectations and one outdated documentation-tree assumption); they were corrected in the staged migration.
- No vendor FPGA implementation, new bitstream, programming, flash modification, or hardware verification was attempted.

## Pending independent gates

- Validate rootless Docker and MCP source mount policy on the **actual** laptop after guarded service cutover.
- Check that the GitHub `development` branch and the canonical local checkout point to the same single migration commit, and `main` remains unchanged.
- Confirm on the refreshed live container that the new project manifests resolve PanoLab's tracked source; reject any fallback to old `/opt/panolab/litex/upstream` source.
- Complete vendor/IP/generated-binary license and physical G2 qualification separately.

**Do not equate a candidate source-build PASS with a completed live deployment.**
