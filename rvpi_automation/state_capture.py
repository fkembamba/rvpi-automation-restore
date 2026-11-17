
"""Read-only file-state evidence capture for RVPI restoration tests."""

import hashlib
from pathlib import Path


def capture_file_state(file_paths):
    """Record file existence, size, and SHA-256 without modifying files."""

    if not isinstance(file_paths, (list, tuple)) or not file_paths:
        raise ValueError("Provide a non-empty list of file paths")

    evidence = []

    for filename in file_paths:
        if not isinstance(filename, (str, Path)) or not str(filename).strip():
            raise ValueError("Each file path must be non-empty")

        path = Path(filename)

        if path.is_symlink():
            raise ValueError(f"Symbolic links are not supported: {path}")

        if not path.exists():
            evidence.append({
                "path": str(path),
                "exists": False,
                "size_bytes": None,
                "sha256": None,
            })
            continue

        if not path.is_file():
            raise ValueError(f"Not a regular file: {path}")

        digest = hashlib.sha256()
        size = 0

        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
                size += len(chunk)

        evidence.append({
            "path": str(path),
            "exists": True,
            "size_bytes": size,
            "sha256": digest.hexdigest(),
        })

    return evidence
