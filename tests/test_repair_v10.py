"""V10 compiler-family controls, using real diagnostic shapes; no model calls."""
import unittest

from agent.repair import MAX_FEEDBACK_CHARS, compiler_diagnostic


class BatchedRootGuidanceTests(unittest.TestCase):
    def test_mixed_syntax_and_assignment_roots_get_guidance_in_one_request(self):
        log = ("ERROR: [VRFC 10-4982] syntax error near '-' [rtl.sv:3]\n"
               "ERROR: [VRFC 10-1280] procedural assignment to a non-register result is not permitted, "
               "left-hand side should be reg/integer/time/genvar [rtl.sv:4]\n"
               "ERROR: [VRFC 10-1280] procedural assignment to a non-register result is not permitted, "
               "left-hand side should be reg/integer/time/genvar [rtl.sv:5]\n"
               "ERROR: [VRFC 10-8530] module 'Main' is ignored due to previous errors [rtl.sv:1]")
        result = compiler_diagnostic(log, "", "compile")
        self.assertEqual(result["category"], "syntax")
        self.assertEqual(result["categories"], ["syntax", "procedural_target"])
        self.assertIn("原端口声明处", result["feedback"])
        self.assertIn("不能另加同名", result["feedback"])
        self.assertIn("数字字面量", result["feedback"])
        self.assertEqual(len(result["diagnostics"]), 3)
        self.assertNotIn("ignored due", result["feedback"])

    def test_primary_signature_repeat_is_unchanged_by_additional_root_family(self):
        first_log = "ERROR: [VRFC 10-4982] syntax error near '-' [rtl.sv:3]"
        first = compiler_diagnostic(first_log, "", "compile")
        mixed = compiler_diagnostic(first_log + "\nERROR: multiple drivers for 'state' [rtl.sv:9]",
                                    "", "compile", first)
        self.assertEqual(first["signature"], mixed["signature"])
        self.assertTrue(mixed["repeated"])
        self.assertEqual(mixed["categories"], ["syntax", "multiple_drivers"])

    def test_only_three_observed_families_and_feedback_remain_bounded(self):
        log = "\n".join((
            "ERROR: syntax error near '-' [rtl.sv:2]",
            "ERROR: left-hand side should be reg/integer/time/genvar [rtl.sv:3]",
            "ERROR: multiple drivers for 'state' [rtl.sv:4]",
            "ERROR: Unknown module type: Helper [rtl.sv:5]"))
        source = "\n".join("// " + "source"*200 for _ in range(20))
        result = compiler_diagnostic(log, source, "compile")
        self.assertEqual(result["categories"], ["syntax", "procedural_target", "multiple_drivers"])
        self.assertEqual(len(result["diagnostics"]), 4)
        self.assertLessEqual(len(result["feedback"]), MAX_FEEDBACK_CHARS)
        self.assertIn("syntax error near '-'", result["feedback"])

    def test_warnings_and_unknown_roots_do_not_invent_known_categories(self):
        result = compiler_diagnostic("WARNING: redeclaration of ANSI port 'x'\n"
            "WARNING: enum member 'N' has a value outside the representable range\n"
            "INFO: multiple drivers", "", "compile")
        self.assertEqual(result["diagnostics"], [])
        self.assertEqual(result["categories"], [])
        unknown = compiler_diagnostic("ERROR: unsupported attribute 'alpha' [rtl.sv:2]\n"
                                      "ERROR: unsupported attribute 'beta' [rtl.sv:3]", "", "compile")
        self.assertEqual(unknown["category"], "unknown")
        self.assertEqual(unknown["categories"], ["unknown"])
        self.assertNotIn("ANSI 输出端口", unknown["feedback"])

    def test_unknown_primary_keeps_identity_and_known_secondary_is_actionable(self):
        result = compiler_diagnostic("ERROR: unsupported attribute 'alpha' [rtl.sv:2]\n"
                                      "ERROR: multiple procedural drivers for 'state' [rtl.sv:3]",
                                      "", "elaborate")
        self.assertEqual(result["category"], "unknown")
        self.assertEqual(result["categories"], ["unknown", "multiple_drivers"])
        self.assertIn("同一时序进程", result["feedback"])


class AdditionalRootFamilyTests(unittest.TestCase):
    def test_ansi_port_redeclaration_is_recognized_without_changing_interface(self):
        log = "ERROR: [VRFC 10-9336] redeclaration of ANSI port 'result_word' is not allowed [rtl.sv:2]"
        first = compiler_diagnostic(log, "module Device;\nlogic result_word;\nendmodule", "compile")
        self.assertEqual(first["category"], "port_redeclaration")
        self.assertEqual(first["categories"], ["port_redeclaration"])
        self.assertIn("只在原端口列表声明一次", first["feedback"])
        self.assertIn("保留方向、位宽、signed", first["feedback"])
        renamed = compiler_diagnostic(log.replace("result_word", "delivery").replace(":2]", ":7]"),
                                      "", "compile", first)
        self.assertTrue(renamed["repeated"])
        self.assertFalse(compiler_diagnostic("ERROR: duplicate declaration of local variable 'data' [rtl.sv:2]",
                                             "", "compile")["category"] == "port_redeclaration")

    def test_enum_range_root_has_internal_width_and_state_preservation_guidance(self):
        log = ("ERROR: [VRFC 10-8928] enum member 'STEP_FINAL' has a value that is outside the "
               "representable range of the enum [rtl.sv:3]")
        result = compiler_diagnostic(log, "", "elaborate")
        self.assertEqual(result["category"], "enum_value_range")
        self.assertIn("扩大内部枚举位宽", result["feedback"])
        self.assertIn("不靠删除状态", result["feedback"])
        self.assertTrue(compiler_diagnostic(log.replace("STEP_FINAL", "STATE_LAST"), "", "elaborate", result)["repeated"])
        self.assertFalse(compiler_diagnostic(log, "", "compile", result)["repeated"])
        unrelated = compiler_diagnostic("ERROR: enum member 'STEP_FINAL' has an unsupported attribute [rtl.sv:3]",
                                        "", "elaborate")
        self.assertEqual(unrelated["category"], "unknown")


if __name__ == "__main__":
    unittest.main()
