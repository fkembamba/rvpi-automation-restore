"""Safety/regression tests for the generic rvpi_lab CLI."""

import unittest
from unittest.mock import call, patch

import rvpi_lab as cli


TARGET = {
    "vmid": 130,
    "node": "pve",
    "baseline": "baseline-clean",
    "credential_profile": "rollback130",
    "power_credential_profile": "power130",
    "verification": {"method": "linux-ssh"},
}


class GenericRestoreCLITests(unittest.TestCase):
    def test_dry_run_never_changes_vm(self):
        with patch.object(cli, "get_restore_target", return_value=TARGET), \
             patch.object(cli, "submit_vm_power") as power, \
             patch.object(cli, "submit_restore") as restore:
            result = cli.restore_test(130)
        self.assertEqual(result["status"], "DRY_RUN")
        self.assertFalse(result["changes_applied"])
        power.assert_not_called()
        restore.assert_not_called()

    def test_unauthorized_vm_blocked(self):
        with patch.object(cli, "get_restore_target", side_effect=PermissionError("Not approved")), \
             patch.object(cli, "submit_restore") as restore:
            with self.assertRaises(PermissionError):
                cli.restore_test(100)
        restore.assert_not_called()

    def test_execute_requires_exact_confirmation(self):
        with patch.object(cli, "get_restore_target", return_value=TARGET), \
             patch.object(cli, "check_restore_token") as api:
            with self.assertRaises(PermissionError):
                cli.restore_test(130, execute=True, confirmation="wrong")
        api.assert_not_called()

    def test_successful_full_lifecycle(self):
        with patch.object(cli, "get_restore_target", return_value=TARGET), \
             patch.object(cli, "check_restore_token", side_effect=[
                 {"vm_status": "running"}, {"vm_status": "running"}, {"vm_status": "stopped"},
                 {"vm_status": "stopped"}, {"vm_status": "running"}
             ]), \
             patch.object(cli, "get_restore_credential", side_effect=lambda profile, vmid, node: {"token_id": profile}), \
             patch.object(cli, "_preflight_baseline_and_verifier"), \
             patch.object(cli, "submit_vm_power", side_effect=[
                 {"status": "SUBMITTED_UNVERIFIED", "task_id": "SHUTDOWN-UPID"},
                 {"status": "SUBMITTED_UNVERIFIED", "task_id": "START-UPID"},
             ]) as power, \
             patch.object(cli, "read_vm_power_task_status", return_value={
                 "task_status": "TASK_SUCCEEDED", "exitstatus": "OK"
             }), \
             patch.object(cli, "submit_restore", return_value={
                 "status": "SUBMITTED_UNVERIFIED", "task_id": "ROLLBACK-UPID"
             }) as restore, \
             patch.object(cli, "read_restore_task_status", return_value={
                 "task_status": "TASK_SUCCEEDED", "exitstatus": "OK"
             }), \
             patch.object(cli, "verify_restoration", return_value={
                 "verification_status": "PASS", "differences": []
             }), \
             patch.object(cli, "save_restore_report", return_value="/tmp/test-report.json") as save:
            result = cli.restore_test(
                130, execute=True, confirmation="RESTORE-130-baseline-clean",
                max_checks=1, interval=0,
            )
        self.assertEqual(result["status"], "VERIFIED")
        self.assertEqual(result["evidence_file"], "/tmp/test-report.json")
        self.assertTrue(result["changes_applied"])
        power.assert_has_calls([
            call(130, "shutdown", "POWER-SHUTDOWN-130", execute=True),
            call(130, "start", "POWER-START-130", execute=True),
        ])
        restore.assert_called_once_with(130, "ROLLBACK-130-baseline-clean")
        save.assert_called_once()

    def test_failed_rollback_never_starts_vm(self):
        with patch.object(cli, "get_restore_target", return_value=TARGET), \
             patch.object(cli, "check_restore_token", return_value={"vm_status": "stopped"}), \
             patch.object(cli, "get_restore_credential", side_effect=lambda profile, vmid, node: {"token_id": profile}), \
             patch.object(cli, "_preflight_baseline_and_verifier"), \
             patch.object(cli, "submit_vm_power") as power, \
             patch.object(cli, "submit_restore", return_value={
                 "status": "SUBMITTED_UNVERIFIED", "task_id": "ROLLBACK-UPID"
             }), \
             patch.object(cli, "read_restore_task_status", return_value={
                 "task_status": "TASK_FAILED", "exitstatus": "simulated failure"
             }), \
             patch.object(cli, "save_restore_report", return_value="/tmp/failure.json"):
            result = cli.restore_test(
                130, execute=True, confirmation="RESTORE-130-baseline-clean",
                max_checks=1, interval=0,
            )
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertEqual(result["error_type"], "RuntimeError")
        power.assert_not_called()

    def test_missing_task_id_is_not_success(self):
        with self.assertRaises(RuntimeError):
            cli._wait_for_task(None, lambda task: None, max_checks=1, interval=0)

    def test_success_requires_explicit_ok_exitstatus(self):
        with self.assertRaises(RuntimeError):
            cli._wait_for_task(
                "MOCK-UPID",
                lambda _: {"task_status": "TASK_SUCCEEDED"},
                max_checks=1,
                interval=0,
            )


if __name__ == "__main__":
    unittest.main()
