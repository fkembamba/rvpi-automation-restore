
"""Unit tests for RVPI restoration-token authentication."""

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rvpi_automation import restore_token


class RestoreTokenTests(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

        folder = Path(self.temp_dir.name)

        self.token_file = folder / "token.json"
        self.ca_cert = folder / "pve-root-ca.pem"

        self.ca_cert.write_text(
            "TEST CA CERTIFICATE",
            encoding="utf-8"
        )

        self.write_token()

        token_patch = patch.object(
            restore_token, "TOKEN_FILE", self.token_file
        )
        ca_patch = patch.object(
            restore_token, "CA_CERT", self.ca_cert
        )

        token_patch.start()
        ca_patch.start()

        self.addCleanup(token_patch.stop)
        self.addCleanup(ca_patch.stop)

    def write_token(self, token_id=None, secret="fake-test-secret"):
        data = {
            "full-tokenid": (
                token_id
                if token_id is not None
                else restore_token.TOKEN_ID
            ),
            "value": secret,
        }

        self.token_file.write_text(
            json.dumps(data),
            encoding="utf-8"
        )

    @patch("rvpi_automation.restore_token.ssl.create_default_context")
    @patch("rvpi_automation.restore_token.urllib.request.urlopen")
    def test_successful_authentication(self, mock_open, mock_tls):
        mock_open.return_value = io.BytesIO(
            b'{"data": {"status": "stopped"}}'
        )

        result = restore_token.check_restore_token()

        self.assertTrue(result["token_authenticated"])
        self.assertEqual(result["vmid"], 130)
        self.assertEqual(result["vm_status"], "stopped")
        self.assertFalse(result["changes_applied"])

        request = mock_open.call_args.args[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertIn("/qemu/130/status/current", request.full_url)

        mock_tls.assert_called_once_with(
            cafile=str(self.ca_cert)
        )

    @patch("rvpi_automation.restore_token.urllib.request.urlopen")
    def test_wrong_token_identity(self, mock_open):
        self.write_token(token_id="wrong@pve!token")

        with self.assertRaises(ValueError):
            restore_token.check_restore_token()

        mock_open.assert_not_called()

    @patch("rvpi_automation.restore_token.urllib.request.urlopen")
    def test_missing_secret(self, mock_open):
        self.write_token(secret="")

        with self.assertRaises(ValueError):
            restore_token.check_restore_token()

        mock_open.assert_not_called()

    @patch("rvpi_automation.restore_token.urllib.request.urlopen")
    def test_missing_token_file(self, mock_open):
        self.token_file.unlink()

        with self.assertRaises(FileNotFoundError):
            restore_token.check_restore_token()

        mock_open.assert_not_called()

    @patch("rvpi_automation.restore_token.urllib.request.urlopen")
    def test_missing_ca_certificate(self, mock_open):
        self.ca_cert.unlink()

        with self.assertRaises(FileNotFoundError):
            restore_token.check_restore_token()

        mock_open.assert_not_called()

    @patch("rvpi_automation.restore_token.ssl.create_default_context")
    @patch("rvpi_automation.restore_token.urllib.request.urlopen")
    def test_api_connection_failure(self, mock_open, mock_tls):
        mock_open.side_effect = OSError(
            "Simulated Proxmox connection failure"
        )

        with self.assertRaises(OSError):
            restore_token.check_restore_token()


if __name__ == "__main__":
    unittest.main()
