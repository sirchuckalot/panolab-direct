# PanoLab Source and Project Architecture Standard

**Status:** Adopted source/project authority. Selected source snapshots,
PanoLab licensing files and project entrypoints are committed in
`development`; a full new-host or live source-mount/worker migration
acceptance is separate and still unverified.
**Date:** 2026-11-23  
**Scope:** PanoLab Direct repository organization, source ownership, third-party integration, build provenance, project packaging, and licensing  
**Implementation boundary:** This document records decisions; it does not itself authorize moving source, rewriting builds, installing tools, flashing hardware, or promoting `main`.

## 1. Purpose and authority

PanoLab Direct is the **engineering platform**: rootless containers, developer and vendor toolchains, controlled agent access, host management, testing, and publication infrastructure. A **project** is a complete, independently identifiable FPGA implementation built *using* that platform. PanoLab Rescue is a project, not a board definition or the platform itself.

This standard is the **source-and-project organization authority** for subsequent PanoLab engineering. Follow it when designing new source trees, importing dependencies, creating projects, changing shared code, or planning the migration. The root [AGENTS.md](../AGENTS.md) directs engineering agents here.

It is a **target architecture**, originally a target rather than a description of folders that already exist. The current deployed layout and tested operational boundaries remain documented in [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md). Rescue's on-device boot, update, security, and image-manifest requirements remain governed by [PANOLAB_RESCUE_V1.md](PANOLAB_RESCUE_V1.md). If implementation work exposes a conflict, record it and obtain review; do not silently redefine this standard or change the working system.

Goals:

- Keep the repository intelligible to human and AI-assisted developers: one obvious owner and one discoverable entry point for each source or project.
- Reuse proven upstream work and shared PanoLab components without unnecessary copies or reinvention.
- Import **only the upstream source needed by supported projects and boards**, while retaining its identity, licensing, provenance, and a practical contribution path back upstream.
- Make source-to-generated-RTL-to-release relationships verifiable, especially when agents perform source transformations.
- Support independent product evolution, commercial distribution where permitted, and reciprocal sharing of improvements to covered code.
- Preserve the functioning laptop laboratory and Git history while making changes in small, independently verified steps.

## 2. Terms and ownership

| Term | Meaning | Ownership boundary |
| --- | --- | --- |
| **Platform / PanoLab Direct** | Engineering tools, containers, agents, deployment, testing, and controls | `host/`, `docker/`, `agent/`, platform `tests/`, operating docs |
| **Project** | A complete buildable FPGA implementation (e.g. Rescue or a logic analyzer), whether experimental or commercial | `projects/<name>/` |
| **Board / BSP** | Physical hardware identity, pinout, clocks, reset/PHY, flash geometry, programming/recovery hooks, constraints, board qualification | `boards/<board-id>/` |
| **Shared component** | PanoLab-authored functionality reused by multiple projects | `shared/` |
| **Upstream component** | Selected third-party source retained under upstream names and applicable licenses | `third_party/` |
| **Build output** | Generated HDL, BIOS/firmware objects, reports, bitstreams and intermediary files | Ignored build workspace; not independently maintained source |
| **Qualified release** | Versioned, verified project deliverable and provenance/source package | Published release artifacts, not ordinary tracked build output |

**Ownership follows behavior, not file language.** A Rescue LiteX/Migen Python SoC generator belongs to Rescue even though it generates Verilog. General reusable PanoLab-written RTL, firmware helpers, or generators belong in `shared/`. Hardware-specific constraints and adaptation belong in `boards/`. A third-party LiteX-Boards platform/target remains third-party source; the PanoLab board BSP refers to or adapts it without creating an unnecessary renamed copy.

A project may use a board, shared component, or upstream component, but must not silently assume ownership of that source. A component moves to `shared/` only when genuinely reusable; do not abstract speculative reuse.

## 3. Target repository layout

```text
panolab-direct/
  README.md
  AGENTS.md
  panolab-install.sh
  host/                      # Host installation and lifecycle
  docker/                    # Modern toolchain, isolated legacy vendor worker, services
  agent/                     # Agent integration and interfaces
  projects/
    rescue/
      README.md              # One obvious engineer-facing starting point
      project.toml           # Authoritative build/dependency entry point
      soc/                   # Rescue-owned SoC construction / generators
      firmware/              # Rescue-owned firmware
      rtl/                   # Rescue-owned handwritten HDL when needed
      tests/                 # Rescue behavior and project tests
  boards/
    pano_g2_rev_b/           # Board-specific data, BSP hooks, constraints, validation
  shared/                    # Reusable PanoLab-authored RTL, generators and libraries
  third_party/
    registry.toml            # One authoritative catalog of approved source snapshots
    <upstream-project>/
      <snapshot-id>/
        upstream.toml        # Exact origin/revision, selection, local changes, license map
        src/                 # Only required imported paths, retaining upstream layout
        ...                  # Required copyright/license/notice files
  tests/                     # Platform and cross-project test infrastructure
  specs/                     # Cross-project standards (including this file)
  docs/                      # Operational architecture, procedures, evidence
  LICENSE                    # Existing PanoLab-owned GPL-3.0-or-later terms
  LICENSES/                  # Existing license/attribution index; upstream full texts retained in snapshots
```

