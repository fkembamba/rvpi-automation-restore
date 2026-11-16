"""No-network tests for starter client validation."""
import os
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from rvpi_automation.proxmox import load_token_secret
from unittest.mock import patch
from rvpi_automation.proxmox import list_vms


class ProxmoxTests(unittest.TestCase):
    def test_requires_configuration(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "PVE_URL"):
                list_vms()

    def test_requires_tls_ca(self):
        settings = {"PVE_URL": "https://pve.example:8006", "PVE_TOKEN_ID": "user@pve!readonly", "PVE_TOKEN_SECRET": "test"}
        with patch.dict(os.environ, settings, clear=True):
            with self.assertRaisesRegex(ValueError, "PVE_CA_CERT"):
                list_vms()

    def test_load_token_secret_from_file(self):
    

        sample = "│ value │ TEST-SECRET-123 │"

        with tempfile.TemporaryDirectory() as directory:
            token_file = Path(directory) / "token.txt"
            token_file.write_text(sample, encoding="utf-8")

            with patch.dict(os.environ, {
                "PVE_TOKEN_FILE": str(token_file),
                "PVE_TOKEN_SECRET": ""
            }):
                self.assertEqual(
                    load_token_secret(),
                    "TEST-SECRET-123"
                )


if __name__ == "__main__":
    unittest.main()
