"""V9 diagnostic and duplicate-detection controls; no live model claims."""
import unittest

from agent.repair import candidate_fingerprint, compiler_diagnostic


class MultipleDriverTests(unittest.TestCase):
    def test_vivado_root_keeps_source_and_has_single_owner_guidance(self):
        source = "module Rename;\nreg [4:0] history;\nendmodule\n"
        log = ("ERROR: [VRFC 10-3818] variable 'history' is driven by invalid combination "
               "of procedural drivers [rtl.sv:2]")
        result = compiler_diagnostic(log, source, "elaborate")
        self.assertEqual(result["category"], "multiple_drivers")
        self.assertEqual(result["source_lines"], [2])
        self.assertIn("同一时序进程", result["feedback"])
        self.assertIn("并行读取旧值", result["feedback"])
        self.assertIn("改时钟沿", result["feedback"])

    def test_renamed_signal_and_location_do_not_hide_same_root(self):
        log = "ERROR: [VRFC 10-3818] variable 'alpha' is driven by invalid combination of procedural drivers [rtl.sv:2]"
        first = compiler_diagnostic(log, "", "elaborate")
        second = compiler_diagnostic(log.replace("alpha", "beta").replace(":2]", ":17]"), "", "elaborate", first)
        self.assertTrue(second["repeated"])
        self.assertFalse(compiler_diagnostic(log, "", "compile", first)["repeated"])

    def test_tool_wording_variants_are_recognized(self):
        for detail in ("multiple procedural drivers for 'state'", "multiple drivers on signal 'state'",
                       "multi-driven variable 'state'", "multiply-driven variable 'state'",
                       "variable 'state' is driven by multiple processes"):
            with self.subTest(detail=detail):
                result = compiler_diagnostic("ERROR: " + detail, "", "elaborate")
                self.assertEqual(result["category"], "multiple_drivers")

    def test_warning_or_unrelated_error_cannot_become_multiple_driver_failure(self):
        log = "WARNING: variable 'state' is multi-driven\nINFO: multiple drivers resolved"
        result = compiler_diagnostic(log, "", "elaborate")
        self.assertEqual(result["diagnostics"], [])
        self.assertIsNone(result["signature"])
        first = compiler_diagnostic("ERROR: unsupported attribute 'alpha' [rtl.sv:2]", "", "elaborate")
        second = compiler_diagnostic("ERROR: unsupported attribute 'beta' [rtl.sv:2]", "", "elaborate", first)
        self.assertEqual(second["category"], "unknown")
        self.assertFalse(second["repeated"])


class CandidateFingerprintTests(unittest.TestCase):
    def test_ordinary_comments_and_spacing_are_ignored(self):
        first = "module A(input a, output y); assign y = ~a; endmodule"
        formatted = "// explanation\nmodule A ( input a,output y );\nassign /* ordinary */ y=~a; endmodule\n"
        self.assertEqual(candidate_fingerprint(first), candidate_fingerprint(formatted))

    def test_operator_boundaries_cannot_be_joined_by_whitespace_removal(self):
        for left, right in (("a + +b", "a++b"), ("a < = b", "a<=b"), ("a & &b", "a&&b"),
                            ("a > >> b", "a>>>b"), ("a - > b", "a->b"), ("a ! == b", "a!==b")):
            with self.subTest(left=left):
                self.assertNotEqual(candidate_fingerprint(left), candidate_fingerprint(right))

    def test_width_sign_value_identifier_and_literal_are_significant(self):
        base = "assign result = 8'sh7f + data;"
        for changed in ("assign result = 9'sh7f + data;", "assign result = 8'h7f + data;",
                        "assign result = 8'sh7e + data;", "assign result = -8'sh7f + data;",
                        "assign result = 8'sh7f + other;", "assign result = 8'sh7f - data;"):
            with self.subTest(changed=changed):
                self.assertNotEqual(candidate_fingerprint(base), candidate_fingerprint(changed))
        self.assertNotEqual(candidate_fingerprint("a = '0;"), candidate_fingerprint("a = 0;"))
        self.assertNotEqual(candidate_fingerprint("a = 1e-2;"), candidate_fingerprint("a = 1e+2;"))
        self.assertNotEqual(candidate_fingerprint("a = 1ns;"), candidate_fingerprint("a = 1ps;"))

    def test_complex_forms_preserve_exact_source(self):
        for source in ('`define V 1\nmodule A; endmodule', '(* keep = 1 *) wire a;',
                       'wire \\escaped.name ;', 'parameter MESSAGE = "a // b";',
                       '// synthesis translate_off\nwire a;', 'wire a; /* unterminated'):
            with self.subTest(source=source):
                self.assertEqual(candidate_fingerprint(source), ("exact", source))
                self.assertNotEqual(candidate_fingerprint(source), candidate_fingerprint(source + " "))

    def test_comments_cannot_merge_identifiers_or_numeric_tokens(self):
        self.assertNotEqual(candidate_fingerprint("wire first/**/second;"), candidate_fingerprint("wire firstsecond;"))
        self.assertNotEqual(candidate_fingerprint("a=1/**/2;"), candidate_fingerprint("a=12;"))
        self.assertNotEqual(candidate_fingerprint("a=8' hff;"), candidate_fingerprint("a=8'hff;"))


if __name__ == "__main__":
    unittest.main()
