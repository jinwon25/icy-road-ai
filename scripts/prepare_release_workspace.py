"""원본·기존 캐시를 보존하고 새 배포본용 빈 작업 복사본을 만든다."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file
from src.observation_io import daily_members


def prepare_workspace(root: Path, archive: Path, release: str) -> Path:
    if not re.fullmatch(r"\d{8}", release):
        raise ValueError("Release must be YYYYMMDD")
    root, archive = root.resolve(), archive.resolve()
    if not archive.is_file() or archive.suffix.lower() != ".zip":
        raise ValueError("A local competition ZIP is required")
    destination = root / "outputs/private/releases" / release
    if destination.exists():
        raise FileExistsError(f"Workspace already exists: {destination}")
    with zipfile.ZipFile(archive) as zipped:
        for kind in ("RWIS", "ASOS", "AWS"):
            daily_members(zipped, kind)
    checksum = sha256_file(archive)
    destination.mkdir(parents=True)
    for name in ("src", "scripts", "tests", "config", "notebooks", "docs", ".github"):
        if (root / name).is_dir():
            shutil.copytree(root / name, destination / name,
                            ignore=shutil.ignore_patterns("__pycache__", ".ipynb_checkpoints", "*.pyc"))
    for name in ("README.md", "AI_USAGE.md", "requirements.txt"):
        if (root / name).is_file():
            shutil.copy2(root / name, destination / name)
    shutil.copy2(archive, destination / archive.name)
    if sha256_file(destination / archive.name) != checksum:
        raise ValueError("Copied archive checksum mismatch")
    config = {
        "schema_version": 1, "archive_filename": archive.name, "sha256": checksum,
        "bytes": archive.stat().st_size, "release": release,
        "status": "isolated_release_pending_audit",
        "migration": "Fresh workspace; no caches copied. Audit before rebuilding features and models."
    }
    (destination / "config").mkdir(exist_ok=True)
    (destination / "config/data_source.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {"release": release, "archive_sha256": checksum, "old_outputs_copied": False,
                "source_files": {str(p.relative_to(destination)).replace("\\", "/"): sha256_file(p)
                                 for directory in ("src", "scripts", "config")
                                 for p in (destination / directory).rglob("*") if p.is_file()}}
    (destination / "workspace_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--release", required=True)
    args = parser.parse_args()
    print(prepare_workspace(ROOT, args.archive, args.release))
