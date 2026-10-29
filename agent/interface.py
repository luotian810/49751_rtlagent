"""轻量接口检查：确定的错误才拦截，不冒充完整 HDL 解析器。"""
from __future__ import annotations

import re


def without_comments(text: str) -> str:
    return re.sub(r"//[^\n]*|/\*.*?\*/", "", text, flags=re.S)


def _code_only(text: str) -> str:
    """遮住注释和字符串，但保留字符位置，避免把其中的 module 当作声明。"""
    pattern = r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"'
    return re.sub(pattern, lambda m: re.sub(r"[^\n]", " ", m.group()), text, flags=re.S)


_DECLARATION = re.compile(
    r"\bmodule\s+(?:(?:automatic|static)\s+)?([A-Za-z_]\w*)\s*(?=[#(;])"
)


def _declared_names(text: str) -> set[str]:
    return set(_DECLARATION.findall(_code_only(text)))


def infer_top(prompt: str, interface: str = "") -> str:
    # 明确接口优先；多个不同模块不能仅因出现顺序就把辅助模块当作顶层。
    declared = _declared_names(interface)
    if len(declared) == 1:
        return next(iter(declared))
    named = re.search(r"module\s+named\s+[`\"']?([A-Za-z_]\w*)", prompt, re.I)
    if named:
        return named.group(1)
    declared = _declared_names(prompt)
    return next(iter(declared)) if len(declared) == 1 else "TopModule"


def strip_think(text: str) -> str:
    """与官方基线同语义：剥离推理草稿，截断在思考中的回复不当作答案。"""
    # 模型模板可能已预填 <think>，因此只有结束标记时也要丢弃此前内容。
    if "</think>" in text:
        return text.rsplit("</think>", 1)[1]
    if "<think>" in text:
        return text.split("<think>", 1)[0]
    return text


def extract_verilog(reply: str, top: str) -> str:
    """保留完整目标与辅助模块；模块边界检查不能代替 HDL 编译。"""
    reply = strip_think(reply)
    blocks = re.findall(r"```(?:systemverilog|verilog|sv|v)?\s*\n(.*?)```", reply, re.S | re.I)
    matching = [b for b in blocks if top in _declared_names(b)]
    if blocks and not matching:
        return ""
    text = max(matching, key=len) if matching else reply
    clean = _code_only(text)
    if top not in _declared_names(text):
        return ""
    if not blocks:
        # 无围栏或围栏未闭合时可提取完整 HDL，但不能先裁掉截断的辅助模块。
        begin = re.search(r"(?m)^\s*(?:`\w+|module\s+)", clean)
        ends = list(re.finditer(r"\bendmodule\b(?:\s*:\s*[A-Za-z_]\w*)?", clean))
        if not begin or not ends:
            return ""
        end = ends[-1].end()
        tail = clean[end:]
        if _DECLARATION.search(tail) or re.search(r"(?m)^\s*module\b", tail):
            return ""
        text = text[begin.start():end]
        clean = _code_only(text)
    # 单纯查找任意 endmodule 会把“完整辅助模块 + 截断顶层”误当完整答案。
    # 不处理预处理器分支或模块内部语法，交给实际编译器判定。
    opened = False
    for token in re.finditer(r"\b(?:module|endmodule)\b", clean):
        if token.group() == "module":
            if opened:
                return ""
            opened = True
        else:
            if not opened:
                return ""
            opened = False
    if opened:
        return ""
    return text.strip() + "\n"


def _prompt_port_details(prompt: str, top: str) -> dict | None:
    """只读取明确的模块签名；同名签名有歧义时不升级为严格检查。"""
    clean = _code_only(prompt)
    signatures = []
    for declaration in _DECLARATION.finditer(clean):
        if declaration.group(1) != top:
            continue
        depth = 0
        complete = False
        for position in range(declaration.end(), len(clean)):
            char = clean[position]
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            elif char == ";" and depth == 0:
                signature = prompt[declaration.start():position + 1]
                ports = _port_details(signature + "\nendmodule", top)
                if ports is None:
                    return None
                signatures.append(ports)
                complete = True
                break
            if depth < 0:
                return None
        if not complete:
            return None
    if signatures and all(ports == signatures[0] for ports in signatures):
        return signatures[0]
    return None


