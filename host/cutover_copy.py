"""Verified cross-bind storage transfer for a quiesced cutover."""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess

STALE_SOCKET = "repo-rpc/panolab-git.sock"


def lexists(path):
    return os.path.lexists(path)


def manifest(entries):
    """Hash tree structure, contents, metadata and relative hardlink groups."""
    files = {}
    links = {}
    root_devices = {}

    def walk(path, relative, group):
        info = path.lstat()
        if info.st_dev != root_devices[group]:
            raise ValueError("Nested filesystem in storage")
        mode = info.st_mode
        if stat.S_ISSOCK(mode) and relative == STALE_SOCKET:
            return
        item = [mode, info.st_uid, info.st_gid, info.st_mtime_ns,
                [(key, os.getxattr(path, key, follow_symlinks=False).hex())
                 for key in sorted(os.listxattr(path, follow_symlinks=False))]]
        if not stat.S_ISDIR(mode):
            key = (info.st_dev, info.st_ino)
            link = links.setdefault(key, (info.st_nlink, group, []))
            if link[1] != group:
                raise ValueError("Hardlink crosses destination binds")
            link[2].append(relative)
        if stat.S_ISREG(mode):
            with path.open("rb") as stream:
                item.extend((info.st_size, hashlib.file_digest(stream, "sha256").hexdigest()))
        elif stat.S_ISLNK(mode):
            item.append(os.readlink(path))
        elif not stat.S_ISDIR(mode):
            raise ValueError("Unapproved special storage entry")
        files[relative] = item
        if stat.S_ISDIR(mode):
            for child in sorted(path.iterdir()):
                walk(child, relative + "/" + child.name, group)

    for path, name, group in entries:
        root_devices.setdefault(group, path.parent.stat().st_dev)
        walk(path, name, group)
    for count, _, names in links.values():
        if count != len(names):
            raise ValueError("Hardlink extends outside inventoried storage")
        if count > 1:
            for name in names:
                files[name].append(sorted(names))
    return hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()


def copy_groups(source, destination):
    """Copy each group in one invocation so cp retains cross-entry hardlinks."""
    for group in dict.fromkeys(group for _, _, group in source):
        inputs = [path for path, _, root in source if root == group]
        outputs = [path for path, _, root in destination if root == group]
        parents = {p.parent for p in outputs}
        if len(parents) != 1 or [p.name for p in inputs] != [p.name for p in outputs]:
            raise ValueError("Copy requires a common staging directory")
        target = outputs[0].parent
        rpc = next((p for p in inputs if p.name == "repo-rpc"), None)
        socket = rpc / "panolab-git.sock" if rpc else None
        command = ["cp", "-a", "-t", str(target)]
        kwargs = {}
        if socket and lexists(socket) and stat.S_ISSOCK(socket.lstat().st_mode):
            # The original gateway is stopped. Omit only its exact stale socket.
            (target / rpc.name).mkdir(mode=0o700)
            inputs = [p.relative_to(rpc.parent) for p in inputs if p != rpc]
            inputs.extend(p.relative_to(rpc.parent) for p in rpc.iterdir() if p != socket)
            command.append("--parents")
            kwargs["cwd"] = rpc.parent
        subprocess.run([*command, "--", *inputs], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kwargs)
        if kwargs:
            shutil.copystat(rpc, target / rpc.name)


def remove_entry(path):
    if not lexists(path):
        return
    if stat.S_ISDIR(path.lstat().st_mode):
        shutil.rmtree(path)
    else:
        path.unlink()


def sync_filesystem(path):
    libc = ctypes.CDLL(None, use_errno=True)
    fd = os.open(path, os.O_DIRECTORY)
    try:
        if libc.syncfs(fd):
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error))
    finally:
        os.close(fd)


def entries(plan, forward):
    return [(new if forward else old, new.name, new.parent) for old, new in plan]


def verify_link_relocation(plan):
    def logical_target(target, side):
        for old, new in plan:
            root = (old, new)[side]
            if target.is_relative_to(root):
                return new.name, target.relative_to(root)
        return target

    def visit(path, destination):
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode):
            link = os.readlink(path)
            old_target = Path(os.path.normpath(path.parent / link))
            new_target = Path(os.path.normpath(destination.parent / link))
            if logical_target(old_target, 0) != logical_target(new_target, 1):
                raise ValueError("Symlink target changes across storage layouts")
        elif stat.S_ISDIR(mode):
            for child in path.iterdir():
                visit(child, destination / child.name)

    for old, new in plan:
        visit(old, new)


def copy_external(plan):
    verify_link_relocation(plan)
    source = entries(plan, False)
    destination = entries(plan, True)
    expected = manifest(source)
    copy_groups(source, destination)
    for root in {path.parent for path, _, _ in destination}:
        sync_filesystem(root)
    if manifest(destination) != expected or manifest(source) != expected:
        raise ValueError("Copied storage verification failed")
    return expected


def restore_legacy(plan, stage, expected, rename, legacy, phase):
    source = entries(plan, True)
    if manifest(source) != expected:
        raise ValueError("External storage identity differs during recovery")
    staged = [(stage / path.name, name, group) for path, name, group in source]
    if phase == "restoring":
        remove_entry(stage)
        stage.mkdir(mode=0o700)
        for old, _ in plan:
            remove_entry(old)
        sync_filesystem(stage.parent)
        copy_groups(source, staged)
        if manifest(staged) != expected or manifest(source) != expected:
            raise ValueError("Restored storage staging verification failed")
        sync_filesystem(stage)
    # The caller journals the staging verification before replacing any legacy entries.
    if phase != "installing-restore":
        return
    if not legacy.exists():
        legacy.mkdir(mode=0o700)
    installed = []
    for old, new in plan:
        staged_path = stage / new.name
        old_present, staged_present = lexists(old), lexists(staged_path)
        if old_present == staged_present:
            raise ValueError("Conflicting or missing rollback entry")
        installed.append((staged_path if staged_present else old, new.name, new.parent))
    if manifest(installed) != expected:
        raise ValueError("Interrupted restore does not match the verified copy")
    for old, new in plan:
        staged_path = stage / new.name
        if lexists(staged_path):
            rename(staged_path, old)
    sync_filesystem(legacy.parent)
    if manifest(entries(plan, False)) != expected:
        raise ValueError("Restored legacy storage verification failed")
    if stage.exists():
        stage.rmdir()
    sync_filesystem(stage.parent)
