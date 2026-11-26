# Evidence index

Use [architecture](ARCHITECTURE.md) for the current operating state and
[operations](GETTING_STARTED.md) for supported procedures. The records below
identify the scope and limitations of earlier checkpoints. Original reports
are pinned to the verified development revision
`31534ed99072af490360a7882103031de8609594`.

| Record | Scope and later evidence |
| --- | --- |
| [G2 engineering handoff](#g2-engineering-handoff) | Earlier deployment decisions and the G2 development stopping point. |
| [LM1](../specs/LAB_MILESTONE_1.md) | Reinstall and six-service reboot on the already provisioned laptop before ISE. Preserves legacy paths and the separate LM2 simulation fixture. |
| [First Rescue build](RESCUE_BUILD_EVIDENCE.md) and [upstream review](../specs/PANOLAB_RESCUE_UPSTREAM_ADOPTION_REVIEW.md) | Source selection, initial generated BIOS/RTL and generic simulation. Later diagnostic evidence is recorded at iteration 15. |
| [LiteX environment recipe](RESCUE_ENVIRONMENT_RECIPE.md) | Initial bootstrap evidence, package and source pin rationale. Use the current installer and Docker recipe for provisioning. |
| [Unified development image](#unified-development-image) | Laptop image rebuild, 23 tests and generic BIOS simulation. Later warning cleanup removed the named stopped rollback container. |
| [Toolchain warning cleanup](DEV_TOOLCHAIN_WARNING_CLEANUP.md) | Warning-free BIOS, RX/RW segments, owner-local Buildx setup and exact stopped-container cleanup. |
| [Source migration](#source-layout-migration) | Isolated source-layout and build-equivalence evidence. The later external storage migration has a separate accepted operational result. |
| [ISE bring-up](#licensed-ise-bring-up) and [milestone review](#remote-ise-milestone) | Generic licensed jobs, network-license correction, eight-container checkpoint and preserved image identities. |
| [Remote iteration](REMOTE_ITERATION_ARCHITECTURE.md) | Historical staging and temporary maintenance design, with the restricted updater still pending. |
| [On-demand setup](#on-demand-ise-setup) | Existing stopped setup lifecycle and worker build. Setup creation from absence remains separate. |
| [Disposable ISE installation](ISE14_DISPOSABLE_INSTALL_ACCEPTANCE.md) | Two fresh vendor installs, builds and verified resource disposal through the normal MCP route on the provisioned laptop. |
| [Fresh-host admission](FRESH_HOST_ACCEPTANCE.md) | Read-only empty-home fixture. Full fresh-host install and reboot remain open. |
| [External storage runbook](EXTERNAL_STORAGE_CUTOVER.md) | Historical owner-local migration procedure and rollback details. See architecture for the accepted cutover evidence. |
| [Rescue BIOS plan](RESCUE_IMPLEMENTATION.md) and [iteration 15](../projects/rescue/experiments/iteration-15/README.md) | Historical implementation design and later G2 diagnostic timing and simulation. Physical recovery and product qualification are open. |
| [Stock research](../research/pano-stock/README.md) | Physical stock discovery and readback, with private evidence and restore limits. |

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
[later cleanup](DEV_TOOLCHAIN_WARNING_CLEANUP.md) records its removal.
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
