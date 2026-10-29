"""Behavior-plan mechanism controls; no model generation or capability claim."""
import copy
import json
import unittest

from agent.behavior_plan import BehaviorPlanError, needs_behavior_plan, parse_behavior_plan


PORTS = [{"name": "pulse", "direction": "input", "width": 1},
         {"name": "clear", "direction": "input", "width": 1},
         {"name": "sample", "direction": "input", "width": 9},
         {"name": "published", "direction": "output", "width": 9},
         {"name": "valid", "direction": "output", "width": 1}]


def plan():
    return {"states": [{"name": "held", "meaning": "最近接受的数据", "reset": "0"}],
            "events": [{"when": "复位有效", "next": "清空所有状态", "outputs": "清零寄存发布结果"},
                       {"when": "没有接受事件", "next": "旧状态保持", "outputs": "发布值保持，valid清零"}],
            "outputs": {"published": {"kind": "registered", "rule": "接受沿后发布保存值；其他沿保持"},
                        "valid": {"kind": "registered", "rule": "仅接受沿后置位"}}}


class BehaviorRoutingTests(unittest.TestCase):
    def test_explicit_edges_and_sequential_language_trigger(self):
        for specification in ("All state updates on the rising edge of pulse.",
                              "All flip-flops are clocked on falling edges.",
                              "D flip-flops sample incoming words.",
                              "Implement sequential logic with reset.",
                              "This is one registered storage slot.",
                              "状态仅在 event_line 的下降沿更新。",
                              "全部时序逻辑在 event_line 上升沿工作。",
                              "always_ff @(posedge event_line) models the required sampling."):
            with self.subTest(specification=specification):
                self.assertTrue(needs_behavior_plan(specification))

    def test_names_and_interface_types_do_not_infer_clock_or_state(self):
        for specification in ("module Echo(input clk, output reg q); q is the complement of clk.",
                              "Return the largest index; all ports are combinational.",
                              "The signal is named sequential_clock.", "", None, 1):
            with self.subTest(specification=specification):
                self.assertFalse(needs_behavior_plan(specification))

    def test_negative_hypothetical_or_example_only_timing_does_not_trigger(self):
        for specification in ("Do not use flip-flops. This is a combinational circuit.",
                              "No sequential logic is required.",
                              "无需时序逻辑，仅做组合映射。",
                              "For example: always @(posedge clk) would be unnecessary.",
                              "Example:\n  always @(posedge clk)\n  q <= d;",
                              "示例：\n```verilog\nalways @(negedge clk) q<=d;\n```",
                              "A sequential implementation could be used, but is not required.",
                              "假设以后需要上升沿触发，目前只实现组合输出。"):
            with self.subTest(specification=specification):
                self.assertFalse(needs_behavior_plan(specification))

    def test_real_requirement_after_example_is_retained(self):
        specification = "Example:\n  always @(posedge previous_clock)\n\nUpdate state on the falling edge of new_event."
        self.assertTrue(needs_behavior_plan(specification))
        self.assertTrue(needs_behavior_plan("无时钟的组合输出只是辅助。\n寄存器在下降沿更新。"))


