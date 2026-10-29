"""Conservative clock-contract controls; no generated model/score claims."""
import unittest

from agent.timing_contract import clock_contract, check_clock_contract


def ports(*names, width=1):
    return [{"name": name, "direction": "input", "width": width, "signed": False} for name in names]


def dut(edge="posedge", clock="pulse", *, top="Unit", reset=True):
    events = f"{edge} {clock}" + (" or negedge clear_n" if reset else "")
    return (f"module {top}(input {clock}, clear_n, d, output reg q);\n"
            f"always @({events}) if (!clear_n) q<=0; else q<=d;\nendmodule\n")


class ClockContractTests(unittest.TestCase):
    def test_named_chinese_english_and_inline_hdl_forms(self):
        for name in ("pulse", "renamed_input", "c"):
            for edge, terms in (("posedge", ("上升沿", "rising", "positive", "posedge")),
                                ("negedge", ("下降沿", "falling", "negative", "negedge"))):
                for text in (f"所有状态在 `{name}` 的{terms[0]}更新。",
                             f"State changes on the {terms[1]} edge of {name}.",
                             f"Use {terms[2]}-edge of '{name}'.", f"Use {terms[3]} {name}."):
                    with self.subTest(text=text):
                        result = clock_contract(text, ports(name, "clear_n"))
                        self.assertEqual((result["name"], result["edge"]), (name, edge))
                        self.assertIn(result["source_quote"], text)

    def test_no_name_guessing_unknown_width_output_or_unknown_ports(self):
        for text, contract_ports in (("Use a rising edge.", ports("clk")),
                                     ("Use posedge pulse.", ports("pulse", width=2)),
                                     ("Use posedge missing.", ports("pulse")),
                                     ("Use posedge pulse.", None),
                                     ("Use posedge pulse.", [{"name":"pulse","direction":"output","width":1}])):
            with self.subTest(text=text, contract_ports=contract_ports):
                self.assertIsNone(clock_contract(text, contract_ports))

    def test_negation_examples_conditionals_and_alternatives_do_not_become_contracts(self):
        for text in ("Do not use posedge pulse.", "Never use falling edge of pulse.",
                     "不要使用 pulse 上升沿。", "不是 pulse 的下降沿。", "If mode, use posedge pulse.",
                     "Use of posedge pulse is forbidden.", "禁止使用 pulse 上升沿。",
                     "Avoid posedge pulse.", "Don't use posedge pulse.", "pulse 的下降沿不更新状态。",
                     "Only if mode, use rising edge of pulse.", "只有 enable=1 时使用 pulse 上升沿。",
                     "Use rising edge of pulse.signal.",
                     "若 enable 为1，使用 pulse 上升沿。", "For example: posedge pulse.",
                     "Example:\nalways @(posedge pulse)\nq<=d;", "```verilog\nalways @(posedge pulse) q<=d;\n```",
                     "Use either rising edge of pulse or falling edge of pulse."):
            with self.subTest(text=text):
                self.assertIsNone(clock_contract(text, ports("pulse")))

    def test_multi_clock_dual_edge_or_conflicting_requirements_are_ambiguous(self):
        for text in ("Use posedge pulse. Use negedge pulse.",
                     "Use posedge pulse. Use posedge other.",
                     "Use posedge pulse. When enable, use posedge other."):
            with self.subTest(text=text):
                self.assertIsNone(clock_contract(text, ports("pulse", "other")))

    def test_declared_edge_before_later_example_remains_available(self):
        result = clock_contract("所有状态在 pulse 上升沿更新。\n例如，输出在下一拍保持。", ports("pulse"))
        self.assertEqual(result["edge"], "posedge")

    def test_reset_assertion_edge_does_not_become_a_sampling_clock(self):
        inputs = ports("pulse", "clear_n", "reset")
        reset_clauses = ("Asynchronous reset occurs on the falling edge of clear_n.",
                         "The falling edge of clear_n resets outputs.",
                         "复位发生在 clear_n 的下降沿。")
        for reset_clause in reset_clauses:
            with self.subTest(reset_clause=reset_clause):
                self.assertIsNone(clock_contract(reset_clause, inputs))
                for text in ("All state updates on the rising edge of pulse. "+reset_clause,
                             reset_clause+" All state updates on the rising edge of pulse."):
                    result = clock_contract(text, inputs)
                    self.assertEqual((result["name"], result["edge"]), ("pulse", "posedge"))
        # This spelling is not itself evidence of reset semantics.
        self.assertEqual(clock_contract("Use posedge reset.", inputs)["name"], "reset")


