"""Source-only guardrails for the engineering handoff and temporary assets.

Never access private user files, Docker, a network or FPGA hardware.
"""
from pathlib import Path
import re
import tomllib
import unittest

ROOT=Path(__file__).resolve().parents[1]

class BaselineDocumentation(unittest.TestCase):
    def test_current_architecture_and_host_script_index_are_discoverable(self):
        readme = (ROOT / "README.md").read_text()
        architecture = (ROOT / "docs/ARCHITECTURE.md").read_text()
        self.assertIn("docs/ARCHITECTURE.md", readme)
        self.assertIn("docs/EVIDENCE.md", readme)
        self.assertIn("../host/README.md", architecture)

    def test_broker_and_temporary_maintenance_remain_intentionally_supported(self):
        compose = (ROOT / "docker/compose.manage.yaml").read_text()
        broker = (ROOT / "docker/control/broker.py").read_text()
        architecture = (ROOT / "docs/ARCHITECTURE.md").read_text()
        host_index = (ROOT / "host/README.md").read_text()
        self.assertIn("trusted-maintenance", compose)
        self.assertIn("@maintenance", broker)
        self.assertIn("docker/control/Maintenance.Dockerfile", architecture)
        self.assertIn("host/trusted-maintenance.sh", architecture)
        self.assertIn("DO NOT RERUN", host_index)

    def test_historical_one_time_scripts_have_explicit_do_not_rerun_marker(self):
        for path in ("host/reconcile-and-upgrade.sh",
                     "host/apply-source-migration.sh",
                     "host/activate-ise-bridge.sh",
                     "host/ise14-repair.py"):
            with self.subTest(path=path):
                self.assertIn("DO NOT RERUN",(ROOT/path).read_text()[:600])

    def test_third_party_snapshots_preserve_original_license_and_provenance(self):
        with (ROOT/"third_party/registry.toml").open("rb") as f:
            snapshots=tomllib.load(f)["snapshots"]
        self.assertEqual(len(snapshots),9)
        for key,entry in snapshots.items():
            base=ROOT/"third_party"/entry["path"]
            with self.subTest(component=key):
                self.assertTrue((base/"upstream.toml").is_file())
                self.assertTrue((base/"files.sha256").is_file())
                self.assertTrue(any(p.is_file() for p in
                  (base/"LICENSE",base/"LICENSE.TXT",base/"COPYING.picolibc")))
        self.assertTrue((ROOT/"LICENSE").is_file())
        self.assertTrue((ROOT/"LICENSES/README.md").is_file())

    def test_active_code_and_proprietary_media_are_separate(self):
        for path in ("docker/modern/Dockerfile","docker/modern/litex-upstream.lock.json",
                     "docker/ise14/Dockerfile","docker/ise14/ise-system-edition.batch",
                     "docker/ise14/acceptance-policy.json","docker/ise14/acceptance_design.v",
                     "docker/ise14/mcp/setup/main.go",
                     "docker/control/ise_acceptance.py","docker/control/mcp/ise_proxy.go",
                     "host/rootless-install.sh","host/fresh-host-audit.py",
                     "projects/rescue/project.toml","boards/pano_g2_rev_b/bsp.py"):
            with self.subTest(path=path):self.assertTrue((ROOT/path).is_file())
        ignored=(ROOT/".gitignore").read_text()
        for private in ("docker/private/","*.lic",".env"):
            self.assertIn(private,ignored)
        self.assertNotIn("Xilinx.lic", "\n".join(p.name for p in (ROOT/"docker/ise14").glob("*")))

    def test_every_local_markdown_link_has_target(self):
        # A global check catches broken links in current and historical
        # documentation without assuming that dated evidence is current.
        for folder in ("docs","host","boards","projects","shared","agent",
                       "LICENSES","specs","tests"):
            for page in (ROOT/folder).rglob("*.md"):
                text=page.read_text(errors="replace")
                for match in re.finditer(r'(?<!!)\[[^\]\n]*\]\(([^)]+)\)',text):
                    target=match.group(1).split("#",1)[0].strip().split(" ",1)[0].strip('"')
                    if not target or re.match(r"(?i)https?://|mailto:|git@",target):
                        continue
                    with self.subTest(file=str(page.relative_to(ROOT)),target=target):
                        self.assertTrue((page.parent/target).exists())
        page=ROOT/"README.md"
        for match in re.finditer(r'(?<!!)\[[^\]\n]*\]\(([^)]+)\)',page.read_text()):
            target=match.group(1).split("#",1)[0]
            if target and not re.match(r"(?i)https?://|mailto:|git@",target):
                self.assertTrue((ROOT/target).exists(),target)

if __name__=="__main__":
    unittest.main()
