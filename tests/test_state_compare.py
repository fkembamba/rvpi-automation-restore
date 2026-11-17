
"""Unit tests for RVPI restoration state comparison."""

import unittest

from rvpi_automation.state_compare import compare_file_states


class StateCompareTests(unittest.TestCase):

    def setUp(self):
        self.baseline = [{
            "path": "baseline.txt",
            "exists": True,
            "size_bytes": 10,
            "sha256": "abc123"
        }]

    def test_matching_states(self):
        observed = [self.baseline[0].copy()]

        result = compare_file_states(self.baseline, observed)

        self.assertEqual(result["status"], "MATCH")
        self.assertEqual(result["files_checked"], 1)
        self.assertEqual(result["differences"], [])

    def test_modified_file_detected(self):
        observed = [{
            "path": "baseline.txt",
            "exists": True,
            "size_bytes": 10,
            "sha256": "different456"
        }]

        result = compare_file_states(self.baseline, observed)

        self.assertEqual(result["status"], "MISMATCH")
        self.assertTrue(result["differences"])

    def test_missing_file_detected(self):
        observed = [{
            "path": "baseline.txt",
            "exists": False,
            "size_bytes": None,
            "sha256": None
        }]

        result = compare_file_states(self.baseline, observed)

        self.assertEqual(result["status"], "MISMATCH")

    def test_missing_evidence_detected(self):
        result = compare_file_states(self.baseline, [])

        self.assertEqual(result["status"], "MISMATCH")
        self.assertEqual(
            result["differences"][0]["reason"],
            "MISSING_EVIDENCE"
        )

    def test_duplicate_paths_rejected(self):
        observed = [
            self.baseline[0].copy(),
            self.baseline[0].copy()
        ]

        with self.assertRaises(ValueError):
            compare_file_states(self.baseline, observed)


if __name__ == "__main__":
    unittest.main()
