#!/usr/bin/env python3
"""Read-only clean-host admission tests, no Docker execution or secret access."""
import contextlib
import importlib.util
import io
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "fresh_host_audit", Path(__file__).with_name("fresh-host-audit.py"))
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


class FreshHostAdmission(unittest.TestCase):
    def test_empty_checkout_is_not_mistaken_for_installed_host(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = mod.scan(root, home=root / "empty-home")
            self.assertEqual(set(result), set(mod.CHECK_NAMES))
            for name in ("git_checkout","private_env_and_directory",
                         "tunnel_api_key","mcp_bearer","xilinx_license",
                         "ise_archive"):
                self.assertFalse(result[name],name)

    def test_private_admission_reads_metadata_only(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "checkout"
            home = Path(temp) / "home"
            config, data = mod.storage_paths(root, home)
            for path in (config, data):
                path.mkdir(parents=True, mode=0o700)
            for name in (".env","tunnel-api-key","mcp-bearer","Xilinx.lic"):
                (config/name).write_text("PRIVATE-NO-LOG")
                (config/name).chmod(0o600)
            (data/"archive.tar").write_text("PRIVATE-NO-LOG")
            result = mod.scan(root, home=home)
            for name in ("private_env_and_directory","tunnel_api_key",
                         "mcp_bearer","xilinx_license","ise_archive"):
                self.assertTrue(result[name],name)
            self.assertNotIn("PRIVATE-NO-LOG",str(result))

    def test_symlinked_secret_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            actual = root/"actual"
            actual.write_text("private")
            alias = root/"alias"
            alias.symlink_to(actual)
            self.assertFalse(mod.private_regular(alias))

    def test_ambiguous_media_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "checkout"
            home = Path(temp) / "home"
            _, data = mod.storage_paths(root, home)
            data.mkdir(parents=True, mode=0o700)
            self.assertFalse(mod.scan(root, home=home)["ise_archive"])
            (data/"one.tar").write_bytes(b"a")
            self.assertTrue(mod.scan(root, home=home)["ise_archive"])
            (data/"two.tgz").write_bytes(b"b")
            self.assertFalse(mod.scan(root, home=home)["ise_archive"])

    def test_clean_host_is_blocked_not_misreported_ready(self):
        with tempfile.TemporaryDirectory() as temp:
            captured = io.StringIO()
            with contextlib.redirect_stdout(captured):
                rc = mod.main(["fresh-host-audit.py",temp])
            self.assertEqual(rc,10)
            self.assertIn("FRESH_HOST_PREREQUISITES=BLOCKED",captured.getvalue())
            self.assertNotIn("FRESH_HOST_PREREQUISITES=READY",captured.getvalue())

    def test_top_level_clean_host_entrypoint_is_read_only_and_reports_blocked(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            host=root/"host"
            host.mkdir()
            source=Path(__file__).parent
            for source_name,destination in (
                ("panolab-install.sh",root/"panolab-install.sh"),
                ("rootless-install.sh",host/"rootless-install.sh"),
                ("fresh-host-audit.py",host/"fresh-host-audit.py"),
                ("storage_paths.py",host/"storage_paths.py"),
            ):
                original = source.parent / source_name if source_name == "panolab-install.sh" else source / source_name
                destination.write_text(original.read_text())
            (root/".git").mkdir()
            env=os.environ.copy()
            env["HOME"]=str(root/"empty-home")
            env["XDG_RUNTIME_DIR"]=str(root/"no-user-session")
            p=subprocess.run(["bash",str(root/"panolab-install.sh"),"--fresh-host-check"],
                capture_output=True,text=True,timeout=20,env=env)
            self.assertEqual(p.returncode,10)
            self.assertIn("FRESH_HOST_PREREQUISITES=BLOCKED",p.stdout)
            self.assertNotIn("PANOLAB ROOTLESS BLOCKED",p.stdout+p.stderr)
            self.assertFalse((root/"docker").exists())
            self.assertFalse((root/"empty-home").exists())

    def test_normal_installer_keeps_setup_optional(self):
        script = Path(__file__).with_name("rootless-install.sh").read_text()
        self.assertIn('--fresh-host-check',script)
        self.assertIn('--profile ise-setup config',script)
        self.assertIn('--profile ise-setup build setup',script)
        self.assertIn('up -d --no-build --no-recreate docker-broker repo-git manager',script)
        self.assertNotIn('up -d --no-build --no-recreate setup docker-broker',script)

    def test_audit_does_not_mutate_host(self):
        code = Path(__file__).with_name("fresh-host-audit.py").read_text()
        for phrase in ("docker run","docker compose up","docker rm",
                       "systemctl start","apt-get install","sudo ",
                       "shutil.rmtree","subprocess.Popen"):
            self.assertNotIn(phrase,code)
        self.assertIn("deployment NOT tested",code)


if __name__=="__main__":
    unittest.main()
