
"""Safety tests for controlled RVPI snapshot rollback submission."""

import io
import json
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from rvpi_automation import restore_executor as executor


class RollbackSubmissionTests(unittest.TestCase):

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)

        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)

        token_file = Path(temp.name) / "test-token.json"
        token_file.write_text(
            json.dumps({
                "full-tokenid": executor.TOKEN_ID,
                "value": "fake-test-secret",
            }),
            encoding="utf-8",
        )

        self.stack.enter_context(
            patch.object(executor, "TOKEN_FILE", token_file)
        )

        self.mock_plan = self.stack.enter_context(
            patch.object(
                executor,
                "plan_restore_execution",
                return_value={"status": "DRY_RUN_READY"},
            )
        )

        self.mock_status = self.stack.enter_context(
            patch.object(
                executor,
                "check_restore_token",
                return_value={"vm_status": "stopped"},
            )
        )

        self.mock_tls = self.stack.enter_context(
            patch.object(executor.ssl, "create_default_context")
        )

        self.mock_urlopen = self.stack.enter_context(
            patch.object(executor.urllib.request, "urlopen")
        )

        self.mock_urlopen.return_value = io.BytesIO(
            b'{"data": "UPID:pve:test-task"}'
        )

    def test_unapproved_vm_rejected(self):
        with self.assertRaises(PermissionError):
            executor.submit_restore(
                100, executor.CONFIRMATION
            )

        self.mock_plan.assert_not_called()
        self.mock_urlopen.assert_not_called()

    def test_missing_confirmation_rejected(self):
        with self.assertRaises(PermissionError):
            executor.submit_restore(
                130, "wrong-confirmation"
            )

        self.mock_plan.assert_not_called()
        self.mock_urlopen.assert_not_called()

    def test_failed_preflight_blocks_rollback(self):
        self.mock_plan.return_value = {
            "status": "BLOCKED_VM_NOT_STOPPED"
        }

        with self.assertRaises(RuntimeError):
            executor.submit_restore(
                130, executor.CONFIRMATION
            )

        self.mock_urlopen.assert_not_called()

    def test_running_vm_blocks_rollback(self):
        self.mock_status.return_value = {
            "vm_status": "running"
        }

        with self.assertRaises(RuntimeError):
            executor.submit_restore(
                130, executor.CONFIRMATION
            )

        self.mock_urlopen.assert_not_called()

    def test_authorized_request_is_submitted(self):
        result = executor.submit_restore(
            130, executor.CONFIRMATION
        )

        self.assertEqual(
            result["status"], "SUBMITTED_UNVERIFIED"
        )
        self.assertFalse(result["restoration_verified"])
        self.assertEqual(result["vmid"], 130)

        self.mock_urlopen.assert_called_once()

        request = self.mock_urlopen.call_args.args[0]

        self.assertEqual(request.get_method(), "POST")
        self.assertIn(
            "/qemu/130/snapshot/baseline-clean/rollback",
            request.full_url,
        )


if __name__ == "__main__":
    unittest.main()
