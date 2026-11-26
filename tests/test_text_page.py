import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from agent.text_page import FOOTER, FRAME_BYTES, read_page, verify_pages


class TextPageTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.git("init", "-q")

    def git(self, *args):
        subprocess.run(["git", "-C", self.root, *args], check=True, capture_output=True)

    def track(self, path, data):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        self.git("add", "--", path)
        return target

    def pages(self, data):
        self.track("text", data)
        pages = []
        offset = 0
        snapshot = None
        while True:
            frame = read_page(self.root, "text", offset, snapshot)
            self.assertLessEqual(len(frame.encode("ascii")), FRAME_BYTES)
            self.assertTrue(frame.endswith(FOOTER))
            page = json.loads(frame[:-len(FOOTER)])
            self.assertEqual(page["start"], offset)
            self.assertEqual(page["size"], len(data))
            self.assertEqual(page["sha256"], hashlib.sha256(data).hexdigest())
            self.assertLessEqual(page["end"] - offset, 1200)
            pages.append(frame)
            if page["eof"]:
                self.assertEqual(page["end"], len(data))
                return pages
            self.assertGreater(page["end"], offset)
            offset = page["end"]
            snapshot = page["snapshot"]

    def test_large_text(self):
        data = b"paragraph\r\n" * 5000
        self.assertEqual(verify_pages(self.pages(data)), data.decode())

    def test_long_line(self):
        data = b"x" * 8000
        self.assertEqual(verify_pages(self.pages(data)), data.decode())

    def test_unicode_and_escaped_characters(self):
        data = ("a" * 1199 + "é🙂漢\x00\n\\\"" * 250).encode()
        pages = self.pages(data)
        self.assertEqual(json.loads(pages[0][:-len(FOOTER)])["end"], 1199)
        self.assertEqual(verify_pages(pages), data.decode())
        with self.assertRaisesRegex(ValueError, "splits"):
            read_page(self.root, "text", 1200)

    def test_empty_and_exact_eof(self):
        self.assertEqual(verify_pages(self.pages(b"")), "")
        pages = self.pages(b"x" * 1200)
        self.assertEqual(len(pages), 1)
        self.assertEqual(verify_pages(pages), "x" * 1200)
        eof = json.loads(read_page(self.root, "text", 1200)[:-len(FOOTER)])
        self.assertEqual((eof["start"], eof["end"], eof["eof"], eof["text"]), (1200, 1200, True, ""))

    def test_changed_snapshot(self):
        data = b"a" * 1300
        pages = self.pages(data)
        snapshot = json.loads(pages[0][:-len(FOOTER)])["snapshot"]
        (self.root / "text").write_bytes(b"b" + data[1:])
        with self.assertRaisesRegex(ValueError, "snapshot changed"):
            read_page(self.root, "text", 1200, snapshot)
        current = read_page(self.root, "text", 1200)
        with self.assertRaisesRegex(ValueError, "snapshot changed"):
            verify_pages([pages[0], current])

    def test_same_content_replacement(self):
        data = b"x" * 1300
        pages = self.pages(data)
        snapshot = json.loads(pages[0][:-len(FOOTER)])["snapshot"]
        replacement = self.root / "replacement"
        replacement.write_bytes(data)
        replacement.replace(self.root / "text")
        with self.assertRaisesRegex(ValueError, "snapshot changed"):
            read_page(self.root, "text", 1200, snapshot)

    def test_reject_incomplete_or_invalid_sequence(self):
        first, middle, last = self.pages(b"x" * 2500)
        for frames in (
            [], [first, middle], [first, last], [middle, first, last],
            [first, middle, middle, last], [first, middle, last, last],
            [first, middle, last[:-1]], [first, middle, "{}" + FOOTER],
            [first, middle, last.replace("xxx", "yxx", 1)],
            [first, middle, last.replace('{"end":', '{"end":0,"end":', 1)],
        ):
            with self.subTest(lengths=list(map(len, frames))), self.assertRaises(ValueError):
                verify_pages(frames)

    def test_reject_invalid_offsets_and_encoding(self):
        self.track("text", b"abc")
        for offset in (-1, 4, True):
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                read_page(self.root, "text", offset)
        self.track("binary", b"\xff")
        with self.assertRaises(UnicodeDecodeError):
            read_page(self.root, "binary")

    def test_reject_private_untracked_and_escaping_paths(self):
        for path in ("docker/.env", "docker/private/secret", ".codex/auth.json"):
            self.track(path, b"fixture")
            with self.subTest(path=path), self.assertRaises(ValueError):
                read_page(self.root, path)
        (self.root / "untracked").write_text("fixture")
        for path in ("untracked", "missing", "../secret", "/etc/passwd", ".git/config"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                read_page(self.root, path)

    def test_reject_symlinks_and_hardlinks(self):
        target = self.track("directory/text", b"fixture")
        link = self.root / "link"
        link.symlink_to(target)
        self.git("add", "--", "link")
        with self.assertRaises(ValueError):
            read_page(self.root, "link")

        original = self.root / "original"
        target.rename(original)
        target.symlink_to(original)
        with self.assertRaises(OSError):
            read_page(self.root, "directory/text")

        target.unlink()
        target.hardlink_to(original)
        with self.assertRaises(ValueError):
            read_page(self.root, "directory/text")

        target.unlink()
        target.parent.rmdir()
        target.parent.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(OSError):
            read_page(self.root, "directory/text")
