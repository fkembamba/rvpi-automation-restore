"""Policy-scoped VM snapshot inventory and creation; no delete/rollback capability.

Snapshot creation is deliberately restricted to approved, stopped VMs.
Proxmox's VM.Snapshot privilege also permits deletion; VM ACLs and token
isolation are essential, in addition to application-level checks.
"""

import json
import re
import ssl
import time
import urllib.parse
import urllib.request
from pathlib import Path

from rvpi_automation.proxmox import list_snapshots
from rvpi_automation.restore_policy import get_restore_target
from rvpi_automation.restore_token import (
    CA_CERT,
    PVE_URL,
    check_restore_token,
    get_restore_credential,
)

# Conservative subset of Proxmox snapshot names; excludes whitespace and paths.
_NAME = re.compile(r"^(?:checkpoint|exp)-[A-Za-z0-9][A-Za-z0-9_-]{0,48}$")


def _validated_target(vmid, name):
    target = get_restore_target(vmid)
    if not isinstance(name, str) or not _NAME.fullmatch(name):
        raise ValueError(
            "Snapshot name must start with checkpoint- or exp-, "
            "followed by letters, numbers, underscores or hyphens"
        )
    if name.casefold() in {"current", str(target["baseline"]).casefold()}:
        raise PermissionError("Approved baseline and reserved names cannot be used")
    return target


def list_approved_snapshots(vmid):
    """List snapshots for an explicitly approved VM (read-only)."""
    target = get_restore_target(vmid)
    return {
        "vmid": vmid,
        "node": target["node"],
        "approved_baseline": target["baseline"],
        "snapshots": list_snapshots(vmid, target["node"]),
        "changes_applied": False,
    }


def plan_snapshot_create(vmid, name, description=""):
    """Local policy-only preview; makes no API or filesystem requests."""
    target = _validated_target(vmid, name)
    if not isinstance(description, str) or len(description) > 200:
        raise ValueError("Description must be text of at most 200 characters")
    return {
        "vmid": vmid,
        "node": target["node"],
        "snapshot": name,
        "approved_baseline": target["baseline"],
        "status": "DRY_RUN_POLICY_ONLY",
        "changes_applied": False,
        "note": "Credential, VM power state, storage and duplicate name not checked",
    }


def _snapshot_credential(target, vmid):
    profile = target.get("snapshot_credential_profile")
    if not profile:
        raise PermissionError("No dedicated snapshot-creation credential approved")
    credential = get_restore_credential(profile, vmid, target["node"])
    # Do not silently reuse rollback/power token identities.
    for other_profile in (
        target.get("credential_profile"),
        target.get("power_credential_profile"),
    ):
        if other_profile:
            other = get_restore_credential(other_profile, vmid, target["node"])
            if credential["token_id"] == other["token_id"]:
                raise PermissionError("Snapshot credential must be independent")
    return profile, credential


def _request_snapshot_api(vmid, node, credential, *, method, suffix, payload=None):
    path = Path(credential["token_file"])
    if not path.is_file():
        raise FileNotFoundError("Dedicated snapshot credential file missing")
    token = json.loads(path.read_text(encoding="utf-8"))
    if token.get("full-tokenid") != credential["token_id"]:
        raise ValueError("Snapshot credential identity mismatch")
    secret = token.get("value")
    if not isinstance(secret, str) or not secret:
        raise ValueError("Snapshot credential secret missing")
    if suffix.startswith("tasks/"):
        url = f"{PVE_URL}/api2/json/nodes/{node}/{suffix}"
    else:
        url = f"{PVE_URL}/api2/json/nodes/{node}/qemu/{vmid}/{suffix}"
    data = urllib.parse.urlencode(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Authorization": f"PVEAPIToken={credential['token_id']}={secret}"},
        method=method,
    )
    context = ssl.create_default_context(cafile=str(CA_CERT))
    with urllib.request.urlopen(request, context=context, timeout=30) as response:
        response_json = json.load(response)
    return response_json.get("data")


