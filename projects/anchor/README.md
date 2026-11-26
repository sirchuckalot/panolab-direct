# PanoLab Anchor

Anchor is the FPGA boot, recovery and deployment product for Pano Logic G2 Rev B
(XC6SLX150-2-FGG484). Its LiteX BIOS and VexRiscv use on-chip ROM and SRAM.
A full FPGA configuration replaces Anchor when an application boots. CPU-less
applications remain separate under the [Direct baseline](../../specs/PANOLAB_DIRECT_v1_0.txt).

The owner approved A-01 on 2026-11-26. [PLR-ARCH-001 v1.2.0](../../specs/PANOLAB_RESCUE_V1.md)
is the sole normative Anchor product specification. Its Gate A SHA-256 is
`1623482797201e840f18949a4c2246f03f255d0514717f202d77873c072487a8`. Gate A records the design and source selections.
Implementation and board qualification remain pending. The Rescue DNS-SD
service name, API v1, manifest v1 and trust profiles carry forward.

## Product source and entry points

Gate B plans `project.toml`, `build.sh`, `test.sh` and `stage_ise.py` under
this directory, with `soc/rescue_soc.py` and `tests/verify_build.py` from the
historical candidate interfaces. Anchor owns product integration and tests.
[The Rev B BSP](../../boards/pano_g2_rev_b/README.md) owns board adaptation,
identity source and geometry. [The source standard](../../specs/PANOLAB_SOURCE_AND_PROJECT_ARCHITECTURE.md)
governs ownership and provenance. Keep reusable code in `shared/` where
actually shared and retain original notices and [licenses](../../LICENSES/README.md).
The [central registry](../../third_party/registry.toml) supplies nine verified
historical selections: LiteX `afed6623`, LiteX-Boards `2ccda127`, LiteEth
`a54c730c`, LiteSPI `a5a0090a`, Migen `e19524c9`, Picolibc `16ff442d`,
pythondata-software-picolibc `6a13ccce`, VexRiscv `1.0.1.post407` and
compiler-rt `0.0.post6206`.

Paths below are relative to the frozen [iteration-15 checkpoint](../rescue/experiments/iteration-15/README.md)
at `9e79ad9f0c5223d15c6eb89c4c6e25004f06472a`. C stems name the source
and matching header where present. Use these paths for provenance audits.
Normal Anchor build, test, stage and packaging must run with Rescue and
archived outputs absent, using only declared inputs. Reject missing or
altered bytes, unsafe links and undeclared imports or overlays.

| Key | Class and selected source | Evidence and integration |
|---|---|---|
| S | CORE — `bios-persistent-probe/rescue_soc.py`, `bios-persistent-probe/bios_source_overlay.py`, and `bios-persistent-probe/boards/pano_g2_rev_b/bsp.py` | Select corrected PLL/reset and buffered Wishbone logic for existing active BSP owner and SoC. Current BSP is the earlier clock/button adaptation. Preserve upstream BIOS and VexRiscv, guarded build-output overlays and waveform/UCF tests. B/C physical clock and button proof. |
| I | CORE — `bios-persistent-probe/firmware/` stems `rescue_bios`, `rescue_boot_policy`, `rescue_diag`, `rescue_flash_probe`, `rescue_flash_probe_litex.c`, `rescue_spi_nor`, `rescue_storage`, `identity_record`, `rescue_protected_read`, read-only `rescue_journal`; `host-diag/rescue_diag_client.py` | Native/RV32/GMII evidence. Reuse LiteX NOR adapter and validation. Protected reader expects normalized identity plus a complete layout. Gate B isolates identity read and reports actual status. The carried firmware passes NULL/0 layout and starts lab Ethernet even on probe failure. |
| M | PRODUCT, UNQUALIFIED — `manifest-core/manifest_core.c`, `manifest-store/manifest_store.c`, `image-core/image_core.c`; `spi-nor/rescue_spi_nor.c` mutation logic behind the same driver | Native and synthetic NOR. Existing parser is a narrow unsigned subset. Integrate full required profile fields, actual detected target and feature checks, overlap/erase protection and independent readback. |
| U | PRODUCT, UNQUALIFIED — `managed-stream/rescue_update.c`, `managed-stream/managed_stream.h`, `managed-stream/stream_slot.h`, `upload-session/upload_session.c`, `flash-transaction/rescue_flash_transaction.c`; `wire-spi-integration/managed_wire_adapter.c`, `management-wire/management_wire.c` and `wire-spi-integration/test_managed_spi.c` | Existing bounded transaction owner and provisional parser. Synthetic 4,221,965-byte upload, 4,124 chunks. Integrate final v1 transport and wire behavior. |
| J | PRODUCT, UNQUALIFIED — `journal-core/rescue_journal.c`, `trial-core/rescue_trial.c` and `boot-model/rescue_boot_model.py` as a test model | Two-copy commit, torn records and mocked return. Integrate persistent trial binding, bounded timer, durable attempt before launch and live return/health verifier. |
| R | PRODUCT, UNQUALIFIED — `icap-integration/icap_launch_interlock.v`, `icap-integration/spartan6_icap.v`, `icap-integration/tb_icap_launch_interlock.v` with `icap/icap_spartan6_stub.v` test-only | Packet/interlock simulation. BSP must own actual SPI exclusivity/CDC, slot-to-address binding and fixed-target CPU-less app return. Interlock transmission does not prove configuration or liveness. |
| H | PRODUCT, UNQUALIFIED — `host-management-sim/host_management.py`, `host-reconcile-sim/reconcile.py`, `network-session/network_session.c` | Injected transport and CPU/GMII synthetic session evidence. Integrate DHCP/discovery/fallback, exact-unit reconnect, ownership/expiry, retries and real profile-aware health/confirm. |
| L | PRODUCT reliability, implementation choice DEFERRED — `operation-ledger/op_ledger.c`, `ledger-reset-integration/test_stream_slot.c`, `reset-recovery-sim/test_stream_slot.c` | 459 synthetic interrupted ledger mutations and 18 abrupt process exits. Reuse outcome recovery invariants. Select extra ledger storage only if existing journal/manifest bindings fail a mandatory retry/replay/reconciliation case. |
| X | SUPERSEDED / DEFERRED — earlier SoC/BIOS alternatives, `update-controller/rescue_update.c`, `stream-slot/rescue_update.c`, standalone ICAP transmitter; synthetic-state, RAM upload/session and expiry BIOS variants and host bridge | Preserve in Rescue. Keep necessary fixtures in product tests with provenance. Leave RAM-backed mutations out of the physical link. Paired and production qualification may follow initial Trusted-LAN bring-up. Their obligations remain binding for those claims. |

