
"""Compare file-state evidence for RVPI restoration verification."""


def compare_file_states(reference, observed):
    """Compare baseline and observed file-state records."""

    def index_records(records):
        if not isinstance(records, list):
            raise ValueError("Evidence must be a list")

        indexed = {}

        for record in records:
            if not isinstance(record, dict):
                raise ValueError("Invalid evidence record")

            required = {"path", "exists", "size_bytes", "sha256"}
            if not required.issubset(record):
                raise ValueError("Incomplete evidence record")

            path = record["path"]

            if not isinstance(path, str) or not path.strip():
                raise ValueError("Invalid evidence path")

            if path in indexed:
                raise ValueError(f"Duplicate evidence path: {path}")

            indexed[path] = record

        return indexed

    if not reference:
        raise ValueError("Baseline reference evidence is required")

    baseline = index_records(reference)
    current = index_records(observed)

    differences = []

    for path in sorted(set(baseline) | set(current)):
        expected = baseline.get(path)
        actual = current.get(path)

        if expected is None or actual is None:
            differences.append({
                "path": path,
                "reason": "MISSING_EVIDENCE"
            })
            continue

        fields = ("exists", "size_bytes", "sha256")

        for field in fields:
            if expected[field] != actual[field]:
                differences.append({
                    "path": path,
                    "field": field,
                    "expected": expected[field],
                    "actual": actual[field]
                })

    return {
        "status": "MATCH" if not differences else "MISMATCH",
        "files_checked": len(baseline),
        "differences": differences
    }
