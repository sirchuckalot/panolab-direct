# ISE 14.7 remote bring-up — verified engineering evidence (2026-11-24)

## Acceptance summary

**REAL LICENSED VENDOR IMPLEMENTATION: PASS.** The PanoLab rootless laptop
successfully ran Xilinx ISE 14.7 through XST, NGDBuild, MAP, PAR, TRACE
and BitGen on a generic Spartan-6 XC6SLX150 FPGA design.

- Successful job: `1795535626519203841`
- Project/source revision: `ise14_smoke-7b13ec819895`
- Build state: `succeeded`, exit code `0`
- Generated `design.bit`: **4,220,305 bytes**
- SHA-256: `2d80c633d3e4915a65308fd58ff39828b8d3d4dd475ee244a2d2fef2aa11f1f9`
- All six separate vendor stage logs exist. `design.twr` also exists.
- **Second independently successful licensed build:** job `1795535788871331709`
  from the distinct first source revision `ise14_smoke-c784a423993f`.
  All six ISE stages passed, exit `0`, and a separate nonempty
  4,220,305-byte `design.bit` was generated. SHA-256:
  `da710d59aa60d5e9806bcc83e2ce82c9d2d38f549090ecd13f996ead7bce8bac`.
  The two source revisions and bitstream SHA-256 values are different;
  **both builds succeeded without another worker image rebuild or restart**.
- This is a generic, deliberately **unconstrained** toolchain smoke design,
  **NOT** a verified Pano G2 Rev B pinout or hardware-programming image.

The job record, artifact size, hash, security/worker state, and separate
stage-log presence were independently rechecked from the mounted, owner-private
results directory as well as through the authenticated remote MCP response.
No hardware FPGA programming, JTAG, SPI flash, or bitstream loading was
performed. The private vendor license contents and MAC are not published.

## The licensing regression and repair

The existing Xilinx license is **node-locked to an Ethernet MAC/HOSTID**.
An earlier MAP attempt failed with FlexNet `-9,57` and `-5,357`, including
a wrong-host-ID message. Our previous diagnosis that a new or rehosted license
was required was **premature and incorrect**.

**Root cause:** The PanoLab ISE worker creation script forced
`--network none`. Docker therefore supplied no Ethernet interface bearing
the node-locked identity, even though the toolchain and license file were
present. The current and earlier PanoLab worker containers both used this
setting; neither was a snapshot of the user's previously working ISE
network configuration. A mismatch between the license's virtual Ethernet
identity and the laptop's physical NICs was not proof of an invalid
entitlement.

**Controlled proof:** A disposable, internal-only rootless Docker network
presented the license's existing Ethernet identity to an isolated
implementation container. A copy of the prior job's `design.ngd`/NGC
inputs was run through the genuine licensed MAP executable. **MAP passed**,
created `design_map.ncd`, and returned exit `0`. That disposable network
was removed afterward. Neither the license nor the persistent worker was
modified by the probe.

**Persistent repair:** The worker was then recreated with the isolated
Docker internal network `panolab-direct-ise14-license-internal`, with a
stable virtual interface matching the license's recorded node identity.
Rootless Docker, a read-only container root filesystem, dropped Linux
capabilities, source/license read-only mounts, the existing private output
mount, and no published vendor ports remain in force. Independent checks
confirmed `Internal=true`, a single network attachment, matching virtual
identity, the correct private license mount, and the unchanged job history.
The old worker is retained as a stopped rollback container
`panolab-direct-ise14-worker-backup-network-none-20261124` (and an older
absolute-binary-change backup is retained).

No physical laptop MAC was changed, no license text was edited, and the
vendor's genuine licensing check was allowed to run and succeeded.

## Additional remote-development repairs

- **Authenticated bridge:** The owner-approved temporary
  `trusted-maintenance` path and named ISE build operations were deployed.
  The remote rootless Docker command, toolchain query, staging, build
  submission, status and result operations all function.
- **MCP argument schema:** The Go worker requires lowercase
  `profile`, `project`, `job_id`, `artifact`, and `offset`. The Python
  adapter now emits those fields, rather than Go field names beginning with
  uppercase letters.
- **Absolute vendor executables:** The Go worker now launches only pinned
  `/opt/Xilinx/14.7/ISE_DS/ISE/bin/lin64/{xst,ngdbuild,map,par,trce,bitgen}`
  paths. The original build failed at XST with exit 127 despite the binary
  existing; a rebuilt worker image with the corrected paths passed tests
  and a live XST execution check.
- **Live source mount bug:** Bind-mounting the three Python files individually
  kept stale Docker bind inodes after atomic remote repository writes. The
  broker now executes `broker.py` from a single read-only
  `docker/control/` **directory** bind. Recreating only the broker and
  checking authenticated remote MCP access succeeded. A subsequent independent
  SHA-256 comparison of host source and the broker's mounted Python module
  returned an exact match, demonstrating that current source is visible.
- **Source revision staging:** Two distinct immutable smoke projects exist:
  `ise14_smoke-c784a423993f`, SHA-256
  `c784a423993f8a9d9ea69338ccc8c60f97c92b932bdaf4e96aec18b57e8b237b`,
  and `ise14_smoke-7b13ec819895`, SHA-256
  `7b13ec8198956c61a8551e3c205f35372aa5218af0d01546d640250124a285e5`.
  The second version changes one counter-bit output selection, and the first
  remains unchanged. Both independently completed the real six-stage
  ISE pipeline with distinct output bitstream hashes and **no worker image
  rebuild or restart between jobs**.

### Chronology of failed jobs (preserved)

| Job | Outcome | Cause |
| --- | --- | --- |
| `1795527453486516942` | failed, exit 127 | Shell could not execute the XST command by name |
| `1795528026936978616` | failed, exit 2 | XST/NGDBuild succeeded; MAP license HOSTID check failed with `--network none` |
| `1795535626519203841` | **succeeded, exit 0** | Corrected vendor paths, MCP arguments and isolated licensed network identity |
| `1795535788871331709` | **succeeded, exit 0** | Second immutable RTL revision, same isolated licensed worker; distinct genuine bitstream |

## Current limitations / future acceptance

1. The bitstream is not qualified for the Pano G2 board: a documented board
   constraints/pinout review and real target-specific build remain necessary.
2. FPGA programming is a separate owner-approval decision; **none is authorized
   or claimed** by this smoke-test success.
3. The temporary owner-trusted maintenance bridge has broad access to the
   owner's *rootless* Docker Engine. Keep it explicitly temporary, record
   the rollback procedure and replace it with a bounded, independently
   recoverable manager before calling the appliance production-hardened.
4. Review additional remote recovery cases (active job cancellation, process
   restarts, stage failures, log redaction and cross-version compatibility).
5. These source changes currently reside in the owner's local
   `development` checkout and have not been committed or pushed as part
   of this bring-up.

Related system rationale:
[remote-first architecture](REMOTE_ITERATION_ARCHITECTURE.md),
[worker MCP contract](TOOLCHAIN_MCP_CONTRACT.md),
[security boundaries](SECURITY.md).