class BehaviorParsingTests(unittest.TestCase):
    def test_valid_plan_normalizes_prose_and_preserves_output_bindings(self):
        proposed = plan()
        proposed["states"][0]["meaning"] = "  最近接受的数据  "
        accepted = parse_behavior_plan(json.dumps(proposed), PORTS)
        self.assertEqual(accepted["states"][0]["meaning"], "最近接受的数据")
        self.assertEqual(set(accepted["outputs"]), {"published", "valid"})
        self.assertEqual(proposed["states"][0]["meaning"], "  最近接受的数据  ")
        self.assertEqual(parse_behavior_plan(json.dumps(accepted), PORTS), accepted)

    def test_unknown_is_explicit_and_never_filled_with_an_assumed_state(self):
        proposed = {"states": [], "events": [{"when": "unknown", "next": "unknown", "outputs": "unknown"}],
                    "outputs": {"published": {"kind": "unknown", "rule": "unknown"},
                                "valid": {"kind": "unknown", "rule": "unknown"}}}
        self.assertEqual(parse_behavior_plan(json.dumps(proposed), PORTS), proposed)
        self.assertEqual(parse_behavior_plan(json.dumps(plan()), None), plan())

    def test_think_wrapper_and_json_fence_are_accepted_but_extra_prose_is_not(self):
        text = json.dumps(plan())
        self.assertEqual(parse_behavior_plan("<think>draft</think>\n```json\n"+text+"\n```", PORTS), plan())
        for reply in ("Here is the plan:\n"+text, text+"\nUse this design.", '{"states":', '[]', '<think>unfinished'):
            with self.subTest(reply=reply), self.assertRaises(BehaviorPlanError):
                parse_behavior_plan(reply, PORTS)

    def test_missing_added_or_input_outputs_and_unknown_fields_are_rejected(self):
        variants = []
        missing = plan()
        del missing["outputs"]["valid"]
        variants.append(missing)
        added = plan()
        added["outputs"]["sample"] = {"kind": "combinational", "rule": "input passthrough"}
        variants.append(added)
        renamed = plan()
        renamed["outputs"]["other"] = renamed["outputs"].pop("valid")
        variants.append(renamed)
        extra = plan()
        extra["ports"] = PORTS
        variants.append(extra)
        for proposed in variants:
            with self.subTest(proposed=proposed), self.assertRaises(BehaviorPlanError):
                parse_behavior_plan(json.dumps(proposed), PORTS)

    def test_schema_bounds_duplicate_state_names_and_duplicate_json_keys(self):
        variants = []
        for field, value in (("events", []), ("events", plan()["events"]*13), ("states", plan()["states"]*17)):
            proposed = plan()
            proposed[field] = value
            variants.append(proposed)
        duplicate = plan()
        duplicate["states"] *= 2
        variants.append(duplicate)
        long_text = plan()
        long_text["outputs"]["valid"]["rule"] = "x"*601
        variants.append(long_text)
        invalid_kind = plan()
        invalid_kind["outputs"]["valid"]["kind"] = True
        variants.append(invalid_kind)
        invalid_event = plan()
        invalid_event["events"][0]["next"] = None
        variants.append(invalid_event)
        for proposed in variants:
            with self.subTest(proposed=proposed), self.assertRaises(BehaviorPlanError):
                parse_behavior_plan(json.dumps(proposed), PORTS)
        for text in ('{"states":[],"states":[],"events":[],"outputs":{}}', 'x'*16001):
            with self.assertRaises(BehaviorPlanError):
                parse_behavior_plan(text, PORTS)

    def test_hdl_commands_and_external_access_are_not_plan_prose(self):
        for source in ("module Bad(input a); endmodule", "always @(posedge pulse) q<=d;",
                       "assign published = sample;", "reg [8:0] q;", "if (enable) q <= d;",
                       "$system(command)", "curl https://example.com/answers", "import os",
                       "hold; rm -rf /workspace", "```verilog q <= d; ```"):
            proposed = plan()
            proposed["events"][0]["next"] = source
            with self.subTest(source=source), self.assertRaises(BehaviorPlanError):
                parse_behavior_plan(json.dumps(proposed), PORTS)

    def test_renamed_and_resized_interfaces_keep_exact_output_coverage(self):
        for width in (1, 7, 35):
            ports = copy.deepcopy(PORTS)
            ports[3].update(name="delivered", width=width)
            proposed = plan()
            proposed["outputs"]["delivered"] = proposed["outputs"].pop("published")
            with self.subTest(width=width):
                self.assertEqual(set(parse_behavior_plan(json.dumps(proposed), ports)["outputs"]), {"delivered", "valid"})
        for bad_ports in ({}, [], [{"name": "x", "direction": "other"}], PORTS+[PORTS[0]]):
            with self.subTest(bad_ports=bad_ports), self.assertRaises(BehaviorPlanError):
                parse_behavior_plan(json.dumps(plan()), bad_ports)


if __name__ == '__main__':
    unittest.main()
