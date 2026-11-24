#!/usr/bin/env python3
"""PanoLab Rescue Rev B source-first LiteX SoC prototype.

Uses pinned upstream LiteX, LiteEth, LiteSPI, LiteX-Boards and Migen.
Not a proven hardware image, managed Ethernet API, or secure A/B flasher.
"""
import argparse
import json
from pathlib import Path

from migen import ClockDomain, Signal, If
from migen.genlib.cdc import MultiReg
from litex.gen import LiteXModule
from litex.soc.cores.clock import S6PLL
from litex.soc.integration.soc import SoCCore
from litex.soc.integration.builder import Builder
from litex.soc.interconnect.csr import AutoCSR, CSRStatus
from litex_boards.platforms import pano_logic_g2
from liteeth.phy import LiteEthPHY
from litespi.modules import M25P128
from litespi.opcodes import SpiNorFlashOpCodes

SYS_CLK = 50_000_000
FLASH_BYTES = 16 * 1024 * 1024
DEFAULT_WINDOW_SECONDS = 5


class RescueClock(LiteXModule):
    """G2 PHY clock/PLL from official platform, but *not* button-held reset.

    The upstream target resets PLL whenever the Pano button is held. That
    works as reset for generic applications but prevents Rescue from
    observing a button held while power is applied. Use dedicated board
    reset input here. Real PHY startup/clock sequencing needs bench proof.
    """
    def __init__(self, platform, clk_freq):
        self.rst = Signal()
        self.cd_sys = ClockDomain()
        self.pll = pll = S6PLL(speedgrade=-2)
        reset_n = platform.request("rst_n")
        self.comb += pll.reset.eq(~reset_n | self.rst)
        pll.register_clkin(platform.request("clk125"), 125e6)
        pll.create_clkout(self.cd_sys, clk_freq)
        platform.add_false_path_constraints(self.cd_sys.clk, pll.clkin)


class RescueButton(LiteXModule, AutoCSR):
    """Synchronize and latch a held recovery button after PLL reset.

    The software may read held_latched before deciding to boot an app.
    This circuit does not reconfigure an FPGA or provide auth by itself.
    """
    def __init__(self, button_n, sample_cycles=50_000):
        if sample_cycles <= 1:
            raise ValueError("sample_cycles must be > 1")
        synced = Signal(reset=1)
        self.specials += MultiReg(button_n, synced)
        count = Signal(max=sample_cycles + 1)
        low_count = Signal(max=sample_cycles + 1)
        held = Signal(reset=0)
        done = Signal(reset=0)
        # Require sustained active-low assertion, not just one sampled glitch.
        self.sync += If(~done,
            If(~synced,
                If(low_count < sample_cycles, low_count.eq(low_count + 1))
            ).Else(low_count.eq(0)),
            If(count == sample_cycles - 1,
                done.eq(1),
                held.eq(low_count >= (sample_cycles // 2)),
            ).Else(count.eq(count + 1))
        )
        self.held_latched = CSRStatus(1, description="Recovery button was held at startup sampling.")
        self.sampled = CSRStatus(1, description="Recovery button startup sample has completed.")
        self.comb += [
            self.held_latched.status.eq(held),
            self.sampled.status.eq(done),
        ]


class RescueSoC(SoCCore):
    def __init__(self, *, with_ethernet=True, dynamic_ip=False,
                 local_ip="192.168.1.50", remote_ip="192.168.1.100",
                 lab_mac=None, window_seconds=DEFAULT_WINDOW_SECONDS, **kwargs):
        if not 1 <= window_seconds <= 60:
            raise ValueError("autoboot window must be 1..60 seconds")
        if dynamic_ip and local_ip is not None:
            raise ValueError("dynamic IP cannot be combined with a fixed local IP")
        if with_ethernet:
            if lab_mac is None:
                raise ValueError("explicit --lab-mac required until identity-from-flash support exists")
            if not isinstance(lab_mac, int) or not (0 <= lab_mac < (1 << 48)):
                raise ValueError("MAC must be 48 bits")
            if not (lab_mac & (1 << 41)) or (lab_mac & (1 << 40)):
                raise ValueError("lab MAC must be locally administered unicast")
        platform = pano_logic_g2.Platform(revision="b")
        self.crg = RescueClock(platform, SYS_CLK)
        SoCCore.__init__(
            self, platform, SYS_CLK, ident="PanoLab Rescue G2B (prototype)",
            integrated_rom_size=0x10000,
            integrated_sram_size=0x10000,
            cpu_type="vexriscv",
            **kwargs,
        )
        self.rescue_button = RescueButton(
            platform.request("user_btn_n"), sample_cycles=SYS_CLK // 100,
        )
        self.add_constant("PANOLAB_RESCUE_API", 1)
        self.add_constant("PANOLAB_AUTOBOOT_WINDOW_S", window_seconds)
        self.add_constant("PANOLAB_BOARD_REV_B", 1)

        # SPI pins and M25P128 are the official Rev B platform + detected
        # family hypothesis; verify real JEDEC ID before any erase/write.
        self.add_spi_flash(
            name="spiflash",
            mode="1x",
            clk_freq=10e6,
            module=M25P128(default_read_cmd=SpiNorFlashOpCodes.READ_1_1_1),
            with_master=True,
        )
        if with_ethernet:
            self.ethphy = LiteEthPHY(
                clock_pads=platform.request("eth_clocks"),
                pads=platform.request("eth"),
                clk_freq=SYS_CLK,
                with_hw_init_reset=False,
            )
            self.add_ethernet(
                phy=self.ethphy,
                dynamic_ip=dynamic_ip,
                local_ip=local_ip,
                remote_ip=remote_ip,
                mac_address=lab_mac,
            )
        self.add_constant("PANOLAB_ETHERNET_POC_ONLY", 1)

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="build/panolab_rescue_g2b")
    ap.add_argument("--dynamic-ip", action="store_true")
    ap.add_argument("--without-ethernet", action="store_true")
    ap.add_argument("--lab-mac", help="explicit per-board locally administered unicast MAC (example 02:00:00:00:00:01)")
    ap.add_argument("--autoboot-seconds", type=int, default=DEFAULT_WINDOW_SECONDS)
    ap.add_argument("--generate", action="store_true", help="Generate HDL/build metadata; no hardware programming")
    args = ap.parse_args()
    lab_mac = int(args.lab_mac.replace(":", ""), 16) if args.lab_mac else None
    soc = RescueSoC(
        lab_mac=lab_mac,
        with_ethernet=not args.without_ethernet,
        dynamic_ip=args.dynamic_ip,
        local_ip=None if args.dynamic_ip else "192.168.1.50",
        window_seconds=args.autoboot_seconds,
    )
    if args.generate:
        builder = Builder(soc, output_dir=args.out)
        builder.build(run=False)
    else:
        soc.finalize()
        print(json.dumps({
            "board": soc.platform.device,
            "soc": "PanoLab Rescue G2B (prototype)",
            "cpu": soc.cpu.name,
            "has_ethernet": hasattr(soc, "ethmac"),
            "has_spiflash": hasattr(soc, "spiflash"),
            "button_csr": hasattr(soc, "rescue_button"),
            "boot_window_s": args.autoboot_seconds,
            "lab_mac": args.lab_mac,
            "runtime_identity": "not implemented",
            "regions": {k: {"origin": v.origin, "size": v.size} for k,v in soc.bus.regions.items() if k in ["rom","sram","spiflash","ethmac"]},
        }, sort_keys=True))

if __name__ == "__main__":
    main()
