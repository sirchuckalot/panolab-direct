# PanoLab Rescue v1 — Cross-Platform Boot, Update, and Recovery Standard

| Document control | Value |
| --- | --- |
| Identifier | `PLR-ARCH-001` |
| Version | **1.0.0** — architecture and interoperability contract |
| Date | 2026-11-23 |
| Status | **Design baseline for development; not implemented or hardware-qualified** |
| Scope | Embedded FPGA board boot, update, rescue, identity, and qualification |
| First reference platform | Pano Logic G2 Rev B, Spartan-6 XC6SLX150-2-FGG484 |
| Repository policy | Develop on `development`; accepted `main` stays unchanged until expressly authorized |
| Authority | PanoLab Direct project engineering standard |

## 1. Executive decision

**PanoLab Rescue v1 SHALL be a LiteX-based, independently bootable rescue environment with two independently bootable FPGA application slots (A/B), a separately persisted device identity, verified trial updates, and recovery through a board-proven physical reset/power-cycle path.** Applications MAY be CPU-less. The rescue environment MAY contain a soft CPU and bare-metal management firmware; Linux is **not** required.

A *common recovery implementation* means common sources, protocol, manifest, state model, and user experience. **It does not mean one universal FPGA bitstream binary**: an FPGA configuration image is built for a specific compatible board/FPGA target, toolchain, pinout, and flash boot arrangement. A BSP SHALL declare its compatibility group.

The original Pano factory firmware is a **one-time provisioning entry point**, not a permanent product dependency. The migration MAY extract only relevant identity bytes/records, provided those are validated and kept safe before erasure. A full factory SPI image is useful for archaeology but **not a product prerequisite**. The integrity of the boot path and per-device identity remains mandatory.

**Normative terms.** `MUST`, `MUST NOT`, `SHOULD`, `SHOULD NOT`, and `MAY` express requirement levels for a conforming implementation. Requirements described as `PENDING / PROOF REQUIRED` are binding qualification gates, not claims of existing functionality.

### 1.1 Goals

- Familiar embedded update semantics: inactive-slot update, validate, trial, health-confirm, revert, rescue.
- A stable API and update package model across FPGA boards; board-specific primitives behind a versioned BSP.
- Recover from an interrupted application update and a known-bad trial without a JTAG cable when the validated board recovery path remains intact.
- Separate manufacturing identity from recovery software and applications; use the board's real unique MAC, not a hard-coded shared address.
- Host-assisted provisioning over a local Ethernet network with repeatable, recorded, authorized operations.
- Let developers build ordinary LiteX/Wishbone, LiteEth/Etherbone, or custom RTL applications without importing a full operating system or the rescue firmware.

### 1.2 Non-goals and limits

- PanoLab is **not** a complete implementation of MCUboot, RAUC, Mender, SWUpdate, or an IETF SUIT conformant updater merely by adopting their patterns.
- v1 does **not** guarantee security against invasive physical attackers or firmware replacement on boards lacking an immutable hardware root of trust.
- v1 does **not** promise recovery from damaged boot ROM/SPI pins, electrically failed flash, destroyed rescue bitstreams, or misconfigured boot-strap hardware.
- v1 does **not** claim automatic reboot from an arbitrarily hung, successfully configured FPGA application unless the BSP independently proves a reset/watchdog path. A reboot or power-cycle can be required.
- No FPGA programming, factory overwrite, or independent physical-device access is authorized by this specification. Such operations require separate per-device approval and a validated recovery plan.

## 2. Logical architecture and interfaces

```text
User / IDE / Agent / CLI
    |
    | discovery (DNS-SD/mDNS), authenticated management API
    v
PanoLab host-side tooling (optional gateway/management proxy)
    |
    | network; each mutating request authorized end-to-end
    v
+-------------- FPGA board / SPI NOR -------------------+
| FPGA boots PanoLab Rescue first on cold boot/reset     |
|  +-------------------------------------------------+  |
|  | LiteX Rescue bitstream + CPU / bare-metal FW    |  |
|  | identity / boot-policy / update / network / SPI |  |
|  | validation / BSP boot & ICAP controls           |  |
|  +---------------------+---------------------------+  |
|                        | ICAP / device reload         |
|               +--------+---------+                    |
|               |                  |                    |
|        App A (verified)   App B (verified/trial)        |
|               |                  |                    |
|               +-- optional standard return-to-rescue --+
|                                                        |
|  Boot state journal | device identity | metadata       |
|  Board-specific boot header / reserved recovery        |
+--------------------------------------------------------+
```

**Hard boundary:** the FPGA fabric is wholly reconfigured when switching to an application. The rescue CPU and its Ethernet service stop running. **Rescue and application do not execute concurrently.** Any health confirmation, application management shim, or return-to-rescue signal MUST account for this; a resident supervisor requires separate hardware not assumed on G2.

