# LM1 — First working agentic FPGA development laboratory

**Software acceptance date:** 2026-11-23. **Frozen source reference:** GitHub `main` commit `006b6ee608c5c496292686e2f8c1f690aaa158f2`. At the freeze, `development` was identical; it is the active work branch and may advance thereafter. **LM1/LM2 here label laboratory milestones**, distinct from the FPGA design roadmap `M0–M5` in [the system specification](PANOLAB_DIRECT_v1_0.txt).

## Acceptance statement and scope

The owner's existing, provisioned Linux laptop has a functioning **rootless Docker, authenticated MCP, agent-accessible software/RTL development laboratory**. A full project-only tear-down and fresh reinstall using the checked-in installer passed; all six services subsequently recovered automatically after a laptop reboot. This is not proof of a fresh unprovisioned host, a Xilinx ISE implementation, LiteX integration, or physical FPGA operation.

## Accepted evidence on the actual laptop

| Gate | Observed result |
| --- | --- |
| Project deployment | Owner-user rootless Docker with systemd cgroups v2; unmodified installer rebuilt five software images and created six services after project-only teardown |
| End-to-end management | Authenticated local/remote MCP worked, anonymous local MCP was rejected, and source/Git and broker operations were constrained |
| Isolation | Only approved rootless broker sees owner Docker socket; source gateway denies `docker/private/`; development source mounts exclude it |
| Toolchain | Modern dev image has Yosys 0.33, Icarus 12.0, Verilator 5.020, Codex CLI 0.171.0 and authenticated Codex session |
| Resource quotas | 2 CPU equivalents (`cpu.max=200000 100000`), 4 GiB memory, 256 PIDs enforced in dev container |
| Reinstall recovery | Private license/media/auth and ignored `docker/.env` preserved and critical file checksums verified; independent recovery backup retained |
| Persistence | First reboot recovered five management/tunnel services but not standalone dev. Docker `unless-stopped` fixed dev; second reboot recovered all six without manual start |
| Source integrity | Canonical local checkout `~/Projects/repos/panolab-direct-main` is on `development` tracking `origin/development`; GitHub has exactly `main` and `development`, identical at freeze commit; 15 source tests and installer read-only preflight passed |
| Development example before LM2 | Container-based Icarus counter smoke test and Yosys/tool availability checks passed |

Evidence is limited to the documented time, host and software configuration. An installer `--check` or successful simulation cannot prove external hardware capability.

## Engineering decisions retained

1. **Local, least-privilege execution.** Laptop owner's rootless Docker Engine with systemd cgroups v2; no host `sudo`, rootful Docker, broad Docker pruning, privileged containers or vendor dependencies installed on the host.
2. **Explicit control and identity boundaries.** Outbound authenticated MCP tunnel → private manager → approved Git/source gateway, ISE setup and restricted rootless broker. Development container mounts only approved source and workspace. Rootless container UID 0 represents the owner, not host root.
3. **Separate private inputs.** Keep `docker/private/` license, vendor archive, credentials, Codex auth and workspace owner-controlled and ignored; `docker/.env` is separate and also private. Protect them independently through changes and backups.
4. **One canonical checkout, two branches.** `main` is the accepted source baseline. New work is staged/tested and committed on `development` only. Promoting to `main` requires explicit owner approval.
5. **Reproducible operational recipe.** Use the checked-in rootless installer; avoid migration overlays as a permanent deployment method. A standalone dev container has `unless-stopped` restart policy, even though it is not Compose-managed.
6. **Evidence has levels.** Software source tests, vendor ISE implementation and physical G2 tests are separate gates. The ISE worker has exactly five existing agent-facing build operations. Never program or flash a board without specific owner authorization and a recovery path.
7. **FPGA design remains staged.** Target is Pano Logic G2 Rev B Spartan-6 `XC6SLX150-2-FGG484`; CPU-less LiteX/LiteEth/Etherbone with allowlisted CSR access is planned, *not implemented*. Factory SPI remains untouched.

The current architecture is maintained in [architecture](../docs/ARCHITECTURE.md); this is an **evidence snapshot**, not a competing set of architecture decisions.

## Lessons learned and implications

- **Fresh project rebuilds find integration defects:** stage-by-stage migration alone did not prove installation from scratch on the same laptop.
- **Secrets cross multiple locations:** preserving only `docker/private/` would miss the independent ignored `docker/.env` and possibly mutable workspace/auth state.
- **Reboot recovery must be tested:** container uptime and a running daemon did not establish standalone dev persistence. A second reboot validated the fixed policy.
- **Git hygiene matters:** old unrelated histories, a single-branch clone's fetch refspec and historical branches required guarded cleanup. Now no stale branches remain.
- **Authentication and access controls require tests:** source inspection cannot substitute for anonymous-rejection and restricted mount checks on the real laptop.
- **Agent tests must detect faults:** an RTL testbench should be proven to reject a representative erroneous implementation, not just pass on the expected design.

## Unverified acceptance gates

An unattended bare-host/bootstrap install; a licensed ISE 14.7 vendor compilation/bitstream and timing closure; pinned compatible LiteX/Migen/LiteEth revisions; exact Rev B FPGA constraints; physical board access, volatile configuration, Etherbone, LiteScope and framebuffer observation; long-run reliability and controlled upgrades.

## LM2 — First complete agent-directed RTL engineering demonstration

**Objective:** Develop and verify a small simulation-only classic Wishbone-style CSR responder while preserving `main`. This is a practice artifact, **not** the accepted FPGA-system M1 Etherbone design.

- RTL: [`gateware/panolab_csr_demo.v`](../gateware/panolab_csr_demo.v) — read-only ID `0x504c4142` (ASCII PLAB), read-only status `1`, byte-enable scratch register, reset, reserved address zero, one ACK for each held classic transaction.
- Self-checking testbench: [`tests/fixtures/panolab_csr_demo_tb.v`](../tests/fixtures/panolab_csr_demo_tb.v) — 44 assertions.
- Regression runner: [`tests/test_panolab_csr_demo.py`](../tests/test_panolab_csr_demo.py) — Icarus simulation, deliberately mutated low-byte enable expected to FAIL, Yosys process/structural checks.
- Acceptance requires a repeatable simulator PASS, injected fault FAIL, Yosys PASS, appropriate source tests, a single reviewed `development` commit, and unchanged `main`. No ISE licensing or physical board contact is needed.

For implementation instructions see [development workflow](../docs/DEVELOPMENT.md) and [operation](../docs/GETTING_STARTED.md).
