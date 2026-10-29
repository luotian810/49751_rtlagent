"""针对跨题重复失败的流程回归；受控模型回复不计为千问能力实测。"""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests import test_flow_v2 as prior
from tests import test_verification_plan_v5 as plans
from agent.llm import Reply
from agent.main import main
from agent.verification import CheckResult, Toolchain


class ProgressAndRoutingTests(unittest.TestCase):
    run_flow = prior.FlowTests.run_flow

    def setUp(self):
        quiet = patch("builtins.print")
        quiet.start()
        self.addCleanup(quiet.stop)

    def test_duplicate_compile_failure_stops_without_third_call_or_recompile(self):
        failed = CheckResult("failed", "fake", "rtl.sv:1: syntax error", 0,
                             {"stage": "compile", "failure_source": "dut"})
        out, summary, calls, sims = self.run_flow(
            [Reply(prior.DUT), Reply(prior.DUT)], [], lint=[failed])
        self.assertEqual(summary["stop_reason"], "repeated_candidate")
        self.assertEqual(summary["unique_candidates"], 1)
        self.assertEqual(len(calls), 2)
        self.assertEqual(sims, [])
        self.assertFalse((out / "round_02/lint").exists())
        self.assertFalse((out / "round_03").exists())
        self.assertEqual((out / "round_02/solution.v").read_text(), prior.DUT + "\n")

    def test_duplicate_rejected_interface_remains_empty(self):
        wrong = prior.DUT.replace("input a", "input [2:0] a")
        out, summary, calls, sims = self.run_flow([Reply(wrong), Reply(wrong)], [])
        self.assertEqual(summary["stop_reason"], "repeated_candidate")
        self.assertEqual((out / "solution.v").read_text(), "")
        self.assertEqual(summary["selected_round"], 0)
        self.assertEqual(len(calls), 2)
        self.assertEqual(sims, [])

    def test_duplicate_functional_failure_cannot_gain_a_fake_second_pass(self):
        out, summary, calls, sims = self.run_flow(
            [Reply(prior.OTHER), Reply(prior.TB), prior.diagnosis("dut_error"), Reply(prior.OTHER)],
            [prior.FAIL, prior.PASS])
        self.assertEqual(summary["stop_reason"], "repeated_candidate")
        self.assertFalse(summary["selfcheck_passed"])
        self.assertEqual(len(calls), 4)
        self.assertEqual(len(sims), 1)
        self.assertEqual((out / "solution.v").read_text(), prior.OTHER + "\n")

    def test_failed_changed_repair_cannot_reuse_stale_diagnosis(self):
        _, summary, calls, sims = self.run_flow(
            [Reply(prior.OTHER), Reply(prior.TB), prior.diagnosis("dut_error"), Reply(prior.DUT)],
            [prior.FAIL, prior.FAIL])
        self.assertEqual(summary["stop_reason"], "selfcheck_repair_failed")
        self.assertEqual(len(calls), 4)
        self.assertEqual(len(sims), 2)

    def test_unknown_compile_or_elaboration_failure_never_calls_functional_diagnosis(self):
        for stage in ("compile", "elaborate"):
            with self.subTest(stage=stage):
                failed = CheckResult("failed", "fake", "ERROR: unresolved instance", 0,
                                     {"stage": stage, "simulation_executed": False,
                                      "assertion_failed": False, "failure_source": "unknown"})
                _, summary, calls, _ = self.run_flow([Reply(prior.DUT), Reply(prior.TB)], [failed])
                self.assertEqual(summary["stop_reason"], f"simulation_{stage}_failed")
                self.assertEqual(len(calls), 2)

    def test_dut_elaboration_error_uses_compile_feedback_without_diagnosis(self):
        failed = CheckResult("failed", "fake", "ERROR: constant index required [rtl.sv:2]", 0,
                             {"stage": "elaborate", "simulation_executed": False,
                              "assertion_failed": False, "failure_source": "dut"})
        _, summary, calls, _ = self.run_flow(
            [Reply(prior.OTHER), Reply(prior.TB), Reply(prior.DUT)], [failed, prior.PASS])
        self.assertTrue(summary["selfcheck_passed"])
        self.assertEqual(len(calls), 3)
        self.assertIn("DUT 编译/展开诊断", calls[2].args[0][1]["content"])

    def test_vivado_testbench_elaboration_error_repairs_only_testbench(self):
        failed = CheckResult("failed", "fake", 'ERROR: "tb.sv" Line 111. random system task is not supported.', 0,
                             {"stage": "elaborate", "simulation_executed": False,
                              "assertion_failed": False, "failure_source": "testbench"})
        _, summary, calls, sims = self.run_flow(
            [Reply(prior.DUT), Reply(prior.TB), Reply(prior.TB)], [failed, prior.PASS])
        self.assertTrue(summary["selfcheck_passed"])
        self.assertEqual(len(calls), 3)
        self.assertEqual(sims[0].args[0], sims[1].args[0])
        self.assertNotIn(prior.DUT, str(calls[2].args[0]))

    def test_invented_stimulus_stops_without_dut_repair(self):
        invented = json.loads(prior.diagnosis("dut_error").text)
        invented["evidence"]["stimulus"]["a"] = "0"
        _, summary, calls, _ = self.run_flow(
            [Reply(prior.OTHER), Reply(prior.TB), Reply(json.dumps(invented))], [prior.FAIL])
        self.assertEqual(summary["stop_reason"], "selfcheck_uncertain")
        self.assertEqual(len(calls), 3)

    def test_timeout_or_unstructured_runtime_failure_never_triggers_speculation(self):
        for message, assertion, reason in (
            ("RTL_AGENT_FAIL timeout", False, "simulation_simulate_failed"),
            ("RTL_AGENT_FAIL mismatch", True, "selfcheck_missing_observation"),
        ):
            with self.subTest(message=message):
                result = CheckResult("failed", "fake", message, 0,
                                     {"stage": "simulate", "simulation_executed": True,
                                      "assertion_failed": assertion})
                _, summary, calls, _ = self.run_flow([Reply(prior.DUT), Reply(prior.TB)], [result])
                self.assertEqual(summary["stop_reason"], reason)
                self.assertEqual(len(calls), 2)

    def test_compact_plan_real_simulation_and_bound_repair_work_end_to_end(self):
        if not Toolchain("iverilog").describe()["available"]:
            self.skipTest("Icarus unavailable")
        correct = plans.COMBO_DUT
        broken = correct.replace("$signed(a) + $signed(b)", "a[0]")
        calls = []

        def reply(messages, **kwargs):
            calls.append(messages)
            if len(calls) == 1:
                return Reply(broken)
            if len(calls) == 2:
                self.assertNotIn(broken, str(messages))
                return Reply(json.dumps(plans.signed_plan()))
            if len(calls) == 3:
                payload = json.loads(messages[1]["content"])
                self.assertNotIn(broken, str(messages))
                self.assertNotIn("testbench_expected", str(messages))
                # 只在测试替身内从真实输入独立计算，不读取失配任一方的输出。
                operands = [int(payload["history"][-1]["inputs"][name], 16) for name in ("a", "b")]
                total = sum(value - 32 if value >= 16 else value for value in operands)
                return Reply(json.dumps({"status": "derived", "sample": payload["target"]["sample"],
                                         "output": "sum", "expected": f"{total & 63:x}",
                                         "reason": "Add the two signed input values.",
                                         "spec_rule": "Return the signed sum."}))
            self.assertEqual(len(calls), 4)
            return Reply(correct)

        with tempfile.TemporaryDirectory() as directory:
            task, out = Path(directory) / "task", Path(directory) / "out"
            task.mkdir()
            (task / "prompt.txt").write_text(plans.COMBO_SPEC, encoding="utf-8")
            with patch("agent.main.LLM.chat", side_effect=reply):
                self.assertEqual(main(["--input", str(task), "--output", str(out),
                                       "--backend", "iverilog", "--deadline", "60"]), 0)
            summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
            self.assertTrue(summary["selfcheck_passed"], summary)
            self.assertEqual(summary["selected_round"], 2)
            self.assertEqual(summary["checks"]["simulation_stage"], "simulate")
            diagnosis = json.loads((out / "round_01/diagnosis.json").read_text(encoding="utf-8"))
            self.assertTrue(diagnosis["observation_bound"])
            self.assertFalse(diagnosis["semantic_verified"])
            self.assertEqual(len(calls), 4)


if __name__ == "__main__":
    unittest.main()
