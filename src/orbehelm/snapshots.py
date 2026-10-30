"""Content-addressed filesystem snapshots with no web or ORM dependencies."""
import json
import os
from pathlib import Path
import tempfile

from .core import OrbeHelmError, canonical, contained, digest

MAX_FILE = 2 * 1024 * 1024
MAX_TREE = 64 * 1024 * 1024
MAX_FILES = 4096


def capture_file(root, relative, result):
    parts = Path(relative).parts
    if not parts or Path(relative).is_absolute() or any(part.startswith('.') for part in parts) or parts[0] in {'state', 'generated', 'legacy'}:
        raise OrbeHelmError(f'Not an allowed source path: {relative}')
    path = contained(root, relative)
    current = Path(root)
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise OrbeHelmError(f"Snapshot symlinks are not supported: {relative}")
    if path.is_symlink():
        raise OrbeHelmError(f"Snapshot symlinks are not supported: {relative}")
    # Interpreter caches are reproducible runtime output, never candidate source.
    if '__pycache__' in parts or path.suffix in {'.pyc', '.pyo'}:
        return
    try:
        data = path.read_bytes()
    except OSError as error:
        raise OrbeHelmError(f'Cannot read source {relative}: {error.strerror}') from error
    if len(data) > MAX_FILE:
        raise OrbeHelmError(f"Source exceeds {MAX_FILE} bytes: {relative}")
    result[relative] = {"content": data, "executable": bool(path.stat().st_mode & 0o111)}
    if len(result) > MAX_FILES or sum(len(x["content"]) for x in result.values()) > MAX_TREE:
        raise OrbeHelmError("Source snapshot exceeds size limit")


def manifest(files):
    return {name: {"sha256": digest(item["content"]), "executable": item["executable"]}
            for name, item in sorted(files.items())}


def snapshot_path(root, snapshot):
    if not isinstance(snapshot, str) or len(snapshot) != 64 or any(c not in '0123456789abcdef' for c in snapshot):
        raise OrbeHelmError("Invalid snapshot hash")
    base = Path(root).resolve()
    for path in (base / 'state', base / 'state/revisions', base / 'state/revisions' / snapshot):
        if path.is_symlink():
            raise OrbeHelmError('Snapshot directories must not be symlinks')
    return contained(root, f"state/revisions/{snapshot}/files")


def save_snapshot(root, files):
    if len(files) > MAX_FILES or sum(len(item['content']) for item in files.values()) > MAX_TREE:
        raise OrbeHelmError('Source snapshot exceeds size limit')
    listing = manifest(files)
    key = digest(canonical(listing).encode())
    target = snapshot_path(root, key)
    if target.exists():
        verify_snapshot(root, key)
        return key
    parent = target.parent.parent
    parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=parent, prefix=".snapshot-") as tmp:
        staged = Path(tmp) / "snapshot"
        (staged / "files").mkdir(parents=True)
        for name, item in files.items():
            path = contained(staged / "files", name)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("wb") as handle:
                handle.write(item["content"])
                handle.flush()
                os.fsync(handle.fileno())
            path.chmod(0o755 if item["executable"] else 0o644)
        (staged / "manifest.json").write_text(canonical(listing), encoding="utf-8")
        staged.rename(target.parent)
    return key


def verify_snapshot(root, key):
    target = snapshot_path(root, key)
    expected = json.loads((target.parent / "manifest.json").read_text())
    if digest(canonical(expected).encode()) != key:
        raise OrbeHelmError(f"Corrupted snapshot manifest: {key}")
    actual = {}
    for path in target.rglob("*"):
        if path.is_symlink():
            raise OrbeHelmError("Snapshot contains a symlink")
        if path.is_file():
            actual[path.relative_to(target).as_posix()] = {
                "sha256": digest(path.read_bytes()), "executable": bool(path.stat().st_mode & 0o111)}
    if actual != expected:
        raise OrbeHelmError(f"Corrupted source snapshot: {key}")
    return target
