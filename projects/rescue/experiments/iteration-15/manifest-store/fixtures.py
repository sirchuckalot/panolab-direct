"""Generate canonical records for two distinct, equal-length simulated images."""
from hashlib import sha256
from runpy import run_path

fixture_tools = run_path("../manifest-core/fixtures.py")
encode, emit = fixture_tools["encode"], fixture_tools["emit"]

manifest = {
    "manifest_version": 1,
    "image_id": "store-app",
    "image_version": "1",
    "image_role": "application",
    "image_length": 1,
    "required_rescue_api": [1, 0],
    "config_format": "xilinx-spartan6-spi",
    "required_features": [],
    "supported_targets": [{
        "board_id": "pano-g2", "board_revision": "b",
        "bsp_profile": "pano-g2-revb/1", "fpga_part": "xc6slx150-2-fgg484",
    }],
    "build_provenance": {
        "dependency_pins": [], "git_commit": "0" * 40, "toolchain": "fixture",
    },
}

for name, image in (("old_manifest", b"A"), ("new_manifest", b"B")):
    emit(name, encode(dict(manifest, image_sha256=sha256(image).digest())))
