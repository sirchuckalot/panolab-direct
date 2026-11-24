#!/usr/bin/env python3
"""Git askpass for the one PanoLab Git gateway, never a general credential helper.

Only invoked for an already allowlisted GitHub development push.
Token bytes are returned on askpass stdout directly to Git (not to the agent).
"""
import os
from pathlib import Path
import re
import stat
import sys

SECRET = Path("/run/panolab-git-auth/github-push-token")

def main():
    if len(sys.argv) != 2:
        return 1
    prompt = sys.argv[1]
    if not re.search(r"for 'https://(?:[^@/' ]+@)?github\.com(?:/[^']*)?':?\s*$", prompt):
        return 1
    if prompt.startswith("Username "):
        os.write(1, b"x-access-token\n")
        return 0
    if not prompt.startswith("Password "):
        return 1
    try:
        info = SECRET.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
            return 1
        token = SECRET.read_text(encoding="ascii").rstrip("\r\n")
        if not re.fullmatch(r"github_pat_[A-Za-z0-9_]{20,}", token):
            return 1
    except (OSError, UnicodeError):
        return 1
    os.write(1, token.encode("ascii") + b"\n")
    return 0

if __name__ == "__main__":
    sys.exit(main())
