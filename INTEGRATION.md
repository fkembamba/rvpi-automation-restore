# RVPI snapshot-creation extension — integration guide

Add the two source files to your **main** `rvpi-automation-restore-python` repository, NOT the separate nested Git checkout.

* `rvpi_automation/snapshot_management.py` -> `rvpi_automation/`
* `tests/test_snapshot_management.py` -> `tests/`

This release does not replace any existing file. Existing policy, credentials, and rollback methods remain intact.

## 1. Update root `rvpi_lab.py`

Add import:

```python
from rvpi_automation.snapshot_management import create_snapshot, list_approved_snapshots
```

In `parser.add_argument("command", choices=[...])`, add `"snapshot-list"` and `"snapshot-create"` to existing choices.

Add args alongside the existing `--vmid`, `--execute`, and `--confirm` arguments:

```python
parser.add_argument("--name", help="New checkpoint snapshot name")
parser.add_argument("--description", default="", help="Snapshot description")
```

In the existing `main` command dispatcher, put these two branches **after** the `verify` branch and **before** the `start`/`shutdown` branch:

```python
elif args.command == "snapshot-list":
    result = list_approved_snapshots(args.vmid)
elif args.command == "snapshot-create":
    if not args.name:
        parser.error("snapshot-create requires --name")
    result = create_snapshot(
        args.vmid,
        args.name,
        description=args.description,
        execute=args.execute,
        confirmation=args.confirm,
        max_checks=args.max_checks,
        interval=args.interval,
    )
```

Do not run the `--execute` form until the dedicated scoped token is configured.

## 2. Unit tests and previews (Windows)

```powershell
python -m unittest discover -s tests -q
python rvpi_lab.py snapshot-create --vmid 130 --name checkpoint-001
```

The second command is a local policy-only preview, not a live readiness check.

## 3. Future credential setup (separate approval and controlled change)

Under `restore_token.py` define a new token ID and owner-only credential path, then register a `snapshot130` entry in `CREDENTIAL_PROFILES` (vmid 130, node pve). Under VM 130's policy set `"snapshot_credential_profile": "snapshot130"`.

Proposed Proxmox account/token: `rvpi-snapshot@pve!create130`, token privsep enabled.
Custom role: `VM.Audit` and `VM.Snapshot`, ACL on `/vms/130` only for both parent and privilege-separated token. Be aware **VM.Snapshot grants both creation and deletion**, even though this module implements **no deletion operation**.

The dedicated token must not reuse `rollback130` or `power130` credentials. Keep token files outside Git, with 0600 file permissions. Do not change existing Proxmox ACLs for other VMs.

## 4. Actual create operation (only after approval, VM stopped and token setup)

```bash
python3 rvpi_lab.py snapshot-create --vmid 130 --name checkpoint-001 --execute --confirm CREATE-SNAPSHOT-130-checkpoint-001
```

The API creates a **disk-only** snapshot (`vmstate=0`) with a unique name. The call requires `VM 130` to be stopped. It checks for duplicate snapshot names and waits for confirmed Proxmox task completion before declaring `CREATED_VERIFIED`.

## Important limits

* Existing `baseline-clean` is never overwritten or reassigned.
* The module never performs snapshot deletion.
* No backup or cross-storage replication is provided; Proxmox snapshots are **not backups**.
* The backend may reject creation if underlying storage cannot snapshot the VM disks.
* On an ambiguous task outcome, investigate Proxmox before retrying: a snapshot may already have been created.
* Evidence reporting for snapshot creation can be added after testing the core create/list flow; existing restore evidence is unaffected.
