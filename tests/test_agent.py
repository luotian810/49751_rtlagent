"""只测试易误判的边界：接口继承、独立验证、修复与预算失败。"""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agent.interface import check_interface, extract_verilog, infer_top
from agent.llm import LLMError, Reply
from agent.main import main, testbench_tool_error
from agent.verification import CheckResult


class InterfaceTests(unittest.TestCase):
    def test_width_continuation_and_auxiliary_module(self):
        iface = "module TopModule(input [7:0] a, b, output [7:0] q);"
        code = "module Helper(); endmodule\n" + iface + " assign q = a ^ b; endmodule"
        self.assertTrue(check_interface(code, "", iface, "TopModule")[0])
        bad = code.replace("a, b,", "a, input b,")
        self.assertFalse(check_interface(bad, "", iface, "TopModule")[0])

    def test_prompt_top_and_advisory(self):
        prompt = "module named Counter with ports\n - input q\n"
        self.assertEqual(infer_top(prompt), "Counter")
        ok, note = check_interface("module Counter(output q); endmodule", prompt, "", "Counter")
        self.assertTrue(ok)
        self.assertIn("提示", note)

    def test_extract_and_incomplete(self):
        self.assertEqual(extract_verilog("module TopModule(input a);", "TopModule"), "")
        self.assertIn("`timescale", extract_verilog("```verilog\n`timescale 1ns/1ps\nmodule TopModule(); endmodule\n```", "TopModule"))

    def test_testbench_diagnostics_do_not_relax_assertions(self):
        self.assertTrue(testbench_tool_error("ERROR: tb.sv:130: $random's seed must be an integer/time variable or a register."))
        self.assertTrue(testbench_tool_error("tb.sv:4: syntax error"))
        self.assertFalse(testbench_tool_error("rtl.sv:4: syntax error"))
        self.assertFalse(testbench_tool_error("RTL_AGENT_FAIL expected=7 actual=6\ntb.sv:4: syntax error"))
        self.assertFalse(testbench_tool_error("tb.sv:4: port q is not a port of dut"))


class FlowTests(unittest.TestCase):
    def test_testbench_syntax_repair_does_not_regenerate_dut(self):
        dut = "module TopModule(input a, output q); assign q = a; endmodule"
        tb = 'module tb; initial begin $display("RTL_AGENT_PASS"); end // RTL_AGENT_FAIL\nendmodule'
        passed = CheckResult(status="passed", backend="fake", log="ok", elapsed_s=0)
        failed = CheckResult(status="failed", backend="fake", log="ERROR: tb.sv:130: $random's seed must be an integer/time variable", elapsed_s=0)
        with tempfile.TemporaryDirectory() as temp:
            task, out = Path(temp) / "task", Path(temp) / "out"
            task.mkdir()
            (task / "prompt.txt").write_text("module named TopModule\n - input a\n - output q\nq equals a", encoding="utf-8")
            with patch("agent.main.LLM.chat", side_effect=[Reply(dut), Reply(tb), Reply(tb)]) as chat, patch("agent.main.Toolchain") as ctor:
                tools = ctor.return_value
                tools.describe.return_value = {"backend": "fake"}
                tools.lint.return_value = passed
                tools.simulate.side_effect = [failed, passed]
                main(["--verification-mode", "legacy", "--input", str(task), "--output", str(out)])
                self.assertNotIn(dut, str(chat.call_args_list[2].args[0]))
            summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
            self.assertTrue(summary["selfcheck_passed"])
            self.assertEqual(summary["selected_round"], 1)
            events = [json.loads(line) for line in (out / "trace.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual([e.get("purpose") for e in events if e["tool"] == "llm"], ["design", "independent_testbench", "testbench_syntax_repair"])

    def test_fixed_independent_tb_and_repair(self):
        dut = "module TopModule(input a, output q); assign q = a; endmodule"
        tb = 'module tb; initial begin $display("RTL_AGENT_PASS"); end // RTL_AGENT_FAIL\nendmodule'
        diagnosis = json.dumps({
            "verdict": "dut_error", "reason": "Mismatch is attributable to the DUT.",
            "spec_rule": "q equals a",
            "evidence": {"sample": 1, "stimulus": {"a": "1"}, "expected": "q=1", "observed": "q=0", "testbench_expected": "q=1"},
        })
        replies = [Reply(dut.replace("q = a", "q = ~a")), Reply(tb), Reply(diagnosis), Reply(dut)]
        passed = CheckResult(status="passed", backend="fake", log="ok", elapsed_s=0)
        failed = CheckResult(status="failed", backend="fake", log="RTL_AGENT_FAIL sample=1 a=1 q=0 expected=1", elapsed_s=0,
                             details={"stage": "simulate", "simulation_executed": True, "assertion_failed": True})
        with tempfile.TemporaryDirectory() as temp:
            task, out = Path(temp) / "task", Path(temp) / "out"
            task.mkdir()
            (task / "prompt.txt").write_text("module named TopModule\n - input a\n - output q\nq equals a", encoding="utf-8")
            # 生成器不得读取同目录的隐藏参考文件。
            (task / "tb.sv").write_text("SECRET_REFERENCE_SENTINEL")
            with patch("agent.main.LLM.chat", side_effect=replies) as chat, patch("agent.main.Toolchain") as ctor:
                tools = ctor.return_value
                tools.describe.return_value = {"backend": "fake"}
                tools.lint.return_value = passed
                tools.simulate.side_effect = [failed, passed]
                self.assertEqual(main(["--verification-mode", "legacy", "--input", str(task), "--output", str(out)]), 0)
                summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
                self.assertTrue(summary["selfcheck_passed"])
                self.assertEqual(summary["selected_round"], 2)
                tb_messages = chat.call_args_list[1].args[0]
                self.assertNotIn(dut, str(tb_messages))
                self.assertNotIn("SECRET_REFERENCE_SENTINEL", str(chat.call_args_list))
                self.assertEqual(tools.simulate.call_args_list[0].args[1], tools.simulate.call_args_list[1].args[1])

    def test_network_failure_emits_empty_solution(self):
        with tempfile.TemporaryDirectory() as temp:
            task, out = Path(temp) / "task", Path(temp) / "out"
            task.mkdir()
            (task / "prompt.txt").write_text("Implement module named TopModule", encoding="utf-8")
            with patch("agent.main.LLM.chat", side_effect=LLMError("HTTP 401")):
                main(["--verification-mode", "legacy", "--input", str(task), "--output", str(out), "--backend", "none"])
            self.assertEqual((out / "solution.v").read_text(), "")
            summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
            self.assertFalse(summary["selfcheck_passed"])
            self.assertEqual(summary["official_evaluation"], "not_run")


if __name__ == "__main__":
    unittest.main()