def _wait_snapshot_task(upid, vmid, node, credential, *, max_checks=60, interval=5):
    """Read task status until confirmed OK; never resubmit an ambiguous request."""
    if not isinstance(upid, str):
        raise RuntimeError("Missing snapshot task UPID; outcome uncertain")
    parts = upid.split(":")
    if (
        len(parts) != 9
        or parts[0] != "UPID"
        or parts[1] != node
        or parts[5] != "qmsnapshot"
        or parts[6] != str(vmid)
        or parts[7] != credential["token_id"]
        or parts[8] != ""
    ):
        raise ValueError("Unexpected snapshot task identity; do not retry submission")
    if type(max_checks) is not int or max_checks < 1 or interval < 0:
        raise ValueError("Invalid task polling bounds")
    task_path = f"tasks/{urllib.parse.quote(upid, safe='')}/status"
    for attempt in range(max_checks):
        result = _request_snapshot_api(
            vmid, node, credential, method="GET", suffix=task_path
        )
        # Defense in depth: no success until final exitstatus OK.
        if not isinstance(result, dict):
            raise RuntimeError("Invalid Proxmox task response")
        if result.get("status") == "stopped":
            if result.get("exitstatus") != "OK":
                raise RuntimeError("Snapshot task stopped without an OK exit status")
            return {"task_status": "TASK_SUCCEEDED", "exitstatus": "OK"}
        if result.get("status") != "running":
            raise RuntimeError("Unexpected snapshot task status")
        if attempt + 1 < max_checks:
            time.sleep(interval)
    raise TimeoutError("Snapshot task outcome unconfirmed; do not resubmit")


def create_snapshot(vmid, name, *, description="", execute=False, confirmation=None,
                    max_checks=60, interval=5):
    """Create a disk-only snapshot on an approved stopped VM; dry-run by default.

    Reports creation as confirmed only after Proxmox task success and an
    inventory check. Never deletes snapshots, alters the approved baseline,
    or performs any automatic rollback.
    """
    preview = plan_snapshot_create(vmid, name, description)
    if execute is not True:
        return preview
    expected = f"CREATE-SNAPSHOT-{vmid}-{name}"
    if confirmation != expected:
        raise PermissionError(f"Explicit confirmation required: {expected}")
    target = _validated_target(vmid, name)
    profile, credential = _snapshot_credential(target, vmid)
    state = check_restore_token(vmid, target["node"], profile)
    if state.get("vm_status") != "stopped":
        raise RuntimeError("BLOCKED_VM_NOT_STOPPED: stop VM before creating a snapshot")
    if any(item.get("name") == name for item in list_snapshots(vmid, target["node"])):
        raise FileExistsError("Snapshot already exists; existing snapshot unchanged")

    # POST is the only mutating call: create disk snapshot without memory state.
    upid = _request_snapshot_api(
        vmid,
        target["node"],
        credential,
        method="POST",
        suffix="snapshot",
        payload={"snapname": name, "description": description, "vmstate": "0"},
    )
    if not isinstance(upid, str) or not upid:
        raise RuntimeError("Snapshot submission outcome unknown; inspect Proxmox tasks")
    result = {
        "vmid": vmid, "node": target["node"], "snapshot": name,
        "status": "SUBMITTED_UNVERIFIED", "task_id": upid,
        "changes_applied": True,
    }
    try:
        task = _wait_snapshot_task(
            upid, vmid, target["node"], credential,
            max_checks=max_checks, interval=interval,
        )
        result["task"] = task
        if not any(item.get("name") == name for item in list_snapshots(vmid, target["node"])):
            raise RuntimeError("Task succeeded but snapshot not visible in inventory")
        result["status"] = "CREATED_VERIFIED"
    except Exception as exc:
        result["status"] = "INCOMPLETE"
        result["error_type"] = type(exc).__name__
        result["error"] = str(exc)
    return result
