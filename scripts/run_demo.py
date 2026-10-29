"""离线运行教学 RTL，绝不调用模型，也不作为智能体比赛成绩。"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent.verification import Toolchain


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", default="auto")
    parser.add_argument("--output", type=Path, default=ROOT / "runs" / "demo")
    parser.add_argument("--timeout", type=float, default=120, help="每题仿真的主机超时秒数")
    parser.add_argument("--synth", action="store_true", help="仿真通过后额外执行 Vivado 综合")
    parser.add_argument("--synth-timeout", type=float, default=180)
    args = parser.parse_args(argv)
    tool = Toolchain(args.backend)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    for name in ("popcount8", "detect_1101", "lfsr8"):
        folder = ROOT / "demos" / name
        (output / name).mkdir(parents=True, exist_ok=True)
        result = tool.simulate(
            (folder / "solution.v").read_text(encoding="utf-8"),
            (folder / "tb.sv").read_text(encoding="utf-8"),
            "TopModule", output / name, args.timeout,
        )
        record = {"demo": name, **asdict(result)}
        rows.append(record)
        (output / name / "tool.log").write_text(result.log, encoding="utf-8")
        print(f"{name}: {result.status} ({result.backend}, {result.elapsed_s:.2f}s)")
        if args.synth and result.status == "passed":
            synthesis = tool.synth(
                (folder / "solution.v").read_text(encoding="utf-8"),
                "TopModule", output / name / "synth", args.synth_timeout,
            )
            record["synthesis"] = asdict(synthesis)
            # 即使工具缺失，仍归档状态；不能用仿真通过替代综合通过。
            synth_dir = output / name / "synth"
            synth_dir.mkdir(exist_ok=True)
            (synth_dir / "result.json").write_text(json.dumps(asdict(synthesis), ensure_ascii=False, indent=2), encoding="utf-8")
            (synth_dir / "tool.log").write_text(synthesis.log, encoding="utf-8")
            print(f"  synthesis: {synthesis.status} ({synthesis.elapsed_s:.2f}s)")
        elif args.synth:
            record["synthesis"] = {"status": "skipped", "reason": "simulation_not_passed"}
        (output / name / "result.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {"kind": "handwritten_educational_examples", "official_evaluation": "not_run",
               "synthesis_requested": args.synth,
               "all_passed": all(row["status"] == "passed" and
                                 (not args.synth or row["synthesis"]["status"] == "passed") for row in rows),
               "results": rows}
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# 教学示例仿真结果", "", "这些是手写教学设计，不是模型生成能力或官方得分。", "",
             "| 示例 | 仿真器 | 仿真 | 综合 | 仿真秒数 |", "| --- | --- | --- | --- | ---: |"]
    lines.extend(f"| {r['demo']} | {r['backend']} | {r['status']} | {r.get('synthesis', {}).get('status', 'not_requested')} | {r['elapsed_s']:.2f} |" for r in rows)
    lines += ["", "每题目录保存 result.json、tool.log 和仿真产物。", ""]
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")
    return 0 if summary["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
