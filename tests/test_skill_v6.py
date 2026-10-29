"""跨接口、位宽及采样条件的机制回归；无真实模型调用或题库答案。"""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agent.llm import Reply
from agent.main import compiler_feedback, main
from agent.verification_plan import PlanError, build_testbench, plan_contract
from tests.test_flow_v2 import PASS, TB
from tests import test_verification_plan_v4 as plan_fixtures
from tests.test_verification_plan_v5 import signed_plan, COMBO_SPEC, COMBO_DUT


def register_case(width, edge, active, asynchronous):
    """同一状态采样规格的参数变换，用来检验模板而非模型解题能力。"""
    top = "SampleBus"
    # 名字故意不暗示极性；复位值也不是默认的零。
    names = {"clock": "event_line", "reset": "clear_line", "enable": "accept_word",
             "data": "incoming", "output": "stored"}
    initial = (1 << (width - 1)) | 1
    signature = (f"module {top}(input event_line, clear_line, accept_word, "
                 f"input [{width-1}:0] incoming, output reg [{width-1}:0] stored);")
    control = {"name": names["reset"], "active": active}
    spec = signature + (f" On {edge}, capture incoming if accept_word, else hold. "
                        f"Reset is {'asynchronous' if asynchronous else 'synchronous'}, active {active}, "
                        f"and sets stored to {initial}, with priority over acceptance.")
    sensitivity = edge + " event_line"
    if asynchronous:
        sensitivity += " or " + ("posedge" if active else "negedge") + " clear_line"
    dut = (signature + f"\nalways @({sensitivity}) begin\n"
           f"if (clear_line == 1'b{active}) stored <= {width}'d{initial};\n"
           "else if (accept_word) stored <= incoming;\nend\nendmodule")

    def values(reset, enable, data):
        return {"clear_line": reset, "accept_word": enable, "incoming": data}

    plan = {
        "clock": {"name": names["clock"], "edge": edge},
        "reset": control, "async_reset": control if asynchronous else None,
        "temporaries": [],
        "states": [{"name": "ref_saved", "width": width, "initial": f"{width}'d{initial}",
                    "next": "accept_word ? incoming : ref_saved"}],
        "expected": {"stored": "ref_saved"},
        "stimulus": {
            # 首条模型刺激故意不复位：模板必须先建立规格初态。
            "directed": [{"values": values(1-active, 0, 0)},
                         {"values": values(1-active, 1, 2)},
                         {"values": values(1-active, 0, initial)},
                         {"values": values(active, 1, 0)},
                         {"values": values(1-active, 0, 1)}],
            "random": {"cycles": 64, "values": values(1-active, "(__va_index%3)!=0", "$random(__va_seed)")},
        },
    }
    return plan, dut, top, spec


class ContractAndDiagnosticsTests(unittest.TestCase):
    def test_contract_names_follow_renamed_and_signed_ports_without_clock_guessing(self):
        for width in (1, 3, 11):
            spec = (f"module WireMap(input signed [{width-1}:0] clock_like, payload, "
                    f"output signed [{width-1}:0] observed);")
            contract = plan_contract(spec, "", "WireMap")
            self.assertEqual(contract["values_template"], {"clock_like": "", "payload": ""})
            self.assertEqual(contract["forbidden_reference_names"], ["observed"])
            self.assertTrue(all(p["width"] == width and p["signed"] for p in contract["ports"]))
        unknown = plan_contract("module P(input [W-1:0] d, output q);", "", "P")
        self.assertFalse(unknown["ports_fixed"])
        self.assertNotIn("values_template", unknown)

    def test_missing_and_extra_names_report_location_without_filling_values(self):
        plan, _, top, spec = register_case(3, "negedge", 1, False)
        values = plan["stimulus"]["directed"][1]["values"]
        del values["clear_line"]
        values["event_line"] = 0
        before = copy.deepcopy(plan)
        with self.assertRaises(PlanError) as caught:
            build_testbench(json.dumps(plan), top, spec)
        self.assertIn("stimulus.directed[1].values", str(caught.exception))
        self.assertIn("缺少 ['clear_line']", str(caught.exception))
        self.assertIn("多余 ['event_line']", str(caught.exception))
        self.assertEqual(plan, before)

    def test_random_and_output_key_errors_identify_the_actual_names(self):
        for section in ("random", "expected"):
            plan = signed_plan()
            if section == "random":
                plan["stimulus"]["random"]["values"] = {"a": 0, "wrong": 0}
            else:
                plan["expected"] = {"wrong": 0}
            with self.subTest(section=section), self.assertRaises(PlanError) as caught:
                build_testbench(json.dumps(plan), "SignedAdder", COMBO_SPEC)
            self.assertIn("stimulus.random.values" if section == "random" else "expected", str(caught.exception))
            self.assertIn("wrong", str(caught.exception))
            self.assertIn("b" if section == "random" else "sum", str(caught.exception))

    def test_forbidden_outputs_and_functions_remain_rejected_with_specific_diagnostics(self):
        for expression, symbol in (("sum", "sum"), ("$countones(a)", "countones")):
            plan = signed_plan()
            plan["temporaries"][0]["expr"] = expression
            with self.subTest(expression=expression), self.assertRaises(PlanError) as caught:
                build_testbench(json.dumps(plan), "SignedAdder", COMBO_SPEC)
            self.assertIn("temporary.stim_total", str(caught.exception))
            self.assertIn(symbol, str(caught.exception))

    def test_compiler_feedback_keeps_early_errors_even_when_footer_is_long(self):
        first = "ERROR: [VRFC 10-2951] selector is not a constant [rtl.sv:12]"
        second = "rtl.sv:18: error: incompatible assignment"
        log = first + "\n" + second + "\n" + "INFO: diagnostic footer\n" * 500
        result = compiler_feedback(log)
        self.assertIn(first, result)
        self.assertIn(second, result)
        self.assertNotIn("diagnostic footer", result)
        self.assertLess(len(result), 4200)

    def test_unrecognized_compiler_output_is_retained_for_review(self):
        self.assertIn("tool exited with code 2", compiler_feedback("tool exited with code 2"))


