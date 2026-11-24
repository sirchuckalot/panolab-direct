"""Physical Pano G2 Rev B board-specific clock/reset and button CSR adaptation.

Uses the exact selected upstream LiteX-Boards Rev B platform. Bench qualification pending.
"""
from migen import ClockDomain, Signal, If
from migen.genlib.cdc import MultiReg
from litex.gen import LiteXModule
from litex.soc.cores.clock import S6PLL
from litex.soc.interconnect.csr import AutoCSR, CSRStatus

SYS_CLK = 50_000_000
FLASH_BYTES = 16 * 1024 * 1024

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
