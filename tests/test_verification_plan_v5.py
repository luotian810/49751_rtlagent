"""紧凑计划的机制回归；手写参考与突变体不计作千问能力测量。"""
import copy
import json
import unittest

from agent.verification_plan import PlanError, build_testbench, plan_contract
from tests import test_verification_plan_v4 as fixtures
from tests.test_verification_plan_v4 import (
    COMBO_DUT, COMBO_SPEC, FIFO_DUT, FIFO_SPEC, PARITY_DUT, PARITY_SPEC,
    native_fifo_plan, native_parity_group_plan,
)


def compact_fixture(plan):
    """复用已验证的规格/参考算法，只改变测试输入的表达格式。"""
    plan = copy.deepcopy(plan)
    advance, variables = plan.pop("advance"), plan.pop("variables")
    plan.pop("ports")
    plan["states"], plan["temporaries"] = [], []
    for variable in variables:
        name = variable["name"]
        if name.startswith("stim_"):
            if name in advance["temporary"]:
                plan["temporaries"].append({**variable, "expr": advance["temporary"][name]})
        elif variable.get("depth", 1) > 1:
            writes = [{k: v for k, v in item.items() if k != "array"}
                      for item in advance["writes"] if item["array"] == name]
            plan["states"].append({**variable, "writes": writes})
        else:
            plan["states"].append({**variable, "next": advance["next"].get(name, name)})
    return plan


def signed_plan():
    return {
        "clock": None, "reset": None, "async_reset": None, "states": [],
        "temporaries": [{"name": "stim_total", "width": 6, "signed": True,
                         "expr": "$signed(a) + $signed(b)"}],
        "expected": {"sum": "stim_total"},
        "stimulus": {
            "directed": [{"values": ["15", "15"]}, {"values": ["16", "16"]}],
            "random": {"cycles": 96, "values": ["__va_index", "$random(__va_seed)"]},
        },
    }


class CompactPlanBoundaryTests(unittest.TestCase):
    def test_solver_uses_fixed_contract_and_saves_compact_plan(self):
        out, summary, events, calls, simulations = fixtures.StructuredFlowTests.run_flow(
            self, [fixtures.Reply(json.dumps(signed_plan()))])
        self.assertTrue(summary["selfcheck_passed"])
        self.assertEqual(simulations, 1)
        payload = json.loads(calls[1].args[0][1]["content"])
        self.assertTrue(payload["contract"]["ports_fixed"])
        plan = json.loads((out / "verification_plan.json").read_text(encoding="utf-8"))
        self.assertIn("temporaries", plan)
        self.assertNotIn("variables", plan)
        fixtures.StructuredFlowTests.assert_specification_only(self, calls)

    def test_fixed_interface_needs_no_model_restatement_and_plan_replays(self):
        contract = plan_contract(COMBO_SPEC, "", "SignedAdder")
        self.assertTrue(contract["ports_fixed"])
        self.assertTrue(all(p["signed"] for p in contract["ports"]))
        tb, plan = build_testbench(json.dumps(signed_plan()), "SignedAdder", COMBO_SPEC)
        self.assertNotIn("variables", plan)
        self.assertEqual(tb, build_testbench(json.dumps(plan), "SignedAdder", COMBO_SPEC)[0])

    def test_fixed_port_width_or_signed_cannot_be_overridden(self):
        for field, value in (("width", 4), ("signed", False)):
            plan = signed_plan()
            plan["ports"] = plan_contract(COMBO_SPEC, "", "SignedAdder")["ports"]
            plan["ports"][0][field] = value
            with self.subTest(field=field), self.assertRaises(PlanError):
                build_testbench(json.dumps(plan), "SignedAdder", COMBO_SPEC)

    def test_unknown_signature_does_not_guess_ports_or_widths(self):
        spec = "module SignedAdder #(parameter W=5)(input signed [W-1:0] a,b, output signed [W:0] sum);"
        self.assertFalse(plan_contract(spec, "", "SignedAdder")["ports_fixed"])
        with self.assertRaises(PlanError):
            build_testbench(json.dumps(signed_plan()), "SignedAdder", spec)

    def test_temporary_declaration_is_local_and_missing_width_is_rejected(self):
        plan = signed_plan()
        del plan["temporaries"][0]["width"]
        with self.assertRaisesRegex(PlanError, "width"):
            build_testbench(json.dumps(plan), "SignedAdder", COMBO_SPEC)

    def test_undeclared_forward_or_cyclic_temporaries_fail_before_compilation(self):
        for expression in ("stim_missing + a", "stim_total + a", "invented_symbol + b"):
            plan = signed_plan()
            plan["temporaries"][0]["expr"] = expression
            with self.subTest(expression=expression), self.assertRaises(PlanError):
                build_testbench(json.dumps(plan), "SignedAdder", COMBO_SPEC)

    def test_expected_cannot_read_dut_outputs_or_undeclared_variables(self):
        for expression in ("sum", "stim_absent", "__va_tests"):
            plan = signed_plan()
            plan["expected"]["sum"] = expression
            with self.subTest(expression=expression), self.assertRaises(PlanError):
                build_testbench(json.dumps(plan), "SignedAdder", COMBO_SPEC)

    def test_state_records_cannot_mix_scalar_array_or_legacy_update_forms(self):
        malformed = []
        missing_next = compact_fixture(native_parity_group_plan())
        del missing_next["states"][0]["next"]
        malformed.append(missing_next)
        legacy = compact_fixture(native_parity_group_plan())
        legacy["advance"] = {}
        malformed.append(legacy)
        invalid_array = compact_fixture(native_fifo_plan())
        invalid_array["states"][0]["next"] = "0"
        malformed.append(invalid_array)
        for plan in malformed:
            with self.subTest(plan=plan), self.assertRaises(PlanError):
                build_testbench(json.dumps(plan), "SmallQueue" if "writes" in plan["states"][0] else "GroupParity",
                                FIFO_SPEC if "writes" in plan["states"][0] else PARITY_SPEC)


