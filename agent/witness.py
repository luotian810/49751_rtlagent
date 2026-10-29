"""只用规格与真实输入历史复核失配期望，避免被 DUT 或自建 oracle 锚定。

此模块不证明参考算法正确。它仅准备有界的盲复核上下文，并在回复后由
程序比较独立期望与实际失配值；无法完整重放时不调用模型猜测历史。
"""
from __future__ import annotations

import json
import re

from .diagnosis import failure_observation
from .interface import strip_think


WITNESS_PROMPT = """你是独立 RTL 规格复核员。只根据 specification 与实际输入历史推导指定输出在 target.sample 的期望。
你看不到 DUT、测试台参考算法、实际输出或测试台期望；不要猜测它们。
输入均为十六进制位模式；sampling 是本次测试使用的采样控制，必须先与题面核对。
sample/target.sample 只是日志中的观测顺序号，不是端口值、位编号、周期计数或已接受事务数。
先从 history.inputs 与有效沿推导状态，最后核对 expected 的位模式与 reason 的结论一致；不能把观测编号代入功能运算。
history 的每条是一次观测，不一定是一个时钟周期：after_edge=1 表示有效沿后；
after_edge=0 是组合检查或异步复位沿前检查，不能当成额外有效沿。
时序历史从已观测复位开始，按 reset、使能、接受事件、旧值和输出延迟逐条推导。
题面含糊、控制与题面不符、必要历史不足或无法可靠推导时返回 uncertain，不编造状态。
只输出完整紧凑 JSON：
{"status":"derived|uncertain","sample":目标整数,"output":"指定输出名",
 "expected":"不带0x的十六进制位模式","spec_rule":"题面依据","reason":"简短推导"}
derived 必须逐项提供这些字段；uncertain 可省略 expected，reason 说明无法推导的原因。
不输出 RTL、测试台、修复方案或 DUT/testbench 对错标签。独立推导仍是待验证假设。
"""

_NAME = re.compile(r"[A-Za-z_][A-Za-z_0-9]*\Z")
_FIELD = re.compile(r"([A-Za-z_][A-Za-z0-9_$]*)=([0-9a-fA-FxXzZ]+)\Z")
_SAMPLE = re.compile(r"RTL_AGENT_SAMPLE sample=([1-9][0-9]*) after_edge=([01]) (.+)\Z")
_HEX = re.compile(r"[0-9a-fA-F]+\Z")


def _fits_width(value: str, width: int) -> bool:
    """Known hex may be zero-padded; X/Z retains its displayed-width bound."""
    if _HEX.fullmatch(value):
        value = value.lstrip("0") or "0"
    return (len(value) <= (width + 3) // 4
            and int(re.sub(r"[xXzZ]", "0", value), 16) < (1 << width))


def _uncertain(reason: str) -> dict:
    return {"verdict": "uncertain", "reason": reason, "spec_rule": ""}


def _ports(plan: dict) -> dict | None:
    records = plan.get("ports")
    if not isinstance(records, list) or not 1 <= len(records) <= 64:
        return None
    ports = {}
    for item in records:
        if (not isinstance(item, dict) or not isinstance(item.get("name"), str)
                or not _NAME.fullmatch(item["name"]) or item["name"] in ports
                or item.get("direction") not in ("input", "output")
                or type(item.get("width")) is not int or not 1 <= item["width"] <= 4096
                or type(item.get("signed", False)) is not bool):
            return None
        ports[item["name"]] = {key: item[key] for key in ("name", "direction", "width")}
        ports[item["name"]]["signed"] = item.get("signed", False)
    return ports


