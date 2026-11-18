
"""Interpret Proxmox task results for RVPI restoration."""

def interpret_task_status(task):
    """Classify a Proxmox task without changing VM state."""

    if not isinstance(task, dict):
        raise ValueError("Invalid Proxmox task response")

    status = task.get("status")
    exitstatus = task.get("exitstatus")

    if status == "running":
        result = "RUNNING"

    elif status == "stopped":
        if exitstatus == "OK":
            result = "TASK_SUCCEEDED"
        elif isinstance(exitstatus, str) and exitstatus:
            result = "TASK_FAILED"
        else:
            result = "TASK_UNKNOWN"

    else:
        raise ValueError("Unknown Proxmox task status")

    return {
        "task_status": result,
        "exitstatus": exitstatus,
        "task_succeeded": result == "TASK_SUCCEEDED",
        "restoration_verified": False,
    }
