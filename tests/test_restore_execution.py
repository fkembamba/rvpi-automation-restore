
"""Unit tests for RVPI controlled restoration preflight checks."""

import unittest
from unittest.mock import patch

from rvpi_automation import restore_execution as execution


class RestoreExecutionTests(unittest.TestCase):

    def setUp(self):
        inventory_patch = patch.object(
            execution,
            "list_vms",
            return_value=[
                {
                    "vmid": 130,
                    "node": "pve",
                    "status": "stopped",
                }
            ],
        )

        baseline_patch = patch.object(
            execution,
            "verify_baseline",
            return_value={
                "vmid": 130,
                "baseline": "baseline-clean",
                "exists": True,
                "status": "READY",
            },
        )

        self.mock_inventory = inventory_patch.start()
        self.mock_baseline = baseline_patch.start()

        self.addCleanup(inventory_patch.stop)
        self.addCleanup(baseline_patch.stop)

    def test_stopped_vm_ready(self):
        result = execution.plan_restore_execution(130)

        self.assertEqual(result["status"], "DRY_RUN_READY")
        self.assertEqual(result["vm_status"], "stopped")
        self.assertFalse(result["changes_applied"])
        self.assertFalse(result["execution_authorized"])

        self.mock_baseline.assert_called_once_with(
            130,
            baseline_name="baseline-clean",
            node="pve",
        )

    def test_running_vm_blocked(self):
        self.mock_inventory.return_value[0]["status"] = "running"

        result = execution.plan_restore_execution(130)

        self.assertEqual(
            result["status"],
            "BLOCKED_VM_NOT_STOPPED",
        )
        self.assertFalse(result["execution_authorized"])

    def test_missing_baseline_blocked(self):
        self.mock_baseline.return_value["exists"] = False

        result = execution.plan_restore_execution(130)

        self.assertEqual(
            result["status"],
            "BLOCKED_MISSING_BASELINE",
        )
        self.assertFalse(result["changes_applied"])

    def test_vm_not_found_blocked(self):
        self.mock_inventory.return_value = []

        result = execution.plan_restore_execution(130)

        self.assertEqual(
            result["status"],
            "BLOCKED_VM_NOT_FOUND",
        )
        self.mock_baseline.assert_not_called()

    def test_unapproved_vm_rejected(self):
        with self.assertRaises(ValueError):
            execution.plan_restore_execution(100)

        self.mock_inventory.assert_not_called()
        self.mock_baseline.assert_not_called()

    def test_wrong_node_blocked(self):
        result = execution.plan_restore_execution(
            130,
            node="unknown-node",
        )

        self.assertEqual(
            result["status"],
            "BLOCKED_VM_NOT_FOUND",
        )
        self.mock_baseline.assert_not_called()


if __name__ == "__main__":
    unittest.main()
