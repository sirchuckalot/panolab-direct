"""Local simulations of the candidate Wishbone register and PLL reset logic."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from migen import ClockDomain, Signal
from migen.build.xilinx.common import XilinxAsyncResetSynchronizer
from migen.fhdl import verilog
from migen.genlib.resetsync import AsyncResetSynchronizer
from migen.sim import run_simulation
from litex.soc.interconnect import wishbone

from boards.pano_g2_rev_b.bsp import RescuePLLReset
from rescue_soc import FlashWishboneRegister


FIELDS = ("adr", "dat_w", "sel", "we", "cti", "bte")
READ = (0x12345, 0x01234567, 0b0101, 0, 0, 0)
WRITE = (0x23456, 0xFEDCBA98, 0b1010, 1, 0, 0)
NO_REPLY = (0, 0)


class WishboneTest(unittest.TestCase):
    def simulate(self, scenario):
        upstream = wishbone.Interface()
        downstream = wishbone.Interface.like(upstream)
        dut = FlashWishboneRegister(upstream, downstream)

        def step(*, cyc=1, stb=1, fields=READ, ack=0, err=0, data=0,
                 request=None, downstream_cyc=1, reply=NO_REPLY, read_data=None):
            # Drive a cycle and sample the signals presented at its rising edge.
            yield upstream.cyc.eq(cyc)
            yield upstream.stb.eq(stb)
            for name, value in zip(FIELDS, fields):
                yield getattr(upstream, name).eq(value)
            yield downstream.ack.eq(ack)
            yield downstream.err.eq(err)
            yield downstream.dat_r.eq(data)
            yield

            self.assertEqual((yield downstream.cyc), downstream_cyc, "downstream CYC")
            self.assertEqual((yield downstream.stb), int(request is not None),
                             "downstream STB")
            self.assertEqual(((yield upstream.ack), (yield upstream.err)), reply,
                             "upstream ACK/ERR")
            if request is not None:
                for name, value in zip(FIELDS, request):
                    self.assertEqual((yield getattr(downstream, name)), value,
                                     f"latched downstream {name}")
            if read_data is not None:
                self.assertEqual((yield upstream.dat_r), read_data, "upstream DAT_R")

        run_simulation(dut, scenario(step))

    def test_delayed_ack_and_fields_stable_under_wait(self):
        def scenario(step):
            beat = (*READ[:4], 0b010, 0b01)
            noise = (*WRITE[:4], 0b111, 0b10)
            yield from step(fields=beat, downstream_cyc=0)
            for _ in range(4):
                yield from step(fields=noise, request=beat)
            yield from step(fields=noise, request=beat, ack=1, data=0xA5F03C69)
            yield from step(fields=noise, reply=(1, 0), read_data=0xA5F03C69)
            yield from step(cyc=0, stb=0)
            yield from step(cyc=0, stb=0, downstream_cyc=0)

        self.simulate(scenario)

    def test_delayed_error(self):
        def scenario(step):
            yield from step(fields=WRITE, downstream_cyc=0)
            yield from step(fields=WRITE, request=WRITE)
            yield from step(fields=WRITE, request=WRITE, err=1)
            yield from step(fields=WRITE, reply=(0, 1))
            yield from step(cyc=0, stb=0)
            yield from step(cyc=0, stb=0, downstream_cyc=0)

        self.simulate(scenario)

    def test_back_to_back_classic_accesses(self):
        def scenario(step):
            yield from step(downstream_cyc=0)
            yield from step(request=READ, ack=1, data=101)
            yield from step(reply=(1, 0), read_data=101)
            # Present the second beat immediately after sampling the first ACK.
            yield from step(fields=WRITE)
            yield from step(fields=WRITE, request=WRITE, ack=1)
            yield from step(fields=WRITE, reply=(1, 0))
            yield from step(cyc=0, stb=0)
            yield from step(cyc=0, stb=0, downstream_cyc=0)

        self.simulate(scenario)

    def test_held_cycle_with_burst_tags(self):
        def scenario(step):
            increment = (*READ[:4], 0b010, 0b01)
            end = (READ[0] + 1, *READ[1:4], 0b111, 0b01)
            yield from step(fields=increment, downstream_cyc=0)
            yield from step(fields=increment, request=increment, ack=1, data=1)
            yield from step(fields=increment, reply=(1, 0), read_data=1)
            for _ in range(strobe_gap):
                yield from step(stb=0)
            yield from step(fields=end)
            yield from step(fields=end, request=end)
            yield from step(fields=end, request=end, ack=1, data=2)
            yield from step(fields=end, reply=(1, 0), read_data=2)
            yield from step(cyc=0, stb=0)
            yield from step(cyc=0, stb=0, downstream_cyc=0)

        for strobe_gap in (0, 3):
            with self.subTest(strobe_gap=strobe_gap):
                self.simulate(scenario)

    def test_abandoned_beat_drains_without_reply(self):
        for drop_cyc, terminate_in_drop, error in (
            (True, False, False),
            (False, False, True),
            (True, True, True),
            (False, True, False),
        ):
            with self.subTest(drop_cyc=drop_cyc, terminate_in_drop=terminate_in_drop,
                              error=error):
                def scenario(step):
                    termination = dict(ack=int(not error), err=int(error), data=99)
                    yield from step(downstream_cyc=0)
                    yield from step(request=READ)
                    if terminate_in_drop:
                        yield from step(cyc=int(not drop_cyc), stb=0, request=READ,
                                        **termination)
                    else:
                        yield from step(cyc=int(not drop_cyc), stb=0, request=READ)
                        # Keep the old beat stable even with CYC gone for several clocks.
                        for _ in range(2):
                            yield from step(cyc=int(not drop_cyc), stb=0, fields=WRITE,
                                            request=READ)
                        # A new request returns before the old termination.
                        yield from step(fields=WRITE, request=READ)
                        yield from step(fields=WRITE, request=READ, **termination)
                    yield from step(fields=WRITE,
                                    downstream_cyc=int(not (drop_cyc and terminate_in_drop)))
                    yield from step(fields=WRITE, request=WRITE, ack=1, data=123)
                    yield from step(fields=WRITE, reply=(1, 0), read_data=123)
                    yield from step(cyc=0, stb=0)
                    yield from step(cyc=0, stb=0, downstream_cyc=0)

                self.simulate(scenario)


class PLLResetTest(unittest.TestCase):
    def test_reset_pulse_and_rearm(self):
        class Platform:
            def add_platform_command(self, *args, **kwargs):
                pass

        ref_clk = Signal(name="ref_clk")
        reset_n = Signal(name="reset_n")
        request = Signal(name="request")
        dut = RescuePLLReset(Platform(), ref_clk, reset_n, request)
        dut.cd_sys = ClockDomain("sys")
        ios = {ref_clk, reset_n, request, dut.reset, dut.cd_sys.clk, dut.cd_sys.rst}
        hdl = verilog.convert(
            dut, ios=ios, name="dut",
            special_overrides={AsyncResetSynchronizer: XilinxAsyncResetSynchronizer},
        )
        with tempfile.TemporaryDirectory(prefix="timing-fix-") as temp:
            directory = Path(temp)
            (directory / "dut.v").write_text(str(hdl))
            (directory / "bench.v").write_text(RESET_BENCH)
            subprocess.run(
                ["iverilog", "-g2012", "-s", "bench", "-o", "bench", "dut.v", "bench.v"],
                cwd=directory, check=True,
            )
            result = subprocess.run(["vvp", "bench"], cwd=directory, text=True,
                                    capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            print(result.stdout.strip(), flush=True)


RESET_BENCH = """`timescale 1ns/1ps

// Functional model of the Spartan-6 async preset flip-flop.
module FDPE #(parameter INIT = 1)(input C, CE, D, PRE, output reg Q = INIT);
    always @(posedge C or posedge PRE)
        if (PRE) Q <= 1'b1;
        else if (CE) Q <= D;
endmodule

module bench;
    reg ref_clk = 0, sys_clk = 0, sys_running = 1;
    reg reset_n = 1, request = 0;
    wire reset;
    dut circuit(.ref_clk(ref_clk), .sys_clk(sys_clk), .sys_rst(1'b0),
                .reset_n(reset_n), .request(request), .reset(reset));
    always #4 ref_clk = ~ref_clk;
    always #10 if (sys_running) sys_clk = ~sys_clk;

    integer pulses = 0;
    time started;
    reg counting = 0;
    always @(posedge reset) if (counting) begin
        pulses = pulses + 1;
        started = $time;
    end
    always @(negedge reset) if (counting && ($time - started != 64))
        $fatal(1, "reset pulse width %0t, expected 64 ns", $time - started);

    task expect_pulses(input integer count);
        if (pulses != count || reset !== 1'b0)
            $fatal(1, "expected %0d completed pulses, got %0d, reset=%b",
                   count, pulses, reset);
    endtask

    initial begin
        #41 reset_n = 0;
        #1 if (reset !== 1'b1) $fatal(1, "board reset failed async assertion");
        #16 if (reset !== 1'b1) $fatal(1, "board reset failed to stay asserted");
        reset_n = 1;
        @(posedge ref_clk);
        #1 if (reset !== 1'b1) $fatal(1, "board reset released on first ref edge");
        @(posedge ref_clk);
        #1 if (reset !== 1'b0) $fatal(1, "board reset missed second ref edge");

        counting = 1;
        @(negedge sys_clk) request = 1;
        @(negedge sys_clk) request = 0;
        #150 expect_pulses(1);

        @(negedge sys_clk) request = 1;
        @(posedge sys_clk);
        #1 sys_running = 0;
        #200 expect_pulses(2);
        #200 expect_pulses(2);

        request = 0;
        sys_running = 1;
        #100 expect_pulses(2);
        @(negedge sys_clk) request = 1;
        @(negedge sys_clk) request = 0;
        #150 expect_pulses(3);
        $display("PLL reset: board reset, three 64 ns pulses, no repeats with sys stopped");
        $finish;
    end
    initial begin
        #2000 $fatal(1, "simulation timeout");
    end
endmodule
"""


if __name__ == "__main__":
    unittest.main(verbosity=2)
