#!/usr/bin/env python3
"""PanoLab Rescue Rev B source-first LiteX SoC prototype.

Uses pinned upstream LiteX, LiteEth, LiteSPI, LiteX-Boards and Migen.
Not a proven hardware image, managed Ethernet API, or secure A/B flasher.
"""
import argparse
import json
from pathlib import Path

from litex.soc.integration.soc import SoCCore
from litex_boards.platforms import pano_logic_g2
from liteeth.phy import LiteEthPHY
from litespi.modules import M25P128
from litespi.opcodes import SpiNorFlashOpCodes
from boards.pano_g2_rev_b.bsp import SYS_CLK, FLASH_BYTES, RescueClock, RescueButton

DEFAULT_WINDOW_SECONDS = 5


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
        from bios_source_overlay import RescueBIOSBuilder
        builder = RescueBIOSBuilder(soc, output_dir=args.out)
        builder.prepare_clean_bios()
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
