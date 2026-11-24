# Clean-laptop / unprovisioned-host acceptance — admission and blocker evidence

**Date:** 2026-11-24
**Status:** **BLOCKED for a truly unprovisioned host.** An isolated,
read-only admission simulation passed its expected **fail-closed** behavior.
A new Linux VM/laptop has **not** been booted or provisioned by this test.

## Goal and safety boundary

Prove the complete chain **on an independent, genuinely clean Linux x86_64
host**: obtain approved host prerequisites; create a normal-user rootless
Docker Engine with delegated cgroups; clone the approved PanoLab source;
provision private tunnel/MCP/Codex credentials, vendor media and licensing
through owner-authorized paths; build images from source; bring up the
normal services; use the normal MCP connection to install ISE unattended
into fresh private storage, run a real six-stage bitstream compilation,
validate hashes and teardown; reboot and verify recovery.

**Do not wipe, uninstall Docker, replace system packages, move private media,
or erase containers on the working laptop to simulate a clean machine.**
Do not run acceptance steps through the temporary `@maintenance` sidecar.

## What was actually tested

The ordinary PanoLab **development container**, without a Docker socket,
was used to execute `host/fresh-host-audit.py` against a synthetic empty
checkout and home with no user runtime session. The audit correctly returned
`FRESH_HOST_PREREQUISITES=BLOCKED` (exit code `10`), listing 20 missing
conditions in this deliberately constrained fixture. These are fixture
conditions, **not a report of missing dependencies on the owner's laptop**.
The fixture did **not** install software, start services, read credential
values, or modify the working host.

Eight source/behavioral tests passed:
- Empty checkout/home cannot be reported as ready.
- Private credentials are checked by metadata, never printed.
- Symlinked credentials and ambiguous ISE media are rejected.
- Missing requirements produce a distinct blocked result.
- The **top-level** `panolab-install.sh --fresh-host-check` reaches the
  prerequisite inventory from a synthetic fresh checkout, without
  requiring Docker first or modifying fixture files.
- Normal installer Compose source keeps setup optional; source/audit
  syntax and no-host-mutation checks pass.

A **read-only Compose source inspection** through temporary maintenance
confirmed that, in the actual existing rootless configuration, the default
services are broker, manager, repo-git and tunnel; enabling the
`ise-setup` profile adds only setup, with `restart: no`. Neither manager
nor tunnel depends on setup. **Temporary maintenance was not used to run
the clean-home admission test or to deploy the appliance**; its only
participation was read-only configuration inspection.

## Installer corrections

- `panolab-install.sh --fresh-host-check` now invokes the new
  read-only `host/fresh-host-audit.py` **before** Docker or private-file
  prerequisites are enforced. It reports individual missing facilities
  and returns code `10` for an incomplete machine. The `READY` result,
  if produced on a suitable host, is **only prerequisite readiness**.
- `host/rootless-install.sh` validates optional setup's Compose config
  using `--profile ise-setup`, fixing the inconsistent post-on-demand
  validation that previously expected setup in default services.
- The ordinary installer builds the optional setup image when missing,
  but no longer automatically starts the setup container. A normal
  deployment starts broker, repo-git and manager, followed by tunnel.
  This change has passed source/unit and read-only Compose validation,
  **not a clean new-host deployment test**.

## Outstanding blockers for true fresh-host acceptance

| Stage | Why it is not yet qualified |
| --- | --- |
| Independent clean OS | The normal development container has no KVM/QEMU and cannot create nested user namespaces; it is not a substitute for a new VM or laptop |
| Host dependencies | The installer still assumes Git/Bash/Python, Docker CLI/Compose/Buildx, user namespaces, subordinate UID/GID mapping, user systemd and a rootless daemon/runtime already provisioned |
| Privileged OS bootstrap | Installing missing `uidmap`/user-session/kernel prerequisites may require one-time OS administrator action or a preconfigured base image; a rootless container cannot safely make those changes to the host |
| Private inputs | A new host needs an owner-controlled tunnel identity/MCP bearer, approved Xilinx media and license, and authenticated Codex state. None can be invented or committed to Git |
| Image/bootstrap dependency | The current normal `@ise-e2e` test assumes a provisioned manager/broker, existing stopped setup container for private mount discovery, existing persistent ISE worker and known-good checkpoint image tags |
| Persistent ISE worker | The general rootless launcher builds the optional setup image but does **not yet** commission the persistent licensed ISE worker from scratch through the normal path |
| Network licensing | A separate host must legitimately satisfy the license's node-locked entitlement. Two vendor installations passed on the original licensed laptop; that does not prove portability |
| End-to-end recovery | Fresh remote tunnel/MCP connection, local Codex authentication, complete install, reboot, rollback and cleanup still need observation on the separate host |

The [disposable ISE vendor test](ISE14_DISPOSABLE_INSTALL_ACCEPTANCE.md)
has already passed twice **on the provisioned licensed laptop**, including
fresh vendor installation and a real bitstream. That is a separate,
stronger vendor-only test than this fresh-home admission simulation.
Neither result is evidence of a complete unprovisioned-machine install.

## Acceptance sequence for the real clean-host gate

1. Launch an **independent disposable Linux x86_64 VM/host** with a
   known OS image and confirmed owner approval for first-time OS setup;
   it must not share the working laptop's Docker images, volumes,
   Git checkout or secret directories.
2. Record the clean baseline, rootless prerequisites, image/cache
   state and absence of PanoLab services. Run
   `bash panolab-install.sh --fresh-host-check` and record all blockers.
3. Establish the host runtime explicitly and safely. If system packages,
   uidmap or kernel changes are required, handle them through a reviewed
   OS provisioning step, never through the temporary PanoLab sidecar.
4. Provide private owner-approved credentials and media through
   a separate encrypted input channel or already-authorized local
   facility. Validate exact vendor SHA-256 and licensing scope; do not
   send credentials/media to a public CI runner.
5. Run the **normal one-command launcher** and make it build the manager,
   broker, repo gateway, modern tools, optional setup and licensed
   worker from reviewed source. Validate typed lifecycle, authenticated
   remote MCP, resource limits and setup-off-by-default behavior.
6. Run `@ise-e2e start` from the **normal MCP route**, wait for
   `passed` + `disposed:true`, verify all six vendor stages, artifact
   hashes and strict cleanup.
7. Exercise a persistent installed worker, reboot the independent host
   and confirm automatic return of the intended six services. Keep
   temporary maintenance absent for the entire acceptance execution.
8. Preserve the evidence/known-good versions and destroy **only the
   independent clean-host test environment** after qualification.

**Current determination:** Real clean-laptop end-to-end acceptance
remains **PENDING**, not PASSED. The working owner laptop and its
seven active engineering services were preserved.
