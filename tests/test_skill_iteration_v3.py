"""V3 规则接线和恢复边界；受控回复不计为模型能力成绩。"""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agent.llm import LLMError, Reply
from agent.main import ROOT as PROJECT_ROOT, main, testbench_tool_error
from agent.verification import CheckResult, Toolchain


PROMPT = "module TopModule(input a, output q); q must equal a. Submit only the DUT."
DUT = "module TopModule(input a, output q); /* IMPLEMENTATION_ONLY_SENTINEL */ assign q=a; endmodule"
TB = ('`timescale 1ns/1ps\nmodule tb; reg a; wire q; TopModule dut(.a(a),.q(q)); '
      'initial begin a=0; #1; if(q!==a) begin $display("RTL_AGENT_FAIL"); $finish; end '
      '$display("RTL_AGENT_PASS"); $finish; end endmodule')
INCOMPLETE = 'module tb; reg a; initial begin $display("RTL_AGENT_FAIL");'
PASS = CheckResult("passed", "fake", "RTL_AGENT_PASS", 0)
TB_ERROR = CheckResult("failed", "fake", "ERROR: [VRFC 10-1280] procedural assignment to a non-register 'a' [/tmp/tb.sv:4]", 0)


class DiagnosticRoutingTests(unittest.TestCase):
    def test_procedural_target_errors_require_testbench_ownership(self):
        errors = (
            "ERROR: [VRFC 10-1280] procedural assignment to a non-register 'a' [/var/tmp/build/tb.sv:14]",
            "tb.sv:4: error: a is not a valid l-value in tb.",
        )
        for error in errors:
            with self.subTest(error=error):
                self.assertTrue(testbench_tool_error(error))
                self.assertFalse(testbench_tool_error(error.replace("tb.sv", "rtl.sv")))
                self.assertFalse(testbench_tool_error(error + "\nRTL_AGENT_FAIL expected=1 actual=0"))

    def test_mixed_source_errors_and_port_mismatches_are_not_syntax_repairs(self):
        self.assertFalse(testbench_tool_error(TB_ERROR.log + "\nrtl.sv:8: syntax error"))
        self.assertFalse(testbench_tool_error("tb.sv:4: error: port q is not a port of dut"))
        self.assertFalse(testbench_tool_error(TB_ERROR.log + "\ntb.sv:7: error: port q is not a port of dut"))

    def test_vivado_declaration_error_with_cascading_diagnostics(self):
        log = ("ERROR: [VRFC 10-2938] 'a' is already implicitly declared on line 7 [/var/tmp/build/tb.sv:13]\n"
               "ERROR: [VRFC 10-8530] module 'tb' is ignored due to previous errors [/var/tmp/build/tb.sv:1]")
        self.assertTrue(testbench_tool_error(log))
        self.assertFalse(testbench_tool_error(log.replace("tb.sv:13", "rtl.sv:13")))
        self.assertFalse(testbench_tool_error(log.splitlines()[1]))


