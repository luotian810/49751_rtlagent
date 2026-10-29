"""把诊断绑定到实际失配；日志绑定不等于证明自建 oracle 正确。"""
from __future__ import annotations

import json
import re

from .interface import strip_think


DIAGNOSE_FAILURE = """你是 RTL 失败归因审查员。本轮只诊断，不生成或修改 RTL、测试台、期望值。
输入包含题面、DUT、自建测试台、日志与 observed_failure（程序从实际首个 FAIL 提取）。
自建测试台不是参考答案；FAIL 只说明双方不一致，不能直接认定 DUT 错。
只分析 observed_failure 的同一采样点，按题面独立推导期望，核对复位、使能、
时钟边沿、非阻塞赋值旧值与采样时机。不要推测日志没有提供的历史周期或输出。
- dut_error：题面明确，独立推导的 expected 与 DUT 不同，且与测试台期望相同。
- testbench_error：题面明确，独立推导的 expected 与 DUT 相同，且与测试台期望不同。
- uncertain：缺少必要历史、题面含糊、无法独立推导、双方可能都有错或工具异常。
只输出一个 JSON 对象，reason 与 spec_rule 各用简短一句话：
{"verdict":"dut_error|testbench_error|uncertain",
 "reason":"该采样点的推导；缺少所需历史时说明缺口，不编造历史",
 "spec_rule":"题面中支持判断的原句或准确转述；未知时为空字符串",
 "evidence":{"sample":1, "stimulus":{"input_name":"hex_value"},
             "expected":"output_name=hex_value",
             "observed":"output_name=hex_value",
             "testbench_expected":"output_name=hex_value"}}
sample、stimulus、observed、testbench_expected 必须逐项复制 observed_failure，
不能加减输入、输出或补写未观测的值。expected 使用同一输出名及十六进制，值由题面推导。
日志绑定只核实观测，不证明 expected 的语义推导。确定归因必须有全部证据；
无法确认同一采样点或必要历史时选 uncertain，未知 evidence 可省略。不要输出修复方案。
"""

_FIELD = re.compile(r"([A-Za-z_][A-Za-z0-9_$]*)=([0-9a-fA-FxXzZ]+)")
_FAILURE = re.compile(r"RTL_AGENT_FAIL sample=([1-9][0-9]*) (.+)")
_VALUES = ("expected", "observed", "testbench_expected")


def failure_observation(log: str) -> dict | None:
    """读取生成器固定格式的首个 FAIL，不猜测任意测试台的打印含义。

    生成器以 %h 打印全部输入、首个失配输出、expected；sample 为十进制。
    首个标记格式未知时不跳过它寻找后面的“可用”证据。
    """
    if not isinstance(log, str):
        return None
    for original_line in log.splitlines():
        line = re.sub(r"^\s*#\s?", "", original_line, count=1).strip()
        if not line.startswith("RTL_AGENT_FAIL"):
            continue
        match = _FAILURE.fullmatch(line)
        if not match:
            return None
        fields = [_FIELD.fullmatch(token) for token in match[2].split()]
        if len(fields) < 2 or any(field is None for field in fields):
            return None
        pairs = [field.groups() for field in fields]
        names = [name for name, _ in pairs]
        if names[-1] != "expected" or len(set(names)) != len(names):
            return None
        signal, actual = pairs[-2]
        return {
            "sample": int(match[1]),
            "stimulus": dict(pairs[:-2]),
            "observed": f"{signal}={actual}",
            "testbench_expected": f"{signal}={pairs[-1][1]}",
            "line": original_line,
        }
    return None


def _uncertain(reason: str) -> dict:
    return {"verdict": "uncertain", "reason": reason, "spec_rule": ""}


def parse_diagnosis(text: str, *, failure_log: str = "") -> dict:
    """校验完整 JSON、实际观测与数值关系；语义归因仍是模型假设。

    没有日志、样本或完整输入记录时拒绝确定归因。观察绑定成功也不验证
    spec_rule 和 expected 的推导，不得据此声称自建测试台或 DUT 已被证明正确。
    """
    if not isinstance(text, str):
        return _uncertain("归因回复不是文本")
    cleaned = strip_think(text).strip()
    fenced = re.fullmatch(r"```(?:json)?\s*\n(.*?)\n?\s*```", cleaned, flags=re.S | re.I)
    if fenced:
        cleaned = fenced[1].strip()
    try:
        result = json.loads(cleaned)
    except (ValueError, TypeError):
        return _uncertain("归因回复不是完整 JSON")
    if not isinstance(result, dict):
        return _uncertain("归因回复必须是 JSON 对象")
    verdict, reason, rule = (result.get(key) for key in ("verdict", "reason", "spec_rule"))
    if verdict not in ("dut_error", "testbench_error", "uncertain"):
        return _uncertain("归因标签未知")
    if not isinstance(reason, str) or not reason.strip() or not isinstance(rule, str):
        return _uncertain("归因缺少理由或题面依据字段")
    parsed = {"verdict": verdict, "reason": reason.strip(), "spec_rule": rule.strip()}
    if verdict == "uncertain":
        return parsed

    evidence = result.get("evidence")
    if not rule.strip() or not isinstance(evidence, dict):
        return _uncertain("确定归因缺少题面依据或失败激励证据")
    observation = failure_observation(failure_log)
    if observation is None:
        return _uncertain("没有可绑定的首个实际 FAIL 记录")
    if (type(evidence.get("sample")) is not int
            or evidence["sample"] != observation["sample"]
            or evidence.get("stimulus") != observation["stimulus"]):
        return _uncertain("归因采样点、输入或观察值与实际 FAIL 不一致")
    values = [_FIELD.fullmatch(evidence.get(key, ""))
              if isinstance(evidence.get(key), str) else None for key in _VALUES]
    values += [_FIELD.fullmatch(observation[key]) for key in ("observed", "testbench_expected")]
    if any(value is None for value in values) or len({value[1] for value in values}) != 1:
        return _uncertain("三个值必须使用同一输出名与十六进制数值")
    if any(re.search("[xXzZ]", value[2]) for value in values):
        return _uncertain("观察或期望包含未知态，不能确定功能归因")
    expected, observed, tb_expected, log_observed, log_expected = (int(value[2], 16) for value in values)
    if observed != log_observed or tb_expected != log_expected:
        return _uncertain("归因观察值或测试台期望与实际 FAIL 不一致")
    consistent = ((observed != expected and tb_expected == expected) if verdict == "dut_error"
                  else (observed == expected and tb_expected != expected))
    if not consistent:
        return _uncertain("归因标签与同一采样点的题面期望、DUT 实际值、测试台期望不一致")
    return {**parsed, "evidence": {key: evidence[key] for key in ("sample", "stimulus", *_VALUES)},
            "observation_bound": True, "semantic_verified": False}