### 2.1 Standard conceptual components

| Component | Mandatory responsibility |
| --- | --- |
| Rescue | First boot path; authenticate management; verify candidate; manage image slots; journal boot state; boot/recover |
| Application A and B | Independently bootable complete FPGA configurations; no assumption that both run simultaneously |
| Identity | Per-unit serial, MAC, board/revision and original raw data with integrity; not overwritten by routine updates |
| Boot state | Durable last-known-good, trial candidate, attempt policy, update generation and recovery reason |
| BSP | Flash geometry/partition map, clock/PHY, FPGA reconfiguration, hard recovery button/reset, hardware identification |
| Host tooling | Discovery, bundle preparation, authenticated updates, health observation, audit, optional pairing |

## 3. Flash and partition contract

### 3.1 Mandatory logical regions

| Region | Role | Routine write permission |
| --- | --- | --- |
| `BOOT` | FPGA-specific configuration header, boot selector, recovery fallback metadata | **No**; separately approved maintenance only |
| `RESCUE` | Independently bootable, proven LiteX recovery bitstream and firmware | **No**; separately approved rescue-update procedure |
| `APP_A` | Complete application bitstream A | Only when inactive and not designated last-known-good |
| `APP_B` | Complete application bitstream B | Only when inactive and not designated last-known-good |
| `IDENTITY` | Serial, MAC, board revision, provisioning identity and preserved raw factory records | Provisioning only; subsequently protected |
| `STATE_0`, `STATE_1` | Two physically separate redundant boot-state journal erase units | Restricted rescue metadata operations |
| `RESERVED` | Board-dependent spare/erase-alignment, optional spare metadata, safe expansion | No routine writes unless declared |

A board's **flash map is defined in its BSP**, not in an application binary or generic high-level CLI. The map MUST include start address, byte length, erase geometry, write granularity, alignment, permissions, and excluded/protected ranges. Regions MUST NOT overlap. Every region subject to an independent erase MUST begin/end at erase-unit boundaries unless the BSP proves another safe atomic method. In particular, an identity record MUST NOT share an erase unit with ordinary application data or a frequently updated state journal.

All image sizes MUST be tested using **actual generated FPGA configuration images** and any required headers, padding, authentication structures and erase alignment. An insufficient-capacity board MUST NOT be advertised as fully A/B-conformant. The v1 standard deliberately does **not** assign universal byte offsets or promise that every supported FPGA board will fit the layout.

The provisioning tool MAY assemble one full-flash binary offline as a reproducible manufacturing artifact, but **MUST program and verify in a power-loss-safe order**. A whole-chip `erase-all`/single uninterrupted stream is forbidden for network conversion while the current boot path is needed for recovery.

### 3.2 Protected identity

- Required logical fields: `identity_format_version`, stable `device_id`, `board_id`, `board_revision`, `fpga_part`, unique `mac_address` (if Ethernet-capable), optional `serial_number`, `source_provenance`, `integrity_check`.
- During migration, save the **raw, device-specific source record** to private host storage before editing it; record extraction tool/version, source address, size, board observations and digest. A whole-firmware backup is optional.
- Validate MAC format and uniqueness against physical label, discovery and repeated reads when available. If values conflict, **stop provisioning**; do not invent a replacement MAC silently.
- Applications and rescue SHALL read identity through a versioned logical API; avoid embedding per-unit MAC/serial values in common bitstreams.
- Identity relocation is allowed only after the target representation and boot/PHY behavior have been tested. Identity records MUST NOT contain private signing keys, login tokens or credentials copied from another board.
- If the original source has unknown factory fields, preserve the raw bytes even when only a subset is decoded.

### 3.3 Boot-state journal and power-fail safety

`STATE_0` and `STATE_1` use independent erase units and generation-numbered records. A v1 record at minimum contains: magic, format version, monotonically increasing record `sequence` (not a security anti-rollback counter), `confirmed_slot` (`A`, `B` or `none`), `pending_slot` (`A`, `B` or `none`), `trial_attempts_remaining`, `state` (`stable`, `trial_pending`, `trial_running`, `rollback_required`, `recovery_only`), `last_boot_reason`, digest of the selected application manifest, and a checksum/CRC. An authenticated record tag is RECOMMENDED if the board can protect its key material.

A journal write MUST be append/commit safe: program and verify a new self-consistent record, then consider it authoritative based on validity/generation; never erase the *only* valid record first. Recovering from interrupted metadata writes MUST deterministically choose the latest valid record or fail into Rescue; arbitrary recovery guesses are forbidden. Simulate torn pages, partial writes and power loss during erase/program before qualifying a BSP.

## 4. Image packaging and manifest

### 4.1 Required model

