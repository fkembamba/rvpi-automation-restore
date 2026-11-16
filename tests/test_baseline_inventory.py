
import unittest
from unittest.mock import patch

from rvpi_automation.baseline_inventory import check_baselines


class BaselineInventoryTests(unittest.TestCase):

    @patch("rvpi_automation.baseline_inventory.verify_baseline")
    def test_multiple_vm_baselines(self, mock_verify):
        mock_verify.side_effect = [
            {
                "vmid": 100,
                "baseline": "baseline-clean",
                "status": "READY",
                "exists": True
            },
            {
                "vmid": 103,
                "baseline": "baseline-clean",
                "status": "MISSING_BASELINE",
                "exists": False
            }
        ]

        results = check_baselines([100, 103])

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["status"], "READY")
        self.assertEqual(
            results[1]["status"], "MISSING_BASELINE"
        )
        self.assertEqual(mock_verify.call_count, 2)


if __name__ == "__main__":
    unittest.main()
