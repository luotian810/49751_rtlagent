"""V2 机制回归；模型为受控替身，不把这些用例计为模型能力成绩。"""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from agent.budget import model_budget
from agent.llm import LLM, LLMError, Reply
from agent.main import main
from agent.verification import CheckResult

DUT = "module TopModule(input a, output q); assign q=a; endmodule"
OTHER = "module TopModule(input a, output q); assign q=~a; endmodule"
TB = 'module tb; initial $display("RTL_AGENT_PASS"); // RTL_AGENT_FAIL\nendmodule'
PASS = CheckResult("passed", "fake", "ok", 0)
FAIL = CheckResult("failed", "fake", "RTL_AGENT_FAIL sample=1 a=1 q=0 expected=1", 0,
                   {"stage": "simulate", "simulation_executed": True, "assertion_failed": True})


def diagnosis(verdict):
    return Reply(json.dumps({
        "verdict": verdict, "reason": "The single failing stimulus was checked against the specification.",
        "spec_rule": "q equals a",
        "evidence": {"sample": 1, "stimulus": {"a": "1"}, "expected": "q=1",
                     "observed": "q=1" if verdict == "testbench_error" else "q=0",
                     "testbench_expected": "q=0" if verdict == "testbench_error" else "q=1"},
    }))


class BudgetTests(unittest.TestCase):
    def test_auxiliary_calls_leave_time_for_simulation_and_repair(self):
        for left in (0, 0.5, 8, 120, 900):
            with self.subTest(left=left):
                tb = model_budget("independent_testbench", left)
                diag = model_budget("failure_diagnosis", left)
                self.assertLessEqual(tb.timeout_s, left * 0.45)
                self.assertLessEqual(diag.timeout_s, left * 0.20)
                self.assertLessEqual(tb.max_tokens, 3072)
                self.assertLessEqual(diag.max_tokens, 768)

    def test_token_cap_sent_to_worker_without_changing_global_default(self):
        llm = LLM()
        llm.max_tokens = 16384
        returned = subprocess.CompletedProcess([], 0, '{"text":"ok"}', "")
        with patch("agent.llm.subprocess.run", return_value=returned) as run:
            llm.chat([], 10, max_tokens=768)
            self.assertEqual(json.loads(run.call_args.kwargs["input"])["max_tokens"], 768)
            llm.chat([], 10, max_tokens=20000)
            self.assertEqual(json.loads(run.call_args.kwargs["input"])["max_tokens"], 16384)
            llm.chat([], 10)
            self.assertEqual(json.loads(run.call_args.kwargs["input"])["max_tokens"], 16384)
            for invalid in (True, -1, 0, 2.5):
                with self.assertRaises(LLMError):
                    llm.chat([], 10, max_tokens=invalid)


