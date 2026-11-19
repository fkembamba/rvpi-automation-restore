
"""Safety tests for sequential RVPI restoration."""

import io
import json
import tempfile
from pathlib import Path

from rvpi_automation import restore_task_api as task_api
import unittest
from unittest.mock import call, patch

from rvpi_automation import restore_executor as executor


class RestoreBatchExecutionTests(unittest.TestCase):

    def setUp(self):
        self.vmids = [130, 131]
        self.confirmations = {
            130: "ROLLBACK-130-baseline-clean",
            131: "ROLLBACK-131-baseline-clean",
        }

        plan = {
            "total_vms": 2,
            "all_ready": True,
            "results": [
                {
                    "vmid": vmid,
                    "baseline": "baseline-clean",
                    "status": "DRY_RUN_READY",
                    "ready": True,
                }
                for vmid in self.vmids
            ],
            "changes_applied": False,
        }

        self.plan = self.mock_function("plan_restore_batch")
        self.submit = self.mock_function("submit_restore")
        self.monitor = self.mock_function("read_restore_task_status")

        self.plan.return_value = plan

        self.submit.side_effect = (
            lambda vmid, confirmation: {
                "task_id": f"MOCK-TASK-{vmid}"
            }
        )

        self.monitor.return_value = {
            "task_status": "TASK_SUCCEEDED",
            "exitstatus": "OK",
        }

        sleep_patch = patch.object(executor.time, "sleep")
        sleep_patch.start()
        self.addCleanup(sleep_patch.stop)

    def mock_function(self, name):
        patcher = patch.object(executor, name)
        mocked = patcher.start()
        self.addCleanup(patcher.stop)
        return mocked

    def test_default_is_dry_run(self):
        result = executor.execute_restore_batch(self.vmids)

        self.assertEqual(result["status"], "DRY_RUN")
        self.assertFalse(result["execution_performed"])
        self.submit.assert_not_called()

    def test_two_vms_processed_sequentially(self):
        result = executor.execute_restore_batch(
            self.vmids,
            self.confirmations,
            execute=True,
        )

        self.assertEqual(
            result["status"],
            "TASKS_SUCCEEDED_GUESTS_UNVERIFIED",
        )
        self.assertEqual(result["processed"], 2)
        self.assertFalse(result["restoration_verified"])

        self.submit.assert_has_calls([
            call(130, self.confirmations[130]),
            call(131, self.confirmations[131]),
        ])

        self.monitor.assert_has_calls([
            call("MOCK-TASK-130", vmid=130),
            call("MOCK-TASK-131", vmid=131),
        ])

    def test_missing_confirmation_blocks_batch(self):
        with self.assertRaises(PermissionError):
            executor.execute_restore_batch(
                self.vmids,
                {130: self.confirmations[130]},
                execute=True,
            )

        self.submit.assert_not_called()

    def test_failed_preflight_blocks_batch(self):
        self.plan.return_value["all_ready"] = False

        with self.assertRaises(RuntimeError):
            executor.execute_restore_batch(
                self.vmids,
                self.confirmations,
                execute=True,
            )

        self.submit.assert_not_called()

    def test_failed_task_stops_next_vm(self):
        self.monitor.return_value = {
            "task_status": "TASK_FAILED",
            "exitstatus": "simulated failure",
        }

        result = executor.execute_restore_batch(
            self.vmids,
            self.confirmations,
            execute=True,
        )

        self.assertEqual(result["status"], "BATCH_INCOMPLETE")
        self.assertEqual(result["processed"], 1)
        self.assertEqual(self.submit.call_count, 1)

    def test_timeout_stops_next_vm(self):
        self.monitor.return_value = {
            "task_status": "RUNNING",
        }

        result = executor.execute_restore_batch(
            self.vmids,
            self.confirmations,
            execute=True,
            max_checks=2,
            poll_interval=0,
        )

        self.assertEqual(result["status"], "BATCH_INCOMPLETE")
        self.assertEqual(
            result["results"][0]["status"],
            "TIMEOUT_UNVERIFIED",
        )
        self.assertEqual(self.submit.call_count, 1)
        self.assertEqual(self.monitor.call_count, 2)


    def test_submission_error_reports_uncertainty(self):
        self.submit.side_effect = RuntimeError(
            "Simulated ambiguous submission error"
        )

        result = executor.execute_restore_batch(
            self.vmids,
            self.confirmations,
            execute=True,
        )

        self.assertEqual(result["status"], "BATCH_INCOMPLETE")
        self.assertFalse(result["execution_performed"])
        self.assertTrue(result["submission_outcome_uncertain"])
        self.assertEqual(self.submit.call_count, 1)
        self.monitor.assert_not_called()



    def test_completed_batch_guest_verification(self):
        report = {
            "results": [{
                "vmid": 130,
                "task_id": "MOCK-TASK-130",
                "status": "TASK_SUCCEEDED",
            }]
        }

        with patch.object(
            executor, "read_restore_task_status",
            return_value={
                "task_status": "TASK_SUCCEEDED",
                "exitstatus": "OK",
            },
        ), patch.object(
            executor, "verify_restoration",
            return_value={
                "verification_status": "PASS",
                "baseline": "baseline-clean",
                "hostname_sha256_match": True,
                "post_snapshot_marker_absent": True,
                "differences": [],
            },
        ):
            result = executor.verify_completed_restore_batch(report)

        self.assertTrue(result["all_verified"])
        self.assertEqual(result["status"], "VERIFIED")
        self.assertEqual(
            result["results"][0]["status"],
            "RESTORATION_VERIFIED",
        )

    def test_guest_verification_failure(self):
        report = {
            "results": [{
                "vmid": 130,
                "task_id": "MOCK-TASK-130",
                "status": "TASK_SUCCEEDED",
            }]
        }

        with patch.object(
            executor, "read_restore_task_status",
            return_value={
                "task_status": "TASK_SUCCEEDED",
                "exitstatus": "OK",
            },
        ), patch.object(
            executor, "verify_restoration",
            side_effect=TimeoutError("Guest unreachable"),
        ):
            result = executor.verify_completed_restore_batch(report)

        self.assertFalse(result["all_verified"])
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertEqual(
            result["results"][0]["status"],
            "VERIFICATION_UNAVAILABLE",
        )


    def test_restoration_evidence_saved(self):
        import json
        import tempfile
        from pathlib import Path

        report = {
            "status": "VERIFIED",
            "results": [{
                "vmid": 130,
                "status": "RESTORATION_VERIFIED",
            }],
        }

        with tempfile.TemporaryDirectory() as folder:
            filename = executor.save_restore_report(
                report,
                evidence_dir=folder,
            )

            saved = json.loads(
                Path(filename).read_text(encoding="utf-8")
            )

            self.assertEqual(saved["report"], report)
            self.assertIn("recorded_at_utc", saved)
            self.assertTrue(Path(filename).is_file())