def _port_details(source: str, top: str) -> dict | None:
    """支持常见 ANSI/非 ANSI 端口；参数化范围宽度标记 unknown。"""
    text = without_comments(source)
    match = re.search(rf"\bmodule\s+(?:(?:automatic|static)\s+)?{re.escape(top)}\s*(?:#\s*\(.*?\)\s*)?\((.*?)\)\s*;(.*?)\bendmodule\b", text, re.S)
    if not match:
        return None
    header, body = match.groups()
    entries = header.split(",")
    if not re.search(r"\b(input|output|inout)\b", header):
        entries = re.findall(r"\b(?:input|output|inout)\b[^;]*", body)
        entries = [part for decl in entries for part in decl.split(",")]
    ports = {}
    direction, width, signed = None, 1, False
    for entry in entries:
        entry = entry.strip()
        # 将范围遮住而不是删除，保留端口名位置，以区分 packed 与 unpacked。
        declaration = entry.split("=")[0]
        masked = re.sub(r"\[[^]]*\]", lambda m: " " * len(m.group()), declaration)
        names = list(re.finditer(r"[A-Za-z_]\w*", masked))
        if not names:
            continue
        name = names[-1]
        prefix = declaration[:name.start()]
        explicit = re.match(r"(input|output|inout)\b", entry)
        if explicit:
            direction = explicit.group(1)
            type_words = re.findall(r"[A-Za-z_]\w*", masked[:name.start()])[1:]
            atom_widths = {"byte": 8, "shortint": 16, "int": 32,
                           "integer": 32, "longint": 64, "time": 64}
            qualifiers = {"wire", "reg", "logic", "bit", "signed", "unsigned", "var"}
            types = [word for word in type_words if word not in qualifiers]
            # 用户类型/复杂类型的宽度无法可靠推断，不按标量硬拦截。
            width = atom_widths.get(types[0]) if len(types) == 1 else (1 if not types else None)
            signed = (bool(types) and types[0] in {"byte", "shortint", "int", "integer", "longint"})
            if "signed" in type_words:
                signed = True
            if "unsigned" in type_words:
                signed = False
        for rng in re.findall(r"\[([^]]*)\]", prefix):
            try:
                left, right = rng.split(":")
                dimension = abs(int(left) - int(right)) + 1
                width = width * dimension if width is not None else None
            except ValueError:
                width = None
        if "[" in declaration[name.end():]:
            # unpacked 数组的形状不属于这个轻量 packed 位宽比较器。
            width = None
        if direction:
            if name.group() in ports:
                return None
            ports[name.group()] = (direction, width, signed)
    return ports or None


def _port_map(source: str, top: str) -> dict[str, tuple[str, int | None]] | None:
    details = _port_details(source, top)
    return {name: item[:2] for name, item in details.items()} if details else None


def _prompt_port_map(prompt: str, top: str) -> dict[str, tuple[str, int | None]] | None:
    details = _prompt_port_details(prompt, top)
    return {name: item[:2] for name, item in details.items()} if details else None


