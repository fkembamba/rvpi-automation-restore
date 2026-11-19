
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

POWER_TOKEN_ID = "rvpi-power@pve!power130"

POWER_TOKEN_FILE = (
    Path.home()
    / ".config/rvpi-automation/power-exec/power130-token.json"
)

SNAPSHOT_TOKEN_ID = "rvpi-snapshot@pve!snapshot130"

SNAPSHOT_TOKEN_FILE = (
    Path.home()
    / ".config/rvpi-automation/snapshot-exec/snapshot130-token.json"
)

CA_CERT = Path.home() / "pve-root-ca.pem"

PVE_URL = "https://pve.aicyber.rw:8006"
TEST_VMID = 130


CREDENTIAL_PROFILES = {
    "rollback130": {
        "token_id": TOKEN_ID,
        "token_file": TOKEN_FILE,
        "vmid": 130,
        "node": "pve",
    },
    "power130": {
        "token_id": POWER_TOKEN_ID,
        "token_file": POWER_TOKEN_FILE,
        "vmid": 130,
        "node": "pve",
    },
    "snapshot130": {
        "token_id": SNAPSHOT_TOKEN_ID,
        "token_file": SNAPSHOT_TOKEN_FILE,
        "vmid": 130,
        "node": "pve",
    },
}


def get_restore_credential(profile, vmid, node):
    """Return a credential only for its authorized VM and node."""

    credential = CREDENTIAL_PROFILES.get(profile)

    if (
        credential is None
        or type(vmid) is not int
        or credential["vmid"] != vmid
        or credential["node"] != node
    ):
        raise PermissionError(
            f"No authorized restoration credential for VM {vmid}"
        )

    return {
        "token_id": credential["token_id"],
        "token_file": credential["token_file"],
    }




def check_restore_token(vmid, node, credential_profile):
    """Check the VM using the currently configured execution token."""

    # # This credential is currently authorized for VM 130 only.
    # if type(vmid) is not int or vmid != TEST_VMID or node != "pve":
    #     raise PermissionError(
    #         "Current restoration token is restricted to VM 130 on pve"
    #     )
    credential = get_restore_credential(
        credential_profile,
        vmid,
        node,
    )

    """Check API authentication without modifying Proxmox."""

    if not credential["token_file"].is_file():
        raise FileNotFoundError(
            f"Credential file not found for profile: {credential_profile}"
        )

    if not CA_CERT.is_file():
        raise FileNotFoundError("Proxmox CA certificate not found")

    token = json.loads(
        credential["token_file"].read_text(encoding="utf-8")
    )

    if token.get("full-tokenid") != credential["token_id"]:
        raise ValueError("Unexpected restoration token identity")

    secret = token.get("value")

    if not isinstance(secret, str) or not secret:
        raise ValueError("Restoration token secret is missing")

    
    url = (
        f"{PVE_URL}/api2/json/nodes/{node}/"
        f"qemu/{vmid}/status/current"
    )


    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"PVEAPIToken={credential['token_id']}={secret}"
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
        "vmid": vmid,
        "vm_status": vm["status"],
        "token_authenticated": True,
        "changes_applied": False,
    }
