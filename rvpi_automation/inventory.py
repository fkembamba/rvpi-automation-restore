"""Pure read-only Proxmox inventory normalization (no networking or VM actions)."""


def normalize_vm_inventory(payload):
    """Normalize a Proxmox /cluster/resources?type=vm JSON response.

    Raises ValueError for malformed responses; never silently reports missing
    or malformed data as an empty inventory.
    """
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise ValueError("Expected a Proxmox JSON object containing a 'data' list")

    result = []
    seen = set()
    for index, vm in enumerate(payload["data"]):
        if not isinstance(vm, dict):
            raise ValueError(f"VM at index {index} must be an object")
        vmid = vm.get("vmid")
        if type(vmid) is not int or vmid <= 0:
            raise ValueError(f"VM at index {index} must contain a positive integer vmid")
        if vmid in seen:
            raise ValueError(f"Duplicate VM ID: {vmid}")
        seen.add(vmid)
        result.append({
            "vmid": vmid,
            "name": vm.get("name") or "",
            "status": vm.get("status") or "unknown",
            "node": vm.get("node") or "",
        })
    return sorted(result, key=lambda vm: vm["vmid"])