This tree is the approved source-ownership model. The migration
candidate now contains the implementation paths, but live host mount and
Docker-service acceptance remains a separate gate. Names selected for the target architecture: **`projects/` rather than `products/`**, since each item is an engineering implementation and may or may not become a commercial product. `products/` is not a second source root. A release or manufactured product is built *from* a project.

Do not create another general development environment per board, tool, or project. One modern pinned development image remains the default. Legacy licensed Xilinx ISE 14.7 remains an isolated vendor worker. Board adaptations belong in BSPs, not duplicate Docker toolchains.

## 4. Selected upstream source and contribution workflow

Use **selective vendoring with explicit upstream provenance**, not complete upstream trees by default, floating `master` downloads, or opaque imports at product-build time.

1. Identify the precise upstream project URL and full commit ID, its license and notices, the needed source paths, and all **transitive** source/data dependencies required for a working build. A two-file board selection is *not* proof of complete dependency closure.
2. Import only that proven closure into a versioned `third_party/` snapshot. Preserve original relative paths, names, copyright/license text, notices, and meaningful attribution. Record the upstream full commit, file selection and checksums in `upstream.toml` and reference the snapshot from the central registry.
3. Record the upstream baseline in an identifiable Git import commit. PanoLab's Git commits then record subsequent edits, their purpose and tests. The original upstream history remains available by exact reference at its repository; **we do not import its entire historical Git commit graph**.
4. Prefer board adapters, wrappers, or product-local integration over editing imported code when that avoids unnecessary upstream divergence. Where an upstream source fix is required, edit the imported source transparently, preserve original notices, and make the change reviewable in separate commits. Do not maintain a second authoritative patch queue duplicating already-modified source.
5. Prepare focused upstream-compatible diffs and contribute suitable fixes back to upstream maintainers through their normal process. Record submission/acceptance or why a local divergence remains. Upstream acceptance is not automatic permission to change PanoLab's approved revision.
6. For upstream updates, create or import a new reviewed snapshot, compare it with the earlier baseline and local fixes, rerun affected project tests, and deliberately update product references. Do not mutate approved dependencies behind a project's back.

Existing Docker-fetched pins and source overlays are **current implementation**, not a reason to abandon this future source-visible rule. Their migration requires a separate review and build-equivalence test.

## 5. Dependencies and version isolation

There is **one authoritative third-party source registry**. Each project's `project.toml` names the exact approved source snapshots it uses. Multiple projects share one snapshot when compatible. Keep distinct, simultaneously available snapshots only when products genuinely need incompatible revisions.

A product never inherits a floating global LiteX/LiteEth revision. Upgrading one product does not silently change another. Project builds use separately resolved source paths and, where appropriate, isolated Python/build environments; no collision through ambient `PYTHONPATH` or mutable global checkouts.

Toolchain provisioning is a separate concern: `docker/` pins the software environment and proprietary-tool prerequisites, while **project source selection is controlled by the project manifest and central source registry**. Avoid competing product-source lock authorities. During migration, existing locks may coexist temporarily, but new tooling must explicitly identify which record is authoritative and verify consistency before retiring old files.

## 6. Complete projects and manifests

Every project has **one obvious entry point** at `projects/<name>/README.md` and one machine-readable `project.toml` declaring:

- Project identity, version, description, and owning source root.
- Supported board IDs/BSP versions, exact FPGA parts or compatibility groups and required hardware capabilities.
- Owned SoC, firmware, RTL, configuration and test entry points.
- Exact approved upstream snapshot references, shared-component references, and any explicitly tracked local modifications.
- Toolchain/environment profile, build command or target, declared inputs and expected outputs.
- Test and acceptance requirements and the applicable source-license/notice references.

A product's build inputs may be shared elsewhere in the same repository; **complete** does not mean copying the whole dependency tree into every project. The manifest must allow an engineer or automated build to resolve all inputs without guessing. Define and validate the concrete TOML schema before enforcing it; the field list above is the required contract, not a claim that a parser already exists.

The **source project manifest is different from the on-device FPGA image/release manifest** in [Rescue v1](PANOLAB_RESCUE_V1.md). The former selects how to build; the latter identifies a produced board-compatible image, digest and, where applicable, its signature and installation constraints. Do not merge those responsibilities.

## 7. Build and provenance contract

Two build states are legitimate:

