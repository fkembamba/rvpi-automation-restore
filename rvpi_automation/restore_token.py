
"""Read-only authentication check for the RVPI restoration API token."""

import json
import ssl
import urllib.request
from pathlib import Path


TOKEN_ID = "rvpi-restore@pve!rollback130"
TOKEN_FILE = (
    Path.home()
    / ".config/rvpi-automation/restore-exec/rollback130-token.json"
)
CA_CERT = Path.home() / "pve-root-ca.pem"

PVE_URL = "https://pve.aicyber.rw:8006"
TEST_VMID = 130


def check_restore_token():
    """Check API authentication without modifying Proxmox."""

    if not TOKEN_FILE.is_file():
        raise FileNotFoundError("Restoration token file not found")

    if not CA_CERT.is_file():
        raise FileNotFoundError("Proxmox CA certificate not found")

    token = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))

    if token.get("full-tokenid") != TOKEN_ID:
        raise ValueError("Unexpected restoration token identity")

    secret = token.get("value")

    if not isinstance(secret, str) or not secret:
        raise ValueError("Restoration token secret is missing")

    url = (
        f"{PVE_URL}/api2/json/nodes/pve/"
        f"qemu/{TEST_VMID}/status/current"
    )

    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"PVEAPIToken={TOKEN_ID}={secret}"
        },
        method="GET",
    )

    context = ssl.create_default_context(cafile=str(CA_CERT))

    with urllib.request.urlopen(
        request,
        context=context,
        timeout=10,
    ) as response:
        vm = json.load(response)["data"]

    return {
        "vmid": TEST_VMID,
        "vm_status": vm["status"],
        "token_authenticated": True,
        "changes_applied": False,
    }
