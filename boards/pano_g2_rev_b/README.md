# Pano Logic G2 Rev B — Board Support

**Hardware:** Pano Logic G2 Rev B, Spartan-6 XC6SLX150-2-FGG484.
**Status:** Source/simulation-level validation; physical clock, PHY, flash and recovery remain unqualified.

`bsp.py` owns the Rev B-specific clock/reset and synchronized recovery-button CSR integration.
The **original upstream board definitions** are preserved, with provenance and BSD licensing, at:
- `../../third_party/litex-boards/2ccda127/src/litex_boards/platforms/pano_logic_g2.py`
- `../../third_party/litex-boards/2ccda127/src/litex_boards/targets/pano_logic_g2.py`

The upstream G2 target is a reference and does not implement PanoLab Rescue's update policy.
The Rescue project lives at [projects/rescue](../../projects/rescue/README.md).
Do not infer that a generated source build is a hardware-qualified FPGA image.