class FlowTests(unittest.TestCase):
    def run_flow(self, replies, sims, *, lint=None, synth=None, rounds=3):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        task, out = root / "task", root / "out"
        task.mkdir()
        (task / "prompt.txt").write_text("module TopModule(input a, output q); q equals a.", encoding="utf-8")
        with patch("agent.main.LLM.chat", side_effect=replies) as chat, patch("agent.main.Toolchain") as ctor:
            tools = ctor.return_value
            tools.describe.return_value = {"backend": "fake"}
            tools.lint.side_effect = lint or [PASS] * rounds
            tools.simulate.side_effect = sims
            tools.synth.side_effect = synth
            argv = ["--verification-mode", "legacy", "--input", str(task), "--output", str(out), "--max-rounds", str(rounds)]
            if synth is not None:
                argv.append("--synth")
            self.assertEqual(main(argv), 0)
            calls = chat.call_args_list
            sim_calls = tools.simulate.call_args_list
        return out, json.loads((out / "summary.json").read_text(encoding="utf-8")), calls, sim_calls

    def test_wrong_or_uncertain_testbench_stops_without_rewriting_either_side(self):
        for verdict in ("testbench_error", "uncertain"):
            with self.subTest(verdict=verdict):
                failure = (CheckResult("failed", "fake", "RTL_AGENT_FAIL sample=1 a=1 q=1 expected=0", 0,
                                       dict(FAIL.details)) if verdict == "testbench_error" else FAIL)
                out, summary, calls, _ = self.run_flow([Reply(DUT), Reply(TB), diagnosis(verdict)], [failure])
                self.assertEqual(summary["stop_reason"], "selfcheck_" + verdict)
                self.assertFalse(summary["selfcheck_passed"])
                self.assertEqual(len(calls), 3)
                self.assertEqual((out / "solution.v").read_text(), DUT + "\n")
                self.assertEqual((out / "generated_tb.sv").read_text(), TB + "\n")
                self.assertFalse((out / "round_02").exists())

    def test_failed_candidate_can_be_replaced_by_verified_repair(self):
        out, summary, calls, sims = self.run_flow(
            [Reply(OTHER), Reply(TB), diagnosis("dut_error"), Reply(DUT)], [FAIL, PASS])
        self.assertTrue(summary["selfcheck_passed"])
        self.assertEqual(summary["selected_round"], 2)
        self.assertEqual((out / "solution.v").read_text(), DUT + "\n")
        self.assertEqual(sims[0].args[1], sims[1].args[1])
        self.assertLess(calls[1].kwargs["max_tokens"], calls[0].kwargs["max_tokens"])
        self.assertLess(calls[2].kwargs["timeout_s"], calls[0].kwargs["timeout_s"])

    def test_long_testbench_does_not_hide_failure_or_diagnosis_from_repair(self):
        long_tb = TB.replace("endmodule", "// " + "padding" * 900 + "\nendmodule")
        _, _, calls, _ = self.run_flow(
            [Reply(OTHER), Reply(long_tb), diagnosis("dut_error"), Reply(DUT)], [FAIL, PASS])
        repair_input = calls[3].args[0][1]["content"]
        self.assertIn('"sample": 1', repair_input)
        self.assertIn('"observed": "q=0"', repair_input)
        self.assertIn('"testbench_expected": "q=1"', repair_input)
        self.assertIn("single failing stimulus was checked", repair_input)
        self.assertIn("题面依据：q equals a", repair_input)
        self.assertNotIn(long_tb, repair_input)
        self.assertNotIn("padding", repair_input)

    def test_synthesis_failure_then_weaker_repair_does_not_lose_simulated_candidate(self):
        out, summary, _, _ = self.run_flow(
            [Reply(DUT), Reply(TB), Reply(OTHER)], [PASS], lint=[PASS, FAIL],
            synth=[FAIL], rounds=2)
        self.assertEqual((out / "solution.v").read_text(), DUT + "\n")
        self.assertEqual(summary["selected_round"], 1)
        self.assertEqual(summary["checks"]["synthesis"], "failed")

    def test_equal_rank_failed_repair_keeps_first_candidate(self):
        out, summary, _, _ = self.run_flow(
            [Reply(DUT), Reply(TB), diagnosis("dut_error"), Reply(OTHER)], [FAIL, FAIL], rounds=2)
        self.assertEqual((out / "solution.v").read_text(), DUT + "\n")
        self.assertEqual(summary["selected_round"], 1)

    def test_truncated_repair_preserves_existing_solution_and_requests_complete_rewrite(self):
        out, summary, calls, _ = self.run_flow(
            [Reply(DUT), Reply(TB), Reply("module TopModule(input a", finish="length"),
             LLMError("deadline")], [PASS], synth=[FAIL])
        self.assertEqual((out / "solution.v").read_text(), DUT + "\n")
        self.assertEqual(summary["selected_round"], 1)
        self.assertIn("从头输出完整模块", calls[3].args[0][1]["content"])


if __name__ == "__main__":
    unittest.main()
