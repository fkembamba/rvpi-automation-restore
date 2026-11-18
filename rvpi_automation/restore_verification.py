
"""Read-only restoration verification for the RVPI test VM."""

import re
import subprocess
from pathlib import Path

from rvpi_automation.state_compare import compare_file_states


# Initial validation is restricted to disposable VM 130.
TEST_VMID = 130
SSH_TARGET = "kemba@10.10.70.130"

SSH_KEY = Path.home() / ".ssh" / "rvpi_restore_test-ed25519"

REFERENCE_FILE = (
    Path.home()
    / "rvpi-evidence"
    / "vm130"
    / "hostname-reference.sha256"
)

HOSTNAME_PATH = "/etc/hostname"
MARKER_PATH = "/home/kemba/rvpi-restore-marker.txt"

REMOTE_COMMAND = (
    "set -e; "
    "sha256sum /etc/hostname; "
    "if test -e /home/kemba/rvpi-restore-marker.txt; "
    "then echo MARKER_PRESENT; "
    "else echo MARKER_ABSENT; fi"
)


def parse_checksum(line):
    """Validate and extract the /etc/hostname SHA-256 checksum."""

    match = re.fullmatch(
        r"([0-9a-f]{64})\s+/etc/hostname",
        line.strip(),
    )

    if not match:
        raise ValueError("Invalid hostname checksum evidence")

    return match.group(1)


def verify_restoration(vmid=TEST_VMID):
    """Verify restored guest evidence without changing the VM."""

    if type(vmid) is not int or vmid != TEST_VMID:
        raise ValueError("Only disposable VM 130 is approved")

    if not SSH_KEY.is_file():
        raise FileNotFoundError(f"SSH key not found: {SSH_KEY}")

    if not REFERENCE_FILE.is_file():
        raise FileNotFoundError(
            f"Baseline evidence not found: {REFERENCE_FILE}"
        )

    expected_hash = parse_checksum(
        REFERENCE_FILE.read_text(encoding="utf-8")
    )

    result = subprocess.run(
        [
            "ssh",
            "-i", str(SSH_KEY),
            "-o", "BatchMode=yes",
            "-o", "IdentitiesOnly=yes",
            "-o", "StrictHostKeyChecking=yes",
            "-o", "ConnectTimeout=5",
            SSH_TARGET,
            REMOTE_COMMAND,
        ],
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
    )

    lines = result.stdout.strip().splitlines()

    if len(lines) != 2:
        raise ValueError("Unexpected SSH evidence response")

    observed_hash = parse_checksum(lines[0])
    marker_status = lines[1].strip()

    if marker_status not in ("MARKER_PRESENT", "MARKER_ABSENT"):
        raise ValueError("Invalid marker verification response")

    reference = [
        {
            "path": HOSTNAME_PATH,
            "exists": True,
            "size_bytes": None,
            "sha256": expected_hash,
        },
        {
            "path": MARKER_PATH,
            "exists": False,
            "size_bytes": None,
            "sha256": None,
        },
    ]

    observed = [
        {
            "path": HOSTNAME_PATH,
            "exists": True,
            "size_bytes": None,
            "sha256": observed_hash,
        },
        {
            "path": MARKER_PATH,
            "exists": marker_status == "MARKER_PRESENT",
            "size_bytes": None,
            "sha256": None,
        },
    ]

    comparison = compare_file_states(reference, observed)

    return {
        "vmid": vmid,
        "target": SSH_TARGET,
        "baseline": "baseline-clean",
        "verification_status": (
            "PASS" if comparison["status"] == "MATCH" else "FAIL"
        ),
        "hostname_sha256_match": expected_hash == observed_hash,
        "post_snapshot_marker_absent": (
            marker_status == "MARKER_ABSENT"
        ),
        "differences": comparison["differences"],
        "changes_applied": False,
    }
