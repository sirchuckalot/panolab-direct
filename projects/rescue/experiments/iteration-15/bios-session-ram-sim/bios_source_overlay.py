"""Build-only Rescue BIOS and warning fixes for pinned upstream sources.

All edits happen in the generated output tree, not in the pinned Git
checkouts or the development-image package installation.
"""
from pathlib import Path
from hashlib import sha256
import shutil
from litex import get_data_mod
from litex.soc.integration.builder import Builder, soc_directory

FIRMWARE = Path(__file__).resolve().parent / "firmware"

EXPECTED = {
"bios/main.c":"60b3e00dfa9bce82dac01498aedca27125b2b342896019a65873cfffde03d3e9",
"bios/Makefile":"a741165091a5c98f226a441f6aaa6c86a8fa558dedb957b685a7db4760841c27",
"bios/linker.ld":"655ce0ad5742a4238f443caaf54b52f9bda0d2e87911c261a85e40ca80a50ea9",
"liblitespi/spiflash.c":"256bdd1f01ae8baca178a7d416211b22f351c27394e4af355b6d376abe46e122",
"libliteeth/sfp.c":"bb136747443c55973070e7b48183366c1c9b3d361a4db4dfc8f3851d46dfa1a8",
"libliteeth/udp.c":"e0f3dfe5ed0d3ddc4089b08808c5fc26fc9b7072e6b67a0d46398213d008c112",
"libliteeth/udp.h":"a3750b1e03a5a366f46213853a71467799e62f2c4ec81974fd127fa5baa085dc",
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

def patch_udp(t):
    t = replace_once(t,
        "//if(ntohs(rxbuffer->frame.contents.udp.ip.fragment_offset) != IP_DONT_FRAGMENT) return;",
        "/* Allow DF, reject fragmentation and the reserved flag. */\n"
        "\tif(ntohs(udp_ip->ip.fragment_offset) & 0xbfff) return;\n"
        "\tif(rxbuffer->frame.eth_header.srcmac[0] & 1) return;\n"
        "\tfor(i=0;i<6;i++)\n"
        "\t\tif(rxbuffer->frame.eth_header.destmac[i] != my_mac[i]) return;")
    t = replace_once(t, "if(udp_length > (ip_total_length - sizeof(struct ip_header)))",
                           "if(udp_length != (ip_total_length - sizeof(struct ip_header)))")

    return t + """
/* Simulation-only deferred reply interface, explicit captured peer. */
int sim_udp_peer_mac(uint8_t *mac);
int sim_udp_send_peer(uint32_t ip,const uint8_t *mac,uint16_t src,uint16_t dst,uint32_t length);
int sim_udp_peer_mac(uint8_t *mac) {
    if (!rx_peer_valid) return 0;
    for (unsigned i=0;i<6;i++) mac[i]=rx_peer_mac[i];
    return 1;
}
int sim_udp_send_peer(uint32_t ip,const uint8_t *mac,uint16_t src,uint16_t dst,uint32_t length) {
    return udp_send_to(ip,mac,src,dst,length);
}
"""

def patch_udp_header(t):
    return replace_once(t, "void udp_service(void);", "void udp_service(void);\nint sim_udp_peer_mac(uint8_t *mac);\nint sim_udp_send_peer(uint32_t ip,const uint8_t *mac,uint16_t src,uint16_t dst,uint32_t length);")


def patch_alias(t, alias, original):
    return replace_once(t, "FNALIAS(%s, %s);" % (alias, original),
        'COMPILER_RT_ABI enum LE_RESULT %s(fp_t a, fp_t b) __attribute__((alias("%s")));' % (alias, original))

def patch_makefile(t):
    t = replace_once(t, " -N -o $@ ", " -o $@ ")
    start = t.index("OBJECTS = boot-helper.o")
    end = t.index("\n\n", start)
    # Keep the stock system console commands. Omit boot and
    # arbitrary memory-write, or flash programming commands.
    return t[:start] + (
        "OBJECTS = helpers.o cmd_bios.o main.o crt0.o "
        "rescue_bios.o rescue_diag.o rescue_boot_policy.o rescue_storage.o rescue_flash_probe.o rescue_flash_probe_litex.o rescue_spi_nor.o identity_record.o rescue_journal.o rescue_protected_read.o sim_upload.o image_core.o rescue_update.o upload_session.o manifest_core.o manifest_store.o rescue_flash_transaction.o rescue_trial.o management_wire.o managed_wire_adapter.o network_session.o"
    ) + t[end:]


def patch_main(t):
    t = replace_once(t, '#include "boot.h"', '#include "rescue_bios.h"')
    t = replace_once(t, "\n\tint sdr_ok;\n", "\n")
    start = t.index("\n\tsdr_ok = 1;")
    end = t.index("\n\t/* Console */", start)
    # Run the rescue startup path before entering the stock UART console.
    return t[:start] + "\n\trescue_bios_diagnose();\n" + t[end:]


class RescueBIOSBuilder(Builder):
    def prepare_clean_bios(self):
        sources = Path(soc_directory) / "software"
        runtime = Path(get_data_mod("software","compiler_rt").data_location)
        source_map = {
          "bios/main.c": sources/"bios/main.c",
          "bios/Makefile": sources/"bios/Makefile",
          "bios/linker.ld": sources/"bios/linker.ld",
          "liblitespi/spiflash.c": sources/"liblitespi/spiflash.c",
          "libliteeth/sfp.c": sources/"libliteeth/sfp.c",
          "libliteeth/udp.c": sources/"libliteeth/udp.c",
          "libliteeth/udp.h": sources/"libliteeth/udp.h",
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
          "bios/main.c": patch_main,
          "bios/Makefile": patch_makefile,
          "bios/linker.ld": patch_linker,
          "liblitespi/spiflash.c": patch_spi,
          "libliteeth/sfp.c": patch_sfp,
          "libliteeth/udp.c": patch_udp,
          "libliteeth/udp.h": patch_udp_header,
          "rt/lib/builtins/comparesf2.c": lambda t: patch_alias(t,"__cmpsf2","__lesf2"),
          "rt/lib/builtins/comparedf2.c": lambda t: patch_alias(t,"__cmpdf2","__ledf2"),
        }
        for key, transform in replacements.items():
            dest=root/key
            result=transform(source_map[key].read_text())
            if result==source_map[key].read_text():
                raise RuntimeError("No overlay change: "+key)
            dest.write_text(result)
        for filename in ("rescue_bios.c", "rescue_bios.h", "rescue_diag.c", "rescue_diag.h",
                         "rescue_boot_policy.c", "rescue_boot_policy.h",
                         "rescue_storage.c", "rescue_storage.h", "rescue_flash_probe.c",
                         "rescue_flash_probe.h", "rescue_flash_probe_litex.c", "rescue_spi_nor.c", "rescue_spi_nor.h",
                         "identity_record.c", "identity_record.h", "rescue_journal.c", "rescue_journal.h",
                         "rescue_protected_read.c", "rescue_protected_read.h",
                         "sim_upload.c", "image_core.c", "rescue_update.c", "upload_session.c", "manifest_core.c", "manifest_store.c", "rescue_flash_transaction.c", "rescue_trial.c", "management_wire.c", "managed_wire_adapter.c",
                         "sim_upload.h", "image_core.h", "rescue_update.h", "upload_session.h", "manifest_core.h", "manifest_store.h", "rescue_flash_transaction.h", "rescue_trial.h", "management_wire.h", "managed_wire_adapter.h", "stream_slot.h", "managed_stream.h", "network_session.c", "network_session.h"):
            shutil.copy2(FIRMWARE / filename, root / "bios" / filename)
        shutil.copy2(sources.parents[3] / "LICENSE", root / "LITEX-LICENSE")
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
