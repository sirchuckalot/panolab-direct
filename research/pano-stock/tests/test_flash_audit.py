# SPDX-License-Identifier: GPL-3.0-or-later
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import flash_audit


class FlashAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        size = flash_audit.SECTOR_SIZE
        data = bytearray().join(bytes([index]) * size for index in range(64))
        data[size:2 * size] = b"\xff" * size
        data[2 * size - 2:2 * size + 2] = bytes.fromhex("aa995566")
        data[3 * size:4 * size] = b"\xff" * size
        data[0x480010:0x480014] = bytes.fromhex("5599aa66")
        cls.private = b"synthetic factory private string"
        data[0x8C0000:0x8C0000 + len(cls.private)] = cls.private
        cls.image = bytes(data)

    def setUp(self):
        directory = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.addCleanup(directory.cleanup)
        self.first = Path(directory.name) / "first.bin"
        self.second = Path(directory.name) / "second.bin"
        self.output = Path(directory.name) / "factory.bin"
        self.first.write_bytes(self.image)
        self.second.write_bytes(self.image)

    def audit(self, *options):
        return subprocess.run(
            [sys.executable, "-B", flash_audit.__file__, str(self.first),
             str(self.second), *map(str, options)],
            capture_output=True,
        )

    def test_matching_images_and_factory_extraction(self):
        result = self.audit("--extract-factory", self.output)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(self.private, result.stdout)
        report = json.loads(result.stdout)
        self.assertTrue(report["equal"])
        self.assertEqual(report["first"], report["second"])
        summary = report["first"]
        self.assertEqual(summary["sha256"], hashlib.sha256(self.image).hexdigest())
        regions = summary["regions"]
        self.assertEqual(
            [(region["name"], region["start"], region["end_exclusive"]) for region in regions],
            [("header", 0, 0x40000), ("golden", 0x40000, 0x480000),
             ("main", 0x480000, 0x8C0000), ("factory", 0x8C0000, 0x900000),
             ("remaining", 0x900000, 0x1000000)],
        )
        self.assertEqual(sum(region["sector_count"] for region in regions), 64)
        self.assertEqual(regions[0]["all_zero_sectors"], 1)
        self.assertEqual(regions[1]["all_ff_sectors"], 1)
        self.assertEqual(regions[1]["sectors"][0]["sync_candidates"]["aa995566"], 1)
        self.assertEqual(regions[2]["sync_candidates"]["5599aa66"], 1)
        self.assertEqual(
            regions[3]["sectors"][0]["sha256"],
            hashlib.sha256(self.image[0x8C0000:0x900000]).hexdigest(),
        )
        self.assertEqual(self.output.read_bytes(), self.image[0x8C0000:0x900000])

    def test_mismatch_refuses_extraction(self):
        self.second.write_bytes(self.image[:-1] + b"\xff")
        result = self.audit("--extract-factory", self.output)
        self.assertEqual(result.returncode, 1)
        report = json.loads(result.stdout)
        self.assertFalse(report["equal"])
        self.assertNotEqual(report["first"]["sha256"], report["second"]["sha256"])
        self.assertFalse(self.output.exists())

    def test_invalid_lengths_refuse_extraction(self):
        for image in (self.image[:-1], self.image + b"\0"):
            with self.subTest(size=len(image)):
                self.second.write_bytes(image)
                result = self.audit("--extract-factory", self.output)
                self.assertEqual(result.returncode, 2)
                self.assertIn(b"exactly 16 MiB", result.stderr)
                self.assertFalse(self.output.exists())

    def test_existing_output_is_preserved(self):
        self.output.write_bytes(b"keep")
        result = self.audit("--extract-factory", self.output)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.output.read_bytes(), b"keep")


if __name__ == "__main__":
    unittest.main()
