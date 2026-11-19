"""No-Proxmox-API tests for generic snapshot lifecycle orchestration."""

import unittest
from unittest.mock import patch

import rvpi_lab as cli


class SnapshotLifecycleCLITests(unittest.TestCase):
    def setUp(self):
        self.target = {
            "vmid": 130,
            "node": "pve",
            "baseline": "baseline-clean",
            "credential_profile": "rollback130",
            "power_credential_profile": "power130",
            "snapshot_credential_profile": "snapshot130",
            "verification": {"method": "linux-ssh", "ssh_key": "unused-key"},
        }
        self.preview = {"vmid": 130, "snapshot": "checkpoint-001", "status": "DRY_RUN_POLICY_ONLY", "changes_applied": False}
        self.patchers = {}
        defaults = {
            "plan_snapshot_create": self.preview,
            "get_restore_target": self.target,
            "list_approved_snapshots": {"snapshots": [{"name": "baseline-clean"}]},
            "check_restore_token": {"vm_status": "running"},
            "submit_vm_power": {"status": "SUBMITTED_UNVERIFIED", "task_id": "MOCK-UPID"},
            "_wait_for_task": {"task_status": "TASK_SUCCEEDED", "exitstatus": "OK"},
            "_wait_for_state": {"vm_status": "stopped"},
            "_wait_for_snapshot_guest": {"guest_ready": True},
            "create_snapshot": {"status": "CREATED_VERIFIED", "task_id": "SNAP-UPID", "changes_applied": True},
            "save_restore_report": "mock-evidence.json",
        }
        for name, value in defaults.items():
            patcher = patch.object(cli, name, return_value=value)
            self.patchers[name] = patcher.start()
            self.addCleanup(patcher.stop)
        credential_patcher = patch.object(cli, "get_restore_credential", side_effect=lambda profile, vmid, node: {
            "token_id": f"fake@pve!{profile}", "token_file": "not-used",
        })
        self.credential_mock = credential_patcher.start()
        self.addCleanup(credential_patcher.stop)
        path_patcher = patch.object(cli.Path, "is_file", return_value=True)
        path_patcher.start()
        self.addCleanup(path_patcher.stop)
        self.patchers["list_approved_snapshots"].side_effect = [
            {"snapshots": [{"name": "baseline-clean"}]},
            {"snapshots": [{"name": "baseline-clean"}, {"name": "checkpoint-001"}]},
        ]

    def run_create(self):
        return cli.snapshot_create_lifecycle(
            130, "checkpoint-001", execute=True,
            confirmation="CREATE-SNAPSHOT-130-checkpoint-001", max_checks=2, interval=0,
        )

    def test_dry_run_does_not_contact_proxmox(self):
        result = cli.snapshot_create_lifecycle(130, "checkpoint-001")
        self.assertEqual(result["status"], "DRY_RUN_POLICY_ONLY")
        self.patchers["submit_vm_power"].assert_not_called()
        self.patchers["create_snapshot"].assert_not_called()
        self.patchers["check_restore_token"].assert_not_called()

    def test_incorrect_confirmation_rejected_before_power_calls(self):
        with self.assertRaises(PermissionError):
            cli.snapshot_create_lifecycle(130, "checkpoint-001", execute=True, confirmation="wrong")
        self.patchers["submit_vm_power"].assert_not_called()

    def test_running_vm_shutdown_snapshot_restart(self):
        result = self.run_create()
        self.assertEqual(result["status"], "CREATED_VERIFIED")
        self.assertEqual(result["initial_vm_status"], "running")
        calls = self.patchers["submit_vm_power"].call_args_list
        self.assertEqual([c.args[1] for c in calls], ["shutdown", "start"])
        self.assertEqual(self.patchers["create_snapshot"].call_count, 1)
        self.assertTrue(result["guest_readiness"]["guest_ready"])
        self.patchers["save_restore_report"].assert_called_once()

    def test_initially_stopped_vm_stays_stopped(self):
        self.patchers["check_restore_token"].return_value = {"vm_status": "stopped"}
        result = self.run_create()
        self.assertEqual(result["status"], "CREATED_VERIFIED")
        self.patchers["submit_vm_power"].assert_not_called()
        self.assertEqual(result["initial_vm_status"], "stopped")

    def test_duplicate_name_blocks_before_shutdown(self):
        self.patchers["list_approved_snapshots"].side_effect = None
        self.patchers["list_approved_snapshots"].return_value = {"snapshots": [
            {"name": "baseline-clean"}, {"name": "checkpoint-001"},
        ]}
        with self.assertRaises(FileExistsError):
            self.run_create()
        self.patchers["submit_vm_power"].assert_not_called()
        self.patchers["create_snapshot"].assert_not_called()

    def test_missing_baseline_blocks_before_shutdown(self):
        self.patchers["list_approved_snapshots"].side_effect = None
        self.patchers["list_approved_snapshots"].return_value = {
            "snapshots": [{"name": "other-checkpoint"}],
        }
        with self.assertRaises(RuntimeError):
            self.run_create()
        self.patchers["submit_vm_power"].assert_not_called()
        self.patchers["create_snapshot"].assert_not_called()

    def test_disagreeing_power_states_block_before_shutdown(self):
        self.patchers["check_restore_token"].side_effect = [
            {"vm_status": "running"}, {"vm_status": "stopped"},
        ]
        with self.assertRaises(RuntimeError):
            self.run_create()
        self.patchers["submit_vm_power"].assert_not_called()

    def test_reused_credential_is_rejected(self):
        self.credential_mock.side_effect = lambda profile, vmid, node: {
            "token_id": "same-token", "token_file": "not-used",
        }
        with self.assertRaises(PermissionError):
            self.run_create()
        self.patchers["submit_vm_power"].assert_not_called()

    def test_unconfirmed_shutdown_does_not_create_snapshot(self):
        self.patchers["_wait_for_task"].side_effect = TimeoutError("pending")
        result = self.run_create()
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertEqual(result["error_type"], "TimeoutError")
        self.patchers["create_snapshot"].assert_not_called()
        self.assertEqual(
            [c.args[1] for c in self.patchers["submit_vm_power"].call_args_list],
            ["shutdown"],
        )

    def test_failed_snapshot_never_auto_restarts(self):
        self.patchers["create_snapshot"].return_value = {"status": "INCOMPLETE", "changes_applied": True}
        result = self.run_create()
        self.assertEqual(result["status"], "INCOMPLETE")
        power_calls = self.patchers["submit_vm_power"].call_args_list
        self.assertEqual([c.args[1] for c in power_calls], ["shutdown"])
        self.patchers["save_restore_report"].assert_called_once()


if __name__ == "__main__":
    unittest.main()