class ClockSourceTests(unittest.TestCase):
    def test_edges_renames_and_async_reset_are_checked_independently(self):
        for name in ("pulse", "sampling_line"):
            for edge in ("posedge", "negedge"):
                contract = {"name":name,"edge":edge,"source_quote":"explicit"}
                with self.subTest(name=name, edge=edge):
                    good, note = check_clock_contract(dut(edge, name), "Unit", contract)
                    self.assertTrue(good, note)
                    self.assertTrue(note.startswith("matched:"))
                    bad, note = check_clock_contract(dut("negedge" if edge == "posedge" else "posedge", name), "Unit", contract)
                    self.assertFalse(bad, note)
                    self.assertIn("第 2 行", note)

    def test_missing_effective_edge_and_mixed_top_edges_are_rejected(self):
        contract = {"name":"pulse","edge":"posedge"}
        code = "module Unit(input pulse,d, output reg q); always @* q=d; endmodule"
        self.assertFalse(check_clock_contract(code, "Unit", contract)[0])
        mixed = dut()+"\n"
        mixed = mixed.replace("endmodule", "always @(negedge pulse) q<=d;\nendmodule")
        self.assertFalse(check_clock_contract(mixed, "Unit", contract)[0])

    def test_helper_events_and_comments_do_not_supply_top_evidence(self):
        contract = {"name":"pulse","edge":"negedge"}
        helper = dut("negedge",top="Helper")
        code = helper+dut("posedge")+"// always @(negedge pulse)\n"
        self.assertFalse(check_clock_contract(code,"Unit",contract)[0])
        self.assertTrue(check_clock_contract(helper+dut("negedge"),"Unit",contract)[0])

    def test_complex_control_does_not_hide_an_explicit_opposite_edge(self):
        contract = {"name":"pulse","edge":"posedge"}
        code = dut("negedge").replace("always", "always @(posedge pulse iff enable) q<=d;\nalways", 1)
        self.assertFalse(check_clock_contract(code,"Unit",contract)[0])

    def test_complex_clocks_macros_aliases_hierarchy_and_unknown_top_are_not_claimed_checked(self):
        contract = {"name":"pulse","edge":"posedge"}
        cases = ("`define EDGE posedge\n"+dut(),
                 dut().replace("posedge pulse", "posedge pulse iff enable"),
                 "module Unit(input pulse,d, output q); Helper u(pulse,d,q); endmodule",
                 "module Unit(input pulse,d, output reg q); wire derived=pulse; always @(posedge derived) q<=d; endmodule",
                 "module Unit(input pulse,d, output q); wire \\escaped.name ; endmodule",
                 "module Other; endmodule")
        for code in cases:
            with self.subTest(code=code):
                ok,note=check_clock_contract(code,"Unit",contract)
                self.assertTrue(ok,note)
                self.assertTrue(note.startswith("not_checked:"),note)

    def test_no_contract_is_explicitly_unchecked_and_no_source_is_rewritten(self):
        source=dut()
        ok,note=check_clock_contract(source,"Unit",None)
        self.assertTrue(ok)
        self.assertTrue(note.startswith("not_checked:"))
        self.assertEqual(source,dut())

    def test_inactive_generate_branch_cannot_reject_a_correct_edge(self):
        contract = {"name":"pulse", "edge":"posedge"}
        code = ("module Unit(input pulse,d, output reg q);\n"
                "generate if (1) begin always @(posedge pulse) q<=d; end\n"
                "else begin always @(negedge pulse) q<=d; end endgenerate\nendmodule")
        ok, note = check_clock_contract(code, "Unit", contract)
        self.assertTrue(ok, note)
        self.assertTrue(note.startswith("not_checked:"), note)

    def test_implicit_generate_branches_are_not_checked_without_elaboration(self):
        contract = {"name":"pulse", "edge":"posedge"}
        header = "module Unit(input pulse,d, output reg q);\n"
        good = "always @(posedge pulse) q<=d;"
        inactive = "always @(negedge pulse) q<=d;"
        for body in (
            f"if (1) {good} else {inactive}",
            f"if ((1 == 1)) begin wire unused; {good} end else begin {inactive} end",
            f"if (1) begin : chosen {good} end else begin : omitted {inactive} end",
            f"case (1) 1: begin {good} end default: begin {inactive} end endcase",
            f"genvar i; for (i=0; i<1; i=i+1) begin : rows {good} end {inactive}",
        ):
            with self.subTest(body=body):
                ok, note = check_clock_contract(header+body+"\nendmodule", "Unit", contract)
                self.assertTrue(ok, note)
                self.assertTrue(note.startswith("not_checked:"), note)

    def test_procedural_if_or_case_does_not_hide_a_later_wrong_edge(self):
        contract = {"name":"pulse", "edge":"posedge"}
        for process in (
            "always @(posedge pulse) if(clear_n) q<=d; else q<=0;",
            "always @(posedge pulse) begin if(clear_n) begin q<=d; end else begin q<=0; end end",
            "always @(posedge pulse) begin case(clear_n) 1: q<=d; default: q<=0; endcase end",
        ):
            with self.subTest(process=process):
                code = ("module Unit(input pulse,clear_n,d, output reg q);\n"+process+
                        "\nalways @(negedge pulse) q<=d; endmodule")
                self.assertFalse(check_clock_contract(code,"Unit",contract)[0])


if __name__ == "__main__":
    unittest.main()
