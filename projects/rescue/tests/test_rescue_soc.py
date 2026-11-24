#!/usr/bin/env python3
"""Offline logic tests for the G2 LiteX Rescue prototype."""
import sys
import unittest
from migen import Signal
from migen.sim import run_simulation
from rescue_soc import RescueButton, RescueSoC, FLASH_BYTES

class ButtonTests(unittest.TestCase):
    def sample(self, values, cycles=12):
        button_n = Signal(reset=1)
        dut = RescueButton(button_n, sample_cycles=cycles)
        samples = []
        def run():
            for value in values:
                yield button_n.eq(value)
                yield
                samples.append((yield dut.held_latched.status))
            for _ in range(cycles + 4):
                yield
                samples.append((yield dut.held_latched.status))
            samples.append((yield dut.sampled.status))
        run_simulation(dut, run(), vcd_name=None)
        return samples

    def test_held_latches(self):
        states=self.sample([0]*14)
        self.assertEqual(states[-2],1)
        self.assertEqual(states[-1],1)

    def test_not_held(self):
        states=self.sample([1]*14)
        self.assertEqual(states[-2],0)
        self.assertEqual(states[-1],1)

    def test_short_press_not_held(self):
        states = self.sample([1]*4 + [0]*2 + [1]*9)
        self.assertEqual(states[-2], 0)
        self.assertEqual(states[-1], 1)

    def test_late_press_does_not_change_latch(self):
        states=self.sample([1]*15 + [0]*4)
        self.assertEqual(states[-2],0)

class IntegrationTests(unittest.TestCase):
    def test_mac_required_for_ethernet(self):
        with self.assertRaises(ValueError):
            RescueSoC()
        with self.assertRaises(ValueError):
            RescueSoC(lab_mac=0x010000000001)  # multicast
        with self.assertRaises(ValueError):
            RescueSoC(lab_mac=0x000000000001)  # globally administered
    def test_ethernet_spi_cpu_revision(self):
        soc=RescueSoC(lab_mac=0x020000000001)
        soc.finalize()
        self.assertEqual(soc.platform.device,"xc6slx150-2-fgg484")
        self.assertEqual(soc.cpu.name,"vexriscv")
        self.assertIsNotNone(soc.ethmac)
        self.assertEqual(soc.bus.regions["spiflash"].size,FLASH_BYTES)
        self.assertTrue(hasattr(soc, "rescue_button"))

    def test_dhcp_no_fixed_ip(self):
        soc=RescueSoC(dynamic_ip=True,local_ip=None,lab_mac=0x020000000001)
        soc.finalize()
        self.assertIsNotNone(soc.ethmac)

    def test_dhcp_rejects_static_ip(self):
        with self.assertRaises(ValueError):
            RescueSoC(dynamic_ip=True,local_ip="192.168.1.50",lab_mac=0x020000000001)

    def test_timer_bounds(self):
        for seconds in (0,61):
            with self.assertRaises(ValueError):
                RescueSoC(window_seconds=seconds,lab_mac=0x020000000001)

if __name__=="__main__":
    unittest.main()
