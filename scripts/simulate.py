"""独立仿真入口：读取 RTL 和 testbench，保存日志、波形与 JSON 结果。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent.verification import Toolchain


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="Verilog/SystemVerilog DUT 文件")
    parser.add_argument("--testbench", required=True, type=Path, help="顶层模块名必须为 tb")
    parser.add_argument("--top", default="TopModule", help="DUT 的顶层模块名")
    parser.add_argument("--backend", default="auto", choices=("auto", "vivado", "modelsim", "iverilog"))
    parser.add_argument("--output", type=Path, default=Path("output/simulation"))
    parser.add_argument("--timeout", type=float, default=60, help="整个仿真步骤的主机超时秒数")
    args = parser.parse_args()
    try:
        source = args.source.read_text(encoding="utf-8")
        testbench = args.testbench.read_text(encoding="utf-8")
        args.output.mkdir(parents=True, exist_ok=True)
        result = Toolchain(args.backend).simulate(source, testbench, args.top, args.output, args.timeout)
    except (OSError, ValueError) as exc:
        print(f"输入错误：{exc}", file=sys.stderr)
        return 2
    (args.output / "result.json").write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    (args.output / "simulation.log").write_text(result.log, encoding="utf-8")
    print(f"{result.status}: {result.backend}")
    print(f"结果：{(args.output / 'result.json').resolve()}")
    if result.status != "passed":
        print(result.log)
    return 0 if result.status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
