"""把模型提供的参考算法装入固定测试台；不包含任何题目的硬件答案。

声明、单步时钟、检查和结束流程由此模块负责。参考算法仍由模型仅依据
规格编写，可能有语义错误，因此通过结果始终只是自检证据。
"""
from __future__ import annotations

import json
import re
from copy import deepcopy

from .interface import check_interface, specification_ports, strip_think, without_comments


class PlanError(ValueError):
    """验证计划结构不完整、越界或不受当前单时钟模板支持。"""


IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z_0-9]*\Z")
DECLARATIONS = r"\b(?:reg|wire|logic|bit|integer|int|longint|shortint|byte|time|real|genvar|parameter|localparam)\b"
CONTROL = r"\b(?:module|endmodule|task|endtask|function|endfunction|initial|always\w*|assign|force|release|fork|join\w*|disable|wait|forever|while)\b"
EXPRESSION_FUNCTIONS = frozenset({"signed", "unsigned", "clog2"})


def _name(value, label):
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value) or value.startswith("__va_"):
        raise PlanError(f"{label}: 必须为普通非保留标识符")
    return value


def _integer(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        raise PlanError(f"{label}: 要求 {low}..{high} 的整数")
    return value


def _fragment(value, label, *, outputs=(), ports=(), random=False, expression=False):
    if expression and type(value) is int:
        value = str(value)
    if not isinstance(value, str) or len(value) > 16000:
        raise PlanError(f"{label}: 要求紧凑字符串")
    clean = without_comments(value)
    # 字符串、预处理器和层次访问不属于参考算法片段；防止逃逸模板或伪造 PASS。
    if re.search(r'["`@#]|[A-Za-z_]\w*\s*\.', clean):
        raise PlanError(f"{label}: 禁止字符串、预处理、时序或层次访问")
    if re.search(DECLARATIONS + "|" + CONTROL, clean):
        raise PlanError(f"{label}: 声明放在 variables 中，片段不能自建进程或任务")
    allowed = EXPRESSION_FUNCTIONS | ({"random"} if random else set())
    forbidden = set(re.findall(r"\$(\w+)", clean)) - allowed
    if forbidden:
        raise PlanError(f"{label}: 含未允许的系统任务 {sorted(forbidden)}；允许 {sorted(allowed)}")
    if re.search(r"\bRTL_AGENT_\w*", clean):
        raise PlanError(f"{label}: 不能提供通过/失败标记")
    read_outputs = [name for name in outputs if re.search(rf"\b{re.escape(name)}\b", clean)]
    if read_outputs:
        raise PlanError(f"{label}: 参考算法不能读取 DUT 输出 {read_outputs}；用输入和独立参考状态推导")
    if re.search(r"\+\+|--", clean) or (not expression and "<=" in clean):
        raise PlanError(f"{label}: 语句使用阻塞赋值与显式加减；表达式才允许 <= 比较")
    assignments = re.findall(r"\b([A-Za-z_]\w*)\s*(?:\[[^;\n]*?\]\s*)?(?:=(?!=)|[+*/%&|^-]=)", clean)
    if any(name in ports or not name.startswith(("ref_", "stim_")) for name in assignments):
        raise PlanError(f"{label}: 只能写 ref_ / stim_ 私有变量")
    if expression and (assignments or re.search(r";|\b(?:begin|end|for|if|else|case|endcase)\b", clean)):
        raise PlanError(f"{label}: 要求单个表达式")
    return value.strip()


def _references(value, allowed, label):
    """只核对符号是否存在，不猜测中间结果位宽或算法含义。"""
    clean = re.sub(r"(?:\d+)?'[sS]?[bBoOdDhH][0-9a-fA-F_xXzZ?]+|'[01xXzZ]", "0", without_comments(value))
    names = set(re.findall(r"\b[A-Za-z_]\w*\b", clean))
    unknown = names - set(allowed) - EXPRESSION_FUNCTIONS - {"random"}
    if unknown:
        raise PlanError(f"{label}: 未声明的符号 {', '.join(sorted(unknown))}")


def plan_contract(specification: str, interface: str, top: str) -> dict:
    ports = specification_ports(specification, interface, top)
    contract = {"ports": ports, "ports_fixed": ports is not None,
                "expression_functions": ["$" + name for name in sorted(EXPRESSION_FUNCTIONS)]}
    if ports is not None:
        # 空字符串只是待填写的形状，不能作为有效刺激；时钟由题意确定后再排除。
        contract["values_template"] = {p["name"]: "" for p in ports if p["direction"] == "input"}
        contract["forbidden_reference_names"] = [p["name"] for p in ports if p["direction"] == "output"]
    return contract


def _exact_keys(value, names, label):
    if not isinstance(value, dict):
        raise PlanError(label + " 必须为按端口名填写的对象")
    expected, actual = set(names), set(value)
    if actual != expected:
        raise PlanError(f"{label}: 键必须精确覆盖端口；缺少 {sorted(expected-actual)}；"
                        f"多余 {sorted(actual-expected)}；要求 {list(names)}")


def _temporary_names(plan, ports):
    """紧凑声明已明确变量角色，只做无冲突的 alpha-renaming，不猜算法。

    不改刺激、状态角色、位宽或运算；旧 variables/advance 格式保持严格读取。
    数字字面量和注释按完整词法片段保留，避免把 8'hff 中的 hff 当变量。
    """
    if "temporaries" not in plan:
        return plan
    records = plan["temporaries"]
    states = plan.get("states", [])
    if not isinstance(records, list) or not isinstance(states, list):
        raise PlanError("temporaries/states 必须为列表")
    port_names = {p["name"] for p in ports}
    state_names = {_name(v.get("name"), "state") for v in states if isinstance(v, dict)}
    occupied = port_names | state_names | {"old_" + name for name in state_names}
    aliases, declared, targets = {}, set(), set()
    for item in records:
        if not isinstance(item, dict):
            raise PlanError("temporary 必须为对象")
        name = _name(item.get("name"), "temporary")
        # 保留名字不能变成普通变量来绕过函数、进程或输出检查。
        if (name in occupied or name in declared or name.startswith(("old_", "RTL_AGENT_"))
                or name in EXPRESSION_FUNCTIONS | {"random"}
                or re.fullmatch(DECLARATIONS + "|" + CONTROL + r"|begin|end|for|if|else|case|endcase", name)):
            raise PlanError("temporary 名称与端口/状态/保留名冲突或重复：" + name)
        target = name if name.startswith("stim_") else "stim_" + name
        if target in occupied or target in targets:
            raise PlanError("temporary 规范化后的名称冲突：" + target)
        declared.add(name)
        targets.add(target)
        if target != name:
            aliases[name] = target
    if not aliases:
        return plan
    # 将注释、字面量、系统函数视为一个整体；只替换普通标识符 token。
    tokens = re.compile(r"//[^\n]*|/\*.*?\*/|(?:[0-9][0-9_]*\s*)?'\s*[sS]?[bBoOdDhH]\s*[0-9a-fA-F_xXzZ?]+"
                        r"|'[01xXzZ]|[0-9][0-9_]*(?:\.[0-9][0-9_]*)?(?:[eE][+-]?[0-9][0-9_]*)?"
                        r"|\$[A-Za-z_]\w*|[A-Za-z_]\w*", re.S)

    def expression(value):
        return tokens.sub(lambda m: aliases.get(m[0], m[0]), value) if isinstance(value, str) else value

    normalized = deepcopy(plan)
    for item in normalized["temporaries"]:
        item["name"] = aliases.get(item["name"], item["name"])
        if "expr" in item:
            item["expr"] = expression(item["expr"])
    for item in [*normalized["temporaries"], *normalized.get("states", [])]:
        if not isinstance(item, dict):
            continue
        for key in ("initial", "next"):
            if key in item:
                item[key] = expression(item[key])
        if isinstance(item.get("writes"), list):
            for write in item["writes"]:
                if isinstance(write, dict):
                    for key in ("index", "value", "when"):
                        if key in write:
                            write[key] = expression(write[key])
    if isinstance(normalized.get("expected"), dict):
        normalized["expected"] = {name: expression(value) for name, value in normalized["expected"].items()}
    return normalized


def _compact_records(plan):
    """将紧凑声明规范化一次；旧计划和新计划共用同一个编译/执行流程。"""
    if not {"states", "temporaries"} & plan.keys():
        return plan
    if {"variables", "advance"} & plan.keys():
        raise PlanError("states/temporaries 不能混用旧 variables/advance")
    variables, temporary, updates, writes = [], {}, {}, []
    for field, prefix in (("temporaries", "stim_"), ("states", "ref_")):
        records = plan.get(field, [])
        if not isinstance(records, list) or len(records) > 64:
            raise PlanError(field + " 必须为最多64项的列表")
        for item in records:
            if not isinstance(item, dict) or not _name(item.get("name"), field).startswith(prefix):
                raise PlanError(field + " 的名称必须以 " + prefix + " 开头")
            name = item["name"]
            _integer(item.get("width"), 1, 4096, name + ".width")
            variables.append({key: item[key] for key in ("name", "width", "signed", "depth", "initial") if key in item})
            if field == "temporaries":
                if item.get("depth", 1) != 1:
                    raise PlanError("temporary 必须为标量；数组只用于 states")
                temporary[name] = item.get("expr")
            elif item.get("depth", 1) == 1:
                if "writes" in item:
                    raise PlanError("标量 state 使用 next；数组使用 writes")
                updates[name] = item.get("next")
            else:
                if "next" in item or not isinstance(item.get("writes"), list):
                    raise PlanError("数组 state 要求 writes 列表，不能使用 next")
                for write in item["writes"]:
                    if not isinstance(write, dict) or "array" in write:
                        raise PlanError("state.writes 仅填写 index/value/when，数组名称由所属 state 决定")
                    writes.append({**write, "array": name})
    return {**{key: value for key, value in plan.items() if key not in ("states", "temporaries")},
            "variables": variables, "advance": {"temporary": temporary, "next": updates, "writes": writes}}


def _parse_reply(reply):
    text = strip_think(reply).strip()
    fenced = re.fullmatch(r"```(?:json)?\s*\n(.*?)\n?```", text, re.S | re.I)
    if fenced:
        text = fenced[1].strip()
    try:
        plan = json.loads(text)
    except (ValueError, TypeError) as exc:
        raise PlanError("未得到完整 JSON 验证计划") from exc
    if not isinstance(plan, dict):
        raise PlanError("验证计划必须为对象")
    return plan


def _ports(ports):
    if not isinstance(ports, list) or not 1 <= len(ports) <= 64:
        raise PlanError("ports 必须包含 1..64 个端口")
    normalized = []
    names = set()
    for port in ports:
        if not isinstance(port, dict):
            raise PlanError("port 必须为对象")
        name = _name(port.get("name"), "port name")
        if name in names:
            raise PlanError("端口重复")
        names.add(name)
        direction = port.get("direction")
        if direction not in ("input", "output"):
            raise PlanError("当前模板只支持 input/output，inout 需要独立验证")
        width = _integer(port.get("width"), 1, 4096, "port width")
        signed = port.get("signed", False)
        if type(signed) is not bool:
            raise PlanError("signed 必须是布尔值")
        normalized.append(dict(name=name, direction=direction, width=width, signed=signed))
    ports = normalized
    outputs = [p for p in ports if p["direction"] == "output"]
    if not outputs:
        raise PlanError("至少需要一个受检输出")
    return ports


def _controls(plan, ports):
    clock = plan.get("clock")
    if clock is not None:
        if not isinstance(clock, dict) or clock.get("edge") not in ("posedge", "negedge"):
            raise PlanError("clock 要求 name 和 posedge/negedge")
        if not any(p["name"] == clock.get("name") and p["direction"] == "input" and p["width"] == 1 for p in ports):
            raise PlanError("clock 必须为 1 位输入")
    reset = plan.get("async_reset")
    reference_reset = plan.get("reset", reset)
    for label, control in (("async_reset", reset), ("reset", reference_reset)):
        if control is not None and (not clock or not isinstance(control, dict)
                or type(control.get("active")) is not int or control["active"] not in (0, 1)
                or not any(p["name"] == control.get("name") and p["direction"] == "input" and p["width"] == 1 for p in ports)
                or control["name"] == clock["name"]):
            raise PlanError(label + " 要求单时钟下独立的1位输入和 active:0/1")
    if reset and (reference_reset is None or reference_reset["name"] != reset["name"] or reference_reset["active"] != reset["active"]):
        raise PlanError("异步复位的 reset 与 async_reset 必须一致")
    return clock, reset, reference_reset


def _variables(variables, ports):
    names = {p["name"] for p in ports}
    outputs = [p for p in ports if p["direction"] == "output"]
    if not isinstance(variables, list) or len(variables) > 64:
        raise PlanError("variables 必须为有界列表")
    private = []
    for variable in variables:
        if not isinstance(variable, dict):
            raise PlanError("variable 必须为对象")
        name = _name(variable.get("name"), "variable name")
        if name in names or not name.startswith(("ref_", "stim_")):
            raise PlanError("私有变量须以 ref_ / stim_ 开头且不能重名")
        names.add(name)
        width = _integer(variable.get("width", 32), 1, 4096, "variable width")
        depth = _integer(variable.get("depth", 1), 1, 4096, "variable depth")
        signed = variable.get("signed", False)
        if type(signed) is not bool:
            raise PlanError("signed 必须是布尔值")
        initial = _fragment(variable.get("initial", "0"), "initial", expression=True,
                            outputs=[p["name"] for p in outputs], ports=[p["name"] for p in ports])
        if any(re.search(rf"\b{re.escape(p['name'])}\b", initial) for p in ports):
            raise PlanError("参考变量初值不能依赖 DUT 端口")
        _references(initial, (), "initial")
        private.append(dict(name=name, width=width, depth=depth, signed=signed, initial=initial))
    return private


def _advance(raw_advance, private, out_names, port_names, reference_reset):
    native = isinstance(raw_advance, dict)
    if native:
        states = {v["name"]: v for v in private if v["name"].startswith("ref_")}
        temps = {v["name"]: v for v in private if v["name"].startswith("stim_")}

        def expression(value, label):
            value = _fragment(value, label, outputs=out_names, ports=port_names, expression=True)
            if not value:
                raise PlanError(label + " 不能为空")
            _references(value, [*port_names, *states, *temps, *("old_" + name for name in states)], label)
            for name in states:
                value = re.sub(rf"\b{re.escape(name)}\b", "old_" + name, value)
            return value

        temporary, updates = raw_advance.get("temporary", {}), raw_advance.get("next", {})
        writes = raw_advance.get("writes", [])
        if not isinstance(temporary, dict) or not isinstance(updates, dict) or not isinstance(writes, list) or len(writes) > 32:
            raise PlanError("advance 要求 temporary/next 映射和有界 writes 列表")
        if set(temporary) - temps.keys() or any(temps[name]["depth"] != 1 for name in temporary):
            raise PlanError("temporary 目标必须为已声明的标量 stim_ 变量")
        if set(updates) - states.keys() or any(states[name]["depth"] != 1 for name in updates):
            raise PlanError("next 目标必须为已声明的标量 ref_ 状态；数组使用 writes")
        algorithm = []
        initialized = set()
        for name, value in temporary.items():
            value = expression(value, "temporary." + name)
            referenced = set(re.findall(r"\bstim_\w*\b", value))
            if referenced - initialized:
                raise PlanError("temporary 表达式只能读取已计算的临时量：" + ", ".join(sorted(referenced - initialized)))
            algorithm.append(name + " = " + value + ";")
            initialized.add(name)
        for name, state in states.items():
            if state["depth"] > 1:
                algorithm.append(_assign(state, "__va_next_" + name, "old_" + name, indexed=True))
            else:
                algorithm.append(f'__va_next_{name} = ' + expression(updates.get(name, name), "next." + name) + ";")
        for write in writes:
            if not isinstance(write, dict) or write.get("array") not in states or states[write["array"]]["depth"] < 2:
                raise PlanError("writes 目标必须为已声明的 ref_ 数组")
            when = expression(write.get("when", "1'b1"), "write.when")
            index = expression(write.get("index"), "write.index")
            value = expression(write.get("value"), "write.value")
            algorithm.append(f'if ({when}) __va_next_{write["array"]}[{index}] = {value};')
        commit, reset_lines = [], []
        for name, state in states.items():
            commit.append(_assign(state, name, "__va_next_" + name, indexed=True))
            reset_lines.append(_assign(state, name, state["initial"]))
        if reference_reset:
            algorithm += [f'if ({reference_reset["name"]} === 1\'b{reference_reset["active"]}) begin',
                          *reset_lines, "end else begin", *commit, "end"]
        else:
            algorithm += commit
        advance = "\n".join(algorithm)
    else:
        advance = _fragment(raw_advance, "advance", outputs=out_names, ports=port_names)
        # 兼容旧计划；原生 next 映射由程序同时提交，不要求模型手写快照名称。
        reads = re.sub(r"\bref_\w*\s*(\[[^;\n]*?\]\s*)?=(?!=)",
                       lambda match: (match[1] or "") + "=", without_comments(advance))
        if re.search(r"\bref_\w*\b", reads):
            raise PlanError("advance 读取旧状态使用 old_ref_ 前缀；ref_ 只作为更新目标")
    return advance, native


def _expected(expected, out_names, port_names, private):
    _exact_keys(expected, out_names, "expected")
    expected = {name: _fragment(value, "expected." + name, outputs=out_names, ports=port_names, expression=True)
                for name, value in expected.items()}
    if any(not value for value in expected.values()):
        raise PlanError("期望表达式不能为空")
    names = [*port_names, *(v["name"] for v in private), *("old_" + v["name"] for v in private if v["name"].startswith("ref_"))]
    for name, value in expected.items():
        _references(value, names, "expected." + name)
    return expected


def _stimulus(raw_stimulus, ports, clock, out_names, port_names):
    inputs = [p for p in ports if p["direction"] == "input" and (not clock or p["name"] != clock["name"])]
    if isinstance(raw_stimulus, dict):
        directed = raw_stimulus.get("directed", [])
        if not isinstance(directed, list) or len(directed) > 24:
            raise PlanError("directed 要求最多24组有界向量，重复使用 repeat")

        def vector(values, label):
            if isinstance(values, dict):
                _exact_keys(values, [p["name"] for p in inputs], label)
                values = [values[p["name"]] for p in inputs]
            if not isinstance(values, list) or len(values) != len(inputs):
                raise PlanError(f"{label}: step 向量参数数目必须匹配非时钟输入 {[p['name'] for p in inputs]}")
            expressions = []
            for port, value in zip(inputs, values):
                if type(value) is int:
                    value = str(value)
                field = label + "." + port["name"]
                expression = _fragment(value, field, outputs=out_names,
                                       ports=port_names, random=True, expression=True)
                if (not expression or re.search(r"\b(?:ref_|stim_|old_ref_)\w*\b", expression)
                        or any(re.search(rf"\b{re.escape(name)}\b", expression) for name in port_names)
                        or any(name not in ("__va_index", "__va_seed")
                               for name in re.findall(r"\b__va_\w*\b", expression))):
                    raise PlanError(field + ": 刺激表达式仅使用常量、__va_index 和 $random(__va_seed)")
                _references(expression, ("__va_index", "__va_seed"), field)
                expressions.append(expression)
            return "step(" + ", ".join(expressions) + ");"

        blocks = []
        for index, item in enumerate(directed):
            if not isinstance(item, dict):
                raise PlanError("directed 元素要求 values/repeat 对象")
            count = _integer(item.get("repeat", 1), 1, 128, "repeat")
            blocks.append(f"for (__va_repeat=0; __va_repeat<{count}; __va_repeat=__va_repeat+1) begin\n"
                          + vector(item.get("values"), f"stimulus.directed[{index}].values") + "\nend")
        random = raw_stimulus.get("random")
        if not isinstance(random, dict):
            raise PlanError("stimulus.random 要求 cycles/values 对象")
        cycles = _integer(random.get("cycles"), 64, 256, "random cycles")
        blocks.append(f"for (__va_index=0; __va_index<{cycles}; __va_index=__va_index+1) begin\n"
                      + vector(random.get("values"), "stimulus.random.values") + "\nend")
        stimulus = "\n".join(blocks)
    else:
        # 保留已保存 V4 计划/受控回归的读取兼容；新模型调用只要求数据向量。
        stimulus = _fragment(raw_stimulus, "stimulus", outputs=out_names, ports=port_names, random=True)
    # 激励只能通过 step 调度，不直接读取或写入端口、时钟或参考状态。
    if not re.search(r"\bstep\s*\(", without_comments(stimulus)):
        raise PlanError("stimulus 必须调用 step")
    if not isinstance(raw_stimulus, dict) and any(re.search(rf"\b{re.escape(name)}\b", without_comments(stimulus)) for name in port_names):
        raise PlanError("stimulus 通过 step 参数驱动端口，不直接访问端口")
    if re.search(r"\bref_\w*\b", without_comments(stimulus)):
        raise PlanError("stimulus 不能干预参考状态")
    return stimulus


def _auto_stimulus(raw, ports, clock, reset):
    """显式选择 auto 时，生成与题号/算法无关的有界输入。

    只负责位模式和调度，不生成参考答案。旧显式向量仍严格检查，不补缺键。
    专有时序由模型追加 directed；其缺省输入明确为零、复位无效。
    """
    if not isinstance(raw, dict) or raw.get("mode") != "auto":
        return raw
    if set(raw) - {"mode", "cycles", "directed"}:
        raise PlanError("auto stimulus 只接受 mode/cycles/directed")
    cycles = _integer(raw.get("cycles", 64), 64, 256, "auto cycles")
    inputs = [p for p in ports if p["direction"] == "input" and (not clock or p["name"] != clock["name"])]
    defaults = {p["name"]: str(1-reset["active"]) if reset and p["name"] == reset["name"] else "0"
                for p in inputs}
    directed = []
    # 零、全一、单低位、符号边界两侧、交替位；覆盖所有声明位宽。
    for pattern in range(7):
        values = dict(defaults)
        for port in inputs:
            name, width = port["name"], port["width"]
            if reset and name == reset["name"]:
                continue
            mask = (1 << width) - 1
            alternating = int("10" * ((width + 1) // 2), 2) & mask
            number = (0, mask, 1, 1 << (width-1), (1 << (width-1))-1,
                      alternating, alternating ^ mask)[pattern]
            values[name] = f"{width}'h{number:x}"
        directed.append({"values": values})
    extra = raw.get("directed", [])
    if not isinstance(extra, list) or len(extra) > 17:
        raise PlanError("auto directed 最多17组，连同7组通用边界不超过24组")
    for i, item in enumerate(extra):
        if not isinstance(item, dict) or set(item) - {"values", "repeat"} or not isinstance(item.get("values"), dict):
            raise PlanError(f"auto directed[{i}] 要求 values 对象和可选 repeat")
        if set(item["values"]) - defaults.keys():
            raise PlanError(f"auto directed[{i}] 只能覆盖非时钟输入 {list(defaults)}")
        directed.append({"values": {**defaults, **item["values"]}, "repeat": item.get("repeat", 1)})
    values = {}
    for port in inputs:
        name, width = port["name"], port["width"]
        if reset and name == reset["name"]:
            values[name] = f"(__va_index % 17 == 16) ? {reset['active']} : {1-reset['active']}"
        else:
            # $random 是32位；拼接足够字数，避免宽输入高位只有符号扩展。
            words = (width + 31) // 32
            values[name] = "$random(__va_seed)" if words == 1 else "{" + ", ".join(["$random(__va_seed)"] * words) + "}"
    return {"directed": directed, "random": {"cycles": cycles, "values": values}}


def _typed(item):
    return ("signed " if item["signed"] else "") + f'[{item["width"]-1}:0] '


def _assign(variable, target, value, *, indexed=False):
    """共享数组复制/初始化循环，避免快照、提交、复位三处漂移。"""
    if variable["depth"] == 1:
        return f"{target} = {value};"
    suffix = "[__va_init]" if indexed else ""
    return (f'for (__va_init=0; __va_init<{variable["depth"]}; __va_init=__va_init+1) '
            f'{target}[__va_init] = {value}{suffix};')


def _render(top, ports, outputs, private, clock, reset, reference_reset, advance, expected, stimulus, native):
    lines = ['`timescale 1ns/1ps', 'module tb;']
    for p in ports:
        lines.append(("reg " if p["direction"] == "input" else "wire ") + _typed(p) + p["name"] + ";")
    for p in outputs:
        lines.append("reg " + _typed(p) + "__va_expected_" + p["name"] + ";")
    for v in private:
        prefixes = [""]
        if v["name"].startswith("ref_"):
            prefixes.append("old_")
            if native:
                prefixes.append("__va_next_")
        for prefix in prefixes:
            lines.append("reg " + _typed(v) + prefix + v["name"] + (f' [0:{v["depth"]-1}]' if v["depth"] > 1 else "") + ";")
    lines += ["integer __va_tests, __va_seed, __va_init, __va_index, __va_repeat;",
              top + " dut(" + ",".join(f'.{p["name"]}({p["name"]})' for p in ports) + ");",
              "task __va_check; input __va_after_edge; begin", "__va_tests = __va_tests + 1;"]
    inputs = [p for p in ports if p["direction"] == "input" and (not clock or p["name"] != clock["name"])]
    stimulus_fmt = " ".join(p["name"] + "=%h" for p in inputs)
    stimulus_args = "".join(", " + p["name"] for p in inputs)
    sample_fmt = " ".join(p["name"] + "=%h" for p in inputs + outputs)
    sample_args = "".join(", " + p["name"] for p in inputs + outputs)
    lines.append(f'$display("RTL_AGENT_SAMPLE sample=%0d after_edge=%0d {sample_fmt}", __va_tests, __va_after_edge{sample_args});')
    for p in outputs:
        name = p["name"]
        lines += [f"if ((^{name} === 1'bx) || (^__va_expected_{name} === 1'bx) || ({name} !== __va_expected_{name})) begin",
                  f'$display("RTL_AGENT_FAIL sample=%0d {stimulus_fmt} {name}=%h expected=%h", __va_tests{stimulus_args}, {name}, __va_expected_{name});',
                  "$finish; end"]
    lines += ["end endtask", "task step;"]
    for p in inputs:
        lines.append("input " + _typed(p) + "arg_" + p["name"] + ";")
    lines += ["begin"]
    for p in inputs:
        lines.append(p["name"] + " = arg_" + p["name"] + ";")
    lines += ["#2;"]
    for v in private:
        if v["name"].startswith("ref_"):
            lines.append(_assign(v, "old_" + v["name"], v["name"], indexed=True))
    lines.append(advance)
    lines += [f"__va_expected_{name} = ({expr});" for name, expr in expected.items()]
    if clock:
        active = 1 if clock["edge"] == "posedge" else 0
        if reset:
            lines.append(f'if ({reset["name"]} === 1\'b{reset["active"]}) __va_check(0);')
        lines += [f'{clock["name"]} = 1\'b{active};', "#1; __va_check(1);",
                  f'{clock["name"]} = 1\'b{1-active};', "#1;"]
    else:
        lines.append("#1; __va_check(0);")
    lines += ["end endtask", "initial begin", "__va_tests=0; __va_seed=137; __va_init=0; __va_index=0; __va_repeat=0;"]
    for p in ports:
        if p["direction"] == "input":
            initial = 1 if clock and p["name"] == clock["name"] and clock["edge"] == "negedge" else 0
            lines.append(p["name"] + f" = {initial};")
    for v in private:
        lines.append(_assign(v, v["name"], v["initial"]))
    if reference_reset:
        # 只使用计划声明的复位语义。先经过真实 DUT 复位，再比较模型刺激；
        # 参考变量的 Python/HDL 初值本身不能证明 DUT 已进入同一初态。
        values = [str(reference_reset["active"]) if p["name"] == reference_reset["name"] else "0"
                  for p in inputs]
        lines += ["// Establish the declared reset before the first functional stimulus.",
                  "step(" + ", ".join(values) + ");"]
    lines += [stimulus, 'if (__va_tests < 32) begin $display("RTL_AGENT_FAIL insufficient_checks=%0d", __va_tests); $finish; end',
              '$display("CHECKS=%0d", __va_tests);', '$display("RTL_AGENT_PASS"); $finish;',
              'end', 'initial begin #900000; $display("RTL_AGENT_FAIL timeout"); $finish; end', 'endmodule']
    return "\n".join(lines) + "\n"


def build_testbench(reply: str, top: str, specification: str = "", interface: str = "") -> tuple[str, dict]:
    """验证、规范化，再用同一个模板生成测试台；不读取 DUT 源码。"""
    _name(top, "top")
    source_plan = _parse_reply(reply)
    fixed = specification_ports(specification, interface, top)
    ports = _ports(source_plan.get("ports", fixed))
    if fixed and {p["name"]: p for p in ports} != {p["name"]: p for p in fixed}:
        raise PlanError("ports 与规格固定接口不一致；名称、方向、位宽及 signed 均不可改写")
    source_plan = _temporary_names(source_plan, ports)
    raw = _compact_records(source_plan)
    outputs = [p for p in ports if p["direction"] == "output"]
    out_names, port_names = [p["name"] for p in outputs], [p["name"] for p in ports]
    clock, reset, reference_reset = _controls(raw, ports)
    private = _variables(raw.get("variables", []), ports)
    raw_advance, raw_stimulus = raw.get("advance", ""), raw.get("stimulus")
    raw_stimulus = _auto_stimulus(raw_stimulus, ports, clock, reference_reset)
    advance, native = _advance(raw_advance, private, out_names, port_names, reference_reset)
    expected = _expected(raw.get("expected"), out_names, port_names, private)
    stimulus = _stimulus(raw_stimulus, ports, clock, out_names, port_names)
    signature = "module " + top + "(" + ",".join(
        p["direction"] + " " + _typed(p) + p["name"] for p in ports) + ");\nendmodule"
    ok, note = check_interface(signature, specification, interface, top)
    if not ok:
        raise PlanError("验证计划" + note)
    plan = dict(ports=ports, clock=clock, async_reset=reset, reset=reference_reset, variables=private,
                advance=raw_advance if native else advance, expected=expected,
                stimulus=raw_stimulus if isinstance(raw_stimulus, dict) else stimulus)
    if source_plan is not raw:
        plan = dict(source_plan, ports=ports, clock=clock, async_reset=reset, reset=reference_reset,
                    expected=expected, stimulus=raw_stimulus)
    return _render(top, ports, outputs, private, clock, reset, reference_reset,
                   advance, expected, stimulus, native), plan
