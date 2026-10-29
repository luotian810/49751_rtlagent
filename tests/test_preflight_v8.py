"""DUT 预检必须展开真实顶层，但不能依赖测试台或运行 HDL。"""

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agent.verification import Toolchain


SOURCE = "module RenamedTop(input wire a, output wire y); assign y = ~a; endmodule"


class PreflightEvidenceTests(unittest.TestCase):
    def run_lint(self, backend, replies, *, elaborate=True, missing=(), clock=None):
        toolchain = Toolchain(backend)
        toolchain._tools[backend] = {name: None if name in missing else name
                                    for name in toolchain._tools[backend]}
        with tempfile.TemporaryDirectory() as directory, \
                patch.dict(os.environ, {"EDA_TMP": "", "AGENT_TMP": ""}), \
                patch("agent.verification._run_command", side_effect=replies) as run:
            root = Path(directory)
            # 外部遗留 TB 即使无效也不属于 DUT 预检，不能读取、编译或覆盖它。
            sentinel = root / "tb.sv"
            sentinel.write_text("this is an invalid testbench", encoding="utf-8")
            if clock is None:
                result = toolchain.lint(SOURCE, "RenamedTop", root, 10, elaborate=elaborate)
            else:
                with patch("agent.verification.time.monotonic", side_effect=clock):
                    result = toolchain.lint(SOURCE, "RenamedTop", root, 10, elaborate=elaborate)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "this is an invalid testbench")
            script = (root / "elaborate.do").read_text(encoding="utf-8") if (root / "elaborate.do").exists() else ""
            calls = run.call_args_list
            self.assertTrue(all(call.args[1] == root.resolve() for call in calls))
            self.assertFalse(any("tb.sv" in call.args[0] for call in calls))
            self.assertFalse((root / "watchdog.sv").exists())
            self.assertFalse((root / "run.tcl").exists())
        self.assertFalse(result.details["simulation_executed"])
        return result, calls, script

    def test_default_vivado_retains_compile_only_without_xelab(self):
        result, calls, _ = self.run_lint("vivado", [(0, "compiled", False)],
                                         elaborate=False, missing=("xelab", "xsim"))
        self.assertEqual([call.args[0] for call in calls], [["xvlog", "--sv", "rtl.sv"]])
        self.assertEqual(result.status, "passed")
        self.assertTrue(result.details["compile_passed"])
        self.assertIsNone(result.details["elaboration_passed"])

    def test_vivado_compiles_once_then_elaborates_in_same_workspace(self):
        result, calls, _ = self.run_lint("vivado", [(0, "compiled", False), (0, "elaborated", False)],
                                         missing=("xsim",))
        self.assertEqual([call.args[0][0] for call in calls], ["xvlog", "xelab"])
        self.assertEqual(calls[1].args[0], ["xelab", "RenamedTop", "--snapshot", "rtl_agent_preflight"])
        self.assertEqual(result.details["stage"], "elaborate")
        self.assertTrue(result.details["compile_passed"])
        self.assertTrue(result.details["elaboration_passed"])
        self.assertEqual(result.status, "passed")

    def test_compile_failure_stops_before_planned_elaboration(self):
        for reply in ((1, "rtl.sv:1: syntax error", False),
                      (0, "ERROR: [VRFC 10] invalid syntax [rtl.sv:1]", False)):
            with self.subTest(reply=reply):
                result, calls, _ = self.run_lint("vivado", [reply])
                self.assertEqual(result.status, "failed")
                self.assertEqual(len(calls), 1)
                self.assertEqual(len(result.details["commands"]), 2)
                self.assertFalse(result.details["compile_passed"])
                self.assertIsNone(result.details["elaboration_passed"])

    def test_elaboration_failure_preserves_compile_success(self):
        result, calls, _ = self.run_lint("vivado", [(0, "compiled", False),
                                                  (1, "ERROR: unresolved module [rtl.sv:1]", False)])
        self.assertEqual(result.status, "failed")
        self.assertEqual(len(calls), 2)
        self.assertTrue(result.details["compile_passed"])
        self.assertFalse(result.details["elaboration_passed"])
        self.assertEqual(result.details["failure_source"], "dut")

    def test_missing_elaborator_is_unavailable_without_claiming_compile(self):
        result, calls, _ = self.run_lint("vivado", [], missing=("xelab",))
        self.assertEqual(result.status, "unavailable")
        self.assertFalse(calls)
        self.assertIsNone(result.details["compile_passed"])
        self.assertIsNone(result.details["elaboration_passed"])

    def test_license_failure_is_not_elaboration_success(self):
        result, _, _ = self.run_lint("vivado", [(0, "compiled", False),
                                                (1, "ERROR: unable to checkout a license", False)])
        self.assertEqual(result.status, "unavailable")
        self.assertEqual(result.details["reason"], "license")
        self.assertTrue(result.details["compile_passed"])
        self.assertFalse(result.details["elaboration_passed"])

    def test_timeout_is_not_elaboration_success_even_with_zero_exit_code(self):
        result, _, _ = self.run_lint("vivado", [(0, "compiled", False), (0, "partial output", True)])
        self.assertEqual(result.status, "timeout")
        self.assertTrue(result.details["compile_passed"])
        self.assertFalse(result.details["elaboration_passed"])

    def test_generated_host_c_compilation_failure_is_environment_error(self):
        result, _, _ = self.run_lint("vivado", [(0, "compiled", False),
            (1, "ERROR: [XSIM 43-3409] Failed to compile generated C file xsim.dir/obj/xsim_1.c.", False)])
        self.assertEqual(result.status, "error")
        self.assertEqual(result.details["reason"], "elaborator_host_compilation")
        self.assertTrue(result.details["compile_passed"])
        self.assertFalse(result.details["elaboration_passed"])

    def test_shared_deadline_prevents_elaboration_after_compile_budget_exhaustion(self):
        result, calls, _ = self.run_lint("vivado", [(0, "compiled", False)], clock=[0, 0, 11, 11])
        self.assertEqual(result.status, "timeout")
        self.assertEqual(len(calls), 1)
        self.assertTrue(result.details["compile_passed"])
        self.assertIsNone(result.details["elaboration_passed"])

    def test_process_launch_error_is_not_execution_evidence(self):
        result, _, _ = self.run_lint("vivado", [OSError("cannot start compiler")])
        self.assertEqual(result.status, "error")
        self.assertIsNone(result.details["compile_passed"])
        self.assertIsNone(result.details["elaboration_passed"])

    def test_modelsim_loads_top_without_run_and_records_elaboration(self):
        result, calls, script = self.run_lint("modelsim", [(0, "", False)] * 3)
        self.assertEqual([call.args[0][0] for call in calls], ["vlib", "vlog", "vsim"])
        self.assertEqual([step["stage"] for step in result.details["steps"]],
                         ["setup", "compile", "elaborate"])
        self.assertIn("vsim work.RenamedTop\n", script)
        self.assertNotRegex(script, r"(?im)^\s*run\b")
        self.assertTrue(result.details["compile_passed"])
        self.assertTrue(result.details["elaboration_passed"])

    def test_modelsim_default_does_not_need_or_invoke_vsim(self):
        result, calls, script = self.run_lint("modelsim", [(0, "", False)] * 2,
                                             elaborate=False, missing=("vsim",))
        self.assertEqual([call.args[0][0] for call in calls], ["vlib", "vlog"])
        self.assertEqual(script, "")
        self.assertEqual(result.status, "passed")
        self.assertIsNone(result.details["elaboration_passed"])

    def test_modelsim_setup_failure_does_not_claim_compile(self):
        result, calls, _ = self.run_lint("modelsim", [(1, "ERROR: work library unavailable", False)])
        self.assertEqual(result.status, "failed")
        self.assertEqual(len(calls), 1)
        self.assertIsNone(result.details["compile_passed"])
        self.assertIsNone(result.details["elaboration_passed"])


class RealIcarusPreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.toolchain = Toolchain("iverilog")
        if not cls.toolchain._tools["iverilog"]["iverilog"]:
            raise unittest.SkipTest("Icarus compiler not installed")

    def lint(self, source, top="RenamedTop"):
        with tempfile.TemporaryDirectory() as directory, \
                patch.dict(os.environ, {"EDA_TMP": "", "AGENT_TMP": ""}):
            root = Path(directory)
            (root / "tb.sv").write_text("invalid unrelated testbench", encoding="utf-8")
            result = self.toolchain.lint(source, top, root, 20, elaborate=True)
            self.assertFalse((root / "runtime-only.txt").exists())
            self.assertEqual((root / "tb.sv").read_text(encoding="utf-8"), "invalid unrelated testbench")
            self.assertEqual(len(result.details["steps"]), 1)
            self.assertTrue(result.details["compile_includes_elaboration"])
            self.assertFalse(result.details["simulation_executed"])
        return result

    def test_hierarchy_and_parameter_width_compile_without_running_initial_block(self):
        source = """module Leaf #(parameter W=13)(input [W-1:0] a, output [W-1:0] y);
          assign y=~a;
        endmodule
        module RenamedTop(input [12:0] a, output [12:0] y);
          Leaf #(.W(13)) child(a,y);
          integer fd;
          initial begin
            fd = $fopen("runtime-only.txt", "w");
            $display("RTL_AGENT_PASS");
            $fclose(fd);
          end
        endmodule"""
        result = self.lint(source)
        self.assertEqual(result.status, "passed", result.log)
        self.assertTrue(result.details["compile_passed"])
        self.assertTrue(result.details["elaboration_passed"])
        self.assertNotIn("RTL_AGENT_PASS", result.log)

    def test_missing_child_module_is_rejected_by_combined_compile_elaboration(self):
        result = self.lint("module RenamedTop; MissingChild instance0(); endmodule")
        self.assertEqual(result.status, "failed", result.log)
        self.assertFalse(result.details["compile_passed"])
        self.assertFalse(result.details["elaboration_passed"])
        self.assertIn("MissingChild", result.log)

    def test_syntax_error_stops_without_simulation(self):
        result = self.lint("module RenamedTop(output y); assign y = ; endmodule")
        self.assertEqual(result.status, "failed", result.log)
        self.assertFalse(result.details["compile_passed"])
        self.assertFalse(result.details["elaboration_passed"])
        self.assertEqual(result.details["failure_source"], "dut")

    def test_unknown_top_is_rejected(self):
        result = self.lint(SOURCE, top="AbsentTop")
        self.assertEqual(result.status, "failed", result.log)
        self.assertFalse(result.details["elaboration_passed"])


if __name__ == "__main__":
    unittest.main()