The logical artifact is a **board-specific raw FPGA image plus a versioned manifest** (and optional development convenience packaging). v1's interoperable machine-readable manifest profile SHALL use deterministic CBOR (RFC 8949) and COSE_Sign1 (RFC 9052) for signed production packages. The host CLI MAY display/export an equivalent JSON representation for debugging, but a JSON rendering MUST NOT be assumed to be identical to the signed CBOR bytes. This is a **PanoLab profile informed by SUIT's architecture and information model**; formal IETF SUIT manifest conformance is not claimed by v1.

Required manifest fields:

| Key | Requirement |
| --- | --- |
| `manifest_version` | Numeric profile version, currently `1` |
| `image_id`, `image_version` | Unique immutable artifact ID and project-defined version |
| `image_role` | `application` or special separately approved `rescue` |
| `supported_targets` | Exact board family/revision compatibility group, FPGA part, and BSP profile version/range |
| `image_length` | Exact raw image size in bytes |
| `image_sha256` | SHA-256 of the exact written raw image bytes, before slot padding |
| `required_rescue_api` | Minimum/compatible rescue protocol version |
| `config_format` | FPGA vendor/family configuration format and encoding |
| `required_features` | Needed BSP capabilities (e.g. Ethernet PHY, ICAP return support) |
| `build_provenance` | Source revision, dependency pins, toolchain version, deterministic build identifier when available |
| `signing_key_id`, `signature` | Signature metadata and COSE signature envelope for production profile |

The manifest MUST NOT encode absolute flash addresses as authoritative placement decisions. Rescue uses the BSP partition map and bounds-checks all writes. Target compatibility compares the actual detected FPGA/board identity, not merely a user-selected name. Unknown mandatory feature IDs, format versions, unsupported FPGA IDs, invalid signatures, incorrect lengths, or mismatched hashes MUST cause rejection before activation.

**Illustrative logical form (NOT the on-wire signed encoding):**

```json
{
  "manifest_version": 1,
  "image_id": "example-csr-v1",
  "image_version": "0.1.0",
  "image_role": "application",
  "supported_targets": [{
    "board_id": "pano-g2",
    "board_revision": "b",
    "fpga_part": "xc6slx150-2-fgg484",
    "bsp_profile": "pano-g2-revb/1"
  }],
  "image_length": 4210000,
  "image_sha256": "<64 lowercase hexadecimal digest characters>",
  "required_rescue_api": "1.0",
  "config_format": "xilinx-spartan6-spi",
  "required_features": ["icap-return-v1"],
  "build_provenance": {
    "git_commit": "<40-hex source SHA>",
    "toolchain": "xilinx-ise-14.7"
  },
  "signing_key_id": "<provisioned release key ID>"
}
```

The example image size is illustrative and MUST NOT be used to compute real Rev B partition boundaries. The production manifest is signed using the canonical CBOR representation; the signature is not represented by the human JSON above.

### 4.2 Verification levels

1. **Transport integrity:** detect packet loss and truncated uploads; resumability MUST NOT change accepted content.
2. **Image integrity:** compare on-flash readback to manifest digest over actual image bytes. Rescued image MUST be reverified as required by boot policy.
3. **Authorization/authenticity:** require a trusted release/developer signing identity for production mode. Development signing keys MAY be separately enrolled after owner authorization.
4. **Target authorization:** board compatibility and region permissions are checked *again* inside Rescue even if host tooling checked them.

SHA-256 alone proves integrity, **not** authorization. A secret or public key stored in rewritable SPI is not an immutable root of trust. v1 SHALL clearly disclose the physical-tamper limitations of each BSP.

## 5. Boot policy and state machine

### 5.1 Required startup invariant

On a normal cold boot, hard reset, and validated recovery reset, **Rescue MUST be the first configured, independently usable environment**. Rescue inspects the journal and optionally the recovery button before deciding which application to load. Loading the application replaces the rescue FPGA configuration. The BSP MUST demonstrate this exact hardware behavior; relying on an application to be cooperative is **not** sufficient to claim recovery support.

```text
RESET / POWER-ON
       |
       v
   RESCUE_BOOT
       |
       +-- identity/boot data invalid --> RECOVERY_ONLY
       |
       +-- recovery button asserted --> RECOVERY_ONLY
       |
       +-- no valid app --> RESCUE_IDLE
       |
       +-- unconfirmed prior trial --> ROLLBACK_TO_CONFIRMED
       |
       +-- confirmed app exists --> VERIFY_CONFIRMED --> BOOT_CONFIRMED

RESCUE_IDLE / RUNNING RESCUE
       |
       +-- upload to inactive slot --> VERIFY_IMAGE
       |                                     |
       |                              invalid --> REJECT
       |                                     |
       |                                  valid
       |                                     v
       +----------------------------> TRIAL_PENDING
                                            |
                                          IPROG
                                            v
                                        TRIAL_RUNNING
                                            |
                 app fails / no confirm --> next RESCUE_BOOT rolls back
                                            |
                      app passes health --> app requests RETURN_TO_RESCUE
                                            |
                                     RESCUE validates evidence
                                            |
                                      CONFIRM_AND_COMMIT
                                            |
                                       STABLE_NEW_SLOT
```

