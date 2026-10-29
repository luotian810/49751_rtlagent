"""V7 机制控制；受控回复和手写测试电路不计作千问能力证据。"""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agent.diagnosis import failure_observation
from agent.llm import Reply
from agent.main import main
from agent.verification import CheckResult
from agent.verification_plan import PlanError, build_testbench
from agent.witness import prepare_witness, parse_witness
from tests import test_verification_plan_v4 as fixtures
from tests.test_verification_plan_v4 import COMBO_DUT, COMBO_SPEC
from tests.test_verification_plan_v5 import signed_plan
from tests.test_skill_v6 import register_case


def seq_log():
    return ("RTL_AGENT_SAMPLE sample=1 after_edge=1 clear_line=1 accept_word=0 incoming=0 stored=0\n"
            "RTL_AGENT_SAMPLE sample=2 after_edge=1 clear_line=0 accept_word=1 incoming=3 stored=3\n"
            "RTL_AGENT_SAMPLE sample=3 after_edge=1 clear_line=0 accept_word=0 incoming=5 stored=5\n"
            "RTL_AGENT_FAIL sample=3 clear_line=0 accept_word=0 incoming=5 stored=5 expected=3\n")


COMBO_LOG = ("RTL_AGENT_SAMPLE sample=1 after_edge=0 a=01 b=02 sum=00\n"
             "RTL_AGENT_FAIL sample=1 a=01 b=02 sum=00 expected=03\n")


def witness_reply(expected="03", sample=1, output="sum"):
    return json.dumps({"status": "derived", "sample": sample, "output": output,
                       "expected": expected, "reason": "按规格重放输入。", "spec_rule": "输出是规定运算结果。"})


class AutoStimulusTests(unittest.TestCase):
    setUp = fixtures.PlanExecutionTests.setUp
    simulate = fixtures.PlanExecutionTests.simulate

    def test_auto_is_explicit_and_replays_without_model_generated_vectors(self):
        plan = signed_plan()
        plan["stimulus"] = {"mode": "auto", "directed": [{"values": {"a": 7}, "repeat": 2}]}
        before = copy.deepcopy(plan)
        tb, normalized = build_testbench(json.dumps(plan), "SignedAdder", COMBO_SPEC)
        self.assertEqual(plan, before)
        self.assertEqual(normalized["stimulus"]["directed"][-1]["values"], {"a": 7, "b": "0"})
        self.assertEqual(tb, build_testbench(json.dumps(normalized), "SignedAdder", COMBO_SPEC)[0])
        result = self.simulate(plan, COMBO_DUT, "SignedAdder", COMBO_SPEC, "auto-sum")
        self.assertEqual(result.status, "passed", result.log)
        self.assertIn("CHECKS=73", result.log)

    def test_wide_renamed_ports_receive_full_width_randomness_and_reject_wrong_design(self):
        for width in (1, 9, 35):
            spec = f"module Renamed(input [{width-1}:0] clock_like, output [{width-1}:0] delivered);"
            dut = spec + " assign delivered=clock_like; endmodule"
            plan = {"clock": None, "temporaries": [], "states": [],
                    "expected": {"delivered": "clock_like"}, "stimulus": {"mode": "auto"}}
            with self.subTest(width=width):
                good = self.simulate(plan, dut, "Renamed", spec, f"width-{width}")
                self.assertEqual(good.status, "passed", good.log)
                mutant = dut.replace("delivered=clock_like", "delivered=0")
                bad = self.simulate(plan, mutant, "Renamed", spec, f"mutant-{width}")
                self.assertEqual(bad.status, "failed", bad.log)
                if width > 32:
                    _, saved = build_testbench(json.dumps(plan), "Renamed", spec)
                    self.assertEqual(saved["stimulus"]["random"]["values"]["clock_like"].count("$random"), 2)
                    values = [int(line.split("clock_like=")[1].split()[0], 16) >> 32
                              for line in good.log.splitlines() if line.startswith("RTL_AGENT_SAMPLE")][7:]
                    self.assertGreater(len(set(values)), 2)

    def test_auto_respects_edges_reset_polarity_and_pause_and_rejects_enable_mutant(self):
        for edge in ("posedge", "negedge"):
            for active in (0, 1):
                for asynchronous in (False, True):
                    plan, dut, top, spec = register_case(7, edge, active, asynchronous)
                    plan["stimulus"] = {"mode": "auto", "directed": [
                        {"values": {"accept_word": 1, "incoming": 6}},
                        {"values": {"accept_word": 0, "incoming": 2}, "repeat": 3}]}
                    tag = f"{edge}-{active}-{asynchronous}"
                    with self.subTest(tag=tag):
                        good = self.simulate(plan, dut, top, spec, tag)
                        self.assertEqual(good.status, "passed", good.log)
                        bad = self.simulate(plan, dut.replace("else if (accept_word)", "else"), top, spec, tag+"-bad")
                        self.assertEqual(bad.status, "failed", bad.log)

    def test_auto_unknown_clock_or_output_override_and_escape_are_rejected(self):
        plan, _, top, spec = register_case(3, "posedge", 1, False)
        for values in ({"event_line": 0}, {"stored": 0}, {"unknown": 0}, {"incoming": "$finish"}):
            plan["stimulus"] = {"mode": "auto", "directed": [{"values": values}]}
            with self.subTest(values=values), self.assertRaises(PlanError):
                build_testbench(json.dumps(plan), top, spec)
        for settings in ({"cycles": True}, {"cycles": 63}, {"random": {}}, {"directed": [{}]*18}):
            plan["stimulus"] = {"mode": "auto", **settings}
            with self.subTest(settings=settings), self.assertRaises(PlanError):
                build_testbench(json.dumps(plan), top, spec)

    def test_explicit_vectors_are_not_silently_completed(self):
        plan = signed_plan()
        plan["stimulus"]["random"]["values"] = {"a": 0}
        with self.assertRaises(PlanError):
            build_testbench(json.dumps(plan), "SignedAdder", COMBO_SPEC)


