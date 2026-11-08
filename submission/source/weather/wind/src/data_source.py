"""Explicit, checksum-verified competition archive selection."""
import hashlib
import json
from pathlib import Path


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def competition_archive(root):
    root = Path(root).resolve()
    config = json.loads((root / "config/data_source.json").read_text(encoding="utf-8"))
    archive = (root / config["archive_filename"]).resolve()
    if archive.parent != root or archive.suffix.lower() != ".zip":
        raise ValueError("Competition ZIP must be directly inside project root")
    if not archive.is_file():
        raise FileNotFoundError(f"Pinned competition archive missing: {archive.name}")
    if sha256_file(archive) != config["sha256"]:
        raise ValueError("Competition archive checksum changed. Audit the new release and rebuild caches before updating config/data_source.json.")
    return archive