class CompactPlanExecutionTests(unittest.TestCase):
    setUp = fixtures.PlanExecutionTests.setUp
    simulate = fixtures.PlanExecutionTests.simulate

    def test_native_expression_comparison_is_not_confused_with_nba_statement(self):
        specification = "module Compare(input [4:0] a,b, output le); Return a <= b."
        dut = "module Compare(input [4:0] a,b, output le); assign le=(a<=b); endmodule"
        plan = signed_plan()
        plan["temporaries"] = [{"name": "stim_le", "width": 1, "expr": "a <= b"}]
        plan["expected"] = {"le": "stim_le"}
        result = self.simulate(plan, dut, "Compare", specification, "compact-comparison")
        self.assertEqual(result.status, "passed", result.log)

    def test_signed_temporary_widens_before_expected_assignment(self):
        good = self.simulate(signed_plan(), COMBO_DUT, "SignedAdder", COMBO_SPEC, "compact-signed")
        narrow = signed_plan()
        narrow["temporaries"][0]["width"] = 5
        bad_oracle = self.simulate(narrow, COMBO_DUT, "SignedAdder", COMBO_SPEC, "compact-narrow-oracle")
        self.assertEqual(good.status, "passed", good.log)
        self.assertEqual(bad_oracle.status, "failed", bad_oracle.log)

    def test_simultaneous_state_updates_include_current_input_once(self):
        plan = compact_fixture(native_parity_group_plan())
        good = self.simulate(plan, PARITY_DUT, "GroupParity", PARITY_SPEC, "compact-group")
        mutant = PARITY_DUT.replace("parity<=accum ^ data;", "parity<=accum;")
        bad = self.simulate(plan, mutant, "GroupParity", PARITY_SPEC, "compact-group-mutant")
        self.assertEqual(good.status, "passed", good.log)
        self.assertEqual(bad.status, "failed", bad.log)
        self.assertIn("after_edge=0 clear_n=0", good.log)
        self.assertIn("after_edge=1 clear_n=1", good.log)

    def test_array_writes_and_post_edge_combinational_output_share_snapshot(self):
        plan = compact_fixture(native_fifo_plan())
        good = self.simulate(plan, FIFO_DUT, "SmallQueue", FIFO_SPEC, "compact-fifo")
        wrong_phase = copy.deepcopy(plan)
        wrong_phase["expected"]["empty"] = "old_ref_count==0"
        bad = self.simulate(wrong_phase, FIFO_DUT, "SmallQueue", FIFO_SPEC, "compact-preedge-oracle")
        self.assertEqual(good.status, "passed", good.log)
        self.assertEqual(bad.status, "failed", bad.log)


if __name__ == "__main__":
    unittest.main()