def prepare_witness(plan: dict, failure_log: str) -> tuple[dict | None, str]:
    """返回不含 DUT 输出/算法的输入上下文，或无法安全重放的具体原因。

    时序仅截取最近有效复位到首个 FAIL，最多 64 次连续观测；组合仅保留
    首个 FAIL 对应输入。既不读取文件，也不把截断历史补成假定的初态。
    """
    if not isinstance(plan, dict) or not isinstance(failure_log, str) or len(failure_log) > 1_000_000:
        return None, "验证计划或日志无效/超出长度限制"
    ports = _ports(plan)
    observation = failure_observation(failure_log)
    if not ports or observation is None:
        return None, "缺少有效端口契约或首个实际 FAIL"
    actual = _FIELD.fullmatch(observation["observed"])
    expected = _FIELD.fullmatch(observation["testbench_expected"])
    if (actual is None or expected is None or actual[1] != expected[1]
            or actual[1] not in ports or ports[actual[1]]["direction"] != "output"
            or not _HEX.fullmatch(expected[2])):
        return None, "失配输出未知或不属于声明的输出"
    output = ports[actual[1]]
    if not _fits_width(actual[2], output["width"]) or not _fits_width(expected[2], output["width"]):
        return None, "失配输出位模式超出端口宽度"
    clock = plan.get("clock")
    reset = plan.get("reset", plan.get("async_reset"))
    asynchronous = plan.get("async_reset")
    if clock is not None and (not isinstance(clock, dict) or clock.get("edge") not in ("posedge", "negedge")
            or clock.get("name") not in ports or ports[clock["name"]]["direction"] != "input"
            or ports[clock["name"]]["width"] != 1):
        return None, "采样时钟声明无效"
    for control in (reset, asynchronous):
        if control is not None and (not clock or not isinstance(control, dict)
                or type(control.get("active")) is not int or control["active"] not in (0, 1)
                or control.get("name") not in ports or ports[control["name"]]["direction"] != "input"
                or ports[control["name"]]["width"] != 1 or control["name"] == clock["name"]):
            return None, "复位声明无效"
    if asynchronous and (not reset or any(asynchronous[key] != reset[key] for key in ("name", "active"))):
        return None, "同步/异步复位描述冲突"
    if clock and reset is None:
        return None, "时序复核缺少可观测复位，不能假设初态"
    input_names = [name for name, port in ports.items()
                   if port["direction"] == "input" and (not clock or name != clock["name"])]
    sample_names = set(input_names) | {name for name, port in ports.items() if port["direction"] == "output"}
    if set(observation["stimulus"]) != set(input_names):
        return None, "首个 FAIL 的输入集合不完整"

    records = []
    # 只保留固定格式的观测，源代码回显和任意工具输出不会变成刺激记录。
    for original in failure_log.splitlines():
        line = re.sub(r"^\s*#\s?", "", original, count=1).strip()
        if line.startswith("RTL_AGENT_FAIL"):
            break
        if not line.startswith("RTL_AGENT_SAMPLE"):
            continue
        match = _SAMPLE.fullmatch(line)
        if match is None:
            return None, "观测记录格式损坏"
        fields = [_FIELD.fullmatch(token) for token in match[3].split()]
        if any(field is None for field in fields):
            return None, "观测信号记录格式损坏"
        pairs = [field.groups() for field in fields]
        values = dict(pairs)
        if len(values) != len(pairs) or set(values) != sample_names:
            return None, "观测信号重复、缺失或不属于端口契约"
        for name, value in values.items():
            if not _fits_width(value, ports[name]["width"]):
                return None, "观测位模式超出端口宽度"
        records.append({"sample": int(match[1]), "after_edge": int(match[2]),
                        "inputs": {name: values[name] for name in input_names},
                        "_actual": values[output["name"]]})
    if (not records or records[-1]["sample"] != observation["sample"]
            or records[-1]["inputs"] != observation["stimulus"]
            or records[-1]["_actual"] != actual[2]):
        return None, "首个 FAIL 未绑定同一输入/实际输出的 SAMPLE"
    if clock:
        starts = [index for index, record in enumerate(records)
                  if _HEX.fullmatch(record["inputs"][reset["name"]])
                  and int(record["inputs"][reset["name"]], 16) == reset["active"]
                  and (record["after_edge"] == 1 or asynchronous)]
        if not starts:
            return None, "历史中没有实际生效的复位观测"
        records = records[starts[-1]:]
    else:
        records = records[-1:]
    if len(records) > 64:
        return None, "从最近有效复位到失配超过64条观测，不能截断推导"
    for index, record in enumerate(records):
        if any(not _HEX.fullmatch(value) for value in record["inputs"].values()):
            return None, "重放历史含未知输入"
        if index and record["sample"] != records[index - 1]["sample"] + 1:
            return None, "复位至失配的观测历史不连续"
        if not clock and record["after_edge"] != 0:
            return None, "组合电路观测含时钟沿"
        if clock and record["after_edge"] == 0:
            if not asynchronous or int(record["inputs"][reset["name"]], 16) != reset["active"]:
                return None, "沿前观测不是有效异步复位"
            if index + 1 < len(records):
                following = records[index + 1]
                if following["after_edge"] != 1 or following["inputs"] != record["inputs"]:
                    return None, "异步复位沿前/沿后观测不成对"
    history = [{key: value for key, value in record.items() if key != "_actual"} for record in records]
    clean_control = lambda control, keys: {key: control[key] for key in keys} if control else None
    payload = {
        "sampling": {"clock": clean_control(clock, ("name", "edge")),
                     "reset": clean_control(reset, ("name", "active")),
                     "async_reset": clean_control(asynchronous, ("name", "active"))},
        "inputs": [{key: ports[name][key] for key in ("name", "width", "signed")} for name in input_names],
        "target": {"sample": observation["sample"],
                   "output": {key: output[key] for key in ("name", "width", "signed")}},
        "history": history,
    }
    if len(json.dumps(payload, ensure_ascii=False)) > 24_000:
        return None, "重放上下文超出24000字符限制"
    return payload, ""


