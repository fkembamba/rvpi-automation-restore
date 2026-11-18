
"""Controlled Proxmox snapshot rollback for disposable VM 130."""

import json
import ssl
import urllib.request

from rvpi_automation.restore_execution import plan_restore_execution
from rvpi_automation.restore_policy import get_restore_target
from rvpi_automation.restore_token import (
    TOKEN_ID,
    TOKEN_FILE,
    CA_CERT,
    PVE_URL,
    check_restore_token,
)


VMID = 130
NODE = "pve"
BASELINE = "baseline-clean"

CONFIRMATION = "ROLLBACK-130-baseline-clean"


def submit_restore(vmid, confirmation):
    """Submit one explicitly authorized rollback request."""

    
    # Safety check 1: Validate against centralized restoration policy.
    target = get_restore_target(vmid)
    node = target["node"]
    baseline = target["baseline"]

    # The current execution token is authorized for VM 130 only.
    if target["vmid"] != VMID:
        raise PermissionError(
            f"No restoration execution credential configured for VM {vmid}"
        )


    # Safety check 2: Require explicit confirmation.
    if confirmation != CONFIRMATION:
        raise PermissionError(
            "Explicit restoration confirmation is required"
        )

    # Safety check 3: Run existing read-only preflight.
    plan = plan_restore_execution(vmid, node=node)

    if plan["status"] != "DRY_RUN_READY":
        raise RuntimeError(
            f"Restoration blocked: {plan['status']}"
        )

    # Safety check 4: Recheck VM state using execution token.
    status = check_restore_token()

    if status["vm_status"] != "stopped":
        raise RuntimeError("VM 130 is not stopped")

    # Safety check 5: Load the dedicated restricted credential.
    token = json.loads(
        TOKEN_FILE.read_text(encoding="utf-8")
    )

    if token.get("full-tokenid") != TOKEN_ID:
        raise ValueError("Unexpected restoration token identity")

    secret = token.get("value")

    if not isinstance(secret, str) or not secret:
        raise ValueError("Missing restoration token secret")

    # Submit rollback through the Proxmox API.
    url = (
        f"{PVE_URL}/api2/json/nodes/{node}/qemu/"
        f"{vmid}/snapshot/{baseline}/rollback"
    )

    request = urllib.request.Request(
        url,
        data=b"",
        headers={
            "Authorization": f"PVEAPIToken={TOKEN_ID}={secret}"
        },
        method="POST",
    )

    context = ssl.create_default_context(
        cafile=str(CA_CERT)
    )

    with urllib.request.urlopen(
        request,
        context=context,
        timeout=30,
    ) as response:
        result = json.load(response)

    task_id = result.get("data")

    if not isinstance(task_id, str) or not task_id:
        raise RuntimeError(
            "Rollback response missing task ID; inspect "
            "Proxmox tasks before attempting another rollback"
        )

    
    return {
        "vmid": vmid,
        "node": node,
        "baseline": baseline,
        "status": "SUBMITTED_UNVERIFIED",
        "task_id": task_id,
        "restoration_verified": False,
    }