## Identity integration boundary

The [stock evidence](../../research/pano-stock/FLASH_LAYOUT.md) covers one
Rev B and one pass of the documented 16 MiB address extent, with 512 block
hashes, 47 prior-reference comparisons and two matching factory-sector
reads. Of 29 eight-byte records, seven known words correlated with live
registers and label. The register decoder and opaque sector audit supply
partial evidence. The raw selectors, byte order, bounds and termination
or conflict rules need a separately verified sanitized contract and
synthetic fixtures before enabling a real decoder. Gate C still needs direct
JEDEC, non-aliasing, physical geometry and same-unit proof. The reference NOR
model supplies no Anchor allocation. Restoration remains unproved.

In B, use bounded BSP-owned, identity-only reads independent of the journal
and application map. Exercise the real startup path with injected readers
and synthetic fixtures. Validate the exact Ethernet MAC and report identity
source and status. Inject GMII requests on bad input to prove product
ARP/UDP stays silent and verify application boot remains disabled. Cover
unapproved profiles, target/JEDEC mismatch, read faults and bounds,
erased/malformed/conflicting records, integrity failure and duplicate MACs.
An explicitly selected and visibly labeled isolated lab mode permits its
fixture MAC and read-only diagnostics. Test the ELF and simulated SPI for
absence of flash mutation, journal commits and ICAP launch.

## Evidence and gate exits

The review verified 436 inventoried files, nine source selections and
19 matching candidate firmware files. It reviewed the 28 historical
[regression groups](../rescue/experiments/iteration-15/evidence/checkpoint-regressions.txt)
and credited 23 offline stock tests. The [historical diagnostic](../rescue/experiments/iteration-15/BUILD_RECORD.md)
used 25,972 bytes of BIOS ROM and a 4,221,965-byte bitstream. ISE job
`1795571940203944746` reported zero setup/hold errors over 894,214 paths
and +1.248 ns system slack. The richest synthetic BIOS used 46,004 bytes
of ROM and 32.97% SRAM including its fixtures. Measure integrated ROM,
SRAM/stack, routed utilization/timing and flash consumption. The BIOS target
is 53,248 bytes within 65,536 bytes, leaving 12 KiB reserve.

