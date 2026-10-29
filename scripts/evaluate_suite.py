"""Evaluate isolated local RTL fixtures against already-generated solution manifests.

No model or network calls occur here. Icarus is a fast development check only.
Vivado delegates grading to the existing, unmodified official judge adapter.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from types import SimpleNamespace
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent.verification import Toolchain, _run_command

DEFAULT_SUITE = ROOT / "evals" / "rtl_generalization_v2"
LABEL = re.compile(r"^[A-Za-z0-9_-]+$")
MISMATCHES = re.compile(r"^Mismatches:\s*(\d+)\s+in\s+(\d+)\s+samples\s*$", re.M)


def read_manifest(path: Path, task_ids: set[str]) -> dict[str, list[Path]]:
    """Accept {task: path} or {task: [independent_sample_paths...]}; never best-of."""
    path = path.resolve()
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict) or not payload:
        raise ValueError(f"{path}: expected non-empty task-to-solution mapping")
    unknown = set(payload) - task_ids
    if unknown:
        raise ValueError(f"{path}: unknown task ids: {sorted(unknown)}")
    result = {}
    for task_id, values in payload.items():
        if isinstance(values, str):
            values = [values]
        if not isinstance(values, list) or not values or not all(isinstance(v, str) for v in values):
            raise ValueError(f"{task_id}: expected path or non-empty list of independent sample paths")
        resolved = [(path.parent / value).resolve() for value in values]
        # Listing the same artifact five times is not five independent generations.
        if len(set(resolved)) != len(resolved):
            raise ValueError(f"{task_id}: repeated sample path; provide independent artifacts")
        result[task_id] = resolved
    return result


def run_icarus(tools: dict, task_dir: Path, config: dict, source: Path | None,
               output: Path, timeout: float) -> dict:
    started = time.monotonic()
    work = Path(tempfile.mkdtemp(prefix="work_", dir=output))
    result = {
        "task_id": config["task_id"], "solution": str(source) if source else None,
        "compiled": False, "functional_pass": False, "synthesized": None,
        "level": None, "coefficient": None, "tool_error": None,
        "work_dir": str(work), "status": "MISSING_SOLUTION",
    }
    if source is None or not source.is_file() or not source.read_text(encoding="utf-8", errors="replace").strip():
        result["elapsed_s"] = 0.0
        return result
    (work / "dut.sv").write_bytes(source.read_bytes())
    command = [tools["iverilog"], "-g2012", "-s", "tb", "-o", str(work / "sim.vvp"),
               str(work / "dut.sv"), str(task_dir / config["reference_module"]),
               str(task_dir / config["testbench"])]
    rc, log, timed_out = _run_command(command, work, timeout)
    (work / "compile.log").write_text(log, encoding="utf-8")
    result["compile_rc"] = rc
    if timed_out:
        result["status"] = "COMPILE_TIMEOUT"
    elif rc != 0:
        result["status"] = "COMPILE_FAILURE"
        if rc < 0 or rc > 255:
            result["tool_error"] = f"Compiler crashed or could not load (exit {rc}); inspect compile.log"
    else:
        result["compiled"] = True
        rc, log, timed_out = _run_command([tools["vvp"], str(work / "sim.vvp")], work, timeout)
        (work / "simulate.log").write_text(log, encoding="utf-8")
        result["simulate_rc"] = rc
        samples = MISMATCHES.findall(log)
        result["status"] = "SIMULATION_FAILURE"
        if "ORACLE_ERROR" in log:
            result["status"] = "FIXTURE_ERROR"
            result["tool_error"] = "Independent testbench check disagreed with reference"
        elif timed_out or re.search(r"^TIMEOUT\b", log, re.M):
            result["status"] = "SIMULATION_TIMEOUT"
        elif rc == 0 and len(samples) == 1 and int(samples[0][1]) > 0:
            result["mismatches"], result["samples"] = map(int, samples[0])
            result["functional_pass"] = result["mismatches"] == 0
            result["status"] = "PASS" if result["functional_pass"] else "FUNCTIONAL_MISMATCH"
        elif rc < 0 or rc > 255:
            result["tool_error"] = f"Simulator crashed or could not load (exit {rc}); inspect simulate.log"
    result["elapsed_s"] = round(time.monotonic() - started, 3)
    return result


def summarize_run(results: list[dict], task_ids: list[str], backend: str) -> dict:
    per_task = {}
    for task_id in task_ids:
        samples = [r for r in results if r["task_id"] == task_id]
        coefficients = [r["coefficient"] for r in samples]
        per_task[task_id] = {
            "sample_count": len(samples),
            "functional_pass_rate": sum(r["functional_pass"] for r in samples) / len(samples),
            "any_functional_pass": any(r["functional_pass"] for r in samples),
            "mean_coefficient": (sum(coefficients) / len(coefficients)
                                 if all(c is not None for c in coefficients) else None),
        }
    values = list(per_task.values())
    valid_grades = backend == "vivado" and all(v["mean_coefficient"] is not None for v in values)
    return {
        "per_task": per_task,
        "functional_pass_at_1_development": sum(v["functional_pass_rate"] for v in values) / len(values),
        "all_requested_samples_passed": all(r["functional_pass"] and not r["tool_error"] for r in results),
        "task_set_coefficient": (sum(v["mean_coefficient"] for v in values) / len(values)
                                 if valid_grades else None),
        "results": results,
    }


def first70_estimates(runs: dict, baseline: str) -> dict:
    """Same arithmetic as the adopted rules; results remain local, not official."""
    base = runs[baseline]
    estimates = {}
    for name, run in runs.items():
        if name == baseline:
            continue
        shapes_match = all(
            run["per_task"][task]["sample_count"] == base["per_task"][task]["sample_count"]
            for task in run["per_task"]
        )
        a, b = run["task_set_coefficient"], base["task_set_coefficient"]
        if not shapes_match or a is None or b is None:
            estimates[name] = {"available": False, "reason": "incomparable sample counts or incomplete Vivado grades"}
            continue
        gain = 1.0 if b == 1 else max(0.0, min(((a - b) / (1 - b)) / 0.6, 1.0))
        estimates[name] = {
            "available": True, "A": a, "B": b,
            "capability_out_of_30": round(30 * a, 4),
            "gain_out_of_40": round(40 * gain, 4),
            "first70_development_estimate": round(30 * a + 40 * gain, 4),
            "independent_samples_per_task": {k: v["sample_count"] for k, v in run["per_task"].items()},
            "is_official_contest_score": False,
        }
    return estimates


def write_report(output: Path, summary: dict) -> None:
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# 自建 RTL 能力回归", "", summary["scope_note"], "",
             f"后端：`{summary['backend']}`；题数：{len(summary['task_ids'])}。", "",
             "| 运行 | 题目 | 样本 | 结果 | 失配/采样 |",
             "| --- | --- | ---: | --- | --- |"]
    for name, run in summary["runs"].items():
        for result in run["results"]:
            lines.append(f"| {name} | {result['task_id']} | {result['sample_index']} | {result['status']} | "
                         f"{result.get('mismatches', '—')}/{result.get('samples', '—')} |")
    if "first70_development_estimates" in summary:
        lines += ["", "前 70 分仅使用本题集、当前样本与用户确认相同的模型设置计算，不能外推官方隐藏题成绩。", "",
                  "```json", json.dumps(summary["first70_development_estimates"], ensure_ascii=False, indent=2), "```"]
    lines += ["", "生成阶段只传入 `prompts/<task_id>/`。不得把 evaluator/、参考代码或测试台加入模型上下文。",
              "本工具不生成候选代码，不联网，不修改官方基线，也不挑选多次生成中的最好一次计分。", ""]
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--backend", choices=("icarus", "vivado"), default="icarus")
    parser.add_argument("--run", action="append", default=[], metavar="LABEL=MANIFEST",
                        help="repeat for v1/v2/baseline; manifest maps each task to a path or independent path list")
    parser.add_argument("--reference", action="store_true", help="evaluate known-good fixture implementations")
    parser.add_argument("--validate-fixtures", action="store_true",
                        help="Icarus: all references must pass; each representative mutant must compile and fail")
    parser.add_argument("--level", type=int, choices=(2, 3), default=3, help="Vivado maximum level")
    parser.add_argument("--timeout", type=float, default=60, help="Icarus per-stage wall-clock seconds")
    parser.add_argument("--timeout-synth", type=float, default=180)
    parser.add_argument("--baseline", help="label of the comparable baseline run")
    parser.add_argument("--estimate-first70", action="store_true",
                        help="explicit local capability+gain estimate; needs Vivado and comparable baseline")
    parser.add_argument("--confirm-comparable-settings", action="store_true",
                        help="assert same model revision, quantization, context, thinking and generation deadline")
    args = parser.parse_args(argv)
    if args.timeout <= 0 or args.timeout_synth <= 0:
        parser.error("timeouts must be positive")
    if args.validate_fixtures and (args.backend != "icarus" or args.run or args.reference):
        parser.error("--validate-fixtures is a standalone Icarus check")
    if args.estimate_first70 and (args.backend != "vivado" or not args.baseline or not args.confirm_comparable_settings):
        parser.error("first70 estimate requires --backend vivado --baseline LABEL --confirm-comparable-settings")
    try:
        suite = args.suite.resolve()
        tasks = {}
        for config_path in sorted((suite / "evaluator" / "tasks").glob("*/task.json")):
            config = json.loads(config_path.read_text(encoding="utf-8"))
            task_id = config["task_id"]
            if not LABEL.fullmatch(task_id) or task_id in tasks:
                raise ValueError("invalid or duplicate fixture task_id")
            if config.get("top") != "TopModule" or config.get("tb_top") != "tb" or config.get("extra_files"):
                raise ValueError(f"{task_id}: unsupported fixture interface")
            for field in ("reference", "reference_module", "testbench"):
                fixture_path = (config_path.parent / config[field]).resolve()
                if not fixture_path.is_relative_to(config_path.parent.resolve()) or not fixture_path.is_file():
                    raise ValueError(f"{task_id}: missing/out-of-directory fixture {field}")
            tasks[task_id] = (config_path.parent, config)
        if not tasks:
            raise ValueError("no fixture task.json found")
        manifests = {}
        for spec in args.run:
            if "=" not in spec:
                raise ValueError("--run must be LABEL=MANIFEST")
            name, value = spec.split("=", 1)
            if not LABEL.fullmatch(name) or name in manifests:
                raise ValueError("invalid or duplicate run label")
            manifests[name] = read_manifest(Path(value), set(tasks))
        if args.reference or args.validate_fixtures:
            if "reference" in manifests:
                raise ValueError("reference label is reserved with --reference")
            manifests["reference"] = read_manifest(suite / "evaluator" / "reference-manifest.json", set(tasks))
        if args.validate_fixtures:
            manifests["mutants"] = read_manifest(suite / "evaluator" / "mutants-manifest.json", set(tasks))
        if not manifests:
            raise ValueError("provide --run, --reference, or --validate-fixtures")
        if args.baseline and args.baseline not in manifests:
            raise ValueError("--baseline must name a supplied --run")
        if args.estimate_first70:
            if len(manifests) < 2:
                raise ValueError("first70 estimate needs both a candidate and baseline")
            if any(set(values) != set(tasks) for values in manifests.values()):
                raise ValueError("first70 estimate requires a solution entry for every fixture")
        chain = Toolchain("iverilog" if args.backend == "icarus" else "vivado")
        tools = chain._tools["iverilog" if args.backend == "icarus" else "vivado"]
        required = ("iverilog", "vvp") if args.backend == "icarus" else (
            ("xvlog", "xelab", "xsim", "vivado") if args.level == 3 else ("xvlog", "xelab", "xsim"))
        missing = [name for name in required if not tools.get(name)]
        if missing:
            raise ValueError(f"tools unavailable: {missing}; no result is counted as a pass")
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    environment = chain.describe()
    if args.backend == "vivado":
        import official_selftest
        runner = official_selftest.NativeRunner(tools, output / "environment")
        official, adapter = official_selftest.load_judges(runner)
        environment["vivado_version"] = runner.version()
        judge_args = SimpleNamespace(level=args.level, timeout_compile=120, timeout_elab=180,
                                     timeout_sim=180, timeout_synth=args.timeout_synth)
    else:
        rc, version, timeout = _run_command([tools["iverilog"], "-V"], output, 10)
        (output / "iverilog-version.log").write_text(version, encoding="utf-8")
        environment["iverilog_version"] = version.splitlines()[0] if rc == 0 and not timeout else "unknown"
    runs = {}
    for name, mapping in manifests.items():
        results = []
        for task_id, (task_dir, config) in tasks.items():
            # Missing tasks stay in the denominator; they are never silently omitted.
            for index, source in enumerate(mapping.get(task_id, [None]), 1):
                sample_dir = output / name / task_id / f"sample_{index:02d}"
                sample_dir.mkdir(parents=True, exist_ok=True)
                if args.backend == "icarus":
                    result = run_icarus(tools, task_dir, config, source, sample_dir, args.timeout)
                elif source is None or not source.is_file():
                    result = {"task_id": task_id, "solution": str(source) if source else None,
                              "level": 0, "coefficient": 0.0, "compiled": False,
                              "functional_pass": False, "synthesized": False,
                              "status": "MISSING_SOLUTION", "tool_error": None, "elapsed_s": 0.0}
                else:
                    result = official_selftest.evaluate(
                        official, adapter, task_dir, config, source, sample_dir, judge_args)
                    result.update({
                        "status": result["local_status"], "compiled": result["stages"]["compile"],
                        "functional_pass": result["stages"]["simulate"],
                        "synthesized": result["stages"]["synth"],
                    })
                result["sample_index"] = index
                (sample_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                results.append(result)
                print(f"{name}/{task_id}/{index}: {result['status']}", flush=True)
        runs[name] = summarize_run(results, list(tasks), args.backend)
    summary = {
        "suite": str(suite), "backend": args.backend, "task_ids": list(tasks),
        "is_official_contest_score": False,
        "scope_note": (
            "6 道自建开发题，非官方隐藏题或正式比赛成绩；结果只覆盖本次激励与已提交样本。"
            + ("Icarus 仅做功能回归，不赋予官方 L1–L3 等级或赛事分数。"
               if args.backend == "icarus" else "Vivado 调用原样官方判定器，开发题结果不外推官方成绩。")
        ),
        "environment": environment, "runs": runs,
    }
    if args.estimate_first70:
        summary["comparison_settings_confirmed_by_caller"] = True
        summary["first70_development_estimates"] = first70_estimates(runs, args.baseline)
    if args.validate_fixtures:
        valid = all(r["functional_pass"] and not r["tool_error"] for r in runs["reference"]["results"])
        rejected = all(r["compiled"] and r["status"] == "FUNCTIONAL_MISMATCH"
                       for r in runs["mutants"]["results"])
        summary["fixture_validation"] = {"all_references_pass": valid, "all_mutants_detected": rejected}
        success = valid and rejected
    else:
        success = all(run["all_requested_samples_passed"] for run in runs.values())
    write_report(output, summary)
    print(f"Report: {output / 'report.md'}")
    return 0 if success else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
