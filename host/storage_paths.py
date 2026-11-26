"""Owner-local storage paths shared by provisioning and migration."""
import os
import stat
import sys
from pathlib import Path


def storage_paths(repo, home=None):
    home = Path.home() if home is None else home
    roots = tuple(
        Path(os.environ.get(f"PANOLAB_{role}_DIR") or
             Path(os.environ.get(xdg) or home / default) / "panolab")
        for role, xdg, default in (
            ("CONFIG", "XDG_CONFIG_HOME", ".config"),
            ("DATA", "XDG_DATA_HOME", ".local/share"),
        )
    )
    repo = Path(repo).resolve()
    for root in roots:
        if (not root.is_absolute() or root.resolve() != root or
                repo.is_relative_to(root) or root.is_relative_to(repo) or
                any(char in str(root) for char in "\n\r,:")):
            raise ValueError("Unsafe external storage path")
    if any(a.is_relative_to(b) for a, b in (roots, roots[::-1])):
        raise ValueError("External storage roots overlap")
    return roots


def check_path(path, mode, directory=False):
    info = path.lstat()
    kind = stat.S_ISDIR if directory else stat.S_ISREG
    if (path.resolve() != path or not kind(info.st_mode) or
            stat.S_IMODE(info.st_mode) != mode or
            (info.st_uid, info.st_gid) != (os.getuid(), os.getgid())):
        raise ValueError("Unexpected storage entry type, ownership or mode")
    return info


def provisioned_roots(repo):
    roots = storage_paths(repo)
    for root in roots:
        check_path(root, 0o700, directory=True)
    return roots


if __name__ == "__main__":
    try:
        print(*provisioned_roots(sys.argv[1]), sep="\n")
    except (ValueError, OSError):
        sys.exit("External PanoLab directories must be distinct owner-owned mode 0700 paths")
