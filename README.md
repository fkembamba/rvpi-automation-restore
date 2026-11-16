# RVPI Automation / Restore Host — Python v0.2

Target host: **10.10.10.13**. Development: **Python 3.10+**, **Visual Studio / VS Code**, and a private GitHub repository.

This incremental version implements `health`, `demo-inventory`, and (later, when configured) `list-vms`. **All commands are read-only.** The `demo-inventory` command reads a local JSON fixture and **never contacts Proxmox**.

## Step 1: Run locally in your IDE terminal

Open the `rvpi-automation-restore-python` project directory, then run:

```bash
python3 -m unittest discover -s tests -v
python3 main.py health
python3 main.py demo-inventory
```

The simulated inventory intentionally contains fictitious VMs 9001 and 9002 on `pve-demo`; they are **not** your actual cyber-range VMs. The command labels its output `SIMULATED — NOT LIVE PROXMOX DATA` to prevent confusion.

## Step 2: Proxmox inventory (deferred)

The live Proxmox management address is not known yet. Keep `.env.example` as placeholders. When ready, provision **read-only, least-privilege** Proxmox API credentials outside the repository, and a trusted Proxmox CA certificate (TLS verification stays enabled). Then use:

```bash
python3 main.py list-vms
```

Do not commit actual tokens, passwords, or private keys. See `.gitignore`.

## Deployment plan

1. Develop and test in Visual Studio / VS Code; commit reviewed code to a private GitHub repository.
2. Inspect Python and connectivity on VM 10.10.10.13.
3. Download the reviewed GitHub revision to that host.
4. Run the same offline tests and `health` there.
5. Add read-only snapshot and network-profile verification in later, separately tested steps.
6. Implement state-changing operations **only after** approval checks, allowlists, audit records, and rollback safeguards are proven.

No snapshot creation/restoration, firewall changes, attack operations, or service API endpoints are implemented in v0.2.

## Verified deployment facts (November 2026)

- Automation / Restore host: **10.10.10.13**, interface `ens18`.
- Host Python: **3.12.3**; host Git: **2.43.0**.
- Host DNS resolver: **10.10.10.1** (pfSense); `github.com` resolved and an HTTPS check returned HTTP 200 after adding 10.10.10.13 to the existing `RVPI_UPDATE_HOSTS` alias.
- Real Proxmox **management IP/hostname, API token ID/secret, and trusted CA path have not been provided**. No live API test has been run.

## Upload the reviewed project to GitHub

Create a **private** repository (suggested name: `rvpi-automation-restore-python`). Upload the files within this project folder to its repository root. Do not upload `.env`, credentials, private keys, or live certificates. If publishing from the IDE, verify `.gitignore` is applied before committing. This package contains no actual token secrets.

After publishing, clone from GitHub onto 10.10.10.13 using a separately authorized GitHub authentication mechanism (do not put access tokens in the clone URL). Before any Proxmox access, run:

```bash
python3 -m unittest discover -s tests -v
python3 main.py health
python3 main.py demo-inventory
```

These three commands are local and do not modify VMs, snapshots, or firewall rules.
