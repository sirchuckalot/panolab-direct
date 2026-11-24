#!/usr/bin/env python3
"""Offline/no-network contract tests for the rootless LiteX image recipe."""
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMAGE = ROOT / "docker" / "modern"
BOARD = ROOT / "boards" / "pano_g2_rev_b"

class LiteXRecipeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lock = json.loads((IMAGE / "litex-upstream.lock.json").read_text())
        cls.board_lock = json.loads((BOARD / "upstream.lock.json").read_text())
        cls.dockerfile = (IMAGE / "Dockerfile").read_text()
        cls.installer = (ROOT / "host/rootless-install.sh").read_text()
        cls.requirements = (IMAGE / "litex-requirements.txt").read_text()

    def test_two_locks_identical(self):
        self.assertEqual(self.lock, self.board_lock)

    def test_complete_git_sha_pins(self):
        names = set(self.lock["repositories"])
        self.assertEqual(names, {"litex","litex-boards","liteeth","litespi",
                                 "migen","picolibc_data","picolibc_pythondata"})
        for name, info in self.lock["repositories"].items():
            with self.subTest(name=name):
                self.assertRegex(info["commit"], r"^[0-9a-f]{40}$")
                self.assertRegex(info["url"], r"^https://github\.com/")
        self.assertEqual(self.lock["schema"], "panolab-rescue-upstream-lock-v1")

    def test_requirements_exact_and_no_stale_picolibc_wheel(self):
        pins = []
        for line in self.requirements.splitlines():
            line = line.strip()
            if not line or line.startswith("#"): continue
            self.assertRegex(line, r"^[A-Za-z0-9_.-]+==[A-Za-z0-9_.+-]+$")
            pins.append(line.lower().split("==")[0].replace("_","-"))
        self.assertEqual(len(set(pins)),len(pins))
        self.assertNotIn("pythondata-software-picolibc",pins)
        for must in ("pythondata-cpu-vexriscv","pythondata-software-compiler-rt",
                     "pythondata-misc-tapcfg","meson","ninja"):
            self.assertIn(must,pins)

    def test_dockerfile_bakes_dependencies(self):
        for name in ("gcc-riscv64-unknown-elf","binutils-riscv64-unknown-elf",
                     "libevent-dev","libjson-c-dev","zlib1g-dev","python3-venv",
                     "iverilog","verilator","yosys",
                     "litex-bootstrap.py","litex-upstream.lock.json",
                     "litex-requirements.txt",
                     'org.panolab.litex.recipe="rescue-g2b-20261123-v1"'):
            self.assertIn(name,self.dockerfile)

    def test_docker_context_is_allowlist(self):
        ignored=(IMAGE/".dockerignore").read_text().splitlines()
        self.assertIn("*",ignored)
        for allowed in ("Dockerfile","litex-bootstrap.py","litex-upstream.lock.json","litex-requirements.txt"):
            self.assertIn("!"+allowed,ignored)

    def test_build_helper_checks_pins_and_no_flash(self):
        helper=(BOARD/"build_probe.sh").read_text()
        for info in self.lock["repositories"].values():
            self.assertIn(info["commit"],helper)
        self.assertIn("run", (BOARD/"rescue_soc.py").read_text())
        self.assertIn("does not fetch, install, flash",helper)
        self.assertIn("not a production identity", helper.lower())

    def test_installer_rebuilds_labeled_image_without_deleting_live_dev(self):
        self.assertIn("rescue-g2b-20261123-v1",self.installer)
        self.assertIn('if [[ "$dev_image" != "$current_modern_image" ]]',self.installer)
        self.assertIn("Preserving it and all mounts",self.installer)
        self.assertIn("verify-only",self.installer)
        self.assertNotIn("docker rm -f",self.installer)
        self.assertNotIn("docker system prune",self.installer)

    def test_verify_only_on_missing_environment_fails_without_fetch(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefix=Path(tmp)/"unprovisioned"
            p=subprocess.run(
                [sys.executable,str(IMAGE/"litex-bootstrap.py"),
                 "--prefix",str(prefix),
                 "--lock",str(IMAGE/"litex-upstream.lock.json"),
                 "--requirements",str(IMAGE/"litex-requirements.txt"),
                 "--verify-only"],
                text=True,capture_output=True,timeout=10)
            self.assertNotEqual(p.returncode,0)
            self.assertFalse(prefix.exists())
            self.assertIn("LITEX_RECIPE_FAILURE",p.stderr)

if __name__ == "__main__":
    unittest.main()