| Gate | Required exit evidence and dependency |
|---|---|
| A | Owner approval of A-01, approved spec identity and independent reconciliation of the source/coverage and qualification boundaries below. |
| B | After A, reproducible source build/test/stage and isolated closure, approved pins/licenses, read-only link and integrated synthetic identity/lab negative and positive tests above. RWE/RWX LOAD or suppressed/unresolved build diagnostics fail. Corrected image requires fresh bound ISE timing/resource proof before C physical use. Real decoder activation requires the sanitized contract. |
| C | Prespecified image/hash, exact experimental target and separate authorized reversible operation, credible recovery plan and private backup verification. Demonstrate startup, Ethernet, clock/reset, held/released button, repeated direct JEDEC, capacity and non-alias evidence, same-unit identity against label/stock and on-wire MAC. Stop on discrepancy, unsafe entry or unverified recovery. A diagnostic can precede full identity proof. Preserve working fallback until independent recovery and required handoff/cold return are demonstrated. |
| D | After applicable C proof, qualify erase/page behavior and exact generated images including headers, padding and alignment. Validate non-overlap, both app capacities, distinct journal erase units and protected BOOT/RESCUE/IDENTITY under A-01. Exercise inactive-only staging, wrong target/size rejection, hash/readback, durable state, SPI interlock, real ICAP handoff and bounded app return to Anchor with host reconnection. Stop at unsafe fit, mismatched readback or unproved fallback. Permanent boot activation is last under §8 and separately approved. |
| E | After D, demonstrate cold/reset Anchor-first, held-button maintenance, bounded configurable autoboot with absent link/invalid images, verified launch, observed app health and identity, matching trial confirmation after return, persistence across power cycle and rollback after failed/unconfirmed trial. A dead app must allow independent physical recovery. |
| F | After E, prove final API ownership, expiry, duplicate/stale/replay defenses, reset reconciliation and operation attribution, interrupted upload and torn journal recovery, with repeated interruption at each applicable phase and preservation of confirmed app and Anchor. Resolve one durable authority per persistent fact. |
| G | After B–F, rerun applicable native, RV32, RTL, full-system, source-closure and licensed implementation gates against one identified revision. Close all applicable Q cases with actual board/release evidence, including two-board discovery and profile negatives. Bind source/constraints/tools/licenses/image/manifest/profiles, audit package, verify recovery and obtain owner release approval before versioned publication or main promotion. |

## Q01–Q25 traceability

The selected-source keys above refer to historical model and component
evidence. Board acceptance is open for all cases. The specification's
[qualification matrix](../../specs/PANOLAB_RESCUE_V1.md#10-qualification-and-acceptance-matrix)
controls qualification, including the prerequisites for a resilient A/B claim.

| Q | Selected source and current evidence | Missing integration and acceptance evidence |
|---|---|---|
| 01 | S/I, simulated JEDEC/PLID, stock single-unit partial bench | B target/identity gating; C correct part/rev, measured geometry and MAC, reject mismatch. |
| 02 | I/M/U, simulated layout and protected NOR | D measured erase/page boundaries, disjoint allocation and deny protected writes through ordinary API. |
| 03 | I, simulated PLID and partial stock correlation | B sanitized grammar and startup; C same-unit proof; D–F raw hash and persistence/protection across reboot, upgrade and failed trial. Apply relocation proof if needed under A-01. |
| 04 | S/I/J, simulated recovery startup | E cold/reset reachable Anchor before launch. |
| 05 | S/R, simulated button/interlock components | C reversible path, E dead-app independent physical recovery. |
| 06 | H, discovery qualification NOT_STARTED | G DNS-SD on two boards with distinct true MAC and ID and ordinary LAN behavior/fallback. |
| 07 | H/U, simulated bounded sessions | F/G real device bounded visible unpaired operations; authenticated profiles reject unauthenticated/replayed updates before claim. |
| 08 | M/U, simulated manifest/slot bounds | D actual revision/FPGA/oversize rejection before flash. |
| 09 | M/U, simulated digest/readback | D/G reject hash mismatch and applicable invalid signatures, preserving confirmed image. |
| 10 | U/M/J, simulated inactive staging | D verify actual inactive-only writes and preserved bootable confirmed slot. |
| 11 | U/H/L, synthetic interruption/expiry | F physical disconnect/retry/power cuts, ignore partial candidate and retain confirmed image. |
| 12 | J/L, synthetic torn writes and resets | F interrupt physical journal erase/program, retain last valid record or enter safe recovery. |
| 13 | J/R, simulated trial and ICAP packets | D/E real trial configuration, expected app image ID. |
| 14 | J, simulated trial exhaustion | E failed confirmation cannot loop; prior confirmed remains selectable. |
| 15 | J/R/H, simulated matching return | E observe health, reconnect, confirm correct trial under supported profile, power-cycle persistence. |
| 16 | J/U, simulated rollback | E requested revert preserves prior known-good and identity on device. |
| 17 | S/R, independent dead-app proof NOT_STARTED | E power-cycle/button restores Anchor with dead app. |
| 18 | U/J/L, synthetic power-failure models | F repeated physical disruptions at each phase retain independent boot. |
| 19 | I/M/U/H, simulated storage restrictions | F/G ordinary API denies protected-region operations and audited public bundle/logs exclude secrets. |
| 20 | S/M, simulated target checks | G reproducible BSP tests and device interoperability with foreign board binary rejection. |
| 21 | S/R, rescue replacement qualification NOT_STARTED | Conditional for a claimed rescue updater. Require separate approval and fault proof of alternate independently bootable path. |
| 22 | S and manifest/resolver, diagnostic build and provenance evidence | G exact release inputs/outputs, replayable build/source package, redacted device/profile and test record. |
| 23 | I/J, simulated 1–60 s policy; live timer open | E actual bounded configurable timeout with no link and absent or invalid image. |
| 24 | S/I, simulated held-button latch | C/E held physical button causes indefinite Ethernet maintenance even with unusable app. |
| 25 | U/H/M/R, synthetic RAM/network and NOR integration | D–G real unpaired Ethernet stage/verify/boot without serial/JTAG/login; reject invalid, mis-targeted and protected writes. |
