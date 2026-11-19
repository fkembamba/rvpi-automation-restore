
"""Small read-only command-line interface for RVPI Automation / Restore."""

import argparse
import json
import platform
from pathlib import Path

from rvpi_automation.inventory import normalize_vm_inventory
from rvpi_automation.proxmox import list_vms
from rvpi_automation.restore_policy import get_restore_target
from rvpi_automation.restore_token import check_restore_token


def main():
    parser = argparse.ArgumentParser(
        description="RVPI Automation / Restore (read-only v0.2)"
    )
    parser.add_argument(
        "command",
        choices=[
            "health",
            "list-vms",
            "demo-inventory",
            "check-restore-token",
        ],
    )
    parser.add_argument(
        "--vmid",
        type=int,
        help="Approved VM ID for restoration token verification",
    )

    args = parser.parse_args()

    if args.command == "health":
        print(json.dumps({
            "status": "ok",
            "component": "rvpi-automation-restore",
            "python": platform.python_version(),
            "mode": "read-only",
        }, indent=2))

    elif args.command == "demo-inventory":
        # Local fixture only; no Proxmox connection.
        fixture = (
            Path(__file__).resolve().parent
            / "tests"
            / "fixtures"
            / "proxmox_vms_demo.json"
        )

        with fixture.open(encoding="utf-8") as handle:
            vms = normalize_vm_inventory(json.load(handle))

        print(json.dumps({
            "source": "SIMULATED — NOT LIVE PROXMOX DATA",
            "vms": vms,
        }, indent=2))

    elif args.command == "list-vms":
        try:
            print(json.dumps(list_vms(), indent=2))
        except (
            ValueError,
            OSError,
            KeyError,
            json.JSONDecodeError,
        ) as exc:
            parser.exit(1, f"Read-only inventory failed: {exc}\n")

    elif args.command == "check-restore-token":
        if args.vmid is None:
            parser.error("check-restore-token requires --vmid")

        try:
            target = get_restore_target(args.vmid)

            result = check_restore_token(
                vmid=args.vmid,
                node=target["node"],
                credential_profile=target["credential_profile"],
            )

            print(json.dumps(result, indent=2))

        except (
            PermissionError,
            ValueError,
            OSError,
            KeyError,
            json.JSONDecodeError,
        ) as exc:
            parser.exit(
                1,
                f"Restoration token check failed: {exc}\n",
            )


if __name__ == "__main__":
    main()
