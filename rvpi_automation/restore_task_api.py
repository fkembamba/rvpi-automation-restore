
"""Read-only retrieval of Proxmox restoration task status."""

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


def read_restore_task_status(upid, vmid=130):
    """Read the status of an authorized rollback task without modifying a VM."""

    # # Current execution credential is restricted to VM 130.
    # if type(vmid) is not int or vmid != 130:
    #     raise PermissionError("Task-monitoring credential is restricted to VM 130")

    target = get_restore_target(vmid)
    node = target["node"]

    credential = get_restore_credential(
        target["credential_profile"],
        vmid,
        node,
    )

    # Ensure the task belongs to the approved node and VM.
    parts = upid.split(":") if isinstance(upid, str) else []

    if (
        len(parts) < 8
        or parts[0] != "UPID"
        or parts[1] != node
        or parts[5] != "qmrollback"
        or parts[6] != str(vmid)
    ):
        raise ValueError("Invalid or unauthorized rollback task ID")

    
    token_id = credential["token_id"]
    token_file = credential["token_file"]

    token = json.loads(
        token_file.read_text(encoding="utf-8")
    )

    if token.get("full-tokenid") != token_id:
        raise ValueError("Unexpected restoration token identity")


    secret = token.get("value")
    if not isinstance(secret, str) or not secret:
        raise ValueError("Missing restoration token secret")

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

    context = ssl.create_default_context(cafile=str(CA_CERT))

    with urllib.request.urlopen(
        request, context=context, timeout=30
    ) as response:
        result = json.load(response)

    task = result.get("data")
    if not isinstance(task, dict):
        raise RuntimeError("Invalid Proxmox task-status response")

    if (
        task.get("upid") != upid
        or task.get("type") != "qmrollback"
        or str(task.get("id")) != str(vmid)
        or task.get("node") != node
    ):
        raise RuntimeError("Proxmox task identity mismatch")

    return {
        "vmid": vmid,
        "node": node,
        "task_id": upid,
        **interpret_task_status(task),
    }
