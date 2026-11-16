
"""Read-only restoration planning for RVPI experiments."""

from rvpi_automation.proxmox import verify_baseline

# Planning scope only; does not authorize execution.
PLANNING_VMIDS = frozenset({100})


def plan_restore(vmid, baseline_name="baseline-clean", node="pve"):
    """Validate a proposed restoration without modifying any VM."""

    if type(vmid) is not int or vmid <= 0:
        raise ValueError("VM ID must be a positive integer")

    if vmid not in PLANNING_VMIDS:
        return {
            "vmid": vmid,
            "status": "BLOCKED_UNAPPROVED_VM",
            "changes_applied": False
        }

    if not baseline_name or baseline_name == "current":
        raise ValueError("Invalid baseline snapshot name")

    result = verify_baseline(
        vmid,
        baseline_name=baseline_name,
        node=node
    )

    if not result["exists"]:
        return {
            "vmid": vmid,
            "status": "BLOCKED_MISSING_BASELINE",
            "changes_applied": False
        }

    return {
        "vmid": vmid,
        "node": node,
        "baseline": baseline_name,
        "status": "PLAN_READY",
        "changes_applied": False,
        "execution_authorized": False
    }
