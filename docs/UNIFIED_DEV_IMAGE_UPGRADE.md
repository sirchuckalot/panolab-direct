# Unified PanoLab Development Image — Build and Controlled Upgrade

**Record:** PLR-ENV-002 | **Date:** 2026-11-23 | **Status:** **LAPTOP_VERIFIED** on 2026-11-24 UTC. The full owner-run rootless image build, same-container-name migration, 23 tests and independent live BIOS simulation passed. See [acceptance evidence](UNIFIED_DEV_IMAGE_ACCEPTANCE.md).

## System architecture (accepted decision)

PanoLab uses **one** general-purpose, source-pinned modern FPGA development Docker image: `panolab-direct-modern:local`, instantiated as the existing `panolab-direct-dev-1` container. It includes all compatible open-source development tools. Separate PanoLab service images exist for the manager, git gateway, broker, tunnel and separately licensed ISE 14.7 workflow; those are operational roles, **not** per-tool development images. No new LiteX service, new modern image name, or second general development Dockerfile is introduced.

The `docker/modern/Dockerfile` now has seven clearly documented functional sections: base OS, HDL, embedded RISC-V, AI tooling, source-pinned LiteX, runtime user/mounts, and acceptance label. Version pins live under `docker/modern`; first-party board source lives under `boards/`. New compatible development tools belong in the same Dockerfile and its pinned scripts. New FPGA families are added via BSPs, not additional everyday development containers. ISE 14.7 remains separate because its vintage operating-system/library and licensed-vendor constraints are genuinely incompatible with this modern stack.

## Current installation states

- **GitHub `development`:** unified modern image definition; installer and tests are committed.
- **Current laptop development container:** runs the *rebuilt unified image* under the original `panolab-direct-dev-1` name; the former container is preserved stopped for rollback.
- **Persistent workspace:** retains the previous local LiteX experiments and the accepted new BIOS/HDL artifacts.
- **Modern image:** `panolab-direct-modern:local` was rebuilt and qualified at image ID `sha256:c5799cd625d42ff4bd8158767a0917a5cda18082e2dc1976869400c93b5b1479`. This is a new revision of the **same** existing development image, not an added image role or service.

Container image layers and a stopped rollback container may temporarily coexist during acceptance. These are safety artifacts, not separately maintained developer tool environments.

## Controlled one-command upgrade

For the owner's established **clean** laptop Git checkout on `development`, the published `host/reconcile-and-upgrade.sh` script is fetched from the trusted Git remote and executed in Bash. The operator command includes a **commit-SHA guard** (see final conversation instruction); it:

1. Confirms a non-root owner, the expected GitHub origin, `development`, a clean working tree and the exact fetched commit.
2. If the local branch is already an ancestor, fast-forwards. If it is precisely historical local commit `f1ca3a66e48aa9fc5acf4827d0bcb779143aae51`, it verifies its **whole tracked file tree** is identical to published milestone `863715050d1894320590b47a3607543f1cf0a8eb` and saves that local commit as `panolab/backup-development-f1ca3a66`. Only then is the clean checkout advanced to GitHub `development`. Any unexpected branch/commit/content/untracked file causes an immediate stop with no reset.
3. Invokes the existing `panolab-install.sh --upgrade-dev` entry point, which keeps the project rootless Engine and checks pre-existing owner credentials/mounts.
4. Rebuilds **only** the existing `panolab-direct-modern:local` image if its approved version label differs; it runs an offline read-only image test **before** disturbing any existing container.
5. Checks the exact label, mount points, privileges, workspace and Codex credential mount of `panolab-direct-dev-1`. If they differ, it refuses the replacement.
6. Stops and renames just the previous development container to `panolab-direct-dev-1-rollback-<UTC timestamp>`, while preserving its bind-mounted workspace, source and Codex authentication. Starts the new container **under the same six-service deployment name** and the original CPU/memory/PID limitations.
7. Checks LiteX/RISC-V/HDL tools, Codex login, G2 source tests and generates a BIOS/Verilog/UCF source proof in a distinct persistent `/workspace/panolab-rescue-upgrade-<timestamp>` directory (not `.bit`; **no hardware flash or ISE invocation**). On failure, the scoped rollback attempts to restore the old dev container.
8. Leaves the old container **stopped as a temporary rollback point** until the owner/agent verifies results. This is *not* a seventh running service. It is not removed or pruned without an explicit subsequent cleanup decision.

An ordinary `bash ./panolab-install.sh` remains available for established full-system installation. The new explicit `--upgrade-dev` mode is for the controlled dev-only image swap. It does not reconfigure the manager, broker, repo gateway, private tunnel, ISE worker, rootless user service or FPGA.

## Evidence and acceptance

**Completed in the existing rootless container before publication:** the current pinned LiteX installation created a 39,156-byte BIOS binary, G2 Rev B HDL and UCF, nine G2 SoC unit/simulation tests, HDL syntax check and an upstream generic LiteX BIOS Verilator session. The versioned dependency recipe passed clean workspace installation and eight offline recipe tests. The unified layout and guarded upgrade added four offline contract tests and three disposable-Git history cases (equal tree/backup/advance, dirty checkout refusal, mismatched-tree refusal). Shell scripts pass `bash -n`.

**Laptop acceptance completed:** the owner-built whole modern Docker image and its dev-only migration passed. Independent MCP verification confirmed 23 tests, exact package/source pins, generated BIOS/HDL artifacts, all six services and generic simulated BIOS console. See [PLR-ENV-003](UNIFIED_DEV_IMAGE_ACCEPTANCE.md). Rollback to the old container was *not exercised*, though the stopped previous container is retained. FPGA hardware, ISE BitGen, Ethernet TAP and all G2 A/B/ICAP features remain separately pending.

### What the operator should return

Provide the final command output, especially:

- `SOURCE_UPDATE=PASS` and the new GitHub commit SHA.
- `LITEX_REQUIRED_TOOLS=PASS` and `DEV_UPGRADE_RESULT=PASS` (or the precise failure).
- `IMAGE_ID`, `BIOS_AND_HDL_ARTIFACTS`, and any `ROLLBACK_CONTAINER` line.
- If a command fails, the complete **nonsecret** error and the exact step where it stopped. Do not paste `.env`, MCP tokens, Codex auth, Xilinx licenses or private keys.

After that, verify the running container via the PanoLab MCP connection, confirm the baseline simulation and full working services, then decide when the stopped rollback container can be removed. Until then **no automatic cleanup**.

## Safe operating boundaries

- One modern dev image tag. No per-tool or per-board Docker image proliferation.
- The separate ISE worker and any approved proprietary vendor packages remain distinct.
- No `sudo`, host-level `apt`, rootful Docker, privileged TAP, unrelated service restarts or global Docker prune.
- No automatic JTAG, FPGA reload, stock SPI layout rewrite, image flashing or network hardware deployment.
- Source control `main` stays the accepted immutable baseline; only `development` gets these commits.
