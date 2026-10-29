"""仿真自编练习的参考实现或候选代码；不调用模型，不计算赛事分数。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import platform
import re
import sys
import time

from tools.verification import Toolchain

ROOT = Path(__file__).resolve().parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--reference", action="store_true", help="验证包内人工参考实现")
    source.add_argument("--solutions", type=Path, help="候选根目录，内部为 <题号>/solution.v")
    parser.add_argument("--task", nargs="+", help="只运行指定题号，默认全部")
    parser.add_argument("--backend", choices=("vivado", "iverilog", "modelsim"), default="vivado")
    parser.add_argument("--timeout", type=float, default=120, help="每题编译与仿真总超时秒数")
    parser.add_argument("--output", type=Path, help="日志与波形目录")
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("timeout 必须大于 0")
    available = sorted(path.name for path in (ROOT / "tasks").iterdir() if path.is_dir())
    task_ids = args.task or available
    if not task_ids or any(task not in available for task in task_ids):
        parser.error("题号必须选自：" + ", ".join(available))
    source_root = ROOT / "reference" if args.reference else args.solutions.resolve()
    output = args.output or ROOT / "results" / ("reference" if args.reference else "candidates")
    output.mkdir(parents=True, exist_ok=True)
    tools = Toolchain(args.backend)
    results = []
    for task_id in task_ids:
        work = output / task_id
        work.mkdir(parents=True, exist_ok=True)
        try:
            code = (source_root / task_id / "solution.v").read_text(encoding="utf-8-sig")
            tb = (ROOT / "testbench" / task_id / "tb.sv").read_text(encoding="utf-8")
            result = tools.simulate(code, tb, "TopModule", work, args.timeout).to_dict()
        except (OSError, ValueError) as exc:
            result = {"status": "error", "backend": args.backend, "log": str(exc),
                      "elapsed_s": 0.0, "details": {}}
        match = re.search(r"^CHECKS=(\d+)", result["log"], re.MULTILINE)
        result.update(task_id=task_id, checks=int(match.group(1)) if match else None)
        (work / "simulation.log").write_text(result["log"], encoding="utf-8")
        (work / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        results.append(result)
        print(f"{task_id}: {result['status']}, checks={result['checks']}", flush=True)
    summary = {
        "scope": "自编练习的开发仿真；不是官方题目、正式判级或模型 pass@1",
        "source": "human_reference" if args.reference else "candidate",
        "host_os": platform.system(), "platform": platform.platform(),
        "python_version": sys.version.split()[0], "timestamp_unix": time.time(),
        "toolchain": tools.describe(), "tasks": results,
        "passed": sum(result["status"] == "passed" for result in results), "total": len(results),
    }
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{summary['passed']}/{summary['total']} passed; summary: {output / 'summary.json'}")
    return 0 if summary["passed"] == summary["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
