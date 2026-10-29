"""新规回归：思考配置一致、避免提取草稿、耗尽预算不丢已有答案。"""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

import baseline
from agent.interface import extract_verilog
from agent.llm import LLM, LLMError, Reply, load_generation
from agent.main import main
from agent.verification import CheckResult


ROOT = Path(__file__).resolve().parents[1]
DUT = "module TopModule(input a, output q); assign q = a; endmodule"
DRAFT = "module TopModule(input a, output q); assign q = ~a; endmodule"
TB = ('module tb; initial begin $display("RTL_AGENT_PASS"); end '
      '// RTL_AGENT_FAIL\nendmodule')


class ThinkingTests(unittest.TestCase):
    def test_thinking_draft_is_never_selected(self):
        for prefix in ("<think>", ""):
            with self.subTest(prefix=prefix):
                reply = prefix + "```verilog\n" + DRAFT + "\n```\n</think>" + DUT
                self.assertEqual(extract_verilog(reply, "TopModule"), DUT + "\n")

    def test_truncated_thinking_has_no_solution(self):
        self.assertEqual(extract_verilog("<think>\n" + DRAFT, "TopModule"), "")

    def test_generation_allowlist_matches_official_baseline(self):
        generation = {
            "chat_template_kwargs": {"enable_thinking": False, "budget": 20,
                                     "style": "brief", "bad": [], "null": None},
            "reasoning_effort": "low", "max_tokens": 1, "temperature": 9,
        }
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / "manifest.json"
            manifest.write_text(json.dumps({"generation": generation}), encoding="utf-8")
            with patch("agent.llm.MANIFEST", manifest), patch.object(
                    baseline, "__file__", str(Path(directory) / "baseline.py")):
                actual = load_generation()
                self.assertEqual(actual, baseline.load_generation())
                self.assertEqual(set(actual), {"chat_template_kwargs", "reasoning_effort"})
                self.assertNotIn("bad", actual["chat_template_kwargs"])

    def test_clients_send_same_declared_configuration(self):
        """真实本地 HTTP + 两个独立子进程；不连接外部模型或读取密钥。"""
        payloads = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def respond(self, body):
                data = json.dumps(body).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                self.respond({"data": [{"id": "Qwen3-14B-Q4_K_M"}]})

            def do_POST(self):
                payloads.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                self.respond({"choices": [{"message": {"content": "<think>" + DRAFT +
                              "</think>" + DUT}, "finish_reason": "stop"}],
                              "usage": {"prompt_tokens": 10, "completion_tokens": 20}})

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
                    "LLM_BASE_URL": f"http://127.0.0.1:{server.server_port}/v1",
                    "MODEL_NAME": "Qwen3-14B-Q4_K_M", "DEEPSEEK_THINKING": "enabled",
                    "PYTHONIOENCODING": "utf-8", "NO_PROXY": "127.0.0.1,localhost",
                    **{key: os.environ[key] for key in ("SystemRoot", "TEMP", "TMP")
                       if key in os.environ}}, clear=True):
                task, out = Path(directory) / "task", Path(directory) / "baseline"
                task.mkdir()
                (task / "prompt.txt").write_text("Output q equals a.", encoding="utf-8")
                reply = LLM().chat([{"role": "user", "content": "Output q equals a."}], 20)
                result = subprocess.run([sys.executable, str(ROOT / "baseline.py"),
                                         str(task), str(out), "rtl"], capture_output=True,
                                        text=True, encoding="utf-8", timeout=20)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual((out / "solution.v").read_text(), DUT + "\n")
                self.assertEqual(extract_verilog(reply.text, "TopModule"), DUT + "\n")
                self.assertEqual(len(payloads), 2)
                for payload in payloads:
                    self.assertEqual(payload["model"], "Qwen3-14B-Q4_K_M")
                    self.assertEqual(payload["max_tokens"], 16384)
                    self.assertNotIn("thinking", payload)
                    for key, value in load_generation().items():
                        self.assertEqual(payload[key], value)
                trace = [json.loads(line) for line in (out / "trace.jsonl").read_text().splitlines()]
                self.assertEqual([event["tool"] for event in trace], ["baseline_meta", "llm"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


class CandidateBudgetTests(unittest.TestCase):
    def test_testbench_or_repair_timeout_keeps_existing_candidate(self):
        passed = CheckResult(status="passed", backend="fake", log="ok", elapsed_s=0)
        failed = CheckResult(status="failed", backend="fake", log="RTL_AGENT_FAIL sample=1 a=1 q=0 expected=1", elapsed_s=0,
                             details={"stage": "simulate", "simulation_executed": True, "assertion_failed": True})
        diagnosis = Reply(json.dumps({
            "verdict": "dut_error", "reason": "The failing stimulus contradicts q=a.",
            "spec_rule": "q equals a",
            "evidence": {"sample": 1, "stimulus": {"a": "1"}, "expected": "q=1", "observed": "q=0", "testbench_expected": "q=1"},
        }))
        for purpose, replies in (
                ("independent_testbench", [Reply(DUT), LLMError("call deadline")]),
                ("failure_diagnosis", [Reply(DUT), Reply(TB), LLMError("call deadline")]),
                ("repair", [Reply(DUT), Reply(TB), diagnosis, LLMError("call deadline")])):
            with self.subTest(purpose=purpose), tempfile.TemporaryDirectory() as directory:
                task, out = Path(directory) / "task", Path(directory) / "out"
                task.mkdir()
                (task / "prompt.txt").write_text("Output q equals a.", encoding="utf-8")
                with patch("agent.main.LLM") as model, patch("agent.main.Toolchain") as tools:
                    model.return_value.model = "fake"
                    model.return_value.describe.return_value = {"model": "fake"}
                    model.return_value.chat.side_effect = replies
                    tools.return_value.describe.return_value = {"backend": "fake"}
                    tools.return_value.lint.return_value = passed
                    tools.return_value.simulate.return_value = failed
                    self.assertEqual(main(["--verification-mode", "legacy", "--input", str(task), "--output", str(out)]), 0)
                self.assertEqual((out / "solution.v").read_text(), DUT + "\n")
                summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
                self.assertEqual(summary["selected_round"], 1)
                self.assertFalse(summary["selfcheck_passed"])
                self.assertIn("deadline", summary["stop_reason"])
                events = [json.loads(line) for line in (out / "trace.jsonl").read_text(
                    encoding="utf-8").splitlines()]
                self.assertTrue(any(event["tool"] == "llm" and event.get("purpose") == purpose
                                    and event["rc"] == 1 for event in events))


if __name__ == "__main__":
    unittest.main()
