
"""Safety tests for sequential RVPI restoration."""

import unittest
from unittest.mock import call, patch

from rvpi_automation import restore_executor as executor


class RestoreBatchExecutionTests(unittest.TestCase):

    def setUp(self):
        self.vmids = [130, 131]
        self.confirmations = {
            130: "ROLLBACK-130-baseline-clean",
            131: "ROLLBACK-131-baseline-clean",
        }

        plan = {
            "total_vms": 2,
            "all_ready": True,
            "results": [
                {
                    "vmid": vmid,
                    "baseline": "baseline-clean",
                    "status": "DRY_RUN_READY",
                    "ready": True,
                }
                for vmid in self.vmids
            ],
            "changes_applied": False,
        }

        self.plan = self.mock_function("plan_restore_batch")
        self.submit = self.mock_function("submit_restore")
        self.monitor = self.mock_function("read_restore_task_status")

        self.plan.return_value = plan

        self.submit.side_effect = (
            lambda vmid, confirmation: {
                "task_id": f"MOCK-TASK-{vmid}"
            }
        )

        self.monitor.return_value = {
            "task_status": "TASK_SUCCEEDED",
            "exitstatus": "OK",
        }

        sleep_patch = patch.object(executor.time, "sleep")
        sleep_patch.start()
        self.addCleanup(sleep_patch.stop)

    def mock_function(self, name):
        patcher = patch.object(executor, name)
        mocked = patcher.start()
        self.addCleanup(patcher.stop)
        return mocked

    def test_default_is_dry_run(self):
        result = executor.execute_restore_batch(self.vmids)

        self.assertEqual(result["status"], "DRY_RUN")
        self.assertFalse(result["execution_performed"])
        self.submit.assert_not_called()

    def test_two_vms_processed_sequentially(self):
        result = executor.execute_restore_batch(
            self.vmids,
            self.confirmations,
            execute=True,
        )

        self.assertEqual(
            result["status"],
            "TASKS_SUCCEEDED_GUESTS_UNVERIFIED",
        )
        self.assertEqual(result["processed"], 2)
        self.assertFalse(result["restoration_verified"])

        self.submit.assert_has_calls([
            call(130, self.confirmations[130]),
            call(131, self.confirmations[131]),
        ])

        self.monitor.assert_has_calls([
            call("MOCK-TASK-130", vmid=130),
            call("MOCK-TASK-131", vmid=131),
        ])

    def test_missing_confirmation_blocks_batch(self):
        with self.assertRaises(PermissionError):
            executor.execute_restore_batch(
                self.vmids,
                {130: self.confirmations[130]},
                execute=True,
            )

        self.submit.assert_not_called()

    def test_failed_preflight_blocks_batch(self):
        self.plan.return_value["all_ready"] = False

        with self.assertRaises(RuntimeError):
            executor.execute_restore_batch(
                self.vmids,
                self.confirmations,
                execute=True,
            )

        self.submit.assert_not_called()

    def test_failed_task_stops_next_vm(self):
        self.monitor.return_value = {
            "task_status": "TASK_FAILED",
            "exitstatus": "simulated failure",
        }

        result = executor.execute_restore_batch(
            self.vmids,
            self.confirmations,
            execute=True,
        )

        self.assertEqual(result["status"], "BATCH_INCOMPLETE")
        self.assertEqual(result["processed"], 1)
        self.assertEqual(self.submit.call_count, 1)

    def test_timeout_stops_next_vm(self):
        self.monitor.return_value = {
            "task_status": "RUNNING",
        }

        result = executor.execute_restore_batch(
            self.vmids,
            self.confirmations,
            execute=True,
            max_checks=2,
            poll_interval=0,
        )

        self.assertEqual(result["status"], "BATCH_INCOMPLETE")
        self.assertEqual(
            result["results"][0]["status"],
            "TIMEOUT_UNVERIFIED",
        )
        self.assertEqual(self.submit.call_count, 1)
        self.assertEqual(self.monitor.call_count, 2)

    
    def test_submission_error_reports_uncertainty(self):
        self.submit.side_effect = RuntimeError(
            "Simulated ambiguous submission error"
        )

        result = executor.execute_restore_batch(
            self.vmids,
            self.confirmations,
            execute=True,
        )

        self.assertEqual(result["status"], "BATCH_INCOMPLETE")
        self.assertFalse(result["execution_performed"])
        self.assertTrue(result["submission_outcome_uncertain"])
        self.assertEqual(self.submit.call_count, 1)
        self.monitor.assert_not_called()



if __name__ == "__main__":
    unittest.main()
