"""在 Windows/Linux 上调用原样保留的赛事方公开样例判定器。

分级逻辑来自 vendor/；此文件只适配工具启动、任务路径和结果归档。
公开样例 + 本机 Vivado 的结果属于本地自测，不能写作比赛官方成绩。
"""

from __future__ import annotations

import argparse
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import re
import sys
import tempfile
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent.verification import Toolchain, _run_command

VENDOR = ROOT / "vendor" / "rtlagent2026_selftest"
DEFAULT_TASKS = VENDOR / "tasks"
ANNOUNCED_VERSION = "2026.1"
GENERATED_SOLUTIONS = {
    "ex01_popcount8": ROOT / "runs/deepseek_final/popcount8/solution.v",
    "ex02_detect_1101": ROOT / "runs/deepseek_final/detect_1101/solution.v",
    "ex03_lfsr8": ROOT / "runs/deepseek_lfsr8_revised/solution.v",
}
WINDOWS_HEAP_CORRUPTION = 0xC0000374


def load_module(name: str, path: Path):
    """veval-judge 无 .py 扩展名，因此显式指定 Python 源文件加载器。"""
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    if spec is None:
        raise RuntimeError(f"Cannot import official judge: {path}")
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class NativeRunner:
    """仅替换 OS 相关的执行步骤；不检查或更改 RTL 分级结果。"""

    def __init__(self, tools: dict[str, str | None], metadata_dir: Path):
        self.tools = tools
        self.metadata_dir = metadata_dir
        self._version: str | None = None

    def run(self, command, cwd, log_fh, timeout, tag):
        started = time.monotonic()
        executable = self.tools.get(command[0])
        if not executable:
            log_fh.write(f"\n===== [{tag}] {' '.join(command)} =====\n")
            log_fh.write(f"[{tag}] executable unavailable: {command[0]}\n")
            log_fh.flush()
            return 127, False, 0.0

        native_command = [executable, *command[1:]]
        # 原脚本的 open() 未指定编码，Windows 下改为 UTF-8 保留工具输出。
        if hasattr(log_fh, "reconfigure"):
            log_fh.reconfigure(encoding="utf-8", errors="replace")
        log_fh.write(f"\n===== [{tag}] {' '.join(native_command)} =====\n")
        log_fh.flush()
        try:
            rc, output, timed_out = _run_command(native_command, Path(cwd), timeout)
        except OSError as exc:
            rc, output, timed_out = 127, f"Tool launch failed: {exc}\n", False
        log_fh.write(output)
        if timed_out:
            # 标记沿用原 run()，让原判定器识别仿真墙钟超时。
            log_fh.write(f"\nTIMEOUT [{tag}] after {timeout}s\n")
            rc = 124
        log_fh.flush()
        return rc, timed_out, time.monotonic() - started

    def version(self) -> str:
        if self._version is None:
            self.metadata_dir.mkdir(parents=True, exist_ok=True)
            tool = self.tools.get("xvlog")
            if not tool:
                self._version = "unknown"
            else:
                try:
                    rc, output, timed_out = _run_command(
                        [tool, "--version"], self.metadata_dir, 60)
                    (self.metadata_dir / "xvlog_version.log").write_text(output, encoding="utf-8")
                    match = re.search(r"v(\d{4}\.\d+)", output)
                    self._version = match.group(1) if match and rc == 0 and not timed_out else "unknown"
                except OSError:
                    self._version = "unknown"
        return self._version


def load_judges(runner: NativeRunner):
    official = load_module("rtl_official_veval_judge", VENDOR / "judge/veval-judge")
    translate = load_module("rtl_official_judge_adapter", VENDOR / "judge.py")
    official.run = runner.run
    official.vivado_version = runner.version
    return official, translate


def load_solutions(args) -> dict[str, Path] | None:
    if args.reference:
        return None
    if args.generated:
        return GENERATED_SOLUTIONS
    manifest = args.solution_manifest.resolve()
    values = json.loads(manifest.read_text(encoding="utf-8"))
    if not isinstance(values, dict) or not values:
        raise ValueError("solution manifest must be a non-empty {task_id: path} JSON object")
    solutions = {}
    for task_id, value in values.items():
        if not isinstance(task_id, str) or not isinstance(value, str):
            raise ValueError("solution manifest keys and values must be strings")
        path = Path(value)
        solutions[task_id] = (manifest.parent / path).resolve() if not path.is_absolute() else path.resolve()
    return solutions


