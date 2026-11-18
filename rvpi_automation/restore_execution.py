
"""Read-only preflight checks for approved RVPI restoration targets."""

from rvpi_automation.proxmox import list_vms, verify_baseline
from rvpi_automation.restore_policy import get_restore_target


def plan_restore_execution(vmid=130, node=None):
    """Validate an approved VM for restoration without modifying it."""

    # Retrieve approved settings from the centralized policy.
    target = get_restore_target(vmid)

    approved_node = target["node"]
    baseline_name = target["baseline"]

    plan = {
        "vmid": vmid,
        "node": approved_node,
        "baseline": baseline_name,
        "changes_applied": False,
        "execution_authorized": False,
    }

    # Reject requests targeting an unapproved Proxmox node.
    if node is not None and node != approved_node:
        return {**plan, "status": "BLOCKED_NODE_MISMATCH"}

    inventory = [
        vm for vm in list_vms()
        if vm["vmid"] == vmid and vm["node"] == approved_node
    ]

    if len(inventory) != 1:
        return {**plan, "status": "BLOCKED_VM_NOT_FOUND"}

    baseline = verify_baseline(
        vmid,
        baseline_name=baseline_name,
        node=approved_node,
    )

    if not baseline["exists"]:
        return {**plan, "status": "BLOCKED_MISSING_BASELINE"}

    vm_status = inventory[0]["status"]

    if vm_status != "stopped":
        return {
            **plan,
            "status": "BLOCKED_VM_NOT_STOPPED",
            "vm_status": vm_status,
        }

    return {
        **plan,
        "status": "DRY_RUN_READY",
        "vm_status": vm_status,
    }
