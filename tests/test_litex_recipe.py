#!/usr/bin/env python3
"""Offline/no-network contract tests for the rootless LiteX image recipe."""
import json
import tomllib
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMAGE = ROOT / "docker" / "modern"
PROJECT = ROOT / "projects" / "rescue"

class LiteXRecipeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lock = json.loads((IMAGE / "litex-upstream.lock.json").read_text())
        cls.project = tomllib.loads((PROJECT / "project.toml").read_text())
        cls.registry = tomllib.loads((ROOT / "third_party/registry.toml").read_text())
        cls.dockerfile = (IMAGE / "Dockerfile").read_text()
        cls.installer = (ROOT / "host/rootless-install.sh").read_text()
        cls.requirements = (IMAGE / "litex-requirements.txt").read_text()

    def test_toolchain_and_project_sources_reconcile(self):
        pins = self.lock["repositories"]
        expected = {
            "litex":"litex", "litex-boards":"litex-boards",
            "liteeth":"liteeth", "litespi":"litespi", "migen":"migen",
            "picolibc_data":"picolibc",
            "picolibc_pythondata":"pythondata-software-picolibc",
        }
        project_deps = {d["name"]: d["revision"] for d in self.project["dependencies"]}
        for old, new in expected.items():
            snap = self.registry["snapshots"][new]
            self.assertEqual(project_deps[new],snap["revision"])
            record = tomllib.loads((ROOT/"third_party"/snap["path"]/"upstream.toml").read_text())
            self.assertEqual(record["revision"], pins[old]["commit"])
            self.assertEqual(record["origin"], pins[old]["url"])

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
                     'org.panolab.litex.recipe="modern-unified-dev-20261123-v2"'):
            self.assertIn(name,self.dockerfile)

    def test_docker_context_is_allowlist(self):
        ignored=(IMAGE/".dockerignore").read_text().splitlines()
        self.assertIn("*",ignored)
        for allowed in ("Dockerfile","litex-bootstrap.py","litex-upstream.lock.json","litex-requirements.txt"):
            self.assertIn("!"+allowed,ignored)

    def test_build_helper_checks_pins_and_no_flash(self):
        helper = (PROJECT/"build_probe.sh").read_text()
        entry = (PROJECT/"build.sh").read_text()
        self.assertIn("PANOLAB_SOURCE_VERIFIED",helper)
        self.assertIn("shared/source_registry.py run",entry)
        self.assertIn("run=False",(PROJECT/"soc/rescue_soc.py").read_text())
        self.assertIn("does not fetch, install, flash",helper.lower())
        self.assertIn("not a production identity",helper.lower())
        self.assertIn("PANOLAB_LAB_MAC",entry)

    def test_installer_rebuilds_labeled_image_without_deleting_live_dev(self):
        self.assertIn("modern-unified-dev-20261123-v2",self.installer)
        self.assertIn('if [[ "$dev_image" != "$current_modern_image" ]]',self.installer)
        self.assertIn("Preserving it and all mounts",self.installer)
        self.assertIn("verify-only",self.installer)
        self.assertNotIn("docker rm -f",self.installer)
        self.assertNotIn("docker system prune",self.installer)

    def test_single_image_seven_sections(self):
        self.assertEqual(len(re.findall(r"^FROM ", self.dockerfile, re.MULTILINE)), 1)
        for n in range(1,8):
            self.assertIn("# ["+str(n).zfill(2)+"]", self.dockerfile)
        self.assertNotIn("FROM xilinx", self.dockerfile.lower())

    def test_explicit_dev_only_upgrade_with_rollback(self):
        upgrade=(ROOT/"host/upgrade-dev-image.sh").read_text()
        self.assertIn('--upgrade-dev', self.installer)
        self.assertIn('bash "$root/host/upgrade-dev-image.sh"', self.installer)
        self.assertIn('panolab-direct-modern:local',upgrade)
        self.assertIn('panolab-direct-dev-1',upgrade)
        self.assertIn('rollback()',upgrade)
        self.assertIn('r rename "$dev" "$backup"',upgrade)
        self.assertIn('r rename "$backup" "$dev"',upgrade)
        self.assertIn('--network none --read-only --cap-drop ALL',upgrade)
        self.assertIn('projects/rescue/build.sh',upgrade)
        self.assertIn('no-new-privileges:true',upgrade)
        self.assertNotIn('docker system prune',upgrade)
        self.assertNotIn('docker rm -f',upgrade)
        self.assertNotIn('docker compose up',upgrade)

    def test_local_branch_reconciliation_fail_closed(self):
        bridge=(ROOT/"host/reconcile-and-upgrade.sh").read_text()
        self.assertIn('git diff --quiet --exit-code "$old" "$equivalent_remote"',bridge)
        self.assertIn('git merge --ff-only "$target"',bridge)
        self.assertIn('git branch "$backup" "$old"',bridge)
        self.assertIn('git reset --hard "$target"',bridge)
        self.assertIn('PANOLAB_EXPECTED_DEV_SHA',bridge)
        self.assertIn('git status --porcelain --untracked-files=all',bridge)
        self.assertIn('bash "$root/panolab-install.sh" --upgrade-dev',bridge)

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
