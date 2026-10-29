"""Bounded design-side behavior planning; no RTL generation or oracle execution.

The fixed main model supplies the plan. Validation establishes only the schema,
output bindings and size bounds; a valid plan can still misread the specification.
The independent testbench must never receive this design-side hypothesis.
"""
from __future__ import annotations

import json
import re

from .interface import strip_think


BEHAVIOR_PLAN = """你是 RTL 行为规划员。只读 specification 和固定接口/采样契约，先建立设计依据。
这是待核对的设计辅助，不是参考答案、测试台或功能证明；题面始终优先。不要输出 HDL、模块声明、命令或解释段落。
先定义每个跨拍状态的含义与复位值，再列出事件接受条件、旧状态到新状态的变化以及输出时刻。
条件判断使用沿前旧状态；本拍输入只计入一次。列全复位、无事件保持、各事件单独发生和同时发生，写明优先级。
对每个输出区分组合可见与寄存发布：完成事件前保持什么、完成沿后发布什么、下一拍如何处理。
使能暂停不等于所有输出都保持；复位对组合输出是否有影响必须来自题面。状态只保留一份权威含义。
不知道初态、事件关系或输出类型时明确写 unknown，不猜测常见电路行为，不使用题号或任何外部资料。
只输出完整紧凑 JSON，字段固定为：
{"states":[{"name":"状态名","meaning":"含义/合法范围","reset":"题面复位值或 unknown"}],
 "events":[{"when":"事件及接受条件","next":"用旧状态描述新状态/保持","outputs":"该事件后的发布/保持规则"}],
 "outputs":{"每个输出端口名":{"kind":"registered|combinational|unknown","rule":"该输出的来源、保持和可见时刻"}}}
states 最多16项，events 为1..24项；没有可确认的状态可用 states=[]。每段说明最多600字符。
states.name 使用唯一的 ASCII 标识符（字母或下划线开头，后续为字母、数字或下划线），最多64字符；含义用中文写在 meaning。
已知固定端口时 outputs 必须精确覆盖全部输出，不重复输入、端口类型或宽度；不能增加 ports 等其他字段。
使用简洁自然语言和数学关系，不写 Verilog 语句，不依据采样编号猜信号值。只做一次规划，不生成测试期望表。
"""


class BehaviorPlanError(ValueError):
    """The proposed design plan is incomplete or outside its bounded contract."""


_NAME = re.compile(r"[A-Za-z_][A-Za-z_0-9]*\Z")
_TIMING = re.compile(
    r"\b(?:posedge|negedge|rising[ -]+edge|falling[ -]+edge|positive[ -]+edge|negative[ -]+edge|"
    r"sequential|(?:d[ -]*)?flip[ -]*flops?|registered\s+(?:output|storage|slot|result))\b|"
    r"上升沿|下降沿|时序(?:逻辑|电路)?|寄存器", re.I)
_NEGATED = re.compile(r"\b(?:not|no|never|without|nonsequential|non-sequential)\b|"
                      r"不要|不得|无需|不使用|不含|无时钟|非时序|不是时序", re.I)
_HYPOTHETICAL = re.compile(r"\b(?:would|could|might|hypothetical|optional(?:ly)?)\b|假设|假如|若需", re.I)
_EXAMPLE_HEADING = re.compile(r"^\s*(?:for example|example(?:s)?|e\.g\.|例如|示例)\s*[:：]", re.I)
_INLINE_EXAMPLE = re.compile(r"(?:\bfor example\b|\be\.g\.|例如|示例\s*[:：])[^\n。;；]*", re.I)
_SOURCE_OR_COMMAND = re.compile(
    r"```|`include\b|\bendmodule\b|\bmodule\s+[A-Za-z_]\w*\s*(?:#\s*\(|\()|"
    r"\balways(?:_ff|_comb|_latch)?\s*(?:@|begin\b)|\binitial\s+begin\b|"
    r"\bassign\s+[A-Za-z_]\w*(?:\[[^\]]+\])?\s*=|"
    r"\b(?:reg|wire|logic)\s+(?:signed\s+)?(?:\[[^\]]+\]\s*)?[A-Za-z_]\w*\s*[,;=]|"
    r"\bif\s*\([^)]*\)\s*(?:begin\b|[A-Za-z_]\w*\s*<=)|"
    r"\$(?:system|fopen|readmem[hb]|writemem[hb])\b|\$\(|https?://|"
    r"\b(?:subprocess|urllib|requests)\s*\.|\b(?:import\s+os|from\s+os\s+import)\b|"
    r"(?:^|[\n;&|])\s*(?:bash|sh|cmd|powershell|curl|wget|python[0-9.]*|pip[0-9.]*|sudo|rm|git)\s+",
    re.I)


