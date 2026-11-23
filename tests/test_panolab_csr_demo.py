"""Simulation-only agent-directed CSR development acceptance.

Run in the laptop rootless development container to exercise Icarus/Yosys.
Hosts without those tools may still run the Python source test suite;
unavailable tool-dependent cases are explicitly SKIPPED, not passed.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
RTL = ROOT / "gateware/panolab_csr_demo.v"
TB = ROOT / "tests/fixtures/panolab_csr_demo_tb.v"


def run(*argv):
    return subprocess.run(argv, text=True, capture_output=True, check=False,
                          timeout=30)


class AgentCsrDemo(unittest.TestCase):
    def test_source_and_fixture_present(self):
        self.assertTrue(RTL.is_file())
        self.assertTrue(TB.is_file())
        source = RTL.read_text()
        self.assertIn("reg served;", source)
        self.assertIn("if (wb_sel_i[0])", source)
        self.assertIn("if (wb_sel_i[3])", source)
        self.assertIn("default_nettype none", source)

    @unittest.skipUnless(shutil.which("iverilog") and shutil.which("vvp"),
                         "requires containerized Icarus Verilog")
    def test_classic_bus_simulation(self):
        with tempfile.TemporaryDirectory() as temp:
            executable = str(Path(temp) / "csr.vvp")
            compile_result = run("iverilog", "-g2012", "-Wall", "-s",
                                 "panolab_csr_demo_tb", "-o", executable,
                                 str(RTL), str(TB))
            self.assertEqual(compile_result.returncode, 0, compile_result.stderr)
            sim = run("vvp", executable)
            self.assertEqual(sim.returncode, 0, sim.stdout + sim.stderr)
            self.assertIn("PANOLAB_AGENT_RTL_PASS checks=44", sim.stdout)

    @unittest.skipUnless(shutil.which("iverilog") and shutil.which("vvp"),
                         "requires containerized Icarus Verilog")
    def test_regression_catches_wrong_byte_enable(self):
        correct = RTL.read_text()
        broken = correct.replace("if (wb_sel_i[0]) scratch[7:0]",
                                 "if (wb_sel_i[1]) scratch[7:0]")
        self.assertNotEqual(broken, correct)
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "deliberately_wrong.v"
            executable = str(Path(temp) / "wrong.vvp")
            source.write_text(broken)
            compile_result = run("iverilog", "-g2012", "-s",
                                 "panolab_csr_demo_tb", "-o", executable,
                                 str(source), str(TB))
            self.assertEqual(compile_result.returncode, 0, compile_result.stderr)
            sim = run("vvp", executable)
            self.assertNotEqual(sim.returncode, 0,
                                "The regression fixture failed to detect the mutation")
            self.assertIn("FAIL: check=18", sim.stdout)

    @unittest.skipUnless(shutil.which("yosys"),
                         "requires containerized Yosys")
    def test_yosys_process_and_structural_check(self):
        command = "read_verilog {}; hierarchy -check -top panolab_csr_demo; proc; check -assert".format(RTL)
        result = run("yosys", "-Q", "-T", "-p", command)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
