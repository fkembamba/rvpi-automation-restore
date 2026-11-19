
"""Controlled Proxmox restoration for approved RVPI virtual machines."""

import json
import ssl
import urllib.request
import time
from rvpi_automation.restore_task_api import read_restore_task_status

from rvpi_automation.restore_execution import plan_restore_execution
from rvpi_automation.restore_policy import get_restore_target

from rvpi_automation.restore_token import (
    TOKEN_ID,
    TOKEN_FILE,
    CA_CERT,
    PVE_URL,
    check_restore_token,
    get_restore_credential,
)


# Retained for compatibility with existing VM 130 tests.
VMID = 130
NODE = "pve"
BASELINE = "baseline-clean"
CONFIRMATION = "ROLLBACK-130-baseline-clean"


def submit_restore(vmid, confirmation):
    """Submit one explicitly authorized Proxmox snapshot rollback."""

    # 1. Verify the target is approved.
    target = get_restore_target(vmid)

    node = target["node"]
    baseline = target["baseline"]

    # 2. Select a credential authorized for this VM and node.
    credential = get_restore_credential(
        target["credential_profile"],
        vmid,
        node,
    )

    # 3. Require target-specific confirmation.
    expected_confirmation = f"ROLLBACK-{vmid}-{baseline}"

    if confirmation != expected_confirmation:
        raise PermissionError(
            "Explicit restoration confirmation is required"
        )

    # 4. Perform the read-only restoration preflight.
    plan = plan_restore_execution(vmid, node=node)

    if plan["status"] != "DRY_RUN_READY":
        raise RuntimeError(
            f"Restoration blocked: {plan['status']}"
        )

    # 5. Recheck VM status using the selected execution credential.
    status = check_restore_token(
        vmid=vmid,
        node=node,
        credential_profile=target["credential_profile"],
    )

    if status["vm_status"] != "stopped":
        raise RuntimeError(
            f"VM {vmid} is not stopped"
        )

    # 6. Load and validate the restricted execution token.
    token_id = credential["token_id"]
    token_file = credential["token_file"]

    token = json.loads(
        token_file.read_text(encoding="utf-8")
    )

    if token.get("full-tokenid") != token_id:
        raise ValueError(
            "Unexpected restoration token identity"
        )

    secret = token.get("value")

    if not isinstance(secret, str) or not secret:
        raise ValueError(
            "Missing restoration token secret"
        )

    # 7. Submit the approved rollback request.
    url = (
        f"{PVE_URL}/api2/json/nodes/{node}/qemu/"
        f"{vmid}/snapshot/{baseline}/rollback"
    )

    request = urllib.request.Request(
        url,
        data=b"",
        headers={
            "Authorization": f"PVEAPIToken={token_id}={secret}"
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


def plan_restore_batch(vmids):
    """
    Plan restoration of multiple approved VMs.

    This function performs read-only checks only.
    It never submits a rollback request.
    """

    # 1. Validate the requested VM list.
    if not isinstance(vmids, (list, tuple)) or not vmids:
        raise ValueError(
            "Provide a nonempty list of VM IDs"
        )

    if any(
        type(vmid) is not int or vmid <= 0
        for vmid in vmids
    ):
        raise ValueError(
            "Every VM ID must be a positive integer"
        )

    if len(vmids) != len(set(vmids)):
        raise ValueError(
            "Duplicate VM IDs are not allowed"
        )

    results = []

    # 2. Evaluate each VM independently.
    for vmid in vmids:
        try:
            target = get_restore_target(vmid)

            node = target["node"]
            baseline = target["baseline"]

            # Check that an authorized credential profile is configured.
            get_restore_credential(
                target["credential_profile"],
                vmid,
                node,
            )

            # Read-only Proxmox preflight.
            plan = plan_restore_execution(
                vmid,
                node=node,
            )

            status = plan["status"]

            results.append({
                "vmid": vmid,
                "node": node,
                "baseline": baseline,
                "status": status,
                "ready": status == "DRY_RUN_READY",
            })

        except (ValueError, PermissionError) as exc:
            results.append({
                "vmid": vmid,
                "status": "BLOCKED",
                "ready": False,
                "reason": str(exc),
            })

        except Exception as exc:
            results.append({
                "vmid": vmid,
                "status": "PREFLIGHT_ERROR",
                "ready": False,
                "reason": str(exc),
            })

    # 3. Return the consolidated batch plan.
    return {
        "total_vms": len(vmids),
        "all_ready": all(
            item["ready"] for item in results
        ),
        "results": results,
        "changes_applied": False,
    }

def execute_restore_batch(
    vmids,
    confirmations=None,
    *,
    execute=False,
    max_checks=60,
    poll_interval=5,
):
    """
    Restore approved VMs sequentially.

    Execution is disabled by default.
    Stop the batch if a rollback fails or cannot be confirmed.
    """

    # Check every target before any rollback request.
    plan = plan_restore_batch(vmids)

    if execute is not True:
        return {
            **plan,
            "status": "DRY_RUN",
            "execution_performed": False,
        }

    if not plan["all_ready"]:
        raise RuntimeError(
            "Batch blocked: not all VMs passed restoration preflight"
        )

    if not isinstance(confirmations, dict):
        raise PermissionError(
            "Per-VM restoration confirmations are required"
        )

    if (
        type(max_checks) is not int
        or max_checks < 1
        or type(poll_interval) not in (int, float)
        or poll_interval < 0
    ):
        raise ValueError("Invalid task-monitoring settings")

    # Validate ALL confirmations before the first POST.
    for item in plan["results"]:
        vmid = item["vmid"]
        expected = (
            f"ROLLBACK-{vmid}-{item['baseline']}"
        )

        if confirmations.get(vmid) != expected:
            raise PermissionError(
                f"Missing or incorrect confirmation for VM {vmid}"
            )

    results = []

    for item in plan["results"]:
        vmid = item["vmid"]
        task_id = None

        try:
            submission = submit_restore(
                vmid,
                confirmations[vmid],
            )

            task_id = submission["task_id"]

            # Wait for Proxmox to finish before the next VM.
            final_task = None

            for check in range(max_checks):
                task = read_restore_task_status(
                    task_id,
                    vmid=vmid,
                )

                if task["task_status"] != "RUNNING":
                    final_task = task
                    break

                if check < max_checks - 1:
                    time.sleep(poll_interval)

            if final_task is None:
                results.append({
                    "vmid": vmid,
                    "task_id": task_id,
                    "status": "TIMEOUT_UNVERIFIED",
                    "restoration_verified": False,
                })
                break

            results.append({
                "vmid": vmid,
                "task_id": task_id,
                "status": final_task["task_status"],
                "exitstatus": final_task.get("exitstatus"),
                "restoration_verified": False,
            })

            if final_task["task_status"] != "TASK_SUCCEEDED":
                break

        except Exception as exc:
            results.append({
                "vmid": vmid,
                "task_id": task_id,
                "status": "ERROR_UNVERIFIED",
                "error": str(exc),
                "restoration_verified": False,
            })
            break

    all_tasks_succeeded = (
        len(results) == len(vmids)
        and all(
            result["status"] == "TASK_SUCCEEDED"
            for result in results
        )
    )

    return {
        "status": (
            "TASKS_SUCCEEDED_GUESTS_UNVERIFIED"
            if all_tasks_succeeded
            else "BATCH_INCOMPLETE"
        ),
        "total_requested": len(vmids),
        "processed": len(results),
        "results": results,
        
        "execution_performed": any(
            result.get("task_id") is not None
            for result in results
        ),
        "submission_outcome_uncertain": any(
            result["status"] == "ERROR_UNVERIFIED"
            for result in results
        ),

        "restoration_verified": False,
    }
