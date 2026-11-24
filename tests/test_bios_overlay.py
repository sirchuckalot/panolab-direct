"""Contract tests for PanoLab's pinned, build-only LiteX BIOS fixes.

No network, installation, or hardware calls. If LiteX isn't present in the
test runner, the patch-algorithm checks are skipped, not silently claimed.
"""
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
BOARD = ROOT / "projects/rescue/soc"
LITEX_PRESENT = importlib.util.find_spec("litex") is not None

@unittest.skipUnless(LITEX_PRESENT, "Needs pinned LiteX dev container")
class CleanBIOSOverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(BOARD))
        import bios_source_overlay as patches
        cls.p = patches

    def test_source_file_sha_guards(self):
        self.assertEqual(len(self.p.EXPECTED), 6)
        for digest in self.p.EXPECTED.values():
            self.assertEqual(len(digest), 64)
            self.assertRegex(digest, r"^[0-9a-f]{64}$")

    def test_linker_has_independent_load_permissions(self):
        original = (
            Path(self.p.soc_directory) / "software/bios/linker.ld"
        ).read_text()
        result = self.p.patch_linker(original)
        self.assertIn("rom PT_LOAD FLAGS(5)", result)
        self.assertIn("ram PT_LOAD FLAGS(6)", result)
        self.assertIn("> sram AT > rom :ram", result)
        self.assertIn("> sram :NONE", result)

    def test_link_flags_do_not_turn_rom_writable(self):
        mk = (Path(self.p.soc_directory) / "software/bios/Makefile").read_text()
        amended = self.p.patch_makefile(mk)
        self.assertNotIn(" -N -o $@", amended)
        self.assertIn(" -o $@", amended)

    def test_master_write_compiles_only_if_used(self):
        src = (Path(self.p.soc_directory) / "software/liblitespi/spiflash.c").read_text()
        patched = self.p.patch_spi(src)
        self.assertIn("#if defined(SPIFLASH_MODULE_QUAD_CAPABLE)", patched)
        self.assertIn("#endif /* master_write used only for Quad/QPI config */", patched)

    def test_sfp_stub_has_prior_prototype(self):
        src = (Path(self.p.soc_directory) / "software/libliteeth/sfp.c").read_text()
        patched = self.p.patch_sfp(src)
        self.assertIn("#include <libliteeth/sfp.h>", patched.split("#if", 1)[0])

    def test_compiler_rt_aliases_have_typed_prototypes(self):
        from litex import get_data_mod
        source = Path(get_data_mod("software", "compiler_rt").data_location)
        for name, alias, target in (
            ("comparesf2.c", "__cmpsf2", "__lesf2"),
            ("comparedf2.c", "__cmpdf2", "__ledf2")
        ):
            with self.subTest(name=name):
                text = (source / "lib/builtins" / name).read_text()
                rewritten = self.p.patch_alias(text, alias, target)
                self.assertIn("enum LE_RESULT " + alias + "(fp_t a, fp_t b)", rewritten)
                self.assertNotIn("FNALIAS(" + alias, rewritten)

    def test_g2_wrapper_rejects_build_warnings_and_rwx(self):
        content = (BOARD.parent/"build_probe.sh").read_text()
        self.assertIn("BIOS_BUILD_DIAGNOSTICS=ZERO", content)
        self.assertIn("BIOS_ELF_NO_RWX=PASS", content)
        self.assertIn("grep -Ei \"warning:|error:\"", content)
        self.assertIn("riscv64-unknown-elf-readelf", content)

    def test_incompatible_source_fails_closed(self):
        with self.assertRaises(RuntimeError):
            self.p.patch_linker("new upstream layout")
        with self.assertRaises(RuntimeError):
            self.p.patch_makefile("missing linker flag")
        with self.assertRaises(RuntimeError):
            self.p.patch_alias("unknown source", "A", "B")

class HostMaintenanceContracts(unittest.TestCase):
    def test_buildx_is_owner_local_and_pinned(self):
        content = (ROOT / "host/install-rootless-buildx.sh").read_text()
        for item in (
            "v0.36.1",
            "48af8a397ebd60178778bf63611dbcebe5f5e7a9be90eb9147b24b9587455778",
            "$HOME/.docker/cli-plugins", "sha256sum --check --status",
        ):
            self.assertIn(item, content)
        self.assertNotIn("sudo ", content)
        self.assertNotIn("docker system prune", content)

    def test_only_exact_rollback_container_deleted(self):
        script = (ROOT / "host/finalize-dev-maintenance.sh").read_text()
        self.assertIn("panolab-direct-dev-1-rollback-20261124T020818Z", script)
        self.assertIn('r container rm "$backup"', script)
        self.assertIn("BUILDKIT_DEFAULT_DRIVER=PASS", script)
        self.assertIn("SIX_SERVICE_HEALTH=PASS", script)
        self.assertNotIn("docker system prune", script)
        self.assertNotIn("docker volume prune", script)
        self.assertNotIn("docker image prune", script)

    def test_existing_installer_uses_buildx_and_explicit_maintenance(self):
        install = (ROOT / "host/rootless-install.sh").read_text()
        upgrade = (ROOT / "host/upgrade-dev-image.sh").read_text()
        self.assertIn("--finalize-maintenance", install)
        self.assertIn('r buildx build --builder default --load', install)
        self.assertIn('r buildx build --builder default --load', upgrade)
        self.assertNotIn("r build -t ", install)
        self.assertNotIn("r build -t ", upgrade)

if __name__ == "__main__":
    unittest.main()
