"""Move public downloads into the native Files tree; legacy paths become aliases."""

import hashlib
import shutil
from pathlib import Path


def same_file(left, right):
    if left.is_symlink() or right.is_symlink():
        return left.is_symlink() and right.is_symlink() and left.readlink() == right.readlink()
    if left.stat().st_size != right.stat().st_size:
        return False

    def digest(path):
        result = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                result.update(block)
        return result.digest()

    return digest(left) == digest(right)


def merge_files(source, target, archive):
    source, target = Path(source), Path(target)
    if not source.exists() or source.is_symlink() or source.resolve() == target.resolve():
        return
    target.mkdir(parents=True, exist_ok=True)
    for entry in list(source.iterdir()):
        destination = target / entry.name
        if entry.is_dir() and not entry.is_symlink():
            merge_files(entry, destination, archive / entry.name)
        elif not destination.exists() and not destination.is_symlink():
            shutil.move(str(entry), destination)
        elif same_file(entry, destination):
            entry.unlink()
        else:
            # Different cache pointers/metadata or user documents are preserved,
            # never overwritten. The preferred install's pointer stays active.
            archive.mkdir(parents=True, exist_ok=True)
            saved = archive / entry.name
            if saved.exists() or saved.is_symlink():
                raise ValueError(f"Storage migration conflict: {saved}")
            shutil.move(str(entry), saved)
    source.rmdir()


def prepare_storage(core, deploy, files):
    files.mkdir(parents=True, exist_ok=True)
    for folder, legacy in [("Reports", "reports"), ("Prices", "prices"), ("Models", "models")]:
        target = files / "OilAgent" / folder
        target.mkdir(parents=True, exist_ok=True)
        # Prefer the running container installation; preserve older host pointers.
        for label, old in [("container", deploy / legacy), ("host", core / "workspace" / legacy)]:
            if old.is_symlink():
                if old.resolve() == target.resolve():
                    continue
                raise ValueError(f"Inspect existing storage alias before migration: {old}")
            if old.exists():
                merge_files(old, target, files / "Imports" / label / folder)
            old.parent.mkdir(parents=True, exist_ok=True)
            old.symlink_to(target.resolve(), target_is_directory=True)
    for label, old in [
        ("container", deploy / "container-native/user_files"),
        ("host", core / "workspace/ouroboros-runtime/user_files"),
    ]:
        if old.exists() and not old.is_symlink() and any(old.iterdir()):
            merge_files(old, files, files / "Imports" / label / "UserFiles")
        if not old.exists():
            old.parent.mkdir(parents=True, exist_ok=True)
            if label == "container":
                old.mkdir()  # Real mountpoint for the nested native Files bind mount.
            else:
                old.symlink_to(files.resolve(), target_is_directory=True)
