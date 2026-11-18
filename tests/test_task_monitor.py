
import unittest

from rvpi_automation.task_monitor import interpret_task_status


class TestTaskMonitor(unittest.TestCase):

    def test_running_task(self):
        result = interpret_task_status({
            "status": "running"
        })
        self.assertEqual(result["task_status"], "RUNNING")
        self.assertFalse(result["task_succeeded"])

    def test_successful_task(self):
        result = interpret_task_status({
            "status": "stopped",
            "exitstatus": "OK"
        })
        self.assertEqual(result["task_status"], "TASK_SUCCEEDED")
        self.assertTrue(result["task_succeeded"])
        self.assertFalse(result["restoration_verified"])

    def test_failed_task(self):
        result = interpret_task_status({
            "status": "stopped",
            "exitstatus": "permission denied"
        })
        self.assertEqual(result["task_status"], "TASK_FAILED")
        self.assertFalse(result["task_succeeded"])

    def test_missing_exit_status(self):
        result = interpret_task_status({
            "status": "stopped"
        })
        self.assertEqual(result["task_status"], "TASK_UNKNOWN")

    def test_unknown_task_status(self):
        with self.assertRaises(ValueError):
            interpret_task_status({
                "status": "invalid"
            })

    def test_invalid_response(self):
        with self.assertRaises(ValueError):
            interpret_task_status(None)


if __name__ == "__main__":
    unittest.main()
