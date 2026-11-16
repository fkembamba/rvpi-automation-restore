
"""Read-only baseline inventory for approved RVPI VMs."""

from rvpi_automation.proxmox import verify_baseline


def check_baselines(vmids, baseline_name="baseline-clean", node="pve"):
    """Check whether the selected VMs have baseline snapshots."""

    if not isinstance(vmids, (list, tuple)) or not vmids:
        raise ValueError("Provide a nonempty list of VM IDs")

    if any(type(vmid) is not int or vmid <= 0 for vmid in vmids):
        raise ValueError("VM IDs must be positive integers")

    if len(set(vmids)) != len(vmids):
        raise ValueError("Duplicate VM IDs are not allowed")

    results = []

    for vmid in vmids:
        result = verify_baseline(
            vmid,
            baseline_name=baseline_name,
            node=node
        )
        results.append(result)

    return results
