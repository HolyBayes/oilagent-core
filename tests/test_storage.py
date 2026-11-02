import importlib.util

from analyst.config import CORE_ROOT


def storage_module():
    spec = importlib.util.spec_from_file_location(
        "prepare_storage", CORE_ROOT / "scripts/prepare_storage.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_downloads_move_to_native_files_without_duplicate_copies(tmp_path):
    core = tmp_path / "core"
    deploy = core / "workspace/container"
    files = core / "workspace/files"
    old = deploy / "reports"
    old.mkdir(parents=True)
    (old / "report.pdf").write_bytes(b"public report")
    host = core / "workspace/reports"
    host.mkdir()
    (host / "report.pdf").write_bytes(b"public report")
    native = deploy / "container-native/user_files"
    native.mkdir(parents=True)
    (native / "uploaded.csv").write_text("date,price\n2026-01-01,70\n")
    module = storage_module()
    module.prepare_storage(core, deploy, files)
    target = files / "OilAgent/Reports/report.pdf"
    assert target.read_bytes() == b"public report"
    assert old.is_symlink() and host.is_symlink()
    assert (old / "report.pdf").samefile(target)
    assert (host / "report.pdf").samefile(target)
    assert (files / "uploaded.csv").is_file()
    assert native.is_dir() and not native.is_symlink() and not list(native.iterdir())
    mount_inode = native.stat().st_ino
    module.prepare_storage(core, deploy, files)
    assert native.stat().st_ino == mount_inode
    assert len(list(files.rglob("report.pdf"))) == 1


def test_conflicting_cache_pointer_is_preserved_not_overwritten(tmp_path):
    module = storage_module()
    core = tmp_path / "core"
    deploy = core / "workspace/container"
    files = core / "workspace/files"
    for folder, value in [
        (deploy / "prices", "container snapshot"),
        (core / "workspace/prices", "host snapshot"),
    ]:
        folder.mkdir(parents=True)
        (folder / "index.json").write_text(value)
    module.prepare_storage(core, deploy, files)
    assert (files / "OilAgent/Prices/index.json").read_text() == "container snapshot"
    assert (files / "Imports/host/Prices/index.json").read_text() == "host snapshot"
