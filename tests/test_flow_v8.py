"""V8 编译修复与候选证据的行为回归；受控回复不算千问实测。"""
import json
import unittest
from unittest.mock import patch

from agent.llm import Reply
from agent.repair import COMPILER_REPAIR
from agent.verification import CheckResult
from tests import test_flow_v2 as prior


def elaboration_failure():
    return CheckResult("failed", "fake", "ERROR: Module <helper> not found [rtl.sv:1]", 0,
                       {"stage": "elaborate", "compile_passed": True,
                        "elaboration_passed": False, "simulation_executed": False,
                        "failure_source": "dut"})


class V8FlowTests(unittest.TestCase):
    run_flow = prior.FlowTests.run_flow

    def setUp(self):
        quiet = patch("builtins.print")
        quiet.start()
        self.addCleanup(quiet.stop)

    def test_elaboration_repair_precedes_testbench_and_survives_invalid_testbench(self):
        out, summary, calls, sims = self.run_flow(
            [Reply(prior.OTHER), Reply(prior.DUT), Reply("no testbench"), Reply("still invalid")],
            [], lint=[elaboration_failure(), prior.PASS])
        self.assertEqual(len(calls), 4)
        self.assertTrue(calls[1].args[0][0]["content"].startswith(COMPILER_REPAIR))
        self.assertIn("Module <helper> not found", calls[1].args[0][1]["content"])
        self.assertEqual(summary["selected_round"], 2)
        self.assertEqual(summary["evidence_level"], "elaborated")
        self.assertEqual(summary["checks"]["elaboration"], "passed")
        self.assertFalse(summary["selfcheck_passed"])
        self.assertEqual(sims, [])
        self.assertEqual((out / "solution.v").read_text(), prior.DUT + "\n")
        record = json.loads((out / "round_01/compiler_diagnostic.json").read_text(encoding="utf-8"))
        self.assertEqual(record["stage"], "elaborate")

    def test_preflight_environment_failure_does_not_spend_model_repair(self):
        for status in ("unavailable", "error", "timeout"):
            with self.subTest(status=status):
                result = CheckResult(status, "fake", "tool unavailable", 0,
                                     {"stage": "elaborate", "compile_passed": True})
                out, summary, calls, sims = self.run_flow([Reply(prior.DUT)], [], lint=[result])
                self.assertEqual(summary["stop_reason"], "lint_" + status)
                self.assertEqual(summary["evidence_level"], "compiled")
                self.assertEqual(len(calls), 1)
                self.assertEqual(sims, [])
                self.assertFalse((out / "round_01/compiler_diagnostic.json").exists())

    def test_recurring_diagnostic_is_persisted_and_reaches_next_repair(self):
        failed = CheckResult("failed", "fake",
                             "ERROR: [VRFC 10-2951] 'select_word' is not a constant [rtl.sv:1]", 0,
                             {"stage": "compile", "compile_passed": False})
        out, summary, calls, _ = self.run_flow(
            [Reply(prior.DUT), Reply(prior.OTHER), Reply(prior.DUT + " // different")],
            [], lint=[failed, failed, failed])
        diagnostic = json.loads((out / "round_02/compiler_diagnostic.json").read_text(encoding="utf-8"))
        self.assertTrue(diagnostic["repeated"])
        self.assertEqual(diagnostic["source_lines"], [1])
        self.assertIn("根诊断重复", calls[2].args[0][1]["content"])
        self.assertEqual(summary["evidence_level"], "interface")

    def test_executed_assertion_is_stronger_than_testbench_elaboration_failure(self):
        out, summary, calls, _ = self.run_flow(
            [Reply(prior.OTHER), Reply(prior.TB), Reply(prior.DUT), prior.diagnosis("uncertain")],
            [elaboration_failure(), prior.FAIL])
        self.assertEqual(len(calls), 4)
        self.assertEqual(summary["selected_round"], 2)
        self.assertEqual(summary["evidence_level"], "executed")
        self.assertFalse(summary["selfcheck_passed"])
        self.assertEqual((out / "solution.v").read_text(), prior.DUT + "\n")

    def test_started_but_timed_out_simulation_does_not_upgrade_candidate(self):
        timeout = CheckResult("timeout", "fake", "deadline", 0,
                              {"stage": "simulate", "simulation_executed": True,
                               "assertion_failed": False})
        _, summary, calls, _ = self.run_flow(
            [Reply(prior.OTHER), Reply(prior.TB), Reply(prior.DUT)],
            [elaboration_failure(), timeout])
        self.assertEqual(len(calls), 3)
        self.assertEqual(summary["selected_round"], 1)
        self.assertEqual(summary["evidence_level"], "elaborated")
        self.assertEqual(summary["stop_reason"], "simulation_timeout")

    def test_valid_repair_is_selected_only_after_stronger_evidence(self):
        _, summary, _, _ = self.run_flow(
            [Reply(prior.OTHER), Reply(prior.TB), prior.diagnosis("dut_error"), Reply(prior.DUT)],
            [prior.FAIL, prior.PASS])
        self.assertEqual(summary["selected_round"], 2)
        self.assertEqual(summary["evidence_level"], "selfcheck_passed")
        self.assertTrue(summary["selfcheck_passed"])


if __name__ == "__main__":
    unittest.main()
