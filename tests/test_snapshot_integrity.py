"""Local-only source-snapshot invariants; no host Docker or FPGA actions."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SnapshotIntegrity(unittest.TestCase):
    def test_reproducible_recipe_paths(self):
        required = (
            "AGENTS.md", "README.md", "panolab-install.sh",
            "host/rootless-install.sh", "host/compose.rootless-laptop.yaml",
            "docker/compose.setup.yaml", "docker/compose.manage.yaml",
            "docker/control/broker.py", "docker/control/repo_gateway.py",
            "docker/control/mcp/main.go", "docker/modern/Dockerfile",
            "docker/ise14/Dockerfile", "docker/ise14/mcp/main.go",
            "docker/.env.example", "docs/SETUP.md",
            "docs/OPERATIONS.md", "docs/TESTING.md",
            "docs/SECURITY.md", "docs/TOOLCHAIN_MCP_CONTRACT.md",
            "specs/PANOLAB_DIRECT_v1_0.txt",
        )
        for rel in required:
            with self.subTest(path=rel):
                self.assertTrue((ROOT / rel).is_file(), rel)

    def test_no_hosted_ci_or_legacy_migration(self):
        self.assertFalse((ROOT / ".github" / "workflows").exists())
        self.assertFalse((ROOT / "docs" / "ci").exists())
        self.assertFalse((ROOT / "appliance").exists())
        script = (ROOT / "host/rootless-install.sh").read_text()
        self.assertIn('name=rootless', script)
        self.assertNotIn('f stop', script)
        self.assertNotIn('appliance:ro', script)
        broker = (ROOT / "docker/control/broker.py").read_text()
        self.assertNotIn('("appliance","ro")', broker)
        gateway = (ROOT / "docker/control/repo_gateway.py").read_text()
        self.assertIn('branch not in ("main", "development")', gateway)
        self.assertNotIn('--rollback', script)
        self.assertNotIn('git reset --hard', script)

    def test_low_noise_local_workflow_contract(self):
        agents = (ROOT / "AGENTS.md").read_text()
        workflow = (ROOT / "docs/GIT_WORKFLOW.md").read_text()
        tests = (ROOT / "docs/TESTING.md").read_text()
        operations = (ROOT / "docs/OPERATIONS.md").read_text()
        self.assertIn("one focused, descriptive commit", agents)
        self.assertIn("uncommitted and unpushed", workflow)
        self.assertIn("shares", workflow)
        self.assertIn("When CI is legitimate", workflow)
        self.assertIn("Proper role of CI", tests)
        self.assertIn("Working stopping point", tests)
        self.assertIn("Create one coherent commit", operations)
        self.assertFalse((ROOT / ".github" / "workflows").exists())

    def test_retired_prototypes_are_not_required(self):
        retired = (
            "tools/docker-isolation-check.sh",
            "tools/ise14-headless-install.sh",
            "tools/ise14-license-mac.sh",
            "docker/mcp/panolab-ise14.server.yaml",
            "docker/ise14/mcp/setup/main_test.go",
        )
        for rel in retired:
            with self.subTest(path=rel):
                self.assertFalse((ROOT / rel).exists(), rel)
        gateway = (ROOT / "docker/control/repo_gateway.py").read_text()
        self.assertNotIn('"tests", "tools")', gateway)
        self.assertNotIn('panolab-ise14.server.yaml',
                         (ROOT / "docker/README.md").read_text())

    def test_no_private_material_in_tree(self):
        self.assertFalse((ROOT / "docker/private").exists())
        self.assertFalse((ROOT / "docker/.env").exists())

    def test_auth_and_vendor_toolchain_boundaries(self):
        worker = (ROOT / "docker/ise14/mcp/main.go").read_text()
        for tool in (
            "toolchain_info", "build_start", "build_status",
            "build_result", "build_cancel",
        ):
            self.assertIn('Name:"' + tool + '"', worker)


if __name__ == "__main__":
    unittest.main()
