
"""Approved restoration targets for the RVPI cyber range."""

# Only disposable VM 130 is approved initially.
# Additional VMs require explicit approval and verified baselines.


APPROVED_TARGETS = {
    130: {
        "node": "pve",
        "baseline": "baseline-clean",
        "purpose": "restoration-test",
        "credential_profile": "rollback130",
        "verification": {
            "method": "linux-ssh",
            "ssh_target": "kemba@10.10.70.130",
            "ssh_key": "~/.ssh/rvpi_restore_test-ed25519",
            "reference_file": "~/rvpi-evidence/vm130/hostname-reference.sha256",
            "hostname_path": "/etc/hostname",
            "marker_path": "/home/kemba/rvpi-restore-marker.txt",
        },
    },
}




def get_restore_target(vmid):
    """Return an approved target configuration."""

    if type(vmid) is not int or vmid <= 0:
        raise ValueError("VM ID must be a positive integer")

    if vmid not in APPROVED_TARGETS:
        raise PermissionError(
            f"VM {vmid} is not approved for restoration"
        )

    return {
        "vmid": vmid,
        **APPROVED_TARGETS[vmid].copy(),
    }


def list_restore_targets():
    """List approved restoration targets without changing VMs."""

    return [
        get_restore_target(vmid)
        for vmid in sorted(APPROVED_TARGETS)
    ]