def _listed_port_details(prompt: str, top: str) -> dict | None:
    """Read an explicitly introduced, complete port list; never infer a partial one.

    Missing widths require the local one-bit default sentence. Other prose,
    parameter expressions, repeated interfaces and malformed records abstain.
    HDL signatures always take precedence over this restricted prose grammar.
    """
    named = re.findall(r"\bmodule\s+named\s+[`\"']?([A-Za-z_]\w*)", prompt, re.I)
    if named != [top] or _DECLARATION.search(_code_only(prompt)):
        return None
    introduction = re.search(
        r"\bmodule\s+named\s+[`\"']?" + re.escape(top) +
        r"[`\"']?\s+with\s+the\s+following\s+interface\s*[.:]", prompt, re.I)
    if not introduction:
        return None
    lines = prompt[introduction.end():].splitlines()
    first = next((i for i, line in enumerate(lines) if line.lstrip().startswith('-')), None)
    if first is None:
        return None
    preamble = ' '.join(' '.join(lines[:first]).split())
    scalar_default = bool(re.fullmatch(
        r"All input and output ports are one bit unless otherwise specified\.", preamble, re.I))
    if preamble and not scalar_default:
        return None
    records, remainder = [], []
    for i in range(first, len(lines)):
        line = lines[i].strip()
        if not line:
            continue
        if not line.startswith('-'):
            remainder = lines[i:]
            break
        records.append(line)
    # A second list or an unbulleted port may mean that the interface is partial.
    # Body prose can begin with "input ... is sampled". Reject declaration-like
    # whole lines and later bullet ports without treating that prose as a port.
    if any(re.match(r"\s*[-*+]\s*(?:input|output|inout)\b", line, re.I)
           or re.fullmatch(r"\s*(?:input|output|inout)\s+(?:(?:signed|unsigned)\s+)?"
                           r"[A-Za-z_]\w*(?:\s*\([^)]*\))?\s*[,;]?\s*", line, re.I)
           for line in remainder):
        return None
    if not 1 <= len(records) <= 64:
        return None
    ports = {}
    for line in records:
        match = re.fullmatch(
            r"-\s*(input|output)\s+(?:(signed|unsigned)\s+)?([A-Za-z_]\w*)"
            r"\s*(?:\(\s*([0-9]+)\s*(?:bits?|位)\s*\))?\s*,?", line)
        if not match:
            return None
        direction, sign, name, width = match.groups()
        if name in ports or (width is None and not scalar_default):
            return None
        width = int(width) if width is not None else 1
        if not 1 <= width <= 4096:
            return None
        ports[name] = (direction, width, sign == 'signed')
    return ports


def _specification_details(prompt: str, interface: str, top: str) -> dict | None:
    if interface.strip():
        return _port_details(interface + "\nendmodule", top)
    if _DECLARATION.search(_code_only(prompt)):
        return _prompt_port_details(prompt, top)
    return _listed_port_details(prompt, top)


def specification_ports(prompt: str, interface: str, top: str) -> list[dict] | None:
    """从无歧义签名或明确完整端口列表取得类型；未知位宽不猜为标量。"""
    details = _specification_details(prompt, interface, top)
    if not details or any(direction not in ("input", "output") or width is None
                          or not 1 <= width <= 4096 for direction, width, signed in details.values()):
        return None
    return [dict(name=name, direction=direction, width=width, signed=signed)
            for name, (direction, width, signed) in details.items()]


def check_interface(source: str, prompt: str, interface: str, top: str) -> tuple[bool, str]:
    if top not in _declared_names(source):
        return False, f"找不到要求的顶层模块 {top}"
    got = _port_details(source, top)
    # 明确完整接口共用生成验证计划时的解析；其他文字仍只给提示。
    want = _specification_details(prompt, interface, top)
    strict = want is not None
    if want is None:
        entries = re.findall(r"^\s*-\s*(input|output|inout)\s+(\w+)\s*,?\s*(?:\(\s*(\d+)\s*(?:bits?|位)\s*\))?\s*$", prompt, re.M)
        want = {name: (direction, int(width) if width else 1, False) for direction, name, width in entries}
    if not want or not got:
        return True, "接口文本不能可靠解析，已跳过端口检查；后续编译不等同于接口正确"
    issues = []
    for name in want.keys() - got.keys():
        issues.append(f"缺少端口 {name}")
    for name in got.keys() - want.keys():
        issues.append(f"多出端口 {name}")
    for name in want.keys() & got.keys():
        wd, ww, ws = want[name]
        gd, gw, gs = got[name]
        # Unknown types/packed widths also make signedness inference unreliable.
        known_types = ww is not None and gw is not None
        if wd != gd or (known_types and ww != gw) or (strict and known_types and ws != gs):
            issues.append(f"端口 {name}: 期望 {wd}[{ww}] signed={ws}，实际 {gd}[{gw}] signed={gs}")
    if issues:
        return (not strict), ("接口错误：" if strict else "接口提示（以完整题意为准）：") + "; ".join(issues)
    return True, "端口清单匹配（仅静态检查）"