class DesignMessageTests(unittest.TestCase):
    def run_flow(self, spec, replies, *, lint=None):
        with tempfile.TemporaryDirectory() as directory:
            task, out = Path(directory)/"task", Path(directory)/"out"
            task.mkdir()
            (task/"prompt.txt").write_text(spec, encoding="utf-8")
            (task/"reference.sv").write_text("HIDDEN_REFERENCE_SENTINEL", encoding="utf-8")
            (task/"tb.sv").write_text("HIDDEN_TESTBENCH_SENTINEL", encoding="utf-8")
            with patch("agent.main.LLM.chat", side_effect=replies) as model, patch("agent.main.Toolchain") as tools, patch("builtins.print"):
                tools.return_value.describe.return_value = {"backend": "fake"}
                tools.return_value.lint.side_effect = lint or [PASS] * 3
                tools.return_value.simulate.return_value = PASS
                self.assertEqual(main(["--input", str(task), "--output", str(out),
                                       "--verification-mode", "legacy", "--deadline", "60"]), 0)
            return model.call_args_list

    def test_design_and_interface_repair_receive_same_fixed_signature(self):
        for width in (3, 9):
            spec = f"module Relay(input signed [{width-1}:0] source_word, output signed [{width-1}:0] dest_word);"
            correct = spec + " assign dest_word=source_word; endmodule"
            wrong = correct.replace(f"[{width-1}:0]", f"[{width}:0]", 1)
            calls = self.run_flow(spec, [Reply(wrong), Reply(correct), Reply(TB)])
            expected = {"top": "Relay", "ports": plan_contract(spec, "", "Relay")["ports"]}
            marker = "固定接口契约（从规格可靠提取，设计和修复都必须保持）：\n"
            for call in calls[:2]:
                text = call.args[0][1]["content"]
                payload, _ = json.JSONDecoder().raw_decode(text.split(marker)[1])
                self.assertEqual(payload, expected)
            verifier = json.loads(calls[2].args[0][1]["content"])
            self.assertEqual(verifier["specification"], spec)
            self.assertNotIn("assign dest_word", str(calls[2].args[0]))
            self.assertNotIn("HIDDEN_", str(calls))

    def test_unknown_parameter_width_does_not_create_a_guessed_design_contract(self):
        spec = "module ParamBus #(parameter W=5)(input [W-1:0] data, output q);"
        code = spec + " assign q=^data; endmodule"
        calls = self.run_flow(spec, [Reply(code), Reply(TB)])
        self.assertEqual(calls[0].args[0][1]["content"], spec)


class ResetAndSamplingExecutionTests(unittest.TestCase):
    setUp = plan_fixtures.PlanExecutionTests.setUp
    simulate = plan_fixtures.PlanExecutionTests.simulate

    def test_initial_reset_and_hold_across_widths_edges_polarities_and_sync_modes(self):
        for width in (3, 7):
            for edge in ("posedge", "negedge"):
                for active in (0, 1):
                    for asynchronous in (False, True):
                        tag = f"w{width}-{edge}-r{active}-async{asynchronous}"
                        with self.subTest(tag=tag):
                            plan, dut, top, spec = register_case(width, edge, active, asynchronous)
                            result = self.simulate(plan, dut, top, spec, tag)
                            self.assertEqual(result.status, "passed", result.log)
                            self.assertIn(f"clear_line={active}", result.log)
                            if asynchronous:
                                self.assertIn("sample=1 after_edge=0", result.log)
                            else:
                                self.assertIn("sample=1 after_edge=1", result.log)

    def test_reference_initialization_alone_cannot_substitute_for_dut_reset(self):
        plan, dut, top, spec = register_case(7, "posedge", 1, False)
        tb, _ = build_testbench(json.dumps(plan), top, spec)
        # 去掉新前置复位后，正确 DUT 在首次保持拍仍为未知态：重现机制缺口。
        no_reset = tb.replace("// Establish the declared reset before the first functional stimulus.\nstep(1, 0, 0);", "")
        self.assertNotEqual(tb, no_reset)
        result = self.tools.simulate(dut, no_reset, top, self.root/"missing-initial-reset", 30)
        self.assertEqual(result.status, "failed", result.log)
        self.assertIn("RTL_AGENT_FAIL", result.log)

    def test_reset_prologue_does_not_hide_wrong_enable_or_wrong_edge(self):
        plan, dut, top, spec = register_case(3, "negedge", 0, True)
        mutants = {
            "ignores-enable": dut.replace("else if (accept_word)", "else"),
            "wrong-edge": dut.replace("negedge event_line", "posedge event_line"),
            "sync-instead-of-async": dut.replace(" or negedge clear_line", ""),
        }
        for tag, mutant in mutants.items():
            with self.subTest(tag=tag):
                result = self.simulate(plan, mutant, top, spec, tag)
                self.assertEqual(result.status, "failed", result.log)

    def test_combinational_plan_still_has_no_reset_or_clock_step(self):
        result = self.simulate(signed_plan(), COMBO_DUT, "SignedAdder", COMBO_SPEC, "combo")
        self.assertEqual(result.status, "passed", result.log)
        self.assertIn("CHECKS=98", result.log)


if __name__ == "__main__":
    unittest.main()
