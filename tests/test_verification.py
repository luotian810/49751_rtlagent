"""验证状态判断的边界，并在真实仿真器可用时执行小型集成测试。"""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from agent.verification import (Toolchain, _command_environment, _fatal_message, _has_pass_marker,
                                _run_command, compile_error_source, testbench_tool_error)


@unittest.skipUnless(os.name == "nt", "Vivado 的主机名兼容设置仅适用于 Windows")
class WindowsVivadoEnvironmentTests(unittest.TestCase):
    def test_non_ascii_hostname_changes_only_child_environment(self):
        with patch.dict(os.environ, {"PATH": "existing-path", "KEEP": "unchanged"}, clear=True), \
                patch("agent.verification.socket.gethostname", return_value="测试电脑"):
            before = dict(os.environ)
            for tool in ("vivado.bat", "xvlog.bat", "xelab.bat", "xsim.bat"):
                with self.subTest(tool=tool):
                    child = _command_environment([tool])
                    self.assertEqual(child["_CLUSTER_NETWORK_NAME_"], "RTLLOCAL")
                    self.assertEqual(child["KEEP"], "unchanged")
            self.assertEqual(dict(os.environ), before)

    def test_ascii_hostname_needs_no_override(self):
        with patch.dict(os.environ, {}, clear=True), \
                patch("agent.verification.socket.gethostname", return_value="RTL-PC"):
            self.assertNotIn("_CLUSTER_NETWORK_NAME_", _command_environment(["vivado.bat"]))

    def test_existing_hostname_override_is_preserved(self):
        with patch.dict(os.environ, {"_CLUSTER_NETWORK_NAME_": "EXISTING-NODE"}, clear=True), \
                patch("agent.verification.socket.gethostname", return_value="测试电脑"):
            child = _command_environment(["vivado.bat"])
            self.assertEqual(child["_CLUSTER_NETWORK_NAME_"], "EXISTING-NODE")

    def test_other_tools_keep_their_hostname_behavior(self):
        with patch.dict(os.environ, {}, clear=True), \
                patch("agent.verification.socket.gethostname", return_value="测试电脑"):
            for tool in ("iverilog.exe", "vvp.exe", "vsim.exe", "python.exe"):
                with self.subTest(tool=tool):
                    self.assertNotIn("_CLUSTER_NETWORK_NAME_", _command_environment([tool]))


class VerificationResultTests(unittest.TestCase):
    def test_compile_error_ownership_and_vivado_elaboration_locations(self):
        constant = "ERROR: [VRFC 10-2951] 'k' is not a constant [/var/tmp/run/tb.sv:29]"
        elaboration = 'ERROR: [XSIM 43-3122] "/var/tmp/run/tb.sv" Line 111. random system task is not supported.'
        for log in (constant, elaboration):
            with self.subTest(log=log):
                self.assertEqual(compile_error_source(log), "testbench")
                self.assertTrue(testbench_tool_error(log))
                self.assertEqual(compile_error_source(log.replace("tb.sv", "rtl.sv")), "dut")
                self.assertFalse(testbench_tool_error(log.replace("tb.sv", "rtl.sv")))
        mixed = constant + "\nrtl.sv:4: syntax error"
        self.assertEqual(compile_error_source(mixed), "mixed")
        self.assertFalse(testbench_tool_error(mixed))
        self.assertEqual(compile_error_source("ERROR: elaboration failed"), "unknown")
        self.assertFalse(testbench_tool_error("tb.sv:4: error: port q is not a port of dut"))

    def test_pass_marker_is_an_exact_output_line(self):
        self.assertTrue(_has_pass_marker("# RTL_AGENT_PASS\n"))
        self.assertFalse(_has_pass_marker('$display("RTL_AGENT_PASS");'))
        self.assertFalse(_has_pass_marker("prefix RTL_AGENT_PASS suffix"))

    def test_error_detection(self):
        for log in ("RTL_AGENT_FAIL", "# RTL_AGENT_FAIL: wrong value", "# ** Error: syntax",
                    "FATAL: mismatch", "# ** Fatal: (vsim-3807) invalid simulation",
                    "ERROR: [XSIM 1] broken", "ERROR: [Common 17-69] Command failed"):
            with self.subTest(log=log):
                self.assertTrue(_fatal_message(log), log)
        self.assertFalse(_fatal_message("Errors: 0, Warnings: 0\n# RTL_AGENT_PASS\n"))

    def test_tcl_source_echo_is_not_a_runtime_failure(self):
        # Vivado 会回显 Tcl 脚本；字符串中的诊断词不代表对应分支实际执行。
        for log in (
            '# puts "ERROR: diagnostic example"',
            '# if {[catch {run 1001 ns} message]} { error $message }',
            '# send_msg_id "Vivado_Tcl 4-1" "ERROR" "example"',
            '# puts "FATAL: diagnostic example"',
            '# puts "RTL_AGENT_FAIL: diagnostic example"',
            '$display("RTL_AGENT_FAIL: mismatches");',
        ):
            with self.subTest(log=log):
                self.assertFalse(_fatal_message(log), log)

    def test_host_timeout_terminates_process(self):
        with tempfile.TemporaryDirectory() as temporary:
            _, _, timed_out = _run_command([sys.executable, "-c", "import time; time.sleep(30)"], Path(temporary), 0.1)
        self.assertTrue(timed_out)

    def test_missing_backend_is_unavailable(self):
        toolchain = Toolchain("modelsim")
        toolchain._tools["modelsim"] = dict(vlib=None, vlog=None, vsim=None)
        with tempfile.TemporaryDirectory() as temporary:
            result = toolchain.simulate("", "", "TopModule", Path(temporary), 1)
        self.assertEqual(result.status, "unavailable")

    def test_invalid_top_is_rejected(self):
        result = Toolchain().lint("", "foo;quit", Path("unused"), 1)
        self.assertEqual(result.status, "error")


