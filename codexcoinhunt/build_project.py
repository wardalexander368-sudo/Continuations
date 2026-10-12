#!/usr/bin/env python3
"""Build verified portable copies using local project files only."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import uuid
import zipfile

PROJECT_ID = "resolant-codexcoinhunt-paper-research"


def included(path, root):
    parts = path.relative_to(root).parts
    return (path.is_file() and not path.is_symlink()
            and "__pycache__" not in parts and path.suffix != ".pyc"
            and ".git" not in parts and "ORIGIN.json" not in parts)


def rows(root, excluded):
    result = []
    for path in sorted(root.rglob("*")):
        if included(path, root) and path.relative_to(root).as_posix() not in excluded:
            body = path.read_bytes()
            result.append({"file": path.relative_to(root).as_posix(), "bytes": len(body),
                           "sha256": hashlib.sha256(body).hexdigest()})
    return result


def write_text_if_changed(path, content):
    """Avoid changing archive metadata when generated content is identical."""
    if path.exists() and path.read_text() == content:
        return
    path.write_text(content)


def write_zip(root, destination, members, prefix):
    stage = destination.with_name(destination.name + "." + uuid.uuid4().hex + ".building")
    try:
        with zipfile.ZipFile(stage, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as output:
            for relative in members:
                output.write(root / relative, prefix + "/" + relative)
        with zipfile.ZipFile(stage) as output:
            bad = output.testzip()
            if bad: raise ValueError("archive CRC mismatch: " + bad)
        os.replace(stage, destination)
    finally:
        if stage.exists(): stage.unlink()


def build(root, project_archive, kit_archive):
    root = root.resolve()
    project_archive = project_archive.resolve()
    kit_archive = kit_archive.resolve()
    for archive in (project_archive, kit_archive):
        if archive == root or root in archive.parents:
            raise ValueError("write archives outside the project folder")
    research = root / "research"
    if not research.is_dir(): raise ValueError("missing research folder")
    research_rows = rows(research, {"manifest.json"})
    write_text_if_changed(research / "manifest.json", json.dumps(research_rows, indent=2) + "\n")
    write_zip(research, kit_archive, [row["file"] for row in research_rows] + ["manifest.json"],
              "Resolant_Memecoin_Research_Kit")
    project_rows = rows(root, {"PROJECT_MANIFEST.json"})
    manifest = {"format_version": 1, "project_id": PROJECT_ID,
                "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                "strategy_sha256": hashlib.sha256((research / "strategy.json").read_bytes()).hexdigest(),
                "files": project_rows}
    (root / "PROJECT_MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    write_zip(root, project_archive, [row["file"] for row in project_rows] + ["PROJECT_MANIFEST.json"],
              "CodexCoinHunt")
    return {"project": str(project_archive), "project_files": len(project_rows),
            "project_sha256": hashlib.sha256(project_archive.read_bytes()).hexdigest(),
            "research_kit": str(kit_archive), "research_files": len(research_rows),
            "research_sha256": hashlib.sha256(kit_archive.read_bytes()).hexdigest(),
            "strategy_sha256": manifest["strategy_sha256"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--project-archive", type=Path)
    parser.add_argument("--kit-archive", type=Path)
    args = parser.parse_args()
    root = args.project.resolve()
    result = build(root, args.project_archive or root.parent / "CodexCoinHunt.zip",
                   args.kit_archive or root.parent / "Resolant_Memecoin_Research_Kit.zip")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
