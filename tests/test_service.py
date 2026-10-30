"""HTTP 契约和超时行为测试：使用本机模拟服务，不访问真实模型或密钥。"""

from contextlib import contextmanager
import http.client
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

from serve import serve_api as api


@contextmanager
def local_server():
    server = api.ServiceServer(("127.0.0.1", 0), api.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {
            "FPGACHINA_TOKEN": "test-token", "MODEL_NAME": "test-model",
            "LLM_API_KEY": "test-api-key", "RTL_SIMULATOR": "iverilog",
            **{key: os.environ[key] for key in ("SystemRoot", "TEMP", "TMP", "PATH")
               if key in os.environ},
        }, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def request(self, port, method, path, data=None, authorized=True, headers=None):
        request_headers = {"Content-Type": "application/json"}
        if authorized:
            request_headers["Authorization"] = "Bearer test-token"
        request_headers.update(headers or {})
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            connection.request(method, path, body=json.dumps(data) if data is not None else None,
                               headers=request_headers)
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def payload(self, **values):
        return api.validate_request({"task_id": "中文-task", "prompt": "实现计数器", **values})

    def model_response(self, models):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({"data": models}).encode()
        return response

    def child_paths(self, command, mode="agent"):
        """Assert the native entry point while exposing its task/output paths."""
        if os.name != "nt":
            script = "run_baseline.sh" if mode == "baseline" else "run.sh"
            self.assertEqual(command[:2], ["bash", str(api.ROOT / script)])
            self.assertEqual(len(command), 4)
            return Path(command[2]), Path(command[3])
        if mode == "baseline":
            self.assertEqual(command[:2], [api.sys.executable, str(api.ROOT / "baseline.py")])
            self.assertEqual(len(command), 5)
            self.assertEqual(command[-1], "rtl")
            return Path(command[2]), Path(command[3])
        self.assertEqual(command[:4], [api.sys.executable, "-m", "agent.main", "--input"])
        return (Path(command[command.index("--input") + 1]),
                Path(command[command.index("--output") + 1]))

    def fake_child(self, return_code=0):
        process = MagicMock()
        # Never allow MagicMock's integer coercion to turn a fake PID into 1.
        process.pid = "mock-child-without-os-pid"
        process.wait.return_value = return_code
        return process

    @contextmanager
    def mock_child_launch(self, **options):
        # Mock both cleanup paths whenever no real subprocess has been started.
        # The integration test below deliberately keeps real process cleanup.
        with patch.object(api.subprocess, "Popen", **options) as launch, \
                patch.object(api, "_stop_process_tree") as stop, \
                patch.object(api, "_cleanup_group") as cleanup:
            yield launch, stop, cleanup

    def test_health_and_solve_require_bearer_token(self):
        with local_server() as port, patch.object(api, "health") as health, patch.object(api, "solve") as solve:
            for method, path in (("GET", "/v1/health"), ("POST", "/v1/solve"),
                                 ("GET", "/v1/jobs/unknown")):
                status, _ = self.request(port, method, path, authorized=False)
                self.assertEqual(status, 401)
            health.assert_not_called()
            solve.assert_not_called()

    def test_missing_token_is_not_public_access(self):
        os.environ.pop("FPGACHINA_TOKEN")
        with local_server() as port:
            status, _ = self.request(port, "GET", "/v1/health")
        self.assertEqual(status, 503)

    def test_success_response_matches_contract(self):
        expected = {"task_id": "中文-task", "solution": "module TopModule; endmodule\n",
                    "trace": '{"tool":"llm"}\n', "elapsed_s": 0.01}
        with local_server() as port, patch.object(api, "solve", return_value=expected) as solve:
            status, accepted = self.request(port, "POST", "/v1/solve", self.payload())
            self.assertEqual(status, 202)
            self.assertEqual(accepted["status"], "queued")
            self.assertNotIn("solution", accepted)
            result = self.poll_done(port, accepted["job_id"])
        self.assertEqual(result, {**expected, "job_id": accepted["job_id"], "status": "done"})
        self.assertEqual(solve.call_args.args[0]["interface"], "")

    def poll_done(self, port, job_id, timeout=3):
        until = time.monotonic() + timeout
        while time.monotonic() < until:
            status, result = self.request(port, "GET", "/v1/jobs/" + job_id)
            self.assertEqual(status, 200)
            if result["status"] == "done":
                return result
            self.assertNotIn("solution", result)
            time.sleep(0.01)
        self.fail("job did not finish")

    def test_invalid_mode_and_deadline_are_rejected_before_launch(self):
        with local_server() as port, patch.object(api, "solve") as solve:
            for fields in ({"mode": "typo"}, {"deadline_s": True}, {"deadline_s": 0},
                           {"deadline_s": 3601}, {"prompt": []}):
                status, _ = self.request(port, "POST", "/v1/solve", {
                    "task_id": "task", "prompt": "counter", **fields,
                })
                self.assertEqual(status, 400)
            solve.assert_not_called()

    def test_body_bound_and_content_type(self):
        with local_server() as port:
            status, _ = self.request(port, "POST", "/v1/solve", {},
                                     headers={"Content-Length": str(api.MAX_BODY_BYTES + 1)})
            self.assertEqual(status, 413)
            status, _ = self.request(port, "POST", "/v1/solve", {},
                                     headers={"Content-Type": "text/plain"})
            self.assertEqual(status, 415)

    def test_slow_job_returns_immediately_and_duplicate_nonce_runs_once(self):
        entered, release = threading.Event(), threading.Event()

        def slow(request, submitted=None, cancel_event=None):
            entered.set()
            release.wait(timeout=3)
            return {"solution": "", "trace": "", "elapsed_s": 0.1}

        with local_server() as port, patch.object(api, "solve", side_effect=slow) as solve:
            try:
                status, job = self.request(port, "POST", "/v1/solve", self.payload(nonce="once"))
                self.assertEqual(status, 202)
                self.assertTrue(entered.wait(timeout=1))
                status, duplicate = self.request(port, "POST", "/v1/solve", self.payload(nonce="once"))
                self.assertEqual(status, 202)
                self.assertEqual(duplicate["job_id"], job["job_id"])
                status, pending = self.request(port, "GET", "/v1/jobs/" + job["job_id"])
                self.assertEqual(pending["status"], "running")
                self.assertNotIn("solution", pending)
            finally:
                release.set()
            self.poll_done(port, job["job_id"])
            _, duplicate = self.request(port, "POST", "/v1/solve", self.payload(nonce="once"))
            self.assertEqual(duplicate["status"], "done")
            self.assertEqual(duplicate["job_id"], job["job_id"])
            self.assertEqual(solve.call_count, 1)

    def test_unknown_job_returns_404(self):
        with local_server() as port:
            status, _ = self.request(port, "GET", "/v1/jobs/missing")
        self.assertEqual(status, 404)

    def test_queue_time_consumes_deadline_without_launching_expired_job(self):
        with self.mock_child_launch() as (launch, _stop, _cleanup):
            result = api.solve(self.payload(deadline_s=1), submitted=time.monotonic() - 2)
        launch.assert_not_called()
        self.assertEqual(result["solution"], "")
        self.assertIn("queue_deadline_expired", result["trace"])

    def test_worker_exception_does_not_block_next_job(self):
        with local_server() as port, patch.object(api, "solve", side_effect=[
                RuntimeError("secret"), {"solution": "ok", "trace": "", "elapsed_s": 0.1}]):
            _, first = self.request(port, "POST", "/v1/solve", self.payload(nonce="first"))
            _, second = self.request(port, "POST", "/v1/solve", self.payload(nonce="second"))
            failed = self.poll_done(port, first["job_id"])
            passed = self.poll_done(port, second["job_id"])
        self.assertIn("service_worker_failed", failed["trace"])
        self.assertNotIn("secret", failed["trace"])
        self.assertEqual(passed["solution"], "ok")

    def test_default_deadline_is_current_900_seconds(self):
        self.assertEqual(self.payload()["deadline_s"], 900)

    def test_close_cancels_current_job_without_starting_queued_job(self):
        entered = threading.Event()

        def blocking(request, submitted=None, cancel_event=None):
            entered.set()
            self.assertTrue(cancel_event.wait(timeout=2))
            return {"solution": "", "trace": "", "elapsed_s": 0.01}

        with patch.object(api, "solve", side_effect=blocking) as solve:
            jobs = api.JobQueue()
            try:
                jobs.submit(self.payload(nonce="active"))
                self.assertTrue(entered.wait(timeout=1))
                jobs.submit(self.payload(nonce="waiting"))
                jobs.close()
                self.assertFalse(jobs.worker.is_alive())
                self.assertEqual(solve.call_count, 1)
            finally:
                jobs.close()

    def test_cancelled_child_keeps_candidate_and_service_removes_eda_files(self):
        cancel = threading.Event()
        process = self.fake_child()
        roots = []

        def launch(command, **options):
            _source, output = self.child_paths(command)
            (output / "solution.v").write_text("module TopModule; endmodule")
            eda = Path(options["env"]["EDA_TMP"])
            roots.append(eda)
            (eda / "unfinished-database").mkdir()
            (eda / "unfinished-database" / "data").write_text("partial")
            cancel.set()
            return process

        with self.mock_child_launch(side_effect=launch) as (_launch, stop, cleanup):
            result = api.solve(self.payload(), cancel_event=cancel)
        stop.assert_called_once_with(process, grace_s=5)
        cleanup.assert_called_once_with(process.pid)
        self.assertIn("endmodule", result["solution"])
        self.assertIn("service_cancelled", result["trace"])
        self.assertFalse(roots[0].exists())

    def test_300_consecutive_jobs_keep_results_and_nonce_identity(self):
        result = {"solution": "module TopModule; endmodule", "trace": "", "elapsed_s": 0.01}
        with local_server() as port, patch.object(api, "solve", return_value=result) as solve:
            first = None
            for index in range(300):
                status, job = self.request(port, "POST", "/v1/solve",
                                           self.payload(nonce=f"sample-{index}"))
                self.assertEqual(status, 202)
                done = self.poll_done(port, job["job_id"])
                self.assertEqual(done["solution"], result["solution"])
                if first is None:
                    first = job["job_id"]
            _, retried = self.request(port, "POST", "/v1/solve", self.payload(nonce="sample-0"))
            self.assertEqual(retried["job_id"], first)
            self.assertEqual(retried["status"], "done")
            self.assertEqual(solve.call_count, 300)

    def test_real_agent_and_baseline_roundtrip_with_local_fake_model(self):
        """真实 HTTP、子进程和 Icarus；模型是假响应，仅验证工程链路。"""
        from agent.verification import Toolchain
        if not Toolchain("iverilog").describe()["available"]:
            self.skipTest("Icarus is needed for the local pipeline test")
        dut = "module TopModule(input a, output q); assign q = a; endmodule"
        plan = json.dumps({"ports": [{"name": "a", "direction": "input", "width": 1},
                                     {"name": "q", "direction": "output", "width": 1}],
                           "clock": None, "async_reset": None,
                           "variables": [{"name": "stim_i"}], "advance": "",
                           "expected": {"q": "a"},
                           "stimulus": "for(stim_i=0;stim_i<64;stim_i=stim_i+1) step(stim_i%2);"})
        answers = iter((dut, dut, plan, dut))
        payloads = []

        class FakeModel(api.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                payloads.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                body = json.dumps({"choices": [{"message": {"content": next(answers)},
                                                "finish_reason": "stop"}]}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        model = api.ThreadingHTTPServer(("127.0.0.1", 0), FakeModel)
        thread = threading.Thread(target=model.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
                    "LLM_BASE_URL": f"http://127.0.0.1:{model.server_port}/v1",
                    "LLM_MODEL": "Qwen3-14B-Q4_K_M", "MODEL_NAME": "Qwen3-14B-Q4_K_M", "AGENT_TMP": directory,
                    "EDA_TMP": str(Path(directory) / "eda"), "NO_PROXY": "127.0.0.1,localhost",
            }), local_server() as port:
                _, job = self.request(port, "POST", "/v1/solve", self.payload(
                    prompt="Implement module named TopModule. Output q equals input a.",
                    interface="module TopModule(input a, output q);", deadline_s=30, nonce="real-agent"))
                result = self.poll_done(port, job["job_id"], timeout=30)
                self.assertEqual(result["solution"].strip(), dut, result["trace"])
                events = [json.loads(line) for line in result["trace"].splitlines()]
                self.assertTrue(any(event.get("tool") == "simulate" and event.get("status") == "passed"
                                    for event in events), result["trace"])
                _, job = self.request(port, "POST", "/v1/solve", self.payload(
                    prompt="Implement module named TopModule. Output q equals input a.",
                    mode="baseline", deadline_s=30, nonce="real-baseline"))
                result = self.poll_done(port, job["job_id"], timeout=30)
                self.assertEqual(result["solution"].strip(), dut, result["trace"])
                events = [json.loads(line) for line in result["trace"].splitlines()]
                self.assertEqual([event["tool"] for event in events], ["baseline_meta", "llm"])
                self.assertEqual(len(payloads), 4)
                self.assertEqual(payloads[0]["chat_template_kwargs"], payloads[3]["chat_template_kwargs"])
                self.assertFalse(list(Path(directory).glob("rtl-request-*")))
                self.assertFalse(list((Path(directory) / "eda").iterdir()))
        finally:
            model.shutdown()
            model.server_close()
            thread.join(timeout=2)

    def test_health_checks_model_auth_and_reports_unknown_vram(self):
        with patch.object(api.urllib.request, "urlopen", return_value=self.model_response([
            {"id": "test-model"}])) as open_url, patch.object(api.Path, "is_file", return_value=True), \
                patch.object(api, "_simulator_available", return_value=True), \
                patch.object(api, "_vram_gb", return_value=None):
            result = api.health()
        self.assertTrue(result["ready"])
        self.assertEqual(result["track"], "rtl")
        self.assertIsNone(result["vram_gb"])
        request = open_url.call_args.args[0]
        self.assertEqual(request.full_url, api.DEFAULT_BASE_URL + "/models")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-api-key")
        self.assertNotIn("test-api-key", json.dumps(result))

    def test_health_not_ready_for_missing_model_or_unreachable_endpoint(self):
        with patch.object(api.urllib.request, "urlopen", return_value=self.model_response([
            {"id": "different-model"}])):
            self.assertEqual(api.health()["status"], "model_not_available")
        with patch.object(api.urllib.request, "urlopen", side_effect=OSError("secret error")):
            result = api.health()
        self.assertFalse(result["ready"])
        self.assertEqual(result["status"], "model_unreachable")
        self.assertNotIn("secret error", json.dumps(result))

    def test_health_not_ready_without_simulator(self):
        with patch.object(api.urllib.request, "urlopen", return_value=self.model_response([
            {"id": "test-model"}])), patch.object(api.Path, "is_file", return_value=True), \
                patch.object(api, "_simulator_available", return_value=False):
            result = api.health()
        self.assertFalse(result["ready"])
        self.assertEqual(result["status"], "simulator_unavailable")

    def test_vram_reads_assigned_card_each_time_and_ignores_host_cards(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dev, sysfs = root / "dev", root / "sys"
            dev.mkdir()
            (dev / "renderD134").touch()
            card = sysfs / "renderD134" / "device"
            card.mkdir(parents=True)
            (card / "vendor").write_text("0x1002\n")
            (card / "mem_info_vram_total").write_text("48000000000")
            used = card / "mem_info_vram_used"
            # A host card visible in sysfs alone must not be included.
            other = sysfs / "renderD128" / "device"
            other.mkdir(parents=True)
            (other / "mem_info_vram_used").write_text("47000000000")
            os.environ["VRAM_GB"] = "99"  # Old startup snapshot must be ignored.
            used.write_text("14500000000")
            self.assertEqual(api._vram_gb(dev, sysfs), 14.5)
            used.write_text("15000000000")
            self.assertEqual(api._vram_gb(dev, sysfs), 15.0)
            for invalid in ("-1", "48000000001", "nan", "unavailable"):
                used.write_text(invalid)
                self.assertIsNone(api._vram_gb(dev, sysfs))
            used.write_text("15000000000")
            (dev / "renderD128").touch()
            self.assertIsNone(api._vram_gb(dev, sysfs))

    def test_vram_unknown_without_assigned_device_does_not_use_environment(self):
        os.environ["VRAM_GB"] = "21.4"
        with tempfile.TemporaryDirectory() as directory:
            self.assertIsNone(api._vram_gb(Path(directory), Path(directory)))

    def test_agent_launch_preserves_output_on_failure_and_redacts_trace(self):
        commands = []

        def launch(command, **options):
            commands.append((command, options))
            source, output = self.child_paths(command)
            self.assertEqual((source / "prompt.txt").read_text(encoding="utf-8"), "实现计数器")
            self.assertFalse((source / "interface.txt").exists())
            (output / "solution.v").write_text("module TopModule; endmodule\n", encoding="utf-8")
            (output / "trace.jsonl").write_text('{"error":"test-api-key"}\n', encoding="utf-8")
            return self.fake_child(return_code=1)

        with self.mock_child_launch(side_effect=launch) as (_launch, stop, cleanup):
            result = api.solve(self.payload())
        stop.assert_not_called()
        cleanup.assert_called_once_with("mock-child-without-os-pid")
        self.assertIn("endmodule", result["solution"])
        self.assertIn("service_child_exit", result["trace"])
        self.assertNotIn("test-api-key", result["trace"])
        command, options = commands[0]
        self.assertEqual(options["env"]["LLM_BASE_URL"], api.DEFAULT_BASE_URL)
        self.assertEqual(options["env"]["PYTHONUTF8"], "1")
        if os.name != "nt":
            self.assertEqual(options["env"]["PYTHON_EXE"], api.sys.executable)
            self.assertTrue(options["start_new_session"])

    def test_timeout_cleans_process_tree_and_returns_prior_candidate(self):
        process = self.fake_child()
        process.wait.side_effect = subprocess.TimeoutExpired("agent", 1)

        def launch(command, **options):
            _source, output = self.child_paths(command)
            (output / "solution.v").write_text("module TopModule; endmodule", encoding="utf-8")
            return process

        with self.mock_child_launch(side_effect=launch) as (_launch, stop, cleanup):
            result = api.solve(self.payload(deadline_s=1))
        stop.assert_called_once_with(process, grace_s=0.25)
        cleanup.assert_called_once_with(process.pid)
        self.assertIn("endmodule", result["solution"])
        self.assertIn("service_timeout", result["trace"])
        self.assertLess(process.wait.call_args.kwargs["timeout"], 1)

    def test_child_deadline_fits_outer_wait_including_short_and_queued_requests(self):
        for deadline, queued_s in ((900, 0), (120, 30), (1, 0), (1, 0.45)):
            with self.subTest(deadline=deadline, queued_s=queued_s):
                process = self.fake_child()
                with self.mock_child_launch(return_value=process) as (launch, stop, cleanup), \
                        patch.object(api.time, "monotonic", return_value=100.0):
                    api.solve(self.payload(deadline_s=deadline), submitted=100.0 - queued_s)
                command = launch.call_args.args[0]
                child_budget = float(launch.call_args.kwargs["env"]["AGENT_DEADLINE_S"])
                wait_budget = process.wait.call_args.kwargs["timeout"]
                reserve = min(10.0, max(0.5, deadline * 0.1))
                self.assertAlmostEqual(wait_budget, deadline - reserve - queued_s)
                self.assertGreater(child_budget, 0)
                self.assertLess(child_budget, wait_budget)
                if deadline == 1:
                    self.assertLess(child_budget, 1)
                if os.name == "nt":
                    self.assertEqual(float(command[command.index("--deadline") + 1]), child_budget)
                self.child_paths(command)
                stop.assert_not_called()
                cleanup.assert_called_once_with(process.pid)

    def test_request_with_only_cleanup_budget_left_does_not_launch(self):
        with self.mock_child_launch() as (launch, stop, cleanup), \
                patch.object(api.time, "monotonic", return_value=100.0):
            result = api.solve(self.payload(deadline_s=1), submitted=99.4)
        launch.assert_not_called()
        stop.assert_not_called()
        cleanup.assert_not_called()
        self.assertIn("queue_deadline_expired", result["trace"])

    def test_baseline_is_launched_directly_with_same_model_configuration(self):
        os.environ.pop("MODEL_NAME")
        os.environ["LLM_MODEL"] = "shared-model"
        process = self.fake_child()
        with self.mock_child_launch(return_value=process) as (launch, stop, cleanup):
            result = api.solve(self.payload(mode="baseline"))
        command = launch.call_args.args[0]
        self.child_paths(command, mode="baseline")
        stop.assert_not_called()
        cleanup.assert_called_once_with(process.pid)
        self.assertEqual(launch.call_args.kwargs["env"]["MODEL_NAME"], "shared-model")
        self.assertEqual(result["solution"], "")

    def test_launch_failure_returns_normal_empty_solution(self):
        with self.mock_child_launch(side_effect=OSError("private secret")) as (_launch, stop, cleanup):
            result = api.solve(self.payload())
        stop.assert_not_called()
        cleanup.assert_not_called()
        self.assertEqual(result["solution"], "")
        self.assertIn("service_launch_failed", result["trace"])
        self.assertNotIn("private secret", result["trace"])


if __name__ == "__main__":
    unittest.main()