class ToolStageTests(unittest.TestCase):
    """工具阶段由实际命令决定，编译错误不能冒充运行断言。"""

    def execute(self, commands, replies, *, simulation=True):
        with tempfile.TemporaryDirectory() as temporary, \
                patch("agent.verification._run_command", side_effect=replies) as run:
            result = Toolchain("vivado")._execute(commands, Path(temporary), 10, simulation=simulation)
        return result, run.call_count

    def test_xvlog_failure_never_claims_simulation(self):
        result, count = self.execute([["xvlog", "--sv", "rtl.sv"], ["xelab", "tb"], ["xsim", "snapshot"]],
                                     [(1, 'ERROR: syntax error near RTL_AGENT_FAIL [rtl.sv:3]', False)])
        self.assertEqual(count, 1)
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.details["stage"], "compile")
        self.assertEqual(result.details["failure_source"], "dut")
        self.assertFalse(result.details["simulation_executed"])
        self.assertFalse(result.details["assertion_failed"])

    def test_xelab_failure_preserves_order_and_stops_before_runtime(self):
        result, count = self.execute([["xvlog", "--sv", "rtl.sv", "tb.sv"], ["xelab", "tb"], ["xsim", "snapshot"]],
                                     [(0, "compiled", False),
                                      (1, 'ERROR: [XSIM 43-3122] "tb.sv" Line 111. random system task is not supported.', False)])
        self.assertEqual(count, 2)
        self.assertEqual(result.details["stage"], "elaborate")
        self.assertEqual(result.details["failure_source"], "testbench")
        self.assertEqual([step["stage"] for step in result.details["steps"]], ["compile", "elaborate"])
        self.assertFalse(result.details["simulation_executed"])
        self.assertFalse(result.details["assertion_failed"])

    def test_runtime_failure_is_bound_to_runtime_output(self):
        result, count = self.execute([["xvlog", "rtl.sv"], ["xelab", "tb"], ["xsim", "snapshot"]],
                                     [(0, "compiled", False), (0, "elaborated", False),
                                      (0, "RTL_AGENT_FAIL sample=1 y=0 expected=1", False)])
        self.assertEqual(count, 3)
        self.assertEqual(result.details["stage"], "simulate")
        self.assertTrue(result.details["simulation_executed"])
        self.assertTrue(result.details["assertion_failed"])
        self.assertEqual(result.status, "failed")

    def test_compile_marker_does_not_prove_runtime_pass(self):
        result, _ = self.execute([["iverilog", "rtl.sv"], ["vvp", "sim.out"]],
                                 [(0, "RTL_AGENT_PASS", False), (0, "simulation ended", False)])
        self.assertTrue(result.details["simulation_executed"])
        self.assertFalse(result.details["assertion_failed"])
        self.assertFalse(result.details["pass_marker_seen"])
        self.assertEqual(result.status, "failed")

    def test_setup_and_synthesis_have_distinct_stages(self):
        result, _ = self.execute([["vlib", "work"], ["vlog", "rtl.sv"], ["vsim", "tb"]],
                                 [(0, "", False), (0, "", False), (0, "# RTL_AGENT_PASS", False)])
        self.assertEqual([step["stage"] for step in result.details["steps"]], ["setup", "compile", "simulate"])
        synth, _ = self.execute([["vivado.bat", "-mode", "batch"]], [(0, "synthesized", False)], simulation=False)
        self.assertEqual(synth.details["stage"], "synthesis")
        self.assertFalse(synth.details["simulation_executed"])


class RealSimulatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.toolchain = Toolchain(os.environ.get("RTL_AGENT_TEST_BACKEND", "auto"))
        if not cls.toolchain.describe()["available"]:
            raise unittest.SkipTest("未安装 HDL 仿真器，真实仿真测试跳过")
        # Windows Vivado 冷启动较慢；预算覆盖编译、详细描述和仿真三个步骤。
        cls.timeout_s = 120 if cls.toolchain.backend == "vivado" else 45
        # 缺许可证与断言失败是两回事：先跑独立冒烟测试，只有已识别的环境问题才跳过。
        with tempfile.TemporaryDirectory() as temporary:
            probe = cls.toolchain.simulate(
                "module TopModule; endmodule",
                'module tb; TopModule dut(); initial begin $display("RTL_AGENT_PASS"); $finish; end endmodule',
                "TopModule", Path(temporary), cls.timeout_s)
        if probe.status == "unavailable":
            raise unittest.SkipTest("仿真工具不可用：" + probe.details.get("reason", probe.log))
        if probe.status != "passed":
            raise AssertionError("真实仿真器冒烟检查失败：\n" + probe.log)

    def simulate(self, body):
        source = "module TopModule(input wire a, output wire y); assign y = ~a; endmodule\n"
        tb = '`timescale 1ns/1ps\nmodule tb; reg a; wire y; TopModule dut(a,y); initial begin\n' + body + "\nend endmodule\n"
        with tempfile.TemporaryDirectory() as temporary:
            return self.toolchain.simulate(source, tb, "TopModule", Path(temporary), self.timeout_s)

    def test_correct_design_passes(self):
        result = self.simulate('a=0; #1; if(y!==1) begin $display("RTL_AGENT_FAIL"); $finish; end '
                               'a=1; #1; if(y!==0) begin $display("RTL_AGENT_FAIL"); $finish; end '
                               '$display("RTL_AGENT_PASS"); $finish;')
        self.assertEqual(result.status, "passed", result.log)
        self.assertEqual(result.details["stage"], "simulate")
        self.assertTrue(result.details["simulation_executed"])
        self.assertFalse(result.details["assertion_failed"])

    def test_invalid_hdl_stops_before_runtime(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = self.toolchain.simulate(
                "module TopModule; assign broken = ; endmodule",
                'module tb; TopModule dut(); initial begin $display("RTL_AGENT_PASS"); $finish; end endmodule',
                "TopModule", Path(temporary), self.timeout_s)
        self.assertEqual(result.status, "failed", result.log)
        self.assertEqual(result.details["stage"], "compile")
        self.assertFalse(result.details["simulation_executed"])
        self.assertFalse(result.details["assertion_failed"])

    def test_missing_success_marker_fails(self):
        result = self.simulate("a=0; #1; $finish;")
        self.assertEqual(result.status, "failed", result.log)

    def test_failure_wins_even_after_pass_marker(self):
        result = self.simulate('$display("RTL_AGENT_PASS"); $display("RTL_AGENT_FAIL: deliberate mismatch"); $finish;')
        self.assertEqual(result.status, "failed", result.log)
        self.assertTrue(result.details["assertion_failed"])

    def test_simulated_time_watchdog_fails(self):
        result = self.simulate("a=0; forever #1 a=~a;")
        self.assertEqual(result.status, "failed", result.log)
        self.assertIn("simulation exceeded", result.log)
        self.assertTrue(result.details["simulation_executed"])
        self.assertTrue(result.details["simulation_limit_reached"])
        self.assertFalse(result.details["assertion_failed"])


if __name__ == "__main__":
    unittest.main()
