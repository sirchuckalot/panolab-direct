"""Source-visible PanoLab project contracts: reproducible selections and fail-closed resolution."""
from pathlib import Path
import importlib.util
import os
import sys
import tomllib
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("panolab_source_registry",ROOT/"shared/source_registry.py")
registry=importlib.util.module_from_spec(spec)
spec.loader.exec_module(registry)

class SourceRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.project=registry.load_project(Path("projects/rescue/project.toml"))
        cls.catalog=tomllib.loads((ROOT/"third_party/registry.toml").read_text())["snapshots"]

    def test_project_declares_exact_approved_snapshots(self):
        used={d["name"]:d["revision"] for d in self.project["dependencies"]}
        self.assertEqual(set(used),set(registry.COMPONENTS))
        self.assertEqual({n:self.catalog[n]["revision"] for n in used},used)

    def test_all_source_bytes_and_license_text_verified(self):
        paths=registry.resolve(self.project)
        self.assertEqual(set(paths),set(registry.COMPONENTS))
        for name,src in paths.items():
            with self.subTest(name=name):
                self.assertTrue(src.is_dir())
                self.assertTrue(src.is_relative_to(ROOT/"third_party"))

    def test_unknown_or_changed_dependency_rejected(self):
        cfg=dict(self.project)
        cfg["dependencies"]=[dict(x) for x in cfg["dependencies"]]
        cfg["dependencies"][0]["revision"]="0"*8
        with self.assertRaisesRegex(ValueError,"unapproved source"):
            registry.resolve(cfg)

    def test_duplicate_dependency_rejected(self):
        cfg=dict(self.project)
        cfg["dependencies"]=self.project["dependencies"]+self.project["dependencies"][:1]
        with self.assertRaisesRegex(ValueError,"duplicate dependency"):
            registry.resolve(cfg)

    def test_source_preserves_g2_platform_and_target_upstream_license(self):
        item=self.catalog["litex-boards"]
        src=ROOT/"third_party"/item["path"]/"src/litex_boards"
        for rel in ("platforms/pano_logic_g2.py","targets/pano_logic_g2.py"):
            with self.subTest(path=rel):
                content=(src/rel).read_text()
                self.assertIn("SPDX-License-Identifier: BSD-2-Clause",content)
        self.assertNotIn("rev C", (ROOT/"projects/rescue/project.toml").read_text())

    def test_imported_bios_source_present(self):
        item=self.catalog["litex"]
        bios=ROOT/"third_party"/item["path"]/"src/litex/soc/software/bios"
        self.assertTrue((bios/"main.c").is_file())
        self.assertTrue((bios/"Makefile").is_file())
        self.assertTrue((bios/"linker.ld").is_file())
        self.assertIn("PANOLAB_LITEX_SOURCE_REVISION",(ROOT/"third_party"/item["path"]/"src/litex/build/tools.py").read_text())

if __name__=="__main__":
    unittest.main()
