
"""Read-only Linux restoration verification for approved RVPI VMs."""

import re
import shlex
import subprocess
from pathlib import Path

from rvpi_automation.restore_policy import get_restore_target
from rvpi_automation.state_compare import compare_file_states


TEST_VMID = 130  # Backward-compatible default for existing tests.


def parse_checksum(line, hostname_path="/etc/hostname"):
    """Validate and extract a hostname SHA-256 checksum."""

    pattern = r"([0-9a-f]{64})\s+" + re.escape(hostname_path)

    match = re.fullmatch(pattern, line.strip())

    if not match:
        raise ValueError("Invalid hostname checksum evidence")

    return match.group(1)


def verify_restoration(vmid=TEST_VMID):
    """Verify an approved Linux VM without changing guest state."""

    # 1. Verify that the target is approved.
    target = get_restore_target(vmid)
    verification = target["verification"]

    if verification["method"] != "linux-ssh":
        raise ValueError(
            "Unsupported restoration verification method"
        )

    ssh_target = verification["ssh_target"]
    ssh_key = Path(verification["ssh_key"]).expanduser()
    reference_path = Path(
        verification["reference_file"]
    ).expanduser()

    hostname_path = verification["hostname_path"]
    marker_path = verification["marker_path"]

    # 2. Validate verification configuration.
    if not isinstance(ssh_target, str) or not ssh_target:
        raise ValueError("Invalid SSH target")

    for path in (hostname_path, marker_path):
        if (
            not isinstance(path, str)
            or not path.startswith("/")
            or "\n" in path
            or "\r" in path
        ):
            raise ValueError("Invalid verification file path")

    if hostname_path == marker_path:
        raise ValueError(
            "Hostname and marker paths must differ"
        )

    if not ssh_key.is_file():
        raise FileNotFoundError(
            f"SSH key not found: {ssh_key}"
        )

    if not reference_path.is_file():
        raise FileNotFoundError(
            f"Baseline evidence not found: {reference_path}"
        )

    # 3. Read the expected baseline checksum.
    expected_hash = parse_checksum(
        reference_path.read_text(encoding="utf-8"),
        hostname_path,
    )

    # 4. Build the VM-specific, read-only SSH command.
    safe_hostname = shlex.quote(hostname_path)
    safe_marker = shlex.quote(marker_path)

    remote_command = (
        "set -e; "
        f"sha256sum -- {safe_hostname}; "
        f"if test -e {safe_marker}; "
        "then echo MARKER_PRESENT; "
        "else echo MARKER_ABSENT; fi"
    )

    # 5. Collect evidence from the restored VM.
    result = subprocess.run(
        [
            "ssh",
            "-i", str(ssh_key),
            "-o", "BatchMode=yes",
            "-o", "IdentitiesOnly=yes",
            "-o", "StrictHostKeyChecking=yes",
            "-o", "ConnectTimeout=5",
            ssh_target,
            remote_command,
        ],
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
    )

    lines = result.stdout.strip().splitlines()

    if len(lines) != 2:
        raise ValueError(
            "Unexpected SSH evidence response"
        )

    observed_hash = parse_checksum(
        lines[0],
        hostname_path,
    )

    marker_status = lines[1].strip()

    if marker_status not in (
        "MARKER_PRESENT",
        "MARKER_ABSENT",
    ):
        raise ValueError(
            "Invalid marker verification response"
        )

    # 6. Compare the observed state with the baseline.
    reference = [
        {
            "path": hostname_path,
            "exists": True,
            "size_bytes": None,
            "sha256": expected_hash,
        },
        {
            "path": marker_path,
            "exists": False,
            "size_bytes": None,
            "sha256": None,
        },
    ]

    observed = [
        {
            "path": hostname_path,
            "exists": True,
            "size_bytes": None,
            "sha256": observed_hash,
        },
        {
            "path": marker_path,
            "exists": marker_status == "MARKER_PRESENT",
            "size_bytes": None,
            "sha256": None,
        },
    ]

    comparison = compare_file_states(
        reference,
        observed,
    )

    # 7. Return verification evidence.
    return {
        "vmid": vmid,
        "target": ssh_target,
        "baseline": target["baseline"],
        "verification_status": (
            "PASS"
            if comparison["status"] == "MATCH"
            else "FAIL"
        ),
        "hostname_sha256_match": (
            expected_hash == observed_hash
        ),
        "post_snapshot_marker_absent": (
            marker_status == "MARKER_ABSENT"
        ),
        "differences": comparison["differences"],
        "changes_applied": False,
    }