- **Development:** Agents or engineers may build from an explicitly identified dirty working tree in a restricted workspace. Output must be labeled unqualified; experiments must not silently replace approved releases.
- **Qualification/release:** Use a specific Git commit, resolved manifest and complete verified source snapshot set. Fail closed on undeclared imports, missing/altered source, unapproved upstream substitutions, unrecorded overlays or incompatible target selections. Record build inputs, source commits/digests, generation steps, toolchain/image versions, constraints, test results and output artifact hashes.

Generated Python-to-Verilog and firmware transformations must be declared and traceable. Their outputs are build artifacts, not a second independently edited source of truth. Do not download or patch hidden alternative source trees during product compilation. Explicit reviewed dependency acquisition and toolchain provisioning are separate operations.

Bit-for-bit reproducibility is a **testable claim**, not guaranteed merely by a manifest; licensed FPGA vendor tools, device-specific options and generated files require actual verification. Simulation success, a source build, vendor synthesis/bitstream generation, and physical FPGA verification are different acceptance gates. Keep qualification evidence with the appropriate project/release and publish validated binaries as versioned releases rather than committing transient outputs.

A standalone distributable source package must include the project's redistributable corresponding source and necessary build definitions/dependency information, plus applicable notices and license-compliant source for included components. Proprietary vendor binaries and license credentials remain separately acquired/private unless redistribution is explicitly authorized.

## 8. Licensing and attribution

**Selected direction:** **GNU GPL-3.0-or-later** for original PanoLab framework code, including PanoLab-authored Python/Migen/LiteX generators, firmware, and HDL/RTL where PanoLab has the rights and license compatibility permits. The migration candidate includes a top-level `LICENSE` and keeps third-party
license files with each imported snapshot. **This is not a claim of a completed
redistribution or generated-hardware licensing audit**.

- Every upstream component retains its **own** copyright, license terms, required notices, and documented origin. A top-level PanoLab license does not relicense third-party files. Record per-file exceptions, not just repository-root license guesses.
- Use clear SPDX file identifiers/copyright records and retained original license texts and notices; include compliant third-party notices in releases.
- Commercial use and sale of PanoLab-derived products are permitted subject to all applicable terms. Distribution of covered GPL derivatives invokes the GPL's corresponding-source and other obligations; a contribution to the central PanoLab GitHub repository is **not** legally mandated by GPL.
- Do not put GPL-only notices on upstream BSD files merely because PanoLab uses them. Keep upstream fixes under terms compatible with the original maintainers' contribution policy where lawful; audit GPLv2-only, LGPL, Apache, generated code and vendor dependencies before combination or redistribution.
- GPL on development tools does **not automatically license independent output designs**; generated FPGA HDL/firmware/bitstreams require a content-specific rights and license review. Preserve any upstream included RTL, firmware, or generated content notices.
- Physical PCB/schematic design files are distinct from FPGA gateware. A strongly reciprocal hardware-design license such as CERN-OHL-S-2.0 is a **future recommendation only**, not adopted for uncreated board designs.
- A future signed commercial consumer appliance must account for GPLv3 installation-information requirements when applicable. Device authentication and secure update design must not silently conflict with the covered software's license.
- AI-assisted contributions require the same authorship/provenance and third-party rights scrutiny as other contributions; do not invent copyright ownership or assume generated output is free of inherited licensing.

The repository-migration approval encompasses initial license placement and
source attribution; a further file-level compatibility and generated-hardware
redistribution audit remains necessary before commercial appliance releases. Do not silently modify source headers or relicense upstream files as part of a repository-layout migration.

## 9. Development, migration and change control

All repository organization principles apply to the platform, projects, boards, shared components and selected upstream code. New source should follow this standard after the source layout is formally migrated; until then, explicitly distinguish current paths from target paths.

- Protect the current working rootless laptop lab, credentials, private ISE media, source history and recovery options. No host-wide cleanup or silent Docker changes.
- Work on `development`. `main` remains the separately accepted baseline; promotion requires explicit owner approval.
- Plan migration as small, reviewable moves with ownership mapping, Git history preservation, source-registry import/closure validation, project build/test equivalence, documentation updates and rollback.
- Keep operational instructions in [docs/GETTING_STARTED.md](../docs/GETTING_STARTED.md), live architecture in [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md), verification and publication procedure in [docs/DEVELOPMENT.md](../docs/DEVELOPMENT.md), security boundaries in [docs/SECURITY.md](../docs/SECURITY.md), and Rescue behavior in [PANOLAB_RESCUE_V1.md](PANOLAB_RESCUE_V1.md).
- Agents must identify the actual source owner and authority, declare their intended files and test gate, verify before publishing one reviewed coherent milestone, and **stop for clarification rather than assume** when source ownership, license rights, upstream identity or hardware effects are ambiguous.

**This standard approves the direction and organizing rules only.** It does not assert that `projects/`, `shared/`, `third_party/`, manifests, licensing files, or source-closure enforcement are present or tested in the existing Git checkout.