class WitnessTests(unittest.TestCase):
    def setUp(self):
        plan, _, top, spec = register_case(3, "posedge", 1, False)
        _, self.plan = build_testbench(json.dumps(plan), top, spec)

    def test_payload_has_only_inputs_controls_and_target_no_oracle_or_outputs(self):
        self.plan["expected"] = {"stored": "SECRET_ORACLE"}
        self.plan["states"] = [{"name": "SECRET_STATE"}]
        context, reason = prepare_witness(self.plan, seq_log())
        self.assertEqual(reason, "")
        self.assertEqual(len(context["history"]), 3)
        self.assertEqual(context["history"][-1]["inputs"], {"clear_line": "0", "accept_word": "0", "incoming": "5"})
        self.assertNotIn("SECRET", json.dumps(context))
        self.assertTrue(all(set(row) == {"sample", "after_edge", "inputs"} for row in context["history"]))
        self.assertNotIn("stored", context["history"][-1]["inputs"])

    def test_missing_history_unknown_inputs_no_reset_and_wrong_fail_binding_skip(self):
        bad_logs = [seq_log().split("\n", 1)[1],
                    seq_log().replace("RTL_AGENT_SAMPLE sample=2", "IGNORED sample=2"),
                    seq_log().replace("incoming=3", "incoming=x"),
                    seq_log().replace("stored=5 expected", "stored=4 expected"),
                    seq_log().replace("after_edge=1 clear_line=0", "after_edge=0 clear_line=0"),
                    seq_log().replace("clear_line=1", "clear_line=0"),
                    seq_log().replace("incoming=5 stored=5\n", "incoming=5 incoming=5 stored=5\n")]
        for log in bad_logs:
            with self.subTest(log=log):
                self.assertIsNone(prepare_witness(self.plan, log)[0])
        self.plan["reset"] = None
        self.assertIsNone(prepare_witness(self.plan, seq_log())[0])

    def test_combinational_context_needs_only_current_input(self):
        _, plan = build_testbench(json.dumps(signed_plan()), "SignedAdder", COMBO_SPEC)
        log = COMBO_LOG.replace("sample=1", "sample=200")
        context, reason = prepare_witness(plan, log)
        self.assertEqual(reason, "")
        self.assertEqual(len(context["history"]), 1)
        self.assertEqual(context["target"]["sample"], 200)

    def test_async_before_edge_failure_and_newest_reset_are_valid_initial_points(self):
        self.plan["async_reset"] = dict(self.plan["reset"])
        log = ("RTL_AGENT_SAMPLE sample=7 after_edge=0 clear_line=1 accept_word=0 incoming=0 stored=5\n"
               "RTL_AGENT_FAIL sample=7 clear_line=1 accept_word=0 incoming=0 stored=5 expected=0")
        context, reason = prepare_witness(self.plan, log)
        self.assertEqual(reason, "")
        self.assertEqual(context["history"][0]["after_edge"], 0)
        context, _ = prepare_witness(self.plan, seq_log().replace("sample=", "sample=1"))
        self.assertEqual([r["sample"] for r in context["history"]], [11, 12, 13])

    def test_history_bound_never_discards_reset_to_fit(self):
        first = seq_log().splitlines()[0]
        rows = [first] + [f"RTL_AGENT_SAMPLE sample={i} after_edge=1 clear_line=0 accept_word=0 incoming=0 stored=0" for i in range(2, 66)]
        log = "\n".join(rows) + "\nRTL_AGENT_FAIL sample=65 clear_line=0 accept_word=0 incoming=0 stored=0 expected=3"
        self.assertIn("64", prepare_witness(self.plan, log)[1])

    def test_program_derives_verdict_without_trusting_model_label(self):
        observed = failure_observation(COMBO_LOG)
        for expected, verdict in (("03", "dut_error"), ("00", "testbench_error"), ("02", "uncertain")):
            reply = json.loads(witness_reply(expected))
            reply["verdict"] = "dut_error"
            result = parse_witness(json.dumps(reply), observed)
            self.assertEqual(result["verdict"], verdict)
            if verdict != "uncertain":
                self.assertFalse(result["semantic_verified"])
                self.assertEqual(result["method"], "blind_input_replay")

    def test_bad_reply_sample_name_value_or_missing_rule_remains_uncertain(self):
        observed = failure_observation(COMBO_LOG)
        for change in ({"sample": 2}, {"sample": True}, {"output": "invented"},
                       {"expected": "x"}, {"expected": "0x03"}, {"spec_rule": ""}, {"status": "other"}):
            reply = json.loads(witness_reply())
            reply.update(change)
            self.assertEqual(parse_witness(json.dumps(reply), observed)["verdict"], "uncertain")
        for text in ("[]", "{}", "no", "```json\n{", None):
            self.assertEqual(parse_witness(text, observed)["verdict"], "uncertain")


