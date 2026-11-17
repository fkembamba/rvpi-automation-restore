
"""Unit tests for RVPI file-state evidence capture."""

import hashlib
import tempfile
import unittest
from pathlib import Path

from rvpi_automation.state_capture import capture_file_state


class StateCaptureTests(unittest.TestCase):

    def test_existing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "baseline.txt"
            content = b"RVPI clean baseline"
            path.write_bytes(content)

            result = capture_file_state([path])[0]

            self.assertTrue(result["exists"])
            self.assertEqual(result["size_bytes"], len(content))
            self.assertEqual(
                result["sha256"],
                hashlib.sha256(content).hexdigest()
            )

    def test_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "created-after-snapshot.txt"

            result = capture_file_state([path])[0]

            self.assertFalse(result["exists"])
            self.assertIsNone(result["size_bytes"])
            self.assertIsNone(result["sha256"])

    def test_empty_file_list_rejected(self):
        with self.assertRaises(ValueError):
            capture_file_state([])

    def test_directory_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                capture_file_state([tmp])


if __name__ == "__main__":
    unittest.main()
