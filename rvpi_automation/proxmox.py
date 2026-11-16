"""Read-only Proxmox VE API client using the Python standard library."""
import json
import os
import ssl
from urllib.request import Request, urlopen

from rvpi_automation.inventory import normalize_vm_inventory


def list_vms():
    """Return the Proxmox cluster VM inventory without modifying any VM."""
    base_url = os.environ.get("PVE_URL", "").rstrip("/")
    token_id = os.environ.get("PVE_TOKEN_ID", "")
    token_secret = os.environ.get("PVE_TOKEN_SECRET", "")
    if not all((base_url, token_id, token_secret)):
        raise ValueError("Set PVE_URL, PVE_TOKEN_ID, and PVE_TOKEN_SECRET")
    if not base_url.startswith("https://"):
        raise ValueError("PVE_URL must begin with https://")
    if not os.environ.get("PVE_CA_CERT"):
        raise ValueError("Set PVE_CA_CERT to a trusted CA PEM file; TLS verification is mandatory")

    context = ssl.create_default_context(cafile=os.environ["PVE_CA_CERT"])
    request = Request(
        f"{base_url}/api2/json/cluster/resources?type=vm",
        headers={"Authorization": f"PVEAPIToken={token_id}={token_secret}"},
        method="GET",
    )
    with urlopen(request, context=context, timeout=10) as response:
        payload = json.load(response)
    return normalize_vm_inventory(payload)