class V7FlowTests(unittest.TestCase):
    def run_flow(self, replies, simulations):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        task, out = root/"task", root/"out"
        task.mkdir()
        (task/"prompt.txt").write_text(COMBO_SPEC, encoding="utf-8")
        (task/"ref.sv").write_text("HIDDEN_ANSWER", encoding="utf-8")
        passed = CheckResult("passed", "fake", "", 0)
        with patch("agent.main.LLM.chat", side_effect=replies) as model, patch("agent.main.Toolchain") as constructor, patch("builtins.print"):
            tools = constructor.return_value
            tools.describe.return_value = {"backend": "fake"}
            tools.lint.return_value = passed
            tools.simulate.side_effect = simulations
            self.assertEqual(main(["--input", str(task), "--output", str(out), "--deadline", "120"]), 0)
        return out, json.loads((out/"summary.json").read_text(encoding="utf-8")), model.call_args_list

    def test_blind_review_never_receives_dut_or_oracle_and_gates_single_repair(self):
        failed = CheckResult("failed", "fake", COMBO_LOG, 0,
                             {"simulation_executed": True, "assertion_failed": True, "stage": "simulate"})
        plan = signed_plan()
        plan["stimulus"] = {"mode": "auto"}
        for expected, reason in (("00", "selfcheck_testbench_error"), ("02", "selfcheck_uncertain"), ("03", "selfcheck_passed")):
            replies = [Reply(COMBO_DUT.replace("$signed(a) + $signed(b)", "6'b0").replace("assign sum", "// DUT_SECRET\nassign sum")), Reply(json.dumps(plan)), Reply(witness_reply(expected))]
            sims = [failed]
            if expected == "03":
                replies.append(Reply(COMBO_DUT))
                sims.append(CheckResult("passed", "fake", "RTL_AGENT_PASS", 0))
            out, summary, calls = self.run_flow(replies, sims)
            self.assertEqual(summary["stop_reason"], reason)
            self.assertEqual(len(calls), 4 if expected == "03" else 3)
            payload = json.loads(calls[2].args[0][1]["content"])
            self.assertEqual(payload["specification"], COMBO_SPEC.strip())
            for secret in ("DUT_SECRET", "stim_total", "testbench_expected", "observed", "HIDDEN_ANSWER"):
                self.assertNotIn(secret, json.dumps(payload))
            self.assertTrue((out/"round_01/witness_request.json").is_file())

    def test_missing_history_stops_before_spending_diagnosis_call(self):
        fail = COMBO_LOG.splitlines()[1]
        failed = CheckResult("failed", "fake", fail, 0, {"simulation_executed": True, "assertion_failed": True})
        _, summary, calls = self.run_flow([Reply(COMBO_DUT), Reply(json.dumps(signed_plan()))], [failed])
        self.assertEqual(summary["stop_reason"], "selfcheck_missing_history")
        self.assertEqual(len(calls), 2)

    def test_format_recovery_receives_original_plan_but_no_dut(self):
        plan = signed_plan()
        invalid = copy.deepcopy(plan)
        invalid["expected"]["sum"] = "stim_missing"
        _, summary, calls = self.run_flow([Reply(COMBO_DUT), Reply(json.dumps(invalid)), Reply(json.dumps(plan))],
                                         [CheckResult("passed", "fake", "RTL_AGENT_PASS", 0)])
        self.assertTrue(summary["selfcheck_passed"])
        payload = json.loads(calls[2].args[0][1]["content"])
        self.assertEqual(json.loads(payload["previous_plan_text"]), invalid)
        self.assertNotIn("assign sum", json.dumps(payload))


if __name__ == "__main__":
    unittest.main()
