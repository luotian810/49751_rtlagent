"""接口泛化与截断回归，不把轻量检查当作完整 HDL 解析。"""
import unittest

from agent.interface import check_interface, extract_verilog, infer_top, specification_ports


class TopInferenceTests(unittest.TestCase):
    def test_prompt_declaration_including_parameters(self):
        for declaration in (
            "module Counter(input clk, output q);",
            "module Counter #(parameter W = 8)(input [W-1:0] d, output q);",
        ):
            with self.subTest(declaration=declaration):
                self.assertEqual(infer_top("Implement:\n```verilog\n" + declaration + "\n```"), "Counter")

    def test_explicit_interface_has_priority(self):
        prompt = "Implement module named Wrong.\nmodule Other(input a);"
        self.assertEqual(infer_top(prompt, "module Actual(input a);"), "Actual")

    def test_multiple_modules_need_named_top(self):
        declarations = "module Helper(); endmodule\nmodule Counter(input clk);"
        self.assertEqual(infer_top(declarations), "TopModule")
        self.assertEqual(infer_top("Implement module named Counter.\n" + declarations), "Counter")
        self.assertEqual(infer_top("Implement module named Counter.", declarations), "Counter")

    def test_comments_and_strings_are_not_declarations(self):
        prompt = '// module Wrong();\n"module Another();"\nmodule Actual(input a);'
        self.assertEqual(infer_top(prompt), "Actual")


class PromptInterfaceTests(unittest.TestCase):
    def test_fixed_ports_preserve_signed_inheritance_and_integer_defaults(self):
        source = "module Typed(input signed [4:0] a,b, input int n, input int unsigned u, output [5:0] q);"
        ports = {p["name"]: p for p in specification_ports(source, "", "Typed")}
        self.assertEqual((ports["b"]["width"], ports["b"]["signed"]), (5, True))
        self.assertEqual((ports["n"]["width"], ports["n"]["signed"]), (32, True))
        self.assertFalse(ports["u"]["signed"])
        self.assertFalse(ports["q"]["signed"])

    def test_fixed_ports_refuse_unknown_or_ambiguous_contract(self):
        for source in (
            "module T(input [N-1:0] a, output q);",
            "module T(input custom_type a, output q);",
            "module T(input [3:0] a [0:3], output q);",
            "module T(inout a, output q);",
            "module T(input a,a, output q);",
            "module T(input signed a, output q); module T(input a, output q);",
        ):
            with self.subTest(source=source):
                self.assertIsNone(specification_ports(source, "", "T"))

    def test_fixed_ports_explicit_non_ansi_interface_has_priority(self):
        source = "module T(a,q); input signed [2:0] a; output [3:0] q;"
        ports = specification_ports("module T(input b, output c);", source, "T")
        self.assertEqual([p["name"] for p in ports], ["a", "q"])
        self.assertTrue(ports[0]["signed"])
        self.assertEqual(ports[1]["width"], 4)

    def test_module_lifetime_keywords_are_accepted(self):
        prompt = "module Counter(input [7:0] d, output q);"
        for lifetime in ("automatic", "static"):
            with self.subTest(lifetime=lifetime):
                code = prompt.replace("module Counter", "module " + lifetime + " Counter") + " endmodule"
                self.assertEqual(infer_top(code), "Counter")
                self.assertTrue(extract_verilog(code, "Counter"))
                self.assertTrue(check_interface(code, prompt, "", "Counter")[0])
                self.assertFalse(check_interface(code.replace("[7:0]", "[3:0]"), prompt, "", "Counter")[0])

    def test_builtin_integer_widths_match_equivalent_vectors(self):
        for kind, width in (("byte", 8), ("shortint", 16), ("int", 32),
                            ("integer", 32), ("longint", 64), ("time", 64)):
            with self.subTest(kind=kind):
                prompt = f"module Counter(input {kind} d, output {kind} q);"
                # Integer atom types are signed by default, except time.
                sign = "unsigned" if kind == "time" else "signed"
                code = f"module Counter(input {sign} [{width-1}:0] d, output {sign} [{width-1}:0] q); endmodule"
                self.assertTrue(check_interface(code, prompt, "", "Counter")[0])
                self.assertFalse(check_interface(code.replace(f"[{width-1}:0]", "[2:0]"), prompt, "", "Counter")[0])
                opposite = "signed" if sign == "unsigned" else "unsigned"
                self.assertFalse(check_interface(code.replace(sign, opposite), prompt, "", "Counter")[0])

    def test_all_packed_dimensions_contribute_to_width(self):
        prompt = "module Counter(input [1:0][3:0] a, b, output q);"
        good = "module Counter(input [7:0] a, b, output q); endmodule"
        self.assertTrue(check_interface(good, prompt, "", "Counter")[0])
        self.assertFalse(check_interface(good.replace("[7:0]", "[1:0]"), prompt, "", "Counter")[0])

    def test_unknown_types_and_dimensions_do_not_become_scalar_widths(self):
        code = "module Counter(input [31:0] d, output q); endmodule"
        for port in ("custom_type d", "logic [N-1:0][3:0] d", "logic [3:0] d [0:7]"):
            with self.subTest(port=port):
                prompt = "module Counter(input " + port + ", output q);"
                self.assertTrue(check_interface(code, prompt, "", "Counter")[0])
                self.assertTrue(check_interface(code.replace('input [', 'input signed ['), prompt, "", "Counter")[0])

    def test_explicit_prompt_signature_is_checked(self):
        prompt = "Use this exact interface:\nmodule Counter(input [7:0] d, output q);"
        good = "module Counter(input [7:0] d, output q); assign q = d[0]; endmodule"
        self.assertTrue(check_interface(good, prompt, "", "Counter")[0])
        ok, note = check_interface(good.replace("[7:0]", "[3:0]"), prompt, "", "Counter")
        self.assertFalse(ok)
        self.assertIn("接口错误", note)

    def test_parameterized_width_stays_unknown(self):
        prompt = "module Counter #(parameter W = (2 + 2))(input [W-1:0] d, output q);"
        code = "module Counter(input [3:0] d, output q); assign q=d[0]; endmodule"
        self.assertTrue(check_interface(code, prompt, "", "Counter")[0])
        self.assertFalse(check_interface(code.replace("output q", "input q"), prompt, "", "Counter")[0])

    def test_explicit_interface_overrides_prompt_signature(self):
        prompt = "module Counter(input [3:0] d, output q);"
        interface = "module Counter(input [7:0] d, output q);"
        code = interface + "\nendmodule"
        self.assertTrue(check_interface(code, prompt, interface, "Counter")[0])

    def test_conflicting_prompt_signatures_are_not_strict(self):
        prompt = "module Counter(input [3:0] d);\nmodule Counter(input [7:0] d);"
        code = "module Counter(input [15:0] d); endmodule"
        ok, note = check_interface(code, prompt, "", "Counter")
        self.assertTrue(ok)
        self.assertIn("跳过", note)

    def test_incomplete_prompt_signature_is_not_strict(self):
        prompt = "module Counter(input [3:0] d);\nmodule Counter(input [7:0]"
        code = "module Counter(input [15:0] d); endmodule"
        ok, note = check_interface(code, prompt, "", "Counter")
        self.assertTrue(ok)
        self.assertIn("跳过", note)

    def test_textual_port_list_remains_advisory(self):
        prompt = "module named Counter\n - input q\n"
        ok, note = check_interface("module Counter(output q); endmodule", prompt, "", "Counter")
        self.assertTrue(ok)
        self.assertIn("提示", note)