### 5.2 Transactional update sequence (MUST)

1. `STAGE`: Rescue accepts the candidate image into the **inactive** application slot. The confirmed slot and Rescue are write-protected.
2. `VALIDATE`: Rescue checks target/length/format, signing policy, on-flash readback hash, metadata consistency and bootability preconditions.
3. `PREPARE`: Rescue durably journals `pending_slot` and a bounded trial policy **before** leaving Rescue.
4. `TRIAL`: Rescue invokes BSP-specific FPGA reconfiguration to candidate A or B.
5. `OBSERVE`: PanoLab host and/or application's documented self-test evaluates target-specific health (e.g. discovery, version, protocol response, expected CSR). Simple FPGA configuration success is **not** sufficient health evidence.
6. `RETURN`: A healthy application MAY initiate ICAP return to Rescue; its minimal return shim contains no unrestricted flash-write capability. Alternatively an independently supported device mechanism returns to Rescue.
7. `CONFIRM`: Only after authenticated approval and matching trial ID/image digest may Rescue commit the new confirmed slot and clear the pending record. Retain former confirmed slot as rollback candidate until policy permits replacement.
8. `ROLLBACK`: If Rescue boots with an unconfirmed exhausted/failed trial, it MUST boot the previous confirmed image or remain in Rescue; it MUST NOT repeatedly retry a bad candidate indefinitely.

**Concurrency caveat:** since the FPGA's Rescue logic is absent while an application runs, the application cannot call a Rescue HTTP endpoint *on the device at that time*. The v1 default health-confirmation protocol therefore uses the host as observer and a standardized application `return-to-rescue` operation; after the return, the host authenticates to Rescue and confirms the matching trial. A design that offers a true independent always-on supervisor MAY support stronger autonomous confirmation, but must declare and prove that hardware feature.

### 5.3 Rollback on a hung, but valid, application

An FPGA image may configure successfully yet contain broken clocks, Ethernet, or logic. Native Spartan-6 configuration fallback does **not** by itself guarantee recovery from that runtime failure. The BSP SHALL prove at least one **application-independent** path back to Rescue, such as power cycle/reset with Rescue-first boot, and a physically accessible recovery-button override when claimed. If recovery requires an external power cycle, the public UX and qualification statement MUST say so. Continuous unattended runtime recovery is OPTIONAL until a real independent watchdog is present and proven.

### 5.4 Recovery and rescue updates

- `RECOVERY_ONLY` exposes identity, status, safe diagnostics, and authenticated repair without automatically booting bad applications.
- Standard A/B application updates MUST NOT overwrite `BOOT`, `RESCUE`, `IDENTITY`, or the other confirmed slot.
- Updating `RESCUE` is a **different maintenance class** requiring owner approval, separate verification, and a demonstrated independent fallback (redundant rescue or a proven hardware programming recovery method). Updating the currently running last recovery copy is forbidden in routine update mode.
- Factory migration can replace obsolete proprietary images eventually, but the independent bootable recovery path MUST be proven before the last working factory fallback is erased.

## 6. Network discovery and management contract

### 6.1 Discovery

- Use DHCP (when available), DNS-SD (RFC 6763) and mDNS (RFC 6762) for LAN discovery of **PanoLab Rescue**. Advertise service type `_panolab-rescue._tcp.local` as a project-specific DNS-SD service name (its protocol is standard, the service type is project-defined).
- TXT records MAY include short non-secret fields: `api=1`, `id=<device-id>`, `bsp=<profile>`, `mode=rescue`, and a protocol hint. Advertisements are **untrusted until authenticated**; never infer authorization from a broadcast response or MAC address.
- When application A/B is running, it MAY expose a compatible application service. The rescue service will disappear until reconfiguration back into Rescue; host software MUST understand this state transition.
- Provide a deterministic fallback for networks that block multicast (configured IP, DHCP lease lookup, or an explicitly authorized subnet probe). No mandatory router firmware changes.

### 6.2 Versioned API resources (contract, not a claim of implementation)

