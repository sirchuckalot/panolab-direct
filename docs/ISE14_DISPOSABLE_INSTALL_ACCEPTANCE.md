# Disposable ISE 14.7 unattended installation acceptance

**Status (2026-11-24): PASSED TWICE on the actual owner laptop.**
Two fully isolated disposable ISE 14.7 System Edition installations
completed via the **normal authenticated PanoLab manager → rootless
Docker broker** path, with no `trusted-maintenance` test execution.
Each used brand-new installation/work volumes, accepted the exact
owner-authorized vendor terms without a prompt, passed licensed
XST, NGDBuild, MAP, PAR, TRACE and BitGen, generated a nonempty
bitstream and timing report, and disposed of all eight test resources.
Read-only independent inspection confirmed both cleanup sets and the
unchanged permanent license, install-state and vendor settings hashes.

## Real vendor acceptance evidence

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

The temporary maintenance sidecar was used only to **inspect source,
review-build a candidate broker image, reload the updated normal broker
code, and independently read-only inspect vendor progress and final
preservation**. It did not create, install, build, verify or remove
acceptance resources. No permanent worker, stopped on-demand setup,
license or vendor installation was replaced.

## Operation and trust boundary

The normal connector's existing `dev_exec` operation accepts the
`@ise-e2e` compatibility prefix, which the **normal broker** intercepts.
No shell is executed in the dev container. Only these fixed operations exist:

- `@ise-e2e preflight`: verifies rootless Docker, stopped normal setup,
  healthy persistent ISE worker, checkpointed vendor images and exact
  read-only private source mounts
- `@ise-e2e start`: creates a single background acceptance run in the
  normal broker with a random scoped 12-hex-digit run ID; overlapping starts
  are rejected
- `@ise-e2e status <run_id>`: returns the run state and phase
- `@ise-e2e result <run_id>`: after completion, returns only bounded
  build/checksum metadata or a sanitized failure category

No `@maintenance` operation, general-purpose Docker shell, host-root
engine, programming interface, or arbitrary caller-supplied paths are used
in the acceptance controller. Temporary maintenance is allowed to inspect
and repair the surrounding implementation, but **executing any acceptance
step through it or modifying disposable resources mid-run invalidates that
run**. Read-only inspection does not make the normal test dependent on
temporary maintenance.

The Python controller resides in `docker/control/ise_acceptance.py`.
Its unit contract is `docker/control/test_ise_acceptance.py`, which is
executed during broker image builds. Runtime output is stored in the
private Docker `management-rpc` volume under `/rpc/ise-e2e/`, not Git.

## Unattended vendor license terms

The user authorized unattended acceptance for the known Xilinx ISE
Design Suite **14.7 System Edition** archive. The corresponding reviewed
acceptance manifest is `docker/ise14/acceptance-policy.json`, pinned to
exactly:

- SHA-256:
  `cee0b046c1bbcfafcae59a96c7596c55c5477628c39bafefff8992cb8d33adaa`
- Expected size: 6,538,618,880 bytes
- Package: Xilinx ISE Design Suite 14.7 System Edition
- `unattended_terms_acceptance: true` for this exact package only

The controller validates the manifest and then asks the *fresh disposable
setup service* to verify the **entire** mounted vendor archive SHA-256.
Only then does it send the existing, narrowly scoped
`INSTALL_ISE_14_7_IN_PANOLAB_ONLY` confirmation as part of the ordinary
setup MCP `ise_install_start` request. Native `batchxsetup` already runs
using the vendor's supported batch configuration and an automatic response
stream. There is no interactive prompt. Any different media or changed
terms require a new explicit owner authorization/policy review; neither a
fabricated entitlement nor license-file editing is part of this procedure.

## Complete disposable data flow

1. Verify the original licensed environment is healthy but **do not start,
   stop, mount for writing, or reinstall** its persistent containers.
2. Create only run-ID-prefixed Docker **named volumes**, with
   `panolab.managed=true` and `panolab.ise.acceptance=<id>` labels:
   `install`, `work`, `projects`, `results`, `secrets`.
3. Start a separate CentOS ISE **setup** image, network `none`,
   read-only root filesystem and dropped capabilities. Original owner
   media, license, bearer and batch configuration are mounted read-only.
   Fresh `/opt/Xilinx` and `/work` are empty named volumes.
4. Inspect and SHA-verify the archived media, issue the exact approved
   unattended installation request, and poll the installation state for
   a real `succeeded` response (bounded by the installer contract).
5. Stage the fixed, unconstrained source fixture from
   `acceptance_build.json` and `acceptance_design.v` into the separate
   `projects` volume, and generate an independent worker token into
   the private `secrets` volume.
6. Launch a **different, disposable** ISE worker with the *freshly installed*
   vendor volume mounted read-only; run on a uniquely named **Docker-internal**
   network with the existing node-locked virtual Ethernet identity.
   The original license is read-only. No external ports or NIC changes.
7. Submit an actual six-stage
   XST → NGDBuild → MAP → PAR → TRACE → BitGen build. Verify job state,
   exit 0, nonempty stage logs, timing report and bitstream, and record
   each artifact's SHA-256 and size. The fixture is deliberately
   **not a Pano G2 board-ready image**, and no FPGA programming is permitted.
8. Delete only matching **labeled** disposable worker/setup containers,
   internal test network and five test volumes. Verify their absence.
   Persist a summarized acceptance record and hashes separately from
   disposable volumes. The original running ISE worker, stopped
   on-demand setup, node-locked network, previous job history, and
   rollback containers are untouched.

The installer, worker, and generated bitstream are all test-private.
Never run this workflow against the installed `/opt/Xilinx` source or
the persistent project's results directory.

## Acceptance criteria and remaining gaps

**Pass** requires all of:
- No user action after the approved media/terms policy is established
- Normal manager/broker interface controls the entire test
- Fresh private installation volume was initially empty and reached
  `succeeded`
- Genuine licensed implementation completed all six vendor stages
- Real bitstream and timing report have nonzero sizes and valid hashes
- All eight test resources were disposed, and the private result record
  reports `passed` and `disposed: true`
- Persistent licensed lab and stopped normal setup remain unchanged

**Fail/incomplete** if the test needs the temporary maintenance interface
for execution, the install is skipped using the old vendor volume,
a step is simulated, any artifact is missing, or disposable resources
remain after cleanup.

Separate qualifications still outstanding: arbitrary first-time
provisioning when no setup image exists, complete clean-host appliance
installation, laptop cold-reboot recovery, and Pano G2 board pin/constraint
acceptance. The acceptance preflight currently requires the **existing
stopped PanoLab setup container to discover approved private media mounts**
and the preserved **known-good setup and worker checkpoint image tags**.
These are normal Docker images (not the temporary maintenance container),
but their availability on a completely new laptop is not yet established.
The next installer/bootstrap revision should build and verify those
images through the normal launcher and derive media paths from a typed,
reviewed private configuration rather than a prior container snapshot.
Success here specifically qualifies the disposable vendor-install
end-to-end path on the already-provisioned rootless laptop.
