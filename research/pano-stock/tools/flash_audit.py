# SPDX-License-Identifier: GPL-3.0-or-later
"""Validate two local raw Rev B flash images and optionally extract the factory sector."""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

IMAGE_SIZE = 0x1000000
SECTOR_SIZE = 0x40000
REGIONS = (
    ("header", 0, 0x40000),
    ("golden", 0x40000, 0x480000),
    ("main", 0x480000, 0x8C0000),
    ("factory", 0x8C0000, 0x900000),
    ("remaining", 0x900000, IMAGE_SIZE),
)
SYNC_MARKERS = {
    "aa995566": bytes.fromhex("aa995566"),
    "5599aa66": bytes.fromhex("5599aa66"),
}
ERASED_SECTOR = b"\xff" * SECTOR_SIZE
ZERO_SECTOR = bytes(SECTOR_SIZE)


def read_image(path, label):
    try:
        if not path.is_file():
            raise ValueError(f"The {label} image must be a regular file.")
        with path.open("rb") as source:
            image = source.read(IMAGE_SIZE + 1)
    except OSError:
        raise ValueError(f"Could not read the {label} image.") from None
    if len(image) != IMAGE_SIZE:
        raise ValueError(f"The {label} image must be exactly 16 MiB.")
    return image


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def summarize(image):
    regions = []
    for name, start, end in REGIONS:
        sectors = []
        for offset in range(start, end, SECTOR_SIZE):
            sector_end = offset + SECTOR_SIZE
            data = image[offset:sector_end]
            # Attribute a marker to the sector containing its first byte.
            scan = image[offset:sector_end + 3]
            sectors.append({
                "offset": offset,
                "sha256": sha256(data),
                "all_ff": data == ERASED_SECTOR,
                "all_zero": data == ZERO_SECTOR,
                "sync_candidates": {
                    name: scan.count(marker) for name, marker in SYNC_MARKERS.items()
                },
            })
        regions.append({
            "name": name,
            "start": start,
            "end_exclusive": end,
            "sha256": sha256(image[start:end]),
            "sector_count": len(sectors),
            "all_ff_sectors": sum(sector["all_ff"] for sector in sectors),
            "all_zero_sectors": sum(sector["all_zero"] for sector in sectors),
            "sync_candidates": {
                marker: sum(sector["sync_candidates"][marker] for sector in sectors)
                for marker in SYNC_MARKERS
            },
            "sectors": sectors,
        })
    return {"sha256": sha256(image), "regions": regions}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("first", type=Path)
    parser.add_argument("second", type=Path)
    parser.add_argument("--extract-factory", type=Path, metavar="OUTPUT",
                        help="Create a new local file from the matching factory sector.")
    args = parser.parse_args(argv)

    try:
        first = read_image(args.first, "first")
        second = read_image(args.second, "second")
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2

    equal = first == second
    first_summary = summarize(first)
    report = {
        "size_bytes": IMAGE_SIZE,
        "sector_size_bytes": SECTOR_SIZE,
        "equal": equal,
        "first": first_summary,
        "second": first_summary if equal else summarize(second),
    }
    print(json.dumps(report, indent=2))
    if not equal:
        return 1

    if args.extract_factory is not None:
        _, start, end = next(region for region in REGIONS if region[0] == "factory")
        try:
            # The exclusive open also refuses existing symlinks and input paths.
            fd = os.open(args.extract_factory, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as output:
                output.write(first[start:end])
        except OSError:
            print("Could not create or write the factory output.", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