| Operation | Suggested resource / action | Authorization |
| --- | --- | --- |
| Identify | `GET /v1/device` | Read-only identity; rate-limited |
| Inventory | `GET /v1/slots` | Read-only; bounded |
| Status & reason | `GET /v1/boot-state` | Read-only; bounded |
| Stage inactive image | `POST /v1/updates` then chunk upload | Authenticated update role |
| Verify candidate | `POST /v1/updates/{id}/verify` | Authenticated update role |
| Trial boot | `POST /v1/boot/trial` | Authenticated boot-control role |
| Confirm trial | `POST /v1/boot/confirm` | Authenticated; matching trial evidence |
| Cancel/revert | `POST /v1/boot/rollback` | Authenticated boot-control role |
| Enter recovery | `POST /v1/boot/rescue` | Authenticated; only when endpoint is actually present |
| Factory/identity provisioning | Separate `/v1/provisioning` operation | Explicit elevated, device-specific enrollment |
| Rescue/boot-region update | Separate maintenance interface | Explicit owner authorization + proven independent fallback |

Responses MUST expose stable machine-readable error codes, request IDs, update/slot status, and protocol version. Mutations MUST be idempotent or carry unique operation IDs and reject stale/replayed sequence values. Flash writes MUST be bounded to the region and update transaction authorized in the request. No generic arbitrary-address flash-write API is part of the ordinary developer interface.

**Security of management:** the preferred external UX is an authenticated HTTPS API, with TLS 1.3 and provisioning-derived device/operator identity where supported. A constrained-board BSP MAY implement a standard equivalent secure transport with a separately documented and reviewed gateway mapping, but **unauthenticated write control over raw UDP, TFTP, Telnet, Etherbone or HTTP is not v1-conformant**. If a host proxy terminates HTTPS, the device MUST still authenticate/authorize update commands or the transport between proxy and board MUST be independently protected; a LAN-resident attacker must not be able to bypass the proxy. The practical LiteX bare-metal footprint, TLS profile and key-provisioning method remain PENDING qualification decisions, not assumed implementation capabilities.

**Standard API ≠ flash protocol.** The BSP may speak SPI, ICAP, vendor boot commands and historic factory protocols internally. Those mechanisms are hidden from user and agent tooling after factory conversion. Existing LiteEth/Etherbone remains available for an application if desired, but it is not an authenticated update control protocol.

## 7. Board Support Package (BSP) contract

Each supported board supplies a declarative hardware profile, software hooks and qualification evidence.

### 7.1 Required declarative profile

```yaml
bsp_api: 1
board_id: pano-g2
revision: b
fpga_part: xc6slx150-2-fgg484
compatibility_group: pano-g2-revb-spartan6-v1
flash:
  capacity_bytes: 16777216
  erase_bytes: 262144  # verify against detected JEDEC part
  page_bytes: 256     # verify against detected JEDEC part
  partitions: "PENDING: derived from built images and first-board recovery proof"
boot:
  rescue_first: "REQUIRED; PENDING physical validation"
  reconfigure: icap_spartan6
  independent_recovery: "PENDING physical reset/button validation"
network:
  phy_clock_reset_profile: g2-revb-25mhz-125mhz
  unique_mac_source: protected_identity
capabilities:
  application_slots: 2
  authenticated_management: "REQUIRED; implementation TBD"
  unattended_watchdog: false
```

This YAML is a proposed profile example, **not a release-ready partition map or implemented BSP**. Geometry, primitive support, and recovery behavior MUST be measured on the precise hardware revision. V1 BSPs SHALL also pin the LiteX/Migen/LiteEth versions, ISE/vendor toolchain, constraints, output bitstream hashes and boot metadata format.

### 7.2 Required BSP hooks

| Interface | Contract |
| --- | --- |
| `identify_board()` | Read actual board revision, FPGA and identity; fail closed on mismatch |
| `flash_geometry()` | JEDEC chip ID, capacity, page and erase unit; reject unknown parts |
| `region_map()` | Return bounded, erase-safe and non-overlapping logical regions |
| `flash_read()`, `flash_program()`, `flash_erase()` | Range-checked operations; protect boot/rescue/identity; verify writes |
| `load_boot_state()`, `commit_boot_state()` | Torn-write-tolerant journal transaction |
| `read_identity()` | Stable versioned data; never forge or regenerate unique MACs silently |
| `image_compatible()` | Validate target part/revision, configuration format, size and features |
| `reconfigure(slot)` | Vendor FPGA reconfiguration from a verified slot |
| `return_to_rescue()` | Small application-side supported recovery shim when needed |
| `recovery_input()` | Physical button/strap selection with specified sampling semantics |
| `boot_status()` | Report watchdog/fallback/reset reason if hardware supports it |
| `network_init()` | Correct PHY clock/reset sequencing; unique MAC initialization |

Never expose BSP raw SPI erase/write to arbitrary remotely supplied offsets; all operations are mediated by a vetted transaction planner and owner authorization.

### 7.3 First BSP: Pano Logic G2 Rev B