class CompleteModuleExtractionTests(unittest.TestCase):
    def test_incomplete_target_or_helper_is_rejected(self):
        cases = (
            "module Helper(); endmodule\nmodule TopModule(input a);",
            "module TopModule(input a); endmodule\nmodule Helper(input b);",
            "module TopModule(input a); endmodule\nmodule Helper",
            "module TopModule(input a);\nmodule Helper(); endmodule",
            "module TopModule(); endmodule\nendmodule",
        )
        for source in cases:
            for fenced in (False, True):
                with self.subTest(source=source, fenced=fenced):
                    reply = "```verilog\n" + source + "\n```" if fenced else source
                    self.assertEqual(extract_verilog(reply, "TopModule"), "")

    def test_module_words_in_comments_or_strings_do_not_close_modules(self):
        incomplete = 'module TopModule(); // endmodule\ninitial $display("endmodule");'
        self.assertEqual(extract_verilog(incomplete, "TopModule"), "")
        complete = ('module TopModule(); // module Helper();\n'
                    'initial $display("module endmodule");\nendmodule')
        self.assertEqual(extract_verilog(complete, "TopModule"), complete + "\n")

    def test_complete_multimodule_and_directive_are_preserved(self):
        source = "`timescale 1ns/1ps\nmodule Helper(); endmodule\nmodule TopModule(); endmodule"
        for reply in (source, "```sv\n" + source + "\n```", "```verilog\n" + source):
            with self.subTest(reply=reply):
                self.assertEqual(extract_verilog(reply, "TopModule"), source + "\n")

    def test_unfenced_explanatory_suffix_is_removed(self):
        source = "module TopModule(); endmodule"
        self.assertEqual(extract_verilog("Here is the code:\n" + source +
                                        "\nThis module implements the requested behavior.", "TopModule"),
                         source + "\n")

    def test_target_only_in_comment_is_rejected(self):
        reply = "```verilog\n// module TopModule();\nmodule Helper(); endmodule\n```"
        self.assertEqual(extract_verilog(reply, "TopModule"), "")


if __name__ == "__main__":
    unittest.main()