class PowerLifecycleTests(unittest.TestCase):


    def test_dry_run_requires_power_profile(self):
        target = {
            "node": "pve",
            "credential_profile": "rollback130",
        }

        with (
            patch.object(
                executor,
                "get_restore_target",
                return_value=target,
            ),
            patch.object(
                executor.urllib.request,
                "urlopen",
            ) as mock_api,
        ):
            result = executor.submit_vm_power(130, "start")

        self.assertEqual(
            result["status"], "BLOCKED_NO_POWER_PROFILE"
        )
        self.assertFalse(result["changes_applied"])
        mock_api.assert_not_called()

    def test_real_action_blocked_without_credential(self):
        target = {
            "node": "pve",
            "credential_profile": "rollback130",
        }

        with (
            patch.object(
                executor,
                "get_restore_target",
                return_value=target,
            ),
            patch.object(
                executor.urllib.request,
                "urlopen",
            ) as mock_api,
        ):
            with self.assertRaises(PermissionError):
                executor.submit_vm_power(
                    130,
                    "start",
                    "POWER-START-130",
                    execute=True,
                )

        mock_api.assert_not_called()


    def test_forced_stop_rejected(self):
        with self.assertRaises(ValueError):
            executor.submit_vm_power(130, "stop")

    def test_wrong_confirmation_rejected(self):
        fake_target = {
            "node": "pve",
            "baseline": "baseline-clean",
            "credential_profile": "rollback130",
            "power_credential_profile": "power130",
        }

        with patch.object(
            executor, "get_restore_target",
            return_value=fake_target,
        ), patch.object(
            executor.urllib.request, "urlopen"
        ) as mock_api:
            with self.assertRaises(PermissionError):
                executor.submit_vm_power(
                    130, "start",
                    "INCORRECT",
                    execute=True,
                )

        mock_api.assert_not_called()



    def test_start_and_shutdown_submission(self):
        import io
        import json
        import tempfile
        from pathlib import Path

        target = {
            "node": "pve",
            "baseline": "baseline-clean",
            "credential_profile": "rollback130",
            "power_credential_profile": "power130",
        }

        with tempfile.TemporaryDirectory() as folder:
            token_file = Path(folder) / "power-token.json"
            token_file.write_text(
                json.dumps({
                    "full-tokenid": "test@pve!power130",
                    "value": "fake-test-secret",
                }),
                encoding="utf-8",
            )

            def credential(profile, vmid, node):
                self.assertEqual(vmid, 130)
                self.assertEqual(node, "pve")
                return {
                    "token_id": (
                        "test@pve!power130"
                        if profile == "power130"
                        else "test@pve!rollback130"
                    ),
                    "token_file": token_file,
                }

            for action, state in (
                ("start", "stopped"),
                ("shutdown", "running"),
            ):
                with self.subTest(action=action):
                    with patch.object(
                        executor, "get_restore_target",
                        return_value=target,
                    ), patch.object(
                        executor, "get_restore_credential",
                        side_effect=credential,
                    ), patch.object(
                        executor, "check_restore_token",
                        return_value={
                            "vmid": 130,
                            "vm_status": state,
                        },
                    ), patch.object(
                        executor.ssl, "create_default_context",
                    ), patch.object(
                        executor.urllib.request, "urlopen",
                        return_value=io.BytesIO(
                            b'{"data":"UPID:pve:mock-power-task"}'
                        ),
                    ) as mock_api:

                        result = executor.submit_vm_power(
                            130,
                            action,
                            f"POWER-{action.upper()}-130",
                            execute=True,
                        )

                        self.assertEqual(
                            result["status"],
                            "SUBMITTED_UNVERIFIED",
                        )
                        self.assertFalse(result["guest_ready"])
                        mock_api.assert_called_once()

                        request = mock_api.call_args.args[0]
                        self.assertEqual(
                            request.get_method(), "POST"
                        )
                        self.assertIn(
                            f"/qemu/130/status/{action}",
                            request.full_url,
                        )

    def test_same_token_cannot_manage_power(self):
        target = {
            "node": "pve",
            "credential_profile": "rollback130",
            "power_credential_profile": "power130",
        }

        with patch.object(
            executor, "get_restore_target",
            return_value=target,
        ), patch.object(
            executor, "get_restore_credential",
            return_value={
                "token_id": "same-token",
            },
        ), patch.object(
            executor.urllib.request, "urlopen",
        ) as mock_api:

            with self.assertRaises(PermissionError):
                executor.submit_vm_power(
                    130,
                    "start",
                    "POWER-START-130",
                    execute=True,
                )

            mock_api.assert_not_called()



    def test_power_dry_run_blocks_missing_credential(self):
        target = {
            "node": "pve",
            "credential_profile": "rollback130",
            "power_credential_profile": "power130",
        }

        def fake_credential(profile, vmid, node):
            return {
                "token_id": f"test@pve!{profile}",
                "token_file": Path("unused-test-token.json"),
            }

        with (
            patch.object(executor, "get_restore_target", return_value=target),
            patch.object(
                executor,
                "get_restore_credential",
                side_effect=fake_credential,
            ),
            patch.object(Path, "is_file", return_value=False),
            patch.object(executor.urllib.request, "urlopen") as mock_api,
        ):
            result = executor.submit_vm_power(130, "shutdown")

        self.assertEqual(
            result["status"], "BLOCKED_POWER_CREDENTIAL_MISSING"
        )
        self.assertFalse(result["changes_applied"])
        mock_api.assert_not_called()


    def test_power_dry_run_rejects_rollback_token_reuse(self):
        target = {
            "node": "pve",
            "credential_profile": "rollback130",
            "power_credential_profile": "power130",
        }

        credential = {
            "token_id": "test@pve!same-token",
            "token_file": Path("unused-test-token.json"),
        }

        with (
            patch.object(executor, "get_restore_target", return_value=target),
            patch.object(
                executor,
                "get_restore_credential",
                return_value=credential,
            ),
            patch.object(executor.urllib.request, "urlopen") as mock_api,
        ):
            result = executor.submit_vm_power(130, "start")

        self.assertEqual(
            result["status"], "BLOCKED_REUSED_ROLLBACK_CREDENTIAL"
        )
        self.assertFalse(result["changes_applied"])
        mock_api.assert_not_called()



class PowerTaskMonitoringTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        self.target = {
            "node": "pve",
            "baseline": "baseline-clean",
            "credential_profile": "rollback130",
            "power_credential_profile": "power130",
        }

        self.files = {}

        for profile in ("rollback130", "power130"):
            path = Path(self.temp.name) / f"{profile}.json"
            path.write_text(
                json.dumps({
                    "full-tokenid": f"test@pve!{profile}",
                    "value": "fake-secret",
                }),
                encoding="utf-8",
            )
            self.files[profile] = path

        def fake_credential(profile, vmid, node):
            self.assertEqual(vmid, 130)
            self.assertEqual(node, "pve")
            return {
                "token_id": f"test@pve!{profile}",
                "token_file": self.files[profile],
            }

        patches = [
            patch.object(
                task_api,
                "get_restore_target",
                return_value=self.target,
            ),
            patch.object(
                task_api,
                "get_restore_credential",
                side_effect=fake_credential,
            ),
            patch.object(
                task_api.ssl,
                "create_default_context",
            ),
            patch.object(
                task_api.urllib.request,
                "urlopen",
            ),
        ]

        self.mocks = [p.start() for p in patches]

        for p in patches:
            self.addCleanup(p.stop)

        self.mock_api = self.mocks[-1]

    def make_upid(self, task_type, profile):
        return (
            f"UPID:pve:00000001:00000002:00000003:"
            f"{task_type}:130:test@pve!{profile}:"
        )

    def mock_response(self, upid, task_type, exitstatus="OK"):
        self.mock_api.return_value = io.BytesIO(
            json.dumps({
                "data": {
                    "upid": upid,
                    "node": "pve",
                    "id": "130",
                    "type": task_type,
                    "status": "stopped",
                    "exitstatus": exitstatus,
                }
            }).encode("utf-8")
        )

    def test_start_and_shutdown_tasks(self):
        for action, task_type in (
            ("start", "qmstart"),
            ("shutdown", "qmshutdown"),
        ):
            with self.subTest(action=action):
                upid = self.make_upid(task_type, "power130")
                self.mock_response(upid, task_type)

                result = task_api.read_vm_power_task_status(
                    upid, 130, action
                )

                self.assertEqual(
                    result["task_status"], "TASK_SUCCEEDED"
                )
                self.assertFalse(result["guest_ready"])

                request = self.mock_api.call_args.args[0]
                self.assertEqual(request.get_method(), "GET")

    def test_failed_power_task(self):
        upid = self.make_upid("qmstart", "power130")
        self.mock_response(
            upid, "qmstart", "simulated startup failure"
        )

        result = task_api.read_vm_power_task_status(
            upid, 130, "start"
        )

        self.assertEqual(
            result["task_status"], "TASK_FAILED"
        )
        self.assertFalse(result["guest_ready"])

    def test_rollback_monitoring_preserved(self):
        upid = self.make_upid("qmrollback", "rollback130")
        self.mock_response(upid, "qmrollback")

        result = task_api.read_restore_task_status(
            upid, vmid=130
        )

        self.assertEqual(
            result["task_status"], "TASK_SUCCEEDED"
        )

    def test_unrelated_task_rejected(self):
        upid = self.make_upid("qmrollback", "power130")

        with self.assertRaises(ValueError):
            task_api.read_vm_power_task_status(
                upid, 130, "start"
            )

        self.mock_api.assert_not_called()

    def test_missing_power_profile_rejected(self):
        self.target.pop("power_credential_profile")

        upid = self.make_upid("qmstart", "power130")

        with self.assertRaises(PermissionError):
            task_api.read_vm_power_task_status(
                upid, 130, "start"
            )

        self.mock_api.assert_not_called()








if __name__ == "__main__":
    unittest.main()
