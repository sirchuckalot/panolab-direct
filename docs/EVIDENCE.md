# Engineering milestone ledger

This is the curated record of significant published engineering changes,
in publication order, not a second Git history or a per-task worklog.
[AGENTS.md](../AGENTS.md#engineering-milestone-ledger) defines the binding
editorial ownership, entry criteria and commit discipline. Use
[architecture](ARCHITECTURE.md) for current design and operating state and
[operations](GETTING_STARTED.md) for supported procedures. The existing
historical evidence below identifies earlier checkpoints and their limits;
original reports link to the Git revisions that preserve them.

| Record | Scope and later evidence |
| --- | --- |
| [Published development milestones](#published-development-milestones) | Original commits in order, acceptance evidence and pending integration. |
| [G2 engineering handoff](#g2-engineering-handoff) | Earlier deployment decisions and the G2 development stopping point. |
| [LM1](../specs/LAB_MILESTONE_1.md) | Reinstall and six-service reboot on the already provisioned laptop before ISE. Preserves legacy paths and the separate LM2 simulation fixture. |
| [First Rescue build](RESCUE_BUILD_EVIDENCE.md) and [upstream review](../specs/PANOLAB_RESCUE_UPSTREAM_ADOPTION_REVIEW.md) | Source selection, initial generated BIOS/RTL and generic simulation. Later diagnostic evidence is recorded at iteration 15. |
| [LiteX environment recipe](#litex-bootstrap) | Initial bootstrap evidence, package and source pin rationale. Use the current installer and Docker recipe for provisioning. |
| [Unified development image](#unified-development-image) | Laptop image rebuild, 23 tests and generic BIOS simulation. Later warning cleanup removed the named stopped rollback container. |
| [Toolchain warning cleanup](#toolchain-warning-cleanup) | Warning-free BIOS, RX/RW segments, owner-local Buildx setup and exact stopped-container cleanup. |
| [Source migration](#source-layout-migration) | Isolated source-layout and build-equivalence evidence. The later external storage migration has a separate accepted operational result. |
| [ISE bring-up](#licensed-ise-bring-up) and [milestone review](#remote-ise-milestone) | Generic licensed jobs, network-license correction, eight-container checkpoint and preserved image identities. |
| [Remote iteration](https://github.com/sirchuckalot/panolab-direct/blob/2ab466ce9977dd8880eba4fbb5ce2906caa0b7c6/docs/REMOTE_ITERATION_ARCHITECTURE.md) | Historical staging and temporary maintenance design, with the restricted updater still pending. |
| [On-demand setup](#on-demand-ise-setup) | Existing stopped setup lifecycle and worker build. Setup creation from absence remains separate. |
| [Disposable ISE installation](#disposable-ise-installation) | Two fresh vendor installs, builds and verified resource disposal through the normal MCP route on the provisioned laptop. |
| [Fresh-host admission](#fresh-host-admission) | Read-only empty-home fixture. Full fresh-host install and reboot remain open. |
| [External storage runbook](#external-storage-cutover) | Historical owner-local migration procedure and rollback details. See architecture for the accepted cutover evidence. |
| [Rescue BIOS plan](RESCUE_IMPLEMENTATION.md) and [iteration 15](../projects/rescue/experiments/iteration-15/README.md) | Historical implementation design and later G2 diagnostic timing and simulation. Physical recovery and product qualification are open. |
| [Stock research](../research/pano-stock/README.md) | Physical stock discovery and readback, with private evidence and restore limits. |

## Published development milestones

Entries follow publication order in the verified development history,
starting at `9490e0c`. Each link identifies an original commit. Historical dates are verified UTC Git committer dates.
Related changes are grouped into meaningful milestones; older checkpoint
details are retained below.

| Milestone | Published commits in order |
| --- | --- |
| 2026-11-24 UTC — Pinned LiteX and unified rootless development image | [9490e0c](https://github.com/sirchuckalot/panolab-direct/commit/9490e0c8e7d938d593785c4d65cab4b2d2dfda5c), [27c0122](https://github.com/sirchuckalot/panolab-direct/commit/27c0122d0edb13a5118f254f4c0a705a6da854ad), [8878d1c](https://github.com/sirchuckalot/panolab-direct/commit/8878d1c998793519beb1e6a2c7f2d04c1d2e6c94) |
| 2026-11-24 UTC — Guarded BIOS warning cleanup, owner-local Buildx and rollback cleanup | [f03660d](https://github.com/sirchuckalot/panolab-direct/commit/f03660d759bd532834c4b1948e054dde69b963ea), [9e00f98](https://github.com/sirchuckalot/panolab-direct/commit/9e00f983376c13cc76a2f145c0009477cc686513) |
| 2026-11-24 UTC — Opt-in scoped GitHub publishing and authentication evidence | [04632b4](https://github.com/sirchuckalot/panolab-direct/commit/04632b4c26ef2efa03f7c08e3cfc8219abea2e6e), [3f28679](https://github.com/sirchuckalot/panolab-direct/commit/3f28679f2b50e2736d082d4fcef94e00bae5d695) |
| 2026-11-24 UTC — Source ownership standard and source-visible G2 layout with pinned provenance | [fa33395](https://github.com/sirchuckalot/panolab-direct/commit/fa33395bb907186e1d6f16fcf632fcee5786eb9a), [3286ab3](https://github.com/sirchuckalot/panolab-direct/commit/3286ab33b76885ce6b5c367b922c5d8f39601039) |
| 2026-11-24 UTC — Licensed ISE worker, immutable build inputs and temporary remote integration | [48782c2](https://github.com/sirchuckalot/panolab-direct/commit/48782c296224b69fc09cc854a5f1dfcd84283688), [3e5e6c3](https://github.com/sirchuckalot/panolab-direct/commit/3e5e6c37841bb4d1607886749268b2ce3cd5ced3) |
| 2026-11-24 UTC — On-demand setup, disposable licensed acceptance, read-only fresh-host audit and engineering handoff | [df741db](https://github.com/sirchuckalot/panolab-direct/commit/df741db54dc6ce55cd687c2153cddfbd81a34e10), [fdffa91](https://github.com/sirchuckalot/panolab-direct/commit/fdffa9159639793a33c3ae048b5f692115596fe4), [5e5768a](https://github.com/sirchuckalot/panolab-direct/commit/5e5768aefa3b309e624f3de1ae03b981261ff4e1), [ef250a4](https://github.com/sirchuckalot/panolab-direct/commit/ef250a4fe2641c27939027dcec0aba13e52cf37a) |
| 2026-11-25 UTC — Research root approval, stock G2 research and preserved Rescue iteration-15 checkpoint | [029141f](https://github.com/sirchuckalot/panolab-direct/commit/029141fc6b212660e781461c5e4f1c3aa41f4da8), [50e8529](https://github.com/sirchuckalot/panolab-direct/commit/50e8529d50d25a040ebbd982668c9a96d1f137f4), [9e79ad9](https://github.com/sirchuckalot/panolab-direct/commit/9e79ad9f0c5223d15c6eb89c4c6e25004f06472a) |
| 2026-11-26 UTC — Read-only canonical research mount | [817829e](https://github.com/sirchuckalot/panolab-direct/commit/817829e385ffc8297c17c65458115750316ca5a6) |
| 2026-11-26 UTC — Fail-closed admission, closed-loop correction, delegated authority and the independent Anchor boundary | [520fe64](https://github.com/sirchuckalot/panolab-direct/commit/520fe64a54d47a66c643bff6aefdd67b698d4abf), [7a33408](https://github.com/sirchuckalot/panolab-direct/commit/7a334086743002804cb8f9a12832842c549f10f7), [85ddd33](https://github.com/sirchuckalot/panolab-direct/commit/85ddd33fd252dbf0277c9cf741a2ed943e30d275) |
| 2026-11-26 UTC — Bounded text retrieval, external configuration and data, full read-only `/repo` with Git metadata masked, installer configuration and guarded cutover shipped together. Two follow-ups corrected external-directory admission and accepted the actual ISE setup and worker job record schemas. | [9549c19](https://github.com/sirchuckalot/panolab-direct/commit/9549c19402b59cf9e7aa1ed91e322dad9b2f4ec8), [897cd12](https://github.com/sirchuckalot/panolab-direct/commit/897cd12e8dc47765b58c246faff807db4783a90d), [31534ed](https://github.com/sirchuckalot/panolab-direct/commit/31534ed99072af490360a7882103031de8609594) |
| 2026-11-26 UTC — Documentation sweep and canonical agent launcher enforcement shipped together | [2ab466c](https://github.com/sirchuckalot/panolab-direct/commit/2ab466ce9977dd8880eba4fbb5ce2906caa0b7c6) |
| 2026-11-26 UTC — Final platform operations, architecture and research documentation consolidation | [db8b329](https://github.com/sirchuckalot/panolab-direct/commit/db8b329ff53f1b3d9874c91332c90226e48e4213) |
| 2026-11-26 UTC — Repository ownership and coherent commit discipline: formalized the existing document ownership map, dependency-ordered milestones and reviewed publication, with 193 independent Python tests and live canonical agent-policy verification. No new documentation files. | [2c488e9](https://github.com/sirchuckalot/panolab-direct/commit/2c488e9c23fc096b5f721afb2dff52c461f51ab1), [351a146](https://github.com/sirchuckalot/panolab-direct/commit/351a14647c2779b012ea3ae0a5c16544b42d5abf) |
| 2026-11-26 UTC — Licensed ISE result integration: corrected build-backed license reporting and integrity-checked, bounded TRACE retrieval. Both normal interfaces retrieved the historical 71,042-byte report (constraint coverage incomplete); fresh job `1795699429166374456` passed all six implementation stages, 20 ns constraint met (2.666 ns reported minimum period, 276 paths, zero setup/hold errors), 4,220,305-byte bitstream, license validated against that job. 202 Python tests and both Go build/test stages passed; rebuilt management images accepted on laptop. See [toolchain contract](TOOLCHAIN_MCP_CONTRACT.md). Not hardware qualification. | [9a35de7](https://github.com/sirchuckalot/panolab-direct/commit/9a35de7998cece688a306de188832a3907fbf5a1), [bc1ace2](https://github.com/sirchuckalot/panolab-direct/commit/bc1ace2adb815a4ec104fc26fc33a5dc4b2eefa9), [6e53368](https://github.com/sirchuckalot/panolab-direct/commit/6e533680cf37e42b6356929ac4f34b4cc3afaa69) |
| 2026-11-26 UTC — Single-owner engineering milestone ledger: established ChatGPT editorial ownership, Codex evidence handoff, material-milestone-only entries and immutable chronological references. No new documentation files; 202 applicable Python tests and live policy canary `a66809d35ead41b3ba56744228a764f3` passed. | [6efbbb3](https://github.com/sirchuckalot/panolab-direct/commit/6efbbb3f3c4a9e70dbbfbe1ed591d69ac494aff2) |
| 2026-11-26 UTC — Anchor Gate A design freeze accepted: owner approved A-01, preserving the qualified factory identity erase unit in place by default and permitting relocation only with verified necessity, preservation and recovery. Adopted PLR-ARCH-001 v1.2.0 as sole normative product specification; captured selected components and all Q01–Q25/Gates A–G in [Anchor](../projects/anchor/README.md). Independent verification: 436 checkpoint inventory hashes, nine upstream pins, 23 stock tests, 19 matching diagnostic firmware files, 204 platform regressions; 28 historical regression groups reviewed. Gate B implementation, sanitized factory-record contract and fresh Anchor timing remain open; no board acceptance or physical operation. | [f1aa4fc](https://github.com/sirchuckalot/panolab-direct/commit/f1aa4fcc366a313310b09cb2bd08c2c775cd4ee5) |

For current commit rules, see the
[mandatory development process](../AGENTS.md#mandatory-development-process).

- **Storage cutover.** Laptop verification recorded 172 migration tests,
  about 43 GiB transferred and verified, and seven services restored.
  Licensed ISE smoke job `1795685528446716627` passed all six stages and
  produced a 4,220,305-byte bitstream. See the
  [accepted migration baseline](ARCHITECTURE.md#accepted-external-storage-and-source-mounts).
- **Launcher and documentation.** Managed startup canary
  `2281bc2389b944f2a22a7283b0eacbc6` verified startup with canonical root
  instructions. Documentation consolidation recorded 193 passing Python
  tests and reduced first-party documentation candidates from 47 to 36,
  excluding upstream and frozen material.
- **Remaining qualification boundaries.** Full fresh-host installation,
  complete reboot qualification for the current topology and physical FPGA
  qualification remain open. Historical timing coverage is not inferred
  from a successful implementation build.

## G2 engineering handoff

The handoff records the owner-laptop baseline, source and configuration
ownership, deferred control-plane work and the next G2 engineering steps.
It records seven running services, nine verified source snapshots and
generic licensed ISE implementation at the development baseline. Use [architecture](ARCHITECTURE.md)
for current ownership, topology and qualification status. The historical G2
diagnostic stopping point remains in the [iteration-15 record](../projects/rescue/experiments/iteration-15/BUILD_RECORD.md).
[Original engineering baseline and handoff](https://github.com/sirchuckalot/panolab-direct/blob/31534ed99072af490360a7882103031de8609594/docs/ENGINEERING_BASELINE.md)

## Source layout migration

On 2026-11-23, the isolated laptop candidate verified tracked source
resolution, a warning-free non-RWX BIOS, 9 SoC tests and 66 cross-repository
tests. The 39,156-byte BIOS matched the pre-migration SHA-256
`52323e59edb6fe30c9b6d5d12b20be1ad7569eac2093217dacc4545db1d822a9`.
The UCF matched byte-for-byte. Verilog differed in timestamps and
nonfunctional blackbox display ordering. The test covered source layout
and equivalence. Canonical checkout and broker cutover had separate gates,
and the candidate did not exercise licensed ISE or hardware.
[Original migration acceptance](https://github.com/sirchuckalot/panolab-direct/blob/31534ed99072af490360a7882103031de8609594/docs/SOURCE_MIGRATION_ACCEPTANCE.md)

## Unified development image

PLR-ENV-003, 2026-11-24 UTC, accepted the owner-laptop rebuild and
dev-only replacement at `27c0122d0edb13a5118f254f4c0a705a6da854ad`.
The running image was
`sha256:c5799cd625d42ff4bd8158767a0917a5cda18082e2dc1976869400c93b5b1479`.
Independent MCP verification recorded 23 tests, seven matching source
pins, six running services, and a generic VexRiscv BIOS prompt with CRC
`7c83c0ea`. The interactive simulator was stopped by the expected timeout.
The 39,156-byte BIOS hash was
`8f9b16abc01f2d789cf7d190df97b690429d3b2d8032383417444d5b210399d3`.
The 492,579-byte HDL hash was
`1461a0e5c9e6a33ef83ae6976b4ed7034e84bfabc080fb0fc9ee8e06f767cf09`.
The stopped rollback was retained at this checkpoint. The
[later cleanup](#toolchain-warning-cleanup) records its removal.
Rollback execution, Ethernet TAP, vendor implementation and physical
qualification were outside this image acceptance.
[Original laptop acceptance and test matrix](https://github.com/sirchuckalot/panolab-direct/blob/31534ed99072af490360a7882103031de8609594/docs/UNIFIED_DEV_IMAGE_ACCEPTANCE.md)

The earlier pinned workspace build passed eight recipe tests and nine G2
tests. The guarded upgrade added four offline contracts and three
disposable-Git history checks. The historical reconciliation matched
`f1ca3a66` and `8637150` and preserved
`panolab/backup-development-f1ca3a66`. Use the
[current upgrade procedure](GETTING_STARTED.md#controlled-development-image-upgrade)
for new work.
[Original upgrade record](https://github.com/sirchuckalot/panolab-direct/blob/31534ed99072af490360a7882103031de8609594/docs/UNIFIED_DEV_IMAGE_UPGRADE.md)

## Licensed ISE bring-up

On 2026-11-24 two generic, unconstrained XC6SLX150 jobs passed XST,
NGDBuild, MAP, PAR, TRACE and BitGen on the normal licensed laptop worker.
Each produced a 4,220,305-byte bitstream, timing report and six stage logs
without another worker rebuild or restart between runs.

| Job | Immutable source SHA-256 | Bitstream SHA-256 |
| --- | --- | --- |
| `1795535626519203841` | `7b13ec8198956c61a8551e3c205f35372aa5218af0d01546d640250124a285e5` | `2d80c633d3e4915a65308fd58ff39828b8d3d4dd475ee244a2d2fef2aa11f1f9` |
| `1795535788871331709` | `c784a423993f8a9d9ea69338ccc8c60f97c92b932bdaf4e96aec18b57e8b237b` | `da710d59aa60d5e9806bcc83e2ce82c9d2d38f549090ecd13f996ead7bce8bac` |

Earlier job `1795527453486516942` failed at XST (127) and
`1795528026936978616` failed at MAP (2). The repairs used absolute vendor
binary paths, lowercase MCP argument names, a broker directory bind, and
an internal worker network presenting the existing licensed Ethernet
identity. Independent checks verified artifacts and worker isolation.
Board constraints, board timing and programming remain separate.
[Original bring-up evidence and failure chronology](https://github.com/sirchuckalot/panolab-direct/blob/31534ed99072af490360a7882103031de8609594/docs/ISE14_REMOTE_BRINGUP_EVIDENCE.md)

## Remote ISE milestone

The 2026-11-24 review began at `3286ab33b76885ce6b5c367b922c5d8f39601039`
with 25 changed or untracked paths and eight active containers. The review
record preserves the path-by-path decisions, seven checkpoint/rollback
image tags and two stopped ISE worker backups. Candidate manager, broker,
worker and setup image tests ran without swapping running services.
The private image/container inventory remains at
`maintenance/checkpoint-20261124-images-and-rollbacks.json` in the owner
workspace. The eight-service checkpoint did not establish reboot recovery
or fresh-host provisioning. See [architecture](ARCHITECTURE.md) for the
subsequent topology and rollback boundaries.
[Original source review and checkpoint image inventory](https://github.com/sirchuckalot/panolab-direct/blob/31534ed99072af490360a7882103031de8609594/docs/ISE14_REMOTE_MILESTONE_REVIEW.md)

## On-demand ISE setup

The 2026-11-24 test passed for a previously provisioned setup container.
Normal authenticated MCP completed 20/20 concurrent status calls
in about 30.8 seconds, three stop/start cycles and one additional
round trip after applying `restart: no`. Ten setup contract and dispatch
tests passed. Vendor media was 6,538,618,880 bytes, SHA-256
`cee0b046c1bbcfafcae59a96c7596c55c5477628c39bafefff8992cb8d33adaa`.
With setup stopped, job `1795542077281586637` passed all six stages,
producing a timing report and a 4,220,305-byte bitstream with SHA-256
`f0ad3f96557a41ba5e994982e929c98b3c393e1ec61d7ee7a0cfe1516bcbfab7`.
Private file hashes matched the pretest snapshot. Setup finished stopped
and seven services remained active. Provisioning setup from absence,
cold reboot, read-only request serialization and board qualification
remain open. Use the [current setup controls](GETTING_STARTED.md#on-demand-ise-setup-controls).
[Original lifecycle and stress-test evidence](https://github.com/sirchuckalot/panolab-direct/blob/31534ed99072af490360a7882103031de8609594/docs/ISE14_SETUP_ONDEMAND_STRESS.md)

## Scoped GitHub authentication

On 2026-11-23 Pacific, the owner-local setup reported
`GITHUB_SECRET_MOUNT_SCOPE=PASS`, `GITHUB_SECRET_AND_ASKPASS=PASS` and
`GITHUB_PUSH_AUTH=PASS`. Independent `repo_push` reported
`Everything up-to-date`. This exercised scoped authentication and a
no-op push. Use the [current owner procedure](GETTING_STARTED.md#scoped-github-push)
for provisioning or renewal.
[Original authentication record and procedure](https://github.com/sirchuckalot/panolab-direct/blob/31534ed99072af490360a7882103031de8609594/docs/GITHUB_PUBLISHING.md)

## LiteX bootstrap

PLR-ENV-001 verified seven pinned source revisions, the pinned Python virtual
environment and a fresh workspace BIOS/HDL build. The pinned Git Picolibc
data and wrapper replaced the incompatible PyPI layout. An absolute data
symlink within the container survives LiteX's source copy. Native simulation
dependencies built successfully. Ethernet TAP execution remains open under
the rootless policy. [Original bootstrap record](https://github.com/sirchuckalot/panolab-direct/blob/2ab466ce9977dd8880eba4fbb5ce2906caa0b7c6/docs/RESCUE_ENVIRONMENT_RECIPE.md)

## Toolchain warning cleanup

PLR-ENV-004 verified the six SHA-256-guarded build-output overlays on the
laptop. The BIOS rebuilt with zero warnings/errors and separate RX/RW ELF
segments. Nine G2 tests and 13 overlay and host maintenance tests passed.
The owner installed pinned Buildx, confirmed the default rootless driver and
removed only the named rollback ending in `020818Z`. Independent status
confirmed six services. A fresh Buildx image rebuild and live generic
simulation using the patched G2 BIOS remained pending at that checkpoint.
[Original cleanup record](https://github.com/sirchuckalot/panolab-direct/blob/2ab466ce9977dd8880eba4fbb5ce2906caa0b7c6/docs/DEV_TOOLCHAIN_WARNING_CLEANUP.md)

## Disposable ISE installation

On 2026-11-24 both runs used the normal authenticated manager/broker path.
Independent inspection confirmed disposal and matching private license,
installation-state and settings hashes. The run venue was the provisioned
laptop. Full timing-report retrieval and separate board acceptance remain open.

| Evidence | First completely disposable run | Repeat run |
| --- | --- | --- |
| Run ID | `f0080a606722` | `e65e511a8633` |
| Vendor job ID | `1795543475178815872` | `1795543672971384328` |
| Archive SHA-256 approved and checked | PASS | PASS |
| Fresh installation from initially empty volume | PASS | PASS |
| Unattended native installer status | `succeeded` | `succeeded` |
| Actual licensed implementation | 6/6 stages passed | 6/6 stages passed |
| `design.bit` | 4,220,305 bytes | 4,220,305 bytes |
| Bitstream SHA-256 | `09d4ada91e617928c79ee3b050a6f5bc641727da23eae73d303ca0fc7d8727f6` | `200a1df5fc44afe5c9811682fdd4ad9b5666d535cb9bb3cf361f480890fbef50` |
| Timing report and six stage logs | Present and hashed | Present and hashed |
| Controller terminal state | `passed`, `finished` | `passed`, `finished` |
| Verified test resource disposal | `disposed:true`, eight absent | `disposed:true`, eight absent |

Both runs used identical source inputs:
`acceptance_build.json` SHA-256
`46ba12cf2ed227b6eb49722612fcfd743520b40eaafb611ba7a5f549201141a7`
and `acceptance_design.v` SHA-256
`a9375958f743a8518ce7c4b99c10bf72765f7d04e58a065fa6970624f35fcfe2`.
Different bitstream hashes between runs are not interpreted as a
deterministic/reproducible binary-output claim; both outputs were independently
verified as real, nonempty vendor artifacts.

One attempted overlapping `@ise-e2e start` request was rejected safely
while the first run was active. Thirteen non-Docker unit tests covered
safe resource names, exact media/terms policy, source/mount separation,
caller output filtering, simulated success/failure and cleanup failure.
A build-time broker candidate with the initial test suite also passed;
no candidate image was promoted solely to run the acceptance tests.

[Original acceptance record](https://github.com/sirchuckalot/panolab-direct/blob/2ab466ce9977dd8880eba4fbb5ce2906caa0b7c6/docs/ISE14_DISPOSABLE_INSTALL_ACCEPTANCE.md) ·
[Current procedure and criteria](GETTING_STARTED.md#disposable-unattended-ise-147-acceptance)

## Fresh-host admission

The read-only 2026-11-24 empty-home fixture returned
`FRESH_HOST_PREREQUISITES=BLOCKED` (exit 10) for 20 missing fixture conditions.
Eight source and behavioral tests passed. An independent installation and
reboot remain pending, including rootless and private-input provisioning,
persistent worker commissioning from scratch, and entitlement on the test host.
[Original fixture and blocker evidence](https://github.com/sirchuckalot/panolab-direct/blob/2ab466ce9977dd8880eba4fbb5ce2906caa0b7c6/docs/FRESH_HOST_ACCEPTANCE.md) ·
[Independent acceptance sequence](GETTING_STARTED.md#independent-fresh-host-qualification)

## External storage cutover

The [accepted migration baseline](ARCHITECTURE.md#accepted-external-storage-and-source-mounts)
records the live cutover. The original owner-local procedure preserves all
transaction-specific paths, commands, inventory and rollback sequencing.
[Original cutover and rollback runbook](https://github.com/sirchuckalot/panolab-direct/blob/2ab466ce9977dd8880eba4fbb5ce2906caa0b7c6/docs/EXTERNAL_STORAGE_CUTOVER.md)
