
import unittest
from unittest.mock import patch

from rvpi_automation.restore import plan_restore


class RestorePlanningTests(unittest.TestCase):

    @patch("rvpi_automation.restore.verify_baseline")
    def test_restore_plan_ready(self, mock_verify):
        mock_verify.return_value = {
            "vmid": 100,
            "exists": True,
            "status": "READY"
        }

        result = plan_restore(100)

        self.assertEqual(result["status"], "PLAN_READY")
        self.assertFalse(result["changes_applied"])
        self.assertFalse(result["execution_authorized"])

    @patch("rvpi_automation.restore.verify_baseline")
    def test_missing_baseline(self, mock_verify):
        mock_verify.return_value = {
            "vmid": 100,
            "exists": False,
            "status": "MISSING_BASELINE"
        }

        result = plan_restore(100)

        self.assertEqual(
            result["status"],
            "BLOCKED_MISSING_BASELINE"
        )
        self.assertFalse(result["changes_applied"])

    @patch("rvpi_automation.restore.verify_baseline")
    def test_protected_vm_blocked(self, mock_verify):
        result = plan_restore(102)

        self.assertEqual(
            result["status"],
            "BLOCKED_UNAPPROVED_VM"
        )
        mock_verify.assert_not_called()

    def test_invalid_vmid(self):
        with self.assertRaises(ValueError):
            plan_restore(-1)


if __name__ == "__main__":
    unittest.main()
