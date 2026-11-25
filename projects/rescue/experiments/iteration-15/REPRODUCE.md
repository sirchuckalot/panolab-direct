# Offline reproduction and source boundaries

The original workspace was `rescue-engineering-ef250a4` inside the rootless modern development container. This snapshot preserves original relative layout and source headers. Run only in a disposable copy outside Git, with the normal pinned PanoLab toolchain and no hardware attached. Existing canonical project source registry remains authoritative.

## Fresh regression gate

The checkpoint re-ran the same 28 component/integration groups from a newly copied source-only tree. For the flash-probe cross-compile, supply `BIOS_BUILD` pointing at the earlier locally generated CSR headers and `LITEX_SOC` at the pinned LiteX SoC source. The first run found that the historical make default expected those generated headers at a relative workspace path; providing the exact existing generated input resolved it. No source logic was modified. This is a dependency on generated output, not a self-contained clean toolchain rebuild.

```sh
# Within a disposable checkpoint copy in the existing development environment.
# BIOS_BUILD must point to generated CSR headers from the appropriate pinned
# diagnostic build; never point at a device or upload endpoint.
export PYTHONDONTWRITEBYTECODE=1
make -C storage-core test
make -C journal-core check
make -C flash-probe check BIOS_BUILD="$BIOS_BUILD"
# Remaining component directories use make check.
```

See [evidence/checkpoint-regressions.txt](evidence/checkpoint-regressions.txt) for the complete executed list and results. Test fixtures are synthetic; no actual packet delivery or device modification is involved. All actual board work is separately authorized. Native and simulated tests must not be interpreted as board acceptance.

## Historical variants

The `bios-*` build helpers and verifiers preserve the original experiment scripts. They refer to the pinned repository resolver and the timing-fix baseline UCF, generated build directories and related relative paths. The generated outputs and some staged inputs are not Git source. Use the source registry and original private build evidence to re-establish exact inputs before attempting a reproducibility test. The historical timing test script references the image bootstrap checkouts and is not the canonical source-verified entry point. The historical simulation harnesses require generated HDL, ROM init data and the pinned VexRiscv file; use the matching generated artifact hashes to identify these, not a random newer build. See [BUILD_RECORD.md](BUILD_RECORD.md).

The parent project's active `build.sh` and `test.sh` continue to select the stable source prototype. No automatic selection, physical programming, ISE execution, network operation or changes to those entrypoints are included in this checkpoint. The next engineering task is to review, consolidate, and qualify a single physical diagnostic candidate, not to merge every historical variant blindly.
