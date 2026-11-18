
"""Unit tests for automated RVPI restoration verification."""

import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from rvpi_automation import restore_verification as verifier


class RestoreVerificationTests(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

        folder = Path(self.temp_dir.name)

        self.ssh_key = folder / "test-key"
        self.ssh_key.write_text("test-key", encoding="utf-8")

        self.reference_file = folder / "reference.sha256"
        self.baseline_hash = "a" * 64

        self.reference_file.write_text(
            f"{self.baseline_hash}  /etc/hostname\n",
            encoding="utf-8",
        )

        key_patch = patch.object(
            verifier, "SSH_KEY", self.ssh_key
        )
        reference_patch = patch.object(
            verifier, "REFERENCE_FILE", self.reference_file
        )

        key_patch.start()
        reference_patch.start()

        self.addCleanup(key_patch.stop)
        self.addCleanup(reference_patch.stop)

    @patch("rvpi_automation.restore_verification.subprocess.run")
    def test_successful_restoration(self, mock_run):
        mock_run.return_value = SimpleNamespace(
            stdout=(
                f"{self.baseline_hash}  /etc/hostname\n"
                "MARKER_ABSENT\n"
            )
        )

        result = verifier.verify_restoration(130)

        self.assertEqual(result["verification_status"], "PASS")
        self.assertTrue(result["hostname_sha256_match"])
        self.assertTrue(result["post_snapshot_marker_absent"])
        self.assertEqual(result["differences"], [])
        self.assertFalse(result["changes_applied"])

    @patch("rvpi_automation.restore_verification.subprocess.run")
    def test_hostname_mismatch(self, mock_run):
        mock_run.return_value = SimpleNamespace(
            stdout=f"{'b' * 64}  /etc/hostname\nMARKER_ABSENT\n"
        )

        result = verifier.verify_restoration(130)

        self.assertEqual(result["verification_status"], "FAIL")
        self.assertFalse(result["hostname_sha256_match"])
        self.assertTrue(result["differences"])

    @patch("rvpi_automation.restore_verification.subprocess.run")
    def test_marker_still_present(self, mock_run):
        mock_run.return_value = SimpleNamespace(
            stdout=(
                f"{self.baseline_hash}  /etc/hostname\n"
                "MARKER_PRESENT\n"
            )
        )

        result = verifier.verify_restoration(130)

        self.assertEqual(result["verification_status"], "FAIL")
        self.assertFalse(result["post_snapshot_marker_absent"])
        self.assertTrue(result["differences"])

    @patch("rvpi_automation.restore_verification.subprocess.run")
    def test_ssh_failure(self, mock_run):
        mock_run.side_effect = subprocess.CalledProcessError(
            255, "ssh"
        )

        with self.assertRaises(subprocess.CalledProcessError):
            verifier.verify_restoration(130)

    @patch("rvpi_automation.restore_verification.subprocess.run")
    def test_unapproved_vm_rejected(self, mock_run):
        with self.assertRaises(ValueError):
            verifier.verify_restoration(100)

        mock_run.assert_not_called()

    @patch("rvpi_automation.restore_verification.subprocess.run")
    def test_incomplete_evidence_rejected(self, mock_run):
        mock_run.return_value = SimpleNamespace(
            stdout=f"{self.baseline_hash}  /etc/hostname\n"
        )

        with self.assertRaises(ValueError):
            verifier.verify_restoration(130)


if __name__ == "__main__":
    unittest.main()
