
"""Read-only preflight checks for controlled RVPI restoration."""

from rvpi_automation.proxmox import list_vms, verify_baseline


TEST_VMID = 130
BASELINE_NAME = "baseline-clean"


def plan_restore_execution(vmid=TEST_VMID, node="pve"):
    """Plan a snapshot restoration without changing VM state."""

    if type(vmid) is not int or vmid != TEST_VMID:
        raise ValueError("Only disposable VM 130 is approved")

    plan = {
        "vmid": vmid,
        "node": node,
        "baseline": BASELINE_NAME,
        "changes_applied": False,
        "execution_authorized": False,
    }

    inventory = [
        vm for vm in list_vms()
        if vm["vmid"] == vmid and vm["node"] == node
    ]

    if len(inventory) != 1:
        return {**plan, "status": "BLOCKED_VM_NOT_FOUND"}

    baseline = verify_baseline(
        vmid,
        baseline_name=BASELINE_NAME,
        node=node,
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