The archived G2 reverse-engineering source identifies Rev B as XC6SLX150, Rev C as XC6SLX100, so the two are **different compatibility targets**. G2 Rev B uses 128 Mbit / 16 MiB SPI NOR; the factory layout includes distinct golden/multiboot images and a data region containing board identity. **Do not reuse factory offsets as the new layout without independent examination**, and do not assume a Rev C board has enough capacity for A/B plus rescue.

The source `panologic-g2-master.zip` documents a particularly important network clock dependency: the Marvell Ethernet PHY supplies FPGA pin `Y13` at **25 MHz while PHY reset is asserted** and **125 MHz after release**. The uploaded `litex-boards-master.zip` Rev B target addresses this with PHY-specific clock/reset logic and declares a board button. Physical sequencing and button/power-cycle recovery still require validation.

The uploaded `litex-master.zip` provides an ICAP core for Xilinx 7-series/UltraScale primitives `ICAPE2`/`ICAPE3`. **That core is not a Spartan-6 drop-in.** The G2 BSP must implement and simulate `ICAP_SPARTAN6` command sequencing, warm-boot address semantics and fallback according to Spartan-6 UG380. In particular, an application firmware transition and a native configuration fallback are distinct from an application-liveness watchdog.

The uploaded `panog2_linux-master.zip` demonstrates that LiteX-based system integration on the G2 is practical but uses JTAG in its cited flash installation procedure. It **does not** establish that this Rescue v1 image has already been deployed over Ethernet or meets any of the requirements in this specification.

**Capacity feasibility (not an allocation):** Three large Spartan-6 images (one rescue and two applications) could fit in 16 MiB, but this depends on measured sizes, any compression and the reserved boot/identity/journal sectors. A requirement to support A/B is **not** a license to silently shrink critical recovery metadata or erase factory identity.

## 8. One-time factory migration / provisioning

The manufacturer's network updater is an initial entry point for converting a supported board. The v1 provisioning sequence SHALL be:

1. **Discover/identify:** inspect stock protocol, MAC, revision and observed board behavior; compare with physical label when possible.
2. **Extract:** copy factory device-identity region/records and unknown raw bytes into private, hashed, owner-controlled storage. Full flash acquisition is optional for archaeology, provided identity extraction is complete and independently validated.
3. **Plan:** generate a board-personalized partition image offline, with exact region map, source artifact hashes, factory boot constraints and failure rollback table.
4. **Establish a recoverable entry:** use only the stock updater's actually proven supported operation to load the **intended LiteX Rescue** into a compatible, reversible slot. A separate disposable bootstrap design is **not required** unless the stock updater cannot load the Rescue image.
5. **Prove Rescue:** repeatedly discover its Ethernet management, read identity, inspect SPI geometry, demonstrate ICAP handoff and cold-boot return, verify a physical recovery-button/power-cycle path.
6. **Finalize layout:** have Rescue relocate/commit required identity data and write the remaining application/metadata regions in a power-loss-safe order, with readback and protected-region assertions.
7. **Activate policy last:** alter permanent boot header/selection **only after** an independently bootable Rescue is proven; never erase the remaining working fallback before that.
8. **Qualify and record:** capture board revision, image digests, manifest, log, test results and explicit final acceptance.

Each step has a **stop on ambiguity** rule: unrecognized JEDEC geometry, mismatched identity, unexpected erase ranges, failed image verification, or an unproven independent recovery route prevents further destructive operations.

## 9. Security and operational safety model

### 9.1 Trust boundaries and threats

- Threats considered: malicious LAN update request, forged discovery, replay of previous command, malformed image/manifest, wrong-board payload, power loss mid-write, stale boot journal, unauthorized agent command, compromised host credentials, and corrupted flash.
- Factory stock protocol, legacy Telnet/TFTP loader and Etherbone are **not inherently authenticated**. Use only on an isolated owner-authorized conversion LAN, or hide them behind a verified dedicated physical provisioning process. They are not the finished product's remote write API.
- Default ordinary user tools expose read-only status, discovery and review. Mutations require explicit user authorization, authenticated identity, per-device scope, per-region bounds, and audit record. Factory identity and Rescue updates require stronger privileges than application updates.
- Production update artifacts SHOULD use COSE signatures with owner-controlled keys. Development keys SHOULD be isolated and separately enrolled. Keys MUST NOT be published in source, image bundles, logs or general agent workspaces.
- Persistent signing key IDs and release policy MAY be in writable flash, but no board lacking immutable verification hardware may be labeled physically tamper-resistant or fully secure-boot-enforced. Software anti-rollback using ordinary writable NOR metadata MUST NOT be advertised as hardware-enforced downgrade resistance.
- Public network advertisements never authorize a session; the manager MUST reauthenticate after reconfiguration and use nonces/operation IDs against replay.
- Devices MUST NOT expose unrestricted flash, JTAG, SPI, bus-master CSR, or FPGA reload commands to an unauthenticated remote caller.

