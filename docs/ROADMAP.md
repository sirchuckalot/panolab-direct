# Functional roadmap

- **Lab foundation:** rootless laptop Docker, authenticated remote MCP,
  Codex and pinned basic HDL tooling.
- **G2 M1:** CPU-less LiteX/LiteEth/Etherbone for Pano Logic G2 Rev B,
  verified clock/reset and safe CSR identity/read/write.
- **Instrumentation:** bounded LiteScope observations through an
  owner-approved hardware access path.
- **Framebuffer observation:** coherent internal BRAM snapshots with
  Ethernet readback and local Linux display.
- **Optional streaming/DDR2:** only after resource and throughput
  measurements justify the complexity.
- **Hardware control:** dedicated trusted approval/recovery path before
  any JTAG, SPI write or persistent programming.

Licensed ISE 14.7 builds, physical board constraints, generated bitstreams
and real hardware observations are independent acceptance gates. Do not
add a CPU, Linux-on-FPGA, external HDMI capture or USB3300 protocol
implementation to the baseline.
