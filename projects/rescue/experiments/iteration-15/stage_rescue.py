#!/usr/bin/env python3
"""Stage the baseline Rescue G2 Rev B gateware for the local ISE worker."""

import hashlib
import json
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory


WORKSPACE = Path(__file__).resolve().parent
GATEWARE = WORKSPACE / "baseline/gateware"
DESTINATION = Path("/workspace/ise-staging/rescue_g2b_baseline")
TOP = "pano_logic_g2"
CPU = Path(
    "/repo/third_party/pythondata-cpu-vexriscv/1.0.1.post407"
    "/src/pythondata_cpu_vexriscv/verilog/VexRiscv.v"
)
CPU_SHA256 = "10a97e84013b214c9fb480e594e438f8b1b5b76121a2545cb6489c7e29679f76"
# Width and depth from the baseline declarations. SRAM has no initial words.
MEMORIES = {"rom": (32, 9789), "sram": (32, 16384), "mem": (8, 31)}


def inline_memories(top, gateware):
    for memory, (width, depth) in MEMORIES.items():
        name = f"{TOP}_{memory}.init"
        declaration = f"reg [{width - 1}:0] {memory}[0:{depth - 1}];\n"
        block = f'initial begin\n\t$readmemh("{name}", {memory});\nend\n'
        if top.count(declaration + block) != 1:
            raise ValueError(f"{memory}: expected exactly one baseline declaration and load block")

        raw = (gateware / name).read_bytes().decode("ascii")
        words = raw.removesuffix("\n").split("\n") if raw else []
        expected_count = 0 if memory == "sram" else depth
        if len(words) != expected_count:
            raise ValueError(f"{name}: expected {expected_count} words, got {len(words)}")

        assignments = []
        for index, word in enumerate(words):
            if not re.fullmatch(rf"[0-9A-Fa-f]{{{width // 4}}}", word):
                raise ValueError(f"{name}:{index + 1}: expected a {width}-bit hex word")
            assignments.append(f"\t{memory}[{index}] = {width}'h{word};\n")

        replacement = "initial begin\n" + "".join(assignments) + "end\n" if words else ""
        top = top.replace(declaration + block, declaration + replacement, 1)

    if re.search(r"\$readmem|\x60include", top):
        raise ValueError("top contains an unexpected memory load or external include")
    return top


def stage():
    top = inline_memories((GATEWARE / f"{TOP}.v").read_bytes().decode("utf-8"), GATEWARE)
    cpu = CPU.read_bytes()
    if hashlib.sha256(cpu).hexdigest() != CPU_SHA256:
        raise ValueError("VexRiscv.v differs from the pinned snapshot checksum")

    manifest = {"top": TOP, "part": "xc6slx150-fgg484-2",
                "verilog": ["VexRiscv.v", f"{TOP}.v"], "ucf": f"{TOP}.ucf"}
    files = {
        "build.json": (json.dumps(manifest, indent=2) + "\n").encode("ascii"),
        "VexRiscv.v": cpu,
        f"{TOP}.v": top.encode("utf-8"),
        f"{TOP}.ucf": (GATEWARE / f"{TOP}.ucf").read_bytes(),
    }

    if DESTINATION.exists() or DESTINATION.is_symlink():
        if (DESTINATION.is_symlink() or not DESTINATION.is_dir()
                or {path.name for path in DESTINATION.iterdir()} != files.keys()
                or any((DESTINATION / name).is_symlink()
                       or not (DESTINATION / name).is_file()
                       or (DESTINATION / name).read_bytes() != contents
                       for name, contents in files.items())):
            raise ValueError(f"{DESTINATION} already exists with different contents")
    else:
        with TemporaryDirectory(dir=WORKSPACE) as temporary:
            pending = Path(temporary) / DESTINATION.name
            pending.mkdir()
            for name, contents in files.items():
                (pending / name).write_bytes(contents)
            pending.rename(DESTINATION)

    print(DESTINATION)
    for name, contents in files.items():
        print(f"{hashlib.sha256(contents).hexdigest()}  {name}")


if __name__ == "__main__":
    try:
        stage()
    except (OSError, ValueError) as error:
        sys.exit(f"staging failed: {error}")
