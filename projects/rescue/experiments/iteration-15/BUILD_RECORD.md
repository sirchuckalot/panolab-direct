# Build and qualification record

| Candidate | BIOS bytes | Qualification |
|---|---:|---|
| Baseline | 39,156 | Source build; baseline ISE not system-clock timing qualified |
| bios-integration | 14,940 | Source/ELF and boot policy tests |
| bios-storage-probe | 16,148 | Source/ELF, JEDEC component tests |
| bios-network-probe | 20,724 | ISE job 1795558394532436045; GMII simulation |
| bios-persistent-probe | 25,972 | ISE job 1795571940203944746, read-only diagnostics |
| bios-synthetic-state-only | 26,172 | Synthetic identity/journal CPU simulation |
| bios-upload-ram-sim | 43,084 | Synthetic RAM-only upload CPU simulation |
| bios-session-ram-sim | 46,004 | Synthetic RAM-only peer/session CPU simulation |
| bios-expiry-short-sim | 46,004 | Synthetic RAM-only short lease test |

Latest vendor-qualified diagnostic: `bios-persistent-probe/build-s5.GxaTDN`. BIOS SHA-256 `46171c583d93cbe91574d3fa3001e6549cbaba1c57fc84576d0b0c9365183aa0`; 39.62% of 64 KiB ROM. Vendor job `1795571940203944746` completed all six ISE stages. Bitstream 4,221,965 bytes, SHA-256 `a1229f2a74f8af417a231393f3f4da4c1493c99648fdc61120e86af65234f2d9`. Timing report SHA-256 `2efd1351836a01cffbfb24663e747df9bbedf8ec9755945cdf3fcab801dd1fab`. 0 setup/hold errors, score 0, 894,214 paths covered; worst reference +3.551 ns, derived system +1.248 ns, RX +1.090 ns, TX +1.629 ns. 0 DRC errors, 11 warnings including documented BRAM advisory. This establishes a vendor implementation/timing result, not actual electrical, clock/PHY, boot or board acceptance.

Richest CPU-simulated firmware: `bios-session-ram-sim/build-s5.BFLBtD`, BIOS 46,004 bytes, 70.18% ROM, 32.97% SRAM, 19,532 bytes ROM remaining. Actual VexRiscv execution with behavioral Spartan-6/GMII and synthetic RAM NOR. Session and short-expiry traces independently validated 13 and 7 exchanges respectively. This firmware does not contain the iteration-15 ledger and is not a physical programming image.

Iteration-15 native results include 459 ledger interruption cases and 18 abrupt process exits at nine application mutations with retained synthetic memory. No physical erase/program or actual power-loss test. The latest real ISE artifact predates these changes. Neither build size nor nominal flash geometry proves a safe new partition map.

Original generated build outputs and vendor-stage input trees are retained locally; selected hashes are listed in [ARTIFACT_INVENTORY.json](ARTIFACT_INVENTORY.json). Source ownership and redistribution follow the parent project and [architecture standard](../../../../specs/PANOLAB_SOURCE_AND_PROJECT_ARCHITECTURE.md). Do not check generated tool copies or raw bitstreams into source history. Exact historical regeneration may need pinned output dependencies and staged files; no bit-for-bit rebuild of the entire checkpoint is claimed.
