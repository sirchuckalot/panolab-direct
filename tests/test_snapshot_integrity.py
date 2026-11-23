"""Local-only baseline safety and documentation integrity checks.

No Docker daemon, private credentials, licensed toolchain or FPGA required.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
DOCS = (
    "README.md",
    "AGENTS.md",
    "docs/ARCHITECTURE.md",
    "docs/GETTING_STARTED.md",
    "docs/DEVELOPMENT.md",
    "docs/SECURITY.md",
    "docs/TOOLCHAIN_MCP_CONTRACT.md",
    "specs/PANOLAB_DIRECT_v1_0.txt",
    "agent/README.md",
    "boards/pano_g2_rev_b/README.md",
    "gateware/README.md",
)


class SnapshotIntegrity(unittest.TestCase):
    def test_essential_recipe_paths(self):
        required = (
            "panolab-install.sh", "host/rootless-install.sh",
            "host/compose.rootless-laptop.yaml",
            "docker/compose.setup.yaml", "docker/compose.manage.yaml",
            "docker/control/broker.py", "docker/control/repo_gateway.py",
            "docker/control/mcp/main.go",
            "docker/control/mcp/setup_proxy.go",
            "docker/modern/Dockerfile", "docker/ise14/Dockerfile",
            "docker/ise14/mcp/main.go",
            "docker/ise14/mcp/setup/main.go",
            "docker/ise14/ise-system-edition.batch",
            "docker/.env.example",
            "tests/fixtures/ise_counter/build.json",
        )
        for name in (*DOCS, *required):
            with self.subTest(path=name):
                self.assertTrue((ROOT / name).is_file(), name)

    def test_rootless_security_contract(self):
        self.assertFalse((ROOT / ".github" / "workflows").exists())
        ignored = (ROOT / ".gitignore").read_text()
        for marker in ("docker/private/", ".env", "*.lic", "*.key"):
            self.assertIn(marker, ignored)
        script = (ROOT / "host/rootless-install.sh").read_text()
        self.assertIn("name=rootless", script)
        self.assertNotIn("--rollback", script)
        self.assertNotIn("git reset --hard", script)
        self.assertNotIn("f stop", script)
        self.assertIn("PANOLAB_ROOTLESS_SOCKET",
                      (ROOT / "docker/compose.manage.yaml").read_text())
        worker = (ROOT / "docker/ise14/mcp/main.go").read_text()
        for name in ("toolchain_info", "build_start", "build_status",
                     "build_result", "build_cancel"):
            self.assertIn('Name:"' + name + '"', worker)

    def test_single_current_documentation_tree(self):
        expected = set(DOCS)
        roots = (ROOT, ROOT / "docs", ROOT / "agent",
                 ROOT / "boards/pano_g2_rev_b", ROOT / "gateware")
        actual = {
            p.relative_to(ROOT).as_posix()
            for directory in roots for p in directory.glob("*.md")
        }
        self.assertEqual(actual, {p for p in expected if p.endswith(".md")})
        readme = (ROOT / "README.md").read_text()
        for page in ("ARCHITECTURE", "GETTING_STARTED", "DEVELOPMENT",
                     "SECURITY", "TOOLCHAIN_MCP_CONTRACT"):
            self.assertIn("docs/" + page + ".md", readme)

    def test_all_local_markdown_links_exist(self):
        link = re.compile(r'\[[^\]]+\]\(([^)]+)\)')
        for name in DOCS:
            if not name.endswith(".md"):
                continue
            file = ROOT / name
            for target in link.findall(file.read_text()):
                if target.startswith(("http:", "https:", "mailto:", "#")):
                    continue
                path = target.split("#", 1)[0]
                if not path:
                    continue
                with self.subTest(file=name, target=target):
                    self.assertTrue((file.parent / path).exists(), target)

    def test_baseline_and_workflow_are_explicit(self):
        agents = (ROOT / "AGENTS.md").read_text()
        development = (ROOT / "docs/DEVELOPMENT.md").read_text()
        architecture = (ROOT / "docs/ARCHITECTURE.md").read_text()
        self.assertIn("one coherent reviewed commit", " ".join(agents.split()))
        self.assertIn("GitHub Actions is legitimate CI", development)
        self.assertIn("do not commit and push each trial", development.lower())
        self.assertIn("current decision baseline", architecture.lower())
        self.assertIn("not yet proven", architecture)
        self.assertIn("histories share ancestry", development)



if __name__ == "__main__":
    unittest.main()
