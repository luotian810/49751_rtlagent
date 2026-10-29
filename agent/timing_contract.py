"""Conservative checks for a clock edge explicitly named in the specification.

This is not a language/HDL parser or a functional proof. Ambiguous natural
language and structural/derived clocks are deliberately left to the HDL tools.
"""
from __future__ import annotations

import re


_IDENTIFIER = r"[A-Za-z_][A-Za-z_0-9]*"
_SIGNAL = rf"(?<![A-Za-z_0-9$])[`\"']?(?P<name>{_IDENTIFIER})[`\"']?(?![A-Za-z_0-9$.])"
_EDGE_PATTERNS = (
    re.compile(_SIGNAL + r"\s*(?:的\s*)?(?P<edge>上升沿|下降沿)", re.I),
    re.compile(r"(?P<edge>posedge|negedge)\s+(?:of\s+)?" + _SIGNAL, re.I),
    re.compile(r"(?P<edge>rising|positive|falling|negative)[ -]+edge\s+(?:of|on)\s+(?:the\s+)?(?:input\s+)?" + _SIGNAL, re.I),
    re.compile(_SIGNAL + r"(?:'s)?\s+(?P<edge>rising|positive|falling|negative)[ -]+edge", re.I),
)
_POSITIVE = {"posedge", "rising", "positive", "上升沿"}
_UNSAFE_CLAUSE = re.compile(r"\b(?:not|never|if|when|unless|assuming|suppose|may|might|could|either|"
                            r"unsupported|forbidden|invalid|incorrect|wrong|avoid|instead|rather|except|optional|perhaps|cannot)\b|"
                            r"\b\w+n't\b|不|勿|无需|无须|非(?:上升|下降)|如果|假设|若|当|只有|除非|或者|可能|错误|非法|禁止", re.I)
