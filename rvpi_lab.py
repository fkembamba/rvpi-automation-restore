#!/usr/bin/env python3
"""Policy-scoped Proxmox VM lifecycle and baseline restoration CLI.

Place this file at the root of the rvpi-automation-restore Python project.
The CLI supports any VM individually enrolled in restore_policy.APPROVED_TARGETS;
no VM IDs, API tokens, or SSH credentials are embedded here.
"""

import argparse
import json
import ssl
import sys
import time
import urllib.request
from pathlib import Path

from rvpi_automation.restore_executor import (
    save_restore_report,
    submit_restore,
    submit_vm_power,
)
from rvpi_automation.restore_policy import (
    get_restore_target,
    list_restore_targets,
)
from rvpi_automation.restore_task_api import (
    read_restore_task_status,
    read_vm_power_task_status,
)
from rvpi_automation.restore_token import CA_CERT, PVE_URL, check_restore_token, get_restore_credential
from rvpi_automation.restore_verification import verify_restoration


SUCCESS = "TASK_SUCCEEDED"
FAILED = {"TASK_FAILED", "FAILED", "ERROR_UNVERIFIED", "TASK_UNKNOWN"}


def _wait_for_task(task_id, status_reader, *, max_checks, interval):
    """Confirm a Proxmox task reached TASK_SUCCEEDED; never retry submissions."""
    if not isinstance(task_id, str) or not task_id:
        raise RuntimeError("No Proxmox task ID returned; submission outcome uncertain")
    for attempt in range(max_checks):
        result = status_reader(task_id)
        status = result.get("task_status")
        if status == SUCCESS and result.get("exitstatus", "OK") == "OK":
            return result
        if status in FAILED or status == SUCCESS:
            raise RuntimeError(f"Proxmox task did not succeed: {status}")
        if attempt + 1 < max_checks:
            time.sleep(interval)
    raise TimeoutError("Task completion not confirmed; do not repeat submission")


def _wait_for_state(vmid, node, profile, desired, *, max_checks, interval):
    """Read only: wait until Proxmox confirms the intended VM power state."""
    for attempt in range(max_checks):
        state = check_restore_token(vmid, node, profile)
        if state.get("vm_status") == desired:
            return state
        if attempt + 1 < max_checks:
            time.sleep(interval)
    raise TimeoutError(f"VM {vmid} did not reach state {desired!r}")


def _wait_for_guest(vmid, *, max_checks, interval):
    """Wait for guest accessibility; a definite FAIL is not automatically retried."""
    for attempt in range(max_checks):
        try:
            result = verify_restoration(vmid)
        except (OSError, ConnectionError, TimeoutError):
            if attempt + 1 == max_checks:
                raise
            time.sleep(interval)
            continue
        if result.get("verification_status") != "PASS":
            raise RuntimeError("Guest baseline verification failed")
        return result
    raise TimeoutError("Guest verification unavailable")


def _preflight_baseline_and_verifier(vmid, target, restore_credential):
    """Read-only checks required before stopping a VM for rollback."""
    verification = target["verification"]
    for field in ("ssh_key", "reference_file"):
        path = Path(verification[field]).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"Guest verifier prerequisite missing: {field}")

    token_file = restore_credential["token_file"]
    token = json.loads(token_file.read_text(encoding="utf-8"))
    if token.get("full-tokenid") != restore_credential["token_id"] or not token.get("value"):
        raise ValueError("Rollback token identity or secret missing")
    url = (
        f"{PVE_URL}/api2/json/nodes/{target['node']}/qemu/{vmid}/snapshot"
    )
    request = urllib.request.Request(
        url,
        headers={"Authorization": f"PVEAPIToken={restore_credential['token_id']}={token['value']}"},
        method="GET",
    )
    context = ssl.create_default_context(cafile=str(CA_CERT))
    with urllib.request.urlopen(request, context=context, timeout=15) as response:
        snapshots = json.load(response)["data"]
    if not any(item.get("name") == target["baseline"] for item in snapshots):
        raise RuntimeError("Approved baseline snapshot not found; VM unchanged")