### 9.2 Release profiles

| Profile | Allowed use | Minimum requirements |
| --- | --- | --- |
| `research` | Simulated or isolated factory observation | Logging, constrained probe, no automatic flash |
| `developer` | Owner-managed experimental board | Protected Rescue/identity, authenticated management, verified A/B and documented physical recovery |
| `production` | Shareable turnkey product | Developer requirements + signed releases, secure enrollment/key lifecycle, replay protection, update authorization, documented remaining hardware-root limitations |

PanoLab agents SHALL NOT automatically elevate from research/developer to production status. Evidence, independent review and exact owner approval are required.

## 10. Qualification and acceptance matrix

Every BSP seeking `PanoLab Rescue v1 — A/B qualified` SHALL pass the required cases. **Software simulation does not substitute for board-level results.** The testing method may use an instrumented bench or an isolated network and must not jeopardize an owner's only working unit without prior approval.

| ID | Test | Required pass criterion |
| --- | --- | --- |
| Q01 | Board/flash identification | Correct part/rev, JEDEC chip/geometry, true per-unit MAC; mismatches refused |
| Q02 | Partition bounds | No overlaps; correct erase/page alignment; protected ranges cannot be erased by standard update |
| Q03 | Device identity migration | Raw source kept and hashed; relocated identity survives reboot, upgrade and failed trial |
| Q04 | Rescue-first cold boot | Rescue reachable before launching apps after power-on/reset |
| Q05 | Independent recovery | Physical recovery selection works with app fabric completely dead/unresponsive |
| Q06 | Discovery | Unique DNS-SD identity across at least two boards; no shared MAC; route across ordinary LAN where supported |
| Q07 | Authentication | Unauthorized or replayed update/boot requests denied on real device |
| Q08 | Wrong-board image | Revision/FPGA mismatch and oversize payload rejected before flash |
| Q09 | Corrupt/manipulated image | Incorrect hash/signature rejected and active app unaffected |
| Q10 | A/B staging | New candidate writes only inactive slot; current confirmed remains bootable |
| Q11 | Partial application upload | Disconnect/retry/power-loss causes no confirmed-slot loss; incomplete image ignored |
| Q12 | Torn state journal | Interrupted state write preserves last valid record and boots into Rescue safely |
| Q13 | First valid trial | Candidate loads via BSP ICAP/reconfiguration and reports expected image ID |
| Q14 | Failed trial | A candidate that never confirms is not repeatedly booted; previous confirmed remains selectable |
| Q15 | Confirm trial | After observed health, return to Rescue and authenticated confirmation persists across power cycle |
| Q16 | Revert | Explicit rollback preserves prior known-good application and identity |
| Q17 | Nonresponsive app | Power cycle/button returns to Rescue without assistance from app logic |
| Q18 | Repeated power interruptions | Multiple interruptions at each flash/journal phase never lose the last independently bootable Rescue |
| Q19 | Security/storage isolation | Recovery and identity erase attempts through ordinary API refused; secret material absent from public bundle/logs |
| Q20 | Multi-device and cross-board CI | BSP source tests and device lab tests verify interoperability; another board's binary rejected |
| Q21 | Recovery maintenance | If rescue updates are supported, a failed Rescue update cannot destroy the only verified boot route |
| Q22 | Audit/reproducibility | Exact hashes, source/tools/BSP versions, device ID and test evidence captured without credential disclosure |

Qualification status MUST indicate `NOT_STARTED`, `SIMULATED`, `BENCH_VERIFIED`, or `BOARD_ACCEPTED` for each test. `BOARD_ACCEPTED` requires logs or other reviewable evidence from the exact board revision; a vendor tool PASS is not physical-boot acceptance. Without Q04, Q05, Q10, Q14, Q17 and protected Rescue write checks, the BSP MUST NOT claim resilient A/B recovery.

### 10.1 Test stages

- **S0 — Model:** flash layout checker, manifest parser, journal fault injection, boot state machine, ICAP testbench, auth API mocks.
- **S1 — FPGA implementation:** pin-compatible LiteX build, timing/resource analysis, reproducible bitstream and vetted BSP image map.
- **S2 — Isolated hardware observation:** board identity, PHY/clock, stock network protocol and safe read-only identity extraction.
- **S3 — Controlled recovery conversion:** explicitly owner-approved power-loss-safe provisioning, rescued cold boot, app A/B test and forced bad-image fallback.
- **S4 — Product qualification:** repeated cycles, two-board uniqueness, security negative tests, update/rollback logs and reproducible clean provisioning.

## 11. Release management, compatibility and versioning