def needs_behavior_plan(specification: str) -> bool:
    """Trigger only on affirmative timing language, never on clock-like names.

    This is a routing hint, not a temporal parser. Ambiguous/negative/example
    clauses are deliberately omitted; the solver can still design directly.
    """
    if not isinstance(specification, str) or not specification or len(specification) > 100_000:
        return False
    lines = []
    example = False
    for line in specification.splitlines():
        if _EXAMPLE_HEADING.search(line):
            example = True
            continue
        if not line.strip():
            example = False
            continue
        if not example:
            lines.append(line)
    text = _INLINE_EXAMPLE.sub("", "\n".join(lines))
    for clause in re.split(r"[。;；\n]|(?<=[.!?])\s+", text):
        if (_TIMING.search(clause) and not _NEGATED.search(clause)
                and not _HYPOTHETICAL.search(clause)):
            return True
    return False


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise BehaviorPlanError("行为规划含重复 JSON 键：" + str(key)[:64])
        result[key] = value
    return result


def _keys(value, expected: set[str], label: str):
    if not isinstance(value, dict) or set(value) != expected:
        raise BehaviorPlanError(label + " 字段必须为 " + ", ".join(sorted(expected)))


def _text(value, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 600:
        raise BehaviorPlanError(label + " 要求1..600字符的说明；不确定时明确写 unknown")
    value = value.strip()
    if _SOURCE_OR_COMMAND.search(value):
        raise BehaviorPlanError(label + " 只接受行为说明，不接受 HDL、命令或外部访问")
    return value


def parse_behavior_plan(text: str, ports: list | None) -> dict:
    """Validate and normalize model prose; this does not validate its semantics."""
    if not isinstance(text, str) or not text or len(text) > 16_000:
        raise BehaviorPlanError("行为规划回复为空或超过16000字符")
    clean = strip_think(text).strip()
    fenced = re.fullmatch(r"```(?:json)?\s*\n(.*?)\n?\s*```", clean, re.I | re.S)
    if fenced:
        clean = fenced[1].strip()
    try:
        raw = json.loads(clean, object_pairs_hook=_object)
    except (ValueError, TypeError, RecursionError) as exc:
        if isinstance(exc, BehaviorPlanError):
            raise
        raise BehaviorPlanError("未得到完整 JSON 行为规划") from exc
    _keys(raw, {"states", "events", "outputs"}, "行为规划")
    states, events, outputs = raw["states"], raw["events"], raw["outputs"]
    if not isinstance(states, list) or len(states) > 16:
        raise BehaviorPlanError("states 必须为最多16项的列表")
    if not isinstance(events, list) or not 1 <= len(events) <= 24:
        raise BehaviorPlanError("events 必须为1..24项的列表")
    if not isinstance(outputs, dict) or not 1 <= len(outputs) <= 64:
        raise BehaviorPlanError("outputs 必须为1..64个输出端口的对象")
    normalized_states, names = [], set()
    for index, state in enumerate(states):
        label = f"states[{index}]"
        _keys(state, {"name", "meaning", "reset"}, label)
        name = state["name"]
        if not isinstance(name, str) or len(name) > 64 or not _NAME.fullmatch(name) or name in names:
            raise BehaviorPlanError(label + ".name 必须为唯一普通标识符，最多64字符")
        names.add(name)
        normalized_states.append({"name": name, "meaning": _text(state["meaning"], label+".meaning"),
                                  "reset": _text(state["reset"], label+".reset")})
    normalized_events = []
    for index, event in enumerate(events):
        label = f"events[{index}]"
        _keys(event, {"when", "next", "outputs"}, label)
        normalized_events.append({key: _text(event[key], label+"."+key)
                                  for key in ("when", "next", "outputs")})
    if ports is not None:
        if not isinstance(ports, list) or not 1 <= len(ports) <= 64:
            raise BehaviorPlanError("固定端口契约无效")
        port_names, output_names = set(), set()
        for port in ports:
            if (not isinstance(port, dict) or not isinstance(port.get("name"), str)
                    or not _NAME.fullmatch(port["name"]) or port["name"] in port_names
                    or port.get("direction") not in ("input", "output")):
                raise BehaviorPlanError("固定端口契约无效")
            port_names.add(port["name"])
            if port["direction"] == "output":
                output_names.add(port["name"])
        if set(outputs) != output_names:
            raise BehaviorPlanError("outputs 必须精确覆盖固定接口中的全部输出，不能增加输入或未知端口")
    normalized_outputs = {}
    for name, value in outputs.items():
        if not _NAME.fullmatch(name):
            raise BehaviorPlanError("输出端口名必须为普通标识符")
        _keys(value, {"kind", "rule"}, "outputs."+name)
        if value["kind"] not in ("registered", "combinational", "unknown"):
            raise BehaviorPlanError("outputs."+name+".kind 必须为 registered/combinational/unknown")
        normalized_outputs[name] = {"kind": value["kind"], "rule": _text(value["rule"], "outputs."+name+".rule")}
    return {"states": normalized_states, "events": normalized_events, "outputs": normalized_outputs}