class RecoveryFlowTests(unittest.TestCase):
    def run_flow(self, replies, sims=(), *, deadline=120, elapsed=(), rules=False):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        task, out = root / "task", root / "out"
        task.mkdir()
        (task / "prompt.txt").write_text(PROMPT, encoding="utf-8")
        (task / "tb.sv").write_text("HIDDEN_TESTBENCH_SENTINEL", encoding="utf-8")
        (task / "reference").mkdir()
        (task / "reference" / "solution.v").write_text("REFERENCE_ANSWER_SENTINEL", encoding="utf-8")
        if rules:
            (root / "skill").mkdir()
            (root / "skill" / "rtl_rules.md").write_text("DESIGN_RULE_SENTINEL", encoding="utf-8")
            (root / "skill" / "verification_rules.md").write_text("VERIFY_RULE_SENTINEL", encoding="utf-8")
        clock = [0.0]
        durations = iter(elapsed)
        responses = iter(replies)

        def chat(*args, **kwargs):
            clock[0] += next(durations, 0)
            response = next(responses)
            if isinstance(response, Exception):
                raise response
            return response

        with patch("agent.main.LLM.chat", side_effect=chat) as model, \
                patch("agent.main.Toolchain") as ctor, \
                patch("agent.main.time.monotonic", side_effect=lambda: clock[0]):
            tools = ctor.return_value
            tools.describe.return_value = {"backend": "fake"}
            tools.lint.return_value = PASS
            tools.simulate.side_effect = sims
            with patch("agent.main.ROOT", root if rules else PROJECT_ROOT):
                self.assertEqual(main(["--verification-mode", "legacy", "--input", str(task), "--output", str(out),
                                       "--deadline", str(deadline)]), 0)
            calls = model.call_args_list
            sim_calls = tools.simulate.call_args_list
        summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
        events = [json.loads(line) for line in (out / "trace.jsonl").read_text(encoding="utf-8").splitlines()]
        purposes = [item["purpose"] for item in events if item["tool"] == "llm"]
        return out, summary, calls, sim_calls, purposes

    def assert_isolated(self, calls):
        for call in calls[1:]:
            messages = call.args[0]
            self.assertNotIn("IMPLEMENTATION_ONLY_SENTINEL", str(messages))
            content = json.loads(messages[1]["content"])
            self.assertEqual(content["specification"], PROMPT)
        self.assertNotIn("HIDDEN_TESTBENCH_SENTINEL", str(calls))
        self.assertNotIn("REFERENCE_ANSWER_SENTINEL", str(calls))

    def test_truncated_testbench_gets_one_isolated_complete_rewrite(self):
        out, summary, calls, sims, purposes = self.run_flow(
            [Reply(DUT), Reply(INCOMPLETE, finish="length"), Reply(TB)], [PASS], rules=True)
        self.assertEqual(purposes, ["design", "independent_testbench", "testbench_format_repair"])
        self.assertTrue(summary["selfcheck_passed"])
        self.assertEqual(summary["selected_round"], 1)
        self.assertEqual(len(sims), 1)
        self.assertEqual((out / "solution.v").read_text(), DUT + "\n")
        self.assert_isolated(calls)
        self.assertNotIn(INCOMPLETE, str(calls[2].args[0]))
        for call in calls[1:]:
            self.assertIn("VERIFY_RULE_SENTINEL", call.args[0][0]["content"])
            self.assertNotIn("DESIGN_RULE_SENTINEL", call.args[0][0]["content"])

    def test_failed_format_retry_keeps_compiled_candidate_and_stops(self):
        out, summary, calls, sims, purposes = self.run_flow(
            [Reply(DUT), Reply(INCOMPLETE, finish="length"), Reply(INCOMPLETE, finish="length")])
        self.assertEqual(purposes, ["design", "independent_testbench", "testbench_format_repair"])
        self.assertFalse(summary["selfcheck_passed"])
        self.assertEqual(summary["selected_round"], 1)
        self.assertEqual((out / "solution.v").read_text(), DUT + "\n")
        self.assertEqual(sims, [])

    def test_format_and_syntax_recovery_share_one_attempt(self):
        out, summary, calls, sims, purposes = self.run_flow(
            [Reply(DUT), Reply(INCOMPLETE, finish="length"), Reply(TB)], [TB_ERROR])
        self.assertEqual(purposes, ["design", "independent_testbench", "testbench_format_repair"])
        self.assertEqual(len(sims), 1)
        self.assertFalse(summary["selfcheck_passed"])
        self.assertEqual((out / "solution.v").read_text(), DUT + "\n")
        self.assertFalse((out / "round_02").exists())

    def test_non_register_error_repairs_only_tb_and_uses_verification_rules(self):
        out, summary, calls, sims, purposes = self.run_flow(
            [Reply(DUT), Reply(TB), Reply(TB)], [TB_ERROR, PASS], rules=True)
        self.assertEqual(purposes, ["design", "independent_testbench", "testbench_syntax_repair"])
        self.assertTrue(summary["selfcheck_passed"])
        self.assertEqual(summary["selected_round"], 1)
        self.assertEqual(sims[0].args[0], sims[1].args[0])
        self.assert_isolated(calls)
        self.assertIn("VERIFY_RULE_SENTINEL", calls[2].args[0][0]["content"])
        self.assertEqual((out / "generated_tb_before_syntax_repair.sv").read_text(), TB + "\n")

    def test_failed_syntax_reply_keeps_candidate_without_dut_repair(self):
        out, summary, calls, sims, purposes = self.run_flow(
            [Reply(DUT), Reply(TB), Reply(INCOMPLETE, finish="length")], [TB_ERROR])
        self.assertEqual(purposes, ["design", "independent_testbench", "testbench_syntax_repair"])
        self.assertFalse(summary["selfcheck_passed"])
        self.assertEqual(summary["selected_round"], 1)
        self.assertEqual((out / "solution.v").read_text(), DUT + "\n")
        self.assertEqual(len(sims), 1)

    def test_low_remaining_budget_skips_format_rewrite(self):
        out, summary, calls, sims, purposes = self.run_flow(
            [Reply(DUT), Reply(INCOMPLETE, finish="length")], deadline=35, elapsed=[1, 12])
        self.assertEqual(purposes, ["design", "independent_testbench"])
        self.assertFalse(summary["selfcheck_passed"])
        self.assertEqual((out / "solution.v").read_text(), DUT + "\n")
        self.assertEqual(sims, [])
        self.assertLessEqual(calls[0].kwargs["timeout_s"], 31.5)
        self.assertLessEqual(calls[1].kwargs["timeout_s"], 30.5)
        self.assertGreaterEqual(calls[1].kwargs["timeout_s"], 12)

    def test_rewrite_service_failure_keeps_candidate(self):
        out, summary, _, sims, purposes = self.run_flow(
            [Reply(DUT), Reply(INCOMPLETE, finish="length"), LLMError("worker timeout")])
        self.assertEqual(purposes, ["design", "independent_testbench", "testbench_format_repair"])
        self.assertFalse(summary["selfcheck_passed"])
        self.assertEqual(summary["selected_round"], 1)
        self.assertEqual((out / "solution.v").read_text(), DUT + "\n")
        self.assertEqual(sims, [])


class RealOracleTests(unittest.TestCase):
    def test_declaration_repair_keeps_oracle_sensitive_to_wrong_dut(self):
        tool = Toolchain("iverilog")
        if not tool.describe()["available"]:
            self.skipTest("Icarus unavailable")
        bad_tb = TB.replace("reg a;", "wire a;")
        mutant = DUT.replace("assign q=a;", "assign q=~a;")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            broken = tool.simulate(DUT, bad_tb, "TopModule", root / "broken", 30)
            fixed = tool.simulate(DUT, TB, "TopModule", root / "fixed", 30)
            rejected = tool.simulate(mutant, TB, "TopModule", root / "mutant", 30)
        self.assertEqual(broken.status, "failed", broken.log)
        self.assertEqual(fixed.status, "passed", fixed.log)
        self.assertEqual(rejected.status, "failed", rejected.log)
        self.assertIn("RTL_AGENT_FAIL", rejected.log)


if __name__ == "__main__":
    unittest.main()
