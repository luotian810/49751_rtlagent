"""调用真实 HDL 工具，并把“通过、失败、缺少工具”明确区分。

ModelSim / Icarus 用于本地开发；比赛综合结果须使用 Vivado 后端。
每次仿真同时限制主机运行时间和 HDL 模拟时间，避免错误设计无限运行。
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field


PASS_MARKER = "RTL_AGENT_PASS"
FAIL_MARKER = "RTL_AGENT_FAIL"
SIMULATION_LIMIT_NS = 1_000_000
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")
# 使用独立顶层模块，既不修改 DUT，也不依赖模型生成的 testbench 有超时保护。
_WATCHDOG = f"""`timescale 1ns/1ps
module __rtl_agent_watchdog;
  initial begin
    #{SIMULATION_LIMIT_NS};
    $display("{FAIL_MARKER}: simulation exceeded {SIMULATION_LIMIT_NS} ns");
    $finish;
  end
endmodule
"""


@dataclass
class CheckResult:
    """一个检查步骤的原始证据；unavailable 绝不等同于 passed。"""

    status: str
    backend: str
    log: str
    elapsed_s: float
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _tool_path(name: str, directories: list[Path]) -> str | None:
    """优先显式安装目录，其次 PATH；只返回实际存在的工具。"""
    suffixes = (".exe", ".bat", ".cmd", "") if os.name == "nt" else ("",)
    for directory in directories:
        for suffix in suffixes:
            candidate = directory / (name + suffix)
            if candidate.is_file():
                return str(candidate.resolve())
    return shutil.which(name)


def _fatal_message(log: str) -> bool:
    """匹配真正的错误，避免把编译器的 `Errors: 0` 汇总误判为失败。"""
    for line in log.splitlines():
        # ModelSim 会给 testbench 的输出加上 '# '。
        clean = re.sub(r"^\s*#\s?", "", line).strip()
        # Vivado 会回显 Tcl 源码（如 '# puts "ERROR ..."'），不能当工具诊断。
        if clean.startswith(FAIL_MARKER):
            return True
        if re.match(r"(?:\*\*\s*)?(?:ERROR|FATAL|Failure)\s*[:\[]", clean, re.I):
            return True
        if re.search(r"\.(?:sv|v)(?::\d+|\(\d+\)).*?\berror\b", clean, re.I):
            return True
    return False


def _has_pass_marker(log: str) -> bool:
    # 要求独立输出行，不能因为编译器回显 $display 源代码而误报通过。
    return any(re.sub(r"^\s*#\s?", "", line).strip() == PASS_MARKER
               for line in log.splitlines())


def _stop_process_tree(process: subprocess.Popen) -> None:
    """超时时结束子进程树，避免 vsim/xsim 后台进程继续占用许可证。"""
    if os.name == "nt":
        try:
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=10, check=False)
        finally:
            if process.poll() is None:
                process.kill()
    elif sys.platform.startswith("linux"):
        # Linux EDA 继承单题进程组，外层服务才能完整回收它。
        # 内部工具超时只结束自己的子树；不能 killpg，否则会结束智能体本身。
        pending, stopped = [process.pid], []
        while pending:
            pid = pending.pop()
            if pid in stopped:
                continue
            try:
                os.kill(pid, signal.SIGSTOP)
                stopped.append(pid)
                for children in Path(f"/proc/{pid}/task").glob("*/children"):
                    try:
                        pending.extend(int(value) for value in children.read_text().split())
                    except (OSError, ValueError):
                        pass
            except ProcessLookupError:
                pass
        for pid in reversed(stopped):
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if process.poll() is None:
        process.kill()


def _command_environment(command: list[str]) -> dict[str, str]:
    """仅配置工具子进程，保留父进程的环境和系统电脑名。"""
    environment = dict(os.environ)
    # 可搬移 Windows 工具的内部 ivl.exe 位于 lib/，其 DLL 位于 bin/。
    # 仅为这个子进程补 PATH，不更改系统或用户环境。
    environment["PATH"] = str(Path(command[0]).parent) + os.pathsep + environment.get("PATH", "")
    if os.name == "nt" and Path(command[0]).stem.lower() in ("vivado", "xvlog", "xelab", "xsim"):
        # Vivado 2025.2 将 UTF-8 临时路径传给按 ACP 解码的 fopen。
        # 非 ASCII 电脑名会使 files.rtd 打开失败，并触发内部异常。
        # 此 Winsock 进程变量只让 gethostname 返回 ASCII，不改注册表或许可证。
        if not socket.gethostname().isascii() and not environment.get("_CLUSTER_NETWORK_NAME_"):
            environment["_CLUSTER_NETWORK_NAME_"] = "RTLLOCAL"
    return environment


def _run_command(command: list[str], cwd: Path, timeout_s: float) -> tuple[int, str, bool]:
    """返回 (退出码, 输出, 是否超时)，始终保存工具的真实 stdout/stderr。"""
    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
    environment = _command_environment(command)
    if os.name == "nt":
        import ctypes
        ctypes.windll.kernel32.SetErrorMode(0x0001 | 0x0002 | 0x8000)
    # Windows 的 Vivado 工具通常通过 .bat 分发；cmd 的参数由 list2cmdline 引用。
    if os.name == "nt" and Path(command[0]).suffix.lower() in (".bat", ".cmd"):
        command = ('"' + os.environ.get("COMSPEC", "cmd.exe") + '" /d /s /c ""'
                   + command[0] + '" ' + subprocess.list2cmdline(command[1:]) + '"')
    process = subprocess.Popen(command, cwd=cwd, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True,
                               encoding="utf-8", errors="replace",
                               env=environment,
                               creationflags=creationflags,
                               start_new_session=(os.name != "nt" and not sys.platform.startswith("linux")))
    try:
        output, _ = process.communicate(timeout=max(timeout_s, 0.01))
        return process.returncode, output, False
    except subprocess.TimeoutExpired:
        _stop_process_tree(process)
        output, _ = process.communicate(timeout=10)
        return process.returncode, output, True
    finally:
        # 服务取消任务时主程序的 SIGTERM 处理器会抛出 SystemExit；仍需清理 EDA 子树。
        if process.poll() is None:
            _stop_process_tree(process)
            process.wait(timeout=10)


class Toolchain:
    """轻量适配器：Vivado、ModelSim 或 Icarus；不自动安装工具。"""

    def __init__(self, backend: str = "auto"):
        if backend not in ("auto", "vivado", "modelsim", "iverilog", "icarus", "none"):
            raise ValueError("backend 必须为 auto / vivado / modelsim / iverilog / none")
        vivado_dirs = []
        if os.environ.get("XILINX_VIVADO"):
            vivado_dirs.append(Path(os.environ["XILINX_VIVADO"]) / "bin")
        modelsim_dirs = []
        if os.environ.get("MODELSIM_BIN"):
            modelsim_dirs.append(Path(os.environ["MODELSIM_BIN"]))
        if os.name == "nt":
            modelsim_dirs.append(Path(r"D:\modelsim_10.1c\win64"))
        iverilog_dirs = []
        if os.environ.get("IVERILOG_BIN"):
            iverilog_dirs.append(Path(os.environ["IVERILOG_BIN"]))
        iverilog_dirs.append(Path(__file__).resolve().parents[1] / ".tools" / "iverilog" / "ucrt64" / "bin")
        iverilog_dirs.append(Path(__file__).resolve().parents[1] / ".tools" / "iverilog" / "bin")
        self._tools = {
            "vivado": {name: _tool_path(name, vivado_dirs) for name in ("vivado", "xvlog", "xelab", "xsim")},
            "modelsim": {name: _tool_path(name, modelsim_dirs) for name in ("vlib", "vlog", "vsim")},
            "iverilog": {name: _tool_path(name, iverilog_dirs) for name in ("iverilog", "vvp")},
        }
        self.requested_backend = backend
        backend = "iverilog" if backend == "icarus" else backend
        if backend == "auto":
            backend = next((name for name in ("vivado", "iverilog", "modelsim")
                            if all(self._tools[name].values())), "unavailable")
        self.backend = "unavailable" if backend == "none" else backend

    def describe(self) -> dict:
        return {"requested_backend": self.requested_backend, "backend": self.backend,
                "available": self.backend != "unavailable" and all(self._tools[self.backend].values()),
                "tools": self._tools, "simulation_limit_ns": SIMULATION_LIMIT_NS,
                "synthesis_available": bool(self._tools["vivado"]["vivado"]),
                "license_checked": False,
                "note": "available 仅表示找到工具文件；许可证须由真实运行检查。ModelSim / Icarus 为开发验证。"}

    def _execute(self, steps: list[list[str]], work_dir: Path, timeout_s: float,
                 simulation: bool = False, backend: str | None = None) -> CheckResult:
        started = time.monotonic()
        selected = backend or self.backend
        logs = []
        details = {"work_dir": str(work_dir), "commands": steps}
        status = "passed"
        try:
            for command in steps:
                remaining = timeout_s - (time.monotonic() - started)
                if remaining <= 0:
                    status = "timeout"
                    logs.append("主机运行时间达到限制。")
                    break
                returncode, output, timed_out = _run_command(command, work_dir, remaining)
                logs.append("$ " + subprocess.list2cmdline(command) + "\n" + output)
                details["returncode"] = returncode
                if timed_out:
                    status = "timeout"
                    logs.append("主机运行时间达到限制，已终止工具进程树。")
                    break
                if returncode < 0 or returncode >= 0x80000000:
                    status = "error"
                    logs.append(f"工具进程异常退出 ({returncode})，请检查运行库/安装，不能按 RTL 功能错误处理。")
                    break
                if re.search(r"unable to checkout a license|invalid license environment|"
                             r"failed to (?:obtain|checkout) a license|license checkout failed|"
                             r"a valid license was not found|could not obtain the necessary license|"
                             r"unable to get licensing information|license checkout failure", output, re.I):
                    status = "unavailable"
                    details["reason"] = "license"
                    break
                if returncode != 0 or _fatal_message(output):
                    status = "failed"
                    break
            if simulation and status == "passed" and not _has_pass_marker(output):
                status = "failed"
                logs.append("未检测到独立的 RTL_AGENT_PASS 输出行，不能判定仿真通过。")
        except (OSError, subprocess.SubprocessError) as exc:
            status = "error"
            logs.append(f"无法完成工具调用：{exc}")
        log = "\n\n".join(logs)
        if simulation:
            details["pass_marker_seen"] = _has_pass_marker(log)
            details["simulation_limit_ns"] = SIMULATION_LIMIT_NS
            waveform = work_dir / "wave.vcd"
            if waveform.is_file():
                details["waveform"] = str(waveform)
            details["verification_scope"] = "generated_testbench_only"
        return CheckResult(status, selected, log, round(time.monotonic() - started, 3), details)

    def _prepare(self, source: str, top: str, work_dir: Path, timeout_s: float,
                 required: tuple[str, ...]) -> Path | CheckResult:
        if not _IDENTIFIER.fullmatch(top):
            return CheckResult("error", self.backend, "top 必须是普通 Verilog 模块标识符。", 0)
        if timeout_s <= 0:
            return CheckResult("error", self.backend, "timeout_s 必须大于 0。", 0)
        toolset = self._tools.get(self.backend, {})
        missing = [name for name in required if not toolset.get(name)]
        if self.backend == "unavailable" or missing:
            return CheckResult("unavailable", self.backend,
                               "未发现所需工具：" + ", ".join(missing or ["HDL simulator"]), 0)
        work_dir = Path(work_dir).resolve()
        work_dir.mkdir(parents=True, exist_ok=True)
        (work_dir / "rtl.sv").write_text(source, encoding="utf-8")
        return work_dir

    def _in_workspace(self, check, *arguments, work_dir: Path, timeout_s: float) -> CheckResult:
        """云端海量中间文件留在本地盘，输出目录只保留可检查的结果。

        未设置临时盘变量时延续本机开发行为，保留完整 Windows 工具目录。
        每次调用独立建目录，成功、失败和取消均由 TemporaryDirectory 清理。
        """
        scratch = os.environ.get("EDA_TMP") or os.environ.get("AGENT_TMP")
        if not scratch:
            return check(*arguments, work_dir, timeout_s)
        destination = Path(work_dir).resolve()
        destination.mkdir(parents=True, exist_ok=True)
        Path(scratch).mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="rtl-eda-", dir=scratch) as directory:
            temporary = Path(directory)
            try:
                result = check(*arguments, temporary, timeout_s)
            finally:
                # 不拷贝 xsim.dir/.Xil 等中间数据库；波形和检查点保留供人工复核。
                evidence = {".v", ".sv", ".tcl", ".do", ".log", ".rpt", ".vcd", ".dcp"}
                for item in temporary.iterdir():
                    if item.is_file() and not item.is_symlink() and item.suffix.lower() in evidence:
                        shutil.copy2(item, destination / item.name)
            result.details["work_dir"] = str(destination)
            result.details["scratch_root"] = str(Path(scratch).resolve())
            result.details["temporary_workspace_cleaned"] = True
            if "waveform" in result.details:
                result.details["waveform"] = str(destination / "wave.vcd")
            return result

    def lint(self, source: str, top: str, work_dir: Path, timeout_s: float = 60) -> CheckResult:
        """真实编译/语法检查；不声称等价于完整功能验证。"""
        return self._in_workspace(self._lint, source, top, work_dir=work_dir, timeout_s=timeout_s)

    def _lint(self, source: str, top: str, work_dir: Path, timeout_s: float) -> CheckResult:
        requirements = {"vivado": ("xvlog",), "modelsim": ("vlib", "vlog"),
                        "iverilog": ("iverilog",)}
        prepared = self._prepare(source, top, work_dir, timeout_s, requirements.get(self.backend, ()))
        if isinstance(prepared, CheckResult):
            return prepared
        tools = self._tools[self.backend]
        if self.backend == "vivado":
            steps = [[tools["xvlog"], "--sv", "rtl.sv"]]
        elif self.backend == "modelsim":
            steps = [[tools["vlib"], "work"], [tools["vlog"], "-sv", "-work", "work", "rtl.sv"]]
        else:
            steps = [[tools["iverilog"], "-g2012", "-s", top, "-o", "lint.out", "rtl.sv"]]
        return self._execute(steps, prepared, timeout_s)

    def simulate(self, source: str, testbench: str, top: str, work_dir: Path,
                 timeout_s: float = 60) -> CheckResult:
        """testbench 顶层为 tb；完成全部断言后须输出 RTL_AGENT_PASS 并 $finish。"""
        return self._in_workspace(self._simulate, source, testbench, top,
                                  work_dir=work_dir, timeout_s=timeout_s)

    def _simulate(self, source: str, testbench: str, top: str, work_dir: Path,
                  timeout_s: float) -> CheckResult:
        requirements = {"vivado": ("xvlog", "xelab", "xsim"),
                        "modelsim": ("vlib", "vlog", "vsim"), "iverilog": ("iverilog", "vvp")}
        prepared = self._prepare(source, top, work_dir, timeout_s, requirements.get(self.backend, ()))
        if isinstance(prepared, CheckResult):
            return prepared
        (prepared / "tb.sv").write_text(testbench, encoding="utf-8")
        (prepared / "watchdog.sv").write_text(_WATCHDOG, encoding="utf-8")
        tools = self._tools[self.backend]
        if self.backend == "modelsim":
            (prepared / "run.do").write_text(
                "onerror {quit -force -code 1}\n"
                "onfinish stop\n"
                "vcd file wave.vcd\nvcd add -r /tb/*\n"
                f"run {SIMULATION_LIMIT_NS + 1} ns\nquit -force -code 0\n", encoding="utf-8")
            steps = [[tools["vlib"], "work"],
                     [tools["vlog"], "-sv", "-work", "work", "rtl.sv", "tb.sv", "watchdog.sv"],
                     [tools["vsim"], "-c", "-voptargs=+acc", "work.tb", "work.__rtl_agent_watchdog", "-do", "run.do"]]
        elif self.backend == "vivado":
            (prepared / "run.tcl").write_text(
                "open_vcd wave.vcd\nset signals [get_objects -quiet -r *]\n"
                "if {[llength $signals] > 0} {log_vcd $signals}\n"
                f"run {SIMULATION_LIMIT_NS + 1} ns\nclose_vcd\nquit\n", encoding="utf-8")
            steps = [[tools["xvlog"], "--sv", "rtl.sv", "tb.sv", "watchdog.sv"],
                     [tools["xelab"], "tb", "__rtl_agent_watchdog", "-timescale", "1ps/1ps", "--debug", "typical", "--snapshot", "rtl_agent_snapshot"],
                     [tools["xsim"], "rtl_agent_snapshot", "--tclbatch", "run.tcl"]]
        else:
            # 独立顶层负责导出波形，保持 DUT 与测试期望值不变。
            (prepared / "waveform.sv").write_text(
                'module __rtl_agent_waveform; initial begin $dumpfile("wave.vcd"); $dumpvars(0, tb); end endmodule\n',
                encoding="utf-8")
            steps = [[tools["iverilog"], "-g2012", "-s", "tb", "-s", "__rtl_agent_watchdog",
                      "-s", "__rtl_agent_waveform", "-o", "sim.out", "rtl.sv", "tb.sv", "watchdog.sv", "waveform.sv"], [tools["vvp"], "sim.out"]]
        return self._execute(steps, prepared, timeout_s, simulation=True)

    def synth(self, source: str, top: str, work_dir: Path, timeout_s: float = 120) -> CheckResult:
        """用 Vivado 对 RTL 执行 synth_design，并保存资源报告。

        默认器件为比赛 ZU3EG，可用 RTL_PART 覆盖。
        不做布局布线，因此不据此声称通过时序或获得官方分数。
        """
        return self._in_workspace(self._synth, source, top, work_dir=work_dir, timeout_s=timeout_s)

    def _synth(self, source: str, top: str, work_dir: Path, timeout_s: float) -> CheckResult:
        if self.backend != "vivado":
            return CheckResult("unavailable", self.backend,
                               "综合检查需要 Vivado 后端；当前后端仅提供开发仿真。", 0)
        prepared = self._prepare(source, top, work_dir, timeout_s, ("vivado",))
        if isinstance(prepared, CheckResult):
            return prepared
        part = os.environ.get("RTL_PART", "xczu3eg-sbva484-1-e")
        if not re.fullmatch(r"[A-Za-z0-9_-]+", part):
            return CheckResult("error", "vivado", "RTL_PART 包含非法器件名字符。", 0)
        (prepared / "synth.tcl").write_text(
            "read_verilog -sv rtl.sv\n"
            f"synth_design -top {top} -part {part} -mode out_of_context\n"
            "if {[llength [get_ports -quiet clk]] > 0} {create_clock -period 5.000 [get_ports clk]}\n"
            "report_utilization -file utilization.rpt\n"
            "report_timing_summary -delay_type min_max -report_unconstrained -file timing_summary.rpt\n"
            "report_timing -max_paths 10 -file timing_paths.rpt\n"
            "write_checkpoint -force synthesized.dcp\nputs RTL_AGENT_SYNTH_DONE\n", encoding="utf-8")
        result = self._execute([[self._tools["vivado"]["vivado"], "-mode", "batch", "-nojournal",
                                 "-source", "synth.tcl"]], prepared, timeout_s)
        result.details.update({"part": part, "scope": "synthesis_only_no_implementation"})
        if result.status == "passed" and (not any(line.strip() == "RTL_AGENT_SYNTH_DONE" for line in result.log.splitlines()) or not (prepared / "synthesized.dcp").is_file()):
            result.status = "failed"
            result.log += "\n综合没有完成标记及检查点，不能宣称成功。"
        return result
