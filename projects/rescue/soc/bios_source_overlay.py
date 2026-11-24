"""Build-only warning fixes for exact upstream LiteX/Compiler-RT sources.

All edits happen in the generated output tree, not in the pinned Git
checkouts or the development-image package installation.
"""
from pathlib import Path
from hashlib import sha256
import shutil
from litex import get_data_mod
from litex.soc.integration.builder import Builder, soc_directory

EXPECTED = {
"bios/Makefile":"a741165091a5c98f226a441f6aaa6c86a8fa558dedb957b685a7db4760841c27",
"bios/linker.ld":"655ce0ad5742a4238f443caaf54b52f9bda0d2e87911c261a85e40ca80a50ea9",
"liblitespi/spiflash.c":"256bdd1f01ae8baca178a7d416211b22f351c27394e4af355b6d376abe46e122",
"libliteeth/sfp.c":"bb136747443c55973070e7b48183366c1c9b3d361a4db4dfc8f3851d46dfa1a8",
"rt/lib/builtins/comparesf2.c":"3283f8012138af40d8d2e0fa1e0c557a06ebbb3c7b4a04928a5a843bcace3282",
"rt/lib/builtins/comparedf2.c":"f2ed52644b6ee481cd756a952c3fc5347a8bef6cf0a7e6dc6b4fc47984892158",
}

def replace_once(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError("Pinned upstream source changed unexpectedly")
    return text.replace(old, new)

def patch_linker(t):
    t = replace_once(t, "SECTIONS\n{",
        "/* RX ROM and RW SRAM: explicit ELF program headers. */\n"
        "PHDRS { rom PT_LOAD FLAGS(5); ram PT_LOAD FLAGS(6); }\nSECTIONS\n{")
    if "} > rom\n" not in t or "} > rom :rom\n" in t:
        raise RuntimeError("ROM linker anchor changed")
    t = t.replace("} > rom\n", "} > rom :rom\n", 1)
    t = replace_once(t, "} > sram\n\n\t.data", "} > sram :NONE\n\n\t.data")
    t = replace_once(t, "} > sram AT > rom", "} > sram AT > rom :ram")
    return t

def patch_spi(t):
    t = replace_once(t, "static void spiflash_master_write(uint32_t val, size_t len, size_t width, uint32_t mask)\n{",
        "#if defined(SPIFLASH_MODULE_QUAD_CAPABLE) || defined(SPIFLASH_MODULE_QPI_CAPABLE)\n"
        "static void spiflash_master_write(uint32_t val, size_t len, size_t width, uint32_t mask)\n{")
    t = replace_once(t, "\tspiflash_master_cs_write(0);\n}\n\nstatic volatile uint8_t w_buf",
        "\tspiflash_master_cs_write(0);\n}\n#endif /* master_write used only for Quad/QPI config */\n\nstatic volatile uint8_t w_buf")
    return t

def patch_sfp(t):
    return replace_once(t, "#include <generated/soc.h>\n",
        "#include <generated/soc.h>\n#include <libliteeth/sfp.h>\n")

def patch_alias(t, alias, original):
    return replace_once(t, "FNALIAS(%s, %s);" % (alias, original),
        'COMPILER_RT_ABI enum LE_RESULT %s(fp_t a, fp_t b) __attribute__((alias("%s")));' % (alias, original))

def patch_makefile(t):
    return replace_once(t, " -N -o $@ \\", " -o $@ \\")

class RescueBIOSBuilder(Builder):
    def prepare_clean_bios(self):
        sources = Path(soc_directory) / "software"
        runtime = Path(get_data_mod("software","compiler_rt").data_location)
        source_map = {
          "bios/Makefile": sources/"bios/Makefile",
          "bios/linker.ld": sources/"bios/linker.ld",
          "liblitespi/spiflash.c": sources/"liblitespi/spiflash.c",
          "libliteeth/sfp.c": sources/"libliteeth/sfp.c",
          "rt/lib/builtins/comparesf2.c": runtime/"lib/builtins/comparesf2.c",
          "rt/lib/builtins/comparedf2.c": runtime/"lib/builtins/comparedf2.c",
        }
        for key, path in source_map.items():
            if sha256(path.read_bytes()).hexdigest() != EXPECTED[key]:
                raise RuntimeError("Unapproved upstream version: "+key)
        root = Path(self.output_dir) / "source_overlays"
        for label, src in (("bios",sources/"bios"),
                           ("liblitespi",sources/"liblitespi"),
                           ("libliteeth",sources/"libliteeth"),("rt",runtime)):
            dst=root/label
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src,dst)
        replacements = {
          "bios/Makefile": patch_makefile,
          "bios/linker.ld": patch_linker,
          "liblitespi/spiflash.c": patch_spi,
          "libliteeth/sfp.c": patch_sfp,
          "rt/lib/builtins/comparesf2.c": lambda t: patch_alias(t,"__cmpsf2","__lesf2"),
          "rt/lib/builtins/comparedf2.c": lambda t: patch_alias(t,"__cmpdf2","__ledf2"),
        }
        for key, transform in replacements.items():
            dest=root/key
            result=transform(source_map[key].read_text())
            if result==source_map[key].read_text():
                raise RuntimeError("No overlay change: "+key)
            dest.write_text(result)
        self.software_packages=[
          (name,str(root/name) if name in ("liblitespi","libliteeth") else src)
          for name,src in self.software_packages
        ]
        self.add_software_package("bios",src_dir=str(root/"bios"))
        self._rescue_rt_dir = root/"rt"
        return root

    def _get_variables_contents(self):
        text=super()._get_variables_contents()
        if not hasattr(self,"_rescue_rt_dir"):
            raise RuntimeError("Call prepare_clean_bios() before build")
        lines=text.splitlines()
        matches=[i for i,line in enumerate(lines) if line.startswith("COMPILER_RT_DIRECTORY=")]
        if len(matches)!=1:
            raise RuntimeError("LiteX upstream Compiler-RT variable changed")
        lines[matches[0]]="COMPILER_RT_DIRECTORY="+str(self._rescue_rt_dir)
        return "\n".join(lines)
