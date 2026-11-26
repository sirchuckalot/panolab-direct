"""Read a tracked UTF-8 file with: python agent/text_page.py PATH [OFFSET].

Pass --snapshot from the first frame for subsequent reads. Feed the complete
frame sequence to verify_pages before relying on the reconstructed text.
"""

import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess


PAGE_BYTES = 1200
FRAME_BYTES = 1600
FOOTER = "\nEND TEXT PAGE\n"


def _json(value):
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _read_tracked(root, path):
    parts = path.split("/")
    if any(
        part.lower() in {"", ".", "..", ".git", "private", ".codex"}
        or part.lower().startswith(".env")
        or "\x00" in part
        or "\\" in part
        for part in parts
    ):
        raise ValueError("path must name a public repository file")

    indexed = subprocess.run(
        ["git", "--literal-pathspecs", "-C", root, "ls-files", "--stage", "-z", "--", path],
        check=True, capture_output=True,
    ).stdout
    metadata, _, indexed_path = indexed.partition(b"\t")
    fields = metadata.split()
    if (
        indexed_path != os.fsencode(path) + b"\0"
        or len(fields) != 3
        or fields[0] not in {b"100644", b"100755"}
        or fields[2] != b"0"
    ):
        raise ValueError("path must name a tracked regular file")

    with ExitStack() as stack:
        directory_flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY
        directory = os.open(root, directory_flags)
        stack.callback(os.close, directory)
        for part in parts[:-1]:
            directory = os.open(part, directory_flags, dir_fd=directory)
            stack.callback(os.close, directory)
        fd = os.open(
            parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory,
        )
        with os.fdopen(fd, "rb") as file:
            before = os.fstat(file.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise ValueError("path must name an unaliased regular file")
            data = file.read()
            after = os.fstat(file.fileno())
            current = os.stat(parts[-1], dir_fd=directory, follow_symlinks=False)
            if _identity(before) != _identity(after) or _identity(after) != _identity(current):
                raise ValueError("file changed during read")
            if len(data) != before.st_size:
                raise ValueError("file size changed during read")
    return data, _identity(before)


def read_page(root, path, offset=0, snapshot=None):
    """Return one complete ASCII frame. Offsets count source UTF-8 bytes."""
    if type(offset) is not int or offset < 0:
        raise ValueError("invalid byte offset")
    data, identity = _read_tracked(root, path)
    data.decode("utf-8")
    digest = _sha(data)
    version = _sha(_json([path, identity, digest]).encode("ascii"))
    if snapshot is not None and snapshot != version:
        raise ValueError("file snapshot changed")
    if offset > len(data):
        raise ValueError("offset past EOF")
    if offset < len(data) and data[offset] & 0xC0 == 0x80:
        raise ValueError("offset splits a UTF-8 character")

    window = data[offset:offset + PAGE_BYTES].decode("utf-8", errors="ignore")
    chars = []
    byte_count = 0
    encoded_count = 0
    for char in window:
        encoded_count += len(_json(char)) - 2
        if encoded_count > PAGE_BYTES:
            break
        chars.append(char)
        byte_count += len(char.encode("utf-8"))
    end = offset + byte_count
    frame = _json({
        "start": offset, "end": end, "size": len(data), "eof": end == len(data),
        "sha256": digest, "snapshot": version, "text": "".join(chars),
    }) + FOOTER
    if len(frame) > FRAME_BYTES:
        raise ValueError("frame exceeds output limit")
    return frame


def verify_pages(frames):
    """Return the reconstructed text only after validating the full sequence."""
    position = 0
    digest = hashlib.sha256()
    identity = None
    eof = False
    chunks = []
    for frame in frames:
        if eof or len(frame) > FRAME_BYTES or not frame.endswith(FOOTER):
            raise ValueError("unexpected, oversized, or truncated frame")
        body = frame[:-len(FOOTER)]
        page = json.loads(body)
        if (
            not isinstance(page, dict)
            or page.keys() != {"start", "end", "size", "eof", "sha256", "snapshot", "text"}
            or _json(page) != body
            or any(type(page[key]) is not int for key in ("start", "end", "size"))
            or type(page["eof"]) is not bool
            or not isinstance(page["text"], str)
        ):
            raise ValueError("invalid page fields")
        for key in ("sha256", "snapshot"):
            value = page[key]
            if not isinstance(value, str) or len(value) != 64 or any(
                char not in "0123456789abcdef" for char in value
            ):
                raise ValueError("invalid digest")
        current = (page["size"], page["sha256"], page["snapshot"])
        if identity is None:
            identity = current
        if current != identity:
            raise ValueError("file snapshot changed between pages")

        content = page["text"].encode("utf-8")
        end = position + len(content)
        eof = page["eof"]
        if (
            page["start"] != position or page["end"] != end or end > page["size"]
            or eof != (end == page["size"])
            or (not content and (position != 0 or not eof))
            or len(_json(page["text"])) - 2 > PAGE_BYTES
        ):
            raise ValueError("invalid or noncontiguous page range")
        position = end
        digest.update(content)
        chunks.append(page["text"])
    if not eof or digest.hexdigest() != identity[1]:
        raise ValueError("missing EOF or whole-file digest mismatch")
    return "".join(chunks)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path")
    parser.add_argument("offset", type=int, nargs="?", default=0)
    parser.add_argument("--snapshot")
    args = parser.parse_args()
    try:
        frame = read_page(Path(__file__).resolve().parents[1], args.path, args.offset, args.snapshot)
    except UnicodeDecodeError:
        parser.exit(1, "text page failed: file is not valid UTF-8\n")
    except ValueError as error:
        parser.exit(1, f"text page failed: {error}\n")
    except OSError as error:
        parser.exit(1, f"text page failed: filesystem error {error.errno}\n")
    except subprocess.CalledProcessError as error:
        parser.exit(1, f"text page failed: Git index lookup exited {error.returncode}\n")
    print(frame, end="")


if __name__ == "__main__":
    main()
