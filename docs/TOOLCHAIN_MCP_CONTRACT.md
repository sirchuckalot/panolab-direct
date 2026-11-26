# Canonical vendor toolchain MCP contract

Every FPGA vendor build appliance is a **persistent runtime container**
with a specified operating system, libraries, separately installed
licensed vendor toolchain and embedded MCP server. Pin exact versions
before reproducible build claims. The MCP server runs **inside the same
container as the build tools**; no MCP sidecar, SSH build controller,
agent shell or second runtime worker is required. A multi-stage
image build used to compile the MCP binary is allowed.

All vendor workers implement exactly these **five mandatory MCP tools**:

| Tool | Purpose |
| --- | --- |
| `toolchain_info` | Report identity, installed version, part support, license availability, image/runtime identity and capabilities |
| `build_start` | Validate a declared project/target/profile and enqueue one bounded build; return a stable job ID |
| `build_status` | Return state, progress/stages and bounded metadata for a job |
| `build_result` | Return bounded logs, stage outcomes, artifact names/sizes/hashes and optionally artifact byte chunks |
| `build_cancel` | Request cancellation of a specific running job; preserve recorded evidence |

The standard build profile `ise14-implementation` executes real
ISE stages as supported by the installed owner-supplied license and
project (for example XST, NGDBuild, MAP, PAR, TRACE, BitGen). A source
fixture is a **client-selected project**, not an embedded appliance
smoke test. External clients decide pass/fail and retrieve verifiable
artifacts. The worker remains running across multiple jobs and
retains bounded durable job status; do not recreate it per build.

A successful `build_result` does **not** authorize programming any
FPGA. Programming/JTAG/SPI/flash operations require an independent
explicit approval boundary. Vendor MAC/HOSTID requirements must be
verified and licensing respected.

Workers must reject unchecked shell commands, traversal paths,
unsafe mounts, cross-project artifact access and unrelated host
operations. Keep build inputs read-only, outputs and logs isolated
by job, and published diagnostics free of private tokens or license
material. Do not add vendor-specific agent-facing tools without
owner-approved interface revision.

The ISE 14.7 worker implementation lives in `docker/ise14/mcp/`.
**Vendor implementation acceptance for generic unconstrained XC6SLX150
smoke designs was achieved on 2026-11-24:** two real runs completed all
six stages and generated independently hashed nonempty bitstreams
([evidence](EVIDENCE.md#licensed-ise-bring-up)).
The node-locked license is satisfied by an explicitly managed,
Docker-**internal** virtual Ethernet identity without publishing the
private host ID. This does **not** qualify any board-specific pinout,
timing budget or physical programming.

The manager exposes additional *adapter* operations
`ise_project_stage`, `ise_worker_diagnostics` and named wrappers for
the five worker operations. Those adapter operations are not extra
mandatory tools inside the vendor worker. During development, the
owner-approved `@ise14` compatibility route and temporary maintenance
bridge provide remote control; see
[temporary maintenance controls](ARCHITECTURE.md#temporary-maintenance-and-retirement).

The ISE worker reports the pinned installation version and license file
availability separately from execution evidence. A readable regular license
file starts as `not_yet_validated`. The worker reports `validated` with
`license_validation_job_id` only after a persisted successful six-stage build
with a nonempty bitstream and matching private license identity before and
after execution. Evidence belongs to the current worker process and clears
when the observed identity changes or becomes unavailable. Failed builds
leave existing proof for the same observed identity intact.
`toolchain_info` invokes no vendor stages and discloses no license identity.

The named `ise_build_result` adapter accepts `ID` and optional
`Artifact: "design.twr"`. The compatibility request is
`["@ise14", "build_result", "<job-id>", "design.twr"]`. Omitting the
selector returns the usual metadata and diagnostic categories without
reading artifact pages. The remote adapter accepts only the timing report
selector. Direct worker clients retain the chunk interface. For
`design.twr` the worker sends pages of at most 8,192 raw bytes. In this
interface an omitted zero offset means zero and an omitted EOF means false.

The broker accepts a terminal job, verifies consecutive pages against the
report's exact metadata size and SHA-256, and bounds the report at 1 MiB
and the operation at 110 seconds. It returns the verified artifact metadata
and bounded TRACE facts, including coverage and reported constraint targets,
setup and hold errors, analyzed paths and reported slack when available.
Constraint indices follow report order. The result uses `constrained`,
`unconstrained`, `unknown` or `incomplete` for recognized evidence, and
rejects unreadable or inconsistent results. The broker exposes a report's
constraint conclusion only with corroborating coverage and constraint
details. These facts describe the supplied report's coverage. Raw timing
paths, clock names, vendor logs and bitstream bytes stay private to the
worker and broker boundary.

**Disposable installation acceptance is a separate normal control-plane
workflow, not a sixth mandatory vendor worker tool.** The authenticated
`@ise-e2e` broker adapter creates a disposable setup and vendor worker
using the same canonical MCP contracts, verifies the exact
[owner-authorized vendor archive policy](../docker/ise14/acceptance-policy.json),
performs the genuine six-stage pipeline, and then removes only its
labeled test resources. Successful artifacts are recorded by SHA-256
in the normal broker's private state volume. The existing persistent
worker is not modified or reinstalled. See
[the full acceptance contract](GETTING_STARTED.md#disposable-unattended-ise-147-acceptance).
This framework must remain independent of the temporary
`trusted-maintenance` route.

[Architecture and acceptance gates](ARCHITECTURE.md) · [Security](ARCHITECTURE.md#security-and-trust-boundaries)