def collect_tasks(args, solutions: dict[str, Path] | None) -> list[tuple[Path, dict, Path]]:
    task_root = args.tasks.resolve()
    items = []
    known = set()
    selected = set(args.only or [])
    for config_path in sorted(task_root.glob("*/task.json")):
        config = json.loads(config_path.read_text(encoding="utf-8"))
        task_id = config.get("task_id", config_path.parent.name)
        config["task_id"] = task_id
        known.add(task_id)
        if selected and task_id not in selected:
            continue
        if solutions is not None and task_id not in solutions:
            continue
        if config.get("top", "TopModule") != "TopModule" or config.get("tb_top", "tb") != "tb":
            raise ValueError(f"{task_id}: official judge requires TopModule and testbench tb")
        if config.get("extra_files"):
            raise ValueError(f"{task_id}: this adapter does not implement extra_files")
        source = (config_path.parent / config["reference"]).resolve() if solutions is None else solutions[task_id]
        paths = [source, config_path.parent / config["reference_module"], config_path.parent / config["testbench"]]
        for path in paths:
            if not path.is_file():
                raise ValueError(f"{task_id}: missing input file {path}")
        items.append((config_path.parent, config, source))
    if selected - known:
        raise ValueError(f"unknown --only task ids: {sorted(selected - known)}")
    if solutions is not None and set(solutions) - known:
        raise ValueError(f"manifest contains unknown task ids: {sorted(set(solutions) - known)}")
    if not items:
        raise ValueError(f"no selected task.json fixtures found under {task_root}")
    return items


def translate_result(adapter, raw: dict, config: dict) -> dict:
    result = {
        "task_id": config["task_id"],
        "top": config.get("top", "TopModule"),
        "level": 0,
        "coefficient": 0.0,
        "stages": {"compile": False, "simulate": False, "synth": False},
        "tool_error": None,
    }
    adapter._translate(raw, result)
    result["verdict"] = raw.get("verdict", "JUDGE_ERROR")
    # 上游按 Linux 工具的退出行为判分，尚未区分这个 Windows 本机崩溃。
    # 只增加本地环境诊断；raw 原始字段和 vendor 判分代码均保持不变。
    result["local_environment_error"] = None
    for stage, stage_result in raw.get("stages", {}).items():
        rc = stage_result.get("rc")
        if isinstance(rc, int) and rc & 0xFFFFFFFF == WINDOWS_HEAP_CORRUPTION:
            result["local_environment_error"] = {
                "kind": "WINDOWS_TOOL_CRASH", "stage": stage, "exit_code": rc,
                "status_hex": "0xC0000374", "status_name": "STATUS_HEAP_CORRUPTION",
            }
            result["upstream_level"] = raw.get("level")
            result["tool_error"] = (
                f"{stage} 工具进程崩溃，退出码 {rc} (0xC0000374)；"
                f"上游原标签为 {result['verdict']}，本地请求的完整分级未完成，不能归因为 RTL 综合错误。"
            )
            break
    result["local_status"] = "TOOL_CRASH" if result["local_environment_error"] else result["verdict"]
    result["excluded_from_score"] = result["tool_error"] is not None
    if result["excluded_from_score"]:
        # 保留上游原始结果，同时避免把环境错误显示成有效 L0 成绩。
        result["level"] = None
        result["coefficient"] = None
    synth = raw.get("stages", {}).get("synth", {})
    result["synthesis_metrics"] = {
        key: synth[key] for key in ("LUT", "FF", "DSP", "BRAM", "SRL", "CARRY", "MUXF", "has_clk", "WNS_ns", "Fmax_MHz")
        if key in synth
    }
    return result