def parse_witness(text: str, observation: dict, *, target: dict | None = None) -> dict:
    """模型只给独立期望；程序推导归因标签，仍不声称语义已获证明。"""
    if not isinstance(text, str) or len(text) > 16_000 or not isinstance(observation, dict):
        return _uncertain("盲复核回复或实际观测无效")
    cleaned = strip_think(text).strip()
    fenced = re.fullmatch(r"```(?:json)?\s*\n(.*?)\n?\s*```", cleaned, re.S | re.I)
    if fenced:
        cleaned = fenced[1].strip()
    try:
        result = json.loads(cleaned)
    except (ValueError, TypeError):
        return _uncertain("盲复核回复不是完整 JSON")
    if not isinstance(result, dict):
        return _uncertain("盲复核回复必须为对象")
    reason, rule = result.get("reason"), result.get("spec_rule")
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 2000:
        return _uncertain("盲复核缺少有界理由")
    if result.get("status") == "uncertain":
        return _uncertain(reason.strip())
    if result.get("status") != "derived" or not isinstance(rule, str) or not rule.strip() or len(rule) > 2000:
        return _uncertain("盲复核未给出明确期望与题面依据")
    actual = _FIELD.fullmatch(observation.get("observed", "")) if isinstance(observation.get("observed"), str) else None
    oracle = _FIELD.fullmatch(observation.get("testbench_expected", "")) if isinstance(observation.get("testbench_expected"), str) else None
    expected = result.get("expected")
    if (actual is None or oracle is None or actual[1] != oracle[1]
            or type(observation.get("sample")) is not int or observation["sample"] < 1
            or type(result.get("sample")) is not int or result["sample"] != observation["sample"]
            or result.get("output") != actual[1] or not isinstance(observation.get("stimulus"), dict)):
        return _uncertain("盲复核未对应实际失配采样点与输出")
    if (not isinstance(expected, str) or not 1 <= len(expected) <= 1024 or not _HEX.fullmatch(expected)
            or not _HEX.fullmatch(oracle[2])):
        return _uncertain("独立期望或测试台期望含未知态/无效位模式")
    if target is not None:
        output = target.get("output") if isinstance(target, dict) else None
        if (not isinstance(output, dict) or output.get("name") != actual[1]
                or type(target.get("sample")) is not int or target["sample"] != observation["sample"]
                or type(output.get("width")) is not int or not 1 <= output["width"] <= 4096):
            return _uncertain("盲复核目标与已绑定观测不一致")
        if any(not _fits_width(value, output["width"]) for value in (expected, actual[2], oracle[2])):
            return _uncertain("盲复核位模式超出目标端口宽度")
    unknown_actual = _HEX.fullmatch(actual[2]) is None
    if unknown_actual and target is None:
        return _uncertain("未知输出缺少已验证上下文的目标端口契约")
    inferred, tb_expected = int(expected, 16), int(oracle[2], 16)
    observed = None if unknown_actual else int(actual[2], 16)
    # Known independent expectation agreeing with the oracle can identify an
    # uninitialized DUT. Two disagreeing expectations still cannot blame it.
    if inferred == tb_expected and (unknown_actual or inferred != observed):
        verdict = "dut_error"
    elif not unknown_actual and inferred == observed and inferred != tb_expected:
        verdict = "testbench_error"
    else:
        return _uncertain("独立期望未与失配双方中的一方一致，不能确定归因")
    return {"verdict": verdict, "reason": reason.strip(), "spec_rule": rule.strip(),
            "evidence": {"sample": observation["sample"], "stimulus": observation["stimulus"],
                         "expected": actual[1] + "=" + expected,
                         "observed": observation["observed"],
                         "testbench_expected": observation["testbench_expected"]},
            "observation_bound": True, "semantic_verified": False, "method": "blind_input_replay"}
