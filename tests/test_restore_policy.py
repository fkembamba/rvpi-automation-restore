
"""Unit tests for RVPI restoration target authorization policy."""

import unittest

from rvpi_automation.restore_policy import (
    get_restore_target,
    list_restore_targets,
)


class RestorePolicyTests(unittest.TestCase):

    def test_approved_vm_130(self):
        target = get_restore_target(130)

        self.assertEqual(target["vmid"], 130)
        self.assertEqual(target["node"], "pve")
        self.assertEqual(target["baseline"], "baseline-clean")
        self.assertEqual(target["purpose"], "restoration-test")

    def test_unapproved_vm_100_rejected(self):
        with self.assertRaises(PermissionError):
            get_restore_target(100)

    def test_infrastructure_vm_rejected(self):
        with self.assertRaises(PermissionError):
            get_restore_target(113)

    def test_invalid_vmids_rejected(self):
        for vmid in (-1, 0, True, "130", None):
            with self.subTest(vmid=vmid):
                with self.assertRaises(ValueError):
                    get_restore_target(vmid)

    def test_approved_target_list(self):
        targets = list_restore_targets()

        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0]["vmid"], 130)

    def test_returned_configuration_is_independent(self):
        target = get_restore_target(130)
        target["baseline"] = "modified-baseline"

        original = get_restore_target(130)

        self.assertEqual(
            original["baseline"],
            "baseline-clean"
        )


if __name__ == "__main__":
    unittest.main()