def evaluate(official, adapter, task_dir, config, source, output: Path, args) -> dict:
    started = time.monotonic()
    task_id = config["task_id"]
    task_output = output / task_id
    task_output.mkdir(parents=True, exist_ok=True)
    # 每次新建隔离目录，不递归删除用户指定的路径，不复用 xsim/Vivado 中间产物。
    work = Path(tempfile.mkdtemp(prefix="work_", dir=task_output))
    dut = work / "dut.sv"
    dut.write_bytes(source.read_bytes())
    settings = SimpleNamespace(
        workdir=str(work / "eda"), clean=False,
        dut=str(dut), ref=str((task_dir / config["reference_module"]).resolve()),
        test=str((task_dir / config["testbench"]).resolve()),
        part=config.get("part", "xczu3eg-sbva484-1-e"),
        clock_ns=float(config.get("period_ns", 5.0)), level=args.level,
        timeout_compile=args.timeout_compile, timeout_elab=args.timeout_elab,
        timeout_sim=args.timeout_sim, timeout_synth=args.timeout_synth,
    )
    if not dut.read_text(encoding="utf-8", errors="replace").strip():
        raw = {"level": 0, "verdict": "L0", "stages": {}, "note": "empty solution"}
    else:
        try:
            raw = official.judge(settings)
        except (Exception, SystemExit) as exc:
            raw = {"level": None, "verdict": "JUDGE_ERROR", "stages": {}, "note": str(exc)}
    (work / "verdict.json").write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    result = translate_result(adapter, raw, config)
    result.update({
        "solution": str(source), "raw_verdict": str(work / "verdict.json"),
        "work_dir": str(work), "elapsed_s": round(time.monotonic() - started, 2),
        "part": settings.part, "clock_ns": settings.clock_ns,
        "vivado_version": official.vivado_version(), "requested_level": args.level,
    })
    (task_output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def write_report(output: Path, summary: dict) -> None:
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# 官方公开样例本地自测", "", summary["scope_note"], "",
             f"模式：`{summary['mode']}`；Vivado：`{summary['vivado_version']}`；请求判定到 L{summary['requested_level']}。",
             "", "| 题目 | 本地判定 | 失配/采样 | LUT | FF | WNS (ns) | 推算 Fmax (MHz) | 耗时 (s) |",
             "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for item in summary["results"]:
        metrics = item["synthesis_metrics"]
        mismatch = f"{item.get('mismatches', '—')}/{item.get('samples', '—')}"
        label = item["verdict"]
        if item.get("local_environment_error"):
            label += "（工具崩溃，完整分级未完成）"
        row = [item["task_id"], label, mismatch]
        row.extend("—" if metrics.get(key) in (None, "") else str(metrics[key])
                   for key in ("LUT", "FF", "WNS_ns", "Fmax_MHz"))
        row.append(str(item["elapsed_s"]))
        lines.append("| " + " | ".join(row) + " |")
    lines += ["", "L1/L2/L3 按原判定器逐级递进；环境和装置错误不计入有效样本。",
              "WNS 与 Fmax 来自综合后的寄存器间路径估计；未布局布线，不能当作板级最高运行频率。",
              "没有时钟或寄存器间路径的题目对应指标为空；时序数值不参与原 L3 通过判据。",
              "每题 result.json 指向完整原始 verdict.json、judge.log 和 synth/synth.log。", ""]
    for item in summary["results"]:
        if item.get("local_environment_error"):
            lines.extend([f"- `{item['task_id']}`：{item['tool_error']}", ""])
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks", type=Path, default=DEFAULT_TASKS,
                        help="public offline selftest fixtures; defaults to the bundled vendor/tasks directory")
    parser.add_argument("--output", required=True, type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--reference", action="store_true", help="judge the official known-good reference solutions")
    mode.add_argument("--generated", action="store_true", help="judge the three existing DeepSeek solutions in this workspace")
    mode.add_argument("--solution-manifest", type=Path, help="JSON object mapping task_id to solution path; relative to the manifest")
    parser.add_argument("--only", action="append", help="select one task_id; repeat to select more")
    parser.add_argument("--level", type=int, choices=(2, 3), default=3)
    parser.add_argument("--timeout-compile", type=float, default=120)
    parser.add_argument("--timeout-elab", type=float, default=300)
    parser.add_argument("--timeout-sim", type=float, default=300)
    parser.add_argument("--timeout-synth", type=float, default=900)
    args = parser.parse_args(argv)
    if min(args.timeout_compile, args.timeout_elab, args.timeout_sim, args.timeout_synth) <= 0:
        parser.error("timeouts must be positive")
    try:
        tasks = collect_tasks(args, load_solutions(args))
        toolchain = Toolchain("vivado")
        tools = toolchain._tools["vivado"]
        required = ("xvlog", "xelab", "xsim", "vivado") if args.level == 3 else ("xvlog", "xelab", "xsim")
        missing = [name for name in required if not tools.get(name)]
        if missing:
            raise ValueError(f"Missing Vivado tools {missing}; set XILINX_VIVADO to the Vivado installation directory")
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        parser.error(str(exc))

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    runner = NativeRunner(tools, output / "environment")
    official, adapter = load_judges(runner)
    version = runner.version()
    results = []
    for task_dir, config, source in tasks:
        print(f"Running {config['task_id']} with Vivado {version} ...", flush=True)
        result = evaluate(official, adapter, task_dir, config, source, output, args)
        results.append(result)
        print(f"  {result['verdict']}: mismatches={result.get('mismatches')} samples={result.get('samples')} ({result['elapsed_s']} s)", flush=True)
        if result.get("local_environment_error"):
            print(f"  TOOL_CRASH: {result['tool_error']}", flush=True)
    summary = {
        "mode": "reference" if args.reference else "generated" if args.generated else "solution_manifest",
        "vivado_version": version, "announced_contest_version": ANNOUNCED_VERSION,
        "version_matches_announced": version == ANNOUNCED_VERSION,
        "is_official_contest_score": False, "requested_level": args.level,
        "scope_note": (
            "使用原样官方判定器与公开样例复现；非比赛官方成绩。"
            + ("已使用赛事指定 Vivado 2026.1，结果仅覆盖本次公开样例。"
               if version == ANNOUNCED_VERSION else
               "当前结果必须在赛事指定 Vivado 2026.1 环境复验。")
        ),
        "results": results,
    }
    write_report(output, summary)
    print(f"Report: {output / 'report.md'}", flush=True)
    return 0 if all(not r["tool_error"] and r["level"] >= args.level for r in results) else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
