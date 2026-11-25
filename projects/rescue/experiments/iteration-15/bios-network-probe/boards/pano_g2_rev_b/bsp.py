"""Physical Pano G2 Rev B board-specific clock/reset and button CSR adaptation.

Uses the exact selected upstream LiteX-Boards Rev B platform. Bench qualification pending.
"""
from migen import ClockDomain, Signal, If
from migen.genlib.cdc import MultiReg
from migen.genlib.resetsync import AsyncResetSynchronizer
from litex.gen import LiteXModule
from litex.soc.cores.clock import S6PLL
from litex.soc.interconnect.csr import AutoCSR, CSRStatus

SYS_CLK = 50_000_000
FLASH_BYTES = 16 * 1024 * 1024

class RescuePLLReset(LiteXModule):
    """Turn a sys-clock request into a finite pulse on the free-running clock."""

    def __init__(self, platform, ref_clk, reset_n, request):
        self.cd_ref = ClockDomain("ref", reset_less=True)
        self.cd_board_reset = ClockDomain("board_reset")
        self.reset = Signal()
        request_sys = Signal(name="pll_request_cdc",
            reset_less=True, attr={"keep", "no_retiming"})
        request_ref = Signal()
        previous = Signal()
        remaining = Signal(max=9)
        board_async = Signal(name="pll_board_reset_async", attr={"keep"})

        self.comb += [
            self.cd_ref.clk.eq(ref_clk),
            self.cd_board_reset.clk.eq(ref_clk),
            board_async.eq(~reset_n),
            self.reset.eq(self.cd_board_reset.rst | (remaining != 0)),
        ]
        # Register the CSR pulse before crossing. A full 20 ns pulse spans
        # more than two reference periods. The edge detector rearms on low.
        self.sync += request_sys.eq(request)
        self.specials += [
            MultiReg(request_sys, request_ref, "ref"),
            AsyncResetSynchronizer(self.cd_board_reset, board_async),
        ]
        self.sync.ref += [
            previous.eq(request_ref),
            If(request_ref & ~previous,
                remaining.eq(8),
            ).Elif(remaining != 0,
                remaining.eq(remaining - 1),
            ),
        ]
        # These dedicated nets reach only the first CDC flop and the two
        # asynchronous PRE inputs, respectively. Keep the release paths timed.
        platform.add_platform_command('NET "{net}" TIG;', net=request_sys)
        platform.add_platform_command('NET "{net}" TIG;', net=board_async)


class RescueClock(LiteXModule):
    """Use the board reset pin and allow the recovery button to be held at boot."""

    def __init__(self, platform, clk_freq):
        self.rst = Signal()
        self.cd_sys = ClockDomain()
        self.pll = pll = S6PLL(speedgrade=-2)
        reset_n = platform.request("rst_n")
        clk125 = platform.request("clk125")
        pll.register_clkin(clk125, 125e6)
        self.reset_control = RescuePLLReset(platform, pll.clkin, reset_n, self.rst)
        self.comb += pll.reset.eq(self.reset_control.reset)
        pll.create_clkout(self.cd_sys, clk_freq)
        platform.add_period_constraint(clk125, 8.0)
        platform.add_period_constraint(self.cd_sys.clk, 1e9 / clk_freq)


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
