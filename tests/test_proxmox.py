"""No-network tests for starter client validation."""
import os
import unittest
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


if __name__ == "__main__":
    unittest.main()
