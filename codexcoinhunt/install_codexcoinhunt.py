#!/usr/bin/env python3
"""Install a verified CodexCoinHunt snapshot in ~/Projects/CodexCoinHunt.

Only codex-research is managed. No project code is executed and no network,
wallet, credential, order or package-install operation is performed.
"""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
import uuid
import zipfile

PROJECT_ID = "resolant-codexcoinhunt-paper-research"
PREFIX = "CodexCoinHunt/"
MAXIMUM_BYTES = 1024 * 1024 * 1024


def safe_relative(name):
    if not isinstance(name, str) or not name or "\\" in name or "\0" in name:
        raise ValueError("invalid archive path")
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in ("", ".", "..") for part in name.split("/")):
        raise ValueError("unsafe archive path")
    return path


def validate_archive(archive):
    with zipfile.ZipFile(archive) as source:
        files = {}
        total = 0
        for info in source.infolist():
            if info.is_dir(): continue
            if not info.filename.startswith(PREFIX):
                raise ValueError("unexpected project archive prefix")
            relative = info.filename[len(PREFIX):]
            safe_relative(relative)
            if relative in files or stat.S_ISLNK(info.external_attr >> 16) or info.flag_bits & 1:
                raise ValueError("duplicate, symbolic-link or encrypted archive member")
            total += info.file_size
            if total > MAXIMUM_BYTES:
                raise ValueError("archive exceeds the one-GiB copy bound")
            files[relative] = info
        if "PROJECT_MANIFEST.json" not in files:
            raise ValueError("missing project manifest")
        manifest = json.loads(source.read(files["PROJECT_MANIFEST.json"]))
        if manifest.get("project_id") != PROJECT_ID or manifest.get("format_version") != 1:
            raise ValueError("unrecognized project manifest")
        rows = manifest.get("files")
        if not isinstance(rows, list): raise ValueError("invalid file manifest")
        expected = {}
        for row in rows:
            relative = str(safe_relative(row["file"]))
            if relative in expected: raise ValueError("duplicated manifest path")
            expected[relative] = row
        if set(files) != set(expected) | {"PROJECT_MANIFEST.json"}:
            raise ValueError("archive and manifest membership differ")
        for relative, row in expected.items():
            data = source.read(files[relative])
            if len(data) != row["bytes"] or hashlib.sha256(data).hexdigest() != row["sha256"]:
                raise ValueError("file size/hash mismatch: " + relative)
    return manifest


def install(archive, destination):
    archive = Path(archive).expanduser().absolute()
    destination = Path(destination).expanduser().absolute()
    manifest = validate_archive(archive)  # Verify before changing the destination.
    managed = destination / "codex-research"
    current = managed / "current"
    if managed.is_symlink() or current.is_symlink():
        raise ValueError("managed copy is a symbolic link; leave it untouched")
    managed.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix="incoming-", dir=managed))
    saved_previous = None
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    try:
        with zipfile.ZipFile(archive) as source:
            for info in source.infolist():
                if info.is_dir(): continue
                relative = safe_relative(info.filename[len(PREFIX):])
                target = stage.joinpath(*relative.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with source.open(info) as incoming, target.open("wb") as output:
                    shutil.copyfileobj(incoming, output)
        # Recheck materialized bytes as well as the compressed archive input.
        for row in manifest["files"]:
            target = stage / row["file"]
            if hashlib.sha256(target.read_bytes()).hexdigest() != row["sha256"]:
                raise ValueError("materialized hash mismatch")
        origin = {"project_id":PROJECT_ID,"installed_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
                  "archive_sha256":hashlib.sha256(archive.read_bytes()).hexdigest(),
                  "source_manifest_created_at_utc":manifest["created_at_utc"],
                  "copy_only":True,"existing_root_files_modified":False}
        (stage / "ORIGIN.json").write_text(json.dumps(origin, indent=2) + "\n")
        if current.exists():
            try:
                known = current.is_dir() and json.loads((current / "ORIGIN.json").read_text()).get("project_id") == PROJECT_ID
            except (OSError, ValueError): known = False
            if not known:
                imports = managed / "imports"
                if imports.is_symlink(): raise ValueError("imports path is a symbolic link")
                imports.mkdir(exist_ok=True)
                installed = imports / now
                stage.rename(installed)
                return {"status":"copied_existing_current_preserved","installed_path":str(installed),
                        "project_folder":str(destination),"previous_snapshot":None,
                        "files_verified":len(manifest["files"]),"note":"Existing current directory is unrecognized and was left untouched; use the printed imported folder."}
            snapshots = managed / "snapshots"
            if snapshots.is_symlink(): raise ValueError("snapshots path is a symbolic link")
            snapshots.mkdir(exist_ok=True)
            saved_previous = snapshots / now
            current.rename(saved_previous)
        try:
            stage.rename(current)
        except Exception:
            if saved_previous and not current.exists(): saved_previous.rename(current)
            raise
        return {"status":"installed","installed_path":str(current),"project_folder":str(destination),
                "previous_snapshot":str(saved_previous) if saved_previous else None,
                "files_verified":len(manifest["files"]),"note":"Other project/Claude files are unchanged. No code, network request or order was executed."}
    finally:
        if stage.exists(): shutil.rmtree(stage)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", nargs="?", type=Path, default=Path(__file__).with_name("CodexCoinHunt.zip"))
    parser.add_argument("--destination", type=Path, default=Path.home() / "Projects" / "CodexCoinHunt")
    args = parser.parse_args()
    try:
        result = install(args.archive, args.destination)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        parser.exit(1, "Copy stopped: " + str(error) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