_EXAMPLE = re.compile(r"\bexamples?\b|\be\.g\.|例如|示例", re.I)
_RESET_CONTEXT = re.compile(r"\breset(?:s|ting)?\b|复位", re.I)
_MASK = re.compile(r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"', re.S)
_PROCESS = r"\balways(?:_ff|_comb|_latch)?\b"
# SystemVerilog may omit generate/endgenerate. Detect conditional process
# regions conservatively, without deciding their constant conditions. Named
# blocks/genvar also require scope/elaboration beyond this text check.
_IMPLICIT_GENERATE = re.compile(
    r"\bgenvar\b|\bbegin\s*:\s*" + _IDENTIFIER + r"\b|"
    r"\bif\s*\([^;]*?\)\s*(?:" + _PROCESS +
    r"|begin\b(?:(?!\bend\b)[\s\S])*?" + _PROCESS + r")|"
    r"\bcase[xz]?\s*\([^;]*?\)(?:(?!\bendcase\b)[\s\S])*?" + _PROCESS)


def clock_contract(specification: str, ports: list | None) -> dict | None:
    """Extract one unambiguous named 1-bit input edge, never infer by its name."""
    if not isinstance(specification, str) or not isinstance(ports, list):
        return None
    candidates = {p.get("name") for p in ports if isinstance(p, dict)
                  and p.get("direction") == "input" and type(p.get("width")) is int
                  and p["width"] == 1 and isinstance(p.get("name"), str)}
    found: dict[tuple[str, str], str] = {}
    mentions = set()
    fenced = example = False
    for line in specification.splitlines():
        if re.match(r"\s*```", line):
            fenced = not fenced
            continue
        if not line.strip():
            example = False
        if fenced:
            continue
        if _EXAMPLE.search(line):
            example = True
        if example:
            continue
        for clause in re.split(r"[。;!?\n]|\.(?=\s|$)", line):
            for pattern in _EDGE_PATTERNS:
                for match in pattern.finditer(clause):
                    if match["name"] not in candidates:
                        continue
                    # A reset assertion edge is not a sampling-clock contract.
                    # Inspect prose outside the matched edge/signal phrase, so
                    # port spelling alone (e.g. a port named reset) is no hint.
                    context = clause[:match.start()] + clause[match.end():]
                    if _RESET_CONTEXT.search(context):
                        continue
                    edge = "posedge" if match["edge"].lower() in _POSITIVE else "negedge"
                    mentions.add((match["name"], edge))
                    if not _UNSAFE_CLAUSE.search(clause):
                        found.setdefault((match["name"], edge), clause.strip())
    if len(found) != 1 or len(mentions) != 1:
        return None
    (name, edge), quote = next(iter(found.items()))
    return {"name": name, "edge": edge, "source_quote": quote}


def _top_body(masked: str, top: str) -> tuple[str, int] | None:
    blocks = []
    opened = None
    for token in re.finditer(r"\b(?:module|endmodule)\b", masked):
        if token[0] == "module":
            if opened is not None:
                return None
            declaration = re.match(r"module\s+(?:(?:automatic|static)\s+)?(" + _IDENTIFIER + r")\b", masked[token.start():])
            if declaration is None:
                return None
            opened = (declaration[1], token.start())
        else:
            if opened is None:
                return None
            if opened[0] == top:
                start = masked.find(";", opened[1], token.start())
                if start < 0:
                    return None
                blocks.append((masked[start + 1:token.start()], start + 1))
            opened = None
    return blocks[0] if opened is None and len(blocks) == 1 else None


def check_clock_contract(code: str, top: str, contract: dict | None) -> tuple[bool, str]:
    """Check direct top-level event controls; return explicit not_checked on ambiguity."""
    if contract is None:
        return True, "not_checked: 规格未直接确定单时钟采样沿"
    if (not isinstance(contract, dict) or contract.get("edge") not in ("posedge", "negedge")
            or not isinstance(contract.get("name"), str)
            or re.fullmatch(_IDENTIFIER, contract["name"]) is None):
        return True, "not_checked: 无有效的直接采样沿契约"
    masked = _MASK.sub(lambda m: re.sub(r"[^\n]", " ", m[0]), code)
    if "`" in masked or "\\" in masked:
        return True, "not_checked: 宏或转义标识符需要完整 HDL 工具解析"
    block = _top_body(masked, top)
    if block is None:
        return True, "not_checked: 无法可靠确定唯一完整顶层模块"
    body, offset = block
    # A text scan cannot tell which parameterized branch is elaborated. Opposite
    # edges in an inactive branch must not reject a legal implementation.
    if re.search(r"\b(?:generate|endgenerate)\b", body):
        return True, "not_checked: generate 分支需要完整 HDL 展开后判断"
    if _IMPLICIT_GENERATE.search(body):
        return True, "not_checked: 隐式 generate 或命名作用域需要完整 HDL 展开后判断"
    name, expected = contract["name"], contract["edge"]
    events = []
    complex_clock = False
    controls = list(re.finditer(r"\b(?:always(?:_ff|_comb|_latch)?|initial)\s*@\s*(\([^()]*\)|\*)", body))
    for control in controls:
        text = control[1]
        if text == "*" or re.fullmatch(r"\(\s*\*\s*\)", text):
            continue
        # Unknown event expressions (iff, computed clocks, etc.) cannot support a rejection.
        simple = re.sub(r"\b(?:posedge|negedge)\s+" + _IDENTIFIER, "EVENT", text[1:-1])
        simple = re.sub(r"\bEVENT\b|\bor\b|[,\s]", "", simple)
        if simple:
            if re.search(r"(?<![A-Za-z_0-9$])" + re.escape(name) + r"(?![A-Za-z_0-9$])", text):
                complex_clock = True
            continue
        for match in re.finditer(r"\b(posedge|negedge)\s+(" + _IDENTIFIER + r")\b", text):
            if match[2] == name:
                line = masked.count("\n", 0, offset + control.start()) + 1
                events.append((match[1], line))
    opposite = [(edge, line) for edge, line in events if edge != expected]
    if opposite:
        locations = ", ".join(str(line) for _, line in opposite)
        return False, (f"采样沿与规格冲突：{name} 要求 {expected}，顶层第 {locations} 行出现相反沿。"
                       "按题面保持复位、使能和输出时刻，只修正错误的时钟事件控制。")
    if complex_clock:
        return True, "not_checked: 时钟事件包含复杂表达式，需要 HDL 工具解析"
    if events:
        return True, f"matched: 顶层 {name} 的直接事件控制符合 {expected}"
    # A legal implementation may instantiate a register primitive or alias its clock.
    # Do not pretend this lightweight scan elaborates that hierarchy or follows aliases.
    if re.search(r"\b" + _IDENTIFIER + r"\s+(?:#\s*\([^;]*?\)\s*)?" + _IDENTIFIER + r"\s*\(", body):
        return True, "not_checked: 顶层含层级实例，不能由局部文本推断有效时钟"
    if re.search(r"(?<![A-Za-z_0-9$])" + re.escape(name) + r"(?![A-Za-z_0-9$])", body):
        return True, "not_checked: 时钟可能通过别名或复杂事件使用，需要完整 HDL 工具解析"
    return False, f"未发现顶层 {name} 的 {expected} 有效沿事件控制；按规格实现时序状态，不能用组合逻辑代替。"
