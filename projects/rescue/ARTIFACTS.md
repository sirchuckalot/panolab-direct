# Rescue build outputs (not Git-tracked source)

Run `PANOLAB_LAB_MAC=02:00:00:00:00:01 bash projects/rescue/build.sh` inside the pinned modern development container with the candidate checkout available.

The source verifier checks every selected imported source file against `third_party/registry.toml` and per-snapshot `files.sha256`, then runs the source-level BIOS and Verilog generation. The default output is `/workspace/panolab-projects/rescue-g2b/` (override using `PANOLAB_RESCUE_OUT` outside the Git checkout).

Expected examples: `software/bios/bios.bin`, `software/bios/bios.elf`, `gateware/pano_logic_g2.v`, `gateware/pano_logic_g2.ucf`, `csr.json`, `build.log`. These **are not** qualified Spartan-6 programming images. No FPGA bitstream, vendor implementation or hardware operation has been demonstrated.

The source BIOS C files are committed in `third_party/litex/afed6623/src/litex/soc/software/bios/`; imported compiler runtime and Picolibc sources and licenses are also versioned under `third_party/`.
