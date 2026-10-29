"""Compiler repair feedback keeps real evidence and general language constraints."""
import unittest

from agent.repair import MAX_FEEDBACK_CHARS, compiler_diagnostic


SOURCE = "module TopModule;\nlogic [15:0] data;\nlogic [3:0] amount;\n" \
         "assign value = data[amount:0];\nendmodule\n"


class RepairFeedbackTests(unittest.TestCase):
    def test_vivado_constant_error_context_and_cascade_filter(self):
        log = "INFO: compiling\nWARNING: no clocks\n" \
              "ERROR: [VRFC 10-2951] 'amount' is not a constant [/var/tmp/a/rtl.sv:4]\n" \
              "ERROR: [VRFC 10-1775] range must be bounded by constant expressions [/var/tmp/a/rtl.sv:4]\n" \
              "ERROR: [VRFC 10-8530] module 'TopModule' is ignored due to previous errors [rtl.sv:1]"
        result = compiler_diagnostic(log, SOURCE, "lint")
        self.assertEqual(result["category"], "constant_expression")
        self.assertEqual(result["source_lines"], [4])
        self.assertIn(">   4: assign value = data[amount:0];", result["feedback"])
        self.assertEqual(len(result["diagnostics"]), 2)
        self.assertNotIn("WARNING", result["feedback"])
        self.assertNotIn("ignored due", result["feedback"])

    def test_renaming_width_line_and_workspace_do_not_hide_repeat(self):
        first = compiler_diagnostic("ERROR: [VRFC 10-2951] 'amount' is not a constant [/var/tmp/a/rtl.sv:4]",
                                    SOURCE, "lint")
        changed = "// new line\n" + SOURCE.replace("15:0", "31:0").replace("amount", "shift_count")
        result = compiler_diagnostic("ERROR: [VRFC 10-2951] 'shift_count' is not a constant [D:\\temp dir\\other\\rtl.sv:5]",
                                     changed, "lint", first)
        self.assertTrue(result["repeated"])
        self.assertEqual(result["source_lines"], [5])
        self.assertIn("不同的合法表达结构", result["feedback"])
        self.assertIn("shift_count", result["feedback"])

    def test_syntax_tokens_and_different_error_families_are_not_merged(self):
        first = compiler_diagnostic("ERROR: [VRFC 10-4982] syntax error near '-' [rtl.sv:4]", SOURCE, "lint")
        for diagnostic in ("syntax error near '.'", "'amount' is not a constant", "syntax error near ')' "):
            result = compiler_diagnostic(f"ERROR: [VRFC 10-4982] {diagnostic} [rtl.sv:4]", SOURCE, "lint", first)
            self.assertFalse(result["repeated"])
        self.assertEqual(first["category"], "syntax")

    def test_icarus_syntax_and_fatal_are_accepted_without_invented_context(self):
        result = compiler_diagnostic("rtl.sv:4: syntax error\nrtl.sv:4: error: malformed statement\n"
                                     "FATAL: compiler aborted", SOURCE, "lint")
        self.assertEqual(result["category"], "syntax")
        self.assertEqual(result["source_lines"], [4])
        self.assertEqual(len(result["diagnostics"]), 3)

    def test_modelsim_quoted_line_and_parentheses_locations(self):
        for location in ('"D:\\work dir\\rtl.sv" Line 4', 'rtl.sv(4)'):
            with self.subTest(location=location):
                result = compiler_diagnostic(f'# ** Error: {location}: near "-": syntax error', SOURCE, "lint")
                self.assertEqual(result["category"], "syntax")
                self.assertEqual(result["source_lines"], [4])

    def test_procedural_target_and_missing_module_have_separate_guidance(self):
        procedural = compiler_diagnostic("ERROR: [VRFC 10-1280] procedural assignment to a non-register value_o "
                                          "is not permitted, left-hand side should be reg/integer/time/genvar [rtl.sv:4]", SOURCE, "lint")
        missing = compiler_diagnostic("rtl.sv:4: error: Unknown module type: HelperUnit", SOURCE, "elaborate")
        self.assertEqual(procedural["category"], "procedural_target")
        self.assertEqual(missing["category"], "missing_module")
        self.assertIn("过程赋值", procedural["feedback"])
        self.assertIn("辅助模块", missing["feedback"])

    def test_unknown_messages_preserved_and_not_merged_by_category(self):
        first = compiler_diagnostic("ERROR: [VRFC 10-9999] unrecognized attribute alpha [rtl.sv:4]", SOURCE, "lint")
        second = compiler_diagnostic("ERROR: [VRFC 10-9999] unrecognized attribute beta [rtl.sv:4]", SOURCE, "lint", first)
        self.assertEqual(first["category"], "unknown")
        self.assertIn("unrecognized attribute alpha", first["feedback"])
        self.assertFalse(second["repeated"])

    def test_warnings_source_echoes_and_summary_are_not_diagnostics(self):
        result = compiler_diagnostic('WARNING: syntax error may follow\nINFO: 0 errors\n'
                                     'rtl.sv:4: warning: undeclared net\n'
                                     '$display("ERROR: a user message");\n0 errors detected', SOURCE, "lint")
        self.assertEqual(result["diagnostics"], [])
        self.assertIsNone(result["signature"])
        self.assertEqual(result["source_lines"], [])
        self.assertFalse(result["repeated"])

    def test_header_testbench_and_out_of_range_locations_have_no_source_context(self):
        for filename, line in (("tb.sv", 4), ("constants.svh", 4), ("rtl.sv", 1000)):
            with self.subTest(filename=filename, line=line):
                result = compiler_diagnostic(f"ERROR: syntax error [{filename}:{line}]", SOURCE, "lint")
                self.assertEqual(result["source_lines"], [])
                self.assertNotIn("assign value =", result["feedback"])

    def test_feedback_is_bounded_and_keeps_root_before_long_context(self):
        source = "\n".join("assign value = " + "x" * 10000 for _ in range(20))
        log = "\n".join(f"ERROR: syntax error near ')' {'detail' * 200} [rtl.sv:{line}]" for line in range(3, 20))
        result = compiler_diagnostic(log, source, "lint")
        self.assertLessEqual(len(result["feedback"]), MAX_FEEDBACK_CHARS)
        self.assertLessEqual(len(result["diagnostics"]), 4)
        self.assertIn("syntax error near ')'", result["feedback"])
        self.assertEqual(result["source_lines"], [3, 4, 5])

    def test_cascade_only_is_retained_and_stage_prevents_false_repeat(self):
        log = "ERROR: failed to elaborate design"
        first = compiler_diagnostic(log, SOURCE, "lint")
        second = compiler_diagnostic(log, SOURCE, "elaborate", first)
        self.assertEqual(first["diagnostics"], [log])
        self.assertFalse(second["repeated"])


if __name__ == "__main__":
    unittest.main()
