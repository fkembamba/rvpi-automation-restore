"""Offline tests for simulated inventory; no Proxmox server is contacted."""
import json
from pathlib import Path
import subprocess
import sys
import unittest

from rvpi_automation.inventory import normalize_vm_inventory


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = PROJECT_ROOT / "tests" / "fixtures" / "proxmox_vms_demo.json"


class InventoryTests(unittest.TestCase):
    def test_demo_normalizes_and_sorts_vms(self):
        with FIXTURE.open(encoding="utf-8") as file:
            vms = normalize_vm_inventory(json.load(file))
        self.assertEqual([vm["vmid"] for vm in vms], [9001, 9002])
        self.assertEqual(vms[0]["status"], "running")
        self.assertEqual(vms[1]["status"], "stopped")

    def test_missing_data_rejected(self):
        with self.assertRaisesRegex(ValueError, "'data' list"):
            normalize_vm_inventory({})

    def test_duplicate_vmid_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate VM ID"):
            normalize_vm_inventory({"data": [{"vmid": 9001}, {"vmid": 9001}]})

    def test_demo_command_is_explicitly_simulated(self):
        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "main.py"), "demo-inventory"],
            capture_output=True, text=True, check=True,
        )
        payload = json.loads(result.stdout)
        self.assertIn("SIMULATED", payload["source"])
        self.assertEqual([vm["vmid"] for vm in payload["vms"]], [9001, 9002])


if __name__ == "__main__":
    unittest.main()
