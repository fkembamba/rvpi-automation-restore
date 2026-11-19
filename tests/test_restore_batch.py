
"""Unit tests for RVPI multi-VM restoration planning."""

import unittest
from unittest.mock import patch

from rvpi_automation import restore_executor as executor


class RestoreBatchTests(unittest.TestCase):

    def setUp(self):
        # Simulated targets; no real VM 131 is authorized.
        self.targets = {
            130: {
                "node": "pve",
                "baseline": "baseline-clean",
                "credential_profile": "rollback130",
            },
            131: {
                "node": "pve",
                "baseline": "baseline-clean",
                "credential_profile": "rollback131",
            },
        }

        def lookup_target(vmid):
            if vmid not in self.targets:
                raise PermissionError(
                    f"VM {vmid} is not approved"
                )
            return self.targets[vmid]

        self.policy = patch.object(
            executor,
            "get_restore_target",
            side_effect=lookup_target,
        ).start()

        self.credential = patch.object(
            executor,
            "get_restore_credential",
            return_value={"token_id": "fake-test-token"},
        ).start()

        self.preflight = patch.object(
            executor,
            "plan_restore_execution",
            return_value={"status": "DRY_RUN_READY"},
        ).start()

        self.api = patch.object(
            executor.urllib.request,
            "urlopen",
        ).start()

        self.addCleanup(patch.stopall)

    def test_two_approved_vms(self):
        result = executor.plan_restore_batch([130, 131])

        self.assertEqual(result["total_vms"], 2)
        self.assertTrue(result["all_ready"])
        self.assertTrue(
            all(item["ready"] for item in result["results"])
        )
        self.assertFalse(result["changes_applied"])
        self.assertEqual(self.preflight.call_count, 2)
        self.api.assert_not_called()

    def test_unauthorized_vm_blocked(self):
        result = executor.plan_restore_batch([130, 100])

        self.assertFalse(result["all_ready"])
        self.assertTrue(result["results"][0]["ready"])
        self.assertEqual(
            result["results"][1]["status"], "BLOCKED"
        )
        self.assertEqual(self.preflight.call_count, 1)
        self.api.assert_not_called()

    def test_missing_credential_blocks_vm(self):
        def credential_check(profile, vmid, node):
            if vmid == 131:
                raise PermissionError("No authorized credential")
            return {"token_id": "fake-test-token"}

        self.credential.side_effect = credential_check

        result = executor.plan_restore_batch([130, 131])

        self.assertFalse(result["all_ready"])
        self.assertEqual(
            result["results"][1]["status"], "BLOCKED"
        )
        self.api.assert_not_called()

    def test_vm_not_stopped(self):
        self.preflight.return_value = {
            "status": "BLOCKED_VM_NOT_STOPPED"
        }

        result = executor.plan_restore_batch([130])

        self.assertFalse(result["all_ready"])
        self.assertFalse(result["results"][0]["ready"])
        self.api.assert_not_called()

    def test_preflight_error_recorded(self):
        self.preflight.side_effect = RuntimeError(
            "Simulated Proxmox connection error"
        )

        result = executor.plan_restore_batch([130])

        self.assertFalse(result["all_ready"])
        self.assertEqual(
            result["results"][0]["status"], "PREFLIGHT_ERROR"
        )
        self.api.assert_not_called()

    def test_invalid_vm_lists(self):
        for vmids in (
            [],
            [130, 130],
            [True],
            [0],
            "130",
        ):
            with self.subTest(vmids=vmids):
                with self.assertRaises(ValueError):
                    executor.plan_restore_batch(vmids)

        self.api.assert_not_called()


if __name__ == "__main__":
    unittest.main()
