
"""Read-only Proxmox task monitoring for approved RVPI VMs."""

import json
import ssl
import urllib.parse
import urllib.request

from rvpi_automation.restore_policy import get_restore_target
from rvpi_automation.restore_token import (
    TOKEN_ID,
    TOKEN_FILE,
    CA_CERT,
    PVE_URL,
    get_restore_credential,
)
from rvpi_automation.task_monitor import interpret_task_status


POWER_TASK_TYPES = {
    "start": "qmstart",
    "shutdown": "qmshutdown",
}


def _read_vm_task_status(
    upid,
    vmid,
    expected_type,
    credential_field,
):
    """Read an authorized task and verify its identity."""

    # 1. Check VM authorization.
    target = get_restore_target(vmid)
    node = target["node"]

    profile = target.get(credential_field)

    if not isinstance(profile, str) or not profile:
        raise PermissionError(
            f"No {credential_field} configured for VM {vmid}"
        )

    # 2. Check task identity before contacting Proxmox.
    parts = upid.split(":") if isinstance(upid, str) else []

    if (
        len(parts) < 8
        or parts[0] != "UPID"
        or parts[1] != node
        or parts[5] != expected_type
        or parts[6] != str(vmid)
    ):
        raise ValueError(
            "Invalid or unauthorized Proxmox task ID"
        )

    # 3. Select a credential authorized for this VM.
    credential = get_restore_credential(
        profile,
        vmid,
        node,
    )

    token_id = credential["token_id"]
    token_file = credential["token_file"]

    token = json.loads(
        token_file.read_text(encoding="utf-8")
    )

    if token.get("full-tokenid") != token_id:
        raise ValueError(
            "Unexpected task-monitoring token identity"
        )

    secret = token.get("value")

    if not isinstance(secret, str) or not secret:
        raise ValueError(
            "Missing task-monitoring token secret"
        )

    # 4. Make a read-only Proxmox API request.
    encoded_upid = urllib.parse.quote(upid, safe="")

    url = (
        f"{PVE_URL}/api2/json/nodes/{node}/tasks/"
        f"{encoded_upid}/status"
    )

    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"PVEAPIToken={token_id}={secret}"
        },
        method="GET",
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

    task = result.get("data")

    if not isinstance(task, dict):
        raise RuntimeError(
            "Invalid Proxmox task-status response"
        )

    # 5. Verify the identity in the API response.
    if (
        task.get("upid") != upid
        or task.get("type") != expected_type
        or str(task.get("id")) != str(vmid)
        or task.get("node") != node
    ):
        raise RuntimeError(
            "Proxmox task identity mismatch"
        )

    # 6. Interpret the task without changing the VM.
    return {
        "vmid": vmid,
        "node": node,
        "task_id": upid,
        **interpret_task_status(task),
    }


def read_restore_task_status(upid, vmid):
    """Monitor an approved VM snapshot rollback."""

    return _read_vm_task_status(
        upid,
        vmid,
        expected_type="qmrollback",
        credential_field="credential_profile",
    )


def read_vm_power_task_status(upid, vmid, action):
    """Monitor an approved VM startup or graceful shutdown."""

    if action not in POWER_TASK_TYPES:
        raise ValueError(
            "Only start and shutdown tasks are supported"
        )

    result = _read_vm_task_status(
        upid,
        vmid,
        expected_type=POWER_TASK_TYPES[action],
        credential_field="power_credential_profile",
    )

    return {
        **result,
        "action": action,
        "guest_ready": False,
    }
