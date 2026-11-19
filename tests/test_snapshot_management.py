"""Tests for policy-scoped snapshot creation. No live Proxmox operations."""

import unittest
from pathlib import Path
from unittest.mock import patch

from rvpi_automation import snapshot_management as snapshots


TARGET = {
    "vmid": 130,
    "node": "pve",
    "baseline": "baseline-clean",
    "credential_profile": "rollback130",
    "power_credential_profile": "power130",
    "snapshot_credential_profile": "snapshot130",
}


def credential(profile, vmid, node):
    assert vmid == 130 and node == "pve"
    return {"token_id": f"test@pve!{profile}", "token_file": Path("unused.json")}


class SnapshotManagementTests(unittest.TestCase):
    def test_dry_run_is_local_and_safe(self):
        with patch.object(snapshots, "get_restore_target", return_value=TARGET), \
             patch.object(snapshots, "_request_snapshot_api") as api, \
             patch.object(snapshots, "list_snapshots") as inventory:
            result = snapshots.create_snapshot(130, "checkpoint-001")
        self.assertEqual(result["status"], "DRY_RUN_POLICY_ONLY")
        self.assertFalse(result["changes_applied"])
        api.assert_not_called()
        inventory.assert_not_called()

    def test_rejects_unapproved_vm(self):
        with patch.object(snapshots, "get_restore_target", side_effect=PermissionError("Not approved")):
            with self.assertRaises(PermissionError):
                snapshots.create_snapshot(100, "checkpoint-001")

    def test_rejects_unapproved_snapshot_name(self):
        with patch.object(snapshots, "get_restore_target", return_value=TARGET):
            for name in ("../bad", "baseline-clean", "current", "a b", "checkout"):
                with self.subTest(name=name), self.assertRaises((ValueError, PermissionError)):
                    snapshots.create_snapshot(130, name)

    def test_missing_profile_blocks_before_mutation(self):
        no_profile = {k: v for k, v in TARGET.items() if k != "snapshot_credential_profile"}
        with patch.object(snapshots, "get_restore_target", return_value=no_profile), \
             patch.object(snapshots, "_request_snapshot_api") as api:
            with self.assertRaises(PermissionError):
                snapshots.create_snapshot(
                    130, "checkpoint-001", execute=True,
                    confirmation="CREATE-SNAPSHOT-130-checkpoint-001",
                )
        api.assert_not_called()

    def test_wrong_confirmation_blocks_before_api_calls(self):
        with patch.object(snapshots, "get_restore_target", return_value=TARGET), \
             patch.object(snapshots, "_request_snapshot_api") as api:
            with self.assertRaises(PermissionError):
                snapshots.create_snapshot(130, "checkpoint-001", execute=True, confirmation="wrong")
        api.assert_not_called()

    def test_running_vm_blocked(self):
        with patch.object(snapshots, "get_restore_target", return_value=TARGET), \
             patch.object(snapshots, "get_restore_credential", side_effect=credential), \
             patch.object(snapshots, "check_restore_token", return_value={"vm_status": "running"}), \
             patch.object(snapshots, "_request_snapshot_api") as api:
            with self.assertRaises(RuntimeError):
                snapshots.create_snapshot(130, "checkpoint-001", execute=True,
                    confirmation="CREATE-SNAPSHOT-130-checkpoint-001")
        api.assert_not_called()

    def test_duplicate_snapshot_is_rejected(self):
        with patch.object(snapshots, "get_restore_target", return_value=TARGET), \
             patch.object(snapshots, "get_restore_credential", side_effect=credential), \
             patch.object(snapshots, "check_restore_token", return_value={"vm_status": "stopped"}), \
             patch.object(snapshots, "list_snapshots", return_value=[{"name": "checkpoint-001"}]), \
             patch.object(snapshots, "_request_snapshot_api") as api:
            with self.assertRaises(FileExistsError):
                snapshots.create_snapshot(130, "checkpoint-001", execute=True,
                    confirmation="CREATE-SNAPSHOT-130-checkpoint-001")
        api.assert_not_called()

    def test_confirmed_creation_checks_task_and_inventory(self):
        with patch.object(snapshots, "get_restore_target", return_value=TARGET), \
             patch.object(snapshots, "get_restore_credential", side_effect=credential), \
             patch.object(snapshots, "check_restore_token", return_value={"vm_status": "stopped"}), \
             patch.object(snapshots, "list_snapshots", side_effect=[[], [{"name": "checkpoint-001"}]]), \
             patch.object(snapshots, "_request_snapshot_api", return_value="FAKE-UPID") as api, \
             patch.object(snapshots, "_wait_snapshot_task", return_value={"task_status": "TASK_SUCCEEDED", "exitstatus": "OK"}):
            result = snapshots.create_snapshot(130, "checkpoint-001", execute=True,
                confirmation="CREATE-SNAPSHOT-130-checkpoint-001")
        self.assertEqual(result["status"], "CREATED_VERIFIED")
        self.assertEqual(api.call_count, 1)
        self.assertEqual(api.call_args.kwargs["method"], "POST")
        self.assertEqual(api.call_args.kwargs["payload"]["vmstate"], "0")

    def test_timeout_is_incomplete_not_success(self):
        with patch.object(snapshots, "get_restore_target", return_value=TARGET), \
             patch.object(snapshots, "get_restore_credential", side_effect=credential), \
             patch.object(snapshots, "check_restore_token", return_value={"vm_status": "stopped"}), \
             patch.object(snapshots, "list_snapshots", return_value=[]), \
             patch.object(snapshots, "_request_snapshot_api", return_value="FAKE-UPID"), \
             patch.object(snapshots, "_wait_snapshot_task", side_effect=TimeoutError("still running")):
            result = snapshots.create_snapshot(130, "checkpoint-001", execute=True,
                confirmation="CREATE-SNAPSHOT-130-checkpoint-001")
        self.assertEqual(result["status"], "INCOMPLETE")

    def test_task_requires_explicit_ok(self):
        upid = "UPID:pve:111:222:333:qmsnapshot:130:test@pve!snapshot130:"
        with patch.object(snapshots, "_request_snapshot_api", return_value={"status": "stopped"}):
            with self.assertRaises(RuntimeError):
                snapshots._wait_snapshot_task(
                    upid, 130, "pve", credential("snapshot130", 130, "pve"),
                    max_checks=1, interval=0,
                )


if __name__ == "__main__":
    unittest.main()
