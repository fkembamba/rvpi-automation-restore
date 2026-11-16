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

    def test_list_snapshots_excludes_current(self):
        import json
        from unittest.mock import patch, MagicMock
        from rvpi_automation.proxmox import list_snapshots

        mock_response = MagicMock()
        mock_response.__enter__.return_value = mock_response

        payload = {
            "data": [
                {"name": "current"},
                {
                    "name": "baseline-clean",
                    "description": "Clean VM baseline",
                    "snaptime": 1790000000
                }
            ]
        }

        with patch.dict("os.environ", {
            "PVE_URL": "https://pve.aicyber.rw:8006",
            "PVE_TOKEN_ID": "automation@pve!readonly",
            "PVE_TOKEN_SECRET": "TEST-ONLY-SECRET",
            "PVE_CA_CERT": "test-ca.pem"
        }):
            with patch("rvpi_automation.proxmox.ssl.create_default_context"):
                with patch(
                    "rvpi_automation.proxmox.urlopen",
                    return_value=mock_response
                ):
                    with patch(
                        "rvpi_automation.proxmox.json.load",
                        return_value=payload
                    ):
                        result = list_snapshots(100)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "baseline-clean")


if __name__ == "__main__":
    unittest.main()