- Spec: semantic versioning. Minor versions add backward-compatible optional features; major versions may change mandatory on-device API or manifest structures.
- Rescue APIs and BSP hooks: independently versioned with explicit minimum/maximum compatibility. Unknown mandatory manifest fields must be rejected.
- Compatibility group: identified by board family, revision, exact FPGA part, flash geometry and boot wiring; a generic `Pano G2` name alone is insufficient.
- Deployed builds: lock LiteX, Migen, LiteEth, BSP source commits, toolchain versions and tool images; record bitstream and manifest SHA-256.
- Git: engineering changes only to `development`, tests and review before any owner-approved promotion to `main`. The source acceptance baseline is not invalidated by drafting this specification.
- Reference implementation SHOULD provide a `panolab` CLI, discovery status, safe backup/export, authenticated inactive-slot update, verify, trial, confirm and rollback using the v1 API, but command syntax is not itself the interoperability boundary.

## 12. Decision log and unresolved technical gates

| Decision | State |
| --- | --- |
| LiteX Rescue with CPU/bare-metal firmware; application may be CPU-less | **Adopted architecture** |
| Standard A/B app slots, separate identity and journal, rescue-first boot | **Adopted architecture; proof required** |
| Common APIs/manifest/BSP contract across board families | **Adopted architecture; implementation pending** |
| Full factory flash backup required | **Rejected as universal requirement**; preserve per-device identity before erase |
| Universal one-size-fits-all Rescue bitstream | **Rejected**; compatible hardware targets need target-specific binaries |
| Permanent extra bootstrap image | **Not required by default**; use Rescue itself for migration when possible |
| Exact Rev B new flash offsets and writable boot header | **PENDING** real image sizing, erase-map and boot-chain analysis |
| Mechanism for Rev B independent cold-boot/button recovery | **PENDING** physical demonstration |
| Spartan-6 ICAP wrapper and configuration/fallback/watchdog semantics | **PENDING** simulation and board validation |
| Bare-metal network API/TLS or alternative authenticated secure transport | **PENDING** resource/security prototype |
| Secure key enrollment and limits of flash-based trust | **PENDING** design and threat review |
| Rev C or future FPGA family A/B qualification | **PENDING** distinct BSP and capacity analysis |

## 13. Source basis and industry references

**Uploaded project sources directly inspected for this specification:**

- `PANOLAB-DIRECT-v1.0-LOW-COST,-FPGA-NATIVE-DEVELOPMENT-LABORATORY.txt`: original CPU-less application design, direct Ethernet and hardware target. Rescue is a separate boot personality and does not require a CPU in the normal application.
- `panologic-g2-master.zip`: `README.md` (Rev B/Rev C, 128 Mbit flash, PHY 25/125 MHz clock behavior), `Pano.ucf` and board peripherals.
- `litex-boards-master.zip`: `litex_boards/platforms/pano_logic_g2.py` and `litex_boards/targets/pano_logic_g2.py` (revision selection, reset/button, PHY, LiteX/Ethernet).
- `litex-master.zip`: `litex/soc/cores/icap.py` (uses ICAPE2/ICAPE3; does not itself implement Spartan-6).
- `panog2_linux-master.zip`: `README.md` and included build/flash instructions (LiteX G2 feasibility; hardware programmer used in that project's documented flow).

**Industry/technical references used as design patterns (not a claim of conformance):**

- [MCUboot design: test/confirm/revert semantics](https://docs.mcuboot.com/design.html)
- [RAUC documentation: booted slot good/bad and bootloader coordination](https://rauc.readthedocs.io/en/latest/using.html)
- [RFC 9019: A Firmware Update Architecture for Internet of Things](https://www.rfc-editor.org/rfc/rfc9019)
- [RFC 9124: Manifest Information Model for Firmware Updates](https://www.rfc-editor.org/rfc/rfc9124)
- [RFC 8949: CBOR](https://www.rfc-editor.org/rfc/rfc8949), [RFC 9052: COSE structures](https://www.rfc-editor.org/rfc/rfc9052)
- [RFC 6762: Multicast DNS](https://www.rfc-editor.org/rfc/rfc6762), [RFC 6763: DNS-SD](https://www.rfc-editor.org/rfc/rfc6763)
- [Xilinx/AMD Spartan-6 Configuration User Guide UG380](https://docs.amd.com/v/u/en-US/ug380)

**Evidence rule:** historical third-party board bring-up does not count as PanoLab Rescue hardware qualification. No hardware writes were undertaken in producing this architecture specification.

---

**Final design principle:** *FPGA application images are disposable workloads; device identity, boot selection, and an independently usable rescue environment are protected system services. The developer sees normal embedded firmware update behavior; FPGA-specific configuration mechanisms stay behind the BSP.*