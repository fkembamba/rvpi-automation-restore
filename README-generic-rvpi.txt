Generic RVPI automation CLI (draft for project integration)
========================================================
Copy rvpi_lab.py to the root of the rvpi-automation-restore-python repo.
Copy test_rvpi_lab.py to tests/test_rvpi_lab.py.

On Windows, from the repository root:
    python -m unittest discover -s tests -q
    python rvpi_lab.py list-targets
    python rvpi_lab.py restore-test --vmid 130

The restore-test command is DRY RUN by default; it does not modify a VM.
A real restoration requires --execute and the exact confirmation string:
    python3 rvpi_lab.py restore-test --vmid 130 --execute --confirm RESTORE-130-baseline-clean

DO NOT execute a real restore until the entire suite passes on VM113 and
preflight, task monitoring, evidence file creation, and dry-run outputs are
reviewed. A baseline rollback is destructive to post-snapshot VM state.

Other commands (by default power operations are dry-run):
    python3 rvpi_lab.py status --vmid 130
    python3 rvpi_lab.py verify --vmid 130
    python3 rvpi_lab.py start --vmid 130
    python3 rvpi_lab.py shutdown --vmid 130

Power commands need --execute and the exact confirmation:
    --confirm POWER-START-130 or --confirm POWER-SHUTDOWN-130

Safety:
 - Uses approved VM policies and existing, per-VM credentials.
 - No blanket Proxmox permissions are added.
 - Full restore is explicitly confirmed and defaults to read-only preview.
 - Validates token identities, snapshot existence, and SSH verifier inputs
   before shutting down; task success and VM states are monitored.
 - Stops automatically when an action fails, and saves a JSON report.
 - The existing restore_verification adapter currently supports linux-ssh.
   Other guest OS methods require an adapter before real restore execution.
 - Unit tests in this bundle cover orchestration via mocks, not live Proxmox.

This CLI is not yet deployed to VM113 or integrated with its complete suite.