def restore_test(vmid, *, execute=False, confirmation=None, max_checks=60, interval=5):
    """Orchestrate shutdown -> rollback -> startup -> guest verification.

    Execute mode is destructive: explicitly confirmed snapshot rollback. On any
    ambiguous or unsuccessful step, STOP without attempting further VM changes.
    """
    target = get_restore_target(vmid)  # Explicit approved-VM enrollment required.
    node = target["node"]
    baseline = target["baseline"]
    power_profile = target.get("power_credential_profile")

    plan = {
        "vmid": vmid,
        "node": node,
        "baseline": baseline,
        "actions": ["shutdown-if-running", "rollback", "start", "verify", "save-evidence"],
        "status": "DRY_RUN",
        "changes_applied": False,
    }
    if not execute:
        plan["ready"] = bool(power_profile and target.get("credential_profile") and target.get("verification", {}).get("method") == "linux-ssh")
        plan["note"] = "Policy preview only; credential and runtime readiness not checked"
        return plan

    expected = f"RESTORE-{vmid}-{baseline}"
    if confirmation != expected:
        raise PermissionError(f"Explicit confirmation required: {expected}")
    if not power_profile or not target.get("credential_profile") or not target.get("verification"):
        raise PermissionError("Approved target lacks power, restore, or verification configuration")
    # Fail closed before shutdown if this target lacks a supported guest verifier.
    if target["verification"].get("method") != "linux-ssh":
        raise NotImplementedError("This version supports linux-ssh verification only")
    power_credential = get_restore_credential(power_profile, vmid, node)
    rollback_credential = get_restore_credential(target["credential_profile"], vmid, node)
    if power_credential["token_id"] == rollback_credential["token_id"]:
        raise PermissionError("Power and rollback credentials must be different")

    record = {
        "vmid": vmid,
        "node": node,
        "baseline": baseline,
        "status": "INCOMPLETE",
        "changes_applied": False,
        "steps": [],
        "results": [{"vmid": vmid, "status": "INCOMPLETE"}],
    }
    try:
        _preflight_baseline_and_verifier(vmid, target, rollback_credential)
        current = check_restore_token(vmid, node, power_profile)
        # Verify rollback credentials are readable BEFORE any shutdown.
        check_restore_token(vmid, node, target["credential_profile"])
        state = current.get("vm_status")
        if state == "running":
            shutdown = submit_vm_power(
                vmid, "shutdown", f"POWER-SHUTDOWN-{vmid}", execute=True
            )
            record["changes_applied"] = True
            record["steps"].append({"action": "shutdown", "task_id": shutdown.get("task_id"), "status": shutdown.get("status")})
            _wait_for_task(
                shutdown.get("task_id"),
                lambda upid: read_vm_power_task_status(upid, vmid, "shutdown"),
                max_checks=max_checks, interval=interval,
            )
            _wait_for_state(vmid, node, power_profile, "stopped", max_checks=max_checks, interval=interval)
        elif state != "stopped":
            raise RuntimeError(f"VM {vmid} has unexpected status: {state!r}")
        else:
            record["steps"].append({"action": "shutdown", "status": "ALREADY_STOPPED"})

        # Roll back only after Proxmox confirms stopped state.
        restore = submit_restore(vmid, f"ROLLBACK-{vmid}-{baseline}")
        record["changes_applied"] = True
        record["steps"].append({"action": "rollback", "task_id": restore.get("task_id"), "status": restore.get("status")})
        _wait_for_task(
            restore.get("task_id"),
            lambda upid: read_restore_task_status(upid, vmid=vmid),
            max_checks=max_checks, interval=interval,
        )

        # Some rollback configurations can leave the VM running. Do not
        # submit a duplicate start request if it is already running.
        after_rollback = check_restore_token(vmid, node, power_profile).get("vm_status")
        if after_rollback == "stopped":
            startup = submit_vm_power(vmid, "start", f"POWER-START-{vmid}", execute=True)
            record["steps"].append({"action": "start", "task_id": startup.get("task_id"), "status": startup.get("status")})
            _wait_for_task(
                startup.get("task_id"),
                lambda upid: read_vm_power_task_status(upid, vmid, "start"),
                max_checks=max_checks, interval=interval,
            )
        elif after_rollback == "running":
            record["steps"].append({"action": "start", "status": "ALREADY_RUNNING"})
        else:
            raise RuntimeError(f"Unexpected VM state after rollback: {after_rollback!r}")
        _wait_for_state(vmid, node, power_profile, "running", max_checks=max_checks, interval=interval)
        guest_result = _wait_for_guest(vmid, max_checks=max_checks, interval=interval)
        record["results"] = [{"vmid": vmid, "status": "RESTORATION_VERIFIED", "verification": guest_result}]
        record["status"] = "VERIFIED"
    except Exception as exc:
        # Do not retry unknown submissions or automatically start after a failed rollback.
        record["error_type"] = type(exc).__name__
        record["error"] = str(exc)
    finally:
        # The existing evidence writer expects a report with a results list.
        record["evidence_file"] = save_restore_report(record)
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description="RVPI policy-scoped Proxmox VM automation")
    parser.add_argument("command", choices=["list-targets", "status", "start", "shutdown", "verify", "restore-test"])
    parser.add_argument("--vmid", type=int, help="Approved VM ID")
    parser.add_argument("--execute", action="store_true", help="Allow real VM changes")
    parser.add_argument("--confirm", help="Required confirmation for real operations")
    parser.add_argument("--max-checks", type=int, default=60)
    parser.add_argument("--interval", type=float, default=5.0)
    args = parser.parse_args(argv)

    if args.max_checks < 1 or args.interval < 0:
        parser.error("--max-checks must be >= 1 and --interval must be >= 0")
    if args.command == "list-targets":
        if args.execute or args.confirm or args.vmid is not None:
            parser.error("list-targets takes no VM or execution options")
        result = list_restore_targets()
    else:
        if args.vmid is None:
            parser.error("--vmid is required")
        target = get_restore_target(args.vmid)
        if args.command == "status":
            result = check_restore_token(args.vmid, target["node"], target.get("power_credential_profile") or target["credential_profile"])
        elif args.command == "verify":
            result = verify_restoration(args.vmid)
        elif args.command in ("start", "shutdown"):
            result = submit_vm_power(args.vmid, args.command, args.confirm, execute=args.execute)
        else:
            result = restore_test(
                args.vmid, execute=args.execute, confirmation=args.confirm,
                max_checks=args.max_checks, interval=args.interval,
            )
    print(json.dumps(result, indent=2))
    if isinstance(result, dict) and result.get("status") == "INCOMPLETE":
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, PermissionError, RuntimeError, OSError, TimeoutError, KeyError, NotImplementedError) as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
