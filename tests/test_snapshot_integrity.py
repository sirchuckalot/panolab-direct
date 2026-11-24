"""Local-only baseline safety and documentation integrity checks.

No Docker daemon, private credentials, licensed toolchain or FPGA required.
"""
from pathlib import Path
import re
import tempfile
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
    "projects/rescue/README.md",
    "projects/rescue/ARTIFACTS.md",
    "shared/README.md",
    "LICENSES/README.md",
    "tests/fixtures/GATEWARE_FIXTURE_README.md",
    "specs/PANOLAB_SOURCE_AND_PROJECT_ARCHITECTURE.md",
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
        self.assertTrue((ROOT / "third_party/registry.toml").is_file())
        self.assertTrue((ROOT / "projects/rescue/project.toml").is_file())
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

    def test_gateway_can_access_active_recipes_but_not_private_data(self):
        # Execute only the source gateway's declarations and functions.
        # Never start its Unix socket listener or touch the live checkout.
        gateway = ROOT / "docker/control/repo_gateway.py"
        source = gateway.read_text()
        prelude, sep, _ = source.partition(
            'if not (ROOT / ".git").is_dir():')
        self.assertTrue(sep, "gateway module startup boundary missing")
        namespace = {"__name__": "panolab_gateway_readonly_test"}
        exec(compile(prelude, str(gateway), "exec"), namespace)

        with tempfile.TemporaryDirectory(prefix="panolab-source-gateway-") as tmp:
            target = Path(tmp)
            (target / "docker").mkdir()
            for filename in ("compose.setup.yaml", "compose.manage.yaml"):
                (target / "docker" / filename).write_text(
                    "services:\n  manager: {}\n")
            namespace["ROOT"] = target
            for filename in (
                "docker/compose.setup.yaml",
                "docker/compose.manage.yaml",
            ):
                with self.subTest(allowed=filename):
                    self.assertEqual(namespace["read_file"](filename)["path"],
                                     filename)
            index = namespace["list_files"](".")["entries"]
            self.assertIn("docker/compose.manage.yaml",
                          {item["name"] for item in index})
            for filename in (
                "docker/private",
                "docker/private/tunnel-api-key",
                "docker/.env",
                "docker/.env.example",
                "docker/other-compose.yaml",
                "docker/../README.md",
            ):
                with self.subTest(denied=filename):
                    with self.assertRaises(ValueError):
                        namespace["safe_path"](filename)

    def test_no_stale_source_migration_messages(self):
        comments = "\n".join((ROOT / name).read_text() for name in (
            "host/rootless-install.sh",
            "docker/compose.manage.yaml",
            "docker/compose.setup.yaml",
            "host/compose.rootless-laptop.yaml",
            "docker/control/broker.py",
        ))
        for obsolete in (
            "Original PanoLab services are untouched",
            "ignored tunnel.env",
            "previously verified rootless launcher",
            "the new rootless Docker Engine",
            "PROJECT-NETWORK",
            "host UID 1000",
        ):
            with self.subTest(obsolete=obsolete):
                self.assertNotIn(obsolete, comments)

    def test_single_current_documentation_tree(self):
        expected = set(DOCS)
        roots = (ROOT, ROOT / "docs", ROOT / "agent",
                 ROOT / "boards/pano_g2_rev_b", ROOT / "projects/rescue",
                 ROOT / "shared", ROOT / "LICENSES", ROOT / "tests/fixtures", ROOT / "specs")
        actual = {
            p.relative_to(ROOT).as_posix()
            for directory in roots for p in directory.glob("*.md")
        }
        self.assertTrue({p for p in expected if p.endswith(".md")} <= actual,
                        "Required markdown and project entry points must exist")
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
